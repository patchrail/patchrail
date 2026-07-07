from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from patchrail.cli import main


class PatchRailCITests(unittest.TestCase):
    def test_ci_adoption_event_reviews_workflow_signal_without_counting_adoption(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            event_path = Path(tmpdir) / "adoption-event.json"
            event_path.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.ci_triage_adoption_event.v1",
                        "product": "ci-triage-action",
                        "action_ref": "v1",
                        "action_repository": "patchrail/ci-triage-action",
                        "adoption_key": "ci-triage:action:ci-triage-action:python-lint",
                        "adoption_event_id": "ci-triage-run:buyer/repo:123:test:python-lint",
                        "failure_class": "python_lint",
                        "failure_slug": "python-lint",
                        "confidence": "0.88",
                        "redacted_categories": 2,
                        "artifact_name": "patchrail-ci-triage-python-lint",
                        "json_result": "ci-result.json",
                        "markdown_report": "ci-report.md",
                        "workflow_repository": "buyer/repo",
                        "workflow_run_id": "123",
                        "workflow_run_url": "https://github.com/buyer/repo/actions/runs/123",
                        "workflow_run_host": "github.com",
                        "workflow_name": "CI",
                        "workflow_job": "test",
                    }
                ),
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "ci",
                        "adoption-event",
                        "--event",
                        str(event_path),
                        "--format",
                        "json",
                    ]
                )

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["schema_version"], "patchrail.ci_triage_adoption_event_review.v1")
        self.assertEqual(payload["signal_kind"], "workflow_run")
        self.assertEqual(payload["workflow_repository"], "buyer/repo")
        self.assertEqual(payload["github_issue"], "patchrail/patchrail#69")
        self.assertTrue(payload["triage_artifacts_present"])
        self.assertTrue(payload["strict_evidence_ready_for_permission_request"])
        self.assertEqual(payload["missing_strict_evidence"], [])
        self.assertIn("explicit permission", payload["safe_next_step"])
        self.assertFalse(payload["counts_as_external_adoption"])
        self.assertIn("--require-workflow-context", payload["strict_verification_command"])
        self.assertIn("--require-triage-artifacts", payload["strict_verification_command"])
        self.assertIsNotNone(payload["permission_request_copy_brief"])
        copy_brief = payload["permission_request_copy_brief"]
        assert copy_brief is not None
        self.assertEqual(copy_brief["schema"], "copy_brief.external_permission_request.v1")
        self.assertEqual(copy_brief["prohibited_fields"], ["body", "draft", "email_body"])
        self.assertEqual(copy_brief["payload"]["type"], "external_permission_request")
        self.assertEqual(copy_brief["payload"]["lead"], "buyer/repo")
        self.assertFalse(copy_brief["payload"]["external_body_allowed"])
        self.assertFalse(copy_brief["payload"]["payment_route_allowed_now"])
        self.assertNotIn("body", copy_brief["payload"])
        self.assertNotIn("draft", copy_brief["payload"])
        self.assertNotIn("email_body", copy_brief["payload"])
        self.assertIn(
            "public_adoption_claim_without_maintainer_permission",
            payload["blocked_actions"],
        )

    def test_ci_adoption_event_writes_permission_copy_brief_without_external_body(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            event_path = Path(tmpdir) / "adoption-event.json"
            brief_path = Path(tmpdir) / "requests" / "permission.json"
            event_path.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.ci_triage_adoption_event.v1",
                        "product": "ci-triage-action",
                        "action_ref": "v1",
                        "action_repository": "patchrail/ci-triage-action",
                        "adoption_key": "ci-triage:action:ci-triage-action:python-lint",
                        "adoption_event_id": "ci-triage-run:buyer/repo:123:test:python-lint",
                        "failure_class": "python_lint",
                        "failure_slug": "python-lint",
                        "confidence": "0.88",
                        "json_result": "ci-result.json",
                        "markdown_report": "ci-report.md",
                        "workflow_repository": "buyer/repo",
                        "workflow_run_id": "123",
                        "workflow_run_url": "https://github.com/buyer/repo/actions/runs/123",
                    }
                ),
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "ci",
                        "adoption-event",
                        "--event",
                        str(event_path),
                        "--write-copy-brief",
                        str(brief_path),
                        "--format",
                        "json",
                    ]
                )
            copy_brief_payload = json.loads(brief_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["copy_brief_write"]["status"], "written")
        self.assertFalse(payload["copy_brief_write"]["prohibited_fields_present"])
        self.assertEqual(copy_brief_payload["type"], "external_permission_request")
        self.assertEqual(copy_brief_payload["channel"], "maintainer_permission")
        self.assertEqual(copy_brief_payload["lead"], "buyer/repo")
        self.assertIn(
            "https://github.com/buyer/repo/actions/runs/123", copy_brief_payload["key_facts"][2]
        )
        self.assertTrue(
            any(
                fact.startswith("Strict verification command: patchrail ci adoption-event ")
                for fact in copy_brief_payload["key_facts"]
            )
        )
        self.assertFalse(copy_brief_payload["external_body_allowed"])
        self.assertFalse(copy_brief_payload["payment_route_allowed_now"])
        self.assertNotIn("body", copy_brief_payload)
        self.assertNotIn("draft", copy_brief_payload)
        self.assertNotIn("email_body", copy_brief_payload)

    def test_ci_adoption_event_writes_permission_copy_brief_to_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            event_path = Path(tmpdir) / "adoption-event.json"
            requests_dir = Path(tmpdir) / "requests"
            event_path.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.ci_triage_adoption_event.v1",
                        "product": "ci-triage-action",
                        "action_ref": "v1",
                        "action_repository": "patchrail/ci-triage-action",
                        "adoption_key": "ci-triage:action:ci-triage-action:python-lint",
                        "adoption_event_id": "ci-triage-run:buyer/repo:123:test:python-lint",
                        "failure_class": "python_lint",
                        "failure_slug": "python-lint",
                        "confidence": "0.88",
                        "json_result": "ci-result.json",
                        "markdown_report": "ci-report.md",
                        "workflow_repository": "buyer/repo",
                        "workflow_run_id": "123",
                        "workflow_run_url": "https://github.com/buyer/repo/actions/runs/123",
                    }
                ),
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "ci",
                        "adoption-event",
                        "--event",
                        str(event_path),
                        "--write-copy-brief-dir",
                        str(requests_dir),
                        "--format",
                        "json",
                    ]
                )
            written_files = list(requests_dir.glob("*.json"))
            copy_brief_payload = json.loads(written_files[0].read_text(encoding="utf-8"))

            self.assertEqual(exit_code, 0)
            self.assertEqual(len(written_files), 1)
            self.assertRegex(
                written_files[0].name,
                r"^\d{8}T\d{6}Z-ci-triage-adoption-permission-buyer-repo-run-123\.json$",
            )
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["copy_brief_write"]["status"], "written")
            self.assertTrue(payload["copy_brief_write"]["auto_named"])
            self.assertEqual(payload["copy_brief_write"]["directory"], str(requests_dir))
            self.assertEqual(payload["copy_brief_write"]["path"], str(written_files[0]))
            self.assertEqual(copy_brief_payload["type"], "external_permission_request")
            self.assertNotIn("body", copy_brief_payload)
            self.assertNotIn("draft", copy_brief_payload)
            self.assertNotIn("email_body", copy_brief_payload)

    def test_ci_adoption_event_rejects_copy_brief_path_and_directory_together(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            event_path = Path(tmpdir) / "adoption-event.json"
            event_path.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.ci_triage_adoption_event.v1",
                        "product": "ci-triage-action",
                        "action_ref": "v1",
                        "action_repository": "patchrail/ci-triage-action",
                        "adoption_key": "ci-triage:action:ci-triage-action:python-lint",
                        "adoption_event_id": "ci-triage-run:buyer/repo:123:test:python-lint",
                        "failure_class": "python_lint",
                        "failure_slug": "python-lint",
                        "json_result": "ci-result.json",
                        "markdown_report": "ci-report.md",
                        "workflow_repository": "buyer/repo",
                        "workflow_run_id": "123",
                        "workflow_run_url": "https://github.com/buyer/repo/actions/runs/123",
                    }
                ),
                encoding="utf-8",
            )

            stderr = StringIO()
            with redirect_stderr(stderr):
                exit_code = main(
                    [
                        "ci",
                        "adoption-event",
                        "--event",
                        str(event_path),
                        "--write-copy-brief",
                        str(Path(tmpdir) / "permission.json"),
                        "--write-copy-brief-dir",
                        str(Path(tmpdir) / "requests"),
                    ]
                )

        self.assertEqual(exit_code, 2)
        self.assertIn("not both", stderr.getvalue())

    def test_ci_adoption_event_require_workflow_context_accepts_real_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            event_path = Path(tmpdir) / "adoption-event.json"
            event_path.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.ci_triage_adoption_event.v1",
                        "product": "ci-triage-action",
                        "action_ref": "v1",
                        "action_repository": "patchrail/ci-triage-action",
                        "adoption_key": "ci-triage:action:ci-triage-action:python-lint",
                        "adoption_event_id": "ci-triage-run:buyer/repo:123:test:python-lint",
                        "failure_class": "python_lint",
                        "failure_slug": "python-lint",
                        "workflow_repository": "buyer/repo",
                        "workflow_run_id": "123",
                        "workflow_run_url": "https://github.com/buyer/repo/actions/runs/123",
                    }
                ),
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "ci",
                        "adoption-event",
                        "--event",
                        str(event_path),
                        "--require-workflow-context",
                        "--format",
                        "json",
                    ]
                )

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["signal_kind"], "workflow_run")
        self.assertEqual(
            payload["workflow_run_url"], "https://github.com/buyer/repo/actions/runs/123"
        )

    def test_ci_adoption_event_rejects_mismatched_workflow_run_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            event_path = Path(tmpdir) / "adoption-event.json"
            event_path.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.ci_triage_adoption_event.v1",
                        "product": "ci-triage-action",
                        "action_ref": "v1",
                        "action_repository": "patchrail/ci-triage-action",
                        "adoption_key": "ci-triage:action:ci-triage-action:python-lint",
                        "adoption_event_id": "ci-triage-run:buyer/repo:123:test:python-lint",
                        "failure_class": "python_lint",
                        "failure_slug": "python-lint",
                        "workflow_repository": "buyer/repo",
                        "workflow_run_id": "123",
                        "workflow_run_url": "https://github.com/other/repo/actions/runs/999",
                    }
                ),
                encoding="utf-8",
            )

            stderr = StringIO()
            with redirect_stderr(stderr):
                exit_code = main(
                    [
                        "ci",
                        "adoption-event",
                        "--event",
                        str(event_path),
                        "--require-workflow-context",
                    ]
                )

        self.assertEqual(exit_code, 1)
        self.assertIn("workflow_run_url must match", stderr.getvalue())

    def test_ci_adoption_event_rejects_insecure_workflow_run_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            event_path = Path(tmpdir) / "adoption-event.json"
            event_path.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.ci_triage_adoption_event.v1",
                        "product": "ci-triage-action",
                        "action_ref": "v1",
                        "action_repository": "patchrail/ci-triage-action",
                        "adoption_key": "ci-triage:action:ci-triage-action:python-lint",
                        "adoption_event_id": "ci-triage-run:buyer/repo:123:test:python-lint",
                        "failure_class": "python_lint",
                        "failure_slug": "python-lint",
                        "workflow_repository": "buyer/repo",
                        "workflow_run_id": "123",
                        "workflow_run_url": "http://github.com/buyer/repo/actions/runs/123",
                    }
                ),
                encoding="utf-8",
            )

            stderr = StringIO()
            with redirect_stderr(stderr):
                exit_code = main(
                    [
                        "ci",
                        "adoption-event",
                        "--event",
                        str(event_path),
                        "--require-workflow-context",
                    ]
                )

        self.assertEqual(exit_code, 1)
        self.assertIn("workflow_run_url must match", stderr.getvalue())

    def test_ci_adoption_event_rejects_malformed_workflow_repository(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            event_path = Path(tmpdir) / "adoption-event.json"
            event_path.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.ci_triage_adoption_event.v1",
                        "product": "ci-triage-action",
                        "action_ref": "v1",
                        "action_repository": "patchrail/ci-triage-action",
                        "adoption_key": "ci-triage:action:ci-triage-action:python-lint",
                        "adoption_event_id": "ci-triage-run:buyer/repo/extra:123:test:python-lint",
                        "failure_class": "python_lint",
                        "failure_slug": "python-lint",
                        "workflow_repository": "buyer/repo/extra",
                        "workflow_run_id": "123",
                        "workflow_run_url": "https://github.com/buyer/repo/extra/actions/runs/123",
                    }
                ),
                encoding="utf-8",
            )

            stderr = StringIO()
            with redirect_stderr(stderr):
                exit_code = main(
                    [
                        "ci",
                        "adoption-event",
                        "--event",
                        str(event_path),
                        "--require-workflow-context",
                    ]
                )

        self.assertEqual(exit_code, 1)
        self.assertIn("workflow_repository must be an owner/repo pair", stderr.getvalue())

    def test_ci_adoption_event_rejects_non_numeric_workflow_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            event_path = Path(tmpdir) / "adoption-event.json"
            event_path.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.ci_triage_adoption_event.v1",
                        "product": "ci-triage-action",
                        "action_ref": "v1",
                        "action_repository": "patchrail/ci-triage-action",
                        "adoption_key": "ci-triage:action:ci-triage-action:python-lint",
                        "adoption_event_id": "ci-triage-run:buyer/repo:not-a-run:test:python-lint",
                        "failure_class": "python_lint",
                        "failure_slug": "python-lint",
                        "workflow_repository": "buyer/repo",
                        "workflow_run_id": "not-a-run",
                        "workflow_run_url": "https://github.com/buyer/repo/actions/runs/not-a-run",
                    }
                ),
                encoding="utf-8",
            )

            stderr = StringIO()
            with redirect_stderr(stderr):
                exit_code = main(
                    [
                        "ci",
                        "adoption-event",
                        "--event",
                        str(event_path),
                        "--require-workflow-context",
                    ]
                )

        self.assertEqual(exit_code, 1)
        self.assertIn("workflow_run_id must be numeric", stderr.getvalue())

    def test_ci_adoption_event_rejects_mismatched_workflow_run_host(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            event_path = Path(tmpdir) / "adoption-event.json"
            event_path.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.ci_triage_adoption_event.v1",
                        "product": "ci-triage-action",
                        "action_ref": "v1",
                        "action_repository": "patchrail/ci-triage-action",
                        "adoption_key": "ci-triage:action:ci-triage-action:python-lint",
                        "adoption_event_id": "ci-triage-run:buyer/repo:123:test:python-lint",
                        "failure_class": "python_lint",
                        "failure_slug": "python-lint",
                        "workflow_repository": "buyer/repo",
                        "workflow_run_id": "123",
                        "workflow_run_url": (
                            "https://github.enterprise.test/buyer/repo/actions/runs/123"
                        ),
                        "workflow_run_host": "github.com",
                    }
                ),
                encoding="utf-8",
            )

            stderr = StringIO()
            with redirect_stderr(stderr):
                exit_code = main(
                    [
                        "ci",
                        "adoption-event",
                        "--event",
                        str(event_path),
                        "--require-workflow-context",
                    ]
                )

        self.assertEqual(exit_code, 1)
        self.assertIn("workflow_run_host must match", stderr.getvalue())

    def test_ci_adoption_event_require_canonical_action_rejects_fork(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            event_path = Path(tmpdir) / "adoption-event.json"
            event_path.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.ci_triage_adoption_event.v1",
                        "product": "ci-triage-action",
                        "action_ref": "v1",
                        "action_repository": "buyer/ci-triage-action-fork",
                        "adoption_key": "ci-triage:action:ci-triage-action:python-lint",
                        "adoption_event_id": "ci-triage-run:buyer/repo:123:test:python-lint",
                        "failure_class": "python_lint",
                        "failure_slug": "python-lint",
                        "workflow_repository": "buyer/repo",
                        "workflow_run_id": "123",
                        "workflow_run_url": "https://github.com/buyer/repo/actions/runs/123",
                    }
                ),
                encoding="utf-8",
            )

            stderr = StringIO()
            with redirect_stderr(stderr):
                exit_code = main(
                    [
                        "ci",
                        "adoption-event",
                        "--event",
                        str(event_path),
                        "--require-workflow-context",
                        "--require-canonical-action",
                    ]
                )

        self.assertEqual(exit_code, 1)
        self.assertIn("--require-canonical-action", stderr.getvalue())

    def test_ci_adoption_event_require_published_action_ref_accepts_v1(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            event_path = Path(tmpdir) / "adoption-event.json"
            event_path.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.ci_triage_adoption_event.v1",
                        "product": "ci-triage-action",
                        "action_ref": "v1",
                        "action_repository": "patchrail/ci-triage-action",
                        "adoption_key": "ci-triage:action:ci-triage-action:python-lint",
                        "adoption_event_id": "ci-triage-run:buyer/repo:123:test:python-lint",
                        "failure_class": "python_lint",
                        "failure_slug": "python-lint",
                        "workflow_repository": "buyer/repo",
                        "workflow_run_id": "123",
                        "workflow_run_url": "https://github.com/buyer/repo/actions/runs/123",
                    }
                ),
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "ci",
                        "adoption-event",
                        "--event",
                        str(event_path),
                        "--require-workflow-context",
                        "--require-canonical-action",
                        "--require-published-action-ref",
                        "--require-external-workflow-repository",
                        "--format",
                        "json",
                    ]
                )

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["action_ref"], "v1")
        self.assertTrue(payload["published_action_ref_match"])
        self.assertTrue(payload["public_github_run_match"])
        self.assertEqual(payload["workflow_repository_owner"], "buyer")
        self.assertTrue(payload["external_workflow_repository_match"])
        self.assertFalse(payload["strict_evidence_ready_for_permission_request"])
        self.assertEqual(payload["missing_strict_evidence"], ["triage_artifacts"])

    def test_ci_adoption_event_require_public_github_run_rejects_enterprise_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            event_path = Path(tmpdir) / "adoption-event.json"
            event_path.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.ci_triage_adoption_event.v1",
                        "product": "ci-triage-action",
                        "action_ref": "v1",
                        "action_repository": "patchrail/ci-triage-action",
                        "adoption_key": "ci-triage:action:ci-triage-action:python-lint",
                        "adoption_event_id": "ci-triage-run:buyer/repo:123:test:python-lint",
                        "failure_class": "python_lint",
                        "failure_slug": "python-lint",
                        "workflow_repository": "buyer/repo",
                        "workflow_run_id": "123",
                        "workflow_run_url": (
                            "https://github.enterprise.test/buyer/repo/actions/runs/123"
                        ),
                    }
                ),
                encoding="utf-8",
            )

            stderr = StringIO()
            with redirect_stderr(stderr):
                exit_code = main(
                    [
                        "ci",
                        "adoption-event",
                        "--event",
                        str(event_path),
                        "--require-workflow-context",
                        "--require-canonical-action",
                        "--require-published-action-ref",
                        "--require-public-github-run",
                    ]
                )

        self.assertEqual(exit_code, 1)
        self.assertIn("--require-public-github-run", stderr.getvalue())

    def test_ci_adoption_event_require_external_repository_rejects_patchrail_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            event_path = Path(tmpdir) / "adoption-event.json"
            event_path.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.ci_triage_adoption_event.v1",
                        "product": "ci-triage-action",
                        "action_ref": "v1",
                        "action_repository": "patchrail/ci-triage-action",
                        "adoption_key": "ci-triage:action:ci-triage-action:python-lint",
                        "adoption_event_id": (
                            "ci-triage-run:patchrail/patchrail:123:test:python-lint"
                        ),
                        "failure_class": "python_lint",
                        "failure_slug": "python-lint",
                        "json_result": "ci-result.json",
                        "markdown_report": "ci-report.md",
                        "workflow_repository": "patchrail/patchrail",
                        "workflow_run_id": "123",
                        "workflow_run_url": (
                            "https://github.com/patchrail/patchrail/actions/runs/123"
                        ),
                    }
                ),
                encoding="utf-8",
            )

            stderr = StringIO()
            with redirect_stderr(stderr):
                exit_code = main(
                    [
                        "ci",
                        "adoption-event",
                        "--event",
                        str(event_path),
                        "--require-workflow-context",
                        "--require-canonical-action",
                        "--require-published-action-ref",
                        "--require-public-github-run",
                        "--require-external-workflow-repository",
                        "--require-triage-artifacts",
                    ]
                )

        self.assertEqual(exit_code, 1)
        self.assertIn("--require-external-workflow-repository", stderr.getvalue())

    def test_ci_adoption_event_require_triage_artifacts_rejects_missing_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            event_path = Path(tmpdir) / "adoption-event.json"
            event_path.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.ci_triage_adoption_event.v1",
                        "product": "ci-triage-action",
                        "action_ref": "v1",
                        "action_repository": "patchrail/ci-triage-action",
                        "adoption_key": "ci-triage:action:ci-triage-action:python-lint",
                        "adoption_event_id": "ci-triage-run:buyer/repo:123:test:python-lint",
                        "failure_class": "python_lint",
                        "failure_slug": "python-lint",
                        "workflow_repository": "buyer/repo",
                        "workflow_run_id": "123",
                        "workflow_run_url": "https://github.com/buyer/repo/actions/runs/123",
                    }
                ),
                encoding="utf-8",
            )

            stderr = StringIO()
            with redirect_stderr(stderr):
                exit_code = main(
                    [
                        "ci",
                        "adoption-event",
                        "--event",
                        str(event_path),
                        "--require-workflow-context",
                        "--require-canonical-action",
                        "--require-published-action-ref",
                        "--require-public-github-run",
                        "--require-triage-artifacts",
                    ]
                )

        self.assertEqual(exit_code, 1)
        self.assertIn("--require-triage-artifacts", stderr.getvalue())

    def test_ci_adoption_event_require_published_action_ref_rejects_local(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            event_path = Path(tmpdir) / "adoption-event.json"
            event_path.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.ci_triage_adoption_event.v1",
                        "product": "ci-triage-action",
                        "action_ref": "local",
                        "action_repository": "patchrail/ci-triage-action",
                        "adoption_key": "ci-triage:action:ci-triage-action:python-lint",
                        "adoption_event_id": "ci-triage-run:buyer/repo:123:test:python-lint",
                        "failure_class": "python_lint",
                        "failure_slug": "python-lint",
                        "workflow_repository": "buyer/repo",
                        "workflow_run_id": "123",
                        "workflow_run_url": "https://github.com/buyer/repo/actions/runs/123",
                    }
                ),
                encoding="utf-8",
            )

            stderr = StringIO()
            with redirect_stderr(stderr):
                exit_code = main(
                    [
                        "ci",
                        "adoption-event",
                        "--event",
                        str(event_path),
                        "--require-workflow-context",
                        "--require-canonical-action",
                        "--require-published-action-ref",
                    ]
                )

        self.assertEqual(exit_code, 1)
        self.assertIn("--require-published-action-ref", stderr.getvalue())

    def test_ci_adoption_event_marks_local_signal_as_non_adoption(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            event_path = Path(tmpdir) / "adoption-event.json"
            event_path.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.ci_triage_adoption_event.v1",
                        "product": "ci-triage-action",
                        "action_ref": "local",
                        "action_repository": "patchrail/ci-triage-action",
                        "adoption_key": "ci-triage:cli:index:pre-commit-hook-failure",
                        "adoption_event_id": "ci-triage:cli:index:pre-commit-hook-failure",
                        "failure_class": "pre_commit_hook_failure",
                        "failure_slug": "pre-commit-hook-failure",
                    }
                ),
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "ci",
                        "adoption-event",
                        "--event",
                        str(event_path),
                        "--format",
                        "markdown",
                    ]
                )

        self.assertEqual(exit_code, 0)
        markdown = stdout.getvalue()
        self.assertIn("- Signal: `local_or_sample_signal`", markdown)
        self.assertIn("- Counts as external adoption: `False`", markdown)
        self.assertIn("- Strict evidence ready for permission request: `False`", markdown)
        self.assertIn("- `workflow_context`", markdown)
        self.assertIn("Use this as local action smoke evidence only", markdown)

    def test_ci_adoption_event_require_workflow_context_rejects_local_signal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            event_path = Path(tmpdir) / "adoption-event.json"
            event_path.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.ci_triage_adoption_event.v1",
                        "product": "ci-triage-action",
                        "action_ref": "local",
                        "action_repository": "patchrail/ci-triage-action",
                        "adoption_key": "ci-triage:cli:index:pre-commit-hook-failure",
                        "adoption_event_id": "ci-triage:cli:index:pre-commit-hook-failure",
                        "failure_class": "pre_commit_hook_failure",
                        "failure_slug": "pre-commit-hook-failure",
                    }
                ),
                encoding="utf-8",
            )

            stderr = StringIO()
            with redirect_stderr(stderr):
                exit_code = main(
                    [
                        "ci",
                        "adoption-event",
                        "--event",
                        str(event_path),
                        "--require-workflow-context",
                    ]
                )

        self.assertEqual(exit_code, 1)
        self.assertIn("--require-workflow-context", stderr.getvalue())

    def test_ci_classify_emits_json_without_external_requirements(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "failed.log"
            log.write_text(
                "python -m pytest -q\nFAILED tests/test_app.py::test_ok - AssertionError\n",
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["ci", "classify", "--log", str(log)])

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["schema_version"], "patchrail.ci_result.v1")
            self.assertEqual(payload["failure_class"], "python_test_failure")
            self.assertEqual(payload["requirements"]["billing_required"], False)
            self.assertEqual(payload["requirements"]["external_model_required"], False)
            self.assertIn("pytest", payload["reproduction_command"])

    def test_ci_classify_detects_runner_memory_exhaustion(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "failed.log"
            log.write_text(
                "Run pytest -q\n"
                "collected 412 items\n"
                "##[error]The operation was canceled.\n"
                "Process completed with exit code 137.\n"
                "Container app was OOMKilled (exceeded memory limit).\n",
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["ci", "classify", "--log", str(log)])

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["failure_class"], "runner_resource_exhaustion")
            self.assertEqual(payload["requirements"]["external_model_required"], False)
            self.assertIn("memory", payload["minimal_repair_strategy"])

    def test_ci_classify_detects_runner_disk_exhaustion(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "failed.log"
            log.write_text(
                "npm error code ENOSPC\n"
                "npm error syscall write\n"
                "npm error errno -28\n"
                "npm error nospc ENOSPC: No space left on device, write\n",
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["ci", "classify", "--log", str(log)])

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["failure_class"], "runner_resource_exhaustion")
            self.assertIn("disk", payload["minimal_repair_strategy"])

    def test_ci_classify_detects_dns_network_transient_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "failed.log"
            log.write_text(
                "Run python -m pip install -r requirements.txt\n"
                "WARNING: Retrying after connection broken by 'NewConnectionError'\n"
                "Could not resolve host: pypi.org\n"
                "Temporary failure in name resolution\n",
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["ci", "classify", "--log", str(log)])

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["failure_class"], "network_transient_failure")
            self.assertIn("retry", payload["minimal_repair_strategy"])
            self.assertEqual(payload["requirements"]["external_model_required"], False)

    def test_ci_classify_transient_registry_outage_wins_over_install_signal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "failed.log"
            log.write_text(
                "npm ERR! code E503\n"
                "npm ERR! 503 Service Unavailable - GET https://registry.npmjs.org/react\n"
                "npm ERR! Connection reset by peer\n",
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["ci", "classify", "--log", str(log)])

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["failure_class"], "network_transient_failure")

    def test_ci_classify_detects_git_network_transient_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "failed.log"
            log.write_text(
                "Run actions/checkout@v4\n"
                "fatal: unable to access 'https://github.com/org/repo/': "
                "Failed to connect to github.com port 443: Connection timed out\n"
                "The remote end hung up unexpectedly\n",
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["ci", "classify", "--log", str(log)])

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["failure_class"], "network_transient_failure")
            self.assertIn("re-run", payload["reproduction_command"])

    def test_ci_classify_detects_github_actions_job_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "failed.log"
            log.write_text(
                "Run python -m pytest -q\n"
                "The job running on runner GitHub Actions 12 has exceeded "
                "the maximum execution time of 360 minutes.\n"
                "##[error]The operation was canceled.\n",
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["ci", "classify", "--log", str(log)])

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["failure_class"], "ci_job_timeout")
            self.assertIn("time limit", payload["reproduction_command"])
            self.assertEqual(payload["requirements"]["external_model_required"], False)

    def test_ci_classify_detects_gitlab_job_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "failed.log"
            log.write_text(
                "Running with gitlab-runner 17.4.0\n"
                "ERROR: Job failed: execution took longer than 1h0m0s seconds\n",
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["ci", "classify", "--log", str(log)])

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["failure_class"], "ci_job_timeout")

    def test_ci_classify_circleci_no_output_timeout_wins_over_network_signal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "failed.log"
            log.write_text(
                "Too long with no output (exceeded 10m0s): context deadline exceeded\n",
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["ci", "classify", "--log", str(log)])

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["failure_class"], "ci_job_timeout")

    def test_ci_classify_job_timeout_wins_over_passing_pytest_signal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "failed.log"
            log.write_text(
                "python -m pytest -q\n"
                "tests/test_app.py ........................                [ 64%]\n"
                "The job running on runner ubuntu-latest-8core has exceeded "
                "the maximum execution time of 90 minutes.\n"
                "##[error]The operation was canceled.\n",
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["ci", "classify", "--log", str(log)])

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["failure_class"], "ci_job_timeout")

    def test_ci_classify_detects_pytest_coverage_threshold_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "failed.log"
            log.write_text(
                "Run pytest --cov=src --cov-fail-under=90\n"
                "======================== 412 passed in 18.44s ========================\n"
                "Required test coverage of 90% not reached. Total coverage: 86.71%\n",
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["ci", "classify", "--log", str(log)])

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["failure_class"], "code_coverage_threshold")
            self.assertIn("coverage", payload["minimal_repair_strategy"])
            self.assertEqual(payload["requirements"]["external_model_required"], False)

    def test_ci_classify_coverage_gate_wins_over_passing_pytest_signal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "failed.log"
            log.write_text(
                "coverage report --fail-under=85\n"
                "Coverage failure: total of 82 is less than fail-under=85\n",
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["ci", "classify", "--log", str(log)])

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["failure_class"], "code_coverage_threshold")

    def test_ci_classify_detects_jest_coverage_threshold_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "failed.log"
            log.write_text(
                'Jest: "global" coverage threshold for statements (90%) not met: 84.21%\n'
                "Jest: Coverage for lines (88%) does not meet global threshold (90%)\n",
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["ci", "classify", "--log", str(log)])

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["failure_class"], "code_coverage_threshold")

    def test_ci_classify_detects_mypy_type_check_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "failed.log"
            log.write_text(
                "Run mypy src\n"
                'src/app.py:42: error: Incompatible return value type (got "int", '
                'expected "str")  [return-value]\n'
                'src/app.py:88: error: Argument 1 to "run" has incompatible type '
                '"bytes"; expected "str"  [arg-type]\n'
                "Found 2 errors in 1 file (checked 24 source files)\n",
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["ci", "classify", "--log", str(log)])

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["failure_class"], "python_type_check")
            self.assertGreaterEqual(payload["confidence"], 0.7)
            self.assertEqual(payload["requirements"]["external_model_required"], False)

    def test_ci_classify_detects_pyright_type_check_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "failed.log"
            log.write_text(
                "Run pyright\n"
                '/repo/src/app.py:17:9 - error: "value" is not assignable to declared '
                'type "int" (reportAssignmentType)\n'
                "3 errors, 0 warnings, 0 informations\n",
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["ci", "classify", "--log", str(log)])

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["failure_class"], "python_type_check")

    def test_ci_classify_type_check_wins_over_passing_pytest_signal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "failed.log"
            log.write_text(
                "Run: pytest && mypy src\n"
                "============== 120 passed in 4.2s ==============\n"
                "src/app.py:10: error: Incompatible types in assignment  [assignment]\n"
                "Found 1 error in 1 file (checked 12 source files)\n",
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["ci", "classify", "--log", str(log)])

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["failure_class"], "python_type_check")

    def test_ci_classify_detects_ruff_lint_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "failed.log"
            log.write_text(
                "Run ruff check .\n"
                "src/app.py:1:1: F401 [*] `os` imported but unused\n"
                "src/app.py:12:89: E501 Line too long (104 > 88)\n"
                "Found 2 errors.\n",
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["ci", "classify", "--log", str(log)])

            self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["failure_class"], "python_lint")
        self.assertGreaterEqual(payload["confidence"], 0.7)

    def test_ci_classify_detects_black_format_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "failed.log"
            log.write_text(
                "Run black --check .\n"
                "would reformat src/app.py\n"
                "Oh no! 1 file would be reformatted, 23 files would be left unchanged.\n",
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["ci", "classify", "--log", str(log)])

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["failure_class"], "python_lint")

    def test_schema_command_emits_ci_result_contract(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "patchrail", "schema", "ci-result"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        schema = json.loads(proc.stdout)
        self.assertEqual(schema["properties"]["schema_version"]["const"], "patchrail.ci_result.v1")
        self.assertIn("python_test_failure", schema["properties"]["failure_class"]["enum"])
        self.assertIn("java_build_failure", schema["properties"]["failure_class"]["enum"])
        self.assertIn("dotnet_build_failure", schema["properties"]["failure_class"]["enum"])
        self.assertIn("docker_build_failure", schema["properties"]["failure_class"]["enum"])
        self.assertIn("browser_test_failure", schema["properties"]["failure_class"]["enum"])
        self.assertIn("security_scan_failure", schema["properties"]["failure_class"]["enum"])
        self.assertIn("ruby_bundle_failure", schema["properties"]["failure_class"]["enum"])
        self.assertIn("php_composer_failure", schema["properties"]["failure_class"]["enum"])
        self.assertIn("runner_resource_exhaustion", schema["properties"]["failure_class"]["enum"])
        self.assertIn("network_transient_failure", schema["properties"]["failure_class"]["enum"])
        self.assertIn("code_coverage_threshold", schema["properties"]["failure_class"]["enum"])
        self.assertIn("python_type_check", schema["properties"]["failure_class"]["enum"])
        self.assertIn("python_lint", schema["properties"]["failure_class"]["enum"])
        self.assertIn("ci_job_timeout", schema["properties"]["failure_class"]["enum"])
        self.assertIn("cpp_build_failure", schema["properties"]["failure_class"]["enum"])
        self.assertNotIn("guide_url", schema["properties"])
        self.assertNotIn("pack_url", schema["properties"])
        self.assertNotIn("sample_url", schema["properties"])
        self.assertNotIn("action_url", schema["properties"])
        self.assertIn("node_test_failure", schema["properties"]["failure_class"]["enum"])
        self.assertIn("node_dependency_install", schema["properties"]["failure_class"]["enum"])
        self.assertIn("rust_lint", schema["properties"]["failure_class"]["enum"])
        self.assertIn("go_lint", schema["properties"]["failure_class"]["enum"])
        self.assertIn("typescript_typecheck", schema["properties"]["failure_class"]["enum"])
        self.assertEqual(
            schema["properties"]["requirements"]["properties"]["billing_required"]["const"], False
        )
        self.assertEqual(
            schema["properties"]["requirements"]["properties"]["external_model_required"]["const"],
            False,
        )

    def test_schema_command_emits_ci_benchmark_and_pilot_contracts(self) -> None:
        expected_versions = {
            "application-dossier": "patchrail.application_dossier.v1",
            "ci-benchmark": "patchrail.ci_benchmark.v1",
            "ci-fixture-check": "patchrail.ci_fixture_check.v1",
            "ci-pilot-summary": "patchrail.ci_pilot_summary.v1",
            "ci-pilot-metrics": "patchrail.ci_pilot_metrics.v1",
            "reviewer-quick-check-artifacts": "patchrail.reviewer_quick_check_artifacts.v1",
        }

        for schema_name, schema_version in expected_versions.items():
            with self.subTest(schema_name=schema_name):
                proc = subprocess.run(
                    [sys.executable, "-m", "patchrail", "schema", schema_name],
                    text=True,
                    capture_output=True,
                    check=False,
                )

                self.assertEqual(proc.returncode, 0, proc.stderr)
                schema = json.loads(proc.stdout)
                self.assertEqual(schema["properties"]["schema_version"]["const"], schema_version)
                if schema_name == "application-dossier":
                    submission = schema["properties"]["submission_policy"]["properties"]
                    safety = schema["properties"]["safety"]["properties"]
                    self.assertEqual(submission["maintainer_tap_required"]["const"], True)
                    self.assertEqual(submission["agent_may_submit"]["const"], False)
                    self.assertEqual(submission["no_placeholder_metrics"]["const"], True)
                    self.assertEqual(submission["no_money_goal"]["const"], True)
                    self.assertEqual(safety["local_first"]["const"], True)
                    self.assertEqual(safety["billing_required"]["const"], False)
                    self.assertEqual(safety["third_party_write_actions_allowed"]["const"], False)
                elif schema_name == "reviewer-quick-check-artifacts":
                    self.assertEqual(
                        schema["properties"]["generated_from"]["const"], "local_checkout"
                    )
                    self.assertEqual(schema["properties"]["network_required"]["const"], False)
                    self.assertEqual(schema["properties"]["write_action_required"]["const"], False)
                    self.assertEqual(
                        schema["properties"]["application_form_submission_performed"]["const"],
                        False,
                    )
                    artifacts = schema["properties"]["artifacts"]["items"]["enum"]
                    self.assertIn("README.md", artifacts)
                    self.assertIn("reviewer-quick-check.md", artifacts)
                    self.assertIn("application-dossier.json", artifacts)
                    self.assertIn("http-api-evidence.json", artifacts)
                    self.assertIn("http-api-evidence.md", artifacts)
                    self.assertIn("release-readiness.json", artifacts)
                    self.assertIn("release-readiness.md", artifacts)
                    self.assertIn("reviewer-quick-check-artifacts.schema.json", artifacts)
                else:
                    requirements = schema["properties"]["requirements"]["properties"]
                    self.assertEqual(requirements["billing_required"]["const"], False)
                    self.assertEqual(requirements["external_model_required"]["const"], False)
                    self.assertEqual(requirements["network_required"]["const"], False)
                    if "github_write_permission_required" in requirements:
                        self.assertEqual(
                            requirements["github_write_permission_required"]["const"], False
                        )

    def test_doctor_reports_local_first_requirements(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "patchrail", "doctor", "--format", "json"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["schema_version"], "patchrail.doctor.v1")
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["local_first"], True)
        self.assertEqual(payload["checks"]["ci_fixture_count"], 169)
        self.assertEqual(payload["checks"]["ci_result_schema_available"], True)
        self.assertEqual(payload["requirements"]["billing_required"], False)
        self.assertEqual(payload["requirements"]["external_model_required"], False)
        self.assertEqual(payload["requirements"]["network_required"], False)
        self.assertEqual(payload["requirements"]["github_write_permission_required"], False)

    def test_ci_benchmark_checks_fixture_expectations(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "patchrail",
                "ci",
                "benchmark",
                "examples/ci-triage",
                "--format",
                "json",
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["schema_version"], "patchrail.ci_benchmark.v1")
        self.assertEqual(payload["total_cases"], 169)
        self.assertEqual(payload["passed"], 169)
        self.assertEqual(payload["failed"], 0)
        self.assertEqual(payload["accuracy"]["top_1"], 1.0)
        self.assertEqual(payload["coverage_gate"]["min_cases_per_class"], 0)
        self.assertEqual(payload["coverage_gate"]["passed"], True)
        self.assertEqual(payload["coverage_gate"]["failures"], [])
        self.assertEqual(payload["root"], "examples/ci-triage")
        self.assertEqual(
            payload["class_summary"],
            {
                "browser_test_failure": {"failed": 0, "passed": 5, "total_cases": 5},
                "dotnet_build_failure": {"failed": 0, "passed": 5, "total_cases": 5},
                "docker_build_failure": {"failed": 0, "passed": 5, "total_cases": 5},
                "github_actions_workflow": {"failed": 0, "passed": 10, "total_cases": 10},
                "go_test_failure": {"failed": 0, "passed": 10, "total_cases": 10},
                "java_build_failure": {"failed": 0, "passed": 5, "total_cases": 5},
                "javascript_lint": {"failed": 0, "passed": 11, "total_cases": 11},
                "node_dependency_install": {"failed": 0, "passed": 19, "total_cases": 19},
                "php_composer_failure": {"failed": 0, "passed": 5, "total_cases": 5},
                "python_dependency_resolution": {"failed": 0, "passed": 27, "total_cases": 27},
                "python_test_failure": {"failed": 0, "passed": 9, "total_cases": 9},
                "ruby_bundle_failure": {"failed": 0, "passed": 8, "total_cases": 8},
                "rust_test_failure": {"failed": 0, "passed": 10, "total_cases": 10},
                "security_scan_failure": {"failed": 0, "passed": 5, "total_cases": 5},
                "typescript_typecheck": {"failed": 0, "passed": 19, "total_cases": 19},
                "shell_lint": {"failed": 0, "passed": 2, "total_cases": 2},
                "elixir_mix_failure": {"failed": 0, "passed": 2, "total_cases": 2},
                "database_migration_failure": {"failed": 0, "passed": 2, "total_cases": 2},
                "kubernetes_deploy_failure": {"failed": 0, "passed": 2, "total_cases": 2},
                "helm_chart_failure": {"failed": 0, "passed": 2, "total_cases": 2},
                "docs_build_failure": {"failed": 0, "passed": 3, "total_cases": 3},
                "xcode_build_failure": {"failed": 0, "passed": 3, "total_cases": 3},
            },
        )
        actual_classes = {case["actual_failure_class"] for case in payload["cases"]}
        self.assertEqual(
            actual_classes,
            {
                "browser_test_failure",
                "dotnet_build_failure",
                "docker_build_failure",
                "github_actions_workflow",
                "go_test_failure",
                "java_build_failure",
                "javascript_lint",
                "node_dependency_install",
                "php_composer_failure",
                "python_dependency_resolution",
                "python_test_failure",
                "ruby_bundle_failure",
                "rust_test_failure",
                "security_scan_failure",
                "typescript_typecheck",
                "shell_lint",
                "elixir_mix_failure",
                "database_migration_failure",
                "kubernetes_deploy_failure",
                "helm_chart_failure",
                "docs_build_failure",
                "xcode_build_failure",
            },
        )
        self.assertEqual(payload["requirements"]["network_required"], False)

    def test_ci_benchmark_summary_only_omits_case_details(self) -> None:
        json_proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "patchrail",
                "ci",
                "benchmark",
                "examples/ci-triage",
                "--format",
                "json",
                "--summary-only",
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(json_proc.returncode, 0, json_proc.stderr)
        payload = json.loads(json_proc.stdout)
        self.assertEqual(payload["schema_version"], "patchrail.ci_benchmark.v1")
        self.assertEqual(payload["total_cases"], 169)
        self.assertEqual(payload["passed"], 169)
        self.assertEqual(payload["failed"], 0)
        self.assertEqual(payload["accuracy"]["top_1"], 1.0)
        self.assertEqual(payload["coverage_gate"]["passed"], True)
        self.assertIn("class_summary", payload)
        self.assertIn("coverage_gate", payload)
        self.assertNotIn("cases", payload)

        markdown_proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "patchrail",
                "ci",
                "benchmark",
                "examples/ci-triage",
                "--format",
                "markdown",
                "--summary-only",
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(markdown_proc.returncode, 0, markdown_proc.stderr)
        self.assertIn("# PatchRail CI Benchmark", markdown_proc.stdout)
        self.assertIn("- Total cases: `169`", markdown_proc.stdout)
        self.assertIn("- Coverage gate passed: `True`", markdown_proc.stdout)
        self.assertIn("## Class summary", markdown_proc.stdout)
        self.assertNotIn("## Cases", markdown_proc.stdout)

    def test_ci_benchmark_coverage_gate_can_require_depth_per_class(self) -> None:
        pass_proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "patchrail",
                "ci",
                "benchmark",
                "examples/ci-triage",
                "--format",
                "json",
                "--summary-only",
                "--min-cases-per-class",
                "2",
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(pass_proc.returncode, 0, pass_proc.stderr)
        pass_payload = json.loads(pass_proc.stdout)
        self.assertEqual(pass_payload["coverage_gate"]["min_cases_per_class"], 2)
        self.assertEqual(pass_payload["coverage_gate"]["passed"], True)
        self.assertEqual(pass_payload["coverage_gate"]["failures"], [])

        fail_proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "patchrail",
                "ci",
                "benchmark",
                "examples/ci-triage",
                "--format",
                "json",
                "--summary-only",
                "--min-cases-per-class",
                "6",
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(fail_proc.returncode, 1)
        fail_payload = json.loads(fail_proc.stdout)
        self.assertEqual(fail_payload["failed"], 0)
        self.assertEqual(fail_payload["coverage_gate"]["passed"], False)
        failing_classes = {
            failure["failure_class"]: failure
            for failure in fail_payload["coverage_gate"]["failures"]
        }
        self.assertEqual(failing_classes["browser_test_failure"]["total_cases"], 5)
        self.assertEqual(failing_classes["browser_test_failure"]["minimum_cases"], 6)

    def test_ci_benchmark_rejects_negative_coverage_gate(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "patchrail",
                "ci",
                "benchmark",
                "examples/ci-triage",
                "--min-cases-per-class",
                "-1",
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 2)
        self.assertIn("--min-cases-per-class must be >= 0", proc.stderr)

    def test_ci_fixture_check_accepts_clean_fixture_pair(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            log = root / "python-test.log"
            log.write_text(
                "python -m pytest -q\nFAILED tests/test_app.py::test_ok - AssertionError\n",
                encoding="utf-8",
            )
            log.with_suffix(".expected.json").write_text(
                json.dumps({"failure_class": "python_test_failure", "minimum_confidence": 0.7}),
                encoding="utf-8",
            )

            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "patchrail",
                    "ci",
                    "fixture-check",
                    str(root),
                    "--format",
                    "json",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["schema_version"], "patchrail.ci_fixture_check.v1")
            self.assertEqual(payload["total_cases"], 1)
            self.assertEqual(payload["passed"], 1)
            self.assertEqual(payload["failed"], 0)
            self.assertEqual(payload["requirements"]["network_required"], False)
            self.assertEqual(payload["requirements"]["github_write_permission_required"], False)

    def test_ci_classify_detects_docker_build_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "docker.log"
            log.write_text(
                "docker buildx build --target runtime .\n"
                'ERROR: failed to solve: target stage "runtime" could not be found\n',
                encoding="utf-8",
            )

            proc = subprocess.run(
                [sys.executable, "-m", "patchrail", "ci", "classify", "--log", str(log)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["failure_class"], "docker_build_failure")
            self.assertIn("docker build", payload["reproduction_command"])
            self.assertEqual(payload["requirements"]["external_model_required"], False)

    def test_ci_classify_detects_cmake_build_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "failed.log"
            log.write_text(
                "CMake Error at CMakeLists.txt:42 (find_package)\n"
                "ninja: build stopped: subcommand failed.\n",
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["ci", "classify", "--log", str(log)])

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["failure_class"], "cpp_build_failure")
            self.assertIn("cmake --build", payload["reproduction_command"])
            self.assertEqual(payload["requirements"]["external_model_required"], False)

    def test_ci_classify_detects_gcc_link_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "failed.log"
            log.write_text(
                "app.o: in function `main': undefined reference to `foo::bar()'\n"
                "collect2: error: ld returned 1 exit status\n"
                "make: *** [app] Error 1\n",
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["ci", "classify", "--log", str(log)])

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["failure_class"], "cpp_build_failure")

    def test_ci_classify_detects_clang_compile_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "failed.log"
            log.write_text(
                "src/widget.cpp:18:5: error: use of undeclared identifier 'widget'\n"
                "clang++: error: unable to execute command: linker command failed\n",
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["ci", "classify", "--log", str(log)])

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["failure_class"], "cpp_build_failure")

    def test_ci_classify_cpp_header_failure_wins_over_docker_signal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "failed.log"
            log.write_text(
                "src/widget.cpp:3:10: fatal error: widget.h: No such file or directory\n"
                "make: *** [obj/widget.o] Error 1\n",
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["ci", "classify", "--log", str(log)])

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["failure_class"], "cpp_build_failure")

    def test_ci_classify_detects_browser_test_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "playwright.log"
            log.write_text(
                "npx playwright test\n"
                "Error: browserType.launch: Executable doesn't exist at <cache>/chromium/chrome\n"
                "Please run npx playwright install\n",
                encoding="utf-8",
            )

            proc = subprocess.run(
                [sys.executable, "-m", "patchrail", "ci", "classify", "--log", str(log)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["failure_class"], "browser_test_failure")
            self.assertIn("playwright", payload["reproduction_command"])
            self.assertEqual(payload["requirements"]["external_model_required"], False)

    def test_ci_classify_detects_java_build_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "java.log"
            log.write_text(
                "Run mvn -B test\n"
                "[ERROR] COMPILATION ERROR :\n"
                "[ERROR] cannot find symbol\n"
                "[ERROR] Failed to execute goal org.apache.maven.plugins:maven-compiler-plugin\n",
                encoding="utf-8",
            )

            proc = subprocess.run(
                [sys.executable, "-m", "patchrail", "ci", "classify", "--log", str(log)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["failure_class"], "java_build_failure")
            self.assertIn("gradlew", payload["reproduction_command"])
            self.assertEqual(payload["requirements"]["external_model_required"], False)

    def test_ci_classify_detects_dotnet_build_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "dotnet.log"
            log.write_text(
                "Run dotnet restore src/App/App.csproj\n"
                "error NU1107: Version conflict detected for Microsoft.Extensions.Logging.\n"
                "Install/reference Microsoft.Extensions.Logging 8.0.0 directly to project.\n",
                encoding="utf-8",
            )

            proc = subprocess.run(
                [sys.executable, "-m", "patchrail", "ci", "classify", "--log", str(log)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["failure_class"], "dotnet_build_failure")
            self.assertIn("dotnet restore", payload["reproduction_command"])
            self.assertEqual(payload["requirements"]["external_model_required"], False)

    def test_ci_classify_detects_ruby_bundle_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "ruby.log"
            log.write_text(
                "Run bundle install\n"
                'Bundler could not find compatible versions for gem "rack":\n'
                "  In Gemfile:\n"
                "    rails was resolved to 7.1.0, which depends on rack (~> 2.2)\n",
                encoding="utf-8",
            )

            proc = subprocess.run(
                [sys.executable, "-m", "patchrail", "ci", "classify", "--log", str(log)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["failure_class"], "ruby_bundle_failure")
            self.assertIn("bundle install", payload["reproduction_command"])
            self.assertEqual(payload["requirements"]["external_model_required"], False)

    def test_ci_classify_detects_php_composer_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "php.log"
            log.write_text(
                "Run composer install --no-interaction --prefer-dist\n"
                "Your requirements could not be resolved to an installable set of packages.\n"
                "Problem 1\n"
                "Root composer.json requires php ^8.3 but your php version (8.2.14) does not satisfy that requirement.\n",
                encoding="utf-8",
            )

            proc = subprocess.run(
                [sys.executable, "-m", "patchrail", "ci", "classify", "--log", str(log)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["failure_class"], "php_composer_failure")
            self.assertIn("composer install", payload["reproduction_command"])
            self.assertEqual(payload["requirements"]["external_model_required"], False)

    def test_ci_fixture_check_fails_for_missing_expected_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            log = root / "missing-metadata.log"
            log.write_text("cargo test\nthread 'demo' panicked\n", encoding="utf-8")

            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "patchrail",
                    "ci",
                    "fixture-check",
                    str(root),
                    "--format",
                    "json",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(proc.returncode, 1)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["failed"], 1)
            self.assertIn("missing neighboring .expected.json file", payload["cases"][0]["issues"])

    def test_ci_fixture_check_fails_for_unredacted_sensitive_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            log = root / "unredacted.log"
            log.write_text(
                "python -m pytest -q\n"
                "FAILED tests/test_app.py::test_ok - AssertionError\n"
                "Contact maintainer@example.com\n"
                "Path /Users/example/project\n",
                encoding="utf-8",
            )
            log.with_suffix(".expected.json").write_text(
                json.dumps({"failure_class": "python_test_failure", "minimum_confidence": 0.7}),
                encoding="utf-8",
            )

            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "patchrail",
                    "ci",
                    "fixture-check",
                    str(root),
                    "--format",
                    "json",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(proc.returncode, 1)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["failed"], 1)
            self.assertIn("email", payload["cases"][0]["redactions"])
            self.assertIn("mac_home_path", payload["cases"][0]["redactions"])
            self.assertIn("possible unredacted sensitive data", payload["cases"][0]["issues"][0])

    def test_ci_fixture_check_flags_registry_tokens_and_windows_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            log = root / "unredacted-windows.log"
            log.write_text(
                "npm audit\n"
                "1 critical severity vulnerability\n"
                "npm token npm_1234567890abcdefghijklmnopqrst\n"
                "Path C:\\Users\\runner\\work\\repo\n",
                encoding="utf-8",
            )
            log.with_suffix(".expected.json").write_text(
                json.dumps({"failure_class": "security_scan_failure", "minimum_confidence": 0.5}),
                encoding="utf-8",
            )

            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "patchrail",
                    "ci",
                    "fixture-check",
                    str(root),
                    "--format",
                    "json",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(proc.returncode, 1)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["failed"], 1)
            self.assertIn("npm_token", payload["cases"][0]["redactions"])
            self.assertIn("windows_home_path", payload["cases"][0]["redactions"])
            self.assertTrue(
                any(
                    "possible unredacted sensitive data" in issue
                    for issue in payload["cases"][0]["issues"]
                )
            )

    def test_ci_explain_defaults_to_markdown_and_states_safety_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "failed.log"
            log.write_text(
                "python -m pip install -r requirements.txt\n"
                "ERROR: Could not find a version that satisfies the requirement demo==99\n"
                "ResolutionImpossible\n",
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["ci", "explain", "--log", str(log)])

            markdown = stdout.getvalue()
            self.assertEqual(exit_code, 0)
            self.assertIn("# PatchRail CI Report", markdown)
            self.assertIn("python_dependency_resolution", markdown)
            self.assertIn("did not create a pull request", markdown)
            self.assertIn("send data to an external service", markdown)

    def test_module_entrypoint_runs_public_cli(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "patchrail", "ci", "classify"],
            input="cargo test\nthread 'demo' panicked\n",
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["failure_class"], "rust_test_failure")
        self.assertNotIn("guide_url", payload)
        self.assertNotIn("pack_url", payload)

    def test_ci_explain_redacts_secret_values_from_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "failed.log"
            fake_github_token = "ghp_" + "abcdefghijklmnopqrstuvwxyz123456"
            log.write_text(
                "python -m pytest -q\n"
                "FAILED tests/test_app.py::test_ok - AssertionError\n"
                f"GITHUB_TOKEN={fake_github_token}\n"
                "Contact maintainer@example.com\n"
                "Path /Users/example/project\n",
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["ci", "explain", "--redact", "--log", str(log)])

            markdown = stdout.getvalue()
            self.assertEqual(exit_code, 0)
            self.assertIn("## Redaction", markdown)
            self.assertIn("env_secret_assignment", markdown)
            self.assertIn("email", markdown)
            self.assertIn("mac_home_path", markdown)
            self.assertNotIn(fake_github_token, markdown)
            self.assertNotIn("maintainer@example.com", markdown)
            self.assertNotIn("/Users/example", markdown)

    def test_ci_pilot_pack_generates_local_redacted_consent_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            log = root / "failed-ci.log"
            out_dir = root / "pilot-pack"
            fake_github_token = "ghp_" + "abcdefghijklmnopqrstuvwxyz123456"
            log.write_text(
                "python -m pip install -r requirements.txt\n"
                "ERROR: Could not find a version that satisfies the requirement demo==99\n"
                "ResolutionImpossible\n"
                f"GITHUB_TOKEN={fake_github_token}\n"
                "Contact maintainer@example.com\n"
                "Path /Users/example/project\n",
                encoding="utf-8",
            )

            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "patchrail",
                    "ci",
                    "pilot-pack",
                    "--log",
                    str(log),
                    "--out-dir",
                    str(out_dir),
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            summary = json.loads(proc.stdout)
            self.assertEqual(summary["schema_version"], "patchrail.ci_pilot_pack_result.v1")
            self.assertEqual(summary["requirements"]["network_required"], False)
            self.assertEqual(summary["requirements"]["github_write_permission_required"], False)
            self.assertIn("open_pull_request", summary["blocked_actions"])
            self.assertIn("contact_maintainer", summary["blocked_actions"])

            manifest = json.loads((out_dir / "pilot-manifest.json").read_text(encoding="utf-8"))
            result = json.loads((out_dir / "patchrail-result.json").read_text(encoding="utf-8"))
            redacted_log = (out_dir / "failed-ci.redacted.log").read_text(encoding="utf-8")
            report = (out_dir / "patchrail-report.md").read_text(encoding="utf-8")
            readme = (out_dir / "README.md").read_text(encoding="utf-8")

            self.assertEqual(manifest["schema_version"], "patchrail.ci_pilot_pack.v1")
            self.assertEqual(manifest["source"]["source_log_name"], "failed-ci.log")
            self.assertEqual(manifest["source"]["raw_log_copied"], False)
            self.assertEqual(
                manifest["classification"]["failure_class"], "python_dependency_resolution"
            )
            self.assertEqual(result["failure_class"], "python_dependency_resolution")
            self.assertNotIn("guide_url", result)
            self.assertNotIn("pack_url", result)
            self.assertNotIn("sample_url", result)
            self.assertNotIn("action_url", result)
            self.assertEqual(
                manifest["consent_boundary"]["maintainer_review_required_before_sharing"], True
            )
            self.assertEqual(
                manifest["consent_boundary"]["repository_write_access_required"], False
            )
            self.assertEqual(manifest["requirements"]["external_model_required"], False)

            serialized = "\n".join([redacted_log, report, readme, json.dumps(manifest)])
            self.assertIn("python_dependency_resolution", serialized)
            self.assertIn("PatchRail did not copy the raw log", readme)
            self.assertIn("Share only after a maintainer reviews", readme)
            self.assertNotIn(fake_github_token, serialized)
            self.assertNotIn("maintainer@example.com", serialized)
            self.assertNotIn("/Users/example", serialized)
            self.assertIn("GITHUB_TOKEN=<redacted>", redacted_log)
            self.assertIn("<email>", redacted_log)
            self.assertIn("/Users/<user>/project", redacted_log)

    def test_ci_pilot_summary_defaults_to_private_repository_mention(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            log = root / "failed-ci.log"
            out_dir = root / "pilot-pack"
            log.write_text(
                "python -m pip install -r requirements.txt\n"
                "ERROR: Could not find a version that satisfies the requirement demo==99\n"
                "ResolutionImpossible\n",
                encoding="utf-8",
            )
            pack_proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "patchrail",
                    "ci",
                    "pilot-pack",
                    "--log",
                    str(log),
                    "--out-dir",
                    str(out_dir),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(pack_proc.returncode, 0, pack_proc.stderr)

            summary_proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "patchrail",
                    "ci",
                    "pilot-summary",
                    "--pack",
                    str(out_dir),
                    "--repository",
                    "private-owner/private-repo",
                    "--ci-provider",
                    "GitHub Actions",
                    "--toolchain",
                    "Python",
                    "--classification-correct",
                    "yes",
                    "--maintainer-action-useful",
                    "yes",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(summary_proc.returncode, 0, summary_proc.stderr)
            self.assertIn("# PatchRail Consent-Only Pilot Summary", summary_proc.stdout)
            self.assertIn("Repository approved for public mention: `false`", summary_proc.stdout)
            self.assertIn("Repository: `not approved for public listing`", summary_proc.stdout)
            self.assertIn("Root cause: `python_dependency_resolution`", summary_proc.stdout)
            self.assertIn("Classification correct: `yes`", summary_proc.stdout)
            self.assertIn("Suggested maintainer action useful: `yes`", summary_proc.stdout)
            self.assertIn("PatchRail ran locally", summary_proc.stdout)
            self.assertIn("did not copy the raw log", summary_proc.stdout)
            self.assertNotIn("private-owner/private-repo", summary_proc.stdout)

    def test_ci_pilot_summary_json_includes_repository_only_when_approved(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            log = root / "failed-ci.log"
            out_dir = root / "pilot-pack"
            log.write_text(
                "cargo test\nthread 'tests::demo' panicked at src/lib.rs:7\n",
                encoding="utf-8",
            )
            pack_proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "patchrail",
                    "ci",
                    "pilot-pack",
                    "--log",
                    str(log),
                    "--out-dir",
                    str(out_dir),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(pack_proc.returncode, 0, pack_proc.stderr)

            summary_proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "patchrail",
                    "ci",
                    "pilot-summary",
                    "--pack",
                    str(out_dir / "pilot-manifest.json"),
                    "--repository",
                    "patchrail/example",
                    "--repository-mention-approved",
                    "yes",
                    "--ci-provider",
                    "GitHub Actions",
                    "--toolchain",
                    "Rust",
                    "--format",
                    "json",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(summary_proc.returncode, 0, summary_proc.stderr)
            payload = json.loads(summary_proc.stdout)
            self.assertEqual(payload["schema_version"], "patchrail.ci_pilot_summary.v1")
            self.assertEqual(payload["pilot_pack"]["manifest_path"], "pilot-manifest.json")
            self.assertEqual(payload["public_listing"]["repository_mention_approved"], True)
            self.assertEqual(payload["public_listing"]["repository"], "patchrail/example")
            self.assertEqual(payload["pilot_context"]["ci_provider"], "GitHub Actions")
            self.assertEqual(payload["pilot_context"]["toolchain"], "Rust")
            self.assertEqual(payload["classification"]["failure_class"], "rust_test_failure")
            self.assertEqual(payload["pilot_pack"]["raw_log_copied"], False)
            self.assertEqual(payload["requirements"]["network_required"], False)
            self.assertIn("open_pull_request", payload["blocked_actions"])
            self.assertNotIn("/Volumes/", summary_proc.stdout)
            self.assertNotIn("/Users/", summary_proc.stdout)
            self.assertNotIn("/home/", summary_proc.stdout)

    def test_ci_pilot_metrics_aggregates_public_and_private_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            first_log = root / "first.log"
            first_pack = root / "first-pack"
            first_summary = root / "first-summary.json"
            first_log.write_text(
                "python -m pytest -q\nFAILED tests/test_app.py::test_ok - AssertionError\n",
                encoding="utf-8",
            )
            first_pack_proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "patchrail",
                    "ci",
                    "pilot-pack",
                    "--log",
                    str(first_log),
                    "--out-dir",
                    str(first_pack),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(first_pack_proc.returncode, 0, first_pack_proc.stderr)
            first_summary_proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "patchrail",
                    "ci",
                    "pilot-summary",
                    "--pack",
                    str(first_pack),
                    "--classification-correct",
                    "yes",
                    "--maintainer-action-useful",
                    "yes",
                    "--format",
                    "json",
                    "--out",
                    str(first_summary),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(first_summary_proc.returncode, 0, first_summary_proc.stderr)

            second_log = root / "second.log"
            second_pack = root / "second-pack"
            second_summary = root / "second-summary.json"
            second_log.write_text(
                "cargo test\nthread 'tests::demo' panicked at src/lib.rs:7\n",
                encoding="utf-8",
            )
            second_pack_proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "patchrail",
                    "ci",
                    "pilot-pack",
                    "--log",
                    str(second_log),
                    "--out-dir",
                    str(second_pack),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(second_pack_proc.returncode, 0, second_pack_proc.stderr)
            second_summary_proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "patchrail",
                    "ci",
                    "pilot-summary",
                    "--pack",
                    str(second_pack),
                    "--repository",
                    "patchrail/example",
                    "--repository-mention-approved",
                    "yes",
                    "--classification-correct",
                    "no",
                    "--maintainer-action-useful",
                    "unknown",
                    "--format",
                    "json",
                    "--out",
                    str(second_summary),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(second_summary_proc.returncode, 0, second_summary_proc.stderr)

            metrics_proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "patchrail",
                    "ci",
                    "pilot-metrics",
                    str(first_summary),
                    str(second_summary),
                    "--format",
                    "json",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(metrics_proc.returncode, 0, metrics_proc.stderr)
            payload = json.loads(metrics_proc.stdout)
            self.assertEqual(payload["schema_version"], "patchrail.ci_pilot_metrics.v1")
            self.assertEqual(payload["total_pilot_summaries"], 2)
            self.assertEqual(payload["public_repository_mentions"], 1)
            self.assertEqual(payload["private_or_unapproved_repository_mentions"], 1)
            self.assertEqual(payload["public_repositories"], ["patchrail/example"])
            self.assertEqual(payload["owned_repository_mentions"], 1)
            self.assertEqual(payload["external_repository_mentions"], 0)
            self.assertEqual(payload["owned_repositories"], ["patchrail/example"])
            self.assertEqual(payload["external_repositories"], [])
            self.assertEqual(payload["evidence_readiness"]["status"], "owned_repo_evidence_only")
            self.assertEqual(payload["evidence_readiness"]["external_adopters_countable"], 0)
            self.assertEqual(payload["evidence_readiness"]["owned_repo_evidence_countable"], 1)
            self.assertEqual(payload["evidence_readiness"]["private_feedback_count"], 1)
            self.assertEqual(payload["classification_correct"]["yes"], 1)
            self.assertEqual(payload["classification_correct"]["no"], 1)
            self.assertEqual(payload["maintainer_action_useful"]["yes"], 1)
            self.assertEqual(payload["maintainer_action_useful"]["unknown"], 1)
            self.assertEqual(payload["local_only_and_no_raw_log"], 2)
            self.assertEqual(payload["requirements"]["network_required"], False)

            markdown_proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "patchrail",
                    "ci",
                    "pilot-metrics",
                    str(first_summary),
                    str(second_summary),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(markdown_proc.returncode, 0, markdown_proc.stderr)
            self.assertIn("# PatchRail Consent-Only Pilot Metrics", markdown_proc.stdout)
            self.assertIn("- Public repository mentions: `1`", markdown_proc.stdout)
            self.assertIn("- Owned-repo public mentions: `1`", markdown_proc.stdout)
            self.assertIn("- External public repository mentions: `0`", markdown_proc.stdout)
            self.assertIn("- Evidence readiness: `owned_repo_evidence_only`", markdown_proc.stdout)
            self.assertIn("- Countable external adopters: `0`", markdown_proc.stdout)
            self.assertIn("- `patchrail/example`", markdown_proc.stdout)
            self.assertIn("- None approved for external adopter listing.", markdown_proc.stdout)

    def test_redact_command_emits_redacted_text(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "patchrail", "redact"],
            input=(
                "TOKEN=secret-value\n"
                "Contact maintainer@example.com\n"
                "Path /home/runner/work\n"
                "Windows path C:\\Users\\runner\\work\\repo\n"
                "GitLab token glpat-1234567890abcdefghijkl\n"
                "PyPI token pypi-AgEIcHlwaS5vcmcCdGVzdC12YWx1ZQ\n"
                "npm token npm_1234567890abcdefghijklmnopqrst\n"
            ),
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("TOKEN=<redacted>", proc.stdout)
        self.assertIn("<email>", proc.stdout)
        self.assertIn("/home/<user>/work", proc.stdout)
        self.assertIn("C:/Users/<user>\\work\\repo", proc.stdout)
        self.assertIn("<gitlab-token>", proc.stdout)
        self.assertIn("<pypi-token>", proc.stdout)
        self.assertIn("<npm-token>", proc.stdout)
        self.assertNotIn("secret-value", proc.stdout)
        self.assertNotIn("maintainer@example.com", proc.stdout)
        self.assertNotIn("glpat-1234567890abcdefghijkl", proc.stdout)
        self.assertNotIn("pypi-AgEIcHlwaS5vcmcCdGVzdC12YWx1ZQ", proc.stdout)
        self.assertNotIn("npm_1234567890abcdefghijklmnopqrst", proc.stdout)

    def test_redact_command_handles_cloud_and_key_material(self) -> None:
        fake_jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.s5b3Qd7n0pXcVm9wQ1aZ2k4L8tR6yU0o"
        fake_google_key = "AIza" + "b" * 35
        # Build at runtime so the recognizable token prefix never appears verbatim in source.
        fake_slack_token = "xox" + "b-123456789012-abcdefghijklmnop"
        private_key = (
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIBVAIBADANBgkqhkiG9w0BAQEFAASCAT4wggE6AgEAAkEA\n"
            "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKL\n"
            "-----END RSA PRIVATE KEY-----"
        )
        proc = subprocess.run(
            [sys.executable, "-m", "patchrail", "redact"],
            input=(
                f"Slack token {fake_slack_token}\n"
                f"Google key {fake_google_key}\n"
                "Google oauth ya29.A0ARrdaM-abcdefghijklmnopqrstuvwxyz0123\n"
                "HuggingFace hf_abcdefghijklmnopqrstuvwxyz0123\n"
                f"Auth header Authorization: Bearer {fake_jwt}\n"
                f"{private_key}\n"
            ),
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("<slack-token>", proc.stdout)
        self.assertIn("<google-api-key>", proc.stdout)
        self.assertIn("<google-oauth-token>", proc.stdout)
        self.assertIn("<huggingface-token>", proc.stdout)
        self.assertIn("<jwt>", proc.stdout)
        self.assertIn("<private-key>", proc.stdout)
        self.assertNotIn(fake_slack_token, proc.stdout)
        self.assertNotIn(fake_google_key, proc.stdout)
        self.assertNotIn("ya29.A0ARrdaM", proc.stdout)
        self.assertNotIn("hf_abcdefghijklmnopqrstuvwxyz0123", proc.stdout)
        self.assertNotIn(fake_jwt, proc.stdout)
        self.assertNotIn("MIIBVAIBADANBgkqhkiG", proc.stdout)
        self.assertNotIn("BEGIN RSA PRIVATE KEY", proc.stdout)

    def test_unknown_log_is_not_repairable(self) -> None:
        result = json.loads(
            subprocess.run(
                [sys.executable, "-m", "patchrail", "ci", "classify"],
                input="build did not work\n",
                text=True,
                capture_output=True,
                check=True,
            ).stdout
        )

        self.assertEqual(result["failure_class"], "unknown")
        self.assertLess(result["confidence"], 0.5)
        self.assertIn("Do not auto-repair", result["minimal_repair_strategy"])
        self.assertNotIn("guide_url", result)
        self.assertNotIn("pack_url", result)
        self.assertNotIn("sample_url", result)
        self.assertNotIn("action_url", result)

    def test_ci_classes_lists_every_supported_class_as_json(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            exit_code = main(["ci", "classes", "--format", "json"])

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["schema_version"], "patchrail.ci_classes.v1")

        classes = payload["classes"]
        self.assertEqual(payload["count"], len(classes))
        names = [entry["failure_class"] for entry in classes]

        # A known rule and the unknown fallback are both listed, once each.
        self.assertIn("python_test_failure", names)
        self.assertEqual(names.count("python_test_failure"), 1)
        self.assertEqual(names[-1], "unknown")
        self.assertEqual(len(names), len(set(names)))

        # Every entry is machine-readable with the three documented fields.
        for entry in classes:
            self.assertEqual(
                set(entry),
                {"failure_class", "likely_subsystem", "reproduction_command"},
            )
            self.assertTrue(entry["reproduction_command"])

        # Stable ordering: two runs emit the same sequence.
        second = StringIO()
        with redirect_stdout(second):
            main(["ci", "classes", "--format", "json"])
        self.assertEqual(
            names,
            [entry["failure_class"] for entry in json.loads(second.getvalue())["classes"]],
        )

    def test_ci_classes_text_output_is_terminal_readable(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            exit_code = main(["ci", "classes"])

        self.assertEqual(exit_code, 0)
        text = stdout.getvalue()
        self.assertIn("supported failure classes", text)
        # One class per line, each carrying its subsystem and reproduce hint.
        class_lines = [line for line in text.splitlines() if line.startswith("- ")]
        self.assertTrue(any("python_test_failure" in line for line in class_lines))
        self.assertTrue(all("reproduce:" in line for line in class_lines))

    def test_ci_explain_empty_log_file_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "empty.log"
            log_path.write_text("", encoding="utf-8")
            out_path = Path(tmpdir) / "should-not-exist.md"

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(["ci", "explain", "--log", str(log_path), "--out", str(out_path)])

        self.assertEqual(exit_code, 2)
        self.assertIn("log input is empty", stderr.getvalue())
        self.assertIn("explain", stderr.getvalue())
        # Nothing misleading is emitted on stdout or written to --out.
        self.assertEqual(stdout.getvalue(), "")
        self.assertFalse(out_path.exists())

    def test_ci_classify_whitespace_only_log_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "blank.log"
            log_path.write_text("   \n\t\n  ", encoding="utf-8")

            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(["ci", "classify", "--log", str(log_path)])

        self.assertEqual(exit_code, 2)
        self.assertIn("log input is empty", stderr.getvalue())
        self.assertIn("classify", stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "")

    def test_ci_explain_empty_stdin_fails_clearly(self) -> None:
        stdout = StringIO()
        stderr = StringIO()
        original_stdin = sys.stdin
        sys.stdin = StringIO("")
        try:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(["ci", "explain"])
        finally:
            sys.stdin = original_stdin

        self.assertEqual(exit_code, 2)
        self.assertIn("log input is empty", stderr.getvalue())
        self.assertIn("stdin", stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "")

    def test_ci_explain_non_empty_log_still_classifies(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "real.log"
            log_path.write_text(
                "E   ModuleNotFoundError: No module named 'requests'\n",
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["ci", "explain", "--log", str(log_path), "--format", "json"])

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["schema_version"], "patchrail.ci_result.v1")
        self.assertNotEqual(payload["failure_class"], "")


if __name__ == "__main__":
    unittest.main()
