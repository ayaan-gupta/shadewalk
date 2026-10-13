/**
 * Art lookup. Every image has a hand-drawn interim version in assets/interim.
 * A delivered file in assets/generated at the same path (extension aside)
 * replaces it, one file at a time, with no code change.
 */

export type AssetKey = 'landing/hero' | 'share/card-template' | `icons/${'sun-path' | 'tree' | 'bus-stop' | 'water-fountain' | 'cooling-center' | 'umbrella'}`

/** "../../assets/interim/icons/tree.svg" -> "icons/tree" */
export function assetKey(path: string): string {
  const tail = path.replace(/^.*\/assets\/(?:interim|generated)\//, '')
  return tail.replace(/\.[a-z0-9]+$/i, '')
}

export function resolveAssets(interim: Record<string, string>, generated: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [path, url] of Object.entries(interim)) out[assetKey(path)] = url
  for (const [path, url] of Object.entries(generated)) out[assetKey(path)] = url
  return out
}

function load(): Record<string, string> {
  const interim = import.meta.glob<string>('../../assets/interim/**/*.{svg,png,webp,jpg}', { eager: true, query: '?url', import: 'default' })
  const generated = import.meta.glob<string>('../../assets/generated/**/*.{svg,png,webp,jpg}', { eager: true, query: '?url', import: 'default' })
  return resolveAssets(interim, generated)
}

const table = load()

export function asset(key: AssetKey): string {
  const url = table[key]
  if (!url) throw new Error(`missing art: ${key}`)
  return url
}
