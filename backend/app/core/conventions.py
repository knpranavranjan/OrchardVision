"""Coordinate, heading and time conventions (docs/PLAN.md section 5.1).

Stored positions are WGS84 degrees. Local geometry is east-north-up metres from
an origin. Heading is degrees clockwise from true north. Time is UTC.

The browser has the same functions in frontend/src/lib/conventions.ts, and both
are tested against contracts/conventions_vectors.json.
"""

import math
from dataclasses import dataclass
from datetime import UTC, datetime

WGS84_A = 6378137.0
WGS84_F = 1 / 298.257223563
WGS84_E2 = WGS84_F * (2 - WGS84_F)


def geodetic_to_ecef(lat_deg: float, lon_deg: float, alt_m: float) -> tuple[float, float, float]:
    lat, lon = math.radians(lat_deg), math.radians(lon_deg)
    n = WGS84_A / math.sqrt(1 - WGS84_E2 * math.sin(lat) ** 2)
    x = (n + alt_m) * math.cos(lat) * math.cos(lon)
    y = (n + alt_m) * math.cos(lat) * math.sin(lon)
    z = (n * (1 - WGS84_E2) + alt_m) * math.sin(lat)
    return x, y, z


def ecef_to_geodetic(x: float, y: float, z: float) -> tuple[float, float, float]:
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    lat = math.atan2(z, p * (1 - WGS84_E2))
    alt = 0.0
    # Fixed-point iteration; converges to sub-millimetre in a few rounds away from the poles.
    for _ in range(8):
        n = WGS84_A / math.sqrt(1 - WGS84_E2 * math.sin(lat) ** 2)
        alt = p / math.cos(lat) - n
        lat = math.atan2(z, p * (1 - WGS84_E2 * n / (n + alt)))
    return math.degrees(lat), math.degrees(lon), alt


@dataclass(frozen=True)
class LocalFrame:
    """East-north-up frame tangent to the ellipsoid at an origin."""

    origin_lat: float
    origin_lon: float
    origin_alt: float = 0.0

    def to_enu(
        self, lat_deg: float, lon_deg: float, alt_m: float = 0.0
    ) -> tuple[float, float, float]:
        ox, oy, oz = geodetic_to_ecef(self.origin_lat, self.origin_lon, self.origin_alt)
        x, y, z = geodetic_to_ecef(lat_deg, lon_deg, alt_m)
        dx, dy, dz = x - ox, y - oy, z - oz
        lat, lon = math.radians(self.origin_lat), math.radians(self.origin_lon)
        sl, cl, so, co = math.sin(lat), math.cos(lat), math.sin(lon), math.cos(lon)
        east = -so * dx + co * dy
        north = -sl * co * dx - sl * so * dy + cl * dz
        up = cl * co * dx + cl * so * dy + sl * dz
        return east, north, up

    def to_geodetic(self, east: float, north: float, up: float = 0.0) -> tuple[float, float, float]:
        ox, oy, oz = geodetic_to_ecef(self.origin_lat, self.origin_lon, self.origin_alt)
        lat, lon = math.radians(self.origin_lat), math.radians(self.origin_lon)
        sl, cl, so, co = math.sin(lat), math.cos(lat), math.sin(lon), math.cos(lon)
        dx = -so * east - sl * co * north + cl * co * up
        dy = co * east - sl * so * north + cl * so * up
        dz = cl * north + sl * up
        return ecef_to_geodetic(ox + dx, oy + dy, oz + dz)

    def to_en(self, lat_deg: float, lon_deg: float) -> tuple[float, float]:
        """Horizontal position only. Height is taken as the origin's."""
        e, n, _ = self.to_enu(lat_deg, lon_deg, self.origin_alt)
        return e, n

    def to_latlon(self, east: float, north: float) -> tuple[float, float]:
        lat, lon, _ = self.to_geodetic(east, north, 0.0)
        return lat, lon


def wrap_heading(deg: float) -> float:
    """Heading in [0, 360)."""
    return deg % 360.0


def heading_diff(target_deg: float, current_deg: float) -> float:
    """Shortest signed turn from current to target, in (-180, 180]. Positive is clockwise."""
    d = (target_deg - current_deg) % 360.0
    return d - 360.0 if d > 180.0 else d


def bearing_from_enu(d_east: float, d_north: float) -> float:
    """Heading of a displacement: 0 is north, 90 is east."""
    return wrap_heading(math.degrees(math.atan2(d_east, d_north)))


def utc_now() -> datetime:
    """Current UTC time, truncated to milliseconds."""
    now = datetime.now(UTC)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


def to_iso_ms(t: datetime) -> str:
    return t.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
