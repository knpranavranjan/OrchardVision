"""Coverage planner: parallel flight lines over a polygon, in local metres."""

import math
from dataclasses import dataclass

from app.core.geometry import Point, rotate, scanline_segments
from app.mission.schema import CameraProfile, SurveySpec


@dataclass
class SurveyLayout:
    lines: list[tuple[Point, Point]]  # each flown from the first point to the second
    line_spacing_m: float
    trigger_distance_m: float
    gsd_cm: float
    footprint_m: tuple[float, float]
    capture_points: list[Point]


def plan_survey(
    polygon_en: list[Point], spec: SurveySpec, camera: CameraProfile, start_near: Point
) -> SurveyLayout:
    across, along = camera.footprint_m(spec.altitude_m)
    wanted_spacing = across * (1 - spec.side_overlap)
    trigger = along * (1 - spec.front_overlap)

    # Rotate so the flight direction lies along +x. angle_deg is a compass heading.
    theta = math.radians(90.0 - spec.angle_deg)
    poly = [rotate(p, -theta) for p in polygon_en]
    ys = [p[1] for p in poly]
    y_min, y_max = min(ys), max(ys)
    width = y_max - y_min

    # Fit a whole number of lines so both edges are covered and overlap is at least as asked.
    count = max(1, math.ceil(width / wanted_spacing)) if wanted_spacing > 0 else 1
    spacing = width / count

    rows: list[list[tuple[float, float, float]]] = []  # per row: (y, x_start, x_end)
    for i in range(count):
        y = y_min + spacing * (i + 0.5)
        segments = scanline_segments(poly, y)
        if segments:
            rows.append([(y, x0 - spec.overshoot_m, x1 + spec.overshoot_m) for x0, x1 in segments])

    def serpentine(ordered: list[list[tuple[float, float, float]]], flip: bool):
        out: list[tuple[Point, Point]] = []
        for index, row in enumerate(ordered):
            reverse = (index % 2 == 1) != flip
            for y, x0, x1 in reversed(row) if reverse else row:
                out.append(((x1, y), (x0, y)) if reverse else ((x0, y), (x1, y)))
        return out

    start = rotate(start_near, -theta)
    candidates = [
        serpentine(rows, False),
        serpentine(rows, True),
        serpentine(rows[::-1], False),
        serpentine(rows[::-1], True),
    ]
    best = min(candidates, key=lambda c: math.dist(c[0][0], start) if c else math.inf)

    lines = [(rotate(a, theta), rotate(b, theta)) for a, b in best]
    captures: list[Point] = []
    for a, b in lines:
        length = math.dist(a, b)
        # A millimetre of slack so a 60.000 m line is not counted as 59.999 m.
        steps = int((length + 1e-3) // trigger) if trigger > 0 else 0
        for k in range(steps + 1):
            t = (k * trigger) / length if length > 0 else 0.0
            captures.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))

    return SurveyLayout(
        lines=lines,
        line_spacing_m=spacing,
        trigger_distance_m=trigger,
        gsd_cm=camera.gsd_cm(spec.altitude_m),
        footprint_m=(across, along),
        capture_points=captures,
    )
