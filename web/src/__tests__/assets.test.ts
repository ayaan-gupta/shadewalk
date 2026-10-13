import { existsSync, readdirSync, readFileSync } from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { assetKey, resolveAssets } from '../assets'

const ROOT = path.resolve(__dirname, '../../../assets')
const KEYS = ['landing/hero', 'share/card-template', 'icons/sun-path', 'icons/tree', 'icons/bus-stop', 'icons/water-fountain', 'icons/cooling-center', 'icons/umbrella']

describe('art loader', () => {
  it('keys a file by its path under interim or generated, without the extension', () => {
    expect(assetKey('../../assets/interim/icons/tree.svg')).toBe('icons/tree')
    expect(assetKey('../../assets/generated/landing/hero.png')).toBe('landing/hero')
  })

  it('prefers a delivered file over the interim one, one file at a time', () => {
    const table = resolveAssets(
      { '../../assets/interim/icons/tree.svg': '/i/tree.svg', '../../assets/interim/icons/umbrella.svg': '/i/umbrella.svg' },
      { '../../assets/generated/icons/tree.png': '/g/tree.png' },
    )
    expect(table).toEqual({ 'icons/tree': '/g/tree.png', 'icons/umbrella': '/i/umbrella.svg' })
  })

  it('has hand-drawn interim art for every image the PRD lists, and a request for each', () => {
    const prompts = readFileSync(path.join(ROOT, 'prompts.md'), 'utf8')
    for (const key of KEYS) {
      const file = path.join(ROOT, 'interim', `${key}.svg`)
      expect(existsSync(file), key).toBe(true)
      const svg = readFileSync(file, 'utf8')
      expect(svg).toContain('<svg')
      expect(svg.toLowerCase()).not.toContain('placeholder')
      expect(prompts).toContain(`assets/generated/${key}.png`)
    }
    expect(prompts.match(/^## SW-\d{3}/gm)).toHaveLength(8)
    expect(readdirSync(path.join(ROOT, 'generated'))).toContain('.gitkeep')
  })
})
