import { useEffect, useRef, useState } from 'react'
import { CircleStop, Loader2, Mic, RotateCcw, ShieldAlert } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { formatBytes } from '@/lib/format'

const MAX_RECORDING_SECONDS = 60
const MIME_TYPES = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4'] as const

type VoiceRecorderProps = {
  recording: File | null
  onRecording: (file: File | null) => void
}

export function VoiceRecorder({ recording, onRecording }: VoiceRecorderProps) {
  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const timerRef = useRef<number | null>(null)
  const generationRef = useRef(0)
  const requestingRef = useRef(false)
  const [requesting, setRequesting] = useState(false)
  const [recordingActive, setRecordingActive] = useState(false)
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => () => {
    generationRef.current += 1
    requestingRef.current = false
    releaseRecorder(recorderRef, streamRef, timerRef)
  }, [])

  useEffect(() => {
    if (recordingActive && elapsedSeconds >= MAX_RECORDING_SECONDS) {
      if (recorderRef.current?.state === 'recording') recorderRef.current.stop()
    }
  }, [elapsedSeconds, recordingActive])

  const start = async () => {
    if (requestingRef.current || recorderRef.current) return
    setError(null)
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setError('Microphone recording is not supported by this browser.')
      return
    }
    const generation = ++generationRef.current
    requestingRef.current = true
    setRequesting(true)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      })
      if (generationRef.current !== generation) {
        stream.getTracks().forEach((track) => track.stop())
        return
      }
      streamRef.current = stream
      const mimeType = MIME_TYPES.find((type) => MediaRecorder.isTypeSupported(type))
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
      const chunks: Blob[] = []
      recorderRef.current = recorder
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunks.push(event.data)
      }
      recorder.onerror = () => {
        if (generationRef.current !== generation) return
        releaseRecorder(recorderRef, streamRef, timerRef)
        setRecordingActive(false)
        setError('The recording could not be completed.')
      }
      recorder.onstop = () => {
        if (generationRef.current !== generation) return
        const finalType = recorder.mimeType || mimeType || 'audio/webm'
        const blob = new Blob(chunks, { type: finalType })
        releaseRecorder(recorderRef, streamRef, timerRef)
        setRecordingActive(false)
        if (blob.size === 0) {
          setError('No microphone audio was captured. Try recording again.')
          return
        }
        const extension = extensionForMimeType(finalType)
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
        onRecording(new File([blob], `voice-${timestamp}.${extension}`, { type: finalType }))
      }
      setElapsedSeconds(0)
      setRecordingActive(true)
      onRecording(null)
      recorder.start(250)
      timerRef.current = window.setInterval(() => {
        setElapsedSeconds((current) => current + 1)
      }, 1000)
    } catch (caught) {
      if (generationRef.current !== generation) return
      releaseRecorder(recorderRef, streamRef, timerRef)
      setRecordingActive(false)
      setError(microphoneError(caught))
    } finally {
      if (generationRef.current === generation) {
        requestingRef.current = false
        setRequesting(false)
      }
    }
  }

  const stop = () => {
    if (recorderRef.current?.state === 'recording') recorderRef.current.stop()
  }

  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
            <span className={recordingActive ? 'size-2 rounded-full bg-red-500 motion-safe:animate-pulse' : 'size-2 rounded-full bg-slate-300'} />
            {requesting ? 'Waiting for microphone permission' : recordingActive ? 'Recording' : recording ? 'Recording captured' : 'Microphone ready'}
          </div>
          <div className="mt-1 truncate text-xs text-slate-600">
            {recordingActive
              ? `${formatClock(elapsedSeconds)} / 1:00`
              : recording
                ? `${recording.name} · ${formatBytes(recording.size)}`
                : 'No recording captured · 60 second limit'}
          </div>
        </div>
        {recordingActive ? (
          <Button size="sm" variant="secondary" onClick={stop}>
            <CircleStop className="size-4 text-red-600" />
            Stop
          </Button>
        ) : (
          <Button size="sm" variant="secondary" disabled={requesting} onClick={() => void start()}>
            {requesting ? <Loader2 className="size-4 animate-spin" /> : recording ? <RotateCcw className="size-4" /> : <Mic className="size-4" />}
            {requesting ? 'Requesting microphone' : recording ? 'Record again' : 'Start recording'}
          </Button>
        )}
      </div>
      {error ? (
        <div className="mt-3 flex items-start gap-2 border-t border-red-200 pt-3 text-xs leading-5 text-red-800" role="alert">
          <ShieldAlert className="mt-0.5 size-4 shrink-0" />
          <span>{error}</span>
        </div>
      ) : null}
    </div>
  )
}

function releaseRecorder(
  recorderRef: React.MutableRefObject<MediaRecorder | null>,
  streamRef: React.MutableRefObject<MediaStream | null>,
  timerRef: React.MutableRefObject<number | null>,
) {
  if (timerRef.current !== null) window.clearInterval(timerRef.current)
  timerRef.current = null
  const recorder = recorderRef.current
  if (recorder) {
    recorder.onstop = null
    recorder.ondataavailable = null
    recorder.onerror = null
    if (recorder.state !== 'inactive') recorder.stop()
  }
  streamRef.current?.getTracks().forEach((track) => track.stop())
  streamRef.current = null
  recorderRef.current = null
}

function extensionForMimeType(mimeType: string) {
  if (mimeType.includes('ogg')) return 'ogg'
  if (mimeType.includes('mp4')) return 'm4a'
  return 'webm'
}

function microphoneError(error: unknown) {
  if (error instanceof DOMException && error.name === 'NotAllowedError') {
    return 'Microphone access was denied. Allow it in browser site settings and try again.'
  }
  if (error instanceof DOMException && error.name === 'NotFoundError') {
    return 'No microphone is available on this device.'
  }
  return 'The microphone could not be started.'
}

function formatClock(seconds: number) {
  const minutes = Math.floor(seconds / 60)
  return `${minutes}:${String(seconds % 60).padStart(2, '0')}`
}
