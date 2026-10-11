import type { TtsModel } from './api'

export function ttsModelStatus(model: TtsModel): string {
  if (model.loaded) return 'Loaded'
  if (model.ready) return 'Cold'
  return model.status.replaceAll('_', ' ').replace(/^./, (letter) => letter.toUpperCase())
}

export function ttsModelMessage(model: TtsModel): string {
  if (model.message) return model.message
  if (model.loaded) return 'Loaded in memory and ready to render.'
  if (model.ready) return 'Model is cold. The next render will load it into memory.'
  const missing = Object.entries(model.checks).filter(([, passed]) => !passed).map(([name]) => name.replaceAll('_', ' '))
  return missing.length ? `Setup required: ${missing.join(', ')}.` : 'Model setup is incomplete. See Settings for details.'
}
