import { Layers } from 'lucide-react'
import {
  Map as MaplibreMap,
  type MapMouseEvent,
  Marker,
  NavigationControl,
  ScaleControl,
} from 'maplibre-gl'
import { type ReactNode, useEffect, useRef, useState } from 'react'

import type { LatLon } from '../lib/api'
import { BASE_STYLE, handle, type LngLat, toLngLat } from '../lib/map'
import { useVehicle } from '../lib/store'
import { MapTools, type PlaceAction } from './MapTools'

/**
 * The map. It creates one MapLibre map, hands it to the page through onReady,
 * and offers address search, "show my location" and a satellite / street switch.
 * Pages draw on it with lib/map helpers.
 */
export function MapView({
  center,
  zoom = 17,
  onReady,
  onClick,
  crosshair,
  placeAction,
  children,
  className = '',
}: {
  center: LatLon
  zoom?: number
  onReady: (map: MaplibreMap) => void
  onClick?: (at: LatLon) => void
  crosshair?: boolean
  /** What the operator can do with a searched place or their own position on this screen. */
  placeAction?: PlaceAction
  children?: ReactNode
  className?: string
}) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MaplibreMap | null>(null)
  const click = useRef(onClick)
  const [satellite, setSatellite] = useState(true)
  const [ready, setReady] = useState<MaplibreMap | null>(null)

  useEffect(() => {
    click.current = onClick
  }, [onClick])

  useEffect(() => {
    if (!container.current) return
    const map = new MaplibreMap({
      container: container.current,
      style: BASE_STYLE,
      center: toLngLat(center),
      zoom,
      attributionControl: { compact: true },
      doubleClickZoom: false,
    })
    map.addControl(new NavigationControl({ visualizePitch: false }), 'bottom-right')
    map.addControl(new ScaleControl({ unit: 'metric' }), 'bottom-left')
    map.on('load', () => {
      mapRef.current = map
      setReady(map)
      onReady(map)
    })
    map.on('click', (e: MapMouseEvent) =>
      click.current?.({ lat: e.lngLat.lat, lon: e.lngLat.lng }),
    )
    return () => {
      mapRef.current = null
      setReady(null)
      map.remove()
    }
    // The map is created once; pages move it with fitTo.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    map.setLayoutProperty('satellite', 'visibility', satellite ? 'visible' : 'none')
    map.setLayoutProperty('streets', 'visibility', satellite ? 'none' : 'visible')
  }, [satellite])

  return (
    <div className={`relative overflow-hidden ${className}`}>
      {/* Inline position: the map library's own stylesheet sets `position: relative` on this element. */}
      <div
        ref={container}
        style={{ position: 'absolute', inset: 0 }}
        className={crosshair ? '[&_canvas]:!cursor-crosshair' : ''}
      />
      {children}
      {/* Tool column, above the zoom buttons. The search panel opens to its left. */}
      <div className="absolute bottom-28 right-2.5 z-20 flex flex-col gap-1.5">
        <MapTools map={ready} action={placeAction} />
        <button
          type="button"
          onClick={() => setSatellite((v) => !v)}
          className="grid size-[29px] place-items-center rounded bg-white text-neutral-800 shadow hover:bg-neutral-100"
          aria-label={satellite ? 'Switch to street map' : 'Switch to satellite map'}
          title={satellite ? 'Street map' : 'Satellite map'}
        >
          <Layers size={16} />
        </button>
      </div>
    </div>
  )
}

/** Keeps a rotating arrow on the map at the vehicle's position. */
export function useVehicleMarker(map: MaplibreMap | null, follow: boolean) {
  const marker = useRef<Marker | null>(null)
  useEffect(() => {
    if (!map) return
    const el = document.createElement('div')
    el.innerHTML =
      '<svg width="38" height="38" viewBox="-19 -19 38 38" aria-hidden="true">' +
      '<circle r="17" fill="rgb(61 220 132 / 0.18)" stroke="#3ddc84" stroke-width="1.5"/>' +
      '<path d="M0,-13 L9,10 L0,5 L-9,10 Z" fill="#3ddc84" stroke="#04200f" stroke-width="1.5" stroke-linejoin="round"/></svg>'
    const m = new Marker({ element: el, rotationAlignment: 'map' })
    marker.current = m
    let placed = false

    const draw = () => {
      const s = useVehicle.getState().state
      if (!s || s.gps_fix === 'none' || (s.lat === 0 && s.lon === 0)) {
        if (placed) {
          m.remove()
          placed = false
        }
        return
      }
      m.setLngLat([s.lon, s.lat]).setRotation(s.heading_deg)
      if (!placed) {
        m.addTo(map)
        placed = true
        map.jumpTo({ center: [s.lon, s.lat] })
      } else if (follow && s.in_air) {
        map.easeTo({ center: [s.lon, s.lat], duration: 250 })
      }
    }
    draw()
    const stop = useVehicle.subscribe(draw)
    return () => {
      stop()
      m.remove()
      marker.current = null
    }
  }, [map, follow])
}

/**
 * Editable corners on the map: click to add, drag to move, click a faint dot to
 * insert between two corners, right-click a corner to remove it.
 */
export function useVertexEditor(
  map: MaplibreMap | null,
  {
    points,
    onChange,
    active,
    color,
    kind = 'vertex',
    closed = true,
  }: {
    points: LatLon[]
    onChange: (points: LatLon[]) => void
    active: boolean
    color: string
    kind?: 'vertex' | 'waypoint'
    closed?: boolean
  },
) {
  const latest = useRef({ points, onChange })
  useEffect(() => {
    latest.current = { points, onChange }
  }, [points, onChange])

  // Corner handles
  useEffect(() => {
    if (!map) return
    const markers: Marker[] = []
    points.forEach((p, index) => {
      const el = handle(kind, color, kind === 'waypoint' ? String(index + 1) : '')
      if (!active) el.style.cursor = 'default'
      const m = new Marker({ element: el, draggable: active })
        .setLngLat(toLngLat(p))
        .addTo(map)
      m.on('dragend', () => {
        const at = m.getLngLat()
        const next = [...latest.current.points]
        next[index] = { ...next[index], lat: at.lat, lon: at.lng }
        latest.current.onChange(next)
      })
      el.addEventListener('contextmenu', (e) => {
        e.preventDefault()
        if (active) latest.current.onChange(latest.current.points.filter((_, i) => i !== index))
      })
      el.addEventListener('click', (e) => e.stopPropagation())
      markers.push(m)
    })

    if (active && points.length >= 2) {
      const last = closed ? points.length : points.length - 1
      for (let i = 0; i < last; i++) {
        const a = points[i]
        const b = points[(i + 1) % points.length]
        const mid: LngLat = [(a.lon + b.lon) / 2, (a.lat + b.lat) / 2]
        const el = handle('mid', color)
        el.title = 'Add a corner here'
        el.addEventListener('click', (e) => {
          e.stopPropagation()
          const next = [...latest.current.points]
          next.splice(i + 1, 0, { ...a, lat: mid[1], lon: mid[0] })
          latest.current.onChange(next)
        })
        markers.push(new Marker({ element: el }).setLngLat(mid).addTo(map))
      }
    }
    return () => markers.forEach((m) => m.remove())
  }, [map, points, active, color, kind, closed])
}

/** One draggable marker, used for the home point. */
export function useHomeMarker(
  map: MaplibreMap | null,
  home: LatLon | null,
  onChange: ((p: LatLon) => void) | null,
  color: string,
) {
  const change = useRef(onChange)
  useEffect(() => {
    change.current = onChange
  }, [onChange])
  const draggable = onChange !== null
  useEffect(() => {
    if (!map || !home) return
    const el = handle('home', color)
    if (!draggable) el.style.cursor = 'default'
    const m = new Marker({ element: el, draggable })
      .setLngLat(toLngLat(home))
      .addTo(map)
    m.on('dragend', () => {
      const at = m.getLngLat()
      change.current?.({ lat: at.lat, lon: at.lng })
    })
    el.addEventListener('click', (e) => e.stopPropagation())
    return () => {
      m.remove()
    }
  }, [map, home, draggable, color])
}
