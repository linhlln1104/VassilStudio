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
    assert 'python -m pip install ".[test,qa]"' in workflow
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
    metadata = tomllib.loads(ROOT.joinpath("pyproject.toml").read_text(encoding="utf-8"))
    assert metadata["project"]["requires-python"] == ">=3.12"
    assert metadata["tool"]["ruff"]["target-version"] == "py312"

    dockerfile = ROOT.joinpath("docker", "Dockerfile").read_text(encoding="utf-8")
    assert "FROM python:3.12-slim@sha256:" in dockerfile
    assert "FROM node:24-alpine@sha256:" in dockerfile
    assert "https://download.pytorch.org/whl/cpu" in dockerfile
    assert '"torch==${TORCH_VERSION}" "torchaudio==${TORCH_VERSION}"' in dockerfile
    assert "--constraint docker/runtime-linux-cpu.constraints.txt" in dockerfile
    assert '".[runtime]"' in dockerfile
    assert 'org.opencontainers.image.licenses="GPL-3.0-or-later"' in dockerfile
    assert "ENV VASSIL_BIND_ADDRESS=0.0.0.0" in dockerfile
    assert "COPY frontend ./frontend" not in dockerfile

    docker_smoke = ROOT.joinpath("scripts", "smoke_docker.ps1").read_text(encoding="utf-8")
    assert "Assert-DirectImageFailsClosed" in docker_smoke
    assert "anonymous non-loopback startup rejected" in docker_smoke

    constraints = ROOT.joinpath("docker", "runtime-linux-cpu.constraints.txt").read_text(
        encoding="utf-8"
    )
    requirements = {
        line.strip()
        for line in constraints.splitlines()
        if line.strip() and not line.startswith("#")
    }
    assert len(requirements) >= 60
    assert all("==" in requirement for requirement in requirements)
    assert {
        "fastapi==0.141.1",
        "onnxruntime==1.27.0",
        "torch==2.11.0",
        "torchaudio==2.11.0",
        "sherpa-onnx==1.13.3",
    } <= requirements


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
    assert extras["qa"] == {"uvicorn>=0.30"}
    assert model_runtime.isdisjoint(extras["qa"])
    assert extras["runtime"] | extras["test"] <= extras["dev"]
    assert "piper_phonemize" not in project_text


def test_release_license_and_packaging_contract_are_declared() -> None:
    metadata = tomllib.loads(ROOT.joinpath("pyproject.toml").read_text(encoding="utf-8"))
    project = metadata["project"]

    assert metadata["build-system"]["requires"] == ["setuptools==81.0.0"]
    assert project["license"] == "GPL-3.0-or-later"
    assert set(project["license-files"]) == {"LICENSE", "THIRD_PARTY_NOTICES.md"}
    assert ROOT.joinpath("LICENSE").is_file()
    assert ROOT.joinpath("THIRD_PARTY_NOTICES.md").is_file()
    assert ROOT.joinpath("scripts", "build_release.py").is_file()
    assert ROOT.joinpath("docs", "releasing.md").is_file()
