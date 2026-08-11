# Design Assets

This file records the visual evidence and custom visual systems used by the VassilStudio product
shell so they can be reviewed or replaced without guessing at their intent.

## Computational Voiceprint

- Component: `frontend/studio-react/src/features/product/VoiceprintCanvas.tsx`
- Purpose: full-bleed landing hero visual behind the product message
- Source: deterministic Canvas 2D rendering; no generated image or remote dependency
- Motion: subtle signal movement with a static `prefers-reduced-motion` fallback
- Palette: solid cyan, cobalt, magenta, ink, and emerald segments on white; no gradients
- Invariant: the same five signal envelopes and color sequence should remain recognizable across
  viewports, even when their density changes

The voiceprint is intentionally code-native and ownable. It replaces the generic acrylic waveform
image so the brand visual can evolve alongside the product instead of depending on a generated hero.

## Product Evidence

The landing page uses four first-party screenshots from the actual Studio build:

- `vassil-studio-generate.png`
- `vassil-studio-transcribe.png`
- `vassil-studio-realtime.png`
- `vassil-studio-voices.png`

Only real screenshots may be used as evidence of product functionality. Any future generated image
must remain contextual, contain no fake UI, and be documented here with its full prompt and source.
