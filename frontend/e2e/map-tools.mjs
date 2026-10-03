/**
 * Browser check of the map tools on the Plan screen: show my location, search
 * for an address, search by coordinates, and move the take-off point to a place.
 *
 * The browser is given a pretend GPS position. The address search is real and
 * needs internet. Needs the backend on :8000 and the dev server on :5173.
 */
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { chromium } from 'playwright-core'

const BASE = process.env.OV_URL ?? 'http://localhost:5173'
const SHOTS = resolve(dirname(fileURLToPath(import.meta.url)), '../../docs/screens')
const HERE = { latitude: 13.0827, longitude: 80.2707, accuracy: 12 } // Chennai
const step = (text) => console.log(`- ${text}`)
const problems = []

function assert(condition, message) {
  if (!condition) throw new Error(`ASSERTION FAILED: ${message}`)
}

const browser = await chromium.launch({
  channel: 'chrome',
  headless: true,
  args: ['--ignore-gpu-blocklist', '--enable-unsafe-swiftshader'],
})
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  geolocation: HERE,
  permissions: ['geolocation', 'clipboard-read', 'clipboard-write'],
})
const page = await context.newPage()
page.on('console', (m) => {
  if (m.type() === 'error' && !/tile|arcgisonline|openstreetmap|Failed to load resource/i.test(m.text())) {
    problems.push(`console: ${m.text()}`)
  }
})
page.on('pageerror', (e) => problems.push(`page error: ${e.message}`))

const centre = () =>
  page.evaluate(() => {
    // The scale control's parent map exposes nothing globally, so read the canvas centre via the URL-free route:
    const el = document.querySelector('.maplibregl-map')
    return el ? el.getBoundingClientRect().width : 0
  })

try {
  await page.goto(`${BASE}/plan`)
  await page.getByRole('button', { name: 'Show my location' }).waitFor()
  await page.waitForTimeout(2500)
  assert((await centre()) > 500, 'the map should be on screen')

  step('Show my location')
  await page.getByRole('button', { name: 'Show my location' }).click()
  await page.getByText('You are here').waitFor({ timeout: 20_000 })
  await page.getByText('13.082700, 80.270700').waitFor()
  await page.getByText('Accurate to about 12 m').waitFor()
  await page.waitForTimeout(3500) // fly-to animation, tiles and the address lookup
  const address = await page.locator('[role="search"] .text-muted').first().innerText()
  step(`  address shown: ${address.replace(/\s+/g, ' ').slice(0, 90)}`)
  await page.screenshot({ path: resolve(SHOTS, '16-my-location.png') })

  step('Use it as the take-off point')
  await page.getByRole('button', { name: 'Set the take-off point here' }).click()
  await page.getByText('Take-off point moved').waitFor()

  step('Search for an address')
  const box = page.getByLabel('Address, place or coordinates')
  await box.fill('Cubbon Park, Bengaluru')
  await box.press('Enter')
  // Several matches give a list to choose from; a single match opens straight away.
  await page.locator('[role="search"] ul button, [role="search"] .num').first().waitFor({ timeout: 20_000 })
  const firstResult = page.locator('[role="search"] ul button').first()
  if (await firstResult.count()) {
    step(`  ${await page.locator('[role="search"] ul button').count()} matches listed; opening the first`)
    await firstResult.click()
  }
  await page.locator('[role="search"]').getByText(/12\.9\d+, 77\.5\d+/).waitFor({ timeout: 10_000 })
  await page.waitForTimeout(3500)
  await page.screenshot({ path: resolve(SHOTS, '17-address-search.png') })
  const shown = await page.locator('[role="search"] .num').first().innerText()
  step(`  found at ${shown}`)

  step('Copy the coordinates')
  await page.getByRole('button', { name: 'Copy coordinates' }).click()
  const clip = await page.evaluate(() => navigator.clipboard.readText())
  assert(/^12\.9\d+, 77\.5\d+$/.test(clip), `clipboard holds "${clip}"`)

  step('Search by coordinates')
  await box.fill('12.9716, 77.5946')
  await box.press('Enter')
  await page.locator('[role="search"]').getByText('Typed coordinates').waitFor({ timeout: 10_000 })
  await page.locator('[role="search"]').getByText('12.971600, 77.594600').first().waitFor()

  step('A search with no match says so')
  await box.fill('zzqxv nowhere place 99887')
  await box.press('Enter')
  await page.getByText('Nothing found').waitFor({ timeout: 20_000 })

  step('The tools are on the other map screens too')
  await page.getByRole('link', { name: 'Orchards' }).click()
  await page.getByRole('button', { name: 'Search for an address' }).waitFor()
  await page.getByRole('link', { name: 'Fly' }).click()
  await page.getByRole('button', { name: 'Show my location' }).waitFor()

  assert(problems.length === 0, `browser reported problems:\n  ${problems.join('\n  ')}`)
  console.log('\nPASS: location and address search work in the browser.')
} catch (error) {
  await page.screenshot({ path: resolve(SHOTS, 'zz-map-tools-failure.png') }).catch(() => undefined)
  console.error(`\nFAIL: ${error.message}`)
  if (problems.length) console.error(`Browser problems:\n  ${problems.join('\n  ')}`)
  process.exitCode = 1
} finally {
  await browser.close()
}
