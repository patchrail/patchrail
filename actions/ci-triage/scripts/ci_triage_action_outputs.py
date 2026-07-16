from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


OUTPUT_KEYS = {
    "failure-class": "failure_class",
    "confidence": "confidence",
    "next-step": "minimal_repair_strategy",
    "reproduction-command": "reproduction_command",
}


def summary_line(result: dict[str, Any]) -> str:
    failure_class = str(result.get("failure_class") or "unknown")
    confidence = str(result.get("confidence") or "0")
    return f"PatchRail CI triage: {failure_class} ({confidence})"


def redacted_category_count(result: dict[str, Any]) -> int:
    redaction = result.get("redaction")
    if not isinstance(redaction, dict):
        return 0
    redactions = redaction.get("redactions")
    if not isinstance(redactions, dict):
        return 0
    return len(redactions)


def failure_slug(result: dict[str, Any]) -> str:
    failure_class = str(result.get("failure_class") or "unknown").strip() or "unknown"
    return failure_class.replace("_", "-")


def adoption_key(result: dict[str, Any], slug: str) -> str:
    return f"ci-triage:{slug}"


def adoption_event_id(
    result: dict[str, Any],
    slug: str,
    workflow_context: dict[str, str] | None = None,
) -> str:
    context = workflow_context or {}
    repository = str(context.get("workflow_repository") or "").strip()
    run_id = str(context.get("workflow_run_id") or "").strip()
    if repository and run_id:
        parts = ["ci-triage-run", repository, run_id]
        job = str(context.get("workflow_job") or "").strip()
        if job:
            parts.append(job)
        parts.append(slug)
        return ":".join(parts)
    return adoption_key(result, slug)


def adoption_event(
    result: dict[str, Any],
    slug: str,
    result_path: Path | None = None,
    report_path: Path | None = None,
    action_ref: str = "local",
    action_repository: str = "patchrail/ci-triage-action",
    workflow_context: dict[str, str] | None = None,
) -> str:
    event = {
        "schema_version": "patchrail.ci_triage_adoption_event.v1",
        "product": "ci-triage-action",
        "action_ref": action_ref or "local",
        "action_repository": action_repository or "patchrail/ci-triage-action",
        "adoption_key": adoption_key(result, slug),
        "adoption_event_id": adoption_event_id(result, slug, workflow_context),
        "failure_class": str(result.get("failure_class") or "unknown"),
        "failure_slug": slug,
        "confidence": str(result.get("confidence") or "0"),
        "redacted_categories": redacted_category_count(result),
        "artifact_name": f"patchrail-ci-triage-{slug}",
    }
    if result_path is not None:
        event["json_result"] = str(result_path)
    if report_path is not None:
        event["markdown_report"] = str(report_path)
    if workflow_context:
        event.update(workflow_context)
    return json.dumps(event, sort_keys=True, separators=(",", ":"))


def workflow_context_from_env(env: dict[str, str] | None = None) -> dict[str, str]:
    source = os.environ if env is None else env
    repository = str(source.get("GITHUB_REPOSITORY") or "").strip()
    run_id = str(source.get("GITHUB_RUN_ID") or "").strip()
    raw_server_url = str(source.get("GITHUB_SERVER_URL") or "").strip()
    server_url = raw_server_url or "https://github.com"
    context: dict[str, str] = {}
    if repository:
        context["workflow_repository"] = repository
    if run_id:
        context["workflow_run_id"] = run_id
    if repository and run_id:
        context["workflow_run_url"] = f"{server_url.rstrip('/')}/{repository}/actions/runs/{run_id}"
    if raw_server_url or repository or run_id:
        context["workflow_run_host"] = urlparse(server_url).netloc or server_url
    optional_fields = {
        "GITHUB_REF": "workflow_ref",
        "GITHUB_SHA": "workflow_sha",
        "GITHUB_WORKFLOW": "workflow_name",
        "GITHUB_JOB": "workflow_job",
    }
    for env_name, event_name in optional_fields.items():
        value = str(source.get(env_name) or "").strip()
        if value:
            context[event_name] = value
    return context


def action_outputs(
    result: dict[str, Any],
    result_path: Path,
    report_path: Path,
    action_ref: str = "local",
    action_repository: str = "patchrail/ci-triage-action",
    workflow_context: dict[str, str] | None = None,
) -> dict[str, str]:
    slug = failure_slug(result)
    outputs = {}
    for output_name, result_name in OUTPUT_KEYS.items():
        outputs[output_name] = str(result.get(result_name, ""))
        if output_name == "failure-class":
            outputs["failure-slug"] = slug
    outputs["artifact-name"] = f"patchrail-ci-triage-{slug}"
    outputs["json-result"] = str(result_path)
    outputs["markdown-report"] = str(report_path)
    outputs["summary-line"] = summary_line(result)
    outputs["redacted-categories"] = str(redacted_category_count(result))
    outputs["adoption-key"] = adoption_key(result, slug)
    outputs["adoption-event-id"] = adoption_event_id(result, slug, workflow_context)
    outputs["adoption-event-json"] = adoption_event(
        result,
        slug,
        result_path=result_path,
        report_path=report_path,
        action_ref=action_ref,
        action_repository=action_repository,
        workflow_context=workflow_context,
    )
    outputs["workflow-repository"] = (workflow_context or {}).get("workflow_repository", "")
    outputs["workflow-run-url"] = (workflow_context or {}).get("workflow_run_url", "")
    outputs["workflow-run-host"] = (workflow_context or {}).get("workflow_run_host", "")
    return outputs


def write_github_outputs(outputs: dict[str, str], path: Path) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for name, value in outputs.items():
            clean_value = value.replace("\n", " ").replace("\r", " ")
            handle.write(f"{name}={clean_value}\n")


def append_step_summary(
    result: dict[str, Any],
    report_path: Path,
    path: Path,
    workflow_context: dict[str, str] | None = None,
) -> None:
    slug = failure_slug(result)
    event_id = adoption_event_id(result, slug, workflow_context)
    lines = [
        "## PatchRail CI triage",
        "",
        f"- Summary: {summary_line(result)}",
        f"- Next step: {result.get('minimal_repair_strategy') or 'Open the report for repair details.'}",
    ]
    reproduction_command = str(result.get("reproduction_command") or "").strip()
    if reproduction_command:
        lines.append(f"- Reproduce locally: `{reproduction_command}`")
    lines += [
        f"- Adoption key: `{adoption_key(result, slug)}`",
        f"- Adoption event ID: `{event_id}`",
        f"- Redacted categories: `{redacted_category_count(result)}`",
        f"- Report: `{report_path}`",
    ]
    workflow_run_url = (workflow_context or {}).get("workflow_run_url", "")
    if workflow_run_url:
        lines.append(f"- Workflow run: {workflow_run_url}")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export PatchRail CI triage GitHub outputs.")
    parser.add_argument("--result", type=Path, required=True, help="PatchRail ci-result.json path.")
    parser.add_argument("--report", type=Path, required=True, help="PatchRail ci-report.md path.")
    parser.add_argument("--output", type=Path, required=True, help="GitHub output file path.")
    parser.add_argument("--summary", type=Path, help="Optional GitHub step summary path.")
    args = parser.parse_args(argv)

    result = json.loads(args.result.read_text(encoding="utf-8"))
    workflow_context = workflow_context_from_env()
    write_github_outputs(
        action_outputs(
            result,
            args.result,
            args.report,
            action_ref=os.environ.get("GITHUB_ACTION_REF", "local"),
            action_repository=os.environ.get(
                "GITHUB_ACTION_REPOSITORY",
                "patchrail/ci-triage-action",
            ),
            workflow_context=workflow_context,
        ),
        args.output,
    )
    if args.summary is not None:
        append_step_summary(result, args.report, args.summary, workflow_context=workflow_context)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
