import { Cable, Cpu, MonitorPlay, Radio, RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'

import { api, type AppSettings, type LatLon, type MissionSummary, type Orchard } from '../lib/api'
import { useVehicle } from '../lib/store'
import { Button, Dialog, SelectField, TextField } from './ui'

type Tab = 'sim' | 'sitl' | 'serial' | 'udp'

const TABS: { id: Tab; label: string; icon: typeof Cpu; blurb: string }[] = [
  {
    id: 'sim',
    label: 'Simulator',
    icon: MonitorPlay,
    blurb: 'A virtual drone built into OrchardVision. Nothing to install. Use it to rehearse a mission.',
  },
  {
    id: 'sitl',
    label: 'Software autopilot',
    icon: Cpu,
    blurb:
      'The real ArduPilot flight code running on this computer. Start it with: docker compose --profile sitl up -d sitl',
  },
  {
    id: 'serial',
    label: 'Drone by USB or radio',
    icon: Cable,
    blurb: 'A Pixhawk on a USB cable (115200) or a SiK telemetry radio (57600).',
  },
  {
    id: 'udp',
    label: 'Drone by network',
    icon: Radio,
    blurb: 'A companion computer or telemetry bridge sending MAVLink to this computer over Wi-Fi.',
  },
]

export function ConnectDialog({ onClose }: { onClose: () => void }) {
  const summary = useVehicle((s) => s.summary)
  const refresh = useVehicle((s) => s.refresh)
  const toast = useVehicle((s) => s.toast)
  const [tab, setTab] = useState<Tab>('sim')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [settings, setSettings] = useState<AppSettings | null>(null)
  const [places, setPlaces] = useState<{ label: string; at: LatLon }[]>([])
  const [place, setPlace] = useState(0)
  const [speedup, setSpeedup] = useState(1)
  const [sitlUrl, setSitlUrl] = useState('tcp:127.0.0.1:5760')
  const [udpUrl, setUdpUrl] = useState('udpin:0.0.0.0:14550')
  const [ports, setPorts] = useState<{ device: string; description: string }[]>([])
  const [port, setPort] = useState('')
  const [baud, setBaud] = useState(57600)

  const loadPorts = () =>
    api
      .ports()
      .then((p) => {
        setPorts(p)
        setPort((current) => current || p[0]?.device || '')
      })
      .catch(() => setPorts([]))

  useEffect(() => {
    void loadPorts()
    const fallback: LatLon = { lat: 12.9716, lon: 77.5946 }
    Promise.all([
      api.settings().catch(() => null),
      api.orchards().catch(() => [] as Orchard[]),
      api.missions().catch(() => [] as MissionSummary[]),
    ]).then(async ([s, orchards, missions]) => {
      if (s) {
        setSettings(s)
        setSitlUrl(s.sitl_url)
        setUdpUrl(s.udp_url)
        setBaud(s.serial_baud)
      }
      const list = [{ label: 'Default map position', at: s?.map_center ?? fallback }]
      for (const m of missions.slice(0, 8)) {
        try {
          const detail = await api.mission(m.id)
          list.push({ label: `Mission: ${m.name} (its home point)`, at: detail.plan.home })
        } catch {
          /* skip a mission that cannot be read */
        }
      }
      for (const o of orchards) {
        if (o.boundary.length) list.push({ label: `Orchard: ${o.name}`, at: o.boundary[0] })
      }
      setPlaces(list)
    })
  }, [])

  const connected = summary && summary.link !== 'disconnected'

  const run = async (action: () => Promise<unknown>, done: string) => {
    setBusy(true)
    setError(null)
    try {
      await action()
      await refresh()
      toast('good', done)
      onClose()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const connect = () => {
    if (tab === 'sim') {
      const at = places[place]?.at ?? settings?.map_center ?? { lat: 12.9716, lon: 77.5946 }
      return run(
        () => api.connect({ kind: 'sim', sim: { home_lat: at.lat, home_lon: at.lon, speedup } }),
        'Simulator connected',
      )
    }
    if (tab === 'sitl') return run(() => api.connect({ kind: 'sitl', url: sitlUrl }), 'Software autopilot connected')
    if (tab === 'serial') return run(() => api.connect({ kind: 'pixhawk', url: port, baud }), 'Drone connected')
    return run(() => api.connect({ kind: 'pixhawk', url: udpUrl }), 'Drone connected')
  }

  if (connected) {
    return (
      <Dialog
        title="Vehicle link"
        onClose={onClose}
        footer={
          <>
            <Button onClick={onClose}>Close</Button>
            <Button variant="danger" busy={busy} onClick={() => run(() => api.disconnect(), 'Disconnected')}>
              Disconnect
            </Button>
          </>
        }
      >
        <p>
          Connected to <b>{summary.description}</b>.
        </p>
        <p className="mt-2 text-[13px] text-muted">
          Disconnecting is refused while the vehicle is in the air. Land it first.
        </p>
        {error && <p role="alert" className="mt-3 rounded-md border border-danger/50 bg-danger/10 p-2.5 text-[13px]">{error}</p>}
      </Dialog>
    )
  }

  const current = TABS.find((t) => t.id === tab)!
  return (
    <Dialog
      title="Connect a vehicle"
      wide
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" busy={busy} disabled={tab === 'serial' && !port} onClick={connect}>
            Connect
          </Button>
        </>
      }
    >
      <div role="tablist" className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => {
              setTab(t.id)
              setError(null)
            }}
            className={`flex min-h-20 flex-col items-center justify-center gap-1.5 rounded-lg border p-2
              text-center text-[12.5px] leading-tight transition ${
                tab === t.id ? 'border-brand bg-brand/10 text-ink' : 'border-line text-muted hover:bg-surface-2'
              }`}
          >
            <t.icon size={22} />
            {t.label}
          </button>
        ))}
      </div>
      <p className="mt-3 text-[13px] text-muted">{current.blurb}</p>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {tab === 'sim' && (
          <>
            <SelectField
              label="Start position"
              value={place}
              onChange={setPlace}
              options={places.map((p, i) => ({ value: i, label: p.label }))}
              hint="The virtual drone sits on the ground here."
            />
            <SelectField
              label="Speed"
              value={speedup}
              onChange={setSpeedup}
              options={[1, 2, 5, 10].map((v) => ({ value: v, label: v === 1 ? 'Real time' : `${v} times faster` }))}
              hint="Can be changed during the flight."
            />
          </>
        )}
        {tab === 'sitl' && (
          <TextField label="Address" value={sitlUrl} onChange={setSitlUrl} hint="TCP address of the software autopilot." />
        )}
        {tab === 'serial' && (
          <>
            <div>
              <SelectField
                label="Port"
                value={port}
                onChange={setPort}
                options={
                  ports.length
                    ? ports.map((p) => ({ value: p.device, label: `${p.device} — ${p.description}` }))
                    : [{ value: '', label: 'No serial ports found' }]
                }
              />
              <Button small variant="ghost" className="mt-1" icon={<RefreshCw size={14} />} onClick={loadPorts}>
                Rescan ports
              </Button>
            </div>
            <SelectField
              label="Baud rate"
              value={baud}
              onChange={setBaud}
              options={[
                { value: 57600, label: '57600 (telemetry radio)' },
                { value: 115200, label: '115200 (USB)' },
                { value: 921600, label: '921600 (companion computer)' },
              ]}
            />
          </>
        )}
        {tab === 'udp' && (
          <TextField
            label="Address"
            value={udpUrl}
            onChange={setUdpUrl}
            hint="udpin:0.0.0.0:14550 listens for a drone sending to this computer."
          />
        )}
      </div>
      {tab !== 'sim' && (
        <p className="mt-3 rounded-md border border-warn/40 bg-warn/10 p-2.5 text-[12.5px]">
          This link is built for ArduPilot Copter. The first time you connect a real drone, do it
          with the propellers removed.
        </p>
      )}
      {error && (
        <p role="alert" className="mt-3 rounded-md border border-danger/50 bg-danger/10 p-2.5 text-[13px]">
          {error}
        </p>
      )}
    </Dialog>
  )
}
