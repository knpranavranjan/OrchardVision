/** The pieces of the Fly screen: instruments, checklist, command bar, manual control, log. */
import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  ChevronsDown,
  ChevronsUp,
  CircleStop,
  Home,
  Pause,
  Play,
  PlaneLanding,
  PlaneTakeoff,
  Power,
  RotateCcw,
  RotateCw,
} from 'lucide-react'
import { type ReactNode, useEffect, useMemo, useRef, useState } from 'react'

import { api, type Preflight, type VehicleEvent } from '../lib/api'
import { clock, distance, fixed } from '../lib/format'
import { useVehicle } from '../lib/store'
import { Badge, Button, CheckRow, HoldButton, NumberField, Stat } from './ui'

// ---------------------------------------------------------------------- instruments

/** Artificial horizon with a heading tape. */
export function AttitudeIndicator({ roll, pitch, heading }: { roll: number; pitch: number; heading: number }) {
  const pxPerDeg = 2.2
  const shift = Math.max(-40, Math.min(40, pitch)) * pxPerDeg
  const ticks = [-20, -10, 10, 20]
  return (
    <svg viewBox="-60 -60 120 136" className="w-full" role="img" aria-label={`Roll ${roll.toFixed(0)} degrees, pitch ${pitch.toFixed(0)} degrees, heading ${heading.toFixed(0)} degrees`}>
      <defs>
        <clipPath id="ai-clip">
          <circle r="54" />
        </clipPath>
      </defs>
      <g clipPath="url(#ai-clip)">
        <g transform={`rotate(${-roll}) translate(0 ${shift})`}>
          <rect x="-150" y="-300" width="300" height="300" fill="#2f7fc1" />
          <rect x="-150" y="0" width="300" height="300" fill="#7a5a34" />
          <line x1="-150" x2="150" y1="0" y2="0" stroke="#fff" strokeWidth="1.2" />
          {ticks.map((t) => (
            <g key={t}>
              <line x1="-14" x2="14" y1={-t * pxPerDeg} y2={-t * pxPerDeg} stroke="#fff" strokeWidth="0.9" />
              <text x="18" y={-t * pxPerDeg + 2.5} fontSize="7" fill="#fff" fontFamily="Fira Code, monospace">
                {Math.abs(t)}
              </text>
            </g>
          ))}
        </g>
      </g>
      <circle r="54" fill="none" stroke="var(--line)" strokeWidth="2" />
      {/* fixed aircraft symbol */}
      <path d="M-34,0 H-12 L-6,6 M34,0 H12 L6,6" fill="none" stroke="#ffd84a" strokeWidth="3" strokeLinecap="round" />
      <circle r="2.2" fill="#ffd84a" />
      {/* roll pointer */}
      <path d="M0,-54 L-4,-46 L4,-46 Z" fill="#fff" transform={`rotate(${-roll})`} />
      <path d="M0,-56 L-3.5,-61 L3.5,-61 Z" fill="#ffd84a" />
      {/* heading */}
      <rect x="-22" y="60" width="44" height="15" rx="3" fill="var(--surface-3)" stroke="var(--line)" />
      <text x="0" y="71" textAnchor="middle" fontSize="10" fontWeight="600" fill="var(--ink)" fontFamily="Fira Code, monospace">
        {String(Math.round(heading) % 360).padStart(3, '0')}°
      </text>
    </svg>
  )
}

export function Instruments() {
  const s = useVehicle((st) => st.state)
  const summary = useVehicle((st) => st.summary)
  if (!s) return null
  const safety = summary?.mission?.safety
  const battTone =
    s.battery_pct === null
      ? undefined
      : s.battery_pct <= (safety?.battery_crit_pct ?? 20)
        ? 'bad'
        : s.battery_pct <= (safety?.battery_warn_pct ?? 30)
          ? 'warn'
          : undefined
  const home =
    s.home_lat !== null && s.home_lon !== null
      ? Math.hypot((s.lat - s.home_lat) * 111_320, (s.lon - s.home_lon) * 111_320 * Math.cos((s.lat * Math.PI) / 180))
      : null
  return (
    <div className="w-60 rounded-lg border border-line bg-overlay p-3 shadow-xl backdrop-blur">
      <div className="mx-auto w-36">
        <AttitudeIndicator roll={s.roll_deg} pitch={s.pitch_deg} heading={s.heading_deg} />
      </div>
      <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-2.5">
        <Stat label="Height" value={fixed(s.alt_rel_m)} unit="m" />
        <Stat label="Ground speed" value={fixed(s.groundspeed_mps)} unit="m/s" />
        <Stat label="Climb" value={fixed(s.vel_up_mps)} unit="m/s" />
        <Stat label="From home" value={home === null ? '—' : distance(home)} />
        <Stat label="Battery" value={s.battery_pct === null ? '—' : Math.round(s.battery_pct)} unit="%" tone={battTone} />
        <Stat label="Voltage" value={fixed(s.battery_v)} unit="V" />
        <Stat
          label="GPS"
          value={s.gps_fix === 'none' ? 'No fix' : s.gps_fix.replace('_', ' ').toUpperCase()}
          tone={s.gps_fix === 'none' || s.gps_fix === '2d' ? 'bad' : undefined}
        />
        <Stat label="Satellites" value={s.satellites} />
      </div>
    </div>
  )
}

/** Mission progress strip shown while a mission is on the vehicle. */
export function MissionProgress() {
  const s = useVehicle((st) => st.state)
  const mission = useVehicle((st) => st.summary?.mission)
  if (!s || !mission) return null
  const count = mission.item_count
  const seq = s.mode === 'auto' && s.mission_seq !== null ? s.mission_seq : null
  const pct = seq === null ? 0 : Math.round(((seq + 1) / count) * 100)
  return (
    <div className="rounded-lg border border-line bg-overlay px-3 py-2 shadow-xl backdrop-blur">
      <div className="flex items-center justify-between gap-3 text-[12.5px]">
        <span className="truncate font-semibold">
          {mission.name}
          {mission.segments > 1 && ` · flight ${mission.segment + 1} of ${mission.segments}`}
        </span>
        <span className="num text-muted">
          {seq === null ? 'not started' : `item ${seq + 1} / ${count}`}
          {s.wp_dist_m !== null && ` · ${distance(s.wp_dist_m)} to next`}
        </span>
      </div>
      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-3" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <div className="h-full bg-brand transition-[width] duration-300" style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-1 flex justify-between text-[11.5px] text-muted">
        <span>
          {mission.verified ? 'Uploaded and verified' : 'Upload not verified'} · revision {mission.revision}
        </span>
        <span className="num">{s.captures} photos</span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------- pre-flight

export function PreflightPanel() {
  const pre = useVehicle((s) => s.preflight)
  const refresh = useVehicle((s) => s.refreshPreflight)
  const link = useVehicle((s) => s.summary?.link)

  const missionKey = useVehicle((s) => `${s.summary?.mission?.mission_id}/${s.summary?.mission?.verified}`)

  // Refresh on a timer, and at once when the link or the mission changes.
  useEffect(() => {
    void refresh()
    const timer = setInterval(() => void refresh(), 1500)
    return () => clearInterval(timer)
  }, [refresh, link, missionKey])

  const groups = useMemo(() => {
    const out = new Map<string, Preflight['checks']>()
    for (const c of pre?.checks ?? []) out.set(c.group, [...(out.get(c.group) ?? []), c])
    return [...out.entries()]
  }, [pre])

  if (!pre) return <p className="text-[13px] text-muted">Loading the checklist…</p>

  const confirm = async (id: string, value: boolean) => {
    useVehicle.setState({ preflight: await api.confirmCheck(id, value) })
  }

  return (
    <div>
      <div
        className={`mb-3 rounded-lg border p-3 text-center ${
          pre.ready ? 'border-brand/60 bg-brand/10' : 'border-line bg-surface-2'
        }`}
        role="status"
      >
        <div className={`text-base font-semibold ${pre.ready ? 'text-brand' : ''}`}>
          {pre.ready ? 'READY TO FLY' : link === 'connected' ? 'NOT READY' : 'NO VEHICLE'}
        </div>
        {!pre.ready && (
          <div className="mt-0.5 text-[12px] text-muted">
            {pre.blocking.length} item{pre.blocking.length === 1 ? '' : 's'} to resolve
          </div>
        )}
      </div>
      {groups.map(([group, checks]) => (
        <div key={group} className="mb-2">
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted">{group}</h3>
          <ul className="divide-y divide-line/60">
            {checks.map((c) => (
              <CheckRow
                key={c.id}
                status={c.status}
                label={c.label}
                detail={c.detail}
                action={
                  c.manual ? (
                    <Button small variant={c.status === 'pass' ? 'ghost' : 'secondary'} onClick={() => confirm(c.id, c.status !== 'pass')}>
                      {c.status === 'pass' ? 'Undo' : 'Confirm'}
                    </Button>
                  ) : undefined
                }
              />
            ))}
          </ul>
        </div>
      ))}
      <p className="text-[11.5px] leading-snug text-muted">
        Arming is refused until every item passes. Operator items clear again after each flight.
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------- commands

export function CommandBar({ onFlyTo, flyToActive }: { onFlyTo: () => void; flyToActive: boolean }) {
  const s = useVehicle((st) => st.state)
  const summary = useVehicle((st) => st.summary)
  const toast = useVehicle((st) => st.toast)
  const [busy, setBusy] = useState<string | null>(null)
  const [alt, setAlt] = useState(15)
  const [override, setOverride] = useState(false)

  const connected = summary?.link === 'connected' && s !== null
  const send = async (command: string, args: Record<string, unknown> = {}) => {
    setBusy(command)
    try {
      const result = await api.command(command, args)
      if (!result.accepted) toast('bad', result.message || `${command} was refused`)
    } catch (e) {
      toast('bad', (e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  if (!connected) {
    return (
      <div className="rounded-lg border border-line bg-overlay px-4 py-3 text-[13px] text-muted shadow-xl backdrop-blur">
        Connect a vehicle to see the flight controls. Use the button at the top left.
      </div>
    )
  }

  const mission = summary.mission
  const ready = summary.preflight.ready
  const inAir = s.in_air
  const paused = s.mode === 'hold' && s.mission_seq !== null && mission !== null
  const landing = s.mode === 'land' || s.mode === 'rtl'

  let controls: ReactNode
  if (!s.armed) {
    controls = (
      <>
        <HoldButton
          variant="primary"
          icon={<Power size={18} />}
          disabled={(!ready && !override) || busy !== null}
          onConfirm={() => send('arm', { override: !ready && override })}
          title={ready ? 'Hold to arm the motors' : 'Pre-flight checks are not passed'}
        >
          Arm
        </HoldButton>
        {!ready && (
          <label className="flex min-h-11 cursor-pointer items-center gap-2 rounded-md border border-warn/50 px-3 text-[12.5px] text-warn">
            <input type="checkbox" checked={override} onChange={(e) => setOverride(e.target.checked)} className="size-4 accent-[var(--warn)]" />
            Override checklist
          </label>
        )}
        <span className="text-[12.5px] text-muted">
          {ready ? 'Checklist passed. Hold Arm to start the motors.' : `Not ready: ${summary.preflight.blocking.slice(0, 2).join(', ')}${summary.preflight.blocking.length > 2 ? '…' : ''}`}
        </span>
      </>
    )
  } else if (!inAir) {
    controls = (
      <>
        {mission?.verified && (
          <HoldButton variant="primary" icon={<Play size={18} />} disabled={busy !== null} onConfirm={() => send('start')}>
            Start mission
          </HoldButton>
        )}
        <div className="w-24">
          <NumberField label="Take-off height" unit="m" value={alt} onChange={setAlt} min={2} max={120} />
        </div>
        <HoldButton variant="secondary" icon={<PlaneTakeoff size={18} />} disabled={busy !== null} onConfirm={() => send('takeoff', { alt_m: alt })} className="self-end">
          Take off
        </HoldButton>
        <Button variant="secondary" icon={<Power size={18} />} onClick={() => send('disarm')} busy={busy === 'disarm'} className="self-end">
          Disarm
        </Button>
      </>
    )
  } else {
    controls = (
      <>
        {s.mode === 'auto' && (
          <Button variant="secondary" icon={<Pause size={18} />} onClick={() => send('pause')} busy={busy === 'pause'}>
            Pause
          </Button>
        )}
        {paused && (
          <Button variant="primary" icon={<Play size={18} />} onClick={() => send('resume')} busy={busy === 'resume'}>
            Resume mission
          </Button>
        )}
        {mission?.verified && s.mode !== 'auto' && !paused && !landing && (
          <HoldButton variant="primary" icon={<Play size={18} />} disabled={busy !== null} onConfirm={() => send('start')}>
            Start mission
          </HoldButton>
        )}
        {s.mode !== 'auto' && s.mode !== 'hold' && !landing && (
          <Button variant="secondary" icon={<CircleStop size={18} />} onClick={() => send('pause')} busy={busy === 'pause'}>
            Hold
          </Button>
        )}
        {!landing && (
          <Button variant={flyToActive ? 'primary' : 'secondary'} onClick={onFlyTo} aria-pressed={flyToActive}>
            {flyToActive ? 'Click the map…' : 'Fly to point'}
          </Button>
        )}
        <span className="mx-1 hidden h-8 w-px bg-line sm:block" />
        <Button variant="danger" icon={<Home size={18} />} onClick={() => send('rtl')} busy={busy === 'rtl'} disabled={s.mode === 'rtl'}>
          Return home
        </Button>
        <Button variant="danger" icon={<PlaneLanding size={18} />} onClick={() => send('land')} busy={busy === 'land'} disabled={s.mode === 'land'}>
          Land now
        </Button>
      </>
    )
  }

  return (
    <div className="flex flex-wrap items-center gap-2.5 rounded-lg border border-line bg-overlay px-3 py-2.5 shadow-xl backdrop-blur">
      {controls}
    </div>
  )
}

// ---------------------------------------------------------------------- manual control

const KEYS: Record<string, [number, number, number, number]> = {
  w: [1, 0, 0, 0],
  s: [-1, 0, 0, 0],
  a: [0, -1, 0, 0],
  d: [0, 1, 0, 0],
  r: [0, 0, 1, 0],
  f: [0, 0, -1, 0],
  q: [0, 0, 0, -1],
  e: [0, 0, 0, 1],
}

function Pad({
  k,
  label,
  icon,
  press,
  release,
  usable,
}: {
  k: string
  label: string
  icon: ReactNode
  press: (k: string) => void
  release: (k: string) => void
  usable: boolean
}) {
  return (
    <button
      type="button"
      disabled={!usable}
      aria-label={label}
      title={`${label} (${k.toUpperCase()})`}
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture(e.pointerId)
        press(k)
      }}
      onPointerUp={() => release(k)}
      onPointerCancel={() => release(k)}
      onLostPointerCapture={() => release(k)}
      className="flex size-14 touch-none select-none flex-col items-center justify-center gap-0.5
        rounded-lg border border-line bg-surface-2 transition active:scale-95 active:bg-brand
        active:text-on-brand disabled:opacity-40"
    >
      {icon}
      <span className="num text-[9px] opacity-70">{k.toUpperCase()}</span>
    </button>
  )
}

/**
 * Hand flying from the ground station. While a button or key is held, stick
 * input is sent five times a second; when it is released the vehicle stops and
 * holds. The backend also stops it if the input stream stops for any reason.
 */
export function ManualControl() {
  const s = useVehicle((st) => st.state)
  const sendManual = useVehicle((st) => st.sendManual)
  const [speed, setSpeed] = useState(2)
  const [keyboard, setKeyboard] = useState(false)
  const held = useRef(new Set<string>())
  const speedRef = useRef(speed)
  useEffect(() => {
    speedRef.current = speed
  }, [speed])

  useEffect(() => {
    const timer = setInterval(() => {
      if (held.current.size === 0) return
      let [f, r, u, y] = [0, 0, 0, 0]
      for (const k of held.current) {
        const v = KEYS[k]
        if (v) [f, r, u, y] = [f + v[0], r + v[1], u + v[2], y + v[3]]
      }
      const v = speedRef.current
      sendManual(f * v, r * v, u * Math.min(v, 2), y * 30)
    }, 200)
    return () => clearInterval(timer)
  }, [sendManual])

  const press = (k: string) => held.current.add(k)
  const release = (k: string) => {
    if (held.current.delete(k) && held.current.size === 0) sendManual(0, 0, 0, 0)
  }

  useEffect(() => {
    if (!keyboard) return
    const down = (e: KeyboardEvent) => {
      const k = e.key.toLowerCase()
      if (k in KEYS && !(e.target instanceof HTMLInputElement) && !(e.target instanceof HTMLSelectElement)) {
        e.preventDefault()
        press(k)
      }
    }
    const up = (e: KeyboardEvent) => release(e.key.toLowerCase())
    const blur = () => {
      held.current.clear()
      sendManual(0, 0, 0, 0)
    }
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', up)
    window.addEventListener('blur', blur)
    return () => {
      window.removeEventListener('keydown', down)
      window.removeEventListener('keyup', up)
      window.removeEventListener('blur', blur)
      blur()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [keyboard])

  const usable = s !== null && s.in_air && s.mode !== 'auto' && s.mode !== 'rtl' && s.mode !== 'land'
  const pad = { press, release, usable }

  return (
    <div>
      <p className="mb-3 text-[12.5px] leading-snug text-muted">
        {usable
          ? 'Hold a button to move. Release it and the vehicle stops and holds position.'
          : s?.mode === 'auto'
            ? 'A mission is being flown. Pause it to take manual control.'
            : 'Take off first. Manual control works while the vehicle is holding or in guided flight.'}
      </p>
      <div className="flex items-start justify-center gap-6">
        <div className="grid grid-cols-3 gap-1.5">
          <Pad {...pad} k="q" label="Turn left" icon={<RotateCcw size={18} />} />
          <Pad {...pad} k="w" label="Forward" icon={<ArrowUp size={18} />} />
          <Pad {...pad} k="e" label="Turn right" icon={<RotateCw size={18} />} />
          <Pad {...pad} k="a" label="Left" icon={<ArrowLeft size={18} />} />
          <Pad {...pad} k="s" label="Back" icon={<ArrowDown size={18} />} />
          <Pad {...pad} k="d" label="Right" icon={<ArrowRight size={18} />} />
        </div>
        <div className="grid gap-1.5">
          <Pad {...pad} k="r" label="Up" icon={<ChevronsUp size={18} />} />
          <Pad {...pad} k="f" label="Down" icon={<ChevronsDown size={18} />} />
        </div>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3">
        <NumberField label="Speed" unit="m/s" value={speed} onChange={(v) => setSpeed(Math.max(0.5, Math.min(5, v)))} min={0.5} max={5} step={0.5} />
        <label className="flex cursor-pointer items-end gap-2 pb-2 text-[13px]">
          <input type="checkbox" checked={keyboard} onChange={(e) => setKeyboard(e.target.checked)} className="size-4 accent-[var(--brand)]" />
          Keyboard control
        </label>
      </div>
      <p className="mt-3 text-[11.5px] leading-snug text-muted">
        This is assisted flying: the autopilot keeps the vehicle level and inside the height limits and the geofence.
        A pilot with the remote control can always take over.
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------- log

const SEVERITY_TONE = { info: 'muted', warning: 'warn', critical: 'bad' } as const

export function EventLog({ events }: { events: VehicleEvent[] }) {
  const shown = useMemo(() => events.filter((e) => e.kind !== 'capture' && e.kind !== 'item_reached').slice(-80).reverse(), [events])
  if (shown.length === 0) return <p className="text-[13px] text-muted">Nothing has happened yet.</p>
  return (
    <ol className="space-y-1.5">
      {shown.map((e, i) => (
        <li key={`${e.time}-${i}`} className="flex gap-2 text-[12.5px] leading-snug">
          <span className="num shrink-0 text-muted">{clock(e.time)}</span>
          <span className="min-w-0 flex-1">
            {e.severity !== 'info' && (
              <Badge tone={SEVERITY_TONE[e.severity]} className="mr-1.5">
                {e.severity}
              </Badge>
            )}
            {e.message}
          </span>
        </li>
      ))}
    </ol>
  )
}
