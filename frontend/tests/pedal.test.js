import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import PedalAlert from '../src/PedalAlert.vue'
import { rollingPowerAverage } from '../src/rollingPower'

let wrapper
beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(10000) })
afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.useRealTimers() })

const samples = (watts = 40) => Array.from({ length: 6 }, (_, index) => ({ time: 5000 + index * 1000, watts }))
const metrics = (watts = 40) => ({ connected: true, power_available: true, stale: false, simulated: false, estimated_watts: watts })
const flashing = () => wrapper.find('[data-testid="pedal-alert"]').exists()
async function enable() {
  wrapper = mount(PedalAlert, { props: { online: true, samples: samples(), metrics: metrics() } })
  expect(flashing()).toBe(false)
  await wrapper.get('[role="switch"]').trigger('click')
}

it('uses an actual five-second time average with irregular polling', () => {
  const readings = [10, 20, 30, 40, 50].map((watts, index) => ({ time: index * 1500, watts }))
  // Window 1000..6000: 0.5s at 10W, then 1.5s each at 20W, 30W, 40W.
  expect(rollingPowerAverage(readings, 6000)).toBe(28)
})

it('waits for a full window and rejects missing or stale data', () => {
  expect(rollingPowerAverage(samples().slice(1), 10000)).toBeNull()
  expect(rollingPowerAverage(samples(), 12501)).toBeNull()
  const missing = samples()
  missing[2].watts = null
  expect(rollingPowerAverage(missing, 10000)).toBeNull()
  expect(rollingPowerAverage(samples().filter((_, index) => ![2, 3].includes(index)), 10000)).toBeNull()
})

it('alerts below 45W average and clears immediately at 45W live, before the average recovers', async () => {
  await enable()
  expect(wrapper.get('input').element.value).toBe('45')
  expect(flashing()).toBe(true)
  const recovered = samples()
  recovered[5].watts = 45
  await wrapper.setProps({ metrics: metrics(45), samples: recovered })
  expect(wrapper.get('[data-testid="effort-average"]').text()).toBe('40W')
  expect(wrapper.get('[data-testid="effort-message"]').text()).toBe('Target reached')
  expect(flashing()).toBe(false)
  await wrapper.setProps({ metrics: metrics(44), samples: samples(44) })
  expect(flashing()).toBe(true)
  await wrapper.get('[role="switch"]').trigger('click')
  expect(flashing()).toBe(false)
})

it('does not flash for a momentary dip while the average is still above target', async () => {
  await enable()
  const readings = samples(60)
  readings[5].watts = 30
  await wrapper.setProps({ metrics: metrics(30), samples: readings })
  expect(flashing()).toBe(false)
  expect(wrapper.get('[data-testid="effort-message"]').text()).toBe('Average on target')
})

it('allows changing the target and pauses on an invalid target', async () => {
  await enable()
  expect(flashing()).toBe(true)
  await wrapper.get('input').setValue(40)
  expect(flashing()).toBe(false)
  await wrapper.get('input').setValue('')
  expect(wrapper.get('input').attributes('aria-invalid')).toBe('true')
  expect(flashing()).toBe(false)
  await wrapper.get('input').setValue(45)
  expect(flashing()).toBe(true)
})

it.each([
  { online: false },
  { metrics: { ...metrics(), stale: true } },
  { metrics: { ...metrics(), connected: false } },
  { metrics: { ...metrics(), simulated: true } },
  { metrics: { ...metrics(), power_available: false } },
])('pauses instead of urging harder pedaling when readings are unavailable: %j', async update => {
  await enable()
  await wrapper.setProps(update)
  expect(flashing()).toBe(false)
  expect(wrapper.get('[data-testid="effort-message"]').text()).toBe('Waiting for live power')
})

it('removes the flash if polling stalls even before a request times out', async () => {
  await enable()
  await vi.advanceTimersByTimeAsync(3000)
  expect(flashing()).toBe(false)
})
