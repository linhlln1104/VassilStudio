# Vassil Studio Runtime Data

Runtime data is local and intentionally not committed.

Recommended layout:

```text
data/
  voices/
  jobs/
    asr/
    tts/
  uploads/
  outputs/
```

`data/voices` stores reusable reference voices, including loose import candidates such as
`sample voice.weba`. Saved profiles carry a `language` field (`vi` or `en`) so Studio and the API
route ASR/TTS work to the matching local model.

`data/jobs` stores async ASR/TTS job metadata and generated job artifacts. Smoke scripts may create
and clean temporary jobs while leaving downloaded verification audio under `tmp/smoke`.

Saved voice profile metadata stores reference audio paths relative to each voice directory. This
keeps profiles portable between local runs and Docker mounts. Older metadata with absolute audio
paths is still read for compatibility.

Docker mounts `./data` into `/app/data` as writable storage.
