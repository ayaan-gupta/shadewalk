/** Pure helpers: formatting, the slider's detour rule and local-time arithmetic. */

export const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

export function formatDistance(metres: number): string {
  return metres < 1000 ? `${Math.round(metres / 10) * 10} m` : `${(metres / 1000).toFixed(2)} km`
}

export function formatMinutes(minutes: number): string {
  if (minutes < 1) return 'under 1 min'
  return `${Math.round(minutes)} min`
}

/** 900 -> "3:00 PM" */
export function clockLabel(minuteOfDay: number): string {
  const h = Math.floor(minuteOfDay / 60) % 24
  const m = Math.round(minuteOfDay % 60)
  const hour12 = h % 12 === 0 ? 12 : h % 12
  return `${hour12}:${String(m).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`
}

const POINTS = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']

export function compass(azimuthDeg: number): string {
  return POINTS[Math.round((((azimuthDeg % 360) + 360) % 360) / 22.5) % 16]!
}

/** Mirrors detour_cap in api/shadewalk/routing.py. */
export function detourCap(weight: number, slider: { default: number; max: number; base_cap: number; max_cap: number }): number {
  if (weight <= slider.default) return slider.base_cap
  const t = Math.min((weight - slider.default) / (slider.max - slider.default), 1)
  return slider.base_cap + t * (slider.max_cap - slider.base_cap)
}

export function sliderCaption(weight: number, slider: { default: number; max: number; base_cap: number; max_cap: number }): string {
  if (weight === 0) return 'Shade ignored. Both routes are the shortest one.'
  const cap = detourCap(weight, slider)
  if (weight <= slider.default) return `Never more than ${cap.toFixed(1)} times the shortest walk.`
  return `Longer detours allowed: up to ${cap.toFixed(1)} times the shortest walk.`
}

/** Sunny coral to shaded teal, through sand. Input 0 to 1. */
export function shadeColor(shade: number): string {
  const stops: [number, [number, number, number]][] = [
    [0, [235, 107, 79]],
    [0.5, [242, 192, 120]],
    [1, [27, 127, 138]],
  ]
  const s = Math.min(Math.max(shade, 0), 1)
  const [a, b] = s <= 0.5 ? [stops[0]!, stops[1]!] : [stops[1]!, stops[2]!]
  const t = (s - a[0]) / (b[0] - a[0])
  const mix = a[1].map((v, i) => Math.round(v + (b[1][i]! - v) * t))
  return `rgb(${mix[0]}, ${mix[1]}, ${mix[2]})`
}

/** The wall-clock date and minute of day in another timezone, e.g. the pilot's. */
export function wallClock(now: Date, timeZone: string): { date: string; minute: number } {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(now)
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? '00'
  return { date: `${get('year')}-${get('month')}-${get('day')}`, minute: Number(get('hour')) * 60 + Number(get('minute')) }
}

/** ("2026-07-15", 900) -> "2026-07-15T15:00", the API's local wall-clock format. */
export function departAt(date: string, minuteOfDay: number): string {
  const h = Math.floor(minuteOfDay / 60)
  const m = minuteOfDay % 60
  return `${date}T${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

export function timeInputValue(minuteOfDay: number): string {
  return departAt('', minuteOfDay).slice(1)
}

export function minuteOfTimeInput(value: string): number {
  const [h, m] = value.split(':').map(Number)
  return (h ?? 0) * 60 + (m ?? 0)
}

export function snapToSlot(minute: number, slot: number): number {
  return Math.min(Math.round(minute / slot) * slot, 1440 - slot)
}
