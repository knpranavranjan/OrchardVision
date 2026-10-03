import { Plus, Save, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'

import { Badge, Button, NumberField, Panel, SelectField, TextField, Toggle } from '../components/ui'
import { api, type AppSettings, type CameraProfile, type FailsafeAction, type Health } from '../lib/api'
import { useVehicle } from '../lib/store'

const ACTIONS: { value: FailsafeAction; label: string }[] = [
  { value: 'rtl', label: 'Return home' },
  { value: 'land', label: 'Land where it is' },
  { value: 'hold', label: 'Hold position' },
]

export function Settings() {
  const toast = useVehicle((s) => s.toast)
  const [settings, setSettings] = useState<AppSettings | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.settings().then(setSettings).catch((e: Error) => setError(e.message))
    api.health().then(setHealth).catch(() => undefined)
  }, [])

  const edit = (change: (s: AppSettings) => AppSettings) => {
    setSettings((s) => (s ? change(s) : s))
    setDirty(true)
  }

  const save = async () => {
    if (!settings) return
    setBusy(true)
    try {
      setSettings(await api.saveSettings(settings))
      setDirty(false)
      toast('good', 'Settings saved. They apply to new missions.')
    } catch (e) {
      toast('bad', (e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const camera = (index: number, change: Partial<CameraProfile>) =>
    edit((s) => ({ ...s, cameras: s.cameras.map((c, i) => (i === index ? { ...c, ...change } : c)) }))

  if (error) {
    return (
      <div className="p-6">
        <p role="alert" className="rounded-md border border-danger/50 bg-danger/10 p-3">Settings could not load: {error}</p>
      </div>
    )
  }
  if (!settings) return <div className="p-6 text-muted">Loading settings…</div>
  const { safety, vehicle } = settings

  return (
    <div className="scroll h-full p-5">
      <div className="mx-auto grid max-w-5xl gap-4">
        <header className="flex items-end justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold">Settings</h1>
            <p className="mt-1 max-w-[70ch] text-[13.5px] text-muted">
              Defaults for new missions. A saved mission keeps its own copy, so changing these never alters a mission
              that has already been planned or flown.
            </p>
          </div>
          <Button variant="primary" icon={<Save size={16} />} busy={busy} disabled={!dirty} onClick={() => void save()}>
            {dirty ? 'Save settings' : 'Saved'}
          </Button>
        </header>

        <div className="grid gap-4 lg:grid-cols-2">
          <Panel title="Safety limits">
            <div className="grid grid-cols-2 gap-3">
              <NumberField label="Height limit" unit="m" value={safety.max_alt_m} min={5} max={120} onChange={(v) => edit((s) => ({ ...s, safety: { ...s.safety, max_alt_m: v } }))} />
              <NumberField label="Lowest flight height" unit="m" value={safety.min_alt_m} min={1} max={50} onChange={(v) => edit((s) => ({ ...s, safety: { ...s.safety, min_alt_m: v } }))} />
              <NumberField label="Speed limit" unit="m/s" value={safety.max_speed_mps} min={1} max={20} onChange={(v) => edit((s) => ({ ...s, safety: { ...s.safety, max_speed_mps: v } }))} />
              <NumberField label="Return height" unit="m" value={safety.rtl_alt_m} min={5} max={120} onChange={(v) => edit((s) => ({ ...s, safety: { ...s.safety, rtl_alt_m: v } }))} />
            </div>
            <div className="mt-3">
              <Toggle label="Geofence required" hint="A mission without a geofence fails validation" checked={safety.fence_enabled} onChange={(v) => edit((s) => ({ ...s, safety: { ...s.safety, fence_enabled: v } }))} />
            </div>
          </Panel>

          <Panel title="Battery">
            <div className="grid grid-cols-3 gap-3">
              <NumberField label="Reserve" unit="%" value={safety.battery_reserve_pct} min={10} max={60} hint="Never planned for use" onChange={(v) => edit((s) => ({ ...s, safety: { ...s.safety, battery_reserve_pct: v } }))} />
              <NumberField label="Warning" unit="%" value={safety.battery_warn_pct} min={10} max={60} onChange={(v) => edit((s) => ({ ...s, safety: { ...s.safety, battery_warn_pct: v } }))} />
              <NumberField label="Critical" unit="%" value={safety.battery_crit_pct} min={5} max={50} onChange={(v) => edit((s) => ({ ...s, safety: { ...s.safety, battery_crit_pct: v } }))} />
            </div>
          </Panel>

          <Panel title="Emergency actions">
            <div className="grid gap-3 sm:grid-cols-2">
              <SelectField label="Link to ground station lost" value={safety.on_link_loss} options={ACTIONS.filter((a) => a.value !== 'hold')} onChange={(v) => edit((s) => ({ ...s, safety: { ...s.safety, on_link_loss: v } }))} />
              <SelectField label="Battery critical" value={safety.on_battery_critical} options={ACTIONS.filter((a) => a.value !== 'hold')} onChange={(v) => edit((s) => ({ ...s, safety: { ...s.safety, on_battery_critical: v } }))} />
              <SelectField label="GPS lost" value={safety.on_gps_loss} options={ACTIONS.filter((a) => a.value !== 'rtl')} hint="Without position the drone cannot navigate home" onChange={(v) => edit((s) => ({ ...s, safety: { ...s.safety, on_gps_loss: v } }))} />
              <SelectField label="Geofence crossed" value={safety.on_fence_breach} options={ACTIONS} onChange={(v) => edit((s) => ({ ...s, safety: { ...s.safety, on_fence_breach: v } }))} />
            </div>
            <p className="mt-3 text-[12.5px] leading-snug text-muted">
              These are uploaded to the drone with each mission and carried out by the autopilot itself, so they still
              work when the link to this computer is down.
            </p>
          </Panel>

          <Panel title="Drone">
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <TextField label="Name" value={vehicle.name} onChange={(v) => edit((s) => ({ ...s, vehicle: { ...s.vehicle, name: v } }))} />
              </div>
              <NumberField label="Flight time per battery" unit="min" value={vehicle.endurance_min} min={3} max={90} hint="Measured, not from the box" onChange={(v) => edit((s) => ({ ...s, vehicle: { ...s.vehicle, endurance_min: v } }))} />
              <NumberField label="Cruise speed" unit="m/s" value={vehicle.cruise_speed_mps} min={1} max={20} onChange={(v) => edit((s) => ({ ...s, vehicle: { ...s.vehicle, cruise_speed_mps: v } }))} />
              <NumberField label="Climb rate" unit="m/s" value={vehicle.climb_rate_mps} min={0.5} max={8} step={0.5} onChange={(v) => edit((s) => ({ ...s, vehicle: { ...s.vehicle, climb_rate_mps: v } }))} />
              <NumberField label="Descent rate" unit="m/s" value={vehicle.descent_rate_mps} min={0.5} max={5} step={0.5} onChange={(v) => edit((s) => ({ ...s, vehicle: { ...s.vehicle, descent_rate_mps: v } }))} />
            </div>
          </Panel>
        </div>

        <Panel
          title="Cameras"
          actions={
            <Button
              small
              variant="ghost"
              icon={<Plus size={14} />}
              onClick={() =>
                edit((s) => ({
                  ...s,
                  cameras: [...s.cameras, { ...s.cameras[0], id: `camera-${Date.now()}`, name: 'New camera' }],
                }))
              }
            >
              Add camera
            </Button>
          }
        >
          <div className="grid gap-3">
            {settings.cameras.map((c, i) => (
              <div key={c.id} className="rounded-lg border border-line p-3">
                <div className="mb-2 flex items-center gap-2">
                  <div className="flex-1">
                    <TextField label="Name" value={c.name} onChange={(v) => camera(i, { name: v })} />
                  </div>
                  {settings.default_camera_id === c.id ? (
                    <Badge tone="good" className="mt-5">Default</Badge>
                  ) : (
                    <Button small variant="ghost" className="mt-5" onClick={() => edit((s) => ({ ...s, default_camera_id: c.id }))}>
                      Make default
                    </Button>
                  )}
                  <Button
                    small
                    variant="ghost"
                    className="mt-5"
                    aria-label={`Remove ${c.name}`}
                    disabled={settings.cameras.length === 1 || settings.default_camera_id === c.id}
                    icon={<Trash2 size={14} />}
                    onClick={() => edit((s) => ({ ...s, cameras: s.cameras.filter((_, j) => j !== i) }))}
                  />
                </div>
                <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
                  <NumberField label="Sensor width" unit="mm" value={c.sensor_width_mm} step={0.01} onChange={(v) => camera(i, { sensor_width_mm: v })} />
                  <NumberField label="Sensor height" unit="mm" value={c.sensor_height_mm} step={0.01} onChange={(v) => camera(i, { sensor_height_mm: v })} />
                  <NumberField label="Lens" unit="mm" value={c.focal_length_mm} step={0.1} onChange={(v) => camera(i, { focal_length_mm: v })} />
                  <NumberField label="Image width" unit="px" value={c.image_width_px} onChange={(v) => camera(i, { image_width_px: Math.round(v) })} />
                  <NumberField label="Image height" unit="px" value={c.image_height_px} onChange={(v) => camera(i, { image_height_px: Math.round(v) })} />
                  <NumberField label="File size" unit="MB" value={c.image_mb} step={0.5} onChange={(v) => camera(i, { image_mb: v })} />
                </div>
              </div>
            ))}
          </div>
          <p className="mt-3 text-[12.5px] text-muted">
            These numbers decide line spacing and how often a photo is taken. Take them from the camera's data sheet.
          </p>
        </Panel>

        <div className="grid gap-4 lg:grid-cols-2">
          <Panel title="Map and connection defaults">
            <div className="grid grid-cols-2 gap-3">
              <NumberField label="Map latitude" value={settings.map_center.lat} step={0.0001} onChange={(v) => edit((s) => ({ ...s, map_center: { ...s.map_center, lat: v } }))} />
              <NumberField label="Map longitude" value={settings.map_center.lon} step={0.0001} onChange={(v) => edit((s) => ({ ...s, map_center: { ...s.map_center, lon: v } }))} />
              <div className="col-span-2">
                <TextField label="Software autopilot address" value={settings.sitl_url} onChange={(v) => edit((s) => ({ ...s, sitl_url: v }))} />
              </div>
              <div className="col-span-2">
                <TextField label="Network drone address" value={settings.udp_url} onChange={(v) => edit((s) => ({ ...s, udp_url: v }))} />
              </div>
              <SelectField label="Serial baud rate" value={settings.serial_baud} onChange={(v) => edit((s) => ({ ...s, serial_baud: v }))}
                options={[{ value: 57600, label: '57600 (radio)' }, { value: 115200, label: '115200 (USB)' }, { value: 921600, label: '921600' }]} />
            </div>
          </Panel>

          <Panel title="System">
            <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1.5 text-[13px]">
              <dt className="text-muted">Version</dt><dd className="num">{health?.version ?? '—'}</dd>
              <dt className="text-muted">Database</dt>
              <dd><Badge tone={health?.database === 'ok' ? 'good' : 'bad'}>{health?.database ?? 'unknown'}</Badge></dd>
              <dt className="text-muted">Model registry</dt>
              <dd><Badge tone={health?.registry.ok ? 'good' : 'bad'}>{health ? `${health.registry.crops} crop profile(s)` : 'unknown'}</Badge></dd>
              <dt className="text-muted">Autopilot support</dt><dd>ArduPilot Copter over MAVLink 2</dd>
            </dl>
            <p className="mt-3 text-[12.5px] leading-snug text-muted">
              Flying works without the database, but flights are then not recorded and orchards and missions cannot be
              opened. The pre-flight checklist warns when recording is unavailable.
            </p>
          </Panel>
        </div>
      </div>
    </div>
  )
}
