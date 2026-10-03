"""Mission validation. Every check is reported; any failure blocks upload."""

import shutil
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel

from app.core.conventions import LocalFrame
from app.core.geometry import (
    distance_to_polygon_edge,
    is_simple_polygon,
    point_in_polygon,
    segment_inside_polygon,
)
from app.mission.compiler import CompiledMission
from app.mission.schema import MissionPlan, MissionType
from app.vehicle.link import MissionItemKind

MAX_ITEMS = 700  # ArduPilot's default mission storage on a Pixhawk-class board
FENCE_MARGIN_M = 3.0


class Status(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class Check(BaseModel):
    id: str
    label: str
    status: Status
    detail: str = ""


class Validation(BaseModel):
    ok: bool
    checks: list[Check]


class CropContext(BaseModel):
    """What validation needs to know about the orchard's crop and its models."""

    crop: str
    min_gsd_cm: float | None = None
    models_ready: bool = True
    models_detail: str = ""


def validate_plan(
    plan: MissionPlan,
    compiled: CompiledMission,
    crop: CropContext | None = None,
    data_dir: Path | None = None,
) -> Validation:
    checks: list[Check] = []

    def add(id_: str, label: str, status: Status, detail: str = "") -> None:
        checks.append(Check(id=id_, label=label, status=status, detail=detail))

    frame = LocalFrame(plan.home.lat, plan.home.lon)
    stats = compiled.stats
    s = plan.safety

    # --- geometry of what the operator drew
    if plan.type == MissionType.SURVEY:
        poly = [frame.to_en(p.lat, p.lon) for p in (plan.survey.polygon if plan.survey else [])]
        if len(poly) < 3:
            add("area", "Survey area", Status.FAIL, "Draw an area with at least three corners.")
        elif not is_simple_polygon(poly):
            add("area", "Survey area", Status.FAIL, "The area's edges cross each other.")
        elif stats.lines == 0:
            add("area", "Survey area", Status.FAIL, "The area is too small for a flight line.")
        else:
            add("area", "Survey area", Status.PASS, f"{stats.area_ha:.2f} ha, {stats.lines} lines")
    else:
        if not plan.waypoints:
            add("route", "Waypoints", Status.FAIL, "Add at least one waypoint.")
        else:
            add("route", "Waypoints", Status.PASS, f"{len(plan.waypoints)} waypoints")

    if not compiled.items:
        add("items", "Mission items", Status.FAIL, "Nothing to fly yet.")
        return Validation(ok=False, checks=checks)

    # --- geofence
    fence = [frame.to_en(p.lat, p.lon) for p in plan.geofence]
    if not s.fence_enabled:
        add("fence", "Geofence", Status.WARN, "The geofence is switched off.")
    elif len(fence) < 3:
        add("fence", "Geofence", Status.FAIL, "Draw a geofence, or switch it off in Safety.")
    elif not is_simple_polygon(fence):
        add("fence", "Geofence", Status.FAIL, "The geofence's edges cross each other.")
    else:
        points = [frame.to_en(lat, lon) for lat, lon, _ in compiled.route]
        outside = [p for p in points if not point_in_polygon(p, fence)]
        crossing = any(
            not segment_inside_polygon(points[i], points[i + 1], fence)
            for i in range(len(points) - 1)
        )
        if not point_in_polygon((0.0, 0.0), fence):
            add("fence", "Geofence", Status.FAIL, "The home point is outside the geofence.")
        elif outside:
            add(
                "fence",
                "Geofence",
                Status.FAIL,
                f"{len(outside)} route points are outside the geofence.",
            )
        elif crossing:
            add("fence", "Geofence", Status.FAIL, "The route leaves the geofence between points.")
        else:
            margin = min(distance_to_polygon_edge(p, fence) for p in points)
            if margin < FENCE_MARGIN_M:
                add(
                    "fence",
                    "Geofence",
                    Status.WARN,
                    f"The route passes {margin:.1f} m from the geofence; GPS error may trip it.",
                )
            else:
                add("fence", "Geofence", Status.PASS, f"Route stays {margin:.0f} m inside")

    # --- height and speed limits
    alts = [i.alt_rel_m for i in compiled.items if i.alt_rel_m is not None]
    if s.rtl_alt_m > s.max_alt_m:
        add(
            "altitude",
            "Height limits",
            Status.FAIL,
            f"The return height ({s.rtl_alt_m:g} m) is above the {s.max_alt_m:g} m limit.",
        )
    elif max(alts) > s.max_alt_m:
        add(
            "altitude",
            "Height limits",
            Status.FAIL,
            f"{max(alts):g} m is above the {s.max_alt_m:g} m limit.",
        )
    elif min(alts) < s.min_alt_m:
        add(
            "altitude",
            "Height limits",
            Status.FAIL,
            f"{min(alts):g} m is below the {s.min_alt_m:g} m limit.",
        )
    else:
        add("altitude", "Height limits", Status.PASS, f"{min(alts):g} to {max(alts):g} m")

    speeds = [i.value for i in compiled.items if i.kind == MissionItemKind.SET_SPEED]
    top = max(speeds, default=plan.vehicle.cruise_speed_mps)
    limit = min(s.max_speed_mps, plan.vehicle.max_speed_mps)
    if top > limit:
        add("speed", "Speed limit", Status.FAIL, f"{top:g} m/s is above the {limit:g} m/s limit.")
    else:
        add("speed", "Speed limit", Status.PASS, f"up to {top:g} m/s")

    # --- camera and image detail
    if plan.type == MissionType.SURVEY and stats.gsd_cm is not None:
        if stats.trigger_distance_m and plan.survey and plan.survey.speed_mps:
            interval = stats.trigger_distance_m / plan.survey.speed_mps
            if interval < 0.8:
                add(
                    "camera",
                    "Camera interval",
                    Status.WARN,
                    f"One photo every {interval:.1f} s; many cameras cannot keep up. "
                    "Fly slower or higher.",
                )
            else:
                add("camera", "Camera interval", Status.PASS, f"one photo every {interval:.1f} s")
        if crop and crop.min_gsd_cm is not None:
            if stats.gsd_cm > crop.min_gsd_cm:
                add(
                    "gsd",
                    "Image detail",
                    Status.FAIL,
                    f"{stats.gsd_cm:.2f} cm per pixel is too coarse for the {crop.crop} "
                    f"tree model (needs {crop.min_gsd_cm:g} cm or finer). Fly lower.",
                )
            else:
                add("gsd", "Image detail", Status.PASS, f"{stats.gsd_cm:.2f} cm per pixel")
        else:
            add("gsd", "Image detail", Status.PASS, f"{stats.gsd_cm:.2f} cm per pixel")

    # --- time and battery
    budget = 100.0 - s.battery_reserve_pct
    minutes = stats.time_s / 60.0
    if stats.battery_pct <= budget:
        add(
            "battery",
            "Battery",
            Status.PASS,
            f"{minutes:.1f} min, about {stats.battery_pct:.0f}% of a battery "
            f"({s.battery_reserve_pct:g}% reserve kept)",
        )
    elif stats.flights_needed > 1:
        worst = max(seg.estimate.battery_pct for seg in compiled.segments)
        status = Status.WARN if worst <= budget else Status.FAIL
        add(
            "battery",
            "Battery",
            status,
            f"Needs {stats.battery_pct:.0f}% of a battery with a {s.battery_reserve_pct:g}% "
            f"reserve. Split into {stats.flights_needed} flights; upload them one at a time.",
        )
    else:
        add(
            "battery",
            "Battery",
            Status.FAIL,
            f"Needs {stats.battery_pct:.0f}% of a battery; only {budget:.0f}% is usable "
            "with the reserve. Shorten the route.",
        )

    # --- storage on this computer
    if data_dir is not None and stats.storage_mb:
        probe = data_dir if data_dir.exists() else data_dir.parent
        free_mb = shutil.disk_usage(probe).free / 1e6
        if free_mb < stats.storage_mb * 2:
            add(
                "storage",
                "Storage",
                Status.FAIL,
                f"Needs {stats.storage_mb:.0f} MB; {free_mb:.0f} MB free.",
            )
        else:
            add("storage", "Storage", Status.PASS, f"about {stats.storage_mb:.0f} MB of images")

    # --- return path and item count
    add("return", "Return path", Status.PASS, f"Ends with {plan.end_action.value.upper()} to home")
    if stats.item_count > MAX_ITEMS:
        add(
            "items",
            "Mission size",
            Status.FAIL,
            f"{stats.item_count} items; the autopilot holds {MAX_ITEMS}.",
        )
    else:
        add("items", "Mission size", Status.PASS, f"{stats.item_count} items")

    # --- models for the orchard's crop
    if crop is not None:
        add(
            "models",
            "AI models",
            Status.PASS if crop.models_ready else Status.FAIL,
            crop.models_detail or f"{crop.crop} models ready",
        )

    return Validation(ok=all(c.status != Status.FAIL for c in checks), checks=checks)
