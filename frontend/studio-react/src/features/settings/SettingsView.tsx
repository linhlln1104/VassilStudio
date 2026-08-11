import { type FormEvent, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  ChevronDown,
  CheckCircle2,
  BadgeCheck,
  Copy,
  Database,
  Download,
  Eraser,
  Eye,
  EyeOff,
  ExternalLink,
  FolderOpen,
  KeyRound,
  Loader2,
  LockKeyhole,
  LogOut,
  ShieldCheck,
  UserRound,
  XCircle,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { api, getStoredApiKey, setStoredApiKey } from '@/lib/api'
import { API_BRAND_NAME } from '@/lib/brand'
import { formatBytes } from '@/lib/format'

const storageRows = [
  { label: 'Source models', value: 'models/source', description: 'Original checkpoints and research assets.' },
  { label: 'Runtime models', value: 'models/runtime', description: 'ONNX models loaded by the backend.' },
  { label: 'Voice assets', value: 'data/voices', description: 'Reference clips and prepared voice profiles.' },
  { label: 'Generated outputs', value: 'data/outputs', description: 'Rendered TTS audio and exported files.' },
  { label: 'Contracts', value: 'contracts/openapi', description: 'Generated API contract for integrations.' },
]

const endpointRows = [
  { label: 'Backend health', href: '/health' },
  { label: 'Model status', href: '/model-status' },
  { label: 'OpenAPI JSON', href: '/openapi.json' },
  { label: 'FastAPI docs', href: '/docs' },
]

type RetentionOption = {
  id: string
  label: string
  description: string
  maxAgeSeconds?: number
}

const retentionOptions: RetentionOption[] = [
  {
    id: '7d',
    label: '7 days',
    description: 'Terminal jobs older than one week.',
    maxAgeSeconds: 7 * 24 * 60 * 60,
  },
  {
    id: '30d',
    label: '30 days',
    description: 'Terminal jobs older than one month.',
    maxAgeSeconds: 30 * 24 * 60 * 60,
  },
  {
    id: 'all',
    label: 'All terminal',
    description: 'Every succeeded, failed, or cancelled job.',
  },
]

export function SettingsView() {
  const [apiKeyDraft, setApiKeyDraft] = useState(() => getStoredApiKey())
  const [apiKeySaved, setApiKeySaved] = useState(false)
  const [showApiKey, setShowApiKey] = useState(false)
  const [copied, setCopied] = useState(false)
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [passwordChangeResult, setPasswordChangeResult] = useState<string | null>(null)
  const [cleanupTarget, setCleanupTarget] = useState<RetentionOption | null>(null)
  const [cleanupResult, setCleanupResult] = useState<string | null>(null)
  const [clearKeyConfirmOpen, setClearKeyConfirmOpen] = useState(false)
  const queryClient = useQueryClient()
  const healthQuery = useQuery({
    queryKey: ['health'],
    queryFn: api.health,
    refetchInterval: 10000,
  })
  const modelQuery = useQuery({
    queryKey: ['model-status'],
    queryFn: api.modelStatus,
    refetchInterval: 10000,
  })
  const authQuery = useQuery({
    queryKey: ['auth-status'],
    queryFn: api.authStatus,
    refetchInterval: 30000,
  })
  const diagnosticsQuery = useQuery({
    queryKey: ['diagnostics'],
    queryFn: api.diagnostics,
    refetchInterval: 30000,
  })
  const warmupMutation = useMutation({
    mutationFn: api.warmup,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['health'] })
      void queryClient.invalidateQueries({ queryKey: ['model-status'] })
    },
  })
  const logoutMutation = useMutation({
    mutationFn: api.authLogout,
    onSuccess: () => {
      window.location.assign('/login')
    },
  })
  const changePasswordMutation = useMutation({
    mutationFn: api.authChangePassword,
    onSuccess: (result) => {
      setCurrentPassword('')
      setNewPassword('')
      setPasswordChangeResult(
        result.other_sessions_revoked > 0
          ? `Password updated. Revoked ${result.other_sessions_revoked} other sessions.`
          : 'Password updated.',
      )
      void queryClient.invalidateQueries({ queryKey: ['auth-status'] })
    },
  })
  const diagnosticsBundleMutation = useMutation({
    mutationFn: api.diagnosticsBundle,
    onSuccess: (blob) => downloadBlob(blob, `vassilstudio-diagnostics-${Date.now()}.zip`),
  })
  const cleanupJobsMutation = useMutation({
    mutationFn: async (retention: RetentionOption) => {
      const [tts, asr] = await Promise.all([
        api.cleanupTtsJobs(retention.maxAgeSeconds),
        api.cleanupAsrJobs(retention.maxAgeSeconds),
      ])
      return {
        deleted: tts.deleted + asr.deleted,
        ttsDeleted: tts.deleted,
        asrDeleted: asr.deleted,
      }
    },
    onSuccess: (result) => {
      setCleanupResult(
        result.deleted > 0
          ? `Removed ${result.deleted} terminal jobs (${result.ttsDeleted} TTS, ${result.asrDeleted} ASR).`
          : 'No terminal jobs matched that retention window.',
      )
      setCleanupTarget(null)
      void queryClient.invalidateQueries({ queryKey: ['diagnostics'] })
      void queryClient.invalidateQueries({ queryKey: ['tts-jobs'] })
      void queryClient.invalidateQueries({ queryKey: ['asr-jobs'] })
    },
  })

  const health = healthQuery.data
  const model = modelQuery.data
  const checks = useMemo(() => Object.entries(model?.checks ?? {}), [model?.checks])
  const passedChecks = checks.filter(([, passed]) => passed).length
  const diagnosticsRunning = healthQuery.isFetching || modelQuery.isFetching || diagnosticsQuery.isFetching
  const backendOffline = healthQuery.isError || modelQuery.isError
  const runtimeReady = !backendOffline && Boolean(model?.ready)

  const handleApiKeySave = () => {
    setStoredApiKey(apiKeyDraft)
    setApiKeySaved(true)
    void modelQuery.refetch()
  }

  const handleCopyKey = async () => {
    if (!apiKeyDraft || typeof navigator === 'undefined') {
      return
    }
    await navigator.clipboard.writeText(apiKeyDraft)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1800)
  }

  const clearApiKey = () => {
    setApiKeyDraft('')
    setStoredApiKey('')
    setApiKeySaved(false)
    setCopied(false)
    setClearKeyConfirmOpen(false)
    void modelQuery.refetch()
  }

  return (
    <div className="space-y-3">
      <SystemDiagnosticsCard
        backendOffline={backendOffline}
        runtimeReady={runtimeReady}
        version={health?.version ?? diagnosticsQuery.data?.version ?? 'unknown'}
        environment={model?.runtime.environment ?? diagnosticsQuery.data?.runtime.environment ?? 'unknown'}
        logLevel={model?.runtime.log_level ?? diagnosticsQuery.data?.runtime.log_level ?? 'unknown'}
        provider={model?.runtime.provider ?? health?.provider ?? 'unknown'}
        threads={String(model?.runtime.num_threads ?? 'unknown')}
        ttsLoaded={Boolean(health?.tts_loaded)}
        asrLoaded={Boolean(health?.asr_loaded)}
        ttsLanguages={model?.runtime.tts_configured_languages ?? []}
        asrLanguages={model?.runtime.asr_configured_languages ?? []}
        asrWorkers={model?.runtime.asr_job_workers ?? 1}
        ttsWorkers={model?.runtime.tts_job_workers ?? 1}
        startupWarmup={Boolean(model?.runtime.warmup_on_startup)}
        passedChecks={passedChecks}
        totalChecks={checks.length}
        checks={checks}
        diagnosticsRunning={diagnosticsRunning}
        warmupRunning={warmupMutation.isPending}
        bundleRunning={diagnosticsBundleMutation.isPending}
        warmupError={warmupMutation.error instanceof Error ? warmupMutation.error.message : null}
        bundleError={
          diagnosticsBundleMutation.error instanceof Error ? diagnosticsBundleMutation.error.message : null
        }
        onRunDiagnostics={() => {
          void healthQuery.refetch()
          void modelQuery.refetch()
          void diagnosticsQuery.refetch()
        }}
        onWarmup={() => warmupMutation.mutate()}
        onDownloadBundle={() => diagnosticsBundleMutation.mutate()}
      />

      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_360px]">
        <AccountSessionCard
          authRequired={Boolean(authQuery.data?.auth_required)}
          authenticated={Boolean(authQuery.data?.authenticated)}
          username={authQuery.data?.user?.username ?? null}
          role={authQuery.data?.user?.role ?? null}
          apiKeyAuthEnabled={Boolean(authQuery.data?.api_key_auth_enabled)}
          sessionCookieName={diagnosticsQuery.data?.security.session_cookie_name ?? 'vassil_session'}
          sessionTtlSeconds={diagnosticsQuery.data?.security.session_ttl_seconds ?? 0}
          secureCookies={Boolean(diagnosticsQuery.data?.security.secure_cookies)}
          authDbPath={diagnosticsQuery.data?.storage.find((item) => item.name === 'auth_db')?.path ?? 'data/auth.sqlite3'}
          signingOut={logoutMutation.isPending}
          currentPassword={currentPassword}
          newPassword={newPassword}
          passwordChangeRunning={changePasswordMutation.isPending}
          passwordChangeResult={passwordChangeResult}
          passwordChangeError={
            changePasswordMutation.error instanceof Error ? changePasswordMutation.error.message : null
          }
          onSignOut={() => logoutMutation.mutate()}
          onCurrentPasswordChange={(value) => {
            setCurrentPassword(value)
            setPasswordChangeResult(null)
            changePasswordMutation.reset()
          }}
          onNewPasswordChange={(value) => {
            setNewPassword(value)
            setPasswordChangeResult(null)
            changePasswordMutation.reset()
          }}
          onChangePassword={(event) => {
            event.preventDefault()
            setPasswordChangeResult(null)
            changePasswordMutation.reset()
            changePasswordMutation.mutate({ currentPassword, newPassword })
          }}
        />
        <LicenseCard
          status={diagnosticsQuery.data?.license.status ?? 'local'}
          plan={diagnosticsQuery.data?.license.plan ?? 'Local workspace'}
          billingEnabled={Boolean(diagnosticsQuery.data?.license.billing_enabled)}
          generatedAt={diagnosticsQuery.data?.generated_at ?? null}
        />
      </div>

      <StorageManagementCard
        storageItems={diagnosticsQuery.data?.storage ?? []}
        cleanupRunning={cleanupJobsMutation.isPending}
        cleanupResult={cleanupResult}
        cleanupError={cleanupJobsMutation.error instanceof Error ? cleanupJobsMutation.error.message : null}
        onRefresh={() => {
          void diagnosticsQuery.refetch()
        }}
        onRequestCleanup={(option) => setCleanupTarget(option)}
      />

      <Card>
        <CardHeader>
          <div>
            <div className="text-sm font-semibold text-slate-950">Security</div>
            <div className="mt-1 text-xs text-slate-600">
              Store a local browser key when VASSIL_API_KEYS is enabled.
            </div>
          </div>
          <LockKeyhole className="size-5 text-slate-500" />
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_auto]">
            <label className="block min-w-0">
              <span className="mb-2 block text-xs font-semibold text-slate-700">
                {API_BRAND_NAME} key
              </span>
              <div className="flex min-w-0 rounded-md border border-slate-300 bg-white focus-within:border-sky-500 focus-within:ring-2 focus-within:ring-sky-100">
                <input
                  className="h-8 min-w-0 flex-1 rounded-l-md border-0 bg-transparent px-2.5 text-xs font-medium text-slate-950 outline-none placeholder:text-slate-500"
                  type={showApiKey ? 'text' : 'password'}
                  value={apiKeyDraft}
                  placeholder="Paste API key for protected endpoints"
                  onChange={(event) => {
                    setApiKeyDraft(event.target.value)
                    setApiKeySaved(false)
                    setCopied(false)
                  }}
                />
                <button
                  className="grid h-8 w-8 place-items-center text-slate-500 hover:text-slate-950"
                  type="button"
                  aria-label={showApiKey ? 'Hide API key' : 'Show API key'}
                  onClick={() => setShowApiKey((value) => !value)}
                >
                  {showApiKey ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>
            </label>
            <div className="flex flex-wrap items-end gap-2">
              <Button onClick={handleApiKeySave}>
                <KeyRound className="size-4" />
                Save key
              </Button>
              <Button variant="secondary" disabled={!apiKeyDraft} onClick={() => { void handleCopyKey() }}>
                <Copy className="size-4" />
                {copied ? 'Copied' : 'Copy'}
              </Button>
              <Button
                variant="secondary"
                disabled={!apiKeyDraft && !getStoredApiKey()}
                onClick={() => setClearKeyConfirmOpen(true)}
              >
                Clear
              </Button>
            </div>
          </div>
          <p className="mt-2 text-xs font-medium leading-5 text-slate-600">
            {apiKeySaved
              ? 'Saved locally in this browser. Server-side secrets are not written by the UI.'
              : 'Leave empty when API key auth is disabled.'}
          </p>
        </CardContent>
      </Card>

      <ConfirmDialog
        open={Boolean(cleanupTarget)}
        title="Clean terminal jobs?"
        description={
          cleanupTarget
            ? `${cleanupTarget.description} This removes matching ASR/TTS job metadata and job files. Active jobs are kept.`
            : ''
        }
        confirmLabel="Clean jobs"
        busy={cleanupJobsMutation.isPending}
        busyLabel="Cleaning"
        onOpenChange={(open) => {
          if (!open) {
            setCleanupTarget(null)
          }
        }}
        onConfirm={() => {
          if (cleanupTarget) {
            cleanupJobsMutation.mutate(cleanupTarget)
          }
        }}
      />

      <ConfirmDialog
        open={clearKeyConfirmOpen}
        title="Clear local API key?"
        description={`This removes the saved ${API_BRAND_NAME} key from this browser. Server-side API keys are not changed.`}
        confirmLabel="Clear key"
        busyLabel="Clearing"
        onOpenChange={setClearKeyConfirmOpen}
        onConfirm={clearApiKey}
      />

      <AdvancedSettings />
    </div>
  )
}

function AccountSessionCard({
  authRequired,
  authenticated,
  username,
  role,
  apiKeyAuthEnabled,
  sessionCookieName,
  sessionTtlSeconds,
  secureCookies,
  authDbPath,
  signingOut,
  currentPassword,
  newPassword,
  passwordChangeRunning,
  passwordChangeResult,
  passwordChangeError,
  onSignOut,
  onCurrentPasswordChange,
  onNewPasswordChange,
  onChangePassword,
}: {
  authRequired: boolean
  authenticated: boolean
  username: string | null
  role: string | null
  apiKeyAuthEnabled: boolean
  sessionCookieName: string
  sessionTtlSeconds: number
  secureCookies: boolean
  authDbPath: string
  signingOut: boolean
  currentPassword: string
  newPassword: string
  passwordChangeRunning: boolean
  passwordChangeResult: string | null
  passwordChangeError: string | null
  onSignOut: () => void
  onCurrentPasswordChange: (value: string) => void
  onNewPasswordChange: (value: string) => void
  onChangePassword: (event: FormEvent<HTMLFormElement>) => void
}) {
  const canChangePassword = currentPassword.length > 0 && newPassword.length >= 8 && !passwordChangeRunning

  return (
    <Card>
      <CardHeader>
        <div>
          <div className="text-sm font-semibold text-slate-950">Account and session</div>
          <div className="mt-1 text-xs text-slate-600">
            Local owner access for this workspace.
          </div>
        </div>
        <UserRound className="size-5 text-slate-500" />
      </CardHeader>
      <CardContent>
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          <SettingsMetric label="Studio auth" value={authRequired ? 'Required' : 'Local dev'} />
          <SettingsMetric label="Session" value={authenticated ? username ?? 'Signed in' : 'Not required'} />
          <SettingsMetric label="Role" value={role ?? 'workspace'} />
          <SettingsMetric label="API keys" value={apiKeyAuthEnabled ? 'Enabled' : 'Disabled'} />
        </div>
        <div className="mt-3 grid gap-2 text-xs lg:grid-cols-3">
          <SettingsMetric label="Cookie" value={sessionCookieName} />
          <SettingsMetric label="TTL" value={formatSeconds(sessionTtlSeconds)} />
          <SettingsMetric label="Secure cookie" value={secureCookies ? 'HTTPS only' : 'Local HTTP'} />
        </div>
        <div className="mt-3 rounded-md border border-slate-200 bg-white px-3 py-2">
          <div className="text-xs font-medium text-slate-600">Account store</div>
          <div className="mt-1 break-all text-xs font-semibold text-slate-950">{authDbPath}</div>
        </div>
        {authRequired && authenticated ? (
          <>
            <form
              className="mt-3 grid gap-2 rounded-md border border-slate-200 bg-white p-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]"
              onSubmit={onChangePassword}
            >
              <label className="block min-w-0">
                <span className="mb-2 block text-xs font-semibold text-slate-700">Current password</span>
                <input
                  className="h-8 w-full rounded-md border border-slate-300 bg-white px-2.5 text-xs font-medium text-slate-950 outline-none placeholder:text-slate-500 focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
                  type="password"
                  value={currentPassword}
                  autoComplete="current-password"
                  onChange={(event) => onCurrentPasswordChange(event.target.value)}
                />
              </label>
              <label className="block min-w-0">
                <span className="mb-2 block text-xs font-semibold text-slate-700">New password</span>
                <input
                  className="h-8 w-full rounded-md border border-slate-300 bg-white px-2.5 text-xs font-medium text-slate-950 outline-none placeholder:text-slate-500 focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
                  type="password"
                  value={newPassword}
                  autoComplete="new-password"
                  minLength={8}
                  onChange={(event) => onNewPasswordChange(event.target.value)}
                />
              </label>
              <div className="flex items-end">
                <Button className="w-full lg:w-auto" type="submit" disabled={!canChangePassword}>
                  {passwordChangeRunning ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <KeyRound className="size-4" />
                  )}
                  {passwordChangeRunning ? 'Updating' : 'Change password'}
                </Button>
              </div>
            </form>
            {passwordChangeResult ? (
              <div className="mt-2 rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-xs font-medium text-blue-700">
                {passwordChangeResult}
              </div>
            ) : null}
            {passwordChangeError ? (
              <div className="mt-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs font-medium text-red-700">
                {passwordChangeError}
              </div>
            ) : null}
            <Button className="mt-3" variant="secondary" onClick={onSignOut} disabled={signingOut}>
              <LogOut className="size-4" />
              {signingOut ? 'Signing out' : 'Sign out'}
            </Button>
          </>
        ) : null}
      </CardContent>
    </Card>
  )
}

function LicenseCard({
  status,
  plan,
  billingEnabled,
  generatedAt,
}: {
  status: string
  plan: string
  billingEnabled: boolean
  generatedAt: string | null
}) {
  return (
    <Card>
      <CardHeader>
        <div>
          <div className="text-sm font-semibold text-slate-950">License</div>
          <div className="mt-1 text-xs text-slate-600">Open-source distribution terms.</div>
        </div>
        <BadgeCheck className="size-5 text-slate-500" />
      </CardHeader>
      <CardContent>
        <div className="grid gap-2">
          <SettingsMetric label="Status" value={status} />
          <SettingsMetric label="License" value={plan} />
          <SettingsMetric label="Billing" value={billingEnabled ? 'Enabled' : 'Not applicable'} />
        </div>
        <div className="mt-3 rounded-md border border-slate-200 bg-white px-3 py-2 text-xs leading-5 text-slate-600">
          Application code is GPL-3.0-or-later. Installed models keep their own terms.
        </div>
        {generatedAt ? (
          <div className="mt-2 text-xs font-medium text-slate-500">
            Diagnostics: {formatDiagnosticTime(generatedAt)}
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}

function StorageManagementCard({
  storageItems,
  cleanupRunning,
  cleanupResult,
  cleanupError,
  onRefresh,
  onRequestCleanup,
}: {
  storageItems: Array<{
    name: string
    path: string
    exists: boolean
    is_dir: boolean
    size_bytes: number
    file_count: number
  }>
  cleanupRunning: boolean
  cleanupResult: string | null
  cleanupError: string | null
  onRefresh: () => void
  onRequestCleanup: (option: RetentionOption) => void
}) {
  const dataRoot = storageItems.find((item) => item.name === 'data')
  const jobStorage = storageItems.filter((item) => item.name === 'asr_jobs' || item.name === 'tts_jobs')
  const jobBytes = jobStorage.reduce((sum, item) => sum + item.size_bytes, 0)
  const jobFiles = jobStorage.reduce((sum, item) => sum + item.file_count, 0)
  const visibleStorage = storageItems.filter((item) =>
    ['voices', 'asr_jobs', 'tts_jobs', 'uploads', 'outputs', 'logs', 'auth_db'].includes(item.name),
  )

  return (
    <Card>
      <CardHeader>
        <div>
          <div className="text-sm font-semibold text-slate-950">Storage and retention</div>
          <div className="mt-1 text-xs text-slate-600">
            Local workspace usage and terminal job cleanup.
          </div>
        </div>
        <Database className="size-5 text-slate-500" />
      </CardHeader>
      <CardContent>
        <div className="grid gap-2 md:grid-cols-3">
          <SettingsMetric label="Data root" value={formatBytes(dataRoot?.size_bytes ?? 0)} />
          <SettingsMetric label="Job files" value={`${formatBytes(jobBytes)} / ${jobFiles} files`} />
          <SettingsMetric label="Tracked paths" value={`${visibleStorage.length} paths`} />
        </div>

        <div className="mt-3 grid gap-2 lg:grid-cols-2 xl:grid-cols-4">
          {visibleStorage.map((item) => (
            <StoragePathRow key={item.name} item={item} />
          ))}
        </div>

        <div className="mt-3 rounded-md border border-slate-200 bg-white p-3">
          <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div className="text-xs font-semibold text-slate-950">Terminal job retention</div>
              <div className="mt-1 text-xs leading-5 text-slate-600">
                Cleanup removes succeeded, failed, and cancelled ASR/TTS jobs only.
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" onClick={onRefresh}>
                <ShieldCheck className="size-4" />
                Refresh usage
              </Button>
              {retentionOptions.map((option) => (
                <Button
                  key={option.id}
                  variant="secondary"
                  disabled={cleanupRunning}
                  onClick={() => onRequestCleanup(option)}
                >
                  {cleanupRunning ? <Loader2 className="size-4 animate-spin" /> : <Eraser className="size-4" />}
                  {option.label}
                </Button>
              ))}
            </div>
          </div>
          {cleanupResult ? (
            <div className="mt-3 rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-xs font-medium text-blue-700">
              {cleanupResult}
            </div>
          ) : null}
          {cleanupError ? (
            <div className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs font-medium text-red-700">
              {cleanupError}
            </div>
          ) : null}
        </div>
      </CardContent>
    </Card>
  )
}

function StoragePathRow({
  item,
}: {
  item: {
    name: string
    path: string
    exists: boolean
    is_dir: boolean
    size_bytes: number
    file_count: number
  }
}) {
  return (
    <div className="rounded-md border border-slate-200 bg-white px-2.5 py-2">
      <div className="flex items-center justify-between gap-2">
        <div className="truncate text-xs font-semibold text-slate-950">{storageLabel(item.name)}</div>
        <div
          className={
            item.exists
              ? 'rounded-md bg-blue-50 px-1.5 py-0.5 text-[10px] font-bold text-blue-700'
              : 'rounded-md bg-amber-50 px-1.5 py-0.5 text-[10px] font-bold text-amber-700'
          }
        >
          {item.exists ? (item.is_dir ? 'dir' : 'file') : 'missing'}
        </div>
      </div>
      <div className="mt-2 text-xs font-semibold text-slate-800">{formatBytes(item.size_bytes)}</div>
      <div className="mt-1 text-xs font-medium text-slate-500">{item.file_count} files</div>
      <div className="mt-2 truncate text-xs text-slate-500" title={item.path}>
        {item.path}
      </div>
    </div>
  )
}

function storageLabel(name: string) {
  return name
    .split('_')
    .map((part) => part.slice(0, 1).toUpperCase() + part.slice(1))
    .join(' ')
}

function SettingsMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white px-2.5 py-2">
      <div className="text-xs font-medium text-slate-600">{label}</div>
      <div className="mt-1 truncate text-xs font-semibold text-slate-950">{value}</div>
    </div>
  )
}

function SystemDiagnosticsCard({
  backendOffline,
  runtimeReady,
  version,
  environment,
  logLevel,
  provider,
  threads,
  ttsLoaded,
  asrLoaded,
  ttsLanguages,
  asrLanguages,
  asrWorkers,
  ttsWorkers,
  startupWarmup,
  passedChecks,
  totalChecks,
  checks,
  diagnosticsRunning,
  warmupRunning,
  bundleRunning,
  warmupError,
  bundleError,
  onRunDiagnostics,
  onWarmup,
  onDownloadBundle,
}: {
  backendOffline: boolean
  runtimeReady: boolean
  version: string
  environment: string
  logLevel: string
  provider: string
  threads: string
  ttsLoaded: boolean
  asrLoaded: boolean
  ttsLanguages: string[]
  asrLanguages: string[]
  asrWorkers: number
  ttsWorkers: number
  startupWarmup: boolean
  passedChecks: number
  totalChecks: number
  checks: Array<[string, boolean]>
  diagnosticsRunning: boolean
  warmupRunning: boolean
  bundleRunning: boolean
  warmupError: string | null
  bundleError: string | null
  onRunDiagnostics: () => void
  onWarmup: () => void
  onDownloadBundle: () => void
}) {
  const healthy = !backendOffline && runtimeReady && passedChecks === totalChecks && totalChecks > 0
  const headline = healthy ? 'Runtime available' : 'Runtime needs attention'

  return (
    <section className="rounded-md border border-slate-200 bg-white p-3">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-xs font-medium text-blue-700">
            <span className="grid size-7 place-items-center rounded-md border border-sky-200 bg-white">
              <ShieldCheck className="size-4" />
            </span>
            Runtime pulse
          </div>
          <div className="mt-3 text-sm font-semibold text-slate-950">{headline}</div>
          <p className="mt-2 max-w-2xl text-xs leading-5 text-slate-600">
            Backend, model readiness, and inference checks stay visible without turning Settings into a control room.
          </p>
        </div>

        <div className="grid gap-2 sm:grid-cols-3 lg:min-w-[560px]">
          <SignalRow label="Backend" value={backendOffline ? 'Offline' : 'Online'} good={!backendOffline} />
          <SignalRow label="Models" value={runtimeReady ? 'Ready' : 'Setup'} good={runtimeReady} />
          <SignalRow
            label="Checks"
            value={totalChecks > 0 ? `${passedChecks}/${totalChecks}` : 'Waiting'}
            good={totalChecks > 0 && passedChecks === totalChecks}
          />
        </div>
      </div>

      <div className="mt-3 flex flex-wrap justify-start gap-2">
        <Button variant="secondary" onClick={onRunDiagnostics}>
          {diagnosticsRunning ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <ShieldCheck className="size-4" />
          )}
          {diagnosticsRunning ? 'Checking' : 'Run diagnostics'}
        </Button>
        <Button variant="secondary" disabled={warmupRunning || backendOffline} onClick={onWarmup}>
          {warmupRunning ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <CheckCircle2 className="size-4" />
          )}
          {warmupRunning ? 'Warming' : 'Warm models'}
        </Button>
        <Button variant="secondary" disabled={bundleRunning || backendOffline} onClick={onDownloadBundle}>
          {bundleRunning ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <Download className="size-4" />
          )}
          {bundleRunning ? 'Preparing' : 'Download diagnostics'}
        </Button>
      </div>
      {warmupError ? (
        <div className="mt-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs font-medium leading-5 text-red-700">
          {warmupError}
        </div>
      ) : null}
      {bundleError ? (
        <div className="mt-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs font-medium leading-5 text-red-700">
          {bundleError}
        </div>
      ) : null}

      <SignalBars healthy={healthy} />

      <details className="group mt-3 rounded-md border border-slate-200 bg-white">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-2 text-xs font-medium text-slate-700">
          Advanced diagnostics
          <ChevronDown className="size-4 text-slate-500 transition-transform group-open:rotate-180" />
        </summary>
        <div className="border-t border-slate-200 p-3">
          <div className="grid grid-cols-2 gap-2 text-xs lg:grid-cols-4 xl:grid-cols-9">
            <SignalMeta label="Version" value={version} />
            <SignalMeta label="Environment" value={environment} />
            <SignalMeta label="Log level" value={logLevel} />
            <SignalMeta label="Provider" value={provider} />
            <SignalMeta label="Threads" value={threads} />
            <SignalMeta label="Workers" value={`ASR ${asrWorkers} / TTS ${ttsWorkers}`} />
            <SignalMeta label="Startup" value={startupWarmup ? 'warmup on' : 'manual warmup'} />
            <SignalMeta label="TTS" value={formatRuntimeMeta(ttsLoaded, ttsLanguages)} />
            <SignalMeta label="ASR" value={formatRuntimeMeta(asrLoaded, asrLanguages)} />
          </div>
          <div className="mt-3 grid gap-2 md:grid-cols-2">
            {checks.length > 0 ? (
              checks.map(([name, passed]) => <CheckRow key={name} label={name} passed={passed} />)
            ) : (
              <div className="rounded-md border border-dashed border-slate-300 bg-white p-4 text-center text-xs text-slate-600 md:col-span-2">
                Waiting for model status.
              </div>
            )}
          </div>
        </div>
      </details>
    </section>
  )
}

function SignalBars({ healthy }: { healthy: boolean }) {
  return (
    <div className="mt-3 flex h-20 items-end gap-1.5 overflow-hidden rounded-md border border-slate-200 bg-white px-3 py-3">
      {Array.from({ length: 28 }).map((_, index) => (
        <motion.div
          // eslint-disable-next-line react/no-array-index-key
          key={index}
          className={
            healthy
              ? 'w-full rounded-t bg-emerald-500'
              : 'w-full rounded-t bg-amber-500'
          }
          initial={{ height: 10 + ((index * 7) % 20), opacity: 0.65 }}
          animate={{ height: [12 + ((index * 5) % 22), 30 + ((index * 11) % 18), 14 + ((index * 3) % 20)] }}
          transition={{
            duration: 1.6 + (index % 5) * 0.12,
            repeat: Infinity,
            repeatType: 'mirror',
            ease: 'easeInOut',
          }}
        />
      ))}
    </div>
  )
}

function SignalMeta({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white px-2.5 py-2">
      <div className="text-xs font-medium text-slate-600">{label}</div>
      <div className="mt-1 truncate font-semibold text-slate-950">{value}</div>
    </div>
  )
}

function SignalRow({ label, value, good }: { label: string; value: string; good: boolean }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white px-3 py-2">
      <div className="flex items-center gap-2">
        {good ? (
          <CheckCircle2 className="size-4 shrink-0 text-emerald-600" />
        ) : (
          <XCircle className="size-4 shrink-0 text-amber-700" />
        )}
        <div className="min-w-0">
          <div className="text-xs font-medium text-slate-600">{label}</div>
          <div className="mt-0.5 truncate text-xs font-semibold text-slate-950">{value}</div>
        </div>
      </div>
    </div>
  )
}

function CheckRow({ label, passed }: { label: string; passed: boolean }) {
  return (
    <div className="flex items-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-2">
      {passed ? (
        <CheckCircle2 className="size-4 shrink-0 text-emerald-600" />
      ) : (
        <XCircle className="size-4 shrink-0 text-amber-700" />
      )}
      <div className="flex min-w-0 items-center gap-2">
        <span className="truncate text-xs font-semibold text-slate-800">{label}</span>
      </div>
    </div>
  )
}

function formatRuntimeMeta(loaded: boolean, languages: string[]) {
  const state = loaded ? 'loaded' : 'cold'
  if (!languages.length) {
    return state
  }
  return `${state} / ${languages.map((language) => language.toUpperCase()).join(', ')}`
}

function formatSeconds(seconds: number) {
  if (!seconds) {
    return 'default'
  }
  const days = Math.round(seconds / 86400)
  if (days >= 1) {
    return `${days}d`
  }
  const hours = Math.round(seconds / 3600)
  if (hours >= 1) {
    return `${hours}h`
  }
  return `${seconds}s`
}

function formatDiagnosticTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString()
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.append(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

function AdvancedSettings() {
  return (
    <Card>
      <details className="group">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-3">
          <div className="min-w-0">
            <div className="text-sm font-semibold text-slate-950">Advanced</div>
            <div className="mt-1 text-xs text-slate-600">
              Backend links and repository paths for operators.
            </div>
          </div>
          <ChevronDown className="size-4 shrink-0 text-slate-500 transition-transform group-open:rotate-180" />
        </summary>
        <div className="border-t border-slate-200 px-3 pb-3 pt-3">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-800">
            <ExternalLink className="size-4 text-slate-500" />
            Backend endpoints
          </div>
          <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-4">
            {endpointRows.map((row) => (
              <a
                key={row.href}
                className="flex h-8 items-center justify-between gap-2 rounded-md border border-slate-200 bg-white px-2.5 text-xs font-medium text-slate-900 transition-colors hover:border-sky-200 hover:text-blue-700"
                href={row.href}
                target="_blank"
                rel="noreferrer"
              >
                {row.label}
                <ExternalLink className="size-4 shrink-0 text-slate-500" />
              </a>
            ))}
          </div>

          <div className="mt-4 flex items-center gap-2 text-xs font-semibold text-slate-800">
            <FolderOpen className="size-4 text-slate-500" />
            Storage paths
          </div>
          <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-5">
            {storageRows.map((row) => (
              <div key={row.label} className="rounded-md border border-slate-200 bg-white p-3">
                <Database className="size-4 text-blue-700" />
                <div className="mt-2 text-sm font-semibold text-slate-950">{row.label}</div>
                <div className="mt-1 break-all text-xs font-medium text-slate-600">{row.value}</div>
                <p className="mt-2 text-xs leading-5 text-slate-500">{row.description}</p>
              </div>
            ))}
          </div>
        </div>
      </details>
    </Card>
  )
}
