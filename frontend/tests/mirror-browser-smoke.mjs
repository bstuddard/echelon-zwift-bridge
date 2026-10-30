import assert from 'node:assert/strict'
import { chromium } from 'playwright'
import { configBase64, keyBase64 } from './mirror-video-fixture.mjs'

const baseURL = process.env.BRIDGE_TEST_URL || 'http://127.0.0.1:8001'
const browser = await chromium.launch({ executablePath: '/usr/bin/chromium', headless: true })
const envelope = (kind, base64, timestamp = 0) => {
  const payload = Buffer.from(base64, 'base64')
  const result = Buffer.alloc(9 + payload.length)
  result[0] = kind
  result.writeBigUInt64BE(BigInt(timestamp), 1)
  payload.copy(result, 9)
  return result
}
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } })
  const page = await context.newPage()
  const errors = []
  let opened = 0, closed = 0
  page.on('pageerror', (error) => errors.push(error.message))
  await page.route('**/api/mirror/status', (route) => route.fulfill({ json: { configured: true, active: false, token: 'browser-test-ticket' } }))
  await page.routeWebSocket('**/api/mirror/stream', (socket) => {
    opened++
    let timestamp = 0
    socket.send(envelope(1, configBase64))
    const timer = setInterval(() => {
      timestamp += 100000
      socket.send(envelope(2, keyBase64, timestamp))
    }, 100)
    socket.onClose(() => { closed++; clearInterval(timer) })
  })
  const response = await page.goto(baseURL + '/mirror')
  assert.equal(response.status(), 200)
  await page.getByRole('heading', { name: 'Phone mirror', exact: true }).waitFor()
  await page.getByRole('button', { name: 'Start mirroring', exact: true }).waitFor()
  assert.equal(opened, 0)
  await page.getByRole('button', { name: 'Start mirroring', exact: true }).click()
  await page.getByText('Live · view only', { exact: true }).waitFor({ timeout: 10000 })
  const color = await page.getByTestId('phone-video').evaluate((canvas) => [...canvas.getContext('2d').getImageData(1, 1, 1, 1).data])
  assert.ok(color[2] > 150 && color[0] < 60 && color[1] > 70 && color[1] < 110, 'The real browser decoder displayed the generated test video')
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
  await page.screenshot({ path: '/tmp/echelon-mirror-desktop.png', fullPage: true })
  await page.getByRole('button', { name: 'Stop mirroring', exact: true }).click()
  await page.getByText('Your phone stays private until you start', { exact: true }).waitFor()
  assert.equal(await page.getByTestId('phone-video').evaluate((canvas) => [...canvas.getContext('2d').getImageData(1, 1, 1, 1).data].slice(0, 3).every((channel) => channel === 0)), true)
  await page.waitForTimeout(100)
  assert.equal(closed, 1)
  await page.getByRole('button', { name: 'Start mirroring', exact: true }).click()
  await page.getByText('Live · view only', { exact: true }).waitFor()
  await page.getByRole('button', { name: 'Ride monitor', exact: true }).click()
  assert.equal(new URL(page.url()).pathname, '/')
  assert.equal(await page.getByTestId('phone-video').count(), 0)
  await page.waitForTimeout(100)
  assert.equal(closed, 2)
  await page.goBack()
  await page.getByRole('heading', { name: 'Phone mirror', exact: true }).waitFor()
  assert.equal(await page.locator('nav [aria-current="page"]').innerText(), 'Phone mirror')
  assert.equal(opened, 2, 'Back navigation never restarts capture')
  await page.setViewportSize({ width: 390, height: 844 })
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
  await page.screenshot({ path: '/tmp/echelon-mirror-mobile.png', fullPage: true })
  assert.deepEqual(errors, [])
  console.log('Mirror browser smoke passed: real H.264 decoding, opt-in start, stop clears image, navigation releases capture, direct URL, mobile layout, no runtime errors. Only generated test video used.')
  await context.close()
} finally {
  await browser.close()
}
