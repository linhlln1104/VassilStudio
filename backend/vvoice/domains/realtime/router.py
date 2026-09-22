from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool

from vvoice.core.errors import VVoiceError, public_error_message
from vvoice.domains.realtime.service import (
    RealtimeAsrSession,
    RealtimeAudioChunk,
    RealtimeProtocolError,
)
from vvoice.shared.language import DEFAULT_LANGUAGE, normalize_language
from vvoice.shared.security.auth import websocket_is_authorized


router = APIRouter()
MAX_CONTROL_MESSAGE_BYTES = 4096


@router.websocket("/asr")
async def realtime_asr(websocket: WebSocket):
    if not websocket_is_authorized(websocket):
        await websocket.close(code=1008)
        return

    await websocket.accept()
    container = websocket.app.state.container
    try:
        if not getattr(container.settings.realtime, "enabled", True):
            raise RealtimeProtocolError("Realtime ASR is disabled")
        language = normalize_language(websocket.query_params.get("language", DEFAULT_LANGUAGE))
        session = RealtimeAsrSession.from_settings(
            container.settings.realtime,
            sample_rate=container.asr.sample_rate_for(language),
        )
        sequence = 0
        await websocket.send_json(
            {
                "type": "ready",
                "protocol": "vvoice.realtime.asr.v1",
                "language": language,
                **session.describe(),
            }
        )
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return

            text = message.get("text")
            if text is not None:
                should_close, sequence = await _handle_control_message(
                    websocket,
                    container,
                    session,
                    language,
                    text,
                    sequence,
                )
                if should_close:
                    await websocket.close()
                    return
                continue

            data = message.get("bytes")
            if data is None:
                continue

            if len(data) > container.settings.limits.max_realtime_frame_bytes:
                raise RealtimeProtocolError("Realtime audio frame exceeds the configured size limit")

            for chunk in session.append_binary(data):
                sequence = await _send_transcript(
                    websocket,
                    container,
                    chunk,
                    sequence,
                    language=language,
                    final=False,
                )
    except WebSocketDisconnect:
        return
    except RealtimeProtocolError as exc:
        await _close_with_error(websocket, str(exc), code=1003)
        return
    except VVoiceError as exc:
        await _close_with_error(websocket, public_error_message(exc), code=1011)
        return


async def _handle_control_message(
    websocket: WebSocket,
    container: Any,
    session: RealtimeAsrSession,
    language: str,
    text: str,
    sequence: int,
) -> tuple[bool, int]:
    if len(text.encode("utf-8")) > MAX_CONTROL_MESSAGE_BYTES:
        raise RealtimeProtocolError("Realtime control message exceeds the size limit")
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise RealtimeProtocolError("Realtime control messages must be JSON") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("type"), str):
        raise RealtimeProtocolError("Realtime control messages require an object with a string type")
    message_type = payload["type"].lower()
    if message_type != "config" and set(payload) != {"type"}:
        raise RealtimeProtocolError("Unexpected realtime control message fields")

    if message_type == "config":
        session.apply_config(payload)
        await websocket.send_json({"type": "configured", "language": language, **session.describe()})
        return False, sequence

    if message_type == "flush":
        sequence = await _flush(websocket, container, session, sequence, language=language, final=True)
        await websocket.send_json({"type": "flushed"})
        return False, sequence

    if message_type == "clear":
        session.clear()
        await websocket.send_json({"type": "cleared"})
        return False, sequence

    if message_type == "ping":
        await websocket.send_json({"type": "pong"})
        return False, sequence

    if message_type == "close":
        sequence = await _flush(websocket, container, session, sequence, language=language, final=True)
        await websocket.send_json({"type": "closed"})
        return True, sequence

    raise RealtimeProtocolError(f"Unsupported realtime control message: {message_type}")


async def _flush(
    websocket: WebSocket,
    container: Any,
    session: RealtimeAsrSession,
    sequence: int,
    *,
    language: str,
    final: bool,
) -> int:
    chunk = session.flush(force=final)
    if chunk is None:
        return sequence
    return await _send_transcript(
        websocket,
        container,
        chunk,
        sequence,
        language=language,
        final=final,
    )


async def _send_transcript(
    websocket: WebSocket,
    container: Any,
    chunk: RealtimeAudioChunk,
    sequence: int,
    *,
    language: str,
    final: bool,
) -> int:
    sequence += 1
    if chunk.is_silence:
        await websocket.send_json(
            {
                "type": "transcript",
                "sequence": sequence,
                "language": language,
                "text": "",
                "final": final,
                "skipped": True,
                "reason": "silence",
                "duration_seconds": chunk.duration_seconds,
                "rms": chunk.rms,
            }
        )
        return sequence

    result = await run_in_threadpool(
        container.asr.transcribe,
        chunk.samples,
        chunk.sample_rate,
        language,
    )
    await websocket.send_json(
        {
            "type": "transcript",
            "sequence": sequence,
            "language": language,
            "text": result.text,
            "final": final,
            "skipped": False,
            "duration_seconds": chunk.duration_seconds,
            "rms": chunk.rms,
        }
    )
    return sequence


async def _close_with_error(websocket: WebSocket, message: str, *, code: int) -> None:
    await websocket.send_json({"type": "error", "message": message})
    await websocket.close(code=code)
