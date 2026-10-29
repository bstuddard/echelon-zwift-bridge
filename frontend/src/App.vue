<script setup>
import { computed, ref } from 'vue'
import { useBridge } from './useBridge'
import PowerChart from './PowerChart.vue'

const { health, metrics, events, samples, online, loading, error, lastUpdated, refresh } = useBridge()
const tab = ref('ride')
const notice = ref('')
const m = computed(() => online.value ? metrics.value : null)
const p = computed(() => online.value ? health.value?.peripheral : null)
const simulated = computed(() => health.value?.simulated)
const status = computed(() => {
  if (loading.value) return { title: 'Connecting to your bridge', detail: 'Reading the local server status.', tone: 'neutral', icon: '◌' }
  if (!online.value) return { title: 'Local server is unavailable', detail: 'Start the bridge with ./bridge start, then refresh this page.', tone: 'error', icon: '!' }
  if (simulated.value) return { title: 'Simulation · Bluetooth smoke test only', detail: 'These fixed readings are test data. Stop simulation and start the live bridge before riding.', tone: 'warning', icon: '!' }
  if (m.value?.auth_required) return { title: 'This bike needs firmware authentication', detail: 'Power is held at zero. This firmware needs an additional compatibility step; see the connection guide.', tone: 'error', icon: '!' }
  if (Object.keys(health.value?.failed_tasks ?? {}).length) return { title: 'A bridge task stopped', detail: 'Open Diagnostics for the error, then restart the bridge.', tone: 'error', icon: '!' }
  if (m.value?.power_available) {
    if (health.value?.ble_power_advertising_enabled && !p.value?.gatt_started) return { title: 'Bike readings are live. Bluetooth needs attention.', detail: p.value?.last_error || 'The virtual power sensor is restarting. Check Diagnostics.', tone: 'warning', icon: '!' }
    return { title: 'Your bike readings are live', detail: !health.value?.ble_power_advertising_enabled ? 'Reader-only mode. Start the full bridge to advertise power to Zwift.' : p.value?.client_subscribed ? 'A Bluetooth client has subscribed. Confirm the sensor is paired in Zwift.' : 'Select EchelonPython as your Power Source on the Zwift pairing screen.', tone: 'ready', icon: '✓' }
  }
  if (health.value?.reader_enabled && health.value?.bike_selection === 'unconfigured') return { title: 'Select your bike first', detail: 'Run echelon-bridge --scan, then save your bike address as ECHELON_ADDRESS in .env.', tone: 'warning', icon: 'i' }
  if (!health.value?.reader_enabled) return { title: 'Diagnostics mode', detail: 'The live bike reader is disabled. Start ./bridge run for bike and Zwift connections.', tone: 'neutral', icon: 'i' }
  if (m.value?.connected && m.value?.stale) return { title: 'Bike connected. Waiting for fresh cadence.', detail: 'Pedal to send a new reading. Power stays at zero while cadence data is stale.', tone: 'warning', icon: '◌' }
  if (m.value?.connected && m.value?.resistance_level == null) return { title: 'Turn the resistance knob once', detail: 'Cadence is arriving. The bike needs to report a resistance level before power can be estimated.', tone: 'warning', icon: '↻' }
  return { title: 'Wake your bike to begin', detail: 'Start pedaling and close Echelon, QZ, or other connected bike apps. The bridge will connect automatically.', tone: 'neutral', icon: '↻' }
})
const bikeLabel = computed(() => !online.value ? 'Unknown' : !health.value?.reader_enabled && !simulated.value ? 'Disabled' : m.value?.connected ? m.value.stale ? 'No fresh data' : 'Connected' : 'Searching')
const peripheralLabel = computed(() => !online.value ? 'Unknown' : !health.value?.ble_power_advertising_enabled ? 'Disabled' : p.value?.client_subscribed ? 'Client subscribed' : p.value?.advertisement_registered ? 'Advertising' : 'Starting')
const age = computed(() => m.value?.last_cadence_age_seconds == null ? '—' : `${m.value.last_cadence_age_seconds.toFixed(1)} s`)
const raw = computed(() => JSON.stringify({ health: health.value, metrics: metrics.value }, null, 2))
const title = computed(() => ({ ride: 'Ride overview', diagnostics: 'Diagnostics', guide: 'Connection guide', legal: 'About & licenses' })[tab.value])
const eventTime = (timestamp) => new Date(timestamp).toLocaleTimeString([], { hour12: false })
const report = () => ({ captured_at: new Date().toISOString(), api_reachable: online.value, health: health.value, metrics: metrics.value, events: events.value })
async function copyDiagnostics() {
  try {
    await navigator.clipboard.writeText(JSON.stringify(report(), null, 2))
    notice.value = 'Diagnostics copied.'
  } catch { notice.value = 'Clipboard unavailable. Use Download instead.' }
}
function downloadDiagnostics() {
  const url = URL.createObjectURL(new Blob([JSON.stringify(report(), null, 2)], { type: 'application/json' }))
  const link = document.createElement('a')
  link.href = url
  link.download = 'echelon-bridge-diagnostics.json'
  link.click()
  URL.revokeObjectURL(url)
  notice.value = 'Diagnostics downloaded.'
}
</script>

<template>
  <div class="min-h-screen lg:flex">
    <aside class="sidebar">
      <a href="/" class="flex items-center gap-3" aria-label="Echelon Bridge home">
        <span class="flex size-10 items-center justify-center rounded-xl bg-[#1b302c] text-[#d3ef9b]">
          <svg width="25" height="25" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="6" cy="16" r="4" stroke="currentColor" stroke-width="1.6"/><circle cx="18" cy="16" r="4" stroke="currentColor" stroke-width="1.6"/><path d="m6 16 5-9 7 9H6m4-9H7m4 0h5l-2-3h-2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </span>
        <span class="leading-tight"><strong class="block text-[15px] font-bold tracking-tight">Echelon Bridge<span class="text-[#689747]">.</span></strong><span class="text-[9px] whitespace-nowrap uppercase tracking-[.1em] text-stone-400">Your bike. Your ride.</span></span>
      </a>
      <div class="mt-9 hidden text-[10px] font-semibold uppercase tracking-[.16em] text-stone-400 lg:block">Workspace</div>
      <nav class="mt-5 flex gap-2 lg:flex-col" aria-label="Main navigation">
        <button class="nav-item" :class="{ active: tab === 'ride' }" :aria-current="tab === 'ride' ? 'page' : undefined" @click="tab = 'ride'"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>Ride monitor</button>
        <button class="nav-item" :class="{ active: tab === 'diagnostics' }" :aria-current="tab === 'diagnostics' ? 'page' : undefined" @click="tab = 'diagnostics'"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M3 12h4l3-8 4 16 3-8h4"/></svg>Diagnostics</button>
        <button class="nav-item" :class="{ active: tab === 'guide' }" :aria-current="tab === 'guide' ? 'page' : undefined" @click="tab = 'guide'"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M9 9a3 3 0 0 1 6 0c0 2-3 2-3 4m0 3v1"/></svg>Setup guide</button>
        <button class="nav-item" :class="{ active: tab === 'legal' }" :aria-current="tab === 'legal' ? 'page' : undefined" @click="tab = 'legal'"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-11v1"/></svg>About</button>
      </nav>
      <div class="mt-auto hidden pt-12 lg:block">
        <div class="rounded-xl border border-stone-200/80 p-4"><div class="mb-2 flex items-center gap-2 text-xs font-semibold"><span class="size-1.5 rounded-full bg-[#6a8d51]"></span>Local by design</div><p class="text-[11px] leading-relaxed text-stone-500">Admin access stays on this computer. Ride data reaches Zwift over Bluetooth.</p></div>
        <div class="mt-5 text-[10px] text-stone-400">Echelon Bridge <span class="float-right font-mono">v0.3.0</span></div>
      </div>
    </aside>

    <main class="min-w-0 flex-1 px-5 pb-8 sm:px-8 lg:px-10 xl:px-14">
      <header class="flex min-h-24 flex-wrap items-center justify-between gap-3 border-b border-stone-200/70 py-5">
        <div><p class="eyebrow">Bike workspace <span class="mx-2 text-stone-300">/</span> {{ title }}</p><h1 class="mt-1.5 text-[25px] font-semibold tracking-[-.045em]">{{ title }}</h1></div>
        <div class="flex items-center gap-3"><span class="chip" :class="online ? 'chip-green' : 'chip-stone'"><span class="size-1.5 rounded-full" :class="online ? 'bg-[#658c47]' : 'bg-stone-400'"></span>{{ loading ? 'Connecting' : online ? 'Server online' : 'Server offline' }}</span><button class="btn btn-white" @click="refresh" aria-label="Refresh bridge status"><span aria-hidden="true">↻</span><span class="hidden sm:inline">Refresh</span></button></div>
      </header>

      <div v-if="simulated" class="mt-5 rounded-xl bg-amber-100 px-4 py-3 text-sm font-semibold text-amber-900" role="alert">SIMULATION — Bluetooth smoke test only. These are not live bike readings.</div>
      <section class="status-banner" :class="`status-${status.tone}`" role="status">
        <span class="status-icon" aria-hidden="true">{{ status.icon }}</span><div class="min-w-0 flex-1"><h2 class="text-sm font-semibold">{{ status.title }}</h2><p class="mt-1 text-xs leading-relaxed opacity-75">{{ status.detail }}</p></div><button v-if="tab !== 'guide'" class="hidden text-xs font-semibold whitespace-nowrap sm:block" @click="tab = 'guide'">View guide <span class="ml-1" aria-hidden="true">↗</span></button>
      </section>

      <template v-if="tab === 'ride'">
        <div class="mb-5 mt-8 flex items-end justify-between"><div><h2 class="section-title">At a glance</h2><p class="section-subtitle">A live view from your bike to Zwift.</p></div><span class="text-[10px] text-stone-400">{{ online ? 'Updates every second' : 'Awaiting local server' }}</span></div>
        <div class="grid grid-cols-2 gap-3 xl:grid-cols-4 xl:gap-4">
          <article class="metric-card metric-primary"><div class="flex items-center justify-between"><span class="metric-label">Estimated power</span><span class="text-lg text-[#94ad71]" aria-hidden="true">ϟ</span></div><div class="metric-value" data-testid="power-value">{{ m?.estimated_watts ?? '—' }}<span>W</span></div><div class="metric-caption"><span class="size-1.5 rounded-full bg-[#c7e79c]"></span>{{ m?.power_available ? 'Receiving live estimate' : 'Output held at zero until ready' }}</div></article>
          <article class="metric-card"><div class="metric-label">Cadence <span class="float-right text-stone-300" aria-hidden="true">↻</span></div><div class="metric-value">{{ m?.cadence_rpm ?? '—' }}<span>rpm</span></div><div class="metric-caption">{{ m?.stale ? 'Waiting for fresh cadence' : 'Your pedaling rhythm' }}</div></article>
          <article class="metric-card"><div class="metric-label">Resistance <span class="float-right text-stone-300" aria-hidden="true">≋</span></div><div class="metric-value">{{ m?.resistance_level ?? '—' }}<span>/ 32</span></div><div class="metric-caption">Adjust with your bike's knob</div></article>
          <article class="metric-card"><div class="metric-label">Data freshness <span class="float-right text-stone-300" aria-hidden="true">◷</span></div><div class="metric-value !text-[34px]">{{ age }}</div><div class="metric-caption"><span class="size-1.5 rounded-full" :class="m && !m.stale ? 'bg-[#7b9a5e]' : 'bg-stone-300'"></span>{{ m && !m.stale ? 'Fresh cadence data' : 'No fresh bike data' }}</div></article>
        </div>

        <div class="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1.8fr)_minmax(280px,1fr)]">
          <section class="panel"><div class="mb-6 flex items-start justify-between"><div><h2 class="section-title">Power over time</h2><p class="section-subtitle">Estimated watts from this browser session</p></div><span class="chip chip-stone"><span class="size-1.5 rounded-full bg-[#63844c]"></span>Power</span></div><PowerChart :samples="samples"/><div class="flex items-center justify-between border-t border-stone-100 pt-4 text-[10px] text-stone-400"><span>QZ default lookup table</span><span>Estimated · uncalibrated</span></div></section>
          <section class="panel"><div class="mb-6 flex items-center justify-between"><h2 class="section-title">Connection path</h2><span class="text-[10px] font-medium uppercase tracking-wider text-stone-400">Bluetooth LE</span></div>
            <div class="connection-step"><span class="step-symbol">01</span><div class="min-w-0 flex-1"><h3>Echelon bike</h3><p>Cadence & manual resistance</p></div><span class="chip" :class="m?.connected ? 'chip-green' : 'chip-stone'">{{ bikeLabel }}</span></div>
            <div class="connection-line"></div>
            <div class="connection-step"><span class="step-symbol">02</span><div class="min-w-0 flex-1"><h3>Python bridge</h3><p>Local power estimation</p></div><span class="chip" :class="online ? 'chip-green' : 'chip-stone'">{{ online ? 'Running' : 'Offline' }}</span></div>
            <div class="connection-line"></div>
            <div class="connection-step"><span class="step-symbol">03</span><div class="min-w-0 flex-1"><h3>Zwift power source</h3><p class="font-mono">{{ health?.peripheral?.name || 'EchelonPython' }}</p></div><span class="chip" :class="p?.client_subscribed ? 'chip-green' : 'chip-stone'">{{ peripheralLabel }}</span></div>
            <p class="mt-6 rounded-lg bg-stone-50 p-3 text-[11px] leading-relaxed text-stone-500">{{ p?.client_subscribed ? 'A BLE client is subscribed. Verify pairing in Zwift; the bridge cannot identify the client app.' : 'In Zwift, choose EchelonPython under Power Source. Your bridge computer needs to stay nearby.' }}</p>
          </section>
        </div>
        <section class="panel mt-5 flex flex-wrap items-center gap-4 !py-5"><span class="flex size-10 items-center justify-center rounded-xl bg-[#f0f4e9] text-xl text-[#6c854a]" aria-hidden="true">⌁</span><div class="min-w-0 flex-1 basis-48"><h2 class="text-sm font-semibold">Everything you need to troubleshoot</h2><p class="mt-1 text-xs text-stone-500">Inspect Bluetooth registration, recent events, and the live API response.</p></div><button class="btn btn-white" @click="tab = 'diagnostics'">Open diagnostics <span aria-hidden="true">↗</span></button></section>
      </template>

      <template v-else-if="tab === 'diagnostics'">
        <div class="mb-5 mt-8 flex flex-wrap items-end justify-between gap-3"><div><h2 class="section-title">Under the hood</h2><p class="section-subtitle">Live status and redacted events from the bridge process.</p></div><div class="flex gap-2"><button class="btn btn-white" @click="copyDiagnostics">Copy diagnostics</button><button class="btn btn-dark" @click="downloadDiagnostics">Download JSON <span aria-hidden="true">↓</span></button></div></div>
        <p v-if="notice" role="status" class="mb-4 text-xs text-[#587940]">{{ notice }}</p>
        <p v-if="error" class="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-800" role="alert">{{ error }}</p>
        <div class="grid gap-5 lg:grid-cols-2">
          <section class="panel"><h2 class="section-title mb-4">Bike reader</h2><dl class="debug-list"><div><dt>Status</dt><dd>{{ online ? m?.reader_status : 'Unavailable' }}</dd></div><div><dt>Adapter</dt><dd>{{ health?.adapter || '—' }}</dd></div><div><dt>Bike selection</dt><dd>{{ !online ? 'Unknown' : health?.bike_selection === 'pinned_address' ? 'Pinned bike address' : 'Not configured' }}</dd></div><div><dt>Initialization</dt><dd>{{ online ? m?.initialized ? 'Complete' : 'Waiting' : 'Unknown' }}</dd></div><div><dt>Packets received</dt><dd>{{ m?.packets_seen ?? '—' }}</dd></div><div><dt>Latest packet</dt><dd>{{ m?.last_packet_kind ?? '—' }}</dd></div><div><dt>Reconnect attempts</dt><dd>{{ m?.reconnects ?? '—' }}</dd></div><div><dt>Firmware authentication</dt><dd>{{ online ? m?.auth_required ? 'Required' : 'No challenge received' : 'Unknown' }}</dd></div></dl></section>
          <section class="panel"><h2 class="section-title mb-4">Virtual power sensor</h2><dl class="debug-list"><div><dt>Device name</dt><dd>{{ health?.peripheral?.name || '—' }}</dd></div><div><dt>Adapter</dt><dd>{{ health?.power_adapter || '—' }}</dd></div><div><dt>GATT service registered</dt><dd>{{ online ? p?.gatt_started ? 'Yes' : 'No' : 'Unknown' }}</dd></div><div><dt>Advertisement registered</dt><dd>{{ online ? p?.advertisement_registered ? 'Yes' : 'No' : 'Unknown' }}</dd></div><div><dt>Adapter advertising active</dt><dd>{{ online ? p?.adapter_advertising_active ? 'Yes' : 'No' : 'Unknown' }}</dd></div><div><dt>Client subscribed</dt><dd>{{ online ? p?.client_subscribed ? 'Yes · app unverified' : 'No' : 'Unknown' }}</dd></div><div><dt>Characteristic updates</dt><dd>{{ p?.updates ?? '—' }}</dd></div></dl></section>
        </div>
        <section v-if="m?.last_error || p?.last_error || Object.keys(health?.failed_tasks ?? {}).length" class="panel mt-5 !border-amber-200 !bg-amber-50/50"><h2 class="text-sm font-semibold text-amber-900">Latest reported issue</h2><p v-if="m?.last_error" class="mt-2 break-words font-mono text-xs leading-relaxed text-amber-900">{{ m.last_error }}</p><p v-if="p?.last_error" class="mt-2 break-words font-mono text-xs leading-relaxed text-amber-900">{{ p.last_error }}</p><pre v-if="Object.keys(health?.failed_tasks ?? {}).length" class="mt-2 overflow-auto text-xs">{{ JSON.stringify(health.failed_tasks, null, 2) }}</pre></section>
        <section class="panel mt-5"><div class="mb-5 flex items-center justify-between"><h2 class="section-title">Recent bridge events</h2><span class="text-[10px] text-stone-400">Last {{ events.length }} · memory only</span></div><div v-if="!events.length" class="rounded-xl bg-stone-50 px-5 py-8 text-center text-xs text-stone-500">No bridge events yet. Connection events will appear here.</div><div v-else class="max-h-72 overflow-auto"><div v-for="(event, index) in [...events].reverse()" :key="`${event.timestamp}-${index}`" class="event-row"><time>{{ eventTime(event.timestamp) }}</time><span class="event-level" :class="event.level === 'warning' || event.level === 'error' ? 'text-amber-700 bg-amber-50' : 'text-[#557441] bg-[#f0f5e9]'">{{ event.level }}</span><span class="min-w-0 break-words font-mono text-[11px] leading-relaxed">{{ event.message }}</span></div></div></section>
        <details class="panel mt-5"><summary class="cursor-pointer text-sm font-semibold">Inspect API response <span class="ml-2 text-[11px] font-normal text-stone-400">{{ online ? 'Live snapshot' : 'Last successful snapshot · server offline' }}</span></summary><pre class="mt-5 max-h-96 overflow-auto rounded-xl bg-[#1d2c28] p-5 font-mono text-[11px] leading-relaxed text-[#dae3d1]">{{ raw }}</pre></details>
      </template>

      <template v-else-if="tab === 'guide'">
        <div class="mb-5 mt-8"><h2 class="section-title">From a first pedal to your first ride</h2><p class="section-subtitle">Keep your bike, bridge computer, and Zwift device within Bluetooth range.</p></div>
        <div class="space-y-4">
          <section class="panel guide-step"><span class="guide-number">1</span><div><h2 class="text-base font-semibold">Wake the Echelon bike</h2><p>Select your bike once with <code>uv run echelon-bridge --scan</code> and save its address as <code>ECHELON_ADDRESS</code> in your private <code>.env</code>. Power the bike and start pedaling. Close Echelon, QZ, and other connected bike apps. Wait for the reader to connect; scanning and retries can take about 40 seconds.</p><p>If cadence appears but resistance is unknown, turn the manual knob once. Readings should change in Ride monitor.</p><span class="chip mt-3" :class="m?.power_available ? 'chip-green' : 'chip-stone'">{{ m?.power_available ? 'Live data received' : 'Waiting for bike data' }}</span></div></section>
          <section class="panel guide-step"><span class="guide-number">2</span><div><h2 class="text-base font-semibold">Check the virtual power sensor</h2><p>On a second device, scan with nRF Connect for <strong>{{ health?.peripheral?.name || 'EchelonPython' }}</strong>. Connect, find Cycling Power Service <code>1818</code>, and subscribe to measurement <code>2A63</code>. Notifications should arrive every second.</p><p>Disconnect nRF Connect before opening Zwift. Local advertisement registration alone cannot confirm over-the-air discovery.</p><span class="chip mt-3" :class="p?.advertisement_registered ? 'chip-green' : 'chip-stone'">{{ p?.advertisement_registered ? 'Advertisement registered locally' : 'Waiting for advertisement' }}</span></div></section>
          <section class="panel guide-step"><span class="guide-number">3</span><div><h2 class="text-base font-semibold">Pair in Zwift and pedal</h2><p>In Zwift on your other computer or tablet, open <strong>Paired Devices → Power Source</strong> and select <strong>EchelonPython</strong>. Optionally select it for Cadence. Use the bike's knob to change resistance.</p><p>Power comes from an estimate based on cadence and resistance. Check the organizer's hardware rules for events that require measured power.</p><span class="chip mt-3" :class="p?.client_subscribed ? 'chip-green' : 'chip-stone'">{{ p?.client_subscribed ? 'BLE client subscribed · confirm in Zwift' : 'Waiting for a BLE subscriber' }}</span></div></section>
        </div>
        <div class="mt-6 grid gap-4 sm:grid-cols-2"><section class="panel"><h2 class="text-sm font-semibold">Need a restart?</h2><p class="mt-2 text-xs leading-relaxed text-stone-500">From the project folder, run:</p><pre class="mt-3 rounded-lg bg-stone-50 p-3 text-xs leading-6">./bridge stop
./bridge start</pre></section><section class="panel"><h2 class="text-sm font-semibold">Still not connecting?</h2><p class="mt-2 text-xs leading-relaxed text-stone-500">Check Diagnostics for firmware authentication or Bluetooth errors. Some adapters need a second USB Bluetooth adapter to connect and advertise simultaneously.</p><p class="mt-3 text-xs leading-relaxed text-stone-500">The complete physical checklist is in <code>SMOKE_TEST.md</code> in this project.</p></section></div>
      </template>
      <section v-if="tab === 'legal'" class="panel mt-8 space-y-5">
        <div><h2 class="section-title">Echelon Bridge · GPL-3.0-only</h2><p class="section-subtitle">Independent, experimental compatibility software.</p></div>
        <p class="text-sm leading-relaxed text-stone-600">You may redistribute and modify this software under the GNU General Public License version 3. It is provided without warranty, including any implied warranty of merchantability or fitness for a particular purpose.</p>
        <p class="text-sm leading-relaxed text-stone-600">Protocol knowledge and the default wattage table are adapted from QZ / qdomyos-zwift by Roberto Viola and contributors. Copyright to adapted QZ material remains with its respective authors. The Python bridge, Vue admin, and Omarchy integration were adapted and modified on 2026-10-28.</p>
        <p class="text-sm leading-relaxed text-stone-600">Vue, Tailwind CSS, Vite-generated helpers, Bleak, Bless, dbus-next, and Omarchy retain the copyright and license notices included below.</p>
        <div class="flex flex-wrap gap-3"><a class="btn btn-white" href="/legal/LICENSE.txt" target="_blank" rel="noreferrer">View GPL license ↗</a><a class="btn btn-white" href="/legal/NOTICE.txt" target="_blank" rel="noreferrer">Attribution ↗</a><a class="btn btn-white" href="/legal/THIRD_PARTY_NOTICES.txt" target="_blank" rel="noreferrer">Third-party notices ↗</a></div>
        <p class="text-xs leading-relaxed text-stone-500">Unaffiliated with Echelon, Zwift, QZ, or Omarchy. Power is an uncalibrated estimate using the original QZ default table, with no gain multiplier.</p>
      </section>
      <footer class="mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-stone-200/70 pt-5 text-[10px] text-stone-400"><span>Local admin <span class="mx-2">·</span> Estimated power, not a calibrated meter</span><span>{{ lastUpdated ? `Last response ${lastUpdated.toLocaleTimeString()}` : 'No response yet' }} <span class="mx-2">·</span><a href="/api/health" target="_blank" rel="noreferrer" class="hover:text-stone-700">API status ↗</a></span></footer>
    </main>
  </div>
</template>
