# RC 0.1.0 Gate Evidence

- Gate date: 2026-08-12
- Release mode: source-first candidate
- Binary publication: blocked pending source/SBOM/signing review

## Accepted

- Unit CI dependency boundary excludes WebSockets, ONNX Runtime, Torch, TorchAudio, and sherpa-onnx.
- GitHub Quality run `31515766187` passed after the split; dependency install fell to 54 seconds.
- A clean boundary test caught an eager WebSocket benchmark import in run `31518644497`.
- Fix commit `9b66260` passed GitHub Quality run `31519117215` with 92 tests.
- Native sample voice E2E, VI/EN language matrix, Docker infrastructure smoke, and Docker sample voice
  E2E passed on the release workstation.
- Digest-pinned, constrained CPU-only Docker image is 541,890,100 bytes and reports matched
  Torch/TorchAudio 2.11.0+cpu.
- Benchmark protocol and accepted baseline are recorded in
  `docs/benchmarks/rc-0.1.0-windows-cpu.md`.
- Application license is GPL-3.0-or-later; major runtime and model boundaries are documented.

## Official Tag Checklist

- Repeat the final quality gate if the candidate commit changes.
- Produce and audit the source bundle from that clean candidate commit.
- Require a green GitHub Quality run for the exact tagged commit.
- Create annotated tag `v0.1.0` only when the owner intentionally approves the public release.

## Explicitly Deferred

- Prebuilt Docker registry image.
- Native Windows installer and code signing.
- Automated SBOM and artifact signatures.
- Bundled model weights or automated acceptance of model/dataset terms.
