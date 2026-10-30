import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import MirrorPage from '../src/MirrorPage.vue'
import { h264Codec } from '../src/useMirror'

let wrapper, sockets, decoders, draw
class Socket {
  static OPEN = 1
  constructor(url, protocols) { this.url = url; this.protocols = protocols; this.readyState = 1; this.close = vi.fn(); this.send = vi.fn(); sockets.push(this) }
}
class Decoder {
  static isConfigSupported = async (options) => ({ supported: options.codec === 'avc1.42001e' })
  constructor(callbacks) { this.callbacks = callbacks; this.state = 'unconfigured'; this.decodeQueueSize = 0; this.chunks = []; decoders.push(this) }
  configure() { this.state = 'configured' }
  reset() { this.state = 'unconfigured' }
  close() { this.state = 'closed' }
  decode(chunk) { this.chunks.push(chunk) }
}
const config = new Uint8Array([0, 0, 0, 1, 0x67, 0x42, 0, 0x1e, 0, 0, 0, 1, 0x68, 0])
function packet(kind, data) {
  const bytes = new Uint8Array(data.length + 9)
  bytes[0] = kind
  new DataView(bytes.buffer).setBigUint64(1, 123n)
  bytes.set(data, 9)
  return bytes.buffer
}
beforeEach(() => {
  sockets = []; decoders = []
  draw = vi.fn()
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ drawImage: draw })
  vi.stubGlobal('WebSocket', Socket)
  vi.stubGlobal('VideoDecoder', Decoder)
  vi.stubGlobal('EncodedVideoChunk', class { constructor(options) { Object.assign(this, options) } })
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ configured: true, token: 'test-session-ticket' }) })))
})
afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.restoreAllMocks(); vi.unstubAllGlobals() })

describe('phone mirror', () => {
  it('stays private until Start and authenticates without putting the ticket in the URL', async () => {
    wrapper = mount(MirrorPage)
    await flushPromises()
    expect(sockets).toHaveLength(0)
    expect(wrapper.text()).toContain('Your phone stays private until you start')
    await wrapper.findAll('button').find((button) => button.text() === 'Start mirroring').trigger('click')
    await flushPromises()
    expect(sockets).toHaveLength(1)
    expect(new URL(sockets[0].url).pathname).toBe('/api/mirror/stream')
    expect(new URL(sockets[0].url).search).toBe('')
    expect(sockets[0].protocols).toEqual(['echelon-mirror', 'ticket.test-session-ticket'])
    wrapper.unmount(); wrapper = undefined
    expect(sockets[0].close).toHaveBeenCalledOnce()
  })

  it('combines codec configuration with a key frame, displays video, and closes the decoder when stopped', async () => {
    wrapper = mount(MirrorPage)
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === 'Start mirroring').trigger('click')
    await flushPromises()
    sockets[0].onmessage({ data: packet(1, config) })
    sockets[0].onmessage({ data: packet(2, new Uint8Array([0, 0, 1, 0x65, 1])) })
    await flushPromises()
    expect(decoders[0].chunks[0].type).toBe('key')
    expect(decoders[0].chunks[0].data.slice(0, config.length)).toEqual(config)
    const frame = { displayWidth: 1280, displayHeight: 720, close: vi.fn() }
    decoders[0].callbacks.output(frame)
    await flushPromises()
    expect(draw).toHaveBeenCalledOnce()
    expect(frame.close).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('Live · view only')
    await wrapper.findAll('button').find((button) => button.text() === 'Stop mirroring').trigger('click')
    expect(decoders[0].state).toBe('closed')
    expect(wrapper.find('canvas').classes()).toContain('invisible')
    decoders[0].callbacks.output({ ...frame, close: vi.fn() })
    expect(draw).toHaveBeenCalledOnce()
  })

  it('stops capture when the browser page is hidden', async () => {
    wrapper = mount(MirrorPage)
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === 'Start mirroring').trigger('click')
    await flushPromises()
    vi.spyOn(document, 'hidden', 'get').mockReturnValue(true)
    document.dispatchEvent(new Event('visibilitychange'))
    await flushPromises()
    expect(sockets[0].close).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('stopped while this page was hidden')
  })

  it('explains browsers without video support and never attempts capture', async () => {
    vi.stubGlobal('VideoDecoder', undefined)
    wrapper = mount(MirrorPage)
    await flushPromises()
    const start = wrapper.findAll('button').find((button) => button.text() === 'Start mirroring')
    expect(start.element.disabled).toBe(true)
    expect(wrapper.text()).toContain('Chrome or Chromium')
    expect(sockets).toHaveLength(0)
  })

  it('reports selected-phone failures without retrying capture automatically', async () => {
    wrapper = mount(MirrorPage)
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === 'Start mirroring').trigger('click')
    await flushPromises()
    sockets[0].onmessage({ data: JSON.stringify({ type: 'error', message: 'Your selected phone is offline.' }) })
    await flushPromises()
    expect(wrapper.text()).toContain('Your selected phone is offline.')
    expect(sockets).toHaveLength(1)
    expect(sockets[0].close).toHaveBeenCalledOnce()
  })

  it('stops capture immediately when the drawing context is lost', async () => {
    wrapper = mount(MirrorPage)
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === 'Start mirroring').trigger('click')
    await flushPromises()
    sockets[0].onmessage({ data: packet(1, config) })
    await flushPromises()
    vi.mocked(HTMLCanvasElement.prototype.getContext).mockReturnValue(null)
    const frame = { displayWidth: 1280, displayHeight: 720, close: vi.fn() }
    expect(() => decoders[0].callbacks.output(frame)).not.toThrow()
    await flushPromises()
    expect(frame.close).toHaveBeenCalledOnce()
    expect(sockets[0].close).toHaveBeenCalledOnce()
    expect(decoders[0].state).toBe('closed')
    expect(wrapper.text()).toContain('browser could not display')
  })

  it('does not open a socket if Stop is chosen while status is still loading', async () => {
    wrapper = mount(MirrorPage)
    await flushPromises()
    let resolveStatus
    vi.mocked(fetch).mockImplementationOnce(() => new Promise((resolve) => { resolveStatus = resolve }))
    await wrapper.findAll('button').find((button) => button.text() === 'Start mirroring').trigger('click')
    await wrapper.findAll('button').find((button) => button.text() === 'Stop mirroring').trigger('click')
    resolveStatus({ ok: true, json: async () => ({ configured: true, token: 'late-test-ticket' }) })
    await flushPromises()
    expect(sockets).toHaveLength(0)
    expect(wrapper.text()).toContain('Mirroring stopped')
  })

  it('closes a stream that never produces its first frame', async () => {
    const timers = []
    vi.spyOn(globalThis, 'setInterval').mockImplementation((callback) => { timers.push(callback); return 123 })
    vi.spyOn(Date, 'now').mockReturnValue(1000)
    wrapper = mount(MirrorPage)
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === 'Start mirroring').trigger('click')
    await flushPromises()
    sockets[0].onopen()
    vi.mocked(Date.now).mockReturnValue(32000)
    timers[1]()
    await flushPromises()
    expect(sockets[0].close).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('took too long to start')
  })

  it('ignores late packets and decoder output from a previous session', async () => {
    wrapper = mount(MirrorPage)
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === 'Start mirroring').trigger('click')
    await flushPromises()
    const staleMessage = sockets[0].onmessage
    sockets[0].onmessage({ data: packet(1, config) })
    await flushPromises()
    const staleOutput = decoders[0].callbacks.output
    await wrapper.findAll('button').find((button) => button.text() === 'Stop mirroring').trigger('click')
    await wrapper.findAll('button').find((button) => button.text() === 'Start mirroring').trigger('click')
    await flushPromises()
    for (let index = 0; index < 30; index++) staleMessage({ data: packet(1, config) })
    const frame = { displayWidth: 1280, displayHeight: 720, close: vi.fn() }
    staleOutput(frame)
    await flushPromises()
    expect(sockets[1].close).not.toHaveBeenCalled()
    expect(draw).not.toHaveBeenCalled()
    expect(frame.close).toHaveBeenCalledOnce()
  })
})

it('rejects codec metadata without an H.264 parameter set', () => {
  expect(() => h264Codec(new Uint8Array(20))).toThrow('supported video configuration')
})
