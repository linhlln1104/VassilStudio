from __future__ import annotations

import pytest

from scripts.build_release import (
    ReleaseError,
    audit_archive_members,
    load_declared_versions,
    normalize_version,
)


def test_release_version_normalization() -> None:
    assert normalize_version("0.1.0") == "0.1.0"
    assert normalize_version("v0.1.0") == "0.1.0"

    with pytest.raises(ReleaseError, match="Invalid release version"):
        normalize_version("latest")


def test_release_versions_are_synchronized() -> None:
    assert set(load_declared_versions().values()) == {"0.1.0"}


def test_source_archive_contract_allows_only_storage_skeletons() -> None:
    prefix = "VassilStudio-0.1.0/"
    members = [
        prefix + "LICENSE",
        prefix + "README.md",
        prefix + "THIRD_PARTY_NOTICES.md",
        prefix + "docker/Dockerfile",
        prefix + "docker/docker-compose.yml",
        prefix + "data/README.md",
        prefix + "models/README.md",
        prefix + "models/runtime/.gitkeep",
        prefix + "models/source/.gitkeep",
        prefix + "logs/.gitkeep",
    ]

    audit_archive_members(members, "0.1.0")


@pytest.mark.parametrize(
    "private_path",
    [
        ".env",
        ".env.production",
        "config/vassil.local.json",
        "data/auth.sqlite3",
        "data/voices/reference.wav",
        "models/runtime/asr/vi/encoder.onnx",
        "logs/vassil.log",
        "foundation/ZipVoice/model.pt",
        "../private.txt",
        "certificates/signing.key",
    ],
)
def test_source_archive_contract_rejects_runtime_and_private_files(private_path: str) -> None:
    prefix = "VassilStudio-0.1.0/"
    members = [
        prefix + "LICENSE",
        prefix + "README.md",
        prefix + "THIRD_PARTY_NOTICES.md",
        prefix + "docker/Dockerfile",
        prefix + "docker/docker-compose.yml",
        prefix + private_path,
    ]

    with pytest.raises(ReleaseError, match="prohibited"):
        audit_archive_members(members, "0.1.0")
