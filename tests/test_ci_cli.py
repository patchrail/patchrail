from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from patchrail.cli import main


class PatchRailCITests(unittest.TestCase):
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
        self.assertEqual(
            schema["properties"]["requirements"]["properties"]["billing_required"]["const"], False
        )
        self.assertEqual(
            schema["properties"]["requirements"]["properties"]["external_model_required"]["const"],
            False,
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
        self.assertEqual(payload["checks"]["ci_fixture_count"], 101)
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
        self.assertEqual(payload["total_cases"], 101)
        self.assertEqual(payload["passed"], 101)
        self.assertEqual(payload["failed"], 0)
        actual_classes = {case["actual_failure_class"] for case in payload["cases"]}
        self.assertEqual(
            actual_classes,
            {
                "github_actions_workflow",
                "go_test_failure",
                "javascript_lint",
                "node_dependency_install",
                "python_dependency_resolution",
                "python_test_failure",
                "rust_test_failure",
                "typescript_typecheck",
            },
        )
        self.assertEqual(payload["requirements"]["network_required"], False)

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

    def test_redact_command_emits_redacted_text(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "patchrail", "redact"],
            input="TOKEN=secret-value\nContact maintainer@example.com\nPath /home/runner/work\n",
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("TOKEN=<redacted>", proc.stdout)
        self.assertIn("<email>", proc.stdout)
        self.assertIn("/home/<user>/work", proc.stdout)
        self.assertNotIn("secret-value", proc.stdout)
        self.assertNotIn("maintainer@example.com", proc.stdout)

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


if __name__ == "__main__":
    unittest.main()
