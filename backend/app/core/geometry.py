"""Plane geometry in local east-north metres. Polygons are lists of (x, y), not closed."""

import math

Point = tuple[float, float]


def polygon_area(poly: list[Point]) -> float:
    """Unsigned area by the shoelace formula."""
    s = 0.0
    for i, (x1, y1) in enumerate(poly):
        x2, y2 = poly[(i + 1) % len(poly)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def polygon_centroid(poly: list[Point]) -> Point:
    a = cx = cy = 0.0
    for i, (x1, y1) in enumerate(poly):
        x2, y2 = poly[(i + 1) % len(poly)]
        cross = x1 * y2 - x2 * y1
        a += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if abs(a) < 1e-12:
        n = len(poly)
        return sum(p[0] for p in poly) / n, sum(p[1] for p in poly) / n
    return cx / (3 * a), cy / (3 * a)


def point_in_polygon(p: Point, poly: list[Point]) -> bool:
    """Ray casting. Points exactly on an edge may fall either way."""
    x, y = p
    inside = False
    for i, (x1, y1) in enumerate(poly):
        x2, y2 = poly[(i + 1) % len(poly)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def distance_to_segment(p: Point, a: Point, b: Point) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 == 0:
        return math.dist(p, a)
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / length2))
    return math.dist(p, (ax + t * dx, ay + t * dy))


def distance_to_polygon_edge(p: Point, poly: list[Point]) -> float:
    return min(distance_to_segment(p, a, poly[(i + 1) % len(poly)]) for i, a in enumerate(poly))


def _segments_cross(a: Point, b: Point, c: Point, d: Point) -> bool:
    def orient(p: Point, q: Point, r: Point) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    return (o1 * o2 < 0) and (o3 * o4 < 0)


def is_simple_polygon(poly: list[Point]) -> bool:
    """True when no two non-adjacent edges cross."""
    n = len(poly)
    if n < 3:
        return False
    for i in range(n):
        for j in range(i + 1, n):
            if j == i or (j + 1) % n == i or (i + 1) % n == j:
                continue
            if _segments_cross(poly[i], poly[(i + 1) % n], poly[j], poly[(j + 1) % n]):
                return False
    return True


def segment_inside_polygon(a: Point, b: Point, poly: list[Point], samples: int = 12) -> bool:
    """Whether the straight path from a to b stays inside the polygon (sampled)."""
    return all(
        point_in_polygon(
            (a[0] + (b[0] - a[0]) * t / samples, a[1] + (b[1] - a[1]) * t / samples), poly
        )
        for t in range(samples + 1)
    )


def rotate(p: Point, angle_rad: float) -> Point:
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    return p[0] * c - p[1] * s, p[0] * s + p[1] * c


def scanline_segments(poly: list[Point], y: float) -> list[tuple[float, float]]:
    """Intervals of x where the horizontal line at y lies inside the polygon."""
    xs = []
    for i, (x1, y1) in enumerate(poly):
        x2, y2 = poly[(i + 1) % len(poly)]
        if (y1 > y) != (y2 > y):
            xs.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
    xs.sort()
    return [(xs[i], xs[i + 1]) for i in range(0, len(xs) - 1, 2)]
