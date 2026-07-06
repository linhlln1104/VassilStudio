from vvoice.shared.security.auth import _candidate_from_mapping, _matches


def test_auth_accepts_api_key_header() -> None:
    candidate = _candidate_from_mapping({"X-Vassil-API-Key": "secret"}, {})

    assert candidate == "secret"
    assert _matches(candidate, ["secret"])


def test_auth_accepts_legacy_api_key_header() -> None:
    candidate = _candidate_from_mapping({"X-VVoice-API-Key": "secret"}, {})

    assert candidate == "secret"
    assert _matches(candidate, ["secret"])


def test_auth_accepts_bearer_header() -> None:
    candidate = _candidate_from_mapping({"Authorization": "Bearer secret"}, {})

    assert candidate == "secret"
    assert _matches(candidate, ["secret"])


def test_auth_accepts_query_key_for_websocket() -> None:
    candidate = _candidate_from_mapping({}, {"api_key": "secret"})

    assert candidate == "secret"
    assert _matches(candidate, ["secret"])


def test_auth_rejects_missing_or_wrong_key() -> None:
    assert _candidate_from_mapping({}, {}) is None
    assert not _matches(None, ["secret"])
    assert not _matches("wrong", ["secret"])
