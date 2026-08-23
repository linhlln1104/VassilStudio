import * as Dialog from '@radix-ui/react-dialog'
import { useEffect, useState } from 'react'
import {
  AlertCircle,
  CheckCircle2,
  FileAudio,
  Languages,
  Loader2,
  RefreshCw,
  Scissors,
  ShieldCheck,
  TriangleAlert,
  X,
} from 'lucide-react'

import { AudioPlayer } from '@/components/ui/audio-player'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { ImportCandidate, VoiceIntakeReport } from '@/lib/api'
import {
  VOICE_LANGUAGES,
  normalizeVoiceLanguage,
  type VoiceLanguage,
} from '@/lib/language'
import { cn } from '@/lib/utils'

export type VoiceIntakeSource =
  | { kind: 'upload'; file: File }
  | { kind: 'local'; candidate: ImportCandidate }

export type VoiceIntakeDraft = {
  source: VoiceIntakeSource
  name: string
  language: VoiceLanguage
  referenceText: string
  report: VoiceIntakeReport
  trimStartSeconds: number
  trimEndSeconds: number
  acknowledged: boolean
  dirty: boolean
}

type VoiceIntakeReviewDialogProps = {
  draft: VoiceIntakeDraft
  analyzing: boolean
  creating: boolean
  error: string | null
  onChange: (next: VoiceIntakeDraft) => void
  onReanalyze: () => void
  onCreate: () => void
  onReuse: (voiceId: string) => void
  onClose: () => void
}

export function VoiceIntakeReviewDialog({
  draft,
  analyzing,
  creating,
  error,
  onChange,
  onReanalyze,
  onCreate,
  onReuse,
  onClose,
}: VoiceIntakeReviewDialogProps) {
  const { report } = draft
  const warnings = report.issues.filter((issue) => issue.severity === 'warning')
  const blocking = report.issues.filter((issue) => issue.severity === 'blocking')
  const createDisabled = Boolean(
    analyzing
      || creating
      || draft.dirty
      || !report.can_create
      || !draft.name.trim()
      || !draft.referenceText.trim()
      || (warnings.length > 0 && !draft.acknowledged),
  )

  const update = (patch: Partial<VoiceIntakeDraft>, qualityChanged = false) => {
    onChange({
      ...draft,
      ...patch,
      dirty: qualityChanged ? true : (patch.dirty ?? draft.dirty),
      acknowledged: qualityChanged ? false : (patch.acknowledged ?? draft.acknowledged),
    })
  }

  return (
    <Dialog.Root open onOpenChange={(open) => { if (!open && !creating) onClose() }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-slate-950/40 backdrop-blur-[2px]" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 flex max-h-[calc(100vh-24px)] w-[min(1040px,calc(100vw-24px))] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-md border border-slate-200 bg-white shadow-2xl outline-none">
          <header className="flex min-w-0 items-start justify-between gap-3 border-b border-slate-200 px-4 py-3 sm:px-5">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <Dialog.Title className="text-base font-semibold text-slate-950">
                  Review voice reference
                </Dialog.Title>
                <StatusBadge status={report.status} />
              </div>
              <Dialog.Description className="mt-1 truncate text-xs text-slate-600">
                {sourceName(draft.source)}
              </Dialog.Description>
            </div>
            <Button
              aria-label="Close voice review"
              title="Close"
              size="icon"
              variant="ghost"
              disabled={creating}
              onClick={onClose}
            >
              <X className="size-4" />
            </Button>
          </header>

          <div className="min-h-0 flex-1 overflow-y-auto">
            <div className="grid min-w-0 lg:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)]">
              <div className="min-w-0 space-y-4 border-b border-slate-200 p-4 sm:p-5 lg:border-b-0 lg:border-r">
                <section>
                  <SectionLabel icon={FileAudio} label="Selection preview" />
                  <div className="mt-2">
                    {draft.source.kind === 'upload' ? (
                      <UploadAudioPreview
                        file={draft.source.file}
                        startSeconds={draft.trimStartSeconds}
                        endSeconds={draft.trimEndSeconds}
                      />
                    ) : (
                      <AudioPlayer
                        src={draft.source.candidate.audio_url}
                        label={`Preview ${draft.source.candidate.name}`}
                        playbackStartSeconds={draft.trimStartSeconds}
                        playbackEndSeconds={draft.trimEndSeconds}
                      />
                    )}
                  </div>
                </section>

                <section className="border-t border-slate-200 pt-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <SectionLabel icon={Scissors} label="Trim selection" />
                    <span className="text-xs font-semibold tabular-nums text-slate-600">
                      {formatSeconds(draft.trimStartSeconds)} - {formatSeconds(draft.trimEndSeconds)}
                    </span>
                  </div>
                  <TrimControls draft={draft} onChange={update} />
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={analyzing || creating}
                      onClick={() => update({
                        trimStartSeconds: report.suggested_trim_start_seconds,
                        trimEndSeconds: report.suggested_trim_end_seconds,
                      }, true)}
                    >
                      <Scissors className="size-4" />
                      Use suggested trim
                    </Button>
                    <Button
                      size="sm"
                      disabled={!draft.dirty || analyzing || creating}
                      onClick={onReanalyze}
                    >
                      {analyzing ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
                      {analyzing ? 'Checking selection' : 'Recheck selection'}
                    </Button>
                  </div>
                </section>

                <section className="border-t border-slate-200 pt-4">
                  <SectionLabel icon={ShieldCheck} label="Signal report" />
                  <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
                    <Metric label="Selection" value={formatSeconds(report.duration_seconds)} />
                    <Metric label="Source" value={`${formatKhz(report.source_sample_rate)} / ${report.channels === 1 ? 'Mono' : `${report.channels} ch`}`} />
                    <Metric label="Speech coverage" value={formatPercent(report.speech_coverage_ratio)} />
                    <Metric label="Clipping" value={formatClipping(report.clipping_ratio)} />
                    <Metric label="Leading silence" value={formatSeconds(report.leading_silence_seconds)} />
                    <Metric label="Trailing silence" value={formatSeconds(report.trailing_silence_seconds)} />
                    <Metric label="Profile rate" value={formatKhz(report.target_sample_rate)} />
                    <Metric label="Peak" value={report.peak_amplitude.toFixed(2)} />
                  </div>
                </section>

                <IssueList report={report} stale={draft.dirty} />
              </div>

              <div className="min-w-0 space-y-4 p-4 sm:p-5">
                <section>
                  <div className="text-sm font-semibold text-slate-950">Profile details</div>
                  <div className="mt-3 space-y-3">
                    <label className="block">
                      <span className="mb-1.5 block text-xs font-semibold text-slate-600">Profile name</span>
                      <input
                        className="h-9 w-full rounded-md border border-slate-300 px-3 text-xs font-medium text-slate-950 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                        value={draft.name}
                        onChange={(event) => update({ name: event.target.value })}
                      />
                    </label>
                    <label className="block">
                      <span className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-slate-600">
                        <Languages className="size-3.5" />
                        Language
                      </span>
                      <select
                        className="h-9 w-full rounded-md border border-slate-300 bg-white px-3 text-xs font-medium text-slate-950 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                        value={draft.language}
                        onChange={(event) => update(
                          { language: normalizeVoiceLanguage(event.target.value) },
                          true,
                        )}
                      >
                        {VOICE_LANGUAGES.map((language) => (
                          <option key={language.value} value={language.value}>{language.label}</option>
                        ))}
                      </select>
                    </label>
                    <label className="block">
                      <span className="mb-1.5 flex items-center justify-between gap-2 text-xs font-semibold text-slate-600">
                        <span>Exact transcript</span>
                        {report.reference_text_source === 'asr' ? <Badge variant="muted">ASR draft</Badge> : null}
                      </span>
                      <textarea
                        className="min-h-32 w-full resize-y rounded-md border border-slate-300 px-3 py-2 text-sm leading-6 text-slate-950 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                        value={draft.referenceText}
                        onChange={(event) => update({ referenceText: event.target.value }, true)}
                      />
                    </label>
                  </div>
                </section>

                {report.duplicate ? (
                  <div className="rounded-md border border-red-200 bg-red-50 p-3">
                    <div className="flex items-start gap-2 text-sm font-semibold text-red-900">
                      <AlertCircle className="mt-0.5 size-4 shrink-0" />
                      Already in your library
                    </div>
                    <p className="mt-1 text-xs leading-5 text-red-800">
                      Reuse {report.duplicate.name}. Edit that profile if you intended to replace its metadata.
                    </p>
                    <Button
                      className="mt-3"
                      size="sm"
                      variant="secondary"
                      onClick={() => onReuse(report.duplicate!.voice_id)}
                    >
                      <CheckCircle2 className="size-4" />
                      Use existing profile
                    </Button>
                  </div>
                ) : null}

                {warnings.length > 0 && blocking.length === 0 && !draft.dirty ? (
                  <label className="flex cursor-pointer items-start gap-2.5 rounded-md border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-950">
                    <input
                      className="mt-1 size-4 shrink-0 accent-blue-600"
                      type="checkbox"
                      checked={draft.acknowledged}
                      onChange={(event) => update({ acknowledged: event.target.checked })}
                    />
                    <span>I listened to the selection and accept these quality warnings.</span>
                  </label>
                ) : null}

                {error ? (
                  <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs font-medium leading-5 text-red-800" role="alert">
                    {error}
                  </div>
                ) : null}
              </div>
            </div>
          </div>

          <footer className="flex flex-col-reverse gap-2 border-t border-slate-200 bg-slate-50 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-5">
            <div className="text-xs font-medium text-slate-600">
              {draft.dirty ? 'Recheck changes before saving.' : statusFooter(report.status, warnings.length)}
            </div>
            <div className="flex gap-2">
              <Button variant="secondary" disabled={creating} onClick={onClose}>Cancel</Button>
              <Button disabled={createDisabled} onClick={onCreate}>
                {creating ? <Loader2 className="size-4 animate-spin" /> : <ShieldCheck className="size-4" />}
                {creating ? 'Creating profile' : 'Create voice profile'}
              </Button>
            </div>
          </footer>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

function TrimControls({
  draft,
  onChange,
}: {
  draft: VoiceIntakeDraft
  onChange: (patch: Partial<VoiceIntakeDraft>, qualityChanged?: boolean) => void
}) {
  const max = Math.max(0.01, draft.report.source_duration_seconds)
  const minimumGap = Math.min(0.05, max)
  return (
    <div className="mt-3 space-y-3 rounded-md border border-slate-200 bg-slate-50 p-3">
      <label className="block">
        <span className="flex items-center justify-between text-xs font-semibold text-slate-600">
          <span>Start</span><span className="tabular-nums">{formatSeconds(draft.trimStartSeconds)}</span>
        </span>
        <input
          aria-label="Trim start"
          className="mt-2 h-2 w-full accent-blue-600"
          min={0}
          max={Math.max(0, draft.trimEndSeconds - minimumGap)}
          step={0.01}
          type="range"
          value={draft.trimStartSeconds}
          onChange={(event) => onChange({ trimStartSeconds: Number(event.target.value) }, true)}
        />
      </label>
      <label className="block">
        <span className="flex items-center justify-between text-xs font-semibold text-slate-600">
          <span>End</span><span className="tabular-nums">{formatSeconds(draft.trimEndSeconds)}</span>
        </span>
        <input
          aria-label="Trim end"
          className="mt-2 h-2 w-full accent-blue-600"
          min={Math.min(max, draft.trimStartSeconds + minimumGap)}
          max={max}
          step={0.01}
          type="range"
          value={draft.trimEndSeconds}
          onChange={(event) => onChange({ trimEndSeconds: Number(event.target.value) }, true)}
        />
      </label>
    </div>
  )
}

function UploadAudioPreview({
  file,
  startSeconds,
  endSeconds,
}: {
  file: File
  startSeconds: number
  endSeconds: number
}) {
  const [src, setSrc] = useState('')
  useEffect(() => {
    const objectUrl = URL.createObjectURL(file)
    setSrc(objectUrl)
    return () => URL.revokeObjectURL(objectUrl)
  }, [file])
  const enforceSelection = (audio: HTMLAudioElement) => {
    if (audio.currentTime < startSeconds || audio.currentTime >= endSeconds) {
      audio.currentTime = startSeconds
    }
  }
  return src ? (
    <audio
      className="h-10 w-full"
      aria-label={`Preview ${file.name}`}
      controls
      preload="metadata"
      src={src}
      onLoadedMetadata={(event) => { event.currentTarget.currentTime = startSeconds }}
      onPlay={(event) => enforceSelection(event.currentTarget)}
      onTimeUpdate={(event) => {
        if (event.currentTarget.currentTime >= endSeconds) event.currentTarget.pause()
      }}
    />
  ) : (
    <div className="h-10 animate-pulse rounded-md bg-slate-100" />
  )
}

function IssueList({ report, stale }: { report: VoiceIntakeReport; stale: boolean }) {
  if (stale) {
    return (
      <div className="rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-xs font-medium text-blue-800">
        Quality results are stale after your changes.
      </div>
    )
  }
  if (report.issues.length === 0) {
    return (
      <div className="flex items-start gap-2 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-medium leading-5 text-emerald-800">
        <CheckCircle2 className="mt-0.5 size-4 shrink-0" />
        Audio and transcript passed the intake checks.
      </div>
    )
  }
  return (
    <div className="space-y-2">
      {report.issues.map((issue) => (
        <div
          key={issue.code}
          className={cn(
            'flex items-start gap-2 rounded-md border px-3 py-2 text-xs leading-5',
            issue.severity === 'blocking'
              ? 'border-red-200 bg-red-50 text-red-800'
              : 'border-amber-200 bg-amber-50 text-amber-900',
          )}
        >
          {issue.severity === 'blocking'
            ? <AlertCircle className="mt-0.5 size-4 shrink-0" />
            : <TriangleAlert className="mt-0.5 size-4 shrink-0" />}
          <span>{issue.message}</span>
        </div>
      ))}
    </div>
  )
}

function StatusBadge({ status }: { status: VoiceIntakeReport['status'] }) {
  if (status === 'ready') return <Badge variant="success">Ready</Badge>
  if (status === 'blocked') return <Badge variant="danger">Blocked</Badge>
  return <Badge variant="warning">Review</Badge>
}

function SectionLabel({ icon: Icon, label }: { icon: typeof FileAudio; label: string }) {
  return (
    <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
      <Icon className="size-4 text-slate-500" />{label}
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-md border border-slate-200 bg-white px-2.5 py-2">
      <div className="truncate text-xs font-semibold text-slate-950">{value}</div>
      <div className="mt-0.5 truncate text-[11px] text-slate-500">{label}</div>
    </div>
  )
}

function sourceName(source: VoiceIntakeSource) {
  return source.kind === 'upload' ? source.file.name : source.candidate.filename
}

function formatSeconds(value: number) {
  return `${value.toFixed(value >= 10 ? 1 : 2)}s`
}

function formatKhz(value: number) {
  return value >= 1000 ? `${(value / 1000).toFixed(value % 1000 === 0 ? 0 : 1)} kHz` : `${value} Hz`
}

function formatPercent(value: number) {
  return `${Math.round(value * 100)}%`
}

function formatClipping(value: number) {
  if (value > 0 && value < 0.0001) return '<0.01%'
  return `${(value * 100).toFixed(value < 0.01 ? 2 : 1)}%`
}

function statusFooter(status: VoiceIntakeReport['status'], warningCount: number) {
  if (status === 'ready') return 'Ready to add to the voice library.'
  if (status === 'blocked') return 'Resolve blocking issues or choose another recording.'
  return `${warningCount} quality warning${warningCount === 1 ? '' : 's'} require review.`
}
