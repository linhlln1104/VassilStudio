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
    asr_loaded: boolean
    tts_loaded: boolean
    asr_configured_languages: string[]
    asr_loaded_languages: string[]
    tts_configured_languages: string[]
    tts_loaded_languages: string[]
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
  text: string | null
  sample_rate: number | null
  duration_seconds: number | null
  audio_url: string | null
}

export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed'

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const apiKey = getStoredApiKey()
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(apiKey ? { 'X-Vassil-API-Key': apiKey } : {}),
      ...init?.headers,
    },
  })

  if (!response.ok) {
    throw new Error(await readErrorMessage(response))
  }

  return response.json() as Promise<T>
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
  health: () => fetchJson<HealthResponse>('/health'),
  modelStatus: () => fetchJson<ModelStatusResponse>('/model-status'),
  warmup: () => fetchJson<WarmupAllResponse>('/warmup', { method: 'POST' }),
  voices: () => fetchJson<Voice[]>('/api/v1/voices'),
  importCandidates: () => fetchJson<ImportCandidate[]>('/api/v1/voices/import-candidates'),
  ttsJobs: () => fetchJson<TtsJob[]>('/api/v1/tts/jobs'),
  asrJobs: () => fetchJson<AsrJob[]>('/api/v1/asr/jobs'),
  cleanupTtsJobs: () =>
    fetchJson<JobCleanupResponse>('/api/v1/tts/jobs', {
      method: 'DELETE',
    }),
  cleanupAsrJobs: () =>
    fetchJson<JobCleanupResponse>('/api/v1/asr/jobs', {
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
