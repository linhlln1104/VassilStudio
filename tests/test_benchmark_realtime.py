import numpy as np

from scripts.benchmark_realtime_chunking import probe_samples


def test_realtime_benchmark_probe_signals_are_deterministic() -> None:
    sample_rate = 16_000
    chunk_seconds = 0.5

    tone = probe_samples(sample_rate, chunk_seconds, "tone")
    silence = probe_samples(sample_rate, chunk_seconds, "silence")

    assert tone.dtype == np.float32
    assert silence.dtype == np.float32
    assert tone.shape == silence.shape == (8_000,)
    assert float(np.sqrt(np.mean(np.square(tone)))) > 0.003
    assert np.count_nonzero(silence) == 0
