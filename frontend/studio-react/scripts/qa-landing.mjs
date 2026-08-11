import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { chromium } from 'playwright'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const repositoryRoot = path.resolve(scriptDir, '..', '..', '..')
const baseUrl = (process.env.VASSIL_QA_BASE_URL || 'http://127.0.0.1:8022').replace(/\/$/, '')
const outputDir = process.env.VASSIL_QA_OUTPUT_DIR || path.join(repositoryRoot, 'artifacts', 'ui-qa', 'landing')
const channel = process.env.PLAYWRIGHT_CHANNEL || 'chrome'
const executablePath = process.env.PLAYWRIGHT_EXECUTABLE_PATH

const viewports = [
  { name: 'desktop', width: 1440, height: 1000 },
  { name: 'tablet', width: 834, height: 1112 },
  { name: 'mobile', width: 390, height: 844 },
]

await fs.mkdir(outputDir, { recursive: true })

const browser = await chromium.launch({
  channel: executablePath ? undefined : channel,
  executablePath,
  headless: true,
})

const report = {
  baseUrl,
  generatedAt: new Date().toISOString(),
  viewports: [],
}

try {
  for (const viewport of viewports) {
    const page = await browser.newPage({
      viewport: { width: viewport.width, height: viewport.height },
      colorScheme: 'light',
      deviceScaleFactor: 1,
    })
    const browserErrors = []

    page.on('console', (message) => {
      if (message.type() === 'error') browserErrors.push(`console: ${message.text()}`)
    })
    page.on('pageerror', (error) => browserErrors.push(`page: ${error.message}`))

    const response = await page.goto(`${baseUrl}/`, { waitUntil: 'networkidle' })
    if (!response || !response.ok()) {
      throw new Error(`${viewport.name}: landing returned ${response?.status() ?? 'no response'}`)
    }

    await page.locator('h1', { hasText: 'VassilStudio' }).waitFor({ state: 'visible' })
    await page.evaluate(() => document.fonts.ready)

    for (const tabName of ['Generate', 'Transcribe', 'Realtime', 'Voices']) {
      await page.getByRole('tab', { name: tabName, exact: true }).click()
      const previewImage = page.locator('#studio-showcase-panel img')
      await previewImage.waitFor({ state: 'visible' })
      await previewImage.evaluate(async (image) => {
        if (!(image instanceof HTMLImageElement)) throw new Error('Showcase preview is not an image')
        if (!image.complete) {
          await new Promise((resolve, reject) => {
            image.addEventListener('load', resolve, { once: true })
            image.addEventListener('error', () => reject(new Error('Showcase image request failed')), { once: true })
          })
        }
        if (image.naturalWidth === 0) {
          throw new Error(`Showcase image failed for ${image.getAttribute('alt') || 'unknown tab'}`)
        }
      })
    }
    await page.getByRole('tab', { name: 'Voices', exact: true }).click()
    await page.evaluate(() => window.scrollTo(0, 0))
    await page.waitForTimeout(100)

    const metrics = await page.evaluate(() => {
      const viewportWidth = document.documentElement.clientWidth
      const horizontalOverflow = document.documentElement.scrollWidth - viewportWidth
      const brokenImages = Array.from(document.images)
        .filter((image) => !image.complete || image.naturalWidth === 0)
        .map((image) => image.currentSrc || image.src)
      const overflowingElements = Array.from(document.body.querySelectorAll('*'))
        .filter((element) => {
          const rect = element.getBoundingClientRect()
          return rect.width > 0 && (rect.left < -1 || rect.right > viewportWidth + 1)
        })
        .slice(0, 10)
        .map((element) => ({
          tag: element.tagName.toLowerCase(),
          className: typeof element.className === 'string' ? element.className : '',
          text: element.textContent?.trim().slice(0, 80) || '',
        }))
      const hero = document.querySelector('[data-qa="landing-hero"]')?.getBoundingClientRect()
      const heroContent = document.querySelector('[data-qa="hero-content"]')?.getBoundingClientRect()
      const productStage = document.querySelector('[data-qa="product-stage"]')?.getBoundingClientRect()

      return {
        documentWidth: document.documentElement.scrollWidth,
        horizontalOverflow,
        brokenImages,
        overflowingElements,
        heroHeight: hero?.height ?? 0,
        heroContentInsideHero: Boolean(
          hero &&
          heroContent &&
          heroContent.top >= hero.top - 1 &&
          heroContent.bottom <= hero.bottom + 1,
        ),
        productProofVisibleInFirstViewport: Boolean(
          productStage && productStage.top < window.innerHeight && productStage.bottom > 0,
        ),
      }
    })

    if (metrics.horizontalOverflow > 1) {
      throw new Error(`${viewport.name}: horizontal overflow is ${metrics.horizontalOverflow}px`)
    }
    if (metrics.brokenImages.length > 0) {
      throw new Error(`${viewport.name}: broken images: ${metrics.brokenImages.join(', ')}`)
    }
    if (!metrics.heroContentInsideHero) {
      throw new Error(`${viewport.name}: hero content leaves its fixed visual boundary`)
    }
    if (!metrics.productProofVisibleInFirstViewport) {
      throw new Error(`${viewport.name}: actual product proof is not visible in the first viewport`)
    }
    if (browserErrors.length > 0) {
      throw new Error(`${viewport.name}: browser errors: ${browserErrors.join(' | ')}`)
    }

    const screenshotPath = path.join(outputDir, `landing-${viewport.name}.png`)
    await page.screenshot({ path: screenshotPath, fullPage: true })
    report.viewports.push({ ...viewport, screenshotPath, ...metrics })
    await page.close()
  }
} finally {
  await browser.close()
}

const reportPath = path.join(outputDir, 'report.json')
await fs.writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8')
console.log(`Landing QA passed: ${report.viewports.length} viewports`)
console.log(`Artifacts: ${outputDir}`)
