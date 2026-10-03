/**
 * The ground station flying the real ArduPilot flight code (SITL), through the
 * browser, exactly as it would fly a Pixhawk: connect, confirm the operator
 * checks, upload with read-back, hold Arm, hold Start, watch it land.
 *
 * Needs the database, the backend on :8000, the dev server on :5173 and
 *   docker compose --profile sitl up -d sitl
 * Takes about five minutes because the autopilot flies in real time.
 */
import { mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { chromium } from 'playwright-core'

const BASE = process.env.OV_URL ?? 'http://localhost:5173'
const SHOTS = resolve(dirname(fileURLToPath(import.meta.url)), '../../docs/screens')
mkdirSync(SHOTS, { recursive: true })
const step = (text) => console.log(`- ${text}`)

function assert(condition, message) {
  if (!condition) throw new Error(`ASSERTION FAILED: ${message}`)
}

const browser = await chromium.launch({
  channel: 'chrome',
  headless: true,
  args: ['--ignore-gpu-blocklist', '--enable-unsafe-swiftshader'],
})
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })

async function api(method, path, body) {
  const response = await page.request.fetch(`${BASE}${path}`, { method, data: body })
  if (!response.ok()) throw new Error(`${method} ${path}: ${response.status()} ${await response.text()}`)
  return response.json().catch(() => null)
}

async function waitFor(condition, what, timeoutMs) {
  const end = Date.now() + timeoutMs
  let status
  while (Date.now() < end) {
    status = await api('GET', '/api/vehicle/status')
    if (condition(status)) return status
    await page.waitForTimeout(500)
  }
  throw new Error(`timed out waiting for ${what}; state=${JSON.stringify(status?.state)}`)
}

async function hold(locator, ms = 1100) {
  const box = await locator.boundingBox()
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  await page.waitForTimeout(ms)
  await page.mouse.up()
}

/** A rectangle given in metres east and north of a point. */
function box(home, e0, n0, e1, n1) {
  const dLat = 1 / 110_574
  const dLon = 1 / (111_320 * Math.cos((home.lat * Math.PI) / 180))
  return [[e0, n0], [e1, n0], [e1, n1], [e0, n1]].map(([e, n]) => ({
    lat: home.lat + n * dLat,
    lon: home.lon + e * dLon,
  }))
}

try {
  const before = await api('GET', '/api/vehicle/status')
  if (before.link !== 'disconnected') await api('POST', '/api/vehicle/disconnect', {})

  step('Connect to the software autopilot through the connection dialog')
  await page.goto(BASE)
  await page.getByRole('button', { name: /Not connected/ }).click()
  await page.getByRole('tab', { name: 'Software autopilot' }).click()
  await page.getByRole('button', { name: 'Connect', exact: true }).click()
  await page.getByText('Software autopilot connected').waitFor({ timeout: 30_000 })

  step('Wait for its GPS, estimator and home position')
  const ready = await waitFor(
    (s) => s.state && s.state.gps_fix !== 'none' && s.state.ekf_ok && s.state.home_lat !== null,
    'GPS and home',
    120_000,
  )
  const home = { lat: ready.state.home_lat, lon: ready.state.home_lon }
  step(`  home ${home.lat.toFixed(6)}, ${home.lon.toFixed(6)}; ${ready.state.satellites} satellites; mode ${ready.state.mode_raw}`)

  step('Create a small survey beside it and upload it')
  const settings = await api('GET', '/api/settings')
  const plan = {
    type: 'survey',
    home,
    takeoff_alt_m: 15,
    survey: {
      polygon: box(home, 10, 10, 50, 50),
      altitude_m: 15,
      speed_mps: 5,
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
    geofence: box(home, -40, -40, 100, 100),
    end_action: 'rtl',
    safety: settings.safety,
    camera: settings.cameras[2],
    vehicle: settings.vehicle,
  }
  const mission = await api('POST', '/api/missions', {
    name: `SITL survey ${Date.now().toString().slice(-6)}`,
    orchard_id: null,
    plan,
  })
  assert(mission.valid, `mission should be valid: ${JSON.stringify(mission.validation.checks.filter((c) => c.status === 'fail'))}`)
  await page.reload()
  await page.getByLabel('Saved mission').selectOption({ label: mission.name })
  await page.getByRole('button', { name: 'Upload to vehicle' }).click()
  await page.getByText('Mission uploaded and read back identical').waitFor({ timeout: 60_000 })

  step('Confirm the operator checks')
  for (let i = 0; i < 4; i++) {
    await page.getByRole('button', { name: 'Confirm', exact: true }).first().click()
    await page.waitForTimeout(300)
  }
  await page.getByText('READY TO FLY').waitFor({ timeout: 60_000 })
  await page.waitForTimeout(1500)
  await page.screenshot({ path: resolve(SHOTS, '14-sitl-ready.png') })

  step('Hold Arm, hold Start mission')
  await hold(page.getByRole('button', { name: /^Arm/ }))
  await waitFor((s) => s.state?.armed, 'armed', 30_000)
  await hold(page.getByRole('button', { name: /^Start mission/ }))
  await waitFor((s) => s.state?.mode === 'auto' && s.state.alt_rel_m > 12, 'climb', 90_000)
  await waitFor((s) => (s.state?.mission_seq ?? 0) >= 6, 'second survey line', 120_000)
  await page.screenshot({ path: resolve(SHOTS, '15-sitl-flying.png') })

  step('Let the autopilot finish, return and land')
  const done = await waitFor((s) => !s.flying, 'landing', 420_000)
  const flight = await api('GET', `/api/flights/${done.last_flight_id}`)
  assert(flight.vehicle_kind === 'sitl', 'the record should say which vehicle flew')
  assert(flight.telemetry.length > 100, 'telemetry should be recorded')
  const track = flight.telemetry
  const maxAlt = Math.max(...track.map((p) => p.alt))
  assert(maxAlt > 13 && maxAlt < 35, `height ${maxAlt}`)
  step(`  flight ${flight.id}: ${flight.status}, ${Math.round(flight.summary.distance_m)} m, ${Math.round(flight.summary.duration_s)} s, max height ${maxAlt.toFixed(1)} m, ${flight.telemetry.length} samples`)
  await api('POST', '/api/vehicle/disconnect', {})
  console.log('\nPASS: the ground station flew a mission on the real ArduPilot flight code.')
} catch (error) {
  await page.screenshot({ path: resolve(SHOTS, 'zz-sitl-failure.png') }).catch(() => undefined)
  console.error(`\nFAIL: ${error.message}`)
  process.exitCode = 1
} finally {
  await browser.close()
}
