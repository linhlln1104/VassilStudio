import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import * as Dialog from '@radix-ui/react-dialog'
import {
  AlertTriangle,
  Braces,
  Captions,
  Check,
  Copy,
  FileText,
  Loader2,
  PencilLine,
  Save,
  Undo2,
  X,
} from 'lucide-react'

import { AudioPlayer } from '@/components/ui/audio-player'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useToast } from '@/components/ui/use-toast'
import {
  api,
  type AsrJob,
  type TranscriptExportFormat,
  type TranscriptSegment,
} from '@/lib/api'
import { compactId, formatDuration } from '@/lib/format'
import { voiceLanguageShortLabel } from '@/lib/language'
import { cn } from '@/lib/utils'

type TranscriptReviewDialogProps = {
  job: AsrJob | null
  onOpenChange: (open: boolean) => void
}

const EXPORT_FORMATS: Array<{
  format: TranscriptExportFormat
  label: string
  icon: typeof FileText
  requiresTiming?: boolean
}> = [
  { format: 'txt', label: 'TXT', icon: FileText },
  { format: 'srt', label: 'SRT', icon: Captions, requiresTiming: true },
  { format: 'vtt', label: 'VTT', icon: Captions, requiresTiming: true },
  { format: 'json', label: 'JSON', icon: Braces },
]

export function TranscriptReviewDialog({ job, onOpenChange }: TranscriptReviewDialogProps) {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const [editing, setEditing] = useState(false)
  const [draftText, setDraftText] = useState('')
  const [draftSegments, setDraftSegments] = useState<Record<string, string>>({})
  const [currentTime, setCurrentTime] = useState(0)
  const [seekRequest, setSeekRequest] = useState<{ seconds: number; requestId: number } | null>(null)
  const [exporting, setExporting] = useState<TranscriptExportFormat | null>(null)
  const [exportError, setExportError] = useState('')
  const [closeWarning, setCloseWarning] = useState(false)
  const [copied, setCopied] = useState(false)

  const segments = useMemo(() => job?.segments ?? [], [job?.segments])

  useEffect(() => {
    setEditing(false)
    setDraftText(job?.text ?? '')
    setDraftSegments(segmentDraft(segments))
    setCurrentTime(0)
    setSeekRequest(null)
    setExportError('')
    setCloseWarning(false)
  }, [job?.job_id, job?.text, job?.transcript_revision, segments])

  const dirty = editing && (segments.length > 0
    ? segments.some((segment) => (draftSegments[segment.segment_id] ?? '') !== segment.text)
    : draftText !== (job?.text ?? ''))
  const invalidDraft = segments.length > 0
    ? segments.some((segment) => !(draftSegments[segment.segment_id] ?? '').trim())
    : !draftText.trim()

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!job) {
        throw new Error('Transcript is no longer available.')
      }
      if (segments.length > 0) {
        return api.reviseAsrTranscript(job.job_id, {
          expectedRevision: job.transcript_revision,
          segments: segments.map((segment) => ({
            segmentId: segment.segment_id,
            text: draftSegments[segment.segment_id] ?? segment.text,
          })),
        })
      }
      return api.reviseAsrTranscript(job.job_id, {
        expectedRevision: job.transcript_revision,
        text: draftText,
      })
    },
    onSuccess: (updated) => {
      queryClient.setQueryData<AsrJob[]>(['asr-jobs'], (current = []) =>
        current.map((item) => (item.job_id === updated.job_id ? updated : item)),
      )
      setEditing(false)
      setCloseWarning(false)
      toast({
        title: 'Transcript saved',
        description: `Revision ${updated.transcript_revision} is ready to export.`,
        variant: 'success',
      })
    },
  })

  if (!job) {
    return null
  }

  const activeSegment = segments.find(
    (segment, index) =>
      currentTime >= segment.start_seconds &&
      (currentTime < segment.end_seconds || (index === segments.length - 1 && currentTime <= segment.end_seconds)),
  )
  const timingAvailable = job.timing_status === 'available' && segments.length > 0
  const rawText = job.raw_text ?? job.text ?? ''
  const saveError = saveMutation.error instanceof Error ? saveMutation.error.message : ''

  const startEditing = () => {
    setDraftText(job.text ?? '')
    setDraftSegments(segmentDraft(segments))
    setCloseWarning(false)
    saveMutation.reset()
    setEditing(true)
  }

  const discardEdits = () => {
    setDraftText(job.text ?? '')
    setDraftSegments(segmentDraft(segments))
    setCloseWarning(false)
    saveMutation.reset()
    setEditing(false)
  }

  const requestClose = () => {
    if (dirty) {
      setCloseWarning(true)
      return
    }
    onOpenChange(false)
  }

  const reloadLatest = () => {
    saveMutation.reset()
    setEditing(false)
    setCloseWarning(false)
    void queryClient.invalidateQueries({ queryKey: ['asr-jobs'] })
  }

  const seekToSegment = (segment: TranscriptSegment) => {
    setCurrentTime(segment.start_seconds)
    setSeekRequest((current) => ({
      seconds: segment.start_seconds,
      requestId: (current?.requestId ?? 0) + 1,
    }))
  }

  const copyTranscript = async () => {
    if (!job.text) {
      return
    }
    try {
      await navigator.clipboard.writeText(job.text)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1600)
    } catch {
      toast({
        title: 'Copy failed',
        description: 'Clipboard access is unavailable.',
        variant: 'danger',
      })
    }
  }

  const downloadExport = async (format: TranscriptExportFormat) => {
    setExportError('')
    setExporting(format)
    try {
      const blob = await api.asrTranscriptExport(job.job_id, format)
      const objectUrl = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = objectUrl
      anchor.download = transcriptFilename(job.job_id, format)
      document.body.append(anchor)
      anchor.click()
      anchor.remove()
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
      toast({
        title: `${format.toUpperCase()} exported`,
        description: anchor.download,
        variant: 'success',
      })
    } catch (error) {
      setExportError(error instanceof Error ? error.message : 'Unable to export this transcript.')
    } finally {
      setExporting(null)
    }
  }

  return (
    <Dialog.Root open onOpenChange={(open) => { if (!open) requestClose() }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-slate-950/40 backdrop-blur-[2px]" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 flex max-h-[min(900px,calc(100vh-24px))] w-[min(1120px,calc(100vw-24px))] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-md border border-slate-200 bg-white shadow-2xl outline-none">
          <header className="flex shrink-0 items-start justify-between gap-4 border-b border-slate-200 px-4 py-3.5 sm:px-5">
            <div className="min-w-0">
              <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
                <Badge variant={timingAvailable ? 'success' : 'muted'}>
                  {timingAvailable ? `${segments.length} timed segments` : 'Untimed transcript'}
                </Badge>
                <Badge variant={job.transcript_edited ? 'warning' : 'muted'}>
                  {job.transcript_edited ? `Revision ${job.transcript_revision}` : 'Model output'}
                </Badge>
                <Badge variant="muted">{voiceLanguageShortLabel(job.language)}</Badge>
              </div>
              <Dialog.Title className="text-base font-semibold leading-6 text-slate-950">
                Review transcript
              </Dialog.Title>
              <Dialog.Description className="mt-0.5 truncate text-xs leading-5 text-slate-600">
                {job.filename} / {formatDuration(job.duration_seconds)} / {compactId(job.job_id)}
              </Dialog.Description>
            </div>
            <Button
              className="shrink-0"
              size="icon"
              variant="ghost"
              aria-label="Close transcript review"
              title="Close"
              onClick={requestClose}
            >
              <X className="size-4" />
            </Button>
          </header>

          <section className="shrink-0 border-b border-slate-200 bg-slate-50 px-4 py-3 sm:px-5">
            {job.audio_url ? (
              <AudioPlayer
                src={job.audio_url}
                label={`Review source audio for ${job.filename}`}
                seekRequest={seekRequest}
                onTimeUpdate={setCurrentTime}
              />
            ) : (
              <div className="flex items-center gap-2 text-xs font-medium text-amber-800" role="status">
                <AlertTriangle className="size-4 shrink-0" />
                Source audio is unavailable for this job.
              </div>
            )}
          </section>

          <div className="min-h-0 flex-1 overflow-y-auto lg:grid lg:grid-cols-[minmax(0,1fr)_292px]">
            <section className="min-w-0 px-4 py-4 sm:px-5">
              <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h3 className="text-sm font-semibold text-slate-950">
                    {timingAvailable ? 'Timed transcript' : 'Transcript'}
                  </h3>
                  <p className="mt-0.5 text-xs leading-5 text-slate-600">
                    {timingAvailable ? 'Select a segment to play from its model timestamp.' : 'Timing was not supplied by this recognition result.'}
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button
                    className="w-8 px-0"
                    size="sm"
                    variant="secondary"
                    aria-label={copied ? 'Transcript copied' : 'Copy transcript'}
                    title={copied ? 'Copied' : 'Copy transcript'}
                    onClick={() => { void copyTranscript() }}
                  >
                    {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
                  </Button>
                  {!editing ? (
                    <Button size="sm" variant="secondary" onClick={startEditing}>
                      <PencilLine className="size-4" />
                      Edit
                    </Button>
                  ) : null}
                </div>
              </div>

              {segments.length > 0 ? (
                <div className="space-y-2" aria-label="Transcript segments">
                  {segments.map((segment, index) => {
                    const active = activeSegment?.segment_id === segment.segment_id
                    return (
                      <div
                        key={segment.segment_id}
                        className={cn(
                          'grid min-w-0 grid-cols-[72px_minmax(0,1fr)] gap-3 rounded-md border p-3 transition-colors sm:grid-cols-[92px_minmax(0,1fr)]',
                          active ? 'border-sky-300 bg-sky-50' : 'border-slate-200 bg-white',
                        )}
                        data-active={active ? 'true' : 'false'}
                      >
                        <button
                          className="text-left"
                          type="button"
                          aria-label={`Play segment ${index + 1} at ${formatReviewTime(segment.start_seconds)}`}
                          onClick={() => seekToSegment(segment)}
                        >
                          <span className={cn('block text-xs font-semibold tabular-nums', active ? 'text-blue-700' : 'text-slate-700')}>
                            {formatReviewTime(segment.start_seconds)}
                          </span>
                          <span className="mt-1 block text-[11px] font-medium text-slate-500">
                            to {formatReviewTime(segment.end_seconds)}
                          </span>
                        </button>
                        {editing ? (
                          <textarea
                            className="min-h-20 w-full resize-y rounded-md border border-slate-300 bg-white px-3 py-2 text-sm leading-6 text-slate-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                            aria-label={`Edit segment ${index + 1}`}
                            value={draftSegments[segment.segment_id] ?? ''}
                            maxLength={2000}
                            onChange={(event) => setDraftSegments((current) => ({
                              ...current,
                              [segment.segment_id]: event.target.value,
                            }))}
                          />
                        ) : (
                          <button
                            className="min-w-0 text-left text-sm leading-6 text-slate-800"
                            type="button"
                            aria-current={active ? 'true' : undefined}
                            onClick={() => seekToSegment(segment)}
                          >
                            {segment.text}
                          </button>
                        )}
                      </div>
                    )
                  })}
                </div>
              ) : editing ? (
                <textarea
                  className="min-h-72 w-full resize-y rounded-md border border-slate-300 bg-white p-3 text-sm leading-7 text-slate-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                  aria-label="Edit transcript"
                  value={draftText}
                  maxLength={100000}
                  onChange={(event) => setDraftText(event.target.value)}
                />
              ) : (
                <div className="min-h-56 whitespace-pre-wrap rounded-md border border-slate-200 bg-white p-3 text-sm leading-7 text-slate-800">
                  {job.text}
                </div>
              )}

              {saveError ? (
                <div className="mt-3 flex flex-col gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs font-medium leading-5 text-red-800 sm:flex-row sm:items-center sm:justify-between" role="alert">
                  <div className="flex min-w-0 items-start gap-2">
                    <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                    <span>{saveError}</span>
                  </div>
                  <Button className="shrink-0" size="sm" variant="secondary" onClick={reloadLatest}>
                    Reload latest
                  </Button>
                </div>
              ) : null}
            </section>

            <aside className="border-t border-slate-200 bg-slate-50 px-4 py-4 sm:px-5 lg:border-l lg:border-t-0">
              <section>
                <h3 className="text-xs font-semibold uppercase text-slate-600">Export</h3>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  {EXPORT_FORMATS.map(({ format, label, icon: Icon, requiresTiming }) => {
                    const disabled = Boolean(requiresTiming && !timingAvailable)
                    return (
                      <Button
                        key={format}
                        size="sm"
                        variant="secondary"
                        disabled={disabled || exporting !== null}
                        title={disabled ? `${label} requires timed segments` : `Export ${label}`}
                        onClick={() => { void downloadExport(format) }}
                      >
                        {exporting === format ? <Loader2 className="size-4 animate-spin" /> : <Icon className="size-4" />}
                        {label}
                      </Button>
                    )
                  })}
                </div>
                {!timingAvailable ? (
                  <p className="mt-2 text-xs leading-5 text-slate-600">SRT and VTT need model timing.</p>
                ) : null}
                {exportError ? (
                  <div className="mt-3 text-xs font-medium leading-5 text-red-700" role="alert">{exportError}</div>
                ) : null}
              </section>

              <section className="mt-5 border-t border-slate-200 pt-4">
                <h3 className="text-xs font-semibold uppercase text-slate-600">Revision</h3>
                <dl className="mt-3 space-y-2 text-xs">
                  <ReviewMetadata label="Current" value={`Revision ${job.transcript_revision}`} />
                  <ReviewMetadata label="Timing" value={timingAvailable ? 'Model timestamps' : 'Unavailable'} />
                  <ReviewMetadata label="Segments" value={String(segments.length)} />
                </dl>
              </section>

              {job.transcript_edited ? (
                <details className="mt-5 border-t border-slate-200 pt-4">
                  <summary className="cursor-pointer text-xs font-semibold text-slate-700">Original model result</summary>
                  <p className="mt-3 max-h-56 overflow-y-auto whitespace-pre-wrap text-xs leading-6 text-slate-600">
                    {rawText}
                  </p>
                </details>
              ) : null}
            </aside>
          </div>

          <footer className="shrink-0 border-t border-slate-200 bg-white px-4 py-3 sm:px-5">
            {closeWarning ? (
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-start gap-2 text-xs font-medium leading-5 text-amber-800">
                  <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                  Unsaved transcript changes will be lost.
                </div>
                <div className="flex justify-end gap-2">
                  <Button size="sm" variant="secondary" onClick={() => setCloseWarning(false)}>Keep editing</Button>
                  <Button size="sm" variant="destructive" onClick={() => onOpenChange(false)}>Discard and close</Button>
                </div>
              </div>
            ) : (
              <div className="flex flex-wrap items-center justify-end gap-2">
                {editing ? (
                  <>
                    <Button size="sm" variant="secondary" disabled={saveMutation.isPending} onClick={discardEdits}>
                      <Undo2 className="size-4" />
                      Discard edits
                    </Button>
                    <Button
                      size="sm"
                      disabled={!dirty || invalidDraft || saveMutation.isPending}
                      onClick={() => saveMutation.mutate()}
                    >
                      {saveMutation.isPending ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
                      Save revision
                    </Button>
                  </>
                ) : (
                  <Button size="sm" variant="secondary" onClick={requestClose}>Close</Button>
                )}
              </div>
            )}
          </footer>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

function ReviewMetadata({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-slate-500">{label}</dt>
      <dd className="text-right font-semibold text-slate-800">{value}</dd>
    </div>
  )
}

function segmentDraft(segments: TranscriptSegment[]) {
  return Object.fromEntries(segments.map((segment) => [segment.segment_id, segment.text]))
}

function transcriptFilename(jobId: string, format: TranscriptExportFormat) {
  const compact = jobId.replaceAll(/[^A-Za-z0-9]/g, '').slice(0, 8) || 'export'
  return `transcript-${compact}.${format}`
}

function formatReviewTime(seconds: number) {
  const safeSeconds = Math.max(0, seconds)
  const minutes = Math.floor(safeSeconds / 60)
  const remainder = safeSeconds - minutes * 60
  return `${minutes}:${remainder.toFixed(1).padStart(4, '0')}`
}
