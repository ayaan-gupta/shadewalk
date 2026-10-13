import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api'
import { Onboarding } from './components/Onboarding'
import { PlannerPanel } from './components/PlannerPanel'
import { RoutePanel } from './components/RoutePanel'
import { ShadePanel } from './components/ShadePanel'
import { ShareDialog } from './components/ShareDialog'
import { departAt, snapToSlot, wallClock } from './format'
import { MapView } from './MapView'
import type { Layer, LonLat, Meta, Mode, PlannerResponse, Poi, RouteResponse, ShadeResponse } from './types'

export interface Place extends LonLat {
  label: string
}

const SEEN_KEY = 'shadewalk.onboarded'

function useCompact(): boolean {
  const [compact, setCompact] = useState(() => window.matchMedia('(max-width: 760px)').matches)
  useEffect(() => {
    const query = window.matchMedia('(max-width: 760px)')
    const listen = () => setCompact(query.matches)
    query.addEventListener('change', listen)
    return () => query.removeEventListener('change', listen)
  }, [])
  return compact
}

export function App() {
  const compact = useCompact()
  const [meta, setMeta] = useState<Meta | null>(null)
  const [pois, setPois] = useState<Poi[]>([])
  const [fatal, setFatal] = useState<string | null>(null)
  const [mode, setMode] = useState<Mode>('route')
  const [layer, setLayer] = useState<Layer>('all')
  const [showIntro, setShowIntro] = useState(() => {
    try {
      return localStorage.getItem(SEEN_KEY) !== '1'
    } catch {
      return true
    }
  })

  // When you walk. One clock drives the route, the shadow layer and the shade map.
  const [date, setDate] = useState('2026-07-15')
  const [minute, setMinute] = useState(15 * 60)
  const month = Number(date.slice(5, 7)) || 7

  const [origin, setOrigin] = useState<Place | null>(null)
  const [destination, setDestination] = useState<Place | null>(null)
  const [picking, setPicking] = useState<'origin' | 'destination' | null>(null)
  const [weight, setWeight] = useState(2)
  const [route, setRoute] = useState<RouteResponse | null>(null)
  const [routeError, setRouteError] = useState<string | null>(null)
  const [routing, setRouting] = useState(false)
  const [sharing, setSharing] = useState(false)

  const [shade, setShade] = useState<ShadeResponse | null>(null)
  const [window_, setWindow] = useState<[number, number]>([12, 18])
  const [planner, setPlanner] = useState<PlannerResponse | null>(null)
  const [focus, setFocus] = useState<LonLat | null>(null)

  useEffect(() => {
    Promise.all([api.meta(), api.pois()])
      .then(([m, p]) => {
        setMeta(m)
        setPois(p)
        setWeight(m.slider.default)
      })
      .catch((error: unknown) => setFatal(error instanceof Error ? error.message : 'The API is not reachable.'))
  }, [])

  const slot = meta?.overlay.slot_minutes ?? 15
  const overlayMinute = snapToSlot(minute, slot)

  // Route whenever both ends and the inputs are settled.
  const request = useRef(0)
  useEffect(() => {
    if (!origin || !destination) {
      setRoute(null)
      return
    }
    const id = ++request.current
    setRouting(true)
    const timer = setTimeout(() => {
      api
        .route(origin, destination, departAt(date, minute), weight, layer)
        .then((result) => {
          if (id !== request.current) return
          setRoute(result)
          setRouteError(null)
        })
        .catch((error: unknown) => {
          if (id !== request.current) return
          setRoute(null)
          setRouteError(error instanceof Error ? error.message : 'Routing failed.')
        })
        .finally(() => id === request.current && setRouting(false))
    }, 120)
    return () => clearTimeout(timer)
  }, [origin, destination, date, minute, weight, layer])

  // Shade per segment for the shade map.
  useEffect(() => {
    if (mode !== 'shade') return
    let live = true
    api.shade(month, overlayMinute, layer).then((result) => live && setShade(result), () => undefined)
    return () => {
      live = false
    }
  }, [mode, month, overlayMinute, layer])

  useEffect(() => {
    if (mode !== 'planner') return
    let live = true
    api.planner(month, window_[0], window_[1], layer).then((result) => live && setPlanner(result), () => undefined)
    return () => {
      live = false
    }
  }, [mode, month, window_, layer])

  // Warm the browser cache with the day's hourly shadow images so the slider scrubs smoothly.
  useEffect(() => {
    if (!meta || mode !== 'shade') return
    const [first, last] = meta.daylight[month - 1] ?? [420, 1140]
    for (let m = Math.ceil(first / 60) * 60; m <= last; m += 30) new Image().src = api.shadowUrl(month, m, layer)
  }, [meta, mode, month, layer])

  const onPick = useCallback(
    (point: LonLat) => {
      if (mode !== 'route') return
      const place: Place = { ...point, label: `Dropped pin ${point.lat.toFixed(4)}, ${point.lon.toFixed(4)}` }
      const target = picking ?? (!origin ? 'origin' : !destination ? 'destination' : null)
      if (target === 'origin') setOrigin(place)
      if (target === 'destination') setDestination(place)
      setPicking(null)
    },
    [mode, picking, origin, destination],
  )

  const landmarks = useMemo(() => {
    const seen = new Set<string>()
    return pois
      .filter((p) => p.name && ['park', 'cooling', 'landmark', 'school', 'rail_stop'].includes(p.kind))
      .filter((p) => (seen.has(p.name!) ? false : (seen.add(p.name!), true)))
      .map((p) => ({ lon: p.lon, lat: p.lat, label: p.name! }))
      .sort((a, b) => a.label.localeCompare(b.label))
  }, [pois])

  const dismissIntro = () => {
    setShowIntro(false)
    try {
      localStorage.setItem(SEEN_KEY, '1')
    } catch {
      // private mode: show it again next time
    }
  }

  if (fatal) {
    return (
      <div className="fatal">
        <h1>ShadeWalk cannot reach its API</h1>
        <p>{fatal}</p>
        <p>
          Start it with <code>make dev</code> and reload.
        </p>
      </div>
    )
  }
  if (!meta) return <div className="loading">Loading the pilot area…</div>

  const setNow = () => {
    const now = wallClock(new Date(), meta.timezone)
    setDate(now.date)
    setMinute(now.minute)
  }

  return (
    <div className={`app mode-${mode}`}>
      <MapView
        meta={meta}
        mode={mode}
        compact={compact}
        month={month}
        minute={overlayMinute}
        layer={layer}
        shadePct={shade?.shade_pct ?? null}
        origin={origin}
        destination={destination}
        route={route}
        planner={planner}
        pois={pois}
        focus={focus}
        onPick={onPick}
      />
      <aside className="panel" data-testid="panel">
        <header className="brand">
          <div>
            <h1>ShadeWalk</h1>
            <p>{meta.name}</p>
          </div>
          <button className="ghost" onClick={() => setShowIntro(true)} aria-label="How ShadeWalk works">
            ?
          </button>
        </header>
        <nav className="segmented" role="tablist" aria-label="View">
          {(['route', 'shade', 'planner'] as const).map((m) => (
            <button key={m} role="tab" aria-selected={mode === m} data-testid={`tab-${m}`} className={mode === m ? 'on' : ''} onClick={() => {
              setMode(m)
              setFocus(null)
            }}>
              {m === 'route' ? 'Route' : m === 'shade' ? 'Shade map' : 'Planner'}
            </button>
          ))}
        </nav>
        {mode === 'route' && (
          <RoutePanel
            meta={meta}
            landmarks={landmarks}
            origin={origin}
            destination={destination}
            picking={picking}
            date={date}
            minute={minute}
            weight={weight}
            layer={layer}
            route={route}
            error={routeError}
            busy={routing}
            onOrigin={setOrigin}
            onDestination={setDestination}
            onPicking={setPicking}
            onDate={setDate}
            onMinute={setMinute}
            onNow={setNow}
            onHottest={() => {
              setDate('2026-07-15')
              setMinute(900)
            }}
            onWeight={setWeight}
            onLayer={setLayer}
            onSwap={() => {
              setOrigin(destination)
              setDestination(origin)
            }}
            onShare={() => setSharing(true)}
          />
        )}
        {mode === 'shade' && <ShadePanel meta={meta} month={month} minute={overlayMinute} layer={layer} shade={shade} onMonth={(m) => setDate(`2026-${String(m).padStart(2, '0')}-15`)} onMinute={setMinute} onLayer={setLayer} />}
        {mode === 'planner' && <PlannerPanel month={month} window={window_} planner={planner} onMonth={(m) => setDate(`2026-${String(m).padStart(2, '0')}-15`)} onWindow={setWindow} onFocus={setFocus} />}
      </aside>
      {showIntro && <Onboarding meta={meta} onClose={dismissIntro} />}
      {sharing && route && <ShareDialog route={route} place={meta.name} onClose={() => setSharing(false)} />}
    </div>
  )
}
