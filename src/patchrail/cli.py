from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import threading
from collections import Counter
from http.server import ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from patchrail import __version__
from patchrail.ci import classify_ci_log, redact_ci_log
from patchrail.funded_issues import (
    SUPPORTED_PROVIDERS,
    explain_issue,
    import_provider_export,
    load_funded_issues,
    summarize_issues,
)
from patchrail.queue import (
    DEFAULT_QUEUE_PATH,
    add_proposal,
    add_work_item,
    approve_proposal,
    approve_work_item,
    export_audit_events,
    export_work_items,
    init_queue,
    list_proposals,
    list_work_items,
    reject_proposal,
    reject_work_item,
    show_proposal,
    show_work_item,
    skip_work_item,
)
from patchrail.queue.server import make_queue_api_handler, serve_queue_api
from patchrail.queue.status import (
    queue_audit_summary_payload,
    queue_bundle_payload,
    queue_status_payload,
)


def _read_log(path: Path | None) -> str:
    if path is None:
        return sys.stdin.read()
    return path.read_text(encoding="utf-8", errors="replace")


def _render_text(result: dict[str, Any]) -> str:
    lines = [
        f"Root cause: {result['failure_class']}",
        f"Confidence: {result['confidence']}",
        f"Subsystem: {result['likely_subsystem']}",
        f"Reproduce: {result['reproduction_command']}",
        f"Suggested action: {result['minimal_repair_strategy']}",
    ]
    redaction = result.get("redaction")
    if isinstance(redaction, dict):
        redactions = redaction.get("redactions") or {}
        lines.append(f"Redaction: {len(redactions)} categories redacted locally")
    return "\n".join(lines) + "\n"


def _render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# PatchRail CI Report",
        "",
        f"- Root cause: `{result['failure_class']}`",
        f"- Confidence: `{result['confidence']}`",
        f"- Subsystem: {result['likely_subsystem']}",
        f"- Reproduce: `{result['reproduction_command']}`",
        f"- Suggested action: {result['minimal_repair_strategy']}",
        "",
        "## Evidence signals",
        "",
    ]
    signals = list(result.get("signals") or [])
    if signals:
        lines.extend(f"- `{signal}`" for signal in signals)
    else:
        lines.append("- No high-confidence local signal found.")
    lines.extend(
        [
            "",
            "## Safety",
            "",
            (
                "PatchRail classified this log locally. It did not create a pull request, "
                "post a comment, claim funding, or send data to an external service."
            ),
        ]
    )
    redaction = result.get("redaction")
    if isinstance(redaction, dict):
        redactions = redaction.get("redactions") or {}
        lines.extend(
            [
                "",
                "## Redaction",
                "",
                f"- Local redaction enabled: `{bool(redaction.get('local_only'))}`",
                f"- Categories redacted: `{len(redactions)}`",
            ]
        )
        for name, count in sorted(redactions.items()):
            lines.append(f"- `{name}`: `{count}`")
    return "\n".join(lines) + "\n"


def _format_result(result: dict[str, Any], output_format: str) -> str:
    if output_format == "json":
        return json.dumps(result, indent=2, sort_keys=True) + "\n"
    if output_format == "markdown":
        return _render_markdown(result)
    return _render_text(result)


def _write_or_print(text: str, out: Path | None) -> None:
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    print(text, end="")


def _json_dump(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _display_path(path: Path) -> str:
    text = str(path)
    return "." if text == "" else text


def _load_schema(name: str) -> str:
    schema_files = {
        "ci-benchmark": "ci-benchmark.v1.schema.json",
        "ci-fixture-check": "ci-fixture-check.v1.schema.json",
        "ci-pilot-metrics": "ci-pilot-metrics.v1.schema.json",
        "ci-pilot-summary": "ci-pilot-summary.v1.schema.json",
        "ci-result": "ci-result.v1.schema.json",
        "queue-audit-event": "queue-audit-event.v1.schema.json",
        "queue-audit-summary": "queue-audit-summary.v1.schema.json",
        "queue-proposal": "queue-proposal.v1.schema.json",
        "queue-status": "queue-status.v1.schema.json",
        "queue-work-item": "queue-work-item.v1.schema.json",
    }
    schema_file = schema_files.get(name)
    if schema_file is None:
        raise ValueError(f"unknown schema: {name}")
    return files("patchrail.schemas").joinpath(schema_file).read_text(encoding="utf-8")


def _doctor_payload(root: Path) -> dict[str, Any]:
    fixture_root = root / "examples" / "ci-triage"
    fixtures = sorted(fixture_root.glob("*.log")) if fixture_root.exists() else []
    schema_available = bool(_load_schema("ci-result").strip())
    return {
        "schema_version": "patchrail.doctor.v1",
        "patchrail_version": __version__,
        "python_version": sys.version.split()[0],
        "project_root": str(root),
        "local_first": True,
        "requirements": {
            "billing_required": False,
            "external_model_required": False,
            "network_required": False,
            "github_write_permission_required": False,
        },
        "checks": {
            "ci_result_schema_available": schema_available,
            "ci_fixture_count": len(fixtures),
            "ci_fixture_directory": str(fixture_root),
        },
        "status": "ok" if schema_available else "warning",
    }


def _render_doctor_text(result: dict[str, Any]) -> str:
    requirements = result["requirements"]
    checks = result["checks"]
    lines = [
        f"PatchRail: {result['patchrail_version']}",
        f"Python: {result['python_version']}",
        f"Status: {result['status']}",
        f"Local-first: {result['local_first']}",
        f"CI fixtures: {checks['ci_fixture_count']}",
        f"Schema available: {checks['ci_result_schema_available']}",
        f"Network required: {requirements['network_required']}",
        f"External model required: {requirements['external_model_required']}",
        f"GitHub write permission required: {requirements['github_write_permission_required']}",
    ]
    return "\n".join(lines) + "\n"


def _render_doctor_markdown(result: dict[str, Any]) -> str:
    requirements = result["requirements"]
    checks = result["checks"]
    lines = [
        "# PatchRail Doctor",
        "",
        f"- PatchRail version: `{result['patchrail_version']}`",
        f"- Python version: `{result['python_version']}`",
        f"- Status: `{result['status']}`",
        f"- Local-first: `{result['local_first']}`",
        f"- CI fixtures: `{checks['ci_fixture_count']}`",
        f"- CI result schema available: `{checks['ci_result_schema_available']}`",
        "",
        "## Requirements",
        "",
        f"- Billing required: `{requirements['billing_required']}`",
        f"- External model required: `{requirements['external_model_required']}`",
        f"- Network required: `{requirements['network_required']}`",
        f"- GitHub write permission required: `{requirements['github_write_permission_required']}`",
    ]
    return "\n".join(lines) + "\n"


def _doctor(args: argparse.Namespace) -> int:
    result = _doctor_payload(Path("."))
    if args.format == "json":
        text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    elif args.format == "markdown":
        text = _render_doctor_markdown(result)
    else:
        text = _render_doctor_text(result)
    _write_or_print(text, args.out)
    return 0 if result["status"] == "ok" else 1


def _read_optional_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _extract_markdown_links(text: str) -> list[dict[str, str]]:
    return [
        {"label": label, "url": url}
        for label, url in re.findall(r"\[([^\]]+)\]\((https://[^)]+)\)", text)
    ]


def _public_review_packet_payload(root: Path) -> dict[str, Any]:
    ledger_path = root / "docs" / "public-workflow-ledger.md"
    ledger_text = ledger_path.read_text(encoding="utf-8")
    issue_to_pr_cycles: list[dict[str, Any]] = []
    focused_prs: list[dict[str, Any]] = []
    section = ""
    for raw_line in ledger_text.splitlines():
        line = raw_line.strip()
        if line == "## Issue-To-PR Cycles":
            section = "issue_to_pr_cycles"
            continue
        if line == "## Focused Maintainer PR Evidence":
            section = "focused_prs"
            continue
        if line.startswith("## ") and section:
            section = ""
            continue
        if not line.startswith("|") or "---" in line or " Area " in line:
            continue

        columns = [column.strip() for column in line.strip("|").split("|")]
        if section == "issue_to_pr_cycles" and len(columns) >= 4:
            issue_links = _extract_markdown_links(columns[1])
            pull_request_links = _extract_markdown_links(columns[2])
            issue_to_pr_cycles.append(
                {
                    "area": columns[0],
                    "issue": issue_links[0] if issue_links else None,
                    "pull_request": pull_request_links[0] if pull_request_links else None,
                    "evidence_type": columns[3],
                }
            )
        elif section == "focused_prs" and len(columns) >= 4:
            pull_request_links = _extract_markdown_links(columns[1])
            ci_links = _extract_markdown_links(columns[2])
            focused_prs.append(
                {
                    "area": columns[0],
                    "pull_request": pull_request_links[0] if pull_request_links else None,
                    "public_ci_evidence": ci_links[0] if ci_links else None,
                    "evidence_type": columns[3],
                }
            )

    gaps = [
        "formal visible Codex review links",
        "permissioned external maintainer triage examples",
        "PyPI publish and download telemetry",
    ]
    return {
        "schema_version": "patchrail.review_packet.v1",
        "patchrail_version": __version__,
        "repository": "patchrail/patchrail",
        "generated_from": "local_checkout",
        "source_file": _safe_evidence_path(root, ledger_path),
        "status": (
            "owned_repo_review_packet_ready"
            if issue_to_pr_cycles and focused_prs
            else "needs_attention"
        ),
        "signals": {
            "issue_to_pr_cycles": len(issue_to_pr_cycles),
            "focused_maintainer_prs": len(focused_prs),
            "total_owned_review_items": len(issue_to_pr_cycles) + len(focused_prs),
        },
        "boundaries": {
            "owned_repository_only": True,
            "external_adoption_claimed": False,
            "formal_codex_review_claimed": False,
            "pypi_download_claimed": False,
            "third_party_write_actions_claimed": False,
        },
        "requirements": {
            "billing_required": False,
            "external_model_required": False,
            "network_required": False,
            "github_write_permission_required": False,
        },
        "issue_to_pr_cycles": issue_to_pr_cycles,
        "focused_maintainer_prs": focused_prs,
        "remaining_evidence_gaps": gaps,
    }


def _render_review_packet_markdown(payload: dict[str, Any]) -> str:
    signals = payload["signals"]
    boundaries = payload["boundaries"]
    lines = [
        "# PatchRail Public Review Packet",
        "",
        f"- Repository: `{payload['repository']}`",
        f"- Status: `{payload['status']}`",
        f"- Source file: `{payload['source_file']}`",
        f"- Issue-to-PR cycles: `{signals['issue_to_pr_cycles']}`",
        f"- Focused maintainer PRs: `{signals['focused_maintainer_prs']}`",
        f"- Total owned review items: `{signals['total_owned_review_items']}`",
        "",
        "## Boundary",
        "",
        f"- Owned repository only: `{boundaries['owned_repository_only']}`",
        f"- External adoption claimed: `{boundaries['external_adoption_claimed']}`",
        f"- Formal Codex review claimed: `{boundaries['formal_codex_review_claimed']}`",
        f"- PyPI download claimed: `{boundaries['pypi_download_claimed']}`",
        f"- Third-party write actions claimed: `{boundaries['third_party_write_actions_claimed']}`",
        "",
        "## Issue-To-PR Cycles",
        "",
    ]
    for item in payload["issue_to_pr_cycles"]:
        issue = item["issue"] or {}
        pull_request = item["pull_request"] or {}
        lines.append(
            f"- {item['area']}: {issue.get('url', 'missing issue')} -> "
            f"{pull_request.get('url', 'missing pull request')} ({item['evidence_type']})"
        )
    lines.extend(["", "## Focused Maintainer PRs", ""])
    for item in payload["focused_maintainer_prs"]:
        pull_request = item["pull_request"] or {}
        ci = item["public_ci_evidence"] or {}
        lines.append(
            f"- {item['area']}: {pull_request.get('url', 'missing pull request')} "
            f"with CI {ci.get('url', 'missing CI evidence')} ({item['evidence_type']})"
        )
    lines.extend(["", "## Remaining Evidence Gaps", ""])
    lines.extend(f"- {gap}" for gap in payload["remaining_evidence_gaps"])
    return "\n".join(lines) + "\n"


def _render_review_packet_text(payload: dict[str, Any]) -> str:
    signals = payload["signals"]
    return (
        "\n".join(
            [
                f"Repository: {payload['repository']}",
                f"Status: {payload['status']}",
                f"Issue-to-PR cycles: {signals['issue_to_pr_cycles']}",
                f"Focused maintainer PRs: {signals['focused_maintainer_prs']}",
                f"Total owned review items: {signals['total_owned_review_items']}",
                "External adoption claimed: False",
                "Formal Codex review claimed: False",
            ]
        )
        + "\n"
    )


def _evidence_review_packet(args: argparse.Namespace) -> int:
    try:
        payload = _public_review_packet_payload(Path("."))
    except FileNotFoundError as exc:
        print(f"Invalid review packet input: {exc}", file=sys.stderr)
        return 1
    if args.format == "json":
        text = _json_dump(payload)
    elif args.format == "markdown":
        text = _render_review_packet_markdown(payload)
    else:
        text = _render_review_packet_text(payload)
    _write_or_print(text, args.out)
    return 0 if payload["status"] == "owned_repo_review_packet_ready" else 1


def _evidence_snapshot_payload(root: Path) -> dict[str, Any]:
    fixture_root = root / "examples" / "ci-triage"
    log_paths = sorted(fixture_root.glob("*.log")) if fixture_root.exists() else []
    expected_paths = sorted(fixture_root.glob("*.expected.json")) if fixture_root.exists() else []
    benchmark = _run_ci_benchmark(fixture_root) if fixture_root.exists() else {}
    triage_workflow = _read_optional_text(root / ".github" / "workflows" / "ci-triage.yml")
    ci_workflow = _read_optional_text(root / ".github" / "workflows" / "ci.yml")
    adopters = _read_optional_text(root / "ADOPTERS.md")
    workflow_ledger = _read_optional_text(root / "docs" / "public-workflow-ledger.md")
    pilot_summaries = sorted((root / "examples" / "pilot-outcome").glob("*.summary.json"))
    approved_pilot_repositories: list[str] = []
    for path in pilot_summaries:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        repository = payload.get("repository")
        if payload.get("repository_mention_approved") is True and repository:
            approved_pilot_repositories.append(str(repository))

    release_evidence_pages = sorted((root / "docs").glob("release-v*.0-evidence.md"))
    required_docs = [
        "ETHICS.md",
        "SECURITY.md",
        "AGENTS.md",
        "docs/threat-model.md",
        "docs/codex-workflows.md",
        "docs/agent-control-plane.md",
        "docs/funded-issues-ethics.md",
        "docs/public-workflow-ledger.md",
        "docs/pilot-request-package.md",
        "docs/metrics.md",
        "docs/oss-program-evidence.md",
    ]
    missing_docs = [path for path in required_docs if not (root / path).exists()]
    read_only_workflow = (
        "contents: read" in triage_workflow
        and "actions: read" in triage_workflow
        and "issues: write" not in triage_workflow
        and "pull-requests: write" not in triage_workflow
        and "gh pr create" not in triage_workflow
        and "gh issue comment" not in triage_workflow
    )
    package_smoke = (
        "package-smoke:" in ci_workflow
        and "python -m pip install dist/*.whl" in ci_workflow
        and "twine check dist/*" in ci_workflow
    )
    no_public_external_adopters = "no public external adopters listed yet" in adopters
    public_adopters = 0 if no_public_external_adopters else None
    benchmark_passed = int(benchmark.get("passed", 0))
    benchmark_failed = int(benchmark.get("failed", 0))
    total_fixtures = len(log_paths)
    owned_issue_pr_cycles = _count_owned_issue_pr_cycles(workflow_ledger)
    review_packet = _public_review_packet_payload(root)
    return {
        "schema_version": "patchrail.evidence_snapshot.v1",
        "patchrail_version": __version__,
        "repository": "patchrail/patchrail",
        "generated_from": "local_checkout",
        "status": "needs_more_evidence"
        if public_adopters == 0 or not pilot_summaries
        else "ready_for_review",
        "signals": {
            "ci_fixtures": total_fixtures,
            "ci_expected_files": len(expected_paths),
            "ci_benchmark_passed": benchmark_passed,
            "ci_benchmark_failed": benchmark_failed,
            "ci_benchmark_top_1": benchmark.get("accuracy", {}).get("top_1"),
            "release_evidence_pages": [path.name for path in release_evidence_pages],
            "public_release_count": 1
            if (root / "docs" / "release-v0.1.0-evidence.md").exists()
            else 0,
            "public_external_adopters": public_adopters,
            "pilot_summary_count": len(pilot_summaries),
            "approved_pilot_repositories": sorted(set(approved_pilot_repositories)),
            "owned_repo_issue_pr_cycles": owned_issue_pr_cycles,
        },
        "workstreams": {
            "ci_janitor": {
                "status": "public_beta",
                "fixture_count": total_fixtures,
                "benchmark_green": total_fixtures > 0 and benchmark_failed == 0,
            },
            "github_action": {
                "status": "read_only_artifact",
                "read_only_permissions": read_only_workflow,
            },
            "agent_control_plane": {
                "status": "local_demo",
                "demo_present": (root / "examples" / "local-agent-queue" / "run_demo.py").exists(),
                "evidence_command": "patchrail evidence control-plane",
            },
            "funded_issue_scout": {
                "status": "read_only_demo",
                "demo_present": (
                    root / "examples" / "funded-issues-readonly" / "run_demo.py"
                ).exists(),
            },
            "release_packaging": {
                "status": "local_ready_pypi_blocked",
                "package_smoke_in_ci": package_smoke,
                "readiness_script_present": (root / "scripts" / "release_readiness.py").exists(),
            },
            "public_review_triage": {
                "status": "owned_repo_visible",
                "ledger_present": bool(workflow_ledger.strip()),
                "owned_issue_pr_cycles": owned_issue_pr_cycles,
                "focused_maintainer_prs": review_packet["signals"]["focused_maintainer_prs"],
                "review_packet_command": "patchrail evidence review-packet",
                "formal_codex_review_links": False,
            },
        },
        "safety": {
            "local_first": True,
            "read_only_ci_triage_workflow": read_only_workflow,
            "missing_required_docs": missing_docs,
            "no_public_external_adopters_without_permission": no_public_external_adopters,
            "github_write_permission_required": False,
            "external_model_required": False,
            "billing_required": False,
            "network_required": False,
        },
        "remaining_evidence_gaps": [
            "first PyPI publish and download telemetry",
            "permissioned external maintainer pilots",
            "formal visible Codex review links and external maintainer triage examples",
        ],
    }


def _count_owned_issue_pr_cycles(workflow_ledger: str) -> int:
    count = 0
    for line in workflow_ledger.splitlines():
        if (
            line.startswith("|")
            and "github.com/patchrail/patchrail/issues/" in line
            and "github.com/patchrail/patchrail/pull/" in line
        ):
            count += 1
    return count


def _render_evidence_snapshot_markdown(payload: dict[str, Any]) -> str:
    signals = payload["signals"]
    safety = payload["safety"]
    workstreams = payload["workstreams"]
    lines = [
        "# PatchRail OSS Evidence Snapshot",
        "",
        f"- Repository: `{payload['repository']}`",
        f"- Status: `{payload['status']}`",
        f"- PatchRail version: `{payload['patchrail_version']}`",
        f"- CI fixtures: `{signals['ci_fixtures']}`",
        (
            f"- Benchmark: `{signals['ci_benchmark_passed']} passed`, "
            f"`{signals['ci_benchmark_failed']} failed`"
        ),
        f"- Public external adopters: `{signals['public_external_adopters']}`",
        f"- Pilot summaries: `{signals['pilot_summary_count']}`",
        f"- Owned repo issue-to-PR cycles: `{signals['owned_repo_issue_pr_cycles']}`",
        "",
        "## Workstreams",
        "",
    ]
    for name, item in workstreams.items():
        details = ", ".join(f"{key}={value}" for key, value in item.items())
        lines.append(f"- `{name}`: {details}")
    lines.extend(
        [
            "",
            "## Safety",
            "",
            f"- Local-first: `{safety['local_first']}`",
            f"- Read-only CI triage workflow: `{safety['read_only_ci_triage_workflow']}`",
            f"- GitHub write permission required: `{safety['github_write_permission_required']}`",
            f"- External model required: `{safety['external_model_required']}`",
            f"- Billing required: `{safety['billing_required']}`",
            f"- Network required: `{safety['network_required']}`",
            "",
            "## Remaining Evidence Gaps",
            "",
        ]
    )
    lines.extend(f"- {gap}" for gap in payload["remaining_evidence_gaps"])
    return "\n".join(lines) + "\n"


def _render_evidence_snapshot_text(payload: dict[str, Any]) -> str:
    signals = payload["signals"]
    return (
        "\n".join(
            [
                f"Repository: {payload['repository']}",
                f"Status: {payload['status']}",
                f"CI fixtures: {signals['ci_fixtures']}",
                (
                    "Benchmark: "
                    f"{signals['ci_benchmark_passed']} passed, "
                    f"{signals['ci_benchmark_failed']} failed"
                ),
                f"Public external adopters: {signals['public_external_adopters']}",
                f"Pilot summaries: {signals['pilot_summary_count']}",
                f"Owned repo issue-to-PR cycles: {signals['owned_repo_issue_pr_cycles']}",
            ]
        )
        + "\n"
    )


def _evidence_snapshot(args: argparse.Namespace) -> int:
    payload = _evidence_snapshot_payload(Path("."))
    if args.format == "json":
        text = _json_dump(payload)
    elif args.format == "markdown":
        text = _render_evidence_snapshot_markdown(payload)
    else:
        text = _render_evidence_snapshot_text(payload)
    _write_or_print(text, args.out)
    return 0


def _exists(root: Path, relative_path: str) -> bool:
    return (root / relative_path).exists()


def _safe_evidence_path(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return path.name


def _roadmap_audit_payload(root: Path) -> dict[str, Any]:
    snapshot = _evidence_snapshot_payload(root)
    signals = snapshot["signals"]
    workstreams = snapshot["workstreams"]

    return {
        "schema_version": "patchrail.roadmap_audit.v1",
        "patchrail_version": __version__,
        "repository": "patchrail/patchrail",
        "generated_from": "local_checkout",
        "status": "active_not_ready_for_external_application",
        "versions": {
            "v0.1.0": {
                "status": "github_release_ready_pypi_blocked",
                "evidence": [
                    "docs/release-v0.1.0-evidence.md",
                    "dist/patchrail-0.1.0-py3-none-any.whl",
                    "dist/patchrail-0.1.0.tar.gz",
                    "README.md",
                    "ETHICS.md",
                    "SECURITY.md",
                    "AGENTS.md",
                ],
                "gaps": [
                    "first PyPI publish and clean install verification",
                    "PyPI download telemetry",
                ],
            },
            "v0.2.0": {
                "status": "benchmark_and_action_artifact_ready",
                "evidence": [
                    "docs/release-v0.2.0-evidence.md",
                    ".github/workflows/ci-triage.yml",
                    "examples/github-action/README.md",
                    "docs/ci-failure-zoo.md",
                    "docs/pilot-request-package.md",
                ],
                "signals": {
                    "ci_fixtures": signals["ci_fixtures"],
                    "ci_benchmark_failed": signals["ci_benchmark_failed"],
                    "read_only_github_action": workstreams["github_action"][
                        "read_only_permissions"
                    ],
                },
                "gaps": [
                    "permissioned external maintainer pilots",
                    "external repositories testing PatchRail",
                ],
            },
            "v0.3.0": {
                "status": "local_agent_control_plane_demo_ready",
                "evidence": [
                    "docs/release-v0.3.0-evidence.md",
                    "docs/agent-control-plane.md",
                    "docs/api-reference.md",
                    "examples/local-agent-queue/run_demo.py",
                    "examples/local-agent-queue/demo-summary.expected.json",
                    "src/patchrail/queue/store.py",
                    "src/patchrail/queue/server.py",
                ],
                "signals": {
                    "demo_present": workstreams["agent_control_plane"]["demo_present"],
                    "evidence_command": workstreams["agent_control_plane"]["evidence_command"],
                    "owned_repo_issue_pr_cycles": signals["owned_repo_issue_pr_cycles"],
                },
                "gaps": [
                    "formal visible review links",
                    "external maintainer triage examples with permission",
                ],
            },
            "v0.4.0": {
                "status": "read_only_demo_kept_secondary_no_money_goal",
                "evidence": [
                    "docs/release-v0.4.0-evidence.md",
                    "docs/funded-issues-ethics.md",
                    "examples/funded-issues-readonly/run_demo.py",
                    "src/patchrail/funded_issues/discovery.py",
                ],
                "signals": {
                    "demo_present": workstreams["funded_issue_scout"]["demo_present"],
                    "money_goal_retired": True,
                },
                "gaps": [
                    "keep funded issue discovery out of the primary narrative",
                    "do not process bounties, payouts, claims, outbound, or money-ranked leads",
                ],
            },
        },
        "weeks": {
            "week_1": {
                "status": "substantially_done",
                "focus": "sanitization, repositioning, CI Janitor CLI, docs, Apache-2.0, CI",
                "evidence": [
                    "README.md",
                    "LICENSE",
                    ".github/workflows/ci.yml",
                    "examples/ci-triage",
                ],
                "gaps": [],
            },
            "week_2": {
                "status": "partial_pypi_blocked",
                "focus": "v0.1.0 public release, JSON/Markdown outputs, redaction, fixtures",
                "evidence": ["docs/release-v0.1.0-evidence.md"],
                "gaps": ["PyPI publish requires maintainer package index credential"],
            },
            "week_3": {
                "status": "partial_owned_repo_evidence_only",
                "focus": "reviewable agent workflows and public evidence pack",
                "evidence": [
                    "docs/codex-workflows.md",
                    "docs/openai-codex-for-oss-evidence.md",
                    "docs/public-workflow-ledger.md",
                ],
                "gaps": ["formal visible review links remain pending"],
            },
            "week_4": {
                "status": "blocked_by_external_launch_gate",
                "focus": "initial launch and feedback",
                "evidence": ["docs/metrics.md", "docs/pilot-request-package.md"],
                "gaps": ["no public announcement or third-party outreach in this audit"],
            },
            "week_5": {
                "status": "partial",
                "focus": "GitHub Action and external fixture intake",
                "evidence": [
                    ".github/workflows/ci-triage.yml",
                    "examples/github-action/README.md",
                ],
                "gaps": ["permissioned maintainer logs and external fixtures"],
            },
            "week_6": {
                "status": "not_ready",
                "focus": "v0.2.0 launch and benchmark publication",
                "evidence": ["docs/release-v0.2.0-evidence.md"],
                "gaps": ["external metrics and launch feedback are not present"],
            },
            "week_7": {
                "status": "local_demo_ready",
                "focus": "Agent Control Plane v0.3 alpha",
                "evidence": [
                    "docs/agent-control-plane.md",
                    "examples/local-agent-queue/run_demo.py",
                ],
                "gaps": ["permissioned end-to-end external demo"],
            },
            "week_8": {
                "status": "pending_external_permission",
                "focus": "pilots and case studies",
                "evidence": ["docs/pilot-guide.md", "ADOPTERS.md"],
                "gaps": ["public external adopters remain 0"],
            },
            "week_9": {
                "status": "guardrailed_no_money_goal",
                "focus": "funded issue scout remains read-only and secondary",
                "evidence": ["docs/funded-issues-ethics.md"],
                "gaps": ["no bounty, payout, claim, outbound, or money-ranked work"],
            },
            "week_10": {
                "status": "partial",
                "focus": "release workflow and visible maintenance",
                "evidence": ["docs/release-process.md", "CHANGELOG.md"],
                "gaps": ["external contributors and release cadence evidence"],
            },
            "week_11": {
                "status": "pending_metrics",
                "focus": "application evidence preparation",
                "evidence": ["docs/openai-codex-for-oss-evidence.md", "docs/metrics.md"],
                "gaps": ["stars/downloads/adopters/review links are insufficient"],
            },
            "week_12": {
                "status": "not_ready",
                "focus": "apply or wait with criteria",
                "evidence": ["docs/oss-program-evidence.md"],
                "gaps": ["do not apply from placeholder metrics"],
            },
        },
        "safety": {
            "network_required": False,
            "github_write_permission_required": False,
            "billing_required": False,
            "external_model_required": False,
            "money_goal_retired": True,
            "manual_gates": [
                "PyPI publish",
                "public announcements",
                "external applications",
                "third-party repository writes",
                "payments, KYC, banking, tax, or destructive changes",
            ],
        },
        "artifact_presence": {
            "release_v0_1": _exists(root, "docs/release-v0.1.0-evidence.md"),
            "release_v0_2": _exists(root, "docs/release-v0.2.0-evidence.md"),
            "release_v0_3": _exists(root, "docs/release-v0.3.0-evidence.md"),
            "release_v0_4": _exists(root, "docs/release-v0.4.0-evidence.md"),
            "agent_control_plane_demo": _exists(root, "examples/local-agent-queue/run_demo.py"),
            "funded_issues_read_only_demo": _exists(
                root, "examples/funded-issues-readonly/run_demo.py"
            ),
            "github_action_example": _exists(root, "examples/github-action/README.md"),
        },
    }


def _render_roadmap_audit_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# PatchRail Roadmap Audit",
        "",
        f"- Repository: `{payload['repository']}`",
        f"- Status: `{payload['status']}`",
        f"- Generated from: `{payload['generated_from']}`",
        "",
        "## Versions",
        "",
    ]
    for version, item in payload["versions"].items():
        lines.append(f"### {version}")
        lines.append("")
        lines.append(f"- Status: `{item['status']}`")
        if "signals" in item:
            lines.append("- Signals:")
            for key, value in item["signals"].items():
                lines.append(f"  - `{key}`: `{value}`")
        lines.append("- Evidence:")
        lines.extend(f"  - `{path}`" for path in item["evidence"])
        lines.append("- Gaps:")
        lines.extend(f"  - {gap}" for gap in item["gaps"])
        lines.append("")

    lines.extend(["## Week Plan", ""])
    for week, item in payload["weeks"].items():
        lines.append(f"- `{week}`: `{item['status']}` - {item['focus']}")
    lines.extend(
        [
            "",
            "## Safety",
            "",
            f"- Network required: `{payload['safety']['network_required']}`",
            (
                "- GitHub write permission required: "
                f"`{payload['safety']['github_write_permission_required']}`"
            ),
            f"- Billing required: `{payload['safety']['billing_required']}`",
            f"- External model required: `{payload['safety']['external_model_required']}`",
            f"- Money goal retired: `{payload['safety']['money_goal_retired']}`",
            "- Manual gates:",
        ]
    )
    lines.extend(f"  - {gate}" for gate in payload["safety"]["manual_gates"])
    return "\n".join(lines) + "\n"


def _render_roadmap_audit_text(payload: dict[str, Any]) -> str:
    version_lines = [
        f"{version}: {item['status']}" for version, item in payload["versions"].items()
    ]
    week_lines = [f"{week}: {item['status']}" for week, item in payload["weeks"].items()]
    return (
        "\n".join(
            [
                f"Repository: {payload['repository']}",
                f"Status: {payload['status']}",
                "Versions:",
                *version_lines,
                "Weeks:",
                *week_lines,
            ]
        )
        + "\n"
    )


def _evidence_roadmap(args: argparse.Namespace) -> int:
    payload = _roadmap_audit_payload(Path("."))
    if args.format == "json":
        text = _json_dump(payload)
    elif args.format == "markdown":
        text = _render_roadmap_audit_markdown(payload)
    else:
        text = _render_roadmap_audit_text(payload)
    _write_or_print(text, args.out)
    return 0


def _control_plane_evidence_payload(root: Path, summary_path: Path | None) -> dict[str, Any]:
    summary_file = summary_path or (
        root / "examples" / "local-agent-queue" / "demo-summary.expected.json"
    )
    summary = json.loads(summary_file.read_text(encoding="utf-8"))
    if summary.get("schema_version") != "patchrail.local_agent_queue_demo.v1":
        raise ValueError("control plane summary must use patchrail.local_agent_queue_demo.v1")

    required_events = [
        "work_item_added",
        "proposal_added",
        "proposal_approved",
        "proposal_rejected",
        "work_item_approved",
        "work_item_rejected",
        "work_items_exported",
    ]
    audit_events = list(summary.get("audit_event_types") or [])
    missing_events = [event for event in required_events if event not in audit_events]
    artifact_files = list(summary.get("artifact_files") or [])
    required_artifacts = [
        "pilot-pack/pilot-manifest.json",
        "pilot-pack/patchrail-result.json",
        "item.json",
        "proposal-approved.json",
        "proposal-rejected.json",
        "approved.json",
        "rejected-item.json",
        "queue.jsonl",
        "audit-events.jsonl",
        "audit-summary.json",
    ]
    missing_artifacts = [
        artifact for artifact in required_artifacts if artifact not in artifact_files
    ]
    source_files = [
        "src/patchrail/queue/store.py",
        "src/patchrail/queue/server.py",
        "examples/local-agent-queue/run_demo.py",
        "docs/agent-control-plane.md",
        "docs/api-reference.md",
        "docs/release-v0.3.0-evidence.md",
    ]
    missing_source_files = [path for path in source_files if not (root / path).exists()]
    write_actions_allowed = summary.get("write_actions_allowed")
    rejected_write_actions_allowed = summary.get("rejected_item_write_actions_allowed")
    write_actions_blocked = write_actions_allowed is False
    rejected_write_actions_blocked = rejected_write_actions_allowed is False
    proposal_rejected = summary.get("rejected_proposal_approval_state") == "rejected"
    proposal_approved = summary.get("proposal_approval_state") == "approved"
    item_approved = summary.get("item_approval_state") == "approved"
    audit_summary_ready = summary.get("audit_summary_status") == "human_gates_exercised"
    audit_summary_missing_events = list(summary.get("audit_summary_missing_required_events") or [])
    local_first = summary.get("local_first") is True
    safety_gaps = []
    if not local_first:
        safety_gaps.append("local_first")
    if not write_actions_blocked:
        safety_gaps.append("write_actions_allowed_false")
    if not rejected_write_actions_blocked:
        safety_gaps.append("rejected_item_write_actions_allowed_false")
    if not item_approved:
        safety_gaps.append("human_approval_gate_exercised")
    if not proposal_approved:
        safety_gaps.append("proposal_approval_gate_exercised")
    if not proposal_rejected:
        safety_gaps.append("risky_proposal_rejection_exercised")
    if not audit_summary_ready:
        safety_gaps.append("audit_summary_human_gates_exercised")
    if audit_summary_missing_events:
        safety_gaps.append("audit_summary_missing_required_events")
    gaps = [*missing_events, *missing_artifacts, *missing_source_files, *safety_gaps]
    return {
        "schema_version": "patchrail.control_plane_evidence.v1",
        "patchrail_version": __version__,
        "repository": "patchrail/patchrail",
        "generated_from": "local_checkout",
        "summary_file": _safe_evidence_path(root, summary_file),
        "status": "local_demo_ready" if not gaps else "needs_attention",
        "signals": {
            "artifact_count": len(artifact_files),
            "audit_event_count": len(audit_events),
            "pending_items_before_decisions": summary.get("pending_items_before_decisions"),
            "source_failure_class": summary.get("source_failure_class"),
            "item_approval_state": summary.get("item_approval_state"),
            "proposal_approval_state": summary.get("proposal_approval_state"),
            "proposal_risk_level": summary.get("proposal_risk_level"),
            "rejected_item_approval_state": summary.get("rejected_item_approval_state"),
            "rejected_proposal_approval_state": summary.get("rejected_proposal_approval_state"),
            "audit_summary_status": summary.get("audit_summary_status"),
        },
        "safety": {
            "local_first": local_first,
            "write_actions_allowed": write_actions_allowed,
            "rejected_item_write_actions_allowed": rejected_write_actions_allowed,
            "human_approval_gate_exercised": item_approved,
            "proposal_approval_gate_exercised": proposal_approved,
            "risky_proposal_rejection_exercised": proposal_rejected,
            "audit_summary_human_gates_exercised": audit_summary_ready,
            "github_write_permission_required": False,
            "external_model_required": False,
            "billing_required": False,
            "network_required": False,
        },
        "artifact_presence": {
            "required_events_present": missing_events == [],
            "required_artifacts_present": missing_artifacts == [],
            "source_files_present": missing_source_files == [],
            "missing_events": missing_events,
            "missing_artifacts": missing_artifacts,
            "missing_source_files": missing_source_files,
            "audit_summary_missing_required_events": audit_summary_missing_events,
            "safety_gaps": safety_gaps,
        },
        "remaining_evidence_gaps": [
            "permissioned external maintainer control-plane demo",
            "formal visible review links for agent handoff examples",
            "public adopter report that explicitly approves repository listing",
        ],
    }


def _render_control_plane_evidence_markdown(payload: dict[str, Any]) -> str:
    signals = payload["signals"]
    safety = payload["safety"]
    artifacts = payload["artifact_presence"]
    lines = [
        "# PatchRail Agent Control Plane Evidence",
        "",
        f"- Repository: `{payload['repository']}`",
        f"- Status: `{payload['status']}`",
        f"- Summary file: `{payload['summary_file']}`",
        f"- Artifact count: `{signals['artifact_count']}`",
        f"- Audit event count: `{signals['audit_event_count']}`",
        f"- Source failure class: `{signals['source_failure_class']}`",
        f"- Proposal approval state: `{signals['proposal_approval_state']}`",
        f"- Risky proposal rejection state: `{signals['rejected_proposal_approval_state']}`",
        f"- Audit summary status: `{signals['audit_summary_status']}`",
        "",
        "## Safety",
        "",
        f"- Local-first: `{safety['local_first']}`",
        f"- Write actions allowed: `{safety['write_actions_allowed']}`",
        f"- Rejected item write actions allowed: `{safety['rejected_item_write_actions_allowed']}`",
        f"- Human approval gate exercised: `{safety['human_approval_gate_exercised']}`",
        f"- Proposal approval gate exercised: `{safety['proposal_approval_gate_exercised']}`",
        f"- Risky proposal rejection exercised: `{safety['risky_proposal_rejection_exercised']}`",
        f"- Audit summary human gates exercised: `{safety['audit_summary_human_gates_exercised']}`",
        f"- GitHub write permission required: `{safety['github_write_permission_required']}`",
        f"- External model required: `{safety['external_model_required']}`",
        f"- Billing required: `{safety['billing_required']}`",
        f"- Network required: `{safety['network_required']}`",
        "",
        "## Artifact Presence",
        "",
        f"- Required events present: `{artifacts['required_events_present']}`",
        f"- Required artifacts present: `{artifacts['required_artifacts_present']}`",
        f"- Source files present: `{artifacts['source_files_present']}`",
        "",
        "## Remaining Evidence Gaps",
        "",
    ]
    lines.extend(f"- {gap}" for gap in payload["remaining_evidence_gaps"])
    return "\n".join(lines) + "\n"


def _render_control_plane_evidence_text(payload: dict[str, Any]) -> str:
    signals = payload["signals"]
    return (
        "\n".join(
            [
                f"Repository: {payload['repository']}",
                f"Status: {payload['status']}",
                f"Summary file: {payload['summary_file']}",
                f"Artifacts: {signals['artifact_count']}",
                f"Audit events: {signals['audit_event_count']}",
                f"Write actions allowed: {payload['safety']['write_actions_allowed']}",
                (
                    "Risky proposal rejected: "
                    f"{payload['safety']['risky_proposal_rejection_exercised']}"
                ),
                (
                    "Audit summary human gates exercised: "
                    f"{payload['safety']['audit_summary_human_gates_exercised']}"
                ),
            ]
        )
        + "\n"
    )


def _evidence_control_plane(args: argparse.Namespace) -> int:
    try:
        payload = _control_plane_evidence_payload(Path("."), args.summary)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        print(f"Invalid control-plane evidence input: {exc}", file=sys.stderr)
        return 1
    if args.format == "json":
        text = _json_dump(payload)
    elif args.format == "markdown":
        text = _render_control_plane_evidence_markdown(payload)
    else:
        text = _render_control_plane_evidence_text(payload)
    _write_or_print(text, args.out)
    return 0 if payload["status"] == "local_demo_ready" else 1


def _http_json_request(url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=5) as response:
        decoded = json.loads(response.read().decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("HTTP evidence endpoint returned a non-object JSON payload")
    return decoded


def _http_api_evidence_payload() -> dict[str, Any]:
    endpoints_checked: list[str] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "queue.sqlite"
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_queue_api_handler(db_path))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            health = _http_json_request(f"{base_url}/health")
            endpoints_checked.append("GET /health")

            item = _http_json_request(
                f"{base_url}/work-items",
                {
                    "kind": "ci_failure",
                    "title": "Review local CI failure evidence",
                    "source": "http-api-evidence",
                    "payload": {"report": "ci-result.json"},
                },
            )
            duplicate_item = _http_json_request(
                f"{base_url}/work-items",
                {
                    "kind": "ci_failure",
                    "title": "Reject duplicate local CI failure evidence",
                    "source": "http-api-evidence",
                    "payload": {"reason": "duplicate local evidence"},
                },
            )
            endpoints_checked.append("POST /work-items")

            proposal = _http_json_request(
                f"{base_url}/proposals",
                {
                    "work_item_id": item["id"],
                    "title": "Patch local dependency range",
                    "summary": "Maintainer-reviewed local proposal only.",
                    "patch_plan": "Reproduce locally, patch constraints, rerun tests.",
                    "risk_level": "low",
                },
            )
            risky_proposal = _http_json_request(
                f"{base_url}/proposals",
                {
                    "work_item_id": duplicate_item["id"],
                    "title": "Open an automatic pull request",
                    "summary": "Rejected because it would skip maintainer review.",
                    "patch_plan": "Generate a patch and open a PR automatically.",
                    "risk_level": "high",
                },
            )
            endpoints_checked.append("POST /proposals")

            approved_proposal = _http_json_request(
                f"{base_url}/proposals/{proposal['id']}/approve",
                {"note": "Maintainer approved the local proposal record."},
            )
            endpoints_checked.append("POST /proposals/{id}/approve")

            rejected_proposal = _http_json_request(
                f"{base_url}/proposals/{risky_proposal['id']}/reject",
                {"note": "Maintainer rejected the automatic PR proposal."},
            )
            endpoints_checked.append("POST /proposals/{id}/reject")

            approved_item = _http_json_request(
                f"{base_url}/work-items/{item['id']}/approve",
                {"note": "Maintainer approved local queue handoff."},
            )
            endpoints_checked.append("POST /work-items/{id}/approve")

            rejected_item = _http_json_request(
                f"{base_url}/work-items/{duplicate_item['id']}/reject",
                {"note": "Maintainer rejected duplicate local queue item."},
            )
            endpoints_checked.append("POST /work-items/{id}/reject")

            status = _http_json_request(f"{base_url}/status")
            endpoints_checked.append("GET /status")
            work_items = _http_json_request(f"{base_url}/work-items")
            endpoints_checked.append("GET /work-items")
            proposals = _http_json_request(f"{base_url}/proposals")
            endpoints_checked.append("GET /proposals")
            audit_events = _http_json_request(f"{base_url}/audit-events")
            endpoints_checked.append("GET /audit-events")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    requirements = dict(health.get("requirements") or {})
    safety = dict(status.get("safety") or {})
    audit_event_types = [
        str(event.get("event_type")) for event in audit_events.get("audit_events", [])
    ]
    required_events = [
        "work_item_added",
        "proposal_added",
        "proposal_approved",
        "proposal_rejected",
        "work_item_approved",
        "work_item_rejected",
    ]
    missing_events = [event for event in required_events if event not in audit_event_types]
    expected_endpoints = [
        "GET /health",
        "GET /status",
        "GET /work-items",
        "POST /work-items",
        "POST /work-items/{id}/approve",
        "POST /work-items/{id}/reject",
        "GET /proposals",
        "POST /proposals",
        "POST /proposals/{id}/approve",
        "POST /proposals/{id}/reject",
        "GET /audit-events",
    ]
    missing_endpoints = [
        endpoint for endpoint in expected_endpoints if endpoint not in endpoints_checked
    ]
    safety_gaps = []
    if health.get("local_first") is not True:
        safety_gaps.append("health_local_first")
    if requirements.get("network_required") is not False:
        safety_gaps.append("network_required_false")
    if requirements.get("github_write_permission_required") is not False:
        safety_gaps.append("github_write_permission_required_false")
    if requirements.get("external_model_required") is not False:
        safety_gaps.append("external_model_required_false")
    if requirements.get("billing_required") is not False:
        safety_gaps.append("billing_required_false")
    if safety.get("approval_records_execute_actions") is not False:
        safety_gaps.append("approval_records_execute_actions_false")
    if approved_item.get("write_actions_allowed") is not False:
        safety_gaps.append("approved_item_write_actions_allowed_false")
    if rejected_item.get("write_actions_allowed") is not False:
        safety_gaps.append("rejected_item_write_actions_allowed_false")
    if approved_proposal.get("approval_state") != "approved":
        safety_gaps.append("proposal_approval_gate_exercised")
    if rejected_proposal.get("approval_state") != "rejected":
        safety_gaps.append("proposal_rejection_gate_exercised")
    gaps = [*missing_events, *missing_endpoints, *safety_gaps]
    return {
        "schema_version": "patchrail.http_api_evidence.v1",
        "patchrail_version": __version__,
        "repository": "patchrail/patchrail",
        "generated_from": "ephemeral_local_http_server",
        "status": "local_http_api_ready" if not gaps else "needs_attention",
        "server": {
            "bind_host": "127.0.0.1",
            "base_url": base_url,
            "database": "temporary SQLite database",
        },
        "endpoints_checked": endpoints_checked,
        "signals": {
            "work_items_total": status["counts"]["work_items_total"],
            "proposals_total": status["counts"]["proposals_total"],
            "audit_events_total": status["counts"]["audit_events_total"],
            "latest_audit_event": status["latest_audit_event"]["event_type"],
            "approved_work_items": status["counts"]["work_items_by_approval_state"].get(
                "approved", 0
            ),
            "rejected_work_items": status["counts"]["work_items_by_approval_state"].get(
                "rejected", 0
            ),
            "approved_proposals": status["counts"]["proposals_by_approval_state"].get(
                "approved", 0
            ),
            "rejected_proposals": status["counts"]["proposals_by_approval_state"].get(
                "rejected", 0
            ),
            "listed_work_items": len(work_items.get("work_items", [])),
            "listed_proposals": len(proposals.get("proposals", [])),
        },
        "safety": {
            "local_first": health.get("local_first") is True,
            "bind_host_local_only": True,
            "network_required": requirements.get("network_required"),
            "github_write_permission_required": requirements.get(
                "github_write_permission_required"
            ),
            "external_model_required": requirements.get("external_model_required"),
            "billing_required": requirements.get("billing_required"),
            "approval_records_execute_actions": safety.get("approval_records_execute_actions"),
            "approved_item_write_actions_allowed": approved_item.get("write_actions_allowed"),
            "rejected_item_write_actions_allowed": rejected_item.get("write_actions_allowed"),
            "proposal_approval_gate_exercised": approved_proposal.get("approval_state")
            == "approved",
            "proposal_rejection_gate_exercised": rejected_proposal.get("approval_state")
            == "rejected",
        },
        "artifact_presence": {
            "required_events_present": missing_events == [],
            "required_endpoints_present": missing_endpoints == [],
            "missing_events": missing_events,
            "missing_endpoints": missing_endpoints,
            "safety_gaps": safety_gaps,
        },
        "remaining_evidence_gaps": [
            "permissioned external maintainer control-plane demo",
            "formal visible review links for agent handoff examples",
            "public adopter report that explicitly approves repository listing",
        ],
    }


def _render_http_api_evidence_markdown(payload: dict[str, Any]) -> str:
    signals = payload["signals"]
    safety = payload["safety"]
    artifacts = payload["artifact_presence"]
    lines = [
        "# PatchRail HTTP API Evidence",
        "",
        f"- Repository: `{payload['repository']}`",
        f"- Status: `{payload['status']}`",
        f"- Generated from: `{payload['generated_from']}`",
        f"- Bind host: `{payload['server']['bind_host']}`",
        f"- Base URL: `{payload['server']['base_url']}`",
        "",
        "## Endpoint Smoke",
        "",
    ]
    lines.extend(f"- `{endpoint}`" for endpoint in payload["endpoints_checked"])
    lines.extend(
        [
            "",
            "## Signals",
            "",
            f"- Work items total: `{signals['work_items_total']}`",
            f"- Proposals total: `{signals['proposals_total']}`",
            f"- Audit events total: `{signals['audit_events_total']}`",
            f"- Latest audit event: `{signals['latest_audit_event']}`",
            f"- Approved work items: `{signals['approved_work_items']}`",
            f"- Rejected work items: `{signals['rejected_work_items']}`",
            f"- Approved proposals: `{signals['approved_proposals']}`",
            f"- Rejected proposals: `{signals['rejected_proposals']}`",
            "",
            "## Safety",
            "",
            f"- Local-first: `{safety['local_first']}`",
            f"- Bind host local-only: `{safety['bind_host_local_only']}`",
            f"- Network required: `{safety['network_required']}`",
            (f"- GitHub write permission required: `{safety['github_write_permission_required']}`"),
            f"- External model required: `{safety['external_model_required']}`",
            f"- Billing required: `{safety['billing_required']}`",
            (f"- Approval records execute actions: `{safety['approval_records_execute_actions']}`"),
            (
                "- Approved item write actions allowed: "
                f"`{safety['approved_item_write_actions_allowed']}`"
            ),
            (
                "- Rejected item write actions allowed: "
                f"`{safety['rejected_item_write_actions_allowed']}`"
            ),
            (f"- Proposal approval gate exercised: `{safety['proposal_approval_gate_exercised']}`"),
            (
                "- Proposal rejection gate exercised: "
                f"`{safety['proposal_rejection_gate_exercised']}`"
            ),
            "",
            "## Artifact Presence",
            "",
            f"- Required events present: `{artifacts['required_events_present']}`",
            f"- Required endpoints present: `{artifacts['required_endpoints_present']}`",
            "",
            "## Remaining Evidence Gaps",
            "",
        ]
    )
    lines.extend(f"- {gap}" for gap in payload["remaining_evidence_gaps"])
    return "\n".join(lines) + "\n"


def _render_http_api_evidence_text(payload: dict[str, Any]) -> str:
    signals = payload["signals"]
    safety = payload["safety"]
    return (
        "\n".join(
            [
                f"Repository: {payload['repository']}",
                f"Status: {payload['status']}",
                f"Bind host: {payload['server']['bind_host']}",
                f"Endpoints checked: {len(payload['endpoints_checked'])}",
                f"Work items: {signals['work_items_total']}",
                f"Proposals: {signals['proposals_total']}",
                f"Audit events: {signals['audit_events_total']}",
                f"Network required: {safety['network_required']}",
                (f"GitHub write permission required: {safety['github_write_permission_required']}"),
                (f"Approval records execute actions: {safety['approval_records_execute_actions']}"),
            ]
        )
        + "\n"
    )


def _evidence_http_api(args: argparse.Namespace) -> int:
    try:
        payload = _http_api_evidence_payload()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Invalid HTTP API evidence run: {exc}", file=sys.stderr)
        return 1
    if args.format == "json":
        text = _json_dump(payload)
    elif args.format == "markdown":
        text = _render_http_api_evidence_markdown(payload)
    else:
        text = _render_http_api_evidence_text(payload)
    _write_or_print(text, args.out)
    return 0 if payload["status"] == "local_http_api_ready" else 1


def _queue_db(args: argparse.Namespace) -> Path:
    return Path(args.db) if args.db else DEFAULT_QUEUE_PATH


def _queue_payload_from_ci_result(path: Path) -> tuple[str, str, str, dict[str, Any]]:
    ci_result = json.loads(path.read_text(encoding="utf-8"))
    if ci_result.get("schema_version") != "patchrail.ci_result.v1":
        raise ValueError("CI result must use schema_version patchrail.ci_result.v1")

    failure_class = str(ci_result.get("failure_class") or "unknown")
    likely_subsystem = str(ci_result.get("likely_subsystem") or "unknown subsystem")
    title = f"Review {failure_class} CI failure"
    payload = {
        "ci_result": ci_result,
        "failure_class": failure_class,
        "likely_subsystem": likely_subsystem,
        "minimal_repair_strategy": ci_result.get("minimal_repair_strategy"),
        "report_source": str(path),
    }
    return "ci_failure", title, str(path), payload


def _queue_payload_from_pilot_pack(path: Path) -> tuple[str, str, str, dict[str, Any]]:
    manifest_path = path / "pilot-manifest.json" if path.is_dir() else path
    manifest_dir = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "patchrail.ci_pilot_pack.v1":
        raise ValueError("pilot pack must use schema_version patchrail.ci_pilot_pack.v1")
    source = manifest.get("source") or {}
    if source.get("raw_log_copied") is not False:
        raise ValueError("pilot pack must not copy the raw CI log")

    files_payload = manifest.get("files") or {}
    result_name = files_payload.get("json_result")
    if not result_name:
        raise ValueError("pilot pack manifest must include files.json_result")
    result_path = manifest_dir / str(result_name)
    ci_result = json.loads(result_path.read_text(encoding="utf-8"))
    if ci_result.get("schema_version") != "patchrail.ci_result.v1":
        raise ValueError("pilot pack result must use schema_version patchrail.ci_result.v1")

    failure_class = str(ci_result.get("failure_class") or "unknown")
    likely_subsystem = str(ci_result.get("likely_subsystem") or "unknown subsystem")
    title = f"Review {failure_class} CI pilot pack"
    pack_files = {key: str(value) for key, value in files_payload.items() if isinstance(value, str)}
    payload = {
        "ci_result": ci_result,
        "failure_class": failure_class,
        "likely_subsystem": likely_subsystem,
        "minimal_repair_strategy": ci_result.get("minimal_repair_strategy"),
        "pilot_pack": {
            "manifest": manifest,
            "manifest_path": str(manifest_path),
            "files": pack_files,
            "raw_log_copied": False,
            "maintainer_review_required_before_sharing": True,
        },
        "report_source": str(result_path),
    }
    return "ci_failure", title, str(manifest_path), payload


def _render_queue_items_text(items: list[dict[str, Any]]) -> str:
    if not items:
        return "No work items.\n"
    lines = []
    for item in items:
        lines.append(f"{item['id']} [{item['approval_state']}] {item['kind']}: {item['title']}")
    return "\n".join(lines) + "\n"


def _render_queue_item_markdown(item: dict[str, Any]) -> str:
    lines = [
        "# PatchRail Queue Item",
        "",
        f"- ID: `{item['id']}`",
        f"- Kind: `{item['kind']}`",
        f"- Title: {item['title']}",
        f"- Source: `{item['source']}`",
        f"- Status: `{item['status']}`",
        f"- Approval state: `{item['approval_state']}`",
        f"- Write actions allowed: `{item['write_actions_allowed']}`",
        f"- Created: `{item['created_at']}`",
        f"- Updated: `{item['updated_at']}`",
    ]
    if item.get("decision_note"):
        lines.append(f"- Decision note: {item['decision_note']}")
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "Queue items are local records. PatchRail does not execute write actions, "
            "post comments, open pull requests, or contact third-party repositories from this command.",
        ]
    )
    return "\n".join(lines) + "\n"


def _render_queue_export_jsonl(payload: dict[str, Any]) -> str:
    return "".join(json.dumps(item, sort_keys=True) + "\n" for item in payload["work_items"])


def _render_queue_audit_jsonl(payload: dict[str, Any]) -> str:
    return "".join(json.dumps(event, sort_keys=True) + "\n" for event in payload["audit_events"])


def _render_queue_audit_text(events: list[dict[str, Any]]) -> str:
    if not events:
        return "No audit events.\n"
    lines = []
    for event in events:
        target = event["work_item_id"] or "queue"
        lines.append(f"{event['id']} {event['ts']} {event['event_type']} {target}")
    return "\n".join(lines) + "\n"


def _render_queue_audit_summary_text(payload: dict[str, Any]) -> str:
    counts = payload["counts"]
    lines = [
        "PatchRail Queue Audit Summary",
        f"DB: {payload['db_path']}",
        f"Status: {payload['status']}",
        f"Audit events: {counts['audit_events_total']}",
        f"Affected work items: {counts['affected_work_items']}",
        f"Missing required events: {payload['missing_required_events']}",
        "Write actions allowed by default: False",
        "Approval records execute actions: False",
    ]
    for event_type, count in counts["event_types"].items():
        lines.append(f"{event_type}: {count}")
    return "\n".join(lines) + "\n"


def _render_queue_audit_summary_markdown(payload: dict[str, Any]) -> str:
    counts = payload["counts"]
    gates = payload["gates"]
    lines = [
        "# PatchRail Queue Audit Summary",
        "",
        f"- DB: `{payload['db_path']}`",
        f"- Status: `{payload['status']}`",
        f"- Audit events: `{counts['audit_events_total']}`",
        f"- Work items: `{counts['work_items_total']}`",
        f"- Proposals: `{counts['proposals_total']}`",
        f"- Affected work items: `{counts['affected_work_items']}`",
        "",
        "## Required Events",
        "",
    ]
    for event_type in payload["required_events"]:
        present = event_type not in payload["missing_required_events"]
        lines.append(f"- `{event_type}`: `{present}`")
    lines.extend(["", "## Human Gates", ""])
    for gate, exercised in gates.items():
        lines.append(f"- `{gate}`: `{exercised}`")
    lines.extend(["", "## Event Counts", ""])
    if counts["event_types"]:
        lines.extend(
            f"- `{event_type}`: `{count}`" for event_type, count in counts["event_types"].items()
        )
    else:
        lines.append("- No audit events recorded.")
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- Local-first: `True`",
            "- Write actions allowed by default: `False`",
            "- GitHub write permission required: `False`",
            "- Network required: `False`",
            "- External model required: `False`",
            "- Billing required: `False`",
            "- Approval records execute actions: `False`",
        ]
    )
    return "\n".join(lines) + "\n"


def _render_queue_bundle_markdown(payload: dict[str, Any]) -> str:
    counts = payload["counts"]
    safety = payload["safety"]
    audit_summary = payload["audit_summary"]
    lines = [
        "# PatchRail Queue Bundle",
        "",
        f"- DB: `{payload['db_path']}`",
        f"- Status: `{payload['status']}`",
        f"- Local-first: `{payload['local_first']}`",
        f"- Work items: `{counts['work_items_total']}`",
        f"- Proposals: `{counts['proposals_total']}`",
        f"- Audit events: `{counts['audit_events_total']}`",
        f"- Audit summary status: `{audit_summary['status']}`",
        "",
        "## Human Gate Coverage",
        "",
    ]
    for event_type in audit_summary["required_events"]:
        present = event_type not in audit_summary["missing_required_events"]
        lines.append(f"- `{event_type}`: `{present}`")
    lines.extend(
        [
            "",
            "## Safety",
            "",
            f"- Local-first: `{payload['local_first']}`",
            f"- Write actions allowed by default: `{safety['write_actions_allowed_by_default']}`",
            f"- GitHub write permission required: `{safety['github_write_permission_required']}`",
            f"- Network required: `{safety['network_required']}`",
            f"- External model required: `{safety['external_model_required']}`",
            f"- Billing required: `{safety['billing_required']}`",
            f"- Approval records execute actions: `{safety['approval_records_execute_actions']}`",
            f"- Bundle is read-only: `{safety['bundle_is_read_only']}`",
            f"- Bundle records audit event: `{safety['bundle_records_audit_event']}`",
            f"- Local paths redacted: `{safety['local_paths_redacted']}`",
            "",
            "## Remaining Gate Gaps",
            "",
        ]
    )
    if payload["remaining_gate_gaps"]:
        lines.extend(f"- `{gap}`" for gap in payload["remaining_gate_gaps"])
    else:
        lines.append("- None.")
    return "\n".join(lines) + "\n"


def _render_queue_bundle_text(payload: dict[str, Any]) -> str:
    counts = payload["counts"]
    return (
        "\n".join(
            [
                "PatchRail Queue Bundle",
                f"DB: {payload['db_path']}",
                f"Status: {payload['status']}",
                f"Work items: {counts['work_items_total']}",
                f"Proposals: {counts['proposals_total']}",
                f"Audit events: {counts['audit_events_total']}",
                f"Missing gate events: {payload['remaining_gate_gaps']}",
                "Bundle is read-only: True",
                "Bundle records audit event: False",
                "Local paths redacted: True",
            ]
        )
        + "\n"
    )


def _render_queue_status_text(payload: dict[str, Any]) -> str:
    counts = payload["counts"]
    latest = payload["latest_audit_event"]
    latest_label = (
        f"{latest['id']} {latest['event_type']} {latest['work_item_id'] or 'queue'}"
        if latest
        else "none"
    )
    lines = [
        "PatchRail Queue Status",
        f"DB: {payload['db_path']}",
        f"Local-first: {payload['local_first']}",
        f"Work items: {counts['work_items_total']}",
        f"Work item approvals: {counts['work_items_by_approval_state']}",
        f"Work item statuses: {counts['work_items_by_status']}",
        f"Proposals: {counts['proposals_total']}",
        f"Proposal approvals: {counts['proposals_by_approval_state']}",
        f"Audit events: {counts['audit_events_total']}",
        f"Latest audit event: {latest_label}",
        "Write actions allowed by default: False",
        "Network required: False",
        "External model required: False",
    ]
    return "\n".join(lines) + "\n"


def _render_queue_status_markdown(payload: dict[str, Any]) -> str:
    counts = payload["counts"]
    latest = payload["latest_audit_event"]
    lines = [
        "# PatchRail Queue Status",
        "",
        f"- DB: `{payload['db_path']}`",
        f"- Local-first: `{payload['local_first']}`",
        f"- Work items: `{counts['work_items_total']}`",
        f"- Proposals: `{counts['proposals_total']}`",
        f"- Audit events: `{counts['audit_events_total']}`",
        "",
        "## Work Items",
        "",
    ]
    work_item_states = counts["work_items_by_approval_state"] or {}
    if work_item_states:
        lines.extend(f"- `{state}`: `{count}`" for state, count in work_item_states.items())
    else:
        lines.append("- No work items recorded.")
    lines.extend(["", "## Proposals", ""])
    proposal_states = counts["proposals_by_approval_state"] or {}
    if proposal_states:
        lines.extend(f"- `{state}`: `{count}`" for state, count in proposal_states.items())
    else:
        lines.append("- No proposals recorded.")
    lines.extend(["", "## Latest Audit Event", ""])
    if latest:
        lines.extend(
            [
                f"- ID: `{latest['id']}`",
                f"- Type: `{latest['event_type']}`",
                f"- Work item: `{latest['work_item_id'] or 'queue'}`",
            ]
        )
    else:
        lines.append("- No audit events recorded.")
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- Write actions allowed by default: `False`",
            "- GitHub write permission required: `False`",
            "- Network required: `False`",
            "- External model required: `False`",
            "- Billing required: `False`",
            "- Approval records execute actions: `False`",
        ]
    )
    return "\n".join(lines) + "\n"


def _render_proposals_text(proposals: list[dict[str, Any]]) -> str:
    if not proposals:
        return "No proposals.\n"
    lines = []
    for proposal in proposals:
        lines.append(
            f"{proposal['id']} [{proposal['approval_state']}] "
            f"{proposal['risk_level']} {proposal['title']}"
        )
    return "\n".join(lines) + "\n"


def _render_proposal_markdown(proposal: dict[str, Any]) -> str:
    lines = [
        "# PatchRail Proposal",
        "",
        f"- ID: `{proposal['id']}`",
        f"- Work item: `{proposal['work_item_id']}`",
        f"- Title: {proposal['title']}",
        f"- Risk level: `{proposal['risk_level']}`",
        f"- Approval state: `{proposal['approval_state']}`",
        f"- Created: `{proposal['created_at']}`",
        f"- Updated: `{proposal['updated_at']}`",
        "",
        "## Summary",
        "",
        proposal["summary"],
        "",
        "## Patch Plan",
        "",
        proposal["patch_plan"],
    ]
    if proposal.get("decision_note"):
        lines.extend(["", "## Decision Note", "", proposal["decision_note"]])
    lines.extend(
        [
            "",
            "## Safety",
            "",
            (
                "This proposal is a local review record. Approval records maintainer intent; "
                "it does not push commits, open pull requests, post comments, or contact repositories."
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def _queue_init(args: argparse.Namespace) -> int:
    payload = init_queue(_queue_db(args))
    _write_or_print(_json_dump(payload), args.out)
    return 0


def _queue_add(args: argparse.Namespace) -> int:
    item_payload: dict[str, Any] = {}
    kind = args.kind
    title = args.title
    source = args.source
    if args.from_ci_result and args.from_pilot_pack:
        print("queue add accepts only one import source", file=sys.stderr)
        return 1
    if args.from_ci_result:
        try:
            imported_kind, imported_title, imported_source, item_payload = (
                _queue_payload_from_ci_result(args.from_ci_result)
            )
        except (json.JSONDecodeError, ValueError) as exc:
            print(f"Invalid CI result: {exc}", file=sys.stderr)
            return 1
        kind = kind or imported_kind
        title = title or imported_title
        source = source if source != "manual" else imported_source
    if args.from_pilot_pack:
        try:
            imported_kind, imported_title, imported_source, item_payload = (
                _queue_payload_from_pilot_pack(args.from_pilot_pack)
            )
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
            print(f"Invalid pilot pack: {exc}", file=sys.stderr)
            return 1
        kind = kind or imported_kind
        title = title or imported_title
        source = source if source != "manual" else imported_source
    if args.payload_json:
        extra_payload = json.loads(args.payload_json)
        item_payload = {**item_payload, **extra_payload}
    if not kind or not title:
        print(
            "queue add requires --kind and --title unless --from-ci-result is provided",
            file=sys.stderr,
        )
        return 1
    item = add_work_item(
        db_path=_queue_db(args),
        kind=kind,
        title=title,
        source=source,
        payload=item_payload,
    ).to_dict()
    _write_or_print(_json_dump(item), args.out)
    return 0


def _queue_list(args: argparse.Namespace) -> int:
    items = [
        item.to_dict()
        for item in list_work_items(
            db_path=_queue_db(args),
            status=args.status,
            approval_state=args.approval_state,
        )
    ]
    if args.format == "json":
        text = _json_dump({"schema_version": "patchrail.queue.v1", "work_items": items})
    else:
        text = _render_queue_items_text(items)
    _write_or_print(text, args.out)
    return 0


def _queue_show(args: argparse.Namespace) -> int:
    try:
        item = show_work_item(db_path=_queue_db(args), item_id=args.item_id).to_dict()
    except KeyError:
        print(f"Unknown work item: {args.item_id}", file=sys.stderr)
        return 1
    if args.format == "json":
        text = _json_dump(item)
    elif args.format == "markdown":
        text = _render_queue_item_markdown(item)
    else:
        text = _render_queue_items_text([item])
    _write_or_print(text, args.out)
    return 0


def _queue_approve(args: argparse.Namespace) -> int:
    try:
        item = approve_work_item(
            db_path=_queue_db(args),
            item_id=args.item_id,
            decision_note=args.note,
        ).to_dict()
    except KeyError:
        print(f"Unknown work item: {args.item_id}", file=sys.stderr)
        return 1
    _write_or_print(_json_dump(item), args.out)
    return 0


def _queue_reject(args: argparse.Namespace) -> int:
    try:
        item = reject_work_item(
            db_path=_queue_db(args),
            item_id=args.item_id,
            decision_note=args.note,
        ).to_dict()
    except KeyError:
        print(f"Unknown work item: {args.item_id}", file=sys.stderr)
        return 1
    _write_or_print(_json_dump(item), args.out)
    return 0


def _queue_skip(args: argparse.Namespace) -> int:
    try:
        item = skip_work_item(
            db_path=_queue_db(args),
            item_id=args.item_id,
            decision_note=args.reason,
        ).to_dict()
    except KeyError:
        print(f"Unknown work item: {args.item_id}", file=sys.stderr)
        return 1
    _write_or_print(_json_dump(item), args.out)
    return 0


def _queue_export(args: argparse.Namespace) -> int:
    payload = export_work_items(db_path=_queue_db(args))
    if args.format == "jsonl":
        text = _render_queue_export_jsonl(payload)
    else:
        text = _json_dump(payload)
    _write_or_print(text, args.out)
    return 0


def _queue_audit(args: argparse.Namespace) -> int:
    payload = export_audit_events(db_path=_queue_db(args), work_item_id=args.item_id)
    if args.format == "jsonl":
        text = _render_queue_audit_jsonl(payload)
    elif args.format == "json":
        text = _json_dump(payload)
    else:
        text = _render_queue_audit_text(payload["audit_events"])
    _write_or_print(text, args.out)
    return 0


def _queue_audit_summary(args: argparse.Namespace) -> int:
    payload = queue_audit_summary_payload(
        _queue_db(args),
        required_events=args.require_event,
    )
    if args.format == "json":
        text = _json_dump(payload)
    elif args.format == "markdown":
        text = _render_queue_audit_summary_markdown(payload)
    else:
        text = _render_queue_audit_summary_text(payload)
    _write_or_print(text, args.out)
    return 0 if payload["status"] == "human_gates_exercised" else 1


def _queue_bundle(args: argparse.Namespace) -> int:
    payload = queue_bundle_payload(
        _queue_db(args),
        required_events=args.require_event,
    )
    if args.format == "json":
        text = _json_dump(payload)
    elif args.format == "markdown":
        text = _render_queue_bundle_markdown(payload)
    else:
        text = _render_queue_bundle_text(payload)
    _write_or_print(text, args.out)
    return 0 if payload["status"] == "ready_for_handoff" else 1


def _queue_status(args: argparse.Namespace) -> int:
    payload = queue_status_payload(_queue_db(args))
    if args.format == "json":
        text = _json_dump(payload)
    elif args.format == "markdown":
        text = _render_queue_status_markdown(payload)
    else:
        text = _render_queue_status_text(payload)
    _write_or_print(text, args.out)
    return 0


def _queue_proposal_add(args: argparse.Namespace) -> int:
    try:
        proposal = add_proposal(
            db_path=_queue_db(args),
            work_item_id=args.item_id,
            title=args.title,
            summary=args.summary,
            patch_plan=args.patch_plan,
            risk_level=args.risk_level,
        ).to_dict()
    except KeyError:
        print(f"Unknown work item: {args.item_id}", file=sys.stderr)
        return 1
    _write_or_print(_json_dump(proposal), args.out)
    return 0


def _queue_proposal_list(args: argparse.Namespace) -> int:
    try:
        proposals = [
            proposal.to_dict()
            for proposal in list_proposals(
                db_path=_queue_db(args),
                work_item_id=args.item_id,
                approval_state=args.approval_state,
            )
        ]
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.format == "json":
        text = _json_dump({"schema_version": "patchrail.queue.v1", "proposals": proposals})
    else:
        text = _render_proposals_text(proposals)
    _write_or_print(text, args.out)
    return 0


def _queue_proposal_show(args: argparse.Namespace) -> int:
    try:
        proposal = show_proposal(db_path=_queue_db(args), proposal_id=args.proposal_id).to_dict()
    except KeyError:
        print(f"Unknown proposal: {args.proposal_id}", file=sys.stderr)
        return 1
    if args.format == "json":
        text = _json_dump(proposal)
    elif args.format == "markdown":
        text = _render_proposal_markdown(proposal)
    else:
        text = _render_proposals_text([proposal])
    _write_or_print(text, args.out)
    return 0


def _queue_proposal_approve(args: argparse.Namespace) -> int:
    try:
        proposal = approve_proposal(
            db_path=_queue_db(args),
            proposal_id=args.proposal_id,
            decision_note=args.note,
        ).to_dict()
    except KeyError:
        print(f"Unknown proposal: {args.proposal_id}", file=sys.stderr)
        return 1
    _write_or_print(_json_dump(proposal), args.out)
    return 0


def _queue_proposal_reject(args: argparse.Namespace) -> int:
    try:
        proposal = reject_proposal(
            db_path=_queue_db(args),
            proposal_id=args.proposal_id,
            decision_note=args.note,
        ).to_dict()
    except KeyError:
        print(f"Unknown proposal: {args.proposal_id}", file=sys.stderr)
        return 1
    _write_or_print(_json_dump(proposal), args.out)
    return 0


def _serve(args: argparse.Namespace) -> int:
    try:
        serve_queue_api(host=args.host, port=args.port, db_path=Path(args.db))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("PatchRail local API stopped.", file=sys.stderr)
        return 130
    return 0


def _ci_explain(args: argparse.Namespace) -> int:
    raw_log = _read_log(args.log)
    result = classify_ci_log(raw_log)
    if args.redact:
        redaction = redact_ci_log(raw_log)
        result["redaction"] = {
            "redacted": redaction["text"],
            "redactions": redaction["redactions"],
            "local_only": True,
        }
    _write_or_print(_format_result(result, args.format), args.out)
    return 0


def _pilot_pack_readme(manifest: dict[str, Any]) -> str:
    return (
        "\n".join(
            [
                "# PatchRail Pilot Pack",
                "",
                "This directory was generated locally from one CI log.",
                "",
                "## Files",
                "",
                "- `failed-ci.redacted.log`: locally redacted CI log excerpt.",
                "- `patchrail-report.md`: maintainer-readable diagnosis.",
                "- `patchrail-result.json`: structured classifier output.",
                "- `pilot-manifest.json`: local safety and consent manifest.",
                "",
                "## Result",
                "",
                f"- Root cause: `{manifest['classification']['failure_class']}`",
                f"- Confidence: `{manifest['classification']['confidence']}`",
                f"- Redaction categories: `{len(manifest['redaction']['categories'])}`",
                "",
                "## Boundary",
                "",
                "PatchRail did not copy the raw log into this pack.",
                "PatchRail did not contact GitHub, call external models, open pull requests, "
                "post comments, or ask for repository write access.",
                "",
                "Share only after a maintainer reviews the redacted log and report.",
            ]
        )
        + "\n"
    )


def _pilot_manifest_path(path: Path) -> Path:
    return path / "pilot-manifest.json" if path.is_dir() else path


def _load_pilot_pack(path: Path) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    manifest_path = _pilot_manifest_path(path)
    manifest_dir = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "patchrail.ci_pilot_pack.v1":
        raise ValueError("pilot pack must use schema_version patchrail.ci_pilot_pack.v1")
    source = manifest.get("source") or {}
    if source.get("raw_log_copied") is not False:
        raise ValueError("pilot pack must not copy the raw CI log")
    files_payload = manifest.get("files") or {}
    result_name = files_payload.get("json_result")
    if not result_name:
        raise ValueError("pilot pack manifest must include files.json_result")
    result = json.loads((manifest_dir / str(result_name)).read_text(encoding="utf-8"))
    if result.get("schema_version") != "patchrail.ci_result.v1":
        raise ValueError("pilot pack result must use schema_version patchrail.ci_result.v1")
    return manifest_path, manifest, result


def _pilot_summary_payload(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path, manifest, result = _load_pilot_pack(args.pack)
    repository_mention_approved = args.repository_mention_approved == "yes"
    repository_public_name = (
        args.repository if repository_mention_approved and args.repository else None
    )
    return {
        "schema_version": "patchrail.ci_pilot_summary.v1",
        "pilot_pack": {
            "manifest_path": manifest_path.name,
            "raw_log_copied": False,
            "redaction_local_only": True,
            "maintainer_review_required_before_sharing": True,
        },
        "public_listing": {
            "repository_mention_approved": repository_mention_approved,
            "repository": repository_public_name,
        },
        "pilot_context": {
            "ci_provider": args.ci_provider,
            "toolchain": args.toolchain,
            "classification_correct": args.classification_correct,
            "maintainer_action_useful": args.maintainer_action_useful,
        },
        "classification": {
            "failure_class": result["failure_class"],
            "confidence": result["confidence"],
            "likely_subsystem": result["likely_subsystem"],
            "minimal_repair_strategy": result["minimal_repair_strategy"],
        },
        "requirements": manifest["requirements"],
        "blocked_actions": manifest["blocked_actions"],
    }


def _render_pilot_summary_markdown(payload: dict[str, Any]) -> str:
    public_listing = payload["public_listing"]
    pilot_context = payload["pilot_context"]
    classification = payload["classification"]
    repository = public_listing["repository"] or "not approved for public listing"
    repository_approved = str(public_listing["repository_mention_approved"]).lower()
    return (
        "\n".join(
            [
                "# PatchRail Consent-Only Pilot Summary",
                "",
                "## Consent",
                "",
                "- Maintainer permission: required before running or publishing pilot results.",
                f"- Repository approved for public mention: `{repository_approved}`",
                f"- Repository: `{repository}`",
                "- Raw CI log copied into pack: `false`",
                "- Maintainer review required before sharing: `true`",
                "",
                "## Pilot Context",
                "",
                f"- CI provider: `{pilot_context['ci_provider']}`",
                f"- Toolchain: `{pilot_context['toolchain']}`",
                f"- Classification correct: `{pilot_context['classification_correct']}`",
                f"- Suggested maintainer action useful: `{pilot_context['maintainer_action_useful']}`",
                "",
                "## Result",
                "",
                f"- Root cause: `{classification['failure_class']}`",
                f"- Confidence: `{classification['confidence']}`",
                f"- Subsystem: `{classification['likely_subsystem']}`",
                f"- Suggested action: {classification['minimal_repair_strategy']}",
                "",
                "## Safety",
                "",
                "PatchRail ran locally. It did not copy the raw log, call external models, "
                "open a pull request, post a comment, contact a maintainer, claim funding, "
                "or request repository write access.",
                "",
                "Before publishing this summary, review the redacted log and report manually.",
            ]
        )
        + "\n"
    )


def _ci_pilot_pack(args: argparse.Namespace) -> int:
    raw_log = _read_log(args.log)
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    redaction = redact_ci_log(raw_log)
    redacted_log = str(redaction["text"])
    result = classify_ci_log(redacted_log)
    report = _render_markdown(result)
    source_name = args.log.name if args.log is not None else "stdin"

    manifest = {
        "schema_version": "patchrail.ci_pilot_pack.v1",
        "source": {
            "source_log_name": source_name,
            "raw_log_copied": False,
        },
        "files": {
            "redacted_log": "failed-ci.redacted.log",
            "markdown_report": "patchrail-report.md",
            "json_result": "patchrail-result.json",
            "manifest": "pilot-manifest.json",
            "readme": "README.md",
        },
        "classification": {
            "failure_class": result["failure_class"],
            "confidence": result["confidence"],
            "likely_subsystem": result["likely_subsystem"],
        },
        "redaction": {
            "local_only": True,
            "categories": redaction["redactions"],
        },
        "consent_boundary": {
            "maintainer_review_required_before_sharing": True,
            "repository_write_access_required": False,
            "raw_logs_should_not_be_shared": True,
        },
        "requirements": {
            "billing_required": False,
            "external_model_required": False,
            "network_required": False,
            "github_write_permission_required": False,
        },
        "blocked_actions": [
            "copy_raw_log",
            "open_pull_request",
            "post_comment",
            "contact_maintainer",
            "call_external_model",
            "request_repository_write_access",
        ],
    }

    (out_dir / "failed-ci.redacted.log").write_text(redacted_log, encoding="utf-8")
    if not redacted_log.endswith("\n"):
        (out_dir / "failed-ci.redacted.log").write_text(redacted_log + "\n", encoding="utf-8")
    (out_dir / "patchrail-report.md").write_text(report, encoding="utf-8")
    (out_dir / "patchrail-result.json").write_text(_json_dump(result), encoding="utf-8")
    (out_dir / "pilot-manifest.json").write_text(_json_dump(manifest), encoding="utf-8")
    (out_dir / "README.md").write_text(_pilot_pack_readme(manifest), encoding="utf-8")

    text = _json_dump(
        {
            "schema_version": "patchrail.ci_pilot_pack_result.v1",
            "out_dir": str(out_dir),
            "files": manifest["files"],
            "requirements": manifest["requirements"],
            "blocked_actions": manifest["blocked_actions"],
        }
    )
    _write_or_print(text, args.out)
    return 0


def _ci_pilot_summary(args: argparse.Namespace) -> int:
    try:
        payload = _pilot_summary_payload(args)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        print(f"Invalid pilot pack: {exc}", file=sys.stderr)
        return 1
    text = _json_dump(payload) if args.format == "json" else _render_pilot_summary_markdown(payload)
    _write_or_print(text, args.out)
    return 0


def _load_pilot_summary_file(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "patchrail.ci_pilot_summary.v1":
        raise ValueError(f"{path} must use schema_version patchrail.ci_pilot_summary.v1")
    return payload


def _pilot_metric_counter(values: list[str]) -> dict[str, int]:
    counts = Counter(values)
    return {key: counts.get(key, 0) for key in ("yes", "no", "unknown")}


def _pilot_metrics_payload(paths: list[Path]) -> dict[str, Any]:
    summaries = [_load_pilot_summary_file(path) for path in paths]
    public_mentions = [
        item["public_listing"]["repository"]
        for item in summaries
        if item["public_listing"].get("repository_mention_approved") is True
        and item["public_listing"].get("repository")
    ]
    owned_mentions = [repo for repo in public_mentions if repo.startswith("patchrail/")]
    external_mentions = [repo for repo in public_mentions if not repo.startswith("patchrail/")]
    private_count = len(summaries) - len(public_mentions)
    classification_values = [
        str(item["pilot_context"].get("classification_correct", "unknown")) for item in summaries
    ]
    usefulness_values = [
        str(item["pilot_context"].get("maintainer_action_useful", "unknown")) for item in summaries
    ]
    local_only_count = sum(
        1
        for item in summaries
        if item["pilot_pack"].get("raw_log_copied") is False
        and item["pilot_pack"].get("redaction_local_only") is True
    )
    return {
        "schema_version": "patchrail.ci_pilot_metrics.v1",
        "total_pilot_summaries": len(summaries),
        "public_repository_mentions": len(public_mentions),
        "private_or_unapproved_repository_mentions": private_count,
        "owned_repository_mentions": len(owned_mentions),
        "external_repository_mentions": len(external_mentions),
        "public_repositories": public_mentions,
        "owned_repositories": owned_mentions,
        "external_repositories": external_mentions,
        "evidence_readiness": {
            "status": (
                "external_evidence_ready"
                if external_mentions
                else "owned_repo_evidence_only"
                if owned_mentions
                else "private_feedback_only"
            ),
            "external_adopters_countable": len(external_mentions),
            "owned_repo_evidence_countable": len(owned_mentions),
            "private_feedback_count": private_count,
            "do_not_count_private_or_unapproved_as_public": True,
        },
        "classification_correct": _pilot_metric_counter(classification_values),
        "maintainer_action_useful": _pilot_metric_counter(usefulness_values),
        "local_only_and_no_raw_log": local_only_count,
        "requirements": {
            "billing_required": False,
            "external_model_required": False,
            "network_required": False,
            "github_write_permission_required": False,
        },
        "source_files": [str(path) for path in paths],
    }


def _render_pilot_metrics_markdown(payload: dict[str, Any]) -> str:
    readiness = payload["evidence_readiness"]
    lines = [
        "# PatchRail Consent-Only Pilot Metrics",
        "",
        f"- Total pilot summaries: `{payload['total_pilot_summaries']}`",
        f"- Public repository mentions: `{payload['public_repository_mentions']}`",
        f"- Owned-repo public mentions: `{payload['owned_repository_mentions']}`",
        f"- External public repository mentions: `{payload['external_repository_mentions']}`",
        (
            "- Private or unapproved repository mentions: "
            f"`{payload['private_or_unapproved_repository_mentions']}`"
        ),
        f"- Local-only summaries with no raw log copied: `{payload['local_only_and_no_raw_log']}`",
        f"- Evidence readiness: `{readiness['status']}`",
        f"- Countable external adopters: `{readiness['external_adopters_countable']}`",
        "",
        "## Maintainer Review Outcomes",
        "",
        (
            "- Classification correct: "
            f"`yes={payload['classification_correct']['yes']}`, "
            f"`no={payload['classification_correct']['no']}`, "
            f"`unknown={payload['classification_correct']['unknown']}`"
        ),
        (
            "- Suggested action useful: "
            f"`yes={payload['maintainer_action_useful']['yes']}`, "
            f"`no={payload['maintainer_action_useful']['no']}`, "
            f"`unknown={payload['maintainer_action_useful']['unknown']}`"
        ),
        "",
        "## Public Repositories",
        "",
    ]
    public_repositories = payload["public_repositories"]
    if public_repositories:
        lines.extend(f"- `{repo}`" for repo in public_repositories)
    else:
        lines.append("- None approved for public listing.")
    lines.extend(["", "## External Repositories", ""])
    external_repositories = payload["external_repositories"]
    if external_repositories:
        lines.extend(f"- `{repo}`" for repo in external_repositories)
    else:
        lines.append("- None approved for external adopter listing.")
    lines.extend(
        [
            "",
            "## Safety",
            "",
            (
                "These metrics are derived from local pilot-summary JSON files. "
                "They do not count private, unapproved, or owned-repo-only repository names as "
                "external public adoption."
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def _ci_pilot_metrics(args: argparse.Namespace) -> int:
    try:
        payload = _pilot_metrics_payload(args.summary_json)
    except (FileNotFoundError, json.JSONDecodeError, ValueError, KeyError) as exc:
        print(f"Invalid pilot summary input: {exc}", file=sys.stderr)
        return 1
    text = _json_dump(payload) if args.format == "json" else _render_pilot_metrics_markdown(payload)
    _write_or_print(text, args.out)
    return 0


def _redact(args: argparse.Namespace) -> int:
    redaction = redact_ci_log(_read_log(args.log))
    if args.format == "json":
        text = json.dumps(redaction, indent=2, sort_keys=True) + "\n"
    else:
        text = str(redaction["text"])
        if not text.endswith("\n"):
            text += "\n"
    _write_or_print(text, args.out)
    return 0


def _schema(args: argparse.Namespace) -> int:
    text = _load_schema(args.schema)
    if not text.endswith("\n"):
        text += "\n"
    _write_or_print(text, args.out)
    return 0


def _expected_path_for(log_path: Path) -> Path:
    return log_path.with_suffix(".expected.json")


def _load_expected(log_path: Path) -> dict[str, Any]:
    expected_path = _expected_path_for(log_path)
    if not expected_path.exists():
        return {
            "failure_class": None,
            "minimum_confidence": None,
            "_missing_expected_file": str(expected_path),
        }
    return json.loads(expected_path.read_text(encoding="utf-8"))


def _benchmark_case(root: Path, log_path: Path) -> dict[str, Any]:
    expected = _load_expected(log_path)
    result = classify_ci_log(log_path.read_text(encoding="utf-8", errors="replace"))
    mismatches: list[str] = []

    expected_class = expected.get("failure_class")
    if expected_class is None:
        mismatches.append("missing expected failure_class")
    elif result["failure_class"] != expected_class:
        mismatches.append(
            f"failure_class expected {expected_class!r}, got {result['failure_class']!r}"
        )

    minimum_confidence = expected.get("minimum_confidence")
    if minimum_confidence is not None and result["confidence"] < float(minimum_confidence):
        mismatches.append(
            f"confidence expected >= {minimum_confidence}, got {result['confidence']}"
        )

    return {
        "log": str(log_path.relative_to(root)),
        "expected_failure_class": expected_class,
        "actual_failure_class": result["failure_class"],
        "expected_minimum_confidence": minimum_confidence,
        "actual_confidence": result["confidence"],
        "passed": not mismatches,
        "mismatches": mismatches,
    }


def _run_ci_benchmark(path: Path) -> dict[str, Any]:
    resolved_path = path.resolve()
    root = resolved_path
    if root.is_file():
        log_paths = [root]
        root = root.parent
        display_root = path.parent if not path.is_absolute() else root
    else:
        log_paths = sorted(root.rglob("*.log"))
        display_root = path if not path.is_absolute() else root

    cases = [_benchmark_case(root, log_path) for log_path in log_paths]
    passed = sum(1 for case in cases if case["passed"])
    failed = len(cases) - passed
    class_counts: Counter[str] = Counter(
        str(case["expected_failure_class"] or "missing_expected") for case in cases
    )
    class_passed: Counter[str] = Counter(
        str(case["expected_failure_class"] or "missing_expected")
        for case in cases
        if case["passed"]
    )
    class_summary = {
        failure_class: {
            "total_cases": total,
            "passed": class_passed[failure_class],
            "failed": total - class_passed[failure_class],
        }
        for failure_class, total in sorted(class_counts.items())
    }
    return {
        "schema_version": "patchrail.ci_benchmark.v1",
        "root": _display_path(display_root),
        "total_cases": len(cases),
        "passed": passed,
        "failed": failed,
        "accuracy": {
            "top_1": round(passed / len(cases), 4) if cases else 0.0,
        },
        "class_summary": class_summary,
        "cases": cases,
        "requirements": {
            "billing_required": False,
            "external_model_required": False,
            "network_required": False,
        },
    }


def _fixture_check_case(root: Path, log_path: Path) -> dict[str, Any]:
    raw_log = log_path.read_text(encoding="utf-8", errors="replace")
    expected_path = _expected_path_for(log_path)
    result = classify_ci_log(raw_log)
    redaction = redact_ci_log(raw_log)
    issues: list[str] = []

    expected: dict[str, Any] = {}
    if not expected_path.exists():
        issues.append("missing neighboring .expected.json file")
    else:
        try:
            expected = json.loads(expected_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            issues.append(f"invalid expected JSON: {exc.msg}")

    expected_class = expected.get("failure_class")
    if expected_path.exists() and expected_class is None:
        issues.append("expected JSON must include failure_class")
    elif expected_class is not None and result["failure_class"] != expected_class:
        issues.append(f"failure_class expected {expected_class!r}, got {result['failure_class']!r}")

    minimum_confidence = expected.get("minimum_confidence")
    if minimum_confidence is not None:
        try:
            confidence_floor = float(minimum_confidence)
        except (TypeError, ValueError):
            issues.append("minimum_confidence must be a number")
        else:
            if result["confidence"] < confidence_floor:
                issues.append(
                    f"confidence expected >= {confidence_floor}, got {result['confidence']}"
                )

    redactions = redaction["redactions"]
    if redactions:
        categories = ", ".join(sorted(redactions))
        issues.append(f"possible unredacted sensitive data: {categories}")

    return {
        "log": str(log_path.relative_to(root)),
        "expected_file": str(expected_path.relative_to(root)) if expected_path.exists() else None,
        "expected_failure_class": expected_class,
        "actual_failure_class": result["failure_class"],
        "expected_minimum_confidence": minimum_confidence,
        "actual_confidence": result["confidence"],
        "redactions": redactions,
        "passed": not issues,
        "issues": issues,
    }


def _run_ci_fixture_check(path: Path) -> dict[str, Any]:
    root = path.resolve()
    if root.is_file():
        log_paths = [root]
        root = root.parent
    else:
        log_paths = sorted(root.rglob("*.log"))

    cases = [_fixture_check_case(root, log_path) for log_path in log_paths]
    passed = sum(1 for case in cases if case["passed"])
    failed = len(cases) - passed
    return {
        "schema_version": "patchrail.ci_fixture_check.v1",
        "root": str(root),
        "total_cases": len(cases),
        "passed": passed,
        "failed": failed,
        "cases": cases,
        "requirements": {
            "billing_required": False,
            "external_model_required": False,
            "network_required": False,
            "github_write_permission_required": False,
        },
    }


def _benchmark_summary(result: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in result.items() if key != "cases"}


def _render_benchmark_markdown(result: dict[str, Any], *, include_cases: bool = True) -> str:
    lines = [
        "# PatchRail CI Benchmark",
        "",
        f"- Total cases: `{result['total_cases']}`",
        f"- Passed: `{result['passed']}`",
        f"- Failed: `{result['failed']}`",
        f"- Top-1 fixture accuracy: `{result['accuracy']['top_1']}`",
        "",
        "## Class summary",
        "",
    ]
    for failure_class, summary in result["class_summary"].items():
        lines.append(
            f"- `{failure_class}`: `{summary['passed']}` / `{summary['total_cases']}` passed"
        )
    if not include_cases:
        return "\n".join(lines) + "\n"
    lines.extend(
        [
            "",
            "## Cases",
            "",
        ]
    )
    for case in result["cases"]:
        status = "pass" if case["passed"] else "fail"
        lines.append(
            f"- `{status}` `{case['log']}`: expected "
            f"`{case['expected_failure_class']}`, got `{case['actual_failure_class']}`"
        )
        for mismatch in case["mismatches"]:
            lines.append(f"  - {mismatch}")
    return "\n".join(lines) + "\n"


def _render_benchmark_text(result: dict[str, Any], *, include_cases: bool = True) -> str:
    lines = [
        f"Total cases: {result['total_cases']}",
        f"Passed: {result['passed']}",
        f"Failed: {result['failed']}",
        f"Top-1 fixture accuracy: {result['accuracy']['top_1']}",
    ]
    for failure_class, summary in result["class_summary"].items():
        lines.append(f"{failure_class}: {summary['passed']} / {summary['total_cases']} passed")
    if not include_cases:
        return "\n".join(lines) + "\n"
    for case in result["cases"]:
        status = "PASS" if case["passed"] else "FAIL"
        lines.append(f"{status} {case['log']}: {case['actual_failure_class']}")
    return "\n".join(lines) + "\n"


def _render_fixture_check_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# PatchRail CI Fixture Check",
        "",
        f"- Total cases: `{result['total_cases']}`",
        f"- Passed: `{result['passed']}`",
        f"- Failed: `{result['failed']}`",
        "",
        "## Cases",
        "",
    ]
    for case in result["cases"]:
        status = "pass" if case["passed"] else "fail"
        lines.append(
            f"- `{status}` `{case['log']}`: `{case['actual_failure_class']}` "
            f"confidence `{case['actual_confidence']}`"
        )
        for issue in case["issues"]:
            lines.append(f"  - {issue}")
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            (
                "This check is local-only. It does not upload logs, contact GitHub, "
                "open pull requests, or call external models."
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def _render_fixture_check_text(result: dict[str, Any]) -> str:
    lines = [
        f"Total cases: {result['total_cases']}",
        f"Passed: {result['passed']}",
        f"Failed: {result['failed']}",
    ]
    for case in result["cases"]:
        status = "PASS" if case["passed"] else "FAIL"
        lines.append(f"{status} {case['log']}: {case['actual_failure_class']}")
        for issue in case["issues"]:
            lines.append(f"  - {issue}")
    return "\n".join(lines) + "\n"


def _render_funded_issues_text(issues: list[dict[str, Any]]) -> str:
    if not issues:
        return "No funded issues matched the safe read-only filters.\n"
    lines = []
    for issue in issues:
        lines.append(
            f"{issue['reference']} [{issue['risk_level']}] "
            f"{issue['funding']['display']} {issue['title']}"
        )
    return "\n".join(lines) + "\n"


def _render_funded_issues_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# PatchRail Funded Issues",
        "",
        f"- Read-only: `{payload['read_only']}`",
        f"- Safe-only filter: `{payload['safe_only']}`",
        f"- Loaded: `{payload['total_loaded']}`",
        f"- Returned: `{payload['total_returned']}`",
        "",
        "## Issues",
        "",
    ]
    if not payload["issues"]:
        lines.append("No funded issues matched the safe read-only filters.")
    for issue in payload["issues"]:
        lines.extend(
            [
                f"### {issue['reference']}",
                "",
                f"- Title: {issue['title']}",
                f"- Platform: `{issue['platform']}`",
                f"- Funding: `{issue['funding']['display']}`",
                f"- Risk level: `{issue['risk_level']}`",
                f"- URL: {issue['url']}",
                "",
            ]
        )
    lines.extend(
        [
            "## Boundary",
            "",
            (
                "PatchRail reads local metadata only. This command does not claim rewards, "
                "post comments, open pull requests, contact maintainers, or rank work by money alone."
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def _render_funded_issue_explain_markdown(payload: dict[str, Any]) -> str:
    issue = payload["issue"]
    lines = [
        "# PatchRail Funded Issue",
        "",
        f"- Reference: `{issue['reference']}`",
        f"- Title: {issue['title']}",
        f"- Platform: `{issue['platform']}`",
        f"- Funding: `{issue['funding']['display']}`",
        f"- Risk level: `{issue['risk_level']}`",
        f"- Read-only: `{payload['read_only']}`",
        f"- URL: {issue['url']}",
        "",
        "## Recommendation",
        "",
        payload["recommendation"],
        "",
        "## Signals",
        "",
    ]
    signals = issue["contribution_signals"]
    if signals:
        lines.extend(f"- {signal}" for signal in signals)
    else:
        lines.append("- No positive contribution-readiness signals recorded.")
    lines.extend(["", "## Risk Flags", ""])
    risk_flags = issue["risk_flags"]
    if risk_flags:
        lines.extend(f"- `{flag}`" for flag in risk_flags)
    else:
        lines.append("- No high-risk flags recorded.")
    lines.extend(
        [
            "",
            "## Blocked Actions",
            "",
        ]
    )
    lines.extend(f"- `{action}`" for action in payload["ethics"]["blocked"])
    lines.extend(
        [
            "",
            "PatchRail does not claim rewards, post comments, open pull requests, "
            "or contact maintainers from funded issue commands.",
        ]
    )
    return "\n".join(lines) + "\n"


def _render_funded_issues_import_markdown(payload: dict[str, Any]) -> str:
    source = payload["import_source"]
    lines = [
        "# PatchRail Funded Issue Import",
        "",
        f"- Provider: `{source['provider']}`",
        f"- Local file only: `{source['local_file_only']}`",
        f"- Records loaded: `{source['records_loaded']}`",
        f"- Read-only: `{payload['read_only']}`",
        f"- Issues exported: `{len(payload['issues'])}`",
        "",
        "## Issues",
        "",
    ]
    if not payload["issues"]:
        lines.append("No issues were normalized from the provider export.")
    for issue in payload["issues"]:
        lines.extend(
            [
                f"### {issue['reference']}",
                "",
                f"- Title: {issue['title']}",
                f"- Funding: `{issue['funding']['display']}`",
                f"- Risk level: `{issue['risk_level']}`",
                f"- Safe to list: `{issue['safe_to_list']}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Boundary",
            "",
            (
                "This command normalizes a local provider export. It does not fetch APIs, "
                "scrape websites, claim rewards, post comments, open pull requests, or contact maintainers."
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def _default_funded_issues_source() -> Path:
    return Path("examples") / "funded-issues-readonly" / "issues.json"


def _load_funded_issues_for_cli(source: Path) -> list[Any]:
    if not source.exists():
        raise FileNotFoundError(source)
    return load_funded_issues(source)


def _funded_issues_list(args: argparse.Namespace) -> int:
    source = args.source or _default_funded_issues_source()
    try:
        issues = _load_funded_issues_for_cli(source)
        payload = summarize_issues(
            issues,
            safe_only=not args.include_risky,
            platform=args.platform,
            language=args.language,
            min_usd=args.min_usd,
        )
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        print(f"Invalid funded issue source: {exc}", file=sys.stderr)
        return 1
    if args.format == "json":
        text = _json_dump(payload)
    elif args.format == "markdown":
        text = _render_funded_issues_markdown(payload)
    else:
        text = _render_funded_issues_text(payload["issues"])
    _write_or_print(text, args.out)
    return 0


def _funded_issues_explain(args: argparse.Namespace) -> int:
    source = args.source or _default_funded_issues_source()
    try:
        issues = _load_funded_issues_for_cli(source)
        payload = explain_issue(issues, args.reference)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        print(f"Invalid funded issue source: {exc}", file=sys.stderr)
        return 1
    except KeyError:
        print(f"Unknown funded issue: {args.reference}", file=sys.stderr)
        return 1
    if args.format == "json":
        text = _json_dump(payload)
    elif args.format == "markdown":
        text = _render_funded_issue_explain_markdown(payload)
    else:
        text = _render_funded_issues_text([payload["issue"]])
    _write_or_print(text, args.out)
    return 0


def _funded_issues_import(args: argparse.Namespace) -> int:
    try:
        payload = import_provider_export(args.provider, args.source)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        print(f"Invalid provider export: {exc}", file=sys.stderr)
        return 1
    if args.format == "json":
        text = _json_dump(payload)
    elif args.format == "markdown":
        text = _render_funded_issues_import_markdown(payload)
    else:
        text = _render_funded_issues_text(payload["issues"])
    _write_or_print(text, args.out)
    return 0


def _ci_benchmark(args: argparse.Namespace) -> int:
    result = _run_ci_benchmark(args.path)
    if args.format == "json":
        payload = _benchmark_summary(result) if args.summary_only else result
        text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    elif args.format == "markdown":
        text = _render_benchmark_markdown(result, include_cases=not args.summary_only)
    else:
        text = _render_benchmark_text(result, include_cases=not args.summary_only)
    _write_or_print(text, args.out)
    return 0 if result["failed"] == 0 else 1


def _ci_fixture_check(args: argparse.Namespace) -> int:
    result = _run_ci_fixture_check(args.path)
    if args.format == "json":
        text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    elif args.format == "markdown":
        text = _render_fixture_check_markdown(result)
    else:
        text = _render_fixture_check_text(result)
    _write_or_print(text, args.out)
    return 0 if result["failed"] == 0 else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="patchrail",
        description="Local-first maintainer automation for open-source projects.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ci_parser = subparsers.add_parser("ci", help="Classify and explain CI failures locally.")
    ci_subparsers = ci_parser.add_subparsers(dest="ci_command", required=True)

    explain = ci_subparsers.add_parser("explain", help="Explain a failed CI log.")
    explain.add_argument("--log", type=Path, help="CI log file. Reads stdin when omitted.")
    explain.add_argument(
        "--redact",
        action="store_true",
        help="Include local redaction metadata for secrets, emails and home paths.",
    )
    explain.add_argument(
        "--format",
        choices=["markdown", "json", "text"],
        default="markdown",
        help="Output format.",
    )
    explain.add_argument("--out", type=Path, help="Optional output path.")
    explain.set_defaults(func=_ci_explain)

    classify = ci_subparsers.add_parser("classify", help="Emit machine-readable CI classification.")
    classify.add_argument("--log", type=Path, help="CI log file. Reads stdin when omitted.")
    classify.add_argument(
        "--redact",
        action="store_true",
        help="Include local redaction metadata for secrets, emails and home paths.",
    )
    classify.add_argument(
        "--format",
        choices=["json", "markdown", "text"],
        default="json",
        help="Output format.",
    )
    classify.add_argument("--out", type=Path, help="Optional output path.")
    classify.set_defaults(func=_ci_explain)

    benchmark = ci_subparsers.add_parser(
        "benchmark",
        help="Run local fixture expectations against CI classifier output.",
    )
    benchmark.add_argument("path", type=Path, help="Directory or single .log file to benchmark.")
    benchmark.add_argument(
        "--format",
        choices=["json", "markdown", "text"],
        default="json",
        help="Output format.",
    )
    benchmark.add_argument(
        "--summary-only",
        action="store_true",
        help="Omit per-case benchmark details and emit only aggregate evidence.",
    )
    benchmark.add_argument("--out", type=Path, help="Optional output path.")
    benchmark.set_defaults(func=_ci_benchmark)

    fixture_check = ci_subparsers.add_parser(
        "fixture-check",
        help="Validate CI fixture metadata and redaction hygiene before sharing.",
    )
    fixture_check.add_argument(
        "path",
        type=Path,
        help="Directory or single .log fixture to check.",
    )
    fixture_check.add_argument(
        "--format",
        choices=["json", "markdown", "text"],
        default="json",
        help="Output format.",
    )
    fixture_check.add_argument("--out", type=Path, help="Optional output path.")
    fixture_check.set_defaults(func=_ci_fixture_check)

    pilot_pack = ci_subparsers.add_parser(
        "pilot-pack",
        help="Create a local consent-only pilot pack from one CI log.",
    )
    pilot_pack.add_argument("--log", type=Path, help="CI log file. Reads stdin when omitted.")
    pilot_pack.add_argument(
        "--out-dir",
        type=Path,
        required=True,
        help="Directory for the generated redacted pilot pack.",
    )
    pilot_pack.add_argument("--out", type=Path, help="Optional JSON summary output path.")
    pilot_pack.set_defaults(func=_ci_pilot_pack)

    pilot_summary = ci_subparsers.add_parser(
        "pilot-summary",
        help="Create a safe consent-only pilot outcome summary from a pilot pack.",
    )
    pilot_summary.add_argument(
        "--pack",
        type=Path,
        required=True,
        help="Pilot pack directory or pilot-manifest.json path.",
    )
    pilot_summary.add_argument(
        "--repository",
        default="",
        help="Repository name to include only when public mention is explicitly approved.",
    )
    pilot_summary.add_argument(
        "--repository-mention-approved",
        choices=["yes", "no"],
        default="no",
        help="Whether the maintainer explicitly approved public repository listing.",
    )
    pilot_summary.add_argument(
        "--ci-provider",
        default="unknown",
        help="CI provider label, for example GitHub Actions.",
    )
    pilot_summary.add_argument(
        "--toolchain",
        default="unknown",
        help="Toolchain label, for example Python, Node, TypeScript, Go, or Rust.",
    )
    pilot_summary.add_argument(
        "--classification-correct",
        choices=["yes", "no", "unknown"],
        default="unknown",
        help="Maintainer-reviewed classification outcome.",
    )
    pilot_summary.add_argument(
        "--maintainer-action-useful",
        choices=["yes", "no", "unknown"],
        default="unknown",
        help="Maintainer-reviewed usefulness of the suggested action.",
    )
    pilot_summary.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format.",
    )
    pilot_summary.add_argument("--out", type=Path, help="Optional output path.")
    pilot_summary.set_defaults(func=_ci_pilot_summary)

    pilot_metrics = ci_subparsers.add_parser(
        "pilot-metrics",
        help="Aggregate consent-only pilot-summary JSON files into safe public metrics.",
    )
    pilot_metrics.add_argument(
        "summary_json",
        type=Path,
        nargs="+",
        help="One or more files created by `patchrail ci pilot-summary --format json`.",
    )
    pilot_metrics.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format.",
    )
    pilot_metrics.add_argument("--out", type=Path, help="Optional output path.")
    pilot_metrics.set_defaults(func=_ci_pilot_metrics)

    redact = subparsers.add_parser("redact", help="Redact secrets, emails and home paths locally.")
    redact.add_argument("--log", type=Path, help="CI log file. Reads stdin when omitted.")
    redact.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format.",
    )
    redact.add_argument("--out", type=Path, help="Optional output path.")
    redact.set_defaults(func=_redact)

    schema = subparsers.add_parser("schema", help="Print PatchRail's versioned JSON schemas.")
    schema.add_argument(
        "schema",
        choices=[
            "ci-benchmark",
            "ci-fixture-check",
            "ci-pilot-metrics",
            "ci-pilot-summary",
            "ci-result",
            "queue-audit-event",
            "queue-audit-summary",
            "queue-proposal",
            "queue-status",
            "queue-work-item",
        ],
        help="Schema name to emit.",
    )
    schema.add_argument("--out", type=Path, help="Optional output path.")
    schema.set_defaults(func=_schema)

    doctor = subparsers.add_parser(
        "doctor",
        help="Check local PatchRail installation and safety requirements.",
    )
    doctor.add_argument(
        "--format",
        choices=["json", "markdown", "text"],
        default="text",
        help="Output format.",
    )
    doctor.add_argument("--out", type=Path, help="Optional output path.")
    doctor.set_defaults(func=_doctor)

    evidence = subparsers.add_parser(
        "evidence",
        help="Summarize local OSS program evidence without network or write actions.",
    )
    evidence_subparsers = evidence.add_subparsers(dest="evidence_command", required=True)
    evidence_snapshot = evidence_subparsers.add_parser(
        "snapshot",
        help="Build a reproducible local snapshot of public PatchRail evidence signals.",
    )
    evidence_snapshot.add_argument(
        "--format",
        choices=["json", "markdown", "text"],
        default="markdown",
        help="Output format.",
    )
    evidence_snapshot.add_argument("--out", type=Path, help="Optional output path.")
    evidence_snapshot.set_defaults(func=_evidence_snapshot)

    evidence_roadmap = evidence_subparsers.add_parser(
        "roadmap",
        help="Audit v0.1.0-v0.4.0 and 12-week OSS roadmap progress from local artifacts.",
    )
    evidence_roadmap.add_argument(
        "--format",
        choices=["json", "markdown", "text"],
        default="markdown",
        help="Output format.",
    )
    evidence_roadmap.add_argument("--out", type=Path, help="Optional output path.")
    evidence_roadmap.set_defaults(func=_evidence_roadmap)

    evidence_control_plane = evidence_subparsers.add_parser(
        "control-plane",
        help="Audit local Agent Control Plane demo evidence from repository artifacts.",
    )
    evidence_control_plane.add_argument(
        "--summary",
        type=Path,
        help=(
            "Optional local agent-queue demo summary JSON. Defaults to "
            "examples/local-agent-queue/demo-summary.expected.json."
        ),
    )
    evidence_control_plane.add_argument(
        "--format",
        choices=["json", "markdown", "text"],
        default="markdown",
        help="Output format.",
    )
    evidence_control_plane.add_argument("--out", type=Path, help="Optional output path.")
    evidence_control_plane.set_defaults(func=_evidence_control_plane)

    evidence_http_api = evidence_subparsers.add_parser(
        "http-api",
        help="Smoke-test the local Agent Control Plane HTTP API on 127.0.0.1.",
    )
    evidence_http_api.add_argument(
        "--format",
        choices=["json", "markdown", "text"],
        default="markdown",
        help="Output format.",
    )
    evidence_http_api.add_argument("--out", type=Path, help="Optional output path.")
    evidence_http_api.set_defaults(func=_evidence_http_api)

    evidence_review_packet = evidence_subparsers.add_parser(
        "review-packet",
        help="Summarize public owned-repo review and triage evidence from the workflow ledger.",
    )
    evidence_review_packet.add_argument(
        "--format",
        choices=["json", "markdown", "text"],
        default="markdown",
        help="Output format.",
    )
    evidence_review_packet.add_argument("--out", type=Path, help="Optional output path.")
    evidence_review_packet.set_defaults(func=_evidence_review_packet)

    serve = subparsers.add_parser(
        "serve",
        help="Run the local-only PatchRail Agent Control Plane HTTP API.",
    )
    serve.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind host. Only 127.0.0.1 or localhost are allowed.",
    )
    serve.add_argument("--port", type=int, default=8765, help="Local API port.")
    serve.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_QUEUE_PATH,
        help="SQLite queue path. Defaults to .patchrail/queue.sqlite.",
    )
    serve.set_defaults(func=_serve)

    queue = subparsers.add_parser(
        "queue",
        help="Manage a local SQLite queue for reviewable maintainer work.",
    )
    queue.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_QUEUE_PATH,
        help="SQLite queue path. Defaults to .patchrail/queue.sqlite.",
    )
    queue_subparsers = queue.add_subparsers(dest="queue_command", required=True)

    queue_init = queue_subparsers.add_parser("init", help="Initialize the local queue database.")
    queue_init.add_argument("--out", type=Path, help="Optional output path.")
    queue_init.set_defaults(func=_queue_init)

    queue_status = queue_subparsers.add_parser(
        "status",
        help="Summarize the local queue, proposal, audit, and safety state.",
    )
    queue_status.add_argument(
        "--format",
        choices=["json", "markdown", "text"],
        default="text",
        help="Output format.",
    )
    queue_status.add_argument("--out", type=Path, help="Optional output path.")
    queue_status.set_defaults(func=_queue_status)

    queue_add = queue_subparsers.add_parser("add", help="Add a local work item.")
    queue_add.add_argument("--kind", help="Work item kind, for example ci_failure.")
    queue_add.add_argument("--title", help="Human-readable work item title.")
    queue_add.add_argument("--source", default="manual", help="Source identifier or URL.")
    queue_add.add_argument("--payload-json", help="Optional JSON payload for local context.")
    queue_add.add_argument(
        "--from-ci-result",
        type=Path,
        help="Import a local patchrail.ci_result.v1 JSON file as a pending ci_failure item.",
    )
    queue_add.add_argument(
        "--from-pilot-pack",
        type=Path,
        help=(
            "Import a local pilot-pack directory or pilot-manifest.json as a pending "
            "ci_failure item."
        ),
    )
    queue_add.add_argument("--out", type=Path, help="Optional output path.")
    queue_add.set_defaults(func=_queue_add)

    queue_list = queue_subparsers.add_parser("list", help="List local work items.")
    queue_list.add_argument(
        "--approval-state",
        choices=["pending", "approved", "rejected"],
        help="Filter by human approval state.",
    )
    queue_list.add_argument("--status", help="Filter by local item status.")
    queue_list.add_argument(
        "--format",
        choices=["json", "text"],
        default="text",
        help="Output format.",
    )
    queue_list.add_argument("--out", type=Path, help="Optional output path.")
    queue_list.set_defaults(func=_queue_list)

    queue_show = queue_subparsers.add_parser("show", help="Show one local work item.")
    queue_show.add_argument("item_id")
    queue_show.add_argument(
        "--format",
        choices=["json", "markdown", "text"],
        default="markdown",
        help="Output format.",
    )
    queue_show.add_argument("--out", type=Path, help="Optional output path.")
    queue_show.set_defaults(func=_queue_show)

    queue_approve = queue_subparsers.add_parser(
        "approve",
        help="Mark a local work item approved by a human maintainer.",
    )
    queue_approve.add_argument("item_id")
    queue_approve.add_argument("--note", help="Decision note to keep in the local audit trail.")
    queue_approve.add_argument("--out", type=Path, help="Optional output path.")
    queue_approve.set_defaults(func=_queue_approve)

    queue_reject = queue_subparsers.add_parser(
        "reject",
        help="Mark a local work item rejected by a human maintainer.",
    )
    queue_reject.add_argument("item_id")
    queue_reject.add_argument("--note", help="Decision note to keep in the local audit trail.")
    queue_reject.add_argument("--out", type=Path, help="Optional output path.")
    queue_reject.set_defaults(func=_queue_reject)

    queue_skip = queue_subparsers.add_parser(
        "skip",
        help="Skip a local work item while preserving it in the audit trail.",
    )
    queue_skip.add_argument("item_id")
    queue_skip.add_argument(
        "--reason",
        required=True,
        help="Reason recorded in the local audit trail.",
    )
    queue_skip.add_argument("--out", type=Path, help="Optional output path.")
    queue_skip.set_defaults(func=_queue_skip)

    queue_export = queue_subparsers.add_parser(
        "export",
        help="Export local queue items for audit or handoff.",
    )
    queue_export.add_argument(
        "--format",
        choices=["json", "jsonl"],
        default="jsonl",
        help="Output format.",
    )
    queue_export.add_argument("--out", type=Path, help="Optional output path.")
    queue_export.set_defaults(func=_queue_export)

    queue_audit = queue_subparsers.add_parser(
        "audit",
        help="Export local audit events for queue decisions and handoffs.",
    )
    queue_audit.add_argument(
        "--item-id",
        help="Only show audit events for one work item.",
    )
    queue_audit.add_argument(
        "--format",
        choices=["json", "jsonl", "text"],
        default="text",
        help="Output format.",
    )
    queue_audit.add_argument("--out", type=Path, help="Optional output path.")
    queue_audit.set_defaults(func=_queue_audit)

    queue_audit_summary = queue_subparsers.add_parser(
        "audit-summary",
        help="Summarize local audit events and verify human gate coverage.",
    )
    queue_audit_summary.add_argument(
        "--require-event",
        action="append",
        help=(
            "Audit event type required for success. May be repeated. Defaults to the "
            "full local demo gate sequence."
        ),
    )
    queue_audit_summary.add_argument(
        "--format",
        choices=["json", "markdown", "text"],
        default="text",
        help="Output format.",
    )
    queue_audit_summary.add_argument("--out", type=Path, help="Optional output path.")
    queue_audit_summary.set_defaults(func=_queue_audit_summary)

    queue_bundle = queue_subparsers.add_parser(
        "bundle",
        help="Emit a read-only handoff bundle with status, gates, items, proposals, and audit events.",
    )
    queue_bundle.add_argument(
        "--require-event",
        action="append",
        help=(
            "Audit event type required for ready status. May be repeated. Defaults to the "
            "full local demo gate sequence."
        ),
    )
    queue_bundle.add_argument(
        "--format",
        choices=["json", "markdown", "text"],
        default="json",
        help="Output format.",
    )
    queue_bundle.add_argument("--out", type=Path, help="Optional output path.")
    queue_bundle.set_defaults(func=_queue_bundle)

    queue_proposal = queue_subparsers.add_parser(
        "proposal",
        help="Manage local patch proposal records linked to queue items.",
    )
    proposal_subparsers = queue_proposal.add_subparsers(
        dest="proposal_command",
        required=True,
    )

    proposal_add = proposal_subparsers.add_parser(
        "add",
        help="Add a local proposal for one work item.",
    )
    proposal_add.add_argument("--item-id", required=True, help="Work item ID to link.")
    proposal_add.add_argument("--title", required=True, help="Human-readable proposal title.")
    proposal_add.add_argument("--summary", required=True, help="Short maintainer-facing summary.")
    proposal_add.add_argument("--patch-plan", required=True, help="Reviewable local patch plan.")
    proposal_add.add_argument(
        "--risk-level",
        choices=["low", "medium", "high"],
        default="medium",
        help="Maintainer review risk level.",
    )
    proposal_add.add_argument("--out", type=Path, help="Optional output path.")
    proposal_add.set_defaults(func=_queue_proposal_add)

    proposal_list = proposal_subparsers.add_parser("list", help="List local proposals.")
    proposal_list.add_argument("--item-id", help="Only show proposals for one work item.")
    proposal_list.add_argument(
        "--approval-state",
        choices=["pending", "approved", "rejected"],
        help="Filter by proposal approval state.",
    )
    proposal_list.add_argument(
        "--format",
        choices=["json", "text"],
        default="text",
        help="Output format.",
    )
    proposal_list.add_argument("--out", type=Path, help="Optional output path.")
    proposal_list.set_defaults(func=_queue_proposal_list)

    proposal_show = proposal_subparsers.add_parser("show", help="Show one local proposal.")
    proposal_show.add_argument("proposal_id")
    proposal_show.add_argument(
        "--format",
        choices=["json", "markdown", "text"],
        default="markdown",
        help="Output format.",
    )
    proposal_show.add_argument("--out", type=Path, help="Optional output path.")
    proposal_show.set_defaults(func=_queue_proposal_show)

    proposal_approve = proposal_subparsers.add_parser(
        "approve",
        help="Mark a local proposal approved by a human maintainer.",
    )
    proposal_approve.add_argument("proposal_id")
    proposal_approve.add_argument("--note", help="Decision note to keep in the audit trail.")
    proposal_approve.add_argument("--out", type=Path, help="Optional output path.")
    proposal_approve.set_defaults(func=_queue_proposal_approve)

    proposal_reject = proposal_subparsers.add_parser(
        "reject",
        help="Mark a local proposal rejected by a human maintainer.",
    )
    proposal_reject.add_argument("proposal_id")
    proposal_reject.add_argument("--note", help="Decision note to keep in the audit trail.")
    proposal_reject.add_argument("--out", type=Path, help="Optional output path.")
    proposal_reject.set_defaults(func=_queue_proposal_reject)

    funded = subparsers.add_parser(
        "funded-issues",
        help="Inspect funded maintenance issues from local read-only metadata.",
    )
    funded_subparsers = funded.add_subparsers(dest="funded_issues_command", required=True)

    funded_list = funded_subparsers.add_parser(
        "list",
        help="List local funded issue metadata with safe-only filtering by default.",
    )
    funded_list.add_argument(
        "--source",
        type=Path,
        help="Local JSON source. Defaults to examples/funded-issues-readonly/issues.json.",
    )
    funded_list.add_argument(
        "--include-risky",
        action="store_true",
        help="Include high-risk issues in local output. Still read-only.",
    )
    funded_list.add_argument("--platform", help="Filter by funding platform.")
    funded_list.add_argument("--language", help="Filter by repository language.")
    funded_list.add_argument(
        "--min-usd", type=float, help="Filter to USD-funded issues at least this amount."
    )
    funded_list.add_argument(
        "--format",
        choices=["json", "markdown", "text"],
        default="text",
        help="Output format.",
    )
    funded_list.add_argument("--out", type=Path, help="Optional output path.")
    funded_list.set_defaults(func=_funded_issues_list)

    funded_explain = funded_subparsers.add_parser(
        "explain",
        help="Explain one local funded issue record and its anti-abuse boundary.",
    )
    funded_explain.add_argument("reference", help="Issue id, URL, or owner/repo#number.")
    funded_explain.add_argument(
        "--source",
        type=Path,
        help="Local JSON source. Defaults to examples/funded-issues-readonly/issues.json.",
    )
    funded_explain.add_argument(
        "--format",
        choices=["json", "markdown", "text"],
        default="markdown",
        help="Output format.",
    )
    funded_explain.add_argument("--out", type=Path, help="Optional output path.")
    funded_explain.set_defaults(func=_funded_issues_explain)

    funded_import = funded_subparsers.add_parser(
        "import",
        help="Normalize a local provider export into PatchRail's read-only funded issue schema.",
    )
    funded_import.add_argument(
        "--provider",
        required=True,
        choices=SUPPORTED_PROVIDERS,
        help="Provider export format to normalize.",
    )
    funded_import.add_argument(
        "--source",
        required=True,
        type=Path,
        help="Local JSON export file. PatchRail does not fetch provider APIs.",
    )
    funded_import.add_argument(
        "--format",
        choices=["json", "markdown", "text"],
        default="json",
        help="Output format.",
    )
    funded_import.add_argument("--out", type=Path, help="Optional output path.")
    funded_import.set_defaults(func=_funded_issues_import)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
