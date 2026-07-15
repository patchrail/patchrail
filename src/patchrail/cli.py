from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shlex
import subprocess
import sys
import tempfile
import threading
from collections import Counter
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from patchrail import __version__
from patchrail.ci import (
    UNKNOWN_FAILURE_CLASS,
    classify_ci_log,
    list_failure_classes,
    redact_ci_log,
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
    DEFAULT_POLICY_RESOLUTION_REASON,
    queue_audit_summary_payload,
    queue_bundle_payload,
    queue_gate_report_payload,
    queue_policy_resolution_payload,
    queue_policy_scan_payload,
    queue_review_payload,
    queue_status_payload,
)


class LogReadError(Exception):
    """A ``--log`` path could not be read as a CI log file.

    Carries a user-facing, actionable message. Callers catch this and print
    ``patchrail <command>: {message}`` to stderr with exit code 2, so a bad
    path (missing file, a directory, an unreadable file) never leaks a raw
    Python traceback to a first-time user.
    """


def _read_log(path: Path | None) -> str:
    if path is None:
        return sys.stdin.read()
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        raise LogReadError(f"log file not found: {path}") from None
    except IsADirectoryError:
        raise LogReadError(
            f"log path is a directory, not a file: {path} (point --log at a single CI log file)"
        ) from None
    except PermissionError:
        raise LogReadError(f"log file is not readable (permission denied): {path}") from None
    except OSError as exc:
        detail = exc.strerror or exc.__class__.__name__
        raise LogReadError(f"could not read log file {path}: {detail}") from None


_CI_TRIAGE_ACTION_BASE = "https://github.com/patchrail/ci-triage-action"
_CI_TRIAGE_MARKETPLACE_BASE = "https://github.com/marketplace/actions/patchrail-ci-triage"

# When PatchRail cannot recognize a log it returns ``unknown``. Point the maintainer
# at the CI failure fixture issue template so the dead-end becomes a contribution.
_CI_FIXTURE_ISSUE_URL = (
    "https://github.com/patchrail/patchrail/issues/new?template=ci_failure_fixture.md"
)


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
    for message in result.get("runner_errors") or []:
        lines.append(f"Runner reported: {message}")
    if result.get("likely_successful_run"):
        lines.append(
            "No failure detected: this log looks like a SUCCESSFUL run, so there is nothing to "
            "triage. PatchRail explains FAILED runs — if you expected a failure, point it at the "
            "failed run (e.g. `gh run view <run-id> --log-failed | patchrail ci explain`)."
        )
    elif result.get("failure_class") == UNKNOWN_FAILURE_CLASS:
        lines.append(
            "Help improve PatchRail: this log did not match a known failure class. "
            "Open a CI failure fixture issue with a sanitized log so we can teach the "
            f"classifier: {_CI_FIXTURE_ISSUE_URL}"
        )
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
    runner_errors = list(result.get("runner_errors") or [])
    if runner_errors:
        lines.extend(
            [
                "",
                "## Errors the runner reported",
                "",
                (
                    "No rule matched this log, so PatchRail did not classify it. The CI "
                    "runner did annotate these lines as errors — start there:"
                ),
                "",
            ]
        )
        lines.extend(f"- `{message}`" for message in runner_errors)
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
    if result.get("likely_successful_run"):
        lines.extend(
            [
                "",
                "## No failure detected",
                "",
                (
                    "This log looks like a **successful** run, so there is nothing to triage. "
                    "PatchRail explains FAILED runs — if you expected a failure, point it at the "
                    "failed run (e.g. `gh run view <run-id> --log-failed | patchrail ci explain`)."
                ),
            ]
        )
    elif result.get("failure_class") == UNKNOWN_FAILURE_CLASS:
        lines.extend(
            [
                "",
                "## Help improve PatchRail",
                "",
                (
                    "This log did not match a known failure class. "
                    f"[Open a CI failure fixture issue]({_CI_FIXTURE_ISSUE_URL}) "
                    "with a sanitized log so PatchRail can learn to classify it."
                ),
            ]
        )
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
        "application-dossier": "application-dossier.v1.schema.json",
        "ci-benchmark": "ci-benchmark.v1.schema.json",
        "ci-classes": "ci-classes.v2.schema.json",
        "ci-fixture-check": "ci-fixture-check.v1.schema.json",
        "ci-pilot-metrics": "ci-pilot-metrics.v1.schema.json",
        "ci-pilot-summary": "ci-pilot-summary.v1.schema.json",
        "ci-result": "ci-result.v1.schema.json",
        "funded-issues-client-report": "funded-issues-client-report.v1.schema.json",
        "funded-issues-report": "funded-issues-report.v1.schema.json",
        "funded-issues-recheck-queue": "funded-issues-recheck-queue.v1.schema.json",
        "funded-issues-recheck-summary": "funded-issues-recheck-summary.v1.schema.json",
        "funded-issues-shortlist": "funded-issues-shortlist.v1.schema.json",
        "funded-issues-store": "funded-issues-store.v1.schema.json",
        "funded-issues-store-status": "funded-issues-store-status.v1.schema.json",
        "queue-audit-event": "queue-audit-event.v1.schema.json",
        "queue-audit-summary": "queue-audit-summary.v1.schema.json",
        "queue-gate-report": "queue-gate-report.v1.schema.json",
        "queue-policy-resolution": "queue-policy-resolution.v1.schema.json",
        "queue-policy-scan": "queue-policy-scan.v1.schema.json",
        "queue-proposal": "queue-proposal.v1.schema.json",
        "queue-review": "queue-review.v1.schema.json",
        "queue-status": "queue-status.v1.schema.json",
        "queue-work-item": "queue-work-item.v1.schema.json",
        "reviewer-quick-check-artifacts": "reviewer-quick-check-artifacts.v1.schema.json",
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


def _metrics_table_value(markdown: str, metric: str) -> str:
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line.startswith("|") or "---" in line:
            continue
        columns = [column.strip() for column in line.strip("|").split("|")]
        if len(columns) >= 2 and columns[0] == metric:
            return columns[1]
    return ""


def _parse_int(text: str) -> int | None:
    try:
        return int(text.replace(",", ""))
    except ValueError:
        return None


def _pypi_package_telemetry(metrics: str) -> dict[str, Any]:
    value = _metrics_table_value(metrics, "Monthly PyPI downloads")
    rolling_match = re.search(
        r"(?P<last_month>[\d,]+) downloads in the last month, "
        r"(?P<last_week>[\d,]+) in the last week, and "
        r"(?P<last_day>[\d,]+) in the last day",
        value,
    )
    python_major_match = re.search(r"python_major` totals (?P<total>[\d,]+)", value)
    as_of_match = re.search(r"as of (?P<as_of>\d{4}-\d{2}-\d{2})", value)
    return {
        "present": bool(value.strip()),
        "source_metric": "Monthly PyPI downloads",
        "package_level_only": True,
        "version_specific_adoption": False,
        "last_month": _parse_int(rolling_match.group("last_month")) if rolling_match else None,
        "last_week": _parse_int(rolling_match.group("last_week")) if rolling_match else None,
        "last_day": _parse_int(rolling_match.group("last_day")) if rolling_match else None,
        "python_major_total": (
            _parse_int(python_major_match.group("total")) if python_major_match else None
        ),
        "as_of": as_of_match.group("as_of") if as_of_match else None,
    }


def _public_external_adopters_count(metrics: str, adopters: str) -> int | None:
    value = _metrics_table_value(metrics, "Public external adopters")
    parsed = _parse_int(value)
    if parsed is not None:
        return parsed
    if "no public external adopters listed yet" in adopters:
        return 0
    return None


def _adoption_next_actions() -> list[dict[str, Any]]:
    return [
        {
            "action": "request_permissioned_external_maintainer_pilot",
            "evidence_required": "approved public pilot summary plus consent checklist",
            "target_date": "2026-06-30",
            "counts_as_adoption": True,
        },
        {
            "action": "record_approved_adopters_listing",
            "evidence_required": "ADOPTERS.md entry approved by the external maintainer",
            "target_date": "2026-06-30",
            "counts_as_adoption": True,
        },
        {
            "action": "track_complete_pypi_30_day_window",
            "evidence_required": "docs/metrics.md row for the first complete 30-day package window",
            "target_date": "2026-07-12",
            "counts_as_adoption": False,
        },
    ]


def _github_action_marketplace_listing(readme: str) -> dict[str, Any]:
    listed = _CI_TRIAGE_MARKETPLACE_BASE in readme
    return {
        "listed": listed,
        "url": _CI_TRIAGE_MARKETPLACE_BASE if listed else "",
        "counts_as_adoption": False,
    }


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
        "formal visible automated review links",
        "permissioned external maintainer triage examples",
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
            "formal_automated_review_claimed": False,
            "pypi_download_claimed": True,
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
        f"- Formal automated review claimed: `{boundaries['formal_automated_review_claimed']}`",
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
                "Formal automated review claimed: False",
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


def _evidence_reviewer_packet(args: argparse.Namespace) -> int:
    from patchrail.reviewer_quick_check import build_reviewer_quick_check

    text = build_reviewer_quick_check(root=Path("."), out_dir=args.out_dir)
    print(text, end="")
    return 0


def _render_reviewer_packet_integrity_markdown(payload: dict[str, Any]) -> str:
    counts = payload["counts"]
    checks = payload["checks"]
    lines = [
        "# PatchRail Reviewer Packet Integrity",
        "",
        f"- Status: `{payload['status']}`",
        f"- Manifest schema: `{payload.get('manifest_schema_version')}`",
        f"- Artifacts: `{counts['artifact_count']}`",
        f"- Details: `{counts['detail_count']}`",
        f"- Verified artifacts: `{counts['verified_artifact_count']}`",
        "",
        "## Checks",
        "",
    ]
    lines.extend(f"- {name}: `{value}`" for name, value in checks.items())
    errors = payload.get("errors") or []
    missing = payload.get("missing_artifacts") or []
    extra = payload.get("extra_files") or []
    mismatches = payload.get("mismatches") or []
    if errors or missing or extra or mismatches:
        lines.extend(["", "## Findings", ""])
        lines.extend(f"- {error}" for error in errors)
        lines.extend(f"- missing artifact: `{path}`" for path in missing)
        lines.extend(f"- extra file not in manifest: `{path}`" for path in extra)
        for mismatch in mismatches:
            lines.append(f"- integrity mismatch: `{mismatch['path']}`")
    return "\n".join(lines) + "\n"


def _render_reviewer_packet_integrity_text(payload: dict[str, Any]) -> str:
    counts = payload["counts"]
    lines = [
        f"Status: {payload['status']}",
        f"Artifacts: {counts['artifact_count']}",
        f"Details: {counts['detail_count']}",
        f"Verified artifacts: {counts['verified_artifact_count']}",
    ]
    errors = payload.get("errors") or []
    missing = payload.get("missing_artifacts") or []
    extra = payload.get("extra_files") or []
    mismatches = payload.get("mismatches") or []
    lines.extend(f"Error: {error}" for error in errors)
    lines.extend(f"Missing artifact: {path}" for path in missing)
    lines.extend(f"Extra file: {path}" for path in extra)
    lines.extend(f"Mismatch: {mismatch['path']}" for mismatch in mismatches)
    return "\n".join(lines) + "\n"


def _evidence_verify_reviewer_packet(args: argparse.Namespace) -> int:
    from patchrail.reviewer_quick_check import verify_reviewer_packet

    payload = verify_reviewer_packet(args.packet_dir)
    if args.format == "json":
        text = _json_dump(payload)
    elif args.format == "markdown":
        text = _render_reviewer_packet_integrity_markdown(payload)
    else:
        text = _render_reviewer_packet_integrity_text(payload)
    _write_or_print(text, args.out)
    return 0 if payload["status"] == "verified" else 1


def _evidence_snapshot_payload(root: Path) -> dict[str, Any]:
    fixture_root = root / "examples" / "ci-triage"
    log_paths = sorted(fixture_root.glob("*.log")) if fixture_root.exists() else []
    expected_paths = sorted(fixture_root.glob("*.expected.json")) if fixture_root.exists() else []
    benchmark = _run_ci_benchmark(fixture_root) if fixture_root.exists() else {}
    triage_workflow = _read_optional_text(root / ".github" / "workflows" / "ci-triage.yml")
    ci_workflow = _read_optional_text(root / ".github" / "workflows" / "ci.yml")
    adopters = _read_optional_text(root / "ADOPTERS.md")
    metrics = _read_optional_text(root / "docs" / "metrics.md")
    readme = _read_optional_text(root / "README.md")
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
        "docs/agent-workflows.md",
        "docs/agent-control-plane.md",
        "docs/funded-issues-ethics.md",
        "docs/public-workflow-ledger.md",
        "docs/pilot-request-package.md",
        "docs/metrics.md",
        "docs/open-source-program-evidence.md",
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
    pypi_release_published = "PyPI package | `patchrail` 0.1.1 published" in metrics
    pypi_initial_download_telemetry_present = any(
        marker in metrics
        for marker in (
            "Initial package telemetry:",
            "Rolling package telemetry:",
        )
    )
    pypi_full_30_day_window_complete = "Full 30-day PyPI download window complete:" in metrics
    external_adopters_count = _public_external_adopters_count(metrics, adopters)
    pypi_telemetry = _pypi_package_telemetry(metrics)
    github_action_marketplace = _github_action_marketplace_listing(readme)
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
            "pypi_release_published": pypi_release_published,
            "pypi_initial_download_telemetry_present": pypi_initial_download_telemetry_present,
            "pypi_full_30_day_window_complete": pypi_full_30_day_window_complete,
            "github_action_marketplace_listed": github_action_marketplace["listed"],
        },
        "adoption_evidence": {
            "public_external_adopters": external_adopters_count,
            "countable_external_adoption_present": bool(external_adopters_count),
            "pypi_package_telemetry": pypi_telemetry,
            "pypi_counts_as_adoption": False,
            "readiness_gate": {
                "status": (
                    "countable_adoption_present"
                    if external_adopters_count
                    else "blocked_by_external_adoption_evidence"
                ),
                "first_countable_adoption_missing": not bool(external_adopters_count),
                "blocking_requirements": []
                if external_adopters_count
                else [
                    "permissioned external maintainer pilot summary",
                    "approved ADOPTERS.md listing",
                ],
                "non_countable_signals": [
                    "PyPI package downloads",
                    "owned-repo pilot outcomes",
                    "GitHub Marketplace action listing",
                ],
            },
            "next_actions": _adoption_next_actions(),
            "pending_public_evidence": [
                "permissioned external maintainer pilot summary",
                "approved ADOPTERS.md listing",
                "full 30-day PyPI package window",
            ],
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
                "install_url": _CI_TRIAGE_ACTION_BASE,
                "marketplace_listed": github_action_marketplace["listed"],
                "marketplace_url": github_action_marketplace["url"],
                "marketplace_counts_as_adoption": github_action_marketplace["counts_as_adoption"],
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
                "status": "public_pypi_initial_telemetry"
                if pypi_release_published and pypi_initial_download_telemetry_present
                else "local_ready_pypi_blocked",
                "package_smoke_in_ci": package_smoke,
                "readiness_script_present": (root / "scripts" / "release_readiness.py").exists(),
            },
            "public_review_triage": {
                "status": "owned_repo_visible",
                "ledger_present": bool(workflow_ledger.strip()),
                "owned_issue_pr_cycles": owned_issue_pr_cycles,
                "focused_maintainer_prs": review_packet["signals"]["focused_maintainer_prs"],
                "review_packet_command": "patchrail evidence review-packet",
                "formal_automated_review_links": False,
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
            "permissioned external maintainer pilots",
            "formal visible automated review links and external maintainer triage examples",
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
    adoption = payload["adoption_evidence"]
    pypi = adoption["pypi_package_telemetry"]
    readiness_gate = adoption["readiness_gate"]
    lines = [
        "# PatchRail Open Source Evidence Snapshot",
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
        "## Adoption Evidence",
        "",
        f"- Public external adopters: `{adoption['public_external_adopters']}`",
        f"- Countable external adoption present: `{adoption['countable_external_adoption_present']}`",
        f"- PyPI package telemetry present: `{pypi['present']}`",
        f"- PyPI last month downloads: `{pypi['last_month']}`",
        f"- PyPI last week downloads: `{pypi['last_week']}`",
        f"- PyPI last day downloads: `{pypi['last_day']}`",
        f"- PyPI counts as adoption: `{adoption['pypi_counts_as_adoption']}`",
        f"- Adoption readiness gate: `{readiness_gate['status']}`",
        (
            "- First countable adoption missing: "
            f"`{readiness_gate['first_countable_adoption_missing']}`"
        ),
        (
            "- Blocking adoption requirements: "
            f"`{', '.join(readiness_gate['blocking_requirements']) or 'none'}`"
        ),
        (f"- Non-countable signals: `{', '.join(readiness_gate['non_countable_signals'])}`"),
        "",
        "## Next Evidence Actions",
        "",
    ]
    for item in adoption["next_actions"]:
        lines.append(
            f"- `{item['action']}` by `{item['target_date']}`: "
            f"{item['evidence_required']} "
            f"(counts as adoption: `{item['counts_as_adoption']}`)"
        )
    lines.extend(
        [
            "",
            "## Workstreams",
            "",
        ]
    )
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
                    "docs/agent-workflows.md",
                    "docs/open-source-program-evidence.md",
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
                "evidence": ["docs/open-source-program-evidence.md", "docs/metrics.md"],
                "gaps": ["stars/downloads/adopters/review links are insufficient"],
            },
            "week_12": {
                "status": "not_ready",
                "focus": "apply or wait with criteria",
                "evidence": ["docs/open-source-program-evidence.md"],
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


def _application_gate_payload(root: Path) -> dict[str, Any]:
    snapshot = _evidence_snapshot_payload(root)
    roadmap = _roadmap_audit_payload(root)
    signals = snapshot["signals"]
    safety = snapshot["safety"]
    review_triage = snapshot["workstreams"]["public_review_triage"]

    checks = {
        "public_repository_present": True,
        "github_release_present": roadmap["artifact_presence"]["release_v0_1"],
        "ci_benchmark_green": snapshot["workstreams"]["ci_janitor"]["benchmark_green"],
        "required_docs_present": safety["missing_required_docs"] == [],
        "read_only_ci_triage_workflow": safety["read_only_ci_triage_workflow"],
        "agent_control_plane_demo_ready": snapshot["workstreams"]["agent_control_plane"][
            "demo_present"
        ],
        "funded_issue_scout_secondary_read_only": snapshot["workstreams"]["funded_issue_scout"][
            "demo_present"
        ],
        "owned_repo_review_packet_ready": review_triage["status"] == "owned_repo_visible",
        "pypi_release_published": bool(signals["pypi_release_published"]),
        "pypi_initial_download_telemetry_present": bool(
            signals["pypi_initial_download_telemetry_present"]
        ),
        "external_adopters_present": bool(signals["public_external_adopters"]),
        "formal_visible_review_links_present": review_triage["formal_automated_review_links"],
        "no_placeholder_metrics_in_application_copy": True,
        "money_goal_retired": roadmap["safety"]["money_goal_retired"],
        "no_network_or_write_required": all(
            safety[key] is False
            for key in [
                "github_write_permission_required",
                "external_model_required",
                "billing_required",
                "network_required",
            ]
        ),
    }
    blocker_map = {
        "external_adopters_present": "permissioned external maintainer pilots or adopters",
        "formal_visible_review_links_present": "formal visible review links",
        "no_placeholder_metrics_in_application_copy": "placeholder metrics in application copy",
    }
    blockers = [reason for key, reason in blocker_map.items() if not checks[key]]
    blocked_dependencies = [
        {
            "blocker": "permissioned external maintainer pilots or adopters",
            "owner": "external_maintainer_permission",
            "required_evidence": "a maintainer-approved public pilot summary or adopter listing",
            "safe_local_alternative": "improve consent-only pilot docs, redaction, and fixture contribution paths",
        },
        {
            "blocker": "formal visible review links",
            "owner": "public_review_artifact",
            "required_evidence": "public review or triage links that are real and attributable without placeholder claims",
            "safe_local_alternative": "continue owned-repo issue-to-PR cycles and review-packet evidence",
        },
    ]
    active_blocked_dependencies = [
        item for item in blocked_dependencies if item["blocker"] in blockers
    ]
    ready = not blockers and all(checks.values())
    return {
        "schema_version": "patchrail.application_gate.v1",
        "patchrail_version": __version__,
        "repository": "patchrail/patchrail",
        "generated_from": "local_checkout",
        "status": "ready_to_apply" if ready else "not_ready",
        "decision": "application_allowed" if ready else "do_not_apply_yet",
        "checks": checks,
        "signals": {
            "ci_fixtures": signals["ci_fixtures"],
            "ci_benchmark_failed": signals["ci_benchmark_failed"],
            "public_release_count": signals["public_release_count"],
            "public_external_adopters": signals["public_external_adopters"],
            "pilot_summary_count": signals["pilot_summary_count"],
            "owned_repo_issue_pr_cycles": signals["owned_repo_issue_pr_cycles"],
            "focused_maintainer_prs": review_triage["focused_maintainer_prs"],
            "pypi_initial_download_telemetry_present": signals[
                "pypi_initial_download_telemetry_present"
            ],
            "pypi_full_30_day_window_complete": signals["pypi_full_30_day_window_complete"],
        },
        "blockers": blockers,
        "blocked_dependencies": active_blocked_dependencies,
        "safe_next_actions": [
            "track the first complete 30-day PyPI download window without treating downloads as adoption",
            "record permissioned external maintainer pilots before counting adopter evidence",
            "add formal visible review links only when public review artifacts exist",
            "keep application copy blocked while any metric is pending or placeholder-derived",
        ],
        "safe_local_work_while_blocked": [
            "extend CI Failure Zoo fixtures and benchmark guardrails",
            "improve Agent Control Plane queue, approval, and audit evidence",
            "keep README, quickstart, release-readiness, and application-gate docs honest",
            "prepare upstream contributions only when a real bug or maintenance improvement exists",
        ],
        "safety": {
            "local_first": True,
            "network_required": False,
            "github_write_permission_required": False,
            "external_model_required": False,
            "billing_required": False,
            "money_goal_retired": True,
            "third_party_write_actions_allowed": False,
        },
    }


def _render_application_gate_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# PatchRail Application Gate",
        "",
        f"- Repository: `{payload['repository']}`",
        f"- Status: `{payload['status']}`",
        f"- Decision: `{payload['decision']}`",
        "",
        "## Checks",
        "",
    ]
    lines.extend(f"- `{key}`: `{value}`" for key, value in payload["checks"].items())
    lines.extend(["", "## Current Signals", ""])
    lines.extend(f"- `{key}`: `{value}`" for key, value in payload["signals"].items())
    lines.extend(["", "## Blockers", ""])
    if payload["blockers"]:
        lines.extend(f"- {blocker}" for blocker in payload["blockers"])
    else:
        lines.append("- none")
    lines.extend(["", "## Blocked Dependencies", ""])
    if payload["blocked_dependencies"]:
        for item in payload["blocked_dependencies"]:
            lines.extend(
                [
                    f"- `{item['blocker']}`",
                    f"  - Owner: `{item['owner']}`",
                    f"  - Required evidence: {item['required_evidence']}",
                    f"  - Safe local alternative: {item['safe_local_alternative']}",
                ]
            )
    else:
        lines.append("- none")
    lines.extend(["", "## Safe Next Actions", ""])
    lines.extend(f"- {action}" for action in payload["safe_next_actions"])
    lines.extend(["", "## Safe Local Work While Blocked", ""])
    lines.extend(f"- {action}" for action in payload["safe_local_work_while_blocked"])
    return "\n".join(lines) + "\n"


def _render_application_gate_text(payload: dict[str, Any]) -> str:
    return (
        "\n".join(
            [
                f"Repository: {payload['repository']}",
                f"Status: {payload['status']}",
                f"Decision: {payload['decision']}",
                f"Blockers: {len(payload['blockers'])}",
            ]
        )
        + "\n"
    )


def _evidence_application_gate(args: argparse.Namespace) -> int:
    payload = _application_gate_payload(Path("."))
    if args.format == "json":
        text = _json_dump(payload)
    elif args.format == "markdown":
        text = _render_application_gate_markdown(payload)
    else:
        text = _render_application_gate_text(payload)
    _write_or_print(text, args.out)
    return 0 if payload["status"] == "ready_to_apply" else 1


def _application_dossier_payload(root: Path) -> dict[str, Any]:
    snapshot = _evidence_snapshot_payload(root)
    roadmap = _roadmap_audit_payload(root)
    review_packet = _public_review_packet_payload(root)
    application_gate = _application_gate_payload(root)
    program_evidence = _read_optional_text(root / "docs" / "open-source-program-evidence.md")

    upstream_contributions: list[dict[str, str]] = []
    if "https://github.com/jamie8johnson/cqs/pull/1650" in program_evidence:
        upstream_contributions.append(
            {
                "project": "jamie8johnson/cqs",
                "url": "https://github.com/jamie8johnson/cqs/pull/1650",
                "status": "merged",
                "evidence": "real upstream bug fix merged 2026-05-20",
            }
        )
    if "https://github.com/pypa/twine/pull/1329" in program_evidence:
        upstream_contributions.append(
            {
                "project": "pypa/twine",
                "url": "https://github.com/pypa/twine/pull/1329",
                "status": "open_ready_for_review",
                "evidence": "focused maintenance PR for local tox debugging",
            }
        )
    merged_upstream_count = sum(1 for item in upstream_contributions if item["status"] == "merged")
    open_upstream_pr_count = sum(
        1 for item in upstream_contributions if item["status"].startswith("open_")
    )

    gate_ready = application_gate["status"] == "ready_to_apply"
    reviewer_quick_checks = [
        {
            "name": "single-command local reviewer check",
            "command": (
                "uv run --extra dev patchrail evidence reviewer-packet "
                "--out-dir patchrail-reviewer-packet"
            ),
            "expected": (
                "local Markdown and JSON packet with doctor, CI demo, fail-closed "
                "application gate, and application dossier contract"
            ),
            "network_required": False,
            "write_action_required": False,
        },
        {
            "name": "10-second no-install demo",
            "command": (
                "open examples/ci-triage/demo-output.md and compare with "
                "uv run --extra dev patchrail ci explain --log "
                "examples/ci-triage/dependency-failure.log --format markdown"
            ),
            "expected": "real CLI output for the bundled fixture; tests prevent drift",
            "network_required": False,
            "write_action_required": False,
        },
        {
            "name": "pre-PyPI source install smoke",
            "command": "uvx --from git+https://github.com/patchrail/patchrail patchrail --help",
            "expected": "runs from GitHub source while PyPI publish is pending",
            "network_required": True,
            "write_action_required": False,
        },
        {
            "name": "fail-closed application gate",
            "command": "patchrail evidence application-gate --format markdown",
            "expected": "returns not_ready / do_not_apply_yet until real public evidence exists",
            "network_required": False,
            "write_action_required": False,
        },
        {
            "name": "local application dossier",
            "command": "patchrail evidence application-dossier --format markdown",
            "expected": "draft only; maintainer tap required before any external form submission",
            "network_required": False,
            "write_action_required": False,
        },
    ]
    return {
        "schema_version": "patchrail.application_dossier.v1",
        "patchrail_version": __version__,
        "repository": "patchrail/patchrail",
        "generated_from": "local_checkout",
        "status": "ready_for_maintainer_review" if gate_ready else "draft_only_do_not_submit",
        "application_gate": {
            "status": application_gate["status"],
            "decision": application_gate["decision"],
            "blockers": application_gate["blockers"],
            "blocked_dependencies": application_gate["blocked_dependencies"],
        },
        "signals": {
            "ci_fixtures": snapshot["signals"]["ci_fixtures"],
            "ci_benchmark_failed": snapshot["signals"]["ci_benchmark_failed"],
            "public_release_count": snapshot["signals"]["public_release_count"],
            "public_external_adopters": snapshot["signals"]["public_external_adopters"],
            "pilot_summary_count": snapshot["signals"]["pilot_summary_count"],
            "owned_repo_issue_pr_cycles": snapshot["signals"]["owned_repo_issue_pr_cycles"],
            "focused_maintainer_prs": review_packet["signals"]["focused_maintainer_prs"],
            "upstream_contribution_count": len(upstream_contributions),
            "merged_upstream_contribution_count": merged_upstream_count,
            "open_upstream_pr_count": open_upstream_pr_count,
        },
        "upstream_contributions": upstream_contributions,
        "evidence_commands": [
            "patchrail evidence snapshot --format markdown",
            "patchrail evidence roadmap --format markdown",
            "patchrail evidence review-packet --format markdown",
            "patchrail evidence reviewer-packet --out-dir patchrail-reviewer-packet",
            "patchrail evidence application-gate --format markdown",
            "patchrail evidence control-plane --format markdown",
        ],
        "evidence_pages": [
            "README.md",
            "docs/open-source-program-evidence.md",
            "docs/public-workflow-ledger.md",
            "docs/release-v0.1.0-evidence.md",
            "docs/release-v0.2.0-evidence.md",
            "docs/release-v0.3.0-evidence.md",
            "docs/release-v0.4.0-evidence.md",
        ],
        "reviewer_quick_checks": reviewer_quick_checks,
        "roadmap_status": roadmap["status"],
        "safe_local_work_while_blocked": application_gate["safe_local_work_while_blocked"],
        "submission_policy": {
            "maintainer_tap_required": True,
            "agent_may_submit": False,
            "form_submission_allowed_by_gate": gate_ready,
            "no_placeholder_metrics": True,
            "no_money_goal": True,
        },
        "safety": {
            "local_first": True,
            "network_required": False,
            "github_write_permission_required": False,
            "external_model_required": False,
            "billing_required": False,
            "third_party_write_actions_allowed": False,
            "application_form_write_action": True,
        },
    }


def _render_application_dossier_markdown(payload: dict[str, Any]) -> str:
    signals = payload["signals"]
    policy = payload["submission_policy"]
    safety = payload["safety"]
    lines = [
        "# PatchRail Application Dossier",
        "",
        f"- Repository: `{payload['repository']}`",
        f"- Status: `{payload['status']}`",
        f"- Roadmap status: `{payload['roadmap_status']}`",
        f"- Application gate: `{payload['application_gate']['status']}`",
        f"- Gate decision: `{payload['application_gate']['decision']}`",
        "",
        "## Signals",
        "",
    ]
    lines.extend(f"- `{key}`: `{value}`" for key, value in signals.items())
    lines.extend(["", "## Upstream Contributions", ""])
    if payload["upstream_contributions"]:
        for item in payload["upstream_contributions"]:
            lines.append(
                f"- `{item['project']}`: {item['url']} ({item['status']}; {item['evidence']})"
            )
    else:
        lines.append("- none recorded")
    lines.extend(["", "## Evidence Commands", ""])
    lines.extend(f"- `{command}`" for command in payload["evidence_commands"])
    lines.extend(["", "## Evidence Pages", ""])
    lines.extend(f"- `{page}`" for page in payload["evidence_pages"])
    lines.extend(["", "## Reviewer Quick Checks", ""])
    for item in payload["reviewer_quick_checks"]:
        lines.extend(
            [
                f"- {item['name']}",
                f"  - Command: `{item['command']}`",
                f"  - Expected: {item['expected']}",
                f"  - Network required: `{item['network_required']}`",
                f"  - Write action required: `{item['write_action_required']}`",
            ]
        )
    lines.extend(["", "## Blocked Dependencies", ""])
    if payload["application_gate"]["blocked_dependencies"]:
        for item in payload["application_gate"]["blocked_dependencies"]:
            lines.extend(
                [
                    f"- `{item['blocker']}`",
                    f"  - Owner: `{item['owner']}`",
                    f"  - Required evidence: {item['required_evidence']}",
                    f"  - Safe local alternative: {item['safe_local_alternative']}",
                ]
            )
    else:
        lines.append("- none")
    lines.extend(["", "## Safe Local Work While Blocked", ""])
    lines.extend(f"- {action}" for action in payload["safe_local_work_while_blocked"])
    lines.extend(
        [
            "",
            "## Submission Policy",
            "",
            f"- Maintainer tap required: `{policy['maintainer_tap_required']}`",
            f"- Agent may submit: `{policy['agent_may_submit']}`",
            (f"- Form submission allowed by gate: `{policy['form_submission_allowed_by_gate']}`"),
            f"- No placeholder metrics: `{policy['no_placeholder_metrics']}`",
            f"- No money goal: `{policy['no_money_goal']}`",
            "",
            "## Safety",
            "",
            f"- Local-first: `{safety['local_first']}`",
            f"- Network required: `{safety['network_required']}`",
            (f"- GitHub write permission required: `{safety['github_write_permission_required']}`"),
            f"- External model required: `{safety['external_model_required']}`",
            f"- Billing required: `{safety['billing_required']}`",
            (
                "- Third-party write actions allowed: "
                f"`{safety['third_party_write_actions_allowed']}`"
            ),
            f"- Application form write action: `{safety['application_form_write_action']}`",
        ]
    )
    return "\n".join(lines) + "\n"


def _render_application_dossier_text(payload: dict[str, Any]) -> str:
    signals = payload["signals"]
    return (
        "\n".join(
            [
                f"Repository: {payload['repository']}",
                f"Status: {payload['status']}",
                f"Application gate: {payload['application_gate']['status']}",
                f"Gate decision: {payload['application_gate']['decision']}",
                f"CI fixtures: {signals['ci_fixtures']}",
                f"Upstream contributions: {signals['upstream_contribution_count']}",
                f"Maintainer tap required: {payload['submission_policy']['maintainer_tap_required']}",
                f"Agent may submit: {payload['submission_policy']['agent_may_submit']}",
            ]
        )
        + "\n"
    )


def _evidence_application_dossier(args: argparse.Namespace) -> int:
    payload = _application_dossier_payload(Path("."))
    if args.format == "json":
        text = _json_dump(payload)
    elif args.format == "markdown":
        text = _render_application_dossier_markdown(payload)
    else:
        text = _render_application_dossier_text(payload)
    _write_or_print(text, args.out)
    return 0


def _release_readiness_payload(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(".")
    script = root / "scripts" / "release_readiness.py"
    if not script.exists():
        raise RuntimeError(
            "scripts/release_readiness.py is required; run this command from a PatchRail checkout."
        )

    command = [
        sys.executable,
        str(script),
        "--dist-dir",
        str(args.dist_dir),
        "--fixture",
        str(args.fixture),
    ]
    if args.clean_dist:
        command.append("--clean-dist")

    proc = subprocess.run(
        command,
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout.strip() or "release readiness command failed")
    payload = json.loads(proc.stdout)
    if not isinstance(payload, dict):
        raise ValueError("release readiness output must be a JSON object")
    return payload


def _render_release_readiness_markdown(payload: dict[str, Any]) -> str:
    checks = payload["checks"]
    safety = payload["safety"]
    lines = [
        "# PatchRail Release Readiness",
        "",
        f"- Schema: `{payload['schema_version']}`",
        f"- Version: `{payload['version']}`",
        f"- Published to PyPI: `{payload['published']}`",
        f"- Build: `{checks['build']}`",
        f"- Twine check: `{checks['twine_check']}`",
        f"- Wheel smoke: `{checks['wheel_smoke']}`",
        f"- Doctor status: `{checks['doctor_status']}`",
        f"- Fixture smoke class: `{checks['fixture_failure_class']}`",
        "",
        "## Artifacts",
        "",
    ]
    lines.extend(
        f"- `{artifact['file']}`: sha256 `{artifact['sha256']}`, {artifact['size_bytes']} bytes"
        for artifact in payload["artifacts"]
    )
    lines.extend(
        [
            "",
            "## Safety",
            "",
            f"- Local-first: `{safety['local_first']}`",
            f"- Created release tag: `{safety['created_release_tag']}`",
            f"- Announced publicly: `{safety['announced_publicly']}`",
            f"- Contacted third parties: `{safety['contacted_third_parties']}`",
            (f"- GitHub write permission required: `{safety['github_write_permission_required']}`"),
            f"- External model required: `{safety['external_model_required']}`",
            "",
            "## Manual Gates Remaining",
            "",
        ]
    )
    lines.extend(f"- {gate}" for gate in payload["manual_gates_remaining"])
    return "\n".join(lines) + "\n"


def _render_release_readiness_text(payload: dict[str, Any]) -> str:
    checks = payload["checks"]
    artifacts = ", ".join(artifact["file"] for artifact in payload["artifacts"])
    return (
        "\n".join(
            [
                f"Version: {payload['version']}",
                f"Published: {payload['published']}",
                f"Build: {checks['build']}",
                f"Twine check: {checks['twine_check']}",
                f"Wheel smoke: {checks['wheel_smoke']}",
                f"Doctor: {checks['doctor_status']}",
                f"Artifacts: {artifacts}",
            ]
        )
        + "\n"
    )


def _evidence_release_readiness(args: argparse.Namespace) -> int:
    try:
        payload = _release_readiness_payload(args)
    except (RuntimeError, json.JSONDecodeError, ValueError) as exc:
        print(f"Invalid release readiness evidence: {exc}", file=sys.stderr)
        return 1
    if args.format == "json":
        text = _json_dump(payload)
    elif args.format == "markdown":
        text = _render_release_readiness_markdown(payload)
    else:
        text = _render_release_readiness_text(payload)
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
        "gate-report.json",
        "gate-report.md",
        "bundle.json",
        "bundle.md",
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
    gate_report_ready = summary.get("gate_report_status") == "ready_for_reviewer_handoff"
    gate_report_ready_flag = summary.get("gate_report_ready_for_reviewer_handoff") is True
    gate_report_pending_decisions = summary.get("gate_report_pending_decisions")
    gate_report_missing_events = list(summary.get("gate_report_missing_required_events") or [])
    gate_report_read_only = summary.get("gate_report_is_read_only") is True
    gate_report_does_not_record = summary.get("gate_report_records_audit_event") is False
    gate_report_execution_allowed = summary.get("gate_report_execution_allowed")
    bundle_ready = summary.get("bundle_status") == "ready_for_handoff"
    bundle_read_only = summary.get("bundle_is_read_only") is True
    bundle_does_not_record = summary.get("bundle_records_audit_event") is False
    bundle_paths_redacted = summary.get("bundle_local_paths_redacted") is True
    bundle_remaining_gaps = list(summary.get("bundle_remaining_gate_gaps") or [])
    bundle_reviewer_ready = summary.get("bundle_reviewer_status") == ("ready_for_reviewer_handoff")
    bundle_reviewer_human_gates = summary.get("bundle_reviewer_human_gates_complete") is True
    bundle_reviewer_pending_decisions = summary.get("bundle_reviewer_pending_decisions")
    bundle_reviewer_execution_allowed = summary.get("bundle_reviewer_execution_allowed")
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
    if not gate_report_ready:
        safety_gaps.append("gate_report_ready_for_reviewer_handoff")
    if not gate_report_ready_flag:
        safety_gaps.append("gate_report_ready_flag_true")
    if gate_report_pending_decisions != 0:
        safety_gaps.append("gate_report_no_pending_decisions")
    if gate_report_missing_events:
        safety_gaps.append("gate_report_missing_required_events")
    if not gate_report_read_only:
        safety_gaps.append("gate_report_read_only")
    if not gate_report_does_not_record:
        safety_gaps.append("gate_report_does_not_record_audit_event")
    if gate_report_execution_allowed is not False:
        safety_gaps.append("gate_report_execution_disallowed")
    if not bundle_ready:
        safety_gaps.append("bundle_ready_for_handoff")
    if not bundle_read_only:
        safety_gaps.append("bundle_read_only")
    if not bundle_does_not_record:
        safety_gaps.append("bundle_does_not_record_audit_event")
    if not bundle_paths_redacted:
        safety_gaps.append("bundle_local_paths_redacted")
    if bundle_remaining_gaps:
        safety_gaps.append("bundle_remaining_gate_gaps")
    if not bundle_reviewer_ready:
        safety_gaps.append("bundle_reviewer_ready_for_handoff")
    if not bundle_reviewer_human_gates:
        safety_gaps.append("bundle_reviewer_human_gates_complete")
    if bundle_reviewer_pending_decisions != 0:
        safety_gaps.append("bundle_reviewer_no_pending_decisions")
    if bundle_reviewer_execution_allowed is not False:
        safety_gaps.append("bundle_reviewer_execution_disallowed")
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
            "gate_report_status": summary.get("gate_report_status"),
            "gate_report_pending_decisions": gate_report_pending_decisions,
            "gate_report_missing_required_events": gate_report_missing_events,
            "bundle_status": summary.get("bundle_status"),
            "bundle_remaining_gate_gaps": bundle_remaining_gaps,
            "bundle_reviewer_status": summary.get("bundle_reviewer_status"),
            "bundle_reviewer_pending_decisions": bundle_reviewer_pending_decisions,
        },
        "safety": {
            "local_first": local_first,
            "write_actions_allowed": write_actions_allowed,
            "rejected_item_write_actions_allowed": rejected_write_actions_allowed,
            "human_approval_gate_exercised": item_approved,
            "proposal_approval_gate_exercised": proposal_approved,
            "risky_proposal_rejection_exercised": proposal_rejected,
            "audit_summary_human_gates_exercised": audit_summary_ready,
            "gate_report_ready_for_reviewer_handoff": gate_report_ready_flag,
            "gate_report_is_read_only": gate_report_read_only,
            "gate_report_records_audit_event": summary.get("gate_report_records_audit_event"),
            "gate_report_execution_allowed": gate_report_execution_allowed,
            "github_write_permission_required": False,
            "external_model_required": False,
            "billing_required": False,
            "network_required": False,
            "bundle_is_read_only": bundle_read_only,
            "bundle_records_audit_event": summary.get("bundle_records_audit_event"),
            "bundle_local_paths_redacted": bundle_paths_redacted,
            "bundle_reviewer_human_gates_complete": bundle_reviewer_human_gates,
            "bundle_reviewer_execution_allowed": bundle_reviewer_execution_allowed,
        },
        "artifact_presence": {
            "required_events_present": missing_events == [],
            "required_artifacts_present": missing_artifacts == [],
            "source_files_present": missing_source_files == [],
            "missing_events": missing_events,
            "missing_artifacts": missing_artifacts,
            "missing_source_files": missing_source_files,
            "audit_summary_missing_required_events": audit_summary_missing_events,
            "gate_report_missing_required_events": gate_report_missing_events,
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
        f"- Gate report status: `{signals['gate_report_status']}`",
        f"- Gate report pending decisions: `{signals['gate_report_pending_decisions']}`",
        f"- Gate report missing events: `{signals['gate_report_missing_required_events']}`",
        f"- Bundle status: `{signals['bundle_status']}`",
        f"- Bundle remaining gate gaps: `{signals['bundle_remaining_gate_gaps']}`",
        f"- Bundle reviewer status: `{signals['bundle_reviewer_status']}`",
        f"- Bundle reviewer pending decisions: `{signals['bundle_reviewer_pending_decisions']}`",
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
        f"- Gate report ready for reviewer handoff: `{safety['gate_report_ready_for_reviewer_handoff']}`",
        f"- Gate report is read-only: `{safety['gate_report_is_read_only']}`",
        f"- Gate report records audit event: `{safety['gate_report_records_audit_event']}`",
        f"- Gate report execution allowed: `{safety['gate_report_execution_allowed']}`",
        f"- GitHub write permission required: `{safety['github_write_permission_required']}`",
        f"- External model required: `{safety['external_model_required']}`",
        f"- Billing required: `{safety['billing_required']}`",
        f"- Network required: `{safety['network_required']}`",
        f"- Bundle is read-only: `{safety['bundle_is_read_only']}`",
        f"- Bundle records audit event: `{safety['bundle_records_audit_event']}`",
        f"- Bundle local paths redacted: `{safety['bundle_local_paths_redacted']}`",
        f"- Bundle reviewer human gates complete: `{safety['bundle_reviewer_human_gates_complete']}`",
        f"- Bundle reviewer execution allowed: `{safety['bundle_reviewer_execution_allowed']}`",
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
                f"Bundle status: {signals['bundle_status']}",
                f"Bundle is read-only: {payload['safety']['bundle_is_read_only']}",
                (f"Bundle records audit event: {payload['safety']['bundle_records_audit_event']}"),
                (
                    "Bundle local paths redacted: "
                    f"{payload['safety']['bundle_local_paths_redacted']}"
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


def _load_local_agent_queue_demo(root: Path):
    script = root / "examples" / "local-agent-queue" / "run_demo.py"
    if not script.exists():
        raise FileNotFoundError(
            "examples/local-agent-queue/run_demo.py is required; "
            "run this command from a PatchRail source checkout."
        )
    spec = importlib.util.spec_from_file_location("patchrail_local_agent_queue_demo", script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load local Agent Control Plane demo from {script}.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    run_demo = getattr(module, "run_demo", None)
    if run_demo is None:
        raise RuntimeError("examples/local-agent-queue/run_demo.py does not expose run_demo.")
    return run_demo


def _control_plane_demo_payload(root: Path, out_dir: Path, *, force: bool) -> dict[str, Any]:
    run_demo = _load_local_agent_queue_demo(root)
    summary = run_demo(out_dir, force=force)
    if not isinstance(summary, dict):
        raise ValueError("local Agent Control Plane demo returned a non-object summary")
    summary_file = out_dir.resolve() / "summary.json"
    evidence = _control_plane_evidence_payload(root, summary_file)
    return {
        "schema_version": "patchrail.control_plane_demo_run.v1",
        "patchrail_version": __version__,
        "repository": "patchrail/patchrail",
        "generated_from": "local_checkout",
        "status": evidence["status"],
        "output_dir": _safe_evidence_path(root, out_dir.resolve()),
        "summary_file": _safe_evidence_path(root, summary_file),
        "artifact_files": summary.get("artifact_files", []),
        "signals": {
            "source_failure_class": summary.get("source_failure_class"),
            "audit_event_count": len(summary.get("audit_event_types") or []),
            "pending_items_before_decisions": summary.get("pending_items_before_decisions"),
            "gate_report_status": summary.get("gate_report_status"),
            "gate_report_pending_decisions": summary.get("gate_report_pending_decisions"),
            "bundle_status": summary.get("bundle_status"),
            "bundle_reviewer_status": summary.get("bundle_reviewer_status"),
        },
        "safety": {
            "local_first": bool(summary.get("local_first")),
            "write_actions_allowed": bool(summary.get("write_actions_allowed")),
            "gate_report_is_read_only": bool(summary.get("gate_report_is_read_only")),
            "gate_report_records_audit_event": bool(summary.get("gate_report_records_audit_event")),
            "gate_report_execution_allowed": bool(summary.get("gate_report_execution_allowed")),
            "bundle_is_read_only": bool(summary.get("bundle_is_read_only")),
            "bundle_records_audit_event": bool(summary.get("bundle_records_audit_event")),
            "bundle_local_paths_redacted": bool(summary.get("bundle_local_paths_redacted")),
            "bundle_reviewer_execution_allowed": bool(
                summary.get("bundle_reviewer_execution_allowed")
            ),
            "network_required": False,
            "github_write_permission_required": False,
            "external_model_required": False,
            "billing_required": False,
        },
        "evidence_status": evidence["status"],
        "remaining_evidence_gaps": evidence["remaining_evidence_gaps"],
    }


def _render_control_plane_demo_markdown(payload: dict[str, Any]) -> str:
    signals = payload["signals"]
    safety = payload["safety"]
    lines = [
        "# PatchRail Agent Control Plane Demo Run",
        "",
        f"- Repository: `{payload['repository']}`",
        f"- Status: `{payload['status']}`",
        f"- Output directory: `{payload['output_dir']}`",
        f"- Summary file: `{payload['summary_file']}`",
        f"- Artifact files: `{len(payload['artifact_files'])}`",
        f"- Source failure class: `{signals['source_failure_class']}`",
        f"- Audit events: `{signals['audit_event_count']}`",
        f"- Pending items before decisions: `{signals['pending_items_before_decisions']}`",
        f"- Gate report status: `{signals['gate_report_status']}`",
        f"- Gate report pending decisions: `{signals['gate_report_pending_decisions']}`",
        f"- Bundle status: `{signals['bundle_status']}`",
        f"- Bundle reviewer status: `{signals['bundle_reviewer_status']}`",
        "",
        "## Safety",
        "",
        f"- Local-first: `{safety['local_first']}`",
        f"- Write actions allowed: `{safety['write_actions_allowed']}`",
        f"- Gate report is read-only: `{safety['gate_report_is_read_only']}`",
        f"- Gate report records audit event: `{safety['gate_report_records_audit_event']}`",
        f"- Gate report execution allowed: `{safety['gate_report_execution_allowed']}`",
        f"- Bundle is read-only: `{safety['bundle_is_read_only']}`",
        f"- Bundle records audit event: `{safety['bundle_records_audit_event']}`",
        f"- Bundle local paths redacted: `{safety['bundle_local_paths_redacted']}`",
        f"- Bundle reviewer execution allowed: `{safety['bundle_reviewer_execution_allowed']}`",
        f"- Network required: `{safety['network_required']}`",
        f"- GitHub write permission required: `{safety['github_write_permission_required']}`",
        f"- External model required: `{safety['external_model_required']}`",
        f"- Billing required: `{safety['billing_required']}`",
    ]
    return "\n".join(lines) + "\n"


def _render_control_plane_demo_text(payload: dict[str, Any]) -> str:
    signals = payload["signals"]
    safety = payload["safety"]
    return (
        "\n".join(
            [
                f"Status: {payload['status']}",
                f"Output directory: {payload['output_dir']}",
                f"Summary file: {payload['summary_file']}",
                f"Artifacts: {len(payload['artifact_files'])}",
                f"Source failure class: {signals['source_failure_class']}",
                f"Gate report status: {signals['gate_report_status']}",
                f"Bundle status: {signals['bundle_status']}",
                f"Write actions allowed: {safety['write_actions_allowed']}",
                f"Network required: {safety['network_required']}",
            ]
        )
        + "\n"
    )


def _evidence_control_plane_demo(args: argparse.Namespace) -> int:
    try:
        payload = _control_plane_demo_payload(Path("."), args.out_dir, force=args.force)
    except (
        AssertionError,
        FileNotFoundError,
        json.JSONDecodeError,
        RuntimeError,
        ValueError,
    ) as exc:
        print(f"Invalid control-plane demo run: {exc}", file=sys.stderr)
        return 1
    if args.format == "json":
        text = _json_dump(payload)
    elif args.format == "markdown":
        text = _render_control_plane_demo_markdown(payload)
    else:
        text = _render_control_plane_demo_text(payload)
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
    human_gate_summary = dict(status.get("human_gate_summary") or {})
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
    if human_gate_summary.get("write_actions_unlocked") is not False:
        safety_gaps.append("human_gate_write_actions_unlocked_false")
    if human_gate_summary.get("total_pending_decisions") != 0:
        safety_gaps.append("human_gate_total_pending_decisions_zero")
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
            "human_gate_status": human_gate_summary.get("status"),
            "human_gate_total_pending_decisions": human_gate_summary.get("total_pending_decisions"),
            "human_gate_pending_work_items": human_gate_summary.get("pending_work_items"),
            "human_gate_pending_proposals": human_gate_summary.get("pending_proposals"),
            "human_gate_write_actions_unlocked": human_gate_summary.get("write_actions_unlocked"),
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
            "human_gate_summary_exposed": bool(human_gate_summary),
            "human_gate_write_actions_unlocked": human_gate_summary.get("write_actions_unlocked"),
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
            f"- Human gate status: `{signals['human_gate_status']}`",
            (f"- Human gate pending decisions: `{signals['human_gate_total_pending_decisions']}`"),
            (
                "- Human gate write actions unlocked: "
                f"`{signals['human_gate_write_actions_unlocked']}`"
            ),
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
            f"- Human gate summary exposed: `{safety['human_gate_summary_exposed']}`",
            (
                "- Human gate write actions unlocked: "
                f"`{safety['human_gate_write_actions_unlocked']}`"
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
                f"Human gate status: {signals['human_gate_status']}",
                (f"Human gate pending decisions: {signals['human_gate_total_pending_decisions']}"),
                (
                    "Human gate write actions unlocked: "
                    f"{signals['human_gate_write_actions_unlocked']}"
                ),
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
    reviewer_summary = payload["reviewer_summary"]
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
        "## Reviewer Checklist",
        "",
        f"- Reviewer handoff status: `{reviewer_summary['status']}`",
        f"- Human gates complete: `{reviewer_summary['human_gates_complete']}`",
        f"- Pending decisions: `{reviewer_summary['pending_decisions']}`",
        f"- Approved work items: `{reviewer_summary['approved_work_items']}`",
        f"- Rejected work items: `{reviewer_summary['rejected_work_items']}`",
        f"- Approved proposals: `{reviewer_summary['approved_proposals']}`",
        f"- Rejected proposals: `{reviewer_summary['rejected_proposals']}`",
        f"- Execution allowed by this bundle: `{reviewer_summary['execution_allowed']}`",
        "",
        "Reviewer steps:",
        "",
    ]
    lines.extend(f"- {step}" for step in reviewer_summary["review_steps"])
    lines.extend(
        [
            "",
            "## Human Gate Coverage",
            "",
        ]
    )
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
    reviewer_summary = payload["reviewer_summary"]
    return (
        "\n".join(
            [
                "PatchRail Queue Bundle",
                f"DB: {payload['db_path']}",
                f"Status: {payload['status']}",
                f"Reviewer handoff status: {reviewer_summary['status']}",
                f"Human gates complete: {reviewer_summary['human_gates_complete']}",
                f"Pending decisions: {reviewer_summary['pending_decisions']}",
                f"Execution allowed by this bundle: {reviewer_summary['execution_allowed']}",
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


def _render_queue_gate_report_markdown(payload: dict[str, Any]) -> str:
    decisions = payload["decision_counts"]
    safety = payload["safety"]
    lines = [
        "# PatchRail Queue Gate Report",
        "",
        f"- DB: `{payload['db_path']}`",
        f"- Status: `{payload['status']}`",
        f"- Ready for reviewer handoff: `{payload['ready_for_reviewer_handoff']}`",
        f"- Pending decisions: `{payload['pending_decisions']}`",
        "",
        "## Decision Counts",
        "",
    ]
    for name, count in decisions.items():
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "## Missing Required Events", ""])
    if payload["missing_required_events"]:
        lines.extend(f"- `{event}`" for event in payload["missing_required_events"])
    else:
        lines.append("- None.")
    lines.extend(["", "## Reviewer Actions", ""])
    lines.extend(f"- {action}" for action in payload["reviewer_actions"])
    lines.extend(
        [
            "",
            "## Safety",
            "",
            f"- Report is read-only: `{safety['report_is_read_only']}`",
            f"- Report records audit event: `{safety['report_records_audit_event']}`",
            f"- Execution allowed: `{safety['execution_allowed']}`",
            f"- Local paths redacted: `{safety['local_paths_redacted']}`",
            f"- Approval records execute actions: `{safety['approval_records_execute_actions']}`",
            f"- GitHub write permission required: `{safety['github_write_permission_required']}`",
            f"- Network required: `{safety['network_required']}`",
            f"- External model required: `{safety['external_model_required']}`",
            f"- Billing required: `{safety['billing_required']}`",
        ]
    )
    return "\n".join(lines) + "\n"


def _render_queue_gate_report_text(payload: dict[str, Any]) -> str:
    return (
        "\n".join(
            [
                "PatchRail Queue Gate Report",
                f"DB: {payload['db_path']}",
                f"Status: {payload['status']}",
                f"Ready for reviewer handoff: {payload['ready_for_reviewer_handoff']}",
                f"Pending decisions: {payload['pending_decisions']}",
                f"Missing required events: {payload['missing_required_events']}",
                f"Reviewer actions: {payload['reviewer_actions']}",
                "Report is read-only: True",
                "Report records audit event: False",
                "Execution allowed: False",
                "Local paths redacted: True",
            ]
        )
        + "\n"
    )


def _render_queue_policy_scan_markdown(payload: dict[str, Any]) -> str:
    safety = payload["safety"]
    lines = [
        "# PatchRail Queue Policy Scan",
        "",
        f"- DB: `{payload['db_path']}`",
        f"- Status: `{payload['status']}`",
        f"- Blocked records: `{payload['blocked_records_count']}`",
        f"- Work items scanned: `{payload['scanned_counts']['work_items_total']}`",
        f"- Proposals scanned: `{payload['scanned_counts']['proposals_total']}`",
        "",
        "## Matches",
        "",
    ]
    if payload["matches"]:
        for match in payload["matches"]:
            lines.extend(
                [
                    f"### {match['record_type']} `{match['id']}`",
                    "",
                    f"- Title: {match['title']}",
                    f"- Matched categories: `{match['matched_categories']}`",
                    f"- Matched terms: `{match['matched_terms']}`",
                    f"- Recommended action: `{match['recommended_action']}`",
                    "",
                ]
            )
    else:
        lines.extend(["- No policy-blocking queue records found.", ""])
    lines.extend(
        [
            "## Reviewer Actions",
            "",
            *[f"- {action}" for action in payload["reviewer_actions"]],
            "",
            "## Safety",
            "",
            f"- Scan is read-only: `{safety['scan_is_read_only']}`",
            f"- Scan records audit event: `{safety['scan_records_audit_event']}`",
            f"- Execution allowed: `{safety['execution_allowed']}`",
            f"- Local paths redacted: `{safety['local_paths_redacted']}`",
            f"- Approval records execute actions: `{safety['approval_records_execute_actions']}`",
            f"- GitHub write permission required: `{safety['github_write_permission_required']}`",
            f"- Network required: `{safety['network_required']}`",
            f"- External model required: `{safety['external_model_required']}`",
            f"- Billing required: `{safety['billing_required']}`",
        ]
    )
    return "\n".join(lines) + "\n"


def _render_queue_policy_scan_text(payload: dict[str, Any]) -> str:
    return (
        "\n".join(
            [
                "PatchRail Queue Policy Scan",
                f"DB: {payload['db_path']}",
                f"Status: {payload['status']}",
                f"Blocked records: {payload['blocked_records_count']}",
                f"Work items scanned: {payload['scanned_counts']['work_items_total']}",
                f"Proposals scanned: {payload['scanned_counts']['proposals_total']}",
                f"Reviewer actions: {payload['reviewer_actions']}",
                "Scan is read-only: True",
                "Scan records audit event: False",
                "Execution allowed: False",
                "Local paths redacted: True",
            ]
        )
        + "\n"
    )


def _render_queue_policy_resolution_markdown(payload: dict[str, Any]) -> str:
    safety = payload["safety"]
    counts = payload["resolved_counts"]
    lines = [
        "# PatchRail Queue Policy Resolution",
        "",
        f"- DB: `{payload['db_path']}`",
        f"- Status: `{payload['status']}`",
        f"- Reason: `{payload['reason']}`",
        f"- Before policy status: `{payload['before_policy_status']}`",
        f"- After policy status: `{payload['after_policy_status']}`",
        f"- Resolved records: `{payload['resolved_records_count']}`",
        f"- Remaining blocked records: `{payload['remaining_blocked_records_count']}`",
        f"- Work items skipped: `{counts['work_items_skipped']}`",
        f"- Proposals rejected: `{counts['proposals_rejected']}`",
        f"- Audit events added: `{counts['audit_events_added']}`",
        "",
        "## Resolved Records",
        "",
    ]
    if payload["resolved_records"]:
        for record in payload["resolved_records"]:
            lines.extend(
                [
                    f"### {record['record_type']} `{record['id']}`",
                    "",
                    f"- Title: {record['title']}",
                    f"- Action: `{record['action']}`",
                    f"- Approval state after: `{record['approval_state_after']}`",
                    f"- Status after: `{record['status_after']}`",
                    f"- Matched categories: `{record['matched_categories']}`",
                    f"- Matched terms: `{record['matched_terms']}`",
                    "",
                ]
            )
    else:
        lines.extend(["- No policy-blocking queue records were active.", ""])
    lines.extend(
        [
            "## Reviewer Actions",
            "",
            *[f"- {action}" for action in payload["reviewer_actions"]],
            "",
            "## Safety",
            "",
            f"- Resolution is local only: `{safety['resolution_is_local_only']}`",
            f"- Resolution records audit event: `{safety['resolution_records_audit_event']}`",
            f"- Execution allowed: `{safety['execution_allowed']}`",
            f"- GitHub write performed: `{safety['github_write_performed']}`",
            f"- Network performed: `{safety['network_performed']}`",
            f"- Proposals executed: `{safety['proposals_executed']}`",
            f"- Work items deleted: `{safety['work_items_deleted']}`",
            f"- Local paths redacted: `{safety['local_paths_redacted']}`",
            f"- Approval records execute actions: `{safety['approval_records_execute_actions']}`",
            f"- GitHub write permission required: `{safety['github_write_permission_required']}`",
            f"- Network required: `{safety['network_required']}`",
            f"- External model required: `{safety['external_model_required']}`",
            f"- Billing required: `{safety['billing_required']}`",
        ]
    )
    return "\n".join(lines) + "\n"


def _render_queue_policy_resolution_text(payload: dict[str, Any]) -> str:
    counts = payload["resolved_counts"]
    return (
        "\n".join(
            [
                "PatchRail Queue Policy Resolution",
                f"DB: {payload['db_path']}",
                f"Status: {payload['status']}",
                f"Reason: {payload['reason']}",
                f"Resolved records: {payload['resolved_records_count']}",
                f"Work items skipped: {counts['work_items_skipped']}",
                f"Proposals rejected: {counts['proposals_rejected']}",
                f"Audit events added: {counts['audit_events_added']}",
                f"After policy status: {payload['after_policy_status']}",
                "Resolution is local only: True",
                "Resolution records audit event: True",
                "Execution allowed: False",
                "GitHub write performed: False",
                "Network performed: False",
                "Proposals executed: False",
                "Work items deleted: False",
                "Local paths redacted: True",
            ]
        )
        + "\n"
    )


def _render_queue_review_markdown(payload: dict[str, Any]) -> str:
    groups = payload["review_groups"]
    safety = payload["safety"]
    lines = [
        "# PatchRail Queue Review Inbox",
        "",
        f"- DB: `{payload['db_path']}`",
        f"- Status: `{payload['status']}`",
        f"- Ready for reviewer handoff: `{payload['ready_for_reviewer_handoff']}`",
        f"- Pending decisions: `{payload['pending_decisions']}`",
        "",
        "## Reviewer Actions",
        "",
    ]
    lines.extend(f"- {action}" for action in payload["reviewer_actions"])
    lines.extend(["", "## Handoff Checklist", ""])
    for step in payload["handoff_checklist"]:
        lines.append(f"- `{step['state']}`: `{step['command']}`")
        lines.append(f"  - Purpose: {step['purpose']}")
    sections = [
        ("Pending Work Items", "pending_work_items", "work_item"),
        ("Pending Proposals", "pending_proposals", "proposal"),
        ("Approved Work Items", "approved_work_items", "work_item"),
        ("Approved Proposals", "approved_proposals", "proposal"),
        ("Rejected Work Items", "rejected_work_items", "work_item"),
        ("Rejected Proposals", "rejected_proposals", "proposal"),
    ]
    for title, key, record_type in sections:
        lines.extend(["", f"## {title}", ""])
        records = groups[key]
        if not records:
            lines.append("- None.")
            continue
        for record in records:
            if record_type == "work_item":
                lines.append(
                    f"- `{record['id']}` `{record['approval_state']}` "
                    f"`{record['kind']}`: {record['title']}"
                )
                lines.append(f"  - Source: `{record['source']}`")
                lines.append(f"  - Write actions allowed: `{record['write_actions_allowed']}`")
            else:
                lines.append(
                    f"- `{record['id']}` `{record['approval_state']}` "
                    f"`{record['risk_level']}`: {record['title']}"
                )
                lines.append(f"  - Work item: `{record['work_item_id']}`")
            if record.get("decision_note"):
                lines.append(f"  - Decision note: {record['decision_note']}")
    lines.extend(
        [
            "",
            "## Safety",
            "",
            f"- Review is read-only: `{safety['review_is_read_only']}`",
            f"- Review records audit event: `{safety['review_records_audit_event']}`",
            f"- Execution allowed: `{safety['execution_allowed']}`",
            f"- Local paths redacted: `{safety['local_paths_redacted']}`",
            f"- Approval records execute actions: `{safety['approval_records_execute_actions']}`",
            f"- GitHub write permission required: `{safety['github_write_permission_required']}`",
            f"- Network required: `{safety['network_required']}`",
            f"- External model required: `{safety['external_model_required']}`",
            f"- Billing required: `{safety['billing_required']}`",
        ]
    )
    return "\n".join(lines) + "\n"


def _render_queue_review_text(payload: dict[str, Any]) -> str:
    counts = payload["counts"]
    return (
        "\n".join(
            [
                "PatchRail Queue Review Inbox",
                f"DB: {payload['db_path']}",
                f"Status: {payload['status']}",
                f"Ready for reviewer handoff: {payload['ready_for_reviewer_handoff']}",
                f"Pending decisions: {payload['pending_decisions']}",
                f"Work items: {counts['work_items_total']}",
                f"Proposals: {counts['proposals_total']}",
                f"Handoff checklist: {payload['handoff_checklist']}",
                "Review is read-only: True",
                "Review records audit event: False",
                "Execution allowed: False",
                "Local paths redacted: True",
            ]
        )
        + "\n"
    )


def _render_queue_status_text(payload: dict[str, Any]) -> str:
    counts = payload["counts"]
    gate_summary = payload["human_gate_summary"]
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
        f"Human gate status: {gate_summary['status']}",
        f"Pending human decisions: {gate_summary['total_pending_decisions']}",
        f"Latest audit event: {latest_label}",
        "Write actions allowed by default: False",
        "Network required: False",
        "External model required: False",
    ]
    return "\n".join(lines) + "\n"


def _render_queue_status_markdown(payload: dict[str, Any]) -> str:
    counts = payload["counts"]
    gate_summary = payload["human_gate_summary"]
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
    lines.extend(
        [
            "",
            "## Human Gate Summary",
            "",
            f"- Status: `{gate_summary['status']}`",
            f"- Pending work items: `{gate_summary['pending_work_items']}`",
            f"- Pending proposals: `{gate_summary['pending_proposals']}`",
            f"- Total pending decisions: `{gate_summary['total_pending_decisions']}`",
            f"- Write actions unlocked: `{gate_summary['write_actions_unlocked']}`",
        ]
    )
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


def _queue_gate_report(args: argparse.Namespace) -> int:
    payload = queue_gate_report_payload(
        _queue_db(args),
        required_events=args.require_event,
    )
    if args.format == "json":
        text = _json_dump(payload)
    elif args.format == "markdown":
        text = _render_queue_gate_report_markdown(payload)
    else:
        text = _render_queue_gate_report_text(payload)
    _write_or_print(text, args.out)
    return 0 if payload["ready_for_reviewer_handoff"] else 1


def _queue_policy_scan(args: argparse.Namespace) -> int:
    payload = queue_policy_scan_payload(_queue_db(args))
    if args.format == "json":
        text = _json_dump(payload)
    elif args.format == "markdown":
        text = _render_queue_policy_scan_markdown(payload)
    else:
        text = _render_queue_policy_scan_text(payload)
    _write_or_print(text, args.out)
    return 0 if payload["status"] == "policy_clear" else 1


def _queue_policy_resolve(args: argparse.Namespace) -> int:
    payload = queue_policy_resolution_payload(_queue_db(args), reason=args.reason)
    if args.format == "json":
        text = _json_dump(payload)
    elif args.format == "markdown":
        text = _render_queue_policy_resolution_markdown(payload)
    else:
        text = _render_queue_policy_resolution_text(payload)
    _write_or_print(text, args.out)
    return 0


def _queue_review(args: argparse.Namespace) -> int:
    payload = queue_review_payload(_queue_db(args))
    if args.format == "json":
        text = _json_dump(payload)
    elif args.format == "markdown":
        text = _render_queue_review_markdown(payload)
    else:
        text = _render_queue_review_text(payload)
    _write_or_print(text, args.out)
    return 0 if payload["ready_for_reviewer_handoff"] else 1


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


def _render_classes_text(payload: dict[str, Any]) -> str:
    classes = list(payload.get("classes") or [])
    lines = [f"{payload['count']} supported failure classes:", ""]
    for entry in classes:
        lines.append(
            f"- {entry['failure_class']}: {entry['likely_subsystem']} "
            f"— reproduce: {entry['reproduction_command']}"
        )
    fallback = payload.get("fallback")
    if fallback:
        lines.append("")
        lines.append(
            f"Plus `{fallback['failure_class']}` — what you get back when no rule matches "
            "the log. It is not one of the classes above."
        )
    return "\n".join(lines) + "\n"


def _render_classes_markdown(payload: dict[str, Any]) -> str:
    classes = list(payload.get("classes") or [])
    lines = [
        "# PatchRail supported failure classes",
        "",
        f"{payload['count']} classes the local classifier can diagnose.",
        "",
    ]
    for entry in classes:
        lines.append(f"- `{entry['failure_class']}` — {entry['likely_subsystem']}")
        lines.append(f"  - reproduce: `{entry['reproduction_command']}`")
    fallback = payload.get("fallback")
    if fallback:
        lines.append("")
        lines.append(
            f"`{fallback['failure_class']}` is the result when no rule matches the log, "
            "not a class the classifier can diagnose."
        )
    return "\n".join(lines) + "\n"


def _format_classes(payload: dict[str, Any], output_format: str) -> str:
    if output_format == "json":
        return _json_dump(payload)
    if output_format == "markdown":
        return _render_classes_markdown(payload)
    return _render_classes_text(payload)


def _ci_classes(args: argparse.Namespace) -> int:
    payload = list_failure_classes()
    _write_or_print(_format_classes(payload, args.format), args.out)
    return 0


def _ci_explain(args: argparse.Namespace) -> int:
    try:
        raw_log = _read_log(args.log)
    except LogReadError as exc:
        print(f"patchrail ci {args.ci_command}: {exc}", file=sys.stderr)
        return 2
    if not raw_log.strip():
        source = f"--log {args.log}" if args.log is not None else "stdin"
        print(
            f"patchrail ci {args.ci_command}: log input is empty (checked {source})",
            file=sys.stderr,
        )
        print(
            "hint: if you piped `gh run view --log-failed`, the run's logs may have "
            "expired or the run has not failed — point it at a RECENT failed run.",
            file=sys.stderr,
        )
        return 2
    result = classify_ci_log(raw_log)
    if args.redact:
        redaction = redact_ci_log(raw_log)
        result["redaction"] = {
            "redacted": redaction["text"],
            "redactions": redaction["redactions"],
            "local_only": True,
        }
    _write_or_print(_format_result(result, args.format), args.out)
    if (
        getattr(args, "fail_on_unknown", False)
        and result["failure_class"] == "unknown"
        and not result.get("likely_successful_run")
    ):
        return 1
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
    try:
        raw_log = _read_log(args.log)
    except LogReadError as exc:
        print(f"patchrail ci pilot-pack: {exc}", file=sys.stderr)
        return 2
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


def _ci_adoption_event_payload(event: dict[str, Any], source: Path) -> dict[str, Any]:
    source_schema = str(event.get("schema_version") or "")
    product = str(event.get("product") or "")
    action_repository = str(event.get("action_repository") or "patchrail/ci-triage-action")
    action_ref = str(event.get("action_ref") or "")
    adoption_event_id = str(event.get("adoption_event_id") or "")
    adoption_key = str(event.get("adoption_key") or "")
    failure_slug = str(event.get("failure_slug") or "")
    if source_schema != "patchrail.ci_triage_adoption_event.v1":
        raise ValueError(f"unsupported adoption event schema: {source_schema or 'missing'}")
    if product != "ci-triage-action":
        raise ValueError(f"unsupported adoption event product: {product or 'missing'}")
    if not adoption_event_id or not adoption_key or not failure_slug:
        raise ValueError("adoption event requires adoption_event_id, adoption_key and failure_slug")

    workflow_repository = str(event.get("workflow_repository") or "")
    workflow_run_id = str(event.get("workflow_run_id") or "")
    workflow_run_url = str(event.get("workflow_run_url") or "")
    workflow_run_host = str(event.get("workflow_run_host") or "")
    parsed_run_url = urlparse(workflow_run_url) if workflow_run_url else None
    workflow_repository_owner = (
        workflow_repository.split("/", 1)[0]
        if re.fullmatch(r"[^/\s]+/[^/\s]+", workflow_repository)
        else ""
    )
    if workflow_repository and workflow_run_id and workflow_run_url:
        if not workflow_repository_owner:
            raise ValueError("workflow_repository must be an owner/repo pair")
        if not workflow_run_id.isdecimal():
            raise ValueError("workflow_run_id must be numeric")
        expected_path = f"/{workflow_repository}/actions/runs/{workflow_run_id}"
        assert parsed_run_url is not None
        if parsed_run_url.scheme != "https" or parsed_run_url.path != expected_path:
            raise ValueError(
                "workflow_run_url must match workflow_repository and workflow_run_id "
                f"({expected_path})"
            )
        if workflow_run_host and parsed_run_url.netloc != workflow_run_host:
            raise ValueError(
                f"workflow_run_host must match workflow_run_url host ({parsed_run_url.netloc})"
            )
    signal_kind = (
        "workflow_run" if workflow_repository and workflow_run_id else "local_or_sample_signal"
    )
    canonical_action_repository_match = action_repository == "patchrail/ci-triage-action"
    published_action_ref_match = bool(re.fullmatch(r"v[1-9]\d*(?:\.\d+){0,2}", action_ref))
    public_github_run_match = bool(
        parsed_run_url
        and parsed_run_url.scheme == "https"
        and parsed_run_url.netloc == "github.com"
    )
    external_workflow_repository_match = bool(
        workflow_repository_owner and workflow_repository_owner.casefold() != "patchrail"
    )
    triage_artifacts_present = bool(event.get("json_result") and event.get("markdown_report"))
    strict_evidence_requirements = {
        "workflow_context": signal_kind == "workflow_run" and bool(workflow_run_url),
        "canonical_action_repository": canonical_action_repository_match,
        "published_action_ref": published_action_ref_match,
        "public_github_run": public_github_run_match,
        "external_workflow_repository": external_workflow_repository_match,
        "triage_artifacts": triage_artifacts_present,
    }
    missing_strict_evidence = [
        requirement for requirement, present in strict_evidence_requirements.items() if not present
    ]
    strict_evidence_ready_for_permission_request = not missing_strict_evidence
    safe_next_step = (
        "Ask the external maintainer for explicit permission before listing this as adoption."
        if strict_evidence_ready_for_permission_request
        else "Collect missing strict evidence before asking for public adoption permission."
    )
    if signal_kind != "workflow_run":
        safe_next_step = (
            "Use this as local action smoke evidence only; do not claim external adoption."
        )
    strict_verification_command = _ci_adoption_event_strict_verification_command(source)
    payload = {
        "schema_version": "patchrail.ci_triage_adoption_event_review.v1",
        "source_schema_version": source_schema,
        "source_file": str(source),
        "github_issue": "patchrail/patchrail#69",
        "product": product,
        "action_repository": action_repository,
        "canonical_action_repository": "patchrail/ci-triage-action",
        "canonical_action_repository_match": canonical_action_repository_match,
        "action_ref": action_ref,
        "published_action_ref_match": published_action_ref_match,
        "public_github_run_match": public_github_run_match,
        "workflow_repository_owner": workflow_repository_owner,
        "external_workflow_repository_match": external_workflow_repository_match,
        "adoption_key": adoption_key,
        "adoption_event_id": adoption_event_id,
        "failure_class": str(event.get("failure_class") or "unknown"),
        "failure_slug": failure_slug,
        "confidence": str(event.get("confidence") or "0"),
        "redacted_categories": int(event.get("redacted_categories") or 0),
        "artifact_name": str(event.get("artifact_name") or f"patchrail-ci-triage-{failure_slug}"),
        "json_result": str(event.get("json_result") or ""),
        "markdown_report": str(event.get("markdown_report") or ""),
        "triage_artifacts_present": triage_artifacts_present,
        "strict_evidence_requirements": strict_evidence_requirements,
        "missing_strict_evidence": missing_strict_evidence,
        "strict_evidence_ready_for_permission_request": (
            strict_evidence_ready_for_permission_request
        ),
        "workflow_repository": workflow_repository,
        "workflow_run_id": workflow_run_id,
        "workflow_run_url": workflow_run_url,
        "workflow_run_host": workflow_run_host,
        "workflow_name": str(event.get("workflow_name") or ""),
        "workflow_job": str(event.get("workflow_job") or ""),
        "signal_kind": signal_kind,
        "counts_as_external_adoption": False,
        "safe_next_step": safe_next_step,
        "strict_verification_command": strict_verification_command,
        "blocked_actions": [
            "public_adoption_claim_without_maintainer_permission",
            "automatic_adopters_md_update",
            "repository_contact_or_comment",
        ],
    }
    payload["permission_request_copy_brief"] = _ci_adoption_permission_copy_brief(payload)
    return payload


def _ci_adoption_event_strict_verification_command(source: Path) -> str:
    parts = [
        "patchrail",
        "ci",
        "adoption-event",
        "--event",
        str(source),
        "--require-workflow-context",
        "--require-canonical-action",
        "--require-published-action-ref",
        "--require-public-github-run",
        "--require-external-workflow-repository",
        "--require-triage-artifacts",
        "--format",
        "json",
    ]
    return " ".join(shlex.quote(part) for part in parts)


def _ci_adoption_permission_copy_brief(payload: dict[str, Any]) -> dict[str, Any] | None:
    if not payload["strict_evidence_ready_for_permission_request"]:
        return None
    return {
        "write_path": (
            "opportunity-desk/outbox/requests/"
            "<timestamp>-ci-triage-adoption-permission-request.json"
        ),
        "schema": "copy_brief.external_permission_request.v1",
        "prohibited_fields": ["body", "draft", "email_body"],
        "payload": {
            "type": "external_permission_request",
            "channel": "maintainer_permission",
            "lead": payload["workflow_repository"],
            "goal": (
                "Ask the external maintainer for explicit written permission before PatchRail "
                "lists this ci-triage-action workflow run as public adoption evidence."
            ),
            "key_facts": [
                "Product: ci-triage-action.",
                f"Repository: {payload['workflow_repository']}.",
                f"Workflow run URL: {payload['workflow_run_url']}.",
                f"Action repository: {payload['action_repository']}.",
                f"Action ref: {payload['action_ref']}.",
                f"Failure class: {payload['failure_class']}.",
                f"Failure slug: {payload['failure_slug']}.",
                f"JSON result artifact: {payload['json_result']}.",
                f"Markdown report artifact: {payload['markdown_report']}.",
                "Strict evidence checks passed; public adoption is still false until permission.",
                f"Strict verification command: {payload['strict_verification_command']}",
            ],
            "tone": "Concise, respectful, maintainer-safe, no hype.",
            "constraints": [
                "Copywriter authors final external prose; worker does not draft publishable text.",
                "Brand-only: PatchRail.",
                "Ask only for explicit permission to list the public workflow run as adoption evidence.",
                "Do not imply endorsement, payout, partnership, merge outcome, or commercial guarantee.",
                "Do not request repository write access, secrets, billing, calls, or private data.",
            ],
            "urgency": "normal",
            "thread_ref": (
                f"ci adoption-event {payload['adoption_event_id']}; "
                f"run={payload['workflow_run_url']}; issue={payload['github_issue']}"
            ),
            "external_body_allowed": False,
            "payment_route_allowed_now": False,
            "forbidden_fields": ["body", "draft", "email_body"],
        },
    }


def _ci_adoption_permission_copy_brief_dir_path(payload: dict[str, Any], directory: Path) -> Path:
    slug_source = (
        f"{payload['workflow_repository']}-run-{payload['workflow_run_id']}"
        if payload["workflow_repository"] and payload["workflow_run_id"]
        else payload["adoption_event_id"]
    )
    slug = re.sub(r"[^a-z0-9]+", "-", slug_source.lower()).strip("-")
    slug = (slug or "external-workflow")[:80].strip("-")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return directory / f"{timestamp}-ci-triage-adoption-permission-{slug}.json"


def _write_ci_adoption_permission_copy_brief(
    payload: dict[str, Any],
    path: Path,
    *,
    auto_named: bool = False,
    directory: Path | None = None,
) -> dict[str, Any]:
    copy_brief_request = payload["permission_request_copy_brief"]
    if copy_brief_request is None:
        result = {
            "status": "skipped",
            "reason": "strict_evidence_not_ready_for_permission_request",
            "path": str(path),
        }
    elif path.exists():
        result = {
            "status": "skipped",
            "reason": "copy_brief_already_exists",
            "path": str(path),
            "type": copy_brief_request["payload"]["type"],
        }
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json_dump(copy_brief_request["payload"]), encoding="utf-8")
        result = {
            "status": "written",
            "path": str(path),
            "type": copy_brief_request["payload"]["type"],
            "prohibited_fields_present": any(
                field in copy_brief_request["payload"]
                for field in copy_brief_request["prohibited_fields"]
            ),
        }
    if auto_named:
        result["auto_named"] = True
    if directory is not None:
        result["directory"] = str(directory)
    return result


def _render_ci_adoption_event_text(payload: dict[str, Any]) -> str:
    lines = [
        "PatchRail CI triage adoption event review",
        f"Event: {payload['adoption_event_id']}",
        f"Signal: {payload['signal_kind']}",
        f"Repository: {payload['workflow_repository'] or 'n/a'}",
        f"Workflow run: {payload['workflow_run_url'] or payload['workflow_run_id'] or 'n/a'}",
        f"Failure: {payload['failure_slug']} ({payload['confidence']})",
        f"Counts as external adoption: {payload['counts_as_external_adoption']}",
        f"Next safe step: {payload['safe_next_step']}",
    ]
    return "\n".join(lines) + "\n"


def _render_ci_adoption_event_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# PatchRail CI Triage Adoption Event Review",
        "",
        f"- Event: `{payload['adoption_event_id']}`",
        f"- Signal: `{payload['signal_kind']}`",
        f"- Repository: `{payload['workflow_repository'] or 'n/a'}`",
        f"- Workflow run: `{payload['workflow_run_url'] or payload['workflow_run_id'] or 'n/a'}`",
        f"- Failure: `{payload['failure_slug']}`",
        f"- Confidence: `{payload['confidence']}`",
        f"- Redacted categories: `{payload['redacted_categories']}`",
        f"- Counts as external adoption: `{payload['counts_as_external_adoption']}`",
        (
            "- Strict evidence ready for permission request: "
            f"`{payload['strict_evidence_ready_for_permission_request']}`"
        ),
        (
            "- Permission copy brief available: "
            f"`{payload['permission_request_copy_brief'] is not None}`"
        ),
        f"- Tracking issue: `{payload['github_issue']}`",
        "",
        "## Next Safe Step",
        "",
        payload["safe_next_step"],
        "",
        "## Blocked Actions",
        "",
    ]
    lines.extend(f"- `{action}`" for action in payload["blocked_actions"])
    lines.extend(["", "## Missing Strict Evidence", ""])
    missing = payload["missing_strict_evidence"]
    if missing:
        lines.extend(f"- `{requirement}`" for requirement in missing)
    else:
        lines.append("- None; permission is still required before public adoption listing.")
    return "\n".join(lines) + "\n"


def _ci_adoption_event(args: argparse.Namespace) -> int:
    try:
        event = json.loads(args.event.read_text(encoding="utf-8"))
        if not isinstance(event, dict):
            raise ValueError("adoption event must be a JSON object")
        payload = _ci_adoption_event_payload(event, args.event)
        if args.require_workflow_context and (
            payload["signal_kind"] != "workflow_run" or not payload["workflow_run_url"]
        ):
            raise ValueError(
                "adoption event must include workflow_repository, workflow_run_id and "
                "workflow_run_url when --require-workflow-context is set"
            )
        if args.require_canonical_action and not payload["canonical_action_repository_match"]:
            raise ValueError(
                "adoption event action_repository must be patchrail/ci-triage-action "
                "when --require-canonical-action is set"
            )
        if args.require_published_action_ref and not payload["published_action_ref_match"]:
            raise ValueError(
                "adoption event action_ref must be a published major or semver tag "
                "like v1 when --require-published-action-ref is set"
            )
        if args.require_public_github_run and (
            payload["signal_kind"] != "workflow_run" or not payload["public_github_run_match"]
        ):
            raise ValueError(
                "adoption event workflow_run_url must be a public https://github.com Actions run "
                "when --require-public-github-run is set"
            )
        if args.require_external_workflow_repository and (
            payload["signal_kind"] != "workflow_run"
            or not payload["external_workflow_repository_match"]
        ):
            raise ValueError(
                "adoption event workflow_repository must be outside the patchrail GitHub owner "
                "when --require-external-workflow-repository is set"
            )
        if args.require_triage_artifacts and not payload["triage_artifacts_present"]:
            raise ValueError(
                "adoption event must include json_result and markdown_report "
                "when --require-triage-artifacts is set"
            )
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        print(f"Invalid adoption event input: {exc}", file=sys.stderr)
        return 1
    if args.write_copy_brief is not None and args.write_copy_brief_dir is not None:
        print(
            "Use either --write-copy-brief or --write-copy-brief-dir, not both",
            file=sys.stderr,
        )
        return 2
    if args.write_copy_brief is not None:
        payload["copy_brief_write"] = _write_ci_adoption_permission_copy_brief(
            payload, args.write_copy_brief
        )
    if args.write_copy_brief_dir is not None:
        brief_path = _ci_adoption_permission_copy_brief_dir_path(payload, args.write_copy_brief_dir)
        payload["copy_brief_write"] = _write_ci_adoption_permission_copy_brief(
            payload,
            brief_path,
            auto_named=True,
            directory=args.write_copy_brief_dir,
        )
    if args.format == "json":
        text = _json_dump(payload)
    elif args.format == "markdown":
        text = _render_ci_adoption_event_markdown(payload)
    else:
        text = _render_ci_adoption_event_text(payload)
    _write_or_print(text, args.out)
    return 0


def _redact(args: argparse.Namespace) -> int:
    try:
        raw_log = _read_log(args.log)
    except LogReadError as exc:
        print(f"patchrail redact: {exc}", file=sys.stderr)
        return 2
    redaction = redact_ci_log(raw_log)
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


def _coverage_gate_payload(
    class_summary: dict[str, dict[str, int]], min_cases_per_class: int
) -> dict[str, Any]:
    failures = [
        {
            "failure_class": failure_class,
            "total_cases": summary["total_cases"],
            "minimum_cases": min_cases_per_class,
        }
        for failure_class, summary in class_summary.items()
        if summary["total_cases"] < min_cases_per_class
    ]
    return {
        "min_cases_per_class": min_cases_per_class,
        "passed": not failures,
        "failures": failures,
    }


def _run_ci_benchmark(path: Path, *, min_cases_per_class: int = 0) -> dict[str, Any]:
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
    coverage_gate = _coverage_gate_payload(class_summary, min_cases_per_class)
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
        "coverage_gate": coverage_gate,
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
        f"- Coverage gate passed: `{result['coverage_gate']['passed']}`",
        f"- Minimum cases per class: `{result['coverage_gate']['min_cases_per_class']}`",
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
            "## Coverage gate failures",
            "",
        ]
    )
    failures = result["coverage_gate"]["failures"]
    if failures:
        for failure in failures:
            lines.append(
                f"- `{failure['failure_class']}` has `{failure['total_cases']}` cases; "
                f"minimum is `{failure['minimum_cases']}`"
            )
    else:
        lines.append("- None.")
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
        f"Coverage gate passed: {result['coverage_gate']['passed']}",
        f"Minimum cases per class: {result['coverage_gate']['min_cases_per_class']}",
    ]
    for failure_class, summary in result["class_summary"].items():
        lines.append(f"{failure_class}: {summary['passed']} / {summary['total_cases']} passed")
    for failure in result["coverage_gate"]["failures"]:
        lines.append(
            f"COVERAGE FAIL {failure['failure_class']}: "
            f"{failure['total_cases']} < {failure['minimum_cases']}"
        )
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


def _ci_benchmark(args: argparse.Namespace) -> int:
    if args.min_cases_per_class < 0:
        print("--min-cases-per-class must be >= 0", file=sys.stderr)
        return 2
    result = _run_ci_benchmark(args.path, min_cases_per_class=args.min_cases_per_class)
    if args.format == "json":
        payload = _benchmark_summary(result) if args.summary_only else result
        text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    elif args.format == "markdown":
        text = _render_benchmark_markdown(result, include_cases=not args.summary_only)
    else:
        text = _render_benchmark_text(result, include_cases=not args.summary_only)
    _write_or_print(text, args.out)
    return 0 if result["failed"] == 0 and result["coverage_gate"]["passed"] else 1


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
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show the installed PatchRail version and exit.",
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
    explain.add_argument(
        "--fail-on-unknown",
        action="store_true",
        help="Exit non-zero when the classifier could not recognize the failure (failure_class: unknown). A log that plainly reports a successful run is exempt: there is no failure to fail on.",
    )
    explain.set_defaults(func=_ci_explain)

    classes = ci_subparsers.add_parser(
        "classes",
        help="List every supported failure class the classifier can diagnose.",
    )
    classes.add_argument(
        "--format",
        choices=["text", "json", "markdown"],
        default="text",
        help="Output format.",
    )
    classes.add_argument("--out", type=Path, help="Optional output path.")
    classes.set_defaults(func=_ci_classes)

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
    classify.add_argument(
        "--fail-on-unknown",
        action="store_true",
        help="Exit non-zero when the classifier could not recognize the failure (failure_class: unknown). A log that plainly reports a successful run is exempt: there is no failure to fail on.",
    )
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
    benchmark.add_argument(
        "--min-cases-per-class",
        type=int,
        default=0,
        help=(
            "Fail the benchmark if any covered root-cause family has fewer than this many fixtures."
        ),
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

    adoption_event = ci_subparsers.add_parser(
        "adoption-event",
        help="Review one ci-triage-action adoption-event-json without claiming adoption.",
    )
    adoption_event.add_argument(
        "--event",
        type=Path,
        required=True,
        help="JSON file emitted by the ci-triage-action adoption-event-json output.",
    )
    adoption_event.add_argument(
        "--format",
        choices=["json", "markdown", "text"],
        default="text",
        help="Output format.",
    )
    adoption_event.add_argument(
        "--require-workflow-context",
        action="store_true",
        help=(
            "Fail unless the event includes repository, run id and run URL from a real "
            "workflow run."
        ),
    )
    adoption_event.add_argument(
        "--require-canonical-action",
        action="store_true",
        help="Fail unless action_repository is patchrail/ci-triage-action.",
    )
    adoption_event.add_argument(
        "--require-published-action-ref",
        action="store_true",
        help="Fail unless action_ref is a published major or semver tag such as v1.",
    )
    adoption_event.add_argument(
        "--require-public-github-run",
        action="store_true",
        help="Fail unless workflow_run_url is a public https://github.com Actions run.",
    )
    adoption_event.add_argument(
        "--require-external-workflow-repository",
        action="store_true",
        help="Fail unless workflow_repository is outside the patchrail GitHub owner.",
    )
    adoption_event.add_argument(
        "--require-triage-artifacts",
        action="store_true",
        help="Fail unless json_result and markdown_report are present in the event.",
    )
    adoption_event.add_argument(
        "--write-copy-brief",
        type=Path,
        help=(
            "Optional outbox/requests path for the facts-only maintainer permission "
            "copy brief when strict evidence is ready."
        ),
    )
    adoption_event.add_argument(
        "--write-copy-brief-dir",
        type=Path,
        help=(
            "Optional outbox/requests directory; PatchRail derives a safe facts-only "
            "maintainer permission copy brief filename from the workflow repository and run."
        ),
    )
    adoption_event.add_argument("--out", type=Path, help="Optional output path.")
    adoption_event.set_defaults(func=_ci_adoption_event)

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
            "application-dossier",
            "ci-benchmark",
            "ci-classes",
            "ci-fixture-check",
            "ci-pilot-metrics",
            "ci-pilot-summary",
            "ci-result",
            "funded-issues-client-report",
            "funded-issues-report",
            "funded-issues-recheck-queue",
            "funded-issues-recheck-summary",
            "funded-issues-shortlist",
            "funded-issues-store",
            "funded-issues-store-status",
            "queue-audit-event",
            "queue-audit-summary",
            "queue-gate-report",
            "queue-policy-resolution",
            "queue-policy-scan",
            "queue-proposal",
            "queue-review",
            "queue-status",
            "queue-work-item",
            "reviewer-quick-check-artifacts",
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
        help="Summarize local open-source program evidence without network or write actions.",
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
        help="Audit v0.1.0-v0.4.0 and 12-week open-source roadmap progress from local artifacts.",
    )
    evidence_roadmap.add_argument(
        "--format",
        choices=["json", "markdown", "text"],
        default="markdown",
        help="Output format.",
    )
    evidence_roadmap.add_argument("--out", type=Path, help="Optional output path.")
    evidence_roadmap.set_defaults(func=_evidence_roadmap)

    evidence_release_readiness = evidence_subparsers.add_parser(
        "release-readiness",
        description="Build and smoke-test local release artifacts without publishing.",
        help="Build and smoke-test local release artifacts without publishing.",
    )
    evidence_release_readiness.add_argument(
        "--dist-dir",
        default=Path("dist"),
        type=Path,
        help="Directory for local sdist and wheel artifacts.",
    )
    evidence_release_readiness.add_argument(
        "--fixture",
        default=Path("examples/ci-triage/dependency-failure.log"),
        type=Path,
        help="Fixture used for the installed-wheel smoke test.",
    )
    evidence_release_readiness.add_argument(
        "--clean-dist",
        action="store_true",
        help="Remove the dist directory before building local artifacts.",
    )
    evidence_release_readiness.add_argument(
        "--format",
        choices=["json", "markdown", "text"],
        default="markdown",
        help="Output format.",
    )
    evidence_release_readiness.add_argument("--out", type=Path, help="Optional output path.")
    evidence_release_readiness.set_defaults(func=_evidence_release_readiness)

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

    evidence_control_plane_demo = evidence_subparsers.add_parser(
        "control-plane-demo",
        help="Run the local Agent Control Plane demo and validate its evidence summary.",
    )
    evidence_control_plane_demo.add_argument(
        "--out-dir",
        type=Path,
        default=Path(".patchrail-demo"),
        help="Directory for generated local demo artifacts. Defaults to .patchrail-demo.",
    )
    evidence_control_plane_demo.add_argument(
        "--force",
        action="store_true",
        help="Overwrite generated demo artifacts in the output directory.",
    )
    evidence_control_plane_demo.add_argument(
        "--format",
        choices=["json", "markdown", "text"],
        default="markdown",
        help="Output format.",
    )
    evidence_control_plane_demo.add_argument("--out", type=Path, help="Optional output path.")
    evidence_control_plane_demo.set_defaults(func=_evidence_control_plane_demo)

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

    evidence_reviewer_packet = evidence_subparsers.add_parser(
        "reviewer-packet",
        help="Generate the local reviewer quick-check Markdown/JSON artifact packet.",
    )
    evidence_reviewer_packet.add_argument(
        "--out-dir",
        type=Path,
        help="Optional directory for reviewer-facing Markdown/JSON artifacts.",
    )
    evidence_reviewer_packet.set_defaults(func=_evidence_reviewer_packet)

    evidence_verify_reviewer_packet = evidence_subparsers.add_parser(
        "verify-reviewer-packet",
        help="Verify a local reviewer packet manifest by recomputing SHA-256 and byte sizes.",
    )
    evidence_verify_reviewer_packet.add_argument(
        "packet_dir",
        type=Path,
        help="Directory created by `patchrail evidence reviewer-packet --out-dir`.",
    )
    evidence_verify_reviewer_packet.add_argument(
        "--format",
        choices=["json", "markdown", "text"],
        default="markdown",
        help="Output format.",
    )
    evidence_verify_reviewer_packet.add_argument("--out", type=Path, help="Optional output path.")
    evidence_verify_reviewer_packet.set_defaults(func=_evidence_verify_reviewer_packet)

    evidence_application_gate = evidence_subparsers.add_parser(
        "application-gate",
        help="Fail closed until external application evidence is real and non-placeholder.",
    )
    evidence_application_gate.add_argument(
        "--format",
        choices=["json", "markdown", "text"],
        default="markdown",
        help="Output format.",
    )
    evidence_application_gate.add_argument("--out", type=Path, help="Optional output path.")
    evidence_application_gate.set_defaults(func=_evidence_application_gate)

    evidence_application_dossier = evidence_subparsers.add_parser(
        "application-dossier",
        description="Compile a local external-program application dossier without submitting it.",
        help="Compile a local external-program application dossier without submitting it.",
    )
    evidence_application_dossier.add_argument(
        "--format",
        choices=["json", "markdown", "text"],
        default="markdown",
        help="Output format.",
    )
    evidence_application_dossier.add_argument("--out", type=Path, help="Optional output path.")
    evidence_application_dossier.set_defaults(func=_evidence_application_dossier)

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

    queue_review = queue_subparsers.add_parser(
        "review",
        help="Show the local human review inbox without exporting full queue records.",
    )
    queue_review.add_argument(
        "--format",
        choices=["json", "markdown", "text"],
        default="markdown",
        help="Output format.",
    )
    queue_review.add_argument("--out", type=Path, help="Optional output path.")
    queue_review.set_defaults(func=_queue_review)

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

    queue_gate_report = queue_subparsers.add_parser(
        "gate-report",
        help="Summarize reviewer handoff readiness without exporting queue records.",
    )
    queue_gate_report.add_argument(
        "--require-event",
        action="append",
        help=(
            "Audit event type required for ready status. May be repeated. Defaults to the "
            "full local demo gate sequence."
        ),
    )
    queue_gate_report.add_argument(
        "--format",
        choices=["json", "markdown", "text"],
        default="text",
        help="Output format.",
    )
    queue_gate_report.add_argument("--out", type=Path, help="Optional output path.")
    queue_gate_report.set_defaults(func=_queue_gate_report)

    queue_policy_scan = queue_subparsers.add_parser(
        "policy-scan",
        help="Fail closed if local queue records contain blocked automation signals.",
    )
    queue_policy_scan.add_argument(
        "--format",
        choices=["json", "markdown", "text"],
        default="markdown",
        help="Output format.",
    )
    queue_policy_scan.add_argument("--out", type=Path, help="Optional output path.")
    queue_policy_scan.set_defaults(func=_queue_policy_scan)

    queue_policy_resolve = queue_subparsers.add_parser(
        "policy-resolve",
        help=(
            "Locally skip/reject active records flagged by policy-scan while preserving audit history."
        ),
    )
    queue_policy_resolve.add_argument(
        "--reason",
        default=DEFAULT_POLICY_RESOLUTION_REASON,
        help="Decision note recorded in the local audit trail.",
    )
    queue_policy_resolve.add_argument(
        "--format",
        choices=["json", "markdown", "text"],
        default="markdown",
        help="Output format.",
    )
    queue_policy_resolve.add_argument("--out", type=Path, help="Optional output path.")
    queue_policy_resolve.set_defaults(func=_queue_policy_resolve)

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

    from patchrail.cli_funded import register as _register_funded_cli

    _register_funded_cli(subparsers)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
