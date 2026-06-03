#!/usr/bin/env python3
"""Build and smoke-test PatchRail release artifacts without publishing them."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _run(command: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> str:
    proc = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"command failed with exit code {proc.returncode}: {' '.join(command)}\n{proc.stdout}"
        )
    return proc.stdout


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _venv_bin(venv: Path, executable: str) -> Path:
    if os.name == "nt":
        return venv / "Scripts" / f"{executable}.exe"
    return venv / "bin" / executable


def _project_version() -> str:
    sys.path.insert(0, str(ROOT / "src"))
    from patchrail import __version__  # noqa: PLC0415

    return __version__


def _build_artifacts(dist_dir: Path) -> list[Path]:
    _run([sys.executable, "-m", "build", "--outdir", str(dist_dir)])
    version = _project_version()
    artifacts = sorted(dist_dir.glob(f"patchrail-{version}*"))
    if not artifacts:
        raise RuntimeError(f"no patchrail-{version} artifacts found in {dist_dir}")
    return artifacts


def _smoke_install(dist_dir: Path, fixture: Path) -> dict[str, Any]:
    version = _project_version()
    tmp_root = ROOT / ".patchrail-release-smoke"
    tmp_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="venv-", dir=tmp_root) as tmp:
        venv = Path(tmp)
        _run([sys.executable, "-m", "venv", str(venv)])
        python = _venv_bin(venv, "python")
        patchrail = _venv_bin(venv, "patchrail")
        _run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-index",
                "--find-links",
                str(dist_dir),
                f"patchrail=={version}",
            ]
        )
        doctor = json.loads(_run([str(patchrail), "doctor", "--format", "json"]))
        explain = json.loads(
            _run(
                [
                    str(patchrail),
                    "ci",
                    "explain",
                    "--log",
                    str(fixture),
                    "--format",
                    "json",
                ]
            )
        )
    try:
        tmp_root.rmdir()
    except OSError:
        pass
    return {
        "doctor_status": doctor["status"],
        "doctor_local_first": doctor["local_first"],
        "external_model_required": doctor["requirements"]["external_model_required"],
        "network_required": doctor["requirements"]["network_required"],
        "github_write_permission_required": doctor["requirements"][
            "github_write_permission_required"
        ],
        "fixture_failure_class": explain["failure_class"],
        "fixture_confidence": explain["confidence"],
    }


def build_release_readiness_report(dist_dir: Path, fixture: Path) -> dict[str, Any]:
    dist_dir.mkdir(parents=True, exist_ok=True)
    artifacts = _build_artifacts(dist_dir)
    _run([sys.executable, "-m", "twine", "check", *[str(path) for path in artifacts]])
    smoke = _smoke_install(dist_dir, fixture)
    return {
        "schema_version": "patchrail.release_readiness.v1",
        "version": _project_version(),
        "published": False,
        "manual_gates_remaining": [
            "PyPI publish",
            "release tag",
            "public announcement",
            "external program application",
        ],
        "commands": [
            "python -m build --outdir dist",
            "python -m twine check dist/*",
            "python -m venv .patchrail-release-smoke/venv-*",
            "python -m pip install --no-index --find-links dist patchrail==<version>",
            "patchrail doctor --format json",
            "patchrail ci explain --format json",
        ],
        "artifacts": [
            {
                "file": path.name,
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
            }
            for path in artifacts
        ],
        "checks": {
            "build": "passed",
            "twine_check": "passed",
            "wheel_smoke": "passed",
            **smoke,
        },
        "safety": {
            "local_first": True,
            "published_to_pypi": False,
            "created_release_tag": False,
            "announced_publicly": False,
            "contacted_third_parties": False,
            "github_write_permission_required": False,
            "external_model_required": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", default="dist", type=Path)
    parser.add_argument(
        "--fixture",
        default=Path("examples/ci-triage/dependency-failure.log"),
        type=Path,
        help="Fixture used for the installed-wheel smoke test.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON output path. Defaults to stdout only.",
    )
    parser.add_argument(
        "--clean-dist",
        action="store_true",
        help="Remove the dist directory before building local artifacts.",
    )
    args = parser.parse_args()

    dist_dir = args.dist_dir if args.dist_dir.is_absolute() else ROOT / args.dist_dir
    fixture = args.fixture if args.fixture.is_absolute() else ROOT / args.fixture
    if args.clean_dist and dist_dir.exists():
        shutil.rmtree(dist_dir)

    report = build_release_readiness_report(dist_dir, fixture)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        output = args.output if args.output.is_absolute() else ROOT / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
