import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, Download, Loader2, RefreshCw } from 'lucide-react'

import { fetchBlob } from '@/lib/api'
import { cn } from '@/lib/utils'
import { Button } from './button'

type AudioPlayerProps = {
  src: string
  label: string
  downloadName?: string
  autoPlay?: boolean
  className?: string
  seekRequest?: { seconds: number; requestId: number } | null
  onTimeUpdate?: (currentTime: number) => void
  playbackStartSeconds?: number
  playbackEndSeconds?: number
}

export function AudioPlayer({
  src,
  label,
  downloadName,
  autoPlay = false,
  className,
  seekRequest,
  onTimeUpdate,
  playbackStartSeconds,
  playbackEndSeconds,
}: AudioPlayerProps) {
  const audioRef = useRef<HTMLAudioElement>(null)
  const [objectUrl, setObjectUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [retryToken, setRetryToken] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    let loadedUrl: string | null = null

    setObjectUrl(null)
    setError(null)

    void fetchBlob(src, { signal: controller.signal })
      .then((blob) => {
        loadedUrl = URL.createObjectURL(blob)
        setObjectUrl(loadedUrl)
      })
      .catch((caught: unknown) => {
        if (controller.signal.aborted) {
          return
        }
        setError(caught instanceof Error ? caught.message : 'Unable to load audio.')
      })

    return () => {
      controller.abort()
      if (loadedUrl) {
        URL.revokeObjectURL(loadedUrl)
      }
    }
  }, [retryToken, src])

  useEffect(() => {
    if (!autoPlay || !objectUrl || !audioRef.current) {
      return
    }
    void audioRef.current.play().catch(() => undefined)
  }, [autoPlay, objectUrl])

  useEffect(() => {
    if (!objectUrl || !audioRef.current || !seekRequest) {
      return
    }
    audioRef.current.currentTime = Math.max(0, seekRequest.seconds)
    void audioRef.current.play().catch(() => undefined)
  }, [objectUrl, seekRequest])

  useEffect(() => {
    if (!objectUrl || !audioRef.current || playbackStartSeconds === undefined) return
    audioRef.current.currentTime = playbackStartSeconds
  }, [objectUrl, playbackStartSeconds])

  const handleTimeUpdate = (audio: HTMLAudioElement) => {
    if (playbackEndSeconds !== undefined && audio.currentTime >= playbackEndSeconds) {
      audio.pause()
    }
    onTimeUpdate?.(audio.currentTime)
  }

  const handlePlay = (audio: HTMLAudioElement) => {
    if (playbackStartSeconds === undefined) return
    if (audio.currentTime < playbackStartSeconds || (
      playbackEndSeconds !== undefined && audio.currentTime >= playbackEndSeconds
    )) {
      audio.currentTime = playbackStartSeconds
    }
  }

  const download = () => {
    if (!objectUrl || !downloadName) {
      return
    }
    const anchor = document.createElement('a')
    anchor.href = objectUrl
    anchor.download = downloadName
    document.body.append(anchor)
    anchor.click()
    anchor.remove()
  }

  if (error) {
    return (
      <div
        className={cn(
          'flex flex-col gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between',
          className,
        )}
        role="alert"
      >
        <div className="flex min-w-0 items-start gap-2 text-xs leading-5 text-red-800">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          <span className="min-w-0 break-words">{error}</span>
        </div>
        <Button size="sm" variant="secondary" onClick={() => setRetryToken((current) => current + 1)}>
          <RefreshCw className="size-4" />
          Retry audio
        </Button>
      </div>
    )
  }

  if (!objectUrl) {
    return (
      <div
        className={cn(
          'flex h-11 items-center gap-2 rounded-md border border-slate-200 bg-slate-50 px-3 text-xs font-medium text-slate-600',
          className,
        )}
        role="status"
      >
        <Loader2 className="size-4 animate-spin text-blue-600" />
        Loading audio...
      </div>
    )
  }

  return (
    <div className={cn('flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center', className)}>
      <audio
        ref={audioRef}
        className="h-10 min-w-0 w-full shrink-0 sm:flex-1"
        aria-label={label}
        controls
        preload="metadata"
        src={objectUrl}
        onPlay={(event) => handlePlay(event.currentTarget)}
        onTimeUpdate={(event) => handleTimeUpdate(event.currentTarget)}
        onError={() => setError('The audio output could not be decoded.')}
      >
        Your browser does not support audio playback.
      </audio>
      {downloadName ? (
        <Button className="shrink-0" size="sm" variant="secondary" onClick={download}>
          <Download className="size-4" />
          Download WAV
        </Button>
      ) : null}
    </div>
  )
}
