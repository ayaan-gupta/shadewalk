import { clockLabel, formatDistance, formatMinutes, MONTHS } from './format'
import type { RouteResponse } from './types'

export const CARD_WIDTH = 1200
export const CARD_HEIGHT = 630

function escapeXml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

export function shareLines(route: RouteResponse, place: string): { headline: string; detail: string; context: string } {
  const { shadiest, shortest, comparison, conditions } = route
  const headline = `${Math.round(shadiest.shade_pct)}% of this walk is in shade`
  const detail = comparison.same_route
    ? `${formatDistance(shadiest.distance_m)}, ${formatMinutes(shadiest.duration_min)}. The shortest way is already the shadiest.`
    : `${formatDistance(shadiest.distance_m)}, ${formatMinutes(shadiest.duration_min)}. ${formatMinutes(Math.max(comparison.extra_min, 0))} longer than the shortest way, ${formatMinutes(Math.max(comparison.sun_min_saved, 0))} less in direct sun (${Math.round(shortest.shade_pct)}% shade).`
  const context = `${place} · ${MONTHS[conditions.month - 1]} at ${clockLabel(conditions.minute)} · ${Math.round(conditions.temperature_c)} °C`
  return { headline, detail, context }
}

function wrap(text: string, max: number): string[] {
  const lines: string[] = []
  let line = ''
  for (const word of text.split(' ')) {
    if ((line + ' ' + word).trim().length > max && line) {
      lines.push(line)
      line = word
    } else line = (line + ' ' + word).trim()
  }
  if (line) lines.push(line)
  return lines
}

/** The share card as one SVG document: the template image with the route's numbers set over its quiet left side. */
export function shareCardSvg(route: RouteResponse, place: string, templateHref: string): string {
  const { headline, detail, context } = shareLines(route, place)
  const font = `-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif`
  const head = wrap(headline, 20)
  const body = wrap(detail, 46)
  const bodyY = 178 + head.length * 76 + 24
  return [
    `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="${CARD_WIDTH}" height="${CARD_HEIGHT}" viewBox="0 0 ${CARD_WIDTH} ${CARD_HEIGHT}">`,
    `<image href="${escapeXml(templateHref)}" xlink:href="${escapeXml(templateHref)}" width="${CARD_WIDTH}" height="${CARD_HEIGHT}" preserveAspectRatio="xMidYMid slice"/>`,
    `<text x="64" y="96" font-family="${font}" font-size="28" font-weight="700" fill="#0E5C68" letter-spacing="1">SHADEWALK</text>`,
    ...head.map((line, i) => `<text x="64" y="${178 + i * 76}" font-family="${font}" font-size="68" font-weight="700" fill="#2B2A33">${escapeXml(line)}</text>`),
    ...body.map((line, i) => `<text x="64" y="${bodyY + i * 40}" font-family="${font}" font-size="29" fill="#4A4852">${escapeXml(line)}</text>`),
    `<text x="64" y="530" font-family="${font}" font-size="24" fill="#6B6875">${escapeXml(context)}</text>`,
    `</svg>`,
  ].join('')
}

async function asDataUrl(url: string): Promise<string> {
  const blob = await (await fetch(url)).blob()
  return await new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(blob)
  })
}

/** Rasterise the card in the browser. The template is inlined first, because an SVG drawn to a canvas cannot fetch. */
export async function shareCardPng(route: RouteResponse, place: string, templateUrl: string): Promise<Blob> {
  const svg = shareCardSvg(route, place, await asDataUrl(templateUrl))
  const image = new Image()
  image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`
  await image.decode()
  const canvas = document.createElement('canvas')
  canvas.width = CARD_WIDTH
  canvas.height = CARD_HEIGHT
  canvas.getContext('2d')!.drawImage(image, 0, 0, CARD_WIDTH, CARD_HEIGHT)
  return await new Promise((resolve, reject) => canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('could not encode the card'))), 'image/png'))
}
