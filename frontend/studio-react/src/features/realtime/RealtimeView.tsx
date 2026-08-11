import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Activity,
  AudioLines,
  CheckCircle2,
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
import { api, getStoredApiKey } from '@/lib/api'
import {
  VOICE_LANGUAGES,
  normalizeVoiceLanguage,
  type VoiceLanguage,
  voiceLanguageLabel,
  voiceLanguageShortLabel,
} from '@/lib/language'
import { getPreferredLanguage, setPreferredLanguage } from '@/lib/studio-preferences'
import { cn } from '@/lib/utils'

type SessionState = 'idle' | 'connecting' | 'listening' | 'stopping' | 'error'

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
  const [selectedLanguage, setSelectedLanguage] = useState<VoiceLanguage>(() =>
    normalizeVoiceLanguage(getPreferredLanguage()),
  )
  const websocketRef = useRef<WebSocket | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const contextRef = useRef<AudioContext | null>(null)
  const processorRef = useRef<ScriptProcessorNode | null>(null)
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null)
  const gainRef = useRef<GainNode | null>(null)

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
  const transcriptText = useMemo(
    () => transcripts.filter((entry) => entry.text).map((entry) => entry.text).join('\n'),
    [transcripts],
  )
  const runtimeLanguageWarning = getRuntimeLanguageWarning(
    selectedLanguage,
    modelStatusQuery.data?.runtime.asr_configured_languages,
  )

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

  const cleanupRealtimeResources = () => {
    const websocket = websocketRef.current
    if (websocket && websocket.readyState !== WebSocket.CLOSED) {
      websocket.close()
    }
    websocketRef.current = null
    cleanupMediaResources()
  }

  useEffect(() => () => cleanupRealtimeResources(), [])

  const startSession = () => {
    if (!microphoneSupported) {
      setError('This browser does not expose microphone capture.')
      setSessionState('error')
      return
    }

    cleanupRealtimeResources()
    setError('')
    setProtocol(null)
    setSessionState('connecting')

    const websocket = new WebSocket(buildRealtimeWebSocketUrl(selectedLanguage))
    websocketRef.current = websocket
    websocket.binaryType = 'arraybuffer'

    websocket.onmessage = (event) => {
      try {
        const message = JSON.parse(String(event.data)) as RealtimeMessage
        handleRealtimeMessage(message, websocket)
      } catch {
        setError('Realtime server returned an unreadable message.')
        setSessionState('error')
      }
    }

    websocket.onerror = () => {
      setError('Realtime websocket failed to connect.')
      setSessionState('error')
      cleanupRealtimeResources()
    }

    websocket.onclose = () => {
      cleanupMediaResources()
      setSessionState((current) => (current === 'error' ? current : 'idle'))
    }
  }

  const handleRealtimeMessage = (message: RealtimeMessage, websocket: WebSocket) => {
    if (message.type === 'ready' || message.type === 'configured') {
      setProtocol(message)
      if (message.type === 'ready') {
        void startMicrophone(websocket, message.sample_rate ?? 16000)
      }
      return
    }

    if (message.type === 'transcript') {
      setTranscripts((current) => [
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
      ])
      return
    }

    if (message.type === 'cleared') {
      setTranscripts([])
      return
    }

    if (message.type === 'error') {
      setError(message.message ?? 'Realtime session failed.')
      setSessionState('error')
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
      const AudioContextCtor =
        window.AudioContext ??
        (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      if (!AudioContextCtor) {
        throw new Error('This browser does not expose Web Audio capture.')
      }
      const audioContext = new AudioContextCtor()
      const source = audioContext.createMediaStreamSource(stream)
      const processor = audioContext.createScriptProcessor(4096, 1, 1)
      const gain = audioContext.createGain()

      gain.gain.value = 0
      processor.onaudioprocess = (event) => {
        if (websocket.readyState !== WebSocket.OPEN) {
          return
        }
        const input = event.inputBuffer.getChannelData(0)
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
      setSessionState('listening')
    } catch (microphoneError) {
      setError(
        microphoneError instanceof Error
          ? microphoneError.message
          : 'Microphone permission was denied or unavailable.',
      )
      setSessionState('error')
      websocket.close()
      cleanupRealtimeResources()
    }
  }

  const stopSession = () => {
    setSessionState('stopping')
    const websocket = websocketRef.current
    if (websocket?.readyState === WebSocket.OPEN) {
      websocket.send(JSON.stringify({ type: 'flush' }))
      websocket.send(JSON.stringify({ type: 'close' }))
    }
    cleanupRealtimeResources()
    setProtocol(null)
    setSessionState('idle')
  }

  const clearSession = () => {
    setTranscripts([])
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

  return (
    <div className="grid min-w-0 grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1fr)_380px]">
      <section className="space-y-3">
        <Card>
          <CardHeader className="flex-wrap">
            <div>
              <div className="text-sm font-semibold text-slate-950">Session controls</div>
              <div className="mt-1 text-xs text-slate-600">
                Capture microphone audio and stream it to the realtime {voiceLanguageLabel(selectedLanguage)} ASR websocket.
              </div>
            </div>
            <div className="flex flex-col items-start gap-2 sm:flex-row">
              {sessionState === 'listening' || sessionState === 'connecting' ? (
                <Button variant="destructive" onClick={stopSession}>
                  {sessionState === 'connecting' ? <Loader2 className="size-4 animate-spin" /> : <Square className="size-4" />}
                  Stop session
                </Button>
              ) : (
                <Button
                  disabled={!backendOnline || !microphoneSupported || Boolean(runtimeLanguageWarning)}
                  onClick={startSession}
                >
                  <Mic className="size-4" />
                  Start session
                </Button>
              )}
              <Button variant="secondary" onClick={clearSession}>
                <Trash2 className="size-4" />
                Clear transcript
              </Button>
            </div>
          </CardHeader>
          <CardContent className="border-t border-slate-200">
            <LanguagePicker
              disabled={sessionState !== 'idle' && sessionState !== 'error'}
              value={selectedLanguage}
              configuredLanguages={modelStatusQuery.data?.runtime.asr_configured_languages}
              onChange={handleLanguageSelect}
            />
            {runtimeLanguageWarning ? (
              <div className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs font-medium leading-5 text-red-700">
                {runtimeLanguageWarning}
              </div>
            ) : null}
          </CardContent>
          {error ? (
            <CardContent>
            <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm font-semibold leading-6 text-red-700">
              {error}
            </div>
            </CardContent>
          ) : null}
        </Card>

        <Card>
          <CardContent className="p-3">
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              <div
                className={cn(
                  'rounded-md border p-3',
                  sessionState === 'listening'
                    ? 'border-sky-200 bg-sky-50'
                    : 'border-slate-200 bg-white',
                )}
              >
                <div className="grid size-9 place-items-center rounded-md bg-white text-blue-700">
                  {sessionState === 'listening' ? <Mic className="size-5" /> : <MicOff className="size-5" />}
                </div>
                <h2 className="mt-3 text-sm font-semibold text-slate-950">Live input</h2>
                <p className="mt-1 text-xs leading-5 text-slate-700">
                  {sessionState === 'listening'
                    ? `Microphone frames are being downsampled and streamed as ${voiceLanguageLabel(selectedLanguage)} PCM.`
                    : 'Start a session to request microphone permission and open the websocket.'}
                </p>
                <div className="mt-3 grid grid-cols-1 gap-2 text-xs font-semibold sm:grid-cols-2">
                  <StateTile label="Mic" value={microphoneSupported ? 'Available' : 'Missing'} good={microphoneSupported} />
                  <StateTile label="Socket" value={sessionState === 'listening' ? 'Open' : 'Idle'} good={sessionState === 'listening'} />
                </div>
              </div>
              <div className="rounded-md border border-slate-200 bg-white p-3">
                <div className="grid size-9 place-items-center rounded-md bg-sky-50 text-blue-700">
                  <AudioLines className="size-5" />
                </div>
                <h2 className="mt-3 text-sm font-semibold text-slate-950">Live transcript</h2>
                <p className="mt-1 text-xs leading-5 text-slate-700">
                  New transcript chunks appear at the top. Silence chunks are tracked but visually muted.
                </p>
                <div className="mt-3 rounded-md border border-slate-200 bg-white p-3">
                  <div className="text-xs font-semibold text-slate-600">Combined text</div>
                  <div className="mt-2 min-h-14 text-xs leading-5 text-slate-900">
                    {transcriptText || 'No transcript yet.'}
                  </div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div>
              <div className="text-sm font-semibold text-slate-950">Transcript stream</div>
              <div className="mt-1 text-xs text-slate-600">Chunk results from the websocket session.</div>
            </div>
          </CardHeader>
          <CardContent>
            {transcripts.length > 0 ? (
              <div className="space-y-3">
                {transcripts.map((entry) => (
                  <div
                    key={entry.id}
                    className={cn(
                      'rounded-md border p-3',
                      entry.skipped ? 'border-slate-200 bg-white text-slate-500' : 'border-slate-200 bg-white',
                    )}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap gap-1.5">
                        <Badge variant={entry.final ? 'success' : entry.skipped ? 'muted' : 'default'}>
                          {entry.skipped ? 'Silence' : entry.final ? 'Final' : 'Partial'}
                        </Badge>
                        <Badge variant="muted">{voiceLanguageShortLabel(entry.language)}</Badge>
                      </div>
                      <span className="text-xs font-semibold text-slate-600">
                        {entry.durationSeconds ? `${entry.durationSeconds.toFixed(2)}s` : 'duration pending'}
                      </span>
                    </div>
                    <p className="mt-2 text-xs leading-5 text-slate-800">
                      {entry.text || 'Silence skipped.'}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-md border border-dashed border-slate-300 bg-white p-4 text-center">
                <Activity className="mx-auto size-6 text-slate-500" />
                <div className="mt-2 text-sm font-semibold text-slate-950">No realtime chunks yet</div>
                <p className="mx-auto mt-1 max-w-sm text-xs leading-5 text-slate-600">
                  Start a session, speak into the microphone, then stop or flush to finalize remaining audio.
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      </section>

      <aside className="space-y-3">
        <Card>
          <CardHeader>
            <div>
              <div className="text-sm font-semibold text-slate-950">Session readiness</div>
              <div className="mt-1 text-xs text-slate-600">Realtime browser and backend state.</div>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <ReadinessRow
              icon={backendOnline ? Wifi : WifiOff}
              label="Backend websocket"
              detail="/api/v1/realtime/asr"
              ready={Boolean(backendOnline)}
            />
            <ReadinessRow
              icon={microphoneSupported ? Mic : MicOff}
              label="Microphone capture"
              detail={microphoneSupported ? 'getUserMedia available' : 'Browser API unavailable'}
              ready={microphoneSupported}
            />
            <ReadinessRow
              icon={CheckCircle2}
              label="PCM protocol"
              detail={
                protocol
                  ? `${voiceLanguageShortLabel(protocol.language)} - ${protocol.encoding} - ${protocol.sample_rate} Hz`
                  : 'Negotiated after connect'
              }
              ready={Boolean(protocol)}
            />
            <ReadinessRow
              icon={RotateCcw}
              label="Chunking"
              detail={protocol ? `${protocol.chunk_seconds}s chunks` : 'Uses backend defaults'}
              ready={Boolean(protocol)}
            />
          </CardContent>
        </Card>
      </aside>
    </div>
  )
}

function StateTile({ label, value, good }: { label: string; value: string; good: boolean }) {
  return (
    <div className={cn('rounded-md border px-3 py-2', good ? 'border-emerald-200 bg-emerald-50/40 text-emerald-800' : 'border-slate-200 bg-white text-slate-600')}>
      <div className="text-xs font-medium opacity-80">{label}</div>
      <div className="mt-1 text-xs font-semibold">{value}</div>
    </div>
  )
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
    <div className="flex items-start gap-2 rounded-md border border-slate-200 bg-white p-3">
      <div className="grid size-7 shrink-0 place-items-center rounded-md border border-slate-200 bg-white text-slate-500">
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

  const apiKey = getStoredApiKey()
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
