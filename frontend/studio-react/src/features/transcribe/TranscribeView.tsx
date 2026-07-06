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
  UploadCloud,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { QueryErrorState } from '@/components/ui/query-error'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { api, type AsrJob } from '@/lib/api'
import { formatDuration } from '@/lib/format'
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

export function TranscribeView() {
  const uploadInputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [selectedLanguage, setSelectedLanguage] = useState<VoiceLanguage>(() =>
    normalizeVoiceLanguage(getPreferredLanguage()),
  )
  const queryClient = useQueryClient()
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
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['asr-jobs'] })
    },
  })

  const jobs = asrJobsQuery.data ?? []
  const latestTranscript = jobs.find((job) => job.text)
  const jobsError = asrJobsQuery.isError
    ? queryErrorMessage(asrJobsQuery.error, 'Unable to load ASR jobs.')
    : null
  const runtimeLanguageWarning = getRuntimeLanguageWarning(
    selectedLanguage,
    modelStatusQuery.data?.runtime.asr_configured_languages,
  )

  const queueAudioFile = (file: File | undefined) => {
    if (file && !runtimeLanguageWarning) {
      uploadMutation.mutate({ file, language: selectedLanguage })
    }
  }

  const handleLanguageSelect = (language: VoiceLanguage) => {
    setSelectedLanguage(language)
    setPreferredLanguage(language)
  }

  const handleAudioUpload = (event: ChangeEvent<HTMLInputElement>) => {
    queueAudioFile(event.target.files?.[0])
    event.target.value = ''
  }

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setDragging(false)
    queueAudioFile(event.dataTransfer.files?.[0])
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
            <div
              className={cn(
                'rounded-md border border-dashed p-4 text-center transition-colors',
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
              <div className="mx-auto grid size-10 place-items-center rounded-md bg-white text-blue-700">
                <UploadCloud className="size-5" />
              </div>
              <div className="mt-3 text-sm font-semibold text-slate-950">
                {dragging ? 'Release to queue audio' : 'Drop audio here'}
              </div>
              <p className="mx-auto mt-1 max-w-md text-xs leading-5 text-slate-600">
                Upload WAV, MP3, WEBM, or WEBA audio to queue a {voiceLanguageLabel(selectedLanguage)} transcription job.
              </p>
              <input
                ref={uploadInputRef}
                className="hidden"
                type="file"
                accept="audio/*,.weba,.webm,.wav,.mp3,.m4a,.flac,.ogg"
                onChange={handleAudioUpload}
              />
              {uploadMutation.isError ? (
                <div className="mx-auto mt-5 max-w-md rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold leading-5 text-red-700">
                  {uploadMutation.error instanceof Error
                    ? uploadMutation.error.message
                    : 'Unable to queue ASR job.'}
                </div>
              ) : null}
              {uploadMutation.isSuccess ? (
                <div className="mx-auto mt-5 max-w-md rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-xs font-semibold text-blue-700">
                  Audio queued for transcription.
                </div>
              ) : null}
              <Button
                className="mt-4"
                disabled={uploadMutation.isPending || Boolean(runtimeLanguageWarning)}
                onClick={() => uploadInputRef.current?.click()}
              >
                {uploadMutation.isPending ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <FileAudio className="size-4" />
                )}
                {uploadMutation.isPending ? 'Queueing' : 'Select audio'}
              </Button>
            </div>
          </CardContent>
        </Card>

        <div className="xl:hidden">
          <TranscriptPreview job={latestTranscript} />
        </div>

        <Card>
          <CardHeader>
            <div>
              <div className="text-sm font-semibold text-slate-950">Recent transcripts</div>
              <div className="mt-1 text-xs text-slate-600">ASR results and queued recordings.</div>
            </div>
          </CardHeader>
          <CardContent>
            {jobsError ? (
              <QueryErrorState
                title="Unable to load transcripts"
                message={jobsError}
                onRetry={() => {
                  void asrJobsQuery.refetch()
                }}
              />
            ) : jobs.length > 0 ? (
              <div className="space-y-3">
                {jobs.map((job) => (
                  <article key={job.job_id} className="rounded-md border border-slate-200 bg-white p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="min-w-0">
                        <div className="truncate text-sm font-semibold text-slate-950">{job.filename}</div>
                        <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-slate-600">
                          <span>{job.duration_seconds ? formatDuration(job.duration_seconds) : 'Duration pending'}</span>
                          <Badge variant="muted">{voiceLanguageShortLabel(job.language)}</Badge>
                        </div>
                      </div>
                      <Badge variant={job.status === 'succeeded' ? 'success' : job.status === 'failed' ? 'danger' : 'warning'}>
                        {job.status}
                      </Badge>
                    </div>
                    <p className="mt-2 line-clamp-3 text-xs leading-5 text-slate-600">
                      {job.text || job.error || 'Transcript pending.'}
                    </p>
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
          </CardContent>
        </Card>
      </section>

      <aside className="hidden space-y-3 xl:block">
        <TranscriptPreview job={latestTranscript} />
      </aside>
    </div>
  )
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
  const text = job?.text ?? ''
  const hasText = Boolean(text.trim())
  const downloadHref = hasText ? `data:text/plain;charset=utf-8,${encodeURIComponent(text)}` : undefined

  const handleCopy = async () => {
    if (!hasText || typeof navigator === 'undefined') {
      return
    }
    await navigator.clipboard.writeText(text)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1800)
  }

  const handleUseInGenerate = () => {
    if (!hasText) {
      return
    }
    setPendingScript(text)
    setPreferredLanguage(normalizeVoiceLanguage(job?.language))
    window.location.hash = '/generate'
  }

  return (
    <Card>
      <CardHeader className="flex-wrap">
        <div>
          <div className="text-sm font-semibold text-slate-950">Transcript preview</div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-slate-600">
            <span>Latest successful recognition output.</span>
            {job ? <Badge variant="muted">{voiceLanguageShortLabel(job.language)}</Badge> : null}
          </div>
        </div>
        <div className="grid w-full grid-cols-2 gap-2 sm:flex sm:w-auto sm:flex-wrap">
          <Button className="min-w-0" size="sm" variant="secondary" disabled={!hasText} onClick={() => { void handleCopy() }}>
            {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
            {copied ? 'Copied' : 'Copy'}
          </Button>
          <Button className="min-w-0" size="sm" variant="secondary" disabled={!hasText} asChild={hasText}>
            {hasText ? (
              <a href={downloadHref} download={`vassil-transcript-${normalizeVoiceLanguage(job?.language)}.txt`}>
                <Download className="size-4" />
                Download
              </a>
            ) : (
              <>
                <Download className="size-4" />
                Download
              </>
            )}
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="min-h-[240px] rounded-md border border-slate-200 bg-white p-3 text-xs leading-6 text-slate-800 xl:min-h-[300px]">
          {hasText ? text : 'The newest transcript will appear here after ASR completes.'}
        </div>
        <Button className="mt-3 w-full" disabled={!hasText} onClick={handleUseInGenerate}>
          <Languages className="size-4" />
          Use as Generate script
          <ArrowRight className="size-4" />
        </Button>
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
