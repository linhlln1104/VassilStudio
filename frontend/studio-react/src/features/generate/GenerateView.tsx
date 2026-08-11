import { useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowRight,
  ArrowUpRight,
  CheckCircle2,
  Circle,
  Download,
  Eraser,
  Languages,
  Loader2,
  SendHorizontal,
  SlidersHorizontal,
  Upload,
  WandSparkles,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { QueryErrorState } from '@/components/ui/query-error'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { useToast } from '@/components/ui/use-toast'
import { api, type TtsJob, type Voice } from '@/lib/api'
import { BRAND_NAME } from '@/lib/brand'
import { compactId, formatDuration } from '@/lib/format'
import {
  VOICE_LANGUAGES,
  hasVietnameseDiacritics,
  normalizeVoiceLanguage,
  type VoiceLanguage,
  voiceLanguageLabel,
  voiceLanguageShortLabel,
} from '@/lib/language'
import { queryErrorMessage } from '@/lib/query-error'
import {
  consumePendingScript,
  getGenerateDraft,
  getPreferredLanguage,
  getPreferredVoiceId,
  setGenerateDraft,
  setPreferredLanguage,
  setPreferredVoiceId,
} from '@/lib/studio-preferences'

const promptSuggestions: Record<VoiceLanguage, string[]> = {
  vi: [
    `Xin ch\u00e0o, \u0111\u00e2y l\u00e0 b\u1ea3n gi\u1edbi thi\u1ec7u ng\u1eafn v\u1ec1 ${BRAND_NAME}, n\u1ec1n t\u1ea3ng gi\u1ecdng n\u00f3i ti\u1ebfng Vi\u1ec7t ch\u1ea1y tr\u00ean m\u00f4 h\u00ecnh c\u1ee5c b\u1ed9.`,
    'Trong video n\u00e0y, ch\u00fang ta s\u1ebd c\u00f9ng xem c\u00e1ch t\u1ea1o m\u1ed9t b\u1ea3n thuy\u1ebft minh t\u1ef1 nhi\u00ean ch\u1ec9 trong v\u00e0i b\u01b0\u1edbc.',
    'C\u1ea3m \u01a1n b\u1ea1n \u0111\u00e3 l\u1eafng nghe. H\u1eb9n g\u1eb7p l\u1ea1i trong t\u1eadp ti\u1ebfp theo c\u1ee7a ch\u01b0\u01a1ng tr\u00ecnh.',
  ],
  en: [
    `Hello, this is a short ${BRAND_NAME} narration pass for a clean English production workflow.`,
    'In this episode, we will turn a simple idea into a polished voiceover for production review.',
    `Thanks for listening. See you in the next update from ${BRAND_NAME}.`,
  ],
}

type RenderMode = 'preview' | 'production'

const renderProfiles: Record<RenderMode, { label: string; numSteps: number; helper: string }> = {
  preview: {
    label: 'Preview',
    numSteps: 8,
    helper: 'Faster draft render for checking voice, pacing, and copy.',
  },
  production: {
    label: 'Production',
    numSteps: 16,
    helper: 'Full default render for final review and export.',
  },
}

export function GenerateView() {
  const [script, setScript] = useState(() => getGenerateDraft())
  const [selectedVoiceId, setSelectedVoiceId] = useState(() => getPreferredVoiceId())
  const [selectedLanguage, setSelectedLanguage] = useState<VoiceLanguage>(() =>
    normalizeVoiceLanguage(getPreferredLanguage()),
  )
  const [renderMode, setRenderMode] = useState<RenderMode>('preview')
  const [speedPercent, setSpeedPercent] = useState(100)
  const importInputRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const voicesQuery = useQuery({ queryKey: ['voices'], queryFn: api.voices })
  const ttsJobsQuery = useQuery({
    queryKey: ['tts-jobs'],
    queryFn: api.ttsJobs,
    refetchInterval: 8000,
  })
  const modelStatusQuery = useQuery({
    queryKey: ['model-status'],
    queryFn: api.modelStatus,
    staleTime: 30000,
    refetchInterval: 30000,
  })

  const voices = voicesQuery.data ?? []
  const ttsJobs = useMemo(() => ttsJobsQuery.data ?? [], [ttsJobsQuery.data])
  const selectedVoice = voices.find((voice) => voice.voice_id === selectedVoiceId) ?? voices[0]
  const selectedVoiceLanguage = normalizeVoiceLanguage(selectedVoice?.language)
  const selectedVoiceEffectId = selectedVoice?.voice_id
  const selectedVoiceEffectLanguage = selectedVoice?.language
  const latestOutput = useMemo(
    () => ttsJobs.find((job) => job.audio_url) ?? null,
    [ttsJobs],
  )
  const activeTtsCount = ttsJobs.filter((job) => ['queued', 'running', 'cancelling'].includes(job.status)).length
  const latestFailedTtsJob = ttsJobs.find((job) => job.status === 'failed') ?? null
  const latestOutputVoice = voices.find((voice) => voice.voice_id === latestOutput?.voice_id)
  const renderProfile = renderProfiles[renderMode]
  const generateMutation = useMutation({
    mutationFn: ({ voiceId, text, language }: { voiceId: string; text: string; language: VoiceLanguage }) =>
      api.createTtsJobWithVoice(voiceId, {
        text,
        language,
        numSteps: renderProfile.numSteps,
        speed: speedFromPercent(speedPercent),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['tts-jobs'] })
    },
  })
  const latestJob = generateMutationJob(ttsJobs, generateMutation.data)
  const latestJobVoice = voices.find((voice) => voice.voice_id === latestJob?.voice_id)
  const firstRunRenderQueued = activeTtsCount > 0 || Boolean(latestOutput) || generateMutation.isSuccess

  const generateErrorMessage =
    generateMutation.error instanceof Error ? generateMutation.error.message : 'Unable to queue TTS job.'
  const voicesError = voicesQuery.isError
    ? queryErrorMessage(voicesQuery.error, 'Unable to load voice profiles.')
    : null
  const jobsError = ttsJobsQuery.isError
    ? queryErrorMessage(ttsJobsQuery.error, 'Unable to load generated outputs.')
    : null
  const scriptReady = Boolean(script.trim())
  const languageWarning = getLanguageWarning(script, selectedLanguage, selectedVoice)
  const runtimeLanguageWarning = getRuntimeLanguageWarning(
    selectedLanguage,
    modelStatusQuery.data?.runtime.tts_configured_languages,
  )
  const modelReadinessMessage = getModelReadinessMessage({
    selectedLanguage,
    configuredLanguages: modelStatusQuery.data?.runtime.tts_configured_languages,
    loadedLanguages: modelStatusQuery.data?.runtime.tts_loaded_languages,
    statusError: modelStatusQuery.error,
    kind: 'TTS',
  })
  const canGenerate = Boolean(scriptReady && selectedVoice && !runtimeLanguageWarning && !generateMutation.isPending)

  useEffect(() => {
    const pendingScript = consumePendingScript()
    if (pendingScript) {
      setScript(pendingScript)
    }
  }, [])

  useEffect(() => {
    setGenerateDraft(script)
  }, [script])

  useEffect(() => {
    const firstVoice = voicesQuery.data?.[0]
    const preferredVoiceExists = voicesQuery.data?.some((voice) => voice.voice_id === selectedVoiceId)
    if (selectedVoiceId && preferredVoiceExists) {
      setPreferredVoiceId(selectedVoiceId)
      return
    }
    if (firstVoice) {
      setSelectedVoiceId(firstVoice.voice_id)
      setPreferredVoiceId(firstVoice.voice_id)
      setSelectedLanguage(normalizeVoiceLanguage(firstVoice.language))
      setPreferredLanguage(normalizeVoiceLanguage(firstVoice.language))
    }
  }, [selectedVoiceId, voicesQuery.data])

  useEffect(() => {
    if (selectedVoiceEffectId) {
      const language = normalizeVoiceLanguage(selectedVoiceEffectLanguage)
      setSelectedLanguage(language)
      setPreferredLanguage(language)
    }
  }, [selectedVoiceEffectId, selectedVoiceEffectLanguage])

  const handleVoiceSelect = (voiceId: string) => {
    setSelectedVoiceId(voiceId)
    setPreferredVoiceId(voiceId)
    const voice = voices.find((item) => item.voice_id === voiceId)
    if (voice) {
      const language = normalizeVoiceLanguage(voice.language)
      setSelectedLanguage(language)
      setPreferredLanguage(language)
    }
  }

  const handleLanguageSelect = (language: VoiceLanguage) => {
    setSelectedLanguage(language)
    setPreferredLanguage(language)
  }

  const handleTextImport = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) {
      return
    }

    try {
      const importedScript = await file.text()
      if (!importedScript.trim()) {
        throw new Error('The selected text file is empty.')
      }
      setScript(importedScript)
      toast({
        title: 'Script imported',
        description: `${file.name} loaded with ${importedScript.length.toLocaleString()} characters.`,
        variant: 'success',
      })
    } catch (error) {
      toast({
        title: 'Import failed',
        description: error instanceof Error ? error.message : 'Unable to read the selected text file.',
        variant: 'danger',
      })
    } finally {
      event.target.value = ''
    }
  }

  const handleGenerate = () => {
    if (selectedVoice) {
      generateMutation.mutate({
        voiceId: selectedVoice.voice_id,
        text: script.trim(),
        language: selectedLanguage,
      })
    }
  }

  const sharedProps = {
    voices,
    selectedVoice,
    selectedVoiceId,
    setSelectedVoiceId: handleVoiceSelect,
    speedPercent,
    setSpeedPercent,
    renderMode,
    setRenderMode,
    selectedLanguage,
    selectedVoiceLanguage,
    languageWarning,
    runtimeLanguageWarning,
    modelReadinessMessage,
    onLanguageChange: handleLanguageSelect,
    scriptReady,
    canGenerate,
    generatePending: generateMutation.isPending,
    generateSuccess: generateMutation.isSuccess,
    generateError: generateMutation.isError ? generateErrorMessage : null,
    voicesError,
    onRetryVoices: () => {
      void voicesQuery.refetch()
    },
    onGenerate: handleGenerate,
  }

  return (
    <>
      <input
        ref={importInputRef}
        className="hidden"
        type="file"
        accept=".txt,text/plain"
        onChange={(event) => {
          void handleTextImport(event)
        }}
      />

      <FirstRunChecklist
        runtimeReady={Boolean(modelStatusQuery.data?.ready)}
        runtimeLoading={modelStatusQuery.isLoading}
        voiceReady={voices.length > 0}
        scriptReady={scriptReady}
        renderQueued={firstRunRenderQueued}
        outputReady={Boolean(latestOutput?.audio_url)}
        canGenerate={canGenerate}
        onUseSample={() => setScript(promptSuggestions[selectedLanguage][0])}
        onGenerate={handleGenerate}
      />

      <div className="grid min-w-0 grid-cols-1 gap-3 xl:hidden">
        <ScriptEditor
          script={script}
          language={selectedLanguage}
          onScriptChange={setScript}
          onClear={() => setScript('')}
          onImportText={() => importInputRef.current?.click()}
          canGenerate={canGenerate}
          onGenerate={handleGenerate}
        />
        <VoicePanel {...sharedProps} />
        <OutputPanel
          latestOutput={latestOutput}
          latestOutputVoice={latestOutputVoice}
          latestJob={latestJob}
          latestJobVoice={latestJobVoice}
          activeCount={activeTtsCount}
          latestFailedJob={latestFailedTtsJob}
          jobsError={jobsError}
          onRetryJobs={() => {
            void ttsJobsQuery.refetch()
          }}
        />
      </div>

      <div className="hidden min-w-0 gap-3 xl:grid xl:grid-cols-[minmax(0,1fr)_380px]">
        <section className="min-w-0 space-y-3">
          <ScriptEditor
            script={script}
            language={selectedLanguage}
            onScriptChange={setScript}
            onClear={() => setScript('')}
            onImportText={() => importInputRef.current?.click()}
            canGenerate={canGenerate}
            onGenerate={handleGenerate}
          />
          <OutputPanel
            latestOutput={latestOutput}
            latestOutputVoice={latestOutputVoice}
            latestJob={latestJob}
            latestJobVoice={latestJobVoice}
            activeCount={activeTtsCount}
            latestFailedJob={latestFailedTtsJob}
            jobsError={jobsError}
            onRetryJobs={() => {
              void ttsJobsQuery.refetch()
            }}
          />
        </section>
        <aside className="min-w-0 space-y-3">
          <VoicePanel {...sharedProps} />
        </aside>
      </div>
    </>
  )
}

function FirstRunChecklist({
  runtimeReady,
  runtimeLoading,
  voiceReady,
  scriptReady,
  renderQueued,
  outputReady,
  canGenerate,
  onUseSample,
  onGenerate,
}: {
  runtimeReady: boolean
  runtimeLoading: boolean
  voiceReady: boolean
  scriptReady: boolean
  renderQueued: boolean
  outputReady: boolean
  canGenerate: boolean
  onUseSample: () => void
  onGenerate: () => void
}) {
  const steps = [
    {
      label: 'Runtime',
      done: runtimeReady,
      value: runtimeLoading ? 'Checking' : runtimeReady ? 'Ready' : 'Needs setup',
      action: !runtimeReady
        ? { label: 'Settings', onClick: () => { window.location.hash = '/settings' } }
        : null,
    },
    {
      label: 'Voice',
      done: voiceReady,
      value: voiceReady ? 'Profile ready' : 'Import one',
      action: !voiceReady
        ? { label: 'Voices', onClick: () => { window.location.hash = '/voices' } }
        : null,
    },
    {
      label: 'Script',
      done: scriptReady,
      value: scriptReady ? 'Text ready' : 'Add text',
      action: !scriptReady ? { label: 'Use sample', onClick: onUseSample } : null,
    },
    {
      label: 'Render',
      done: renderQueued,
      value: renderQueued ? 'Queued' : 'Not queued',
      action: !renderQueued && canGenerate ? { label: 'Generate', onClick: onGenerate } : null,
    },
    {
      label: 'Output',
      done: outputReady,
      value: outputReady ? 'Playable' : 'Waiting',
      action: !outputReady && renderQueued
        ? { label: 'Jobs', onClick: () => { window.location.hash = '/jobs' } }
        : null,
    },
  ]
  const completed = steps.filter((step) => step.done).length

  if (completed === steps.length) {
    return null
  }

  return (
    <section className="mb-3 min-w-0 rounded-md border border-studio-border bg-white p-3">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <div className="text-sm font-semibold text-slate-950">First output checklist</div>
          <div className="mt-1 text-xs text-slate-600">
            {completed}/{steps.length} ready
          </div>
        </div>
        <div className="flex min-w-0 flex-wrap gap-2">
          {steps.map((step) => (
            <div
              className="flex min-h-8 max-w-full min-w-0 items-center gap-2 rounded-md border border-studio-border bg-white px-2.5 text-xs"
              key={step.label}
            >
              {step.done ? (
                <CheckCircle2 className="size-4 shrink-0 text-emerald-600" />
              ) : (
                <Circle className="size-4 shrink-0 text-slate-400" />
              )}
              <span className="font-semibold text-slate-950">{step.label}</span>
              <span className="hidden font-medium text-slate-500 sm:inline">{step.value}</span>
              {step.action ? (
                <button
                  className="inline-flex shrink-0 items-center gap-1 font-semibold text-blue-700 hover:text-blue-900"
                  type="button"
                  onClick={step.action.onClick}
                >
                  {step.action.label}
                  <ArrowRight className="size-3" />
                </button>
              ) : null}
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

type VoicePanelProps = {
  voices: Voice[]
  selectedVoice: Voice | undefined
  selectedVoiceId: string
  setSelectedVoiceId: (voiceId: string) => void
  speedPercent: number
  setSpeedPercent: (value: number) => void
  renderMode: RenderMode
  setRenderMode: (value: RenderMode) => void
  selectedLanguage: VoiceLanguage
  selectedVoiceLanguage: VoiceLanguage
  languageWarning: string | null
  runtimeLanguageWarning: string | null
  modelReadinessMessage: string | null
  onLanguageChange: (language: VoiceLanguage) => void
  scriptReady: boolean
  canGenerate: boolean
  generatePending: boolean
  generateSuccess: boolean
  generateError: string | null
  voicesError: string | null
  onRetryVoices: () => void
  onGenerate: () => void
}

function VoicePanel({
  voices,
  selectedVoice,
  selectedVoiceId,
  setSelectedVoiceId,
  speedPercent,
  setSpeedPercent,
  renderMode,
  setRenderMode,
  selectedLanguage,
  selectedVoiceLanguage,
  languageWarning,
  runtimeLanguageWarning,
  modelReadinessMessage,
  onLanguageChange,
  scriptReady,
  canGenerate,
  generatePending,
  generateSuccess,
  generateError,
  voicesError,
  onRetryVoices,
  onGenerate,
}: VoicePanelProps) {
  return (
    <Card>
      <CardHeader>
        <div>
          <div className="text-sm font-semibold text-slate-950">Voice and render</div>
          <div className="mt-1 text-xs text-slate-600">Settings for the next audio job.</div>
        </div>
        <SlidersHorizontal className="size-5 text-slate-500" />
      </CardHeader>
      <CardContent className="space-y-3">
        {voicesError ? (
          <QueryErrorState
            compact
            title="Unable to load voices"
            message={voicesError}
            onRetry={onRetryVoices}
          />
        ) : voices.length === 0 ? (
          <div className="rounded-md border border-dashed border-amber-300 bg-amber-50 p-3">
            <div className="text-sm font-semibold text-slate-950">No voice profiles yet</div>
            <p className="mt-1 text-xs leading-5 text-slate-700">
              Import a reference recording before rendering with ZipVoice.
            </p>
            <Button className="mt-3 w-full" onClick={() => { window.location.hash = '/voices' }}>
              Import a voice
            </Button>
          </div>
        ) : (
          <>
            <label className="block">
              <span className="mb-2 block text-xs font-semibold text-slate-700">
                Voice
              </span>
              <select
                value={selectedVoiceId}
                onChange={(event) => setSelectedVoiceId(event.target.value)}
                className="h-8 w-full rounded-md border border-slate-300 bg-white px-2.5 text-xs font-medium text-slate-950 outline-none transition-colors focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
              >
                {voices.map((voice) => (
                  <option key={voice.voice_id} value={voice.voice_id}>
                    {voice.name}
                  </option>
                ))}
              </select>
            </label>

            <VoicePreview voice={selectedVoice} />

            <LanguageControl
              value={selectedLanguage}
              voiceLanguage={selectedVoiceLanguage}
              onChange={onLanguageChange}
            />
            {runtimeLanguageWarning ? (
              <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs font-medium leading-5 text-red-700">
                {runtimeLanguageWarning}
              </div>
            ) : null}
            {modelReadinessMessage ? (
              <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-medium leading-5 text-amber-800">
                {modelReadinessMessage}
              </div>
            ) : null}
            {languageWarning ? (
              <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-medium leading-5 text-amber-800">
                {languageWarning}
              </div>
            ) : null}

            <ControlSlider
              label="Speed"
              min="Slower"
              max="Faster"
              value={speedPercent}
              valueLabel={`${speedFromPercent(speedPercent).toFixed(2)}x`}
              onChange={setSpeedPercent}
            />
            <RenderModeControl value={renderMode} onChange={setRenderMode} />

            <GenerateActionContent
              selectedVoice={selectedVoice}
              scriptReady={scriptReady}
              canGenerate={canGenerate}
              generatePending={generatePending}
              generateSuccess={generateSuccess}
              generateError={generateError}
              blockedReason={runtimeLanguageWarning}
              onGenerate={onGenerate}
            />
          </>
        )}
      </CardContent>
    </Card>
  )
}

function GenerateActionContent({
  selectedVoice,
  scriptReady,
  canGenerate,
  generatePending,
  generateSuccess,
  generateError,
  blockedReason,
  onGenerate,
}: {
  selectedVoice: Voice | undefined
  scriptReady: boolean
  canGenerate: boolean
  generatePending: boolean
  generateSuccess: boolean
  generateError: string | null
  blockedReason: string | null
  onGenerate: () => void
}) {
  const helper = !selectedVoice
    ? 'Import a voice profile before rendering.'
    : !scriptReady
      ? 'Add a script to enable rendering.'
      : blockedReason
        ? 'Select a configured render language.'
        : 'Queue a local ZipVoice render.'

  return (
    <div className="space-y-2.5">
      {generateError ? (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold leading-5 text-red-700">
          {generateError}
        </div>
      ) : null}

      {generateSuccess ? (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-700">
          Job queued. Output refreshes automatically.
        </div>
      ) : null}

      <div className="text-xs font-medium text-slate-600">{helper}</div>
      <Button className="w-full" disabled={!canGenerate} onClick={onGenerate}>
        {generatePending ? (
          <Loader2 className="size-4 animate-spin" />
        ) : (
          <SendHorizontal className="size-4" />
        )}
        {generatePending ? 'Queueing' : 'Generate audio'}
      </Button>
    </div>
  )
}

function ScriptEditor({
  script,
  language,
  onScriptChange,
  onClear,
  onImportText,
  canGenerate,
  onGenerate,
}: {
  script: string
  language: VoiceLanguage
  onScriptChange: (value: string) => void
  onClear: () => void
  onImportText: () => void
  canGenerate: boolean
  onGenerate: () => void
}) {
  const suggestions = promptSuggestions[language]
  const wordCount = script.trim() ? script.trim().split(/\s+/).length : 0
  return (
    <Card className="min-w-0 overflow-hidden">
      <CardHeader className="flex-wrap border-b border-slate-200 bg-white">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-slate-950">Script editor</div>
          <div className="mt-1 text-xs text-slate-600">One paragraph per take keeps review clean.</div>
        </div>
        <div className="flex w-full shrink-0 gap-2 sm:w-auto">
          <Button
            className="flex-1 sm:flex-none"
            size="sm"
            variant="ghost"
            disabled={!script}
            onClick={onClear}
          >
            <Eraser className="size-4" />
            Clear
          </Button>
          <Button className="flex-1 sm:flex-none" size="sm" variant="secondary" onClick={onImportText}>
            <Upload className="size-4" />
            Import text
          </Button>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <textarea
          value={script}
          onChange={(event) => onScriptChange(event.target.value)}
          onKeyDown={(event) => {
            if ((event.ctrlKey || event.metaKey) && event.key === 'Enter' && canGenerate) {
              event.preventDefault()
              onGenerate()
            }
          }}
          placeholder={
            language === 'vi'
              ? 'Start typing here or paste any Vietnamese script...'
              : 'Start typing here or paste any English script...'
          }
          className="min-h-[180px] w-full resize-y border-0 bg-white p-3 text-sm leading-6 text-slate-900 outline-none placeholder:text-slate-500 sm:min-h-[260px] lg:min-h-[300px] xl:min-h-[320px]"
        />
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-200 bg-neutral-50 px-3 py-2 text-xs text-neutral-500">
          <span>{script.length.toLocaleString()} characters</span>
          <span>{wordCount.toLocaleString()} words</span>
          <Badge variant="muted">{voiceLanguageShortLabel(language)}</Badge>
        </div>
        <div className="border-t border-slate-200 bg-white px-2.5 py-2">
          <div className="flex min-w-0 flex-wrap gap-2">
            {suggestions.map((prompt) => (
              <button
                key={prompt}
                type="button"
                title={prompt}
                onClick={() => onScriptChange(prompt)}
                className="w-full min-w-0 max-w-full flex-none truncate rounded-md border border-slate-200 bg-white px-2 py-1.5 text-left text-xs font-medium leading-4 text-slate-700 transition-colors hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700 sm:w-auto sm:max-w-[240px] sm:flex-1"
              >
                {prompt}
              </button>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function OutputPanel({
  latestOutput,
  latestOutputVoice,
  latestJob,
  latestJobVoice,
  activeCount,
  latestFailedJob,
  jobsError,
  onRetryJobs,
}: {
  latestOutput: TtsJob | null
  latestOutputVoice: Voice | undefined
  latestJob: TtsJob | null
  latestJobVoice: Voice | undefined
  activeCount: number
  latestFailedJob: TtsJob | null
  jobsError: string | null
  onRetryJobs: () => void
}) {
  return (
    <Card className="overflow-hidden">
      <CardHeader>
        <div>
          <div className="text-sm font-semibold text-slate-950">Output and queue</div>
          <div className="mt-1 text-xs text-slate-600">Latest local render and job state.</div>
        </div>
        <Button
          aria-label="Open jobs"
          title="Open jobs"
          size="icon"
          variant="ghost"
          onClick={() => { window.location.hash = '/jobs' }}
        >
          <ArrowUpRight className="size-4" />
        </Button>
      </CardHeader>
      <CardContent>
        {latestJob ? (
          <div className="mb-3 rounded-md border border-neutral-200 bg-neutral-50 px-3 py-2.5">
            <div className="flex min-w-0 items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="truncate text-xs font-semibold text-neutral-900">
                  {latestJobVoice?.name ?? 'Voice render'}
                </div>
                <div className="mt-1 truncate text-xs text-neutral-500">
                  {compactId(latestJob.job_id)} / {formatDateTime(latestJob.created_at)}
                </div>
              </div>
              <Badge variant={jobBadgeVariant(latestJob.status)}>{formatJobStatus(latestJob.status)}</Badge>
            </div>
          </div>
        ) : null}
        {activeCount > 0 || latestFailedJob ? (
          <div className="mb-3 grid grid-cols-1 gap-2">
            {activeCount > 0 ? (
              <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-800">
                {activeCount} render {activeCount === 1 ? 'job is' : 'jobs are'} active.
              </div>
            ) : null}
            {latestFailedJob ? (
              <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold leading-5 text-red-700">
                Latest failed job {compactId(latestFailedJob.job_id)}: {latestFailedJob.error ?? 'Render failed.'}
              </div>
            ) : null}
          </div>
        ) : null}
        {jobsError ? (
          <QueryErrorState
            compact
            title="Unable to load outputs"
            message={jobsError}
            onRetry={onRetryJobs}
          />
        ) : latestOutput ? (
          <div className="rounded-md border border-slate-200 bg-white p-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-slate-950">
                  {latestOutputVoice?.name ?? 'Generated voice'}
                </div>
                <div className="mt-1 text-xs font-medium text-slate-600">
                  {latestOutput.duration_seconds
                    ? formatDuration(latestOutput.duration_seconds)
                    : 'Duration pending'}{' '}
                  {' - '}
                  {formatDateTime(latestOutput.completed_at ?? latestOutput.created_at)}
                </div>
              </div>
              <Badge variant={latestOutput.status === 'succeeded' ? 'success' : 'warning'}>
                {latestOutput.status}
              </Badge>
            </div>
            <div className="mt-3 grid grid-cols-3 gap-2">
              <OutputMeta
                label="Duration"
                value={latestOutput.duration_seconds ? formatDuration(latestOutput.duration_seconds) : 'Pending'}
              />
              <OutputMeta
                label="Sample rate"
                value={latestOutput.sample_rate ? formatSampleRate(latestOutput.sample_rate) : 'Pending'}
              />
              <OutputMeta label="Language" value={voiceLanguageShortLabel(latestOutput.language)} />
            </div>
            {latestOutput.audio_url ? (
              <audio className="mt-3 w-full" controls src={latestOutput.audio_url} />
            ) : null}
            <div className="mt-3 flex items-center justify-between gap-3">
              <span className="truncate text-xs font-medium text-slate-500">
                Job {compactId(latestOutput.job_id)}
              </span>
              {latestOutput.audio_url ? (
                <a
                  className="inline-flex h-8 shrink-0 items-center justify-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 text-xs font-medium text-slate-800 transition-colors hover:bg-slate-50"
                  href={latestOutput.audio_url}
                  download
                >
                  <Download className="size-4" />
                  Download
                </a>
              ) : null}
            </div>
          </div>
        ) : (
          <div className="rounded-md border border-dashed border-slate-300 bg-white p-4 text-center">
            <WandSparkles className="mx-auto size-7 text-slate-500" />
            <div className="mt-3 text-sm font-semibold text-slate-800">No output yet</div>
            <p className="mt-1 text-xs leading-5 text-slate-600">
              Generated clips will appear here with playback and export.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function VoicePreview({ voice }: { voice: Voice | undefined }) {
  const name = voice?.name ?? 'No voice selected'
  return (
    <div className="rounded-md border border-slate-200 bg-white p-2.5">
      <div className="flex items-center gap-3">
        <div className="grid size-8 place-items-center rounded-md border border-slate-200 bg-white text-xs font-semibold text-blue-700">
          {name.slice(0, 1).toUpperCase()}
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-slate-950">{name}</div>
          <div className="mt-0.5 flex min-w-0 items-center gap-1.5">
            <span className="shrink-0 rounded-full border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[10px] font-bold text-slate-600">
              {voiceLanguageShortLabel(voice?.language)}
            </span>
            <span className="truncate text-xs font-medium text-slate-600">
              {formatReferenceSource(voice?.reference_text_source)}
            </span>
          </div>
        </div>
      </div>
      {voice?.reference_audio_url ? (
        <audio className="mt-2 h-8 w-full" controls preload="metadata" src={voice.reference_audio_url} />
      ) : null}
    </div>
  )
}

function LanguageControl({
  value,
  voiceLanguage,
  onChange,
}: {
  value: VoiceLanguage
  voiceLanguage: VoiceLanguage
  onChange: (language: VoiceLanguage) => void
}) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-2.5">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-700">
          <Languages className="size-4 text-slate-500" />
          Language
        </div>
        <span className="min-w-0 truncate text-xs font-medium text-slate-600">
          Voice: {voiceLanguageLabel(voiceLanguage)}
        </span>
      </div>
      <SegmentedControl
        equalWidth
        options={VOICE_LANGUAGES.map((item) => ({
          value: item.value,
          label: item.label,
          title: item.helper,
        }))}
        value={value}
        onChange={onChange}
      />
    </div>
  )
}

function RenderModeControl({
  value,
  onChange,
}: {
  value: RenderMode
  onChange: (value: RenderMode) => void
}) {
  const profile = renderProfiles[value]
  return (
    <div className="rounded-md border border-slate-200 bg-white p-2.5">
      <div className="mb-2 flex items-center justify-between gap-2 text-xs font-semibold text-slate-700">
        <span>Render mode</span>
        <span className="text-slate-500">{profile.numSteps} steps</span>
      </div>
      <SegmentedControl
        equalWidth
        options={(Object.keys(renderProfiles) as RenderMode[]).map((mode) => ({
          value: mode,
          label: renderProfiles[mode].label,
          title: renderProfiles[mode].helper,
        }))}
        value={value}
        onChange={onChange}
      />
      <p className="mt-2 text-xs font-medium leading-5 text-slate-600">{profile.helper}</p>
    </div>
  )
}

function ControlSlider({
  label,
  min,
  max,
  value,
  valueLabel,
  onChange,
}: {
  label: string
  min: string
  max: string
  value: number
  valueLabel: string
  onChange: (value: number) => void
}) {
  return (
    <div>
      <div className="flex items-center justify-between text-xs font-semibold text-slate-700">
        <span>{label}</span>
        <span>{valueLabel}</span>
      </div>
      <input
        aria-label={label}
        className="mt-2 h-2 w-full accent-blue-600"
        min={50}
        max={150}
        step={1}
        type="range"
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
      <div className="mt-1 flex items-center justify-between text-xs font-semibold text-slate-500">
        <span>{min}</span>
        <span>{max}</span>
      </div>
    </div>
  )
}

function OutputMeta({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-md border border-neutral-200 bg-neutral-50 px-2 py-1.5">
      <div className="truncate text-xs font-semibold text-neutral-900">{value}</div>
      <div className="mt-0.5 truncate text-[11px] text-neutral-500">{label}</div>
    </div>
  )
}

function generateMutationJob(jobs: TtsJob[], mutationJob: TtsJob | undefined): TtsJob | null {
  if (!mutationJob) {
    return jobs[0] ?? null
  }
  return jobs.find((job) => job.job_id === mutationJob.job_id) ?? mutationJob
}

function jobBadgeVariant(status: TtsJob['status']): 'success' | 'warning' | 'danger' | 'muted' {
  if (status === 'succeeded') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'cancelled') return 'muted'
  return 'warning'
}

function formatJobStatus(status: TtsJob['status']) {
  return status.charAt(0).toUpperCase() + status.slice(1)
}

function formatReferenceSource(source: string | undefined) {
  if (source === 'asr') return 'Auto transcript'
  if (source === 'user') return 'Manual transcript'
  return 'Reference profile'
}

function formatSampleRate(sampleRate: number) {
  return sampleRate >= 1000 ? `${(sampleRate / 1000).toFixed(sampleRate % 1000 === 0 ? 0 : 1)} kHz` : `${sampleRate} Hz`
}

function speedFromPercent(value: number) {
  return value / 100
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function getLanguageWarning(
  script: string,
  selectedLanguage: VoiceLanguage,
  selectedVoice: Voice | undefined,
) {
  if (selectedVoice && normalizeVoiceLanguage(selectedVoice.language) !== selectedLanguage) {
    return `Selected voice is tagged ${voiceLanguageLabel(selectedVoice.language)}, but render language is ${voiceLanguageLabel(selectedLanguage)}.`
  }

  if (selectedLanguage === 'en' && hasVietnameseDiacritics(script)) {
    return 'This script contains Vietnamese diacritics while English is selected.'
  }

  return null
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
  return `${voiceLanguageLabel(selectedLanguage)} TTS is not configured on this backend. Available runtime: ${available}.`
}

function getModelReadinessMessage({
  selectedLanguage,
  configuredLanguages,
  loadedLanguages,
  statusError,
  kind,
}: {
  selectedLanguage: VoiceLanguage
  configuredLanguages: string[] | undefined
  loadedLanguages: string[] | undefined
  statusError: unknown
  kind: 'ASR' | 'TTS'
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

  return `${voiceLanguageLabel(selectedLanguage)} ${kind} model is cold. The next request may spend extra time loading local assets.`
}
