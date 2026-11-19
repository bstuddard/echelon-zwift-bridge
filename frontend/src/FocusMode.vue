<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'

defineProps({ average: { type: Number, default: null }, warning: Boolean, target: Number })
const emit = defineEmits(['close'])
const stage = ref(null)
const controls = ref(true)
const fullscreen = ref(false)
let hideTimer, previousFocus, previousOverflow, app, previousInert

function revealControls() {
  controls.value = true
  clearTimeout(hideTimer)
  hideTimer = setTimeout(() => {
    if (!stage.value?.querySelector('.focus-controls')?.contains(document.activeElement)) controls.value = false
  }, 2200)
}

async function enterFullscreen() {
  try { await stage.value?.requestFullscreen?.() } catch { /* The viewport view works without fullscreen permission. */ }
}

function fullscreenChanged() {
  const wasFullscreen = fullscreen.value
  fullscreen.value = document.fullscreenElement === stage.value
  if (wasFullscreen && !fullscreen.value) emit('close')
}

function keydown(event) {
  if (event.key === 'Escape') { event.preventDefault(); emit('close') }
  if (event.key === 'Tab') {
    revealControls()
    const buttons = [...stage.value.querySelectorAll('button')].filter(button => !button.hidden)
    const index = buttons.indexOf(document.activeElement)
    event.preventDefault()
    const next = index < 0 ? (event.shiftKey ? buttons.length - 1 : 0) :
      (index + (event.shiftKey ? -1 : 1) + buttons.length) % buttons.length
    buttons[next]?.focus()
  }
}

onMounted(() => {
  previousFocus = document.activeElement
  previousOverflow = document.body.style.overflow
  document.body.style.overflow = 'hidden'
  app = document.getElementById('app')
  previousInert = app?.inert
  if (app) app.inert = true
  stage.value.focus()
  document.addEventListener('fullscreenchange', fullscreenChanged)
  revealControls()
  enterFullscreen()
})

onBeforeUnmount(() => {
  clearTimeout(hideTimer)
  document.removeEventListener('fullscreenchange', fullscreenChanged)
  if (document.fullscreenElement === stage.value) document.exitFullscreen?.().catch(() => {})
  document.body.style.overflow = previousOverflow
  if (app) app.inert = previousInert
  previousFocus?.focus?.()
})
</script>

<template>
  <div ref="stage" class="focus-stage" :class="{ 'is-warning': warning, 'controls-hidden': !controls }"
    role="dialog" aria-modal="true" aria-label="Focus mode" tabindex="-1" data-testid="focus-mode"
    @pointermove="revealControls" @pointerdown="revealControls" @keydown="keydown" @focusout="revealControls">
    <div class="focus-controls" :class="{ 'is-visible': controls }">
      <span>Esc to exit</span>
      <button v-if="!fullscreen" type="button" @click="enterFullscreen">Fullscreen</button>
      <button type="button" @click="emit('close')">Exit focus</button>
    </div>
    <div class="focus-center">
      <p v-if="warning" class="focus-warning" role="alert">PEDAL HARDER</p>
      <p class="focus-watts" data-testid="focus-average" aria-label="Five-second average power">{{ average === null ? '—' : Math.round(average) }} <span>W</span></p>
      <p v-if="warning" class="focus-detail">Reach {{ target }} W to clear</p>
      <p v-else-if="average === null" class="focus-waiting">Waiting for five seconds of live power</p>
    </div>
  </div>
</template>
