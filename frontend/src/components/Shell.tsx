import {
  BatteryFull,
  BatteryLow,
  BatteryMedium,
  BatteryWarning,
  Boxes,
  ClipboardList,
  FlaskConical,
  Map as MapIcon,
  Moon,
  Navigation,
  Plug,
  Satellite,
  Settings as SettingsIcon,
  Sprout,
  Sun,
  TriangleAlert,
} from 'lucide-react'
import { type ReactNode, useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'

import type { LinkStatus, VehicleState } from '../lib/api'
import { fixed } from '../lib/format'
import { useVehicle } from '../lib/store'
import { ConnectDialog } from './ConnectDialog'
import { Badge, Toasts } from './ui'

const NAV = [
  { to: '/', label: 'Fly', icon: Navigation, end: true },
  { to: '/plan', label: 'Plan', icon: MapIcon },
  { to: '/orchards', label: 'Orchards', icon: Sprout },
  { to: '/flights', label: 'Flights', icon: ClipboardList },
  { to: '/simulation', label: 'Simulate', icon: FlaskConical },
  { to: '/models', label: 'Models', icon: Boxes },
  { to: '/settings', label: 'Settings', icon: SettingsIcon },
]

const LINK_TONE: Record<LinkStatus, 'good' | 'warn' | 'bad' | 'muted'> = {
  connected: 'good',
  connecting: 'warn',
  lost: 'bad',
  disconnected: 'muted',
}

const LINK_TEXT: Record<LinkStatus, string> = {
  connected: 'Connected',
  connecting: 'Connecting',
  lost: 'Link lost',
  disconnected: 'Not connected',
}

function BatteryGlyph({ pct }: { pct: number | null }) {
  if (pct === null) return <BatteryWarning size={16} />
  if (pct > 60) return <BatteryFull size={16} />
  if (pct > 30) return <BatteryMedium size={16} />
  return <BatteryLow size={16} />
}

function Readout({ label, children, tone }: { label: string; children: ReactNode; tone?: 'warn' | 'bad' }) {
  return (
    <div className="hidden flex-col leading-none md:flex">
      <span className="text-[9.5px] font-medium uppercase tracking-wider text-muted">{label}</span>
      <span
        className={`num mt-1 text-[15px] font-semibold ${
          tone === 'bad' ? 'text-danger' : tone === 'warn' ? 'text-warn' : ''
        }`}
      >
        {children}
      </span>
    </div>
  )
}

function VehicleReadouts({ s, warnPct, critPct }: { s: VehicleState; warnPct: number; critPct: number }) {
  const battTone = s.battery_pct === null ? undefined : s.battery_pct <= critPct ? 'bad' : s.battery_pct <= warnPct ? 'warn' : undefined
  const gpsBad = s.gps_fix === 'none' || s.gps_fix === '2d'
  return (
    <>
      <Badge tone={s.armed ? 'warn' : 'muted'}>{s.armed ? 'Armed' : 'Disarmed'}</Badge>
      <Badge tone={s.mode === 'rtl' || s.mode === 'land' ? 'warn' : 'info'}>{s.mode_raw || s.mode}</Badge>
      <Readout label="Height">{fixed(s.alt_rel_m)} m</Readout>
      <Readout label="Speed">{fixed(s.groundspeed_mps)} m/s</Readout>
      <Readout label="GPS" tone={gpsBad ? 'bad' : undefined}>
        <span className="inline-flex items-center gap-1">
          <Satellite size={14} />
          {gpsBad ? 'No fix' : `${s.satellites}`}
        </span>
      </Readout>
      <Readout label="Battery" tone={battTone}>
        <span className="inline-flex items-center gap-1">
          <BatteryGlyph pct={s.battery_pct} />
          {s.battery_pct === null ? '—' : `${Math.round(s.battery_pct)}%`}
        </span>
      </Readout>
    </>
  )
}

function useTheme(): ['dark' | 'light', () => void] {
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    try {
      return localStorage.getItem('ov-theme') === 'light' ? 'light' : 'dark'
    } catch {
      return 'dark'
    }
  })
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try {
      localStorage.setItem('ov-theme', theme)
    } catch {
      /* private browsing: the choice just does not persist */
    }
  }, [theme])
  return [theme, () => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))]
}

export function Shell({ children }: { children: ReactNode }) {
  const summary = useVehicle((s) => s.summary)
  const state = useVehicle((s) => s.state)
  const channel = useVehicle((s) => s.channel)
  const [connectOpen, setConnectOpen] = useState(false)
  const [theme, toggleTheme] = useTheme()

  const link: LinkStatus = summary?.link ?? 'disconnected'
  const safety = summary?.mission?.safety

  return (
    <div className="grid h-full grid-cols-[76px_1fr] grid-rows-[56px_1fr]">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-surface focus:p-2">
        Skip to content
      </a>

      <header className="col-span-2 flex items-center gap-4 border-b border-line bg-surface px-3">
        <div className="flex w-[64px] items-center justify-center" aria-label="OrchardVision">
          <svg width="30" height="30" viewBox="0 0 32 32" aria-hidden="true">
            <rect width="32" height="32" rx="7" fill="var(--brand)" />
            <rect x="14.5" y="14" width="3" height="13" fill="var(--on-brand)" />
            <circle cx="16" cy="12" r="7" fill="var(--on-brand)" />
            <ellipse cx="16" cy="19" rx="2.2" ry="3.2" fill="#e8b93c" />
          </svg>
        </div>

        <button
          type="button"
          onClick={() => setConnectOpen(true)}
          className={`flex min-h-10 items-center gap-2 rounded-md border px-3 text-left transition
            hover:bg-surface-2 ${link === 'lost' ? 'alarm border-danger' : 'border-line'}`}
        >
          {link === 'lost' ? <TriangleAlert size={18} className="text-danger" /> : <Plug size={18} className="text-muted" />}
          <span className="leading-tight">
            <span className="block text-[13px] font-semibold">
              {LINK_TEXT[link]}
              {summary?.kind === 'sim' && link === 'connected' && ' · simulation'}
            </span>
            <span className="block max-w-56 truncate text-[11px] text-muted">
              {link === 'disconnected' ? 'Select to connect a vehicle' : summary?.description}
            </span>
          </span>
          <Badge tone={LINK_TONE[link]} className="ml-1">
            {link === 'connected' ? 'Live' : link === 'lost' ? 'Lost' : link === 'connecting' ? '…' : 'Off'}
          </Badge>
        </button>

        {state && link !== 'disconnected' && (
          <div className="flex items-center gap-4">
            <VehicleReadouts s={state} warnPct={safety?.battery_warn_pct ?? 30} critPct={safety?.battery_crit_pct ?? 20} />
          </div>
        )}

        <div className="ml-auto flex items-center gap-3">
          {summary?.flying && (
            <span className="flex items-center gap-1.5 text-[12px] font-semibold text-danger">
              <span className="size-2.5 animate-pulse rounded-full bg-danger" />
              {summary.recording ? 'RECORDING' : 'NOT RECORDED'}
            </span>
          )}
          {channel !== 'open' && <Badge tone="bad">Backend offline</Badge>}
          <button
            type="button"
            onClick={toggleTheme}
            aria-label={theme === 'dark' ? 'Switch to the light theme' : 'Switch to the dark theme'}
            title={theme === 'dark' ? 'Light theme (for sunlight)' : 'Dark theme'}
            className="grid size-10 place-items-center rounded-md hover:bg-surface-3"
          >
            {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
          </button>
        </div>
      </header>

      <nav aria-label="Sections" className="flex flex-col gap-1 border-r border-line bg-surface p-1.5">
        {NAV.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            end={n.end}
            className={({ isActive }) =>
              `flex min-h-14 flex-col items-center justify-center gap-1 rounded-md text-[11px]
               font-medium transition ${
                 isActive ? 'bg-brand/15 text-brand' : 'text-muted hover:bg-surface-2 hover:text-ink'
               }`
            }
          >
            <n.icon size={20} />
            {n.label}
          </NavLink>
        ))}
      </nav>

      <main id="main" className="min-h-0 min-w-0">
        {children}
      </main>

      {connectOpen && <ConnectDialog onClose={() => setConnectOpen(false)} />}
      <Toasts />
    </div>
  )
}
