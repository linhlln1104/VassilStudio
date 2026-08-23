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

async function installAsrCreateFixture(page, fixture) {
  await page.route('**/api/v1/asr/jobs', async (route) => {
    const request = route.request()
    if (request.method() !== 'POST') return route.continue()

    fixture.creates.push({
      idempotencyKey: request.headers()['idempotency-key'] || '',
      body: request.postData() || '',
    })
    await new Promise((resolve) => setTimeout(resolve, 80))
    const now = new Date().toISOString()
    return route.fulfill({
      status: 202,
      contentType: 'application/json',
      body: JSON.stringify({
        job_id: 'asr-qa-double-submit',
        status: 'queued',
        filename: 'interview-vi.wav',
        language: 'vi',
        created_at: now,
        started_at: null,
        completed_at: null,
        error: null,
        attempt: 0,
        max_attempts: 2,
        cancel_requested: false,
        cancellation_mode: 'safe_point',
        failed_reason: null,
        progress_stage: 'queued',
        stage_started_at: now,
        text: null,
        sample_rate: 16000,
        duration_seconds: 1,
        audio_url: '/api/v1/asr/jobs/asr-qa-double-submit/audio',
      }),
    })
  })
}

async function installGenerateFixture(page, fixture) {
  await page.route('**/*', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const method = request.method()
    const json = (body, status = 200) => route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body),
    })

    if (url.pathname === '/api/v1/auth/status') {
      return json({ auth_required: false, setup_required: false, authenticated: true, api_key_auth_enabled: false, user: null })
    }
    if (url.pathname === '/model-status') {
      return json({
        ready: true,
        runtime: {
          tts_configured_languages: ['vi', 'en'],
          tts_loaded_languages: ['vi'],
          asr_configured_languages: ['vi', 'en'],
          asr_loaded_languages: ['vi'],
        },
      })
    }
    if (url.pathname === '/api/v1/voices' && method === 'GET') {
      return json([{
        voice_id: 'voice-qa-runtime',
        name: 'QA Voice',
        language: 'vi',
        reference_text: 'Xin chao tu VassilStudio.',
        reference_text_source: 'user',
        audio_size_bytes: 32044,
        sample_rate: 16000,
        duration_seconds: 1,
        created_at: '2026-08-24T00:00:00Z',
        updated_at: null,
        reference_audio_url: '',
      }])
    }
    if (url.pathname === '/api/v1/tts/jobs' && method === 'GET') {
      return json(fixture.jobs)
    }
    if (url.pathname.startsWith('/api/v1/tts/jobs/voices/') && method === 'POST') {
      fixture.creates.push({
        idempotencyKey: request.headers()['idempotency-key'] || '',
        body: request.postData() || '',
      })
      await new Promise((resolve) => setTimeout(resolve, 80))
      const now = new Date().toISOString()
      const job = {
        job_id: 'tts-qa-double-submit',
        status: 'queued',
        voice_id: 'voice-qa-runtime',
        language: 'vi',
        text: 'Day la bai kiem tra runtime integrity.',
        num_steps: 4,
        speed: 1,
        created_at: now,
        started_at: null,
        completed_at: null,
        error: null,
        attempt: 0,
        max_attempts: 2,
        cancel_requested: false,
        cancellation_mode: 'safe_point',
        failed_reason: null,
        progress_stage: 'queued',
        stage_started_at: now,
        sample_rate: null,
        duration_seconds: null,
        audio_url: null,
      }
      fixture.jobs = [job]
      return json(job, 202)
    }
    return route.continue()
  })
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
    const asrFixture = { creates: [] }
    await installAsrCreateFixture(transcribePage, asrFixture)
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

    const asrCreateResponse = transcribePage.waitForResponse((response) => (
      response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/asr/jobs'
    ))
    await transcribePage.getByRole('button', { name: 'Queue transcription' }).evaluate((button) => {
      button.click()
      button.click()
    })
    await asrCreateResponse
    await transcribePage.getByText('interview-vi.wav: Waiting in queue.', { exact: true }).waitFor({ state: 'visible' })
    if (asrFixture.creates.length !== 1) {
      throw new Error(`${viewport.name}: double submit created ${asrFixture.creates.length} ASR requests`)
    }
    if (!asrFixture.creates[0].idempotencyKey.startsWith('asr:')) {
      throw new Error(`${viewport.name}: ASR create omitted its idempotency key`)
    }
    await transcribePage.close()

    const generatePage = await browser.newPage({
      viewport: { width: viewport.width, height: viewport.height },
      colorScheme: 'light',
      reducedMotion: 'reduce',
    })
    const generateErrors = captureBrowserErrors(generatePage)
    const ttsFixture = { creates: [], jobs: [] }
    await installGenerateFixture(generatePage, ttsFixture)
    await assertPageResponse(generatePage, 'generate')
    await generatePage.locator('textarea:visible').fill('Day la bai kiem tra runtime integrity.')
    const generateButton = generatePage.getByRole('button', { name: 'Generate audio', exact: true })
    await generateButton.waitFor({ state: 'visible' })
    const ttsCreateResponse = generatePage.waitForResponse((response) => (
      response.request().method() === 'POST' && new URL(response.url()).pathname.startsWith('/api/v1/tts/jobs/voices/')
    ))
    await generateButton.evaluate((button) => {
      button.click()
      button.click()
    })
    await ttsCreateResponse
    await generatePage.getByText('Queued. Waiting in queue.', { exact: true }).filter({ visible: true }).waitFor({ state: 'visible' })
    await generatePage.getByRole('button', { name: 'Render active', exact: true }).waitFor({ state: 'visible' })
    if (ttsFixture.creates.length !== 1) {
      throw new Error(`${viewport.name}: double submit created ${ttsFixture.creates.length} TTS requests`)
    }
    if (!ttsFixture.creates[0].idempotencyKey.startsWith('tts:')) {
      throw new Error(`${viewport.name}: TTS create omitted its idempotency key`)
    }
    const completedAt = new Date().toISOString()
    ttsFixture.jobs[0] = {
      ...ttsFixture.jobs[0],
      status: 'succeeded',
      started_at: completedAt,
      completed_at: completedAt,
      progress_stage: 'succeeded',
      stage_started_at: completedAt,
      sample_rate: 24000,
      duration_seconds: 1.2,
    }
    const completedPoll = generatePage.waitForResponse((response) => (
      response.request().method() === 'GET' && new URL(response.url()).pathname === '/api/v1/tts/jobs'
    ))
    await completedPoll
    await generatePage.getByText('Succeeded. Completed.', { exact: true }).filter({ visible: true }).waitFor({ state: 'visible' })
    await generatePage.getByRole('button', { name: 'Generate audio', exact: true }).waitFor({ state: 'visible' })
    const generateLayout = await getLayoutMetrics(generatePage)
    if (generateLayout.horizontalOverflow > 1) {
      throw new Error(`${viewport.name}: Generate overflowed by ${generateLayout.horizontalOverflow}px`)
    }
    if (generateErrors.length > 0) {
      throw new Error(`${viewport.name}: Generate browser errors: ${generateErrors.join(' | ')}`)
    }
    const generateScreenshot = path.join(outputDir, `generate-runtime-${viewport.name}.png`)
    await generatePage.screenshot({ path: generateScreenshot, fullPage: true })
    await generatePage.close()

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
      asrCreateRequests: asrFixture.creates.length,
      ttsCreateRequests: ttsFixture.creates.length,
      inputDecibels,
      sessionTime,
      stoppedCleanly,
      transcribeScreenshot,
      generateScreenshot,
      realtimeScreenshot,
      transcribeLayout,
      generateLayout,
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
