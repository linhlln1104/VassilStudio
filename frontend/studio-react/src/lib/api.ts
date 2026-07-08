const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''
export const API_KEY_STORAGE_KEY = 'vassil.apiKey'
const LEGACY_API_KEY_STORAGE_KEY = 'vvoice.apiKey'

export function getStoredApiKey(): string {
  if (typeof window === 'undefined') {
    return ''
  }

  const value = window.localStorage.getItem(API_KEY_STORAGE_KEY)
  if (value) {
    return value
  }

  const legacyValue = window.localStorage.getItem(LEGACY_API_KEY_STORAGE_KEY)
  if (legacyValue) {
    window.localStorage.setItem(API_KEY_STORAGE_KEY, legacyValue)
    return legacyValue
  }

  return ''
}

export function setStoredApiKey(apiKey: string): void {
  if (typeof window === 'undefined') {
    return
  }

  const normalized = apiKey.trim()
  if (normalized) {
    window.localStorage.setItem(API_KEY_STORAGE_KEY, normalized)
    window.localStorage.removeItem(LEGACY_API_KEY_STORAGE_KEY)
  } else {
    window.localStorage.removeItem(API_KEY_STORAGE_KEY)
    window.localStorage.removeItem(LEGACY_API_KEY_STORAGE_KEY)
  }
}

export type HealthResponse = {
  status: string
  version: string
  asr_enabled: boolean
  tts_enabled: boolean
  provider: string
  asr_loaded: boolean
  tts_loaded: boolean
}

export type ModelStatusResponse = {
  ready: boolean
  checks: Record<string, boolean>
  runtime: {
    provider: string
    num_threads: number
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

export type DiagnosticsResponse = {
  generated_at: string
  version: string
  runtime: ModelStatusResponse['runtime']
  security: {
    auth_required: boolean
    api_key_auth_enabled: boolean
    session_cookie_name: string
    session_ttl_seconds: number
    secure_cookies: boolean
  }
  storage: Array<{
    name: string
    path: string
    exists: boolean
    is_dir: boolean
    size_bytes: number
    file_count: number
  }>
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

export type Voice = {
  voice_id: string
  name: string
  language: string
  reference_text: string
  reference_text_source: string
  audio_path: string
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

function fetchWithAuth(path: string, init?: RequestInit): Promise<Response> {
  const apiKey = getStoredApiKey()
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
  authStatus: () => fetchJson<AuthStatusResponse>('/api/v1/auth/status'),
  authSetup: (payload: { username: string; password: string }) =>
    fetchJson<AuthSessionResponse>('/api/v1/auth/setup', {
      method: 'POST',
      body: JSON.stringify(payload),
      headers: { 'Content-Type': 'application/json' },
    }),
  authLogin: (payload: { username: string; password: string }) =>
    fetchJson<AuthSessionResponse>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify(payload),
      headers: { 'Content-Type': 'application/json' },
    }),
  authLogout: () =>
    fetchJson<AuthLogoutResponse>('/api/v1/auth/logout', {
      method: 'POST',
    }),
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
  modelStatus: () => fetchJson<ModelStatusResponse>('/model-status'),
  diagnostics: () => fetchJson<DiagnosticsResponse>('/diagnostics'),
  diagnosticsBundle: () => fetchBlob('/diagnostics/bundle'),
  warmup: () => fetchJson<WarmupAllResponse>('/warmup', { method: 'POST' }),
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
