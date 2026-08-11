# RC 0.1.0 Windows CPU Baseline

- Status: accepted release-candidate baseline
- Measured: 2026-08-12 (Asia/Bangkok)
- Provider: CPU, 2 runtime threads

## Environment

| Item | Value |
| --- | --- |
| Host OS | Windows 11 Pro 64-bit, build 26200 |
| CPU | Intel Core i5-14600K, 14 cores / 20 logical processors |
| Memory | 64 GB installed |
| Docker Engine | 29.5.2, Linux x86_64 |
| Runtime image | `sha256:d3b76d412bd0f7ffc3d3621c41b9426fa5777ec8ab4a44dd2bad83a90bc774a5` |
| Image size | 541,890,100 bytes |
| Python | 3.12.13 |
| Torch / TorchAudio | 2.11.0+cpu / 2.11.0+cpu |
| ONNX Runtime / sherpa-onnx | 1.27.0 / 1.13.3 |
| Runtime constraints SHA256 | `8877206ee39f71eaabb01ca5c89f2f1493754cd299f179f90ec1b0d045663f8d` |

The optimized image replaced a 3,295,311,893-byte CUDA-bearing build. The CPU image is about 83
percent smaller and has a matched Torch/TorchAudio pair.

## TTS

Input: Vietnamese, 48 characters, 2-second synthetic reference, 8 ZipVoice steps. Each output was
mono PCM16 at 24 kHz, 10.688 seconds, 513,068 bytes.

| Run | State | Latency | Real-time factor |
| --- | --- | ---: | ---: |
| 1 | Cold | 24,384.48 ms | 2.281 |
| 2 | Warm | 20,386.26 ms | 1.907 |
| 3 | Warm | 20,779.46 ms | 1.944 |

Overall mean: 21,850.07 ms. Warm mean: 20,582.86 ms; warm mean RTF: 1.926.

## ASR

Input: 1.0-second synthetic 220 Hz probe, 16 kHz mono.

| Run | State | Latency | Real-time factor |
| --- | --- | ---: | ---: |
| 1 | Cold | 1,225.87 ms | 1.226 |
| 2 | Warm | 22.40 ms | 0.022 |
| 3 | Warm | 42.39 ms | 0.042 |

Warm mean: 32.40 ms. The synthetic probe verifies decode latency and response shape, not transcript
accuracy.

## Realtime

Five 0.5-second chunks were sent after ASR warmup.

| Signal | Expected path | Mean | Min | Max |
| --- | --- | ---: | ---: | ---: |
| 220 Hz tone | ASR inference, `skipped=false` | 16.37 ms | 15.26 ms | 17.28 ms |
| Silence | Transport/skip, `skipped=true` | 0.87 ms | 0.57 ms | 1.74 ms |

## Quality And Packaging Smokes

- Native sample-voice E2E passed in 87.2 seconds from cold ASR/TTS state.
- VI/EN language matrix passed in 214.1 seconds. Direct and realtime transcripts met every keyword
  threshold for both languages.
- Clean constrained Docker build, boot, liveness, model readiness, Studio shell, and asset smoke
  passed in 123.6 seconds.
- Docker sample-voice E2E passed in 38.6 seconds and produced mono PCM16 WAV at 24 kHz, 3.296 seconds.
- GitHub unit CI after dependency split completed with a 54-74 second dependency-install range,
  compared with 116 seconds before the split.

## VI Model Fingerprints

```text
ASR encoder   b3abdef7a660fea7faf5e076b3c7613b0fc98406707103784d018189bb522124
ASR decoder   d1d27cca84c824a8acf5ce6edf0f2c0880cfe295d2e69b95134de1707e1d9998
ASR joiner    38ec49e1c18e4feb0cad4de13e25c83a866cf56f4a66f22e8ff579d591a69a46
ASR tokens    f536d03c2e95ebd2930cf0abec88e823bd17d3c1933da7ae6a82db3b80605e15
TTS text      add78393bef93d4cc010172ad5dd6791c6fc2f9919509c9cee1a1c4512a9b68a
TTS flow      03f8dbd456beb57ffcd66c949cd4c6244ca2c9403bce4df53c4921e8080031d8
TTS vocoder   bcb3b970e384161c4d634f0bb9e999ff1c471b34c9bc0b1049a5014065ed3cc0
TTS tokens    8d66ec16528522393beb08e6e4b0e62fd3bb80099a8669a303aed49c15cca278
TTS lexicon   64d8718642816ec9aec67b1b1a797714bde2d4788d509ba91f4e4fc557ec7941
```

## Comparison Rule

Treat an unexplained warm mean regression above 20 percent as release-blocking on equivalent
hardware. Create a new baseline when hardware, thread count, runtime versions, benchmark fixture,
or any model fingerprint changes.
