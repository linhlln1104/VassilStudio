import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { chromium } from 'playwright'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const repositoryRoot = path.resolve(scriptDir, '..', '..', '..')
const baseUrl = (process.env.VASSIL_QA_BASE_URL || 'http://127.0.0.1:8022').replace(/\/$/, '')
const outputDir = process.env.VASSIL_QA_OUTPUT_DIR || path.join(repositoryRoot, 'artifacts', 'ui-qa', 'settings')
const channel = process.env.PLAYWRIGHT_CHANNEL || 'chrome'
const executablePath = process.env.PLAYWRIGHT_EXECUTABLE_PATH

const viewports = [
  { name: 'desktop', width: 1440, height: 1000 },
  { name: 'mobile', width: 390, height: 844 },
]

function settingsFixture() {
  const modelChecks = {
    asr_vi_encoder: true,
    asr_vi_decoder: true,
    asr_vi_joiner: true,
    asr_vi_tokens: true,
    asr_en_encoder: true,
    asr_en_decoder: true,
    asr_en_joiner: true,
    asr_en_tokens: true,
    tts_vi_encoder: true,
    tts_vi_decoder: true,
    tts_vi_vocoder: true,
    tts_vi_tokens: true,
    tts_vi_lexicon: true,
    tts_vi_data_dir: true,
    tts_en_encoder: true,
    tts_en_decoder: true,
    tts_en_vocoder: false,
    tts_en_tokens: true,
    tts_en_lexicon: true,
    tts_en_data_dir: true,
  }
  const runtime = {
    environment: 'local',
    log_level: 'INFO',
    provider: 'cpu',
    num_threads: 4,
    asr_num_threads: 4,
    tts_num_threads: 8,
    debug: false,
    warmup_on_startup: false,
    asr_job_workers: 1,
    tts_job_workers: 1,
    asr_job_max_attempts: 3,
    tts_job_max_attempts: 3,
    job_retry_backoff_seconds: 0.5,
    asr_loaded: true,
    tts_loaded: false,
    asr_configured_languages: ['vi', 'en'],
    asr_loaded_languages: ['vi'],
    tts_configured_languages: ['vi', 'en'],
    tts_loaded_languages: [],
  }
  const storage = [
    storageItem('data', 'DATA_ROOT', true, true, '1_to_9_gb', '100_to_999'),
    storageItem('voices', 'DATA_ROOT/voices', true, true, '100_to_999_mb', '10_to_99'),
    storageItem('asr_jobs', 'DATA_ROOT/jobs/asr', true, true, '100_to_999_mb', '10_to_99'),
    storageItem('tts_jobs', 'DATA_ROOT/jobs/tts', true, true, '100_to_999_mb', '10_to_99'),
    storageItem('uploads', 'DATA_ROOT/uploads', true, true, '1_to_99_mb', '10_to_99'),
    storageItem('outputs', 'DATA_ROOT/outputs', true, true, '100_to_999_mb', '10_to_99'),
    storageItem('logs', 'LOGS_ROOT', false, true, 'empty', 'none'),
    { ...storageItem('auth_db', 'DATA_ROOT/auth.sqlite3', false, true, 'empty', 'none'), is_dir: false },
  ]
  const readinessChecks = {
    ...modelChecks,
    storage_data_dir: true,
    storage_voices_dir: true,
    storage_asr_jobs_dir: true,
    storage_tts_jobs_dir: true,
    storage_uploads_dir: true,
    storage_outputs_dir: true,
    storage_logs_dir: false,
  }

  return {
    health: {
      status: 'ok',
      version: '0.9.0-qa',
      privacy: {
        storage_paths: 'logical_aliases',
        storage_metrics: 'bucketed',
        host_metadata_included: false,
      },
      asr_enabled: true,
      tts_enabled: true,
      provider: 'cpu',
      asr_loaded: true,
      tts_loaded: false,
    },
    liveness: { status: 'ok', checks: {} },
    readiness: { status: 'not_ready', checks: readinessChecks },
    model: { ready: false, checks: modelChecks, runtime },
    diagnostics: {
      generated_at: '2026-08-23T15:00:00Z',
      version: '0.9.0-qa',
      runtime,
      security: {
        auth_required: false,
        api_key_auth_enabled: true,
        session_cookie_name: 'vassil_session',
        session_ttl_seconds: 604800,
        secure_cookies: false,
      },
      storage,
      license: { status: 'open-source', plan: 'GPL-3.0-or-later', billing_enabled: false },
    },
    auth: {
      auth_required: false,
      setup_required: false,
      authenticated: true,
      api_key_auth_enabled: true,
      user: null,
    },
    calls: {
      ready: 0,
      diagnostics: 0,
      warmup: [],
      cleanup: [],
      bundles: [],
      protectedRequests: [],
      logouts: 0,
    },
  }
}

function storageItem(name, pathAlias, exists, writable, usageBucket, fileCountBucket) {
  return {
    name,
    path_alias: pathAlias,
    exists,
    is_dir: true,
    writable,
    usage_bucket: usageBucket,
    file_count_bucket: fileCountBucket,
    capacity_bucket: '100_to_499_gb',
    free_space_bucket: '10_to_49_gb',
    storage_pressure: 'normal',
  }
}

async function installApiFixture(page, fixture) {
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
      return json(fixture.auth)
    }
    if (url.pathname === '/api/v1/auth/logout' && method === 'POST') {
      fixture.calls.logouts += 1
      fixture.auth.authenticated = false
      fixture.auth.user = null
      return json({ logged_out: true })
    }
    if (url.pathname === '/health') {
      return json(fixture.health)
    }
    if (url.pathname === '/livez') {
      return json(fixture.liveness)
    }
    if (url.pathname === '/readyz') {
      fixture.calls.ready += 1
      return json(fixture.readiness, fixture.readiness.status === 'ready' ? 200 : 503)
    }
    if (url.pathname === '/model-status') {
      fixture.calls.protectedRequests.push({
        path: url.pathname,
        apiKey: request.headers()['x-vassil-api-key'] ?? null,
      })
      return json(fixture.model)
    }
    if (url.pathname === '/diagnostics' && method === 'GET') {
      fixture.calls.diagnostics += 1
      return json(fixture.diagnostics)
    }
    if (url.pathname === '/diagnostics/bundle' && method === 'GET') {
      fixture.calls.bundles.push(url.searchParams.get('include_host_metadata') === 'true')
      return route.fulfill({
        status: 200,
        contentType: 'application/zip',
        body: Buffer.from('PK\u0003\u0004vassil-qa-bundle'),
      })
    }
    if ((url.pathname === '/warmup/asr' || url.pathname === '/warmup/tts') && method === 'POST') {
      const engine = url.pathname.endsWith('/asr') ? 'asr' : 'tts'
      const language = url.searchParams.get('language') || 'vi'
      fixture.calls.warmup.push({ engine, language })
      const loadedLanguages = fixture.model.runtime[`${engine}_loaded_languages`]
      if (!loadedLanguages.includes(language)) loadedLanguages.push(language)
      fixture.model.runtime[`${engine}_loaded`] = true
      fixture.health[`${engine}_loaded`] = true
      return json({ loaded: true, loaded_languages: loadedLanguages })
    }
    if (url.pathname === '/warmup' && method === 'POST') {
      fixture.calls.warmup.push({ engine: 'all', language: 'all' })
      fixture.model.runtime.asr_loaded_languages = ['vi', 'en']
      fixture.model.runtime.tts_loaded_languages = ['vi', 'en']
      fixture.model.runtime.asr_loaded = true
      fixture.model.runtime.tts_loaded = true
      fixture.health.asr_loaded = true
      fixture.health.tts_loaded = true
      return json({
        asr_loaded: true,
        tts_loaded: true,
        asr_loaded_languages: ['vi', 'en'],
        tts_loaded_languages: ['vi', 'en'],
      })
    }
    if ((url.pathname === '/api/v1/tts/jobs' || url.pathname === '/api/v1/asr/jobs') && method === 'DELETE') {
      fixture.calls.cleanup.push({ path: url.pathname, maxAge: url.searchParams.get('max_age_seconds') })
      return json({
        deleted: url.pathname.includes('/tts/') ? 2 : 1,
        job_ids: url.pathname.includes('/tts/') ? ['tts-old-1', 'tts-old-2'] : ['asr-old-1'],
      })
    }

    return route.continue()
  })
}

function captureBrowserErrors(page) {
  const errors = []
  page.on('console', (message) => {
    const text = message.text()
    if (message.type() === 'error' && !text.includes('status of 503')) errors.push(`console: ${text}`)
  })
  page.on('pageerror', (error) => errors.push(`page: ${error.message}`))
  return errors
}

async function assertStudioResponse(page) {
  const response = await page.goto(`${baseUrl}/studio#/settings`, { waitUntil: 'networkidle' })
  if (!response || !response.ok()) {
    throw new Error(`Studio returned ${response?.status() ?? 'no response'}`)
  }
  await page.evaluate(() => document.fonts.ready)
  await page.getByRole('button', { name: 'Runtime', exact: true }).waitFor({ state: 'visible' })
}

async function layoutMetrics(page) {
  return page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: document.documentElement.clientWidth,
    horizontalOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  }))
}

async function dismissNotifications(page) {
  const dismissButtons = page.getByRole('button', { name: 'Dismiss notification' })
  while (await dismissButtons.count()) {
    await dismissButtons.first().click()
  }
}

await fs.mkdir(outputDir, { recursive: true })

const browser = await chromium.launch({
  channel: executablePath ? undefined : channel,
  executablePath,
  headless: true,
})

const report = { baseUrl, generatedAt: new Date().toISOString(), viewports: [] }

try {
  for (const viewport of viewports) {
    const page = await browser.newPage({
      viewport: { width: viewport.width, height: viewport.height },
      colorScheme: 'light',
      reducedMotion: 'reduce',
      acceptDownloads: true,
    })
    const fixture = settingsFixture()
    const browserErrors = captureBrowserErrors(page)
    await page.addInitScript(() => {
      window.localStorage.setItem('vassil.apiKey', 'retired-current-key')
      window.localStorage.setItem('vvoice.apiKey', 'retired-legacy-key')
    })
    await installApiFixture(page, fixture)
    await assertStudioResponse(page)

    await page.getByText('Runtime setup needs attention', { exact: true }).waitFor({ state: 'visible' })
    await page.getByText('English TTS vocoder', { exact: true }).first().waitFor({ state: 'visible' })
    await page.getByText('Logs storage', { exact: true }).first().waitFor({ state: 'visible' })
    await page.getByRole('button', { name: 'Warm all models' }).isDisabled().then((disabled) => {
      if (!disabled) throw new Error(`${viewport.name}: warm-all should be blocked while model assets are missing`)
    })

    const ttsWarmResponse = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return response.request().method() === 'POST' && url.pathname === '/warmup/tts' && url.searchParams.get('language') === 'vi'
    })
    await page.getByRole('button', { name: 'Warm Vietnamese TTS' }).click()
    await ttsWarmResponse
    await page.getByText('Warmup complete', { exact: true }).waitFor({ state: 'visible' })
    if (fixture.calls.warmup.length !== 1 || fixture.calls.warmup[0].language !== 'vi') {
      throw new Error(`${viewport.name}: language-specific TTS warmup was not preserved`)
    }

    const readyCallsBeforeRefresh = fixture.calls.ready
    const readinessRefresh = page.waitForResponse((response) => new URL(response.url()).pathname === '/readyz')
    await page.getByRole('button', { name: 'Run diagnostics', exact: true }).click()
    await readinessRefresh
    await page.getByText('Diagnostics complete', { exact: true }).waitFor({ state: 'visible' })
    if (fixture.calls.ready <= readyCallsBeforeRefresh) {
      throw new Error(`${viewport.name}: diagnostics did not refresh readiness`)
    }

    const downloadPromise = page.waitForEvent('download')
    await page.getByRole('button', { name: 'Download bundle', exact: true }).click()
    const download = await downloadPromise
    if (!download.suggestedFilename().startsWith('vassilstudio-diagnostics-')) {
      throw new Error(`${viewport.name}: diagnostics download filename is not productized`)
    }
    if (fixture.calls.bundles.length !== 1 || fixture.calls.bundles[0] !== false) {
      throw new Error(`${viewport.name}: privacy-filtered support bundle was not requested by default`)
    }
    await page.getByRole('checkbox', { name: 'Host details' }).check()
    const hostDownloadPromise = page.waitForEvent('download')
    await page.getByRole('button', { name: 'Download bundle', exact: true }).click()
    await hostDownloadPromise
    if (fixture.calls.bundles.length !== 2 || fixture.calls.bundles[1] !== true) {
      throw new Error(`${viewport.name}: host metadata was not an explicit bundle opt-in`)
    }
    if (await page.getByRole('checkbox', { name: 'Host details' }).isChecked()) {
      throw new Error(`${viewport.name}: host metadata opt-in was not reset after download`)
    }
    await dismissNotifications(page)

    const runtimeLayout = await layoutMetrics(page)
    if (runtimeLayout.horizontalOverflow > 1) {
      throw new Error(`${viewport.name}: Runtime settings overflowed by ${runtimeLayout.horizontalOverflow}px`)
    }
    const runtimeScreenshot = path.join(outputDir, `settings-runtime-${viewport.name}.png`)
    await page.screenshot({ path: runtimeScreenshot, fullPage: true })

    await page.getByRole('button', { name: 'Account', exact: true }).click()
    await page.getByText('DATA_ROOT/auth.sqlite3', { exact: true }).waitFor({ state: 'visible' })
    const accountLayout = await layoutMetrics(page)
    if (accountLayout.horizontalOverflow > 1) {
      throw new Error(`${viewport.name}: Account settings overflowed by ${accountLayout.horizontalOverflow}px`)
    }
    const accountScreenshot = path.join(outputDir, `settings-account-${viewport.name}.png`)
    await page.screenshot({ path: accountScreenshot, fullPage: true })

    await page.getByRole('button', { name: 'Storage', exact: true }).click()
    await page.getByText('10-49 GB', { exact: true }).waitFor({ state: 'visible' })
    await page.getByText('Storage needs attention', { exact: true }).waitFor({ state: 'visible' })
    await page.getByText('6/7 ready', { exact: true }).waitFor({ state: 'visible' })

    const storageScreenshot = path.join(outputDir, `settings-storage-${viewport.name}.png`)
    await page.screenshot({ path: storageScreenshot, fullPage: true })

    await page.getByRole('button', { name: 'Clean jobs', exact: true }).click()
    const confirmDialog = page.getByRole('dialog')
    await confirmDialog.getByRole('heading', { name: 'Clean terminal jobs?' }).waitFor({ state: 'visible' })
    const cleanupResponses = Promise.all([
      page.waitForResponse((response) => response.request().method() === 'DELETE' && new URL(response.url()).pathname === '/api/v1/tts/jobs'),
      page.waitForResponse((response) => response.request().method() === 'DELETE' && new URL(response.url()).pathname === '/api/v1/asr/jobs'),
    ])
    await confirmDialog.getByRole('button', { name: 'Clean jobs', exact: true }).click()
    await cleanupResponses
    await page.getByText('Removed 3 terminal jobs (2 TTS, 1 ASR).', { exact: true }).waitFor({ state: 'visible' })

    if (fixture.calls.cleanup.length !== 2 || fixture.calls.cleanup.some((call) => call.maxAge !== '2592000')) {
      throw new Error(`${viewport.name}: 30-day retention was not sent to both queues`)
    }
    const storageLayout = await layoutMetrics(page)
    if (storageLayout.horizontalOverflow > 1) {
      throw new Error(`${viewport.name}: Storage settings overflowed by ${storageLayout.horizontalOverflow}px`)
    }

    await page.getByRole('button', { name: 'Security', exact: true }).click()
    await page.getByText('Browser access', { exact: true }).waitFor({ state: 'visible' })
    const retiredKeys = await page.evaluate(() => ({
      current: window.localStorage.getItem('vassil.apiKey'),
      legacy: window.localStorage.getItem('vvoice.apiKey'),
    }))
    if (retiredKeys.current !== null || retiredKeys.legacy !== null) {
      throw new Error(`${viewport.name}: retired localStorage API keys were not scrubbed`)
    }

    const apiKeyInput = page.locator('input[placeholder="Paste API key for protected endpoints"]')
    const sessionPersistence = page.getByRole('checkbox', { name: 'Keep through reloads in this tab' })
    const memorySecret = 'qa-memory-only-key'
    const memoryRequest = page.waitForResponse((response) => new URL(response.url()).pathname === '/model-status')
    await apiKeyInput.fill(memorySecret)
    await page.getByRole('button', { name: 'Use key', exact: true }).click()
    await memoryRequest
    const memoryCredential = fixture.calls.protectedRequests.at(-1)?.apiKey
    if (memoryCredential !== memorySecret) {
      throw new Error(`${viewport.name}: memory-only API key was not used for the protected request`)
    }
    if (await apiKeyInput.inputValue()) {
      throw new Error(`${viewport.name}: API key remained visible in the input after activation`)
    }
    if (await page.getByRole('button', { name: /Copy API key/i }).count()) {
      throw new Error(`${viewport.name}: API key copy control is still exposed`)
    }
    const memoryStorage = await page.evaluate(() => ({
      localCurrent: window.localStorage.getItem('vassil.apiKey'),
      localLegacy: window.localStorage.getItem('vvoice.apiKey'),
      session: window.sessionStorage.getItem('vassil.sessionApiKey'),
      bodyContainsSecret: document.body.textContent?.includes('qa-memory-only-key') ?? false,
    }))
    if (
      memoryStorage.localCurrent !== null
      || memoryStorage.localLegacy !== null
      || memoryStorage.session !== null
      || memoryStorage.bodyContainsSecret
    ) {
      throw new Error(`${viewport.name}: memory-only API key escaped into browser storage or DOM`)
    }

    const securityLayout = await layoutMetrics(page)
    if (securityLayout.horizontalOverflow > 1) {
      throw new Error(`${viewport.name}: Security settings overflowed by ${securityLayout.horizontalOverflow}px`)
    }
    const securityScreenshot = path.join(outputDir, `settings-security-${viewport.name}.png`)
    await page.screenshot({ path: securityScreenshot, fullPage: true })

    await page.reload({ waitUntil: 'networkidle' })
    await page.getByRole('button', { name: 'Security', exact: true }).click()
    await page.getByText('Not set', { exact: true }).waitFor({ state: 'visible' })

    const sessionSecret = 'qa-tab-session-key'
    await sessionPersistence.check()
    await apiKeyInput.fill(sessionSecret)
    const sessionRequest = page.waitForResponse((response) => new URL(response.url()).pathname === '/model-status')
    await page.getByRole('button', { name: 'Use key', exact: true }).click()
    await sessionRequest
    const sessionStorageValue = await page.evaluate(() => window.sessionStorage.getItem('vassil.sessionApiKey'))
    if (sessionStorageValue !== sessionSecret) {
      throw new Error(`${viewport.name}: session-only API key did not persist in this tab`)
    }

    await page.reload({ waitUntil: 'networkidle' })
    await page.getByRole('button', { name: 'Security', exact: true }).click()
    await page.getByText('Active', { exact: true }).waitFor({ state: 'visible' })
    if (!(await sessionPersistence.isChecked())) {
      throw new Error(`${viewport.name}: session-only key was not restored after reload`)
    }

    const ownerRequestsStart = fixture.calls.protectedRequests.length
    fixture.auth.auth_required = true
    fixture.auth.authenticated = true
    fixture.auth.user = { account_id: 'qa-owner', username: 'owner', role: 'owner' }
    await page.reload({ waitUntil: 'networkidle' })
    await page.getByRole('button', { name: 'Security', exact: true }).click()
    await page.getByText('Standby', { exact: true }).waitFor({ state: 'visible' })
    await page.getByText('Owner session active; the temporary key is not sent.', { exact: true })
      .waitFor({ state: 'visible' })
    const ownerRequests = fixture.calls.protectedRequests.slice(ownerRequestsStart)
    if (!ownerRequests.length || ownerRequests.some((request) => request.apiKey !== null)) {
      throw new Error(`${viewport.name}: owner session did not suppress the browser API key header`)
    }
    if (await page.evaluate(() => window.sessionStorage.getItem('vassil.sessionApiKey')) !== sessionSecret) {
      throw new Error(`${viewport.name}: owner-session preference unexpectedly destroyed the temporary key`)
    }

    await page.getByRole('button', { name: 'Sign out', exact: true }).click()
    await page.waitForURL('**/login')
    const signedOutStorage = await page.evaluate(() => ({
      session: window.sessionStorage.getItem('vassil.sessionApiKey'),
      current: window.localStorage.getItem('vassil.apiKey'),
      legacy: window.localStorage.getItem('vvoice.apiKey'),
    }))
    if (
      fixture.calls.logouts !== 1
      || signedOutStorage.session !== null
      || signedOutStorage.current !== null
      || signedOutStorage.legacy !== null
    ) {
      throw new Error(`${viewport.name}: sign-out did not clear temporary browser credentials`)
    }
    if (browserErrors.length) {
      throw new Error(`${viewport.name}: browser errors: ${browserErrors.join(' | ')}`)
    }

    report.viewports.push({
      ...viewport,
      warmupCalls: fixture.calls.warmup,
      readinessCalls: fixture.calls.ready,
      cleanupCalls: fixture.calls.cleanup,
      bundleDownloads: fixture.calls.bundles.length,
      bundleHostMetadataChoices: fixture.calls.bundles,
      runtimeLayout,
      accountLayout,
      storageLayout,
      securityLayout,
      runtimeScreenshot,
      accountScreenshot,
      storageScreenshot,
      securityScreenshot,
    })
    await page.close()
  }
} finally {
  await browser.close()
}

const reportPath = path.join(outputDir, 'report.json')
await fs.writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8')
console.log(`Settings workflow QA passed: ${report.viewports.length} viewports`)
console.log(`Artifacts: ${outputDir}`)
