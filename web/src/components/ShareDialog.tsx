import { useMemo, useState } from 'react'
import { asset } from '../assets'
import { shareCardPng, shareCardSvg } from '../share'
import type { RouteResponse } from '../types'

export function ShareDialog({ route, place, onClose }: { route: RouteResponse; place: string; onClose: () => void }) {
  const template = asset('share/card-template')
  // Inline markup, not an <img>: an SVG loaded as an image is not allowed to fetch its own template.
  const preview = useMemo(() => shareCardSvg(route, place, template), [route, place, template])
  const [busy, setBusy] = useState(false)

  const download = async () => {
    setBusy(true)
    try {
      const blob = await shareCardPng(route, place, template)
      const link = document.createElement('a')
      link.href = URL.createObjectURL(blob)
      link.download = 'shadewalk.png'
      link.click()
      setTimeout(() => URL.revokeObjectURL(link.href), 2000)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="scrim" role="dialog" aria-modal="true" aria-label="Share this walk" data-testid="share-dialog" onClick={onClose}>
      <div className="sheet share" onClick={(e) => e.stopPropagation()}>
        <div className="card-preview" role="img" aria-label="Share card preview" dangerouslySetInnerHTML={{ __html: preview }} />
        <div className="share-actions">
          <button className="ghost wide" onClick={onClose}>
            Close
          </button>
          <button className="primary" onClick={download} disabled={busy} data-testid="download-card">
            {busy ? 'Drawing…' : 'Download PNG'}
          </button>
        </div>
      </div>
    </div>
  )
}
