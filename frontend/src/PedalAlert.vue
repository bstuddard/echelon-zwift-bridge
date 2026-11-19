<script setup>
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { rollingPowerAverage } from './rollingPower'
import FocusMode from './FocusMode.vue'
import { usePedalSound } from './usePedalSound'

const props = defineProps({ metrics: Object, online: Boolean, samples: { type: Array, default: () => [] }, visible: { type: Boolean, default: true } })
const enabled = ref(false)
const target = ref(45)
const focusOpen = ref(false)
const soundEnabled = ref(true)
const now = ref(Date.now())
let timer
onMounted(() => { timer = setInterval(() => { now.value = Date.now() }, 500) })
onBeforeUnmount(() => clearInterval(timer))

const validTarget = computed(() => Number.isInteger(target.value) && target.value >= 1 && target.value <= 2000)
const fresh = computed(() => props.online && props.metrics?.connected && props.metrics?.power_available &&
  !props.metrics?.stale && !props.metrics?.simulated && !props.metrics?.auth_required &&
  Number.isFinite(props.metrics?.estimated_watts) && props.metrics.estimated_watts >= 0 &&
  props.samples.length && Date.now() - props.samples.at(-1).time <= 2500 &&
  now.value - props.samples.at(-1).time <= 2500)
const live = computed(() => fresh.value ? props.metrics.estimated_watts : null)
const average = computed(() => fresh.value ? rollingPowerAverage(props.samples, Math.max(now.value, Date.now())) : null)
const warning = computed(() => enabled.value && validTarget.value && average.value !== null &&
  average.value < target.value && live.value < target.value)
const { arm, unavailable: soundUnavailable } = usePedalSound(computed(() => warning.value && soundEnabled.value && props.visible))
function toggleReminder() {
  enabled.value = !enabled.value
  if (enabled.value && soundEnabled.value) arm()
}
function openFocus() {
  if (enabled.value && soundEnabled.value) arm()
  focusOpen.value = true
}
watch(() => props.visible, visible => { if (!visible) focusOpen.value = false })
const reached = computed(() => enabled.value && validTarget.value && live.value !== null && live.value >= target.value)
const progress = computed(() => average.value !== null && validTarget.value ? Math.min(1, average.value / target.value) : 0)
const ringLength = 2 * Math.PI * 51
const heading = computed(() => !validTarget.value ? 'Set your watt target' : !fresh.value ? 'Waiting for live power' :
  warning.value ? 'Pedal harder' : reached.value ? 'Target reached' : average.value === null ? 'Measuring your effort' : 'Average on target')
const detail = computed(() => !validTarget.value ? 'Enter a whole number from 1 to 2,000 W.' : !fresh.value ? 'The reminder pauses until fresh bike readings return.' :
  warning.value ? `Reach ${target.value} W live to clear this alert.` : reached.value ? 'Live power is at your target. The alert is clear.' :
  average.value === null ? 'Gathering five seconds of fresh power readings.' : 'Your five-second average is above the alert threshold.')
</script>

<template>
  <section class="effort-card mt-5" :class="{ 'is-enabled': enabled, 'is-warning': warning, 'is-reached': reached }" aria-labelledby="effort-heading">
    <div class="effort-controls">
      <div class="flex min-w-0 items-center gap-3">
        <span class="effort-symbol" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="m13 2-8 12h6l-1 8 9-12h-6l1-8Z" stroke-linejoin="round"/></svg></span>
        <div><h2 id="effort-heading" class="section-title">Pedal reminder</h2><p class="effort-caption">A nudge to hold your power.</p></div>
      </div>
      <div class="flex flex-wrap items-center gap-4">
        <label v-if="enabled" class="effort-target" for="effort-target">Target power
          <span class="effort-input"><input id="effort-target" v-model.number="target" type="number" min="1" max="2000" step="1"
            :aria-invalid="!validTarget" aria-describedby="effort-help" /><span aria-hidden="true">W</span></span>
        </label>
        <label v-if="enabled" class="effort-sound"><input v-model="soundEnabled" type="checkbox" @change="soundEnabled && arm()" /> Beep</label>
        <button type="button" role="switch" :aria-checked="enabled" aria-label="Pedal harder reminder"
          class="effort-switch" @click="toggleReminder"><span aria-hidden="true" class="effort-switch-track"><span /></span>{{ enabled ? 'On' : 'Off' }}</button>
        <button type="button" class="btn btn-white" @click="openFocus">Focus mode</button>
      </div>
    </div>

    <div v-if="enabled" class="effort-body">
      <div class="effort-dial" aria-label="Five-second average power">
        <svg viewBox="0 0 120 120" aria-hidden="true"><circle class="effort-ring-track" cx="60" cy="60" r="51" />
          <circle class="effort-ring-value" cx="60" cy="60" r="51" :stroke-dasharray="`${progress * ringLength} ${ringLength}`" /></svg>
        <div class="effort-dial-value"><strong data-testid="effort-average">{{ average === null ? '—' : Math.round(average) }}<small>W</small></strong><span>5-second average</span></div>
      </div>
      <div class="min-w-0 flex-1">
        <p class="effort-eyebrow"><span class="effort-status-dot" aria-hidden="true" />{{ warning ? 'Below your target' : reached ? 'Back in rhythm' : 'Power check' }}</p>
        <h3 class="effort-message" :class="{ 'effort-message-warning': warning }" aria-live="polite" aria-atomic="true" data-testid="effort-message">{{ heading }}</h3>
        <p class="effort-detail">{{ detail }}</p>
        <div class="effort-readings"><span>Live <strong data-testid="effort-live">{{ live === null ? '—' : live }} W</strong></span><span>Target <strong>{{ validTarget ? target : '—' }} W</strong></span></div>
      </div>
    </div>
    <p v-if="enabled" id="effort-help" class="effort-help">Five-second average to alert. Live power at target to clear. Keep this dashboard visible.</p>
    <p v-if="enabled && soundEnabled && soundUnavailable" class="effort-help" role="status">Sound is unavailable. Allow audio in your browser, then toggle Beep off and on.</p>
    <div v-if="warning && !focusOpen" class="effort-screen-cue" aria-hidden="true" data-testid="pedal-alert" />
    <Teleport to="body">
      <FocusMode v-if="focusOpen" :average="average" :warning="warning" :target="validTarget ? target : null" @close="focusOpen = false" />
    </Teleport>
  </section>
</template>
