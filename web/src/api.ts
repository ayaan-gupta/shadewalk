import type { Layer, LonLat, Meta, PlannerResponse, Poi, RouteResponse, ShadeResponse } from './types'

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? ''

async function get<T>(path: string): Promise<T> {
  const response = await fetch(BASE + path)
  if (!response.ok) throw new Error(await detail(response))
  return (await response.json()) as T
}

async function detail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown }
    if (typeof body.detail === 'string') return body.detail
  } catch {
    // fall through to the status line
  }
  return `The server answered ${response.status}.`
}

export const api = {
  meta: () => get<Meta>('/api/meta'),
  pois: () => get<Poi[]>('/api/pois'),
  geojsonUrl: (name: 'network' | 'buildings' | 'canopy') => `${BASE}/api/${name}`,
  shadowUrl: (month: number, minute: number, layer: Layer) => `${BASE}/api/shadow.png?month=${month}&minute=${minute}&layer=${layer}`,
  shade: (month: number, minute: number, layer: Layer) => get<ShadeResponse>(`/api/shade?month=${month}&minute=${minute}&layer=${layer}`),
  planner: (month: number, startHour: number, endHour: number, layer: Layer) =>
    get<PlannerResponse>(`/api/planner?month=${month}&start_hour=${startHour}&end_hour=${endHour}&layer=${layer}&limit=30`),
  async route(origin: LonLat, destination: LonLat, departAt: string, shadeWeight: number, layer: Layer): Promise<RouteResponse> {
    const response = await fetch(`${BASE}/api/route`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ origin, destination, depart_at: departAt, shade_weight: shadeWeight, layer }),
    })
    if (!response.ok) throw new Error(await detail(response))
    return (await response.json()) as RouteResponse
  },
}
