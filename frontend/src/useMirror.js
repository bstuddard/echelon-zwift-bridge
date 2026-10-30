import { computed, onMounted, onUnmounted, ref } from 'vue'

export function h264Codec(data) {
  for (let i = 0; i + 7 < data.length; i++) {
    let offset = 0
    if (data[i] === 0 && data[i + 1] === 0 && data[i + 2] === 1) offset = i + 3
    else if (data[i] === 0 && data[i + 1] === 0 && data[i + 2] === 0 && data[i + 3] === 1) offset = i + 4
    if (offset && (data[offset] & 31) === 7) {
      return 'avc1.' + [...data.slice(offset + 1, offset + 4)].map((byte) => byte.toString(16).padStart(2, '0')).join('')
    }
  }
  throw new Error('The phone did not provide a supported video configuration.')
}

export function useMirror(canvas) {
  const phase = ref('idle')
  const message = ref('Capture stays off until you choose Start.')
  const configured = ref(false)
  const checking = ref(true)
  const supported = typeof globalThis.VideoDecoder === 'function' && typeof globalThis.VideoDecoder.isConfigSupported === 'function' && typeof globalThis.EncodedVideoChunk === 'function'
  const active = computed(() => phase.value === 'connecting' || phase.value === 'live')
  let socket, decoder, controller, heartbeat, watchdog
  let generation = 0
  let config, needsKey = true, lastFrame = 0, epoch = 0

  function clearPicture() {
    if (canvas.value) canvas.value.width = canvas.value.width
  }

  function stop(text = 'Mirroring stopped. Your phone continues running normally.', state = 'stopped') {
    generation++
    epoch++
    clearInterval(heartbeat)
    clearInterval(watchdog)
    controller?.abort()
    controller = undefined
    if (socket) { socket.onclose = socket.onerror = socket.onmessage = socket.onopen = null; socket.close(); socket = undefined }
    if (decoder && decoder.state !== 'closed') decoder.close()
    decoder = undefined
    config = undefined
    needsKey = true
    clearPicture()
    phase.value = state
    message.value = text
  }

  async function refresh() {
    controller?.abort()
    controller = new AbortController()
    checking.value = true
    try {
      const response = await fetch('/api/mirror/status', { cache: 'no-store', signal: controller.signal })
      if (!response.ok) throw new Error('Phone mirror status is unavailable. Check the local server.')
      const result = await response.json()
      configured.value = result.configured === true
      if (!configured.value && !active.value) message.value = result.message || 'Select your phone before starting.'
      return result
    } finally { checking.value = false }
  }

  async function start() {
    stop('', 'connecting')
    if (!supported) { stop('This browser cannot decode the phone video. Open the dashboard in a recent Chrome or Chromium browser.', 'unsupported'); return }
    message.value = 'Connecting to your selected phone…'
    const current = generation
    try {
      const details = await refresh()
      if (current !== generation) return
      if (!details.configured || !details.token) throw new Error(details.message || 'Select your phone before starting.')
      const url = new URL('/api/mirror/stream', location.href)
      url.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
      socket = new WebSocket(url, ['echelon-mirror', 'ticket.' + details.token])
      socket.binaryType = 'arraybuffer'
      let queue = Promise.resolve()
      let pending = 0
      socket.onopen = () => {
        if (current !== generation) return
        lastFrame = Date.now()
        heartbeat = setInterval(() => { if (socket?.readyState === WebSocket.OPEN) socket.send('keepalive') }, 10000)
        watchdog = setInterval(() => {
          if (phase.value === 'connecting' && Date.now() - lastFrame > 30000) stop('The phone video took too long to start. Check its connection and retry.', 'error')
          else if (phase.value === 'live' && Date.now() - lastFrame > 5000) stop('Video paused. Check the phone connection and try again.', 'error')
        }, 1000)
      }
      socket.onmessage = (event) => {
        if (current !== generation) return
        if (++pending > 20) { stop('Video is arriving faster than this browser can display it. Stop other busy apps and retry.', 'error'); return }
        queue = queue.then(async () => {
          if (current !== generation) return
          if (typeof event.data === 'string') {
            const data = JSON.parse(event.data)
            if (data.type === 'error') throw new Error(data.message || 'Phone mirroring ended.')
            return
          }
          const data = new Uint8Array(event.data)
          if (data.length < 10 || data.length > 4194313) throw new Error('The video stream was interrupted.')
          const kind = data[0]
          const payload = data.subarray(9)
          if (kind === 1) {
            config = new Uint8Array(payload)
            needsKey = true
            const options = { codec: h264Codec(config), optimizeForLatency: true }
            const support = await VideoDecoder.isConfigSupported(options)
            if (current !== generation) return
            if (!support.supported) throw new Error('This browser cannot decode the phone’s video. Try Chrome or Chromium.')
            if (decoder && decoder.state !== 'closed') decoder.close()
            const ownEpoch = ++epoch
            decoder = new VideoDecoder({
              output(frame) {
                try {
                  if (current !== generation || ownEpoch !== epoch || !canvas.value) return
                  if (frame.displayWidth > 4096 || frame.displayHeight > 4096) { stop('The video dimensions are unsupported.', 'error'); return }
                  const element = canvas.value
                  if (element.width !== frame.displayWidth || element.height !== frame.displayHeight) {
                    element.width = frame.displayWidth
                    element.height = frame.displayHeight
                  }
                  const context = element.getContext('2d', { alpha: false })
                  if (!context) throw new Error('Display unavailable')
                  context.drawImage(frame, 0, 0)
                  lastFrame = Date.now()
                  phase.value = 'live'
                  message.value = 'Live from your selected phone. Use the phone to control Zwift.'
                } catch {
                  if (current === generation) stop('The browser could not display the phone video. Mirroring was stopped.', 'error')
                } finally { frame.close() }
              },
              error() { if (current === generation && ownEpoch === epoch) stop('Video decoding stopped. Check the phone and try again.', 'error') },
            })
            decoder.configure(options)
            return
          }
          if (![2, 3].includes(kind) || !decoder || decoder.state !== 'configured' || !config) return
          if (decoder.decodeQueueSize > 6) needsKey = true
          if (needsKey && kind !== 2) return
          let chunk = payload
          if (kind === 2) {
            chunk = new Uint8Array(config.length + payload.length)
            chunk.set(config)
            chunk.set(payload, config.length)
            if (needsKey) {
              decoder.reset()
              decoder.configure({ codec: h264Codec(config), optimizeForLatency: true })
            }
            needsKey = false
          }
          const timestamp = Number(new DataView(event.data).getBigUint64(1))
          if (!Number.isSafeInteger(timestamp)) throw new Error('The video stream was interrupted.')
          decoder.decode(new EncodedVideoChunk({ type: kind === 2 ? 'key' : 'delta', timestamp, data: chunk }))
        }).catch((error) => { if (current === generation) stop(error.message || 'Phone mirroring ended.', 'error') })
          .finally(() => { pending-- })
      }
      socket.onerror = () => { if (current === generation) stop('Could not open the local phone stream. Check the server and retry.', 'error') }
      socket.onclose = () => { if (current === generation) stop('Phone disconnected. Check its connection, then choose Start again.') }
    } catch (error) {
      if (current === generation && error.name !== 'AbortError') stop(error.message || 'Phone mirroring could not start.', 'error')
    }
  }

  const visibility = () => { if (document.hidden && active.value) stop('Mirroring stopped while this page was hidden. Choose Start to resume.') }
  onMounted(() => {
    refresh().catch(() => { if (phase.value === 'idle') message.value = 'Phone mirror status is unavailable. Check the local server.' })
    document.addEventListener('visibilitychange', visibility)
  })
  onUnmounted(() => { stop(); document.removeEventListener('visibilitychange', visibility) })
  return { phase, message, configured, checking, supported, active, start, stop, refresh }
}
