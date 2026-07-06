import json

from scripts.export_openapi import export_openapi


def test_export_openapi_writes_contract(tmp_path) -> None:
    output = tmp_path / "openapi.json"

    export_openapi(output)

    schema = json.loads(output.read_text(encoding="utf-8"))
    assert schema["info"]["title"] == "Vassil Studio API"
    assert "/health" in schema["paths"]
    assert "/api/v1/voices/import-candidates" in schema["paths"]

    schemas = schema["components"]["schemas"]
    assert "HealthResponse" in schemas
    assert "ModelStatusResponse" in schemas
    assert "TranscriptionResponse" in schemas
    assert "AsrJobResponse" in schemas
    assert "TtsJobResponse" in schemas
    assert "VoiceResponse" in schemas
    assert "VoiceImportCandidateResponse" in schemas
    assert "audio_size_bytes" in schemas["VoiceResponse"]["properties"]
