<script setup>
import { ref } from 'vue'
import { useMirror } from './useMirror'

defineProps({ metrics: { type: Object, default: null } })
const canvas = ref(null)
const stage = ref(null)
const { phase, message, configured, checking, supported, active, start, stop, refresh } = useMirror(canvas)
async function fullscreen() {
  try { await stage.value?.requestFullscreen() } catch { /* The normal player remains usable. */ }
}
</script>

<template>
  <section class="mt-8" aria-label="Phone mirror">
    <div class="mb-5 flex flex-wrap items-end justify-between gap-4">
      <div><h2 class="section-title">Your ride on the big screen</h2><p class="section-subtitle">Zwift runs on your phone. Watch it here beside your bike readings.</p></div>
      <div class="flex flex-wrap gap-2">
        <button v-if="!active" class="btn btn-dark" :disabled="checking || !configured || !supported" @click="start">Start mirroring</button>
        <button v-else class="btn btn-white" @click="stop()">Stop mirroring</button>
        <button class="btn btn-white" :disabled="!active" @click="fullscreen">Full screen <span aria-hidden="true">⛶</span></button>
      </div>
    </div>
    <div ref="stage" class="mirror-stage relative flex aspect-video min-h-52 w-full items-center justify-center overflow-hidden rounded-xl border border-stone-800 bg-[#111915]" :aria-busy="phase === 'connecting'">
      <canvas ref="canvas" class="h-full w-full object-contain" :class="{ invisible: phase !== 'live' }" width="1280" height="720" aria-label="Live view of the selected phone" data-testid="phone-video"></canvas>
      <div v-if="phase !== 'live'" class="absolute inset-0 flex flex-col items-center justify-center gap-4 p-6 text-center">
        <svg class="h-12 w-12 text-[#8ca07a]" viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.2" aria-hidden="true"><rect x="9" y="3" width="14" height="26" rx="3"/><path d="M13 6h6m-4 20h2"/></svg>
        <p class="text-sm font-medium text-stone-100">{{ phase === 'connecting' ? 'Connecting to your phone…' : phase === 'error' ? 'Mirror needs attention' : 'Your phone stays private until you start' }}</p>
        <p class="max-w-md text-xs leading-6 text-stone-400">{{ phase === 'connecting' ? 'Keep your phone unlocked and connected. Your bike bridge continues running.' : 'Connect your selected phone, open Zwift, and choose Start mirroring.' }}</p>
      </div>
      <span v-if="phase === 'live'" class="absolute top-3 left-3 inline-flex items-center gap-2 rounded-md bg-black/70 px-3 py-1.5 text-[10px] font-medium text-white"><span class="size-1.5 rounded-full bg-[#c7e79c]"></span>Live · view only</span>
    </div>
    <p class="mt-3 text-xs leading-6" :class="phase === 'error' ? 'text-red-800' : 'text-stone-500'" role="status">{{ !supported ? 'Open this page in a recent Chrome or Chromium browser to view the phone video.' : message }}</p>
    <div class="mt-5 grid grid-cols-3 gap-3">
      <article class="metric-card !py-4"><div class="metric-label">Estimated power</div><div class="mt-2 text-2xl font-semibold tracking-tight tabular-nums">{{ metrics?.estimated_watts ?? '—' }} <span class="text-xs font-normal text-stone-400">W</span></div></article>
      <article class="metric-card !py-4"><div class="metric-label">Cadence</div><div class="mt-2 text-2xl font-semibold tracking-tight tabular-nums">{{ metrics?.cadence_rpm ?? '—' }} <span class="text-xs font-normal text-stone-400">rpm</span></div></article>
      <article class="metric-card !py-4"><div class="metric-label">Resistance</div><div class="mt-2 text-2xl font-semibold tracking-tight tabular-nums">{{ metrics?.resistance_level ?? '—' }} <span class="text-xs font-normal text-stone-400">/ 32</span></div></article>
    </div>
    <section class="panel mt-5">
      <h2 class="section-title">A private view of your phone</h2>
      <p class="mt-3 text-xs leading-6 text-stone-500">Only the phone selected during setup can stream here. Audio, phone controls, clipboard sharing, and recording are disabled. Leaving this page, hiding the browser tab, or pressing Stop ends capture and clears the picture.</p>
      <p class="mt-2 text-xs leading-6 text-stone-500">For wireless mirroring, turn on Wireless debugging on your trusted home network. Turn it off when you finish. Debugging gives this computer broader access than the viewer itself uses.</p>
      <details v-if="!configured" class="mt-4 rounded-lg bg-stone-50 p-4">
        <summary class="cursor-pointer text-xs font-semibold">Select a phone for the first time</summary>
        <p class="mt-3 text-xs leading-6 text-stone-500">Install scrcpy 4.x or 5.x, authorize one Android phone over USB or encrypted wireless pairing, then run this in the project folder:</p>
        <code class="mt-3 block overflow-auto text-xs">uv run echelon-mirror-setup</code>
        <p class="mt-3 text-xs leading-6 text-stone-500">Phone selection stays in your private user configuration. Your bike’s .env needs no extra entry.</p>
        <button class="btn btn-white mt-3" @click="refresh().catch(() => {})">Check setup again</button>
      </details>
    </section>
  </section>
</template>
