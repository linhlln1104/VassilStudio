import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { chromium } from 'playwright'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const repositoryRoot = path.resolve(scriptDir, '..', '..', '..')
const baseUrl = (process.env.VASSIL_QA_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')
const outputDir = process.env.VASSIL_QA_OUTPUT_DIR || path.join(repositoryRoot, 'artifacts', 'ui-qa', 'transcript-review')
const channel = process.env.PLAYWRIGHT_CHANNEL || 'chrome'
const executablePath = process.env.PLAYWRIGHT_EXECUTABLE_PATH

const viewports = [
  { name: 'desktop', width: 1440, height: 1000 },
  { name: 'mobile', width: 390, height: 844 },
]

function createWaveBuffer(seconds = 3, sampleRate = 16000) {
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
    const sample = Math.round(Math.sin(2 * Math.PI * 220 * index / sampleRate) * 3000)
    buffer.writeInt16LE(sample, 44 + index * 2)
  }
  return buffer
}

function completedJob() {
  const segments = [
    { segment_id: 'segment-0001', start_seconds: 0.1, end_seconds: 1.4, text: 'Raw first sentence.' },
    { segment_id: 'segment-0002', start_seconds: 1.4, end_seconds: 2.9, text: 'Raw second sentence.' },
  ]
  return {
    job_id: '12345678-abcd-4000-9000-123456789abc',
    status: 'succeeded',
    filename: 'interview-en.wav',
    language: 'en',
    created_at: '2026-08-24T08:00:00Z',
    started_at: '2026-08-24T08:00:01Z',
    completed_at: '2026-08-24T08:00:04Z',
    error: null,
    attempt: 1,
    max_attempts: 2,
    cancel_requested: false,
    cancellation_mode: 'safe_point',
    failed_reason: null,
    progress_stage: 'succeeded',
    stage_started_at: '2026-08-24T08:00:04Z',
    text: 'Raw first sentence. Raw second sentence.',
    sample_rate: 16000,
    duration_seconds: 3,
    audio_url: '/api/v1/asr/jobs/12345678-abcd-4000-9000-123456789abc/audio',
    raw_text: 'Raw first sentence. Raw second sentence.',
    raw_segments: structuredClone(segments),
    segments,
    timing_status: 'available',
    transcript_revision: 0,
    transcript_edited: false,
    transcript_updated_at: null,
  }
}

async function installFixture(page, fixture) {
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
        checks: {},
        runtime: {
          asr_configured_languages: ['vi', 'en'],
          asr_loaded_languages: ['en'],
          tts_configured_languages: ['vi', 'en'],
          tts_loaded_languages: [],
        },
      })
    }
    if (url.pathname === '/api/v1/asr/jobs' && method === 'GET') {
      return json([fixture.job])
    }
    if (url.pathname === '/api/v1/tts/jobs' && method === 'GET') {
      return json([])
    }
    if (url.pathname === fixture.job.audio_url && method === 'GET') {
      return route.fulfill({ status: 200, contentType: 'audio/wav', body: createWaveBuffer() })
    }
    if (url.pathname.endsWith('/transcript') && method === 'PATCH') {
      const payload = request.postDataJSON()
      fixture.patchBodies.push(payload)
      if (payload.expected_revision !== fixture.job.transcript_revision) {
        return json({ error: 'transcript_revision_conflict', message: 'Transcript revision is stale' }, 409)
      }
      const edits = new Map(payload.segments.map((segment) => [segment.segment_id, segment.text.trim()]))
      fixture.job = {
        ...fixture.job,
        text: fixture.job.segments.map((segment) => edits.get(segment.segment_id)).join(' '),
        segments: fixture.job.segments.map((segment) => ({ ...segment, text: edits.get(segment.segment_id) })),
        transcript_revision: fixture.job.transcript_revision + 1,
        transcript_edited: true,
        transcript_updated_at: new Date().toISOString(),
      }
      return json(fixture.job)
    }
    if (url.pathname.includes('/exports/') && method === 'GET') {
      const format = url.pathname.split('/').at(-1)
      fixture.exports.push(format)
      const bodies = {
        txt: `${fixture.job.text}\n`,
        srt: `1\n00:00:00,100 --> 00:00:01,400\n${fixture.job.segments[0].text}\n`,
        vtt: `WEBVTT\n\n00:00:00.100 --> 00:00:01.400\n${fixture.job.segments[0].text}\n`,
        json: JSON.stringify({ schema_version: 'vassil.transcript.v1', transcript: fixture.job }),
      }
      return route.fulfill({
        status: 200,
        contentType: format === 'json' ? 'application/json' : 'text/plain; charset=utf-8',
        headers: { 'Content-Disposition': `attachment; filename="transcript-12345678.${format}"` },
        body: bodies[format],
      })
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

async function openRoute(page, route) {
  const response = await page.goto(`${baseUrl}/studio#/${route}`, { waitUntil: 'networkidle' })
  if (response && !response.ok()) throw new Error(`${route}: Studio returned ${response.status()}`)
  await page.evaluate(() => document.fonts.ready)
}

async function assertNoOverflow(page, label) {
  const metrics = await page.evaluate(() => ({
    documentOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    dialogOverflow: (() => {
      const dialog = document.querySelector('[role="dialog"]')
      return dialog ? dialog.scrollWidth - dialog.clientWidth : 0
    })(),
  }))
  if (metrics.documentOverflow > 1 || metrics.dialogOverflow > 1) {
    throw new Error(`${label}: horizontal overflow ${JSON.stringify(metrics)}`)
  }
}

await fs.mkdir(outputDir, { recursive: true })
const browser = await chromium.launch({ channel: executablePath ? undefined : channel, executablePath, headless: true })

try {
  for (const viewport of viewports) {
    const page = await browser.newPage({
      viewport: { width: viewport.width, height: viewport.height },
      colorScheme: 'light',
      reducedMotion: 'reduce',
      acceptDownloads: true,
    })
    const errors = captureBrowserErrors(page)
    const fixture = { job: completedJob(), patchBodies: [], exports: [] }
    await installFixture(page, fixture)
    await openRoute(page, 'transcribe')

    await page.getByRole('button', { name: 'Review', exact: true }).first().click()
    await page.getByRole('heading', { name: 'Review transcript' }).waitFor()
    await page.getByText('2 timed segments', { exact: true }).waitFor()
    await page.locator('audio[aria-label^="Review source audio"]').waitFor()
    await assertNoOverflow(page, `${viewport.name} review`)

    await page.getByRole('button', { name: /Play segment 2 at/ }).click()
    await page.waitForTimeout(150)
    await page.locator('[data-active="true"]').getByText('Raw second sentence.', { exact: true }).waitFor()
    const seekTime = await page.locator('audio[aria-label^="Review source audio"]').evaluate((audio) => audio.currentTime)
    if (seekTime < 1.3) throw new Error(`${viewport.name}: segment seek stopped at ${seekTime}`)

    await page.getByRole('button', { name: 'Edit', exact: true }).click()
    await page.getByRole('textbox', { name: 'Edit segment 1' }).fill('Corrected first sentence.')
    await page.getByRole('button', { name: 'Close transcript review' }).click()
    await page.getByText('Unsaved transcript changes will be lost.', { exact: true }).waitFor()
    await page.getByRole('button', { name: 'Keep editing' }).click()

    const patchResponse = page.waitForResponse((response) => (
      response.request().method() === 'PATCH' && new URL(response.url()).pathname.endsWith('/transcript')
    ))
    await page.getByRole('button', { name: 'Save revision' }).click()
    await patchResponse
    await page.getByText('Revision 1', { exact: true }).first().waitFor()
    if (fixture.patchBodies.length !== 1 || fixture.patchBodies[0].expected_revision !== 0) {
      throw new Error(`${viewport.name}: transcript revision payload was not optimistic`)
    }

    await page.getByText('Original model result', { exact: true }).click()
    await page.getByText('Raw first sentence. Raw second sentence.', { exact: true }).waitFor()

    const downloadPromise = page.waitForEvent('download')
    await page.getByRole('button', { name: 'SRT', exact: true }).click()
    const download = await downloadPromise
    if (download.suggestedFilename() !== 'transcript-12345678.srt') {
      throw new Error(`${viewport.name}: unexpected export filename ${download.suggestedFilename()}`)
    }
    if (!fixture.exports.includes('srt')) throw new Error(`${viewport.name}: SRT export endpoint was not called`)

    await page.getByRole('button', { name: 'Close transcript review' }).click()
    await page.getByRole('heading', { name: 'Review transcript' }).waitFor({ state: 'hidden' })
    await page.getByRole('button', { name: 'Review', exact: true }).first().click()
    await page.getByText('Corrected first sentence.', { exact: true }).waitFor()
    await page.getByRole('button', { name: 'Close transcript review' }).click()

    await openRoute(page, 'jobs')
    await page.getByRole('button', { name: 'Review', exact: true }).first().click()
    await page.getByRole('heading', { name: 'Review transcript' }).waitFor()
    await page.getByText('Corrected first sentence.', { exact: true }).waitFor()
    await assertNoOverflow(page, `${viewport.name} jobs review`)

    await page.screenshot({ path: path.join(outputDir, `transcript-review-${viewport.name}.png`), fullPage: true })
    if (errors.length > 0) throw new Error(`${viewport.name}: browser errors: ${errors.join(' | ')}`)
    await page.close()
  }
} finally {
  await browser.close()
}

console.log(`Transcript review QA passed: ${outputDir}`)
