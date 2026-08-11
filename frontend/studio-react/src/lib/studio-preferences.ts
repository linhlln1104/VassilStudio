const SELECTED_VOICE_STORAGE_KEY = 'vassil.selectedVoiceId'
const SELECTED_LANGUAGE_STORAGE_KEY = 'vassil.selectedLanguage'
const PENDING_SCRIPT_STORAGE_KEY = 'vassil.pendingScript'
const GENERATE_DRAFT_STORAGE_KEY = 'vassil.generateDraft'

const LEGACY_SELECTED_VOICE_STORAGE_KEY = 'vvoice.selectedVoiceId'
const LEGACY_SELECTED_LANGUAGE_STORAGE_KEY = 'vvoice.selectedLanguage'
const LEGACY_PENDING_SCRIPT_STORAGE_KEY = 'vvoice.pendingScript'
const LEGACY_GENERATE_DRAFT_STORAGE_KEY = 'vvoice.generateDraft'

function readStoredPreference(key: string, legacyKey: string): string {
  if (typeof window === 'undefined') {
    return ''
  }

  const value = window.localStorage.getItem(key)
  if (value) {
    return value
  }

  const legacyValue = window.localStorage.getItem(legacyKey)
  if (legacyValue) {
    window.localStorage.setItem(key, legacyValue)
    return legacyValue
  }

  return ''
}

function writeStoredPreference(key: string, legacyKey: string, value: string): void {
  if (typeof window === 'undefined') {
    return
  }

  const normalized = value.trim()
  if (normalized) {
    window.localStorage.setItem(key, normalized)
    window.localStorage.removeItem(legacyKey)
  } else {
    window.localStorage.removeItem(key)
    window.localStorage.removeItem(legacyKey)
  }
}

export function getPreferredVoiceId(): string {
  return readStoredPreference(SELECTED_VOICE_STORAGE_KEY, LEGACY_SELECTED_VOICE_STORAGE_KEY)
}

export function setPreferredVoiceId(voiceId: string): void {
  writeStoredPreference(SELECTED_VOICE_STORAGE_KEY, LEGACY_SELECTED_VOICE_STORAGE_KEY, voiceId)
}

export function getPreferredLanguage(): string {
  return readStoredPreference(SELECTED_LANGUAGE_STORAGE_KEY, LEGACY_SELECTED_LANGUAGE_STORAGE_KEY)
}

export function setPreferredLanguage(language: string): void {
  writeStoredPreference(SELECTED_LANGUAGE_STORAGE_KEY, LEGACY_SELECTED_LANGUAGE_STORAGE_KEY, language)
}

export function getPendingScript(): string {
  return readStoredPreference(PENDING_SCRIPT_STORAGE_KEY, LEGACY_PENDING_SCRIPT_STORAGE_KEY)
}

export function consumePendingScript(): string {
  const pendingScript = getPendingScript()
  if (typeof window !== 'undefined') {
    window.localStorage.removeItem(PENDING_SCRIPT_STORAGE_KEY)
    window.localStorage.removeItem(LEGACY_PENDING_SCRIPT_STORAGE_KEY)
  }
  return pendingScript
}

export function setPendingScript(script: string): void {
  writeStoredPreference(PENDING_SCRIPT_STORAGE_KEY, LEGACY_PENDING_SCRIPT_STORAGE_KEY, script)
}

export function getGenerateDraft(): string {
  return readStoredPreference(GENERATE_DRAFT_STORAGE_KEY, LEGACY_GENERATE_DRAFT_STORAGE_KEY)
}

export function setGenerateDraft(script: string): void {
  if (typeof window === 'undefined') {
    return
  }

  if (script) {
    window.localStorage.setItem(GENERATE_DRAFT_STORAGE_KEY, script)
    window.localStorage.removeItem(LEGACY_GENERATE_DRAFT_STORAGE_KEY)
  } else {
    window.localStorage.removeItem(GENERATE_DRAFT_STORAGE_KEY)
    window.localStorage.removeItem(LEGACY_GENERATE_DRAFT_STORAGE_KEY)
  }
}
