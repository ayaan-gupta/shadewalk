/** Phone-width still of the route view, loaded at phone size from the start: `npx tsx scripts/phone.ts`. */
import path from 'node:path'
import { chromium } from 'playwright'
import { cachedChromium, GL_ARGS } from './shot'

const browser = await chromium.launch({ executablePath: cachedChromium(), args: GL_ARGS })
const page = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true })
await page.goto(process.env.DEMO_URL ?? 'http://127.0.0.1:4107', { waitUntil: 'networkidle' })
await page.click('[data-testid="start"]')
await page.waitForSelector('[data-testid="map"][data-ready="true"]')
await page.selectOption('[data-testid="select-origin"]', { label: 'Klyde Warren Park' })
await page.selectOption('[data-testid="select-destination"]', { label: 'Main Street Garden' })
await page.waitForSelector('[data-testid="results"]')
await page.waitForTimeout(2500)
await page.locator('[data-testid="panel"]').evaluate((el) => el.scrollTo({ top: 250 }))
await page.waitForTimeout(300)
await page.screenshot({ path: path.resolve(process.cwd(), '..', 'docs', 'screen-phone.png') })
await browser.close()
