import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { chromium } from 'playwright'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const repositoryRoot = path.resolve(scriptDir, '..', '..', '..')
const baseUrl = (process.env.VASSIL_QA_BASE_URL || 'http://127.0.0.1:8022').replace(/\/$/, '')
const outputDir = process.env.VASSIL_QA_OUTPUT_DIR || path.join(repositoryRoot, 'artifacts', 'ui-qa', 'jobs')
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
  return buffer
}

function jobFixture() {
  const ttsJobs = [
    {
      job_id: 'tts-20260823-success-abcdef12',
      status: 'succeeded',
      voice_id: 'voice-hanoi-editorial-7ab82c10',
      language: 'vi',
      text: 'VassilStudio keeps every voice render inside your local workspace.',
      num_steps: 18,
      speed: 1.05,
      created_at: '2026-08-23T08:20:00Z',
      started_at: '2026-08-23T08:20:02Z',
      completed_at: '2026-08-23T08:20:06Z',
      error: null,
      attempt: 1,
      max_attempts: 3,
      cancel_requested: false,
      cancellation_mode: 'safe_point',
      failed_reason: null,
      progress_stage: 'succeeded',
      stage_started_at: '2026-08-23T08:20:06Z',
      sample_rate: 24000,
      duration_seconds: 4.2,
      audio_url: '/api/v1/tts/jobs/tts-20260823-success-abcdef12/audio',
    },
    {
      job_id: 'tts-20260823-failed-deadbeef',
      status: 'failed',
      voice_id: 'voice-saigon-narrator-1f119ecc',
      language: 'vi',
      text: 'A failed render remains available for diagnosis and recovery.',
      num_steps: 16,
      speed: 1,
      created_at: '2026-08-23T08:10:00Z',
      started_at: '2026-08-23T08:10:01Z',
      completed_at: '2026-08-23T08:10:03Z',
      error: 'Vocoder asset is missing for language vi.',
      attempt: 3,
      max_attempts: 3,
      cancel_requested: false,
      cancellation_mode: 'safe_point',
      failed_reason: 'model_dependency_missing',
      progress_stage: 'failed',
      stage_started_at: '2026-08-23T08:10:03Z',
      sample_rate: null,
      duration_seconds: null,
      audio_url: null,
    },
  ]
  const asrJobs = [
    {
      job_id: 'asr-20260823-running-0a11ce55',
      status: 'running',
      filename: 'field-note-vi.wav',
      language: 'vi',
      created_at: '2026-08-23T08:30:00Z',
      started_at: '2026-08-23T08:30:02Z',
      completed_at: null,
      error: null,
      attempt: 1,
      max_attempts: 3,
      cancel_requested: false,
      cancellation_mode: 'safe_point',
      failed_reason: null,
      progress_stage: 'running_model',
      stage_started_at: '2026-08-23T08:30:03Z',
      text: null,
      sample_rate: 16000,
      duration_seconds: null,
      audio_url: '/api/v1/asr/jobs/asr-20260823-running-0a11ce55/audio',
    },
    {
      job_id: 'asr-20260823-success-1234abcd',
      status: 'succeeded',
      filename: 'interview-en.wav',
      language: 'en',
      created_at: '2026-08-23T07:30:00Z',
      started_at: '2026-08-23T07:30:01Z',
      completed_at: '2026-08-23T07:30:05Z',
      error: null,
      attempt: 1,
      max_attempts: 3,
      cancel_requested: false,
      cancellation_mode: 'safe_point',
      failed_reason: null,
      progress_stage: 'succeeded',
      stage_started_at: '2026-08-23T07:30:05Z',
      text: 'The local recording is ready for editorial review.',
      sample_rate: 16000,
      duration_seconds: 12.4,
      audio_url: '/api/v1/asr/jobs/asr-20260823-success-1234abcd/audio',
    },
    {
      job_id: 'asr-20260823-cancelled-baadf00d',
      status: 'cancelled',
      filename: 'cancelled-take.wav',
      language: 'en',
      created_at: '2026-08-23T07:00:00Z',
      started_at: null,
      completed_at: '2026-08-23T07:00:02Z',
      error: null,
      attempt: 1,
      max_attempts: 3,
      cancel_requested: true,
      cancellation_mode: 'safe_point',
      failed_reason: 'cancelled',
      progress_stage: 'cancelled',
      stage_started_at: '2026-08-23T07:00:02Z',
      text: null,
      sample_rate: null,
      duration_seconds: null,
      audio_url: '/api/v1/asr/jobs/asr-20260823-cancelled-baadf00d/audio',
    },
  ]

  return {
    ttsJobs,
    asrJobs,
    ttsCreates: [],
    asrCreates: [],
    audioReads: [],
    audioApiKeys: [],
    audioFailuresRemaining: 1,
  }
}

async function installApiFixture(page, fixture) {
  const wave = createWaveBuffer()
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
      return json({ auth_required: false, setup_required: false, authenticated: true, user: null })
    }
    if (url.pathname === '/model-status') {
      return json({ ready: true, runtime: { asr_loaded: true, tts_loaded: true } })
    }
    if (url.pathname === '/api/v1/tts/jobs' && method === 'GET') {
      return json(fixture.ttsJobs)
    }
    if (url.pathname === '/api/v1/asr/jobs' && method === 'GET') {
      return json(fixture.asrJobs)
    }
    if (url.pathname.startsWith('/api/v1/tts/jobs/voices/') && method === 'POST') {
      fixture.ttsCreates.push({
        path: url.pathname,
        body: request.postData() || '',
        idempotencyKey: request.headers()['idempotency-key'] || '',
      })
      const source = fixture.ttsJobs.find((job) => job.job_id === 'tts-20260823-failed-deadbeef')
      const created = {
        ...source,
        job_id: `tts-qa-retry-${fixture.ttsCreates.length}`,
        status: 'queued',
        created_at: new Date().toISOString(),
        started_at: null,
        completed_at: null,
        error: null,
        attempt: 0,
        failed_reason: null,
        progress_stage: 'queued',
        stage_started_at: new Date().toISOString(),
      }
      fixture.ttsJobs.unshift(created)
      return json(created, 202)
    }
    if (url.pathname === '/api/v1/asr/jobs' && method === 'POST') {
      fixture.asrCreates.push({
        path: url.pathname,
        body: request.postData() || '',
        idempotencyKey: request.headers()['idempotency-key'] || '',
      })
      const created = {
        ...fixture.asrJobs.find((job) => job.job_id === 'asr-20260823-success-1234abcd'),
        job_id: `asr-qa-retry-${fixture.asrCreates.length}`,
        status: 'queued',
        created_at: new Date().toISOString(),
        started_at: null,
        completed_at: null,
        text: null,
        duration_seconds: null,
        progress_stage: 'queued',
        stage_started_at: new Date().toISOString(),
      }
      fixture.asrJobs.unshift(created)
      return json(created, 202)
    }
    if (/^\/api\/v1\/(tts|asr)\/jobs\/[^/]+\/audio$/.test(url.pathname) && method === 'GET') {
      fixture.audioReads.push(url.pathname)
      fixture.audioApiKeys.push(request.headers()['x-vassil-api-key'] || null)
      if (url.pathname.includes('tts-20260823-success-abcdef12') && fixture.audioFailuresRemaining > 0) {
        fixture.audioFailuresRemaining -= 1
        return json({ detail: 'Audio temporarily unavailable.' }, 503)
      }
      return route.fulfill({ status: 200, contentType: 'audio/wav', body: wave })
    }

    return route.continue()
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

async function assertStudioResponse(page) {
  const response = await page.goto(`${baseUrl}/studio#/jobs`, { waitUntil: 'networkidle' })
  if (!response || !response.ok()) {
    throw new Error(`Studio returned ${response?.status() ?? 'no response'}`)
  }
  await page.evaluate(() => document.fonts.ready)
  await page.getByText('Queue activity', { exact: true }).waitFor({ state: 'visible' })
}

async function layoutMetrics(page) {
  return page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: document.documentElement.clientWidth,
    horizontalOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  }))
}

function assertMultipartBody(body, expected, label) {
  for (const value of expected) {
    if (!body.includes(value)) {
      throw new Error(`${label}: multipart payload did not include ${value}`)
    }
  }
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
    const page = await browser.newPage({
      viewport: { width: viewport.width, height: viewport.height },
      colorScheme: 'light',
      reducedMotion: 'reduce',
    })
    await page.addInitScript(() => {
      window.sessionStorage.setItem('vassil.sessionApiKey', 'jobs-qa-api-key')
    })
    const fixture = jobFixture()
    const browserErrors = captureBrowserErrors(page)
    await installApiFixture(page, fixture)
    await assertStudioResponse(page)

    await page.getByText('5 total', { exact: true }).waitFor({ state: 'visible' })
    await page.getByRole('button', { name: 'Failed', exact: true }).click()
    await page.getByRole('button', { name: /Inspect TTS job/ }).click()

    let dialog = page.getByRole('dialog')
    await dialog.getByRole('heading', { name: 'Job details' }).waitFor({ state: 'visible' })
    await dialog.getByRole('heading', { name: 'Failure details' }).waitFor({ state: 'visible' })
    await dialog.getByText('Vocoder asset is missing for language vi.', { exact: true }).waitFor({ state: 'visible' })
    await dialog.getByText('Attempt 3 of 3', { exact: false }).waitFor({ state: 'visible' })
    await page.waitForTimeout(350)

    const dialogBox = await dialog.boundingBox()
    if (!dialogBox || dialogBox.width > viewport.width + 1) {
      throw new Error(`${viewport.name}: job inspector exceeded the viewport width`)
    }
    const footerActionBoxes = await Promise.all([
      dialog.getByRole('button', { name: 'Delete job', exact: true }).boundingBox(),
      dialog.getByRole('button', { name: 'Use in Generate', exact: true }).boundingBox(),
      dialog.getByRole('button', { name: 'Run again', exact: true }).boundingBox(),
    ])
    if (footerActionBoxes.some((box) => !box)) {
      throw new Error(`${viewport.name}: one or more recovery actions were not visible`)
    }
    const actionTops = footerActionBoxes.map((box) => box.y)
    if (Math.max(...actionTops) - Math.min(...actionTops) > 2) {
      throw new Error(`${viewport.name}: recovery actions wrapped onto multiple rows`)
    }
    const failedScreenshot = path.join(outputDir, `jobs-failed-inspector-${viewport.name}.png`)
    await page.screenshot({ path: failedScreenshot })

    const ttsRecoveryResponse = page.waitForResponse((response) => {
      const request = response.request()
      return request.method() === 'POST' && new URL(response.url()).pathname.startsWith('/api/v1/tts/jobs/voices/')
    })
    await dialog.getByRole('button', { name: 'Run again', exact: true }).click()
    await ttsRecoveryResponse
    await page.getByText('Job accepted', { exact: true }).waitFor({ state: 'visible' })
    if (fixture.ttsCreates.length !== 1) {
      throw new Error(`${viewport.name}: expected one TTS recovery request`)
    }
    assertMultipartBody(
      fixture.ttsCreates[0].body,
      ['A failed render remains available for diagnosis and recovery.', 'num_steps', '16', 'speed', '1'],
      `${viewport.name} TTS recovery`,
    )
    if (!fixture.ttsCreates[0].path.endsWith('/voice-saigon-narrator-1f119ecc')) {
      throw new Error(`${viewport.name}: TTS recovery used the wrong voice profile`)
    }
    if (!fixture.ttsCreates[0].idempotencyKey.startsWith('tts:')) {
      throw new Error(`${viewport.name}: TTS recovery omitted its idempotency key`)
    }

    await page.getByRole('button', { name: 'Done', exact: true }).click()
    const succeededTtsRow = page.locator('article').filter({
      hasText: 'VassilStudio keeps every voice render inside your local workspace.',
    })
    await succeededTtsRow.getByRole('button', { name: 'Listen', exact: true }).click()
    await succeededTtsRow.locator('[id^="job-audio-"]').waitFor({ state: 'visible' })
    await succeededTtsRow.getByText('Audio temporarily unavailable.', { exact: true }).waitFor({ state: 'visible' })
    await succeededTtsRow.getByRole('button', { name: 'Retry audio', exact: true }).click()
    const inlineAudio = succeededTtsRow.getByLabel(/TTS job .* audio/)
    await inlineAudio.waitFor({ state: 'attached' })
    await page.waitForFunction(() => {
      const audio = document.querySelector('article audio')
      return audio && audio.readyState >= HTMLMediaElement.HAVE_METADATA
    })
    const inlineSource = await inlineAudio.getAttribute('src')
    if (!inlineSource?.startsWith('blob:')) {
      throw new Error(`${viewport.name}: inline job audio did not use an authenticated blob URL`)
    }
    await page.waitForFunction(() => {
      const audio = document.querySelector('article audio')
      return audio && (audio.currentTime > 0 || audio.ended)
    })
    const playbackScreenshot = path.join(outputDir, `jobs-playback-${viewport.name}.png`)
    await page.screenshot({ path: playbackScreenshot, fullPage: true })
    const downloadPromise = page.waitForEvent('download')
    await succeededTtsRow.getByRole('button', { name: 'Download WAV', exact: true }).click()
    const download = await downloadPromise
    if (download.suggestedFilename() !== 'vassil-render-tts-2026.wav') {
      throw new Error(`${viewport.name}: job audio download filename was not stable`)
    }
    await succeededTtsRow.getByRole('button', { name: 'Hide player', exact: true }).click()

    await page.getByRole('button', { name: /Inspect TTS job/ }).click()
    dialog = page.getByRole('dialog')
    await dialog.getByRole('heading', { name: 'Output audio' }).waitFor({ state: 'visible' })
    await dialog.locator('audio').waitFor({ state: 'attached' })
    const inspectorSource = await dialog.locator('audio').getAttribute('src')
    if (!inspectorSource?.startsWith('blob:')) {
      throw new Error(`${viewport.name}: inspector audio did not use an authenticated blob URL`)
    }
    await dialog.getByText('24,000 Hz', { exact: true }).waitFor({ state: 'visible' })
    await dialog.getByRole('button', { name: 'Close job details' }).click()

    await page.getByRole('button', { name: 'ASR', exact: true }).click()
    await page.getByRole('button', { name: /Inspect ASR job/ }).click()
    dialog = page.getByRole('dialog')
    await dialog.getByRole('heading', { name: 'Input audio' }).waitFor({ state: 'visible' })
    await dialog.getByText('interview-en.wav', { exact: true }).waitFor({ state: 'visible' })
    const asrRecoveryResponse = page.waitForResponse((response) => {
      const request = response.request()
      return request.method() === 'POST' && new URL(response.url()).pathname === '/api/v1/asr/jobs'
    })
    await dialog.getByRole('button', { name: 'Run again', exact: true }).click()
    await asrRecoveryResponse

    if (fixture.asrCreates.length !== 1) {
      throw new Error(`${viewport.name}: expected one ASR recovery request`)
    }
    assertMultipartBody(
      fixture.asrCreates[0].body,
      ['interview-en.wav', 'language', 'en'],
      `${viewport.name} ASR recovery`,
    )
    if (!fixture.audioReads.some((value) => value.includes('asr-20260823-success-1234abcd'))) {
      throw new Error(`${viewport.name}: ASR recovery did not read the original input audio`)
    }
    if (!fixture.asrCreates[0].idempotencyKey.startsWith('asr:')) {
      throw new Error(`${viewport.name}: ASR recovery omitted its idempotency key`)
    }
    if (fixture.audioApiKeys.some((value) => value !== 'jobs-qa-api-key')) {
      throw new Error(`${viewport.name}: one or more job audio requests omitted the API key header`)
    }

    const layout = await layoutMetrics(page)
    if (layout.horizontalOverflow > 1) {
      throw new Error(`${viewport.name}: Jobs overflowed horizontally by ${layout.horizontalOverflow}px`)
    }
    const unexpectedBrowserErrors = browserErrors.filter(
      (message) => !message.includes('503 (Service Unavailable)'),
    )
    if (unexpectedBrowserErrors.length > 0) {
      throw new Error(`${viewport.name}: browser errors: ${unexpectedBrowserErrors.join(' | ')}`)
    }

    const queueScreenshot = path.join(outputDir, `jobs-queue-${viewport.name}.png`)
    await page.screenshot({ path: queueScreenshot, fullPage: true })
    report.viewports.push({
      ...viewport,
      dialogWidth: dialogBox.width,
      footerActionBoxes,
      ttsRecoveryRequests: fixture.ttsCreates.length,
      asrRecoveryRequests: fixture.asrCreates.length,
      audioReads: fixture.audioReads,
      playbackScreenshot,
      layout,
      failedScreenshot,
      queueScreenshot,
    })
    await page.close()
  }
} finally {
  await browser.close()
}

const reportPath = path.join(outputDir, 'report.json')
await fs.writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8')
console.log(`Jobs workflow QA passed: ${report.viewports.length} viewports`)
console.log(`Artifacts: ${outputDir}`)
