import { fetchBlob, fetchJson } from './api'

export type Page<T> = { items: T[]; total: number }
export type Project = { owner_id?: string; members?: Array<{principal_id: string; role: string}>; project_id: string; name: string; description: string; revision: number; created_at: string; updated_at: string }
export type Segment = {
  segment_id: string; project_id: string; external_id: string; text: string; language: string;
  voice_id: string | null; model_id: string | null; position: number; revision: number;
  script_revision: number; selected_take_id: string | null; created_at: string; updated_at: string
}
export type Take = {
  take_id: string; segment_id: string; segment_revision: number; status: string; job_id?: string;
  review_status: 'pending' | 'approved' | 'rejected'; revision: number; audio_url?: string;
  error?: string | null; created_at: string; review_note?: string; reviewed_by?: string | null; model_id?: string; provenance?: Record<string, unknown>
}
export type DictionaryEntry = { source: string; replacement: string; language?: 'vi' | 'en' }
export type Dictionary = { project_id: string; revision: number; entries: DictionaryEntry[] }
export type BatchRow = { external_id: string; text: string; language?: string; voice_id?: string; model_id?: string; num_steps?: number; speed?: number }
export type BatchInput = { project_id: string; name?: string; rows: BatchRow[]; preflight_token?: string; defaults?: { language?: string; voice_id?: string; model_id?: string } }
export type Preflight = {
  can_submit: boolean; row_count: number; errors: string[]; preflight_token: string;
  rows: Array<BatchRow & { row_number: number; normalized_text: string; errors: string[]; warnings: string[] }>
}
export type Batch = {
  batch_id: string; project_id: string; name: string; status: string; item_count: number;
  counts: Record<string, number>; created_at: string; updated_at: string
}
export type BatchItem = Take & {
  item_id: string; external_id: string; row_number: number; segment_id: string; take_id: string;
  job_id: string | null; status: string; text: string; model_id: string; voice_id: string;
  review_status: Take['review_status']; error: string | null
}

const id = encodeURIComponent
export const jsonRequest = <T,>(path: string, method: string, body?: unknown, key?: string) => fetchJson<T>(path, {
  method, headers: { 'Content-Type': 'application/json', ...(key ? { 'Idempotency-Key': key } : {}) },
  body: body === undefined ? undefined : JSON.stringify(body),
})
const projectPath = (project: string) => `/api/v1/projects/${id(project)}`
const segmentPath = (project: string, segment: string) => `${projectPath(project)}/segments/${id(segment)}`

export const productionApi = {
  projects: (offset = 0) => fetchJson<Page<Project>>(`/api/v1/projects?limit=50&offset=${offset}`),
  project: (project: string) => fetchJson<Project>(projectPath(project)),
  createProject: (body: { name: string; description: string }) => jsonRequest<Project>('/api/v1/projects', 'POST', body),
  updateProject: (project: string, body: { expected_revision: number; name: string; description: string }) => jsonRequest<Project>(projectPath(project), 'PATCH', body),
  segments: (project: string, offset = 0) => fetchJson<Page<Segment>>(`${projectPath(project)}/segments?limit=50&offset=${offset}`),
  segment: (project: string, segment: string) => fetchJson<Segment>(segmentPath(project, segment)),
  revisions: (project: string, segment: string) => fetchJson<{items: Segment[]}>(`${segmentPath(project, segment)}/revisions`),
  createSegment: (project: string, body: Partial<Segment> & { text: string }) => jsonRequest<Segment>(`${projectPath(project)}/segments`, 'POST', body),
  updateSegment: (project: string, segment: string, body: Partial<Segment> & { expected_revision: number }) => jsonRequest<Segment>(segmentPath(project, segment), 'PATCH', body),
  takes: (project: string, segment: string, offset = 0) => fetchJson<Page<Take>>(`${segmentPath(project, segment)}/takes?limit=25&offset=${offset}`),
  createTake: (project: string, segment: string, revision: number, key: string, options: {model_id?: string; voice_id?: string; num_steps?: number; speed?: number} = {}) => jsonRequest<Take>(`${segmentPath(project, segment)}/takes`, 'POST', { expected_revision: revision, ...options }, key),
  reviewTake: (project: string, take: Take, status: Take['review_status'], note: string) => jsonRequest<Take>(`${projectPath(project)}/takes/${id(take.take_id)}/review`, 'PATCH', { expected_revision: take.revision, status, note }),
  selectTake: (project: string, segment: Segment, take: string) => jsonRequest<Segment>(`${segmentPath(project, segment.segment_id)}/selection`, 'PUT', { expected_revision: segment.revision, take_id: take }),
  dictionary: (project: string) => fetchJson<Dictionary>(`${projectPath(project)}/dictionary`),
  saveDictionary: (project: string, body: { expected_revision: number; entries: DictionaryEntry[] }) => jsonRequest<Dictionary>(`${projectPath(project)}/dictionary`, 'PUT', body),
  previewDictionary: (project: string, text: string, language: string) => jsonRequest<{ text?: string; normalized_text?: string }>(`${projectPath(project)}/dictionary/preview`, 'POST', { text, language }),
  analyzeBatch: (body: BatchInput) => jsonRequest<Preflight>('/api/v1/batches/analyze', 'POST', body),
  createBatch: (body: BatchInput, key: string) => jsonRequest<Batch>('/api/v1/batches', 'POST', body, key),
  batches: (offset = 0, project = '') => fetchJson<Page<Batch>>(`/api/v1/batches?limit=25&offset=${offset}${project ? `&project_id=${id(project)}` : ''}`),
  batch: (batch: string) => fetchJson<Batch>(`/api/v1/batches/${id(batch)}`),
  batchItems: (batch: string, offset = 0) => fetchJson<Page<BatchItem>>(`/api/v1/batches/${id(batch)}/items?limit=25&offset=${offset}`),
  retryBatch: (batch: string, items?: string[]) => jsonRequest<Batch>(`/api/v1/batches/${id(batch)}/retry-failed`, 'POST', items?.length ? { item_ids: items } : undefined),
  cancelBatch: (batch: string) => jsonRequest<Batch>(`/api/v1/batches/${id(batch)}/cancel`, 'POST'),
  exportProject: (project: string) => fetchBlob(`${projectPath(project)}/export?approved_only=true`),
  exportBatch: (batch: string) => fetchBlob(`/api/v1/batches/${id(batch)}/export?approved_only=true`),
}

export function downloadFile(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename.replace(/[\\/:*?"<>|]/g, '-')
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
