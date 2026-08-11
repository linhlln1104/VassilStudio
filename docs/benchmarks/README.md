# Benchmark Protocol

VassilStudio benchmarks are release comparison tools, not universal performance claims. Record the
hardware, OS, runtime image digest, dependency versions, model hashes, provider, thread count, input
shape, and cold/warm ordering with every result.

## Standard CPU Sequence

1. Build the candidate Docker image and start a fresh container. Record the image ID and SHA256 of
   `docker/runtime-linux-cpu.constraints.txt`. Do not call warmup endpoints.
2. Run TTS first so iteration 1 includes TTS model load and iterations 2-3 are warm:

   ```powershell
   $env:VASSIL_BASE_URL = "http://127.0.0.1:8018"
   .\.venv\Scripts\python.exe .\scripts\benchmark_tts_latency.py --iterations 3 --language vi --num-steps 8
   ```

3. Run ASR next so iteration 1 includes ASR model load and iterations 2-3 are warm. Restart the
   container first if an earlier smoke or E2E already loaded ASR:

   ```powershell
   .\.venv\Scripts\python.exe .\scripts\benchmark_asr_latency.py --iterations 3 --language vi --duration-seconds 1.0
   ```

4. Run realtime inference and transport probes after ASR is warm:

   ```powershell
   .\.venv\Scripts\python.exe .\scripts\benchmark_realtime_chunking.py --chunks 5 --chunk-seconds 0.5 --signal tone
   .\.venv\Scripts\python.exe .\scripts\benchmark_realtime_chunking.py --chunks 5 --chunk-seconds 0.5 --signal silence
   ```

5. Run `smoke_language_matrix.py` separately for transcript quality. Synthetic tone/silence probes
   measure latency and control-path behavior; they do not measure WER, intelligibility, or MOS.

## Required Assertions

- TTS response is non-empty WAV, mono PCM16, 24 kHz, with a positive reported duration.
- ASR accepts 16 kHz input and every request succeeds.
- Realtime tone chunks report `skipped=false`; silence chunks report `skipped=true`.
- JSON output records every iteration and summary statistics.
- No unexplained warm mean latency regression exceeds 20 percent on equivalent hardware.
- A changed model fingerprint creates a new baseline instead of silently replacing the old one.

Keep raw JSON under `tmp/benchmarks/` or another ignored evidence directory. Commit a concise,
reviewed baseline under `docs/benchmarks/`.
