import type { Place } from '../App'
import { clockLabel, formatDistance, formatMinutes, minuteOfTimeInput, MONTHS, sliderCaption, timeInputValue, compass } from '../format'
import type { Layer, Meta, RouteOut, RouteResponse } from '../types'

interface Props {
  meta: Meta
  landmarks: Place[]
  origin: Place | null
  destination: Place | null
  picking: 'origin' | 'destination' | null
  date: string
  minute: number
  weight: number
  layer: Layer
  route: RouteResponse | null
  error: string | null
  busy: boolean
  onOrigin: (p: Place | null) => void
  onDestination: (p: Place | null) => void
  onPicking: (which: 'origin' | 'destination' | null) => void
  onDate: (d: string) => void
  onMinute: (m: number) => void
  onNow: () => void
  onHottest: () => void
  onWeight: (w: number) => void
  onLayer: (l: Layer) => void
  onSwap: () => void
  onShare: () => void
}

function PlaceRow(props: { tag: string; which: 'origin' | 'destination'; place: Place | null; picking: boolean; landmarks: Place[]; onPick: () => void; onChoose: (p: Place) => void }) {
  const { tag, which, place, picking, landmarks, onPick, onChoose } = props
  return (
    <div className={`row place-row ${picking ? 'picking' : ''}`}>
      <span className={`dot ${which}`}>{tag}</span>
      <button className="place-label" data-testid={`pick-${which}`} onClick={onPick}>
        {picking ? 'Tap the map…' : (place?.label ?? (which === 'origin' ? 'Tap the map for a start' : 'Tap the map for a destination'))}
      </button>
      <select
        aria-label={`Choose a ${which === 'origin' ? 'start' : 'destination'} from known places`}
        data-testid={`select-${which}`}
        value=""
        onChange={(e) => {
          const hit = landmarks[Number(e.target.value)]
          if (hit) onChoose(hit)
        }}
      >
        <option value="">Places</option>
        {landmarks.map((l, i) => (
          <option key={l.label} value={i}>
            {l.label}
          </option>
        ))}
      </select>
    </div>
  )
}

function Card(props: { title: string; kind: 'shady' | 'short'; route: RouteOut; note?: string }) {
  const { title, kind, route, note } = props
  return (
    <div className={`card ${kind}`} data-testid={`card-${kind}`}>
      <div className="card-head">
        <span className={`swatch ${kind}`} />
        <h3>{title}</h3>
        <strong>{formatMinutes(route.duration_min)}</strong>
      </div>
      <div className="bar" aria-hidden="true">
        <span style={{ width: `${route.shade_pct}%` }} />
      </div>
      <dl>
        <div>
          <dt>Distance</dt>
          <dd>{formatDistance(route.distance_m)}</dd>
        </div>
        <div>
          <dt>In shade</dt>
          <dd data-testid={`shade-${kind}`}>{Math.round(route.shade_pct)}%</dd>
        </div>
        <div>
          <dt>In direct sun</dt>
          <dd>{formatMinutes(route.sun_min)}</dd>
        </div>
      </dl>
      {note && <p className="note">{note}</p>}
    </div>
  )
}

export function RoutePanel(p: Props) {
  const { meta, route } = p
  const c = route?.comparison
  return (
    <section className="stack" data-testid="route-panel">
      <div className="group">
        <PlaceRow tag="A" which="origin" place={p.origin} picking={p.picking === 'origin'} landmarks={p.landmarks} onPick={() => p.onPicking(p.picking === 'origin' ? null : 'origin')} onChoose={p.onOrigin} />
        <PlaceRow tag="B" which="destination" place={p.destination} picking={p.picking === 'destination'} landmarks={p.landmarks} onPick={() => p.onPicking(p.picking === 'destination' ? null : 'destination')} onChoose={p.onDestination} />
        <div className="row when">
          <label>
            <span>Leave</span>
            <input type="date" value={p.date} onChange={(e) => e.target.value && p.onDate(e.target.value)} data-testid="date" />
          </label>
          <input type="time" aria-label="Departure time" value={timeInputValue(p.minute)} onChange={(e) => e.target.value && p.onMinute(minuteOfTimeInput(e.target.value))} data-testid="time" />
        </div>
        <div className="chips">
          <button onClick={p.onNow} data-testid="chip-now">Now</button>
          <button onClick={p.onHottest} data-testid="chip-july">July, 3 PM</button>
          <button onClick={p.onSwap} disabled={!p.origin || !p.destination}>Swap ends</button>
        </div>
      </div>

      <div className="group">
        <label className="slider">
          <span className="slider-head">
            <span>Shade preference</span>
            <output>{p.weight === 0 ? 'Off' : p.weight <= meta.slider.default ? 'Balanced' : 'Shade first'}</output>
          </span>
          <input type="range" min={meta.slider.min} max={meta.slider.max} step={0.25} value={p.weight} onChange={(e) => p.onWeight(Number(e.target.value))} data-testid="weight" list="weight-ticks" />
          <datalist id="weight-ticks">
            <option value={meta.slider.default} />
          </datalist>
          <span className="hint" data-testid="weight-caption">{sliderCaption(p.weight, meta.slider)}</span>
        </label>
        <label className="toggle">
          <input type="checkbox" checked={p.layer === 'all'} onChange={(e) => p.onLayer(e.target.checked ? 'all' : 'buildings')} data-testid="trees" />
          <span>Count tree shade</span>
        </label>
      </div>

      {p.error && <p className="error" role="alert">{p.error}</p>}
      {!route && !p.error && (
        <p className="hint lead">{p.busy ? 'Finding both routes…' : 'Tap the map twice: once where you start, once where you are going. Or pick from Places.'}</p>
      )}
      {route && c && (
        <div className="results" data-testid="results" aria-busy={p.busy}>
          <p className="verdict" data-testid="verdict">
            {!route.conditions.sun.up
              ? 'The sun is down at that hour, so every route is in shade.'
              : c.same_route
                ? 'The shortest way is already the shadiest one at this hour.'
                : `${formatMinutes(Math.max(c.extra_min, 0))} longer buys ${formatMinutes(Math.max(c.sun_min_saved, 0))} less in direct sun.`}
          </p>
          <Card title="Shadiest" kind="shady" route={route.shadiest} note={c.capped ? `Held to ${c.detour_cap.toFixed(1)} times the shortest distance. Raise the slider to allow more.` : undefined} />
          {!c.same_route && <Card title="Shortest" kind="short" route={route.shortest} />}
          <p className="conditions">
            {Math.round(route.conditions.temperature_c)} °C {route.conditions.temperature_source === 'forecast' ? 'forecast' : `typical for ${MONTHS[route.conditions.month - 1]}`} at {clockLabel(route.conditions.minute)}
            {route.conditions.sun.up && ` · sun ${Math.round(route.conditions.sun.elevation_deg)}° up in the ${compass(route.conditions.sun.azimuth_deg)}`} · heat factor {route.conditions.heat_factor.toFixed(2)}
          </p>
          <button className="primary" onClick={p.onShare} data-testid="share">Share this walk</button>
        </div>
      )}
    </section>
  )
}
