import assert from 'node:assert/strict'
import { chromium } from 'playwright'

const [url, path] = process.argv.slice(2)
assert.equal(new URL(url).hostname, '127.0.0.1')
const browser = await chromium.launch(process.platform === 'win32'
  ? { channel: 'msedge', headless: true }
  : { executablePath: '/usr/bin/chromium', headless: true })
try {
  const page = await browser.newPage()
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto(url)
  await page.getByRole('button', { name: 'Start session', exact: true }).click()
  await page.waitForFunction(expected => document.getElementById('session-file')?.value === expected, path)
  await page.getByRole('button', { name: 'Start recording' }).click()
  await page.getByRole('heading', { name: 'Session in progress' }).waitFor()
  const average = page.locator('dl > div').filter({ has: page.getByText('Average power', { exact: true }) })
  await average.getByText('165 W', { exact: true }).waitFor()
  assert.match(await page.getByTestId('power-value').innerText(), /165/)
  await page.reload()
  await page.getByRole('heading', { name: 'Session in progress' }).waitFor()
  await page.getByRole('button', { name: 'Finish session' }).click()
  await page.getByRole('heading', { name: 'Session summary' }).waitFor()
  assert.match(await average.innerText(), /165 W/)
  assert.equal(await page.getByText('Estimated FTP', { exact: true }).count(), 1)
  assert.deepEqual(errors, [])
  console.log('Ride session UI passed: private default path, live and average power, reload, finish and summary.')
} finally {
  await browser.close()
}
