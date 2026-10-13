import maplibregl, { type GeoJSONSource, type ImageSource, type LngLatBoundsLike, type StyleSpecification } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { FeatureCollection } from 'geojson'
import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import { asset } from './assets'
import type { Layer, LonLat, Meta, Mode, PlannerResponse, Poi, RouteResponse } from './types'

/** Keyless vector style. Set VITE_MAP_STYLE_URL=offline to draw only ShadeWalk's own layers. */
const STYLE_URL = (import.meta.env.VITE_MAP_STYLE_URL as string | undefined) ?? 'https://tiles.openfreemap.org/styles/positron'

const OFFLINE_STYLE: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: 'paper', type: 'background', paint: { 'background-color': '#F4EFE6' } }],
}

const SHADE_RAMP = ['interpolate', ['linear'], ['coalesce', ['feature-state', 'shade'], 0], 0, '#EB6B4F', 0.5, '#F2C078', 1, '#1B7F8A'] as unknown as maplibregl.ExpressionSpecification
const LEG_RAMP = ['interpolate', ['linear'], ['get', 'shade'], 0, '#EB6B4F', 0.5, '#F2C078', 1, '#1B7F8A'] as unknown as maplibregl.ExpressionSpecification
const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] }

async function loadStyle(): Promise<StyleSpecification | string> {
  if (STYLE_URL === 'offline') return OFFLINE_STYLE
  try {
    const response = await fetch(STYLE_URL, { signal: AbortSignal.timeout(5000) })
    if (!response.ok) throw new Error(String(response.status))
    return (await response.json()) as StyleSpecification
  } catch {
    // No network: the app still works on its own buildings, streets and shadows.
    return OFFLINE_STYLE
  }
}

function legs(route: RouteResponse['shortest']): FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: route.legs.map((leg) => ({ type: 'Feature', properties: { shade: leg.shade }, geometry: { type: 'LineString', coordinates: leg.coords } })),
  }
}

function pin(label: string, className: string): HTMLElement {
  const el = document.createElement('div')
  el.className = `pin ${className}`
  el.textContent = label
  return el
}

interface Props {
  meta: Meta
  mode: Mode
  compact: boolean
  month: number
  minute: number
  layer: Layer
  shadePct: number[] | null
  origin: LonLat | null
  destination: LonLat | null
  route: RouteResponse | null
  planner: PlannerResponse | null
  pois: Poi[]
  focus: LonLat | null
  onPick: (point: LonLat) => void
}

export function MapView(props: Props) {
  const { meta, mode, compact, month, minute, layer, shadePct, origin, destination, route, planner, pois, focus, onPick } = props
  const holder = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const pick = useRef(onPick)
  pick.current = onPick
  const markers = useRef<{ origin?: maplibregl.Marker; destination?: maplibregl.Marker; places: maplibregl.Marker[] }>({ places: [] })
  const [ready, setReady] = useState(false)

  useEffect(() => {
    let cancelled = false
    let map: maplibregl.Map | null = null
    void loadStyle().then((style) => {
      if (cancelled || !holder.current) return
      const [w, s, e, n] = meta.bbox
      map = new maplibregl.Map({
        container: holder.current,
        style,
        bounds: [w, s, e, n] as LngLatBoundsLike,
        fitBoundsOptions: { padding: compact ? { top: 70, bottom: 20, left: 12, right: 12 } : { top: 40, bottom: 40, left: 440, right: 40 } },
        maxBounds: [w - 0.03, s - 0.03, e + 0.03, n + 0.03],
        attributionControl: false,
        dragRotate: false,
        pitchWithRotate: false,
      })
      map.addControl(new maplibregl.AttributionControl({ compact: true, customAttribution: '© OpenStreetMap contributors · NAIP imagery (USDA) · 3DEP lidar (USGS)' }), 'bottom-right')
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
      map.on('load', () => {
        if (!map) return
        const before = map.getStyle().layers.find((l) => l.type === 'symbol')?.id
        map.addSource('shadow', { type: 'image', url: api.shadowUrl(month, minute, layer), coordinates: meta.overlay.corners as [[number, number], [number, number], [number, number], [number, number]] })
        map.addSource('buildings', { type: 'geojson', data: api.geojsonUrl('buildings') })
        map.addSource('segments', { type: 'geojson', data: api.geojsonUrl('network') })
        for (const id of ['planner', 'short', 'shady', 'stops', 'area']) map.addSource(id, { type: 'geojson', data: EMPTY })
        ;(map.getSource('area') as GeoJSONSource).setData({ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: [[w, s], [e, s], [e, n], [w, n], [w, s]] } })

        map.addLayer({ id: 'sw-shadow', type: 'raster', source: 'shadow', paint: { 'raster-fade-duration': 0, 'raster-resampling': 'linear' } }, before)
        map.addLayer({ id: 'sw-buildings', type: 'fill', source: 'buildings', paint: { 'fill-color': '#E9DFD0', 'fill-outline-color': '#CDBFAA' } }, before)
        map.addLayer({ id: 'sw-area', type: 'line', source: 'area', paint: { 'line-color': '#5B3A5E', 'line-width': 1.5, 'line-dasharray': [2, 3], 'line-opacity': 0.6 } }, before)
        map.addLayer({ id: 'sw-walkways', type: 'line', source: 'segments', layout: { 'line-cap': 'round' }, paint: { 'line-color': '#FFFFFF', 'line-width': ['interpolate', ['linear'], ['zoom'], 14, 0.6, 18, 3], 'line-opacity': 0.7 } }, before)
        map.addLayer({ id: 'sw-segments', type: 'line', source: 'segments', layout: { 'line-cap': 'round', visibility: 'none' }, paint: { 'line-color': SHADE_RAMP, 'line-width': ['interpolate', ['linear'], ['zoom'], 14, 1.6, 18, 6] } }, before)
        map.addLayer({ id: 'sw-planner-halo', type: 'line', source: 'planner', layout: { 'line-cap': 'round' }, paint: { 'line-color': '#FFFFFF', 'line-width': 10 } }, before)
        map.addLayer({ id: 'sw-planner', type: 'line', source: 'planner', layout: { 'line-cap': 'round' }, paint: { 'line-color': '#C44D58', 'line-width': 6 } }, before)
        map.addLayer({ id: 'sw-short', type: 'line', source: 'short', layout: { 'line-cap': 'butt' }, paint: { 'line-color': '#2B2A33', 'line-width': 3, 'line-dasharray': [1.2, 1.6], 'line-opacity': 0.75 } }, before)
        map.addLayer({ id: 'sw-shady-casing', type: 'line', source: 'shady', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#FFFFFF', 'line-width': 11 } }, before)
        map.addLayer({ id: 'sw-shady', type: 'line', source: 'shady', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': LEG_RAMP, 'line-width': 6.5 } }, before)
        map.addLayer({
          id: 'sw-stops',
          type: 'circle',
          source: 'stops',
          paint: {
            'circle-radius': ['interpolate', ['linear'], ['zoom'], 14, 3.5, 18, 8],
            'circle-color': ['interpolate', ['linear'], ['get', 'shade'], 0, '#EB6B4F', 0.5, '#F2C078', 1, '#1B7F8A'],
            'circle-stroke-color': '#FFFFFF',
            'circle-stroke-width': 1.5,
          },
        })
        if (compact) {
          // On a phone the attribution starts folded behind its (i) button, so it does not cover the map.
          const credit = holder.current?.querySelector('.maplibregl-ctrl-attrib')
          credit?.classList.remove('maplibregl-compact-show')
          credit?.removeAttribute('open')
        }
        setReady(true)
      })
      map.on('click', (event) => pick.current({ lon: event.lngLat.lng, lat: event.lngLat.lat }))
      mapRef.current = map
      ;(window as unknown as { __map?: maplibregl.Map }).__map = map
    })
    return () => {
      cancelled = true
      map?.remove()
      mapRef.current = null
    }
    // The map is created once per pilot. Later changes arrive through the effects below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meta.slug])

  // The shadow image follows the time slider.
  useEffect(() => {
    if (!ready) return
    const source = mapRef.current?.getSource('shadow') as ImageSource | undefined
    source?.updateImage({ url: api.shadowUrl(month, minute, layer), coordinates: meta.overlay.corners as [[number, number], [number, number], [number, number], [number, number]] })
  }, [ready, month, minute, layer, meta])

  // Segment colours come from the shade table through feature state.
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    map.setLayoutProperty('sw-segments', 'visibility', mode === 'shade' ? 'visible' : 'none')
    map.setLayoutProperty('sw-shadow', 'visibility', 'visible')
    if (mode !== 'shade' || !shadePct) return
    const apply = () => shadePct.forEach((pct, id) => map.setFeatureState({ source: 'segments', id }, { shade: pct / 100 }))
    if (map.isSourceLoaded('segments')) apply()
    else map.once('idle', apply)
  }, [ready, mode, shadePct])

  // Routes.
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    const show = mode === 'route' && route
    ;(map.getSource('short') as GeoJSONSource).setData(show && !route.comparison.same_route ? legs(route.shortest) : EMPTY)
    ;(map.getSource('shady') as GeoJSONSource).setData(show ? legs(route.shadiest) : EMPTY)
    if (show) {
      const bounds = new maplibregl.LngLatBounds()
      for (const leg of [...route.shortest.legs, ...route.shadiest.legs]) for (const c of leg.coords) bounds.extend(c)
      map.fitBounds(bounds, { padding: compact ? { top: 80, bottom: 30, left: 30, right: 30 } : { top: 80, bottom: 80, left: 470, right: 80 }, maxZoom: 17, duration: 600 })
    }
  }, [ready, mode, route, compact])

  // Start and destination pins.
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    const place = (key: 'origin' | 'destination', point: LonLat | null, label: string) => {
      markers.current[key]?.remove()
      markers.current[key] = undefined
      if (point && mode === 'route') markers.current[key] = new maplibregl.Marker({ element: pin(label, key), anchor: 'bottom' }).setLngLat([point.lon, point.lat]).addTo(map)
    }
    place('origin', origin, 'A')
    place('destination', destination, 'B')
  }, [ready, mode, origin, destination])

  // Water and public indoor places in the route view, stops and blocks in the planner view.
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    markers.current.places.forEach((m) => m.remove())
    markers.current.places = []
    if (mode === 'route') {
      for (const poi of pois.filter((p) => p.kind === 'water' || p.kind === 'cooling')) {
        const el = document.createElement('img')
        el.src = asset(poi.kind === 'water' ? 'icons/water-fountain' : 'icons/cooling-center')
        el.alt = poi.kind === 'water' ? 'Drinking water' : (poi.name ?? 'Public indoor place')
        el.title = poi.name ?? (poi.kind === 'water' ? 'Drinking water' : 'Public indoor place')
        el.className = 'place'
        markers.current.places.push(new maplibregl.Marker({ element: el }).setLngLat([poi.lon, poi.lat]).addTo(map))
      }
    }
    const showPlanner = mode === 'planner' && planner
    ;(map.getSource('planner') as GeoJSONSource).setData(
      showPlanner ? { type: 'FeatureCollection', features: planner.blocks.map((b) => ({ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: b.coords } })) } : EMPTY,
    )
    ;(map.getSource('stops') as GeoJSONSource).setData(
      showPlanner
        ? { type: 'FeatureCollection', features: planner.stops.map((s) => ({ type: 'Feature', properties: { shade: s.shade_pct / 100 }, geometry: { type: 'Point', coordinates: [s.lon, s.lat] } })) }
        : EMPTY,
    )
  }, [ready, mode, pois, planner])

  useEffect(() => {
    if (ready && focus && mode === 'planner') mapRef.current?.flyTo({ center: [focus.lon, focus.lat], zoom: 17.2, duration: 700, padding: compact ? { top: 0, bottom: 0, left: 0, right: 0 } : { top: 0, bottom: 0, left: 420, right: 0 } })
    // Only a new focus should move the camera, not a resize or a tab change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, focus])

  return <div ref={holder} className="map" data-testid="map" data-ready={ready} />
}
