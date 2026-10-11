import { fetchJson, type TtsModelsResponse } from './api'
import { jsonRequest } from './production-api'

export type Principal = { principal_id: string; name: string; kind: string; role: string; scopes: string[] }
export type ServiceAccount = Principal & { created_at: string; disabled_at: string | null }
export type AccessKey = { key_id: string; principal_id: string; name: string; prefix: string; created_at: string; expires_at: string | null; revoked_at: string | null; last_used_at: string | null }
export type AuditEvent = { event_id?: number; actor_name?: string; request_id?: string; details?: Record<string, unknown>; actor_id?: string; principal_id?: string; action?: string; resource_id?: string; result?: string; created_at?: string; timestamp?: string }
export type Deployments = { deployments: Array<{ model_id: string; enabled: boolean | number; active_version: string | null; activated_at: string | null }>; versions: Array<{ version: string; model_id: string; created_at: string }> }
export const hasScope = (principal: Principal | undefined, scope: string) => Boolean(principal && (principal.scopes.includes('*') || principal.scopes.includes(scope)))
export const administrationApi = {
  principal: () => fetchJson<Principal>('/api/v1/auth/principal'),
  accounts: () => fetchJson<ServiceAccount[]>('/api/v1/auth/service-accounts'),
  createAccount: (payload: { name: string; role: string; scopes?: string[] }) => jsonRequest<ServiceAccount>('/api/v1/auth/service-accounts', 'POST', payload),
  disableAccount: (account: string) => jsonRequest<ServiceAccount>(`/api/v1/auth/service-accounts/${encodeURIComponent(account)}/disable`, 'POST'),
  keys: () => fetchJson<AccessKey[]>('/api/v1/auth/api-keys'),
  createKey: (account: string, name: string, expires?: string) => jsonRequest<{ key: AccessKey; token: string }>(`/api/v1/auth/service-accounts/${encodeURIComponent(account)}/keys`, 'POST', { name, ...(expires ? { expires_at: expires } : {}) }),
  revokeKey: (key: string) => jsonRequest(`/api/v1/auth/api-keys/${encodeURIComponent(key)}`, 'DELETE'),
  audit: (offset: number) => fetchJson<AuditEvent[]>(`/api/v1/auth/audit?limit=25&offset=${offset}`),
  modelAction: (model: string, action: 'warmup' | 'unload' | 'enable' | 'disable' | 'activate') => jsonRequest<TtsModelsResponse>(`/api/v1/tts/models/${encodeURIComponent(model)}/${action}`, 'POST'),
  deployments: () => fetchJson<Deployments>('/api/v1/tts/models/deployments'),
  importModel: (payload: unknown) => jsonRequest<TtsModelsResponse>('/api/v1/tts/models/import', 'POST', payload),
  rollbackModel: (model: string, version: string) => jsonRequest<TtsModelsResponse>(`/api/v1/tts/models/${encodeURIComponent(model)}/rollback`, 'POST', { version }),
}
