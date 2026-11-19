import { onBeforeUnmount, ref, watch } from 'vue'

// One short, locally generated tone per 1.5 seconds; never queue future beeps.
export function usePedalSound(active) {
  const unavailable = ref(false)
  let context, repeat, voice, disposed = false

  function stopVoice() {
    if (!voice) return
    const { oscillator, gain } = voice
    voice = null
    oscillator.onended = null
    try { oscillator.stop() } catch { /* It may already have ended. */ }
    oscillator.disconnect()
    gain.disconnect()
  }

  function stop() {
    clearInterval(repeat)
    repeat = undefined
    stopVoice()
  }

  function beep() {
    if (disposed || !active.value || context?.state !== 'running') return stop()
    stopVoice()
    const oscillator = context.createOscillator()
    const gain = context.createGain()
    const start = context.currentTime
    oscillator.type = 'sine'
    oscillator.frequency.value = 740
    gain.gain.setValueAtTime(0, start)
    gain.gain.linearRampToValueAtTime(0.12, start + 0.012)
    gain.gain.setValueAtTime(0.12, start + 0.14)
    gain.gain.linearRampToValueAtTime(0, start + 0.20)
    oscillator.connect(gain)
    gain.connect(context.destination)
    voice = { oscillator, gain }
    oscillator.onended = () => {
      oscillator.disconnect()
      gain.disconnect()
      if (voice?.oscillator === oscillator) voice = null
    }
    oscillator.start(start)
    oscillator.stop(start + 0.21)
  }

  function sync() {
    if (disposed || !active.value || context?.state !== 'running') return stop()
    if (repeat !== undefined) return
    beep()
    repeat = setInterval(beep, 1500)
  }

  // Called directly from a click so browsers can grant audio playback.
  async function arm() {
    if (disposed) return
    try {
      if (!context) {
        const Audio = window.AudioContext || window.webkitAudioContext
        if (!Audio) throw new Error('Audio unavailable')
        context = new Audio()
        context.onstatechange = () => {
          unavailable.value = context.state !== 'running'
          sync()
        }
      }
      await context.resume()
      if (disposed) return
      unavailable.value = context.state !== 'running'
      sync()
    } catch { unavailable.value = true; stop() }
  }

  watch(active, sync, { flush: 'sync' })
  onBeforeUnmount(() => {
    disposed = true
    stop()
    if (context) {
      context.onstatechange = null
      context.close().catch(() => {})
    }
  })
  return { arm, unavailable }
}
