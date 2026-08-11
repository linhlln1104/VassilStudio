import re
from pathlib import Path
import tomllib


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
    assert 'python -m pip install ".[test]"' in workflow
    assert 'python -m pip install ".[dev]"' not in workflow
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
    assert 'Invoke-Step "studio-react dependency audit"' in script
    assert "audit --audit-level=high" in script


def test_toolchain_versions_match_container_baseline() -> None:
    assert ROOT.joinpath(".python-version").read_text(encoding="utf-8").strip() == "3.12"
    assert ROOT.joinpath(".node-version").read_text(encoding="utf-8").strip() == "24"

    dockerfile = ROOT.joinpath("docker", "Dockerfile").read_text(encoding="utf-8")
    assert "FROM python:3.12-slim" in dockerfile
    assert "FROM node:24-alpine" in dockerfile
    assert "https://download.pytorch.org/whl/cpu" in dockerfile
    assert '"torch==${TORCH_VERSION}" "torchaudio==${TORCH_VERSION}"' in dockerfile
    assert 'python -m pip install ".[runtime]"' in dockerfile
    assert "COPY frontend ./frontend" not in dockerfile


def test_runtime_dependencies_are_resolvable_from_supported_package_indexes() -> None:
    project_text = ROOT.joinpath("pyproject.toml").read_text(encoding="utf-8")
    project = tomllib.loads(project_text)["project"]
    base = set(project["dependencies"])
    extras = {name: set(values) for name, values in project["optional-dependencies"].items()}

    model_runtime = {
        "onnxruntime==1.27.0",
        "torch==2.11.0",
        "torchaudio==2.11.0",
        "sherpa-onnx==1.13.3",
    }
    test_tools = {"httpx2==2.5.0", "pytest==9.1.1", "ruff==0.15.20"}

    assert {"phonemizer-fork==3.3.2", "espeakng-loader==0.2.4"} <= base
    assert model_runtime <= extras["runtime"]
    assert model_runtime.isdisjoint(base | extras["test"])
    assert test_tools == extras["test"]
    assert extras["runtime"] | extras["test"] <= extras["dev"]
    assert "piper_phonemize" not in project_text
