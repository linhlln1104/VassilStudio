import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FULL_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")


def test_github_quality_workflow_uses_read_only_pinned_actions() -> None:
    workflow = ROOT.joinpath(".github", "workflows", "quality.yml").read_text(
        encoding="utf-8"
    )

    assert "permissions:\n  contents: read" in workflow
    assert "runs-on: windows-latest" in workflow
    assert "timeout-minutes: 45" in workflow
    assert "./scripts/check.ps1 -CI" in workflow
    assert "secrets." not in workflow

    action_references = re.findall(r"uses: [^@\s]+@([^\s]+)", workflow)
    assert action_references
    assert all(FULL_COMMIT_SHA.fullmatch(reference) for reference in action_references)


def test_ci_check_mode_is_reproducible_and_model_independent() -> None:
    script = ROOT.joinpath("scripts", "check.ps1").read_text(encoding="utf-8")

    assert "[switch]$CI" in script
    assert "$SkipDoctor = $true" in script
    assert "$SkipCompose = $true" in script
    assert 'Invoke-Step "generated contract drift"' in script
    assert "$CI -or -not (Test-Path" in script


def test_toolchain_versions_match_container_baseline() -> None:
    assert ROOT.joinpath(".python-version").read_text(encoding="utf-8").strip() == "3.12"
    assert ROOT.joinpath(".node-version").read_text(encoding="utf-8").strip() == "24"

    dockerfile = ROOT.joinpath("docker", "Dockerfile").read_text(encoding="utf-8")
    assert "FROM python:3.12-slim" in dockerfile
    assert "FROM node:24-alpine" in dockerfile
