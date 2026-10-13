/**
 * Drives the real app in a headless browser and records docs/demo.gif plus the
 * README screenshots. Needs `make dev` running and network access for the base map.
 *
 *   make dev &
 *   make demo
 */
import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright'
import sharp from 'sharp'
import type { Frame } from './lib/gif'
import { encodeGif } from './lib/gif'
import { cachedChromium, GL_ARGS } from './shot'

const BASE = process.env.DEMO_URL ?? 'http://127.0.0.1:4107'
const WIDTH = 880
const HEIGHT = 560
const DOCS = path.resolve(process.cwd(), '..', 'docs')

async function main() {
  mkdirSync(DOCS, { recursive: true })
  const browser = await chromium.launch({ executablePath: cachedChromium(), args: GL_ARGS })
  const context = await browser.newContext({ viewport: { width: WIDTH, height: HEIGHT }, deviceScaleFactor: 1, acceptDownloads: true })
  const page = await context.newPage()
  const frames: Frame[] = []

  const shoot = async (delay: number) => {
    const png = await page.screenshot({ type: 'png' })
    const { data } = await sharp(png).ensureAlpha().raw().toBuffer({ resolveWithObject: true })
    frames.push({ rgba: new Uint8Array(data), delay })
  }
  const hold = async (ms: number, every = 250) => {
    for (let t = 0; t < ms; t += every) {
      await shoot(every)
      await page.waitForTimeout(60)
    }
  }
  const still = async (name: string, size?: { width: number; height: number }) => {
    if (size) await page.setViewportSize(size)
    await page.waitForTimeout(size ? 2200 : 300)
    await page.screenshot({ path: path.join(DOCS, name) })
    if (size) await page.setViewportSize({ width: WIDTH, height: HEIGHT })
  }
  const settle = async () => {
    await page.waitForFunction(() => document.querySelector('[data-testid="results"]')?.getAttribute('aria-busy') === 'false')
    await page.waitForTimeout(1100)
  }
  const numbers = async () => ({
    shadiest: await page.textContent('[data-testid="shade-shady"]'),
    shortest: await page.textContent('[data-testid="shade-short"]').catch(() => null),
    verdict: await page.textContent('[data-testid="verdict"]'),
  })

  // Scene 1: first run.
  await page.goto(BASE, { waitUntil: 'networkidle' })
  await page.waitForSelector('[data-testid="map"][data-ready="true"]', { timeout: 30000 })
  await page.waitForTimeout(1500)
  await hold(1500)
  await still('screen-onboarding.png', { width: 1280, height: 800 })
  await page.click('[data-testid="start"]')
  await hold(500)

  // Scene 2: a walk across downtown at 3 PM in July.
  await page.selectOption('[data-testid="select-origin"]', { label: 'Klyde Warren Park' })
  await hold(400)
  await page.selectOption('[data-testid="select-destination"]', { label: 'Main Street Garden' })
  await settle()
  await hold(2600)
  const july = await numbers()
  await still('screen-route.png', { width: 1280, height: 800 })

  // Scene 3: the same walk at 9 AM, when the shadows fall the other way.
  await page.fill('[data-testid="time"]', '09:00')
  await settle()
  await hold(2200)
  const morning = await numbers()
  await page.fill('[data-testid="time"]', '15:00')
  await settle()

  // Scene 4: raise the slider past the default and the detour cap relaxes.
  for (const w of ['3', '4', '5']) {
    await page.fill('[data-testid="weight"]', w)
    await shoot(200)
  }
  await settle()
  await hold(2000)
  const raised = { ...(await numbers()), caption: await page.textContent('[data-testid="weight-caption"]') }
  await page.fill('[data-testid="weight"]', '2')
  await settle()

  // Scene 5: the share card.
  await page.locator('[data-testid="share"]').scrollIntoViewIfNeeded()
  await page.click('[data-testid="share"]')
  await page.waitForTimeout(500)
  await hold(1600)
  await still('screen-share.png', { width: 1280, height: 800 })
  const [download] = await Promise.all([page.waitForEvent('download'), page.click('[data-testid="download-card"]')])
  await download.saveAs(path.join(DOCS, 'share-card.png'))
  await page.keyboard.press('Escape')
  await page.mouse.click(8, 8)
  await page.locator('[data-testid="panel"]').evaluate((el) => el.scrollTo({ top: 0 }))

  // Scene 6: the shade map through a July day.
  await page.click('[data-testid="tab-shade"]')
  await page.waitForTimeout(1500)
  const range = page.locator('[data-testid="time-slider"]')
  const first = Number(await range.getAttribute('min'))
  const last = Number(await range.getAttribute('max'))
  const day: Record<string, string | null> = {}
  for (let minute = Math.ceil(first / 30) * 30; minute <= last; minute += 30) {
    await range.fill(String(minute))
    await page.waitForTimeout(650)
    await shoot(260)
    if (minute % 180 === 0) day[String(minute / 60)] = await page.textContent('[data-testid="network-shade"]')
  }
  await range.fill('900')
  await page.waitForTimeout(900)
  await hold(1200)
  await still('screen-shade.png', { width: 1280, height: 800 })

  // Scene 7: the planner view.
  await page.click('[data-testid="tab-planner"]')
  await page.waitForSelector('[data-testid="blocks"] li')
  await page.waitForTimeout(900)
  await hold(2200)
  await still('screen-planner.png', { width: 1280, height: 800 })
  await page.click('[data-testid="blocks"] li:first-child button')
  await page.waitForTimeout(1200)
  await hold(1800)
  const stats = await page.textContent('[data-testid="planner-stats"]')

  // A phone-width still of the route view.
  await page.click('[data-testid="tab-route"]')
  await still('screen-phone.png', { width: 390, height: 844 })

  await browser.close()
  const gif = encodeGif(frames, WIDTH, HEIGHT)
  writeFileSync(path.join(DOCS, 'demo.gif'), gif)
  console.log(JSON.stringify({ frames: frames.length, gifMB: +(gif.length / 1024 / 1024).toFixed(2), july, morning, raised, shadeByHour: day, plannerStats: stats }, null, 2))
}

void main()
