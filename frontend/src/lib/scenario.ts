/**
 * A rehearsal scenario: one failure injected into the simulator when the mission
 * reaches a chosen point. It lives outside any page so it keeps watching while
 * the operator is on the Fly screen.
 */
import { api } from './api'
import { useVehicle } from './store'

export type Failure = 'none' | 'gps' | 'battery' | 'link' | 'wind'

export const FAILURES: { value: Failure; label: string; expect: string }[] = [
  { value: 'none', label: 'No failure', expect: 'The mission completes and the drone lands at home.' },
  { value: 'battery', label: 'Battery drops to critical', expect: 'The battery failsafe takes over.' },
  { value: 'gps', label: 'GPS is lost', expect: 'The GPS failsafe takes over; by default the drone lands where it is.' },
  { value: 'link', label: 'Link drops for 8 seconds', expect: 'The ground station shows the link as lost and the link failsafe takes over.' },
  { value: 'wind', label: 'Wind rises to 10 m/s', expect: 'The flight continues and uses more battery than planned.' },
]

let stop: (() => void) | null = null

export function cancelScenario() {
  stop?.()
  stop = null
}

export function armScenario(failure: Failure, atPercent: number) {
  cancelScenario()
  if (failure === 'none') return
  stop = useVehicle.subscribe((store) => {
    const s = store.state
    const count = store.summary?.mission?.item_count
    if (!s || !count || s.mode !== 'auto' || s.mission_seq === null) return
    if (((s.mission_seq + 1) / count) * 100 < atPercent) return
    cancelScenario()
    const conditions =
      failure === 'gps'
        ? { gps_ok: false }
        : failure === 'battery'
          ? { battery_pct: 15 }
          : failure === 'link'
            ? { link_blackout_s: 8 }
            : { wind_mps: 10, wind_from_deg: 270 }
    api.simConditions(conditions).catch(() => undefined)
  })
}
