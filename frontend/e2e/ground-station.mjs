/**
 * End-to-end check of the ground station in a real browser.
 *
 * It does what an operator does: creates an orchard by clicking its corners on
 * the map, plans a survey over it, rehearses the mission in the simulator from
 * arming to landing, then opens the flight record. Screenshots go to docs/screens.
 *
 * Needs the database, the backend on :8000 and the dev server on :5173.
 *   node e2e/ground-station.mjs
 */
import { mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { chromium } from 'playwright-core'

const BASE = process.env.OV_URL ?? 'http://localhost:5173'
const SHOTS = resolve(dirname(fileURLToPath(import.meta.url)), '../../docs/screens')
mkdirSync(SHOTS, { recursive: true })

const stamp = Date.now().toString().slice(-6)
const ORCHARD = `E2E Orchard ${stamp}`
const MISSION = `E2E Survey ${stamp}`

const problems = []
const step = (text) => console.log(`- ${text}`)

function assert(condition, message) {
  if (!condition) throw new Error(`ASSERTION FAILED: ${message}`)
}

async function api(page, method, path, body) {
  const response = await page.request.fetch(`${BASE}${path}`, { method, data: body })
  return response.ok() ? response.json().catch(() => null) : Promise.reject(new Error(`${method} ${path}: ${response.status()} ${await response.text()}`))
}

async function waitForStatus(page, condition, what, timeoutMs = 120_000) {
  const end = Date.now() + timeoutMs
  let status
  while (Date.now() < end) {
    status = await api(page, 'GET', '/api/vehicle/status')
    if (condition(status)) return status
    await page.waitForTimeout(300)
  }
  throw new Error(`timed out waiting for ${what}; mode=${status?.state?.mode} seq=${status?.state?.mission_seq}`)
}

async function hold(page, locator, ms = 1100) {
  const box = await locator.boundingBox()
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  await page.waitForTimeout(ms)
  await page.mouse.up()
}

const shot = (page, name) => page.screenshot({ path: resolve(SHOTS, `${name}.png`) })

const browser = await chromium.launch({
  channel: 'chrome',
  headless: true,
  args: ['--ignore-gpu-blocklist', '--enable-unsafe-swiftshader'],
})
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
page.on('console', (m) => {
  // Map tiles can fail without internet; that is not an application error.
  if (m.type() === 'error' && !/tile|arcgisonline|openstreetmap|Failed to load resource/i.test(m.text())) {
    problems.push(`console: ${m.text()}`)
  }
})
page.on('pageerror', (e) => problems.push(`page error: ${e.message}`))

try {
  // A clean start: no vehicle connected.
  const before = await api(page, 'GET', '/api/vehicle/status')
  if (before.link !== 'disconnected') await api(page, 'POST', '/api/vehicle/disconnect', {})

  step('Fly screen with no vehicle')
  await page.goto(BASE)
  await page.getByText('NO VEHICLE').waitFor()
  await page.waitForTimeout(2500) // map tiles
  await shot(page, '01-fly-not-connected')

  step('Create an orchard by clicking its corners')
  await page.getByRole('link', { name: 'Orchards' }).click()
  await page.getByRole('button', { name: 'New orchard' }).click()
  await page.getByLabel('Name', { exact: true }).fill(ORCHARD)
  await page.waitForTimeout(1500)
  const cx = 76 + 360 + (1440 - 436) / 2
  const cy = 56 + (900 - 56) / 2
  for (const [dx, dy] of [[-60, 68], [115, 68], [115, -65], [-60, -65]]) {
    await page.mouse.click(cx + dx, cy + dy)
    await page.waitForTimeout(150)
  }
  await page.getByText('Boundary: 4 corners').waitFor()
  await page.getByRole('button', { name: 'Save' }).click()
  await page.getByText(`Saved ${ORCHARD}`).waitFor()
  await shot(page, '02-orchard')
  const orchard = (await api(page, 'GET', '/api/orchards')).find((o) => o.name === ORCHARD)
  assert(orchard && orchard.area_ha > 0.3 && orchard.area_ha < 2, `orchard area ${orchard?.area_ha}`)
  step(`  orchard saved: ${orchard.area_ha} ha, models ready: ${orchard.models_ready}`)

  step('Plan a survey over it')
  await page.getByRole('link', { name: 'Plan' }).click()
  await page.getByLabel('Name', { exact: true }).fill(MISSION)
  await page.getByLabel('Orchard', { exact: true }).selectOption({ label: `${ORCHARD} (papaya)` })
  await page.getByRole('button', { name: 'Use the orchard boundary as the area' }).click()
  await page.getByRole('button', { name: 'Fence 20 m around' }).click()
  await page.getByText('Ready', { exact: true }).waitFor({ timeout: 15_000 })
  await page.waitForTimeout(1200)
  await shot(page, '03-plan')
  await page.getByRole('button', { name: 'Save mission' }).click()
  await page.getByText('Saved as revision 1').waitFor()
  const mission = (await api(page, 'GET', '/api/missions')).find((m) => m.name === MISSION)
  assert(mission?.valid, 'mission should be valid')
  step(`  mission saved: ${mission.stats.lines} lines, ${mission.stats.photos} photos, ${Math.round(mission.stats.time_s / 60)} min, ${Math.round(mission.stats.battery_pct)}% battery`)

  step('Rehearse it in the simulator')
  await page.getByRole('button', { name: 'Rehearse in the simulator' }).click()
  await page.waitForURL(`${BASE}/`)
  await page.getByText('READY TO FLY').waitFor({ timeout: 15_000 })
  await page.waitForTimeout(1500)
  await shot(page, '04-fly-ready')
  const loaded = await api(page, 'GET', '/api/vehicle/status')
  assert(loaded.mission?.verified, 'mission should be verified on the vehicle')

  step('Hold Arm, then hold Start mission')
  await hold(page, page.getByRole('button', { name: /^Arm/ }))
  await waitForStatus(page, (s) => s.state?.armed, 'armed', 10_000)
  await hold(page, page.getByRole('button', { name: /^Start mission/ }))
  await waitForStatus(page, (s) => s.state?.mode === 'auto' && s.state.alt_rel_m > 5, 'take-off', 60_000)
  await api(page, 'POST', '/api/vehicle/sim/conditions', { speedup: 20 })
  await waitForStatus(page, (s) => (s.state?.mission_seq ?? 0) >= 12, 'a few survey lines', 120_000)
  await shot(page, '05-fly-in-mission')

  step('Pause, fly by hand, resume')
  await api(page, 'POST', '/api/vehicle/sim/conditions', { speedup: 1 })
  await page.getByRole('button', { name: 'Pause' }).click()
  await waitForStatus(page, (s) => s.state?.mode === 'hold', 'hold', 15_000)
  await page.getByRole('tab', { name: 'Manual' }).click()
  const beforeManual = (await api(page, 'GET', '/api/vehicle/status')).state
  await hold(page, page.getByRole('button', { name: 'Forward' }), 2500)
  const afterManual = (await api(page, 'GET', '/api/vehicle/status')).state
  const moved = Math.hypot(afterManual.lat - beforeManual.lat, afterManual.lon - beforeManual.lon) * 111_320
  assert(moved > 1.5, `manual control should move the vehicle, moved ${moved.toFixed(2)} m`)
  step(`  moved ${moved.toFixed(1)} m by hand`)
  await shot(page, '06-fly-manual')
  // After hand flying the mission is restarted from the Start button, as on a real drone.
  await hold(page, page.getByRole('button', { name: /^Start mission/ }))
  await waitForStatus(page, (s) => s.state?.mode === 'auto', 'mission restarted', 15_000)
  await api(page, 'POST', '/api/vehicle/sim/conditions', { speedup: 20 })

  step('Let it finish and land')
  const done = await waitForStatus(page, (s) => !s.flying, 'landing', 240_000)
  assert(done.last_flight_id, 'a flight should have been recorded')
  await page.getByRole('tab', { name: 'Log' }).click()
  await page.waitForTimeout(800)
  await shot(page, '07-fly-landed')

  step('Open the flight record')
  await page.getByRole('link', { name: 'Flights' }).click()
  await page.getByRole('button', { name: new RegExp(MISSION) }).first().click()
  await page.getByRole('heading', { name: 'What happened' }).waitFor()
  await page.waitForTimeout(2500)
  await shot(page, '08-flight-record')
  const flight = await api(page, 'GET', `/api/flights/${done.last_flight_id}`)
  assert(flight.status === 'completed', `flight status ${flight.status}`)
  assert(flight.summary.captures > 0, 'photos should be recorded')
  assert(flight.telemetry.length > 20, 'telemetry should be recorded')
  step(`  flight ${flight.id}: ${flight.status}, ${Math.round(flight.summary.distance_m)} m, ${flight.summary.captures} photos, ${flight.telemetry.length} samples`)

  step('Simulation, Models and Settings screens')
  await page.getByRole('link', { name: 'Simulate' }).click()
  await page.getByRole('heading', { name: 'Rehearse a mission' }).waitFor()
  await page.waitForTimeout(600)
  await shot(page, '09-simulation')
  await page.getByRole('link', { name: 'Models' }).click()
  await page.getByRole('heading', { name: 'Crop profiles' }).waitFor()
  await shot(page, '10-models')
  await page.getByRole('link', { name: 'Settings' }).click()
  await page.getByRole('heading', { name: 'Emergency actions' }).waitFor()
  await shot(page, '11-settings')

  step('Light theme and the connection dialog')
  await page.getByRole('button', { name: 'Switch to the light theme' }).click()
  await page.getByRole('link', { name: 'Fly' }).click()
  await page.getByRole('button', { name: /Connected/ }).click()
  await page.getByRole('dialog').waitFor()
  await shot(page, '12-light-theme-link-dialog')
  await page.getByRole('button', { name: 'Disconnect' }).click()
  await page.getByText('NO VEHICLE').waitFor()
  await page.getByRole('button', { name: /Not connected/ }).click()
  await page.getByRole('tab', { name: 'Drone by USB or radio' }).click()
  await shot(page, '13-connect-dialog')
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'Switch to the dark theme' }).click()

  assert(problems.length === 0, `browser reported problems:\n  ${problems.join('\n  ')}`)
  console.log('\nPASS: the ground station worked end to end in the browser.')
} catch (error) {
  await shot(page, 'zz-failure').catch(() => undefined)
  console.error(`\nFAIL: ${error.message}`)
  if (problems.length) console.error(`Browser problems:\n  ${problems.join('\n  ')}`)
  process.exitCode = 1
} finally {
  await browser.close()
}
