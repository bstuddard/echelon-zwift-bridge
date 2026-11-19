import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import PedalAlert from '../src/PedalAlert.vue'
import FocusMode from '../src/FocusMode.vue'

let wrapper
beforeEach(() => {
  vi.useFakeTimers(); vi.setSystemTime(10000)
  Object.defineProperty(document, 'fullscreenElement', { configurable: true, get: () => null })
  HTMLElement.prototype.requestFullscreen = vi.fn().mockResolvedValue(undefined)
})
afterEach(() => {
  wrapper?.unmount(); wrapper = undefined; document.body.innerHTML = ''
  delete HTMLElement.prototype.requestFullscreen
  delete document.fullscreenElement
  vi.useRealTimers()
})
const readings = watts => Array.from({ length: 6 }, (_, i) => ({ time: 5000 + i * 1000, watts }))
const metrics = watts => ({ connected: true, power_available: true, estimated_watts: watts })

async function open() {
  await wrapper.findAll('button').find(button => button.text() === 'Focus mode').trigger('click')
  return wrapper.getComponent(FocusMode)
}

it('shows the same five-second average quietly with the reminder off and restores focus on exit', async () => {
  document.body.innerHTML = '<div id="app"><button id="previous">Before</button></div>'
  const previous = document.getElementById('previous')
  previous.focus()
  wrapper = mount(PedalAlert, { props: { online: true, samples: readings(40), metrics: metrics(40) }, attachTo: '#app' })
  const focus = await open()
  expect(focus.get('[data-testid="focus-average"]').text()).toBe('40 W')
  expect(focus.classes()).not.toContain('is-warning')
  expect(document.getElementById('app').inert).toBe(true)
  expect(document.body.style.overflow).toBe('hidden')
  await focus.trigger('keydown', { key: 'Escape' })
  expect(wrapper.findComponent(FocusMode).exists()).toBe(false)
  expect(document.getElementById('app').inert).toBeFalsy()
  expect(document.body.style.overflow).toBe('')
  expect(document.activeElement).toBe(previous)
})

it('uses the configured target, clears red immediately at live target, and preserves settings when exiting', async () => {
  wrapper = mount(PedalAlert, { props: { online: true, samples: readings(40), metrics: metrics(40) } })
  await wrapper.get('[role="switch"]').trigger('click')
  await wrapper.get('input[type="number"]').setValue(50)
  const focus = await open()
  expect(focus.classes()).toContain('is-warning')
  expect(focus.text()).toContain('Reach 50 W to clear')
  const recovered = readings(40)
  recovered[5].watts = 50
  await wrapper.setProps({ metrics: metrics(50), samples: recovered })
  expect(focus.classes()).not.toContain('is-warning')
  expect(focus.get('[data-testid="focus-average"]').text()).toBe('40 W')
  await focus.findAll('button').find(button => button.text() === 'Exit focus').trigger('click')
  expect(wrapper.get('input[type="number"]').element.value).toBe('50')
  expect(wrapper.get('[role="switch"]').attributes('aria-checked')).toBe('true')
})

it('pauses focus alerts and blanks the average when fresh power stops', async () => {
  wrapper = mount(PedalAlert, { props: { online: true, samples: readings(40), metrics: metrics(40) } })
  await wrapper.get('[role="switch"]').trigger('click')
  const focus = await open()
  expect(focus.classes()).toContain('is-warning')
  await vi.advanceTimersByTimeAsync(3000)
  expect(focus.classes()).not.toContain('is-warning')
  expect(focus.get('[data-testid="focus-average"]').text()).toBe('— W')
  await wrapper.setProps({ visible: false })
  expect(wrapper.findComponent(FocusMode).exists()).toBe(false)
})

it('falls back when fullscreen is denied and reveals controls using the mouse or keyboard', async () => {
  vi.spyOn(HTMLElement.prototype, 'requestFullscreen').mockRejectedValue(new Error('Denied'))
  wrapper = mount(FocusMode, { props: { average: 60 } })
  await flushPromises()
  await vi.advanceTimersByTimeAsync(2300)
  expect(wrapper.classes()).toContain('controls-hidden')
  await wrapper.trigger('pointermove')
  expect(wrapper.classes()).not.toContain('controls-hidden')
  await wrapper.trigger('keydown', { key: 'Tab' })
  expect(wrapper.findAll('button').map(button => button.text())).toEqual(['Fullscreen', 'Exit focus'])
  await wrapper.trigger('keydown', { key: 'Escape' })
  expect(wrapper.emitted('close')).toHaveLength(1)
})

it('closes focus when native fullscreen is exited', async () => {
  wrapper = mount(FocusMode, { props: { average: 60 } })
  vi.spyOn(document, 'fullscreenElement', 'get').mockReturnValue(wrapper.element)
  document.dispatchEvent(new Event('fullscreenchange'))
  await flushPromises()
  vi.spyOn(document, 'fullscreenElement', 'get').mockReturnValue(null)
  document.dispatchEvent(new Event('fullscreenchange'))
  expect(wrapper.emitted('close')).toHaveLength(1)
})
