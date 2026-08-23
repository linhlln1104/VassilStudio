import * as Dialog from '@radix-ui/react-dialog'
import {
  Captions,
  CheckCircle2,
  Clock3,
  Copy,
  FileAudio,
  FileText,
  Gauge,
  Hash,
  Languages,
  Loader2,
  RotateCcw,
  Trash2,
  Volume2,
  X,
  XCircle,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { AudioPlayer } from '@/components/ui/audio-player'
import { Button } from '@/components/ui/button'
import { useToast } from '@/components/ui/use-toast'
import type { JobProgressStage, JobStatus } from '@/lib/api'
import { formatDuration } from '@/lib/format'
import { jobProgressLabel, jobStatusLabel } from '@/lib/job-runtime'
import { voiceLanguageShortLabel } from '@/lib/language'
import { cn } from '@/lib/utils'

export type StudioJob = {
  id: string
  type: 'TTS' | 'ASR'
  status: JobStatus
  language: string
  createdAt: string
  startedAt: string | null
  completedAt: string | null
  durationSeconds: number | null
  sampleRate: number | null
  audioUrl: string | null
  audioFilename: string
  attempt: number
  maxAttempts: number
  cancelRequested: boolean
  cancellationMode: 'safe_point'
  failedReason: string | null
  progressStage: JobProgressStage
  stageStartedAt: string
  summary: string
  reusableText: string
  error: string | null
  voiceId: string | null
  numSteps: number | null
  speed: number | null
  filename: string | null
}

type JobInspectorProps = {
  job: StudioJob | null
  cancelling: boolean
  deleting: boolean
  runningAgain: boolean
  onOpenChange: (open: boolean) => void
  onCancel: (job: StudioJob) => void
  onDelete: (job: StudioJob) => void
  onReuse: (job: StudioJob) => void
  onRunAgain: (job: StudioJob) => void
  onReviewTranscript: (job: StudioJob) => void
}

export function JobInspector({
  job,
  cancelling,
  deleting,
  runningAgain,
  onOpenChange,
  onCancel,
  onDelete,
  onReuse,
  onRunAgain,
  onReviewTranscript,
}: JobInspectorProps) {
  const { toast } = useToast()

  if (!job) {
    return null
  }

  const terminal = isTerminalStatus(job.status)
  const canCancel = job.status === 'queued' || job.status === 'running'
  const canReuse = Boolean(job.reusableText.trim())
  const canRunAgain =
    terminal &&
    (job.type === 'TTS'
      ? Boolean(job.voiceId && job.reusableText.trim())
      : Boolean(job.audioUrl))
  const contentLabel = job.type === 'TTS' ? 'Script' : 'Transcript'

  const copyValue = async (value: string, label: string) => {
    try {
      await navigator.clipboard.writeText(value)
      toast({
        title: `${label} copied`,
        description: 'Ready to paste wherever you need it.',
        variant: 'success',
      })
    } catch {
      toast({
        title: 'Copy failed',
        description: `Unable to copy ${label.toLowerCase()} to the clipboard.`,
        variant: 'danger',
      })
    }
  }

  return (
    <Dialog.Root open onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-slate-950/30 backdrop-blur-[1px] data-[state=closed]:animate-out data-[state=open]:animate-in data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <Dialog.Content className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[36rem] flex-col overflow-hidden border-l border-slate-200 bg-white shadow-2xl outline-none data-[state=closed]:animate-out data-[state=open]:animate-in data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right data-[state=closed]:duration-200 data-[state=open]:duration-300">
          <header className="flex shrink-0 items-start justify-between gap-4 border-b border-slate-200 px-4 py-4 sm:px-5">
            <div className="min-w-0">
              <div className="mb-2 flex flex-wrap items-center gap-1.5">
                <Badge variant="muted">{job.type}</Badge>
                <InspectorStatusBadge status={job.status} />
                <Badge variant="muted">{voiceLanguageShortLabel(job.language)}</Badge>
              </div>
              <Dialog.Title className="text-base font-semibold leading-6 text-slate-950">
                Job details
              </Dialog.Title>
              <Dialog.Description className="mt-0.5 text-xs leading-5 text-slate-600">
                Inspect lifecycle, source metadata, and local output.
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <Button className="shrink-0" size="icon" variant="ghost" aria-label="Close job details" title="Close">
                <X className="size-4" />
              </Button>
            </Dialog.Close>
          </header>

          <div className="min-h-0 flex-1 overflow-y-auto">
            <InspectorSection title="Identity" icon={Hash}>
              <div className="flex min-w-0 items-start gap-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-2.5">
                <code className="min-w-0 flex-1 break-all text-xs font-medium leading-5 text-slate-800">{job.id}</code>
                <Button
                  className="size-8 shrink-0 px-0"
                  size="sm"
                  variant="secondary"
                  aria-label="Copy job ID"
                  title="Copy job ID"
                  onClick={() => void copyValue(job.id, 'Job ID')}
                >
                  <Copy className="size-4" />
                </Button>
              </div>
            </InspectorSection>

            <InspectorSection title="Lifecycle" icon={Clock3}>
              <div className="divide-y divide-slate-100">
                <LifecycleRow label="Created" value={formatTimestamp(job.createdAt)} complete />
                <LifecycleRow
                  label="Processing started"
                  value={job.startedAt ? formatTimestamp(job.startedAt) : 'Waiting in queue'}
                  complete={Boolean(job.startedAt)}
                  active={job.status === 'queued'}
                />
                <LifecycleRow
                  label="Current stage"
                  value={jobProgressLabel(job, job.type)}
                  complete={terminal && job.status !== 'failed'}
                  active={!terminal}
                  failed={job.status === 'failed'}
                />
                <LifecycleRow
                  label="Finished"
                  value={job.completedAt ? formatTimestamp(job.completedAt) : lifecycleProgressLabel(job.status)}
                  complete={Boolean(job.completedAt)}
                  active={job.status === 'running' || job.status === 'cancelling'}
                />
              </div>
              <div className="mt-2 text-xs font-medium text-slate-500">
                Elapsed {formatElapsed(job)}
                {job.maxAttempts > 1 ? ` / Attempt ${job.attempt} of ${job.maxAttempts}` : ''}
              </div>
              {job.status === 'cancelling' ? (
                <div className="mt-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-medium leading-5 text-amber-800">
                  Stop requested. The current stage will exit at its next safe point.
                </div>
              ) : null}
            </InspectorSection>

            <InspectorSection title="Runtime" icon={Gauge}>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3">
                <Metadata label="Language" value={voiceLanguageShortLabel(job.language)} icon={Languages} />
                <Metadata
                  label="Audio length"
                  value={job.durationSeconds === null ? 'Pending' : formatDuration(job.durationSeconds)}
                  icon={Clock3}
                />
                <Metadata
                  label="Sample rate"
                  value={job.sampleRate === null ? 'Pending' : `${job.sampleRate.toLocaleString()} Hz`}
                  icon={Volume2}
                />
                {job.type === 'TTS' ? (
                  <>
                    <Metadata label="Voice profile" value={job.voiceId || 'Unavailable'} icon={FileAudio} />
                    <Metadata label="Render steps" value={job.numSteps === null ? 'Default' : String(job.numSteps)} icon={Gauge} />
                    <Metadata label="Speed" value={job.speed === null ? 'Default' : `${job.speed.toFixed(2)}x`} icon={Clock3} />
                  </>
                ) : (
                  <Metadata label="Source file" value={job.filename || 'Unavailable'} icon={FileAudio} className="col-span-2 sm:col-span-3" />
                )}
              </dl>
            </InspectorSection>

            {job.error || job.failedReason ? (
              <InspectorSection title="Failure details" icon={XCircle} tone="danger">
                <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm leading-6 text-red-900">
                  {job.error || 'This job did not complete.'}
                </div>
                {job.failedReason ? (
                  <div className="mt-2 text-xs font-medium text-red-700">
                    Reason: {job.failedReason.replaceAll('_', ' ')}
                  </div>
                ) : null}
              </InspectorSection>
            ) : null}

            <InspectorSection title={contentLabel} icon={FileText}>
              {job.reusableText.trim() ? (
                <div className="relative rounded-md border border-slate-200 bg-slate-50 p-3 pr-12">
                  <p className="whitespace-pre-wrap break-words text-sm leading-6 text-slate-800">{job.reusableText}</p>
                  <Button
                    className="absolute right-2 top-2 size-8 px-0"
                    size="sm"
                    variant="secondary"
                    aria-label={`Copy ${contentLabel.toLowerCase()}`}
                    title={`Copy ${contentLabel.toLowerCase()}`}
                    onClick={() => void copyValue(job.reusableText, contentLabel)}
                  >
                    <Copy className="size-4" />
                  </Button>
                </div>
              ) : (
                <div className="rounded-md border border-dashed border-slate-300 px-3 py-5 text-center text-xs leading-5 text-slate-600">
                  {job.type === 'ASR' ? 'No transcript was produced.' : 'The source script is unavailable.'}
                </div>
              )}
            </InspectorSection>

            {job.audioUrl ? (
              <InspectorSection title={job.type === 'TTS' ? 'Output audio' : 'Input audio'} icon={Volume2}>
                <AudioPlayer
                  src={job.audioUrl}
                  label={`${job.type} job ${job.id} audio`}
                  downloadName={job.audioFilename}
                />
              </InspectorSection>
            ) : null}
          </div>

          <footer className="shrink-0 border-t border-slate-200 bg-white px-4 py-3 sm:px-5">
            <div className="flex flex-wrap items-center justify-end gap-2">
              {terminal ? (
                <Button
                  className="mr-auto w-8 border-red-200 px-0 text-red-700 hover:bg-red-50 hover:text-red-800"
                  size="sm"
                  variant="secondary"
                  disabled={deleting}
                  aria-label="Delete job"
                  title="Delete job"
                  onClick={() => onDelete(job)}
                >
                  {deleting ? <Loader2 className="size-4 animate-spin" /> : <Trash2 className="size-4" />}
                  <span className="sr-only">Delete job</span>
                </Button>
              ) : null}
              {canCancel ? (
                <Button size="sm" variant="secondary" disabled={cancelling} onClick={() => onCancel(job)}>
                  {cancelling ? <Loader2 className="size-4 animate-spin" /> : <X className="size-4" />}
                  Cancel
                </Button>
              ) : null}
              {canReuse ? (
                <Button size="sm" variant="secondary" onClick={() => onReuse(job)}>
                  <FileText className="size-4" />
                  Use in Generate
                </Button>
              ) : null}
              {job.type === 'ASR' && job.status === 'succeeded' && canReuse ? (
                <Button size="sm" variant="secondary" onClick={() => onReviewTranscript(job)}>
                  <Captions className="size-4" />
                  Review transcript
                </Button>
              ) : null}
              {terminal ? (
                <Button
                  size="sm"
                  disabled={!canRunAgain || runningAgain}
                  title={canRunAgain ? 'Create a new job from this source' : 'Original source is unavailable'}
                  onClick={() => onRunAgain(job)}
                >
                  {runningAgain ? <Loader2 className="size-4 animate-spin" /> : <RotateCcw className="size-4" />}
                  Run again
                </Button>
              ) : null}
            </div>
          </footer>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

function InspectorSection({
  title,
  icon: Icon,
  tone = 'neutral',
  children,
}: {
  title: string
  icon: typeof Clock3
  tone?: 'neutral' | 'danger'
  children: React.ReactNode
}) {
  return (
    <section className="border-b border-slate-200 px-4 py-4 sm:px-5">
      <div className={cn('mb-3 flex items-center gap-2 text-xs font-semibold uppercase text-slate-600', tone === 'danger' && 'text-red-700')}>
        <Icon className="size-4" />
        <h3>{title}</h3>
      </div>
      {children}
    </section>
  )
}

function LifecycleRow({
  label,
  value,
  complete = false,
  active = false,
  failed = false,
}: {
  label: string
  value: string
  complete?: boolean
  active?: boolean
  failed?: boolean
}) {
  return (
    <div className="flex items-start gap-3 py-2 first:pt-0 last:pb-0">
      <div className="mt-0.5 grid size-5 shrink-0 place-items-center">
        {failed ? (
          <XCircle className="size-4 text-red-600" />
        ) : complete ? (
          <CheckCircle2 className="size-4 text-emerald-600" />
        ) : active ? (
          <Loader2 className="size-4 animate-spin text-amber-600" />
        ) : (
          <span className="size-2 rounded-full bg-slate-300" />
        )}
      </div>
      <div className="min-w-0 flex-1 sm:flex sm:items-baseline sm:justify-between sm:gap-4">
        <div className={cn('text-xs font-medium leading-5 text-slate-700', failed && 'text-red-800')}>{label}</div>
        <div className={cn('text-xs leading-5 text-slate-500 sm:text-right', failed && 'text-red-700')}>{value}</div>
      </div>
    </div>
  )
}

function Metadata({
  label,
  value,
  icon: Icon,
  className,
}: {
  label: string
  value: string
  icon: typeof Clock3
  className?: string
}) {
  return (
    <div className={cn('min-w-0', className)}>
      <dt className="flex items-center gap-1.5 text-xs font-medium text-slate-500">
        <Icon className="size-3.5 shrink-0" />
        {label}
      </dt>
      <dd className="mt-1 truncate text-xs font-semibold text-slate-900" title={value}>
        {value}
      </dd>
    </div>
  )
}

function InspectorStatusBadge({ status }: { status: JobStatus }) {
  const label = jobStatusLabel(status)
  const variant = status === 'succeeded' ? 'success' : status === 'failed' ? 'danger' : status === 'cancelled' ? 'muted' : 'warning'

  return (
    <Badge variant={variant}>
      {status === 'succeeded' ? <CheckCircle2 className="mr-1 size-3" /> : null}
      {status === 'failed' || status === 'cancelled' ? <XCircle className="mr-1 size-3" /> : null}
      {status === 'queued' || status === 'running' || status === 'cancelling' ? <Loader2 className="mr-1 size-3 animate-spin" /> : null}
      {label}
    </Badge>
  )
}

function lifecycleProgressLabel(status: JobStatus) {
  if (status === 'queued') {
    return 'Waiting to start'
  }
  if (status === 'running') {
    return 'Processing now'
  }
  if (status === 'cancelling') {
    return 'Stopping at safe point'
  }
  return 'Timestamp unavailable'
}

function formatElapsed(job: StudioJob) {
  const start = new Date(job.startedAt || job.createdAt).getTime()
  const end = job.completedAt ? new Date(job.completedAt).getTime() : Date.now()
  const seconds = Math.max(0, Math.round((end - start) / 1000))
  return formatDuration(seconds)
}

function formatTimestamp(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(value))
}

function isTerminalStatus(status: JobStatus) {
  return status === 'succeeded' || status === 'failed' || status === 'cancelled'
}
