import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { chromium } from 'playwright'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const repositoryRoot = path.resolve(scriptDir, '..', '..', '..')
const baseUrl = (process.env.VASSIL_QA_BASE_URL || 'http://127.0.0.1:8022').replace(/\/$/, '')
const outputDir = process.env.VASSIL_QA_OUTPUT_DIR || path.join(repositoryRoot, 'artifacts', 'ui-qa', 'audio-workflows')
const channel = process.env.PLAYWRIGHT_CHANNEL || 'chrome'
const executablePath = process.env.PLAYWRIGHT_EXECUTABLE_PATH

const viewports = [
  { name: 'desktop', width: 1440, height: 1000 },
  { name: 'mobile', width: 390, height: 844 },
]

function createWaveBuffer(seconds = 1, sampleRate = 16000) {
  const sampleCount = seconds * sampleRate
  const dataBytes = sampleCount * 2
  const buffer = Buffer.alloc(44 + dataBytes)
  buffer.write('RIFF', 0)
  buffer.writeUInt32LE(36 + dataBytes, 4)
  buffer.write('WAVE', 8)
  buffer.write('fmt ', 12)
  buffer.writeUInt32LE(16, 16)
  buffer.writeUInt16LE(1, 20)
  buffer.writeUInt16LE(1, 22)
  buffer.writeUInt32LE(sampleRate, 24)
  buffer.writeUInt32LE(sampleRate * 2, 28)
  buffer.writeUInt16LE(2, 32)
  buffer.writeUInt16LE(16, 34)
  buffer.write('data', 36)
  buffer.writeUInt32LE(dataBytes, 40)

  for (let index = 0; index < sampleCount; index += 1) {
    const sample = Math.round(Math.sin(2 * Math.PI * 220 * index / sampleRate) * 5000)
    buffer.writeInt16LE(sample, 44 + index * 2)
  }
  return buffer
}

function installRealtimeFixture() {
  class QaWebSocket {
    static CONNECTING = 0
    static OPEN = 1
    static CLOSING = 2
    static CLOSED = 3

    readyState = QaWebSocket.CONNECTING
    binaryType = 'blob'
    onopen = null
    onmessage = null
    onerror = null
    onclose = null
    emittedTranscript = false

    constructor(url) {
      this.url = url
      window.setTimeout(() => {
        this.readyState = QaWebSocket.OPEN
        this.onopen?.({ type: 'open' })
        this.onmessage?.({
          data: JSON.stringify({
            type: 'ready',
            protocol: 'qa',
            sample_rate: 16000,
            encoding: 'pcm_f32le',
            chunk_seconds: 0.5,
            language: 'vi',
          }),
        })
      }, 30)
    }

    send(payload) {
      if (typeof payload === 'string') {
        const message = JSON.parse(payload)
        if (message.type === 'close') {
          window.setTimeout(() => {
            this.onmessage?.({ data: JSON.stringify({ type: 'closed' }) })
            this.close()
          }, 30)
        }
        return
      }

      if (!this.emittedTranscript) {
        this.emittedTranscript = true
        window.setTimeout(() => {
          this.onmessage?.({
            data: JSON.stringify({
              type: 'transcript',
              sequence: 1,
              text: 'QA microphone signal received.',
              final: true,
              skipped: false,
              duration_seconds: 0.5,
              rms: 0.08,
              language: 'vi',
            }),
          })
        }, 80)
      }
    }

    close() {
      if (this.readyState === QaWebSocket.CLOSED) return
      this.readyState = QaWebSocket.CLOSED
      this.onclose?.({ type: 'close' })
    }
  }

  Object.defineProperty(window, 'WebSocket', { configurable: true, value: QaWebSocket })
  Object.defineProperty(navigator.mediaDevices, 'getUserMedia', {
    configurable: true,
    value: async () => {
      const context = new AudioContext()
      await context.resume()
      const oscillator = context.createOscillator()
      const gain = context.createGain()
      const destination = context.createMediaStreamDestination()
      oscillator.frequency.value = 220
      gain.gain.value = 0.15
      oscillator.connect(gain)
      gain.connect(destination)
      oscillator.start()
      window.__vassilQaAudio = { context, oscillator, gain }
      return destination.stream
    },
  })
}

function captureBrowserErrors(page) {
  const errors = []
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(`console: ${message.text()}`)
  })
  page.on('pageerror', (error) => errors.push(`page: ${error.message}`))
  return errors
}

async function assertPageResponse(page, route) {
  const response = await page.goto(`${baseUrl}/studio#/${route}`, { waitUntil: 'networkidle' })
  if (!response || !response.ok()) {
    throw new Error(`${route}: Studio returned ${response?.status() ?? 'no response'}`)
  }
  await page.evaluate(() => document.fonts.ready)
}

async function getLayoutMetrics(page) {
  return page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: document.documentElement.clientWidth,
    horizontalOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  }))
}

await fs.mkdir(outputDir, { recursive: true })

const browser = await chromium.launch({
  channel: executablePath ? undefined : channel,
  executablePath,
  headless: true,
  args: ['--autoplay-policy=no-user-gesture-required'],
})

const report = {
  baseUrl,
  generatedAt: new Date().toISOString(),
  viewports: [],
}

try {
  for (const viewport of viewports) {
    const transcribePage = await browser.newPage({
      viewport: { width: viewport.width, height: viewport.height },
      colorScheme: 'light',
      reducedMotion: 'reduce',
    })
    const transcribeErrors = captureBrowserErrors(transcribePage)
    await assertPageResponse(transcribePage, 'transcribe')
    await transcribePage.locator('input[type="file"]').setInputFiles({
      name: 'interview-vi.wav',
      mimeType: 'audio/wav',
      buffer: createWaveBuffer(),
    })
    const audioPreview = transcribePage.locator('audio')
    await audioPreview.waitFor({ state: 'visible' })
    await transcribePage.waitForFunction(() => {
      const audio = document.querySelector('audio')
      return audio instanceof HTMLAudioElement && Number.isFinite(audio.duration) && audio.duration >= 0.9
    })
    await transcribePage.waitForTimeout(200)

    const audioDuration = await audioPreview.evaluate((audio) => audio instanceof HTMLAudioElement ? audio.duration : 0)
    const queueButtonEnabled = await transcribePage.getByRole('button', { name: 'Queue transcription' }).isEnabled()
    const transcribeLayout = await getLayoutMetrics(transcribePage)
    if (!queueButtonEnabled || audioDuration < 0.9) {
      throw new Error(`${viewport.name}: staged transcription audio was not ready to queue`)
    }
    if (transcribeLayout.horizontalOverflow > 1) {
      throw new Error(`${viewport.name}: Transcribe overflowed by ${transcribeLayout.horizontalOverflow}px`)
    }
    if (transcribeErrors.length > 0) {
      throw new Error(`${viewport.name}: Transcribe browser errors: ${transcribeErrors.join(' | ')}`)
    }

    const transcribeScreenshot = path.join(outputDir, `transcribe-staged-${viewport.name}.png`)
    await transcribePage.screenshot({ path: transcribeScreenshot, fullPage: true })
    await transcribePage.close()

    const realtimePage = await browser.newPage({
      viewport: { width: viewport.width, height: viewport.height },
      colorScheme: 'light',
      reducedMotion: 'reduce',
    })
    const realtimeErrors = captureBrowserErrors(realtimePage)
    await realtimePage.addInitScript(installRealtimeFixture)
    await assertPageResponse(realtimePage, 'realtime')
    await realtimePage.getByRole('button', { name: 'Start session' }).click()
    await realtimePage.getByRole('button', { name: 'Stop and finalize' }).waitFor({ state: 'visible' })
    await realtimePage.getByText('Active for this session', { exact: true }).waitFor({ state: 'visible' })
    await realtimePage.getByText('QA microphone signal received.', { exact: true }).first().waitFor({ state: 'visible' })
    await realtimePage.waitForFunction(() => {
      const value = Number(document.querySelector('[data-qa="input-level-meter"]')?.getAttribute('aria-valuenow'))
      return Number.isFinite(value) && value > -55
    })
    await realtimePage.waitForFunction(() => document.querySelector('[data-qa="session-time"]')?.textContent !== '0:00')

    const realtimeLayout = await getLayoutMetrics(realtimePage)
    const inputDecibels = Number(await realtimePage.locator('[data-qa="input-level-meter"]').getAttribute('aria-valuenow'))
    const sessionTime = await realtimePage.locator('[data-qa="session-time"]').textContent()
    if (realtimeLayout.horizontalOverflow > 1) {
      throw new Error(`${viewport.name}: Realtime overflowed by ${realtimeLayout.horizontalOverflow}px`)
    }
    if (realtimeErrors.length > 0) {
      throw new Error(`${viewport.name}: Realtime browser errors: ${realtimeErrors.join(' | ')}`)
    }

    const realtimeScreenshot = path.join(outputDir, `realtime-listening-${viewport.name}.png`)
    await realtimePage.screenshot({ path: realtimeScreenshot, fullPage: true })
    await realtimePage.getByRole('button', { name: 'Stop and finalize' }).click()
    await realtimePage.getByRole('button', { name: 'Start session' }).waitFor({ state: 'visible' })
    const stoppedCleanly = await realtimePage.locator('[data-qa="input-level-meter"]').count() === 0
    if (!stoppedCleanly) throw new Error(`${viewport.name}: Realtime input monitor remained active after stop`)
    await realtimePage.close()

    report.viewports.push({
      ...viewport,
      audioDuration,
      queueButtonEnabled,
      inputDecibels,
      sessionTime,
      stoppedCleanly,
      transcribeScreenshot,
      realtimeScreenshot,
      transcribeLayout,
      realtimeLayout,
    })
  }
} finally {
  await browser.close()
}

const reportPath = path.join(outputDir, 'report.json')
await fs.writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8')
console.log(`Audio workflow QA passed: ${report.viewports.length} viewports`)
console.log(`Artifacts: ${outputDir}`)
