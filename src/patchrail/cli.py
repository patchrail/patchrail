from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from importlib.resources import files
from pathlib import Path
from typing import Any

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
)
from patchrail.queue.server import serve_queue_api


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
        "ci-result": "ci-result.v1.schema.json",
        "queue-audit-event": "queue-audit-event.v1.schema.json",
        "queue-proposal": "queue-proposal.v1.schema.json",
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
        choices=["ci-result", "queue-audit-event", "queue-proposal", "queue-work-item"],
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
