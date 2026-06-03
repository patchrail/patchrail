from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ARTIFACTS = [
    "ci-report.md",
    "ci-result.json",
    "item.json",
    "item.md",
    "proposal.json",
    "proposal.md",
    "proposal-approved.json",
    "approved.json",
    "queue.jsonl",
    "audit-events.jsonl",
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
    generated = [
        output / "queue.sqlite",
        output / "queue.sqlite-wal",
        output / "queue.sqlite-shm",
        output / "init.json",
        output / "summary.json",
        *(output / artifact for artifact in ARTIFACTS),
    ]
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

    db = output / "queue.sqlite"
    ci_report = output / "ci-report.md"
    ci_result = output / "ci-result.json"
    init_json = output / "init.json"
    item_json = output / "item.json"
    item_md = output / "item.md"
    proposal_json = output / "proposal.json"
    proposal_md = output / "proposal.md"
    proposal_approved_json = output / "proposal-approved.json"
    approved_json = output / "approved.json"
    queue_jsonl = output / "queue.jsonl"
    audit_jsonl = output / "audit-events.jsonl"
    summary_json = output / "summary.json"

    fixture_log = Path("examples") / "ci-triage" / "dependency-failure.log"
    _run_patchrail(
        root,
        [
            "ci",
            "explain",
            "--log",
            str(fixture_log),
            "--format",
            "markdown",
            "--out",
            str(ci_report),
        ],
    )
    _run_patchrail(
        root,
        ["ci", "classify", "--log", str(fixture_log), "--format", "json", "--out", str(ci_result)],
    )
    _run_patchrail(root, ["queue", "--db", str(db), "init", "--out", str(init_json)])
    _run_patchrail(
        root,
        [
            "queue",
            "--db",
            str(db),
            "add",
            "--from-ci-result",
            str(ci_result),
            "--payload-json",
            json.dumps({"markdown_report": "ci-report.md"}, sort_keys=True),
            "--out",
            str(item_json),
        ],
    )
    item = _json_file(item_json)
    item_id = str(item["id"])

    _run_patchrail(
        root,
        ["queue", "--db", str(db), "show", item_id, "--format", "markdown", "--out", str(item_md)],
    )
    _run_patchrail(
        root,
        [
            "queue",
            "--db",
            str(db),
            "proposal",
            "add",
            "--item-id",
            item_id,
            "--title",
            "Pin compatible dependency range",
            "--summary",
            "Adjust dependency constraints and re-run the affected CI matrix.",
            "--patch-plan",
            "1. Reproduce the dependency install failure.\n"
            "2. Update the conflicting dependency range.\n"
            "3. Re-run the failing Python CI matrix.",
            "--risk-level",
            "low",
            "--out",
            str(proposal_json),
        ],
    )
    proposal = _json_file(proposal_json)
    proposal_id = str(proposal["id"])

    _run_patchrail(
        root,
        [
            "queue",
            "--db",
            str(db),
            "proposal",
            "show",
            proposal_id,
            "--format",
            "markdown",
            "--out",
            str(proposal_md),
        ],
    )
    _run_patchrail(
        root,
        [
            "queue",
            "--db",
            str(db),
            "proposal",
            "approve",
            proposal_id,
            "--note",
            "Maintainer approved the local patch plan.",
            "--out",
            str(proposal_approved_json),
        ],
    )
    _run_patchrail(
        root,
        [
            "queue",
            "--db",
            str(db),
            "approve",
            item_id,
            "--note",
            "Maintainer reviewed the local CI evidence and approved handoff.",
            "--out",
            str(approved_json),
        ],
    )
    _run_patchrail(
        root,
        ["queue", "--db", str(db), "export", "--format", "jsonl", "--out", str(queue_jsonl)],
    )
    _run_patchrail(
        root,
        ["queue", "--db", str(db), "audit", "--format", "jsonl", "--out", str(audit_jsonl)],
    )

    ci_payload = _json_file(ci_result)
    approved_item = _json_file(approved_json)
    approved_proposal = _json_file(proposal_approved_json)
    events = [json.loads(line) for line in audit_jsonl.read_text(encoding="utf-8").splitlines()]

    summary = {
        "schema_version": "patchrail.local_agent_queue_demo.v1",
        "local_first": True,
        "source_failure_class": ci_payload["failure_class"],
        "item_approval_state": approved_item["approval_state"],
        "proposal_approval_state": approved_proposal["approval_state"],
        "proposal_risk_level": approved_proposal["risk_level"],
        "write_actions_allowed": approved_item["write_actions_allowed"],
        "audit_event_types": [event["event_type"] for event in events],
        "artifact_files": ARTIFACTS,
    }

    if summary["write_actions_allowed"]:
        raise AssertionError("Demo must not grant write actions.")
    if summary["item_approval_state"] != "approved":
        raise AssertionError("Work item approval was not recorded.")
    if summary["proposal_approval_state"] != "approved":
        raise AssertionError("Proposal approval was not recorded.")

    summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the local PatchRail Agent Control Plane demo end to end."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".patchrail-demo"),
        help="Directory for local demo artifacts. Defaults to .patchrail-demo.",
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
