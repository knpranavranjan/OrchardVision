import { Download, Pause, Play, Trash2 } from 'lucide-react'
import { type Map as MlMap, Marker } from 'maplibre-gl'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { MapView } from '../components/MapView'
import { Badge, Button, Empty, Panel, Stat } from '../components/ui'
import { api, type FlightDetail, type FlightSummary, type LatLon, type TelemetryPoint } from '../lib/api'
import { dateTime, distance, duration, fixed } from '../lib/format'
import { fitTo, type LngLat, pairToLngLat, setLine, setPoints, setPolygon, token } from '../lib/map'
import { useVehicle } from '../lib/store'

const DEFAULT_CENTER: LatLon = { lat: 12.9716, lon: 77.5946 }
const STATUS_TONE = { completed: 'good', aborted: 'bad', in_progress: 'warn' } as const

/** A small line chart with a time cursor. Click or drag to move the cursor. */
function Chart({
  label,
  unit,
  points,
  value,
  color,
  cursor,
  onSeek,
}: {
  label: string
  unit: string
  points: TelemetryPoint[]
  value: (p: TelemetryPoint) => number | null
  color: string
  cursor: number
  onSeek: (index: number) => void
}) {
  const W = 600
  const H = 64
  const values = points.map((p) => value(p) ?? 0)
  const max = Math.max(...values, 0.001)
  const min = Math.min(...values, 0)
  const tMax = points[points.length - 1]?.t || 1
  const x = (t: number) => (t / tMax) * W
  const y = (v: number) => H - 4 - ((v - min) / (max - min || 1)) * (H - 10)
  const path = points.map((p, i) => `${i ? 'L' : 'M'}${x(p.t).toFixed(1)},${y(values[i]).toFixed(1)}`).join('')
  const here = points[cursor]

  const seek = (clientX: number, target: SVGSVGElement) => {
    const box = target.getBoundingClientRect()
    const t = ((clientX - box.left) / box.width) * tMax
    let best = 0
    for (let i = 0; i < points.length; i++) if (Math.abs(points[i].t - t) < Math.abs(points[best].t - t)) best = i
    onSeek(best)
  }

  return (
    <div>
      <div className="flex items-baseline justify-between text-[11.5px]">
        <span className="font-medium uppercase tracking-wider text-muted">{label}</span>
        <span className="num">
          {here ? fixed(value(here)) : '—'} {unit}
          <span className="ml-2 text-muted">max {fixed(max)}</span>
        </span>
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        className="h-16 w-full cursor-crosshair rounded bg-surface-2"
        role="img"
        aria-label={`${label} over the flight, maximum ${fixed(max)} ${unit}`}
        onPointerDown={(e) => {
          e.currentTarget.setPointerCapture(e.pointerId)
          seek(e.clientX, e.currentTarget)
        }}
        onPointerMove={(e) => e.buttons === 1 && seek(e.clientX, e.currentTarget)}
      >
        <path d={path} fill="none" stroke={color} strokeWidth="1.6" vectorEffect="non-scaling-stroke" />
        {here && <line x1={x(here.t)} x2={x(here.t)} y1="0" y2={H} stroke="var(--ink)" strokeWidth="1" vectorEffect="non-scaling-stroke" />}
      </svg>
    </div>
  )
}

function Replay({ flight, onDeleted }: { flight: FlightDetail; onDeleted: () => void }) {
  const [map, setMap] = useState<MlMap | null>(null)
  const [cursor, setCursor] = useState(0)
  const [playing, setPlaying] = useState(false)
  const marker = useRef<Marker | null>(null)
  const points = flight.telemetry
  const here = points[Math.min(cursor, points.length - 1)]

  useEffect(() => {
    setCursor(0)
    setPlaying(false)
  }, [flight.id])

  useEffect(() => {
    if (!map) return
    const snap = flight.plan_snapshot
    const track: LngLat[] = points.map((p) => [p.lon, p.lat])
    setPolygon(map, 'replay-area', (snap.area ?? []).map(pairToLngLat), { color: token('--plan'), fillOpacity: 0.08, width: 1.5 })
    setPolygon(map, 'replay-fence', (snap.geofence ?? []).map(pairToLngLat), { color: token('--fence'), fillOpacity: 0, dash: [3, 2] })
    setLine(map, 'replay-route', (snap.route ?? []).map(pairToLngLat), { color: token('--plan'), width: 1.8, dash: [2, 1.5] })
    setLine(map, 'replay-track', track, { color: token('--track'), width: 3 })
    setPoints(map, 'replay-captures', flight.captures.map((c) => [c.lon, c.lat]), { color: '#ffffff', radius: 2.6 })
    fitTo(map, [...track, ...(snap.geofence ?? []).map(pairToLngLat)], 70)
  }, [map, flight, points])

  useEffect(() => {
    if (!map || !here) return
    if (!marker.current) {
      const el = document.createElement('div')
      el.innerHTML =
        '<svg width="34" height="34" viewBox="-17 -17 34 34"><circle r="15" fill="rgb(255 216 74 / 0.2)" stroke="#ffd84a" stroke-width="1.5"/>' +
        '<path d="M0,-12 L8,9 L0,4 L-8,9 Z" fill="#ffd84a" stroke="#3b2f00" stroke-width="1.2"/></svg>'
      marker.current = new Marker({ element: el, rotationAlignment: 'map' }).setLngLat([here.lon, here.lat]).addTo(map)
    }
    marker.current.setLngLat([here.lon, here.lat]).setRotation(here.hdg)
  }, [map, here])
  useEffect(
    () => () => {
      marker.current?.remove()
      marker.current = null
    },
    [map],
  )

  // Play back at ten times real speed, following the recorded time gaps.
  useEffect(() => {
    if (!playing) return
    if (cursor >= points.length - 1) {
      setPlaying(false)
      return
    }
    const gap = Math.max(20, ((points[cursor + 1].t - points[cursor].t) * 1000) / 10)
    const timer = setTimeout(() => setCursor((c) => c + 1), gap)
    return () => clearTimeout(timer)
  }, [playing, cursor, points])

  const s = flight.summary
  const remove = async () => {
    if (!window.confirm('Delete this flight record? This cannot be undone.')) return
    await api.deleteFlight(flight.id)
    onDeleted()
  }

  return (
    <div className="grid h-full grid-rows-[1fr_auto]">
      <MapView center={DEFAULT_CENTER} onReady={setMap} className="min-h-0" />
      <div className="scroll max-h-[46vh] border-t border-line bg-bg p-3">
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <h2 className="text-base font-semibold">{flight.mission_name}</h2>
          <Badge tone={STATUS_TONE[flight.status]}>{flight.status.replace('_', ' ')}</Badge>
          <span className="text-[12.5px] text-muted">
            {dateTime(flight.started_at)} · {flight.vehicle_description}
            {flight.mission_revision !== null && ` · revision ${flight.mission_revision}`}
          </span>
          <span className="ml-auto flex gap-2">
            <a href={`/api/flights/${flight.id}/captures.csv`} className="inline-flex min-h-9 items-center gap-1.5 rounded-md border border-line bg-surface-3 px-2.5 text-[13px]">
              <Download size={14} /> Capture log (CSV)
            </a>
            <Button small variant="ghost" icon={<Trash2 size={14} />} onClick={() => void remove()}>
              Delete
            </Button>
          </span>
        </div>

        <div className="grid gap-3 lg:grid-cols-[1fr_300px]">
          <Panel>
            <div className="mb-3 grid grid-cols-3 gap-3 sm:grid-cols-6">
              <Stat label="Duration" value={duration(s.duration_s)} unit="min" />
              <Stat label="Distance" value={distance(s.distance_m)} />
              <Stat label="Max height" value={fixed(s.max_alt_m)} unit="m" />
              <Stat label="Max speed" value={fixed(s.max_speed_mps)} unit="m/s" />
              <Stat label="Photos" value={s.captures ?? 0} />
              <Stat
                label="Battery used"
                value={s.battery_start_pct != null && s.battery_end_pct != null ? Math.round(s.battery_start_pct - s.battery_end_pct) : '—'}
                unit="%"
              />
            </div>
            {points.length > 1 ? (
              <>
                <div className="mb-2 flex items-center gap-3">
                  <Button small variant="secondary" icon={playing ? <Pause size={14} /> : <Play size={14} />}
                    onClick={() => { if (cursor >= points.length - 1) setCursor(0); setPlaying((p) => !p) }}>
                    {playing ? 'Pause' : 'Replay'}
                  </Button>
                  <input
                    type="range"
                    aria-label="Position in the flight"
                    className="flex-1 accent-[var(--track)]"
                    min={0}
                    max={points.length - 1}
                    value={cursor}
                    onChange={(e) => { setPlaying(false); setCursor(Number(e.target.value)) }}
                  />
                  <span className="num w-24 text-right text-[12.5px] text-muted">
                    {duration(here?.t)} / {duration(points[points.length - 1].t)}
                  </span>
                </div>
                <div className="grid gap-2">
                  <Chart label="Height" unit="m" points={points} value={(p) => p.alt} color="var(--track)" cursor={cursor} onSeek={setCursor} />
                  <Chart label="Ground speed" unit="m/s" points={points} value={(p) => p.spd} color="var(--info)" cursor={cursor} onSeek={setCursor} />
                  <Chart label="Battery" unit="%" points={points} value={(p) => p.batt} color="var(--brand)" cursor={cursor} onSeek={setCursor} />
                </div>
              </>
            ) : (
              <p className="text-[13px] text-muted">No telemetry was recorded for this flight.</p>
            )}
          </Panel>
          <Panel title="What happened">
            {s.failsafes && s.failsafes.length > 0 && (
              <p role="alert" className="mb-2 rounded-md border border-danger/50 bg-danger/10 p-2 text-[12.5px]">
                {s.failsafes.join('; ')}
              </p>
            )}
            <ol className="space-y-1 text-[12.5px]">
              {flight.events
                .filter((e) => e.kind !== 'item_reached')
                .map((e, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="num w-10 shrink-0 text-muted">{duration(e.t)}</span>
                    <span className={e.severity === 'critical' ? 'text-danger' : e.severity === 'warning' ? 'text-warn' : ''}>{e.message}</span>
                  </li>
                ))}
            </ol>
          </Panel>
        </div>
      </div>
    </div>
  )
}

export function Flights() {
  const toast = useVehicle((s) => s.toast)
  const lastFlight = useVehicle((s) => s.summary?.last_flight_id)
  const [flights, setFlights] = useState<FlightSummary[]>([])
  const [detail, setDetail] = useState<FlightDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setFlights(await api.flights())
      setError(null)
    } catch (e) {
      setError((e as Error).message)
    }
  }, [])
  useEffect(() => {
    void load()
  }, [load, lastFlight])

  const open = async (id: number) => {
    try {
      setDetail(await api.flight(id))
    } catch (e) {
      toast('bad', (e as Error).message)
    }
  }

  const totals = useMemo(
    () => ({
      distance: flights.reduce((a, f) => a + (f.summary.distance_m ?? 0), 0),
      photos: flights.reduce((a, f) => a + (f.summary.captures ?? 0), 0),
      time: flights.reduce((a, f) => a + (f.summary.duration_s ?? 0), 0),
    }),
    [flights],
  )

  return (
    <div className="grid h-full grid-cols-[380px_1fr]">
      <aside className="scroll flex flex-col gap-3 border-r border-line bg-bg p-3">
        <h1 className="text-lg font-semibold">Flight records</h1>
        <div className="grid grid-cols-3 gap-2 rounded-lg border border-line bg-surface p-3">
          <Stat label="Flights" value={flights.length} />
          <Stat label="Flown" value={distance(totals.distance)} />
          <Stat label="Photos" value={totals.photos} />
        </div>
        {error && <p role="alert" className="rounded-md border border-danger/50 bg-danger/10 p-2.5 text-[13px]">{error}</p>}
        {flights.length === 0 && !error ? (
          <Empty title="No flights recorded yet">
            Every time a vehicle arms, the flight is recorded here with its track, photos and events, whether it is
            simulated or real.
          </Empty>
        ) : (
          <ul className="grid gap-2">
            {flights.map((f) => (
              <li key={f.id}>
                <button
                  type="button"
                  onClick={() => void open(f.id)}
                  className={`w-full rounded-lg border p-3 text-left transition hover:bg-surface-2 ${
                    detail?.id === f.id ? 'border-brand bg-brand/5' : 'border-line bg-surface'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate font-semibold">{f.mission_name}</span>
                    <Badge tone={STATUS_TONE[f.status]}>{f.status.replace('_', ' ')}</Badge>
                  </div>
                  <div className="mt-1 text-[12.5px] text-muted">{dateTime(f.started_at)}</div>
                  <div className="num mt-0.5 text-[12.5px] text-muted">
                    {f.vehicle_kind === 'sim' ? 'Simulated' : f.vehicle_kind === 'sitl' ? 'Software autopilot' : 'Real drone'} ·{' '}
                    {duration(f.summary.duration_s)} · {distance(f.summary.distance_m)} · {f.summary.captures ?? 0} photos
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </aside>
      {detail ? (
        <Replay
          flight={detail}
          onDeleted={() => {
            setDetail(null)
            void load()
          }}
        />
      ) : (
        <div className="grid place-items-center p-6">
          <Empty title="Select a flight">Its track, photos, charts and event log open here, with a replay.</Empty>
        </div>
      )}
    </div>
  )
}
