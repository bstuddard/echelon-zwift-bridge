<script setup>
import { computed } from 'vue'
const props = defineProps({ samples: { type: Array, default: () => [] } })
const hasData = computed(() => props.samples.some((sample) => sample.watts !== null))
const ceiling = computed(() => Math.max(100, Math.ceil(Math.max(...props.samples.map((s) => s.watts ?? 0), 0) / 50) * 50))
const paths = computed(() => {
  const segments = []
  let current = []
  props.samples.forEach((sample, index) => {
    if (sample.watts === null) {
      if (current.length) segments.push(current.join(' '))
      current = []
    } else {
      const x = 24 + (index / 119) * 852
      const y = 168 - (sample.watts / ceiling.value) * 148
      current.push(`${current.length ? 'L' : 'M'} ${x.toFixed(1)} ${y.toFixed(1)}`)
    }
  })
  if (current.length) segments.push(current.join(' '))
  return segments
})
</script>

<template>
  <div class="relative h-56" data-testid="power-chart">
    <div class="absolute inset-y-0 right-0 flex w-9 flex-col justify-between pb-9 pt-3 text-right text-[10px] text-stone-400" aria-hidden="true">
      <span>{{ ceiling }} W</span><span>{{ ceiling / 2 }}</span><span>0</span>
    </div>
    <svg viewBox="0 0 900 200" preserveAspectRatio="none" class="h-48 w-[calc(100%-2.5rem)] overflow-visible" role="img" aria-label="Estimated power history from the latest 120 observations. Gaps mean unavailable data.">
      <g stroke="#e8edeb" stroke-width="1" stroke-dasharray="4 6">
        <line x1="0" x2="900" y1="20" y2="20" /><line x1="0" x2="900" y1="94" y2="94" /><line x1="0" x2="900" y1="168" y2="168" />
      </g>
      <path v-for="(path, index) in paths" :key="index" :d="path" fill="none" stroke="#446b32" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke" />
    </svg>
    <div v-if="!hasData" class="absolute inset-0 flex flex-col items-center justify-center pb-8 text-center">
      <span class="mb-2 rounded-full bg-white px-3 py-1 text-xs font-medium text-stone-500 ring-1 ring-stone-200">Waiting for live readings</span>
      <p class="max-w-56 text-xs leading-relaxed text-stone-400">Your power trace will appear here when bike data is available.</p>
    </div>
    <div class="flex justify-between pr-10 text-[10px] text-stone-400"><span>Last 120 observations</span><span>Now</span></div>
  </div>
</template>
