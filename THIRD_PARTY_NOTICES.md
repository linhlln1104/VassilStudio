# Third-Party Notices

VassilStudio's original application source is licensed under MIT. The full application license is in
`LICENSE`. This grant does not relicense third-party code, dependencies, models, or datasets.
This notice identifies the principal direct components and bundled native tools used by
the local runtime; it is not a complete transitive SBOM and does not replace license files shipped
by those components.

## Runtime Components

| Component | Release baseline | License | Upstream source |
| --- | --- | --- | --- |
| FastAPI | 0.141.1 | MIT | https://github.com/fastapi/fastapi |
| python-multipart | 0.0.32 | Apache-2.0 | https://github.com/Kludex/python-multipart |
| NumPy | 2.4.6 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | https://github.com/numpy/numpy |
| SoundFile | 0.14.0 | BSD-3-Clause wrapper | https://github.com/bastibe/python-soundfile |
| libsndfile used by SoundFile | 1.2.2 | LGPL-2.1-or-later | https://github.com/libsndfile/libsndfile |
| librosa | 1.0.0 | ISC | https://github.com/librosa/librosa |
| Uvicorn | 0.52.1 | BSD-3-Clause | https://github.com/Kludex/uvicorn |
| Requests | 2.34.2 | Apache-2.0 | https://github.com/psf/requests |
| websockets | 17.0.1 | BSD-3-Clause | https://github.com/python-websockets/websockets |
| phonemizer-fork | 3.3.2 | GPL-3.0-or-later | https://github.com/bootphon/phonemizer |
| espeakng-loader | 0.2.4 | MIT loader; bundles eSpeak NG | https://github.com/thewh1teagle/espeakng-loader |
| eSpeak NG | 1.52.0 (`4870adfa25b1a32b4361592f1be8a40337c58d6c`) | GPL-3.0-or-later | https://github.com/espeak-ng/espeak-ng/tree/1.52.0 |
| imageio-ffmpeg | 0.6.0 | BSD-2-Clause wrapper | https://github.com/imageio/imageio-ffmpeg/tree/v0.6.0 |
| FFmpeg executable supplied by imageio-ffmpeg | Platform wheel dependent | GPL-3.0-or-later for the RC builds using `--enable-gpl --enable-version3` | https://github.com/FFmpeg/FFmpeg |
| sherpa-onnx | 1.13.3 | Apache-2.0 | https://github.com/k2-fsa/sherpa-onnx |
| ZipVoice source/runtime design | Upstream source | Apache-2.0 | https://github.com/k2-fsa/ZipVoice |
| ONNX Runtime | 1.27.0 | MIT | https://github.com/microsoft/onnxruntime |
| PyTorch | 2.11.0 CPU | BSD-3-Clause | https://github.com/pytorch/pytorch |
| TorchAudio | 2.11.0 CPU | BSD-2-Clause | https://github.com/pytorch/audio |
| Lucide | 1.23.0 | ISC | https://github.com/lucide-icons/lucide |

The Python wheel metadata installed in the runtime and
`frontend/studio-react/package-lock.json` provide the detailed package inventory. Their upstream
copyright and license notices remain applicable.

`docker/runtime-linux-cpu.constraints.txt` records the complete Python package version set for the
benchmarked Linux CPU image. It is a reproducibility constraint, not a substitute for an SBOM or a
license scanner.

## Models And Data

VassilStudio source archives and Docker images do not contain ASR/TTS model weights, tokenizers,
vocoders, voice samples, or training datasets. Operators install these assets separately and must
review and retain each model card, dataset license, source URL, version, and checksum. The
VassilStudio application license does not grant rights to third-party model or dataset assets.

## Binary Distribution

The supported RC distribution is source-first. The Dockerfile is a reproducible local build recipe
that downloads upstream binary packages. Anyone who redistributes a built image or native bundle is
responsible for preserving notices and satisfying the applicable corresponding-source obligations,
including those for eSpeak NG and GPL-enabled FFmpeg builds. Review `docs/releasing.md` before
publishing a binary artifact.
