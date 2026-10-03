/**
 * Live vehicle state for the whole application.
 *
 * One reconnecting WebSocket feeds this store. Components subscribe to the slices
 * they draw, so a telemetry update re-renders the HUD and the map marker, not the page.
 */
import { create } from 'zustand'

import type {
  MissionGeometry,
  Preflight,
  VehicleEvent,
  VehicleSnapshot,
  VehicleState,
  VehicleSummary,
} from './api'
import { api } from './api'

export type ChannelStatus = 'connecting' | 'open' | 'closed'

const TRACK_LIMIT = 6000
const EVENT_LIMIT = 200
const RETRY_MS = 1500

export interface Toast {
  id: number
  tone: 'info' | 'good' | 'warn' | 'bad'
  text: string
}

interface Store {
  channel: ChannelStatus
  summary: VehicleSummary | null
  state: VehicleState | null
  geometry: MissionGeometry | null
  events: VehicleEvent[]
  track: [number, number][] // lon, lat of the current flight
  captures: [number, number][]
  preflight: Preflight | null
  toasts: Toast[]
  refresh: () => Promise<void>
  refreshPreflight: () => Promise<void>
  toast: (tone: Toast['tone'], text: string) => void
  dismiss: (id: number) => void
  sendManual: (forward: number, right: number, up: number, yaw_rate: number) => void
}

let socket: WebSocket | null = null
let toastId = 0

export const useVehicle = create<Store>((set, get) => ({
  channel: 'connecting',
  summary: null,
  state: null,
  geometry: null,
  events: [],
  track: [],
  captures: [],
  preflight: null,
  toasts: [],

  refresh: async () => {
    applySnapshot(await api.vehicleStatus())
  },
  refreshPreflight: async () => {
    try {
      set({ preflight: await api.preflight() })
    } catch {
      /* the status bar already shows the backend is unreachable */
    }
  },
  toast: (tone, text) => {
    const id = ++toastId
    set((s) => ({ toasts: [...s.toasts.slice(-3), { id, tone, text }] }))
    setTimeout(() => get().dismiss(id), tone === 'bad' ? 8000 : 4500)
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
  sendManual: (forward, right, up, yaw_rate) => {
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'manual', data: { forward, right, up, yaw_rate } }))
    }
  },
}))

function applySnapshot(snap: VehicleSnapshot) {
  const { mission_geometry, state, events, ...summary } = snap
  useVehicle.setState({ summary, state, geometry: mission_geometry, events })
}

function onMessage(raw: string) {
  const message = JSON.parse(raw) as { type: string; data: unknown }
  const store = useVehicle.getState()
  switch (message.type) {
    case 'snapshot':
      applySnapshot(message.data as VehicleSnapshot)
      break
    case 'telemetry': {
      const state = message.data as VehicleState
      const next: Partial<Store> = { state }
      const last = store.track[store.track.length - 1]
      const flying = state.armed && state.gps_fix !== 'none'
      if (flying && (!last || last[0] !== state.lon || last[1] !== state.lat)) {
        next.track = [...store.track.slice(-TRACK_LIMIT), [state.lon, state.lat]]
      }
      useVehicle.setState(next)
      break
    }
    case 'event': {
      const event = message.data as VehicleEvent
      const next: Partial<Store> = { events: [...store.events.slice(-EVENT_LIMIT), event] }
      if (event.kind === 'capture') {
        next.captures = [...store.captures, [event.data.lon as number, event.data.lat as number]]
      }
      if (event.kind === 'armed') {
        next.track = []
        next.captures = []
      }
      useVehicle.setState(next)
      if (event.severity === 'critical') store.toast('bad', event.message)
      break
    }
    case 'status': {
      const summary = message.data as VehicleSummary
      const before = store.summary
      useVehicle.setState(
        // A fresh connection starts with a clean map.
        summary.link === 'disconnected' && before?.link !== 'disconnected'
          ? { summary, state: null, track: [], captures: [] }
          : { summary },
      )
      // Mission geometry only travels in snapshots; fetch it when the mission changes.
      const changed =
        before?.mission?.mission_id !== summary.mission?.mission_id ||
        before?.mission?.revision !== summary.mission?.revision ||
        before?.mission?.segment !== summary.mission?.segment ||
        before?.link !== summary.link
      if (changed) void store.refresh()
      break
    }
  }
}

/** Open the live channel once, for the lifetime of the page. */
export function startLiveChannel() {
  if (socket) return
  const open = () => {
    const scheme = location.protocol === 'https:' ? 'wss' : 'ws'
    socket = new WebSocket(`${scheme}://${location.host}/ws`)
    useVehicle.setState({ channel: 'connecting' })
    socket.onopen = () => useVehicle.setState({ channel: 'open' })
    socket.onmessage = (event) => onMessage(event.data as string)
    socket.onclose = () => {
      useVehicle.setState({ channel: 'closed' })
      setTimeout(open, RETRY_MS)
    }
  }
  open()
}
