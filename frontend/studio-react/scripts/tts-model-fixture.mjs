export function ttsModelCatalog(overrides = {}) {
  const profiles = [
    { model_id: 'zipvoice-vi', engine: 'zipvoice', label: 'ZipVoice Vietnamese', languages: ['vi'], sample_rate: 24000, capabilities: { reference_audio: true, num_steps: true, speed: true } },
    { model_id: 'zipvoice-en', engine: 'zipvoice', label: 'ZipVoice English', languages: ['en'], sample_rate: 24000, capabilities: { reference_audio: true, num_steps: true, speed: true } },
    { model_id: 'vieneu-v3-turbo', engine: 'vieneu', label: 'VieNeu TTS v3 Turbo', languages: ['vi', 'en'], sample_rate: 48000, capabilities: { reference_audio: true, num_steps: false, speed: false } },
  ]
  return {
    default_models: { vi: 'zipvoice-vi', en: 'zipvoice-en' },
    models: profiles.map((profile) => ({
      ready: true, loaded: false, status: 'cold', checks: { dependency: true, assets: true }, message: null,
      ...profile, ...overrides[profile.model_id],
    })),
  }
}
