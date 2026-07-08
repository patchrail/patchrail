from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from patchrail.cli import main


ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / "actions" / "ci-triage" / "action.yml"
HELPER = ROOT / "actions" / "ci-triage" / "scripts" / "ci_triage_action_outputs.py"
FIXTURE = ROOT / "examples" / "ci-triage" / "dependency-failure.log"
ACTION_SNIPPET = ROOT / "examples" / "ci-triage-action" / "README.md"
ACTION_SAMPLE = ROOT / "examples" / "ci-triage-action" / "sample"


def _load_helper():
    spec = importlib.util.spec_from_file_location("ci_triage_action_outputs", HELPER)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_ci_triage_action_is_local_composite_action() -> None:
    text = ACTION.read_text(encoding="utf-8")

    assert "using: composite" in text
    assert "patchrail ci classify" in text
    assert "patchrail ci explain" in text
    assert "$GITHUB_ACTION_PATH/../.." in text
    assert "failure-class:" in text
    assert "failure-slug:" in text
    assert "artifact-name:" in text
    assert "next-step:" in text
    assert "reproduction-command:" in text
    assert "summary-line:" in text
    assert "redacted-categories:" in text
    assert "adoption-key:" in text
    assert "adoption-event-id:" in text
    assert "adoption-event-json:" in text
    assert "workflow-repository:" in text
    assert "workflow-run-url:" in text
    assert "workflow-run-host:" in text
    assert "GITHUB_STEP_SUMMARY" in text


def test_ci_triage_action_snippet_is_local_only() -> None:
    text = ACTION_SNIPPET.read_text(encoding="utf-8")

    assert "uses: patchrail/ci-triage-action@v1" in text
    assert "report-dir: patchrail-ci-triage" in text
    assert "`next-step`" in text
    assert "`adoption-key`" in text
    assert "`adoption-event-id`" in text
    assert "`adoption-event-json`" in text
    assert "`workflow-run-url`" in text
    assert "`workflow-run-host`" in text
    assert "real workflow usage countable" in text
    assert "does not open pull requests" in text
    assert "post comments" in text
    assert "send the log to" in text
    assert "an external service" in text
    assert "sample/ci-result.json" in text
    assert "docs/fix/python-dependency-resolution.md" in text
    assert "gumroad" not in text
    assert "utm_" not in text


def test_ci_triage_action_helper_exports_reusable_outputs(tmp_path: Path, monkeypatch) -> None:
    result_path = tmp_path / "ci-result.json"
    report_path = tmp_path / "ci-report.md"
    output_path = tmp_path / "github-output.txt"
    summary_path = tmp_path / "step-summary.md"
    for name in (
        "GITHUB_REPOSITORY",
        "GITHUB_RUN_ID",
        "GITHUB_REF",
        "GITHUB_SHA",
        "GITHUB_WORKFLOW",
        "GITHUB_JOB",
        "GITHUB_SERVER_URL",
    ):
        monkeypatch.delenv(name, raising=False)

    assert (
        main(
            [
                "ci",
                "classify",
                "--log",
                str(FIXTURE),
                "--format",
                "json",
                "--out",
                str(result_path),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "ci",
                "explain",
                "--log",
                str(FIXTURE),
                "--format",
                "markdown",
                "--out",
                str(report_path),
            ]
        )
        == 0
    )

    helper = _load_helper()
    assert (
        helper.main(
            [
                "--result",
                str(result_path),
                "--report",
                str(report_path),
                "--output",
                str(output_path),
                "--summary",
                str(summary_path),
            ]
        )
        == 0
    )

    lines = output_path.read_text(encoding="utf-8").splitlines()
    outputs = dict(line.split("=", 1) for line in lines)
    result = json.loads(result_path.read_text(encoding="utf-8"))

    assert outputs["failure-class"] == result["failure_class"]
    assert outputs["failure-slug"] == "python-dependency-resolution"
    assert outputs["confidence"] == str(result["confidence"])
    assert "guide-url" not in outputs
    assert "pack-url" not in outputs
    assert "sample-url" not in outputs
    assert "action-url" not in outputs
    assert "utm-source" not in outputs
    assert "utm-campaign" not in outputs
    assert outputs["next-step"] == result["minimal_repair_strategy"]
    assert outputs["reproduction-command"] == result["reproduction_command"]
    assert outputs["json-result"] == str(result_path)
    assert outputs["artifact-name"] == "patchrail-ci-triage-python-dependency-resolution"
    assert outputs["markdown-report"] == str(report_path)
    assert outputs["summary-line"].startswith("PatchRail CI triage: python_dependency_resolution")
    assert outputs["redacted-categories"] == "0"
    assert outputs["adoption-key"] == "ci-triage:python-dependency-resolution"
    assert outputs["adoption-event-id"] == "ci-triage:python-dependency-resolution"
    adoption_event = json.loads(outputs["adoption-event-json"])
    assert adoption_event == {
        "schema_version": "patchrail.ci_triage_adoption_event.v1",
        "product": "ci-triage-action",
        "action_ref": "local",
        "action_repository": "patchrail/ci-triage-action",
        "adoption_key": "ci-triage:python-dependency-resolution",
        "adoption_event_id": "ci-triage:python-dependency-resolution",
        "failure_class": "python_dependency_resolution",
        "failure_slug": "python-dependency-resolution",
        "confidence": "0.89",
        "redacted_categories": 0,
        "artifact_name": "patchrail-ci-triage-python-dependency-resolution",
        "json_result": str(result_path),
        "markdown_report": str(report_path),
    }
    assert outputs["workflow-repository"] == ""
    assert outputs["workflow-run-url"] == ""
    assert outputs["workflow-run-host"] == ""

    summary = summary_path.read_text(encoding="utf-8")
    assert "## PatchRail CI triage" in summary
    assert outputs["summary-line"] in summary
    assert outputs["next-step"] in summary
    assert "- Redacted categories: `0`" in summary
    assert "- Adoption key: `ci-triage:python-dependency-resolution`" in summary
    assert "- Adoption event ID: `ci-triage:python-dependency-resolution`" in summary
    assert str(report_path) in summary


def test_ci_triage_action_helper_exports_stable_keys_for_unlisted_classes() -> None:
    helper = _load_helper()
    outputs = helper.action_outputs(
        {
            "failure_class": "pre_commit_hook_failure",
            "confidence": 0.7,
            "minimal_repair_strategy": "Run the hook locally.",
            "reproduction_command": "pre-commit run --all-files",
        },
        Path("ci-result.json"),
        Path("ci-report.md"),
    )

    assert outputs["failure-slug"] == "pre-commit-hook-failure"
    assert outputs["adoption-key"] == "ci-triage:pre-commit-hook-failure"
    assert outputs["adoption-event-id"] == "ci-triage:pre-commit-hook-failure"
    adoption_event = json.loads(outputs["adoption-event-json"])
    assert adoption_event["adoption_event_id"] == "ci-triage:pre-commit-hook-failure"
    assert adoption_event["json_result"] == "ci-result.json"
    assert adoption_event["markdown_report"] == "ci-report.md"


def test_ci_triage_action_helper_exports_workflow_context_when_available(tmp_path: Path) -> None:
    helper = _load_helper()
    result = {
        "failure_class": "python_lint",
        "confidence": 0.88,
        "minimal_repair_strategy": "Run ruff locally.",
        "reproduction_command": "ruff check .",
    }
    context = helper.workflow_context_from_env(
        {
            "GITHUB_REPOSITORY": "buyer/repo",
            "GITHUB_RUN_ID": "123456",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": "abc123",
            "GITHUB_WORKFLOW": "CI",
            "GITHUB_JOB": "test",
            "GITHUB_SERVER_URL": "https://github.enterprise.test",
        }
    )

    outputs = helper.action_outputs(
        result,
        Path("ci-result.json"),
        Path("ci-report.md"),
        action_ref="v1",
        action_repository="patchrail/ci-triage-action",
        workflow_context=context,
    )

    assert outputs["workflow-repository"] == "buyer/repo"
    assert (
        outputs["workflow-run-url"]
        == "https://github.enterprise.test/buyer/repo/actions/runs/123456"
    )
    assert outputs["workflow-run-host"] == "github.enterprise.test"
    assert outputs["adoption-event-id"] == "ci-triage-run:buyer/repo:123456:test:python-lint"
    adoption_event = json.loads(outputs["adoption-event-json"])
    assert adoption_event["adoption_event_id"] == "ci-triage-run:buyer/repo:123456:test:python-lint"
    assert adoption_event["workflow_repository"] == "buyer/repo"
    assert adoption_event["workflow_run_id"] == "123456"
    assert (
        adoption_event["workflow_run_url"]
        == "https://github.enterprise.test/buyer/repo/actions/runs/123456"
    )
    assert adoption_event["workflow_run_host"] == "github.enterprise.test"
    assert adoption_event["workflow_ref"] == "refs/heads/main"
    assert adoption_event["workflow_sha"] == "abc123"
    assert adoption_event["workflow_name"] == "CI"
    assert adoption_event["workflow_job"] == "test"

    summary_path = tmp_path / "step-summary.md"
    helper.append_step_summary(result, Path("ci-report.md"), summary_path, workflow_context=context)
    summary = summary_path.read_text(encoding="utf-8")

    assert "- Adoption event ID: `ci-triage-run:buyer/repo:123456:test:python-lint`" in summary
    assert (
        "- Workflow run: https://github.enterprise.test/buyer/repo/actions/runs/123456" in summary
    )


def test_ci_triage_action_helper_counts_redacted_categories(tmp_path: Path) -> None:
    helper = _load_helper()
    result = {
        "failure_class": "python_test_failure",
        "confidence": 0.9,
        "minimal_repair_strategy": "Rerun pytest locally.",
        "reproduction_command": "pytest tests/test_app.py",
        "redaction": {
            "local_only": True,
            "redactions": {
                "github_token": 1,
                "email": 2,
            },
        },
    }

    output_path = tmp_path / "github-output.txt"
    summary_path = tmp_path / "step-summary.md"
    outputs = helper.action_outputs(
        result,
        Path("ci-result.json"),
        Path("ci-report.md"),
        action_ref="v1",
        action_repository="patchrail/ci-triage-action",
    )

    assert outputs["redacted-categories"] == "2"
    adoption_event = json.loads(outputs["adoption-event-json"])
    assert adoption_event["redacted_categories"] == 2
    assert adoption_event["action_ref"] == "v1"

    helper.write_github_outputs(outputs, output_path)
    assert "adoption-event-id=ci-triage:python-test-failure\n" in output_path.read_text(
        encoding="utf-8"
    )
    assert "redacted-categories=2\n" in output_path.read_text(encoding="utf-8")

    helper.append_step_summary(result, Path("ci-report.md"), summary_path)
    assert "- Adoption event ID: `ci-triage:python-test-failure`" in summary_path.read_text(
        encoding="utf-8"
    )
    assert "- Redacted categories: `2`" in summary_path.read_text(encoding="utf-8")


def test_ci_triage_action_sample_matches_dependency_fixture(tmp_path: Path) -> None:
    generated_result = tmp_path / "ci-result.json"
    generated_report = tmp_path / "ci-report.md"
    generated_summary = tmp_path / "step-summary.md"

    assert (
        main(
            [
                "ci",
                "classify",
                "--log",
                str(FIXTURE),
                "--format",
                "json",
                "--out",
                str(generated_result),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "ci",
                "explain",
                "--log",
                str(FIXTURE),
                "--format",
                "markdown",
                "--out",
                str(generated_report),
            ]
        )
        == 0
    )

    sample_result = ACTION_SAMPLE / "ci-result.json"
    sample_report = ACTION_SAMPLE / "ci-report.md"
    sample_output = ACTION_SAMPLE / "github-output.txt"
    sample_summary = ACTION_SAMPLE / "step-summary.md"

    assert sample_result.read_text(encoding="utf-8") == generated_result.read_text(encoding="utf-8")
    assert sample_report.read_text(encoding="utf-8") == generated_report.read_text(encoding="utf-8")

    helper = _load_helper()
    result = json.loads(sample_result.read_text(encoding="utf-8"))
    expected_outputs = helper.action_outputs(
        result,
        Path("examples/ci-triage-action/sample/ci-result.json"),
        Path("examples/ci-triage-action/sample/ci-report.md"),
    )
    assert sample_output.read_text(encoding="utf-8") == "".join(
        f"{name}={value}\n" for name, value in expected_outputs.items()
    )

    helper.append_step_summary(
        result,
        Path("examples/ci-triage-action/sample/ci-report.md"),
        generated_summary,
    )
    assert sample_summary.read_text(encoding="utf-8") == generated_summary.read_text(
        encoding="utf-8"
    )
