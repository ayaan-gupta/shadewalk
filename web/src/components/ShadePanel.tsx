import { useEffect, useState } from 'react'
import { clockLabel, compass, MONTHS } from '../format'
import type { Layer, Meta, ShadeResponse } from '../types'

interface Props {
  meta: Meta
  month: number
  minute: number
  layer: Layer
  shade: ShadeResponse | null
  onMonth: (m: number) => void
  onMinute: (m: number) => void
  onLayer: (l: Layer) => void
}

/** A small sky: the horizon, the day's arc and where the sun is on it now. */
function SunDial({ azimuth, elevation }: { azimuth: number; elevation: number }) {
  const up = elevation > 0
  // East on the left, west on the right: azimuth 90 to 270 maps across the width.
  const x = 20 + ((Math.min(Math.max(azimuth, 60), 300) - 60) / 240) * 160
  const y = 84 - (Math.max(elevation, 0) / 90) * 70
  return (
    <svg viewBox="0 0 200 100" className="sundial" role="img" aria-label={up ? `Sun ${Math.round(elevation)} degrees up in the ${compass(azimuth)}` : 'Sun below the horizon'}>
      <path d="M 20 84 Q 100 -40 180 84" fill="none" stroke="#EB6B4F" strokeWidth="1.5" strokeDasharray="2 5" />
      <line x1="10" y1="84" x2="190" y2="84" stroke="#0E5C68" strokeWidth="2" strokeLinecap="round" />
      {up && <circle cx={x} cy={y} r="9" fill="#F2994A" />}
      <text x="14" y="97" fontSize="9" fill="#6B6875">E</text>
      <text x="97" y="97" fontSize="9" fill="#6B6875">S</text>
      <text x="181" y="97" fontSize="9" fill="#6B6875">W</text>
    </svg>
  )
}

export function ShadePanel({ meta, month, minute, layer, shade, onMonth, onMinute, onLayer }: Props) {
  const [first, last] = meta.daylight[month - 1] ?? [420, 1140]
  const step = meta.overlay.slot_minutes
  const [playing, setPlaying] = useState(false)

  useEffect(() => {
    if (!playing) return
    const timer = setInterval(() => onMinute(minute + step > last ? first : minute + step), 260)
    return () => clearInterval(timer)
  }, [playing, minute, first, last, step, onMinute])

  const clamped = Math.min(Math.max(minute, first), last)
  return (
    <section className="stack" data-testid="shade-panel">
      <div className="group">
        <div className="row">
          <label className="grow">
            <span>Month</span>
            <select value={month} onChange={(e) => onMonth(Number(e.target.value))} data-testid="shade-month">
              {MONTHS.map((name, i) => (
                <option key={name} value={i + 1}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <button className="ghost wide" onClick={() => setPlaying(!playing)} data-testid="play">
            {playing ? 'Pause' : 'Play the day'}
          </button>
        </div>
        <label className="slider">
          <span className="slider-head">
            <span>Time of day</span>
            <output data-testid="shade-time">{clockLabel(clamped)}</output>
          </span>
          <input type="range" min={first} max={last} step={step} value={clamped} onChange={(e) => onMinute(Number(e.target.value))} data-testid="time-slider" />
          <span className="hint">
            {clockLabel(first)} to {clockLabel(last)}, sunrise to sunset on the 15th
          </span>
        </label>
        <label className="toggle">
          <input type="checkbox" checked={layer === 'all'} onChange={(e) => onLayer(e.target.checked ? 'all' : 'buildings')} />
          <span>Count tree shade</span>
        </label>
      </div>
      <div className="group readout">
        <SunDial azimuth={shade?.sun.azimuth_deg ?? 180} elevation={shade?.sun.elevation_deg ?? 0} />
        <div>
          <strong data-testid="network-shade">{shade ? `${Math.round(shade.network_shade_pct)}%` : '…'}</strong>
          <span>of {meta.counts.km} km of walkways in shade</span>
          {shade && <span className="hint">Sun {Math.round(shade.sun.elevation_deg)}° up, {compass(shade.sun.azimuth_deg)}</span>}
        </div>
      </div>
      <div className="legend">
        <span className="ramp" />
        <div>
          <span>Full sun</span>
          <span>Full shade</span>
        </div>
        <p>
          <i className="key shadow" /> shadow on the ground <i className="key crown" /> under a tree crown
        </p>
      </div>
    </section>
  )
}
