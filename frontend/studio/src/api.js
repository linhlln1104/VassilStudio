export function createApi(getApiKey) {
  return {
    health: "/health",
    modelStatus: "/model-status",
    warmup: "/warmup",
    voices: "/api/v1/voices",
    voiceImportCandidates: "/api/v1/voices/import-candidates",
    voiceImportCandidateAudio: (filename) =>
      `/api/v1/voices/import-candidates/${encodeURIComponent(filename)}/audio`,
    voiceImport: "/api/v1/voices/import",
    voice: (voiceId) => `/api/v1/voices/${encodeURIComponent(voiceId)}`,
    asr: "/api/v1/asr/transcribe",
    asrJobs: "/api/v1/asr/jobs",
    asrJob: (jobId) => `/api/v1/asr/jobs/${encodeURIComponent(jobId)}`,
    ttsVoice: (voiceId) => `/api/v1/tts/synthesize/voices/${encodeURIComponent(voiceId)}`,
    ttsJobs: "/api/v1/tts/jobs",
    ttsJob: (jobId) => `/api/v1/tts/jobs/${encodeURIComponent(jobId)}`,
    ttsJobVoice: (voiceId) => `/api/v1/tts/jobs/voices/${encodeURIComponent(voiceId)}`,
    voiceAudio: (voiceId) => `/api/v1/voices/${encodeURIComponent(voiceId)}/reference-audio`,
    realtimeAsr: () => {
      const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
      const url = new URL(`${scheme}//${window.location.host}/api/v1/realtime/asr`);
      const apiKey = getApiKey();
      if (apiKey) {
        url.searchParams.set("api_key", apiKey);
      }
      return url.toString();
    },
  };
}
