/**
 * Map tools: find my location, and search for an address.
 *
 * Both end in the same place card: what is there, its coordinates, and (on
 * screens that offer one) an action such as "Set the take-off point here".
 */
import { Check, Copy, LocateFixed, MapPin, Search, X } from 'lucide-react'
import { type Map as MaplibreMap, Marker } from 'maplibre-gl'
import { type FormEvent, useEffect, useRef, useState } from 'react'

import { api, type LatLon, type Place } from '../lib/api'
import { LocalFrame } from '../lib/conventions'
import { type LngLat, setPolygon } from '../lib/map'

export interface PlaceAction {
  label: string
  onPick: (at: LatLon) => void
}

interface Shown {
  place: Place
  /** Set when the place is the operator's own position. Metres. */
  accuracy?: number
}

const BUTTON =
  'grid size-[29px] place-items-center rounded bg-white text-neutral-800 shadow ' +
  'hover:bg-neutral-100 disabled:opacity-60'

const LOCATION_ERRORS: Record<number, string> = {
  1: 'Location permission was refused. Allow it for this site in the browser, then try again.',
  2: 'This device could not work out its position. Search for the address instead.',
  3: 'Finding your position took too long. Try again, or search for the address.',
}

function pin(color: string, label: string) {
  const el = document.createElement('div')
  el.title = label
  el.innerHTML =
    `<svg width="30" height="38" viewBox="0 0 30 38" aria-hidden="true">` +
    `<path d="M15 37C15 37 28 22 28 14A13 13 0 1 0 2 14C2 22 15 37 15 37Z" fill="${color}" stroke="#fff" stroke-width="2"/>` +
    `<circle cx="15" cy="14" r="5" fill="#fff"/></svg>`
  return el
}

function dot() {
  const el = document.createElement('div')
  el.title = 'Your position'
  el.style.cssText =
    'width:18px;height:18px;border-radius:9999px;background:#2f8cff;border:3px solid #fff;' +
    'box-shadow:0 0 0 2px rgb(47 140 255 / 0.45),0 1px 4px rgb(0 0 0 / 0.6);'
  return el
}

/** A circle of the given radius in metres, as a ring of [lon, lat]. */
function circle(center: LatLon, radiusM: number): LngLat[] {
  const frame = new LocalFrame(center.lat, center.lon)
  return Array.from({ length: 48 }, (_, i) => {
    const a = (i / 48) * 2 * Math.PI
    const [lat, lon] = frame.toGeodetic(radiusM * Math.cos(a), radiusM * Math.sin(a))
    return [lon, lat] as LngLat
  })
}

function describe(place: Place) {
  return [place.kind, place.locality, place.state, place.postcode, place.country].filter(Boolean).join(' · ')
}

export function MapTools({ map, action }: { map: MaplibreMap | null; action?: PlaceAction }) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<Place[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [locating, setLocating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [shown, setShown] = useState<Shown | null>(null)
  const [copied, setCopied] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const placeMarker = useRef<Marker | null>(null)
  const meMarker = useRef<Marker | null>(null)

  useEffect(() => {
    if (open) input.current?.focus()
  }, [open])

  // The pin for a searched place
  useEffect(() => {
    placeMarker.current?.remove()
    placeMarker.current = null
    if (!map || !shown || shown.accuracy !== undefined) return
    placeMarker.current = new Marker({ element: pin('#f7b23b', shown.place.name), anchor: 'bottom' })
      .setLngLat([shown.place.lon, shown.place.lat])
      .addTo(map)
    return () => {
      placeMarker.current?.remove()
      placeMarker.current = null
    }
  }, [map, shown])

  useEffect(
    () => () => {
      meMarker.current?.remove()
    },
    [],
  )

  const show = (place: Place) => {
    setShown({ place })
    setResults(null)
    if (!map) return
    if (place.bounds) {
      const [south, north, west, east] = place.bounds
      map.fitBounds([[west, south], [east, north]], { padding: 80, maxZoom: 18, duration: 600 })
    } else {
      map.flyTo({ center: [place.lon, place.lat], zoom: 18, duration: 600 })
    }
  }

  const search = async (event: FormEvent) => {
    event.preventDefault()
    const text = query.trim()
    if (text.length < 2) return
    setBusy(true)
    setError(null)
    setShown(null)
    try {
      const found = await api.searchPlaces(text)
      if (found.length === 1) show(found[0])
      else setResults(found)
    } catch (e) {
      setResults(null)
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const locate = () => {
    if (!('geolocation' in navigator)) {
      setOpen(true)
      setError('This browser cannot report a position. Search for the address instead.')
      return
    }
    setLocating(true)
    setError(null)
    navigator.geolocation.getCurrentPosition(
      async (position) => {
        const at = { lat: position.coords.latitude, lon: position.coords.longitude }
        const accuracy = position.coords.accuracy
        setLocating(false)
        setOpen(true)
        setResults(null)
        if (map) {
          meMarker.current?.remove()
          meMarker.current = new Marker({ element: dot() }).setLngLat([at.lon, at.lat]).addTo(map)
          setPolygon(map, 'me-accuracy', circle(at, accuracy), { color: '#2f8cff', fillOpacity: 0.12, width: 1 })
          map.flyTo({ center: [at.lon, at.lat], zoom: accuracy < 60 ? 18 : accuracy < 500 ? 16 : 13, duration: 700 })
        }
        const fallback: Place = {
          name: 'Your position',
          display_name: '',
          ...at,
          kind: '',
          locality: '',
          state: '',
          country: '',
          postcode: '',
          bounds: null,
        }
        setShown({ place: fallback, accuracy })
        try {
          const place = await api.placeAt(at.lat, at.lon)
          setShown({ place: { ...place, bounds: null }, accuracy })
        } catch {
          /* no internet: the coordinates alone are still useful */
        }
      },
      (failure) => {
        setLocating(false)
        setOpen(true)
        setError(LOCATION_ERRORS[failure.code] ?? 'Your position could not be found.')
      },
      { enableHighAccuracy: true, timeout: 15_000, maximumAge: 10_000 },
    )
  }

  const copy = async (place: Place) => {
    try {
      await navigator.clipboard.writeText(`${place.lat.toFixed(6)}, ${place.lon.toFixed(6)}`)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      /* clipboard unavailable: the coordinates are on screen to copy by hand */
    }
  }

  const close = () => {
    setOpen(false)
    setResults(null)
    setError(null)
    setShown(null)
  }

  return (
    <>
      <button type="button" className={BUTTON} onClick={() => (open ? close() : setOpen(true))} aria-label="Search for an address" aria-expanded={open} title="Search for an address or coordinates">
        <Search size={16} />
      </button>
      <button type="button" className={BUTTON} onClick={locate} disabled={locating} aria-label="Show my location" title="Show my location">
        {locating ? (
          <span className="size-4 animate-spin rounded-full border-2 border-neutral-700 border-t-transparent" />
        ) : (
          <LocateFixed size={16} />
        )}
      </button>

      {open && (
        <div
          role="search"
          className="absolute bottom-0 right-10 z-20 w-80 rounded-lg border border-line bg-surface text-ink shadow-2xl"
        >
          <form onSubmit={search} className="flex items-center gap-1.5 p-2">
            <label htmlFor="map-search" className="sr-only">
              Address, place or coordinates
            </label>
            <input
              id="map-search"
              ref={input}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Address, place, or 12.9716, 77.5946"
              className="min-h-10 min-w-0 flex-1 rounded-md border border-line bg-surface-2 px-2.5 placeholder:text-muted"
              autoComplete="off"
            />
            <button
              type="submit"
              disabled={busy || query.trim().length < 2}
              className="grid size-10 shrink-0 place-items-center rounded-md bg-brand text-on-brand disabled:opacity-45"
              aria-label="Search"
            >
              {busy ? <span className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent" /> : <Search size={16} />}
            </button>
            <button type="button" onClick={close} className="grid size-10 shrink-0 place-items-center rounded-md hover:bg-surface-3" aria-label="Close search">
              <X size={16} />
            </button>
          </form>

          {error && (
            <p role="alert" className="mx-2 mb-2 rounded-md border border-danger/50 bg-danger/10 p-2 text-[12.5px] leading-snug">
              {error}
            </p>
          )}

          {results && results.length === 0 && (
            <p className="px-3 pb-3 text-[13px] text-muted">
              Nothing found. Try a nearby town or landmark, or type the coordinates.
            </p>
          )}

          {results && results.length > 0 && (
            <ul className="scroll max-h-64 border-t border-line">
              {results.map((p, i) => (
                <li key={`${p.lat},${p.lon},${i}`}>
                  <button type="button" onClick={() => show(p)} className="flex w-full items-start gap-2 px-3 py-2 text-left hover:bg-surface-2">
                    <MapPin size={15} className="mt-0.5 shrink-0 text-muted" />
                    <span className="min-w-0">
                      <span className="block truncate text-[13px] font-medium">{p.name || p.display_name}</span>
                      <span className="block truncate text-[11.5px] text-muted">{p.display_name}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}

          {shown && (
            <div className="border-t border-line p-3">
              <div className="text-[14px] font-semibold leading-tight">
                {shown.accuracy !== undefined ? 'You are here' : shown.place.name}
              </div>
              {shown.place.display_name && (
                <div className="mt-1 text-[12.5px] leading-snug text-muted">{shown.place.display_name}</div>
              )}
              {describe(shown.place) && shown.accuracy === undefined && (
                <div className="mt-1 text-[11.5px] capitalize text-muted">{describe(shown.place)}</div>
              )}
              <div className="mt-2 flex items-center gap-2">
                <span className="num text-[13px]">
                  {shown.place.lat.toFixed(6)}, {shown.place.lon.toFixed(6)}
                </span>
                <button type="button" onClick={() => void copy(shown.place)} className="grid size-8 place-items-center rounded hover:bg-surface-3" aria-label="Copy coordinates" title="Copy coordinates">
                  {copied ? <Check size={14} className="text-brand" /> : <Copy size={14} />}
                </button>
              </div>
              {shown.accuracy !== undefined && (
                <p className={`mt-1 text-[12px] leading-snug ${shown.accuracy > 200 ? 'text-warn' : 'text-muted'}`}>
                  Accurate to about {shown.accuracy >= 1000 ? `${(shown.accuracy / 1000).toFixed(1)} km` : `${Math.round(shown.accuracy)} m`}.
                  {shown.accuracy > 200 &&
                    ' This computer has no GPS, so the position comes from the network and can be well off. Search for the address, or use a device with GPS in the field.'}
                </p>
              )}
              {action && (
                <button
                  type="button"
                  onClick={() => action.onPick({ lat: shown.place.lat, lon: shown.place.lon })}
                  className="mt-3 min-h-10 w-full rounded-md bg-brand px-3 text-[13px] font-semibold text-on-brand hover:brightness-110"
                >
                  {action.label}
                </button>
              )}
            </div>
          )}

          {!shown && !results && !error && (
            <p className="px-3 pb-3 text-[12px] leading-snug text-muted">
              Press Enter to search. Addresses are looked up with OpenStreetMap and need internet; coordinates do not.
            </p>
          )}
        </div>
      )}
    </>
  )
}
