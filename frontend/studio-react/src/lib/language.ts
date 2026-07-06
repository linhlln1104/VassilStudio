export type VoiceLanguage = 'vi' | 'en'

export const VOICE_LANGUAGES: Array<{
  value: VoiceLanguage
  label: string
  shortLabel: string
  helper: string
}> = [
  {
    value: 'vi',
    label: 'Vietnamese',
    shortLabel: 'VI',
    helper: 'Use Vietnamese reference text and Vietnamese scripts.',
  },
  {
    value: 'en',
    label: 'English',
    shortLabel: 'EN',
    helper: 'Use English reference text and English scripts.',
  },
]

const VIETNAMESE_DIACRITIC_PATTERN =
  /[\u0103\u00e2\u0111\u00ea\u00f4\u01a1\u01b0\u00e1\u00e0\u1ea3\u00e3\u1ea1\u1eaf\u1eb1\u1eb3\u1eb5\u1eb7\u1ea5\u1ea7\u1ea9\u1eab\u1ead\u00e9\u00e8\u1ebb\u1ebd\u1eb9\u1ebf\u1ec1\u1ec3\u1ec5\u1ec7\u00ed\u00ec\u1ec9\u0129\u1ecb\u00f3\u00f2\u1ecf\u00f5\u1ecd\u1ed1\u1ed3\u1ed5\u1ed7\u1ed9\u1edb\u1edd\u1edf\u1ee1\u1ee3\u00fa\u00f9\u1ee7\u0169\u1ee5\u1ee9\u1eeb\u1eed\u1eef\u1ef1\u00fd\u1ef3\u1ef7\u1ef9\u1ef5]/i

export function normalizeVoiceLanguage(value: string | null | undefined): VoiceLanguage {
  return value === 'en' ? 'en' : 'vi'
}

export function voiceLanguageLabel(language: string | null | undefined): string {
  return VOICE_LANGUAGES.find((item) => item.value === normalizeVoiceLanguage(language))?.label ?? 'Vietnamese'
}

export function voiceLanguageShortLabel(language: string | null | undefined): string {
  return VOICE_LANGUAGES.find((item) => item.value === normalizeVoiceLanguage(language))?.shortLabel ?? 'VI'
}

export function hasVietnameseDiacritics(text: string): boolean {
  return VIETNAMESE_DIACRITIC_PATTERN.test(text)
}
