# VassilStudio Product Completeness Research

Date: 2026-08-24

## Product boundary

VassilStudio should become a small, complete local-first voice studio, not a local clone of a
multi-tenant cloud suite. A complete release must let one owner move from source material to a
reviewed, reusable output without opening the filesystem or calling the API manually.

In scope:

- Local owner workspace, voice profiles, TTS, batch ASR, realtime ASR, output history, model
  readiness, storage, diagnostics, backup, and deterministic export.
- Vietnamese and English workflows with explicit model/language compatibility.
- Offline operation after model installation.

Out of scope for the small product:

- Cloud signup, billing, credits, teams, public share links, and online collaboration.
- Marketplace voices, hosted inference, and mobile synchronization.
- Full destructive waveform editing or DAW-style multitrack mixing.

## Evidence from current products

The following are product patterns, not a requirement to copy every feature.

| Product evidence | Product expectation derived for VassilStudio | Source |
| --- | --- | --- |
| Generated files remain available in history and can be downloaded in several formats | A completed render must be playable and downloadable directly from history; Jobs cannot be only a queue monitor | [ElevenLabs generated-file history](https://elevenlabs.io/docs/help-center/website/can-i-access-the-files-i-generated-in-the-past) |
| Generation history supports listening, downloading, and restoring an earlier take | TTS needs take/version comparison before adding broad project features | [ElevenLabs Studio overview](https://elevenlabs.io/docs/projects/audio-native) |
| Long-form work is organized into paragraphs/chapters and exported as one file or split files | A later Project mode should be block-based and should compile deterministic exports | [ElevenLabs Studio overview](https://elevenlabs.io/docs/projects/audio-native) |
| Speech-to-text returns word timestamps, speaker IDs, channels, and additional output formats | A transcript result needs timed segments and a structured contract, not only one text field | [ElevenLabs Speech-to-Text API](https://elevenlabs.io/docs/api-reference/speech-to-text/convert) |
| Subtitle export supports SRT/VTT, speaker labels, line length, and cards | Transcript export should be an explicit workflow with predictable formatting controls | [Descript subtitle export](https://help.descript.com/hc/en-us/articles/10255811669773-Exporting-subtitles) |
| A local transcription product exports subtitles, documents, and structured text | Local processing is not enough by itself; portable outputs are part of the product promise | [MacWhisper](https://www.macwhisper.com/) |
| Desktop audio export exposes name, folder, format, sample rate, range, metadata, and multi-file export | Output naming and export settings should be first-class, while advanced audio editing can remain out of scope | [Audacity Export Audio](https://manual.audacityteam.org/man/file_export_dialog.html) |

## Current gap analysis

| Workflow | Current product capability | Missing completion criteria | Priority |
| --- | --- | --- | --- |
| Generate | Voice/language/mode/speed selection, idempotent queue submission, server-derived progress, latest output | Output name/format, take comparison, pronunciation overrides | P1 |
| Voices | Upload/local import, metadata edit, preview, search/filter, delete | Review-before-create, duplicate detection, trim, silence/clipping checks, source replacement, record from microphone, backup/export | P1 |
| Jobs/History | Search/filter, lifecycle, retry/reuse/delete/cleanup; inline authenticated playback and WAV download added in this phase | User title, favorite/pin, retention indicator, batch export/delete, pagination, compare takes, reveal/export destination | P1/P2 |
| Transcribe | Upload/preview, queued ASR, result copy/TXT download, Generate handoff | Timed segments, synchronized playback, transcript editing, SRT/VTT/JSON export, multi-file batch, optional speaker/channel metadata | P1 |
| Realtime | Microphone capture, level meter, partial/final segments, copy/download, finalize | Device selector, pause/resume, reconnect, permission diagnostics, saved session with source audio and transcript | P1 |
| Settings | Model readiness, warmup, storage inventory, retention cleanup, account/security, diagnostics | Model install/import/update/unload, compatibility check, editable safe runtime controls, backup/restore, open data folder, bounded log viewer | P1/P2 |
| Product shell | Landing, local owner auth, privacy/support/license/operations pages | VI/EN interface localization, first-run guided model/voice/output checklist, recovery flow | P2 |

## Prioritized implementation backlog

### P1-A: Runtime integrity - completed 2026-08-24

1. [x] Add an idempotency key to TTS/ASR job creation and reject accidental duplicate submission.
2. [x] Lock Generate submission while the create request is unresolved and derive success state from the
   server job, not stale mutation state.
3. [x] Make cancellation capability explicit. If inference cannot be interrupted, show `Stopping after
   current inference` instead of implying immediate cancellation.
4. [x] Add progress stages (`queued`, `preparing_input`, `running_model`, `finalizing`, `retry_wait`) and
   measured elapsed time; add ETA only after it is benchmark-backed.

Acceptance: repeated clicks create one job, UI state survives refresh, and cancellation wording matches
the actual safe point.

Implemented contract: create endpoints accept optional `Idempotency-Key`; only its SHA-256 digest and
a request fingerprint are persisted. Same-key/same-payload replay returns the original job, while
same-key/different-payload returns `409`. Job responses expose `progress_stage`, `stage_started_at`, and
`cancellation_mode: safe_point`. Terminal transitions are lock-protected, and TTS output is promoted
from a temporary file only after the final cancellation check. Playwright double-submit coverage passed
for Generate and Transcribe at desktop and mobile viewports.

### P1-B: Transcript review and export - completed 2026-08-24

1. [x] Extend the ASR result contract with timed segments; retain room for word timestamps and speaker ID.
2. [x] Show audio and transcript in one review surface with seek-to-segment and active-segment tracking.
3. [x] Allow non-destructive transcript editing while retaining the raw model result.
4. [x] Export TXT, SRT, VTT, and structured JSON with deterministic filenames and UTF-8 encoding.
5. [x] Remove any timestamp claim until the backend contract supplies real timings.

Acceptance: a completed ASR job can be reviewed against audio, corrected, reopened, and exported as a
valid subtitle file without external tools.

Implemented contract: ZipFormer token timestamps are converted into stable timed segments when the
runtime supplies them. Raw model text/segments remain immutable while the current transcript uses an
optimistic `transcript_revision`; stale edits return `409`. Legacy jobs load as untimed and can still be
edited and exported to TXT/JSON, while SRT/VTT remain unavailable instead of receiving inferred fake
timings. The shared Transcribe/Jobs review dialog provides authenticated audio playback, segment seek,
active tracking, edit protection, raw-result comparison, and deterministic UTF-8 exports.

### P1-C: Voice intake quality gate

1. Stage upload/local candidates in a review step before creating a voice profile.
2. Detect duplicate audio by content hash and explain whether to reuse or replace the profile.
3. Report duration, sample rate, channels, leading/trailing silence, clipping, and speech coverage.
4. Add trim boundaries and microphone recording; keep denoise/normalization optional and reversible.
5. Validate reference transcript/language compatibility before saving.

Acceptance: invalid or poor reference audio is caught before it becomes a reusable profile, and an
import action never creates an unexpected duplicate.

### P1-D: Realtime session completion

1. Select and remember an input device; expose permission and missing-device errors.
2. Support pause/resume and bounded reconnect without merging unrelated sessions.
3. Save a finalized session into history with transcript, language, timing metadata, and source audio
   when recording retention is enabled.
4. Reopen and export a saved session.

Acceptance: disconnects and device changes are recoverable, and stopping a session produces a durable
result rather than disposable screen text.

### P1-E: Local model operations

1. Add manifest-driven model import/install with checksum, license acknowledgement, disk estimate, and
   language/runtime compatibility validation.
2. Support warm, unload, replace, and rollback states without editing JSON by hand.
3. Keep downloads optional; allow importing an already downloaded model directory.

Acceptance: a non-developer can resolve `model missing` from Settings and understand disk/license
impact before changing the runtime.

### P2: Creative project mode

1. Add projects containing ordered script blocks, per-block voice/settings, pauses, and render state.
2. Keep multiple takes per block and allow listening, comparing, selecting, and deleting takes.
3. Add a VI/EN pronunciation dictionary using aliases first; phoneme syntax can follow model support.
4. Compile selected takes to one WAV or a ZIP of named blocks with a reproducible manifest.

Acceptance: a short narration can be revised block by block and exported without regenerating accepted
audio.

### P2: Library and lifecycle polish

- User-defined output titles, favorites, tags, sort, server pagination, batch export/delete, and
  retention visibility.
- Workspace backup/restore for metadata, voices, projects, transcripts, and selected outputs.
- VI/EN UI localization, keyboard accessibility, and route-level headings.
- Optional waveform overview and loudness/clipping analysis; avoid a full DAW surface.

## Recommended next phase

With **P1-A Runtime integrity** and **P1-B Transcript review and export** complete, implement **P1-C
Voice intake quality gate** next. Voice creation remains the highest-risk irreversible workflow because
local candidates can become reusable profiles before duplicate and recording-quality review.
