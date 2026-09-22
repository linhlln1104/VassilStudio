import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Activity,
  ArrowRight,
  AudioLines,
  Check,
  CheckCircle2,
  Copy,
  Download,
  Languages,
  Loader2,
  Mic,
  MicOff,
  RotateCcw,
  Square,
  Trash2,
  Wifi,
  WifiOff,
} from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { SegmentedControl } from '@/components/ui/segmented-control'
import { api, getRequestApiKey } from '@/lib/api'
import {
  VOICE_LANGUAGES,
  normalizeVoiceLanguage,
  type VoiceLanguage,
  voiceLanguageLabel,
  voiceLanguageShortLabel,
} from '@/lib/language'
import { getPreferredLanguage, setPendingScript, setPreferredLanguage } from '@/lib/studio-preferences'
import { cn } from '@/lib/utils'

type SessionState = 'idle' | 'connecting' | 'listening' | 'stopping' | 'error'
const FINALIZATION_TIMEOUT_MS = 30_000
const INCOMPLETE_TRANSCRIPT_MESSAGE = 'The final transcript was not confirmed. The text received so far is preserved; the last audio may be missing. Copy or download it before starting again.'

type RealtimeMessage = {
  type: string
  protocol?: string
  sample_rate?: number
  encoding?: string
  chunk_seconds?: number
  language?: string
  sequence?: number
  text?: string
  final?: boolean
  skipped?: boolean
  reason?: string
  duration_seconds?: number
  rms?: number
  message?: string
}

type TranscriptEntry = {
  id: string
  text: string
  language: VoiceLanguage
  final: boolean
  skipped: boolean
  durationSeconds: number | null
  rms: number | null
}

export function RealtimeView() {
  const [sessionState, setSessionState] = useState<SessionState>('idle')
  const [error, setError] = useState('')
  const [protocol, setProtocol] = useState<RealtimeMessage | null>(null)
  const [transcripts, setTranscripts] = useState<TranscriptEntry[]>([])
  const [transcriptText, setTranscriptText] = useState('')
  const [copied, setCopied] = useState(false)
  const [inputRms, setInputRms] = useState(0)
  const [sessionElapsedSeconds, setSessionElapsedSeconds] = useState(0)
  const [selectedLanguage, setSelectedLanguage] = useState<VoiceLanguage>(() =>
    normalizeVoiceLanguage(getPreferredLanguage()),
  )
  const websocketRef = useRef<WebSocket | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const contextRef = useRef<AudioContext | null>(null)
  const processorRef = useRef<ScriptProcessorNode | null>(null)
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null)
  const gainRef = useRef<GainNode | null>(null)
  const stopTimeoutRef = useRef<number | null>(null)
  const finalizingRef = useRef(false)
  const sessionStartedAtRef = useRef<number | null>(null)

  const healthQuery = useQuery({
    queryKey: ['health'],
    queryFn: api.health,
    refetchInterval: 10000,
  })
  const modelStatusQuery = useQuery({
    queryKey: ['model-status'],
    queryFn: api.modelStatus,
    staleTime: 30000,
    refetchInterval: 30000,
  })

  const backendOnline = healthQuery.data?.status === 'ok'
  const microphoneSupported =
    typeof navigator !== 'undefined' && Boolean(navigator.mediaDevices?.getUserMedia)
  const spokenChunks = transcripts.filter((entry) => !entry.skipped && entry.text).length
  const capturedDuration = transcripts.reduce((total, entry) => total + (entry.durationSeconds ?? 0), 0)
  const downloadHref = transcriptText
    ? `data:text/plain;charset=utf-8,${encodeURIComponent(transcriptText)}`
    : undefined
  const runtimeLanguageWarning = getRuntimeLanguageWarning(
    selectedLanguage,
    modelStatusQuery.data?.runtime.asr_configured_languages,
  )
  const modelReadinessMessage = getModelReadinessMessage(
    selectedLanguage,
    modelStatusQuery.data?.runtime.asr_configured_languages,
    modelStatusQuery.data?.runtime.asr_loaded_languages,
  )
  const selectedModelLoaded = new Set(
    (modelStatusQuery.data?.runtime.asr_loaded_languages ?? []).map((language) =>
      normalizeVoiceLanguage(language),
    ),
  ).has(selectedLanguage)
  const sessionModelActive = sessionState === 'listening' || sessionState === 'stopping'
  const selectedModelReady = selectedModelLoaded || sessionModelActive
  const selectedModelDetail = sessionModelActive
    ? 'Active for this session'
    : modelStatusQuery.isError
      ? 'Status unavailable'
      : selectedModelLoaded
        ? 'Loaded in memory'
        : runtimeLanguageWarning
          ? 'Not configured'
          : 'Cold start expected'
  const inputDb = Math.max(-60, Math.min(0, 20 * Math.log10(Math.max(inputRms, 0.001))))
  const inputLevel = Math.max(0, Math.min(1, (inputDb + 60) / 60))

  useEffect(() => {
    if (sessionState !== 'listening') return

    const updateElapsedTime = () => {
      if (sessionStartedAtRef.current !== null) {
        setSessionElapsedSeconds((Date.now() - sessionStartedAtRef.current) / 1000)
      }
    }
    updateElapsedTime()
    const interval = window.setInterval(updateElapsedTime, 250)
    return () => window.clearInterval(interval)
  }, [sessionState])

  const finalizeSessionTimer = () => {
    if (sessionStartedAtRef.current !== null) {
      setSessionElapsedSeconds((Date.now() - sessionStartedAtRef.current) / 1000)
      sessionStartedAtRef.current = null
    }
  }

  const cleanupMediaResources = () => {
    processorRef.current?.disconnect()
    sourceRef.current?.disconnect()
    gainRef.current?.disconnect()
    streamRef.current?.getTracks().forEach((track) => track.stop())
    void contextRef.current?.close()

    processorRef.current = null
    sourceRef.current = null
    gainRef.current = null
    streamRef.current = null
    contextRef.current = null
  }

  const clearStopTimeout = () => {
    if (stopTimeoutRef.current !== null) {
      window.clearTimeout(stopTimeoutRef.current)
      stopTimeoutRef.current = null
    }
  }

  const cleanupRealtimeResources = () => {
    clearStopTimeout()
    const websocket = websocketRef.current
    websocketRef.current = null
    if (websocket && websocket.readyState !== WebSocket.CLOSED) {
      websocket.close()
    }
    cleanupMediaResources()
  }

  useEffect(() => () => cleanupRealtimeResources(), [])

  const startSession = () => {
    if (websocketRef.current) return
    if (!microphoneSupported) {
      setError('This browser does not expose microphone capture.')
      setSessionState('error')
      return
    }

    cleanupRealtimeResources()
    finalizingRef.current = false
    setError('')
    setProtocol(null)
    setInputRms(0)
    setSessionElapsedSeconds(0)
    sessionStartedAtRef.current = null
    setSessionState('connecting')

    let websocket: WebSocket
    try {
      websocket = new WebSocket(buildRealtimeWebSocketUrl(selectedLanguage))
    } catch (connectionError) {
      setError(
        connectionError instanceof Error
          ? connectionError.message
          : 'Realtime websocket URL is invalid.',
      )
      setSessionState('error')
      return
    }
    websocketRef.current = websocket
    websocket.binaryType = 'arraybuffer'

    websocket.onmessage = (event) => {
      if (websocketRef.current !== websocket) return
      try {
        const message = JSON.parse(String(event.data)) as RealtimeMessage
        handleRealtimeMessage(message, websocket)
      } catch {
        setError('Realtime server returned an unreadable message.')
        setSessionState('error')
        finalizeSessionTimer()
        cleanupRealtimeResources()
      }
    }

    websocket.onerror = () => {
      if (websocketRef.current !== websocket) {
        return
      }
      setError(finalizingRef.current ? INCOMPLETE_TRANSCRIPT_MESSAGE : 'Realtime connection failed. Text received so far is preserved.')
      setSessionState('error')
      setInputRms(0)
      finalizeSessionTimer()
      cleanupRealtimeResources()
    }

    websocket.onclose = () => {
      if (websocketRef.current !== websocket) {
        return
      }
      clearStopTimeout()
      websocketRef.current = null
      cleanupMediaResources()
      setInputRms(0)
      finalizeSessionTimer()
      setError(finalizingRef.current ? INCOMPLETE_TRANSCRIPT_MESSAGE : 'Realtime connection closed unexpectedly. Text received so far is preserved.')
      setSessionState('error')
    }
  }

  const handleRealtimeMessage = (message: RealtimeMessage, websocket: WebSocket) => {
    if (message.type === 'ready' || message.type === 'configured') {
      setProtocol(message)
      if (message.type === 'ready' && !finalizingRef.current) {
        void startMicrophone(websocket, message.sample_rate ?? 16000)
      }
      return
    }

    if (message.type === 'transcript') {
      const recognizedText = message.text?.trim() ?? ''
      if (recognizedText) {
        setTranscriptText((current) => current ? `${current} ${recognizedText}` : recognizedText)
      }
      setTranscripts((current) =>
        [
          {
            id: `${message.sequence ?? current.length + 1}-${Date.now()}`,
            text: message.text ?? '',
            language: normalizeVoiceLanguage(message.language),
            final: Boolean(message.final),
            skipped: Boolean(message.skipped),
            durationSeconds: message.duration_seconds ?? null,
            rms: message.rms ?? null,
          },
          ...current,
        ],
      )
      return
    }

    if (message.type === 'cleared') {
      setTranscripts([])
      setTranscriptText('')
      return
    }

    if (message.type === 'closed') {
      if (!finalizingRef.current) {
        setError(INCOMPLETE_TRANSCRIPT_MESSAGE)
        setSessionState('error')
        cleanupRealtimeResources()
        return
      }
      finalizingRef.current = false
      setInputRms(0)
      finalizeSessionTimer()
      cleanupRealtimeResources()
      setSessionState('idle')
      return
    }

    if (message.type === 'error') {
      setError(message.message ?? 'Realtime session failed.')
      setSessionState('error')
      setInputRms(0)
      finalizeSessionTimer()
      cleanupRealtimeResources()
    }
  }

  const startMicrophone = async (websocket: WebSocket, targetSampleRate: number) => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      })
      if (websocketRef.current !== websocket || websocket.readyState !== WebSocket.OPEN || finalizingRef.current) {
        stream.getTracks().forEach((track) => track.stop())
        return
      }
      streamRef.current = stream
      const AudioContextCtor =
        window.AudioContext ??
        (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      if (!AudioContextCtor) {
        throw new Error('This browser does not expose Web Audio capture.')
      }
      const audioContext = new AudioContextCtor()
      contextRef.current = audioContext
      const source = audioContext.createMediaStreamSource(stream)
      const processor = audioContext.createScriptProcessor(4096, 1, 1)
      const gain = audioContext.createGain()

      gain.gain.value = 0
      processor.onaudioprocess = (event) => {
        if (websocket.readyState !== WebSocket.OPEN) {
          return
        }
        const input = event.inputBuffer.getChannelData(0)
        let energy = 0
        for (let index = 0; index < input.length; index += 1) {
          energy += input[index] * input[index]
        }
        setInputRms(Math.sqrt(energy / input.length))
        const samples = downsampleFloat32(input, audioContext.sampleRate, targetSampleRate)
        if (samples.length > 0) {
          websocket.send(samples.buffer)
        }
      }

      source.connect(processor)
      processor.connect(gain)
      gain.connect(audioContext.destination)

      streamRef.current = stream
      contextRef.current = audioContext
      sourceRef.current = source
      processorRef.current = processor
      gainRef.current = gain
      sessionStartedAtRef.current = Date.now()
      setSessionElapsedSeconds(0)
      setSessionState('listening')
    } catch (microphoneError) {
      if (websocketRef.current !== websocket || finalizingRef.current) return
      setError(
        microphoneError instanceof Error
          ? microphoneError.message
          : 'Microphone permission was denied or unavailable.',
      )
      setSessionState('error')
      setInputRms(0)
      finalizeSessionTimer()
      cleanupRealtimeResources()
    }
  }

  const stopSession = () => {
    setSessionState('stopping')
    setInputRms(0)
    finalizeSessionTimer()
    const websocket = websocketRef.current
    cleanupMediaResources()
    if (websocket?.readyState === WebSocket.OPEN) {
      finalizingRef.current = true
      clearStopTimeout()
      stopTimeoutRef.current = window.setTimeout(() => {
        if (websocketRef.current === websocket) {
          cleanupRealtimeResources()
          setError(INCOMPLETE_TRANSCRIPT_MESSAGE)
          setSessionState('error')
        }
      }, FINALIZATION_TIMEOUT_MS)
      websocket.send(JSON.stringify({ type: 'close' }))
      return
    }
    cleanupRealtimeResources()
    setSessionState('idle')
  }

  const clearSession = () => {
    setTranscripts([])
    setTranscriptText('')
    setCopied(false)
    const websocket = websocketRef.current
    if (websocket?.readyState === WebSocket.OPEN) {
      websocket.send(JSON.stringify({ type: 'clear' }))
    }
  }

  const handleLanguageSelect = (language: VoiceLanguage) => {
    setSelectedLanguage(language)
    setPreferredLanguage(language)
    setProtocol(null)
  }

  const handleCopy = async () => {
    if (!transcriptText || typeof navigator === 'undefined') {
      return
    }
    try {
      await navigator.clipboard.writeText(transcriptText)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1800)
    } catch {
      setError('Clipboard access failed. Download the transcript instead.')
    }
  }

  const handleUseInGenerate = () => {
    if (!transcriptText) {
      return
    }
    setPendingScript(transcriptText)
    setPreferredLanguage(selectedLanguage)
    window.location.hash = '/generate'
  }

  return (
    <div className="grid min-w-0 grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1fr)_360px]">
      <section className="min-w-0 space-y-3">
        <Card>
          <CardHeader className="flex-wrap">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <div className="text-sm font-semibold text-slate-950">Realtime session</div>
                <SessionStatusBadge state={sessionState} />
              </div>
              <div className="mt-1 text-xs text-slate-600">
                Stream microphone audio to {voiceLanguageLabel(selectedLanguage)} ASR.
              </div>
            </div>
            <div className="flex w-full gap-2 sm:w-auto">
              {transcripts.length > 0 ? (
                <Button
                  className="w-8 shrink-0 px-0"
                  size="sm"
                  variant="secondary"
                  aria-label="Clear realtime transcript"
                  title="Clear realtime transcript"
                  disabled={sessionState === 'stopping'}
                  onClick={clearSession}
                >
                  <Trash2 className="size-4" />
                </Button>
              ) : null}
              {sessionState === 'listening' || sessionState === 'connecting' || sessionState === 'stopping' ? (
                <Button
                  className="min-w-0 flex-1 sm:flex-none"
                  variant="destructive"
                  disabled={sessionState === 'stopping'}
                  onClick={stopSession}
                >
                  {sessionState === 'stopping' || sessionState === 'connecting' ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <Square className="size-4" />
                  )}
                  {sessionState === 'stopping' ? 'Finalizing' : 'Stop and finalize'}
                </Button>
              ) : (
                <Button
                  className="min-w-0 flex-1 sm:flex-none"
                  disabled={!backendOnline || !microphoneSupported || Boolean(runtimeLanguageWarning)}
                  onClick={startSession}
                >
                  <Mic className="size-4" />
                  Start session
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent className="space-y-3 border-t border-slate-200">
            <LanguagePicker
              disabled={sessionState !== 'idle' && sessionState !== 'error'}
              value={selectedLanguage}
              configuredLanguages={modelStatusQuery.data?.runtime.asr_configured_languages}
              onChange={handleLanguageSelect}
            />
            <MicrophoneInputMonitor
              state={sessionState}
              inputDb={inputDb}
              inputLevel={inputLevel}
              elapsedSeconds={sessionElapsedSeconds}
            />
            {runtimeLanguageWarning ? (
              <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs font-medium leading-5 text-red-700">
                {runtimeLanguageWarning}
              </div>
            ) : modelReadinessMessage && sessionState !== 'listening' && sessionState !== 'stopping' ? (
              <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-medium leading-5 text-amber-800">
                {modelReadinessMessage}
              </div>
            ) : null}
            {!healthQuery.isLoading && !backendOnline ? (
              <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold leading-5 text-red-700">
                Realtime backend is unavailable. Check diagnostics before starting a session.
              </div>
            ) : null}
            {error ? (
              <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold leading-5 text-red-700" role="alert">
                {error}
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-wrap">
            <div>
              <div className="text-sm font-semibold text-slate-950">Live transcript</div>
              <div className="mt-1 text-xs text-slate-600">
                {spokenChunks > 0 ? `${spokenChunks} speech chunks / ${capturedDuration.toFixed(1)}s captured` : 'Combined recognition output'}
              </div>
            </div>
            {transcriptText ? (
              <div className="flex gap-2">
                <Button
                  className="w-8 px-0"
                  size="sm"
                  variant="secondary"
                  aria-label={copied ? 'Realtime transcript copied' : 'Copy realtime transcript'}
                  title={copied ? 'Copied' : 'Copy realtime transcript'}
                  onClick={() => { void handleCopy() }}
                >
                  {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
                </Button>
                <Button
                  className="w-8 px-0"
                  size="sm"
                  variant="secondary"
                  asChild
                  aria-label="Download realtime transcript"
                  title="Download realtime transcript"
                >
                  <a href={downloadHref} download={`vassil-realtime-${selectedLanguage}.txt`}>
                    <Download className="size-4" />
                  </a>
                </Button>
              </div>
            ) : null}
          </CardHeader>
          <CardContent>
            {transcriptText ? (
              <>
                <div className="min-h-[220px] whitespace-pre-wrap rounded-md border border-slate-200 bg-white p-3 text-sm leading-6 text-slate-900">
                  {transcriptText}
                </div>
                <Button className="mt-3 w-full" onClick={handleUseInGenerate}>
                  <AudioLines className="size-4" />
                  Use as Generate script
                  <ArrowRight className="size-4" />
                </Button>
              </>
            ) : (
              <div className="grid min-h-[220px] place-items-center rounded-md border border-dashed border-slate-300 bg-white p-4 text-center">
                <div>
                  {sessionState === 'listening' ? (
                    <Mic className="mx-auto size-6 text-blue-600" />
                  ) : (
                    <AudioLines className="mx-auto size-6 text-slate-400" />
                  )}
                  <div className="mt-2 text-sm font-semibold text-slate-950">
                    {sessionState === 'listening' ? 'Listening for speech' : 'No realtime transcript'}
                  </div>
                  <p className="mt-1 text-xs leading-5 text-slate-600">
                    {sessionState === 'listening' ? 'Recognition text will appear as chunks complete.' : 'Start a session when the microphone is ready.'}
                  </p>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        <section>
          <div className="mb-3 flex items-start justify-between gap-3 px-1">
            <div>
              <div className="text-sm font-semibold text-slate-950">Transcript segments</div>
              <div className="mt-1 text-xs text-slate-600">Newest recognition chunks appear first.</div>
            </div>
            <Badge variant="muted">{transcripts.length}</Badge>
          </div>
          {transcripts.length > 0 ? (
            <div className="space-y-2">
              {transcripts.slice(0, 20).map((entry) => (
                <article
                  key={entry.id}
                  className={cn(
                    'rounded-md border border-slate-200 bg-white p-3',
                    entry.skipped && 'text-slate-500',
                  )}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap gap-1.5">
                      <Badge variant={entry.final ? 'success' : entry.skipped ? 'muted' : 'default'}>
                        {entry.skipped ? 'Silence' : entry.final ? 'Final' : 'Live'}
                      </Badge>
                      <Badge variant="muted">{voiceLanguageShortLabel(entry.language)}</Badge>
                    </div>
                    <span className="text-xs font-semibold text-slate-600">
                      {entry.durationSeconds ? `${entry.durationSeconds.toFixed(2)}s` : 'Duration pending'}
                    </span>
                  </div>
                  <p className="mt-2 text-xs leading-5 text-slate-800">{entry.text || 'Silence skipped.'}</p>
                </article>
              ))}
              {transcripts.length > 20 ? (
                <div className="px-1 text-xs font-medium text-slate-500">Showing the latest 20 of {transcripts.length} chunks.</div>
              ) : null}
            </div>
          ) : (
            <div className="rounded-md border border-dashed border-slate-300 bg-white p-4 text-center">
              <Activity className="mx-auto size-6 text-slate-400" />
              <div className="mt-2 text-sm font-semibold text-slate-950">No transcript segments</div>
              <p className="mt-1 text-xs leading-5 text-slate-600">Speech and skipped silence chunks will be listed here.</p>
            </div>
          )}
        </section>
      </section>

      <aside className="space-y-3">
        <Card>
          <CardHeader>
            <div>
              <div className="text-sm font-semibold text-slate-950">Session status</div>
              <div className="mt-1 text-xs text-slate-600">Browser, model, and stream readiness.</div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-3 pb-3">
              <div
                className={cn(
                  'grid size-10 shrink-0 place-items-center rounded-md',
                  sessionState === 'listening' ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-600',
                  sessionState === 'error' && 'bg-red-50 text-red-700',
                )}
              >
                {sessionState === 'listening' ? <Mic className="size-5" /> : <MicOff className="size-5" />}
              </div>
              <div className="min-w-0">
                <div className="text-sm font-semibold text-slate-950">{sessionStateLabel(sessionState)}</div>
                <div className="mt-1 text-xs leading-5 text-slate-600">{sessionStateDescription(sessionState)}</div>
              </div>
            </div>
            <div className="grid grid-cols-3 divide-x divide-slate-200 border-y border-slate-200 py-3">
              <SessionMetric label="Chunks" value={transcripts.length.toString()} />
              <SessionMetric label="Speech" value={spokenChunks.toString()} />
              <SessionMetric label="Session" value={formatSessionTime(sessionElapsedSeconds)} />
            </div>
            <div className="divide-y divide-slate-200 pt-1">
              <ReadinessRow
                icon={backendOnline ? Wifi : WifiOff}
                label="Backend websocket"
                detail={healthQuery.isLoading ? 'Checking connection' : backendOnline ? 'Available' : 'Unavailable'}
                ready={Boolean(backendOnline)}
              />
              <ReadinessRow
                icon={microphoneSupported ? Mic : MicOff}
                label="Microphone capture"
                detail={microphoneSupported ? 'Browser API available' : 'Browser API unavailable'}
                ready={microphoneSupported}
              />
              <ReadinessRow
                icon={CheckCircle2}
                label={`${voiceLanguageShortLabel(selectedLanguage)} ASR model`}
                detail={selectedModelDetail}
                ready={selectedModelReady}
              />
              <ReadinessRow
                icon={RotateCcw}
                label="Stream protocol"
                detail={
                  protocol
                    ? `${protocol.encoding} / ${protocol.sample_rate} Hz / ${protocol.chunk_seconds}s`
                    : 'Negotiated after connect'
                }
                ready={Boolean(protocol)}
              />
            </div>
          </CardContent>
        </Card>
      </aside>
    </div>
  )
}

function MicrophoneInputMonitor({
  state,
  inputDb,
  inputLevel,
  elapsedSeconds,
}: {
  state: SessionState
  inputDb: number
  inputLevel: number
  elapsedSeconds: number
}) {
  if (state === 'idle' || state === 'error') return null

  const levelPercent = Math.round(inputLevel * 100)
  const levelColor = inputLevel > 0.9 ? 'bg-red-500' : inputLevel > 0.25 ? 'bg-emerald-500' : 'bg-blue-500'
  const stateLabel = state === 'connecting' ? 'Opening microphone' : state === 'stopping' ? 'Finalizing session' : 'Microphone input'

  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
      <div className="flex items-center justify-between gap-3 text-xs font-semibold">
        <span className="text-slate-700">{stateLabel}</span>
        <span className="flex shrink-0 items-center gap-3 font-mono tabular-nums text-slate-600">
          <span>{state === 'listening' ? `${Math.round(inputDb)} dB` : '-- dB'}</span>
          <span data-qa="session-time">{formatSessionTime(elapsedSeconds)}</span>
        </span>
      </div>
      <div
        data-qa="input-level-meter"
        className="mt-2 h-2 overflow-hidden rounded-sm bg-slate-200"
        role="meter"
        aria-label="Microphone input level"
        aria-valuemin={-60}
        aria-valuemax={0}
        aria-valuenow={Math.round(inputDb)}
        aria-valuetext={`${Math.round(inputDb)} decibels`}
      >
        <div
          className={cn('h-full transition-[width] duration-100', levelColor)}
          style={{ width: `${levelPercent}%` }}
        />
      </div>
    </div>
  )
}

function SessionMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 px-2 text-center">
      <div className="truncate text-sm font-semibold tabular-nums text-slate-950">{value}</div>
      <div className="mt-1 text-[10px] font-medium uppercase text-slate-500">{label}</div>
    </div>
  )
}

function formatSessionTime(value: number) {
  const totalSeconds = Math.max(0, Math.floor(value))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = String(totalSeconds % 60).padStart(2, '0')
  return `${minutes}:${seconds}`
}

function SessionStatusBadge({ state }: { state: SessionState }) {
  if (state === 'listening') {
    return <Badge variant="success">Listening</Badge>
  }
  if (state === 'connecting' || state === 'stopping') {
    return (
      <Badge variant="warning">
        <Loader2 className="mr-1 size-3 animate-spin" />
        {state === 'connecting' ? 'Connecting' : 'Finalizing'}
      </Badge>
    )
  }
  if (state === 'error') {
    return <Badge variant="danger">Attention</Badge>
  }
  return <Badge variant="muted">Idle</Badge>
}

function sessionStateLabel(state: SessionState) {
  return {
    idle: 'Ready to start',
    connecting: 'Opening session',
    listening: 'Microphone live',
    stopping: 'Finalizing audio',
    error: 'Session needs attention',
  }[state]
}

function sessionStateDescription(state: SessionState) {
  return {
    idle: 'No microphone audio is being sent.',
    connecting: 'Waiting for browser and backend readiness.',
    listening: 'Audio frames are streaming to local ASR.',
    stopping: 'Waiting for the final transcript chunk.',
    error: 'Review the error and start a new session.',
  }[state]
}

function ReadinessRow({
  icon: Icon,
  label,
  detail,
  ready,
}: {
  icon: typeof Activity
  label: string
  detail: string
  ready: boolean
}) {
  return (
    <div className="flex items-start gap-2 py-3">
      <div className="grid size-7 shrink-0 place-items-center rounded-md bg-slate-50 text-slate-500">
        <Icon className={cn('size-4', ready && 'text-emerald-600')} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-xs font-semibold text-slate-900">{label}</div>
        <div className="mt-1 break-all text-xs leading-5 text-slate-600">{detail}</div>
      </div>
    </div>
  )
}

function LanguagePicker({
  value,
  configuredLanguages,
  disabled,
  onChange,
}: {
  value: VoiceLanguage
  configuredLanguages: string[] | undefined
  disabled: boolean
  onChange: (language: VoiceLanguage) => void
}) {
  const configured = new Set((configuredLanguages ?? []).map((language) => normalizeVoiceLanguage(language)))

  return (
    <div className="flex flex-col gap-2 rounded-md border border-slate-200 bg-white p-2.5 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 items-center justify-between gap-3 sm:flex-1">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-700">
          <Languages className="size-4 text-slate-500" />
          Recognition language
        </div>
        {disabled ? (
          <span className="text-xs font-medium text-slate-600">Locked during session</span>
        ) : null}
      </div>
      <SegmentedControl
        equalWidth
        className="w-full sm:w-[320px]"
        disabled={disabled}
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

function buildRealtimeWebSocketUrl(language: VoiceLanguage) {
  const baseUrl = import.meta.env.VITE_API_BASE_URL || window.location.origin
  const url = new URL('/api/v1/realtime/asr', baseUrl)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  url.searchParams.set('language', language)

  const apiKey = getRequestApiKey()
  if (apiKey) {
    url.searchParams.set('api_key', apiKey)
  }

  return url.toString()
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

function getModelReadinessMessage(
  selectedLanguage: VoiceLanguage,
  configuredLanguages: string[] | undefined,
  loadedLanguages: string[] | undefined,
) {
  if (!configuredLanguages?.length) {
    return null
  }
  const configured = new Set(configuredLanguages.map((language) => normalizeVoiceLanguage(language)))
  const loaded = new Set((loadedLanguages ?? []).map((language) => normalizeVoiceLanguage(language)))
  if (!configured.has(selectedLanguage) || loaded.has(selectedLanguage)) {
    return null
  }
  return `${voiceLanguageLabel(selectedLanguage)} ASR model is cold. The first session may take longer to begin.`
}

function downsampleFloat32(input: Float32Array, inputSampleRate: number, outputSampleRate: number) {
  if (inputSampleRate === outputSampleRate) {
    return new Float32Array(input)
  }

  const ratio = inputSampleRate / outputSampleRate
  const outputLength = Math.max(1, Math.round(input.length / ratio))
  const output = new Float32Array(outputLength)

  for (let index = 0; index < outputLength; index += 1) {
    const start = Math.floor(index * ratio)
    const end = Math.min(input.length, Math.floor((index + 1) * ratio))
    let sum = 0
    let count = 0
    for (let sourceIndex = start; sourceIndex < end; sourceIndex += 1) {
      sum += input[sourceIndex] ?? 0
      count += 1
    }
    output[index] = count > 0 ? sum / count : 0
  }

  return output
}
