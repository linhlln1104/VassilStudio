import json

from scripts.export_openapi import export_openapi


def test_export_openapi_writes_contract(tmp_path) -> None:
    output = tmp_path / "openapi.json"

    export_openapi(output)

    schema = json.loads(output.read_text(encoding="utf-8"))
    assert schema["info"]["title"] == "VassilStudio API"
    assert "/health" in schema["paths"]
    assert "/api/v1/voices/import-candidates" in schema["paths"]
    assert "/api/v1/asr/jobs/{job_id}/cancel" in schema["paths"]
    assert "/api/v1/tts/jobs/{job_id}/cancel" in schema["paths"]

    schemas = schema["components"]["schemas"]
    assert "HealthResponse" in schemas
    assert "ModelStatusResponse" in schemas
    assert "TranscriptionResponse" in schemas
    assert "AsrJobResponse" in schemas
    assert "TtsJobResponse" in schemas
    assert "VoiceResponse" in schemas
    assert "VoiceImportCandidateResponse" in schemas
    assert "audio_size_bytes" in schemas["VoiceResponse"]["properties"]
    assert "audio_path" not in schemas["VoiceResponse"]["properties"]
    assert "attempt" in schemas["AsrJobResponse"]["properties"]
    assert "cancel_requested" in schemas["TtsJobResponse"]["properties"]
    assert "progress_stage" in schemas["AsrJobResponse"]["properties"]
    assert "stage_started_at" in schemas["TtsJobResponse"]["properties"]
    assert "cancellation_mode" in schemas["TtsJobResponse"]["properties"]

    asr_create = schema["paths"]["/api/v1/asr/jobs"]["post"]
    tts_create = schema["paths"]["/api/v1/tts/jobs/voices/{voice_id}"]["post"]
    assert "409" in asr_create["responses"]
    assert "409" in tts_create["responses"]
    assert any(
        parameter["name"] == "Idempotency-Key" and parameter["in"] == "header"
        for parameter in asr_create["parameters"]
    )
    assert any(
        parameter["name"] == "Idempotency-Key" and parameter["in"] == "header"
        for parameter in tts_create["parameters"]
    )
