import { ref, onMounted, onBeforeUnmount } from 'vue'

export function useBridge() {
  const health = ref(null)
  const metrics = ref(null)
  const events = ref([])
  const samples = ref([])
  const online = ref(false)
  const loading = ref(true)
  const error = ref('')
  const lastUpdated = ref(null)
  let timer, controller, inFlight = false, stopped = false

  async function refresh() {
    if (inFlight || stopped) return
    clearTimeout(timer)
    inFlight = true
    controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 5000)
    try {
      const results = await Promise.all(['health', 'metrics', 'events'].map(async (route) => {
        const response = await fetch(`/api/${route}`, { signal: controller.signal, cache: 'no-store' })
        if (!response.ok) throw new Error(`Local API returned HTTP ${response.status}`)
        return response.json()
      }))
      if (stopped) return
      ;[health.value, metrics.value] = results
      events.value = results[2].events
      online.value = true
      error.value = ''
      lastUpdated.value = new Date()
      samples.value = [...samples.value, {
        time: Date.now(), watts: metrics.value.power_available ? metrics.value.estimated_watts : null,
      }].slice(-120)
    } catch (exc) {
      if (stopped) return
      online.value = false
      error.value = exc.name === 'AbortError' ? 'The local server took too long to respond.' : 'Could not reach the local bridge server.'
      samples.value = [...samples.value, { time: Date.now(), watts: null }].slice(-120)
    } finally {
      clearTimeout(timeout)
      inFlight = false
      loading.value = false
      if (!stopped) timer = setTimeout(refresh, 1000)
    }
  }

  onMounted(refresh)
  onBeforeUnmount(() => {
    stopped = true
    clearTimeout(timer)
    controller?.abort()
  })
  return { health, metrics, events, samples, online, loading, error, lastUpdated, refresh }
}
