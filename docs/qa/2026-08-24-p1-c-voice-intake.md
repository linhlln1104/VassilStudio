# P1-C Voice Intake Quality Gate

Date: 2026-08-24

## Scope

- Staged review for browser uploads, microphone recordings, and loose local candidates.
- Revalidated trim, source hash, transcript/language compatibility, and warning acknowledgement at
  commit.
- Canonical WAV content hashes and lock-protected duplicate prevention for new and legacy profiles.
- Responsive ready/review/blocked UI with authenticated local-file playback and duplicate reuse.

## Quality Policy

The report uses deterministic signal heuristics, not a model quality score. Speech coverage is an
energy-based estimate and is presented as such in the API contract.

- Block: selection under 1 second or over 60 seconds, no usable signal, severe clipping affecting at
  least 10% of samples, missing/non-verbal transcript, or a clear transcript/language mismatch.
- Review: selection under 3 seconds or over 20 seconds, speech coverage below 55%, at least 0.5
  seconds of leading/trailing silence, clipping affecting at least 0.1% of samples, or Vietnamese text
  without diacritics.
- Duplicate: canonical post-trim WAV hash matches a saved profile. The report returns that profile and
  commit fails with `409`; the Studio offers reuse rather than creating another copy.

## Verification

| Gate | Result |
| --- | --- |
| Targeted intake/store/router tests | 16 passed |
| Full `scripts/check.ps1` | Passed |
| Full pytest suite | 170 passed |
| Ruff | Passed |
| Frontend lint/typecheck/build | Passed |
| OpenAPI export | Passed; canonical and legacy contracts updated |
| Auth/product smoke | Passed |
| Docker Compose config | Passed |
| `npm run qa:voices` | Passed at 1440x1000 and 390x844; no browser errors or horizontal overflow |

The Playwright gate verifies that no profile is created before review, warnings require explicit
acknowledgement, trim changes invalidate stale analysis, recheck restores a valid commit, the commit
contains `reviewed_source_sha256`, duplicate audio cannot be created, an existing profile can be
reused, and mocked microphone capture reaches the recorded state.

## Runtime Probe

The real local `sample voice.weba` candidate produced a 7.38-second mono/48 kHz report with 1.24
seconds of leading silence and 60.9% speech coverage, so its initial state was `review`. Applying the
suggested trim produced a 5.96-second `ready` selection with about 0.10 seconds of silence at each end
and 75.5% speech coverage. A real Vietnamese ASR-assisted review returned an ASR draft in 2.4 seconds
without creating or changing a voice profile.

## Deferred

Source-audio replacement, denoise/normalization transforms, and workspace voice backup/export remain
separate reversible lifecycle work. They are not represented as available controls in this phase.
