import {
  Download,
  FlaskConical,
  MapPin,
  Pentagon,
  Save,
  Shield,
  Trash2,
  Upload,
  Waypoints,
} from 'lucide-react'
import type { Map as MlMap } from 'maplibre-gl'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { MapView, useHomeMarker, useVertexEditor } from '../components/MapView'
import { Badge, Button, CheckRow, NumberField, Panel, SelectField, Stat, TextField, Toggle } from '../components/ui'
import {
  api,
  type AppSettings,
  type Evaluation,
  type FailsafeAction,
  type LatLon,
  type MissionPlan,
  type MissionSummary,
  type Orchard,
  type WaypointSpec,
} from '../lib/api'
import { boundingFence } from '../lib/conventions'
import { distance, duration, fixed } from '../lib/format'
import { fitTo, pairToLngLat, setLine, setPoints, setPolygon, token, toLngLat } from '../lib/map'
import { useVehicle } from '../lib/store'

type Tool = 'area' | 'fence' | 'waypoints' | null

// Stable empty lists, so "nothing drawn" does not look like a change on every render.
const NONE: LatLon[] = []
const NO_WAYPOINTS: WaypointSpec[] = []

const ACTIONS: { value: FailsafeAction; label: string }[] = [
  { value: 'rtl', label: 'Return home' },
  { value: 'land', label: 'Land where it is' },
  { value: 'hold', label: 'Hold position' },
]

function newPlan(settings: AppSettings, home: LatLon): MissionPlan {
  const camera = settings.cameras.find((c) => c.id === settings.default_camera_id) ?? settings.cameras[0]
  return {
    type: 'survey',
    home,
    takeoff_alt_m: 25,
    survey: {
      polygon: [],
      altitude_m: 25,
      speed_mps: 3,
      front_overlap: 0.8,
      side_overlap: 0.7,
      angle_deg: 0,
      gimbal_pitch_deg: -90,
      overshoot_m: 0,
    },
    waypoints: [],
    waypoint_speed_mps: 4,
    waypoint_capture_distance_m: 0,
    waypoint_gimbal_pitch_deg: -90,
    geofence: [],
    end_action: 'rtl',
    safety: settings.safety,
    camera,
    vehicle: settings.vehicle,
  }
}

export function Plan() {
  const navigate = useNavigate()
  const toast = useVehicle((s) => s.toast)
  const refreshVehicle = useVehicle((s) => s.refresh)
  const link = useVehicle((s) => s.summary?.link)
  const flying = useVehicle((s) => s.summary?.flying)

  const [map, setMap] = useState<MlMap | null>(null)
  const [settings, setSettings] = useState<AppSettings | null>(null)
  const [orchards, setOrchards] = useState<Orchard[]>([])
  const [missions, setMissions] = useState<MissionSummary[]>([])

  const [missionId, setMissionId] = useState<number | null>(null)
  const [revision, setRevision] = useState<number | null>(null)
  const [name, setName] = useState('New mission')
  const [orchardId, setOrchardId] = useState<number | null>(null)
  const [plan, setPlan] = useState<MissionPlan | null>(null)
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null)
  const [dirty, setDirty] = useState(false)
  const [tool, setTool] = useState<Tool>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  // ------------------------------------------------------------------ loading
  useEffect(() => {
    Promise.all([api.settings(), api.orchards(), api.missions()])
      .then(([s, o, m]) => {
        setSettings(s)
        setOrchards(o)
        setMissions(m)
        setPlan(newPlan(s, s.map_center))
      })
      .catch((e: Error) => setError(e.message))
  }, [])

  const edit = useCallback((change: (p: MissionPlan) => MissionPlan) => {
    setPlan((p) => (p ? change(p) : p))
    setDirty(true)
  }, [])

  const open = async (id: number | null) => {
    setTool(null)
    if (id === null) {
      if (!settings) return
      const at = map ? { lat: map.getCenter().lat, lon: map.getCenter().lng } : settings.map_center
      setMissionId(null)
      setRevision(null)
      setName('New mission')
      setPlan(newPlan(settings, at))
      setEvaluation(null)
      setDirty(false)
      return
    }
    try {
      const m = await api.mission(id)
      setMissionId(m.id)
      setRevision(m.revision)
      setName(m.name)
      setOrchardId(m.orchard_id)
      setPlan(m.plan)
      setEvaluation(m)
      setDirty(false)
      if (map) fitTo(map, [...m.plan.geofence.map(toLngLat), ...m.route.map(pairToLngLat)], 70)
    } catch (e) {
      toast('bad', (e as Error).message)
    }
  }

  // ------------------------------------------------------------------ live preview
  const previewTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  useEffect(() => {
    if (!plan) return
    clearTimeout(previewTimer.current)
    previewTimer.current = setTimeout(() => {
      api
        .previewMission(plan, orchardId)
        .then((e) => {
          setEvaluation(e)
          setError(null)
        })
        .catch((e: Error) => setError(e.message))
    }, 250)
    return () => clearTimeout(previewTimer.current)
  }, [plan, orchardId])

  // ------------------------------------------------------------------ map drawing
  const area = plan?.survey?.polygon ?? NONE
  const fence = plan?.geofence ?? NONE
  const waypoints = plan?.waypoints ?? NO_WAYPOINTS
  const isSurvey = plan?.type === 'survey'

  useEffect(() => {
    if (!map || !plan) return
    setPolygon(map, 'plan-area', isSurvey ? area.map(toLngLat) : [], { color: token('--plan'), fillOpacity: 0.14 })
    setPolygon(map, 'plan-fence', fence.map(toLngLat), { color: token('--fence'), fillOpacity: 0, dash: [3, 2] })
  }, [map, plan, area, fence, isSurvey])

  useEffect(() => {
    if (!map) return
    const route = (evaluation?.route ?? []).map(pairToLngLat)
    setLine(map, 'plan-route', route, { color: token('--track'), width: 2.2 })
    setPoints(map, 'plan-captures', (evaluation?.capture_points ?? []).map(pairToLngLat), { color: '#ffffff', radius: 2 })
  }, [map, evaluation])

  useVertexEditor(map, {
    points: isSurvey ? area : NONE,
    onChange: (points) => edit((p) => ({ ...p, survey: { ...p.survey!, polygon: points } })),
    active: tool === 'area',
    color: token('--plan') || '#4cc2ff',
  })
  useVertexEditor(map, {
    points: fence,
    onChange: (points) => edit((p) => ({ ...p, geofence: points })),
    active: tool === 'fence',
    color: token('--fence') || '#ff5a4f',
  })
  useVertexEditor(map, {
    points: isSurvey ? NONE : waypoints,
    onChange: (points) => edit((p) => ({ ...p, waypoints: points as WaypointSpec[] })),
    active: tool === 'waypoints',
    color: token('--plan') || '#4cc2ff',
    kind: 'waypoint',
    closed: false,
  })
  useHomeMarker(
    map,
    plan?.home ?? null,
    useCallback((home: LatLon) => edit((p) => ({ ...p, home })), [edit]),
    token('--brand') || '#3ddc84',
  )

  const onMapClick = useCallback(
    (at: LatLon) => {
      if (tool === 'area') edit((p) => ({ ...p, survey: { ...p.survey!, polygon: [...p.survey!.polygon, at] } }))
      else if (tool === 'fence') edit((p) => ({ ...p, geofence: [...p.geofence, at] }))
      else if (tool === 'waypoints')
        edit((p) => ({
          ...p,
          waypoints: [...p.waypoints, { ...at, alt_m: p.takeoff_alt_m, hold_s: 0, speed_mps: null }],
        }))
    },
    [tool, edit],
  )

  // ------------------------------------------------------------------ helpers
  const orchard = orchards.find((o) => o.id === orchardId) ?? null

  const useOrchardBoundary = () => {
    if (!orchard || orchard.boundary.length < 3) return
    edit((p) => ({ ...p, type: 'survey', home: p.home, survey: { ...p.survey!, polygon: orchard.boundary } }))
    if (map) fitTo(map, orchard.boundary.map(toLngLat), 80)
  }

  const autoFence = () => {
    if (!plan) return
    const points = [...(isSurvey ? area : waypoints), plan.home]
    edit((p) => ({ ...p, geofence: boundingFence(points, 20) }))
  }

  const moveHomeHere = () => {
    if (!map) return
    const c = map.getCenter()
    edit((p) => ({ ...p, home: { lat: c.lat, lon: c.lng } }))
  }

  const save = async (): Promise<number | null> => {
    if (!plan) return null
    setBusy('save')
    try {
      const saved =
        missionId === null
          ? await api.createMission(name, orchardId, plan)
          : await api.updateMission(missionId, name, orchardId, plan)
      setMissionId(saved.id)
      setRevision(saved.revision)
      setEvaluation(saved)
      setDirty(false)
      setMissions(await api.missions())
      toast('good', `Saved as revision ${saved.revision}`)
      return saved.id
    } catch (e) {
      toast('bad', (e as Error).message)
      return null
    } finally {
      setBusy(null)
    }
  }

  const upload = async (simulate: boolean) => {
    if (!plan) return
    setBusy(simulate ? 'simulate' : 'upload')
    try {
      const id = dirty || missionId === null ? await save() : missionId
      if (id === null) return
      if (simulate && link !== 'connected') {
        await api.connect({ kind: 'sim', sim: { home_lat: plan.home.lat, home_lon: plan.home.lon, speedup: 5 } })
      }
      const result = await api.uploadMission(id, 0)
      await refreshVehicle()
      if (result.ok) {
        toast('good', simulate ? 'Mission loaded in the simulator. Arm and start it on the Fly screen.' : 'Mission uploaded and read back identical')
        navigate('/')
      } else {
        toast('bad', `Upload incomplete: ${result.steps.filter((s) => !s.ok).map((s) => s.step).join(', ')}`)
      }
    } catch (e) {
      toast('bad', (e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  const remove = async () => {
    if (missionId === null || !window.confirm(`Delete the mission "${name}"? Flight records are kept.`)) return
    await api.deleteMission(missionId)
    setMissions(await api.missions())
    await open(null)
  }

  const stats = evaluation?.stats
  const validation = evaluation?.validation
  const canUpload = validation?.ok && link === 'connected' && !flying

  const camerasOptions = useMemo(
    () => (settings?.cameras ?? []).map((c) => ({ value: c.id, label: c.name })),
    [settings],
  )

  if (error && !plan) {
    return (
      <div className="p-6">
        <p role="alert" className="rounded-md border border-danger/50 bg-danger/10 p-3">
          The planner could not load: {error}
        </p>
      </div>
    )
  }
  if (!plan || !settings) return <div className="p-6 text-muted">Loading the planner…</div>

  return (
    <div className="grid h-full grid-cols-[340px_1fr_320px]">
      {/* ------------------------------------------------------------ left: what to fly */}
      <aside className="scroll flex flex-col gap-3 border-r border-line bg-bg p-3">
        <Panel title="Mission">
          <div className="grid gap-3">
            <SelectField
              label="Open"
              value={missionId ?? 0}
              onChange={(v) => void open(v === 0 ? null : v)}
              options={[{ value: 0, label: 'New mission' }, ...missions.map((m) => ({ value: m.id, label: m.name }))]}
            />
            <TextField label="Name" value={name} onChange={(v) => { setName(v); setDirty(true) }} />
            <SelectField
              label="Orchard"
              value={orchardId ?? 0}
              onChange={(v) => { setOrchardId(v === 0 ? null : v); setDirty(true) }}
              options={[{ value: 0, label: 'None' }, ...orchards.map((o) => ({ value: o.id, label: `${o.name} (${o.crop})` }))]}
              hint={orchard ? orchard.models_detail : 'Choosing an orchard checks image detail against its crop models.'}
            />
            <div role="radiogroup" aria-label="Mission type" className="grid grid-cols-2 gap-2">
              {([['survey', 'Area survey', Pentagon], ['waypoints', 'Waypoints', Waypoints]] as const).map(([type, label, Icon]) => (
                <button
                  key={type}
                  type="button"
                  role="radio"
                  aria-checked={plan.type === type}
                  onClick={() => { edit((p) => ({ ...p, type })); setTool(null) }}
                  className={`flex min-h-11 items-center justify-center gap-2 rounded-md border text-[13px] transition ${
                    plan.type === type ? 'border-brand bg-brand/10' : 'border-line text-muted hover:bg-surface-2'
                  }`}
                >
                  <Icon size={16} /> {label}
                </button>
              ))}
            </div>
          </div>
        </Panel>

        <Panel title="Draw on the map">
          <div className="grid grid-cols-2 gap-2">
            <Button
              variant={tool === (isSurvey ? 'area' : 'waypoints') ? 'primary' : 'secondary'}
              icon={isSurvey ? <Pentagon size={16} /> : <Waypoints size={16} />}
              onClick={() => setTool(tool === (isSurvey ? 'area' : 'waypoints') ? null : isSurvey ? 'area' : 'waypoints')}
            >
              {isSurvey ? 'Survey area' : 'Waypoints'}
            </Button>
            <Button variant={tool === 'fence' ? 'primary' : 'secondary'} icon={<Shield size={16} />} onClick={() => setTool(tool === 'fence' ? null : 'fence')}>
              Geofence
            </Button>
            <Button small variant="ghost" onClick={autoFence}>Fence 20 m around</Button>
            <Button small variant="ghost" icon={<MapPin size={14} />} onClick={moveHomeHere}>Home to map centre</Button>
            {orchard && orchard.boundary.length >= 3 && isSurvey && (
              <Button small variant="ghost" className="col-span-2" onClick={useOrchardBoundary}>
                Use the orchard boundary as the area
              </Button>
            )}
            <Button
              small
              variant="ghost"
              className="col-span-2"
              onClick={() => edit((p) => ({ ...p, geofence: [], waypoints: [], survey: p.survey ? { ...p.survey, polygon: [] } : null }))}
            >
              Clear everything drawn
            </Button>
          </div>
          <p className="mt-2 text-[12px] leading-snug text-muted">
            {tool
              ? 'Click the map to add a corner. Drag a corner to move it. Click a faint dot to add one between two corners. Right-click a corner to remove it.'
              : 'Pick a tool to draw. Drag the H marker to set where the drone takes off and lands.'}
          </p>
        </Panel>

        {isSurvey && plan.survey ? (
          <Panel title="Survey settings">
            <div className="grid grid-cols-2 gap-3">
              <NumberField label="Height" unit="m" value={plan.survey.altitude_m} min={3} max={120}
                onChange={(v) => edit((p) => ({ ...p, takeoff_alt_m: v, survey: { ...p.survey!, altitude_m: v } }))} />
              <NumberField label="Speed" unit="m/s" value={plan.survey.speed_mps} min={0.5} max={15} step={0.5}
                onChange={(v) => edit((p) => ({ ...p, survey: { ...p.survey!, speed_mps: v } }))} />
              <NumberField label="Front overlap" unit="%" value={Math.round(plan.survey.front_overlap * 100)} min={0} max={94}
                onChange={(v) => edit((p) => ({ ...p, survey: { ...p.survey!, front_overlap: Math.min(0.94, Math.max(0, v / 100)) } }))} />
              <NumberField label="Side overlap" unit="%" value={Math.round(plan.survey.side_overlap * 100)} min={0} max={94}
                onChange={(v) => edit((p) => ({ ...p, survey: { ...p.survey!, side_overlap: Math.min(0.94, Math.max(0, v / 100)) } }))} />
              <NumberField label="Line direction" unit="degrees" value={plan.survey.angle_deg} min={0} max={359} step={5}
                hint="0 flies north-south"
                onChange={(v) => edit((p) => ({ ...p, survey: { ...p.survey!, angle_deg: v } }))} />
              <NumberField label="Camera tilt" unit="degrees" value={plan.survey.gimbal_pitch_deg} min={-90} max={0} step={5}
                hint="-90 looks straight down"
                onChange={(v) => edit((p) => ({ ...p, survey: { ...p.survey!, gimbal_pitch_deg: v } }))} />
            </div>
          </Panel>
        ) : (
          <Panel title="Waypoint settings">
            <div className="grid grid-cols-2 gap-3">
              <NumberField label="Take-off height" unit="m" value={plan.takeoff_alt_m} min={3} max={120}
                onChange={(v) => edit((p) => ({ ...p, takeoff_alt_m: v }))} />
              <NumberField label="Speed" unit="m/s" value={plan.waypoint_speed_mps} min={0.5} max={15} step={0.5}
                onChange={(v) => edit((p) => ({ ...p, waypoint_speed_mps: v }))} />
              <NumberField label="Photo every" unit="m" value={plan.waypoint_capture_distance_m} min={0} max={100}
                hint="0 takes no photos"
                onChange={(v) => edit((p) => ({ ...p, waypoint_capture_distance_m: v }))} />
              <NumberField label="Camera tilt" unit="degrees" value={plan.waypoint_gimbal_pitch_deg} min={-90} max={0} step={5}
                onChange={(v) => edit((p) => ({ ...p, waypoint_gimbal_pitch_deg: v }))} />
            </div>
            {waypoints.length > 0 && (
              <table className="mt-3 w-full text-[12.5px]">
                <thead className="text-left text-[11px] uppercase text-muted">
                  <tr><th className="pb-1">#</th><th>Height (m)</th><th>Hold (s)</th><th /></tr>
                </thead>
                <tbody>
                  {waypoints.map((w, i) => (
                    <tr key={i}>
                      <td className="num pr-2">{i + 1}</td>
                      <td className="pr-2">
                        <input aria-label={`Waypoint ${i + 1} height`} type="number" className="num min-h-9 w-20 rounded border border-line bg-surface-2 px-2" value={w.alt_m} min={3}
                          onChange={(e) => edit((p) => ({ ...p, waypoints: p.waypoints.map((x, j) => (j === i ? { ...x, alt_m: Number(e.target.value) || x.alt_m } : x)) }))} />
                      </td>
                      <td className="pr-2">
                        <input aria-label={`Waypoint ${i + 1} hold time`} type="number" className="num min-h-9 w-20 rounded border border-line bg-surface-2 px-2" value={w.hold_s} min={0}
                          onChange={(e) => edit((p) => ({ ...p, waypoints: p.waypoints.map((x, j) => (j === i ? { ...x, hold_s: Math.max(0, Number(e.target.value)) } : x)) }))} />
                      </td>
                      <td>
                        <button type="button" aria-label={`Remove waypoint ${i + 1}`} className="grid size-9 place-items-center rounded text-muted hover:bg-surface-3 hover:text-danger"
                          onClick={() => edit((p) => ({ ...p, waypoints: p.waypoints.filter((_, j) => j !== i) }))}>
                          <Trash2 size={15} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Panel>
        )}

        <Panel title="Camera and ending">
          <div className="grid gap-3">
            <SelectField label="Camera" value={plan.camera.id} options={camerasOptions}
              onChange={(id) => edit((p) => ({ ...p, camera: settings.cameras.find((c) => c.id === id) ?? p.camera }))} />
            <SelectField label="At the end" value={plan.end_action}
              options={[{ value: 'rtl', label: 'Return home and land' }, { value: 'land', label: 'Fly home at survey height, then land' }]}
              onChange={(v) => edit((p) => ({ ...p, end_action: v }))} />
          </div>
        </Panel>

        <details className="rounded-lg border border-line bg-surface">
          <summary className="flex min-h-11 items-center px-3 text-[13px] font-semibold uppercase tracking-wide text-muted">
            Safety for this mission
          </summary>
          <div className="grid gap-3 border-t border-line p-3">
            <Toggle label="Geofence" checked={plan.safety.fence_enabled} hint="The drone refuses to leave the fence"
              onChange={(v) => edit((p) => ({ ...p, safety: { ...p.safety, fence_enabled: v } }))} />
            <div className="grid grid-cols-2 gap-3">
              <NumberField label="Height limit" unit="m" value={plan.safety.max_alt_m} min={5} max={120}
                onChange={(v) => edit((p) => ({ ...p, safety: { ...p.safety, max_alt_m: v } }))} />
              <NumberField label="Return height" unit="m" value={plan.safety.rtl_alt_m} min={5} max={120}
                onChange={(v) => edit((p) => ({ ...p, safety: { ...p.safety, rtl_alt_m: v } }))} />
              <NumberField label="Battery reserve" unit="%" value={plan.safety.battery_reserve_pct} min={10} max={60}
                onChange={(v) => edit((p) => ({ ...p, safety: { ...p.safety, battery_reserve_pct: v } }))} />
              <NumberField label="Critical battery" unit="%" value={plan.safety.battery_crit_pct} min={5} max={50}
                onChange={(v) => edit((p) => ({ ...p, safety: { ...p.safety, battery_crit_pct: v } }))} />
            </div>
            <SelectField label="If the link is lost" value={plan.safety.on_link_loss} options={ACTIONS.filter((a) => a.value !== 'hold')}
              onChange={(v) => edit((p) => ({ ...p, safety: { ...p.safety, on_link_loss: v } }))} />
            <SelectField label="If the battery is critical" value={plan.safety.on_battery_critical} options={ACTIONS.filter((a) => a.value !== 'hold')}
              onChange={(v) => edit((p) => ({ ...p, safety: { ...p.safety, on_battery_critical: v } }))} />
            <SelectField label="If GPS is lost" value={plan.safety.on_gps_loss} options={ACTIONS.filter((a) => a.value !== 'rtl')}
              onChange={(v) => edit((p) => ({ ...p, safety: { ...p.safety, on_gps_loss: v } }))} />
            <SelectField label="If the geofence is crossed" value={plan.safety.on_fence_breach} options={ACTIONS}
              onChange={(v) => edit((p) => ({ ...p, safety: { ...p.safety, on_fence_breach: v } }))} />
          </div>
        </details>
      </aside>

      {/* ------------------------------------------------------------ centre: the map */}
      <MapView
        center={settings.map_center}
        onReady={setMap}
        onClick={onMapClick}
        crosshair={tool !== null}
        className="h-full"
        placeAction={{
          label: 'Set the take-off point here',
          onPick: (home) => {
            edit((p) => ({ ...p, home }))
            toast('good', 'Take-off point moved. Draw the survey area around it.')
          },
        }}
      >
        {tool && (
          <div className="absolute left-1/2 top-3 -translate-x-1/2 rounded-full border border-brand bg-overlay px-4 py-1.5 text-[13px] shadow-xl backdrop-blur">
            Drawing: <b>{tool === 'area' ? 'survey area' : tool === 'fence' ? 'geofence' : 'waypoints'}</b>
            <button type="button" className="ml-3 text-info underline" onClick={() => setTool(null)}>
              Done
            </button>
          </div>
        )}
      </MapView>

      {/* ------------------------------------------------------------ right: is it flyable */}
      <aside className="scroll flex flex-col gap-3 border-l border-line bg-bg p-3">
        <Panel
          title="Estimate"
          actions={
            revision !== null && (
              <Badge tone={dirty ? 'warn' : 'muted'}>{dirty ? 'unsaved changes' : `revision ${revision}`}</Badge>
            )
          }
        >
          {stats && stats.item_count > 0 ? (
            <div className="grid grid-cols-2 gap-x-3 gap-y-3">
              <Stat label="Flight time" value={duration(stats.time_s)} unit="min" />
              <Stat label="Battery" value={Math.round(stats.battery_pct)} unit="%" tone={stats.battery_pct > 100 - plan.safety.battery_reserve_pct ? 'warn' : undefined} />
              <Stat label="Distance" value={distance(stats.distance_m)} />
              <Stat label="Photos" value={stats.photos} />
              {isSurvey && (
                <>
                  <Stat label="Area" value={fixed(stats.area_ha, 2)} unit="ha" />
                  <Stat label="Flight lines" value={stats.lines} />
                  <Stat label="Image detail" value={fixed(stats.gsd_cm, 2)} unit="cm/px" />
                  <Stat label="Line spacing" value={fixed(stats.line_spacing_m)} unit="m" />
                  <Stat label="Photo every" value={fixed(stats.trigger_distance_m)} unit="m" />
                  <Stat label="Photo covers" value={`${fixed(stats.footprint_across_m, 0)}×${fixed(stats.footprint_along_m, 0)}`} unit="m" />
                </>
              )}
              <Stat label="Storage" value={fixed(stats.storage_mb, 0)} unit="MB" />
              <Stat label="Flights needed" value={stats.flights_needed} tone={stats.flights_needed > 1 ? 'warn' : undefined} />
            </div>
          ) : (
            <p className="text-[13px] text-muted">
              {isSurvey ? 'Draw a survey area with at least three corners.' : 'Add at least one waypoint.'}
            </p>
          )}
          {evaluation && evaluation.segments.length > 1 && (
            <ul className="mt-3 space-y-1 border-t border-line pt-2 text-[12.5px]">
              {evaluation.segments.map((s) => (
                <li key={s.index} className="num flex justify-between text-muted">
                  <span>Flight {s.index + 1}: lines {(s.first_line ?? 0) + 1}–{(s.last_line ?? 0) + 1}</span>
                  <span>{duration(s.estimate.time_s)} · {Math.round(s.estimate.battery_pct)}%</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="Validation" actions={validation && <Badge tone={validation.ok ? 'good' : 'bad'}>{validation.ok ? 'Ready' : 'Blocked'}</Badge>}>
          {validation ? (
            <ul className="divide-y divide-line/60">
              {validation.checks.map((c) => (
                <CheckRow key={c.id} status={c.status} label={c.label} detail={c.detail} />
              ))}
            </ul>
          ) : (
            <p className="text-[13px] text-muted">Checking…</p>
          )}
          {error && <p role="alert" className="mt-2 text-[12.5px] text-danger">{error}</p>}
        </Panel>

        <div className="grid gap-2">
          <Button variant="primary" icon={<Save size={16} />} busy={busy === 'save'} disabled={!dirty && missionId !== null} onClick={() => void save()}>
            {missionId === null ? 'Save mission' : dirty ? 'Save changes' : 'Saved'}
          </Button>
          {link === 'connected' ? (
            <Button icon={<Upload size={16} />} busy={busy === 'upload'} disabled={!canUpload} onClick={() => void upload(false)}>
              Upload to the connected vehicle
            </Button>
          ) : (
            <Button icon={<FlaskConical size={16} />} busy={busy === 'simulate'} disabled={!validation?.ok} onClick={() => void upload(true)}>
              Rehearse in the simulator
            </Button>
          )}
          {!validation?.ok && <p className="text-[12px] text-muted">Fix the failed checks to enable upload.</p>}
          {missionId !== null && !dirty && (
            <div className="mt-1 rounded-lg border border-line p-2.5">
              <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">
                <Download size={13} /> Export
              </div>
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-[13px]">
                <a className="text-info underline" href={`/api/missions/${missionId}/export/qgc`}>QGroundControl plan</a>
                <a className="text-info underline" href={`/api/missions/${missionId}/export/waypoints`}>Waypoint file</a>
                <a className="text-info underline" href={`/api/missions/${missionId}/export/kml`}>KML</a>
              </div>
            </div>
          )}
          {missionId !== null && (
            <Button variant="ghost" small icon={<Trash2 size={14} />} onClick={() => void remove()}>
              Delete this mission
            </Button>
          )}
        </div>
      </aside>
    </div>
  )
}
