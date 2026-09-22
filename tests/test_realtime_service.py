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


@pytest.mark.parametrize("payload", [
    {"chunk_seconds": "abc"}, {"chunk_seconds": float("nan")},
    {"chunk_seconds": float("inf")}, {"max_buffer_seconds": 1e9},
    {"chunk_seconds": 0.0001}, {"sample_rate": True},
    {"encoding": []}, {"silence_rms": -1}, {"extra": 1},
    {"max_buffer_seconds": 3},
])
def test_config_rejection_is_atomic_and_preserves_buffer(payload) -> None:
    session = make_session()
    session.append_binary(np.full(800, 0.1, dtype=np.float32).tobytes())
    before = session.describe()
    with pytest.raises(RealtimeProtocolError):
        session.apply_config({"type": "config", **payload})
    assert session.describe() == before
    assert session.flush(force=True).samples.size == 800


def test_session_rejects_oversized_audio_without_losing_existing_samples() -> None:
    session = make_session()
    session.append_binary(np.full(800, 0.1, dtype=np.float32).tobytes())
    with pytest.raises(RealtimeProtocolError, match="buffer limit"):
        session.append_binary(np.zeros(32001, dtype=np.float32).tobytes())
    assert session.flush(force=True).samples.size == 800


def test_config_accepts_existing_small_chunk_client_and_keeps_server_cap() -> None:
    session = make_session(chunk_seconds=3, min_chunk_seconds=0.6, max_buffer_seconds=12)
    session.apply_config({"type": "config", "chunk_seconds": 0.5})
    assert session.chunk_seconds == 0.5
    with pytest.raises(RealtimeProtocolError):
        session.apply_config({"type": "config", "max_buffer_seconds": 13})


def test_frames_cross_chunk_boundary_when_buffer_equals_chunk() -> None:
    session = make_session(chunk_seconds=0.5, max_buffer_seconds=0.5)
    emitted = []
    for _ in range(6):
        emitted.extend(session.append_binary(np.full(1365, 0.1, dtype=np.float32).tobytes()))
    assert [len(chunk.samples) for chunk in emitted] == [8000]
    assert len(session.flush(force=True).samples) == 190
