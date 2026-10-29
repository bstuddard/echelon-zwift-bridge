import assert from 'node:assert/strict'
import { chromium } from 'playwright'

const baseURL = process.env.BRIDGE_TEST_URL || 'http://127.0.0.1:8001'
const browser = await chromium.launch({ executablePath: '/usr/bin/chromium', headless: true })
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, reducedMotion: 'reduce' })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  const response = await page.goto(baseURL + '/')
  assert.equal(response.status(), 200)
  await page.getByText('Server online', { exact: true }).waitFor()
  assert.equal(await page.locator('h1').innerText(), 'Ride overview')
  assert.equal(await page.locator('.metric-primary').evaluate((node) => getComputedStyle(node).backgroundColor), 'rgb(36, 59, 48)')
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
  await page.screenshot({ path: '/tmp/echelon-admin-desktop.png', fullPage: true })
  await page.getByRole('button', { name: 'Diagnostics', exact: true }).click()
  await page.getByText('Recent bridge events', { exact: true }).waitFor()
  await page.locator('details summary').click()
  assert.match(await page.locator('details pre').innerText(), /"reader_enabled": false/)
  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download JSON' }).click()
  assert.equal((await downloadPromise).suggestedFilename(), 'echelon-bridge-diagnostics.json')
  await page.getByRole('button', { name: 'Setup guide', exact: true }).click()
  await page.getByText('From a first pedal to your first ride', { exact: true }).waitFor()
  await page.getByRole('button', { name: 'About', exact: true }).click()
  await page.getByText('Echelon Bridge · GPL-3.0-only', { exact: true }).waitFor()
  for (const name of ['LICENSE.txt', 'NOTICE.txt', 'THIRD_PARTY_NOTICES.txt']) {
    const legal = await page.request.get(`${baseURL}/legal/${name}`)
    assert.equal(legal.status(), 200)
    assert.match(legal.headers()['content-type'], /text\/plain/)
    assert.ok((await legal.text()).length > 100)
  }
  // Browser-only failure injection; no data enters the bridge or BLE.
  await page.route('**/api/**', (route) => route.abort())
  await page.getByRole('button', { name: 'Refresh bridge status' }).click()
  await page.getByText('Local server is unavailable', { exact: true }).waitFor()
  await page.getByRole('button', { name: 'Ride monitor', exact: true }).click()
  assert.match(await page.getByTestId('power-value').innerText(), /—/)
  await page.unroute('**/api/**')
  await page.setViewportSize({ width: 390, height: 844 })
  await page.reload()
  await page.getByText('Server online', { exact: true }).waitFor()
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
  await page.screenshot({ path: '/tmp/echelon-admin-mobile.png', fullPage: true })
  assert.deepEqual(errors, [])
  console.log('Browser smoke passed: production assets/CSS, tabs, diagnostics, JSON download, local license copies, API loss, desktop/mobile layouts; no runtime errors.')
} finally {
  await browser.close()
}
