import numpy as np
import pytest

from vvoice.domains.realtime.service import RealtimeAsrSession, RealtimeProtocolError


def make_session(**overrides) -> RealtimeAsrSession:
    values = {
        "sample_rate": 16000,
        "encoding": "pcm_f32le",
        "chunk_seconds": 0.5,
        "min_chunk_seconds": 0.1,
        "max_buffer_seconds": 2.0,
        "silence_rms": 0.003,
    }
    values.update(overrides)
    return RealtimeAsrSession(**values)


def test_realtime_session_chunks_float32_pcm() -> None:
    session = make_session()
    samples = np.full(16000, 0.1, dtype=np.float32)

    chunks = session.append_binary(samples.tobytes())

    assert len(chunks) == 2
    assert chunks[0].sample_rate == 16000
    assert chunks[0].duration_seconds == 0.5
    assert chunks[0].is_silence is False


def test_realtime_session_decodes_int16_and_flushes_remainder() -> None:
    session = make_session(encoding="pcm_s16le", chunk_seconds=1.0)
    samples = np.full(4000, 16384, dtype=np.int16)

    assert session.append_binary(samples.tobytes()) == []
    chunk = session.flush(force=True)

    assert chunk is not None
    assert chunk.duration_seconds == 0.25
    assert np.allclose(chunk.samples, 0.5)


def test_realtime_session_rejects_bad_payload_alignment() -> None:
    session = make_session()

    with pytest.raises(RealtimeProtocolError):
        session.append_binary(b"abc")
