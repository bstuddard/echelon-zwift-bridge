<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  session: Object,
  online: Boolean,
  enabled: Boolean,
  windows: Boolean,
  refresh: Function,
})
const choosing = ref(false)
const path = ref('')
const busy = ref(false)
const error = ref('')
const active = computed(() => props.session?.status === 'active')
const hasStats = computed(() => props.session?.elapsed_s != null)
const elapsed = computed(() => {
  const seconds = props.session?.elapsed_s ?? 0
  const pad = value => String(value).padStart(2, '0')
  return [Math.floor(seconds / 3600), Math.floor(seconds / 60) % 60, seconds % 60].map(pad).join(':')
})

watch(active, value => { if (value) choosing.value = false })
async function action(name) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    const response = await fetch('/api/session/' + name, {
      method: 'POST',
      headers: { 'X-Session-Revision': props.session.revision, 'Content-Type': 'text/plain;charset=UTF-8' },
      body: name === 'start' ? path.value : undefined,
    })
    const result = await response.json()
    if (!response.ok) throw new Error(result.detail || 'Session request failed.')
    if (name === 'pick-log') {
      if (result.path) path.value = result.path
    } else {
      choosing.value = false
      await props.refresh()
    }
  } catch (exc) {
    error.value = exc.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="panel mt-5" aria-labelledby="session-heading">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 id="session-heading" class="section-title">{{ active ? 'Session in progress' : hasStats ? 'Session summary' : 'Ride session' }}</h2>
        <p class="section-subtitle">{{ active ? 'Recording to your selected history file.' : 'Track time, distance, average power, and estimated FTP.' }}</p>
      </div>
      <button v-if="active" class="btn btn-dark" :disabled="busy || !online" @click="action('finish')">Finish session</button>
      <button v-else-if="!choosing" class="btn btn-dark" :disabled="!online || !enabled || !session" @click="choosing = true; error = ''">Start session</button>
    </div>
    <form v-if="choosing && !active" class="mt-4" @submit.prevent="action('start')">
      <label for="session-file" class="text-xs font-semibold">Ride history file (.psv)</label>
      <div class="mt-1 flex flex-wrap gap-2">
        <input id="session-file" v-model="path" required spellcheck="false" autocomplete="off"
          class="min-w-0 flex-1 rounded-lg border border-stone-300 px-3 py-2 text-sm"
          :placeholder="windows ? 'Full Windows file path' : 'Full Linux file path'" />
        <button type="button" class="btn btn-white" :disabled="busy" @click="action('pick-log')">Browse…</button>
      </div>
      <p class="section-subtitle">Choose a new file or append this ride to an existing Echelon log.</p>
      <div class="mt-3 flex gap-2">
        <button class="btn btn-dark" :disabled="busy || !path || !online">Start recording</button>
        <button type="button" class="btn btn-white" :disabled="busy" @click="choosing = false; error = ''">Cancel</button>
      </div>
    </form>
    <p v-if="error || session?.error" role="alert" class="mt-3 text-sm text-red-800">{{ error || session.error }}</p>
    <dl v-if="hasStats" class="mt-5 grid grid-cols-2 gap-4 border-t border-stone-100 pt-4 md:grid-cols-4">
      <div><dt class="metric-label">Elapsed time</dt><dd class="mt-1 text-xl font-semibold tabular-nums">{{ elapsed }}</dd></div>
      <div><dt class="metric-label">Estimated distance</dt><dd class="mt-1 text-xl font-semibold tabular-nums">{{ (session.distance_km / 1.609344).toFixed(2) }} mi</dd><p class="section-subtitle">{{ session.distance_km.toFixed(2) }} km · from cadence</p></div>
      <div><dt class="metric-label">Average power</dt><dd class="mt-1 text-xl font-semibold tabular-nums">{{ session.avg_watts ?? '—' }} W</dd><p class="section-subtitle">Includes zero-power readings</p></div>
      <div><dt class="metric-label">Estimated FTP</dt><dd class="mt-1 text-xl font-semibold tabular-nums">{{ session.ftp_watts ?? '—' }} W</dd>
        <p class="section-subtitle">{{ session.ftp_watts == null ? Math.min(20, Math.floor(session.continuous_power_s / 60)) + ' / 20 min of continuous power' : '95% of best 20-minute power' }}</p></div>
    </dl>
  </section>
</template>
