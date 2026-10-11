import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import path from 'node:path'
import { chromium } from 'playwright'
import { ttsModelCatalog } from './tts-model-fixture.mjs'

const baseUrl = (process.env.VASSIL_QA_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')
const outputDir = process.env.VASSIL_QA_OUTPUT_DIR || 'artifacts/ui-qa/models'
const browser = await chromium.launch(process.env.PLAYWRIGHT_EXECUTABLE_PATH
  ? { executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH }
  : { channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome' })
const passed = []

async function fixture(page) {
  const state = { catalog: ttsModelCatalog(), catalogError: false, jobs: [], creates: [] }
  await page.route('**/*', async (route) => {
    const request = route.request()
    const pathname = new URL(request.url()).pathname
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
    if (pathname === '/api/v1/auth/status') return json({ auth_required: false, authenticated: true, setup_required: false, user: null })
    if (pathname === '/model-status') return json({ ready: true, runtime: { asr_loaded: false, tts_loaded: false } })
    if (pathname === '/api/v1/tts/models') return state.catalogError ? json({ detail: 'Catalog temporarily unavailable' }, 503) : json(state.catalog)
    if (pathname === '/api/v1/voices') return json([{
      voice_id: 'reference-voice', name: 'Reference voice', language: 'vi', reference_text: 'Reference script',
      reference_text_source: 'user', reference_audio_url: '', duration_seconds: 2, sample_rate: 24000,
    }])
    if (pathname === '/api/v1/tts/jobs') return json(state.jobs)
    if (pathname === '/api/v1/asr/jobs') return json([])
    if (pathname === '/api/v1/tts/jobs/voices/reference-voice' && request.method() === 'POST') {
      const form = await new Response(request.postDataBuffer(), { headers: { 'Content-Type': request.headers()['content-type'] } }).formData()
      const fields = Object.fromEntries(form)
      state.creates.push({ fields, key: request.headers()['idempotency-key'] })
      const now = new Date().toISOString()
      const job = {
        job_id: `${state.creates.length}-model-job`, model_id: fields.model_id, voice_id: 'reference-voice',
        language: fields.language, text: fields.text, status: 'queued',
        num_steps: fields.num_steps ? Number(fields.num_steps) : null, speed: fields.speed ? Number(fields.speed) : null,
        created_at: now, started_at: null, completed_at: null, error: null, attempt: 0, max_attempts: 1,
        cancel_requested: false, cancellation_mode: 'safe_point', failed_reason: null,
        progress_stage: 'queued', stage_started_at: now, sample_rate: null, duration_seconds: null, audio_url: null,
      }
      state.jobs.unshift(job)
      return json(job, 202)
    }
    if (pathname.startsWith('/api/')) throw new Error(`Unexpected API request: ${pathname}`)
    return route.continue()
  })
  return state
}

async function create(page) {
  const response = page.waitForResponse((item) => item.request().method() === 'POST' && item.url().includes('/tts/jobs/voices/'))
  await page.getByRole('button', { name: 'Generate audio', exact: true }).click()
  await response
  await page.getByRole('button', { name: 'Render active', exact: true }).waitFor()
}

try {
  for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
    const page = await browser.newPage({ viewport, reducedMotion: 'reduce' })
    page.setDefaultTimeout(10000)
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    const state = await fixture(page)
    await page.addInitScript(() => {
      if (!sessionStorage.getItem('model-preference-seeded')) {
        localStorage.setItem('vassil.selectedTtsModel.vi', 'removed-model')
        sessionStorage.setItem('model-preference-seeded', 'yes')
      }
    })
    await page.goto(`${baseUrl}/studio/#/generate`)
    const select = page.getByLabel('TTS model', { exact: true }).filter({ visible: true })
    await select.waitFor()
    assert.equal(await select.inputValue(), 'zipvoice-vi')
    await page.locator('textarea:visible').fill('Cung mot kich ban cho hai model.')
    await page.getByRole('button', { name: 'Production', exact: true }).click()
    await page.getByRole('slider', { name: 'Speed' }).fill('125')
    await create(page)
    assert.deepEqual(state.creates[0].fields, {
      text: 'Cung mot kich ban cho hai model.', language: 'vi', model_id: 'zipvoice-vi', num_steps: '8', speed: '1.25',
    })

    await select.selectOption('vieneu-v3-turbo')
    assert.equal(await page.getByRole('slider', { name: 'Speed' }).count(), 0)
    assert.equal(await page.getByRole('button', { name: 'Production', exact: true }).count(), 0)
    assert.equal(await page.getByRole('button', { name: 'Generate audio', exact: true }).isEnabled(), true)
    await create(page)
    assert.deepEqual(state.creates[1].fields, {
      text: 'Cung mot kich ban cho hai model.', language: 'vi', model_id: 'vieneu-v3-turbo',
    })
    assert.notEqual(state.creates[0].key, state.creates[1].key)
    await page.reload()
    await page.getByRole('button', { name: 'Render active', exact: true }).waitFor()
    assert.equal(await select.inputValue(), 'vieneu-v3-turbo')
    assert.equal(state.creates.length, 2)
    await page.getByRole('button', { name: 'English', exact: true }).click()
    assert.equal(await select.inputValue(), 'zipvoice-en')
    assert.equal(await select.locator('option[value="zipvoice-vi"]').count(), 0)
    await page.getByRole('button', { name: 'Vietnamese', exact: true }).click()
    assert.equal(await select.inputValue(), 'vieneu-v3-turbo')

    state.jobs[0].status = 'succeeded'
    state.jobs[0].progress_stage = 'succeeded'
    state.jobs[0].completed_at = new Date().toISOString()
    await page.goto(`${baseUrl}/studio/#/jobs`)
    await page.reload()
    await page.getByRole('button', { name: 'Inspect TTS job 2-model-', exact: true }).click()
    const dialog = page.getByRole('dialog')
    await dialog.getByText('vieneu-v3-turbo', { exact: true }).waitFor()
    const rerun = page.waitForResponse((item) => item.request().method() === 'POST' && item.url().includes('/tts/jobs/voices/'))
    await dialog.getByRole('button', { name: 'Create new take', exact: true }).click()
    await rerun
    assert.equal(state.creates[2].fields.model_id, 'vieneu-v3-turbo')
    assert.equal(state.creates[2].fields.num_steps, undefined)
    assert.equal(state.creates[2].fields.speed, undefined)

    state.catalog.models.find((model) => model.model_id === 'vieneu-v3-turbo').ready = false
    state.catalog.models.find((model) => model.model_id === 'vieneu-v3-turbo').status = 'missing_dependencies'
    state.catalog.models.find((model) => model.model_id === 'vieneu-v3-turbo').message = 'Install the VieNeu engine dependency.'
    await page.goto(`${baseUrl}/studio/#/generate`)
    await page.reload()
    await page.getByText('Install the VieNeu engine dependency.', { exact: true }).filter({ visible: true }).waitFor()
    await page.locator('textarea:visible').fill('Another script')
    assert.equal(await page.getByRole('button', { name: 'Generate audio', exact: true }).isDisabled(), true)
    assert.match(await select.locator('option:checked').textContent(), /Missing dependencies/)
    await fs.mkdir(outputDir, { recursive: true })
    await page.screenshot({ path: path.join(outputDir, `models-${viewport.width}.png`), fullPage: true })

    state.catalogError = true
    await page.reload()
    await page.getByText('Unable to load TTS models', { exact: true }).filter({ visible: true }).waitFor()
    assert.equal(await select.isDisabled(), true)
    assert.equal(await page.getByRole('button', { name: 'Generate audio', exact: true }).isDisabled(), true)
    assert.deepEqual(errors, [])
    passed.push(`${viewport.width}px: model selection, controls, payloads, idempotency, active matching, persistence, language filtering, rerun and setup/catalog errors`)
    await page.close()
  }
} finally {
  await browser.close()
}
await fs.writeFile(path.join(outputDir, 'report.json'), JSON.stringify({ passed }, null, 2))
console.log(`Multi-model QA passed: ${passed.length} viewports`)
