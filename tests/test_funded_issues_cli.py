from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest


def run_patchrail(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "patchrail", *args],
        text=True,
        capture_output=True,
        check=False,
    )


class PatchRailFundedIssuesTests(unittest.TestCase):
    def test_funded_issues_list_is_safe_only_and_read_only_by_default(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "list",
                "--source",
                "examples/funded-issues-readonly/issues.json",
                "--format",
                "json",
            ]
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["schema_version"], "patchrail.funded_issues.v1")
        self.assertEqual(payload["safe_only"], True)
        self.assertEqual(payload["read_only"], True)
        self.assertEqual(payload["total_loaded"], 2)
        self.assertEqual(payload["total_returned"], 1)
        self.assertEqual(payload["issues"][0]["reference"], "example/project#42")
        self.assertEqual(payload["issues"][0]["risk_level"], "low")
        self.assertIn("automatic_pull_requests", payload["blocked_actions"])
        self.assertEqual(payload["requirements"]["network_required"], False)
        self.assertEqual(payload["requirements"]["github_write_permission_required"], False)

    def test_funded_issues_can_show_risky_items_only_when_requested(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "list",
                "--source",
                "examples/funded-issues-readonly/issues.json",
                "--include-risky",
                "--format",
                "json",
            ]
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["safe_only"], False)
        self.assertEqual(payload["total_returned"], 2)
        risky = [issue for issue in payload["issues"] if issue["risk_level"] == "high"]
        self.assertEqual(risky[0]["reference"], "example/toolkit#17")
        self.assertIn("ambiguous_scope", risky[0]["risk_flags"])

    def test_funded_issues_explain_states_ethics_boundary(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "explain",
                "example/project#42",
                "--source",
                "examples/funded-issues-readonly/issues.json",
                "--format",
                "markdown",
            ]
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("# PatchRail Funded Issue", proc.stdout)
        self.assertIn("Safe to keep in a local funded-maintenance shortlist", proc.stdout)
        self.assertIn("automatic_pull_requests", proc.stdout)
        self.assertIn("does not claim rewards", proc.stdout)

    def test_funded_issues_unknown_reference_fails_cleanly(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "explain",
                "example/missing#1",
                "--source",
                "examples/funded-issues-readonly/issues.json",
            ]
        )

        self.assertEqual(proc.returncode, 1)
        self.assertIn("Unknown funded issue", proc.stderr)

    def test_funded_issues_import_normalizes_local_provider_export(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "import",
                "--provider",
                "github",
                "--source",
                "examples/funded-issues-readonly/provider-github-export.json",
                "--format",
                "json",
            ]
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["schema_version"], "patchrail.funded_issues.v1")
        self.assertEqual(payload["read_only"], True)
        self.assertEqual(payload["import_source"]["provider"], "github")
        self.assertEqual(payload["import_source"]["local_file_only"], True)
        self.assertEqual(payload["import_source"]["records_loaded"], 2)
        self.assertEqual(payload["requirements"]["network_required"], False)
        self.assertEqual(payload["requirements"]["github_write_permission_required"], False)
        safe_issue = payload["issues"][0]
        self.assertEqual(safe_issue["reference"], "example/project#42")
        self.assertEqual(safe_issue["funding"]["display"], "250 USD")
        self.assertEqual(safe_issue["risk_level"], "low")
        self.assertIn("contribution guidelines linked", safe_issue["contribution_signals"])
        risky_issue = payload["issues"][1]
        self.assertEqual(risky_issue["reference"], "example/toolkit#17")
        self.assertEqual(risky_issue["risk_level"], "high")
        self.assertIn("ambiguous_scope", risky_issue["risk_flags"])
        self.assertIn("automatic_issue_comments", payload["blocked_actions"])

    def test_imported_provider_export_can_feed_safe_only_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            normalized = Path(tmp) / "funded-issues.json"
            import_proc = run_patchrail(
                [
                    "funded-issues",
                    "import",
                    "--provider",
                    "github",
                    "--source",
                    "examples/funded-issues-readonly/provider-github-export.json",
                    "--out",
                    str(normalized),
                ]
            )
            self.assertEqual(import_proc.returncode, 0, import_proc.stderr)

            list_proc = run_patchrail(
                [
                    "funded-issues",
                    "list",
                    "--source",
                    str(normalized),
                    "--format",
                    "json",
                ]
            )

        self.assertEqual(list_proc.returncode, 0, list_proc.stderr)
        payload = json.loads(list_proc.stdout)
        self.assertEqual(payload["total_loaded"], 2)
        self.assertEqual(payload["total_returned"], 1)
        self.assertEqual(payload["issues"][0]["reference"], "example/project#42")

    def test_funded_issues_readonly_demo_has_stable_summary(self) -> None:
        expected = json.loads(
            Path("examples/funded-issues-readonly/demo-summary.expected.json").read_text(
                encoding="utf-8"
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [
                    sys.executable,
                    "examples/funded-issues-readonly/run_demo.py",
                    "--output",
                    tmp,
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            summary = json.loads((Path(tmp) / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary, expected)

            for artifact in expected["artifact_files"]:
                self.assertTrue((Path(tmp) / artifact).exists())

            safe_list = json.loads((Path(tmp) / "safe-list.json").read_text(encoding="utf-8"))
            all_issues = json.loads((Path(tmp) / "all-issues.json").read_text(encoding="utf-8"))
            risky = json.loads((Path(tmp) / "risky-explain.json").read_text(encoding="utf-8"))
            safe_explain = (Path(tmp) / "safe-explain.md").read_text(encoding="utf-8")

        self.assertEqual(safe_list["total_returned"], 1)
        self.assertEqual(all_issues["total_returned"], 2)
        self.assertEqual(risky["issue"]["risk_level"], "high")
        self.assertIn("automatic_claims", risky["ethics"]["blocked"])
        self.assertIn("automatic_issue_comments", risky["ethics"]["blocked"])
        self.assertIn("Safe to keep in a local funded-maintenance shortlist", safe_explain)
        self.assertFalse(summary["requirements"]["network_required"])
        self.assertFalse(summary["requirements"]["github_write_permission_required"])


if __name__ == "__main__":
    unittest.main()
