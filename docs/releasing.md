# VassilStudio Release Process

## Release Decision

VassilStudio 0.1.x uses a source-first release model:

- Application source is licensed under `GPL-3.0-or-later`.
- The official artifact is a tagged source ZIP with a JSON manifest and SHA256 checksums.
- Docker Compose is the supported production-like build and runtime recipe.
- Model weights, tokenizers, vocoders, datasets, voice samples, local data, logs, and secrets are
  never part of a VassilStudio release artifact.
- A prebuilt Docker image or native installer is not an official 0.1.x artifact. Publishing one
  requires a complete third-party source/notice review, an SBOM, signing, and binary install smoke.

This decision follows the actual runtime composition. `phonemizer-fork`, bundled eSpeak NG, and the
GPL-enabled FFmpeg executables used by `imageio-ffmpeg` carry GPL obligations. Apache, MIT, BSD, and
frontend package notices remain applicable; see `THIRD_PARTY_NOTICES.md`. This document is an
engineering distribution policy, not legal advice. Obtain legal review before proprietary, paid,
or externally hosted binary distribution.

## Artifact Contract

| Artifact | RC 0.1.x | Contains | Does not contain |
| --- | --- | --- | --- |
| Source ZIP | Publish | Tracked source, Docker recipe, docs, license, notices | Models, data, logs, secrets, build output |
| Release manifest | Publish | Version, commit, tag state, archive hash and size | Host paths or secrets |
| SHA256SUMS | Publish | Source ZIP and manifest hashes | Signatures |
| Docker image | Build and smoke locally | App, CPU runtime, built Studio | Models and workspace data |
| Python wheel | Internal component only | Backend package metadata | Complete product UI/config/operations bundle |
| Native installer | Deferred | None for 0.1.x | Unsigned DLL/runtime bundle |

The source ZIP is generated with `git archive`, so only committed files can enter it. The builder
then rejects model/audio/database/log files and requires the license, notices, README, and Docker
files to be present.

The release Docker recipe pins its Node and Python base image indexes plus the Linux/Python 3.12 CPU
package set in `docker/runtime-linux-cpu.constraints.txt`. Refresh that constraints file only as an
intentional runtime upgrade, then rerun Docker E2E and record a new benchmark baseline. The
constraints file is not a cross-platform lock or a cryptographic dependency integrity file.

## Candidate Gate

Run from a short, space-free Windows path when possible. The release workspace must contain the
operator-supplied VI/EN models and the sample voice fixture used by E2E.

1. Confirm `git status --short` is empty.
2. Run the default gate:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check.ps1
   ```

3. Start the native API without changing release data, then run:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke_e2e_sample_voice.ps1 --base-url http://127.0.0.1:8000
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke_language_matrix.ps1 --base-url http://127.0.0.1:8000
   ```

4. Run a clean Docker build and infrastructure smoke:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke_docker.ps1 -Port 8018
   ```

5. Keep the already-built container up and run the real Docker E2E:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke_docker.ps1 -Port 8018 -SkipBuild -KeepRunning
   .\.venv\Scripts\python.exe .\scripts\smoke_e2e_sample_voice.py --base-url http://127.0.0.1:8018
   docker compose -p vassil-smoke -f .\docker\docker-compose.yml down --remove-orphans
   ```

6. Run the benchmark protocol in `docs/benchmarks/README.md` and compare it with the accepted
   baseline. Investigate any unexplained warm-latency regression above 20 percent.
7. Push the candidate commit and require a green GitHub `Quality` workflow.
8. Create annotated tag `v<version>` only after every required gate is green.

## Build Artifacts

For an untagged RC dry run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_release.ps1 --version 0.1.0 --allow-untagged
```

For an official tagged release:

```powershell
git tag -a v0.1.0 -m "VassilStudio 0.1.0"
git push origin v0.1.0
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_release.ps1 --version 0.1.0
```

Outputs are written to `artifacts/releases/v<version>/`. Upload all three files together. Do not
modify an artifact after checksums are generated; rebuild from the tagged clean commit instead.

## Binary Publication Exit Criteria

A prebuilt image or native installer remains blocked until all of these are true:

- Exact dependency and binary SBOM is attached to the release.
- Corresponding-source access and notices are verified for eSpeak NG, GPL-enabled FFmpeg, and every
  other copyleft binary in the artifact.
- Image/native artifacts are signed and checksums are published.
- The packaged artifact passes E2E on a clean target host, not only the build machine.
- Model acquisition remains separate and records model-specific license acceptance.
- A legal reviewer approves the intended distribution and commercial model.
