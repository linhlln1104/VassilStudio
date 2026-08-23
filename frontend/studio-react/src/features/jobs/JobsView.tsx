import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  Captions,
  CheckCircle2,
  Clock3,
  Eraser,
  FileAudio,
  Loader2,
  PanelRightOpen,
  RefreshCw,
  RotateCcw,
  Search,
  Trash2,
  X,
  XCircle,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { useToast } from '@/components/ui/use-toast'
import { api, fetchBlob, type JobStatus } from '@/lib/api'
import { compactId, formatDuration } from '@/lib/format'
import { jobRefetchInterval } from '@/lib/job-polling'
import { normalizeVoiceLanguage, voiceLanguageShortLabel } from '@/lib/language'
import { setPendingScript, setPreferredLanguage } from '@/lib/studio-preferences'
import { cn } from '@/lib/utils'
import { JobInspector, type StudioJob } from './JobInspector'

type JobFilter = 'all' | 'active' | 'succeeded' | 'failed' | 'cancelled'
type JobTypeFilter = 'all' | 'TTS' | 'ASR'

const statusFilters: Array<{ id: JobFilter; label: string }> = [
  { id: 'all', label: 'All' },
  { id: 'active', label: 'Active' },
  { id: 'succeeded', label: 'Done' },
  { id: 'failed', label: 'Failed' },
  { id: 'cancelled', label: 'Cancelled' },
]

const typeFilters: Array<{ id: JobTypeFilter; label: string }> = [
  { id: 'all', label: 'All types' },
  { id: 'TTS', label: 'TTS' },
  { id: 'ASR', label: 'ASR' },
]

export function JobsView() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const [filter, setFilter] = useState<JobFilter>('all')
  const [typeFilter, setTypeFilter] = useState<JobTypeFilter>('all')
  const [search, setSearch] = useState('')
  const [visibleLimit, setVisibleLimit] = useState(30)
  const [deleteTarget, setDeleteTarget] = useState<StudioJob | null>(null)
  const [selectedJobKey, setSelectedJobKey] = useState<string | null>(null)
  const [cleanupConfirmOpen, setCleanupConfirmOpen] = useState(false)
  const ttsJobsQuery = useQuery({
    queryKey: ['tts-jobs'],
    queryFn: api.ttsJobs,
    refetchInterval: (query) => jobRefetchInterval(query.state.data),
  })
  const asrJobsQuery = useQuery({
    queryKey: ['asr-jobs'],
    queryFn: api.asrJobs,
    refetchInterval: (query) => jobRefetchInterval(query.state.data),
  })

  const jobs = useMemo<StudioJob[]>(() => {
    const ttsJobs =
      ttsJobsQuery.data?.map((job) => ({
        id: job.job_id,
        type: 'TTS' as const,
        status: job.status,
        language: job.language,
        createdAt: job.created_at,
        startedAt: job.started_at,
        completedAt: job.completed_at,
        durationSeconds: job.duration_seconds,
        sampleRate: job.sample_rate,
        audioUrl: job.audio_url,
        attempt: job.attempt,
        maxAttempts: job.max_attempts,
        cancelRequested: job.cancel_requested,
        failedReason: job.failed_reason,
        summary: job.text,
        reusableText: job.text,
        error: job.error,
        voiceId: job.voice_id,
        numSteps: job.num_steps,
        speed: job.speed,
        filename: null,
      })) ?? []

    const asrJobs =
      asrJobsQuery.data?.map((job) => ({
        id: job.job_id,
        type: 'ASR' as const,
        status: job.status,
        language: job.language,
        createdAt: job.created_at,
        startedAt: job.started_at,
        completedAt: job.completed_at,
        durationSeconds: job.duration_seconds,
        sampleRate: job.sample_rate,
        audioUrl: job.audio_url,
        attempt: job.attempt,
        maxAttempts: job.max_attempts,
        cancelRequested: job.cancel_requested,
        failedReason: job.failed_reason,
        summary: job.text || job.filename,
        reusableText: job.text || '',
        error: job.error,
        voiceId: null,
        numSteps: null,
        speed: null,
        filename: job.filename,
      })) ?? []

    return [...ttsJobs, ...asrJobs].sort((a, b) => {
      const priorityDifference = jobPriority(a.status) - jobPriority(b.status)
      if (priorityDifference !== 0) {
        return priorityDifference
      }
      return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
    })
  }, [asrJobsQuery.data, ttsJobsQuery.data])

  const selectedJob = selectedJobKey
    ? jobs.find((job) => jobKey(job) === selectedJobKey) ?? null
    : null

  const activeCount = jobs.filter((job) => isActiveStatus(job.status)).length
  const failedCount = jobs.filter((job) => job.status === 'failed').length
  const succeededCount = jobs.filter((job) => job.status === 'succeeded').length
  const cancelledCount = jobs.filter((job) => job.status === 'cancelled').length
  const terminalJobs = jobs.filter((job) => isTerminalStatus(job.status))
  const normalizedSearch = search.trim().toLowerCase()
  const filteredJobs = jobs.filter((job) => {
    if (typeFilter !== 'all' && job.type !== typeFilter) {
      return false
    }
    if (filter === 'active' && !isActiveStatus(job.status)) {
      return false
    }
    if (filter !== 'all' && filter !== 'active' && job.status !== filter) {
      return false
    }
    if (!normalizedSearch) {
      return true
    }
    return [job.id, compactId(job.id), job.type, job.status, job.language, job.summary, job.error]
      .join(' ')
      .toLowerCase()
      .includes(normalizedSearch)
  })
  const visibleJobs = filteredJobs.slice(0, visibleLimit)
  const loading = ttsJobsQuery.isLoading || asrJobsQuery.isLoading
  const refreshing = ttsJobsQuery.isFetching || asrJobsQuery.isFetching
  const hasQueryError = ttsJobsQuery.isError || asrJobsQuery.isError

  useEffect(() => {
    setVisibleLimit(30)
  }, [filter, search, typeFilter])

  const deleteJobMutation = useMutation({
    mutationFn: (job: StudioJob) =>
      job.type === 'TTS' ? api.deleteTtsJob(job.id) : api.deleteAsrJob(job.id),
    onSuccess: (_, job) => {
      void queryClient.invalidateQueries({ queryKey: ['tts-jobs'] })
      void queryClient.invalidateQueries({ queryKey: ['asr-jobs'] })
      setDeleteTarget(null)
      toast({
        title: 'Job deleted',
        description: `${job.type} job ${compactId(job.id)} was removed from the queue.`,
        variant: 'success',
      })
    },
    onError: (error) => {
      toast({
        title: 'Delete failed',
        description: errorMessage(error, 'Unable to delete this job.'),
        variant: 'danger',
      })
    },
  })

  const cancelJobMutation = useMutation({
    mutationFn: async (job: StudioJob) => {
      if (job.type === 'TTS') {
        await api.cancelTtsJob(job.id)
      } else {
        await api.cancelAsrJob(job.id)
      }
    },
    onSuccess: (_, job) => {
      void queryClient.invalidateQueries({ queryKey: ['tts-jobs'] })
      void queryClient.invalidateQueries({ queryKey: ['asr-jobs'] })
      toast({
        title: 'Cancellation requested',
        description: `${job.type} job ${compactId(job.id)} will stop at the next safe point.`,
        variant: 'success',
      })
    },
    onError: (error) => {
      toast({
        title: 'Cancel failed',
        description: errorMessage(error, 'Unable to cancel this job.'),
        variant: 'danger',
      })
    },
  })

  const cleanupMutation = useMutation({
    mutationFn: async () => {
      const [tts, asr] = await Promise.all([api.cleanupTtsJobs(), api.cleanupAsrJobs()])
      return {
        deleted: tts.deleted + asr.deleted,
        jobIds: [...tts.job_ids, ...asr.job_ids],
      }
    },
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ['tts-jobs'] })
      void queryClient.invalidateQueries({ queryKey: ['asr-jobs'] })
      setCleanupConfirmOpen(false)
      toast({
        title: result.deleted > 0 ? 'Queue cleaned' : 'Queue already clean',
        description:
          result.deleted > 0
            ? `Removed ${result.deleted} terminal jobs.`
            : 'No terminal jobs were available to remove.',
        variant: 'success',
      })
    },
    onError: (error) => {
      toast({
        title: 'Cleanup failed',
        description: errorMessage(error, 'Unable to clean the queue.'),
        variant: 'danger',
      })
    },
  })

  const runAgainMutation = useMutation({
    mutationFn: async (job: StudioJob) => {
      if (job.type === 'TTS') {
        if (!job.voiceId || !job.reusableText.trim()) {
          throw new Error('The original voice profile or script is unavailable.')
        }
        return api.createTtsJobWithVoice(job.voiceId, {
          text: job.reusableText,
          language: job.language,
          numSteps: job.numSteps ?? undefined,
          speed: job.speed ?? undefined,
        })
      }

      if (!job.audioUrl) {
        throw new Error('The original input audio is unavailable.')
      }
      const blob = await fetchBlob(job.audioUrl)
      const source = new File([blob], job.filename || `${job.id}-input.wav`, {
        type: blob.type || 'audio/wav',
      })
      return api.createAsrJob(source, { language: job.language })
    },
    onSuccess: (createdJob, sourceJob) => {
      void queryClient.invalidateQueries({ queryKey: ['tts-jobs'] })
      void queryClient.invalidateQueries({ queryKey: ['asr-jobs'] })
      setSelectedJobKey(null)
      toast({
        title: 'New job queued',
        description: `${sourceJob.type} job ${compactId(createdJob.job_id)} was created from ${compactId(sourceJob.id)}.`,
        variant: 'success',
      })
    },
    onError: (error) => {
      toast({
        title: 'Run again failed',
        description: errorMessage(error, 'Unable to create a new job from this source.'),
        variant: 'danger',
      })
    },
  })

  const refetchJobs = () => {
    void ttsJobsQuery.refetch()
    void asrJobsQuery.refetch()
  }

  const reuseJob = (job: StudioJob) => {
    const script = job.reusableText.trim()
    if (!script) {
      toast({
        title: 'Nothing to reuse',
        description: 'This job does not contain script or transcript text.',
        variant: 'info',
      })
      return
    }

    setPendingScript(script)
    setPreferredLanguage(normalizeVoiceLanguage(job.language))
    toast({
      title: job.type === 'ASR' ? 'Transcript ready for Generate' : 'Script ready for Generate',
      description: `${compactId(job.id)} was copied into the Generate editor.`,
      variant: 'success',
    })
    window.location.hash = '/generate'
  }

  return (
    <div className="space-y-3">
      <header className="flex flex-col gap-3 px-1 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <div className="text-sm font-semibold leading-5 text-slate-950">Queue activity</div>
          <div className="mt-1 text-xs leading-5 text-slate-600">
            Active and failed jobs are prioritized for review.
          </div>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <Metric label="Active" value={activeCount} tone="warning" />
          <Metric label="Done" value={succeededCount} tone="success" />
          <Metric label="Failed" value={failedCount} tone="danger" />
          <Metric label="Cancelled" value={cancelledCount} tone="neutral" />
        </div>
      </header>

      <div className="space-y-2 rounded-md border border-slate-200 bg-white p-2">
        <div className="flex flex-col gap-2 sm:flex-row">
          <label className="flex h-9 min-w-0 flex-1 items-center gap-2 rounded-md border border-slate-200 bg-white px-2.5">
            <Search className="size-4 text-slate-500" />
            <span className="sr-only">Search jobs</span>
            <input
              className="min-w-0 flex-1 bg-transparent text-xs font-medium text-slate-900 outline-none placeholder:text-slate-500"
              value={search}
              placeholder="Search ID, text, language, or status"
              onChange={(event) => setSearch(event.target.value)}
            />
            {search ? (
              <button
                className="grid size-7 place-items-center rounded-md text-slate-500 hover:bg-slate-50 hover:text-slate-950"
                type="button"
                aria-label="Clear job search"
                onClick={() => setSearch('')}
              >
                <X className="size-4" />
              </button>
            ) : null}
          </label>
          <div className="flex shrink-0 gap-2">
            <Button
              className="w-9 px-0"
              variant="secondary"
              aria-label="Clean completed jobs"
              title="Clean completed jobs"
              disabled={terminalJobs.length === 0 || cleanupMutation.isPending}
              onClick={() => setCleanupConfirmOpen(true)}
            >
              {cleanupMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : <Eraser className="size-4" />}
            </Button>
            <Button
              className="w-9 px-0"
              variant="secondary"
              aria-label="Refresh jobs"
              title="Refresh jobs"
              onClick={refetchJobs}
            >
              {refreshing ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
            </Button>
          </div>
        </div>
        <div className="flex flex-col gap-2 lg:flex-row">
          <SegmentedControl
            equalWidth
            className="w-full lg:w-[220px]"
            options={typeFilters.map((item) => ({ value: item.id, label: item.label }))}
            value={typeFilter}
            onChange={setTypeFilter}
          />
          <SegmentedControl
            equalWidth
            className="w-full lg:flex-1"
            itemClassName="px-1 sm:px-2"
            options={statusFilters.map((item) => ({ value: item.id, label: item.label }))}
            value={filter}
            onChange={setFilter}
          />
        </div>
      </div>

      {hasQueryError && jobs.length > 0 ? (
        <ErrorBanner
          message={errorMessage(
            ttsJobsQuery.error ?? asrJobsQuery.error,
            'One queue could not be refreshed. Existing cached jobs are still shown.',
          )}
          onRetry={refetchJobs}
        />
      ) : null}

      <section>
        <div className="mb-3 flex items-start justify-between gap-3 px-1">
          <div>
            <div className="text-sm font-semibold text-slate-950">Jobs</div>
            <div className="mt-1 text-xs leading-5 text-slate-600">
              Showing {visibleJobs.length} of {filteredJobs.length} matching jobs.
            </div>
          </div>
          <Badge variant="muted">{jobs.length} total</Badge>
        </div>
        {loading ? (
          <div className="grid grid-cols-1 gap-2">
            {Array.from({ length: 4 }).map((_, index) => (
              <div key={index} className="h-24 animate-pulse rounded-md bg-slate-100" />
            ))}
          </div>
        ) : hasQueryError && jobs.length === 0 ? (
          <ErrorState
            title="Unable to load jobs"
            copy={errorMessage(ttsJobsQuery.error ?? asrJobsQuery.error, 'The queue could not be loaded.')}
            onRetry={refetchJobs}
          />
        ) : visibleJobs.length > 0 ? (
          <div className="space-y-2">
            {visibleJobs.map((job) => (
              <JobRow
                key={`${job.type}-${job.id}`}
                job={job}
                deleting={deleteJobMutation.isPending && deleteTarget?.id === job.id}
                cancelling={cancelJobMutation.isPending && cancelJobMutation.variables?.id === job.id}
                onCancel={() => cancelJobMutation.mutate(job)}
                onDelete={() => setDeleteTarget(job)}
                onInspect={() => setSelectedJobKey(jobKey(job))}
                onReuse={() => reuseJob(job)}
              />
            ))}
            {visibleJobs.length < filteredJobs.length ? (
              <div className="pt-1 text-center">
                <Button variant="secondary" onClick={() => setVisibleLimit((current) => current + 30)}>
                  Show more
                </Button>
              </div>
            ) : null}
          </div>
        ) : (
          <EmptyQueue hasJobs={jobs.length > 0} />
        )}
      </section>

      <JobInspector
        job={selectedJob}
        cancelling={cancelJobMutation.isPending && cancelJobMutation.variables?.id === selectedJob?.id}
        deleting={deleteJobMutation.isPending && deleteTarget?.id === selectedJob?.id}
        runningAgain={runAgainMutation.isPending && runAgainMutation.variables?.id === selectedJob?.id}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedJobKey(null)
          }
        }}
        onCancel={(job) => cancelJobMutation.mutate(job)}
        onDelete={(job) => {
          setSelectedJobKey(null)
          setDeleteTarget(job)
        }}
        onReuse={reuseJob}
        onRunAgain={(job) => runAgainMutation.mutate(job)}
      />

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title={deleteTarget ? `Delete ${deleteTarget.type} job?` : 'Delete job?'}
        description={
          deleteTarget
            ? `This removes job ${compactId(deleteTarget.id)} and its local files from the queue. Active jobs must be cancelled first.`
            : ''
        }
        confirmLabel="Delete job"
        busyLabel="Deleting"
        busy={deleteJobMutation.isPending}
        onOpenChange={(open) => {
          if (!open) {
            setDeleteTarget(null)
          }
        }}
        onConfirm={() => {
          if (deleteTarget) {
            deleteJobMutation.mutate(deleteTarget)
          }
        }}
      />

      <ConfirmDialog
        open={cleanupConfirmOpen}
        title="Clean completed jobs?"
        description={`This removes ${terminalJobs.length} completed, failed, or cancelled jobs from the local queue. Active jobs will stay untouched.`}
        confirmLabel="Clean queue"
        busyLabel="Cleaning"
        busy={cleanupMutation.isPending}
        onOpenChange={setCleanupConfirmOpen}
        onConfirm={() => cleanupMutation.mutate()}
      />
    </div>
  )
}

function JobRow({
  job,
  deleting,
  cancelling,
  onCancel,
  onDelete,
  onInspect,
  onReuse,
}: {
  job: StudioJob
  deleting: boolean
  cancelling: boolean
  onCancel: () => void
  onDelete: () => void
  onInspect: () => void
  onReuse: () => void
}) {
  const failed = job.status === 'failed'
  const terminal = isTerminalStatus(job.status)
  const canCancel = job.status === 'queued' || job.status === 'running'
  const canReuse = Boolean(job.reusableText.trim())

  return (
    <article
      className={cn(
        'grid grid-cols-1 gap-3 rounded-md border border-slate-200 bg-white p-3 transition-colors hover:border-sky-200 hover:bg-sky-50/20 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center',
        failed && 'bg-red-50/55',
      )}
    >
      <div className="flex min-w-0 items-start gap-3">
        <div
          className={cn(
            'grid size-9 shrink-0 place-items-center rounded-md text-white',
            job.type === 'TTS' ? 'bg-blue-600' : 'bg-slate-800',
          )}
        >
          {job.type === 'TTS' ? <FileAudio className="size-4" /> : <Captions className="size-4" />}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 flex-wrap items-center gap-1.5">
            <span className="truncate text-sm font-semibold leading-5 text-slate-950">{compactId(job.id)}</span>
            <Badge variant="muted">{job.type}</Badge>
            <Badge variant="muted">{voiceLanguageShortLabel(job.language)}</Badge>
            <StatusBadge status={job.status} />
          </div>
          <div className={cn('mt-1 line-clamp-2 text-sm leading-6', failed ? 'text-red-800' : 'text-slate-700')}>
            {job.error || job.summary || 'No summary'}
          </div>
          <div className="mt-1 text-xs font-medium leading-5 text-slate-500">
            Created {formatDate(job.createdAt)}
            {job.durationSeconds ? ` / ${formatDuration(job.durationSeconds)}` : ''}
            {job.maxAttempts > 1 ? ` / Attempt ${job.attempt}/${job.maxAttempts}` : ''}
            {job.failedReason ? ` / ${formatReason(job.failedReason)}` : ''}
          </div>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 lg:justify-end">
        <div className="flex flex-wrap gap-1.5">
          <Button
            size="sm"
            variant="secondary"
            className="w-8 px-0"
            onClick={onInspect}
            aria-label={`Inspect ${job.type} job ${compactId(job.id)}`}
            title="Job details"
          >
            <PanelRightOpen className="size-4" />
          </Button>
          {canCancel ? (
            <Button size="sm" variant="secondary" disabled={cancelling} onClick={onCancel}>
              {cancelling ? <Loader2 className="size-4 animate-spin" /> : <X className="size-4" />}
              Cancel
            </Button>
          ) : null}
          {canReuse ? (
            <Button size="sm" variant="secondary" onClick={onReuse}>
              <RotateCcw className="size-4" />
              Generate
            </Button>
          ) : null}
          {terminal ? (
            <Button
              size="sm"
              variant="secondary"
              disabled={deleting}
              className="w-8 border-red-200 px-0 text-red-700 hover:bg-red-50 hover:text-red-800"
              onClick={onDelete}
              aria-label="Delete job"
              title="Delete job"
            >
              {deleting ? <Loader2 className="size-4 animate-spin" /> : <Trash2 className="size-4" />}
              <span className="sr-only">Delete</span>
            </Button>
          ) : null}
        </div>
      </div>
    </article>
  )
}

function EmptyQueue({ hasJobs }: { hasJobs: boolean }) {
  const filtered = hasJobs

  return (
    <div className="rounded-md border border-dashed border-slate-300 bg-white p-4 text-center">
      <Clock3 className="mx-auto size-6 text-slate-500" />
      <div className="mt-2 text-sm font-semibold text-slate-950">
        {filtered ? 'No jobs match this filter' : 'No jobs yet'}
      </div>
      <p className="mx-auto mt-1 max-w-sm text-xs leading-5 text-slate-600">
        {filtered
          ? 'Switch filters to inspect another slice of the queue.'
          : 'Start with a voice render or a transcription upload. Jobs will appear here automatically.'}
      </p>
      {!filtered ? (
        <div className="mt-4 flex flex-col justify-center gap-2 sm:flex-row">
          <Button onClick={() => { window.location.hash = '/generate' }}>
            Generate audio
          </Button>
          <Button variant="secondary" onClick={() => { window.location.hash = '/transcribe' }}>
            Transcribe audio
          </Button>
        </div>
      ) : null}
    </div>
  )
}

function ErrorState({ title, copy, onRetry }: { title: string; copy: string; onRetry: () => void }) {
  return (
    <div className="rounded-md border border-red-200 bg-red-50 p-4 text-center">
      <AlertTriangle className="mx-auto size-6 text-red-600" />
      <div className="mt-2 text-sm font-semibold text-red-950">{title}</div>
      <p className="mx-auto mt-1 max-w-md text-xs leading-5 text-red-800">{copy}</p>
      <Button className="mt-4" variant="secondary" onClick={onRetry}>
        <RefreshCw className="size-4" />
        Retry
      </Button>
    </div>
  )
}

function ErrorBanner({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex flex-col gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 items-start gap-2">
        <AlertTriangle className="mt-0.5 size-4 shrink-0" />
        <span className="min-w-0 leading-6">{message}</span>
      </div>
      <Button size="sm" variant="secondary" onClick={onRetry}>
        <RefreshCw className="size-4" />
        Retry
      </Button>
    </div>
  )
}

function Metric({
  label,
  value,
  tone,
}: {
  label: string
  value: number
  tone: 'success' | 'warning' | 'danger' | 'neutral'
}) {
  const toneClass = {
    success: 'border-emerald-200 text-emerald-700',
    warning: 'border-amber-200 text-amber-700',
    danger: 'border-red-200 text-red-700',
    neutral: 'border-slate-200 text-slate-600',
  }[tone]

  return (
    <div className={`inline-flex h-6 items-center gap-1.5 rounded-md border bg-white px-2 text-xs font-medium ${toneClass}`}>
      <span className="font-semibold tabular-nums text-slate-950">{value}</span>
      <span>{label}</span>
    </div>
  )
}

function StatusBadge({ status }: { status: JobStatus }) {
  if (status === 'succeeded') {
    return (
      <Badge variant="success">
        <CheckCircle2 className="mr-1 size-3" />
        Succeeded
      </Badge>
    )
  }

  if (status === 'failed') {
    return (
      <Badge variant="danger">
        <XCircle className="mr-1 size-3" />
        Failed
      </Badge>
    )
  }

  if (status === 'cancelled') {
    return (
      <Badge variant="muted">
        <XCircle className="mr-1 size-3" />
        Cancelled
      </Badge>
    )
  }

  if (status === 'cancelling') {
    return (
      <Badge variant="warning">
        <Loader2 className="mr-1 size-3 animate-spin" />
        Cancelling
      </Badge>
    )
  }

  return (
    <Badge variant="warning">
      <Loader2 className="mr-1 size-3 animate-spin" />
      {status === 'queued' ? 'Queued' : 'Running'}
    </Badge>
  )
}

function jobPriority(status: JobStatus) {
  return {
    running: 0,
    queued: 1,
    cancelling: 2,
    failed: 3,
    succeeded: 4,
    cancelled: 5,
  }[status]
}

function isTerminalStatus(status: JobStatus) {
  return status === 'succeeded' || status === 'failed' || status === 'cancelled'
}

function isActiveStatus(status: JobStatus) {
  return status === 'queued' || status === 'running' || status === 'cancelling'
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error && error.message ? error.message : fallback
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function formatReason(value: string) {
  return value.replaceAll('_', ' ')
}

function jobKey(job: StudioJob) {
  return `${job.type}:${job.id}`
}
