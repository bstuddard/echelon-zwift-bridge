// Browser-local API fixtures never alter the real bike or ride recording.
import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { chromium } from 'playwright'

const url = process.argv[2] || 'http://127.0.0.1:8000'
assert.equal(new URL(url).hostname, '127.0.0.1')
const browser = await chromium.launch(process.platform === 'win32'
  ? { channel: 'msedge', headless: true, args: ['--mute-audio'] }
  : { executablePath: '/usr/bin/chromium', headless: true, args: ['--mute-audio'] })
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } })
  await page.addInitScript(() => {
    window.audioProbe = { starts: 0, immediateStops: 0, states: [] }
    const NativeAudio = window.AudioContext
    window.AudioContext = class extends NativeAudio {
      constructor(...args) {
        super(...args)
        this.addEventListener('statechange', () => window.audioProbe.states.push(this.state))
      }
      createOscillator() {
        const oscillator = super.createOscillator()
        const start = oscillator.start.bind(oscillator)
        const stop = oscillator.stop.bind(oscillator)
        oscillator.start = (...args) => { window.audioProbe.starts++; return start(...args) }
        oscillator.stop = (...args) => { if (!args.length) window.audioProbe.immediateStops++; return stop(...args) }
        return oscillator
      }
    }
  })
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

  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.getByRole('button', { name: 'Focus mode', exact: true }).click()
  const focus = page.getByTestId('focus-mode')
  await focus.waitFor()
  assert.equal(await focus.evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(196, 0, 29)')
  await page.getByRole('alert').filter({ hasText: 'PEDAL HARDER' }).waitFor()
  await page.waitForFunction(() => document.fullscreenElement?.dataset.testid === 'focus-mode')
  await page.waitForFunction(() => getComputedStyle(document.querySelector('.focus-controls')).opacity === '0')
  await page.screenshot({ path: 'screenshots/focus-reminder.png' })
  assert.ok((await page.evaluate(() => window.audioProbe.states)).includes('running'))
  const beepsBefore = await page.evaluate(() => window.audioProbe.starts)
  await page.waitForFunction(count => window.audioProbe.starts > count, beepsBefore)

  watts = 45
  await page.waitForFunction(() => !document.querySelector('.focus-stage')?.classList.contains('is-warning'), null, { timeout: 2500 })
  assert.ok(parseInt(await page.getByTestId('focus-average').textContent(), 10) < 45)
  const quietCount = await page.evaluate(() => window.audioProbe.starts)
  await page.waitForTimeout(1700)
  assert.equal(await page.evaluate(() => window.audioProbe.starts), quietCount)
  assert.equal(await focus.evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(0, 0, 0)')
  assert.equal(await page.getByTestId('focus-average').evaluate(el => getComputedStyle(el).fontSize), '28px')
  await page.screenshot({ path: 'screenshots/focus-quiet.png' })

  // Browser fullscreen exit (including its native Esc handling) must restore the dashboard.
  await page.evaluate(() => document.exitFullscreen())
  await focus.waitFor({ state: 'detached' })
  assert.equal(await toggle.getAttribute('aria-checked'), 'true')
  assert.equal(await page.getByLabel('Target power').inputValue(), '45')
  await page.getByLabel('Beep', { exact: true }).uncheck()
  watts = 38
  await page.getByTestId('pedal-alert').waitFor({ timeout: 12000 })
  const mutedCount = await page.evaluate(() => window.audioProbe.starts)
  // Denied fullscreen still provides a working overlay and keyboard exit.
  await page.evaluate(() => { Element.prototype.requestFullscreen = () => Promise.reject(new Error('Fixture denial')) })
  await page.getByRole('button', { name: 'Focus mode', exact: true }).click()
  await focus.waitFor()
  await page.setViewportSize({ width: 390, height: 844 })
  assert.ok(await focus.evaluate(el => el.scrollWidth <= innerWidth))
  await page.screenshot({ path: 'screenshots/focus-mobile.png' })
  await page.waitForTimeout(1700)
  assert.equal(await page.evaluate(() => window.audioProbe.starts), mutedCount)

  available = false
  await page.getByTestId('focus-average').filter({ hasText: '— W' }).waitFor()
  assert.equal(await focus.evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(0, 0, 0)')
  await page.keyboard.press('Escape')
  await focus.waitFor({ state: 'detached' })
  await toggle.click()
  assert.equal(await toggle.getAttribute('aria-checked'), 'false')
  assert.deepEqual(errors, [])
  console.log('Pedal alert UI passed: five-second average, immediate visual/audio recovery, repeat and mute, focus fullscreen and fallback, exit, missing readings, reduced motion, mobile layout.')
} finally {
  await browser.close()
}
