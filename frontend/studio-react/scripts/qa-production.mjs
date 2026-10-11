import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import path from 'node:path'
import { chromium } from 'playwright'
import { ttsModelCatalog } from './tts-model-fixture.mjs'
import { parseBatchImport } from '../src/lib/batch-import.ts'

const baseUrl = (process.env.VASSIL_QA_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')
const outputDir = process.env.VASSIL_QA_OUTPUT_DIR || 'artifacts/ui-qa/production'
const browser = await chromium.launch(process.env.PLAYWRIGHT_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH } : { channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome' })
const passed = []
const now = '2026-10-11T08:00:00Z'
const token = 'f'.repeat(64)
const pageResult = (items) => ({ items, total: items.length })
// Short PCM fixture exercises the audio element, without running inference.
const wav = Buffer.alloc(44 + 4800 * 2)
wav.write('RIFF', 0); wav.writeUInt32LE(wav.length - 8, 4); wav.write('WAVEfmt ', 8); wav.writeUInt32LE(16, 16)
wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22); wav.writeUInt32LE(24000, 24); wav.writeUInt32LE(48000, 28)
wav.writeUInt16LE(2, 32); wav.writeUInt16LE(16, 34); wav.write('data', 36); wav.writeUInt32LE(9600, 40)
for (let i = 0; i < 4800; i++) wav.writeInt16LE(Math.round(Math.sin(i * 2 * Math.PI * 220 / 24000) * 1000), 44 + i * 2)


async function fixture(page, scopes = ['*']) {
  const state = { requests: [], conflict: false, auth: false, accounts: [], keys: [], batch: null, catalog: ttsModelCatalog(), dictionary: { project_id: 'p1', revision: 1, entries: [] } }
  state.project = { project_id: 'p1', name: 'Training launch', description: 'Onboarding audio', owner_id: 'owner', members: [], revision: 1, created_at: now, updated_at: now }
  state.segment = { segment_id: 's1', project_id: 'p1', external_id: 'welcome', text: 'Xin chào đội ngũ.', language: 'vi', voice_id: 'v1', model_id: 'zipvoice-vi', position: 0, revision: 1, script_revision: 1, selected_take_id: null, created_at: now, updated_at: now }
  state.takes = ['take-a', 'take-b'].map((take_id, index) => ({ take_id, project_id: 'p1', segment_id: 's1', segment_revision: 1, model_id: index ? 'vieneu-v3-turbo' : 'zipvoice-vi', status: 'succeeded', review_status: 'pending', revision: 1, audio_url: `/api/v1/projects/p1/takes/${take_id}/audio`, error: null, review_note: '', created_at: now }))
  await page.route('**/*', async (route) => {
    const request = route.request(), url = new URL(request.url()), p = url.pathname, method = request.method()
    const body = request.postData() ? (() => { try { return request.postDataJSON() } catch { return null } })() : null
    const json = (value, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(value) })
    if (p.startsWith('/api/') && method !== 'GET') state.requests.push({ p, method, body, key: request.headers()['idempotency-key'] })
    if (p === '/api/v1/auth/status') return json({ auth_required: state.auth, authenticated: !state.auth, setup_required: false, user: null })
    if (p === '/api/v1/auth/key-login') { state.auth = false; return json({ authenticated: true, user: { account_id: 'svc1', username: 'Review bot', role: 'reviewer' }, expires_at: now }) }
    if (p === '/model-status') return json({ ready: true, runtime: { asr_loaded: false, tts_loaded: false } })
    if (p === '/api/v1/auth/principal') return json({ principal_id: 'owner', name: 'Workspace owner', kind: 'owner', role: scopes.includes('*') ? 'owner' : 'reviewer', scopes })
    if (p === '/api/v1/tts/models') return json(state.catalog)
    if (p === '/api/v1/tts/models/deployments') return json({ deployments: [{ model_id: 'zipvoice-vi', enabled: true, active_version: 'current-version', activated_at: now }], versions: [{ model_id: 'zipvoice-vi', version: 'old-version', created_at: now }] })
    if (p === '/api/v1/tts/models/import') return json(state.catalog)
    if (/\/tts\/models\/[^/]+\/(activate|unload|warmup|disable|enable|rollback)$/.test(p)) return json(state.catalog)
    if (p === '/api/v1/voices') return json([{ voice_id: 'v1', name: 'Training narrator', language: 'vi', reference_text: 'Reference', reference_audio_url: '', reference_text_source: 'user', duration_seconds: 4, sample_rate: 24000 }])
    if (p === '/api/v1/tts/jobs' || p === '/api/v1/asr/jobs') return json([])
    if (p === '/api/v1/projects') return json(pageResult([state.project]))
    if (p === '/api/v1/projects/p1') return json(state.project)
    if (p === '/api/v1/projects/p1/members') return json({ revision: 1, members: [], owner_id: 'owner' })
    if (p === '/api/v1/projects/p1/segments') return json(pageResult([state.segment]))
    if (p === '/api/v1/projects/p1/segments/s1') {
      if (method === 'PATCH') {
        assert(!('external_id' in body), 'immutable external ID is not patched')
        if (state.conflict) { state.conflict = false; return json({ detail: 'Revision changed on server', request_id: 'conflict-test' }, 409) }
        assert.equal(body.expected_revision, state.segment.revision)
        state.segment = { ...state.segment, ...body, revision: state.segment.revision + 1, script_revision: state.segment.revision + 1, selected_take_id: null }
      }
      return json(state.segment)
    }
    if (p.endsWith('/segments/s1/revisions')) return json({ items: [state.segment] })
    if (p.endsWith('/segments/s1/takes')) {
      if (method === 'POST') { assert(request.headers()['idempotency-key']); return json(state.takes[0], 202) }
      return json(pageResult(state.takes))
    }
    if (p.endsWith('/segments/s1/selection')) { assert.equal(body.expected_revision, state.segment.revision); state.segment.selected_take_id = body.take_id; state.segment.revision++; return json(state.segment) }
    if (/\/takes\/[^/]+\/review$/.test(p)) {
      const take = state.takes.find((t) => p.includes(t.take_id))
      assert.equal(body.expected_revision, take.revision)
      Object.assign(take, { review_status: body.status, review_note: body.note, revision: take.revision + 1 })
      return json(take)
    }
    if (p.endsWith('/audio')) return route.fulfill({ contentType: 'audio/wav', body: wav })
    if (p === '/api/v1/projects/p1/dictionary') {
      if (method === 'PUT') state.dictionary = { ...state.dictionary, entries: body.entries, revision: state.dictionary.revision + 1 }
      return json(state.dictionary)
    }
    if (p.endsWith('/dictionary/preview')) return json({ normalized_text: body.text.replace('API', 'ây pi ai') })
    if (p === '/api/v1/batches/analyze') return json({ can_submit: true, errors: [], row_count: body.rows.length, preflight_token: token, dictionary_revision: 1, rows: body.rows.map((row, i) => ({ ...row, row_number: i + 1, normalized_text: row.text, model_id: body.defaults.model_id || 'zipvoice-vi', voice_id: body.defaults.voice_id || 'v1', errors: [], warnings: [] })) })
    if (p === '/api/v1/batches') {
      if (method === 'POST') { assert.equal(body.preflight_token, token); assert(request.headers()['idempotency-key']); state.batch = { batch_id: 'b1', project_id: 'p1', name: body.name, status: 'completed_with_errors', item_count: 2, counts: { pending: 0, queued: 0, running: 0, succeeded: 1, failed: 1, cancelled: 0 }, created_at: now, updated_at: now }; return json(state.batch, 202) }
      return json(pageResult(state.batch ? [state.batch] : []))
    }
    if (p === '/api/v1/batches/b1' || p.endsWith('/retry-failed')) return json(state.batch)
    if (p.endsWith('/batches/b1/items')) return json(pageResult([{ ...state.takes[0], item_id: 'i1', external_id: 'welcome', row_number: 1, segment_id: 's1', take_id: 'take-a', status: 'succeeded', review_status: state.takes[0].review_status, text: 'Welcome', model_id: 'zipvoice-vi' }, { ...state.takes[1], item_id: 'i2', external_id: 'goodbye', row_number: 2, segment_id: 's1', take_id: 'take-b', status: 'failed', review_status: 'pending', text: 'Goodbye', model_id: 'zipvoice-vi', error: 'Example unavailable runtime' }]))
    if (p.endsWith('/export')) return route.fulfill({ contentType: 'application/zip', body: Buffer.from('test-export') })
    if (p === '/api/v1/auth/service-accounts') {
      if (method === 'POST') { const account = { ...body, principal_id: 'svc1', scopes: body.scopes || ['production:read'], created_at: now, disabled_at: null }; state.accounts.push(account); return json(account, 201) }
      return json(state.accounts)
    }
    if (p.endsWith('/service-accounts/svc1/keys')) { const key = { key_id: 'key1', principal_id: 'svc1', name: body.name, prefix: 'vvs_test', created_at: now, expires_at: null, revoked_at: null, last_used_at: null }; state.keys.push(key); return json({ key, token: 'vvs_once_only_test' }, 201) }
    if (p === '/api/v1/auth/api-keys') return json(state.keys)
    if (p.endsWith('/api-keys/key1')) { state.keys[0].revoked_at = now; return json({ revoked: true }) }
    if (p === '/api/v1/auth/audit') return json([{ event_id: 1, created_at: now, actor_id: 'owner', action: 'production.take.review', resource_id: 'take-a', request_id: 'qa-request' }])
    if (p.startsWith('/api/')) throw new Error(`Unexpected fixture request ${method} ${p}`)
    return route.continue()
  })
  return state
}

try {
  assert.deepEqual(parseBatchImport('id,script\n1,"Hello, world"\n2,"Line one\nLine two"').records, [{ id: '1', script: 'Hello, world' }, { id: '2', script: 'Line one\nLine two' }])
  assert.throws(() => parseBatchImport('text,text\na,b'), /unique|duplicate/i)
  assert.throws(() => parseBatchImport('[{"text":{"nested":true}}]'), /value|text|scalar|simple/i)
  passed.push('CSV quoted comma/newline and malformed-input validation')
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' })
  page.setDefaultTimeout(12000)
  const errors = []; page.on('pageerror', (error) => errors.push(error.message))
  const state = await fixture(page)
  await page.goto(`${baseUrl}/studio/#/projects?project=p1`)
  await page.getByRole('heading', { name: 'Segment editor' }).waitFor()
  await page.getByRole('button', { name: 'Compare', exact: true }).nth(0).click()
  await page.getByRole('button', { name: 'Compare', exact: true }).nth(0).click()
  await page.getByLabel('Compare takes').waitFor()
  await page.getByRole('button', { name: 'Approve take', exact: true }).first().click()
  await page.getByRole('button', { name: 'Select for export', exact: true }).first().click()
  await page.getByText('Selected for export', { exact: true }).waitFor()
  await page.getByLabel('Take model', { exact: true }).selectOption('vieneu-v3-turbo')
  await Promise.all([page.waitForResponse((r) => r.request().method() === 'POST' && r.url().endsWith('/segments/s1/takes')), page.getByRole('button', { name: 'Render new take', exact: true }).click()])
  assert.equal(state.requests.find((r) => r.p.endsWith('/segments/s1/takes')).body.model_id, 'vieneu-v3-turbo')
  assert.equal(state.requests.find((r) => r.p.endsWith('/segments/s1/takes')).body.expected_revision, 2)
  passed.push('A/B takes, approval, selection, model override preserves script revision')
  state.conflict = true
  await page.getByLabel('Script text').fill('My unsaved edit')
  await page.getByRole('button', { name: 'Save revision', exact: true }).click()
  await page.getByText('Revision changed on server').waitFor()
  assert.equal(await page.getByLabel('Script text').inputValue(), 'My unsaved edit')
  await page.getByRole('button', { name: 'Reload latest', exact: true }).click()
  await page.waitForFunction(() => document.querySelector('textarea')?.value === 'Xin chào đội ngũ.')
  await page.getByLabel('Script text').fill('Updated script')
  await page.getByRole('button', { name: 'Save revision', exact: true }).click()
  await page.getByText('Script revision 3 · Saved').waitFor()
  passed.push('Optimistic conflict preserves draft and explicit reload then save')
  await page.getByRole('button', { name: 'Pronunciation', exact: true }).click()
  await page.getByRole('button', { name: 'Add pronunciation' }).click()
  await page.getByLabel('Source 1').fill('API')
  await page.getByLabel('Pronunciation 1').fill('ây pi ai')
  await page.getByRole('button', { name: 'Save dictionary revision' }).click()
  await page.getByText(/Version 2\./).waitFor()
  await page.getByLabel('Preview text').fill('API')
  await page.getByRole('button', { name: 'Preview saved pronunciation' }).click()
  await page.getByRole('status').filter({ hasText: 'ây pi ai' }).waitFor()
  await fs.mkdir(outputDir, { recursive: true })
  await page.screenshot({ path: path.join(outputDir, 'project-dictionary.png'), fullPage: true })
  passed.push('Versioned pronunciation save and server preview')
  await page.goto(`${baseUrl}/studio/#/batches`)
  await page.getByLabel('Project', { exact: true }).selectOption('p1')
  await page.getByLabel('CSV or JSON file').setInputFiles({ name: 'onboarding.csv', mimeType: 'text/csv', buffer: Buffer.from('id,script\nwelcome,Welcome\ngoodbye,Goodbye') })
  await page.getByLabel('Map external_id').selectOption('id')
  await page.getByLabel('Map text').selectOption('script')
  await page.getByLabel('Default voice').selectOption('v1')
  await page.getByRole('button', { name: '2. Validate rows' }).click()
  await page.getByRole('button', { name: '3. Queue 2 rows' }).waitFor()
  await page.getByLabel('Batch name').fill('Validated release')
  await page.getByText('Import settings changed. Validate again before submitting.').waitFor()
  assert.equal(await page.getByRole('button', { name: '3. Queue 2 rows' }).count(), 0)
  await page.getByRole('button', { name: '2. Validate rows' }).click()
  await page.getByRole('button', { name: '3. Queue 2 rows' }).click()
  await page.getByText('2 of 2 finished').waitFor()
  await page.getByRole('checkbox', { name: 'Retry goodbye' }).check()
  await Promise.all([page.waitForResponse((r) => r.url().endsWith('/retry-failed')), page.getByRole('button', { name: 'Retry 1 selected items' }).click()])
  assert.deepEqual(state.requests.find((r) => r.p.endsWith('/retry-failed')).body.item_ids, ['i2'])
  await page.getByRole('button', { name: 'Review audio' }).first().click()
  await page.getByLabel('Review welcome').waitFor()
  const download = page.waitForEvent('download'); await page.getByRole('button', { name: 'Export approved results' }).click(); await download
  await page.screenshot({ path: path.join(outputDir, 'batch-review.png'), fullPage: true })
  passed.push('Column mapping, stale-preflight invalidation, token submission, grouped progress, selected retry and export')
  await page.goto(`${baseUrl}/studio/#/models`)
  await page.getByRole('button', { name: 'Activate current version' }).first().click()
  await page.getByText(/configured language default remains unchanged/).waitFor()
  await page.getByRole('button', { name: 'Apply model change' }).click()
  await page.getByLabel('Version history for ZipVoice Vietnamese').selectOption('old-version')
  await page.getByRole('button', { name: 'Rollback', exact: true }).click()
  await page.getByRole('button', { name: 'Rollback version' }).click()
  await page.getByLabel('Model profile JSON').fill('{invalid')
  await page.getByRole('button', { name: 'Import profile', exact: true }).click()
  await page.getByRole('alert').waitFor()
  await page.getByLabel('Model profile JSON').fill(JSON.stringify({ model_id: 'example', engine: 'vieneu', label: 'Example', languages: ['vi'], sample_rate: 24000, options: {} }))
  await page.getByRole('button', { name: 'Import profile', exact: true }).click()
  await page.getByText(/Profile imported/).waitFor()
  passed.push('Model activation semantics, recorded-version rollback, import validation')
  await page.goto(`${baseUrl}/studio/#/administration`)
  await page.getByLabel('System name').fill('Review pipeline')
  await page.getByLabel('Account role').selectOption('reviewer')
  await page.getByRole('button', { name: 'Create service account', exact: true }).click()
  await page.getByLabel('Key name').fill('Integration')
  await page.getByRole('button', { name: 'Issue key', exact: true }).click()
  await page.getByText('vvs_once_only_test', { exact: true }).waitFor()
  assert.equal(await page.evaluate(() => Object.values(localStorage).some((value) => value.includes('vvs_once_only_test'))), false)
  await page.getByRole('button', { name: /I saved it/ }).click()
  assert.equal(await page.getByText('vvs_once_only_test', { exact: true }).count(), 0)
  await page.getByRole('button', { name: 'Revoke', exact: true }).click()
  await page.getByRole('button', { name: 'Revoke key', exact: true }).click()
  await page.getByText('revoked', { exact: true }).waitFor()
  passed.push('Named service identity, one-time credential with no local storage and revocation')
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(`${baseUrl}/studio/#/projects?project=p1`)
  await page.getByRole('heading', { name: 'Segment editor' }).waitFor()
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true)
  await page.screenshot({ path: path.join(outputDir, 'project-mobile.png'), fullPage: true })
  assert.deepEqual(errors, [])
  await page.close()
  const reader = await browser.newPage()
  const readerState = await fixture(reader, ['production:read', 'production:review', 'models:read'])
  await reader.goto(`${baseUrl}/studio/#/administration`)
  await reader.getByRole('heading', { name: 'Administrator access required' }).waitFor()
  assert.equal(readerState.requests.length, 0)
  await reader.goto(`${baseUrl}/studio/#/models`)
  await reader.getByText(/Model management scope|model management scope|operator with model management scope/).waitFor()
  assert.equal(await reader.getByRole('button', { name: 'Activate current version' }).first().isDisabled(), true)
  readerState.auth = true
  await reader.goto(`${baseUrl}/login`)
  await reader.getByRole('button', { name: 'Service access key', exact: true }).click()
  await reader.getByLabel('Service access key', { exact: true }).fill('test-scoped-key')
  await reader.getByRole('button', { name: 'Open Studio' }).click()
  await reader.waitForURL((url) => url.pathname === '/studio' || url.pathname.startsWith('/studio/'))
  assert.equal(readerState.requests.find((r) => r.p.endsWith('/key-login')).body.api_key, 'test-scoped-key')
  passed.push('Responsive project editor, read-only administration/model controls and scoped cookie login')
  await fs.writeFile(path.join(outputDir, 'report.json'), JSON.stringify({ status: 'passed', passed }, null, 2))
  console.log(JSON.stringify({ status: 'passed', passed }, null, 2))
} finally { await browser.close() }
