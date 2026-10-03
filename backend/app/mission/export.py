"""Mission exports: QGroundControl plan, MAVLink waypoint file, KML."""

import json
from xml.sax.saxutils import escape

from app.mission.schema import MissionPlan
from app.vehicle.link import MissionItem, MissionItemKind

K = MissionItemKind

# MAVLink command numbers
NAV_WAYPOINT, NAV_RTL, NAV_LAND, NAV_TAKEOFF = 16, 20, 21, 22
DO_CHANGE_SPEED, DO_MOUNT_CONTROL, DO_SET_CAM_TRIGG_DIST = 178, 205, 206
FRAME_GLOBAL, FRAME_MISSION, FRAME_GLOBAL_RELATIVE_ALT = 0, 2, 3


def mav_fields(item: MissionItem) -> tuple[int, int, list[float]]:
    """(command, frame, [param1..param4, x, y, z]) for one item."""
    lat, lon, alt = item.lat or 0.0, item.lon or 0.0, item.alt_rel_m or 0.0
    if item.kind == K.TAKEOFF:
        return NAV_TAKEOFF, FRAME_GLOBAL_RELATIVE_ALT, [0, 0, 0, 0, 0, 0, alt]
    if item.kind == K.WAYPOINT:
        return NAV_WAYPOINT, FRAME_GLOBAL_RELATIVE_ALT, [item.value, 0, 0, 0, lat, lon, alt]
    if item.kind == K.SET_SPEED:
        return DO_CHANGE_SPEED, FRAME_MISSION, [1, item.value, -1, 0, 0, 0, 0]
    if item.kind == K.CAMERA_TRIGGER_DISTANCE:
        return DO_SET_CAM_TRIGG_DIST, FRAME_MISSION, [item.value, 0, 1, 0, 0, 0, 0]
    if item.kind == K.GIMBAL_PITCH:
        return DO_MOUNT_CONTROL, FRAME_MISSION, [item.value, 0, 0, 0, 0, 0, 2]
    if item.kind == K.RTL:
        return NAV_RTL, FRAME_GLOBAL_RELATIVE_ALT, [0, 0, 0, 0, 0, 0, 0]
    if item.kind == K.LAND:
        return NAV_LAND, FRAME_GLOBAL_RELATIVE_ALT, [0, 0, 0, 0, 0, 0, 0]
    raise ValueError(f"no MAVLink mapping for {item.kind}")


def to_qgc_plan(plan: MissionPlan, items: list[MissionItem]) -> str:
    mission_items = []
    for item in items:
        command, frame, p = mav_fields(item)
        mission_items.append(
            {
                "type": "SimpleItem",
                "autoContinue": True,
                "command": command,
                "frame": frame,
                "doJumpId": item.seq + 1,
                "params": [p[0], p[1], p[2], p[3], p[4] or None, p[5] or None, p[6]]
                if frame == FRAME_GLOBAL_RELATIVE_ALT
                else p,
            }
        )
    fence = [[p.lat, p.lon] for p in plan.geofence]
    doc = {
        "fileType": "Plan",
        "version": 1,
        "groundStation": "OrchardVision",
        "mission": {
            "version": 2,
            "firmwareType": 3,  # ArduPilot
            "vehicleType": 2,  # multirotor
            "cruiseSpeed": plan.vehicle.cruise_speed_mps,
            "hoverSpeed": plan.vehicle.cruise_speed_mps,
            "globalPlanAltitudeMode": 1,
            "plannedHomePosition": [plan.home.lat, plan.home.lon, 0],
            "items": mission_items,
        },
        "geoFence": {
            "version": 2,
            "circles": [],
            "polygons": [{"inclusion": True, "version": 1, "polygon": fence}] if fence else [],
        },
        "rallyPoints": {"version": 2, "points": []},
    }
    return json.dumps(doc, indent=2)


def to_waypoints(plan: MissionPlan, items: list[MissionItem]) -> str:
    """The plain-text format Mission Planner and MAVProxy read."""
    rows = [
        "QGC WPL 110",
        f"0\t1\t0\t16\t0\t0\t0\t0\t{plan.home.lat:.7f}\t{plan.home.lon:.7f}\t0\t1",
    ]
    for item in items:
        command, frame, p = mav_fields(item)
        rows.append(
            f"{item.seq + 1}\t0\t{frame}\t{command}\t{p[0]:g}\t{p[1]:g}\t{p[2]:g}\t{p[3]:g}"
            f"\t{p[4]:.7f}\t{p[5]:.7f}\t{p[6]:g}\t1"
        )
    return "\n".join(rows) + "\n"


def to_kml(name: str, plan: MissionPlan, route: list[tuple[float, float, float]]) -> str:
    def ring(points: list[tuple[float, float]]) -> str:
        closed = points + points[:1]
        return " ".join(f"{lon:.7f},{lat:.7f},0" for lat, lon in closed)

    path = " ".join(f"{lon:.7f},{lat:.7f},{alt:.1f}" for lat, lon, alt in route)
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
        f"<name>{escape(name)}</name>",
        "<Placemark><name>Home</name><Point><coordinates>"
        f"{plan.home.lon:.7f},{plan.home.lat:.7f},0</coordinates></Point></Placemark>",
        "<Placemark><name>Route</name><LineString><altitudeMode>relativeToGround</altitudeMode>"
        f"<coordinates>{path}</coordinates></LineString></Placemark>",
    ]
    if plan.survey and len(plan.survey.polygon) >= 3:
        pts = [p.tuple() for p in plan.survey.polygon]
        parts.append(
            "<Placemark><name>Survey area</name><Polygon><outerBoundaryIs><LinearRing>"
            f"<coordinates>{ring(pts)}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>"
        )
    if len(plan.geofence) >= 3:
        pts = [p.tuple() for p in plan.geofence]
        parts.append(
            "<Placemark><name>Geofence</name><Polygon><outerBoundaryIs><LinearRing>"
            f"<coordinates>{ring(pts)}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>"
        )
    parts.append("</Document></kml>")
    return "\n".join(parts) + "\n"
