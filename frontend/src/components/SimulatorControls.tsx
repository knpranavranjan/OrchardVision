import { BatteryWarning, SatelliteDish, Unplug, Wind } from 'lucide-react'
import { useState } from 'react'

import { api } from '../lib/api'
import { useVehicle } from '../lib/store'
import { Button, NumberField, SelectField } from './ui'

/**
 * Change the simulator's conditions mid-flight to rehearse failures: the same
 * failsafe settings that go to a real drone decide what the virtual one does.
 */
export function SimulatorControls() {
  const sim = useVehicle((s) => s.summary?.sim)
  const kind = useVehicle((s) => s.summary?.kind)
  const state = useVehicle((s) => s.state)
  const toast = useVehicle((s) => s.toast)
  const [wind, setWind] = useState(6)
  const [windFrom, setWindFrom] = useState(270)
  const [battery, setBattery] = useState(19)

  if (kind !== 'sim' || !sim) {
    return <p className="text-[13px] text-muted">Connect the built-in simulator to use these controls.</p>
  }

  const apply = async (conditions: Parameters<typeof api.simConditions>[0], done: string) => {
    try {
      await api.simConditions(conditions)
      toast('warn', done)
    } catch (e) {
      toast('bad', (e as Error).message)
    }
  }

  return (
    <div className="grid gap-4">
      <SelectField
        label="Simulation speed"
        value={sim.speedup}
        onChange={(v) => apply({ speedup: v }, `Simulation speed set to ${v}x`)}
        options={[1, 2, 5, 10, 20].map((v) => ({ value: v, label: v === 1 ? 'Real time' : `${v} times faster` }))}
      />

      <div>
        <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">Rehearse a failure</div>
        <div className="grid gap-2">
          <div className="grid grid-cols-[1fr_auto] items-end gap-2">
            <NumberField label="Set battery to" unit="%" value={battery} onChange={setBattery} min={0} max={100} />
            <Button icon={<BatteryWarning size={16} />} onClick={() => apply({ battery_pct: battery }, `Battery set to ${battery}%`)}>
              Apply
            </Button>
          </div>
          <Button
            icon={<SatelliteDish size={16} />}
            onClick={() =>
              state?.gps_fix === 'none'
                ? apply({ gps_ok: true }, 'GPS restored')
                : apply({ gps_ok: false }, 'GPS switched off')
            }
          >
            {state?.gps_fix === 'none' ? 'Restore GPS' : 'Lose GPS'}
          </Button>
          <Button icon={<Unplug size={16} />} onClick={() => apply({ link_blackout_s: 8 }, 'Link dropped for 8 seconds')}>
            Drop the link for 8 seconds
          </Button>
        </div>
      </div>

      <div>
        <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">Wind</div>
        <div className="grid grid-cols-2 gap-2">
          <NumberField label="Speed" unit="m/s" value={wind} onChange={setWind} min={0} max={25} />
          <NumberField label="From" unit="degrees" value={windFrom} onChange={setWindFrom} min={0} max={359} />
        </div>
        <div className="mt-2 flex gap-2">
          <Button icon={<Wind size={16} />} onClick={() => apply({ wind_mps: wind, wind_from_deg: windFrom }, `Wind ${wind} m/s from ${windFrom}°`)}>
            Set wind
          </Button>
          <Button variant="ghost" onClick={() => apply({ wind_mps: 0 }, 'Wind off')}>
            Calm
          </Button>
        </div>
        <p className="mt-1.5 text-[11.5px] text-muted">
          Now: {sim.wind_mps.toFixed(0)} m/s from {sim.wind_from_deg.toFixed(0)}°. Wind drains the battery faster.
        </p>
      </div>
    </div>
  )
}
