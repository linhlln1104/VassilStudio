import {
  AlertTriangle,
  AudioLines,
  Captions,
  CheckCircle2,
  CirclePower,
  Cpu,
  Download,
  ExternalLink,
  Gauge,
  Loader2,
  RefreshCw,
  Server,
  ShieldCheck,
  XCircle,
  type LucideIcon,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type {
  DiagnosticsResponse,
  HealthResponse,
  ModelStatusResponse,
  ProbeResponse,
} from '@/lib/api'
import { cn } from '@/lib/utils'

export type WarmupTarget =
  | { engine: 'all' }
  | { engine: 'asr' | 'tts'; language: string }

type RuntimeDiagnosticsProps = {
  health: HealthResponse | undefined
  liveness: ProbeResponse | undefined
  readiness: ProbeResponse | undefined
  model: ModelStatusResponse | undefined
  diagnostics: DiagnosticsResponse | undefined
  loading: boolean
  refreshing: boolean
  lastCheckedAt: number
  queryErrors: Array<{ source: string; message: string }>
  warmingTarget: WarmupTarget | null
  bundleRunning: boolean
  warmupError: string | null
  bundleError: string | null
  onRunDiagnostics: () => void
  onWarmup: (target: WarmupTarget) => void
  onDownloadBundle: () => void
}

export function RuntimeDiagnostics({
  health,
  liveness,
  readiness,
  model,
  diagnostics,
  loading,
  refreshing,
  lastCheckedAt,
  queryErrors,
  warmingTarget,
  bundleRunning,
  warmupError,
  bundleError,
  onRunDiagnostics,
  onWarmup,
  onDownloadBundle,
}: RuntimeDiagnosticsProps) {
  const runtime = model?.runtime ?? diagnostics?.runtime
  const readinessChecks = Object.entries(readiness?.checks ?? model?.checks ?? {})
  const failedChecks = readinessChecks.filter(([, passed]) => !passed)
  const passedChecks = readinessChecks.length - failedChecks.length
  const serviceOnline = health?.status === 'ok' && liveness?.status === 'ok'
  const workspaceReady = readiness?.status === 'ready'
  const modelAssetsReady = Boolean(model?.ready)
  const initialCheck = loading && !(health && liveness && readiness && model)
  const coreOffline = queryErrors.some((error) => error.source === 'Health' || error.source === 'Liveness')
  const overall = initialCheck
    ? { label: 'Checking', variant: 'muted' as const, headline: 'Checking local runtime' }
    : coreOffline || !serviceOnline
      ? { label: 'Offline', variant: 'danger' as const, headline: 'Local API is unavailable' }
      : workspaceReady && modelAssetsReady
        ? { label: 'Ready', variant: 'success' as const, headline: 'Runtime ready for local inference' }
        : { label: 'Needs attention', variant: 'warning' as const, headline: 'Runtime setup needs attention' }

  return (
    <div className="space-y-3">
      <section className="border-b border-slate-200 px-1 pb-4 pt-1">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={overall.variant}>{overall.label}</Badge>
              <span className="text-xs font-medium text-slate-500">
                {lastCheckedAt ? `Checked ${formatTimestamp(lastCheckedAt)}` : 'Awaiting first check'}
              </span>
            </div>
            <h2 className="mt-2 text-base font-semibold leading-6 text-slate-950">{overall.headline}</h2>
            <p className="mt-1 max-w-2xl text-xs leading-5 text-slate-600">
              {overall.label === 'Ready'
                ? 'Configured model assets and writable workspace paths passed readiness.'
                : overall.label === 'Offline'
                  ? 'Start the local API, then run diagnostics again.'
                  : overall.label === 'Checking'
                    ? 'Reading process, model, and workspace probes.'
                    : `${failedChecks.length || 'One or more'} readiness blockers require review.`}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" disabled={refreshing} onClick={onRunDiagnostics}>
              {refreshing ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
              {refreshing ? 'Checking' : 'Run diagnostics'}
            </Button>
            <Button
              variant="secondary"
              disabled={Boolean(warmingTarget) || coreOffline || initialCheck || !modelAssetsReady}
              title={modelAssetsReady ? 'Load every configured ASR and TTS language' : 'Resolve missing model assets first'}
              onClick={() => onWarmup({ engine: 'all' })}
            >
              {warmingTarget?.engine === 'all' ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <CirclePower className="size-4" />
              )}
              {warmingTarget?.engine === 'all' ? 'Warming' : 'Warm all models'}
            </Button>
            <Button
              variant="secondary"
              disabled={bundleRunning || coreOffline || initialCheck}
              onClick={onDownloadBundle}
            >
              {bundleRunning ? <Loader2 className="size-4 animate-spin" /> : <Download className="size-4" />}
              {bundleRunning ? 'Preparing' : 'Download bundle'}
            </Button>
          </div>
        </div>

        <div className="mt-3 grid gap-2 sm:grid-cols-3">
          <ProbeTile
            icon={Server}
            label="Local API"
            value={initialCheck ? 'Checking' : serviceOnline ? 'Online' : 'Offline'}
            detail={liveness?.status === 'ok' ? 'Process is live' : 'No liveness signal'}
            state={initialCheck ? 'neutral' : serviceOnline ? 'success' : 'danger'}
          />
          <ProbeTile
            icon={ShieldCheck}
            label="Workspace readiness"
            value={readiness?.status === 'ready' ? 'Ready' : readiness?.status === 'not_ready' ? 'Blocked' : 'Checking'}
            detail={readinessChecks.length ? `${passedChecks} of ${readinessChecks.length} checks passed` : 'Waiting for checks'}
            state={workspaceReady ? 'success' : readiness ? 'warning' : 'neutral'}
          />
          <ProbeTile
            icon={Cpu}
            label="Model assets"
            value={modelAssetsReady ? 'Complete' : model ? 'Incomplete' : 'Checking'}
            detail={runtime ? `${runtime.provider.toUpperCase()} / ASR ${runtime.asr_num_threads} / TTS ${runtime.tts_num_threads}` : 'Runtime metadata pending'}
            state={modelAssetsReady ? 'success' : model ? 'warning' : 'neutral'}
          />
        </div>
      </section>

      {queryErrors.length ? (
        <div className="rounded-md border border-red-200 bg-red-50 p-3" role="alert">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-red-700" />
            <div className="min-w-0">
              <div className="text-xs font-semibold text-red-900">Some diagnostics could not be refreshed</div>
              <div className="mt-1 space-y-1 text-xs leading-5 text-red-800">
                {queryErrors.map((error) => (
                  <div key={error.source}>
                    <span className="font-semibold">{error.source}:</span> {error.message}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {warmupError || bundleError ? (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs font-medium leading-5 text-red-800" role="alert">
          {warmupError || bundleError}
        </div>
      ) : null}

      <div className="grid gap-3 xl:grid-cols-2">
        <RuntimeEngine
          engine="asr"
          title="Speech recognition"
          runtimeName="ZipFormer ASR"
          icon={Captions}
          configuredLanguages={runtime?.asr_configured_languages ?? []}
          loadedLanguages={runtime?.asr_loaded_languages ?? []}
          assetChecks={model?.checks ?? {}}
          warmingTarget={warmingTarget}
          controlsDisabled={coreOffline || initialCheck}
          onWarmup={onWarmup}
        />
        <RuntimeEngine
          engine="tts"
          title="Voice synthesis"
          runtimeName="ZipVoice TTS"
          icon={AudioLines}
          configuredLanguages={runtime?.tts_configured_languages ?? []}
          loadedLanguages={runtime?.tts_loaded_languages ?? []}
          assetChecks={model?.checks ?? {}}
          warmingTarget={warmingTarget}
          controlsDisabled={coreOffline || initialCheck}
          onWarmup={onWarmup}
        />
      </div>

      <RuntimeConfiguration runtime={runtime} version={health?.version ?? diagnostics?.version ?? 'unknown'} />

      <Troubleshooting
        checks={readinessChecks}
        failedChecks={failedChecks}
        storage={diagnostics?.storage ?? []}
        readinessAvailable={Boolean(readiness)}
        bundleRunning={bundleRunning}
        onDownloadBundle={onDownloadBundle}
      />
    </div>
  )
}

function ProbeTile({
  icon: Icon,
  label,
  value,
  detail,
  state,
}: {
  icon: LucideIcon
  label: string
  value: string
  detail: string
  state: 'success' | 'warning' | 'danger' | 'neutral'
}) {
  const iconTone = {
    success: 'text-emerald-600',
    warning: 'text-amber-700',
    danger: 'text-red-700',
    neutral: 'text-slate-500',
  }[state]

  return (
    <div className="rounded-md border border-slate-200 bg-white p-3">
      <div className="flex items-start gap-2.5">
        <Icon className={cn('mt-0.5 size-4 shrink-0', iconTone)} />
        <div className="min-w-0">
          <div className="text-xs font-medium text-slate-500">{label}</div>
          <div className="mt-0.5 text-sm font-semibold leading-5 text-slate-950">{value}</div>
          <div className="mt-1 truncate text-xs text-slate-600" title={detail}>{detail}</div>
        </div>
      </div>
    </div>
  )
}

function RuntimeEngine({
  engine,
  title,
  runtimeName,
  icon: Icon,
  configuredLanguages,
  loadedLanguages,
  assetChecks,
  warmingTarget,
  controlsDisabled,
  onWarmup,
}: {
  engine: 'asr' | 'tts'
  title: string
  runtimeName: string
  icon: LucideIcon
  configuredLanguages: string[]
  loadedLanguages: string[]
  assetChecks: Record<string, boolean>
  warmingTarget: WarmupTarget | null
  controlsDisabled: boolean
  onWarmup: (target: WarmupTarget) => void
}) {
  const loaded = new Set(loadedLanguages.map((language) => language.toLowerCase()))
  const readyCount = configuredLanguages.filter((language) => loaded.has(language.toLowerCase())).length
  const blockedCount = configuredLanguages.filter((language) => !languageAssetsReady(engine, language, assetChecks)).length
  const complete = configuredLanguages.length > 0 && readyCount === configuredLanguages.length
  const stateLabel = blockedCount > 0 ? 'Assets missing' : complete ? 'Warm' : readyCount > 0 ? 'Partially warm' : 'Cold'

  return (
    <article className="rounded-md border border-slate-200 bg-white">
      <header className="flex items-start justify-between gap-3 border-b border-slate-200 p-3">
        <div className="flex min-w-0 items-start gap-2.5">
          <span className={cn('grid size-8 shrink-0 place-items-center rounded-md text-white', engine === 'asr' ? 'bg-slate-800' : 'bg-blue-600')}>
            <Icon className="size-4" />
          </span>
          <div className="min-w-0">
            <h3 className="text-sm font-semibold leading-5 text-slate-950">{title}</h3>
            <div className="mt-0.5 text-xs text-slate-600">{runtimeName}</div>
          </div>
        </div>
        <Badge variant={blockedCount > 0 ? 'danger' : complete ? 'success' : readyCount > 0 ? 'warning' : 'muted'}>{stateLabel}</Badge>
      </header>
      {configuredLanguages.length ? (
        <div className="divide-y divide-slate-100 px-3">
          {configuredLanguages.map((language) => {
            const languageLoaded = loaded.has(language.toLowerCase())
            const assetsReady = languageAssetsReady(engine, language, assetChecks)
            const target: WarmupTarget = { engine, language }
            const warming = warmupTargetKey(warmingTarget) === warmupTargetKey(target)
            return (
              <div key={language} className="flex min-h-12 items-center justify-between gap-3 py-2">
                <div className="flex min-w-0 items-center gap-2.5">
                  {languageLoaded ? (
                    <CheckCircle2 className="size-4 shrink-0 text-emerald-600" />
                  ) : !assetsReady ? (
                    <XCircle className="size-4 shrink-0 text-red-600" />
                  ) : (
                    <span className="size-2 shrink-0 rounded-full bg-slate-300" />
                  )}
                  <div className="min-w-0">
                    <div className="text-xs font-semibold text-slate-900">{languageName(language)}</div>
                    <div className="mt-0.5 text-xs text-slate-500">
                      {languageLoaded ? 'Loaded in memory' : assetsReady ? 'Available on disk' : 'Model assets incomplete'}
                    </div>
                  </div>
                </div>
                {languageLoaded ? (
                  <Badge variant="success">Loaded</Badge>
                ) : !assetsReady ? (
                  <Badge variant="danger">Blocked</Badge>
                ) : (
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={Boolean(warmingTarget) || controlsDisabled}
                    aria-label={`Warm ${languageName(language)} ${engine.toUpperCase()}`}
                    onClick={() => onWarmup(target)}
                  >
                    {warming ? <Loader2 className="size-4 animate-spin" /> : <CirclePower className="size-4" />}
                    {warming ? 'Warming' : 'Warm'}
                  </Button>
                )}
              </div>
            )
          })}
        </div>
      ) : (
        <div className="p-4 text-center text-xs leading-5 text-slate-600">No languages are configured.</div>
      )}
      <footer className="border-t border-slate-100 px-3 py-2 text-xs font-medium text-slate-500">
        {readyCount} of {configuredLanguages.length} languages loaded
        {blockedCount ? ` / ${blockedCount} blocked` : ''}
      </footer>
    </article>
  )
}

function RuntimeConfiguration({
  runtime,
  version,
}: {
  runtime: ModelStatusResponse['runtime'] | undefined
  version: string
}) {
  const values = [
    ['Version', version],
    ['Environment', runtime?.environment ?? 'unknown'],
    ['Provider', runtime?.provider.toUpperCase() ?? 'unknown'],
    ['Model threads', runtime ? `ASR ${runtime.asr_num_threads} / TTS ${runtime.tts_num_threads}` : 'unknown'],
    ['ASR queue', runtime ? `${runtime.asr_job_workers} workers / ${runtime.asr_job_max_attempts} attempts` : 'unknown'],
    ['TTS queue', runtime ? `${runtime.tts_job_workers} workers / ${runtime.tts_job_max_attempts} attempts` : 'unknown'],
    ['Retry backoff', runtime ? `${runtime.job_retry_backoff_seconds}s` : 'unknown'],
    ['Startup', runtime?.warmup_on_startup ? 'Warm on startup' : 'Cold start'],
    ['Logging', runtime ? `${runtime.log_level}${runtime.debug ? ' / debug' : ''}` : 'unknown'],
  ]

  return (
    <section className="border-y border-slate-200 py-4">
      <div className="flex items-center gap-2 px-1">
        <Gauge className="size-4 text-slate-500" />
        <h3 className="text-sm font-semibold text-slate-950">Runtime configuration</h3>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3 px-1 md:grid-cols-4">
        {values.map(([label, value]) => (
          <div key={label} className="min-w-0 border-l-2 border-slate-200 pl-2.5">
            <dt className="text-xs font-medium text-slate-500">{label}</dt>
            <dd className="mt-1 truncate text-xs font-semibold text-slate-900" title={value}>{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}

function Troubleshooting({
  checks,
  failedChecks,
  storage,
  readinessAvailable,
  bundleRunning,
  onDownloadBundle,
}: {
  checks: Array<[string, boolean]>
  failedChecks: Array<[string, boolean]>
  storage: DiagnosticsResponse['storage']
  readinessAvailable: boolean
  bundleRunning: boolean
  onDownloadBundle: () => void
}) {
  return (
    <section className="pb-1 pt-1">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            {failedChecks.length ? (
              <AlertTriangle className="size-4 text-amber-700" />
            ) : (
              <ShieldCheck className="size-4 text-emerald-600" />
            )}
            <h3 className="text-sm font-semibold text-slate-950">Troubleshooting</h3>
          </div>
          <p className="mt-1 text-xs leading-5 text-slate-600">
            {failedChecks.length
              ? `${failedChecks.length} blockers must pass before the workspace is ready.`
              : readinessAvailable
                ? 'No readiness blockers detected.'
                : 'Readiness results are not available yet.'}
          </p>
        </div>
        <div className="flex gap-2">
          <Button asChild size="sm" variant="secondary">
            <a href="/operations" target="_blank" rel="noreferrer">
              <ExternalLink className="size-4" />
              Operations guide
            </a>
          </Button>
          <Button size="sm" variant="secondary" disabled={bundleRunning} onClick={onDownloadBundle}>
            {bundleRunning ? <Loader2 className="size-4 animate-spin" /> : <Download className="size-4" />}
            Support bundle
          </Button>
        </div>
      </div>

      {failedChecks.length ? (
        <div className="mt-3 divide-y divide-amber-100 rounded-md border border-amber-200 bg-amber-50/60">
          {failedChecks.map(([name]) => {
            const issue = describeCheck(name, storage)
            return (
              <div key={name} className="flex items-start gap-3 p-3">
                <XCircle className="mt-0.5 size-4 shrink-0 text-amber-700" />
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-semibold text-amber-950">{issue.label}</div>
                  <div className="mt-1 text-xs leading-5 text-amber-900">{issue.remedy}</div>
                  {issue.path ? <code className="mt-1 block break-all text-xs text-amber-800">{issue.path}</code> : null}
                </div>
              </div>
            )
          })}
        </div>
      ) : null}

      <details className="group mt-3 rounded-md border border-slate-200 bg-white">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-2.5 text-xs font-semibold text-slate-700">
          Readiness checks
          <span className="text-xs font-medium text-slate-500">{checks.length ? `${checks.length - failedChecks.length}/${checks.length}` : 'Waiting'}</span>
        </summary>
        <div className="divide-y divide-slate-100 border-t border-slate-200 px-3">
          {checks.length ? checks.map(([name, passed]) => {
            const issue = describeCheck(name, storage)
            return (
              <div key={name} className="flex items-center justify-between gap-3 py-2">
                <div className="min-w-0">
                  <div className="truncate text-xs font-medium text-slate-800">{issue.label}</div>
                  <code className="mt-0.5 block truncate text-[11px] text-slate-500">{name}</code>
                </div>
                <Badge variant={passed ? 'success' : 'danger'}>{passed ? 'Passed' : 'Failed'}</Badge>
              </div>
            )
          }) : (
            <div className="py-4 text-center text-xs text-slate-600">Waiting for readiness data.</div>
          )}
        </div>
      </details>
    </section>
  )
}

function describeCheck(name: string, storage: DiagnosticsResponse['storage']) {
  if (name.startsWith('storage_')) {
    const storageName = name.slice('storage_'.length).replace(/_dir$/, '')
    const item = storage.find((candidate) => candidate.name === storageName)
    const label = `${storageLabel(storageName)} storage`
    const remedy = item?.exists
      ? 'Verify this location is writable by the VassilStudio process, then rerun diagnostics.'
      : 'Create the configured location, then rerun diagnostics.'
    return { label, remedy, path: item?.path ?? null }
  }

  const [engine, language, ...componentParts] = name.split('_')
  const component = componentParts.join('_')
  const label = `${languageName(language)} ${engine.toUpperCase()} ${componentLabel(component)}`
  return {
    label,
    remedy: 'Restore the configured model asset and verify its path in VASSIL_CONFIG, then rerun diagnostics.',
    path: null,
  }
}

function componentLabel(value: string) {
  const labels: Record<string, string> = {
    encoder: 'encoder',
    decoder: 'decoder',
    joiner: 'joiner',
    tokens: 'token file',
    vocoder: 'vocoder',
    lexicon: 'lexicon',
    data_dir: 'language data',
  }
  return labels[value] ?? value.replaceAll('_', ' ')
}

function storageLabel(value: string) {
  const labels: Record<string, string> = {
    data: 'Data root',
    voices: 'Voice profiles',
    asr_jobs: 'ASR jobs',
    tts_jobs: 'TTS jobs',
    uploads: 'Uploads',
    outputs: 'Outputs',
    logs: 'Logs',
  }
  if (labels[value]) {
    return labels[value]
  }
  return value
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function languageName(value: string) {
  const labels: Record<string, string> = { vi: 'Vietnamese', en: 'English' }
  return labels[value.toLowerCase()] ?? value.toUpperCase()
}

function warmupTargetKey(target: WarmupTarget | null) {
  if (!target) {
    return ''
  }
  return target.engine === 'all' ? 'all' : `${target.engine}:${target.language.toLowerCase()}`
}

function languageAssetsReady(engine: 'asr' | 'tts', language: string, checks: Record<string, boolean>) {
  const prefix = `${engine}_${language.toLowerCase()}_`
  const matchingChecks = Object.entries(checks).filter(([name]) => name.startsWith(prefix))
  return matchingChecks.length > 0 && matchingChecks.every(([, passed]) => passed)
}

function formatTimestamp(value: number) {
  return new Intl.DateTimeFormat(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(value))
}
