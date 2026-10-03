/** Helpers for drawing on the MapLibre map. Coordinates here are [lon, lat]. */
import type { Feature, FeatureCollection, GeoJSON } from 'geojson'
import {
  type GeoJSONSource,
  LngLatBounds,
  type Map as MlMap,
  setWorkerUrl,
  type StyleSpecification,
} from 'maplibre-gl'

import type { LatLon } from './api'

// The worker is served from public/maplibre (see scripts/copy-map-worker.mjs).
setWorkerUrl(`${import.meta.env.BASE_URL}maplibre/maplibre-gl-worker.mjs`)

export type LngLat = [number, number]

export const toLngLat = (p: LatLon): LngLat => [p.lon, p.lat]
export const pairToLngLat = (p: [number, number] | [number, number, number]): LngLat => [p[1], p[0]]

/** Read a design token, because the map needs literal colours. */
export const token = (name: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim()

/**
 * Raster base maps that need no API key. Tiles the browser has already loaded
 * keep working offline; a packaged offline tile set is a later addition.
 */
export const BASE_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    satellite: {
      type: 'raster',
      tiles: [
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      ],
      tileSize: 256,
      maxzoom: 19,
      attribution: 'Imagery © Esri, Maxar, Earthstar Geographics',
    },
    streets: {
      type: 'raster',
      tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      maxzoom: 19,
      attribution: '© OpenStreetMap contributors',
    },
  },
  layers: [
    { id: 'background', type: 'background', paint: { 'background-color': '#0f171d' } },
    { id: 'streets', type: 'raster', source: 'streets', layout: { visibility: 'none' } },
    { id: 'satellite', type: 'raster', source: 'satellite' },
  ],
}

function upsert(map: MlMap, id: string, data: GeoJSON, addLayers: () => void) {
  const source = map.getSource(id) as GeoJSONSource | undefined
  if (source) {
    source.setData(data)
  } else {
    map.addSource(id, { type: 'geojson', data })
    addLayers()
  }
}

export function setLine(
  map: MlMap,
  id: string,
  coords: LngLat[],
  paint: { color: string; width?: number; dash?: number[]; opacity?: number },
) {
  const data: Feature = {
    type: 'Feature',
    properties: {},
    geometry: { type: 'LineString', coordinates: coords },
  }
  upsert(map, id, data, () =>
    map.addLayer({
      id,
      type: 'line',
      source: id,
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: {
        'line-color': paint.color,
        'line-width': paint.width ?? 2.5,
        'line-opacity': paint.opacity ?? 1,
        ...(paint.dash ? { 'line-dasharray': paint.dash } : {}),
      },
    }),
  )
}

export function setPolygon(
  map: MlMap,
  id: string,
  ring: LngLat[],
  paint: { color: string; fillOpacity?: number; width?: number; dash?: number[] },
) {
  const closed = ring.length >= 3 ? [...ring, ring[0]] : ring
  const data: Feature = {
    type: 'Feature',
    properties: {},
    geometry:
      ring.length >= 3
        ? { type: 'Polygon', coordinates: [closed] }
        : { type: 'LineString', coordinates: ring },
  }
  upsert(map, id, data, () => {
    map.addLayer({
      id: `${id}-fill`,
      type: 'fill',
      source: id,
      filter: ['==', '$type', 'Polygon'],
      paint: { 'fill-color': paint.color, 'fill-opacity': paint.fillOpacity ?? 0.12 },
    })
    map.addLayer({
      id,
      type: 'line',
      source: id,
      paint: {
        'line-color': paint.color,
        'line-width': paint.width ?? 2,
        ...(paint.dash ? { 'line-dasharray': paint.dash } : {}),
      },
    })
  })
}

export function setPoints(
  map: MlMap,
  id: string,
  coords: LngLat[],
  paint: { color: string; radius?: number; stroke?: string },
) {
  const data: FeatureCollection = {
    type: 'FeatureCollection',
    features: coords.map((c) => ({
      type: 'Feature',
      properties: {},
      geometry: { type: 'Point', coordinates: c },
    })),
  }
  upsert(map, id, data, () =>
    map.addLayer({
      id,
      type: 'circle',
      source: id,
      paint: {
        'circle-color': paint.color,
        'circle-radius': paint.radius ?? 3,
        'circle-stroke-color': paint.stroke ?? '#000000',
        'circle-stroke-width': 0.6,
      },
    }),
  )
}

export function fitTo(map: MlMap, coords: LngLat[], padding = 60) {
  if (coords.length === 0) return
  const bounds = new LngLatBounds(coords[0], coords[0])
  for (const c of coords) bounds.extend(c)
  map.fitBounds(bounds, { padding, maxZoom: 19, duration: 400 })
}

/** A round handle used for polygon corners, waypoints and the home point. */
export function handle(kind: 'vertex' | 'mid' | 'waypoint' | 'home', color: string, text = '') {
  const el = document.createElement('div')
  const base =
    'display:grid;place-items:center;border-radius:9999px;font:600 11px "Fira Code",monospace;' +
    'box-shadow:0 1px 4px rgb(0 0 0 / 0.6);user-select:none;'
  if (kind === 'vertex') {
    el.style.cssText = `${base}width:16px;height:16px;background:#fff;border:3px solid ${color};cursor:grab;`
  } else if (kind === 'mid') {
    el.style.cssText = `${base}width:12px;height:12px;background:${color};opacity:0.55;border:2px solid #fff;cursor:copy;`
  } else if (kind === 'waypoint') {
    el.style.cssText = `${base}width:24px;height:24px;background:${color};color:#04121b;border:2px solid #fff;cursor:grab;`
    el.textContent = text
  } else {
    el.style.cssText = `${base}width:26px;height:26px;background:#fff;color:#0a0f14;border:3px solid ${color};cursor:grab;`
    el.textContent = 'H'
    el.title = 'Home: take-off and landing point'
  }
  return el
}
