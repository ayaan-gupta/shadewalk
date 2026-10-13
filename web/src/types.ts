export type Layer = 'all' | 'buildings'
export type Mode = 'route' | 'shade' | 'planner'

export interface LonLat {
  lon: number
  lat: number
}

export interface Meta {
  slug: string
  name: string
  bbox: [number, number, number, number]
  centre: [number, number]
  timezone: string
  slider: { min: number; max: number; default: number; base_cap: number; max_cap: number }
  walk_speed_mps: number
  store: string
  weather: string
  daylight: [number, number][]
  overlay: { corners: [number, number][]; slot_minutes: number }
  counts: { nodes: number; segments: number; km: number; buildings: number; canopy_patches: number; pois: Record<string, number> }
}

export interface Poi {
  id: number
  kind: 'bus_stop' | 'rail_stop' | 'school' | 'water' | 'cooling' | 'park' | 'landmark'
  name: string | null
  lon: number
  lat: number
}

export interface Sun {
  azimuth_deg: number
  elevation_deg: number
  up: boolean
}

export interface ShadeResponse {
  month: number
  minute: number
  layer: Layer
  sun: Sun
  network_shade_pct: number
  shade_pct: number[]
}

export interface Leg {
  segment_id: number
  shade: number
  length_m: number
  street: string | null
  coords: [number, number][]
}

export interface RouteOut {
  distance_m: number
  duration_min: number
  shade_pct: number
  shaded_m: number
  sunny_m: number
  sun_min: number
  legs: Leg[]
}

export interface RouteResponse {
  origin: LonLat & { snapped_m: number }
  destination: LonLat & { snapped_m: number }
  conditions: {
    depart_at: string
    month: number
    minute: number
    sun: Sun
    temperature_c: number
    temperature_source: 'forecast' | 'climatology'
    temperature_detail: string
    heat_factor: number
  }
  shortest: RouteOut
  shadiest: RouteOut
  comparison: {
    extra_m: number
    extra_min: number
    shade_gain_points: number
    sun_min_saved: number
    detour_ratio: number
    detour_cap: number
    capped: boolean
    weight_requested: number
    weight_used: number
    same_route: boolean
  }
  elapsed_ms: number
}

export interface Block {
  segment_id: number
  street: string | null
  kind: string
  length_m: number
  shade_pct: number
  bus_stops: number
  rail_stops: number
  schools: number
  priority: number
  lon: number
  lat: number
  coords: [number, number][]
}

export interface Stop {
  id: number
  kind: string
  name: string | null
  lon: number
  lat: number
  shade_pct: number
}

export interface PlannerResponse {
  month: number
  start_hour: number
  end_hour: number
  store: string
  network_shade_pct: number
  low_shade_km: number
  unshaded_stops: number
  stop_count: number
  blocks: Block[]
  stops: Stop[]
}
