import { FlaskConical, Play } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { SimulatorControls } from '../components/SimulatorControls'
import { Badge, Button, Empty, NumberField, Panel, SelectField, Toggle } from '../components/ui'
import { api, type FlightSummary, type MissionSummary } from '../lib/api'
import { dateTime, distance, duration } from '../lib/format'
import { armScenario, FAILURES, type Failure } from '../lib/scenario'
import { useVehicle } from '../lib/store'

/**
 * The simulation planner: rehearse a saved mission on the virtual drone, with a
 * chosen failure, before it is ever flown for real.
 */
export function Simulation() {
  const navigate = useNavigate()
  const summary = useVehicle((s) => s.summary)
  const refresh = useVehicle((s) => s.refresh)
  const toast = useVehicle((s) => s.toast)

  const [missions, setMissions] = useState<MissionSummary[]>([])
  const [flights, setFlights] = useState<FlightSummary[]>([])
  const [missionId, setMissionId] = useState<number | null>(null)
  const [speedup, setSpeedup] = useState(5)
  const [battery, setBattery] = useState(100)
  const [wind, setWind] = useState(0)
  const [failure, setFailure] = useState<Failure>('none')
  const [atPercent, setAtPercent] = useState(50)
  const [autoStart, setAutoStart] = useState(true)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.missions().then((m) => {
      setMissions(m)
      setMissionId((id) => id ?? m.find((x) => x.valid)?.id ?? null)
    }).catch(() => undefined)
    api.flights().then((f) => setFlights(f.filter((x) => x.vehicle_kind === 'sim').slice(0, 8))).catch(() => undefined)
  }, [summary?.last_flight_id])

  const mission = missions.find((m) => m.id === missionId)
  const realVehicle = summary?.link !== 'disconnected' && summary?.kind !== 'sim' && summary?.kind != null
  const expected = FAILURES.find((f) => f.value === failure)!.expect

  const run = async () => {
    if (!mission) return
    setBusy(true)
    try {
      if (summary?.link === 'connected' && summary.kind === 'sim') await api.disconnect()
      const detail = await api.mission(mission.id)
      await api.connect({
        kind: 'sim',
        sim: {
          home_lat: detail.plan.home.lat,
          home_lon: detail.plan.home.lon,
          speedup,
          battery_start_pct: battery,
          wind_mps: wind,
          wind_from_deg: 270,
        },
      })
      const upload = await api.uploadMission(mission.id, 0)
      if (!upload.ok) throw new Error(`Upload incomplete: ${upload.steps.filter((s) => !s.ok).map((s) => s.message).join('; ')}`)
      await refresh()
      armScenario(failure, atPercent)
      if (autoStart) {
        const armed = await api.command('arm')
        if (!armed.accepted) throw new Error(armed.message)
        const started = await api.command('start')
        if (!started.accepted) throw new Error(started.message)
      }
      navigate('/')
    } catch (e) {
      toast('bad', (e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="scroll h-full p-5">
      <div className="mx-auto grid max-w-6xl gap-4 lg:grid-cols-[1fr_340px]">
        <div className="grid content-start gap-4">
          <header>
            <h1 className="text-xl font-semibold">Simulation</h1>
            <p className="mt-1 max-w-[70ch] text-[13.5px] text-muted">
              Rehearse a mission on a virtual drone before flying it. The simulator receives the same mission items,
              geofence and failsafe settings a real drone would, and the flight is recorded like any other.
            </p>
          </header>

          <Panel title="Rehearse a mission">
            {missions.length === 0 ? (
              <Empty title="No missions to rehearse">
                <Link to="/plan" className="text-info underline">Plan a mission</Link> first.
              </Empty>
            ) : (
              <div className="grid gap-4">
                <div className="grid gap-3 sm:grid-cols-2">
                  <SelectField
                    label="Mission"
                    value={missionId ?? 0}
                    onChange={setMissionId}
                    options={missions.map((m) => ({ value: m.id, label: `${m.name}${m.valid ? '' : ' (not valid)'}` }))}
                    hint={mission ? `${duration(mission.stats.time_s)} min, ${distance(mission.stats.distance_m)}, ${mission.stats.photos} photos planned` : undefined}
                  />
                  <SelectField
                    label="Speed"
                    value={speedup}
                    onChange={setSpeedup}
                    options={[1, 2, 5, 10, 20].map((v) => ({ value: v, label: v === 1 ? 'Real time' : `${v} times faster` }))}
                  />
                  <NumberField label="Battery at take-off" unit="%" value={battery} onChange={setBattery} min={10} max={100} />
                  <NumberField label="Wind" unit="m/s" value={wind} onChange={setWind} min={0} max={20} hint="From the west. Costs battery." />
                </div>

                <div className="rounded-lg border border-line p-3">
                  <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted">Failure to rehearse</div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <SelectField label="What goes wrong" value={failure} onChange={setFailure} options={FAILURES.map((f) => ({ value: f.value, label: f.label }))} />
                    {failure !== 'none' && (
                      <NumberField label="When the mission is" unit="% done" value={atPercent} onChange={(v) => setAtPercent(Math.max(5, Math.min(95, v)))} min={5} max={95} step={5} />
                    )}
                  </div>
                  <p className="mt-2 text-[12.5px] text-muted">Expected: {expected}</p>
                </div>

                <Toggle label="Arm and start automatically" hint="Otherwise the mission is loaded and you start it on the Fly screen" checked={autoStart} onChange={setAutoStart} />

                {realVehicle ? (
                  <p role="alert" className="rounded-md border border-warn/50 bg-warn/10 p-2.5 text-[13px]">
                    A real vehicle or software autopilot is connected. Disconnect it before starting the simulator.
                  </p>
                ) : summary?.flying ? (
                  <p role="alert" className="rounded-md border border-warn/50 bg-warn/10 p-2.5 text-[13px]">
                    The simulator is flying. Land it before starting another rehearsal.
                  </p>
                ) : null}

                <div>
                  <Button variant="primary" icon={<Play size={16} />} busy={busy} disabled={!mission?.valid || realVehicle || summary?.flying} onClick={() => void run()}>
                    Run the rehearsal
                  </Button>
                </div>
              </div>
            )}
          </Panel>

          <Panel title="Recent rehearsals">
            {flights.length === 0 ? (
              <p className="text-[13px] text-muted">No simulated flights yet.</p>
            ) : (
              <table className="w-full text-[13px]">
                <thead className="text-left text-[11px] uppercase tracking-wider text-muted">
                  <tr><th className="pb-1.5">Mission</th><th>When</th><th>Time</th><th>Photos</th><th>Result</th></tr>
                </thead>
                <tbody className="divide-y divide-line/60">
                  {flights.map((f) => (
                    <tr key={f.id}>
                      <td className="py-1.5 pr-2">{f.mission_name}</td>
                      <td className="pr-2 text-muted">{dateTime(f.started_at)}</td>
                      <td className="num pr-2">{duration(f.summary.duration_s)}</td>
                      <td className="num pr-2">{f.summary.captures ?? 0}</td>
                      <td>
                        <Badge tone={f.status === 'completed' ? 'good' : f.status === 'aborted' ? 'bad' : 'warn'}>
                          {f.status === 'aborted' ? (f.summary.failsafes?.[0] ?? 'aborted') : f.status.replace('_', ' ')}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <p className="mt-2 text-[12.5px] text-muted">
              Open <Link to="/flights" className="text-info underline">Flights</Link> to replay any of them.
            </p>
          </Panel>
        </div>

        <div className="grid content-start gap-4">
          <Panel title="Live conditions" actions={<FlaskConical size={16} className="text-muted" />}>
            <SimulatorControls />
          </Panel>
          <Panel title="Three ways to test">
            <ul className="space-y-2.5 text-[13px] leading-snug">
              <li><b>Built-in simulator.</b> Instant, repeatable, can run faster than real time. Tests the mission, the geofence, the failsafes and the record.</li>
              <li><b>Software autopilot.</b> The real ArduPilot flight code on this computer. Connect to it exactly as to a drone. Proves the mission flies on the real firmware.</li>
              <li><b>Real drone.</b> The same mission, uploaded the same way. Only the connection changes.</li>
            </ul>
          </Panel>
        </div>
      </div>
    </div>
  )
}
