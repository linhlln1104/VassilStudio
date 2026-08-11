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
      reducedMotion: 'reduce',
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

    const reducedMotionFrame = await page.locator('[data-qa="voiceprint-canvas"]').evaluate((canvas) =>
      canvas instanceof HTMLCanvasElement ? canvas.toDataURL() : '',
    )
    await page.waitForTimeout(160)
    const reducedMotionFrameAfterWait = await page.locator('[data-qa="voiceprint-canvas"]').evaluate((canvas) =>
      canvas instanceof HTMLCanvasElement ? canvas.toDataURL() : '',
    )
    const voiceprintStableWithReducedMotion = reducedMotionFrame === reducedMotionFrameAfterWait

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
      const voiceprint = document.querySelector('[data-qa="voiceprint-canvas"]')
      let voiceprintColoredSamples = 0

      if (voiceprint instanceof HTMLCanvasElement) {
        const context = voiceprint.getContext('2d')
        const pixels = context?.getImageData(0, 0, voiceprint.width, voiceprint.height).data
        if (pixels) {
          for (let index = 0; index < pixels.length; index += 64) {
            const red = pixels[index]
            const green = pixels[index + 1]
            const blue = pixels[index + 2]
            const alpha = pixels[index + 3]
            const chroma = Math.max(red, green, blue) - Math.min(red, green, blue)
            if (alpha > 200 && chroma > 35) voiceprintColoredSamples += 1
          }
        }
      }

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
        voiceprintCanvasReady: Boolean(
          voiceprint instanceof HTMLCanvasElement && voiceprint.width > 0 && voiceprint.height > 0,
        ),
        voiceprintColoredSamples,
      }
    })
    metrics.voiceprintStableWithReducedMotion = voiceprintStableWithReducedMotion

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
    if (!metrics.voiceprintCanvasReady || metrics.voiceprintColoredSamples < 100) {
      throw new Error(`${viewport.name}: computational voiceprint did not render a visible signal`)
    }
    if (!metrics.voiceprintStableWithReducedMotion) {
      throw new Error(`${viewport.name}: voiceprint ignored the reduced-motion preference`)
    }
    if (browserErrors.length > 0) {
      throw new Error(`${viewport.name}: browser errors: ${browserErrors.join(' | ')}`)
    }

    const screenshotPath = path.join(outputDir, `landing-${viewport.name}.png`)
    await page.screenshot({ path: screenshotPath, fullPage: true })
    report.viewports.push({ ...viewport, screenshotPath, ...metrics })
    await page.close()
  }

  const interactionPage = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
    colorScheme: 'light',
    deviceScaleFactor: 1,
    reducedMotion: 'no-preference',
  })
  const response = await interactionPage.goto(`${baseUrl}/`, { waitUntil: 'networkidle' })
  if (!response || !response.ok()) throw new Error(`interaction QA: landing returned ${response?.status() ?? 'no response'}`)

  const voiceprint = interactionPage.locator('[data-qa="voiceprint-canvas"]')
  await voiceprint.waitFor({ state: 'visible' })
  const motionFrame = await voiceprint.evaluate((canvas) => canvas instanceof HTMLCanvasElement ? canvas.toDataURL() : '')
  await interactionPage.waitForTimeout(180)
  const motionFrameAfterWait = await voiceprint.evaluate((canvas) => canvas instanceof HTMLCanvasElement ? canvas.toDataURL() : '')
  const voiceprintAnimated = motionFrame !== motionFrameAfterWait
  if (!voiceprintAnimated) throw new Error('interaction QA: voiceprint did not animate')

  await interactionPage.evaluate(() => {
    document.documentElement.style.scrollBehavior = 'auto'
    window.scrollTo(0, document.documentElement.scrollHeight)
  })
  await interactionPage.waitForTimeout(100)
  const scrollProgressRatio = await interactionPage.locator('[data-qa="scroll-progress"]').evaluate((indicator) => {
    const parentWidth = indicator.parentElement?.getBoundingClientRect().width ?? 0
    return parentWidth > 0 ? indicator.getBoundingClientRect().width / parentWidth : 0
  })
  if (scrollProgressRatio < 0.98) throw new Error(`interaction QA: scroll progress stopped at ${scrollProgressRatio}`)

  report.interactions = { voiceprintAnimated, scrollProgressRatio }
  await interactionPage.close()
} finally {
  await browser.close()
}

const reportPath = path.join(outputDir, 'report.json')
await fs.writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8')
console.log(`Landing QA passed: ${report.viewports.length} viewports`)
console.log(`Artifacts: ${outputDir}`)
