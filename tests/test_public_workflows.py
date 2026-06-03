from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ci_triage_workflow_is_read_only_and_human_reviewed() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci-triage.yml").read_text(encoding="utf-8")

    assert "contents: read" in workflow
    assert "actions: read" in workflow
    assert "issues: write" not in workflow
    assert "pull-requests: write" not in workflow
    assert "uv run patchrail ci explain --redact" in workflow
    assert "uv run patchrail ci classify --redact" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "gh pr create" not in workflow
    assert "gh issue comment" not in workflow


def test_github_action_docs_preserve_safety_boundary() -> None:
    docs = (ROOT / "docs" / "github-action.md").read_text(encoding="utf-8")

    assert "does not comment on issues or pull requests" in docs
    assert "does not open pull requests" in docs
    assert "does not call external models" in docs
    assert "contents: read" in docs
    assert "actions: read" in docs
    assert "patchrail-ci-triage" in docs
    assert "examples/github-action" in docs


def test_github_action_artifact_example_is_report_only_and_sanitized() -> None:
    artifact_dir = ROOT / "examples" / "github-action" / "patchrail-ci-triage-artifact"
    readme = (ROOT / "examples" / "github-action" / "README.md").read_text(encoding="utf-8")
    report = (artifact_dir / "ci-report.md").read_text(encoding="utf-8")
    result = json.loads((artifact_dir / "ci-result.json").read_text(encoding="utf-8"))
    benchmark = json.loads((artifact_dir / "fixture-benchmark.json").read_text(encoding="utf-8"))
    doctor = json.loads((artifact_dir / "doctor.json").read_text(encoding="utf-8"))

    assert "patchrail-ci-triage" in readme
    assert "does not comment on issues or pull requests" in readme
    assert "does not open pull requests" in readme
    assert "does not call external models" in readme

    assert "PatchRail classified this log locally" in report
    assert "did not create a pull request" in report
    assert result["failure_class"] == "python_dependency_resolution"
    assert result["requirements"]["billing_required"] is False
    assert result["requirements"]["external_model_required"] is False
    assert benchmark["total_cases"] == 101
    assert benchmark["failed"] == 0
    assert doctor["status"] == "ok"
    assert doctor["requirements"]["github_write_permission_required"] is False

    serialized = "\n".join(
        [
            readme,
            report,
            json.dumps(result),
            json.dumps(benchmark),
            json.dumps(doctor),
        ]
    )
    assert "/Volumes/" not in serialized
    assert "/Users/" not in serialized
    assert "/home/runner/" not in serialized


def test_oss_plan_canonical_docs_exist_and_preserve_human_gates() -> None:
    codex_workflows = (ROOT / "docs" / "codex-workflows.md").read_text(encoding="utf-8")
    evidence = (ROOT / "docs" / "openai-codex-for-oss-evidence.md").read_text(encoding="utf-8")
    api_reference = (ROOT / "docs" / "api-reference.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    quickstart = (ROOT / "docs" / "quickstart.md").read_text(encoding="utf-8")

    assert "docs/codex-workflows.md" in readme
    assert "docs/openai-codex-for-oss-evidence.md" in readme
    assert "docs/api-reference.md" in readme
    assert "pipx install patchrail" in readme
    assert "pipx install patchrail" in quickstart
    assert "patchrail ci explain --log failed-github-actions.log" in quickstart
    assert "The v0.1 release does not require Codex or any external model" in codex_workflows
    assert "no automatic pull requests" in codex_workflows
    assert "Human approval gates for write actions" in evidence
    assert "No automatic bounty claiming" in evidence
    assert "patchrail.queue_api.v1" in api_reference
    assert "write_actions_allowed_by_default" in api_reference
    assert "Approval does not open a pull request" in api_reference


def test_funded_issues_docs_preserve_read_only_boundary() -> None:
    docs = (ROOT / "docs" / "funded-issues-ethics.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "docs" / "roadmap.md").read_text(encoding="utf-8")
    example = (ROOT / "examples" / "funded-issues-readonly" / "README.md").read_text(
        encoding="utf-8"
    )

    combined = "\n".join([docs, roadmap, example])
    assert "patchrail funded-issues list" in combined
    assert "patchrail funded-issues explain" in combined
    assert "does not claim rewards" in combined
    assert "does not permit write actions" in combined
    assert "No automatic claims, comments, pull requests" in roadmap
    assert "local JSON" in combined


def test_ci_workflow_builds_and_smokes_installable_package() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    release_process = (ROOT / "docs" / "release-process.md").read_text(encoding="utf-8")

    assert "package-smoke:" in workflow
    assert "uv run --extra dev python -m build" in workflow
    assert "uv run --extra dev twine check dist/*" in workflow
    assert "uv run ruff format --check ." in workflow
    assert "python -m venv .pkg-smoke" in workflow
    assert "python -m pip install dist/*.whl" in workflow
    assert "patchrail doctor --format json" in workflow

    assert "python -m pip install dist/*.whl" in release_process
    assert "patchrail ci explain --log examples/ci-triage/dependency-failure.log" in release_process
