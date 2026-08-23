import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { chromium } from 'playwright'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const repositoryRoot = path.resolve(scriptDir, '..', '..', '..')
const baseUrl = (process.env.VASSIL_QA_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')
const outputDir = process.env.VASSIL_QA_OUTPUT_DIR || path.join(repositoryRoot, 'artifacts', 'ui-qa', 'voice-intake')
const channel = process.env.PLAYWRIGHT_CHANNEL || 'chrome'
const executablePath = process.env.PLAYWRIGHT_EXECUTABLE_PATH

const viewports = [
  { name: 'desktop', width: 1440, height: 1000 },
  { name: 'mobile', width: 390, height: 844 },
]

function createWaveBuffer(seconds = 4, sampleRate = 16000) {
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
    const sample = index < sampleRate
      ? 0
      : Math.round(Math.sin(2 * Math.PI * 220 * index / sampleRate) * 8000)
    buffer.writeInt16LE(sample, 44 + index * 2)
  }
  return buffer
}

function baseReport() {
  return {
    status: 'ready',
    can_create: true,
    source_sha256: 'a'.repeat(64),
    audio_sha256: 'b'.repeat(64),
    source_duration_seconds: 4,
    duration_seconds: 4,
    source_sample_rate: 16000,
    target_sample_rate: 24000,
    channels: 1,
    trim_start_seconds: 0,
    trim_end_seconds: 4,
    suggested_trim_start_seconds: 0,
    suggested_trim_end_seconds: 4,
    leading_silence_seconds: 0,
    trailing_silence_seconds: 0,
    clipping_ratio: 0,
    speech_coverage_ratio: 1,
    peak_amplitude: 0.25,
    reference_text: 'Giọng nói rõ ràng cho bản kiểm tra.',
    reference_text_source: 'user',
    issues: [],
    duplicate: null,
  }
}

async function installFixture(page, fixture) {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: async () => ({ getTracks: () => [{ stop() {} }] }),
      },
    })
    class QaMediaRecorder {
      static isTypeSupported(type) { return type.startsWith('audio/webm') }
      state = 'inactive'
      mimeType = 'audio/webm;codecs=opus'
      ondataavailable = null
      onstop = null
      onerror = null
      constructor(stream, options) {
        this.stream = stream
        if (options?.mimeType) this.mimeType = options.mimeType
      }
      start() { this.state = 'recording' }
      stop() {
        this.state = 'inactive'
        this.ondataavailable?.({ data: new Blob(['qa-voice'], { type: this.mimeType }) })
        this.onstop?.()
      }
    }
    Object.defineProperty(window, 'MediaRecorder', { configurable: true, value: QaMediaRecorder })
  })

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
    if (url.pathname === '/api/v1/voices/import-candidates' && method === 'GET') return json([])
    if (url.pathname === '/api/v1/voices' && method === 'GET') return json(fixture.voices)
    if (url.pathname === '/api/v1/voices/intake/analyze' && method === 'POST') {
      fixture.analyzeRequests += 1
      if (fixture.voices.length === 0 && fixture.analyzeRequests === 1) {
        return json({
          ...baseReport(),
          status: 'review',
          leading_silence_seconds: 1,
          speech_coverage_ratio: 0.75,
          suggested_trim_start_seconds: 0.9,
          issues: [{ code: 'leading_silence', severity: 'warning', message: 'The selection begins with at least 0.5 seconds of silence.' }],
        })
      }
      if (fixture.voices.length === 0) {
        return json({
          ...baseReport(),
          duration_seconds: 3.1,
          trim_start_seconds: 0.9,
          trim_end_seconds: 4,
          suggested_trim_start_seconds: 0.9,
        })
      }
      return json({
        ...baseReport(),
        status: 'blocked',
        can_create: false,
        duplicate: { voice_id: 'voice-qa-reviewed', name: 'QA Reviewed Voice', language: 'vi' },
        issues: [{ code: 'duplicate_audio', severity: 'blocking', message: 'This audio already belongs to voice profile "QA Reviewed Voice". Reuse it instead.' }],
      })
    }
    if (url.pathname === '/api/v1/voices' && method === 'POST') {
      fixture.createRequests.push(request.postData() || '')
      const voice = {
        voice_id: 'voice-qa-reviewed',
        name: 'QA Reviewed Voice',
        language: 'vi',
        reference_text: 'Giọng nói rõ ràng cho bản kiểm tra.',
        reference_text_source: 'user',
        audio_size_bytes: 128044,
        sample_rate: 24000,
        duration_seconds: 4,
        created_at: '2026-08-24T00:00:00Z',
        updated_at: '2026-08-24T00:00:00Z',
        reference_audio_url: '',
      }
      fixture.voices = [voice]
      return json(voice)
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

await fs.mkdir(outputDir, { recursive: true })
const browser = await chromium.launch({
  channel: executablePath ? undefined : channel,
  executablePath,
  headless: true,
  args: ['--autoplay-policy=no-user-gesture-required'],
})
const report = { baseUrl, generatedAt: new Date().toISOString(), viewports: [] }

try {
  for (const viewport of viewports) {
    const page = await browser.newPage({ viewport, colorScheme: 'light', reducedMotion: 'reduce' })
    const fixture = { voices: [], analyzeRequests: 0, createRequests: [] }
    const browserErrors = captureBrowserErrors(page)
    await installFixture(page, fixture)
    const response = await page.goto(`${baseUrl}/studio#/voices`, { waitUntil: 'networkidle' })
    if (!response?.ok()) throw new Error(`${viewport.name}: Studio returned ${response?.status()}`)

    const fileInput = page.locator('input[type="file"]')
    await fileInput.setInputFiles({ name: 'qa-reference.wav', mimeType: 'audio/wav', buffer: createWaveBuffer() })
    await page.getByPlaceholder('Exact Vietnamese transcript').fill('Giọng nói rõ ràng cho bản kiểm tra.')
    await page.getByLabel('Profile name').fill('QA Reviewed Voice')
    if (fixture.createRequests.length !== 0) throw new Error(`${viewport.name}: profile was created before review`)

    await page.getByRole('button', { name: 'Review recording' }).click()
    await page.getByRole('dialog').waitFor({ state: 'visible' })
    await page.getByText('The selection begins with at least 0.5 seconds of silence.').waitFor({ state: 'visible' })
    const createButton = page.getByRole('button', { name: 'Create voice profile' })
    if (await createButton.isEnabled()) throw new Error(`${viewport.name}: warning was not acknowledged`)
    const acknowledgement = page.getByText('I listened to the selection and accept these quality warnings.')
    await acknowledgement.click()
    if (!await createButton.isEnabled()) throw new Error(`${viewport.name}: warning acknowledgement did not unlock create`)
    await acknowledgement.click()
    await page.getByRole('button', { name: 'Use suggested trim' }).click()
    if (await createButton.isEnabled()) throw new Error(`${viewport.name}: stale trim could be created without recheck`)
    const selectionAudio = page.getByRole('dialog').locator('audio')
    await selectionAudio.evaluate((audio) => audio.play())
    await page.waitForFunction(() => {
      const audio = document.querySelector('[role="dialog"] audio')
      return audio instanceof HTMLAudioElement && audio.currentTime >= 0.9
    })
    await selectionAudio.evaluate((audio) => audio.pause())
    await page.getByRole('button', { name: 'Recheck selection' }).click()
    await page.getByText('Audio and transcript passed the intake checks.').waitFor({ state: 'visible' })
    await page.getByText('Speech coverage').waitFor({ state: 'visible' })
    await page.waitForFunction(() => {
      const button = Array.from(document.querySelectorAll('button')).find((item) => item.textContent?.includes('Create voice profile'))
      return button instanceof HTMLButtonElement && !button.disabled
    })
    await page.waitForTimeout(150)
    const createButtonState = await createButton.evaluate((button) => ({
      disabled: button.disabled,
      backgroundColor: getComputedStyle(button).backgroundColor,
    }))
    if (createButtonState.disabled) throw new Error(`${viewport.name}: reviewed clean audio could not be created`)

    const screenshot = path.join(outputDir, `voice-review-${viewport.name}.png`)
    await page.screenshot({ path: screenshot, fullPage: true })
    await createButton.click()
    await page.getByText('QA Reviewed Voice').first().waitFor({ state: 'visible' })
    if (fixture.createRequests.length !== 1) throw new Error(`${viewport.name}: expected one create request`)
    if (!fixture.createRequests[0].includes('reviewed_source_sha256')) {
      throw new Error(`${viewport.name}: create request omitted reviewed source hash`)
    }

    await fileInput.setInputFiles({ name: 'qa-reference-copy.wav', mimeType: 'audio/wav', buffer: createWaveBuffer() })
    await page.getByRole('button', { name: 'Review recording' }).click()
    await page.getByText('Already in your library').waitFor({ state: 'visible' })
    if (await page.getByRole('button', { name: 'Create voice profile' }).isEnabled()) {
      throw new Error(`${viewport.name}: duplicate audio could still be created`)
    }
    await page.getByRole('button', { name: 'Use existing profile' }).click()
    await page.getByRole('dialog').waitFor({ state: 'detached' })

    await page.getByRole('button', { name: 'Record', exact: true }).click()
    await page.getByRole('button', { name: 'Start recording' }).click()
    await page.getByRole('button', { name: 'Stop' }).click()
    await page.getByText('Recording captured').waitFor({ state: 'visible' })

    const horizontalOverflow = await page.evaluate(() => (
      document.documentElement.scrollWidth - document.documentElement.clientWidth
    ))
    if (horizontalOverflow > 1) throw new Error(`${viewport.name}: page overflowed by ${horizontalOverflow}px`)
    if (browserErrors.length > 0) throw new Error(`${viewport.name}: browser errors: ${browserErrors.join(' | ')}`)
    report.viewports.push({ ...viewport, analyzeRequests: fixture.analyzeRequests, createRequests: fixture.createRequests.length, createButtonState, horizontalOverflow, screenshot })
    await page.close()
  }
} finally {
  await browser.close()
}

await fs.writeFile(path.join(outputDir, 'report.json'), `${JSON.stringify(report, null, 2)}\n`, 'utf8')
console.log(`Voice intake QA passed: ${report.viewports.length} viewports`)
console.log(`Artifacts: ${outputDir}`)
