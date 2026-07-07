# VassilStudio UI Research

For the React/shadcn rebuild plan and UI/UX Guardian review process, see
[`ui-redesign-plan.md`](ui-redesign-plan.md).

## Market Reference

- ElevenLabs positions the product as a multi-surface voice platform: TTS, STT, voice cloning,
  conversational agents, generative audio, and no-code studio projects.
  Source: https://elevenlabs.io/docs/overview/intro
- Murf emphasizes a studio workflow: script input, voice library, language/accent selection,
  pitch/speed/emphasis/pauses, cloning, export, dubbing, and project organization.
  Source: https://murf.ai/ai-voice-generator
- Descript's strongest pattern is transcript-first editing: audio/video editing behaves like a
  document, with recording, transcription, enhancement, and publishing in one workflow.
  Source: https://www.descript.com/
- AssemblyAI's playground pattern is a simple developer demo surface: left navigation, upload/drop
  zone, transcription, speaker labels, summaries, logs, and API docs close by.
  Source: https://www.assemblyai.com/playground
- Deepgram's voice-agent pattern emphasizes a live pipeline: listen, transcribe, think, speak,
  all over a real-time WebSocket interface.
  Source: https://developers.deepgram.com/docs/voice-agent
- Cartesia highlights low-latency streaming TTS, voice cloning, pronunciation/accent controls,
  dubbing, narration, and conversational use cases.
  Source: https://docs.cartesia.ai/get-started/overview
- Resemble AI adds a safety/governance angle: usage-based credits, team seats, voice clones,
  deepfake detection, API access, and enterprise controls.
  Source: https://www.resemble.ai/pricing

## Common Product Patterns

- Main navigation separates create, voices, jobs/history, realtime, API/docs, and settings.
- TTS studios use a large script editor, voice selector, tuning controls, preview audio, and export.
- ASR playgrounds use file upload/drop, transcript output, metadata, and optional summaries.
- Voice libraries show cards with name, duration/sample rate/language/source, preview audio, edit,
  delete, and clone/create actions.
- Realtime products visualize the speech loop with listening/processing/speaking states, latency,
  and waveform/meter feedback.
- Developer-first tools keep API keys, model status, logs, and docs links close to the workspace.
- Enterprise products surface retention, team access, consent, auditability, and safety controls.

## Direction For VassilStudio

- Use a light, calm studio palette so local operators can work for long sessions without the heavy
  dark-console feeling.
- Keep the first screen as the actual tool, not a marketing landing page.
- Move toward a production app shell: persistent left navigation, a large transcript/script editor,
  a right settings panel for voice/model/tuning, and lower library/history sections.
- Preserve the three working zones: voice library, TTS/ASR workbench, realtime monitor.
- Add product-like status: runtime cards, counts, status pills, job history, cleanup, and waveform
  activity tied to real state.
- Later additions worth building: drag-and-drop upload, project/history timeline, pronunciation
  dictionary, SSML/pause controls, language/model selector, audio analytics, retention settings,
  and API/logs panel.
