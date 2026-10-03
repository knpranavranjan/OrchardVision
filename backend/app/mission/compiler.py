"""Turns a mission plan into the flat item list the autopilot executes, plus estimates.

Compilation is deterministic: the same plan always gives the same items. Only the
items are uploaded, and validation runs on them, not on the plan.
"""

import math

from pydantic import BaseModel

from app.core.conventions import LocalFrame
from app.core.geometry import Point, polygon_area
from app.mission.schema import EndAction, MissionPlan, MissionType
from app.mission.survey import SurveyLayout, plan_survey
from app.vehicle.link import MissionItem, MissionItemKind

K = MissionItemKind


class Estimate(BaseModel):
    distance_m: float
    time_s: float
    battery_pct: float
    photos: int


class FlightSegment(BaseModel):
    """One battery's worth of the mission."""

    index: int
    items: list[MissionItem]
    first_line: int | None = None
    last_line: int | None = None
    estimate: Estimate


class MissionStats(BaseModel):
    area_ha: float = 0.0
    distance_m: float = 0.0
    time_s: float = 0.0
    battery_pct: float = 0.0
    photos: int = 0
    storage_mb: float = 0.0
    gsd_cm: float | None = None
    footprint_across_m: float | None = None
    footprint_along_m: float | None = None
    line_spacing_m: float | None = None
    trigger_distance_m: float | None = None
    lines: int = 0
    max_alt_m: float = 0.0
    item_count: int = 0
    flights_needed: int = 1


class CompiledMission(BaseModel):
    items: list[MissionItem]
    route: list[tuple[float, float, float]]  # lat, lon, height: the path to draw
    lines: list[tuple[tuple[float, float], tuple[float, float]]]
    capture_points: list[tuple[float, float]]
    stats: MissionStats
    segments: list[FlightSegment]


def _r7(x: float) -> float:
    # The autopilot stores degrees as integers of 1e-7, so plan to that precision.
    return round(x, 7)


class _Builder:
    def __init__(self) -> None:
        self.items: list[MissionItem] = []

    def add(self, kind: MissionItemKind, **fields: float) -> None:
        self.items.append(MissionItem(seq=len(self.items), kind=kind, **fields))

    def waypoint(self, frame: LocalFrame, p: Point, alt: float, hold_s: float = 0.0) -> None:
        lat, lon = frame.to_latlon(*p)
        self.add(K.WAYPOINT, lat=_r7(lat), lon=_r7(lon), alt_rel_m=round(alt, 2), value=hold_s)


def _survey_items(
    plan: MissionPlan, frame: LocalFrame, lines: list[tuple[Point, Point]], trigger: float
) -> list[MissionItem]:
    s = plan.survey
    b = _Builder()
    b.add(K.TAKEOFF, alt_rel_m=round(plan.takeoff_alt_m, 2))
    b.add(K.SET_SPEED, value=s.speed_mps)
    b.add(K.GIMBAL_PITCH, value=s.gimbal_pitch_deg)
    for start, end in lines:
        b.waypoint(frame, start, s.altitude_m)
        b.add(K.CAMERA_TRIGGER_DISTANCE, value=round(trigger, 2))
        b.waypoint(frame, end, s.altitude_m)
        b.add(K.CAMERA_TRIGGER_DISTANCE, value=0.0)
    _finish(b, plan, frame, s.altitude_m)
    return b.items


def _waypoint_items(plan: MissionPlan, frame: LocalFrame) -> list[MissionItem]:
    b = _Builder()
    b.add(K.TAKEOFF, alt_rel_m=round(plan.takeoff_alt_m, 2))
    b.add(K.SET_SPEED, value=plan.waypoint_speed_mps)
    b.add(K.GIMBAL_PITCH, value=plan.waypoint_gimbal_pitch_deg)
    capturing = plan.waypoint_capture_distance_m > 0
    if capturing:
        b.add(K.CAMERA_TRIGGER_DISTANCE, value=round(plan.waypoint_capture_distance_m, 2))
    last_alt = plan.takeoff_alt_m
    for w in plan.waypoints:
        if w.speed_mps:
            b.add(K.SET_SPEED, value=w.speed_mps)
        b.add(
            K.WAYPOINT,
            lat=_r7(w.lat),
            lon=_r7(w.lon),
            alt_rel_m=round(w.alt_m, 2),
            value=w.hold_s,
        )
        last_alt = w.alt_m
    if capturing:
        b.add(K.CAMERA_TRIGGER_DISTANCE, value=0.0)
    _finish(b, plan, frame, last_alt)
    return b.items


def _finish(b: _Builder, plan: MissionPlan, frame: LocalFrame, alt: float) -> None:
    if plan.end_action == EndAction.RTL:
        b.add(K.RTL)
    else:
        b.waypoint(frame, (0.0, 0.0), alt)
        b.add(K.LAND)


def estimate(items: list[MissionItem], plan: MissionPlan, frame: LocalFrame) -> Estimate:
    """Distance, time, battery and photo count from the items alone."""
    v = plan.vehicle
    e = n = z = 0.0
    speed = v.cruise_speed_mps
    trigger = 0.0
    distance = time_s = 0.0
    photos = 0

    def leg(te: float, tn: float, tz: float) -> None:
        nonlocal e, n, z, distance, time_s, photos
        d = math.hypot(te - e, tn - n)
        dz = tz - z
        vertical = abs(dz) / (v.climb_rate_mps if dz > 0 else v.descent_rate_mps)
        time_s += max(d / max(speed, 0.1), vertical)
        distance += d
        if trigger > 0 and d > 0:
            photos += int((d + 1e-3) // trigger) + 1
        e, n, z = te, tn, tz

    for item in items:
        if item.kind == K.TAKEOFF:
            leg(e, n, item.alt_rel_m or 0.0)
        elif item.kind == K.WAYPOINT:
            te, tn = frame.to_en(item.lat, item.lon)
            leg(te, tn, item.alt_rel_m if item.alt_rel_m is not None else z)
            time_s += v.turn_time_s + item.value
        elif item.kind == K.SET_SPEED:
            speed = item.value
        elif item.kind == K.CAMERA_TRIGGER_DISTANCE:
            trigger = item.value
        elif item.kind == K.RTL:
            trigger = 0.0
            leg(e, n, max(z, plan.safety.rtl_alt_m) if math.hypot(e, n) > 2 else z)
            leg(0.0, 0.0, z)
            leg(0.0, 0.0, 0.0)
        elif item.kind == K.LAND:
            trigger = 0.0
            leg(e, n, 0.0)

    return Estimate(
        distance_m=round(distance, 1),
        time_s=round(time_s, 1),
        battery_pct=round(time_s / (v.endurance_min * 60.0) * 100.0, 1),
        photos=photos,
    )


def _route(items: list[MissionItem], plan: MissionPlan) -> list[tuple[float, float, float]]:
    home = (plan.home.lat, plan.home.lon)
    route = [(*home, 0.0)]
    alt = 0.0
    for item in items:
        if item.kind == K.TAKEOFF:
            alt = item.alt_rel_m or 0.0
            route.append((*home, alt))
        elif item.kind == K.WAYPOINT:
            alt = item.alt_rel_m if item.alt_rel_m is not None else alt
            route.append((item.lat, item.lon, alt))
        elif item.kind == K.RTL:
            route.append((*home, alt))
    return route


def _split(
    plan: MissionPlan, frame: LocalFrame, layout: SurveyLayout, budget_pct: float
) -> list[FlightSegment]:
    """Greedy split of survey lines into flights that each fit the battery budget."""
    segments: list[FlightSegment] = []
    first = 0
    total = len(layout.lines)
    while first < total:
        last = first
        items = _survey_items(
            plan, frame, layout.lines[first : last + 1], layout.trigger_distance_m
        )
        est = estimate(items, plan, frame)
        while last + 1 < total:
            trial = _survey_items(
                plan, frame, layout.lines[first : last + 2], layout.trigger_distance_m
            )
            trial_est = estimate(trial, plan, frame)
            if trial_est.battery_pct > budget_pct:
                break
            last, items, est = last + 1, trial, trial_est
        segments.append(
            FlightSegment(
                index=len(segments), items=items, first_line=first, last_line=last, estimate=est
            )
        )
        first = last + 1
    return segments


def compile_plan(plan: MissionPlan) -> CompiledMission:
    frame = LocalFrame(plan.home.lat, plan.home.lon)
    stats = MissionStats()
    lines_ll: list[tuple[tuple[float, float], tuple[float, float]]] = []
    captures_ll: list[tuple[float, float]] = []
    layout: SurveyLayout | None = None

    if plan.type == MissionType.SURVEY and plan.survey and len(plan.survey.polygon) >= 3:
        polygon = [frame.to_en(p.lat, p.lon) for p in plan.survey.polygon]
        layout = plan_survey(polygon, plan.survey, plan.camera, start_near=(0.0, 0.0))
        items = _survey_items(plan, frame, layout.lines, layout.trigger_distance_m)
        lines_ll = [(frame.to_latlon(*a), frame.to_latlon(*b)) for a, b in layout.lines]
        captures_ll = [frame.to_latlon(*p) for p in layout.capture_points]
        stats.area_ha = round(polygon_area(polygon) / 10_000.0, 3)
        stats.gsd_cm = round(layout.gsd_cm, 2)
        stats.footprint_across_m = round(layout.footprint_m[0], 1)
        stats.footprint_along_m = round(layout.footprint_m[1], 1)
        stats.line_spacing_m = round(layout.line_spacing_m, 2)
        stats.trigger_distance_m = round(layout.trigger_distance_m, 2)
        stats.lines = len(layout.lines)
    elif plan.type == MissionType.WAYPOINTS and plan.waypoints:
        items = _waypoint_items(plan, frame)
        stats.gsd_cm = round(plan.camera.gsd_cm(max(w.alt_m for w in plan.waypoints)), 2)
    else:
        items = []

    est = (
        estimate(items, plan, frame)
        if items
        else Estimate(distance_m=0, time_s=0, battery_pct=0, photos=0)
    )
    stats.distance_m = est.distance_m
    stats.time_s = est.time_s
    stats.battery_pct = est.battery_pct
    stats.photos = len(captures_ll) if captures_ll else est.photos
    stats.storage_mb = round(stats.photos * plan.camera.image_mb, 1)
    stats.max_alt_m = max((i.alt_rel_m or 0.0 for i in items), default=0.0)
    stats.item_count = len(items)

    budget = 100.0 - plan.safety.battery_reserve_pct
    whole = FlightSegment(
        index=0,
        items=items,
        first_line=0 if layout and layout.lines else None,
        last_line=len(layout.lines) - 1 if layout and layout.lines else None,
        estimate=est,
    )
    segments = [whole]
    if layout and layout.lines and est.battery_pct > budget:
        segments = _split(plan, frame, layout, budget)
    stats.flights_needed = len(segments)

    return CompiledMission(
        items=items,
        route=_route(items, plan),
        lines=lines_ll,
        capture_points=captures_ll,
        stats=stats,
        segments=segments,
    )
