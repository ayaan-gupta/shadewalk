/** Quick look at the running app: `npx tsx scripts/shot.ts out.png [width height] [tab]`. */
import { existsSync, readdirSync } from 'node:fs'
import { homedir } from 'node:os'
import path from 'node:path'
import { chromium } from 'playwright'

export function cachedChromium(): string | undefined {
  const cache = path.join(homedir(), 'Library', 'Caches', 'ms-playwright')
  if (!existsSync(cache)) return undefined
  for (const dir of readdirSync(cache).filter((d) => d.startsWith('chromium_headless_shell-')).sort().reverse()) {
    const bin = path.join(cache, dir, 'chrome-headless-shell-mac-arm64', 'chrome-headless-shell')
    if (existsSync(bin)) return bin
  }
  return undefined
}

export const GL_ARGS = ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--enable-webgl']

async function main() {
  const [out = 'shot.png', w = '1280', h = '800', tab = ''] = process.argv.slice(2)
  const browser = await chromium.launch({ executablePath: cachedChromium(), args: GL_ARGS })
  const page = await browser.newPage({ viewport: { width: Number(w), height: Number(h) } })
  page.on('console', (m) => m.type() === 'error' && console.log('console error:', m.text()))
  page.on('pageerror', (e) => console.log('page error:', e.message))
  await page.goto(process.env.DEMO_URL ?? 'http://127.0.0.1:4107', { waitUntil: 'networkidle' })
  if (tab !== 'intro') await page.click('[data-testid="start"]')
  await page.waitForSelector('[data-testid="map"][data-ready="true"]', { timeout: 20000 })
  if (tab === 'route' || tab === '') {
    await page.selectOption('[data-testid="select-origin"]', { label: 'Klyde Warren Park' })
    await page.selectOption('[data-testid="select-destination"]', { label: 'Main Street Garden' })
    await page.waitForSelector('[data-testid="results"]')
  } else if (tab !== 'intro') await page.click(`[data-testid="tab-${tab}"]`)
  await page.waitForTimeout(2500)
  await page.screenshot({ path: out })
  await browser.close()
}

if (process.argv[1]?.endsWith('shot.ts')) void main()
