from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ARTIFACTS = [
    "normalized-provider-export.json",
    "safe-list.json",
    "all-issues.json",
    "safe-explain.md",
    "risky-explain.json",
    "summary.json",
]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_patchrail(root: Path, args: list[str]) -> None:
    env = os.environ.copy()
    src = str(root / "src")
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        src if not existing_pythonpath else f"{src}{os.pathsep}{existing_pythonpath}"
    )
    proc = subprocess.run(
        [sys.executable, "-m", "patchrail", *args],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        if proc.stdout:
            print(proc.stdout, file=sys.stderr, end="")
        if proc.stderr:
            print(proc.stderr, file=sys.stderr, end="")
        raise SystemExit(proc.returncode)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr, end="")


def _prepare_output(output: Path, *, force: bool) -> None:
    output.mkdir(parents=True, exist_ok=True)
    generated = [output / artifact for artifact in ARTIFACTS]
    existing = [path for path in generated if path.exists()]
    if existing and not force:
        existing_names = ", ".join(path.name for path in existing)
        raise SystemExit(
            f"Output directory already contains demo artifacts: {existing_names}. "
            "Use --force or choose a new --output path."
        )
    for path in existing:
        path.unlink()


def run_demo(output: Path, *, force: bool = False) -> dict[str, Any]:
    root = _repo_root()
    output = output.resolve()
    _prepare_output(output, force=force)

    fixture_dir = Path("examples") / "funded-issues-readonly"
    provider_export = fixture_dir / "provider-github-export.json"
    normalized = output / "normalized-provider-export.json"
    safe_list = output / "safe-list.json"
    all_issues = output / "all-issues.json"
    safe_explain = output / "safe-explain.md"
    risky_explain = output / "risky-explain.json"
    summary_json = output / "summary.json"

    _run_patchrail(
        root,
        [
            "funded-issues",
            "import",
            "--provider",
            "github",
            "--source",
            str(provider_export),
            "--out",
            str(normalized),
        ],
    )
    _run_patchrail(
        root,
        [
            "funded-issues",
            "list",
            "--source",
            str(normalized),
            "--format",
            "json",
            "--out",
            str(safe_list),
        ],
    )
    _run_patchrail(
        root,
        [
            "funded-issues",
            "list",
            "--source",
            str(normalized),
            "--include-risky",
            "--format",
            "json",
            "--out",
            str(all_issues),
        ],
    )
    _run_patchrail(
        root,
        [
            "funded-issues",
            "explain",
            "example/project#42",
            "--source",
            str(normalized),
            "--format",
            "markdown",
            "--out",
            str(safe_explain),
        ],
    )
    _run_patchrail(
        root,
        [
            "funded-issues",
            "explain",
            "example/toolkit#17",
            "--source",
            str(normalized),
            "--format",
            "json",
            "--out",
            str(risky_explain),
        ],
    )

    normalized_payload = _json_file(normalized)
    safe_payload = _json_file(safe_list)
    all_payload = _json_file(all_issues)
    risky_payload = _json_file(risky_explain)
    blocked_actions = normalized_payload["blocked_actions"]

    summary = {
        "schema_version": "patchrail.funded_issues_readonly_demo.v1",
        "local_first": True,
        "read_only": normalized_payload["read_only"],
        "provider_records_loaded": normalized_payload["import_source"]["records_loaded"],
        "safe_only_total_returned": safe_payload["total_returned"],
        "include_risky_total_returned": all_payload["total_returned"],
        "risky_recommendation": risky_payload["recommendation"],
        "risky_issue_risk_level": risky_payload["issue"]["risk_level"],
        "blocked_actions": blocked_actions,
        "requirements": normalized_payload["requirements"],
        "artifact_files": ARTIFACTS,
    }

    if not summary["read_only"]:
        raise AssertionError("Funded issue demo must stay read-only.")
    if summary["safe_only_total_returned"] >= summary["include_risky_total_returned"]:
        raise AssertionError("Safe-only filtering did not hide the risky issue.")
    if risky_payload["issue"]["safe_to_list"]:
        raise AssertionError("Risky demo issue should not be safe to list by default.")
    if "automatic_claims" not in blocked_actions:
        raise AssertionError("Blocked actions must include automatic claims.")
    if normalized_payload["requirements"]["network_required"]:
        raise AssertionError("Funded issue demo must not require network access.")

    summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the local PatchRail funded issues read-only demo end to end."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".patchrail-funded-issues-demo"),
        help="Directory for local demo artifacts. Defaults to .patchrail-funded-issues-demo.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite generated demo artifacts in the output directory.",
    )
    args = parser.parse_args(argv)
    summary = run_demo(args.output, force=args.force)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
