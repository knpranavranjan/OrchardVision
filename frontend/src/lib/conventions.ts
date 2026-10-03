/**
 * Coordinate and heading conventions (docs/PLAN.md section 5.1).
 *
 * Mirrors backend/app/core/conventions.py. Both are tested against
 * contracts/conventions_vectors.json so they cannot drift apart.
 */

const WGS84_A = 6378137.0
const WGS84_F = 1 / 298.257223563
const WGS84_E2 = WGS84_F * (2 - WGS84_F)

const rad = (deg: number) => (deg * Math.PI) / 180
const deg = (r: number) => (r * 180) / Math.PI

export type Vec3 = [number, number, number]

export function geodeticToEcef(latDeg: number, lonDeg: number, altM: number): Vec3 {
  const lat = rad(latDeg)
  const lon = rad(lonDeg)
  const n = WGS84_A / Math.sqrt(1 - WGS84_E2 * Math.sin(lat) ** 2)
  return [
    (n + altM) * Math.cos(lat) * Math.cos(lon),
    (n + altM) * Math.cos(lat) * Math.sin(lon),
    (n * (1 - WGS84_E2) + altM) * Math.sin(lat),
  ]
}

export function ecefToGeodetic(x: number, y: number, z: number): Vec3 {
  const lon = Math.atan2(y, x)
  const p = Math.hypot(x, y)
  let lat = Math.atan2(z, p * (1 - WGS84_E2))
  let alt = 0
  for (let i = 0; i < 8; i++) {
    const n = WGS84_A / Math.sqrt(1 - WGS84_E2 * Math.sin(lat) ** 2)
    alt = p / Math.cos(lat) - n
    lat = Math.atan2(z, p * (1 - (WGS84_E2 * n) / (n + alt)))
  }
  return [deg(lat), deg(lon), alt]
}

/** East-north-up frame tangent to the ellipsoid at an origin. */
export class LocalFrame {
  readonly originLat: number
  readonly originLon: number
  readonly originAlt: number

  constructor(originLat: number, originLon: number, originAlt = 0) {
    this.originLat = originLat
    this.originLon = originLon
    this.originAlt = originAlt
  }

  toEnu(latDeg: number, lonDeg: number, altM = 0): Vec3 {
    const [ox, oy, oz] = geodeticToEcef(this.originLat, this.originLon, this.originAlt)
    const [x, y, z] = geodeticToEcef(latDeg, lonDeg, altM)
    const [dx, dy, dz] = [x - ox, y - oy, z - oz]
    const lat = rad(this.originLat)
    const lon = rad(this.originLon)
    const [sl, cl, so, co] = [Math.sin(lat), Math.cos(lat), Math.sin(lon), Math.cos(lon)]
    return [
      -so * dx + co * dy,
      -sl * co * dx - sl * so * dy + cl * dz,
      cl * co * dx + cl * so * dy + sl * dz,
    ]
  }

  toGeodetic(east: number, north: number, up = 0): Vec3 {
    const [ox, oy, oz] = geodeticToEcef(this.originLat, this.originLon, this.originAlt)
    const lat = rad(this.originLat)
    const lon = rad(this.originLon)
    const [sl, cl, so, co] = [Math.sin(lat), Math.cos(lat), Math.sin(lon), Math.cos(lon)]
    const dx = -so * east - sl * co * north + cl * co * up
    const dy = co * east - sl * so * north + cl * so * up
    const dz = cl * north + sl * up
    return ecefToGeodetic(ox + dx, oy + dy, oz + dz)
  }
}

/** Heading in [0, 360). */
export function wrapHeading(d: number): number {
  return ((d % 360) + 360) % 360
}

/** Shortest signed turn from current to target, in (-180, 180]. Positive is clockwise. */
export function headingDiff(targetDeg: number, currentDeg: number): number {
  const d = wrapHeading(targetDeg - currentDeg)
  return d > 180 ? d - 360 : d
}

/** Heading of a displacement: 0 is north, 90 is east. */
export function bearingFromEnu(dEast: number, dNorth: number): number {
  return wrapHeading(deg(Math.atan2(dEast, dNorth)))
}

/** A rectangle around some points with a margin in metres: the quick way to make a fence. */
export function boundingFence(
  points: { lat: number; lon: number }[],
  marginM: number,
): { lat: number; lon: number }[] {
  if (points.length === 0) return []
  const frame = new LocalFrame(points[0].lat, points[0].lon)
  const en = points.map((p) => frame.toEnu(p.lat, p.lon))
  const e0 = Math.min(...en.map((p) => p[0])) - marginM
  const e1 = Math.max(...en.map((p) => p[0])) + marginM
  const n0 = Math.min(...en.map((p) => p[1])) - marginM
  const n1 = Math.max(...en.map((p) => p[1])) + marginM
  return [
    [e0, n0],
    [e1, n0],
    [e1, n1],
    [e0, n1],
  ].map(([e, n]) => {
    const [lat, lon] = frame.toGeodetic(e, n)
    return { lat, lon }
  })
}
