import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  ChevronDown,
  CheckCircle2,
  Copy,
  Database,
  Eye,
  EyeOff,
  ExternalLink,
  FolderOpen,
  KeyRound,
  Loader2,
  LockKeyhole,
  ShieldCheck,
  XCircle,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { api, getStoredApiKey, setStoredApiKey } from '@/lib/api'
import { API_BRAND_NAME } from '@/lib/brand'

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

export function SettingsView() {
  const [apiKeyDraft, setApiKeyDraft] = useState(() => getStoredApiKey())
  const [apiKeySaved, setApiKeySaved] = useState(false)
  const [showApiKey, setShowApiKey] = useState(false)
  const [copied, setCopied] = useState(false)
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
  const warmupMutation = useMutation({
    mutationFn: api.warmup,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['health'] })
      void queryClient.invalidateQueries({ queryKey: ['model-status'] })
    },
  })

  const health = healthQuery.data
  const model = modelQuery.data
  const checks = useMemo(() => Object.entries(model?.checks ?? {}), [model?.checks])
  const passedChecks = checks.filter(([, passed]) => passed).length
  const diagnosticsRunning = healthQuery.isFetching || modelQuery.isFetching
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
        provider={model?.runtime.provider ?? health?.provider ?? 'unknown'}
        threads={String(model?.runtime.num_threads ?? 'unknown')}
        ttsLoaded={Boolean(health?.tts_loaded)}
        asrLoaded={Boolean(health?.asr_loaded)}
        ttsLanguages={model?.runtime.tts_configured_languages ?? []}
        asrLanguages={model?.runtime.asr_configured_languages ?? []}
        asrWorkers={model?.runtime.asr_job_workers ?? 1}
        ttsWorkers={model?.runtime.tts_job_workers ?? 1}
        passedChecks={passedChecks}
        totalChecks={checks.length}
        checks={checks}
        diagnosticsRunning={diagnosticsRunning}
        warmupRunning={warmupMutation.isPending}
        warmupError={warmupMutation.error instanceof Error ? warmupMutation.error.message : null}
        onRunDiagnostics={() => {
          void healthQuery.refetch()
          void modelQuery.refetch()
        }}
        onWarmup={() => warmupMutation.mutate()}
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

function SystemDiagnosticsCard({
  backendOffline,
  runtimeReady,
  provider,
  threads,
  ttsLoaded,
  asrLoaded,
  ttsLanguages,
  asrLanguages,
  asrWorkers,
  ttsWorkers,
  passedChecks,
  totalChecks,
  checks,
  diagnosticsRunning,
  warmupRunning,
  warmupError,
  onRunDiagnostics,
  onWarmup,
}: {
  backendOffline: boolean
  runtimeReady: boolean
  provider: string
  threads: string
  ttsLoaded: boolean
  asrLoaded: boolean
  ttsLanguages: string[]
  asrLanguages: string[]
  asrWorkers: number
  ttsWorkers: number
  passedChecks: number
  totalChecks: number
  checks: Array<[string, boolean]>
  diagnosticsRunning: boolean
  warmupRunning: boolean
  warmupError: string | null
  onRunDiagnostics: () => void
  onWarmup: () => void
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
      </div>
      {warmupError ? (
        <div className="mt-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs font-medium leading-5 text-red-700">
          {warmupError}
        </div>
      ) : null}

      <SignalBars healthy={healthy} />

      <details className="group mt-3 rounded-md border border-slate-200 bg-white">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-2 text-xs font-medium text-slate-700">
          Advanced diagnostics
          <ChevronDown className="size-4 text-slate-500 transition-transform group-open:rotate-180" />
        </summary>
        <div className="border-t border-slate-200 p-3">
          <div className="grid grid-cols-2 gap-2 text-xs lg:grid-cols-5">
            <SignalMeta label="Provider" value={provider} />
            <SignalMeta label="Threads" value={threads} />
            <SignalMeta label="Workers" value={`ASR ${asrWorkers} / TTS ${ttsWorkers}`} />
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
              ? 'w-full rounded-t bg-gradient-to-t from-blue-600 via-sky-400 to-fuchsia-400'
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
          <CheckCircle2 className="size-4 shrink-0 text-blue-700" />
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
        <CheckCircle2 className="size-4 shrink-0 text-blue-700" />
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
