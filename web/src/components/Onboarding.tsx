import { asset, type AssetKey } from '../assets'
import type { Meta } from '../types'

const STEPS: { icon: AssetKey; title: string; body: string }[] = [
  { icon: 'icons/sun-path', title: 'Shade moves with the sun', body: 'Routes are worked out for the hour you leave, in the month you leave.' },
  { icon: 'icons/tree', title: 'Trees count', body: 'Canopy is read from aerial imagery and casts shadows like buildings do.' },
  { icon: 'icons/bus-stop', title: 'Waiting counts too', body: 'The planner view shows which stops stand in full sun.' },
  { icon: 'icons/water-fountain', title: 'Water on the way', body: 'Drinking fountains from OpenStreetMap are marked on the map.' },
  { icon: 'icons/cooling-center', title: 'Somewhere to cool down', body: 'Libraries and museums are marked as public indoor places.' },
  { icon: 'icons/umbrella', title: 'When there is no shade to find', body: 'The route says how many minutes are in direct sun, so you can plan for them.' },
]

export function Onboarding({ meta, onClose }: { meta: Meta; onClose: () => void }) {
  return (
    <div className="scrim" role="dialog" aria-modal="true" aria-labelledby="intro-title" data-testid="onboarding">
      <div className="sheet intro">
        <img className="hero" src={asset('landing/hero')} alt="A walker follows a line of shade down a sunlit street" />
        <div className="intro-body">
          <h2 id="intro-title">Walk on the shady side</h2>
          <p>
            ShadeWalk compares the shortest way with the shadiest way for the time you will actually walk. This pilot covers {meta.name}: {meta.counts.km} km of sidewalks and paths.
          </p>
          <ul className="steps">
            {STEPS.map((step) => (
              <li key={step.title}>
                <img src={asset(step.icon)} alt="" />
                <div>
                  <strong>{step.title}</strong>
                  <span>{step.body}</span>
                </div>
              </li>
            ))}
          </ul>
          <button className="primary" onClick={onClose} data-testid="start">
            Plan a walk
          </button>
        </div>
      </div>
    </div>
  )
}
