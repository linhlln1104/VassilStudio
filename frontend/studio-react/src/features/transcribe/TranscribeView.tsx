import { useRef, useState, type ChangeEvent, type DragEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowRight,
  Check,
  Copy,
  Download,
  FileAudio,
  Languages,
  Loader2,
  Mic2,
  X,
  XCircle,
  UploadCloud,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { QueryErrorState } from '@/components/ui/query-error'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { useToast } from '@/components/ui/use-toast'
import { api, type AsrJob } from '@/lib/api'
import { compactId, formatBytes, formatDuration } from '@/lib/format'
import {
  VOICE_LANGUAGES,
  normalizeVoiceLanguage,
  type VoiceLanguage,
  voiceLanguageLabel,
  voiceLanguageShortLabel,
} from '@/lib/language'
import { queryErrorMessage } from '@/lib/query-error'
import { getPreferredLanguage, setPendingScript, setPreferredLanguage } from '@/lib/studio-preferences'
import { cn } from '@/lib/utils'

const ASR_AUDIO_EXTENSIONS = new Set(['wav', 'mp3', 'webm', 'weba', 'flac', 'm4a', 'ogg', 'opus'])

export function TranscribeView() {
  const uploadInputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [fileError, setFileError] = useState('')
  const [selectedLanguage, setSelectedLanguage] = useState<VoiceLanguage>(() =>
    normalizeVoiceLanguage(getPreferredLanguage()),
  )
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const asrJobsQuery = useQuery({
    queryKey: ['asr-jobs'],
    queryFn: api.asrJobs,
    refetchInterval: 8000,
  })
  const modelStatusQuery = useQuery({
    queryKey: ['model-status'],
    queryFn: api.modelStatus,
    staleTime: 30000,
    refetchInterval: 30000,
  })
  const uploadMutation = useMutation({
    mutationFn: ({ file, language }: { file: File; language: VoiceLanguage }) =>
      api.createAsrJob(file, { language }),
    onSuccess: (job) => {
      void queryClient.invalidateQueries({ queryKey: ['asr-jobs'] })
      setSelectedFile(null)
      setFileError('')
      toast({
        title: 'Transcription queued',
        description: `${job.filename} is queued as ${compactId(job.job_id)}.`,
        variant: 'success',
      })
    },
  })
  const cancelJobMutation = useMutation({
    mutationFn: api.cancelAsrJob,
    onSuccess: (job) => {
      void queryClient.invalidateQueries({ queryKey: ['asr-jobs'] })
      toast({
        title: 'Cancellation requested',
        description: `${compactId(job.job_id)} will stop at the next safe point.`,
        variant: 'success',
      })
    },
    onError: (error) => {
      toast({
        title: 'Cancel failed',
        description: error instanceof Error ? error.message : 'Unable to cancel this transcription.',
        variant: 'danger',
      })
    },
  })

  const jobs = asrJobsQuery.data ?? []
  const latestTranscript = jobs.find((job) => job.text)
  const activeAsrCount = jobs.filter((job) => ['queued', 'running', 'cancelling'].includes(job.status)).length
  const latestFailedJob = jobs.find((job) => job.status === 'failed') ?? null
  const jobsError = asrJobsQuery.isError
    ? queryErrorMessage(asrJobsQuery.error, 'Unable to load ASR jobs.')
    : null
  const runtimeLanguageWarning = getRuntimeLanguageWarning(
    selectedLanguage,
    modelStatusQuery.data?.runtime.asr_configured_languages,
  )
  const modelReadinessMessage = getModelReadinessMessage({
    selectedLanguage,
    configuredLanguages: modelStatusQuery.data?.runtime.asr_configured_languages,
    loadedLanguages: modelStatusQuery.data?.runtime.asr_loaded_languages,
    statusError: modelStatusQuery.error,
  })

  const stageAudioFile = (file: File | undefined) => {
    if (uploadMutation.isPending) {
      return
    }
    uploadMutation.reset()
    if (!file) {
      setSelectedFile(null)
      setFileError('')
      return
    }

    const extension = file.name.split('.').pop()?.toLowerCase() ?? ''
    if (file.size <= 0) {
      setSelectedFile(null)
      setFileError('Choose a non-empty audio file.')
      return
    }
    if (!ASR_AUDIO_EXTENSIONS.has(extension)) {
      setSelectedFile(null)
      setFileError('Choose WAV, MP3, WEBM, WEBA, FLAC, M4A, OGG, or OPUS audio.')
      return
    }

    setSelectedFile(file)
    setFileError('')
  }

  const queueSelectedFile = () => {
    if (!selectedFile || runtimeLanguageWarning) {
      return
    }
    uploadMutation.mutate({ file: selectedFile, language: selectedLanguage })
  }

  const handleLanguageSelect = (language: VoiceLanguage) => {
    setSelectedLanguage(language)
    setPreferredLanguage(language)
  }

  const handleAudioUpload = (event: ChangeEvent<HTMLInputElement>) => {
    stageAudioFile(event.target.files?.[0])
    event.target.value = ''
  }

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setDragging(false)
    stageAudioFile(event.dataTransfer.files?.[0])
  }

  return (
    <div className="grid min-w-0 grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1fr)_380px]">
      <section className="space-y-3">
        <Card>
          <CardHeader>
            <div>
              <div className="text-sm font-semibold text-slate-950">Upload audio</div>
              <div className="mt-1 text-xs text-slate-600">
                Queue a {voiceLanguageLabel(selectedLanguage)} ASR job from a local recording.
              </div>
            </div>
            <UploadCloud className="size-5 text-slate-500" />
          </CardHeader>
          <CardContent>
            <LanguagePicker
              value={selectedLanguage}
              configuredLanguages={modelStatusQuery.data?.runtime.asr_configured_languages}
              onChange={handleLanguageSelect}
            />
            {runtimeLanguageWarning ? (
              <div className="mb-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs font-medium leading-5 text-red-700">
                {runtimeLanguageWarning}
              </div>
            ) : null}
            {modelReadinessMessage ? (
              <div className="mb-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-medium leading-5 text-amber-800">
                {modelReadinessMessage}
              </div>
            ) : null}
            {uploadMutation.isSuccess ? (
              <div className="mb-3 flex items-start gap-2 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-semibold leading-5 text-emerald-800">
                <Check className="mt-0.5 size-4 shrink-0" />
                <span>{uploadMutation.data.filename} was added to the ASR queue.</span>
              </div>
            ) : null}
            <div
              className={cn(
                'rounded-md border border-dashed p-3 transition-colors',
                dragging
                  ? 'border-blue-400 bg-sky-50'
                  : 'border-slate-300 bg-white',
              )}
              onDragEnter={(event) => {
                event.preventDefault()
                setDragging(true)
              }}
              onDragOver={(event) => {
                event.preventDefault()
                setDragging(true)
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={handleDrop}
            >
              {selectedFile ? (
                <div className="flex min-w-0 items-center gap-3 text-left">
                  <div className="grid size-10 shrink-0 place-items-center rounded-md bg-sky-50 text-blue-700">
                    <FileAudio className="size-5" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-semibold text-slate-950">{selectedFile.name}</div>
                    <div className="mt-1 text-xs font-medium text-slate-600">
                      {formatBytes(selectedFile.size)} / {voiceLanguageShortLabel(selectedLanguage)}
                    </div>
                  </div>
                  <Button
                    className="w-8 shrink-0 px-0"
                    size="sm"
                    variant="ghost"
                    aria-label="Remove selected audio"
                    title="Remove selected audio"
                    onClick={() => stageAudioFile(undefined)}
                  >
                    <X className="size-4" />
                  </Button>
                </div>
              ) : (
                <div className="py-2 text-center">
                  <div className="mx-auto grid size-10 place-items-center rounded-md bg-sky-50 text-blue-700">
                    <UploadCloud className="size-5" />
                  </div>
                  <div className="mt-3 text-sm font-semibold text-slate-950">
                    {dragging ? 'Release to select audio' : 'Drop audio here'}
                  </div>
                  <p className="mt-1 text-xs leading-5 text-slate-600">WAV, MP3, WEBM, WEBA, FLAC, M4A, OGG, or OPUS</p>
                </div>
              )}
              <input
                ref={uploadInputRef}
                className="hidden"
                type="file"
                accept="audio/*,.weba,.webm,.wav,.mp3,.m4a,.flac,.ogg,.opus"
                onChange={handleAudioUpload}
              />
            </div>
            {fileError || uploadMutation.isError ? (
              <div
                className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold leading-5 text-red-700"
                role="alert"
              >
                {fileError ||
                  (uploadMutation.error instanceof Error
                    ? uploadMutation.error.message
                    : 'Unable to queue ASR job.')}
              </div>
            ) : null}
            <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <Button
                className="w-full sm:w-auto"
                variant="secondary"
                disabled={uploadMutation.isPending}
                onClick={() => uploadInputRef.current?.click()}
              >
                <FileAudio className="size-4" />
                {selectedFile ? 'Replace audio' : 'Choose audio'}
              </Button>
              <Button
                className="w-full sm:w-auto"
                disabled={!selectedFile || uploadMutation.isPending || Boolean(runtimeLanguageWarning)}
                onClick={queueSelectedFile}
              >
                {uploadMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : <UploadCloud className="size-4" />}
                {uploadMutation.isPending ? 'Queueing' : 'Queue transcription'}
              </Button>
            </div>
          </CardContent>
        </Card>

        <div className="xl:hidden">
          <TranscriptPreview job={latestTranscript} />
        </div>

        <section>
          <div className="mb-3 flex items-start justify-between gap-3 px-1">
            <div>
              <div className="text-sm font-semibold text-slate-950">Recent transcripts</div>
              <div className="mt-1 text-xs text-slate-600">ASR results and queued recordings.</div>
            </div>
            <Button
              className="shrink-0"
              size="sm"
              variant="secondary"
              onClick={() => { window.location.hash = '/jobs' }}
            >
              View all
              <ArrowRight className="size-4" />
            </Button>
          </div>
          {jobsError ? (
              <QueryErrorState
                title="Unable to load transcripts"
                message={jobsError}
                onRetry={() => {
                  void asrJobsQuery.refetch()
                }}
              />
            ) : asrJobsQuery.isLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 3 }).map((_, index) => (
                  <div key={index} className="h-24 animate-pulse rounded-md bg-slate-100" />
                ))}
              </div>
            ) : jobs.length > 0 ? (
              <div className="space-y-2">
                {jobs.slice(0, 5).map((job) => (
                  <article key={job.job_id} className="rounded-md border border-slate-200 bg-white p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="min-w-0">
                        <div className="truncate text-sm font-semibold text-slate-950">{job.filename}</div>
                        <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-slate-600">
                          <span>{job.duration_seconds ? formatDuration(job.duration_seconds) : 'Duration pending'}</span>
                          <Badge variant="muted">{voiceLanguageShortLabel(job.language)}</Badge>
                        </div>
                      </div>
                      <JobStatusBadge job={job} />
                    </div>
                    <p className="mt-2 line-clamp-3 text-xs leading-5 text-slate-600">
                      {job.text || job.error || 'Transcript pending.'}
                    </p>
                    <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                      <span className="text-xs font-medium text-slate-500">
                        {job.max_attempts > 1 ? `Attempt ${job.attempt}/${job.max_attempts}` : 'ASR queue'}
                      </span>
                      <div className="flex flex-wrap gap-2">
                        {job.text ? (
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => sendTranscriptToGenerate(job)}
                          >
                            Generate
                            <ArrowRight className="size-4" />
                          </Button>
                        ) : null}
                        {canCancelJob(job) ? (
                          <Button
                            size="sm"
                            variant="secondary"
                            disabled={cancelJobMutation.isPending}
                            onClick={() => cancelJobMutation.mutate(job.job_id)}
                          >
                            {cancelJobMutation.isPending && cancelJobMutation.variables === job.job_id ? (
                              <Loader2 className="size-4 animate-spin" />
                            ) : (
                              <X className="size-4" />
                            )}
                            Cancel
                          </Button>
                        ) : null}
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <div className="rounded-md border border-dashed border-slate-300 bg-white p-4 text-center">
                <Mic2 className="mx-auto size-6 text-slate-400" />
                <div className="mt-2 text-sm font-semibold text-slate-900">No ASR jobs yet</div>
                <p className="mx-auto mt-1 max-w-sm text-xs leading-5 text-slate-600">
                  Upload a clip to see timestamps, transcripts, and review status here.
                </p>
              </div>
            )}
        </section>
      </section>

      <aside className="hidden space-y-3 xl:block">
        <QueueHealthPanel activeCount={activeAsrCount} latestFailedJob={latestFailedJob} />
        <TranscriptPreview job={latestTranscript} />
      </aside>
    </div>
  )
}

function QueueHealthPanel({
  activeCount,
  latestFailedJob,
}: {
  activeCount: number
  latestFailedJob: AsrJob | null
}) {
  if (activeCount === 0 && !latestFailedJob) {
    return null
  }

  return (
    <Card>
      <CardHeader>
        <div>
          <div className="text-sm font-semibold text-slate-950">Queue state</div>
          <div className="mt-1 text-xs text-slate-600">Current ASR workload.</div>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {activeCount > 0 ? (
          <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-800">
            {activeCount} transcription {activeCount === 1 ? 'job is' : 'jobs are'} active.
          </div>
        ) : null}
        {latestFailedJob ? (
          <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold leading-5 text-red-700">
            Latest failed job: {latestFailedJob.error ?? 'Transcription failed.'}
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}

function JobStatusBadge({ job }: { job: AsrJob }) {
  if (job.status === 'succeeded') {
    return <Badge variant="success">Succeeded</Badge>
  }

  if (job.status === 'failed') {
    return (
      <Badge variant="danger">
        <XCircle className="mr-1 size-3" />
        Failed
      </Badge>
    )
  }

  if (job.status === 'cancelled') {
    return <Badge variant="muted">Cancelled</Badge>
  }

  return (
    <Badge variant="warning">
      <Loader2 className="mr-1 size-3 animate-spin" />
      {job.status === 'cancelling' ? 'Cancelling' : job.status === 'queued' ? 'Queued' : 'Running'}
    </Badge>
  )
}

function canCancelJob(job: AsrJob) {
  return job.status === 'queued' || job.status === 'running'
}

function sendTranscriptToGenerate(job: AsrJob) {
  if (!job.text?.trim()) {
    return
  }
  setPendingScript(job.text)
  setPreferredLanguage(normalizeVoiceLanguage(job.language))
  window.location.hash = '/generate'
}

function LanguagePicker({
  value,
  configuredLanguages,
  onChange,
}: {
  value: VoiceLanguage
  configuredLanguages: string[] | undefined
  onChange: (language: VoiceLanguage) => void
}) {
  const configured = new Set((configuredLanguages ?? []).map((language) => normalizeVoiceLanguage(language)))

  return (
    <div className="mb-3 flex flex-col gap-2 rounded-md border border-slate-200 bg-white p-2.5 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-center gap-2 text-xs font-semibold text-slate-700">
        <Languages className="size-4 text-slate-500" />
        Recognition language
      </div>
      <SegmentedControl
        equalWidth
        className="w-full sm:w-[320px]"
        options={VOICE_LANGUAGES.map((item) => {
          const unavailable = configured.size > 0 && !configured.has(item.value)
          return {
            value: item.value,
            label: item.label,
            title: unavailable ? `${item.label} ASR is not configured` : item.helper,
          }
        })}
        value={value}
        onChange={onChange}
      />
    </div>
  )
}

function TranscriptPreview({ job }: { job: AsrJob | undefined }) {
  const [copied, setCopied] = useState(false)
  const { toast } = useToast()
  const text = job?.text ?? ''
  const hasText = Boolean(text.trim())
  const downloadHref = hasText ? `data:text/plain;charset=utf-8,${encodeURIComponent(text)}` : undefined

  const handleCopy = async () => {
    if (!hasText || typeof navigator === 'undefined') {
      return
    }
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1800)
    } catch {
      toast({
        title: 'Copy failed',
        description: 'Clipboard access is unavailable. Download the transcript instead.',
        variant: 'danger',
      })
    }
  }

  return (
    <Card>
      <CardHeader className="flex-wrap">
        <div>
          <div className="text-sm font-semibold text-slate-950">Transcript preview</div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-slate-600">
            <span>{job?.filename ?? 'Latest successful recognition output'}</span>
            {job ? <Badge variant="muted">{voiceLanguageShortLabel(job.language)}</Badge> : null}
            {job?.duration_seconds ? <span>{formatDuration(job.duration_seconds)}</span> : null}
          </div>
        </div>
        {hasText ? (
          <div className="flex gap-2">
            <Button
              className="w-8 px-0"
              size="sm"
              variant="secondary"
              aria-label={copied ? 'Transcript copied' : 'Copy transcript'}
              title={copied ? 'Copied' : 'Copy transcript'}
              onClick={() => { void handleCopy() }}
            >
              {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
            </Button>
            <Button
              className="w-8 px-0"
              size="sm"
              variant="secondary"
              asChild
              aria-label="Download transcript"
              title="Download transcript"
            >
              <a href={downloadHref} download={`vassil-transcript-${normalizeVoiceLanguage(job?.language)}.txt`}>
                <Download className="size-4" />
              </a>
            </Button>
          </div>
        ) : null}
      </CardHeader>
      <CardContent>
        {hasText ? (
          <>
            <div className="min-h-[240px] whitespace-pre-wrap rounded-md border border-slate-200 bg-white p-3 text-xs leading-6 text-slate-800 xl:min-h-[300px]">
              {text}
            </div>
            <Button className="mt-3 w-full" onClick={() => { if (job) sendTranscriptToGenerate(job) }}>
              <Languages className="size-4" />
              Use as Generate script
              <ArrowRight className="size-4" />
            </Button>
          </>
        ) : (
          <div className="grid min-h-[240px] place-items-center rounded-md border border-dashed border-slate-300 bg-white p-4 text-center xl:min-h-[300px]">
            <div>
              <Mic2 className="mx-auto size-6 text-slate-400" />
              <div className="mt-2 text-sm font-semibold text-slate-950">No transcript output</div>
              <p className="mt-1 text-xs leading-5 text-slate-600">Completed recognition text will appear here.</p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function getRuntimeLanguageWarning(
  selectedLanguage: VoiceLanguage,
  configuredLanguages: string[] | undefined,
) {
  if (!configuredLanguages?.length) {
    return null
  }

  const configured = new Set(configuredLanguages.map((language) => normalizeVoiceLanguage(language)))
  if (configured.has(selectedLanguage)) {
    return null
  }

  const available = Array.from(configured)
    .map((language) => voiceLanguageLabel(language))
    .join(', ')
  return `${voiceLanguageLabel(selectedLanguage)} ASR is not configured on this backend. Available runtime: ${available}.`
}

function getModelReadinessMessage({
  selectedLanguage,
  configuredLanguages,
  loadedLanguages,
  statusError,
}: {
  selectedLanguage: VoiceLanguage
  configuredLanguages: string[] | undefined
  loadedLanguages: string[] | undefined
  statusError: unknown
}) {
  if (statusError instanceof Error) {
    return `Model status unavailable: ${statusError.message}`
  }
  if (!configuredLanguages?.length) {
    return null
  }

  const configured = new Set(configuredLanguages.map((language) => normalizeVoiceLanguage(language)))
  if (!configured.has(selectedLanguage)) {
    return null
  }

  const loaded = new Set((loadedLanguages ?? []).map((language) => normalizeVoiceLanguage(language)))
  if (loaded.has(selectedLanguage)) {
    return null
  }

  return `${voiceLanguageLabel(selectedLanguage)} ASR model is cold. The next upload may spend extra time loading local assets.`
}
