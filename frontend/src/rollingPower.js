// Average the last five seconds by elapsed time, rather than by sample count.
// A reading holds until the next one arrives. Gaps invalidate the window.
export function rollingPowerAverage(samples, now, windowMs = 5000) {
  if (samples.length < 2) return null
  const end = samples.at(-1).time
  const cutoff = end - windowMs
  if (!Number.isFinite(end) || now - end > 2500 || end > now || samples[0].time > cutoff) return null

  let weighted = 0
  let duration = 0
  for (let i = 0; i < samples.length - 1; i++) {
    const current = samples[i]
    const next = samples[i + 1]
    if (next.time <= cutoff) continue
    if (!Number.isFinite(current.watts) || current.watts < 0 ||
        !Number.isFinite(next.watts) || next.watts < 0 ||
        !Number.isFinite(current.time) || !Number.isFinite(next.time) ||
        next.time <= current.time || next.time - current.time > 2500) return null
    const elapsed = next.time - Math.max(current.time, cutoff)
    weighted += current.watts * elapsed
    duration += elapsed
  }
  return duration === windowMs ? weighted / duration : null
}
