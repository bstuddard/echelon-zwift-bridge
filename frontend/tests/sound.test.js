import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import PedalAlert from '../src/PedalAlert.vue'

let wrapper, contexts, oscillators
beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(10000)
  contexts = []
  oscillators = []
  vi.stubGlobal('AudioContext', class {
    state = 'suspended'
    currentTime = 0
    destination = {}
    constructor() { contexts.push(this) }
    resume = vi.fn(async () => { this.state = 'running' })
    close = vi.fn(async () => { this.state = 'closed' })
    createGain = () => ({ gain: { setValueAtTime() {}, linearRampToValueAtTime() {} }, connect() {}, disconnect: vi.fn() })
    createOscillator = () => {
      const oscillator = { frequency: {}, connect() {}, disconnect: vi.fn(), start: vi.fn(), stop: vi.fn() }
      oscillators.push(oscillator)
      return oscillator
    }
  })
})
afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.useRealTimers() })
function props(watts = 40) {
  return { online: true, metrics: { connected: true, power_available: true, estimated_watts: watts },
    samples: Array.from({ length: 6 }, (_, i) => ({ time: Date.now() - 5000 + i * 1000, watts })) }
}
async function enable() {
  wrapper = mount(PedalAlert, { props: props() })
  expect(contexts).toHaveLength(0)
  await wrapper.get('[role="switch"]').trigger('click')
  await flushPromises()
}

it('arms sound only on a user toggle, repeats below target, and cancels the current tone immediately at live target', async () => {
  await enable()
  expect(contexts).toHaveLength(1)
  expect(oscillators).toHaveLength(1)
  await vi.advanceTimersByTimeAsync(1500)
  expect(oscillators).toHaveLength(2)
  const current = oscillators.at(-1)
  const recovered = props()
  recovered.metrics.estimated_watts = 45
  recovered.samples.at(-1).watts = 45
  await wrapper.setProps(recovered)
  expect(wrapper.get('[data-testid="effort-average"]').text()).toBe('40W')
  expect(current.stop).toHaveBeenLastCalledWith()
  expect(current.disconnect).toHaveBeenCalled()
  await vi.advanceTimersByTimeAsync(2000)
  expect(oscillators).toHaveLength(2)
})

it('keeps the visual reminder while muted and rearms from the checkbox', async () => {
  await enable()
  await wrapper.get('input[type="checkbox"]').setValue(false)
  expect(wrapper.find('[data-testid="pedal-alert"]').exists()).toBe(true)
  await vi.advanceTimersByTimeAsync(1500)
  expect(oscillators).toHaveLength(1)
  await wrapper.get('input[type="checkbox"]').setValue(true)
  await flushPromises()
  expect(oscillators).toHaveLength(2)
})

it.each(['stale', 'offline', 'disabled', 'invalid target', 'other page', 'unmount'])('stops beeping for %s', async reason => {
  await enable()
  const current = oscillators.at(-1)
  if (reason === 'stale') await vi.advanceTimersByTimeAsync(3000)
  if (reason === 'offline') await wrapper.setProps({ online: false })
  if (reason === 'disabled') await wrapper.get('[role="switch"]').trigger('click')
  if (reason === 'invalid target') await wrapper.get('input[type="number"]').setValue('')
  if (reason === 'other page') await wrapper.setProps({ visible: false })
  if (reason === 'unmount') { wrapper.unmount(); wrapper = undefined; expect(contexts[0].close).toHaveBeenCalled() }
  const count = oscillators.length
  expect(current.stop).toHaveBeenLastCalledWith()
  await vi.advanceTimersByTimeAsync(5000)
  expect(oscillators).toHaveLength(count)
})

it('retains the visual alert and explains blocked audio', async () => {
  wrapper = mount(PedalAlert, { props: props() })
  vi.stubGlobal('AudioContext', class { resume = () => Promise.reject(new Error('Denied')); close = () => Promise.resolve() })
  await wrapper.get('[role="switch"]').trigger('click')
  await flushPromises()
  expect(wrapper.find('[data-testid="pedal-alert"]').exists()).toBe(true)
  expect(wrapper.get('[role="status"]').text()).toContain('Sound is unavailable')
})
