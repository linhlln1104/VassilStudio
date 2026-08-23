# Windows CPU Latency Tuning - 2026-08-24

- Status: accepted local performance baseline
- Host: Intel Core i5-14600K, 14 cores / 20 logical processors
- Runtime: ONNX Runtime 1.27.0, CPUExecutionProvider
- Model: local Vietnamese ZipVoice ONNX assets

## Decision

Use 2 ASR threads, 8 TTS threads, 4 ZipVoice steps for Preview, and 8 steps for
Production. The shared `runtime.num_threads` value remains a compatibility fallback.

ZipVoice upstream documents 8 steps as the default and 4 steps as the low-latency
setting for distilled models. It also recommends ONNX and CPU multithreading. VassilStudio
keeps both render modes because the local Vietnamese model passed the product quality smoke
at 4 steps while 1-step and 2-step output did not.

Upstream reference: https://github.com/k2-fsa/ZipVoice#32-speed-optimization

## Step Gate

Input: Vietnamese, 32 characters, 2-second synthetic reference, 2 TTS threads.
Each output was 7.179 seconds at 24 kHz.

| Steps | API latency | VI transcript quality |
| ---: | ---: | --- |
| 1 | 2,325.87 ms | Failed; no required keyword hits |
| 2 | 4,373.60 ms | Failed; 2 of 6 keyword hits |
| 4 | 8,355.94 ms | Passed direct and realtime ASR smoke |
| 8 | 15,473.89 ms | Quality profile |

Four steps is the fastest accepted product preset. Lower values remain valid API inputs for
experimentation but are not exposed as Studio render modes.

## Thread Matrix

Input: saved Vietnamese voice profile, 32-character text, 4 steps, 1.941-second output.
Model session load time was excluded from synthesis latency.

| TTS threads | Synthesis latency |
| ---: | ---: |
| 2 | 7,239.05 ms |
| 4 | 5,233.43 ms |
| 6 | 4,896.26 ms |
| 8 | 4,408.77 ms |
| 12 | 19,040.29 ms |

Repeated warm 8-thread runs reached 3,860.87 ms and 3,746.85 ms. Twelve threads caused a
large regression on this hybrid CPU, so the local default is capped at the measured 8-thread
optimum. ASR remains at 2 threads; its 1-second probe averaged 17.90 ms at 2 threads and
22.43 ms at 8 threads.

## API Baseline

Input: Vietnamese, 48 characters, 2-second synthetic reference. Each output was 10.688
seconds, mono PCM16 at 24 kHz.

| Mode | Steps | State | Latency | Real-time factor |
| --- | ---: | --- | ---: | ---: |
| Preview | 4 | Cold | 8,480.30 ms | 0.793 |
| Preview | 4 | Warm | 5,224.93 ms | 0.489 |
| Preview | 4 | Warm | 5,268.79 ms | 0.493 |
| Production | 8 | Warm | 10,282.98 ms | 0.962 |
| Production | 8 | Warm | 10,402.08 ms | 0.973 |
| Production | 8 | Warm | 10,799.69 ms | 1.010 |

Preview warm mean: 5,246.86 ms, or 3.92x faster than the previous 20,582.86 ms
8-step / 2-thread warm baseline. Production mean: 10,494.92 ms, or 1.96x faster than
that equivalent 8-step baseline.

## UX Latency

Generate, Transcribe, and Jobs now poll every second while a job is queued, running, or
cancelling. They return to an 8-second interval when idle. This removes up to seven seconds
of avoidable output-display delay without continuously polling at the active rate.

## Verification

- VI 4-step direct ASR quality smoke: passed.
- VI 4-step realtime ASR quality smoke: passed.
- EN 8-step direct and realtime ASR quality smoke: passed.
- React lint and production build: passed.
- Playwright desktop/mobile audio, jobs, and settings workflows: passed.
- Chrome Generate check: Preview 4 steps, Production 8 steps, zero console errors, zero
  horizontal overflow.
