// Runs only against scripts/test_mirror_e2e.py's isolated fake-phone server.
// No routes are mocked: Chromium -> Uvicorn -> WebSocket -> fake ADB -> loopback video.
import assert from 'node:assert/strict'
import crypto from 'node:crypto'
import fs from 'node:fs/promises'
import http from 'node:http'
import net from 'node:net'
import path from 'node:path'
import { chromium } from 'playwright'

const root = process.env.MIRROR_TEST_ROOT
assert.ok(root && root.startsWith('/tmp/echelon-mirror-e2e-'), 'Use the isolated E2E runner, never a live phone server')
const base = process.env.BRIDGE_TEST_URL
const target = new URL(base)
const wsURL = base.replace(/^http:/, 'ws:') + '/api/mirror/stream'
const mode = (value) => fs.writeFile(path.join(root, 'mode'), value)
const events = async () => {
  try { return (await fs.readFile(path.join(root, 'events.jsonl'), 'utf8')).trim().split('\n').filter(Boolean).map(JSON.parse) }
  catch (error) { if (error.code === 'ENOENT') return []; throw error }
}
const get = (route, headers = {}) => new Promise((resolve, reject) => {
  http.get(base + route, { headers }, (response) => {
    const chunks = []
    response.on('data', (chunk) => chunks.push(chunk))
    response.on('end', () => resolve({ status: response.statusCode, headers: response.headers, text: Buffer.concat(chunks).toString() }))
  }).on('error', reject)
})
const status = async () => JSON.parse((await get('/api/mirror/status')).text)
async function until(predicate, timeout = 10000) {
  const deadline = Date.now() + timeout
  while (Date.now() < deadline) { if (await predicate()) return; await new Promise((resolve) => setTimeout(resolve, 30)) }
  throw new Error('Timed out waiting for isolated test cleanup')
}
async function clean() {
  await until(async () => !(await status()).active)
  for (const name of ['uploaded', 'tunnel']) {
    await assert.rejects(fs.stat(path.join(root, name)), { code: 'ENOENT' })
  }
  const rows = await events()
  const started = rows.filter((row) => row.kind === 'capture-start').length
  const stopped = rows.filter((row) => row.kind === 'capture-stop').length
  assert.equal(stopped, started, 'Every synthetic capture process stopped')
}
function handshake({ origin = base, protocols, host = target.host, query = '', extensions } = {}) {
  return new Promise((resolve, reject) => {
    const socket = net.connect({ host: '127.0.0.1', port: Number(target.port) })
    let output = ''
    let resolved = false
    socket.setTimeout(3000, () => { socket.destroy(); reject(new Error('Handshake timeout')) })
    socket.on('error', reject)
    socket.on('close', () => { if (!resolved) { resolved = true; resolve(0) } })
    socket.on('connect', () => {
      const headers = [`GET /api/mirror/stream${query} HTTP/1.1`, `Host: ${host}`, 'Connection: Upgrade', 'Upgrade: websocket', 'Sec-WebSocket-Version: 13', 'Sec-WebSocket-Key: ' + crypto.randomBytes(16).toString('base64')]
      if (origin !== null) headers.push('Origin: ' + origin)
      if (protocols) headers.push('Sec-WebSocket-Protocol: ' + protocols.join(', '))
      if (extensions) headers.push('Sec-WebSocket-Extensions: ' + extensions)
      socket.write(headers.join('\r\n') + '\r\n\r\n')
    })
    socket.on('data', (chunk) => {
      output += chunk.toString()
      if (output.includes('\r\n\r\n')) {
        const code = Number(output.split(' ')[1])
        resolved = true
        socket.destroy()
        resolve(code)
      }
    })
  })
}

const browser = await chromium.launch({ executablePath: '/usr/bin/chromium', headless: true })
let evil
let checks = 0
try {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  async function load() {
    await page.goto(base + '/mirror')
    await page.getByRole('heading', { name: 'Phone mirror', exact: true }).waitFor()
    await page.bringToFront()
  }
  async function start() {
    await page.getByRole('button', { name: 'Start mirroring', exact: true }).click()
  }
  const live = () => page.getByText('Live · view only', { exact: true }).waitFor({ timeout: 10000 })
  const text = (value) => page.waitForFunction((value) => document.body.innerText.includes(value), value, { timeout: 12000 })
  async function stop() {
    await page.getByRole('button', { name: 'Stop mirroring', exact: true }).click()
    await clean()
    const pixel = await page.getByTestId('phone-video').evaluate((canvas) => [...canvas.getContext('2d').getImageData(1, 1, 1, 1).data].slice(0, 3))
    assert.deepEqual(pixel, [0, 0, 0], 'Stop clears decoded pixels')
  }

  await load()
  assert.equal((await events()).length, 0, 'Loading the page does not run ADB')
  const ticket = (await status()).token
  const protocols = ['echelon-mirror', 'ticket.' + ticket]
  const bad = [
    { origin: 'https://untrusted.example', protocols },
    { origin: null, protocols },
    { origin: 'null', protocols },
    { protocols: ['echelon-mirror', 'ticket.stale'] },
    { protocols: ['echelon-mirror', 'ticket.é'] },
    { protocols, extensions: 'permessage-deflate; é' },
    { protocols: ['echelon-mirror'] },
    { query: '?token=' + ticket },
    { host: 'untrusted.example', protocols },
    { host: 'localhost:65536', origin: 'http://localhost:65536', protocols },
  ]
  for (const [index, options] of bad.entries()) {
    const code = await handshake(options)
    assert.ok([400, 403].includes(code), `Malformed handshake case ${index} returned HTTP ${code}`)
    checks++
  }
  assert.equal((await events()).length, 0, 'Rejected connections never start ADB')
  console.log('E2E: malformed requests rejected before ADB startup.')
  const rejected = await get('/mirror', { host: 'untrusted.example' })
  assert.equal(rejected.status, 400)
  assert.ok(!rejected.headers['content-security-policy'].includes('untrusted.example'))
  const health = await get('/api/health')
  assert.ok(!health.text.includes(ticket))

  // Real cross-origin browser, even with knowledge of the valid ticket.
  evil = http.createServer((request, response) => { response.setHeader('Content-Type', 'text/html'); response.end('<!doctype html><title>Untrusted test origin</title>') })
  await new Promise((resolve) => evil.listen(0, '127.0.0.1', resolve))
  const other = await context.newPage()
  await other.goto(`http://127.0.0.1:${evil.address().port}`)
  const attack = await other.evaluate(async ({ base, wsURL, ticket }) => {
    const readable = await fetch(base + '/api/mirror/status').then((response) => response.json()).then(() => true).catch(() => false)
    const opened = await new Promise((resolve) => {
      const socket = new WebSocket(wsURL, ['echelon-mirror', 'ticket.' + ticket])
      socket.onopen = () => { socket.close(); resolve(true) }
      socket.onerror = () => resolve(false)
    })
    return { readable, opened }
  }, { base, wsURL, ticket })
  assert.deepEqual(attack, { readable: false, opened: false })
  await other.close()
  assert.equal((await events()).length, 0)
  checks += 3
  console.log('E2E: real cross-origin browser cannot read tickets or open a stream.')
  await page.bringToFront()

  await start(); await live()
  const color = await page.getByTestId('phone-video').evaluate((canvas) => [...canvas.getContext('2d').getImageData(1, 1, 1, 1).data])
  assert.ok(color[2] > 150 && color[0] < 60)
  const starts = (await events()).filter((row) => row.kind === 'capture-start').length
  const second = await page.evaluate(({ wsURL, ticket }) => new Promise((resolve) => {
    const socket = new WebSocket(wsURL, ['echelon-mirror', 'ticket.' + ticket])
    socket.onmessage = ({ data }) => { const value = JSON.parse(data); socket.close(); resolve(value.message) }
  }), { wsURL, ticket })
  assert.ok(second.includes('already open'))
  assert.equal((await events()).filter((row) => row.kind === 'capture-start').length, starts)
  await stop(); checks += 4
  console.log('E2E: production stream decodes video; Stop clears pixels and cleans resources.')

  // Rapid starts/stops exercise cancellation before and after bootstrap.
  for (let i = 0; i < 4; i++) {
    await start()
    await page.getByRole('button', { name: 'Stop mirroring', exact: true }).click()
    await clean()
  }
  checks += 4
  await mode('normal'); await start(); await live()
  await page.getByRole('button', { name: 'Ride monitor', exact: true }).click()
  await clean()
  assert.equal(await page.getByTestId('phone-video').count(), 0)
  await load(); checks++

  await mode('rotate'); await start(); await live()
  await page.waitForFunction(() => { const canvas = document.querySelector('[data-testid="phone-video"]'); return canvas?.width === 48 && canvas?.height === 64 })
  await stop(); checks++

  for (const [value, expected] of [
    ['identity-mismatch', 'Phone identity changed'], ['missing-phone', 'Your selected phone is offline'],
    ['legacy-only', 'Your selected phone is offline'], ['bad-listener', 'ADB must listen only'],
    ['unauthorized', 'not authorized or connected'], ['bad-codec', 'expected video format'],
    ['oversize', 'invalid video packet'], ['truncated-header', 'video connection ended'],
    ['corrupt-after-frame', 'invalid video packet'],
  ]) {
    await mode(value); await start(); await text(expected); await clean()
    assert.equal(await page.getByTestId('phone-video').evaluate((canvas) => canvas.classList.contains('invisible')), true)
    checks++
  }

  for (const value of ['slow-upload', 'slow-start']) {
    const offset = (await events()).length
    await mode(value); await start()
    await until(async () => (await events()).slice(offset).some((entry) => entry.kind === 'adb' && entry.args.includes(value === 'slow-upload' ? 'push' : 'app_process')))
    await page.getByRole('button', { name: 'Stop mirroring', exact: true }).click()
    await clean(); checks++
  }

  await mode('normal')
  const serverFile = process.env.MIRROR_TEST_SERVER
  const original = await fs.readFile(serverFile)
  await fs.writeFile(serverFile, 'tampered synthetic server')
  await load()
  await text('scrcpy installation changed')
  assert.equal(await page.getByRole('button', { name: 'Start mirroring', exact: true }).isDisabled(), true)
  await fs.writeFile(serverFile, original)
  await load(); checks++

  // Transport limit rejects large viewer messages, and controls cannot reach ADB.
  for (const command of ['tap 100 100', 'x'.repeat(2048)]) {
    const close = await page.evaluate(({ wsURL, ticket, command }) => new Promise((resolve) => {
      const socket = new WebSocket(wsURL, ['echelon-mirror', 'ticket.' + ticket])
      socket.onopen = () => socket.send(command)
      socket.onclose = ({ code }) => resolve(code)
    }), { wsURL, ticket, command })
    assert.ok([1000, 1009].includes(close))
    await clean(); checks++
  }

  await start(); await live()
  await page.close()
  await clean(); checks++
  const all = await events()
  assert.ok(all.filter((entry) => entry.kind === 'adb').every((entry) => !entry.args.includes('connect') && !entry.args.includes('input') && !entry.args.includes('tcpip')))
  for (const entry of all.filter((entry) => entry.kind === 'adb' && entry.args.includes('app_process'))) {
    for (const flag of ['audio=false', 'control=false', 'clipboard_autosync=false', 'power_on=false']) assert.ok(entry.args.includes(flag))
  }
  assert.deepEqual(errors, [])
  const diagnostics = (await get('/api/events')).text
  for (const privateValue of [ticket, 'synthetic-phone-serial', 'adb-synthetic-phone']) assert.ok(!diagnostics.includes(privateValue))
  console.log(`Isolated production-pipeline E2E passed: ${checks} scenarios; real Chromium decoding, cross-origin attacks, malformed handshakes, device/TLS selection, rapid stop, rotation, tampering, corrupt/truncated data, transport size limits, browser close, and process/file/tunnel cleanup. No real phone or ADB used.`)
  await context.close()
} finally {
  evil?.close()
  await browser.close()
}
