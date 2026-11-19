// Browser-local API fixtures never alter the real bike or ride recording.
import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'

const url = process.argv[2] || 'http://127.0.0.1:8000'
assert.equal(new URL(url).hostname, '127.0.0.1')
const browser = await chromium.launch(process.platform === 'win32'
  ? { channel: 'msedge', headless: true }
  : { executablePath: '/usr/bin/chromium', headless: true })
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } })
  let watts = 38
  let available = true
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname
    const responses = {
      '/api/health': { host_platform: 'windows', reader_enabled: true, bike_connected: true, simulated: false, failed_tasks: {}, peripheral: {}, bike_selection: 'pinned_address' },
      '/api/metrics': { connected: true, initialized: true, power_available: available, stale: !available, simulated: false,
        estimated_watts: watts, cadence_rpm: 45, resistance_level: 10, last_cadence_age_seconds: 0.1,
        session: { status: 'idle', revision: 'fixture' } },
      '/api/events': { events: [] },
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(responses[path] || {}) })
  })
  await page.goto(url)
  const toggle = page.getByRole('switch', { name: 'Pedal harder reminder' })
  assert.equal(await toggle.getAttribute('aria-checked'), 'false')
  await toggle.click()
  await page.getByLabel('Target power').fill('45')
  await page.getByTestId('pedal-alert').waitFor({ timeout: 12000 })
  assert.match(await page.getByTestId('effort-average').textContent(), /38/)
  assert.equal(await page.getByTestId('pedal-alert').evaluate(el => getComputedStyle(el).pointerEvents), 'none')
  await mkdir('screenshots', { recursive: true })
  await page.screenshot({ path: 'screenshots/pedal-alert-desktop.png', fullPage: true })

  watts = 45
  await page.getByRole('button', { name: 'Refresh bridge status' }).click()
  await page.getByTestId('pedal-alert').waitFor({ state: 'detached', timeout: 2000 })
  assert.equal(await page.getByTestId('effort-message').textContent(), 'Target reached')
  assert.ok(parseInt(await page.getByTestId('effort-average').textContent(), 10) < 45)

  watts = 38
  await page.getByRole('button', { name: 'Refresh bridge status' }).click()
  await page.getByTestId('pedal-alert').waitFor()
  await page.emulateMedia({ reducedMotion: 'reduce' })
  assert.equal(await page.getByTestId('pedal-alert').evaluate(el => getComputedStyle(el).animationName), 'none')
  await page.setViewportSize({ width: 390, height: 844 })
  await page.locator('.effort-card').scrollIntoViewIfNeeded()
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
  await page.screenshot({ path: 'screenshots/pedal-alert-mobile.png', fullPage: true })

  available = false
  await page.getByRole('button', { name: 'Refresh bridge status' }).click()
  await page.getByTestId('pedal-alert').waitFor({ state: 'detached', timeout: 2000 })
  await toggle.click()
  assert.equal(await toggle.getAttribute('aria-checked'), 'false')
  assert.deepEqual(errors, [])
  console.log('Pedal alert UI passed: 5-second average, immediate recovery, editable target, missing readings, reduced motion, and mobile layout.')
} finally {
  await browser.close()
}
