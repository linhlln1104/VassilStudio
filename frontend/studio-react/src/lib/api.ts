const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''
export const SESSION_API_KEY_STORAGE_KEY = 'vassil.sessionApiKey'
const RETIRED_LOCAL_API_KEY_STORAGE_KEYS = ['vassil.apiKey', 'vvoice.apiKey'] as const

export type BrowserApiKeyPersistence = 'none' | 'memory' | 'session'

export type BrowserApiKeyState = {
  active: boolean
  persistence: BrowserApiKeyPersistence
}

let browserApiKey = ''
let browserApiKeyPersistence: BrowserApiKeyPersistence = 'none'
let browserApiKeyInitialized = false
let ownerSessionActive = false

export function getBrowserApiKeyState(): BrowserApiKeyState {
  initializeBrowserApiKey()
  return {
    active: Boolean(browserApiKey),
    persistence: browserApiKeyPersistence,
  }
}

export function setBrowserApiKey(
  apiKey: string,
  options: { persistForSession?: boolean } = {},
): BrowserApiKeyState {
  initializeBrowserApiKey()
  browserApiKey = apiKey.trim()
  if (!browserApiKey) {
    return clearBrowserApiKey()
  }

  browserApiKeyPersistence = options.persistForSession && writeSessionApiKey(browserApiKey)
    ? 'session'
    : 'memory'
  if (browserApiKeyPersistence === 'memory') {
    removeSessionApiKey()
  }
  return getBrowserApiKeyState()
}

export function setBrowserApiKeyPersistence(persistForSession: boolean): BrowserApiKeyState {
  initializeBrowserApiKey()
  if (!browserApiKey) {
    removeSessionApiKey()
    browserApiKeyPersistence = 'none'
    return getBrowserApiKeyState()
  }

  browserApiKeyPersistence = persistForSession && writeSessionApiKey(browserApiKey)
    ? 'session'
    : 'memory'
  if (browserApiKeyPersistence === 'memory') {
    removeSessionApiKey()
  }
  return getBrowserApiKeyState()
}

export function clearBrowserApiKey(): BrowserApiKeyState {
  browserApiKey = ''
  browserApiKeyPersistence = 'none'
  removeSessionApiKey()
  scrubRetiredLocalApiKeys()
  return { active: false, persistence: 'none' }
}

export function getRequestApiKey(): string {
  initializeBrowserApiKey()
  return ownerSessionActive ? '' : browserApiKey
}

function initializeBrowserApiKey(): void {
  if (browserApiKeyInitialized || typeof window === 'undefined') {
    return
  }
  browserApiKeyInitialized = true
  scrubRetiredLocalApiKeys()
  const sessionValue = readSessionApiKey()
  if (sessionValue) {
    browserApiKey = sessionValue
    browserApiKeyPersistence = 'session'
  }
}

function scrubRetiredLocalApiKeys(): void {
  if (typeof window === 'undefined') {
    return
  }
  try {
    for (const key of RETIRED_LOCAL_API_KEY_STORAGE_KEYS) {
      window.localStorage.removeItem(key)
    }
  } catch {
    // Browser storage may be unavailable; memory-only operation remains usable.
  }
}

function readSessionApiKey(): string {
  if (typeof window === 'undefined') {
    return ''
  }
  try {
    return window.sessionStorage.getItem(SESSION_API_KEY_STORAGE_KEY)?.trim() ?? ''
  } catch {
    return ''
  }
}

function writeSessionApiKey(value: string): boolean {
  if (typeof window === 'undefined') {
    return false
  }
  try {
    window.sessionStorage.setItem(SESSION_API_KEY_STORAGE_KEY, value)
    return true
  } catch {
    return false
  }
}

function removeSessionApiKey(): void {
  if (typeof window === 'undefined') {
    return
  }
  try {
    window.sessionStorage.removeItem(SESSION_API_KEY_STORAGE_KEY)
  } catch {
    // Browser storage may be unavailable; the in-memory key is still cleared.
  }
}

initializeBrowserApiKey()

export type HealthResponse = {
  status: string
  version: string
  asr_enabled: boolean
  tts_enabled: boolean
  provider: string
  asr_loaded: boolean
  tts_loaded: boolean
}

export type ProbeResponse = {
  status: 'ok' | 'ready' | 'not_ready'
  checks: Record<string, boolean>
}

export type ModelStatusResponse = {
  ready: boolean
  checks: Record<string, boolean>
  runtime: {
    environment: string
    log_level: string
    provider: string
    num_threads: number
    asr_num_threads: number
    tts_num_threads: number
    debug: boolean
    warmup_on_startup: boolean
    asr_job_workers: number
    tts_job_workers: number
    asr_job_max_attempts: number
    tts_job_max_attempts: number
    job_retry_backoff_seconds: number
    asr_loaded: boolean
    tts_loaded: boolean
    asr_configured_languages: string[]
    asr_loaded_languages: string[]
    tts_configured_languages: string[]
    tts_loaded_languages: string[]
  }
}

export type DiagnosticsStorageItem = {
  name: string
  path_alias: string
  exists: boolean
  is_dir: boolean
  writable: boolean
  usage_bucket:
    | 'empty'
    | 'under_1_mb'
    | '1_to_99_mb'
    | '100_to_999_mb'
    | '1_to_9_gb'
    | '10_to_99_gb'
    | '100_gb_or_more'
  file_count_bucket: 'none' | '1_to_9' | '10_to_99' | '100_to_999' | '1000_or_more'
  capacity_bucket:
    | 'under_10_gb'
    | '10_to_49_gb'
    | '50_to_99_gb'
    | '100_to_499_gb'
    | '500_to_999_gb'
    | '1_tb_or_more'
    | null
  free_space_bucket: DiagnosticsStorageItem['capacity_bucket']
  storage_pressure: 'normal' | 'low' | 'critical' | 'unknown'
}

export type DiagnosticsResponse = {
  generated_at: string
  version: string
  privacy: {
    storage_paths: 'logical_aliases'
    storage_metrics: 'bucketed'
    host_metadata_included: boolean
  }
  runtime: ModelStatusResponse['runtime']
  security: {
    auth_required: boolean
    api_key_auth_enabled: boolean
    session_cookie_name: string
    session_ttl_seconds: number
    secure_cookies: boolean
  }
  storage: DiagnosticsStorageItem[]
  license: {
    status: string
    plan: string
    billing_enabled: boolean
  }
}

export type WarmupAllResponse = {
  asr_loaded: boolean
  tts_loaded: boolean
  asr_loaded_languages: string[]
  tts_loaded_languages: string[]
}

export type WarmupResponse = {
  loaded: boolean
  loaded_languages: string[]
}

export type Voice = {
  voice_id: string
  name: string
  language: string
  reference_text: string
  reference_text_source: string
  audio_size_bytes: number
  sample_rate: number
  duration_seconds: number
  created_at: string
  updated_at: string | null
  reference_audio_url: string
}

export type VoiceDeleteResponse = {
  deleted: boolean
  voice_id: string
}

export type ImportCandidate = {
  filename: string
  name: string
  size_bytes: number
  updated_at: number
  audio_url: string
}

export type TtsJob = {
  job_id: string
  status: JobStatus
  voice_id: string
  language: string
  text: string
  num_steps: number | null
  speed: number | null
  created_at: string
  started_at: string | null
  completed_at: string | null
  error: string | null
  attempt: number
  max_attempts: number
  cancel_requested: boolean
  failed_reason: string | null
  sample_rate: number | null
  duration_seconds: number | null
  audio_url: string | null
}

export type JobCleanupResponse = {
  deleted: number
  job_ids: string[]
}

export type JobDeleteResponse = {
  deleted: boolean
  job_id: string
}

export type AsrJob = {
  job_id: string
  status: JobStatus
  filename: string
  language: string
  created_at: string
  started_at: string | null
  completed_at: string | null
  error: string | null
  attempt: number
  max_attempts: number
  cancel_requested: boolean
  failed_reason: string | null
  text: string | null
  sample_rate: number | null
  duration_seconds: number | null
  audio_url: string | null
}

export type JobStatus = 'queued' | 'running' | 'cancelling' | 'succeeded' | 'failed' | 'cancelled'

export type AuthUser = {
  account_id: string
  username: string
  role: string
}

export type AuthStatusResponse = {
  auth_required: boolean
  setup_required: boolean
  authenticated: boolean
  api_key_auth_enabled: boolean
  user: AuthUser | null
}

export type AuthSessionResponse = {
  authenticated: boolean
  user: AuthUser
  expires_at: string
}

export type AuthLogoutResponse = {
  logged_out: boolean
}

export type AuthPasswordChangeResponse = {
  password_changed: boolean
  other_sessions_revoked: number
}

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetchWithAuth(path, init)

  if (!response.ok) {
    throw new Error(await readErrorMessage(response))
  }

  return response.json() as Promise<T>
}

export async function fetchBlob(path: string, init?: RequestInit): Promise<Blob> {
  const response = await fetchWithAuth(path, init)

  if (!response.ok) {
    throw new Error(await readErrorMessage(response))
  }

  return response.blob()
}

async function fetchProbe(path: string): Promise<ProbeResponse> {
  const response = await fetchWithAuth(path)
  if (!response.ok && response.status !== 503) {
    throw new Error(await readErrorMessage(response))
  }
  return response.json() as Promise<ProbeResponse>
}

function fetchWithAuth(path: string, init?: RequestInit): Promise<Response> {
  const apiKey = path.startsWith('/api/v1/auth/') ? '' : getRequestApiKey()
  return fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: init?.credentials ?? 'same-origin',
    headers: {
      Accept: 'application/json',
      ...(apiKey ? { 'X-Vassil-API-Key': apiKey } : {}),
      ...init?.headers,
    },
  })
}

async function readErrorMessage(response: Response) {
  const fallback = `Request failed: ${response.status}`
  const body = await response.text()
  if (!body) {
    return fallback
  }

  try {
    const parsed = JSON.parse(body) as unknown
    return errorMessageFromJson(parsed) || fallback
  } catch {
    return body
  }
}

function errorMessageFromJson(value: unknown): string {
  if (typeof value === 'string') {
    return value
  }

  if (!value || typeof value !== 'object') {
    return ''
  }

  const record = value as Record<string, unknown>
  for (const key of ['detail', 'message', 'error']) {
    const candidate = record[key]
    const message = errorDetailToString(candidate)
    if (message) {
      return message
    }
  }

  return ''
}

function errorDetailToString(value: unknown): string {
  if (typeof value === 'string') {
    return value
  }

  if (Array.isArray(value)) {
    return value.map(errorDetailToString).filter(Boolean).join('; ')
  }

  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>
    if (typeof record.msg === 'string') {
      return record.msg
    }
    if (typeof record.message === 'string') {
      return record.message
    }
  }

  return ''
}

export const api = {
  authStatus: async () => {
    const status = await fetchJson<AuthStatusResponse>('/api/v1/auth/status')
    ownerSessionActive = status.auth_required && status.authenticated
    return status
  },
  authSetup: async (payload: { username: string; password: string }) => {
    const session = await fetchJson<AuthSessionResponse>('/api/v1/auth/setup', {
      method: 'POST',
      body: JSON.stringify(payload),
      headers: { 'Content-Type': 'application/json' },
    })
    ownerSessionActive = true
    return session
  },
  authLogin: async (payload: { username: string; password: string }) => {
    const session = await fetchJson<AuthSessionResponse>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify(payload),
      headers: { 'Content-Type': 'application/json' },
    })
    ownerSessionActive = true
    return session
  },
  authLogout: async () => {
    try {
      return await fetchJson<AuthLogoutResponse>('/api/v1/auth/logout', { method: 'POST' })
    } finally {
      ownerSessionActive = false
      clearBrowserApiKey()
    }
  },
  authChangePassword: (payload: { currentPassword: string; newPassword: string }) =>
    fetchJson<AuthPasswordChangeResponse>('/api/v1/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({
        current_password: payload.currentPassword,
        new_password: payload.newPassword,
      }),
      headers: { 'Content-Type': 'application/json' },
    }),
  health: () => fetchJson<HealthResponse>('/health'),
  liveness: () => fetchProbe('/livez'),
  readiness: () => fetchProbe('/readyz'),
  modelStatus: () => fetchJson<ModelStatusResponse>('/model-status'),
  diagnostics: () => fetchJson<DiagnosticsResponse>('/diagnostics'),
  diagnosticsBundle: (includeHostMetadata = false) =>
    fetchBlob(`/diagnostics/bundle${includeHostMetadata ? '?include_host_metadata=true' : ''}`),
  warmup: () => fetchJson<WarmupAllResponse>('/warmup', { method: 'POST' }),
  warmupAsr: (language?: string) =>
    fetchJson<WarmupResponse>(`/warmup/asr${language ? `?language=${encodeURIComponent(language)}` : ''}`, {
      method: 'POST',
    }),
  warmupTts: (language?: string) =>
    fetchJson<WarmupResponse>(`/warmup/tts${language ? `?language=${encodeURIComponent(language)}` : ''}`, {
      method: 'POST',
    }),
  voices: () => fetchJson<Voice[]>('/api/v1/voices'),
  importCandidates: () => fetchJson<ImportCandidate[]>('/api/v1/voices/import-candidates'),
  ttsJobs: () => fetchJson<TtsJob[]>('/api/v1/tts/jobs'),
  asrJobs: () => fetchJson<AsrJob[]>('/api/v1/asr/jobs'),
  cleanupTtsJobs: (maxAgeSeconds?: number) =>
    fetchJson<JobCleanupResponse>(cleanupPath('/api/v1/tts/jobs', maxAgeSeconds), {
      method: 'DELETE',
    }),
  cleanupAsrJobs: (maxAgeSeconds?: number) =>
    fetchJson<JobCleanupResponse>(cleanupPath('/api/v1/asr/jobs', maxAgeSeconds), {
      method: 'DELETE',
    }),
  deleteTtsJob: (jobId: string) =>
    fetchJson<JobDeleteResponse>(`/api/v1/tts/jobs/${encodeURIComponent(jobId)}`, {
      method: 'DELETE',
    }),
  deleteAsrJob: (jobId: string) =>
    fetchJson<JobDeleteResponse>(`/api/v1/asr/jobs/${encodeURIComponent(jobId)}`, {
      method: 'DELETE',
    }),
  cancelTtsJob: (jobId: string) =>
    fetchJson<TtsJob>(`/api/v1/tts/jobs/${encodeURIComponent(jobId)}/cancel`, {
      method: 'POST',
    }),
  cancelAsrJob: (jobId: string) =>
    fetchJson<AsrJob>(`/api/v1/asr/jobs/${encodeURIComponent(jobId)}/cancel`, {
      method: 'POST',
    }),
  createAsrJob: (file: File, payload: { language?: string } = {}) => {
    const form = new FormData()
    form.set('audio', file)
    if (payload.language) {
      form.set('language', payload.language)
    }

    return fetchJson<AsrJob>('/api/v1/asr/jobs', {
      method: 'POST',
      body: form,
    })
  },
  createTtsJobWithVoice: (
    voiceId: string,
    payload: { text: string; language?: string; numSteps?: number; speed?: number },
  ) => {
    const form = new FormData()
    form.set('text', payload.text)
    if (payload.language !== undefined) {
      form.set('language', payload.language)
    }
    if (payload.numSteps !== undefined) {
      form.set('num_steps', String(payload.numSteps))
    }
    if (payload.speed !== undefined) {
      form.set('speed', String(payload.speed))
    }

    return fetchJson<TtsJob>(`/api/v1/tts/jobs/voices/${encodeURIComponent(voiceId)}`, {
      method: 'POST',
      body: form,
    })
  },
  createVoice: (
    file: File,
    payload: { name: string; language: string; referenceText?: string; autoTranscribe?: boolean },
  ) => {
    const form = new FormData()
    form.set('reference_audio', file)
    form.set('name', payload.name)
    form.set('language', payload.language)
    form.set('auto_transcribe', String(payload.autoTranscribe ?? false))
    if (payload.referenceText) {
      form.set('reference_text', payload.referenceText)
    }

    return fetchJson<Voice>('/api/v1/voices', {
      method: 'POST',
      body: form,
    })
  },
  importVoiceCandidate: (
    filename: string,
    payload: { name?: string; language?: string; referenceText?: string; autoTranscribe?: boolean } = {},
  ) => {
    const form = new URLSearchParams()
    form.set('filename', filename)
    form.set('auto_transcribe', String(payload.autoTranscribe ?? true))
    if (payload.name) {
      form.set('name', payload.name)
    }
    if (payload.language) {
      form.set('language', payload.language)
    }
    if (payload.referenceText) {
      form.set('reference_text', payload.referenceText)
    }

    return fetchJson<Voice>('/api/v1/voices/import', {
      method: 'POST',
      body: form,
    })
  },
  updateVoice: (voiceId: string, payload: { name?: string; language?: string; referenceText?: string }) => {
    const form = new FormData()
    if (payload.name !== undefined) {
      form.set('name', payload.name)
    }
    if (payload.language !== undefined) {
      form.set('language', payload.language)
    }
    if (payload.referenceText !== undefined) {
      form.set('reference_text', payload.referenceText)
    }

    return fetchJson<Voice>(`/api/v1/voices/${encodeURIComponent(voiceId)}`, {
      method: 'PATCH',
      body: form,
    })
  },
  deleteVoice: (voiceId: string) =>
    fetchJson<VoiceDeleteResponse>(`/api/v1/voices/${encodeURIComponent(voiceId)}`, {
      method: 'DELETE',
    }),
}

function cleanupPath(path: string, maxAgeSeconds?: number) {
  if (maxAgeSeconds === undefined) {
    return path
  }
  const params = new URLSearchParams({ max_age_seconds: String(maxAgeSeconds) })
  return `${path}?${params.toString()}`
}
