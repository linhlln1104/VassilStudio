import { useEffect, useRef } from 'react'

const SIGNAL_SEGMENTS = [
  { start: 0.04, end: 0.18, color: '#06b6d4' },
  { start: 0.23, end: 0.39, color: '#2563eb' },
  { start: 0.44, end: 0.59, color: '#d946ef' },
  { start: 0.65, end: 0.81, color: '#0f172a' },
  { start: 0.86, end: 0.96, color: '#10b981' },
] as const

function signalEnvelope(position: number) {
  // Five repeatable envelopes give the field the cadence of a spoken phrase.
  return Math.min(
    1,
    0.72 * Math.exp(-Math.pow((position - 0.11) / 0.065, 2)) +
      0.92 * Math.exp(-Math.pow((position - 0.31) / 0.08, 2)) +
      0.62 * Math.exp(-Math.pow((position - 0.51) / 0.06, 2)) +
      1.0 * Math.exp(-Math.pow((position - 0.73) / 0.085, 2)) +
      0.7 * Math.exp(-Math.pow((position - 0.91) / 0.055, 2)),
  )
}

function signalColor(position: number) {
  return SIGNAL_SEGMENTS.find((segment) => position >= segment.start && position <= segment.end)?.color ?? '#cbd5e1'
}

function drawVoiceprint(
  context: CanvasRenderingContext2D,
  width: number,
  height: number,
  phase: number,
) {
  context.clearRect(0, 0, width, height)
  context.fillStyle = '#ffffff'
  context.fillRect(0, 0, width, height)

  context.fillStyle = '#e2e8f0'
  for (const position of [0.08, 0.27, 0.5, 0.73, 0.92]) {
    context.fillRect(Math.round(width * position), 0, 1, height)
  }
  context.fillRect(0, Math.round(height * 0.72), width, 1)

  const baseline = height * 0.72
  const barGap = width < 540 ? 4 : 5
  const barCount = Math.ceil(width / barGap)
  const maximumAmplitude = height * 0.19

  for (let index = 0; index <= barCount; index += 1) {
    const x = index * barGap
    const position = x / width
    const envelope = signalEnvelope(position)
    const carrier =
      0.22 +
      0.5 * Math.abs(Math.sin(index * 0.49 + phase)) +
      0.28 * Math.abs(Math.sin(index * 0.17 - phase * 0.7))
    const amplitude = 3 + envelope * maximumAmplitude * carrier

    context.fillStyle = signalColor(position)
    context.globalAlpha = envelope > 0.08 ? 0.82 : 0.42
    context.fillRect(Math.round(x), Math.round(baseline - amplitude), 1.5, Math.round(amplitude * 2))
  }

  context.globalAlpha = 1
  context.fillStyle = '#0f172a'
  context.fillRect(0, Math.round(baseline), width, 1)
}

export function VoiceprintCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const context = canvas?.getContext('2d')
    if (!canvas || !context) return

    const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)')
    let animationFrame = 0
    let logicalWidth = 0
    let logicalHeight = 0

    const resize = () => {
      const bounds = canvas.getBoundingClientRect()
      const pixelRatio = Math.min(window.devicePixelRatio || 1, 2)
      logicalWidth = Math.max(1, Math.round(bounds.width))
      logicalHeight = Math.max(1, Math.round(bounds.height))
      canvas.width = Math.round(logicalWidth * pixelRatio)
      canvas.height = Math.round(logicalHeight * pixelRatio)
      context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0)
      drawVoiceprint(context, logicalWidth, logicalHeight, 0)
    }

    const render = (time: number) => {
      drawVoiceprint(context, logicalWidth, logicalHeight, time * 0.00035)
      animationFrame = window.requestAnimationFrame(render)
    }

    const applyMotionPreference = () => {
      window.cancelAnimationFrame(animationFrame)
      if (motionPreference.matches) {
        drawVoiceprint(context, logicalWidth, logicalHeight, 0)
      } else {
        animationFrame = window.requestAnimationFrame(render)
      }
    }

    const resizeObserver = new ResizeObserver(resize)
    resizeObserver.observe(canvas)
    motionPreference.addEventListener('change', applyMotionPreference)
    resize()
    applyMotionPreference()

    return () => {
      window.cancelAnimationFrame(animationFrame)
      resizeObserver.disconnect()
      motionPreference.removeEventListener('change', applyMotionPreference)
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      data-qa="voiceprint-canvas"
      className="pointer-events-none absolute inset-0 size-full"
      aria-hidden="true"
    />
  )
}
