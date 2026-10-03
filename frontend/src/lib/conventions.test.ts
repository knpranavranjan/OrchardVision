import { describe, expect, it } from 'vitest'

import vectors from '../../../contracts/conventions_vectors.json'
import { bearingFromEnu, boundingFence, headingDiff, LocalFrame, wrapHeading } from './conventions'

const dist = (a: number[], b: number[]) => Math.hypot(...a.map((v, i) => v - b[i]))

describe('conventions shared with the backend', () => {
  const [lat, lon, alt] = vectors.origin
  const frame = new LocalFrame(lat, lon, alt)

  it.each(vectors.enu)('matches the backend for $geodetic', (c) => {
    const [la, lo, al] = c.geodetic
    expect(dist(frame.toEnu(la, lo, al), c.enu)).toBeLessThan(1e-3)
  })

  it.each(vectors.heading_diff)('heading diff $target from $current', (c) => {
    expect(headingDiff(c.target, c.current)).toBeCloseTo(c.diff, 9)
  })

  it('round-trips within an orchard to a tenth of a millimetre', () => {
    for (const [e, n, u] of [[0, 0, 0], [120.5, -340.25, 25], [-499, 499, 110]]) {
      const [la, lo, al] = frame.toGeodetic(e, n, u)
      expect(dist(frame.toEnu(la, lo, al), [e, n, u])).toBeLessThan(1e-4)
    }
  })
})

describe('independent checks', () => {
  it('one millidegree east at the equator is 111.32 m', () => {
    const [east, north] = new LocalFrame(0, 0).toEnu(0, 0.001)
    expect(east).toBeCloseTo(111.3195, 3)
    expect(north).toBeCloseTo(0, 6)
  })

  it('headings', () => {
    expect(wrapHeading(-10)).toBe(350)
    expect(wrapHeading(720)).toBe(0)
    expect(bearingFromEnu(1, 0)).toBeCloseTo(90)
    expect(bearingFromEnu(-1, 0)).toBeCloseTo(270)
  })
})

describe('boundingFence', () => {
  it('wraps the points with the margin on every side', () => {
    const frame = new LocalFrame(12.9716, 77.5946)
    const corners = [[0, 0], [100, 0], [100, 60], [0, 60]].map(([e, n]) => {
      const [lat, lon] = frame.toGeodetic(e, n)
      return { lat, lon }
    })
    const fence = boundingFence(corners, 20)
    expect(fence).toHaveLength(4)
    const en = fence.map((p) => frame.toEnu(p.lat, p.lon))
    expect(Math.min(...en.map((p) => p[0]))).toBeCloseTo(-20, 2)
    expect(Math.max(...en.map((p) => p[0]))).toBeCloseTo(120, 2)
    expect(Math.min(...en.map((p) => p[1]))).toBeCloseTo(-20, 2)
    expect(Math.max(...en.map((p) => p[1]))).toBeCloseTo(80, 2)
  })

  it('returns nothing for no points', () => {
    expect(boundingFence([], 20)).toEqual([])
  })
})
