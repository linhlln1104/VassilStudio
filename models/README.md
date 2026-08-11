# Vassil Studio Models

Model files are local runtime assets and are intentionally not committed.

Recommended layout:

```text
models/
  runtime/
    asr/
      vi/zipformer/
        encoder.onnx
        decoder.onnx
        joiner.onnx
        tokens.txt
    tts/
      vi/zipvoice/
        text_model.onnx
        flow_matching_model.onnx
        vocos_24khz.onnx
        tokens.txt
        lexicon_vi_minimal.txt
        espeak-ng-data/
      en/zipvoice/
        text_model.onnx
        flow_matching_model.onnx
        vocos_24khz.onnx
        tokens.txt
        espeak-ng-data/
  source/
    asr/
    tts/
```

`runtime` is what `config/vassil.example.json` uses. TTS runtime profiles live under
`tts.models.<language>`; only generate languages that have a configured profile. `source` is for original exports,
checkpoints, or legacy drops that should not be mounted into production unless needed.

ZipVoice profiles are phonemized by Vassil Studio, mapped directly to each model `tokens.txt`, and executed
through the direct ONNX runtime path. Use `vocos_24khz.onnx` for both Vietnamese and English ZipVoice
profiles because the flow decoder emits 100-bin mel features. Older `vocoder.onnx` files that expect
80-bin mel features are retained only for traceability and should not be selected in runtime config.

Docker mounts `./models` into `/app/models` as read-only.

## Model License Evidence

Models are operator-supplied assets and are not covered by the VassilStudio application license.
Before a model is used in a release environment, record its upstream URL, model card, license and
dataset terms, version or revision, file SHA256 checksums, and the date the terms were reviewed.
Do not copy model weights, tokenizer files, vocoders, datasets, or voice samples into a source or
binary release artifact.
