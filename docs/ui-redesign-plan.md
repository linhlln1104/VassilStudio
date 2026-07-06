# Vassil Studio UI/UX Redesign Plan

## Goal

Rebuild Vassil Studio as a focused Vietnamese voice production tool, not a demo UI wrapped around APIs. The new interface should feel light, premium, fast to scan, and reliable for repeated audio work.

The current vanilla HTML/CSS/JS Studio has reached its complexity ceiling. It should be preserved while a new React Studio is built beside it, then swapped into `/studio` once it passes review.

## Current Implementation Status

- `frontend/studio-react` is the active Studio implementation.
- The backend Studio router serves `frontend/studio-react/dist` when built.
- Docker builds the React Studio in a Node stage and serves the generated assets from `/studio`.
- `frontend/studio` remains as the legacy fallback for one transition period.
- `scripts/check.ps1` includes React Studio lint/build.

## Product Principles

- Generate is the default first screen.
- Workflows come before dashboards.
- Backend APIs remain the source of truth.
- Light theme, restrained color, strong typography, precise spacing.
- No marketing hero inside the Studio.
- No nested-card-heavy dashboard layout.
- Audio output, selected voice, model readiness, and active jobs must always be easy to understand.
- Motion should clarify state transitions only; avoid decorative animation.

## Proposed Frontend Stack

```text
React + Vite
TypeScript
Tailwind CSS
shadcn/ui
Radix UI
Framer Motion
lucide-react
TanStack Query
```

Why:

- React handles shared state, async jobs, polling, and reusable UI components cleanly.
- shadcn/ui and Radix provide accessible production primitives without locking us into a heavy component library.
- Tailwind gives a controlled design token system.
- TanStack Query makes health, voices, jobs, and polling predictable.
- Framer Motion should be used lightly for route transitions, job status changes, and audio/result reveal.

## New Source Layout

Build beside the current UI first:

```text
frontend/studio-react/
  index.html
  package.json
  vite.config.ts
  tailwind.config.ts
  src/
    main.tsx
    app/
      App.tsx
      routes.tsx
      providers.tsx
    components/
      app-shell/
      audio/
      jobs/
      status/
      voices/
      ui/
    features/
      generate/
      voices/
      jobs/
      transcribe/
      realtime/
      settings/
    lib/
      api.ts
      query.ts
      format.ts
      audio.ts
      constants.ts
    styles/
      globals.css
```

After the new UI passes review:

- Build static assets to `frontend/studio-react/dist`.
- Update backend Studio router to serve the new dist.
- Keep old `frontend/studio` as `frontend/studio-legacy` for one transition period, or remove it after the new UI is stable.

## Information Architecture

### App Shell

- Left sidebar navigation.
- Top status bar with model readiness, backend connection, active job count.
- Main view area.
- Optional right inspector/result panel on desktop.
- Bottom action bar on mobile only when it helps the active workflow.

### Primary Views

1. Generate
2. Voices
3. Jobs
4. Transcribe
5. Realtime
6. Settings

## Phase Plan

### Phase 0: Contract And Design Prep

Deliverables:

- Audit current OpenAPI contract.
- Define TypeScript API types for health, model status, voices, TTS jobs, ASR jobs.
- Create initial design tokens: colors, spacing, radius, shadows, typography, status colors.
- Define shared UI states: loading, empty, error, disabled, success.

Acceptance:

- No UI implementation yet.
- API client can call existing backend endpoints.
- Design tokens are documented and do not depend on one dominant hue.

Guardian checkpoint:

- IA/wireframe review.
- Design token review.

### Phase 1: React Studio Foundation

Deliverables:

- Scaffold `frontend/studio-react`.
- Install and configure React, Vite, TypeScript, Tailwind, shadcn/ui, Radix, TanStack Query, Framer Motion.
- Add AppShell with sidebar, top status bar, responsive layout.
- Add placeholder routes for all six views.
- Add local dev script and production build script.

Acceptance:

- `npm run build` passes.
- `npm run lint` or equivalent passes if configured.
- App renders at local dev URL.
- Desktop and mobile screenshots show no overflow or clipped nav.

Guardian checkpoint:

- App shell review.
- Responsive layout review.

### Phase 2: Shared Production Components

Deliverables:

- `ModelStatusBar`
- `VoicePicker`
- `AudioPlayer`
- `WaveformPreview`
- `JobStatusBadge`
- `JobTable`
- `EmptyState`
- `ErrorState`
- `LoadingSkeleton`
- `ConfirmDialog`
- `ToastCenter`

Acceptance:

- Components have consistent density, spacing, focus states, disabled states, and empty/error states.
- Audio player is stable before and after audio loads; no layout jump.
- Destructive actions use confirmation.

Guardian checkpoint:

- Design system review.
- Component state review.

### Phase 3: Generate View

Deliverables:

- Script editor with character count and validation.
- Voice picker with selected voice preview.
- Immediate Generate action using `/api/v1/tts/synthesize/voices/{voice_id}`.
- Queue action using `/api/v1/tts/jobs/voices/{voice_id}`.
- Stable result panel with audio playback, download, duration, status.
- Recent TTS jobs in a secondary panel.
- Model unavailable/error states.

Acceptance:

- User can generate speech from a saved sample voice profile.
- User can queue a TTS job and see it update.
- Completed job can be played and downloaded.
- Empty, loading, running, succeeded, failed states are visible and clear.
- Mobile keeps voice, script, and primary Generate reachable.

Guardian checkpoint:

- Generate view implementation review.
- Audio/result flow review.

### Phase 4: Voices View

Deliverables:

- Saved voices list/grid with preview audio.
- Import candidates section for loose files like `sample voice.weba`.
- Upload/import flow.
- Rename/edit reference text.
- Delete confirmation.
- Search across saved voices and local files.
- "Use in Generate" action.

Acceptance:

- Saved voices and import candidates are visually distinct.
- User can import `sample voice.weba`.
- User can preview, edit, delete, and select a voice.
- Failed import or missing reference text explains the issue.

Guardian checkpoint:

- Voices workflow review.

### Phase 5: Jobs View

Deliverables:

- Unified TTS + ASR job table/list.
- Filters: type, status, search, recent.
- Running job polling.
- TTS play/download.
- ASR transcript preview/copy/download if supported by frontend.
- Retry/reuse actions where backend supports it.
- Cleanup confirmation.

Acceptance:

- Job status is scannable.
- Running jobs update without full-page refresh.
- Failed jobs show useful error detail.
- Cleanup does not feel dangerously easy.

Guardian checkpoint:

- Jobs view review.
- Async state review.

### Phase 6: Transcribe View

Deliverables:

- Drag/drop file upload.
- Immediate transcription.
- Queue ASR job.
- Transcript panel with copy and use-as-script action.
- Prior ASR jobs visible in workflow.

Acceptance:

- Upload errors are clear.
- Transcript is readable and copyable.
- User can move transcript into Generate.
- Loading state communicates active processing.

Guardian checkpoint:

- Transcribe workflow review.

### Phase 7: Realtime ASR View

Deliverables:

- Mic permission state.
- WebSocket connection state.
- Start/stop controls.
- Live ASR transcript panel.
- Session clear action.
- Connection recovery messaging.
- Protocol/readiness details for `/api/v1/realtime/asr`.
- Realtime TTS playback remains future work until a duplex TTS backend exists.

Acceptance:

- Recording state cannot be confused with connection/model state.
- Transcript does not jump the viewport.
- Mobile keeps session controls reachable.
- Browser audio is downsampled and streamed as mono PCM to the backend websocket.

Guardian checkpoint:

- Realtime ASR session review.

### Phase 8: Settings And Diagnostics

Deliverables:

- Backend health.
- Model readiness.
- Runtime provider/thread info.
- API key config.
- Links to raw docs/status endpoints.
- Optional default TTS/ASR settings only if persistence exists.

Acceptance:

- Diagnostics are clear but not dominant.
- Missing model files point to specific checks.
- No dense debug dump as primary UI.

Guardian checkpoint:

- Settings/diagnostics review.

### Phase 9: Integration Swap

Deliverables:

- Build React Studio.
- Serve React build from `/studio`.
- Update Docker image to include built assets.
- Update smoke tests for React assets.
- Keep E2E `sample voice.weba` smoke passing.

Acceptance:

- `/studio` loads React Studio.
- Docker smoke passes.
- `scripts/check.ps1` passes.
- `smoke_e2e_sample_voice.py` passes against new UI-compatible backend.
- Desktop/mobile screenshots pass visual QA.

Guardian checkpoint:

- Final full-product review.

## UI/UX Guardian Review Protocol

Call the UI/UX Guardian after every phase with:

- Running URL or screenshots.
- Phase deliverables.
- Known constraints.
- Specific questions.

Expected Guardian output:

```text
Pass/blocker summary
Issues by severity
Required fixes before next phase
Nice-to-have polish
Screens/views reviewed
```

Severity:

- P0: blocks production usability or creates broken layout/workflow.
- P1: meaningful UX weakness that should be fixed before moving far.
- P2: polish or improvement, can be batched.

## Visual QA Checklist

Each implemented phase should be checked at:

- Desktop: 1440 x 1100
- Tablet: 900 x 1100
- Mobile: 390 x 1100

Checks:

- No text overlap.
- No clipped primary controls.
- No unintended horizontal scroll.
- Audio player visible and stable.
- Loading/empty/error states are understandable.
- Primary action is visually obvious.
- Keyboard focus is visible.
- Destructive actions are confirmed.

## Risks

- Rebuilding into a generic shadcn dashboard.
- Overusing cards, badges, gradients, or animation.
- Creating fake settings not backed by API.
- Letting Tailwind classes become unstructured visual noise.
- Delaying empty/error/loading states until the end.
- Not checking mobile until too late.
- Duplicating job polling logic across views.

## Recommended Immediate Next Step

Start with Phase 0 and Phase 1:

1. Confirm exact frontend dependencies and setup commands from official docs.
2. Scaffold `frontend/studio-react`.
3. Build the AppShell, design tokens, and placeholder routes.
4. Run the first Guardian review before implementing Generate.
