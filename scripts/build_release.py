from __future__ import annotations

import argparse
import ast
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tomllib
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = ROOT / "artifacts" / "releases"
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[a-zA-Z0-9.-]+)?$")
PROHIBITED_SUFFIXES = {
    ".db",
    ".flac",
    ".key",
    ".log",
    ".mp3",
    ".onnx",
    ".p12",
    ".pem",
    ".pfx",
    ".pt",
    ".pth",
    ".sqlite",
    ".sqlite3",
    ".wav",
    ".webm",
}
REQUIRED_ARCHIVE_FILES = {
    "LICENSE",
    "README.md",
    "THIRD_PARTY_NOTICES.md",
    "docker/Dockerfile",
    "docker/docker-compose.yml",
}
ALLOWED_DATA_FILES = {"data/README.md"}
ALLOWED_MODEL_FILES = {
    "models/README.md",
    "models/runtime/.gitkeep",
    "models/source/.gitkeep",
}
ALLOWED_LOG_FILES = {"logs/.gitkeep"}


class ReleaseError(RuntimeError):
    pass


def main() -> int:
    args = parse_args()
    try:
        version = normalize_version(args.version)
        declared_versions = load_declared_versions()
        if any(item != version for item in declared_versions.values()):
            detail = ", ".join(f"{name}={item}" for name, item in declared_versions.items())
            raise ReleaseError(
                f"Requested version {version!r} does not match release metadata: {detail}."
            )

        ensure_clean_worktree()
        commit = git_output("rev-parse", "HEAD")
        expected_tag = f"v{version}"
        tags = set(filter(None, git_output("tag", "--points-at", "HEAD").splitlines()))
        if expected_tag not in tags and not args.allow_untagged:
            raise ReleaseError(
                f"HEAD is not tagged {expected_tag}. Tag the verified commit or use "
                "--allow-untagged for an RC dry run."
            )

        output_dir = args.output_dir.resolve() / expected_tag
        output_dir.mkdir(parents=True, exist_ok=True)
        archive_path = output_dir / f"VassilStudio-{version}-source.zip"
        manifest_path = output_dir / "release-manifest.json"
        checksums_path = output_dir / "SHA256SUMS"
        targets = (archive_path, manifest_path, checksums_path)
        existing = [path for path in targets if path.exists()]
        if existing and not args.force:
            names = ", ".join(path.name for path in existing)
            raise ReleaseError(f"Release output already exists: {names}. Use --force to replace it.")
        for path in existing:
            path.unlink()

        run_git(
            "archive",
            "--format=zip",
            f"--prefix=VassilStudio-{version}/",
            f"--output={archive_path}",
            "HEAD",
        )

        with ZipFile(archive_path) as archive:
            members = [item.filename for item in archive.infolist() if not item.is_dir()]
        audit_archive_members(members, version)

        archive_sha256 = sha256_file(archive_path)
        manifest = {
            "schema_version": 1,
            "product": "VassilStudio",
            "version": version,
            "source_commit": commit,
            "source_tag": expected_tag if expected_tag in tags else None,
            "candidate_build": expected_tag not in tags,
            "built_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "license": "GPL-3.0-or-later",
            "distribution": "source-first",
            "models_included": False,
            "binary_images_published": False,
            "source_archive": {
                "filename": archive_path.name,
                "size_bytes": archive_path.stat().st_size,
                "sha256": archive_sha256,
                "file_count": len(members),
            },
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        checksums_path.write_text(
            "".join(
                f"{sha256_file(path)}  {path.name}\n"
                for path in (archive_path, manifest_path)
            ),
            encoding="ascii",
            newline="\n",
        )

        print(f"source_archive: {archive_path}")
        print(f"manifest: {manifest_path}")
        print(f"checksums: {checksums_path}")
        print(f"commit: {commit}")
        print(f"tag: {expected_tag if expected_tag in tags else 'untagged candidate'}")
        return 0
    except (ReleaseError, subprocess.CalledProcessError) as exc:
        print(f"Release build failed: {exc}", file=sys.stderr)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an audited VassilStudio source release with manifest and SHA256 checksums."
    )
    parser.add_argument("--version", required=True, help="Release version, for example 0.1.0.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--allow-untagged",
        action="store_true",
        help="Allow an untagged HEAD for release-candidate dry runs.",
    )
    parser.add_argument("--force", action="store_true", help="Replace known release output files.")
    return parser.parse_args()


def normalize_version(value: str) -> str:
    normalized = value.strip().removeprefix("v")
    if not VERSION_PATTERN.fullmatch(normalized):
        raise ReleaseError(f"Invalid release version: {value!r}.")
    return normalized


def load_declared_versions() -> dict[str, str]:
    project = tomllib.loads(ROOT.joinpath("pyproject.toml").read_text(encoding="utf-8"))
    frontend = json.loads(
        ROOT.joinpath("frontend", "studio-react", "package.json").read_text(encoding="utf-8")
    )
    backend_module = ast.parse(
        ROOT.joinpath("backend", "vvoice", "__init__.py").read_text(encoding="utf-8")
    )
    backend_version = None
    for node in backend_module.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets):
            backend_version = ast.literal_eval(node.value)
            break
    if not isinstance(backend_version, str):
        raise ReleaseError("backend/vvoice/__init__.py does not declare a string __version__.")

    return {
        "pyproject": str(project["project"]["version"]),
        "backend": backend_version,
        "frontend": str(frontend["version"]),
    }


def ensure_clean_worktree() -> None:
    status = git_output("status", "--porcelain=v1", "--untracked-files=all")
    if status:
        preview = "\n".join(status.splitlines()[:10])
        raise ReleaseError(f"Working tree must be clean before packaging:\n{preview}")


def git_output(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def run_git(*args: str) -> None:
    subprocess.run(["git", *args], cwd=ROOT, check=True)


def audit_archive_members(members: list[str], version: str) -> None:
    prefix = f"VassilStudio-{version}/"
    relative_files: set[str] = set()
    violations: list[str] = []

    for member in members:
        if not member.startswith(prefix):
            violations.append(member)
            continue
        relative = PurePosixPath(member.removeprefix(prefix)).as_posix()
        relative_files.add(relative)
        relative_path = PurePosixPath(relative)
        suffix = relative_path.suffix.lower()
        filename = relative_path.name.lower()

        if relative_path.is_absolute() or ".." in relative_path.parts:
            violations.append(relative)
        elif suffix in PROHIBITED_SUFFIXES:
            violations.append(relative)
        elif filename.startswith(".env") and filename != ".env.example":
            violations.append(relative)
        elif relative in {"config/vassil.local.json", "config/vvoice.local.json"}:
            violations.append(relative)
        elif relative.startswith("data/") and relative not in ALLOWED_DATA_FILES:
            violations.append(relative)
        elif relative.startswith("models/") and relative not in ALLOWED_MODEL_FILES:
            violations.append(relative)
        elif relative.startswith("logs/") and relative not in ALLOWED_LOG_FILES:
            violations.append(relative)
        elif relative.startswith(("tmp/", "artifacts/", ".venv/")):
            violations.append(relative)
        elif relative.startswith(("foundation/sherpa-onnx/", "foundation/ZipVoice/")):
            violations.append(relative)

    missing = sorted(REQUIRED_ARCHIVE_FILES - relative_files)
    if violations:
        raise ReleaseError(
            "Release archive contains prohibited runtime/private files: "
            + ", ".join(sorted(violations)[:10])
        )
    if missing:
        raise ReleaseError("Release archive is missing required files: " + ", ".join(missing))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
