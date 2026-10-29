import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import App from '../src/App.vue'
import PowerChart from '../src/PowerChart.vue'

let wrapper
const peripheral = { name: 'EchelonPython', gatt_started: true, advertisement_registered: true, adapter_advertising_active: true, client_subscribed: false, updates: 5 }
function fixtures({ available = false, simulated = false, auth = false, subscribed = false } = {}) {
  const sensor = { ...peripheral, client_subscribed: subscribed, name: simulated ? 'EchelonSIM-TEST' : 'EchelonPython' }
  return {
    '/api/health': { status: available ? 'ready' : 'waiting', reader_enabled: true, simulated, ble_power_advertising_enabled: true, adapter: 'default', power_adapter: 'hci0', failed_tasks: {}, peripheral: sensor },
    '/api/metrics': { connected: available, initialized: available, power_available: available, stale: !available, cadence_rpm: available ? 90 : 0, estimated_watts: available ? 165 : 0, resistance_level: available ? 20 : null, auth_required: auth, reader_status: available ? 'reading' : 'scanning', last_cadence_age_seconds: available ? 0.2 : null, packets_seen: 4 },
    '/api/events': { events: [{ timestamp: '2026-10-28T00:00:00Z', level: 'info', message: 'event=power_gatt_registered name=EchelonPython' }] },
  }
}
function serve(data) {
  const mock = vi.fn(async (url) => ({ ok: true, json: async () => data[url] }))
  vi.stubGlobal('fetch', mock)
  return mock
}
async function start(options) {
  serve(fixtures(options))
  wrapper = mount(App)
  await flushPromises()
}
afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.unstubAllGlobals() })

describe('live admin state', () => {
  it('explains the absent bike without inventing readings or pairing', async () => {
    await start()
    expect(wrapper.text()).toContain('Wake your bike to begin')
    expect(wrapper.text()).toContain('Advertising')
    expect(wrapper.text()).toContain('Searching')
    expect(wrapper.find('[data-testid="power-value"]').text()).toContain('0')
    expect(wrapper.text()).toContain('Waiting for live readings')
  })

  it('displays real values then clears current values when the server becomes unreachable', async () => {
    await start({ available: true })
    expect(wrapper.find('[data-testid="power-value"]').text()).toContain('165')
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('connection refused') }))
    await wrapper.find('[aria-label="Refresh bridge status"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Local server is unavailable')
    expect(wrapper.find('[data-testid="power-value"]').text()).toContain('—')
    expect(wrapper.find('[data-testid="power-value"]').text()).not.toContain('165')
    expect(wrapper.text()).toContain('Unknown')
  })

  it('labels simulation in a prominent alert and uses its distinct sensor name', async () => {
    await start({ available: true, simulated: true })
    expect(wrapper.find('[role="alert"]').text()).toContain('SIMULATION')
    expect(wrapper.text()).toContain('EchelonSIM-TEST')
    expect(wrapper.text()).toContain('These are not live bike readings')
  })

  it('explains firmware authentication while showing zero output', async () => {
    await start({ auth: true })
    expect(wrapper.text()).toContain('This bike needs firmware authentication')
    expect(wrapper.find('[data-testid="power-value"]').text()).toContain('0')
  })

  it('distinguishes a subscriber from Zwift pairing and exposes redacted process events', async () => {
    await start({ available: true, subscribed: true })
    expect(wrapper.text()).toContain('Confirm the sensor is paired in Zwift')
    const diagnostics = wrapper.findAll('nav button').find((button) => button.text() === 'Diagnostics')
    await diagnostics.trigger('click')
    expect(wrapper.text()).toContain('Yes · app unverified')
    expect(wrapper.text()).toContain('event=power_gatt_registered')
    expect(wrapper.text()).toContain('Recent bridge events')
    expect(wrapper.find('details').text()).toContain('Inspect API response')
  })

  it('stops polling when the admin is closed', async () => {
    await start()
    const fetchMock = vi.mocked(fetch)
    expect(fetchMock).toHaveBeenCalledTimes(3)
    const signal = fetchMock.mock.calls[0][1].signal
    wrapper.unmount()
    wrapper = undefined
    expect(signal.aborted).toBe(true)
  })
})

it('leaves gaps in the power graph when telemetry is unavailable', () => {
  wrapper = mount(PowerChart, { props: { samples: [{ watts: 100 }, { watts: 120 }, { watts: null }, { watts: 90 }, { watts: 80 }] } })
  expect(wrapper.findAll('path')).toHaveLength(2)
  expect(wrapper.find('[role="img"]').attributes('aria-label')).toContain('Gaps mean unavailable data')
})

it('provides local license copies and makes the estimate policy explicit', async () => {
  await start()
  await wrapper.findAll('nav button').find((button) => button.text() === 'About').trigger('click')
  expect(wrapper.text()).toContain('GPL-3.0-only')
  expect(wrapper.text()).toContain('without warranty')
  expect(wrapper.text()).toContain('no gain multiplier')
  expect(wrapper.find('a[href="/legal/LICENSE.txt"]').exists()).toBe(true)
  expect(wrapper.find('a[href="/legal/THIRD_PARTY_NOTICES.txt"]').exists()).toBe(true)
})
