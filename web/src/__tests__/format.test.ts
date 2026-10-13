import { describe, expect, it } from 'vitest'
import { clockLabel, compass, departAt, detourCap, formatDistance, formatMinutes, minuteOfTimeInput, shadeColor, sliderCaption, snapToSlot, timeInputValue, wallClock } from '../format'

const slider = { min: 0, max: 5, default: 2, base_cap: 1.5, max_cap: 3 }

describe('format', () => {
  it('writes distances and durations the way a person would say them', () => {
    expect(formatDistance(437)).toBe('440 m')
    expect(formatDistance(1348.3)).toBe('1.35 km')
    expect(formatMinutes(0.4)).toBe('under 1 min')
    expect(formatMinutes(17.3)).toBe('17 min')
  })

  it('labels clock times and compass points', () => {
    expect(clockLabel(900)).toBe('3:00 PM')
    expect(clockLabel(0)).toBe('12:00 AM')
    expect(clockLabel(12 * 60 + 15)).toBe('12:15 PM')
    expect(compass(244.8)).toBe('WSW')
    expect(compass(359)).toBe('N')
  })

  it('mirrors the server detour rule: 1.5 up to the default slider, relaxing to 3.0 at the top', () => {
    expect(detourCap(0, slider)).toBe(1.5)
    expect(detourCap(2, slider)).toBe(1.5)
    expect(detourCap(3.5, slider)).toBeCloseTo(2.25)
    expect(detourCap(5, slider)).toBe(3)
    expect(sliderCaption(2, slider)).toContain('Never more than 1.5')
    expect(sliderCaption(5, slider)).toContain('up to 3.0')
    expect(sliderCaption(0, slider)).toContain('ignored')
  })

  it('runs the shade ramp from coral through sand to teal', () => {
    expect(shadeColor(0)).toBe('rgb(235, 107, 79)')
    expect(shadeColor(0.5)).toBe('rgb(242, 192, 120)')
    expect(shadeColor(1)).toBe('rgb(27, 127, 138)')
    expect(shadeColor(7)).toBe(shadeColor(1))
  })

  it('does local-time arithmetic in the pilot timezone, not the browser one', () => {
    const now = new Date('2026-07-15T20:05:00Z')
    expect(wallClock(now, 'America/Chicago')).toEqual({ date: '2026-07-15', minute: 15 * 60 + 5 })
    expect(wallClock(new Date('2026-01-01T03:30:00Z'), 'America/Chicago')).toEqual({ date: '2025-12-31', minute: 21 * 60 + 30 })
    expect(departAt('2026-07-15', 905)).toBe('2026-07-15T15:05')
    expect(minuteOfTimeInput(timeInputValue(905))).toBe(905)
    expect(snapToSlot(907, 15)).toBe(900)
    expect(snapToSlot(1439, 15)).toBe(1425)
  })
})
