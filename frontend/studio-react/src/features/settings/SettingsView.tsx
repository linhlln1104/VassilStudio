import { type FormEvent, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ChevronDown,
  BadgeCheck,
  Database,
  Eraser,
  Eye,
  EyeOff,
  ExternalLink,
  FolderOpen,
  KeyRound,
  Loader2,
  LockKeyhole,
  LogOut,
  RefreshCw,
  Trash2,
  UserRound,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { useToast } from '@/components/ui/use-toast'
import {
  api,
  clearBrowserApiKey,
  getBrowserApiKeyState,
  setBrowserApiKey,
  setBrowserApiKeyPersistence,
  type DiagnosticsStorageItem,
} from '@/lib/api'
import { API_BRAND_NAME } from '@/lib/brand'
import { RuntimeDiagnostics, type WarmupTarget } from './RuntimeDiagnostics'

const storageRows = [
  { label: 'Source models', value: 'MODEL_SOURCE_ROOT', description: 'Original checkpoints and research assets.' },
  { label: 'Runtime models', value: 'MODEL_RUNTIME_ROOT', description: 'ONNX models loaded by the backend.' },
  { label: 'Voice assets', value: 'DATA_ROOT/voices', description: 'Reference clips and prepared voice profiles.' },
  { label: 'Generated outputs', value: 'DATA_ROOT/outputs', description: 'Rendered TTS audio and exported files.' },
  { label: 'Contracts', value: 'CONTRACT_ROOT', description: 'Generated API contract for integrations.' },
]

const endpointRows = [
  { label: 'Backend health', href: '/health' },
  { label: 'Liveness probe', href: '/livez' },
  { label: 'Readiness probe', href: '/readyz' },
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

type SettingsTab = 'runtime' | 'account' | 'storage' | 'security'

const settingsTabs: Array<{ value: SettingsTab; label: string }> = [
  { value: 'runtime', label: 'Runtime' },
  { value: 'account', label: 'Account' },
  { value: 'storage', label: 'Storage' },
  { value: 'security', label: 'Security' },
]

export function SettingsView() {
  const [activeTab, setActiveTab] = useState<SettingsTab>('runtime')
  const [apiKeyDraft, setApiKeyDraft] = useState('')
  const [apiKeySaved, setApiKeySaved] = useState(() => getBrowserApiKeyState().active)
  const [persistApiKeyForSession, setPersistApiKeyForSession] = useState(
    () => getBrowserApiKeyState().persistence === 'session',
  )
  const [showApiKey, setShowApiKey] = useState(false)
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [passwordChangeResult, setPasswordChangeResult] = useState<string | null>(null)
  const [cleanupTarget, setCleanupTarget] = useState<RetentionOption | null>(null)
  const [cleanupResult, setCleanupResult] = useState<string | null>(null)
  const [clearKeyConfirmOpen, setClearKeyConfirmOpen] = useState(false)
  const [includeHostMetadata, setIncludeHostMetadata] = useState(false)
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const healthQuery = useQuery({
    queryKey: ['health'],
    queryFn: api.health,
    refetchInterval: 10000,
  })
  const livenessQuery = useQuery({
    queryKey: ['liveness'],
    queryFn: api.liveness,
    refetchInterval: 10000,
  })
  const readinessQuery = useQuery({
    queryKey: ['readiness'],
    queryFn: api.readiness,
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
  const ownerSessionActive = Boolean(
    authQuery.data?.auth_required && authQuery.data.authenticated,
  )
  const diagnosticsQuery = useQuery({
    queryKey: ['diagnostics'],
    queryFn: api.diagnostics,
    refetchInterval: 30000,
  })
  const warmupMutation = useMutation<unknown, Error, WarmupTarget>({
    mutationFn: (target: WarmupTarget) => {
      if (target.engine === 'all') {
        return api.warmup()
      }
      return target.engine === 'asr' ? api.warmupAsr(target.language) : api.warmupTts(target.language)
    },
    onSuccess: (_, target) => {
      void queryClient.invalidateQueries({ queryKey: ['health'] })
      void queryClient.invalidateQueries({ queryKey: ['readiness'] })
      void queryClient.invalidateQueries({ queryKey: ['model-status'] })
      void queryClient.invalidateQueries({ queryKey: ['diagnostics'] })
      const targetLabel = target.engine === 'all'
        ? 'All configured models'
        : `${target.language.toUpperCase()} ${target.engine.toUpperCase()}`
      toast({
        title: 'Warmup complete',
        description: `${targetLabel} loaded successfully.`,
        variant: 'success',
      })
    },
    onError: (error) => {
      toast({
        title: 'Warmup failed',
        description: error instanceof Error ? error.message : 'Unable to load the selected runtime.',
        variant: 'danger',
      })
    },
  })
  const logoutMutation = useMutation({
    mutationFn: api.authLogout,
    onSuccess: () => {
      window.location.assign('/login')
    },
    onError: (error) => {
      toast({
        title: 'Sign out failed',
        description: error instanceof Error ? error.message : 'Unable to end this session.',
        variant: 'danger',
      })
    },
  })
  const changePasswordMutation = useMutation({
    mutationFn: api.authChangePassword,
    onSuccess: (result) => {
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      setPasswordChangeResult(
        result.other_sessions_revoked > 0
          ? `Password updated. Revoked ${result.other_sessions_revoked} other sessions.`
          : 'Password updated.',
      )
      void queryClient.invalidateQueries({ queryKey: ['auth-status'] })
    },
  })
  const diagnosticsBundleMutation = useMutation({
    mutationFn: (includeHostDetails: boolean) => api.diagnosticsBundle(includeHostDetails),
    onSuccess: (blob, includeHostDetails) => {
      downloadBlob(blob, `vassilstudio-diagnostics-${Date.now()}.zip`)
      if (includeHostDetails) {
        setIncludeHostMetadata(false)
      }
      toast({
        title: 'Diagnostics downloaded',
        description: includeHostDetails
          ? 'This bundle includes host details. Review it before sharing.'
          : 'The privacy-filtered bundle is ready. Review it before sharing.',
        variant: 'success',
      })
    },
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

  const diagnosticsRunning =
    healthQuery.isFetching ||
    livenessQuery.isFetching ||
    readinessQuery.isFetching ||
    modelQuery.isFetching ||
    diagnosticsQuery.isFetching
  const runtimeQueryErrors = [
    queryError('Health', healthQuery.error),
    queryError('Liveness', livenessQuery.error),
    queryError('Readiness', readinessQuery.error),
    queryError('Model status', modelQuery.error),
    queryError('Diagnostics', diagnosticsQuery.error),
  ].filter((item): item is { source: string; message: string } => Boolean(item))
  const lastCheckedAt = Math.max(
    healthQuery.dataUpdatedAt,
    livenessQuery.dataUpdatedAt,
    readinessQuery.dataUpdatedAt,
    modelQuery.dataUpdatedAt,
    diagnosticsQuery.dataUpdatedAt,
  )

  const runDiagnostics = async () => {
    const results = await Promise.all([
      healthQuery.refetch(),
      livenessQuery.refetch(),
      readinessQuery.refetch(),
      modelQuery.refetch(),
      diagnosticsQuery.refetch(),
    ])
    const failed = results.filter((result) => result.isError).length
    toast({
      title: failed ? 'Diagnostics incomplete' : 'Diagnostics complete',
      description: failed
        ? `${failed} checks could not be refreshed.`
        : 'Runtime, model, and storage signals are current.',
      variant: failed ? 'danger' : 'success',
    })
  }

  const handleApiKeySave = () => {
    const normalized = apiKeyDraft.trim()
    if (!normalized) {
      return
    }
    const state = setBrowserApiKey(normalized, { persistForSession: persistApiKeyForSession })
    setApiKeyDraft('')
    setApiKeySaved(state.active)
    setPersistApiKeyForSession(state.persistence === 'session')
    setShowApiKey(false)
    void modelQuery.refetch()
    toast({
      title: state.persistence === 'session' ? 'API key active for this tab' : 'API key active in memory',
      description: state.persistence === 'session'
        ? 'The key survives reloads in this tab and is cleared on sign-out.'
        : 'The key is cleared on reload, sign-out, or tab close.',
      variant: persistApiKeyForSession && state.persistence !== 'session' ? 'danger' : 'success',
    })
  }

  const handleApiKeyPersistenceChange = (persistForSession: boolean) => {
    setPersistApiKeyForSession(persistForSession)
    if (!apiKeySaved) {
      return
    }
    const state = setBrowserApiKeyPersistence(persistForSession)
    setPersistApiKeyForSession(state.persistence === 'session')
    if (persistForSession && state.persistence !== 'session') {
      toast({
        title: 'Session storage unavailable',
        description: 'The API key remains memory-only.',
        variant: 'danger',
      })
    }
  }

  const clearApiKey = () => {
    setApiKeyDraft('')
    clearBrowserApiKey()
    setApiKeySaved(false)
    setPersistApiKeyForSession(false)
    setShowApiKey(false)
    setClearKeyConfirmOpen(false)
    void modelQuery.refetch()
    toast({
      title: 'API key cleared',
      description: 'Protected requests no longer use a temporary browser key.',
      variant: 'success',
    })
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-2 rounded-md border border-slate-200 bg-white p-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="hidden px-1 sm:block">
          <div className="text-xs font-semibold text-slate-950">Workspace settings</div>
          <div className="mt-1 text-xs text-slate-500">Local runtime and operator controls.</div>
        </div>
        <SegmentedControl
          equalWidth
          className="w-full sm:w-[430px]"
          itemClassName="px-1 sm:px-3"
          options={settingsTabs}
          value={activeTab}
          onChange={setActiveTab}
        />
      </div>

      {activeTab === 'runtime' ? (
        <>
          <RuntimeDiagnostics
            health={healthQuery.data}
            liveness={livenessQuery.data}
            readiness={readinessQuery.data}
            model={modelQuery.data}
            diagnostics={diagnosticsQuery.data}
            loading={
              healthQuery.isLoading ||
              livenessQuery.isLoading ||
              readinessQuery.isLoading ||
              modelQuery.isLoading
            }
            refreshing={diagnosticsRunning}
            lastCheckedAt={lastCheckedAt}
            queryErrors={runtimeQueryErrors}
            warmingTarget={warmupMutation.isPending ? warmupMutation.variables : null}
            bundleRunning={diagnosticsBundleMutation.isPending}
            warmupError={warmupMutation.error instanceof Error ? warmupMutation.error.message : null}
            bundleError={
              diagnosticsBundleMutation.error instanceof Error ? diagnosticsBundleMutation.error.message : null
            }
            includeHostMetadata={includeHostMetadata}
            onRunDiagnostics={() => { void runDiagnostics() }}
            onWarmup={(target) => warmupMutation.mutate(target)}
            onIncludeHostMetadataChange={setIncludeHostMetadata}
            onDownloadBundle={() => diagnosticsBundleMutation.mutate(includeHostMetadata)}
          />
          <AdvancedSettings />
        </>
      ) : null}

      {activeTab === 'account' ? (
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
          authDbLocation={
            diagnosticsQuery.data?.storage.find((item) => item.name === 'auth_db')?.path_alias
              ?? 'DATA_ROOT/auth.sqlite3'
          }
          signingOut={logoutMutation.isPending}
          currentPassword={currentPassword}
          newPassword={newPassword}
          confirmPassword={confirmPassword}
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
          onConfirmPasswordChange={(value) => {
            setConfirmPassword(value)
            setPasswordChangeResult(null)
            changePasswordMutation.reset()
          }}
          onChangePassword={(event) => {
            event.preventDefault()
            if (!currentPassword || newPassword.length < 8 || newPassword !== confirmPassword) {
              return
            }
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
      ) : null}

      {activeTab === 'storage' ? (
        <StorageManagementCard
          storageItems={diagnosticsQuery.data?.storage ?? []}
          loading={diagnosticsQuery.isLoading}
          refreshing={diagnosticsQuery.isFetching}
          error={diagnosticsQuery.error instanceof Error ? diagnosticsQuery.error.message : null}
          generatedAt={diagnosticsQuery.data?.generated_at ?? null}
          cleanupRunning={cleanupJobsMutation.isPending}
          cleanupResult={cleanupResult}
          cleanupError={cleanupJobsMutation.error instanceof Error ? cleanupJobsMutation.error.message : null}
          onRefresh={() => {
            void diagnosticsQuery.refetch()
          }}
          onRequestCleanup={(option) => setCleanupTarget(option)}
        />
      ) : null}

      {activeTab === 'security' ? (
        <Card>
          <CardHeader>
          <div>
            <div className="text-sm font-semibold text-slate-950">Browser access</div>
            <div className="mt-1 text-xs text-slate-600">
              Owner sign-in is preferred. Use an automation key only for temporary browser access.
            </div>
          </div>
          <LockKeyhole className="size-5 text-slate-500" />
          </CardHeader>
          <CardContent>
          <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_auto]">
            <label className="block min-w-0">
              <span className="mb-2 block text-xs font-semibold text-slate-700">
                {API_BRAND_NAME} automation key
              </span>
              <div className="flex min-w-0 rounded-md border border-slate-300 bg-white focus-within:border-sky-500 focus-within:ring-2 focus-within:ring-sky-100">
                <input
                  className="h-8 min-w-0 flex-1 rounded-l-md border-0 bg-transparent px-2.5 text-xs font-medium text-slate-950 outline-none placeholder:text-slate-500"
                  type={showApiKey ? 'text' : 'password'}
                  value={apiKeyDraft}
                  placeholder="Paste API key for protected endpoints"
                  autoComplete="off"
                  disabled={!authQuery.data?.api_key_auth_enabled}
                  onChange={(event) => {
                    setApiKeyDraft(event.target.value)
                  }}
                />
                <button
                  className="grid h-8 w-8 place-items-center text-slate-500 hover:text-slate-950"
                  type="button"
                  disabled={!authQuery.data?.api_key_auth_enabled || !apiKeyDraft}
                  aria-label={showApiKey ? 'Hide API key' : 'Show API key'}
                  title={showApiKey ? 'Hide API key' : 'Show API key'}
                  onClick={() => setShowApiKey((value) => !value)}
                >
                  {showApiKey ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>
            </label>
            <div className="flex flex-wrap items-end gap-2">
              <Button
                disabled={!authQuery.data?.api_key_auth_enabled || !apiKeyDraft.trim()}
                onClick={handleApiKeySave}
              >
                <KeyRound className="size-4" />
                Use key
              </Button>
              <Button
                className="w-9 border-red-200 px-0 text-red-700 hover:bg-red-50 hover:text-red-800"
                variant="secondary"
                disabled={!apiKeyDraft && !apiKeySaved}
                aria-label="Clear temporary API key"
                title="Clear temporary API key"
                onClick={() => setClearKeyConfirmOpen(true)}
              >
                <Trash2 className="size-4" />
              </Button>
            </div>
          </div>
          <div className="mt-3 flex flex-col gap-2 border-t border-slate-200 pt-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2 text-xs font-medium text-slate-600">
              <Badge variant={apiKeySaved ? ownerSessionActive ? 'warning' : 'success' : 'muted'}>
                {apiKeySaved ? ownerSessionActive ? 'Standby' : 'Active' : 'Not set'}
              </Badge>
              <span>
                {apiKeySaved
                  ? ownerSessionActive
                    ? 'Owner session active; the temporary key is not sent.'
                    : persistApiKeyForSession
                    ? 'Available through reloads in this tab.'
                    : 'Memory-only until this page reloads.'
                  : authQuery.data?.api_key_auth_enabled
                    ? 'Owner session remains the preferred access method.'
                    : 'Automation key auth is not configured.'}
              </span>
            </div>
            <label className="flex items-center gap-2 text-xs font-medium text-slate-700">
              <input
                className="size-4 accent-blue-600"
                type="checkbox"
                checked={persistApiKeyForSession}
                disabled={!authQuery.data?.api_key_auth_enabled}
                onChange={(event) => handleApiKeyPersistenceChange(event.target.checked)}
              />
              Keep through reloads in this tab
            </label>
          </div>
          </CardContent>
        </Card>
      ) : null}

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
        title="Clear temporary API key?"
        description={`This removes the active ${API_BRAND_NAME} key from memory and this tab's session storage. Server-side keys are unchanged.`}
        confirmLabel="Clear key"
        busyLabel="Clearing"
        onOpenChange={setClearKeyConfirmOpen}
        onConfirm={clearApiKey}
      />
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
  authDbLocation,
  signingOut,
  currentPassword,
  newPassword,
  confirmPassword,
  passwordChangeRunning,
  passwordChangeResult,
  passwordChangeError,
  onSignOut,
  onCurrentPasswordChange,
  onNewPasswordChange,
  onConfirmPasswordChange,
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
  authDbLocation: string
  signingOut: boolean
  currentPassword: string
  newPassword: string
  confirmPassword: string
  passwordChangeRunning: boolean
  passwordChangeResult: string | null
  passwordChangeError: string | null
  onSignOut: () => void
  onCurrentPasswordChange: (value: string) => void
  onNewPasswordChange: (value: string) => void
  onConfirmPasswordChange: (value: string) => void
  onChangePassword: (event: FormEvent<HTMLFormElement>) => void
}) {
  const [showPasswords, setShowPasswords] = useState(false)
  const passwordMismatch = confirmPassword.length > 0 && newPassword !== confirmPassword
  const canChangePassword =
    currentPassword.length > 0 &&
    newPassword.length >= 8 &&
    newPassword === confirmPassword &&
    !passwordChangeRunning

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
          <div className="mt-1 break-all text-xs font-semibold text-slate-950">{authDbLocation}</div>
        </div>
        {authRequired && authenticated ? (
          <>
            <form
              className="mt-3 rounded-md border border-slate-200 bg-white p-3"
              onSubmit={onChangePassword}
            >
              <div className="flex items-center justify-between gap-2">
                <div>
                  <div className="text-xs font-semibold text-slate-950">Change password</div>
                  <div className="mt-1 text-xs text-slate-500">At least 8 characters.</div>
                </div>
                <Button
                  className="w-8 px-0"
                  size="sm"
                  variant="ghost"
                  type="button"
                  aria-label={showPasswords ? 'Hide passwords' : 'Show passwords'}
                  title={showPasswords ? 'Hide passwords' : 'Show passwords'}
                  onClick={() => setShowPasswords((current) => !current)}
                >
                  {showPasswords ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </Button>
              </div>
              <div className="mt-3 grid gap-2 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_auto]">
                <PasswordField
                  label="Current password"
                  value={currentPassword}
                  visible={showPasswords}
                  autoComplete="current-password"
                  onChange={onCurrentPasswordChange}
                />
                <PasswordField
                  label="New password"
                  value={newPassword}
                  visible={showPasswords}
                  autoComplete="new-password"
                  minLength={8}
                  onChange={onNewPasswordChange}
                />
                <PasswordField
                  label="Confirm password"
                  value={confirmPassword}
                  visible={showPasswords}
                  autoComplete="new-password"
                  minLength={8}
                  invalid={passwordMismatch}
                  onChange={onConfirmPasswordChange}
                />
                <div className="flex items-end">
                  <Button className="w-full lg:w-auto" type="submit" disabled={!canChangePassword}>
                    {passwordChangeRunning ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : (
                      <KeyRound className="size-4" />
                    )}
                    {passwordChangeRunning ? 'Updating' : 'Update'}
                  </Button>
                </div>
              </div>
              {passwordMismatch ? (
                <div className="mt-2 text-xs font-medium text-red-700" role="alert">Passwords do not match.</div>
              ) : null}
            </form>
            {passwordChangeResult ? (
              <div className="mt-2 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-medium text-emerald-800">
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

function PasswordField({
  label,
  value,
  visible,
  autoComplete,
  minLength,
  invalid = false,
  onChange,
}: {
  label: string
  value: string
  visible: boolean
  autoComplete: string
  minLength?: number
  invalid?: boolean
  onChange: (value: string) => void
}) {
  return (
    <label className="block min-w-0">
      <span className="mb-2 block text-xs font-semibold text-slate-700">{label}</span>
      <input
        className="h-8 w-full rounded-md border border-slate-300 bg-white px-2.5 text-xs font-medium text-slate-950 outline-none placeholder:text-slate-500 focus:border-sky-500 focus:ring-2 focus:ring-sky-100 aria-invalid:border-red-400 aria-invalid:ring-red-100"
        type={visible ? 'text' : 'password'}
        value={value}
        autoComplete={autoComplete}
        minLength={minLength}
        maxLength={512}
        required
        aria-invalid={invalid}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
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
  loading,
  refreshing,
  error,
  generatedAt,
  cleanupRunning,
  cleanupResult,
  cleanupError,
  onRefresh,
  onRequestCleanup,
}: {
  storageItems: DiagnosticsStorageItem[]
  loading: boolean
  refreshing: boolean
  error: string | null
  generatedAt: string | null
  cleanupRunning: boolean
  cleanupResult: string | null
  cleanupError: string | null
  onRefresh: () => void
  onRequestCleanup: (option: RetentionOption) => void
}) {
  const [retentionId, setRetentionId] = useState('30d')
  const dataRoot = storageItems.find((item) => item.name === 'data')
  const visibleStorage = storageItems.filter((item) =>
    ['voices', 'asr_jobs', 'tts_jobs', 'uploads', 'outputs', 'logs', 'auth_db'].includes(item.name),
  )
  const readinessStorage = storageItems.filter((item) =>
    ['data', 'voices', 'asr_jobs', 'tts_jobs', 'uploads', 'outputs', 'logs'].includes(item.name),
  )
  const healthyStorage = readinessStorage.filter((item) => item.exists && item.is_dir && item.writable)
  const storageIssues = readinessStorage.filter((item) => !item.exists || !item.is_dir || !item.writable)
  const selectedRetention = retentionOptions.find((option) => option.id === retentionId) ?? retentionOptions[1]
  const storagePressure = dataRoot?.storage_pressure ?? 'unknown'
  const lowDiskSpace = storagePressure === 'low' || storagePressure === 'critical'

  return (
    <section>
      <div className="flex flex-col gap-2 border-b border-slate-200 px-1 pb-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="text-sm font-semibold text-slate-950">Storage and retention</div>
          <div className="mt-1 text-xs text-slate-600">
            Local workspace inventory, disk headroom, and terminal job cleanup.
          </div>
        </div>
        <Button
          className="w-9 px-0"
          variant="secondary"
          disabled={refreshing}
          aria-label="Refresh storage usage"
          title="Refresh storage usage"
          onClick={onRefresh}
        >
          {refreshing ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
        </Button>
      </div>

      <div className="grid gap-2 py-3 sm:grid-cols-2 xl:grid-cols-4">
        <SettingsMetric label="Local data" value={formatUsageBucket(dataRoot?.usage_bucket)} />
        <SettingsMetric
          label="Disk free"
          value={formatCapacityBucket(dataRoot?.free_space_bucket)}
        />
        <SettingsMetric label="Disk status" value={formatStoragePressure(storagePressure)} />
        <SettingsMetric label="Path health" value={`${healthyStorage.length}/${readinessStorage.length || 0} ready`} />
      </div>

      {lowDiskSpace ? (
        <div
          className={
            storagePressure === 'critical'
              ? 'mb-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs font-medium leading-5 text-red-900'
              : 'mb-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-medium leading-5 text-amber-900'
          }
          role="alert"
        >
          Storage headroom is {storagePressure}. Free space before importing voices or rendering long outputs.
        </div>
      ) : null}

      {storageIssues.length ? (
        <div className="mb-3 rounded-md border border-red-200 bg-red-50 p-3" role="alert">
          <div className="text-xs font-semibold text-red-900">Storage needs attention</div>
          <div className="mt-1 space-y-1 text-xs leading-5 text-red-800">
            {storageIssues.map((item) => (
              <div key={item.name}>
                <span className="font-semibold">{storageLabel(item.name)}:</span>{' '}
                {!item.exists ? 'path is missing' : !item.is_dir ? 'expected a directory' : 'path is not writable'}
                <code className="ml-1 break-all">{item.path_alias}</code>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {error ? (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-center">
          <div className="text-sm font-semibold text-red-950">Storage diagnostics unavailable</div>
          <p className="mt-1 text-xs leading-5 text-red-800">{error}</p>
          <Button className="mt-3" size="sm" variant="secondary" onClick={onRefresh}>
            <RefreshCw className="size-4" />
            Retry
          </Button>
        </div>
      ) : loading ? (
        <div className="grid gap-2 lg:grid-cols-2">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="h-16 animate-pulse rounded-md bg-slate-100" />
          ))}
        </div>
      ) : visibleStorage.length > 0 ? (
        <div className="divide-y divide-slate-100 rounded-md border border-slate-200 bg-white">
          {visibleStorage.map((item) => (
            <StoragePathRow key={item.name} item={item} />
          ))}
        </div>
      ) : (
        <div className="rounded-md border border-dashed border-slate-300 bg-white p-4 text-center text-xs text-slate-600">
          No storage inventory was returned.
        </div>
      )}

        <div className="mt-3 border-y border-slate-200 py-3">
          <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div className="text-xs font-semibold text-slate-950">Terminal job retention</div>
              <div className="mt-1 text-xs leading-5 text-slate-600">
                Cleanup removes succeeded, failed, and cancelled ASR/TTS jobs only.
              </div>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <SegmentedControl
                equalWidth
                className="w-full sm:w-[260px]"
                options={retentionOptions.map((option) => ({ value: option.id, label: option.label }))}
                value={retentionId}
                onChange={setRetentionId}
              />
              <Button
                variant={selectedRetention.id === 'all' ? 'destructive' : 'secondary'}
                disabled={cleanupRunning}
                onClick={() => onRequestCleanup(selectedRetention)}
              >
                {cleanupRunning ? <Loader2 className="size-4 animate-spin" /> : <Eraser className="size-4" />}
                {cleanupRunning ? 'Cleaning' : 'Clean jobs'}
              </Button>
            </div>
          </div>
          {cleanupResult ? (
            <div className="mt-3 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-medium text-emerald-800">
              {cleanupResult}
            </div>
          ) : null}
          {cleanupError ? (
            <div className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs font-medium text-red-700">
              {cleanupError}
            </div>
          ) : null}
        </div>
        <div className="mt-2 px-1 text-xs font-medium text-slate-500">
          {generatedAt ? `Inventory scanned ${formatDiagnosticTime(generatedAt)}` : 'Inventory has not been scanned.'}
        </div>
    </section>
  )
}

function StoragePathRow({ item }: { item: DiagnosticsStorageItem }) {
  const accountStorePending = item.name === 'auth_db' && !item.exists
  const healthy = item.exists && item.writable && (item.is_dir || item.name === 'auth_db')
  const status = accountStorePending ? 'Not created' : !item.exists ? 'Missing' : !item.writable ? 'Read only' : 'Ready'

  return (
    <div className="grid gap-2 px-3 py-2.5 sm:grid-cols-[150px_130px_minmax(0,1fr)_auto] sm:items-center">
      <div className="min-w-0">
        <div className="truncate text-xs font-semibold text-slate-950">{storageLabel(item.name)}</div>
        <div className="mt-0.5 text-xs text-slate-500">{item.is_dir ? 'Directory' : item.exists ? 'File' : 'Expected path'}</div>
      </div>
      <div className="text-xs text-slate-600">
        <span className="font-semibold text-slate-900">{formatUsageBucket(item.usage_bucket)}</span>
        <span className="ml-1">/ {formatFileCountBucket(item.file_count_bucket)}</span>
      </div>
      <code className="min-w-0 truncate text-xs text-slate-500" title={item.path_alias}>{item.path_alias}</code>
      <div className="flex justify-start sm:justify-end">
        <Badge variant={healthy ? 'success' : accountStorePending ? 'muted' : 'danger'}>{status}</Badge>
      </div>
    </div>
  )
}

function storageLabel(name: string) {
  const labels: Record<string, string> = {
    data: 'Data root',
    voices: 'Voice profiles',
    asr_jobs: 'ASR jobs',
    tts_jobs: 'TTS jobs',
    uploads: 'Uploads',
    outputs: 'Outputs',
    logs: 'Logs',
    auth_db: 'Account database',
  }
  if (labels[name]) {
    return labels[name]
  }
  return name
    .split('_')
    .map((part) => part.slice(0, 1).toUpperCase() + part.slice(1))
    .join(' ')
}

function formatUsageBucket(bucket: DiagnosticsStorageItem['usage_bucket'] | undefined) {
  if (!bucket) {
    return 'Unavailable'
  }
  const labels: Record<DiagnosticsStorageItem['usage_bucket'], string> = {
    empty: 'Empty',
    under_1_mb: '< 1 MB',
    '1_to_99_mb': '1-99 MB',
    '100_to_999_mb': '100-999 MB',
    '1_to_9_gb': '1-9 GB',
    '10_to_99_gb': '10-99 GB',
    '100_gb_or_more': '100+ GB',
  }
  return labels[bucket]
}

function formatFileCountBucket(bucket: DiagnosticsStorageItem['file_count_bucket']) {
  const labels: Record<DiagnosticsStorageItem['file_count_bucket'], string> = {
    none: 'no files',
    '1_to_9': '1-9 files',
    '10_to_99': '10-99 files',
    '100_to_999': '100-999 files',
    '1000_or_more': '1,000+ files',
  }
  return labels[bucket]
}

function formatCapacityBucket(bucket: DiagnosticsStorageItem['capacity_bucket'] | undefined) {
  if (!bucket) {
    return 'Unavailable'
  }
  const labels: Record<NonNullable<DiagnosticsStorageItem['capacity_bucket']>, string> = {
    under_10_gb: '< 10 GB',
    '10_to_49_gb': '10-49 GB',
    '50_to_99_gb': '50-99 GB',
    '100_to_499_gb': '100-499 GB',
    '500_to_999_gb': '500-999 GB',
    '1_tb_or_more': '1+ TB',
  }
  return labels[bucket]
}

function formatStoragePressure(pressure: DiagnosticsStorageItem['storage_pressure']) {
  const labels: Record<DiagnosticsStorageItem['storage_pressure'], string> = {
    normal: 'Healthy',
    low: 'Low headroom',
    critical: 'Critical',
    unknown: 'Unavailable',
  }
  return labels[pressure]
}

function SettingsMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white px-2.5 py-2">
      <div className="text-xs font-medium text-slate-600">{label}</div>
      <div className="mt-1 truncate text-xs font-semibold text-slate-950">{value}</div>
    </div>
  )
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

function queryError(source: string, error: unknown) {
  if (!error) {
    return null
  }
  return {
    source,
    message: error instanceof Error && error.message ? error.message : 'Request failed.',
  }
}

function AdvancedSettings() {
  return (
    <Card>
      <details className="group">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-3">
          <div className="min-w-0">
            <div className="text-sm font-semibold text-slate-950">Advanced</div>
            <div className="mt-1 text-xs text-slate-600">
              Backend links and logical storage aliases for operators.
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
            Storage aliases
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
