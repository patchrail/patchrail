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
    assert "JavaScript Action Runtime Review" in docs
    assert "Reviewed on 2026-06-03" in docs
    assert "actions/checkout" in docs
    assert "`v6` | `node24` | No" in docs
    assert "actions/setup-python" in docs
    assert "astral-sh/setup-uv" in docs
    assert "`v8.1.0` | `node24` | No" in docs
    assert "FORCE_JAVASCRIPT_ACTIONS_TO_NODE24" in docs
    assert "read-only" in docs


def test_github_actions_runtime_review_keeps_workflows_node24_ready() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    triage = (ROOT / ".github" / "workflows" / "ci-triage.yml").read_text(encoding="utf-8")
    docs = (ROOT / "docs" / "github-action.md").read_text(encoding="utf-8")

    combined = "\n".join([ci, triage])
    assert 'FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"' in ci
    assert 'FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"' in triage
    assert "actions/checkout@v6" in combined
    assert "actions/setup-python@v6" in combined
    assert "astral-sh/setup-uv@v8.1.0" in combined
    assert "actions/download-artifact@v4" in triage
    assert "actions/upload-artifact@v4" in triage

    assert "contents: read" in triage
    assert "actions: read" in triage
    assert "issues: write" not in triage
    assert "pull-requests: write" not in triage
    assert "gh pr create" not in combined
    assert "gh issue comment" not in combined

    assert "`actions/checkout` | `v6` | `node24` | No" in docs
    assert "`actions/setup-python` | `v6` | `node24` | No" in docs
    assert "`astral-sh/setup-uv` | `v8.1.0` | `node24` | No" in docs
    assert "`actions/download-artifact` | `v4` | `node20` | No change" in docs
    assert "`actions/upload-artifact` | `v4` | `node20` | No change" in docs


def test_github_action_artifact_example_is_report_only_and_sanitized() -> None:
    artifact_dir = ROOT / "examples" / "github-action" / "patchrail-ci-triage-artifact"
    readme = (ROOT / "examples" / "github-action" / "README.md").read_text(encoding="utf-8")
    report = (artifact_dir / "ci-report.md").read_text(encoding="utf-8")
    benchmark_summary = (artifact_dir / "fixture-benchmark-summary.md").read_text(encoding="utf-8")
    result = json.loads((artifact_dir / "ci-result.json").read_text(encoding="utf-8"))
    benchmark = json.loads((artifact_dir / "fixture-benchmark.json").read_text(encoding="utf-8"))
    doctor = json.loads((artifact_dir / "doctor.json").read_text(encoding="utf-8"))

    assert "patchrail-ci-triage" in readme
    assert "does not comment on issues or pull requests" in readme
    assert "does not open pull requests" in readme
    assert "does not call external models" in readme
    assert "Copy The Workflow" in readme
    assert "permissions:" in readme
    assert "contents: read" in readme
    assert "actions: read" in readme
    assert 'gh workflow run "PatchRail CI Triage"' in readme
    assert "gh run download" in readme
    assert "--name patchrail-ci-triage" in readme
    assert "Artifact Contents" in readme
    assert "`ci-report.md`: Markdown summary for maintainers" in readme
    assert "`ci-result.json`: structured classifier output" in readme
    assert "`fixture-benchmark.json`: benchmark result" in readme
    assert "`fixture-benchmark-summary.md`: short Markdown benchmark summary" in readme
    assert "`doctor.json`: local safety check" in readme
    assert "Do not paste raw CI logs, secrets, private paths" in readme

    assert "PatchRail classified this log locally" in report
    assert "did not create a pull request" in report
    assert "# PatchRail CI Benchmark" in benchmark_summary
    assert "- Total cases: `115`" in benchmark_summary
    assert "## Class summary" in benchmark_summary
    assert "## Cases" not in benchmark_summary
    assert result["failure_class"] == "python_dependency_resolution"
    assert result["requirements"]["billing_required"] is False
    assert result["requirements"]["external_model_required"] is False
    assert benchmark["total_cases"] == 115
    assert benchmark["failed"] == 0
    assert benchmark["accuracy"]["top_1"] == 1.0
    assert benchmark["class_summary"]["python_dependency_resolution"]["total_cases"] == 27
    assert benchmark["class_summary"]["node_dependency_install"]["total_cases"] == 19
    assert benchmark["class_summary"]["typescript_typecheck"]["total_cases"] == 19
    assert doctor["status"] == "ok"
    assert doctor["requirements"]["github_write_permission_required"] is False

    serialized = "\n".join(
        [
            readme,
            report,
            benchmark_summary,
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
    oss_program_evidence = (ROOT / "docs" / "oss-program-evidence.md").read_text(encoding="utf-8")
    api_reference = (ROOT / "docs" / "api-reference.md").read_text(encoding="utf-8")
    pilot_guide = (ROOT / "docs" / "pilot-guide.md").read_text(encoding="utf-8")
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    threat_model = (ROOT / "docs" / "threat-model.md").read_text(encoding="utf-8")
    metrics = (ROOT / "docs" / "metrics.md").read_text(encoding="utf-8")
    adopters = (ROOT / "ADOPTERS.md").read_text(encoding="utf-8")
    adopter_report = (ROOT / ".github" / "ISSUE_TEMPLATE" / "adopter_report.md").read_text(
        encoding="utf-8"
    )
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    quickstart = (ROOT / "docs" / "quickstart.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "docs" / "roadmap.md").read_text(encoding="utf-8")
    release_v02 = (ROOT / "docs" / "release-v0.2.0-evidence.md").read_text(encoding="utf-8")
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    skill_dir = ROOT / ".agents" / "skills"
    ci_skill = (skill_dir / "patchrail-ci-triage" / "SKILL.md").read_text(encoding="utf-8")
    release_skill = (skill_dir / "patchrail-release-captain" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    guardrails_skill = (skill_dir / "patchrail-review-guardrails" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "docs/codex-workflows.md" in readme
    assert "docs/openai-codex-for-oss-evidence.md" in readme
    assert "docs/api-reference.md" in readme
    assert "docs/pilot-guide.md" in readme
    assert "docs/metrics.md" in readme
    assert "patchrail ci pilot-pack --log failed.log --out-dir patchrail-pilot-pack" in readme
    assert "ADOPTERS.md" in readme
    assert ".github/ISSUE_TEMPLATE/ci_failure_fixture.md" in readme
    assert ".agents/skills" in readme
    assert "pipx install patchrail" in readme
    assert "pipx install patchrail" in quickstart
    assert "patchrail ci explain --log failed-github-actions.log" in quickstart
    assert "patchrail ci pilot-pack --log failed-github-actions.log" in quickstart
    assert "The v0.1 release does not require Codex or any external model" in codex_workflows
    assert "no automatic pull requests" in codex_workflows
    assert "patchrail-ci-triage" in codex_workflows
    assert "patchrail-release-captain" in codex_workflows
    assert "patchrail-review-guardrails" in codex_workflows
    assert "Human approval gates for write actions" in evidence
    assert "No automatic bounty claiming" in evidence
    assert ".agents/skills/patchrail-ci-triage" in evidence
    assert "Public CI fixtures: 115 sanitized synthetic fixtures" in oss_program_evidence
    assert "https://github.com/patchrail/patchrail/issues/27" in oss_program_evidence
    assert "https://github.com/patchrail/patchrail/issues/37" in oss_program_evidence
    assert "https://github.com/patchrail/patchrail/issues/1>" not in oss_program_evidence
    assert "https://github.com/patchrail/patchrail/issues/27" in evidence
    assert "https://github.com/patchrail/patchrail/issues/37" in evidence
    assert "https://github.com/patchrail/patchrail/issues/1>" not in evidence
    assert (
        "Fixture hygiene gate: `patchrail ci fixture-check examples/ci-triage --format json`"
        in oss_program_evidence
    )
    assert "Tests: `uv run --extra dev pytest -q` -> 46 passed." in oss_program_evidence
    assert (
        "Fixture hygiene: `uv run --extra dev patchrail ci fixture-check "
        "examples/ci-triage --format json` -> 115 / 115 fixtures passed."
    ) in oss_program_evidence
    assert "GitHub Release: <https://github.com/patchrail/patchrail/releases/tag/v0.1.0>" in (
        oss_program_evidence
    )
    assert "Agent Control Plane demo" in oss_program_evidence
    assert "Pilot pack importer: `patchrail queue add --from-pilot-pack patchrail-pilot-pack`" in (
        oss_program_evidence
    )
    assert "validates `pilot-manifest.json`, confirms the raw log was not copied" in (
        oss_program_evidence
    )
    assert "Local queue API: `patchrail serve --host 127.0.0.1 --port 8765`" in (
        oss_program_evidence
    )
    assert "Funded issue read-only demo" in oss_program_evidence
    assert "External repositories using PatchRail: pending pilots" in oss_program_evidence
    assert "PyPI release link after package index publish" in oss_program_evidence
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
    assert "patchrail queue --db patchrail-pilot.sqlite add --from-pilot-pack" in pilot_guide
    assert "The importer validates that the manifest did not copy the raw log" in pilot_guide
    assert "patchrail ci pilot-pack --log failed-ci.log --out-dir patchrail-pilot-pack" in (
        pilot_guide
    )
    assert "It does not copy the raw log into the output directory" in pilot_guide
    assert "## Pilot pack boundary" in security
    assert "schema_version=patchrail.ci_pilot_pack.v1" in security
    assert "source.raw_log_copied=false" in security
    assert "creates a pending work item with `write_actions_allowed=false`" in security
    assert "## Pilot pack trust boundary" in threat_model
    assert "`patchrail queue add --from-pilot-pack` accepts either the pack directory" in (
        threat_model
    )
    assert "rejects manifests where" in threat_model
    assert "`source.raw_log_copied` is not `false`" in threat_model
    assert "Queue approval remains local" in threat_model
    assert "pilot-manifest.json" in pilot_guide
    assert "patchrail ci pilot-pack" in roadmap
    assert "patchrail ci pilot-pack" in release_v02
    assert "local redacted bundle generated without copying the raw log" in release_v02
    assert "Pilot pack command: `patchrail ci pilot-pack`" in evidence
    assert "Pilot pack queue importer: `patchrail queue add --from-pilot-pack`" in evidence
    assert "no raw log copy" in evidence
    assert "Do not share raw logs that contain secrets or personal data" in pilot_guide
    assert "Sanitized fixture contribution path" in contributing
    assert "patchrail redact --log failed-ci.log > failed-ci.redacted.log" in contributing
    assert "patchrail ci fixture-check examples/ci-triage --format json" in contributing
    assert "patchrail ci benchmark examples/ci-triage --format json" in contributing
    assert "Do not commit it" in contributing
    assert "the fixture is synthetic" in contributing
    assert "PatchRail tracks adoption and quality metrics" in metrics
    assert "Monthly PyPI downloads" in metrics
    assert "Pending first PyPI release" in metrics
    assert "Public external adopters | 0" in metrics
    assert "Public releases | 1" in metrics
    assert "Fixture hygiene gate | 115 / 115 passing" in metrics
    assert "Do not use placeholders as evidence" in metrics
    assert "public PRs reviewed with Codex" in metrics
    assert "only with explicit maintainer permission" in adopters
    assert "There are no public external adopters listed yet" in adopters
    assert "Use `patchrail redact`" in adopters
    assert "Adopter or pilot report" in adopter_report
    assert "I maintain this repository or have permission" in adopter_report
    assert "PatchRail may list the repository in `ADOPTERS.md`" in adopter_report
    assert "Use `patchrail redact`" in adopter_report
    assert "Do not quote raw logs that may contain secrets" in ci_skill
    assert "uv run --extra dev patchrail ci benchmark examples/ci-triage --format json" in ci_skill
    assert "Do not publish to PyPI without an explicit maintainer release request" in release_skill
    assert "uv run --extra dev twine check dist/*" in release_skill
    assert "automatic bounty or funded-issue claiming" in guardrails_skill
    assert "GitHub write actions without dry-run and human approval" in guardrails_skill


def test_release_evidence_pages_cover_v01_to_v04_without_publish_actions() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    release_process = (ROOT / "docs" / "release-process.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "docs" / "roadmap.md").read_text(encoding="utf-8")
    oss_evidence = (ROOT / "docs" / "openai-codex-for-oss-evidence.md").read_text(encoding="utf-8")

    for version in ("v0.1.0", "v0.2.0", "v0.3.0", "v0.4.0"):
        path = ROOT / "docs" / f"release-{version}-evidence.md"
        doc = path.read_text(encoding="utf-8")

        assert f"docs/release-{version}-evidence.md" in readme
        assert f"release-{version}-evidence.md" in release_process
        assert f"release-{version}-evidence.md" in oss_evidence
        assert "PyPI" in doc
        assert "external applications" in doc or "external program" in doc

    v01 = (ROOT / "docs" / "release-v0.1.0-evidence.md").read_text(encoding="utf-8")
    assert "Published release:" in v01
    assert "Manual Gates Remaining" in v01
    assert "publish the package to PyPI when package index credentials are available" in v01
    assert "announce the release publicly" in v01
    assert "submit the Codex for Open Source application" in v01

    for version in ("v0.2.0", "v0.3.0", "v0.4.0"):
        doc = (ROOT / "docs" / f"release-{version}-evidence.md").read_text(encoding="utf-8")
        assert "Status:" in doc
        assert "not a published release" in doc
        assert "Manual Gates Before Publishing" in doc
        assert "Publish to PyPI only when the maintainer has configured the credential" in doc
        assert "Announce or request external program review only with real, current metrics" in doc
        assert (
            ("contact third-party" in doc and "maintainers" in doc)
            or "external applications" in doc
            or "external program applications" in doc
        )

    v03 = (ROOT / "docs" / "release-v0.3.0-evidence.md").read_text(encoding="utf-8")
    v04 = (ROOT / "docs" / "release-v0.4.0-evidence.md").read_text(encoding="utf-8")

    assert "Agent Control Plane" in roadmap
    assert "v0.3.0 release-candidate evidence page" in roadmap
    assert "Funded Issue Scout read-only" in roadmap
    assert "v0.4.0 release-candidate evidence page" in roadmap

    assert "examples/local-agent-queue/run_demo.py" in v03
    assert "queue add --from-pilot-pack" in v03
    assert "patchrail schema queue-work-item" in v03
    assert "patchrail serve --host 127.0.0.1 --port 8765" in v03
    assert "Proposal approval/rejection records human decisions only" in release_process
    assert "No pull request creation" in v03
    assert "GitHub write permissions" in v03

    assert "examples/funded-issues-readonly/run_demo.py" in v04
    assert "patchrail funded-issues list" in v04
    assert "patchrail funded-issues import" in v04
    assert "No funded issue command fetches provider APIs" in release_process
    assert "automatic claims" in v04
    assert "money-only ranking" in v04


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

        report = (Path(tmpdir) / "pilot-pack" / "patchrail-report.md").read_text(encoding="utf-8")
        item = json.loads((Path(tmpdir) / "approved.json").read_text(encoding="utf-8"))
        rejected_item = json.loads(
            (Path(tmpdir) / "rejected-item.json").read_text(encoding="utf-8")
        )
        queue_before_decisions = json.loads(
            (Path(tmpdir) / "queue-before-decisions.json").read_text(encoding="utf-8")
        )
        proposal = json.loads((Path(tmpdir) / "proposal-approved.json").read_text(encoding="utf-8"))
        rejected_proposal = json.loads(
            (Path(tmpdir) / "proposal-rejected.json").read_text(encoding="utf-8")
        )
        rejected_proposal_markdown = (Path(tmpdir) / "proposal-rejected.md").read_text(
            encoding="utf-8"
        )
        events = [
            json.loads(line)
            for line in (Path(tmpdir) / "audit-events.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]

        assert "PatchRail classified this log locally" in report
        assert "did not create a pull request" in report
        assert item["write_actions_allowed"] is False
        assert item["payload"]["markdown_report"] == "pilot-pack/patchrail-report.md"
        assert item["payload"]["ci_result"]["requirements"]["external_model_required"] is False
        assert item["payload"]["pilot_pack"]["raw_log_copied"] is False
        assert item["payload"]["pilot_pack"]["maintainer_review_required_before_sharing"] is True
        assert rejected_item["approval_state"] == "rejected"
        assert rejected_item["write_actions_allowed"] is False
        assert len(queue_before_decisions["work_items"]) == 2
        assert proposal["approval_state"] == "approved"
        assert proposal["risk_level"] == "low"
        assert rejected_proposal["approval_state"] == "rejected"
        assert rejected_proposal["risk_level"] == "high"
        assert "Open a pull request immediately" in rejected_proposal_markdown
        assert "does not push commits" in rejected_proposal_markdown
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
    release_v02_evidence = (ROOT / "docs" / "release-v0.2.0-evidence.md").read_text(
        encoding="utf-8"
    )
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    oss_evidence = (ROOT / "docs" / "openai-codex-for-oss-evidence.md").read_text(encoding="utf-8")
    program_evidence = (ROOT / "docs" / "oss-program-evidence.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "docs" / "roadmap.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert "package-smoke:" in workflow
    assert "uv run --extra dev python -m build" in workflow
    assert "uv run --extra dev twine check dist/*" in workflow
    assert "uv run ruff format --check ." in workflow
    assert '"/.agents"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "python -m venv .pkg-smoke" in workflow
    assert "python -m pip install dist/*.whl" in workflow
    assert "patchrail doctor --format json" in workflow
    assert '"/ADOPTERS.md"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "python -m pip install dist/*.whl" in release_process
    assert "patchrail ci explain --log examples/ci-triage/dependency-failure.log" in release_process
    assert "release-v0.1.0-evidence.md" in release_process
    assert "release-v0.2.0-evidence.md" in release_process
    assert "docs/release-v0.1.0-evidence.md" in readme
    assert "release-v0.1.0-evidence.md" in oss_evidence

    assert "dist/patchrail-0.1.0.tar.gz" in release_evidence
    assert "dist/patchrail-0.1.0-py3-none-any.whl" in release_evidence
    assert "Tests: 32 passed." in release_evidence
    assert "Tests: 34 passed." in release_evidence
    assert "Benchmark: 115 total, 115 passed, 0 failed." in release_evidence
    assert "https://github.com/patchrail/patchrail/pull/17" in release_evidence

    assert "Status: release candidate evidence, not a published release." in release_v02_evidence
    assert "uv run --extra dev patchrail ci fixture-check examples/ci-triage --format json" in (
        release_v02_evidence
    )
    assert "Fixture hygiene: 115 / 115 fixtures passed." in release_v02_evidence
    assert "Benchmark: 115 total, 115 passed, 0 failed." in release_v02_evidence
    assert "Top-1 fixture accuracy: 1.0." in release_v02_evidence
    assert "Class coverage: 8 root-cause families." in release_v02_evidence
    assert "Bump `pyproject.toml` from `0.1.0` to `0.2.0`." in release_v02_evidence
    assert "Publish to PyPI only when the maintainer has configured the credential." in (
        release_v02_evidence
    )
    assert "External adoption evidence is still pending consent-only pilots." in (
        release_v02_evidence
    )
    assert "release-v0.2.0-evidence.md" in program_evidence
    assert "v0.2.0 release-candidate evidence page" in roadmap
    assert "## 0.2.0 - draft" in changelog
    assert "https://github.com/patchrail/patchrail/actions/runs/26869827161" in release_evidence
    assert "https://github.com/patchrail/patchrail/releases/tag/v0.1.0" in release_evidence
    assert "07b4934d91866c3ea2978c2aff265f923cd232bf" in release_evidence
    assert "5f1f91e36fce4197a6cf8405da2ac5bfcbb6cefa1cb393464349c868e9719dfd" in release_evidence
    assert "package-smoke" in release_evidence
    assert "manual maintainer gate" in release_evidence
    assert "publish the package to PyPI" in release_evidence
    assert "no automatic pull requests" in release_evidence
