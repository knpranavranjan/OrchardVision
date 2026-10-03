import { ClipboardCheck, Crosshair, FlaskConical, Gamepad2, ScrollText, Upload } from 'lucide-react'
import type { Map as MlMap } from 'maplibre-gl'
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { CommandBar, EventLog, Instruments, ManualControl, MissionProgress, PreflightPanel } from '../components/flight'
import { MapView, useHomeMarker, useVehicleMarker } from '../components/MapView'
import { SimulatorControls } from '../components/SimulatorControls'
import { Button, Dialog, NumberField, SelectField } from '../components/ui'
import { api, type LatLon, type MissionSummary } from '../lib/api'
import { fitTo, type LngLat, pairToLngLat, setLine, setPoints, setPolygon, token } from '../lib/map'
import { useVehicle } from '../lib/store'

type Tab = 'checklist' | 'manual' | 'log' | 'sim'

const DEFAULT_CENTER: LatLon = { lat: 12.9716, lon: 77.5946 }

function MissionLoader() {
  const summary = useVehicle((s) => s.summary)
  const toast = useVehicle((s) => s.toast)
  const refresh = useVehicle((s) => s.refresh)
  const [missions, setMissions] = useState<MissionSummary[]>([])
  const [pick, setPick] = useState<number | null>(null)
  const [segment, setSegment] = useState(0)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api
      .missions()
      .then((m) => {
        setMissions(m)
        setPick((p) => p ?? m[0]?.id ?? null)
      })
      .catch(() => setMissions([]))
  }, [])

  const chosen = missions.find((m) => m.id === pick)
  const flights = chosen?.stats.flights_needed ?? 1

  const upload = async () => {
    if (pick === null) return
    setBusy(true)
    try {
      const result = await api.uploadMission(pick, segment)
      await refresh()
      const failed = result.steps.filter((s) => !s.ok)
      if (result.ok) toast('good', 'Mission uploaded and read back identical')
      else toast('bad', `Upload incomplete: ${failed.map((s) => `${s.step} (${s.message})`).join('; ')}`)
    } catch (e) {
      toast('bad', (e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (summary?.link !== 'connected') return null
  return (
    <div className="mb-3 rounded-lg border border-line bg-surface-2 p-2.5">
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted">Mission</div>
      {missions.length === 0 ? (
        <p className="text-[13px] text-muted">
          No saved missions.{' '}
          <Link to="/plan" className="text-info underline">
            Plan one
          </Link>
          , or fly by hand.
        </p>
      ) : (
        <div className="grid gap-2">
          <SelectField
            label="Saved mission"
            value={pick ?? 0}
            onChange={(v) => {
              setPick(v)
              setSegment(0)
            }}
            options={missions.map((m) => ({
              value: m.id,
              label: `${m.name}${m.valid ? '' : ' (not valid)'}`,
            }))}
          />
          {flights > 1 && (
            <SelectField
              label="Flight"
              value={segment}
              onChange={setSegment}
              options={Array.from({ length: flights }, (_, i) => ({ value: i, label: `Flight ${i + 1} of ${flights}` }))}
              hint="This mission needs more than one battery."
            />
          )}
          <Button variant="secondary" icon={<Upload size={16} />} busy={busy} disabled={!chosen?.valid || summary.flying} onClick={upload}>
            Upload to vehicle
          </Button>
        </div>
      )}
    </div>
  )
}

export function Fly() {
  const [map, setMap] = useState<MlMap | null>(null)
  const [tab, setTab] = useState<Tab>('checklist')
  const [follow, setFollow] = useState(true)
  const [flyTo, setFlyTo] = useState(false)
  const [target, setTarget] = useState<LatLon | null>(null)
  const [targetAlt, setTargetAlt] = useState(15)

  const geometry = useVehicle((s) => s.geometry)
  const track = useVehicle((s) => s.track)
  const captures = useVehicle((s) => s.captures)
  const events = useVehicle((s) => s.events)
  const kind = useVehicle((s) => s.summary?.kind)
  const state = useVehicle((s) => s.state)
  const toast = useVehicle((s) => s.toast)

  useVehicleMarker(map, follow)
  const home = state && state.home_lat !== null && state.home_lon !== null ? { lat: state.home_lat, lon: state.home_lon } : null
  // Stable identity so the marker is not rebuilt on every telemetry message.
  const homeKey = home ? `${home.lat.toFixed(7)},${home.lon.toFixed(7)}` : ''
  const [stableHome, setStableHome] = useState<LatLon | null>(null)
  useEffect(() => {
    setStableHome(home)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [homeKey])
  useHomeMarker(map, stableHome, null, token('--brand'))

  // Planned geometry
  useEffect(() => {
    if (!map) return
    const fence = (geometry?.geofence ?? []).map(pairToLngLat)
    const area = (geometry?.area ?? []).map(pairToLngLat)
    const route = (geometry?.route ?? []).map(pairToLngLat)
    setPolygon(map, 'fly-area', area, { color: token('--plan'), fillOpacity: 0.08, width: 1.5 })
    setPolygon(map, 'fly-fence', fence, { color: token('--fence'), fillOpacity: 0, width: 2, dash: [3, 2] })
    setLine(map, 'fly-route', route, { color: token('--plan'), width: 2, dash: [2, 1.5] })
    const all: LngLat[] = [...fence, ...route]
    if (all.length) fitTo(map, all, 90)
  }, [map, geometry])

  // What actually happened
  useEffect(() => {
    if (!map) return
    setLine(map, 'fly-track', track, { color: token('--track'), width: 3.5 })
    setPoints(map, 'fly-captures', captures, { color: '#ffffff', radius: 2.6 })
  }, [map, track, captures])

  useEffect(() => {
    if (!map || !target) return
    setPoints(map, 'fly-target', [[target.lon, target.lat]], { color: token('--warn'), radius: 8, stroke: '#fff' })
    return () => setPoints(map, 'fly-target', [], { color: token('--warn') })
  }, [map, target])

  const onMapClick = useCallback(
    (at: LatLon) => {
      if (!flyTo) return
      setTarget(at)
      setTargetAlt(Math.max(5, Math.round(useVehicle.getState().state?.alt_rel_m ?? 15)))
      setFlyTo(false)
    },
    [flyTo],
  )

  const confirmFlyTo = async () => {
    if (!target) return
    const result = await api.command('goto', { lat: target.lat, lon: target.lon, alt_m: targetAlt })
    if (!result.accepted) toast('bad', result.message)
    setTarget(null)
  }

  const tabs: { id: Tab; label: string; icon: typeof ClipboardCheck }[] = [
    { id: 'checklist', label: 'Pre-flight', icon: ClipboardCheck },
    { id: 'manual', label: 'Manual', icon: Gamepad2 },
    { id: 'log', label: 'Log', icon: ScrollText },
    ...(kind === 'sim' ? [{ id: 'sim' as Tab, label: 'Simulator', icon: FlaskConical }] : []),
  ]

  return (
    <div className="grid h-full grid-cols-[1fr_340px]">
      <MapView center={DEFAULT_CENTER} onReady={setMap} onClick={onMapClick} crosshair={flyTo} className="h-full">
        <div className="pointer-events-none absolute inset-0 flex flex-col justify-between p-3">
          <div className="flex items-start justify-between gap-3">
            <div className="pointer-events-auto">
              <Instruments />
            </div>
            <div className="pointer-events-auto w-full max-w-md">
              <MissionProgress />
            </div>
            <button
              type="button"
              onClick={() => setFollow((v) => !v)}
              aria-pressed={follow}
              title="Keep the vehicle in the centre of the map"
              className={`pointer-events-auto flex min-h-10 items-center gap-1.5 rounded-md border px-2.5 text-[12.5px]
                shadow-xl backdrop-blur ${follow ? 'border-brand bg-brand/20 text-brand' : 'border-line bg-overlay text-muted'}`}
            >
              <Crosshair size={16} /> Follow
            </button>
          </div>
          <div className="pointer-events-auto mx-auto mb-6 max-w-full">
            <CommandBar onFlyTo={() => setFlyTo((v) => !v)} flyToActive={flyTo} />
          </div>
        </div>
      </MapView>

      <aside className="flex min-h-0 flex-col border-l border-line bg-surface">
        <div role="tablist" className="flex border-b border-line">
          {tabs.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={tab === t.id}
              onClick={() => setTab(t.id)}
              className={`flex min-h-12 flex-1 flex-col items-center justify-center gap-0.5 text-[11px] font-medium
                transition ${tab === t.id ? 'border-b-2 border-brand text-brand' : 'text-muted hover:text-ink'}`}
            >
              <t.icon size={17} />
              {t.label}
            </button>
          ))}
        </div>
        <div className="scroll min-h-0 flex-1 p-3">
          {tab === 'checklist' && (
            <>
              <MissionLoader />
              <PreflightPanel />
            </>
          )}
          {tab === 'manual' && <ManualControl />}
          {tab === 'log' && <EventLog events={events} />}
          {tab === 'sim' && <SimulatorControls />}
        </div>
      </aside>

      {target && (
        <Dialog
          title="Fly to this point?"
          onClose={() => setTarget(null)}
          footer={
            <>
              <Button onClick={() => setTarget(null)}>Cancel</Button>
              <Button variant="primary" onClick={confirmFlyTo}>
                Fly there
              </Button>
            </>
          }
        >
          <p className="num text-[13px] text-muted">
            {target.lat.toFixed(6)}, {target.lon.toFixed(6)}
          </p>
          <div className="mt-3 w-40">
            <NumberField label="Height" unit="m" value={targetAlt} onChange={setTargetAlt} min={2} max={120} />
          </div>
          <p className="mt-3 text-[12.5px] text-muted">
            The vehicle flies there in a straight line and holds. It will not leave the geofence.
          </p>
        </Dialog>
      )}
    </div>
  )
}
