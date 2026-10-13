import { clockLabel, MONTHS } from '../format'
import type { LonLat, PlannerResponse } from '../types'

interface Props {
  month: number
  window: [number, number]
  planner: PlannerResponse | null
  onMonth: (m: number) => void
  onWindow: (w: [number, number]) => void
  onFocus: (p: LonLat) => void
}

const HOURS = Array.from({ length: 17 }, (_, i) => i + 6)

export function PlannerPanel({ month, window, planner, onMonth, onWindow, onFocus }: Props) {
  return (
    <section className="stack" data-testid="planner-panel">
      <div className="group">
        <div className="row three">
          <label>
            <span>Month</span>
            <select value={month} onChange={(e) => onMonth(Number(e.target.value))}>
              {MONTHS.map((name, i) => (
                <option key={name} value={i + 1}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>From</span>
            <select value={window[0]} onChange={(e) => onWindow([Number(e.target.value), Math.max(Number(e.target.value), window[1])])}>
              {HOURS.map((h) => (
                <option key={h} value={h}>
                  {clockLabel(h * 60)}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>To</span>
            <select value={window[1]} onChange={(e) => onWindow([Math.min(window[0], Number(e.target.value)), Number(e.target.value)])}>
              {HOURS.map((h) => (
                <option key={h} value={h}>
                  {clockLabel(h * 60)}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>
      {!planner && <p className="hint lead">Ranking blocks…</p>}
      {planner && (
        <>
          <div className="stats" data-testid="planner-stats">
            <div>
              <strong>{Math.round(planner.network_shade_pct)}%</strong>
              <span>of walkway length shaded</span>
            </div>
            <div>
              <strong>{planner.low_shade_km} km</strong>
              <span>under 20% shade</span>
            </div>
            <div>
              <strong>
                {planner.unshaded_stops} of {planner.stop_count}
              </strong>
              <span>transit stops with no shade</span>
            </div>
          </div>
          <h2>Sunniest blocks where people walk and wait</h2>
          <p className="hint">Sun exposure times nearby bus stops, rail stops (x2) and schools (x3). A ranking aid, not a pedestrian count.</p>
          <ol className="blocks" data-testid="blocks">
            {planner.blocks.map((b, i) => (
              <li key={b.segment_id}>
                <button onClick={() => onFocus({ lon: b.lon, lat: b.lat })}>
                  <span className="rank">{i + 1}</span>
                  <span className="what">
                    <strong>{b.street ?? 'Unnamed walkway'}</strong>
                    <span>
                      {Math.round(b.length_m)} m · {Math.round(b.shade_pct)}% shade
                    </span>
                  </span>
                  <span className="tags">
                    {b.bus_stops > 0 && <i>{b.bus_stops} bus</i>}
                    {b.rail_stops > 0 && <i>{b.rail_stops} rail</i>}
                    {b.schools > 0 && <i>{b.schools} school</i>}
                  </span>
                </button>
              </li>
            ))}
          </ol>
          <h2>Stops with the least shade</h2>
          <ol className="blocks stops">
            {planner.stops.slice(0, 8).map((s) => (
              <li key={s.id}>
                <button onClick={() => onFocus({ lon: s.lon, lat: s.lat })}>
                  <span className="what">
                    <strong>{s.name ?? (s.kind === 'bus_stop' ? 'Bus stop' : 'Rail stop')}</strong>
                    <span>
                      {s.kind === 'bus_stop' ? 'Bus' : 'Rail'} · {Math.round(s.shade_pct)}% of the ground within 3 m shaded
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ol>
          <p className="hint">Demand counts by {planner.store === 'postgis' ? 'a PostGIS spatial join' : 'the in-memory spatial join'}.</p>
        </>
      )}
    </section>
  )
}
