import { describe, expect, it } from 'vitest'
import { shareCardSvg, shareLines } from '../share'
import type { RouteOut, RouteResponse } from '../types'

const leg = (shade_pct: number, distance_m: number, sun_min: number): RouteOut => ({ distance_m, duration_min: distance_m / 78, shade_pct, shaded_m: 0, sunny_m: 0, sun_min, legs: [] })

const route = (same: boolean): RouteResponse => ({
  origin: { lon: 0, lat: 0, snapped_m: 0 },
  destination: { lon: 0, lat: 0, snapped_m: 0 },
  conditions: { depart_at: '2026-07-15T15:00', month: 7, minute: 900, sun: { azimuth_deg: 245, elevation_deg: 68, up: true }, temperature_c: 34.4, temperature_source: 'climatology', temperature_detail: '', heat_factor: 0.96 },
  shortest: leg(45.7, 1210, 8.4),
  shadiest: leg(75.6, 1348, 4.2),
  comparison: { extra_m: 138, extra_min: 1.8, shade_gain_points: 29.9, sun_min_saved: 4.2, detour_ratio: 1.11, detour_cap: 1.5, capped: false, weight_requested: 2, weight_used: 2, same_route: same },
  elapsed_ms: 1,
})

describe('share card', () => {
  it('says what the detour costs and what it buys', () => {
    const lines = shareLines(route(false), 'Downtown Dallas')
    expect(lines.headline).toBe('76% of this walk is in shade')
    expect(lines.detail).toContain('1.35 km')
    expect(lines.detail).toContain('2 min longer')
    expect(lines.detail).toContain('4 min less in direct sun')
    expect(lines.context).toBe('Downtown Dallas · July at 3:00 PM · 34 °C')
  })

  it('does not invent a trade when both routes are the same', () => {
    expect(shareLines(route(true), 'x').detail).toContain('already the shadiest')
  })

  it('draws a 1200 by 630 card over the template and escapes what it prints', () => {
    const svg = shareCardSvg(route(false), 'Main & <Elm>', '/assets/card.svg?a=1&b=2')
    expect(svg).toContain('width="1200" height="630"')
    expect(svg).toContain('href="/assets/card.svg?a=1&amp;b=2"')
    expect(svg).toContain('Main &amp; &lt;Elm&gt;')
    expect(svg).not.toContain('—')
  })
})
