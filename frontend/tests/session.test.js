import { afterEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import SessionPanel from '../src/SessionPanel.vue'

let wrapper
afterEach(() => { wrapper?.unmount(); vi.unstubAllGlobals() })
const button = name => wrapper.findAll('button').find(item => item.text() === name)

it('prefills the private default without recording and preserves an edited choice', async () => {
  const defaults = 'C:/Example/my rides.psv'
  const override = 'C:/Example/another ride.psv'
  const fetchMock = vi.fn(async () => ({ ok: true, json: async () => ({ path: defaults }) }))
  vi.stubGlobal('fetch', fetchMock)
  wrapper = mount(SessionPanel, { props: { session: { status: 'idle', revision: 'current' }, online: true, enabled: true, windows: true, refresh: vi.fn() } })
  await button('Start session').trigger('click')
  await flushPromises()
  expect(wrapper.find('input').element.value).toBe(defaults)
  expect(fetchMock).toHaveBeenCalledTimes(1)
  expect(fetchMock.mock.calls[0][0]).toBe('/api/session/default-log')
  expect(fetchMock.mock.calls[0][1].headers['X-Session-Revision']).toBe('current')
  await wrapper.find('input').setValue(override)
  await button('Cancel').trigger('click')
  await button('Start session').trigger('click')
  await flushPromises()
  expect(wrapper.find('input').element.value).toBe(override)
  expect(fetchMock).toHaveBeenCalledTimes(1)
  await wrapper.find('form').trigger('submit')
  await flushPromises()
  expect(fetchMock.mock.calls[1][0]).toBe('/api/session/start')
  expect(fetchMock.mock.calls[1][1].body).toBe(override)
})

it('allows choosing a file when no default is configured', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ path: '' }) })))
  wrapper = mount(SessionPanel, { props: { session: { status: 'idle', revision: 'current' }, online: true, enabled: true } })
  await button('Start session').trigger('click')
  await flushPromises()
  expect(wrapper.find('input').element.value).toBe('')
  expect(button('Start recording').attributes('disabled')).toBeDefined()
  await wrapper.find('input').setValue('/example/rides.psv')
  expect(button('Start recording').attributes('disabled')).toBeUndefined()
})
