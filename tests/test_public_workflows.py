from __future__ import annotations

import json
import subprocess
import sys
import tempfile
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
    pilot_guide = (ROOT / "docs" / "pilot-guide.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    quickstart = (ROOT / "docs" / "quickstart.md").read_text(encoding="utf-8")

    assert "docs/codex-workflows.md" in readme
    assert "docs/openai-codex-for-oss-evidence.md" in readme
    assert "docs/api-reference.md" in readme
    assert "docs/pilot-guide.md" in readme
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
    assert "patchrail schema queue-work-item" in api_reference
    assert "schemas/queue_work_item.schema.json" in api_reference
    assert "consent-only" in pilot_guide
    assert "does not give PatchRail write access" in pilot_guide
    assert "patchrail redact --log failed-ci.log" in pilot_guide
    assert "patchrail ci classify --log failed-ci.redacted.log --format json" in pilot_guide
    assert "patchrail queue --db patchrail-pilot.sqlite add --from-ci-result" in pilot_guide
    assert "Do not share raw logs that contain secrets or personal data" in pilot_guide


def test_local_agent_queue_demo_runs_end_to_end_with_stable_summary() -> None:
    expected = json.loads(
        (ROOT / "examples" / "local-agent-queue" / "demo-summary.expected.json").read_text(
            encoding="utf-8"
        )
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        proc = subprocess.run(
            [
                sys.executable,
                "examples/local-agent-queue/run_demo.py",
                "--output",
                tmpdir,
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        assert proc.returncode == 0, proc.stderr
        summary = json.loads((Path(tmpdir) / "summary.json").read_text(encoding="utf-8"))
        assert summary == expected

        for artifact in expected["artifact_files"]:
            assert (Path(tmpdir) / artifact).exists()

        report = (Path(tmpdir) / "ci-report.md").read_text(encoding="utf-8")
        item = json.loads((Path(tmpdir) / "approved.json").read_text(encoding="utf-8"))
        proposal = json.loads((Path(tmpdir) / "proposal-approved.json").read_text(encoding="utf-8"))
        events = [
            json.loads(line)
            for line in (Path(tmpdir) / "audit-events.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]

        assert "PatchRail classified this log locally" in report
        assert "did not create a pull request" in report
        assert item["write_actions_allowed"] is False
        assert item["payload"]["markdown_report"] == "ci-report.md"
        assert item["payload"]["ci_result"]["requirements"]["external_model_required"] is False
        assert proposal["approval_state"] == "approved"
        assert [event["event_type"] for event in events] == expected["audit_event_types"]


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
    release_evidence = (ROOT / "docs" / "release-v0.1.0-evidence.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    oss_evidence = (ROOT / "docs" / "openai-codex-for-oss-evidence.md").read_text(encoding="utf-8")

    assert "package-smoke:" in workflow
    assert "uv run --extra dev python -m build" in workflow
    assert "uv run --extra dev twine check dist/*" in workflow
    assert "uv run ruff format --check ." in workflow
    assert "python -m venv .pkg-smoke" in workflow
    assert "python -m pip install dist/*.whl" in workflow
    assert "patchrail doctor --format json" in workflow

    assert "python -m pip install dist/*.whl" in release_process
    assert "patchrail ci explain --log examples/ci-triage/dependency-failure.log" in release_process
    assert "release-v0.1.0-evidence.md" in release_process
    assert "docs/release-v0.1.0-evidence.md" in readme
    assert "release-v0.1.0-evidence.md" in oss_evidence

    assert "dist/patchrail-0.1.0.tar.gz" in release_evidence
    assert "dist/patchrail-0.1.0-py3-none-any.whl" in release_evidence
    assert "Tests: 32 passed." in release_evidence
    assert "Benchmark: 101 total, 101 passed, 0 failed." in release_evidence
    assert "manual maintainer gate" in release_evidence
    assert "create or push a `v0.1.0` tag" in release_evidence
    assert "publish the package to PyPI" in release_evidence
    assert "no automatic pull requests" in release_evidence
