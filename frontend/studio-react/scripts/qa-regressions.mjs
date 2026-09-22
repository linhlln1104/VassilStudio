import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..')
const baseUrl = (process.env.VASSIL_QA_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')
const outputDir = process.env.VASSIL_QA_OUTPUT_DIR || path.join(root, 'artifacts', 'ui-qa', 'regressions')
const browser = await chromium.launch(process.env.PLAYWRIGHT_EXECUTABLE_PATH
  ? { executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH }
  : { channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome' })
const passed = []
const runtime = {
  provider: 'cpu', num_threads: 1, asr_num_threads: 1, tts_num_threads: 1,
  asr_loaded: true, tts_loaded: true, asr_configured_languages: ['vi', 'en'],
  tts_configured_languages: ['vi', 'en'], asr_loaded_languages: ['vi', 'en'],
  tts_loaded_languages: ['vi', 'en'], asr_job_workers: 1, tts_job_workers: 1,
  asr_job_max_attempts: 2, tts_job_max_attempts: 2, job_retry_backoff_seconds: 1,
  environment: 'test', log_level: 'INFO', debug: false, warmup_on_startup: false,
}

function wav() {
  const buffer = Buffer.alloc(44 + 3200)
  buffer.write('RIFF'); buffer.writeUInt32LE(buffer.length - 8, 4); buffer.write('WAVEfmt ', 8)
  buffer.writeUInt32LE(16, 16); buffer.writeUInt16LE(1, 20); buffer.writeUInt16LE(1, 22)
  buffer.writeUInt32LE(16000, 24); buffer.writeUInt32LE(32000, 28)
  buffer.writeUInt16LE(2, 32); buffer.writeUInt16LE(16, 34); buffer.write('data', 36)
  buffer.writeUInt32LE(3200, 40)
  return buffer
}

function asrJob(filename) {
  return {
    job_id: 'qa-asr-job', filename, language: 'en', status: 'succeeded', text: 'Saved words.',
    created_at: '2026-09-22T00:00:00Z', started_at: '2026-09-22T00:00:00Z',
    completed_at: '2026-09-22T00:00:01Z', error: null, failed_reason: null,
    attempt: 1, max_attempts: 2, cancel_requested: false, cancellation_mode: 'safe_point',
    progress_stage: 'succeeded', stage_started_at: '2026-09-22T00:00:01Z',
    duration_seconds: 0.1, sample_rate: 16000, audio_url: '/api/v1/asr/jobs/qa-asr-job/audio',
    raw_text: 'Saved words.', raw_segments: [], segments: [], timing_status: 'unavailable',
    transcript_revision: 0, transcript_edited: false, transcript_updated_at: null,
  }
}

async function fixture(page, options = {}) {
  const state = { authenticated: !options.auth, creates: [], jobs: options.jobs || [] }
  await page.route('**/*', async (route) => {
    const request = route.request()
    const pathname = new URL(request.url()).pathname
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
    if (pathname === '/api/v1/auth/status') return json({
      auth_required: Boolean(options.auth), setup_required: false, authenticated: state.authenticated,
      api_key_auth_enabled: false, user: state.authenticated ? { account_id: 'owner', username: 'owner', role: 'owner' } : null,
    })
    if (pathname === '/api/v1/auth/login') {
      state.authenticated = true
      return json({ authenticated: true, user: { account_id: 'owner', username: 'owner', role: 'owner' }, expires_at: '2099-01-01T00:00:00Z' })
    }
    if (pathname === '/api/v1/auth/logout') { state.authenticated = false; return json({ logged_out: true }) }
    if (pathname === '/model-status') return json({ ready: true, checks: {}, runtime })
    if (pathname === '/health') return json({ status: 'ok', version: 'qa', provider: 'cpu', asr_enabled: true, tts_enabled: true, asr_loaded: true, tts_loaded: true })
    if (pathname === '/livez' || pathname === '/readyz') return json({ status: pathname === '/livez' ? 'ok' : 'ready', checks: {} })
    if (pathname === '/diagnostics') return json({ generated_at: '2026-09-22T00:00:00Z', runtime, storage: [], security: {}, license: {} })
    if (pathname === '/api/v1/asr/jobs' && request.method() === 'POST') {
      state.creates.push(request.postDataBuffer())
      return json({ ...asrJob('interview.wav'), job_id: 'qa-rerun', status: 'queued' })
    }
    if (pathname === '/api/v1/asr/jobs') return json(state.jobs)
    if (pathname.endsWith('/audio')) return route.fulfill({ contentType: 'audio/wav', body: wav() })
    if (['/api/v1/tts/jobs', '/api/v1/voices', '/api/v1/voices/import-candidates'].includes(pathname)) return json([])
    if (pathname.startsWith('/api/')) throw new Error(`Unexpected API request: ${request.method()} ${pathname}`)
    return route.continue()
  })
  return state
}

async function pageFor(options) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce', ...options })
  const page = await context.newPage()
  page.setDefaultTimeout(10000)
  return page
}

async function login(page) {
  assert.equal(await page.getByLabel('Password', { exact: true }).count(), 1)
  await page.getByLabel('Username', { exact: true }).fill('owner')
  await page.getByLabel('Password', { exact: true }).fill('test-password')
  await page.getByRole('button', { name: 'Open Studio', exact: true }).click()
}

function installRecorderFixture() {
  const state = { calls: 0, stopped: 0, created: 0, recorderStopped: 0, grant: null }
  window.__mic = state
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: {
    getUserMedia: () => {
      state.calls++
      return new Promise((resolve) => { state.grant = () => resolve({ getTracks: () => [{ stop: () => state.stopped++ }] }) })
    },
  } })
  class Recorder {
    static isTypeSupported() { return true }
    state = 'inactive'; mimeType = 'audio/webm'; onstop = null; ondataavailable = null; onerror = null
    constructor() { state.created++ }
    start() { this.state = 'recording' }
    stop() { this.state = 'inactive'; state.recorderStopped++; this.onstop?.() }
  }
  window.MediaRecorder = Recorder
}

function installRealtimeFixture() {
  const node = () => ({ connect() {}, disconnect() {} })
  class Context {
    sampleRate = 16000; destination = node()
    createMediaStreamSource() { return node() }
    createScriptProcessor() { return node() }
    createGain() { return { ...node(), gain: { value: 0 } } }
    close() { return Promise.resolve() }
  }
  window.AudioContext = Context
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: {
    getUserMedia: async () => ({ getTracks: () => [{ stop() {} }] }),
  } })
  class Socket {
    static OPEN = 1; static CLOSED = 3
    readyState = 0; onmessage = null; onclose = null; onerror = null
    constructor() {
      window.__socket = this
      setTimeout(() => {
        this.readyState = 1
        this.emit({ type: 'ready', sample_rate: 16000, language: 'vi' })
        this.emit({ type: 'transcript', text: 'Words already received.', sequence: 1, language: 'vi' })
      }, 0)
    }
    emit(message) { this.onmessage?.({ data: JSON.stringify(message) }) }
    send(payload) { if (typeof payload === 'string' && JSON.parse(payload).type === 'close') this.stopRequested = true }
    close() { this.readyState = 3; this.onclose?.({}) }
  }
  window.WebSocket = Socket
}

try {
  {
    const page = await pageFor()
    await fixture(page, { auth: true })
    await page.addInitScript(() => {
      if (sessionStorage.getItem('draft-seeded')) return
      sessionStorage.setItem('draft-seeded', 'yes')
      for (const key of ['vassil.generateDraft', 'vassil.pendingScript', 'vvoice.generateDraft', 'vvoice.pendingScript']) localStorage.setItem(key, 'private draft')
    })
    await page.goto(`${baseUrl}/login?return_to=%2Fstudio#/jobs`)
    await login(page)
    await page.getByRole('heading', { level: 1, name: 'Jobs', exact: true }).waitFor()
    assert.equal(new URL(page.url()).hash, '#/jobs')
    await page.getByRole('button', { name: 'Sign out', exact: true }).click()
    await page.waitForURL('**/login')
    assert.equal(await page.evaluate(() => Object.keys(localStorage).filter((key) => /(?:generateDraft|pendingScript)$/.test(key)).length), 0)
    passed.push('auth deep link, password accessible name, logout draft removal')
    await page.context().close()
  }
  for (const destination of ['https://example.invalid/studio', '//example.invalid/studio', '/support']) {
    const page = await pageFor()
    await fixture(page, { auth: true })
    await page.goto(`${baseUrl}/login?return_to=${encodeURIComponent(destination)}`)
    await login(page)
    await page.getByRole('heading', { level: 1, name: 'Generate', exact: true }).waitFor()
    assert.equal(new URL(page.url()).origin, new URL(baseUrl).origin)
    assert.equal(new URL(page.url()).pathname, '/studio')
    await page.context().close()
  }
  passed.push('unsafe auth return destinations rejected')

  for (const extension of ['mp3', 'webm', 'm4a']) {
    const page = await pageFor()
    const state = await fixture(page, { jobs: [asrJob(`interview.${extension}`)] })
    await page.goto(`${baseUrl}/studio#/jobs`)
    await page.getByRole('button', { name: /Inspect ASR job/ }).click()
    const created = page.waitForResponse((response) => new URL(response.url()).pathname === '/api/v1/asr/jobs' && response.request().method() === 'POST')
    await page.getByRole('dialog').getByRole('button', { name: 'Run again', exact: true }).click()
    await created
    assert.equal(state.creates.length, 1)
    const body = state.creates[0].toString('latin1')
    assert.ok(body.includes('filename="interview.wav"'), `retry of ${extension} must be named WAV`)
    assert.ok(body.includes('Content-Type: audio/wav'))
    assert.ok(body.includes('RIFF'))
    await page.context().close()
  }
  passed.push('ASR Run again uses WAV content, MIME and extension for MP3/WebM/M4A originals')

  {
    const page = await pageFor({ viewport: { width: 390, height: 844 } })
    await fixture(page)
    await page.goto(`${baseUrl}/studio#/jobs`)
    const trigger = page.getByRole('button', { name: 'Open navigation' })
    await trigger.click()
    const dialog = page.getByRole('dialog', { name: 'Studio navigation' })
    await dialog.waitFor()
    for (let index = 0; index < 12; index++) {
      await page.keyboard.press('Tab')
      assert.equal(await dialog.evaluate((element) => element.contains(document.activeElement)), true)
    }
    await page.keyboard.press('Escape')
    await dialog.waitFor({ state: 'hidden' })
    assert.equal(await trigger.evaluate((element) => element === document.activeElement), true)
    passed.push('mobile navigation focus trap, Escape and focus restoration')
    await page.context().close()
  }

  {
    const page = await pageFor()
    await fixture(page)
    await page.addInitScript(installRecorderFixture)
    await page.goto(`${baseUrl}/studio#/voices`)
    await page.getByRole('button', { name: 'Record', exact: true }).click()
    await page.getByRole('button', { name: 'Start recording', exact: true }).evaluate((button) => { button.click(); button.click() })
    await page.getByRole('button', { name: 'Requesting microphone', exact: true }).waitFor()
    assert.equal(await page.evaluate(() => window.__mic.calls), 1)
    await page.evaluate(() => { window.location.hash = '/jobs' })
    await page.getByRole('heading', { level: 1, name: 'Jobs', exact: true }).waitFor()
    await page.evaluate(() => window.__mic.grant())
    await page.waitForFunction(() => window.__mic.stopped === 1)
    assert.equal(await page.evaluate(() => window.__mic.created), 0)
    passed.push('recorder double start locked and late permission stream stopped after navigation')
    await page.context().close()
  }

  {
    const page = await pageFor()
    await fixture(page)
    await page.addInitScript(installRealtimeFixture)
    await page.goto(`${baseUrl}/studio#/realtime`)
    await page.getByRole('button', { name: 'Start session', exact: true }).click()
    await page.getByText('Microphone live', { exact: true }).waitFor()
    await page.clock.install()
    await page.getByRole('button', { name: 'Stop and finalize', exact: true }).click()
    await page.clock.fastForward(6500)
    await page.getByRole('button', { name: 'Finalizing', exact: true }).waitFor()
    assert.equal(await page.evaluate(() => window.__socket.readyState), 1)
    await page.evaluate(() => {
      window.__socket.emit({ type: 'transcript', text: 'Delayed final words.', sequence: 2, final: true, language: 'vi' })
      window.__socket.emit({ type: 'closed' })
    })
    await page.getByRole('button', { name: 'Start session', exact: true }).waitFor()
    await page.getByText('Words already received. Delayed final words.', { exact: true }).waitFor()
    await page.getByRole('button', { name: 'Start session', exact: true }).click()
    await page.clock.runFor(10)
    await page.getByText('Microphone live', { exact: true }).waitFor()
    await page.getByRole('button', { name: 'Stop and finalize', exact: true }).click()
    await page.clock.fastForward(31000)
    await page.getByRole('alert').filter({ hasText: 'The final transcript was not confirmed' }).waitFor()
    assert.ok(await page.getByText(/Delayed final words/).count() > 0)
    assert.equal(await page.evaluate(() => window.__socket.readyState), 3)
    passed.push('realtime waits beyond 5s for final ACK and reports missing ACK without discarding transcript')
    await page.context().close()
  }

  await fs.mkdir(outputDir, { recursive: true })
  await fs.writeFile(path.join(outputDir, 'regressions.json'), JSON.stringify({ baseUrl, passed }, null, 2) + '\n')
  console.log(`Frontend regression QA passed: ${passed.length} checks`)
} finally {
  await browser.close()
}
