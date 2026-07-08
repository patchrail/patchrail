from __future__ import annotations

import csv
import io
import json
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

from patchrail.funded_issues.importers import import_provider_export


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
        self.assertEqual(payload["issues"][0]["opportunity_state"], "active")
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
        self.assertEqual(risky[0]["opportunity_state"], "closed")
        self.assertFalse(risky[0]["safe_to_list"])
        self.assertIn("ambiguous_scope", risky[0]["risk_flags"])

    def test_funded_issues_list_exports_safe_only_tracker_csv(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "list",
                "--source",
                "examples/funded-issues-readonly/issues.json",
                "--format",
                "csv",
            ]
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        rows = list(csv.DictReader(io.StringIO(proc.stdout)))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["reference"], "example/project#42")
        self.assertEqual(rows[0]["platform"], "polar")
        self.assertEqual(rows[0]["funding_amount"], "250.0")
        self.assertEqual(rows[0]["funding_currency"], "USD")
        self.assertEqual(rows[0]["opportunity_state"], "active")
        self.assertEqual(rows[0]["risk_level"], "low")
        self.assertEqual(rows[0]["safe_to_list"], "true")
        self.assertEqual(rows[0]["read_only"], "true")
        self.assertIn("reproduction included", rows[0]["contribution_signals"])

    def test_funded_issues_list_exports_safe_only_jsonl_for_pipeline_ingest(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "list",
                "--source",
                "examples/funded-issues-readonly/issues.json",
                "--format",
                "jsonl",
            ]
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = proc.stdout.splitlines()
        self.assertEqual(len(lines), 1)
        row = json.loads(lines[0])
        self.assertEqual(row["reference"], "example/project#42")
        self.assertEqual(row["risk_level"], "low")
        self.assertEqual(row["opportunity_state"], "active")
        self.assertEqual(row["read_only"], True)
        self.assertTrue(row["safe_to_list"])
        self.assertIn("automatic_pull_requests", row["blocked_actions"])
        self.assertIn("reproduction included", row["contribution_signals"])

    def test_funded_issues_fresh_can_scope_from_solver_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store.json"
            allowlist = Path(tmp) / "SOLVER_ALLOWLIST.md"
            allowlist.write_text(
                "\n".join(
                    [
                        "| org/repo | evidencia |",
                        "|---|---|",
                        "| acme/* (org entera) | active rewards |",
                        "| archestra-ai/archestra | active board |",
                    ]
                ),
                encoding="utf-8",
            )
            store.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.funded_issues.store.v1",
                        "source_schema_version": "patchrail.funded_issues.v1",
                        "read_only": True,
                        "blocked_actions": [],
                        "requirements": {"network_required": False},
                        "entries": {
                            "https://github.com/acme/repo/issues/1": {
                                "issue": {
                                    "id": "allowlisted",
                                    "platform": "github",
                                    "repository": "acme/repo",
                                    "reference": "acme/repo#1",
                                    "issue_number": 1,
                                    "title": "Fix scoped bounty",
                                    "url": "https://github.com/acme/repo/issues/1",
                                    "funding": {"amount": 100, "currency": "USD"},
                                    "opportunity_state": "active",
                                    "attempt_count": 0,
                                },
                                "first_seen": "2026-06-12T08:00:00+00:00",
                                "last_seen": "2026-06-12T08:00:00+00:00",
                                "last_checked": "2026-06-12T08:00:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                            "https://github.com/nope/repo/issues/2": {
                                "issue": {
                                    "id": "not-allowlisted",
                                    "platform": "github",
                                    "repository": "nope/repo",
                                    "reference": "nope/repo#2",
                                    "issue_number": 2,
                                    "title": "Do not include",
                                    "url": "https://github.com/nope/repo/issues/2",
                                    "funding": {"amount": 100, "currency": "USD"},
                                    "opportunity_state": "active",
                                    "attempt_count": 0,
                                },
                                "first_seen": "2026-06-12T08:00:00+00:00",
                                "last_seen": "2026-06-12T08:00:00+00:00",
                                "last_checked": "2026-06-12T08:00:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            proc = run_patchrail(
                [
                    "funded-issues",
                    "fresh",
                    "--store",
                    str(store),
                    "--solver-allowlist",
                    str(allowlist),
                    "--now",
                    "2026-06-12T09:00:00+00:00",
                    "--format",
                    "json",
                ]
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["orgs"], ["acme", "archestra-ai"])
        self.assertEqual(payload["fresh_count"], 1)
        self.assertEqual(payload["fresh"][0]["reference"], "acme/repo#1")
        self.assertEqual(payload["solver_allowlist_path"], str(allowlist))

    def test_funded_issues_fresh_solver_quality_profile_applies_claim_filters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store.json"
            allowlist = Path(tmp) / "SOLVER_ALLOWLIST.md"
            allowlist.write_text(
                "\n".join(
                    [
                        "| org/repo | evidencia |",
                        "|---|---|",
                        "| acme/* | active rewards |",
                    ]
                ),
                encoding="utf-8",
            )
            store.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.funded_issues.store.v1",
                        "source_schema_version": "patchrail.funded_issues.v1",
                        "read_only": True,
                        "blocked_actions": [],
                        "requirements": {"network_required": False},
                        "entries": {
                            "https://github.com/acme/repo/issues/1": {
                                "issue": {
                                    "id": "profile-go",
                                    "platform": "github",
                                    "repository": "acme/repo",
                                    "reference": "acme/repo#1",
                                    "issue_number": 1,
                                    "title": "Fix deterministic CI failure",
                                    "url": "https://github.com/acme/repo/issues/1",
                                    "updated_at": "2026-06-12T08:30:00+00:00",
                                    "funding": {"amount": 100, "currency": "USD"},
                                    "opportunity_state": "active",
                                    "attempt_count": 1,
                                    "contribution_signals": ["failing test included"],
                                },
                                "first_seen": "2026-06-12T08:00:00+00:00",
                                "last_seen": "2026-06-12T08:00:00+00:00",
                                "last_checked": "2026-06-12T08:00:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                            "https://github.com/acme/repo/issues/2": {
                                "issue": {
                                    "id": "too-expensive",
                                    "platform": "github",
                                    "repository": "acme/repo",
                                    "reference": "acme/repo#2",
                                    "issue_number": 2,
                                    "title": "Large refactor",
                                    "url": "https://github.com/acme/repo/issues/2",
                                    "updated_at": "2026-06-12T08:30:00+00:00",
                                    "funding": {"amount": 500, "currency": "USD"},
                                    "opportunity_state": "active",
                                    "attempt_count": 1,
                                    "contribution_signals": ["reproduction included"],
                                },
                                "first_seen": "2026-06-12T08:00:00+00:00",
                                "last_seen": "2026-06-12T08:00:00+00:00",
                                "last_checked": "2026-06-12T08:00:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                            "https://github.com/acme/repo/issues/3": {
                                "issue": {
                                    "id": "no-tests",
                                    "platform": "github",
                                    "repository": "acme/repo",
                                    "reference": "acme/repo#3",
                                    "issue_number": 3,
                                    "title": "Clarify UI",
                                    "url": "https://github.com/acme/repo/issues/3",
                                    "updated_at": "2026-06-12T08:30:00+00:00",
                                    "funding": {"amount": 100, "currency": "USD"},
                                    "opportunity_state": "active",
                                    "attempt_count": 1,
                                    "contribution_signals": ["contribution guide linked"],
                                },
                                "first_seen": "2026-06-12T08:00:00+00:00",
                                "last_seen": "2026-06-12T08:00:00+00:00",
                                "last_checked": "2026-06-12T08:00:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                            "https://github.com/nope/repo/issues/4": {
                                "issue": {
                                    "id": "not-allowlisted",
                                    "platform": "github",
                                    "repository": "nope/repo",
                                    "reference": "nope/repo#4",
                                    "issue_number": 4,
                                    "title": "Fix scoped bounty",
                                    "url": "https://github.com/nope/repo/issues/4",
                                    "updated_at": "2026-06-12T08:30:00+00:00",
                                    "funding": {"amount": 100, "currency": "USD"},
                                    "opportunity_state": "active",
                                    "attempt_count": 1,
                                    "contribution_signals": ["failing test included"],
                                },
                                "first_seen": "2026-06-12T08:00:00+00:00",
                                "last_seen": "2026-06-12T08:00:00+00:00",
                                "last_checked": "2026-06-12T08:00:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            proc = run_patchrail(
                [
                    "funded-issues",
                    "fresh",
                    "--store",
                    str(store),
                    "--solver-allowlist",
                    str(allowlist),
                    "--quality-profile",
                    "solver",
                    "--now",
                    "2026-06-12T09:00:00+00:00",
                    "--format",
                    "json",
                ]
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["quality_profile"], "solver")
        self.assertEqual(payload["orgs"], ["acme"])
        self.assertEqual(payload["min_usd"], 25)
        self.assertEqual(payload["max_usd"], 300)
        self.assertEqual(payload["max_attempts"], 3)
        self.assertEqual(payload["min_age_minutes"], 10)
        self.assertEqual(payload["max_updated_age_hours"], 168)
        self.assertEqual(payload["require_tests_signal"], True)
        self.assertEqual(payload["fresh_count"], 1)
        self.assertEqual(payload["fresh"][0]["reference"], "acme/repo#1")

    def test_funded_issues_fresh_shortlist_note_is_memory_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store.json"
            store.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.funded_issues.store.v1",
                        "source_schema_version": "patchrail.funded_issues.v1",
                        "read_only": True,
                        "blocked_actions": [],
                        "requirements": {"network_required": False},
                        "entries": {
                            "https://github.com/example/project/issues/42": {
                                "issue": {
                                    "id": "fresh-go",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#42",
                                    "issue_number": 42,
                                    "title": "Fix deterministic CI failure",
                                    "url": "https://github.com/example/project/issues/42",
                                    "funding": {
                                        "amount": 250,
                                        "currency": "USD",
                                        "display": "250 USD",
                                    },
                                    "opportunity_state": "active",
                                    "attempt_count": 0,
                                },
                                "first_seen": "2026-06-12T08:00:00+00:00",
                                "last_seen": "2026-06-12T08:00:00+00:00",
                                "last_checked": "2026-06-12T08:00:00+00:00",
                                "state": "active",
                                "state_history": [
                                    {
                                        "state": "active",
                                        "at": "2026-06-12T08:00:00+00:00",
                                        "from": None,
                                    }
                                ],
                                "noise_flags": [],
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            fresh_proc = run_patchrail(
                [
                    "funded-issues",
                    "fresh",
                    "--store",
                    str(store),
                    "--hours",
                    "48",
                    "--min-usd",
                    "25",
                    "--max-usd",
                    "300",
                    "--now",
                    "2026-06-12T09:00:00+00:00",
                    "--format",
                    "shortlist-note",
                ]
            )

        self.assertEqual(fresh_proc.returncode, 0, fresh_proc.stderr)
        self.assertIn("## BARRIDO 2026-06-12 09:00:00Z", fresh_proc.stdout)
        self.assertIn("fresh=1", fresh_proc.stdout)
        self.assertIn("go=1", fresh_proc.stdout)
        self.assertIn("go_candidate: example/project#42", fresh_proc.stdout)
        self.assertIn("priority: clean solver candidate", fresh_proc.stdout)
        self.assertIn("https://github.com/example/project/issues/42", fresh_proc.stdout)

    def test_funded_issues_fresh_claim_checklist_includes_scoped_recheck_command(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store.json"
            store.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.funded_issues.store.v1",
                        "source_schema_version": "patchrail.funded_issues.v1",
                        "read_only": True,
                        "blocked_actions": [],
                        "requirements": {"network_required": False},
                        "entries": {
                            "https://github.com/example/project/issues/42": {
                                "issue": {
                                    "id": "fresh-go",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#42",
                                    "issue_number": 42,
                                    "title": "Fix deterministic CI failure",
                                    "url": "https://github.com/example/project/issues/42",
                                    "funding": {
                                        "amount": 250,
                                        "currency": "USD",
                                        "display": "250 USD",
                                    },
                                    "opportunity_state": "active",
                                    "attempt_count": 0,
                                },
                                "first_seen": "2026-06-12T08:00:00+00:00",
                                "last_seen": "2026-06-12T08:00:00+00:00",
                                "last_checked": "2026-06-12T08:00:00+00:00",
                                "state": "active",
                                "state_history": [
                                    {
                                        "state": "active",
                                        "at": "2026-06-12T08:00:00+00:00",
                                        "from": None,
                                    }
                                ],
                                "noise_flags": [],
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            fresh_proc = run_patchrail(
                [
                    "funded-issues",
                    "fresh",
                    "--store",
                    str(store),
                    "--hours",
                    "48",
                    "--org",
                    "example",
                    "--min-usd",
                    "25",
                    "--max-usd",
                    "300",
                    "--now",
                    "2026-06-12T09:00:00+00:00",
                    "--format",
                    "claim-checklist",
                ]
            )

        self.assertEqual(fresh_proc.returncode, 0, fresh_proc.stderr)
        self.assertIn("Next safe action: prepare_fix_and_claim_pr", fresh_proc.stdout)
        self.assertIn("Action code: prepare_fix_and_claim_pr", fresh_proc.stdout)
        self.assertIn("Attempts: 0", fresh_proc.stdout)
        self.assertIn("Assignees: 0", fresh_proc.stdout)
        self.assertIn("GO blockers: none", fresh_proc.stdout)
        self.assertIn("Recheck command: patchrail funded-issues fresh", fresh_proc.stdout)
        self.assertIn(f"--store {store}", fresh_proc.stdout)
        self.assertIn("--org example", fresh_proc.stdout)
        self.assertIn("--solver-status go_candidate", fresh_proc.stdout)
        self.assertIn("--min-usd 25", fresh_proc.stdout)
        self.assertIn("--max-usd 300", fresh_proc.stdout)
        self.assertIn("--format claim-checklist", fresh_proc.stdout)
        self.assertIn("Add `/claim #42` in the PR only after the PR is ready.", fresh_proc.stdout)

    def test_funded_issues_fresh_json_includes_next_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store.json"
            store.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.funded_issues.store.v1",
                        "source_schema_version": "patchrail.funded_issues.v1",
                        "read_only": True,
                        "blocked_actions": [],
                        "requirements": {"network_required": False},
                        "entries": {
                            "https://github.com/example/project/issues/42": {
                                "issue": {
                                    "id": "fresh-go",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#42",
                                    "issue_number": 42,
                                    "title": "Fix deterministic CI failure",
                                    "url": "https://github.com/example/project/issues/42",
                                    "funding": {
                                        "amount": 250,
                                        "currency": "USD",
                                        "display": "250 USD",
                                    },
                                    "opportunity_state": "active",
                                    "attempt_count": 0,
                                },
                                "first_seen": "2026-06-12T08:00:00+00:00",
                                "last_seen": "2026-06-12T08:00:00+00:00",
                                "last_checked": "2026-06-12T08:00:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                            "https://github.com/example/project/issues/43": {
                                "issue": {
                                    "id": "needs-review",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#43",
                                    "issue_number": 43,
                                    "title": "Clarify flaky integration test",
                                    "url": "https://github.com/example/project/issues/43",
                                    "funding": {"amount": 100, "currency": "USD"},
                                    "opportunity_state": "active",
                                },
                                "first_seen": "2026-06-12T08:10:00+00:00",
                                "last_seen": "2026-06-12T08:10:00+00:00",
                                "last_checked": "2026-06-12T08:10:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                            "https://github.com/example/project/issues/44": {
                                "issue": {
                                    "id": "skip",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#44",
                                    "issue_number": 44,
                                    "title": "Rewrite the whole CLI",
                                    "url": "https://github.com/example/project/issues/44",
                                    "funding": {"amount": 500, "currency": "USD"},
                                    "opportunity_state": "active",
                                    "attempt_count": 7,
                                },
                                "first_seen": "2026-06-12T08:20:00+00:00",
                                "last_seen": "2026-06-12T08:20:00+00:00",
                                "last_checked": "2026-06-12T08:20:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            fresh_proc = run_patchrail(
                [
                    "funded-issues",
                    "fresh",
                    "--store",
                    str(store),
                    "--hours",
                    "48",
                    "--now",
                    "2026-06-12T09:00:00+00:00",
                    "--format",
                    "json",
                ]
            )

        self.assertEqual(fresh_proc.returncode, 0, fresh_proc.stderr)
        payload = json.loads(fresh_proc.stdout)
        self.assertEqual(
            payload["solver_counts"],
            {"go_candidate": 1, "needs_review": 1, "no_go": 1},
        )
        self.assertEqual(
            payload["solver_counts_before_limit"],
            {"go_candidate": 1, "needs_review": 1, "no_go": 1},
        )
        self.assertEqual(payload["next_safe_action"], "prepare_fix_and_claim_pr")
        actions = {row["reference"]: row["next_action"] for row in payload["fresh"]}
        self.assertEqual(actions["example/project#42"], "prepare_fix_and_claim_pr")
        self.assertEqual(actions["example/project#43"], "manual_recheck:attempts_unknown")
        self.assertEqual(
            actions["example/project#44"], "skip:too_many_attempts,amount_out_of_range"
        )

    def test_funded_issues_fresh_can_filter_by_known_attempt_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store.json"
            store.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.funded_issues.store.v1",
                        "source_schema_version": "patchrail.funded_issues.v1",
                        "read_only": True,
                        "blocked_actions": [],
                        "requirements": {"network_required": False},
                        "entries": {
                            "https://github.com/example/project/issues/42": {
                                "issue": {
                                    "id": "fresh-go",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#42",
                                    "issue_number": 42,
                                    "title": "Fix deterministic CI failure",
                                    "url": "https://github.com/example/project/issues/42",
                                    "funding": {"amount": 250, "currency": "USD"},
                                    "opportunity_state": "active",
                                    "attempt_count": 3,
                                },
                                "first_seen": "2026-06-12T08:00:00+00:00",
                                "last_seen": "2026-06-12T08:00:00+00:00",
                                "last_checked": "2026-06-12T08:00:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                            "https://github.com/example/project/issues/43": {
                                "issue": {
                                    "id": "attempts-unknown",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#43",
                                    "issue_number": 43,
                                    "title": "Needs manual attempt check",
                                    "url": "https://github.com/example/project/issues/43",
                                    "funding": {"amount": 100, "currency": "USD"},
                                    "opportunity_state": "active",
                                },
                                "first_seen": "2026-06-12T08:10:00+00:00",
                                "last_seen": "2026-06-12T08:10:00+00:00",
                                "last_checked": "2026-06-12T08:10:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                            "https://github.com/example/project/issues/44": {
                                "issue": {
                                    "id": "too-contested",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#44",
                                    "issue_number": 44,
                                    "title": "Seven attempts already",
                                    "url": "https://github.com/example/project/issues/44",
                                    "funding": {"amount": 100, "currency": "USD"},
                                    "opportunity_state": "active",
                                    "attempt_count": 7,
                                },
                                "first_seen": "2026-06-12T08:20:00+00:00",
                                "last_seen": "2026-06-12T08:20:00+00:00",
                                "last_checked": "2026-06-12T08:20:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            proc = run_patchrail(
                [
                    "funded-issues",
                    "fresh",
                    "--store",
                    str(store),
                    "--hours",
                    "48",
                    "--max-attempts",
                    "3",
                    "--now",
                    "2026-06-12T09:00:00+00:00",
                    "--format",
                    "json",
                ]
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["max_attempts"], 3)
        self.assertEqual(payload["fresh_count"], 1)
        self.assertEqual(payload["fresh"][0]["reference"], "example/project#42")
        self.assertEqual(
            payload["solver_counts"], {"go_candidate": 1, "needs_review": 0, "no_go": 0}
        )

    def test_funded_issues_fresh_rejects_negative_max_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store.json"
            store.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.funded_issues.store.v1",
                        "source_schema_version": "patchrail.funded_issues.v1",
                        "read_only": True,
                        "blocked_actions": [],
                        "requirements": {"network_required": False},
                        "entries": {},
                    }
                ),
                encoding="utf-8",
            )

            proc = run_patchrail(
                [
                    "funded-issues",
                    "fresh",
                    "--store",
                    str(store),
                    "--max-attempts",
                    "-1",
                ]
            )

        self.assertEqual(proc.returncode, 1)
        self.assertIn("max_attempts must be at least 0", proc.stderr)

    def test_funded_issues_fresh_can_filter_by_min_age_minutes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store.json"
            store.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.funded_issues.store.v1",
                        "source_schema_version": "patchrail.funded_issues.v1",
                        "read_only": True,
                        "blocked_actions": [],
                        "requirements": {"network_required": False},
                        "entries": {
                            "https://github.com/example/project/issues/42": {
                                "issue": {
                                    "id": "stable-go",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#42",
                                    "issue_number": 42,
                                    "title": "Stable enough to inspect",
                                    "url": "https://github.com/example/project/issues/42",
                                    "funding": {"amount": 250, "currency": "USD"},
                                    "opportunity_state": "active",
                                    "attempt_count": 0,
                                },
                                "first_seen": "2026-06-12T08:15:00+00:00",
                                "last_seen": "2026-06-12T08:15:00+00:00",
                                "last_checked": "2026-06-12T08:15:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                            "https://github.com/example/project/issues/43": {
                                "issue": {
                                    "id": "too-new",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#43",
                                    "issue_number": 43,
                                    "title": "Label just appeared",
                                    "url": "https://github.com/example/project/issues/43",
                                    "funding": {"amount": 100, "currency": "USD"},
                                    "opportunity_state": "active",
                                    "attempt_count": 0,
                                },
                                "first_seen": "2026-06-12T08:50:00+00:00",
                                "last_seen": "2026-06-12T08:50:00+00:00",
                                "last_checked": "2026-06-12T08:50:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            proc = run_patchrail(
                [
                    "funded-issues",
                    "fresh",
                    "--store",
                    str(store),
                    "--hours",
                    "48",
                    "--min-age-minutes",
                    "30",
                    "--now",
                    "2026-06-12T09:00:00+00:00",
                    "--format",
                    "json",
                ]
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["min_age_minutes"], 30)
        self.assertEqual(payload["fresh_count"], 1)
        self.assertEqual(payload["fresh"][0]["reference"], "example/project#42")

    def test_funded_issues_fresh_rejects_negative_min_age_minutes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store.json"
            store.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.funded_issues.store.v1",
                        "source_schema_version": "patchrail.funded_issues.v1",
                        "read_only": True,
                        "blocked_actions": [],
                        "requirements": {"network_required": False},
                        "entries": {},
                    }
                ),
                encoding="utf-8",
            )

            proc = run_patchrail(
                [
                    "funded-issues",
                    "fresh",
                    "--store",
                    str(store),
                    "--min-age-minutes",
                    "-1",
                ]
            )

        self.assertEqual(proc.returncode, 1)
        self.assertIn("min_age_minutes must be at least 0", proc.stderr)

    def test_funded_issues_fresh_can_filter_by_recent_public_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store.json"
            store.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.funded_issues.store.v1",
                        "source_schema_version": "patchrail.funded_issues.v1",
                        "read_only": True,
                        "blocked_actions": [],
                        "requirements": {"network_required": False},
                        "entries": {
                            "https://github.com/example/project/issues/42": {
                                "issue": {
                                    "id": "recently-active",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#42",
                                    "issue_number": 42,
                                    "title": "Recently updated bounty",
                                    "url": "https://github.com/example/project/issues/42",
                                    "funding": {"amount": 250, "currency": "USD"},
                                    "opportunity_state": "active",
                                    "attempt_count": 0,
                                    "updated_at": "2026-06-12T08:00:00+00:00",
                                },
                                "first_seen": "2026-06-12T07:00:00+00:00",
                                "last_seen": "2026-06-12T07:00:00+00:00",
                                "last_checked": "2026-06-12T08:00:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                            "https://github.com/example/project/issues/43": {
                                "issue": {
                                    "id": "quiet",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#43",
                                    "issue_number": 43,
                                    "title": "Fresh but quiet bounty",
                                    "url": "https://github.com/example/project/issues/43",
                                    "funding": {"amount": 250, "currency": "USD"},
                                    "opportunity_state": "active",
                                    "attempt_count": 0,
                                    "updated_at": "2026-06-11T20:00:00+00:00",
                                },
                                "first_seen": "2026-06-12T07:30:00+00:00",
                                "last_seen": "2026-06-12T07:30:00+00:00",
                                "last_checked": "2026-06-12T07:30:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            proc = run_patchrail(
                [
                    "funded-issues",
                    "fresh",
                    "--store",
                    str(store),
                    "--hours",
                    "48",
                    "--max-updated-age-hours",
                    "4",
                    "--now",
                    "2026-06-12T09:00:00+00:00",
                    "--format",
                    "json",
                ]
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["max_updated_age_hours"], 4)
        self.assertEqual(payload["fresh_count"], 1)
        self.assertEqual(payload["fresh"][0]["reference"], "example/project#42")
        self.assertEqual(payload["fresh"][0]["updated_age_hours"], 1.0)

    def test_funded_issues_fresh_rejects_negative_max_updated_age_hours(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store.json"
            store.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.funded_issues.store.v1",
                        "source_schema_version": "patchrail.funded_issues.v1",
                        "read_only": True,
                        "blocked_actions": [],
                        "requirements": {"network_required": False},
                        "entries": {},
                    }
                ),
                encoding="utf-8",
            )

            proc = run_patchrail(
                [
                    "funded-issues",
                    "fresh",
                    "--store",
                    str(store),
                    "--max-updated-age-hours",
                    "-1",
                ]
            )

        self.assertEqual(proc.returncode, 1)
        self.assertIn("max_updated_age_hours must be at least 0", proc.stderr)

    def test_funded_issues_fresh_can_filter_by_max_assignees(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store.json"
            store.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.funded_issues.store.v1",
                        "source_schema_version": "patchrail.funded_issues.v1",
                        "read_only": True,
                        "blocked_actions": [],
                        "requirements": {"network_required": False},
                        "entries": {
                            "https://github.com/example/project/issues/42": {
                                "issue": {
                                    "id": "fresh-open",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#42",
                                    "issue_number": 42,
                                    "title": "Fresh unassigned bounty",
                                    "url": "https://github.com/example/project/issues/42",
                                    "funding": {"amount": 100, "currency": "USD"},
                                    "opportunity_state": "active",
                                    "attempt_count": 1,
                                },
                                "first_seen": "2026-06-12T08:00:00+00:00",
                                "last_seen": "2026-06-12T08:00:00+00:00",
                                "last_checked": "2026-06-12T08:00:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                            "https://github.com/example/project/issues/43": {
                                "issue": {
                                    "id": "assigned",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#43",
                                    "issue_number": 43,
                                    "title": "Already assigned bounty",
                                    "url": "https://github.com/example/project/issues/43",
                                    "funding": {"amount": 100, "currency": "USD"},
                                    "opportunity_state": "active",
                                    "attempt_count": 1,
                                    "assignee": "alice",
                                },
                                "first_seen": "2026-06-12T08:10:00+00:00",
                                "last_seen": "2026-06-12T08:10:00+00:00",
                                "last_checked": "2026-06-12T08:10:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            proc = run_patchrail(
                [
                    "funded-issues",
                    "fresh",
                    "--store",
                    str(store),
                    "--hours",
                    "48",
                    "--max-assignees",
                    "0",
                    "--now",
                    "2026-06-12T09:00:00+00:00",
                    "--format",
                    "json",
                ]
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["max_assignees"], 0)
        self.assertEqual(payload["fresh_count"], 1)
        self.assertEqual(payload["fresh"][0]["reference"], "example/project#42")

    def test_funded_issues_fresh_can_require_public_testability_signal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store.json"
            store.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.funded_issues.store.v1",
                        "source_schema_version": "patchrail.funded_issues.v1",
                        "read_only": True,
                        "blocked_actions": [],
                        "requirements": {"network_required": False},
                        "entries": {
                            "https://github.com/example/project/issues/42": {
                                "issue": {
                                    "id": "testable",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#42",
                                    "issue_number": 42,
                                    "title": "Fix deterministic CI failure",
                                    "url": "https://github.com/example/project/issues/42",
                                    "funding": {"amount": 100, "currency": "USD"},
                                    "opportunity_state": "active",
                                    "attempt_count": 1,
                                    "contribution_signals": [
                                        "reproduction included",
                                        "failing test described",
                                    ],
                                },
                                "first_seen": "2026-06-12T08:00:00+00:00",
                                "last_seen": "2026-06-12T08:00:00+00:00",
                                "last_checked": "2026-06-12T08:00:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                            "https://github.com/example/project/issues/43": {
                                "issue": {
                                    "id": "unclear",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#43",
                                    "issue_number": 43,
                                    "title": "Improve admin screen",
                                    "url": "https://github.com/example/project/issues/43",
                                    "funding": {"amount": 100, "currency": "USD"},
                                    "opportunity_state": "active",
                                    "attempt_count": 1,
                                    "contribution_signals": ["contribution guidelines linked"],
                                },
                                "first_seen": "2026-06-12T08:05:00+00:00",
                                "last_seen": "2026-06-12T08:05:00+00:00",
                                "last_checked": "2026-06-12T08:05:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            json_proc = run_patchrail(
                [
                    "funded-issues",
                    "fresh",
                    "--store",
                    str(store),
                    "--hours",
                    "48",
                    "--require-tests-signal",
                    "--now",
                    "2026-06-12T09:00:00+00:00",
                    "--format",
                    "json",
                ]
            )
            csv_proc = run_patchrail(
                [
                    "funded-issues",
                    "fresh",
                    "--store",
                    str(store),
                    "--hours",
                    "48",
                    "--require-tests-signal",
                    "--now",
                    "2026-06-12T09:00:00+00:00",
                    "--format",
                    "csv",
                ]
            )

        self.assertEqual(json_proc.returncode, 0, json_proc.stderr)
        payload = json.loads(json_proc.stdout)
        self.assertEqual(payload["require_tests_signal"], True)
        self.assertEqual(payload["fresh_count"], 1)
        self.assertEqual(payload["fresh"][0]["reference"], "example/project#42")
        self.assertEqual(payload["fresh"][0]["testability_signal"], True)

        self.assertEqual(csv_proc.returncode, 0, csv_proc.stderr)
        rows = list(csv.DictReader(io.StringIO(csv_proc.stdout)))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["reference"], "example/project#42")
        self.assertEqual(rows[0]["testability_signal"], "true")

    def test_funded_issues_fresh_rejects_negative_max_assignees(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store.json"
            store.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.funded_issues.store.v1",
                        "source_schema_version": "patchrail.funded_issues.v1",
                        "read_only": True,
                        "blocked_actions": [],
                        "requirements": {"network_required": False},
                        "entries": {},
                    }
                ),
                encoding="utf-8",
            )

            proc = run_patchrail(
                [
                    "funded-issues",
                    "fresh",
                    "--store",
                    str(store),
                    "--max-assignees",
                    "-1",
                ]
            )

        self.assertEqual(proc.returncode, 1)
        self.assertIn("max_assignees must be at least 0", proc.stderr)

    def test_funded_issues_fresh_can_signal_go_candidate_with_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store.json"
            store.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.funded_issues.store.v1",
                        "source_schema_version": "patchrail.funded_issues.v1",
                        "read_only": True,
                        "blocked_actions": [],
                        "requirements": {"network_required": False},
                        "entries": {
                            "https://github.com/example/project/issues/42": {
                                "issue": {
                                    "id": "fresh-go",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#42",
                                    "issue_number": 42,
                                    "title": "Fix deterministic CI failure",
                                    "url": "https://github.com/example/project/issues/42",
                                    "funding": {
                                        "amount": 250,
                                        "currency": "USD",
                                        "display": "250 USD",
                                    },
                                    "opportunity_state": "active",
                                    "attempt_count": 0,
                                },
                                "first_seen": "2026-06-12T08:00:00+00:00",
                                "last_seen": "2026-06-12T08:00:00+00:00",
                                "last_checked": "2026-06-12T08:00:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                            "https://github.com/example/project/issues/44": {
                                "issue": {
                                    "id": "skip",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#44",
                                    "issue_number": 44,
                                    "title": "Rewrite the whole CLI",
                                    "url": "https://github.com/example/project/issues/44",
                                    "funding": {"amount": 500, "currency": "USD"},
                                    "opportunity_state": "active",
                                    "attempt_count": 7,
                                },
                                "first_seen": "2026-06-12T08:20:00+00:00",
                                "last_seen": "2026-06-12T08:20:00+00:00",
                                "last_checked": "2026-06-12T08:20:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            go_proc = run_patchrail(
                [
                    "funded-issues",
                    "fresh",
                    "--store",
                    str(store),
                    "--hours",
                    "48",
                    "--now",
                    "2026-06-12T09:00:00+00:00",
                    "--format",
                    "json",
                    "--exit-code-on-go",
                ]
            )
            skip_proc = run_patchrail(
                [
                    "funded-issues",
                    "fresh",
                    "--store",
                    str(store),
                    "--hours",
                    "48",
                    "--solver-status",
                    "no_go",
                    "--now",
                    "2026-06-12T09:00:00+00:00",
                    "--format",
                    "json",
                    "--exit-code-on-go",
                ]
            )

        self.assertEqual(go_proc.returncode, 2, go_proc.stderr)
        go_payload = json.loads(go_proc.stdout)
        self.assertEqual(go_payload["solver_counts"]["go_candidate"], 1)
        self.assertEqual(skip_proc.returncode, 0, skip_proc.stderr)
        skip_payload = json.loads(skip_proc.stdout)
        self.assertEqual(skip_payload["solver_counts"]["go_candidate"], 0)
        self.assertEqual(skip_payload["solver_counts"]["no_go"], 1)

    def test_funded_issues_fresh_go_only_filters_to_claim_ready_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store.json"
            store.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.funded_issues.store.v1",
                        "source_schema_version": "patchrail.funded_issues.v1",
                        "read_only": True,
                        "blocked_actions": [],
                        "requirements": {"network_required": False},
                        "entries": {
                            "https://github.com/example/project/issues/42": {
                                "issue": {
                                    "id": "fresh-go",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#42",
                                    "issue_number": 42,
                                    "title": "Fix deterministic CI failure",
                                    "url": "https://github.com/example/project/issues/42",
                                    "funding": {
                                        "amount": 250,
                                        "currency": "USD",
                                        "display": "250 USD",
                                    },
                                    "opportunity_state": "active",
                                    "attempt_count": 0,
                                },
                                "first_seen": "2026-06-12T08:00:00+00:00",
                                "last_seen": "2026-06-12T08:00:00+00:00",
                                "last_checked": "2026-06-12T08:00:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                            "https://github.com/example/project/issues/43": {
                                "issue": {
                                    "id": "needs-review",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#43",
                                    "issue_number": 43,
                                    "title": "Clarify flaky integration test",
                                    "url": "https://github.com/example/project/issues/43",
                                    "funding": {"amount": 100, "currency": "USD"},
                                    "opportunity_state": "active",
                                },
                                "first_seen": "2026-06-12T08:10:00+00:00",
                                "last_seen": "2026-06-12T08:10:00+00:00",
                                "last_checked": "2026-06-12T08:10:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            go_proc = run_patchrail(
                [
                    "funded-issues",
                    "fresh",
                    "--store",
                    str(store),
                    "--hours",
                    "48",
                    "--now",
                    "2026-06-12T09:00:00+00:00",
                    "--format",
                    "json",
                    "--go-only",
                ]
            )
            conflict_proc = run_patchrail(
                [
                    "funded-issues",
                    "fresh",
                    "--store",
                    str(store),
                    "--hours",
                    "48",
                    "--now",
                    "2026-06-12T09:00:00+00:00",
                    "--solver-status",
                    "no_go",
                    "--go-only",
                ]
            )

        self.assertEqual(go_proc.returncode, 0, go_proc.stderr)
        payload = json.loads(go_proc.stdout)
        self.assertEqual(payload["solver_status"], "go_candidate")
        self.assertEqual(payload["fresh_count"], 1)
        self.assertEqual(
            payload["solver_counts"], {"go_candidate": 1, "needs_review": 0, "no_go": 0}
        )
        self.assertEqual(payload["fresh"][0]["reference"], "example/project#42")
        self.assertEqual(conflict_proc.returncode, 1)
        self.assertIn("--go-only cannot be combined", conflict_proc.stderr)

    def test_funded_issues_fresh_exports_csv_and_jsonl_for_operator_pipelines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store.json"
            store.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.funded_issues.store.v1",
                        "source_schema_version": "patchrail.funded_issues.v1",
                        "read_only": True,
                        "blocked_actions": [],
                        "requirements": {"network_required": False},
                        "entries": {
                            "https://github.com/example/project/issues/42": {
                                "issue": {
                                    "id": "fresh-go",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#42",
                                    "issue_number": 42,
                                    "title": "=fix deterministic CI failure",
                                    "url": "https://github.com/example/project/issues/42",
                                    "funding": {
                                        "amount": 250,
                                        "currency": "USD",
                                        "display": "250 USD",
                                    },
                                    "opportunity_state": "active",
                                    "attempt_count": 0,
                                },
                                "first_seen": "2026-06-12T08:00:00+00:00",
                                "last_seen": "2026-06-12T08:00:00+00:00",
                                "last_checked": "2026-06-12T08:00:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                            "https://github.com/example/project/issues/44": {
                                "issue": {
                                    "id": "skip",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#44",
                                    "issue_number": 44,
                                    "title": "Rewrite the whole CLI",
                                    "url": "https://github.com/example/project/issues/44",
                                    "funding": {"amount": 500, "currency": "USD"},
                                    "opportunity_state": "active",
                                    "attempt_count": 7,
                                },
                                "first_seen": "2026-06-12T08:20:00+00:00",
                                "last_seen": "2026-06-12T08:20:00+00:00",
                                "last_checked": "2026-06-12T08:20:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            base_args = [
                "funded-issues",
                "fresh",
                "--store",
                str(store),
                "--hours",
                "48",
                "--sort",
                "solver",
                "--now",
                "2026-06-12T09:00:00+00:00",
            ]
            csv_proc = run_patchrail([*base_args, "--format", "csv"])
            jsonl_proc = run_patchrail([*base_args, "--format", "jsonl"])

        self.assertEqual(csv_proc.returncode, 0, csv_proc.stderr)
        rows = list(csv.DictReader(io.StringIO(csv_proc.stdout)))
        self.assertEqual(
            [row["reference"] for row in rows], ["example/project#42", "example/project#44"]
        )
        self.assertEqual(rows[0]["title"], "'=fix deterministic CI failure")
        self.assertEqual(rows[0]["solver_status"], "go_candidate")
        self.assertEqual(rows[0]["next_action"], "prepare_fix_and_claim_pr")
        self.assertEqual(rows[1]["solver_status"], "no_go")
        self.assertEqual(rows[1]["go_blockers"], "too_many_attempts; amount_out_of_range")
        self.assertEqual(rows[1]["next_action"], "skip:too_many_attempts,amount_out_of_range")

        self.assertEqual(jsonl_proc.returncode, 0, jsonl_proc.stderr)
        jsonl_rows = [json.loads(line) for line in jsonl_proc.stdout.splitlines()]
        self.assertEqual(jsonl_rows[0]["reference"], "example/project#42")
        self.assertEqual(jsonl_rows[0]["solver_status"], "go_candidate")
        self.assertEqual(jsonl_rows[0]["next_action"], "prepare_fix_and_claim_pr")
        self.assertEqual(jsonl_rows[1]["solver_status"], "no_go")
        self.assertEqual(jsonl_rows[1]["go_blockers"], ["too_many_attempts", "amount_out_of_range"])

    def test_funded_issues_fresh_exports_env_summary_for_supervisors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store.json"
            store.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.funded_issues.store.v1",
                        "source_schema_version": "patchrail.funded_issues.v1",
                        "read_only": True,
                        "blocked_actions": [],
                        "requirements": {"network_required": False},
                        "entries": {
                            "https://github.com/example/project/issues/42": {
                                "issue": {
                                    "id": "fresh-go",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#42",
                                    "issue_number": 42,
                                    "title": "Fix deterministic CI failure",
                                    "url": "https://github.com/example/project/issues/42",
                                    "funding": {
                                        "amount": 250,
                                        "currency": "USD",
                                        "display": "250 USD",
                                    },
                                    "opportunity_state": "active",
                                    "attempt_count": 0,
                                },
                                "first_seen": "2026-06-12T08:00:00+00:00",
                                "last_seen": "2026-06-12T08:00:00+00:00",
                                "last_checked": "2026-06-12T08:00:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                            "https://github.com/example/project/issues/44": {
                                "issue": {
                                    "id": "skip",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#44",
                                    "issue_number": 44,
                                    "title": "Rewrite the whole CLI",
                                    "url": "https://github.com/example/project/issues/44",
                                    "funding": {"amount": 500, "currency": "USD"},
                                    "opportunity_state": "active",
                                    "attempt_count": 7,
                                },
                                "first_seen": "2026-06-12T08:20:00+00:00",
                                "last_seen": "2026-06-12T08:20:00+00:00",
                                "last_checked": "2026-06-12T08:20:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            proc = run_patchrail(
                [
                    "funded-issues",
                    "fresh",
                    "--store",
                    str(store),
                    "--hours",
                    "48",
                    "--sort",
                    "solver",
                    "--now",
                    "2026-06-12T09:00:00+00:00",
                    "--format",
                    "env",
                ]
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = dict(shlex.split(line)[0].split("=", 1) for line in proc.stdout.splitlines())
        self.assertEqual(lines["PATCHRAIL_FUNDED_SCHEMA"], "patchrail.funded_issues.fresh.v1")
        self.assertEqual(lines["PATCHRAIL_FUNDED_FRESH_COUNT"], "2")
        self.assertEqual(lines["PATCHRAIL_FUNDED_GO_COUNT"], "1")
        self.assertEqual(lines["PATCHRAIL_FUNDED_NO_GO_COUNT"], "1")
        self.assertEqual(lines["PATCHRAIL_FUNDED_NEXT_SAFE_ACTION"], "prepare_fix_and_claim_pr")
        self.assertEqual(lines["PATCHRAIL_FUNDED_FIRST_GO_REFERENCE"], "example/project#42")
        self.assertEqual(
            lines["PATCHRAIL_FUNDED_FIRST_GO_URL"],
            "https://github.com/example/project/issues/42",
        )
        self.assertEqual(lines["PATCHRAIL_FUNDED_FIRST_GO_NEXT_ACTION"], "prepare_fix_and_claim_pr")

    def test_funded_issues_fresh_exports_single_line_signal_for_supervisors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store.json"
            store.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.funded_issues.store.v1",
                        "source_schema_version": "patchrail.funded_issues.v1",
                        "read_only": True,
                        "blocked_actions": [],
                        "requirements": {"network_required": False},
                        "entries": {
                            "https://github.com/example/project/issues/42": {
                                "issue": {
                                    "id": "fresh-go",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#42",
                                    "issue_number": 42,
                                    "title": "Fix deterministic CI failure",
                                    "url": "https://github.com/example/project/issues/42",
                                    "funding": {
                                        "amount": 250,
                                        "currency": "USD",
                                        "display": "250 USD",
                                    },
                                    "opportunity_state": "active",
                                    "attempt_count": 0,
                                },
                                "first_seen": "2026-06-12T08:00:00+00:00",
                                "last_seen": "2026-06-12T08:00:00+00:00",
                                "last_checked": "2026-06-12T08:00:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            empty_store = Path(tmp) / "empty-store.json"
            empty_store.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.funded_issues.store.v1",
                        "source_schema_version": "patchrail.funded_issues.v1",
                        "read_only": True,
                        "blocked_actions": [],
                        "requirements": {"network_required": False},
                        "entries": {},
                    }
                ),
                encoding="utf-8",
            )

            claim_proc = run_patchrail(
                [
                    "funded-issues",
                    "fresh",
                    "--store",
                    str(store),
                    "--hours",
                    "48",
                    "--now",
                    "2026-06-12T09:00:00+00:00",
                    "--format",
                    "signal",
                ]
            )
            wait_proc = run_patchrail(
                [
                    "funded-issues",
                    "fresh",
                    "--store",
                    str(empty_store),
                    "--hours",
                    "48",
                    "--now",
                    "2026-06-12T09:00:00+00:00",
                    "--format",
                    "signal",
                ]
            )

        self.assertEqual(claim_proc.returncode, 0, claim_proc.stderr)
        self.assertEqual(
            claim_proc.stdout,
            (
                "CLAIM_READY count=1 reference='example/project#42' "
                "url=https://github.com/example/project/issues/42 "
                "next_action=prepare_fix_and_claim_pr\n"
            ),
        )
        self.assertEqual(wait_proc.returncode, 0, wait_proc.stderr)
        self.assertEqual(
            wait_proc.stdout,
            "WAIT count=0 next_action=wait_for_fresh_funded_issue\n",
        )

    def test_funded_issues_fresh_operator_brief_groups_next_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store.json"
            store.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.funded_issues.store.v1",
                        "source_schema_version": "patchrail.funded_issues.v1",
                        "read_only": True,
                        "blocked_actions": [],
                        "requirements": {"network_required": False},
                        "entries": {
                            "https://github.com/example/project/issues/42": {
                                "issue": {
                                    "id": "fresh-go",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#42",
                                    "issue_number": 42,
                                    "title": "Fix deterministic CI failure",
                                    "url": "https://github.com/example/project/issues/42",
                                    "funding": {
                                        "amount": 250,
                                        "currency": "USD",
                                        "display": "250 USD",
                                    },
                                    "opportunity_state": "active",
                                    "attempt_count": 0,
                                },
                                "first_seen": "2026-06-12T08:00:00+00:00",
                                "last_seen": "2026-06-12T08:00:00+00:00",
                                "last_checked": "2026-06-12T08:00:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                            "https://github.com/example/project/issues/43": {
                                "issue": {
                                    "id": "needs-review",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#43",
                                    "issue_number": 43,
                                    "title": "Clarify flaky integration test",
                                    "url": "https://github.com/example/project/issues/43",
                                    "funding": {"amount": 100, "currency": "USD"},
                                    "opportunity_state": "active",
                                },
                                "first_seen": "2026-06-12T08:10:00+00:00",
                                "last_seen": "2026-06-12T08:10:00+00:00",
                                "last_checked": "2026-06-12T08:10:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                            "https://github.com/example/project/issues/44": {
                                "issue": {
                                    "id": "skip",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#44",
                                    "issue_number": 44,
                                    "title": "Rewrite the whole CLI",
                                    "url": "https://github.com/example/project/issues/44",
                                    "funding": {"amount": 500, "currency": "USD"},
                                    "opportunity_state": "active",
                                    "attempt_count": 7,
                                },
                                "first_seen": "2026-06-12T08:20:00+00:00",
                                "last_seen": "2026-06-12T08:20:00+00:00",
                                "last_checked": "2026-06-12T08:20:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            fresh_proc = run_patchrail(
                [
                    "funded-issues",
                    "fresh",
                    "--store",
                    str(store),
                    "--hours",
                    "48",
                    "--now",
                    "2026-06-12T09:00:00+00:00",
                    "--format",
                    "operator-brief",
                ]
            )

        self.assertEqual(fresh_proc.returncode, 0, fresh_proc.stderr)
        self.assertIn("GO: 1  Recheck: 1  Skip: 1", fresh_proc.stdout)
        self.assertIn("NEXT_SAFE_ACTION: prepare_fix_and_claim_pr", fresh_proc.stdout)
        self.assertIn("CLAIM_READY", fresh_proc.stdout)
        self.assertIn("Recheck: patchrail funded-issues fresh", fresh_proc.stdout)
        self.assertIn(
            "Next: branch, minimal fix, target tests, PR, then /claim.", fresh_proc.stdout
        )
        self.assertIn("RECHECK_ONLY", fresh_proc.stdout)
        self.assertIn("Code: manual_recheck:attempts_unknown", fresh_proc.stdout)
        self.assertIn("SKIP", fresh_proc.stdout)
        self.assertIn(
            "example/project#44: too_many_attempts, amount_out_of_range", fresh_proc.stdout
        )
        self.assertIn("Boundary: local read-only triage only", fresh_proc.stdout)

    def test_funded_issues_fresh_exports_github_annotations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store.json"
            store.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.funded_issues.store.v1",
                        "source_schema_version": "patchrail.funded_issues.v1",
                        "read_only": True,
                        "blocked_actions": [],
                        "requirements": {"network_required": False},
                        "entries": {
                            "https://github.com/example/project/issues/42": {
                                "issue": {
                                    "id": "fresh-go",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#42",
                                    "issue_number": 42,
                                    "title": "Fix deterministic CI failure",
                                    "url": "https://github.com/example/project/issues/42",
                                    "funding": {"amount": 250, "currency": "USD"},
                                    "opportunity_state": "active",
                                    "attempt_count": 0,
                                },
                                "first_seen": "2026-06-12T08:00:00+00:00",
                                "last_seen": "2026-06-12T08:00:00+00:00",
                                "last_checked": "2026-06-12T08:00:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                            "https://github.com/example/project/issues/43": {
                                "issue": {
                                    "id": "needs-review",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#43",
                                    "issue_number": 43,
                                    "title": "Clarify flaky integration test",
                                    "url": "https://github.com/example/project/issues/43",
                                    "funding": {"amount": 100, "currency": "USD"},
                                    "opportunity_state": "active",
                                },
                                "first_seen": "2026-06-12T08:10:00+00:00",
                                "last_seen": "2026-06-12T08:10:00+00:00",
                                "last_checked": "2026-06-12T08:10:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                            "https://github.com/example/project/issues/44": {
                                "issue": {
                                    "id": "skip",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#44",
                                    "issue_number": 44,
                                    "title": "Rewrite the whole CLI",
                                    "url": "https://github.com/example/project/issues/44",
                                    "funding": {"amount": 500, "currency": "USD"},
                                    "opportunity_state": "active",
                                    "attempt_count": 7,
                                },
                                "first_seen": "2026-06-12T08:20:00+00:00",
                                "last_seen": "2026-06-12T08:20:00+00:00",
                                "last_checked": "2026-06-12T08:20:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            proc = run_patchrail(
                [
                    "funded-issues",
                    "fresh",
                    "--store",
                    str(store),
                    "--hours",
                    "48",
                    "--now",
                    "2026-06-12T09:00:00+00:00",
                    "--format",
                    "github-annotations",
                ]
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = proc.stdout.splitlines()
        self.assertEqual(len(lines), 3)
        joined = "\n".join(lines)
        self.assertIn("::warning title=PatchRail claim-ready funded issue::", joined)
        self.assertIn("go_candidate: example/project#42", joined)
        self.assertIn("next=prepare_fix_and_claim_pr", joined)
        self.assertIn("::notice title=PatchRail funded issue needs recheck::", joined)
        self.assertIn("needs_review: example/project#43", joined)
        self.assertIn("blockers=attempts_unknown", joined)
        self.assertIn("::notice title=PatchRail funded issue skipped::", joined)
        self.assertIn("no_go: example/project#44", joined)
        self.assertIn("too_many_attempts, amount_out_of_range", joined)

    def test_funded_issues_fresh_exports_read_only_recheck_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store.json"
            store.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.funded_issues.store.v1",
                        "source_schema_version": "patchrail.funded_issues.v1",
                        "read_only": True,
                        "blocked_actions": [],
                        "requirements": {"network_required": False},
                        "entries": {
                            "https://github.com/example/project/issues/42": {
                                "issue": {
                                    "id": "fresh-go",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#42",
                                    "issue_number": 42,
                                    "title": "Fix deterministic CI failure",
                                    "url": "https://github.com/example/project/issues/42",
                                    "funding": {
                                        "amount": 250,
                                        "currency": "USD",
                                        "display": "250 USD",
                                    },
                                    "opportunity_state": "active",
                                    "attempt_count": 0,
                                },
                                "first_seen": "2026-06-12T08:00:00+00:00",
                                "last_seen": "2026-06-12T08:00:00+00:00",
                                "last_checked": "2026-06-12T08:00:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                            "https://github.com/example/project/issues/43": {
                                "issue": {
                                    "id": "needs-review",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#43",
                                    "issue_number": 43,
                                    "title": "Clarify flaky integration test",
                                    "url": "https://github.com/example/project/issues/43",
                                    "funding": {"amount": 100, "currency": "USD"},
                                    "opportunity_state": "active",
                                },
                                "first_seen": "2026-06-12T08:10:00+00:00",
                                "last_seen": "2026-06-12T08:10:00+00:00",
                                "last_checked": "2026-06-12T08:10:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                            "https://github.com/example/project/issues/44": {
                                "issue": {
                                    "id": "skip",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#44",
                                    "issue_number": 44,
                                    "title": "Rewrite the whole CLI",
                                    "url": "https://github.com/example/project/issues/44",
                                    "funding": {"amount": 500, "currency": "USD"},
                                    "opportunity_state": "active",
                                    "attempt_count": 7,
                                },
                                "first_seen": "2026-06-12T08:20:00+00:00",
                                "last_seen": "2026-06-12T08:20:00+00:00",
                                "last_checked": "2026-06-12T08:20:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            proc = run_patchrail(
                [
                    "funded-issues",
                    "fresh",
                    "--store",
                    str(store),
                    "--hours",
                    "48",
                    "--now",
                    "2026-06-12T09:00:00+00:00",
                    "--format",
                    "recheck-commands",
                ]
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("gh issue view 42 --repo example/project", proc.stdout)
        self.assertIn("gh issue view 43 --repo example/project", proc.stdout)
        self.assertNotIn("gh issue view 44", proc.stdout)
        self.assertIn("--solver-status go_candidate", proc.stdout)
        self.assertIn("--solver-status needs_review", proc.stdout)
        self.assertNotIn("gh pr create", proc.stdout)
        self.assertNotIn("gh issue comment", proc.stdout)
        self.assertNotIn("/claim", proc.stdout)

    def test_funded_issues_fresh_exports_short_read_only_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store.json"
            store.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.funded_issues.store.v1",
                        "source_schema_version": "patchrail.funded_issues.v1",
                        "read_only": True,
                        "blocked_actions": [],
                        "requirements": {"network_required": False},
                        "entries": {
                            "https://github.com/example/project/issues/42": {
                                "issue": {
                                    "id": "fresh-go",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#42",
                                    "issue_number": 42,
                                    "title": "Fix deterministic CI failure",
                                    "url": "https://github.com/example/project/issues/42",
                                    "funding": {
                                        "amount": 250,
                                        "currency": "USD",
                                        "display": "250 USD",
                                    },
                                    "opportunity_state": "active",
                                    "attempt_count": 0,
                                },
                                "first_seen": "2026-06-12T08:00:00+00:00",
                                "last_seen": "2026-06-12T08:00:00+00:00",
                                "last_checked": "2026-06-12T08:00:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                            "https://github.com/example/project/issues/43": {
                                "issue": {
                                    "id": "needs-review",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#43",
                                    "issue_number": 43,
                                    "title": "Clarify flaky integration test",
                                    "url": "https://github.com/example/project/issues/43",
                                    "funding": {"amount": 100, "currency": "USD"},
                                    "opportunity_state": "active",
                                },
                                "first_seen": "2026-06-12T08:10:00+00:00",
                                "last_seen": "2026-06-12T08:10:00+00:00",
                                "last_checked": "2026-06-12T08:10:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                            "https://github.com/example/project/issues/44": {
                                "issue": {
                                    "id": "skip",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#44",
                                    "issue_number": 44,
                                    "title": "Rewrite the whole CLI",
                                    "url": "https://github.com/example/project/issues/44",
                                    "funding": {"amount": 500, "currency": "USD"},
                                    "opportunity_state": "active",
                                    "attempt_count": 7,
                                },
                                "first_seen": "2026-06-12T08:20:00+00:00",
                                "last_seen": "2026-06-12T08:20:00+00:00",
                                "last_checked": "2026-06-12T08:20:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            proc = run_patchrail(
                [
                    "funded-issues",
                    "fresh",
                    "--store",
                    str(store),
                    "--hours",
                    "48",
                    "--now",
                    "2026-06-12T09:00:00+00:00",
                    "--format",
                    "digest",
                ]
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(len(proc.stdout.splitlines()), 8)
        self.assertIn("CLAIM_READY: fresh=3 go=1 recheck=1 skip=1", proc.stdout)
        self.assertIn("Candidate: example/project#42 (250 USD)", proc.stdout)
        self.assertIn("Recheck: gh issue view 42 --repo example/project", proc.stdout)
        self.assertIn("Boundary: read-only digest", proc.stdout)
        self.assertNotIn("gh pr create", proc.stdout)
        self.assertNotIn("gh issue comment", proc.stdout)
        self.assertNotIn("/claim", proc.stdout)

    def test_funded_issues_fresh_exports_claim_packet_for_solver_worker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store.json"
            store.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.funded_issues.store.v1",
                        "source_schema_version": "patchrail.funded_issues.v1",
                        "read_only": True,
                        "blocked_actions": [],
                        "requirements": {"network_required": False},
                        "entries": {
                            "https://github.com/example/project/issues/42": {
                                "issue": {
                                    "id": "fresh-go",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#42",
                                    "issue_number": 42,
                                    "title": "Fix deterministic CI failure",
                                    "url": "https://github.com/example/project/issues/42",
                                    "funding": {
                                        "amount": 250,
                                        "currency": "USD",
                                        "display": "250 USD",
                                    },
                                    "opportunity_state": "active",
                                    "attempt_count": 0,
                                },
                                "first_seen": "2026-06-12T08:00:00+00:00",
                                "last_seen": "2026-06-12T08:00:00+00:00",
                                "last_checked": "2026-06-12T08:00:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                            "https://github.com/example/project/issues/43": {
                                "issue": {
                                    "id": "needs-review",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#43",
                                    "issue_number": 43,
                                    "title": "Clarify flaky integration test",
                                    "url": "https://github.com/example/project/issues/43",
                                    "funding": {"amount": 100, "currency": "USD"},
                                    "opportunity_state": "active",
                                },
                                "first_seen": "2026-06-12T08:10:00+00:00",
                                "last_seen": "2026-06-12T08:10:00+00:00",
                                "last_checked": "2026-06-12T08:10:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            proc = run_patchrail(
                [
                    "funded-issues",
                    "fresh",
                    "--store",
                    str(store),
                    "--hours",
                    "48",
                    "--now",
                    "2026-06-12T09:00:00+00:00",
                    "--format",
                    "claim-packet",
                ]
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        packet = json.loads(proc.stdout)
        self.assertEqual(packet["schema_version"], "patchrail.funded_issues.claim_packet.v1")
        self.assertTrue(packet["read_only"])
        self.assertIn("automatic_pull_requests", packet["blocked_actions"])
        self.assertIn("automatic_claim_comments", packet["blocked_actions"])
        self.assertEqual(packet["go_count"], 1)
        self.assertEqual(len(packet["candidates"]), 1)
        candidate = packet["candidates"][0]
        self.assertEqual(candidate["reference"], "example/project#42")
        self.assertEqual(candidate["repository"], "example/project")
        self.assertEqual(candidate["issue_number"], "42")
        self.assertEqual(candidate["go_blockers"], [])
        self.assertIn(
            "gh issue view 42 --repo example/project", candidate["readonly_recheck_command"]
        )
        self.assertIn("--format claim-checklist", candidate["local_filter_command"])
        self.assertIn("only after the branch", candidate["claim_instruction"])
        self.assertNotIn("gh pr create", proc.stdout)
        self.assertNotIn("gh issue comment", proc.stdout)

    def test_funded_issues_fresh_exports_solver_brief_for_local_fix_prep(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "store.json"
            store.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.funded_issues.store.v1",
                        "source_schema_version": "patchrail.funded_issues.v1",
                        "read_only": True,
                        "blocked_actions": [],
                        "requirements": {"network_required": False},
                        "entries": {
                            "https://github.com/example/project/issues/42": {
                                "issue": {
                                    "id": "fresh-go",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#42",
                                    "issue_number": 42,
                                    "title": "Fix deterministic CI failure",
                                    "url": "https://github.com/example/project/issues/42",
                                    "funding": {
                                        "amount": 250,
                                        "currency": "USD",
                                        "display": "250 USD",
                                    },
                                    "opportunity_state": "active",
                                    "attempt_count": 0,
                                },
                                "first_seen": "2026-06-12T08:00:00+00:00",
                                "last_seen": "2026-06-12T08:00:00+00:00",
                                "last_checked": "2026-06-12T08:00:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                            "https://github.com/example/project/issues/43": {
                                "issue": {
                                    "id": "needs-review",
                                    "platform": "github",
                                    "repository": "example/project",
                                    "reference": "example/project#43",
                                    "issue_number": 43,
                                    "title": "Clarify flaky integration test",
                                    "url": "https://github.com/example/project/issues/43",
                                    "funding": {"amount": 100, "currency": "USD"},
                                    "opportunity_state": "active",
                                },
                                "first_seen": "2026-06-12T08:10:00+00:00",
                                "last_seen": "2026-06-12T08:10:00+00:00",
                                "last_checked": "2026-06-12T08:10:00+00:00",
                                "state": "active",
                                "state_history": [],
                                "noise_flags": [],
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            proc = run_patchrail(
                [
                    "funded-issues",
                    "fresh",
                    "--store",
                    str(store),
                    "--hours",
                    "48",
                    "--now",
                    "2026-06-12T09:00:00+00:00",
                    "--format",
                    "solver-brief",
                ]
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("# PatchRail funded-issues solver brief", proc.stdout)
        self.assertIn("GO candidates: `1`", proc.stdout)
        self.assertIn("## Candidate 1: example/project#42", proc.stdout)
        self.assertIn("- Repo: `example/project`", proc.stdout)
        self.assertIn("- Issue: `#42`", proc.stdout)
        self.assertIn("- Branch: `patchrail/example-project-42`", proc.stdout)
        self.assertIn("gh issue view 42 --repo example/project", proc.stdout)
        self.assertIn("--format claim-checklist", proc.stdout)
        self.assertIn("Open a PR only after local checks pass", proc.stdout)
        self.assertIn("no automatic PR, claim comment", proc.stdout)
        self.assertNotIn("example/project#43", proc.stdout)
        self.assertNotIn("gh pr create", proc.stdout)
        self.assertNotIn("gh issue comment", proc.stdout)

    def test_funded_issues_list_can_filter_by_opportunity_state(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "list",
                "--source",
                "examples/funded-issues-readonly/issues.json",
                "--include-risky",
                "--opportunity-state",
                "closed",
                "--format",
                "json",
            ]
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["total_loaded"], 2)
        self.assertEqual(payload["total_returned"], 1)
        self.assertEqual(payload["issues"][0]["reference"], "example/toolkit#17")
        self.assertEqual(payload["issues"][0]["opportunity_state"], "closed")
        self.assertFalse(payload["issues"][0]["safe_to_list"])

    def test_funded_issues_list_can_filter_by_risk_level(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "list",
                "--source",
                "examples/funded-issues-readonly/issues.json",
                "--include-risky",
                "--risk-level",
                "high",
                "--format",
                "json",
            ]
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["total_loaded"], 2)
        self.assertEqual(payload["total_returned"], 1)
        self.assertEqual(payload["issues"][0]["reference"], "example/toolkit#17")
        self.assertEqual(payload["issues"][0]["risk_level"], "high")
        self.assertFalse(payload["issues"][0]["safe_to_list"])

    def test_funded_issues_list_csv_neutralizes_formula_cells(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "issues.json"
            source.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.funded_issues.v1",
                        "issues": [
                            {
                                "id": "formula-title",
                                "platform": "github",
                                "repository": "example/formula",
                                "issue_number": 9,
                                "title": '=IMPORTDATA("https://example.invalid")',
                                "url": "https://github.com/example/formula/issues/9",
                                "funding": {"amount": 100, "currency": "USD"},
                                "language": "python",
                                "labels": ["bug"],
                                "risk_flags": [],
                                "contribution_guidelines_url": (
                                    "https://github.com/example/formula/blob/main/CONTRIBUTING.md"
                                ),
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            proc = run_patchrail(
                [
                    "funded-issues",
                    "list",
                    "--source",
                    str(source),
                    "--format",
                    "csv",
                ]
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        rows = list(csv.DictReader(io.StringIO(proc.stdout)))
        self.assertEqual(rows[0]["title"], '\'=IMPORTDATA("https://example.invalid")')

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
        self.assertEqual(safe_issue["opportunity_state"], "active")
        self.assertEqual(safe_issue["risk_level"], "low")
        self.assertIn("contribution guidelines linked", safe_issue["contribution_signals"])
        risky_issue = payload["issues"][1]
        self.assertEqual(risky_issue["reference"], "example/toolkit#17")
        self.assertEqual(risky_issue["opportunity_state"], "closed")
        self.assertEqual(risky_issue["risk_level"], "high")
        self.assertIn("closed_or_inactive", risky_issue["risk_flags"])
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

    def _import_records(self, records: list[dict]) -> list[dict]:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "export.json"
            source.write_text(json.dumps(records), encoding="utf-8")
            payload = import_provider_export("github", source)
        return payload["issues"]

    def test_import_infers_currency_from_symbol(self) -> None:
        issues = self._import_records(
            [
                {"repository": "ex/a", "issue_number": 1, "funding": {"amount": "€500"}},
                {"repository": "ex/b", "issue_number": 2, "funding": {"amount": "£750"}},
                {"repository": "ex/c", "issue_number": 3, "funding": {"amount": "¥1000"}},
            ]
        )
        self.assertEqual(issues[0]["funding"]["amount"], 500.0)
        self.assertEqual(issues[0]["funding"]["currency"], "EUR")
        self.assertEqual(issues[1]["funding"]["currency"], "GBP")
        self.assertEqual(issues[2]["funding"]["currency"], "JPY")

    def test_import_parses_dollar_prefixed_amount_as_usd(self) -> None:
        issues = self._import_records(
            [{"repository": "ex/a", "issue_number": 1, "bounty_amount": "$1,000"}]
        )
        self.assertEqual(issues[0]["funding"]["amount"], 1000.0)
        self.assertEqual(issues[0]["funding"]["currency"], "USD")

    def test_import_reads_trailing_currency_code(self) -> None:
        issues = self._import_records(
            [{"repository": "ex/a", "issue_number": 1, "bounty": {"amount": "750 GBP"}}]
        )
        self.assertEqual(issues[0]["funding"]["amount"], 750.0)
        self.assertEqual(issues[0]["funding"]["currency"], "GBP")

    def test_import_explicit_currency_field_beats_symbol(self) -> None:
        issues = self._import_records(
            [
                {
                    "repository": "ex/a",
                    "issue_number": 1,
                    "funding": {"amount": "€500", "currency": "usd"},
                }
            ]
        )
        self.assertEqual(issues[0]["funding"]["amount"], 500.0)
        self.assertEqual(issues[0]["funding"]["currency"], "USD")

    def test_funded_issues_validate_passes_clean_local_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "clean-funded-issues.json"
            source.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.funded_issues.v1",
                        "issues": [
                            {
                                "id": "clean-issue",
                                "platform": "polar",
                                "repository": "example/clean",
                                "issue_number": 12,
                                "title": "Fix reproducible CLI regression",
                                "url": "https://github.com/example/clean/issues/12",
                                "funding": {"amount": 250, "currency": "USD"},
                                "language": "python",
                                "opportunity_state": "active",
                                "labels": ["bug"],
                                "contribution_signals": ["reproduction included"],
                                "risk_flags": [],
                                "contribution_guidelines_url": (
                                    "https://github.com/example/clean/blob/main/CONTRIBUTING.md"
                                ),
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            proc = run_patchrail(
                ["funded-issues", "validate", "--source", str(source), "--format", "json"]
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["schema_version"], "patchrail.funded_issues.validation.v1")
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["warning_count"], 0)
        self.assertEqual(payload["counts"]["low_risk"], 1)
        self.assertEqual(payload["counts"]["active"], 1)
        self.assertEqual(payload["counts"]["stale"], 0)
        self.assertEqual(payload["counts"]["closed"], 0)
        self.assertEqual(payload["requirements"]["network_required"], False)
        self.assertEqual(payload["requirements"]["github_write_permission_required"], False)

    def test_funded_issues_validate_warns_on_review_gaps_without_strict_failure(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "validate",
                "--source",
                "examples/funded-issues-readonly/issues.json",
                "--format",
                "json",
            ]
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "needs_review")
        self.assertGreater(payload["warning_count"], 0)
        self.assertIn("example/toolkit#17", payload["warnings"]["high_risk"])
        self.assertIn("example/toolkit#17", payload["warnings"]["missing_contribution_guidelines"])
        self.assertIn("example/toolkit#17", payload["warnings"]["stale_or_closed"])
        self.assertIn("automatic_claims", payload["blocked_actions"])
        self.assertIn("read-only", payload["boundary"])

    def test_funded_issues_validate_strict_fails_on_review_warnings(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "validate",
                "--source",
                "examples/funded-issues-readonly/issues.json",
                "--strict",
                "--format",
                "json",
            ]
        )

        self.assertEqual(proc.returncode, 1)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["strict"])
        self.assertEqual(payload["status"], "needs_review")
        self.assertGreater(payload["warning_count"], 0)

    def test_funded_issues_validate_returns_structured_invalid_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "invalid-funded-issues.json"
            source.write_text(
                json.dumps({"schema_version": "wrong.version", "issues": []}),
                encoding="utf-8",
            )

            proc = run_patchrail(
                ["funded-issues", "validate", "--source", str(source), "--format", "json"]
            )

        self.assertEqual(proc.returncode, 1)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "invalid")
        self.assertEqual(payload["total_loaded"], 0)
        self.assertFalse(payload["requirements"]["network_required"])
        self.assertIn("patchrail.funded_issues.v1", payload["errors"][0])

    def test_funded_issues_report_summarizes_coverage_and_no_go_moat(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "report",
                "--source",
                "examples/funded-issues-readonly/issues.json",
                "--format",
                "json",
            ]
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["schema_version"], "patchrail.funded_issues.report.v1")
        self.assertEqual(payload["read_only"], True)
        self.assertEqual(payload["totals"]["loaded"], 2)
        self.assertEqual(payload["totals"]["in_scope"], 2)
        self.assertEqual(payload["totals"]["safe_to_list"], 1)
        self.assertEqual(payload["totals"]["high_risk"], 1)
        self.assertEqual(payload["breakdown"]["risk_levels"], {"high": 1, "low": 1})
        self.assertEqual(payload["breakdown"]["platforms"], {"algora": 1, "polar": 1})
        self.assertEqual(payload["breakdown"]["opportunity_states"], {"active": 1, "closed": 1})
        self.assertEqual(payload["no_go_moat"]["high_risk_or_excluded"], 1)
        self.assertEqual(payload["no_go_moat"]["ambiguous_scope"], 1)
        self.assertEqual(payload["no_go_moat"]["spam_attractive"], 1)
        self.assertEqual(payload["no_go_moat"]["stale_or_closed"], 1)
        self.assertEqual(payload["decision_summary"]["candidate_rows"], 1)
        self.assertEqual(payload["decision_summary"]["no_go_rows"], 1)
        self.assertEqual(payload["decision_summary"]["verification_needed"], 0)
        self.assertEqual(payload["decision_summary"]["authorization_needed"], 0)
        self.assertEqual(payload["decision_summary"]["gate_counts"]["go_after_recheck"], 1)
        self.assertEqual(payload["decision_summary"]["gate_counts"]["no_go"], 1)
        self.assertIn(
            "Review go-after-recheck",
            payload["decision_summary"]["recommended_batch_action"],
        )
        self.assertIn("do not claim", payload["decision_summary"]["safety_boundary"])
        self.assertEqual(payload["delivery_budget"]["suggested_package"], "mini_diagnostic")
        self.assertEqual(payload["delivery_budget"]["estimated_review_minutes"], 13)
        self.assertEqual(payload["delivery_budget"]["estimated_review_hours"], 0.22)
        self.assertEqual(payload["delivery_budget"]["max_paid_hours"], 3)
        self.assertTrue(payload["delivery_budget"]["within_margin_budget"])
        self.assertEqual(
            payload["delivery_budget"]["analysis_rows"],
            {
                "l1_state_and_noise_review": 1,
                "l2_scope_and_readiness_review": 1,
                "l3_deep_dive_deferred": 0,
            },
        )
        self.assertIn("paid scope", payload["delivery_budget"]["boundary"])
        delivery_pack = payload["delivery_pack"]
        self.assertEqual(delivery_pack["suggested_package"], "mini_diagnostic")
        self.assertEqual(
            delivery_pack["phase_counts"],
            {
                "l1_state_and_noise_review": 1,
                "l2_shortlist_readiness_review": 1,
                "l3_deep_dive_deferred": 0,
            },
        )
        self.assertEqual(
            delivery_pack["handoff"]["candidate_references"],
            ["example/project#42"],
        )
        self.assertEqual(
            delivery_pack["handoff"]["no_go_references"],
            ["example/toolkit#17"],
        )
        self.assertIn("paid decision support", delivery_pack["boundary"])
        source_quality = payload["source_quality"]
        self.assertEqual(
            source_quality["summary"],
            {
                "source_count": 2,
                "total_rows": 2,
                "candidate_rows": 1,
                "no_go_rows": 1,
                "candidate_source_count": 1,
                "no_go_only_source_count": 1,
                "funding_verification_needed": 0,
                "authorization_needed": 0,
                "status": "candidate_sources_available",
                "next_tracker_action": (
                    "Run read-only public-state recheck on candidate sources before paid "
                    "shortlist use."
                ),
                "boundary": (
                    "Source summary is local tracker evidence only. It does not authorize "
                    "scraping, claims, comments, maintainer contact, pull requests, or "
                    "payout/merge guarantees."
                ),
            },
        )
        self.assertEqual(source_quality["sources"]["polar"]["total_rows"], 1)
        self.assertEqual(source_quality["sources"]["polar"]["candidate_rows"], 1)
        self.assertEqual(source_quality["sources"]["polar"]["no_go_rows"], 0)
        self.assertEqual(source_quality["sources"]["polar"]["safe_to_list"], 1)
        self.assertEqual(source_quality["sources"]["polar"]["average_score"], 99)
        self.assertEqual(source_quality["sources"]["polar"]["usable_signal_ratio"], 1)
        self.assertEqual(source_quality["sources"]["algora"]["total_rows"], 1)
        self.assertEqual(source_quality["sources"]["algora"]["candidate_rows"], 0)
        self.assertEqual(source_quality["sources"]["algora"]["no_go_rows"], 1)
        self.assertEqual(source_quality["sources"]["algora"]["safe_to_list"], 0)
        self.assertEqual(source_quality["sources"]["algora"]["average_score"], 0)
        self.assertEqual(source_quality["sources"]["algora"]["usable_signal_ratio"], 0)
        self.assertIn("no-go moat evidence", source_quality["sources"]["algora"]["recommended_use"])
        self.assertIn("read-only benchmarking", source_quality["boundary"])
        recheck_plan = payload["recheck_plan"]
        self.assertEqual(recheck_plan["total_rows"], 2)
        self.assertEqual(recheck_plan["recheck_rows"], 1)
        self.assertEqual(recheck_plan["no_go_rows"], 1)
        self.assertEqual(recheck_plan["priority_counts"], {"high": 1})
        self.assertEqual(
            recheck_plan["action_counts"],
            {"archive_as_no_go_evidence": 1, "recheck_public_issue_state": 1},
        )
        self.assertEqual(recheck_plan["next_rows"][0]["reference"], "example/project#42")
        self.assertEqual(recheck_plan["next_rows"][0]["priority"], "high")
        self.assertEqual(recheck_plan["next_rows"][0]["action"], "recheck_public_issue_state")
        self.assertIn("read-only tracker triage", recheck_plan["boundary"])
        evidence_debt = payload["evidence_debt"]
        self.assertEqual(evidence_debt["status"], "active_evidence_debt")
        self.assertEqual(evidence_debt["blocking_rows"], 1)
        self.assertEqual(evidence_debt["archive_only_rows"], 1)
        self.assertEqual(evidence_debt["highest_priority"], "high")
        self.assertEqual(evidence_debt["next_action"], "recheck_public_issue_state")
        self.assertEqual(evidence_debt["action_counts"], {"recheck_public_issue_state": 1})
        self.assertEqual(evidence_debt["platform_counts"], {"polar": 1})
        self.assertEqual(evidence_debt["priority_counts"], {"high": 1})
        self.assertEqual(evidence_debt["references"], ["example/project#42"])
        self.assertFalse(evidence_debt["payment_route_allowed_now"])
        self.assertFalse(evidence_debt["external_body_allowed"])
        self.assertIn("internal read-only delivery readiness", evidence_debt["boundary"])
        client_fit_summary = payload["client_fit_summary"]
        self.assertIsNone(client_fit_summary["profile_name"])
        self.assertEqual(client_fit_summary["status"], "no_profile")
        self.assertEqual(client_fit_summary["total_rows"], 2)
        self.assertEqual(client_fit_summary["matching_rows"], 2)
        self.assertEqual(client_fit_summary["excluded_rows"], 0)
        self.assertEqual(client_fit_summary["gap_counts"], {})
        self.assertIn("read-only client profile", client_fit_summary["recommended_action"])
        self.assertIn("does not authorize claiming", client_fit_summary["boundary"])
        intake_followup = payload["intake_followup"]
        self.assertEqual(intake_followup["status"], "needs_buyer_intake")
        self.assertEqual(intake_followup["suggested_package"], "mini_diagnostic")
        self.assertEqual(intake_followup["required_before_paid_delivery"], 3)
        self.assertEqual(
            [field["field"] for field in intake_followup["requested_fields"]],
            [
                "preferred_languages",
                "minimum_payout_usd",
                "allowed_risk_levels",
                "public_state_recheck_window",
            ],
        )
        self.assertIn("PatchRail copy-brief", intake_followup["next_internal_action"])
        self.assertIn("not customer-facing email copy", intake_followup["boundary"])
        cash_path_status = payload["cash_path_status"]
        self.assertEqual(cash_path_status["status"], "needs_buyer_intake")
        self.assertEqual(cash_path_status["next_revenue_action"], "collect_buyer_intake")
        self.assertTrue(cash_path_status["copy_brief_facts_available"])
        self.assertFalse(cash_path_status["payment_route_allowed_now"])
        self.assertTrue(cash_path_status["requires_written_acceptance_before_payment_route"])
        self.assertFalse(cash_path_status["buyer_ready"])
        self.assertIn("internal structured handoff only", cash_path_status["boundary"])
        self.assertIn("does not create a payment route", cash_path_status["boundary"])
        self.assertIn("does not authorize claims", cash_path_status["boundary"])
        operator_next_steps = payload["operator_next_steps"]
        self.assertEqual(
            operator_next_steps["schema_version"],
            "patchrail.funded_issues.operator_next_steps.v1",
        )
        self.assertEqual(operator_next_steps["status"], "needs_buyer_intake")
        self.assertEqual(operator_next_steps["primary_action"], "collect_buyer_intake")
        self.assertFalse(operator_next_steps["external_body_allowed"])
        self.assertFalse(operator_next_steps["payment_route_allowed_now"])
        self.assertEqual(
            [step["action"] for step in operator_next_steps["steps"]],
            [
                "collect_buyer_intake",
                "run_read_only_recheck",
                "preserve_no_go_evidence",
            ],
        )
        self.assertTrue(operator_next_steps["steps"][0]["copy_brief_allowed"])
        self.assertTrue(operator_next_steps["steps"][0]["blocks_paid_delivery"])
        self.assertIn(
            "preferred_languages",
            operator_next_steps["steps"][0]["evidence_required"],
        )
        self.assertIn("example/project#42", operator_next_steps["steps"][1]["reference_scope"])
        self.assertFalse(operator_next_steps["steps"][2]["blocks_paid_delivery"])
        self.assertIn("does not write external prose", operator_next_steps["boundary"])
        self.assertEqual(payload["top_safe_candidates"][0]["reference"], "example/project#42")
        self.assertEqual(payload["top_safe_candidates"][0]["opportunity_state"], "active")
        self.assertIn("ranking_by_money_only", payload["blocked_actions"])
        self.assertEqual(payload["requirements"]["network_required"], False)
        self.assertEqual(payload["requirements"]["github_write_permission_required"], False)

    def test_funded_issues_report_markdown_preserves_read_only_boundary(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "report",
                "--source",
                "examples/funded-issues-readonly/issues.json",
                "--format",
                "markdown",
            ]
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("# PatchRail Funded Issues Report", proc.stdout)
        self.assertIn("## Decision Summary", proc.stdout)
        self.assertIn("Candidate rows: `1`", proc.stdout)
        self.assertIn("Recommended batch action", proc.stdout)
        self.assertIn("`go_after_recheck` | 1", proc.stdout)
        self.assertIn("## Delivery Budget", proc.stdout)
        self.assertIn("Suggested package: `mini_diagnostic`", proc.stdout)
        self.assertIn("Estimated local review: `13` minutes", proc.stdout)
        self.assertIn("l2_scope_and_readiness_review", proc.stdout)
        self.assertIn("## Delivery Pack", proc.stdout)
        self.assertIn("l2_shortlist_readiness_review", proc.stdout)
        self.assertIn("Candidate references: `example/project#42`", proc.stdout)
        self.assertIn("No-go references: `example/toolkit#17`", proc.stdout)
        self.assertIn("## Source Quality", proc.stdout)
        self.assertIn("Status: `candidate_sources_available`", proc.stdout)
        self.assertIn("Candidate sources: `1`", proc.stdout)
        self.assertIn("No-go-only sources: `1`", proc.stdout)
        self.assertIn("Next tracker action: Run read-only public-state recheck", proc.stdout)
        self.assertIn("`polar` | 1 | 1 | 0 | 1", proc.stdout)
        self.assertIn("`algora` | 1 | 0 | 1 | 0", proc.stdout)
        self.assertIn("Source summary is local tracker evidence only", proc.stdout)
        self.assertIn("read-only benchmarking", proc.stdout)
        self.assertIn("## Recheck Plan", proc.stdout)
        self.assertIn("Active rechecks: `1`", proc.stdout)
        self.assertIn("`recheck_public_issue_state` | 1", proc.stdout)
        self.assertIn("read-only tracker triage", proc.stdout)
        self.assertIn("## Evidence Debt", proc.stdout)
        self.assertIn("Blocking rows: `1`", proc.stdout)
        self.assertIn("Next action: `recheck_public_issue_state`", proc.stdout)
        self.assertIn("internal read-only delivery readiness", proc.stdout)
        self.assertIn("## Client Fit Summary", proc.stdout)
        self.assertIn("Status: `no_profile`", proc.stdout)
        self.assertIn("Matching rows: `2` / `2`", proc.stdout)
        self.assertIn("## Intake Follow-Up", proc.stdout)
        self.assertIn("Status: `needs_buyer_intake`", proc.stdout)
        self.assertIn("`preferred_languages`", proc.stdout)
        self.assertIn("not customer-facing email copy", proc.stdout)
        self.assertIn("## Operator Next Steps", proc.stdout)
        self.assertIn("Primary action: `collect_buyer_intake`", proc.stdout)
        self.assertIn("`preserve_no_go_evidence`", proc.stdout)
        self.assertIn("External body allowed: `False`", proc.stdout)
        self.assertIn("does not write external prose", proc.stdout)
        self.assertIn("## Funding Path Status", proc.stdout)
        self.assertIn("Next internal action: `collect_buyer_intake`", proc.stdout)
        self.assertIn("Outbound action allowed now: `False`", proc.stdout)
        self.assertIn("does not create a payment route", proc.stdout)
        self.assertIn("paid scope", proc.stdout)
        self.assertIn("## No-Go Moat", proc.stdout)
        self.assertIn("High-risk or excluded | 1", proc.stdout)
        self.assertIn("Stale or closed | 1", proc.stdout)
        self.assertIn("### Opportunity States", proc.stdout)
        self.assertIn("`active`: `1`", proc.stdout)
        self.assertIn("example/project#42", proc.stdout)
        self.assertIn("example/toolkit#17", proc.stdout)
        self.assertIn("does not claim rewards", proc.stdout)
        self.assertIn("automatic_issue_comments", proc.stdout)

    def test_funded_issues_report_filters_by_active_state_for_tracker_metrics(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "report",
                "--source",
                "examples/funded-issues-readonly/issues.json",
                "--opportunity-state",
                "active",
                "--format",
                "json",
            ]
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["filters"]["opportunity_state"], "active")
        self.assertEqual(payload["totals"]["in_scope"], 1)
        self.assertEqual(payload["totals"]["safe_to_list"], 1)
        self.assertEqual(payload["breakdown"]["opportunity_states"], {"active": 1})
        self.assertEqual(payload["no_go_moat"]["stale_or_closed"], 0)

    def test_funded_issues_report_filters_by_risk_level_for_no_go_moat(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "report",
                "--source",
                "examples/funded-issues-readonly/issues.json",
                "--risk-level",
                "high",
                "--format",
                "json",
            ]
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["filters"]["risk_level"], "high")
        self.assertEqual(payload["totals"]["in_scope"], 1)
        self.assertEqual(payload["totals"]["safe_to_list"], 0)
        self.assertEqual(payload["breakdown"]["risk_levels"], {"high": 1})
        self.assertEqual(payload["breakdown"]["opportunity_states"], {"closed": 1})
        self.assertEqual(payload["no_go_moat"]["high_risk_or_excluded"], 1)
        self.assertEqual(payload["top_safe_candidates"], [])

    def test_funded_issues_recheck_queue_builds_local_read_only_work_queue(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "recheck-queue",
                "--source",
                "examples/funded-issues-readonly/issues.json",
                "--include-risky",
                "--format",
                "json",
            ]
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["schema_version"], "patchrail.funded_issues.recheck_queue.v1")
        self.assertEqual(payload["source_schema_version"], "patchrail.funded_issues.v1")
        self.assertTrue(payload["read_only"])
        self.assertFalse(payload["safe_only"])
        self.assertEqual(payload["total_loaded"], 2)
        self.assertEqual(payload["total_scored"], 2)
        self.assertIsNone(payload["queue_limit"])
        self.assertEqual(payload["queue_rows_before_limit"], 1)
        self.assertEqual(payload["queue_rows"], 1)
        self.assertEqual(payload["no_go_archive_rows"], 1)
        self.assertEqual(payload["priority_counts"], {"high": 1})
        self.assertEqual(
            payload["action_counts"],
            {"archive_as_no_go_evidence": 1, "recheck_public_issue_state": 1},
        )
        focus_batch = payload["focus_batch"]
        self.assertEqual(focus_batch["status"], "active_recheck_batch")
        self.assertEqual(focus_batch["primary_action"], "recheck_public_issue_state")
        self.assertEqual(focus_batch["priority"], "high")
        self.assertEqual(focus_batch["item_count"], 1)
        self.assertEqual(focus_batch["references"], ["example/project#42"])
        self.assertEqual(focus_batch["platform_counts"], {"polar": 1})
        self.assertIn("confirm issue is still open", focus_batch["evidence_checklist"][0])
        self.assertIn("does not authorize external prose", focus_batch["boundary"])
        self.assertFalse(payload["requirements"]["network_required"])
        self.assertFalse(payload["requirements"]["github_write_permission_required"])
        self.assertFalse(payload["requirements"]["external_model_required"])
        self.assertFalse(payload["requirements"]["billing_required"])
        self.assertIn("automatic_pull_requests", payload["blocked_actions"])
        self.assertIn("mass_outreach", payload["blocked_actions"])
        row = payload["items"][0]
        self.assertEqual(row["reference"], "example/project#42")
        self.assertEqual(row["platform"], "polar")
        self.assertEqual(row["funding"], "250 USD")
        self.assertEqual(row["priority"], "high")
        self.assertEqual(row["action"], "recheck_public_issue_state")
        self.assertEqual(row["decision_gate"], "go_after_recheck")
        self.assertIn("confirm issue is still open", row["evidence_checklist"][0])
        self.assertIn("confirm funding is still visible", row["evidence_checklist"][2])
        self.assertIn("does not claim rewards", payload["boundary"])
        self.assertIn("guarantee merge or payout outcomes", payload["boundary"])

    def test_funded_issues_recheck_queue_schema_matches_cli_payload_contract(self) -> None:
        schema_proc = run_patchrail(["schema", "funded-issues-recheck-queue"])
        payload_proc = run_patchrail(
            [
                "funded-issues",
                "recheck-queue",
                "--source",
                "examples/funded-issues-readonly/issues.json",
                "--format",
                "json",
            ]
        )

        self.assertEqual(schema_proc.returncode, 0, schema_proc.stderr)
        self.assertEqual(payload_proc.returncode, 0, payload_proc.stderr)
        schema = json.loads(schema_proc.stdout)
        payload = json.loads(payload_proc.stdout)
        self.assertEqual(
            schema["$id"],
            "https://patchrail.dev/schemas/funded-issues-recheck-queue.v1.schema.json",
        )
        self.assertEqual(
            schema["properties"]["schema_version"]["const"],
            "patchrail.funded_issues.recheck_queue.v1",
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(sorted(schema["required"]), sorted(payload.keys()))
        self.assertEqual(
            sorted(schema["$defs"]["focus_batch"]["required"]),
            sorted(payload["focus_batch"].keys()),
        )
        self.assertEqual(
            sorted(schema["$defs"]["recheck_queue_item"]["required"]),
            sorted(payload["items"][0].keys()),
        )
        self.assertFalse(
            schema["$defs"]["safe_requirements"]["properties"]["network_required"]["const"]
        )
        self.assertFalse(
            schema["$defs"]["safe_requirements"]["properties"]["github_write_permission_required"][
                "const"
            ]
        )
        self.assertIn("automatic_claims", schema["$defs"]["blocked_actions"]["contains"].values())
        self.assertIn(
            "recheck_public_issue_state",
            schema["$defs"]["recheck_queue_item"]["properties"]["action"]["enum"],
        )
        self.assertNotIn(
            "archive_as_no_go_evidence",
            schema["$defs"]["recheck_queue_item"]["properties"]["action"]["enum"],
        )

    def test_funded_issues_recheck_queue_can_limit_active_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "issues.json"
            payload = json.loads(
                Path("examples/funded-issues-readonly/issues.json").read_text(encoding="utf-8")
            )
            second_active = json.loads(json.dumps(payload["issues"][0]))
            second_active["id"] = "polar-example-project-43"
            second_active["issue_number"] = 43
            second_active["url"] = "https://github.com/example/project/issues/43"
            second_active["title"] = "Document flaky integration test repro"
            payload["issues"].append(second_active)
            source.write_text(json.dumps(payload), encoding="utf-8")

            proc = run_patchrail(
                [
                    "funded-issues",
                    "recheck-queue",
                    "--source",
                    str(source),
                    "--max-rows",
                    "1",
                    "--format",
                    "json",
                ]
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["queue_limit"], 1)
        self.assertEqual(result["queue_rows_before_limit"], 2)
        self.assertEqual(result["queue_rows"], 1)
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["reference"], "example/project#42")

    def test_funded_issues_recheck_queue_rejects_zero_limit(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "recheck-queue",
                "--source",
                "examples/funded-issues-readonly/issues.json",
                "--max-rows",
                "0",
                "--format",
                "json",
            ]
        )

        self.assertEqual(proc.returncode, 1)
        self.assertIn("max_rows must be at least 1", proc.stderr)

    def test_funded_issues_recheck_queue_markdown_preserves_boundaries(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "recheck-queue",
                "--source",
                "examples/funded-issues-readonly/issues.json",
                "--format",
                "markdown",
            ]
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("# PatchRail Funded Issues Recheck Queue", proc.stdout)
        self.assertIn("- Read-only: `True`", proc.stdout)
        self.assertIn("- Safe-only: `True`", proc.stdout)
        self.assertIn("- Queue limit: `None`", proc.stdout)
        self.assertIn("- Queue rows before limit: `1`", proc.stdout)
        self.assertIn("- Queue rows: `1`", proc.stdout)
        self.assertIn("- No-go archive rows: `0`", proc.stdout)
        self.assertIn("## Focus Batch", proc.stdout)
        self.assertIn("- Primary action: `recheck_public_issue_state`", proc.stdout)
        self.assertIn("- References: `example/project#42`", proc.stdout)
        self.assertIn(
            "Focus batch is the next local read-only tracker maintenance slice", proc.stdout
        )
        self.assertIn("| `high` | `recheck_public_issue_state` |", proc.stdout)
        self.assertIn("example/project#42", proc.stdout)
        self.assertIn("confirm issue is still open", proc.stdout)
        self.assertIn("confirm funding is still visible", proc.stdout)
        self.assertIn("`recheck_public_issue_state` | 1", proc.stdout)
        self.assertIn("does not claim rewards", proc.stdout)
        self.assertIn("automatic_claims", proc.stdout)
        self.assertIn("automatic_pull_requests", proc.stdout)

    def test_funded_issues_cash_actions_builds_internal_revenue_queue(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "cash-actions",
                "--source",
                "examples/funded-issues-readonly/issues.json",
                "--include-risky",
                "--format",
                "json",
            ]
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["schema_version"], "patchrail.funded_issues.cash_actions.v1")
        self.assertEqual(payload["source_schema_version"], "patchrail.funded_issues.v1")
        self.assertTrue(payload["read_only"])
        self.assertFalse(payload["safe_only"])
        self.assertIsNone(payload["action_limit"])
        self.assertEqual(payload["actions_before_limit"], 2)
        self.assertEqual(payload["action_rows"], 2)
        self.assertEqual(
            payload["cash_path_status"]["next_revenue_action"],
            "collect_buyer_intake",
        )
        self.assertFalse(payload["cash_path_status"]["payment_route_allowed_now"])
        self.assertFalse(payload["requirements"]["network_required"])
        self.assertFalse(payload["requirements"]["github_write_permission_required"])
        self.assertFalse(payload["requirements"]["external_model_required"])
        self.assertFalse(payload["requirements"]["billing_required"])
        self.assertIn("automatic_pull_requests", payload["blocked_actions"])
        self.assertIn("mass_outreach", payload["blocked_actions"])
        first = payload["items"][0]
        self.assertEqual(first["action"], "collect_buyer_intake")
        self.assertEqual(first["priority"], "high")
        self.assertEqual(first["suggested_package"], "mini_diagnostic")
        self.assertTrue(first["copy_brief_allowed"])
        self.assertEqual(
            first["copy_brief_facts"]["schema_version"],
            "patchrail.funded_issues.copy_brief_facts.v1",
        )
        self.assertEqual(first["copy_brief_facts"]["type"], "reply")
        self.assertEqual(first["copy_brief_facts"]["goal"], "collect_buyer_intake")
        self.assertIn(
            "requested_fields=preferred_languages,minimum_payout_usd,allowed_risk_levels",
            first["copy_brief_facts"]["key_facts"],
        )
        self.assertIn(
            "evidence_references=example/project#42",
            first["copy_brief_facts"]["key_facts"],
        )
        self.assertEqual(
            first["copy_brief_facts"]["forbidden_fields"],
            ["body", "draft", "email_body"],
        )
        self.assertNotIn("body", first["copy_brief_facts"])
        self.assertNotIn("draft", first["copy_brief_facts"])
        self.assertNotIn("email_body", first["copy_brief_facts"])
        self.assertFalse(first["copy_brief_facts"]["external_body_allowed"])
        self.assertFalse(first["copy_brief_facts"]["payment_route_allowed_now"])
        self.assertFalse(first["external_body_allowed"])
        self.assertFalse(first["payment_route_allowed_now"])
        self.assertTrue(first["requires_written_acceptance_before_payment_route"])
        self.assertIn("preferred_languages", first["requested_fields"])
        self.assertIn("minimum_payout_usd", first["requested_fields"])
        self.assertIn("example/project#42", first["evidence_references"])
        self.assertIn("Do not write external prose", first["boundary"])
        second = payload["items"][1]
        self.assertEqual(second["action"], "run_read_only_recheck")
        self.assertEqual(second["priority"], "medium")
        self.assertFalse(second["copy_brief_allowed"])
        self.assertIsNone(second["copy_brief_facts"])
        self.assertIn("example/project#42", second["evidence_references"])
        self.assertEqual(
            payload["operator_next_steps"]["primary_action"],
            "collect_buyer_intake",
        )
        self.assertEqual(len(payload["operator_next_steps"]["steps"]), 3)
        self.assertFalse(payload["operator_next_steps"]["external_body_allowed"])
        self.assertFalse(payload["operator_next_steps"]["payment_route_allowed_now"])
        self.assertIn("not external prose", payload["boundary"])
        self.assertIn("do not create a payment route", payload["boundary"])
        self.assertIn("guarantee merge or payout outcomes", payload["boundary"])

    def test_funded_issues_cash_actions_markdown_preserves_boundaries(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "cash-actions",
                "--source",
                "examples/funded-issues-readonly/issues.json",
                "--max-actions",
                "1",
                "--format",
                "markdown",
            ]
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("# PatchRail Funded Issues Cash Actions", proc.stdout)
        self.assertIn("- Read-only: `True`", proc.stdout)
        self.assertIn("- Action limit: `1`", proc.stdout)
        self.assertIn("- Actions before limit: `2`", proc.stdout)
        self.assertIn("- Action rows: `1`", proc.stdout)
        self.assertIn("Next internal action: `collect_buyer_intake`", proc.stdout)
        self.assertIn("Outbound action allowed now: `False`", proc.stdout)
        self.assertIn("`collect_buyer_intake`", proc.stdout)
        self.assertIn("`mini_diagnostic`", proc.stdout)
        self.assertIn("`preferred_languages`", proc.stdout)
        self.assertIn("7 facts; forbidden:", proc.stdout)
        self.assertIn("`body`, `draft`, `email_body`", proc.stdout)
        self.assertIn("## Operator Next Steps", proc.stdout)
        self.assertIn("Primary action: `collect_buyer_intake`", proc.stdout)
        self.assertIn("not external prose", proc.stdout)
        self.assertIn("does not create a payment route", proc.stdout)
        self.assertIn("automatic_pull_requests", proc.stdout)

    def test_funded_issues_cash_actions_rejects_zero_limit(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "cash-actions",
                "--source",
                "examples/funded-issues-readonly/issues.json",
                "--max-actions",
                "0",
                "--format",
                "json",
            ]
        )

        self.assertEqual(proc.returncode, 1)
        self.assertIn("max_actions must be at least 1", proc.stderr)

    def test_funded_issues_fulfillment_packet_builds_internal_delivery_packet(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "fulfillment-packet",
                "--source",
                "examples/funded-issues-readonly/issues.json",
                "--include-risky",
                "--format",
                "json",
            ]
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(
            payload["schema_version"],
            "patchrail.funded_issues.fulfillment_packet.v1",
        )
        self.assertEqual(payload["source_schema_version"], "patchrail.funded_issues.v1")
        self.assertTrue(payload["read_only"])
        self.assertFalse(payload["safe_only"])
        self.assertEqual(payload["status"], "needs_buyer_intake")
        self.assertEqual(payload["suggested_package"], "mini_diagnostic")
        self.assertIsNone(payload["packet_limit"])
        self.assertEqual(payload["items_before_limit"], 3)
        self.assertEqual(payload["item_rows"], 3)
        self.assertEqual(payload["totals"]["loaded"], 2)
        self.assertEqual(payload["totals"]["candidate_references"], 1)
        self.assertEqual(payload["totals"]["no_go_references"], 1)
        self.assertEqual(payload["totals"]["active_rechecks"], 1)
        self.assertEqual(payload["totals"]["source_count"], 2)
        self.assertEqual(
            payload["cash_path_status"]["next_revenue_action"],
            "collect_buyer_intake",
        )
        self.assertFalse(payload["cash_path_status"]["payment_route_allowed_now"])
        gate_map = {gate["gate"]: gate for gate in payload["qa_gates"]}
        self.assertFalse(gate_map["buyer_intake_fields_complete"]["passed"])
        self.assertIn("preferred_languages", gate_map["buyer_intake_fields_complete"]["evidence"])
        self.assertFalse(gate_map["public_state_recheck_complete"]["passed"])
        self.assertIn("example/project#42", gate_map["public_state_recheck_complete"]["evidence"])
        self.assertTrue(gate_map["source_quality_recorded"]["passed"])
        self.assertTrue(gate_map["third_party_write_boundary"]["passed"])
        self.assertFalse(gate_map["payment_route_written_acceptance"]["passed"])
        readiness = payload["delivery_readiness"]
        self.assertFalse(readiness["ready_for_paid_delivery"])
        self.assertEqual(readiness["status"], "blocked_internal")
        self.assertEqual(readiness["next_internal_action"], "collect_buyer_intake")
        self.assertFalse(readiness["payment_route_allowed_now"])
        self.assertFalse(readiness["external_body_allowed"])
        self.assertIn("buyer_intake_fields_complete", readiness["blocking_gates"])
        self.assertIn("public_state_recheck_complete", readiness["blocking_gates"])
        self.assertIn("payment_route_written_acceptance", readiness["blocking_gates"])
        self.assertIn("collect_buyer_intake", readiness["blocking_item_actions"])
        self.assertIn("recheck_public_issue_state", readiness["blocking_item_actions"])
        self.assertIn("example/project#42", readiness["blocking_reference_scope"])
        self.assertIn("does not authorize", readiness["boundary"])
        digest = payload["operations_digest"]
        self.assertEqual(
            digest["schema_version"],
            "patchrail.funded_issues.operations_digest.v1",
        )
        self.assertEqual(digest["status"], "blocked_internal")
        self.assertEqual(digest["blocking_count"], 5)
        self.assertEqual(digest["gate_pass_rate"], 0.5)
        self.assertEqual(digest["stage_counts"], {"cash_path": 2, "public_state_recheck": 1})
        self.assertEqual(
            digest["blocking_stage_counts"],
            {"cash_path": 1, "public_state_recheck": 1},
        )
        self.assertEqual(digest["non_blocking_actions"], ["run_read_only_recheck"])
        self.assertEqual(digest["next_blocker"]["action"], "buyer_intake_fields_complete")
        self.assertEqual(digest["next_blocker"]["owner"], "buyer_or_written_acceptance")
        self.assertIn("preferred_languages", digest["next_blocker"]["evidence"])
        self.assertEqual(
            digest["next_safe_local_action"]["action"],
            "public_state_recheck_complete",
        )
        self.assertEqual(digest["next_safe_local_action"]["owner"], "patchrail_operator")
        self.assertIn("example/project#42", digest["next_safe_local_action"]["evidence"])
        self.assertFalse(digest["payment_route_allowed_now"])
        self.assertFalse(digest["external_body_allowed"])
        self.assertIn("does not write customer prose", digest["boundary"])
        evidence_manifest = payload["evidence_manifest"]
        self.assertEqual(
            evidence_manifest["schema_version"],
            "patchrail.funded_issues.evidence_manifest.v1",
        )
        self.assertEqual(evidence_manifest["status"], "blocked_internal")
        self.assertEqual(evidence_manifest["artifact_count"], 7)
        self.assertEqual(evidence_manifest["required_artifact_count"], 5)
        self.assertEqual(evidence_manifest["ready_required_artifact_count"], 2)
        self.assertEqual(
            evidence_manifest["blocked_artifacts"],
            [
                "public_state_recheck_queue",
                "buyer_intake_record",
                "payment_acceptance_record",
            ],
        )
        artifact_map = {
            artifact["artifact"]: artifact for artifact in evidence_manifest["artifacts"]
        }
        self.assertEqual(artifact_map["source_batch"]["status"], "ready")
        self.assertEqual(artifact_map["source_batch"]["references"], ["algora", "polar"])
        self.assertEqual(artifact_map["scored_candidate_set"]["references"], ["example/project#42"])
        self.assertEqual(
            artifact_map["public_state_recheck_queue"]["references"],
            ["example/project#42"],
        )
        self.assertIn(
            "preferred_languages",
            artifact_map["buyer_intake_record"]["references"],
        )
        self.assertEqual(artifact_map["copy_brief_facts"]["status"], "ready")
        self.assertEqual(artifact_map["copy_brief_facts"]["references"], ["collect_buyer_intake"])
        self.assertFalse(evidence_manifest["payment_route_allowed_now"])
        self.assertFalse(evidence_manifest["external_body_allowed"])
        self.assertIn("does not write customer prose", evidence_manifest["boundary"])
        report_plan = payload["report_assembly_plan"]
        self.assertEqual(
            report_plan["schema_version"],
            "patchrail.funded_issues.report_assembly_plan.v1",
        )
        self.assertEqual(report_plan["status"], "blocked_before_customer_delivery")
        self.assertTrue(report_plan["internal_assembly_ready"])
        self.assertFalse(report_plan["customer_delivery_ready"])
        self.assertEqual(report_plan["section_count"], 7)
        self.assertIn("executive_summary", report_plan["ready_sections"])
        self.assertIn("no_go_list", report_plan["ready_sections"])
        self.assertIn("top_recommendations", report_plan["blocked_sections"])
        self.assertIn("watchlist", report_plan["blocked_sections"])
        self.assertIn("recommended_operating_procedure", report_plan["blocked_sections"])
        self.assertEqual(report_plan["candidate_references"], ["example/project#42"])
        self.assertEqual(report_plan["verification_references"], [])
        self.assertEqual(report_plan["no_go_references"], ["example/toolkit#17"])
        self.assertEqual(report_plan["source_quality_status"], "candidate_sources_available")
        self.assertFalse(report_plan["payment_route_allowed_now"])
        self.assertFalse(report_plan["external_body_allowed"])
        self.assertFalse(report_plan["customer_facing_prose_allowed"])
        section_map = {section["section"]: section for section in report_plan["sections"]}
        self.assertEqual(
            section_map["top_recommendations"]["blocked_by"],
            ["public_state_recheck_complete", "buyer_intake_fields_complete"],
        )
        self.assertIn(
            "delivery_pack.handoff.candidate_references",
            section_map["top_recommendations"]["source_fields"],
        )
        self.assertEqual(section_map["disclaimer"]["status"], "ready_for_internal_draft")
        self.assertIn("does not write customer prose", report_plan["boundary"])
        self.assertEqual(
            payload["operator_next_steps"]["primary_action"],
            "collect_buyer_intake",
        )
        self.assertEqual(
            [step["source"] for step in payload["operator_next_steps"]["steps"]],
            ["cash_path", "recheck_plan", "delivery_pack"],
        )
        self.assertFalse(payload["operator_next_steps"]["external_body_allowed"])
        self.assertFalse(payload["operator_next_steps"]["payment_route_allowed_now"])
        self.assertFalse(payload["handoff"]["external_body_allowed"])
        self.assertFalse(payload["handoff"]["payment_route_allowed_now"])
        self.assertTrue(payload["handoff"]["requires_written_acceptance_before_payment_route"])
        self.assertIn("cash_actions", payload["handoff"]["sections"])
        self.assertIn("evidence_manifest", payload["handoff"]["sections"])
        self.assertFalse(payload["requirements"]["network_required"])
        self.assertFalse(payload["requirements"]["github_write_permission_required"])
        self.assertFalse(payload["requirements"]["external_model_required"])
        self.assertFalse(payload["requirements"]["billing_required"])
        self.assertIn("automatic_pull_requests", payload["blocked_actions"])
        self.assertIn("mass_outreach", payload["blocked_actions"])
        actions = [item["action"] for item in payload["items"]]
        self.assertEqual(
            actions,
            ["collect_buyer_intake", "recheck_public_issue_state", "run_read_only_recheck"],
        )
        first = payload["items"][0]
        self.assertEqual(first["stage"], "cash_path")
        self.assertIn("preferred_languages", first["evidence_required"])
        self.assertTrue(first["blocks_paid_delivery"])
        self.assertFalse(first["external_body_allowed"])
        self.assertFalse(first["payment_route_allowed_now"])
        self.assertFalse(first["github_write_permission_required"])
        self.assertFalse(first["network_required"])
        self.assertIn("Do not write customer prose", first["boundary"])
        self.assertIn("not customer-facing prose", payload["boundary"])
        self.assertIn("does not create a payment route", payload["boundary"])
        self.assertIn("guarantee merge or payout outcomes", payload["boundary"])

    def test_funded_issues_fulfillment_packet_markdown_preserves_boundaries(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "fulfillment-packet",
                "--source",
                "examples/funded-issues-readonly/issues.json",
                "--max-items",
                "2",
                "--format",
                "markdown",
            ]
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("# PatchRail Funded Issues Fulfillment Packet", proc.stdout)
        self.assertIn("- Read-only: `True`", proc.stdout)
        self.assertIn("- Status: `needs_buyer_intake`", proc.stdout)
        self.assertIn("- Packet limit: `2`", proc.stdout)
        self.assertIn("- Items before limit: `3`", proc.stdout)
        self.assertIn("- Item rows: `2`", proc.stdout)
        self.assertIn("## QA Gates", proc.stdout)
        self.assertIn("`buyer_intake_fields_complete`", proc.stdout)
        self.assertIn("`public_state_recheck_complete`", proc.stdout)
        self.assertIn("`payment_route_written_acceptance`", proc.stdout)
        self.assertIn("## Delivery Readiness", proc.stdout)
        self.assertIn("- Status: `blocked_internal`", proc.stdout)
        self.assertIn("- Ready for paid delivery: `False`", proc.stdout)
        self.assertIn("- Outbound action allowed now: `False`", proc.stdout)
        self.assertIn("- External body allowed: `False`", proc.stdout)
        self.assertIn("`collect_buyer_intake`", proc.stdout)
        self.assertIn("## Operations Digest", proc.stdout)
        self.assertIn("- Blocking count: `5`", proc.stdout)
        self.assertIn("- Gate pass rate: `0.5`", proc.stdout)
        self.assertIn("Next safe local action: `public_state_recheck_complete`", proc.stdout)
        self.assertIn("`buyer_intake_fields_complete`", proc.stdout)
        self.assertIn("`patchrail_operator`", proc.stdout)
        self.assertIn("`run_read_only_recheck`", proc.stdout)
        self.assertIn("does not write customer prose", proc.stdout)
        self.assertIn("## Evidence Manifest", proc.stdout)
        self.assertIn("- Status: `blocked_internal`", proc.stdout)
        self.assertIn("- Artifact count: `7`", proc.stdout)
        self.assertIn("- Ready required artifacts: `2`", proc.stdout)
        self.assertIn("`public_state_recheck_queue`", proc.stdout)
        self.assertIn("`buyer_intake_record`", proc.stdout)
        self.assertIn("`payment_acceptance_record`", proc.stdout)
        self.assertIn("`copy_brief_facts`", proc.stdout)
        self.assertIn("## Report Assembly Plan", proc.stdout)
        self.assertIn("- Status: `blocked_before_customer_delivery`", proc.stdout)
        self.assertIn("- Internal assembly ready: `True`", proc.stdout)
        self.assertIn("- Customer delivery ready: `False`", proc.stdout)
        self.assertIn(
            "- Blocked sections: `top_recommendations`, `watchlist`, `recommended_operating_procedure`",
            proc.stdout,
        )
        self.assertIn("`delivery_pack.handoff.candidate_references`", proc.stdout)
        self.assertIn("`public_state_recheck_complete`", proc.stdout)
        self.assertIn("Customer-facing prose allowed: `False`", proc.stdout)
        self.assertIn("Outbound action allowed now: `False`", proc.stdout)
        self.assertIn("## Operator Next Steps", proc.stdout)
        self.assertIn("`preserve_no_go_evidence`", proc.stdout)
        self.assertIn("## Fulfillment Items", proc.stdout)
        self.assertIn("`collect_buyer_intake`", proc.stdout)
        self.assertIn("`recheck_public_issue_state`", proc.stdout)
        self.assertIn("`preferred_languages`", proc.stdout)
        self.assertIn("## Handoff", proc.stdout)
        self.assertIn("- External body allowed: `False`", proc.stdout)
        self.assertIn("- Outbound action allowed now: `False`", proc.stdout)
        self.assertIn("not customer-facing prose", proc.stdout)
        self.assertIn("does not create a payment route", proc.stdout)
        self.assertIn("automatic_pull_requests", proc.stdout)

    def test_funded_issues_fulfillment_packet_rejects_zero_limit(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "fulfillment-packet",
                "--source",
                "examples/funded-issues-readonly/issues.json",
                "--max-items",
                "0",
                "--format",
                "json",
            ]
        )

        self.assertEqual(proc.returncode, 1)
        self.assertIn("max_items must be at least 1", proc.stderr)

    def test_funded_issues_report_accepts_read_only_client_profile(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "report",
                "--source",
                "examples/funded-issues-readonly/issues.json",
                "--profile",
                "examples/funded-issues-readonly/client-profile-python.json",
                "--format",
                "markdown",
            ]
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Client profile: `Async Python buyer`", proc.stdout)
        self.assertIn("In scope: `1`", proc.stdout)
        self.assertIn("example/project#42", proc.stdout)
        self.assertIn("## Client Fit Summary", proc.stdout)
        self.assertIn("Status: `partial_match`", proc.stdout)
        self.assertIn("Matching rows: `1` / `2`", proc.stdout)
        self.assertIn("EXCLUDED_RISK_FLAG:spam_attractive", proc.stdout)
        self.assertIn("## Client Fit Gaps", proc.stdout)
        self.assertIn("example/toolkit#17", proc.stdout)
        self.assertIn("LANGUAGE_MISMATCH", proc.stdout)
        self.assertIn("OPPORTUNITY_STATE_NOT_ALLOWED", proc.stdout)
        self.assertIn("RISK_LEVEL_NOT_ALLOWED", proc.stdout)
        self.assertIn("EXCLUDED_RISK_FLAG:spam_attractive", proc.stdout)
        self.assertIn("## Intake Follow-Up", proc.stdout)
        self.assertIn("Status: `needs_buyer_intake`", proc.stdout)
        self.assertIn("`profile_gap_confirmation`", proc.stdout)
        self.assertIn("`public_state_recheck_window`", proc.stdout)
        self.assertIn("does not claim rewards", proc.stdout)

    def test_funded_issues_list_profile_preserves_filters_in_json(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "list",
                "--source",
                "examples/funded-issues-readonly/issues.json",
                "--profile",
                "examples/funded-issues-readonly/client-profile-python.json",
                "--format",
                "json",
            ]
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["total_loaded"], 2)
        self.assertEqual(payload["total_returned"], 1)
        self.assertEqual(payload["filters"]["profile"]["name"], "Async Python buyer")
        self.assertEqual(
            payload["filters"]["profile"]["schema_version"],
            "patchrail.funded_issues.client_profile.v1",
        )
        self.assertEqual(payload["filters"]["profile"]["languages"], ["python"])
        self.assertEqual(payload["filters"]["profile"]["min_usd"], 200.0)
        self.assertTrue(payload["filters"]["profile"]["read_only"])
        self.assertEqual(payload["issues"][0]["reference"], "example/project#42")

    def test_schema_command_exposes_funded_issues_report_and_shortlist_contracts(self) -> None:
        expected_versions = {
            "funded-issues-report": "patchrail.funded_issues.report.v1",
            "funded-issues-shortlist": "patchrail.funded_issues.shortlist.v1",
        }

        for schema_name, schema_version in expected_versions.items():
            with self.subTest(schema_name=schema_name):
                proc = run_patchrail(["schema", schema_name])

                self.assertEqual(proc.returncode, 0, proc.stderr)
                schema = json.loads(proc.stdout)
                self.assertIn("https://patchrail.dev/schemas/", schema["$id"])
                self.assertEqual(schema["properties"]["schema_version"]["const"], schema_version)
                self.assertEqual(schema["properties"]["read_only"]["const"], True)
                self.assertIn("blocked_actions", schema["required"])
                self.assertIn("requirements", schema["required"])
                self.assertIn("source_quality", schema["required"])
                self.assertIn("sources", schema["$defs"]["source_quality"]["required"])
                self.assertIn("summary", schema["$defs"]["source_quality"]["required"])
                source_summary = schema["$defs"]["source_quality_summary"]
                self.assertIn("candidate_source_count", source_summary["required"])
                self.assertIn("next_tracker_action", source_summary["required"])
                self.assertIn(
                    "candidate_sources_available",
                    source_summary["properties"]["status"]["enum"],
                )
                self.assertIn("recheck_plan", schema["required"])
                self.assertIn("next_rows", schema["$defs"]["recheck_plan"]["required"])
                self.assertIn("action", schema["$defs"]["recheck_row"]["required"])
                self.assertIn(
                    "recheck_public_issue_state",
                    schema["$defs"]["recheck_row"]["properties"]["action"]["enum"],
                )
                self.assertIn("evidence_debt", schema["required"])
                evidence_debt = schema["$defs"]["evidence_debt"]
                self.assertIn("blocking_rows", evidence_debt["required"])
                self.assertIn("references", evidence_debt["required"])
                self.assertIn(
                    "active_evidence_debt",
                    evidence_debt["properties"]["status"]["enum"],
                )
                self.assertIn(
                    "ready_for_delivery_readiness_review",
                    evidence_debt["properties"]["next_action"]["enum"],
                )
                self.assertEqual(
                    evidence_debt["properties"]["payment_route_allowed_now"]["const"],
                    False,
                )
                self.assertEqual(
                    evidence_debt["properties"]["external_body_allowed"]["const"],
                    False,
                )
                self.assertIn("client_fit_gaps", schema["required"])
                self.assertIn("client_fit_summary", schema["required"])
                self.assertIn("intake_followup", schema["required"])
                self.assertIn("cash_path_status", schema["required"])
                intake_followup = schema["$defs"]["intake_followup"]
                self.assertIn("requested_fields", intake_followup["required"])
                self.assertIn(
                    "needs_buyer_intake",
                    intake_followup["properties"]["status"]["enum"],
                )
                self.assertIn(
                    "ready_after_read_only_recheck",
                    intake_followup["properties"]["status"]["enum"],
                )
                intake_field = schema["$defs"]["intake_field"]
                self.assertIn("required_before_paid_delivery", intake_field["required"])
                cash_path_status = schema["$defs"]["cash_path_status"]
                self.assertIn("next_revenue_action", cash_path_status["required"])
                self.assertIn(
                    "collect_buyer_intake",
                    cash_path_status["properties"]["next_revenue_action"]["enum"],
                )
                self.assertEqual(
                    cash_path_status["properties"]["payment_route_allowed_now"]["const"],
                    False,
                )
                self.assertEqual(
                    cash_path_status["properties"][
                        "requires_written_acceptance_before_payment_route"
                    ]["const"],
                    True,
                )
                client_fit_summary = schema["$defs"]["client_fit_summary"]
                self.assertIn("matching_rows", client_fit_summary["required"])
                self.assertIn("partial_match", client_fit_summary["properties"]["status"]["enum"])
                self.assertIn("gap_counts", client_fit_summary["required"])
                client_fit_gap = schema["$defs"]["client_fit_gap"]
                self.assertIn("gap_codes", client_fit_gap["required"])
                self.assertIn("gap_summary", client_fit_gap["required"])
                source_stats = schema["$defs"]["source_quality_source"]
                self.assertIn("usable_signal_ratio", source_stats["required"])
                self.assertIn("recommended_use", source_stats["required"])
                requirements = schema["$defs"]["safe_requirements"]["properties"]
                self.assertEqual(requirements["network_required"]["const"], False)
                self.assertEqual(requirements["github_write_permission_required"]["const"], False)
                self.assertEqual(requirements["external_model_required"]["const"], False)
                self.assertEqual(requirements["billing_required"]["const"], False)
                filters = schema["$defs"]["filters"]
                self.assertIn("opportunity_state", filters["required"])
                self.assertIn("opportunity_state", filters["properties"])
                self.assertIn("risk_level", filters["required"])
                self.assertIn("risk_level", filters["properties"])
                self.assertIn("profile", filters["required"])
                self.assertIn("profile", filters["properties"])
                profile_schema = schema["$defs"]["client_profile"]
                self.assertEqual(
                    profile_schema["properties"]["schema_version"]["const"],
                    "patchrail.funded_issues.client_profile.v1",
                )
                self.assertIn("allowed_opportunity_states", profile_schema["required"])
                self.assertIn("allowed_risk_levels", profile_schema["required"])
                self.assertIn("excluded_risk_flags", profile_schema["required"])
                self.assertEqual(profile_schema["properties"]["read_only"]["const"], True)

                blocked_actions = schema["$defs"]["blocked_actions"]["items"]["enum"]
                self.assertIn("automatic_claims", blocked_actions)
                self.assertIn("automatic_pull_requests", blocked_actions)
                self.assertIn("automatic_issue_comments", blocked_actions)
                self.assertIn("mass_outreach", blocked_actions)
                self.assertIn("ranking_by_money_only", blocked_actions)
                self.assertIn("decision_summary", schema["required"])
                self.assertIn("delivery_budget", schema["required"])
                self.assertIn("delivery_pack", schema["required"])
                self.assertIn("handoff", schema["$defs"]["delivery_pack"]["required"])
                self.assertIn("phases", schema["$defs"]["delivery_pack"]["required"])
                self.assertIn(
                    "l2_shortlist_readiness_review",
                    schema["$defs"]["delivery_phase"]["properties"]["phase"]["enum"],
                )

                if schema_name == "funded-issues-shortlist":
                    self.assertIn(
                        "recommended_batch_action",
                        schema["$defs"]["decision_summary"]["required"],
                    )
                    self.assertIn(
                        "suggested_package",
                        schema["$defs"]["delivery_budget"]["required"],
                    )
                    self.assertIn(
                        "opportunity_shortlist",
                        schema["$defs"]["delivery_budget"]["properties"]["suggested_package"][
                            "enum"
                        ],
                    )
                    self.assertIn("shortlist", schema["required"])
                    self.assertIn("no_go_evidence", schema["required"])
                    self.assertEqual(
                        schema["$defs"]["scored_issue"]["properties"]["score"]["maximum"], 100
                    )
                    self.assertIn(
                        "confidence",
                        schema["$defs"]["scored_issue"]["required"],
                    )
                    self.assertEqual(
                        schema["$defs"]["scored_issue"]["properties"]["confidence"]["maximum"], 1
                    )
                    self.assertIn(
                        "recommended_next_step",
                        schema["$defs"]["scored_issue"]["required"],
                    )
                    self.assertIn(
                        "decision_gate",
                        schema["$defs"]["scored_issue"]["required"],
                    )
                    self.assertIn(
                        "source_review",
                        schema["$defs"]["funded_issue"]["required"],
                    )
                    self.assertIn(
                        "primary_source_required",
                        schema["$defs"]["source_review"]["required"],
                    )
                    self.assertIn(
                        "discovery_only_source",
                        schema["$defs"]["source_review"]["properties"]["risk_flags"]["items"][
                            "enum"
                        ],
                    )
                    self.assertIn(
                        "needs_funding_verification",
                        schema["$defs"]["scored_issue"]["properties"]["decision_gate"]["enum"],
                    )
                else:
                    self.assertIn(
                        "safety_boundary",
                        schema["$defs"]["decision_summary"]["required"],
                    )
                    self.assertIn(
                        "within_margin_budget",
                        schema["$defs"]["delivery_budget"]["required"],
                    )
                    self.assertIn("top_safe_candidates", schema["required"])
                    self.assertIn("no_go_moat", schema["required"])

    def test_funded_issues_score_ranks_readiness_with_reason_codes(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "score",
                "--source",
                "examples/funded-issues-readonly/issues.json",
                "--include-risky",
                "--format",
                "json",
            ]
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["schema_version"], "patchrail.funded_issues.score.v1")
        self.assertEqual(payload["read_only"], True)
        self.assertEqual(payload["total_loaded"], 2)
        self.assertEqual(payload["total_scored"], 2)
        self.assertEqual(payload["rating_counts"], {"go_candidate": 1, "no_go": 1})
        self.assertEqual(payload["scores"][0]["issue"]["reference"], "example/project#42")
        self.assertEqual(payload["scores"][0]["score"], 99)
        self.assertEqual(payload["scores"][0]["confidence"], 0.99)
        self.assertEqual(payload["scores"][0]["rating"], "go_candidate")
        self.assertEqual(payload["scores"][0]["decision_gate"], "go_after_recheck")
        self.assertEqual(payload["scores"][0]["reason_codes"], ["NO_MAJOR_REVIEW_GAPS"])
        self.assertIn("Reproduce locally", payload["scores"][0]["recommended_next_step"])
        self.assertIn("re-check assignment", payload["scores"][0]["recommended_next_step"])
        risky = payload["scores"][1]
        self.assertEqual(risky["issue"]["reference"], "example/toolkit#17")
        self.assertEqual(risky["issue"]["opportunity_state"], "closed")
        self.assertEqual(risky["score"], 0)
        self.assertEqual(risky["confidence"], 0.3)
        self.assertEqual(risky["rating"], "no_go")
        self.assertEqual(risky["decision_gate"], "no_go")
        self.assertIn("CLOSED_OR_INACTIVE", risky["reason_codes"])
        self.assertIn("SCOPE_TOO_BROAD", risky["reason_codes"])
        self.assertIn("SPAM_ATTRACTIVE", risky["reason_codes"])
        self.assertIn("NO_CONTRIBUTION_GUIDELINES", risky["reason_codes"])
        self.assertIn("Do not engage", risky["recommended_next_step"])
        self.assertIn("live again", risky["recommended_next_step"])
        self.assertFalse(payload["requirements"]["network_required"])
        self.assertFalse(payload["requirements"]["github_write_permission_required"])
        self.assertIn("ranking_by_money_only", payload["blocked_actions"])

    def test_funded_issues_score_safe_only_filters_high_risk(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "score",
                "--source",
                "examples/funded-issues-readonly/issues.json",
                "--format",
                "markdown",
            ]
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("# PatchRail Funded Issues Score", proc.stdout)
        self.assertIn("example/project#42", proc.stdout)
        self.assertNotIn("example/toolkit#17", proc.stdout)
        self.assertIn("Recommended next step", proc.stdout)
        self.assertIn("claim rewards", proc.stdout)
        self.assertIn("automatic_pull_requests", proc.stdout)

    def test_funded_issues_score_filters_by_closed_state(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "score",
                "--source",
                "examples/funded-issues-readonly/issues.json",
                "--include-risky",
                "--opportunity-state",
                "closed",
                "--format",
                "json",
            ]
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["filters"]["opportunity_state"], "closed")
        self.assertEqual(payload["total_scored"], 1)
        self.assertEqual(payload["rating_counts"], {"no_go": 1})
        self.assertEqual(payload["scores"][0]["issue"]["reference"], "example/toolkit#17")
        self.assertIn("CLOSED_OR_INACTIVE", payload["scores"][0]["reason_codes"])

    def test_funded_issues_score_filters_by_low_risk_candidates(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "score",
                "--source",
                "examples/funded-issues-readonly/issues.json",
                "--risk-level",
                "low",
                "--format",
                "json",
            ]
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["filters"]["risk_level"], "low")
        self.assertEqual(payload["total_scored"], 1)
        self.assertEqual(payload["rating_counts"], {"go_candidate": 1})
        self.assertEqual(payload["scores"][0]["issue"]["reference"], "example/project#42")
        self.assertEqual(payload["scores"][0]["issue"]["risk_level"], "low")

    def test_funded_issues_score_marks_unclear_funding_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "issues.json"
            source.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.funded_issues.v1",
                        "issues": [
                            {
                                "id": "unclear",
                                "platform": "github",
                                "repository": "example/unclear",
                                "issue_number": 8,
                                "title": "Investigate funded but unverified issue",
                                "url": "https://github.com/example/unclear/issues/8",
                                "language": "python",
                                "labels": ["bug"],
                                "opportunity_state": "unknown",
                                "contribution_signals": ["reproduction included"],
                                "risk_flags": [],
                                "contribution_guidelines_url": (
                                    "https://github.com/example/unclear/blob/main/CONTRIBUTING.md"
                                ),
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            proc = run_patchrail(
                [
                    "funded-issues",
                    "score",
                    "--source",
                    str(source),
                    "--format",
                    "json",
                ]
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["scores"][0]["decision_gate"], "needs_funding_verification")
        self.assertIn("FUNDING_STATE_UNCLEAR", payload["scores"][0]["reason_codes"])
        self.assertIn("OPPORTUNITY_STATE_UNCLEAR", payload["scores"][0]["reason_codes"])

    def test_funded_issues_score_requires_primary_source_for_discovery_only_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "issues.json"
            source.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.funded_issues.v1",
                        "issues": [
                            {
                                "id": "discovery-only",
                                "platform": "github_l0_l1_review",
                                "repository": "example/discovery",
                                "issue_number": 51,
                                "title": "Funded signal seen through aggregator only",
                                "url": "https://github.com/example/discovery/issues/51",
                                "funding": {"amount": 400, "currency": "USD"},
                                "language": "python",
                                "labels": ["bug"],
                                "opportunity_state": "active",
                                "contribution_signals": [
                                    "reproduction included",
                                    "tests referenced",
                                    "clear failure mode",
                                ],
                                "risk_flags": ["discovery_only_source"],
                                "contribution_guidelines_url": (
                                    "https://github.com/example/discovery/blob/main/CONTRIBUTING.md"
                                ),
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            score_proc = run_patchrail(
                [
                    "funded-issues",
                    "score",
                    "--source",
                    str(source),
                    "--include-risky",
                    "--format",
                    "json",
                ]
            )
            report_proc = run_patchrail(
                [
                    "funded-issues",
                    "report",
                    "--source",
                    str(source),
                    "--format",
                    "json",
                ]
            )
            shortlist_proc = run_patchrail(
                [
                    "funded-issues",
                    "shortlist",
                    "--source",
                    str(source),
                    "--format",
                    "json",
                ]
            )

        self.assertEqual(score_proc.returncode, 0, score_proc.stderr)
        score_payload = json.loads(score_proc.stdout)
        row = score_payload["scores"][0]
        self.assertEqual(row["issue"]["reference"], "example/discovery#51")
        self.assertEqual(row["rating"], "watchlist")
        self.assertEqual(row["decision_gate"], "needs_funding_verification")
        self.assertFalse(row["issue"]["safe_to_list"])
        self.assertTrue(row["issue"]["source_review"]["primary_source_required"])
        self.assertTrue(row["issue"]["source_review"]["required_before_shortlist"])
        self.assertEqual(row["issue"]["source_review"]["risk_flags"], ["discovery_only_source"])
        self.assertIn("DISCOVERY_ONLY_SOURCE", row["reason_codes"])
        self.assertIn("permitted primary public/API source", row["recommended_next_step"])

        self.assertEqual(report_proc.returncode, 0, report_proc.stderr)
        report_payload = json.loads(report_proc.stdout)
        self.assertEqual(report_payload["totals"]["safe_to_list"], 0)
        self.assertEqual(report_payload["decision_summary"]["verification_needed"], 1)
        self.assertEqual(
            report_payload["source_quality"]["summary"]["funding_verification_needed"],
            1,
        )
        self.assertEqual(
            report_payload["source_quality"]["summary"]["status"],
            "needs_funding_verification",
        )
        self.assertEqual(
            report_payload["recheck_plan"]["action_counts"],
            {"verify_funding_visibility": 1},
        )
        self.assertEqual(
            report_payload["recheck_plan"]["next_rows"][0]["action"],
            "verify_funding_visibility",
        )

        self.assertEqual(shortlist_proc.returncode, 0, shortlist_proc.stderr)
        shortlist_payload = json.loads(shortlist_proc.stdout)
        self.assertEqual(shortlist_payload["shortlist"], [])
        self.assertEqual(shortlist_payload["decision_summary"]["verification_needed"], 1)

    def test_funded_issues_score_marks_authorization_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "issues.json"
            source.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.funded_issues.v1",
                        "issues": [
                            {
                                "id": "authorization",
                                "platform": "algora",
                                "repository": "example/authorization",
                                "issue_number": 12,
                                "title": "Requires private maintainer contact",
                                "url": "https://github.com/example/authorization/issues/12",
                                "funding": {"amount": 1000, "currency": "USD"},
                                "language": "typescript",
                                "labels": ["integration"],
                                "opportunity_state": "active",
                                "contribution_signals": ["requires maintainer confirmation"],
                                "risk_flags": ["requires_external_contact"],
                                "contribution_guidelines_url": (
                                    "https://github.com/example/authorization/blob/main/CONTRIBUTING.md"
                                ),
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            proc = run_patchrail(
                [
                    "funded-issues",
                    "score",
                    "--source",
                    str(source),
                    "--include-risky",
                    "--format",
                    "json",
                ]
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["scores"][0]["decision_gate"], "needs_authorization")
        self.assertIn("NEEDS_AUTHORIZATION", payload["scores"][0]["reason_codes"])

    def test_funded_issues_shortlist_builds_decision_support_artifact(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "shortlist",
                "--source",
                "examples/funded-issues-readonly/issues.json",
                "--format",
                "json",
            ]
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["schema_version"], "patchrail.funded_issues.shortlist.v1")
        self.assertEqual(payload["read_only"], True)
        self.assertEqual(payload["summary"]["total_loaded"], 2)
        self.assertEqual(payload["client_fit_gaps"], [])
        self.assertEqual(payload["summary"]["opportunity_states"], {"active": 1, "closed": 1})
        self.assertEqual(payload["summary"]["rating_counts"], {"go_candidate": 1, "no_go": 1})
        self.assertEqual(payload["shortlist"][0]["issue"]["reference"], "example/project#42")
        self.assertEqual(payload["shortlist"][0]["confidence"], 0.99)
        self.assertEqual(payload["shortlist"][0]["rating"], "go_candidate")
        self.assertEqual(payload["shortlist"][0]["decision_gate"], "go_after_recheck")
        self.assertIn("Reproduce locally", payload["shortlist"][0]["recommended_next_step"])
        self.assertEqual(payload["no_go_evidence"][0]["issue"]["reference"], "example/toolkit#17")
        self.assertEqual(payload["no_go_evidence"][0]["issue"]["opportunity_state"], "closed")
        self.assertEqual(payload["no_go_evidence"][0]["confidence"], 0.3)
        self.assertEqual(payload["no_go_evidence"][0]["rating"], "no_go")
        self.assertEqual(payload["no_go_evidence"][0]["decision_gate"], "no_go")
        self.assertIn("Do not engage", payload["no_go_evidence"][0]["recommended_next_step"])
        self.assertEqual(payload["no_go_moat"]["ambiguous_scope"], 1)
        self.assertEqual(payload["no_go_moat"]["stale_or_closed"], 1)
        self.assertEqual(payload["decision_summary"]["candidate_rows"], 1)
        self.assertEqual(payload["decision_summary"]["no_go_rows"], 1)
        self.assertEqual(payload["decision_summary"]["gate_counts"]["go_after_recheck"], 1)
        self.assertEqual(payload["decision_summary"]["gate_counts"]["no_go"], 1)
        self.assertIn(
            "verify public state",
            payload["decision_summary"]["recommended_batch_action"],
        )
        self.assertIn("do not claim", payload["decision_summary"]["safety_boundary"])
        self.assertEqual(payload["delivery_budget"]["suggested_package"], "mini_diagnostic")
        self.assertEqual(payload["delivery_budget"]["estimated_review_minutes"], 13)
        self.assertTrue(payload["delivery_budget"]["within_margin_budget"])
        self.assertEqual(
            payload["delivery_budget"]["analysis_rows"]["l1_state_and_noise_review"], 1
        )
        self.assertEqual(
            payload["delivery_budget"]["analysis_rows"]["l2_scope_and_readiness_review"], 1
        )
        self.assertEqual(payload["delivery_pack"]["suggested_package"], "mini_diagnostic")
        self.assertEqual(
            payload["delivery_pack"]["handoff"]["candidate_references"],
            ["example/project#42"],
        )
        self.assertEqual(
            payload["delivery_pack"]["handoff"]["no_go_references"],
            ["example/toolkit#17"],
        )
        self.assertEqual(
            payload["delivery_pack"]["phases"][1]["phase"],
            "l2_shortlist_readiness_review",
        )
        self.assertEqual(
            payload["delivery_pack"]["phases"][1]["references"],
            ["example/project#42"],
        )
        source_quality = payload["source_quality"]
        self.assertEqual(source_quality["sources"]["polar"]["candidate_rows"], 1)
        self.assertEqual(source_quality["sources"]["polar"]["usable_signal_ratio"], 1)
        self.assertEqual(source_quality["sources"]["algora"]["no_go_rows"], 1)
        self.assertEqual(source_quality["sources"]["algora"]["usable_signal_ratio"], 0)
        self.assertIn("read-only benchmarking", source_quality["boundary"])
        self.assertEqual(payload["recheck_plan"]["recheck_rows"], 1)
        self.assertEqual(payload["recheck_plan"]["no_go_rows"], 1)
        self.assertEqual(
            payload["recheck_plan"]["next_rows"][0]["action"],
            "recheck_public_issue_state",
        )
        evidence_debt = payload["evidence_debt"]
        self.assertEqual(evidence_debt["status"], "active_evidence_debt")
        self.assertEqual(evidence_debt["blocking_rows"], 1)
        self.assertEqual(evidence_debt["next_action"], "recheck_public_issue_state")
        self.assertEqual(evidence_debt["references"], ["example/project#42"])
        self.assertFalse(evidence_debt["payment_route_allowed_now"])
        self.assertFalse(evidence_debt["external_body_allowed"])
        client_fit_summary = payload["client_fit_summary"]
        self.assertEqual(client_fit_summary["status"], "no_profile")
        self.assertEqual(client_fit_summary["matching_rows"], 2)
        self.assertEqual(client_fit_summary["excluded_rows"], 0)
        intake_followup = payload["intake_followup"]
        self.assertEqual(intake_followup["status"], "needs_buyer_intake")
        self.assertEqual(intake_followup["required_before_paid_delivery"], 3)
        self.assertEqual(
            intake_followup["requested_fields"][0]["field"],
            "preferred_languages",
        )
        cash_path_status = payload["cash_path_status"]
        self.assertEqual(cash_path_status["status"], "needs_buyer_intake")
        self.assertEqual(cash_path_status["next_revenue_action"], "collect_buyer_intake")
        self.assertTrue(cash_path_status["copy_brief_facts_available"])
        self.assertFalse(cash_path_status["payment_route_allowed_now"])
        self.assertTrue(cash_path_status["requires_written_acceptance_before_payment_route"])
        self.assertFalse(cash_path_status["buyer_ready"])
        self.assertIn("internal structured handoff only", cash_path_status["boundary"])
        self.assertIn("does not authorize claims", cash_path_status["boundary"])
        self.assertIn("automatic_claims", payload["blocked_actions"])
        self.assertIn("automatic_issue_comments", payload["blocked_actions"])
        self.assertFalse(payload["requirements"]["network_required"])
        self.assertFalse(payload["requirements"]["github_write_permission_required"])
        self.assertFalse(payload["requirements"]["billing_required"])
        self.assertIn("Decision support only", payload["boundary"])
        self.assertIn("guarantee merge or payout", payload["boundary"])

    def test_funded_issues_shortlist_markdown_preserves_no_go_boundary(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "shortlist",
                "--source",
                "examples/funded-issues-readonly/issues.json",
                "--format",
                "markdown",
            ]
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("# PatchRail Funded Issues Shortlist", proc.stdout)
        self.assertIn("## Decision Summary", proc.stdout)
        self.assertIn("Candidate rows: `1`", proc.stdout)
        self.assertIn("No-go rows: `1`", proc.stdout)
        self.assertIn("`no_go` | 1", proc.stdout)
        self.assertIn("## Delivery Budget", proc.stdout)
        self.assertIn("Suggested package: `mini_diagnostic`", proc.stdout)
        self.assertIn("Estimated local review: `13` minutes", proc.stdout)
        self.assertIn("## Delivery Pack", proc.stdout)
        self.assertIn("Candidate references: `example/project#42`", proc.stdout)
        self.assertIn("No-go references: `example/toolkit#17`", proc.stdout)
        self.assertIn("## Source Quality", proc.stdout)
        self.assertIn("`polar` | 1 | 1 | 0 | 1", proc.stdout)
        self.assertIn("`algora` | 1 | 0 | 1 | 0", proc.stdout)
        self.assertIn("## Recheck Plan", proc.stdout)
        self.assertIn("Archived no-go rows: `1`", proc.stdout)
        self.assertIn("`archive_as_no_go_evidence` | 1", proc.stdout)
        self.assertIn("## Evidence Debt", proc.stdout)
        self.assertIn("Blocking rows: `1`", proc.stdout)
        self.assertIn("References: `example/project#42`", proc.stdout)
        self.assertIn("## Client Fit Summary", proc.stdout)
        self.assertIn("Status: `no_profile`", proc.stdout)
        self.assertIn("## Intake Follow-Up", proc.stdout)
        self.assertIn("Status: `needs_buyer_intake`", proc.stdout)
        self.assertIn("`minimum_payout_usd`", proc.stdout)
        self.assertIn("## Funding Path Status", proc.stdout)
        self.assertIn("Next internal action: `collect_buyer_intake`", proc.stdout)
        self.assertIn("Outbound action allowed now: `False`", proc.stdout)
        self.assertIn("does not create a payment route", proc.stdout)
        self.assertIn("## Shortlist", proc.stdout)
        self.assertIn("example/project#42", proc.stdout)
        self.assertIn("Confidence: `0.99`", proc.stdout)
        self.assertIn("Decision gate", proc.stdout)
        self.assertIn("go_after_recheck", proc.stdout)
        self.assertIn("## No-Go Evidence", proc.stdout)
        self.assertIn("example/toolkit#17", proc.stdout)
        self.assertIn("Recommended next step", proc.stdout)
        self.assertIn("Decision support only", proc.stdout)
        self.assertIn("automatic_pull_requests", proc.stdout)

    def test_funded_issues_shortlist_limit_caps_candidate_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "issues.json"
            source.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.funded_issues.v1",
                        "issues": [
                            {
                                "id": "one",
                                "platform": "polar",
                                "repository": "example/one",
                                "issue_number": 1,
                                "title": "Fix deterministic CI failure",
                                "url": "https://github.com/example/one/issues/1",
                                "funding": {"amount": 100, "currency": "USD"},
                                "language": "python",
                                "opportunity_state": "active",
                                "labels": ["bug"],
                                "contribution_signals": ["reproduction included"],
                                "risk_flags": [],
                                "contribution_guidelines_url": (
                                    "https://github.com/example/one/blob/main/CONTRIBUTING.md"
                                ),
                            },
                            {
                                "id": "two",
                                "platform": "polar",
                                "repository": "example/two",
                                "issue_number": 2,
                                "title": "Repair release workflow",
                                "url": "https://github.com/example/two/issues/2",
                                "funding": {"amount": 200, "currency": "USD"},
                                "language": "python",
                                "opportunity_state": "active",
                                "labels": ["ci"],
                                "contribution_signals": [
                                    "reproduction included",
                                    "failing CI linked",
                                ],
                                "risk_flags": [],
                                "contribution_guidelines_url": (
                                    "https://github.com/example/two/blob/main/CONTRIBUTING.md"
                                ),
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            proc = run_patchrail(
                [
                    "funded-issues",
                    "shortlist",
                    "--source",
                    str(source),
                    "--limit",
                    "1",
                    "--format",
                    "json",
                ]
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["limit"], 1)
        self.assertEqual(len(payload["shortlist"]), 1)
        self.assertEqual(payload["shortlist"][0]["issue"]["reference"], "example/two#2")
        self.assertEqual(payload["summary"]["rating_counts"], {"go_candidate": 2})

    def test_funded_issues_shortlist_filters_no_go_evidence_by_state(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "shortlist",
                "--source",
                "examples/funded-issues-readonly/issues.json",
                "--opportunity-state",
                "closed",
                "--format",
                "json",
            ]
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["filters"]["opportunity_state"], "closed")
        self.assertEqual(payload["summary"]["in_scope"], 1)
        self.assertEqual(payload["shortlist"], [])
        self.assertEqual(len(payload["no_go_evidence"]), 1)
        self.assertEqual(payload["no_go_evidence"][0]["issue"]["reference"], "example/toolkit#17")

    def test_funded_issues_shortlist_filters_by_high_risk_no_go_evidence(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "shortlist",
                "--source",
                "examples/funded-issues-readonly/issues.json",
                "--risk-level",
                "high",
                "--format",
                "json",
            ]
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["filters"]["risk_level"], "high")
        self.assertEqual(payload["summary"]["in_scope"], 1)
        self.assertEqual(payload["shortlist"], [])
        self.assertEqual(len(payload["no_go_evidence"]), 1)
        self.assertEqual(payload["no_go_evidence"][0]["issue"]["reference"], "example/toolkit#17")
        self.assertEqual(payload["no_go_moat"]["high_risk_or_excluded"], 1)

    def test_funded_issues_shortlist_filters_with_client_profile(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "shortlist",
                "--source",
                "examples/funded-issues-readonly/issues.json",
                "--profile",
                "examples/funded-issues-readonly/client-profile-python.json",
                "--format",
                "json",
            ]
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["filters"]["profile"]["name"], "Async Python buyer")
        self.assertTrue(payload["filters"]["profile"]["read_only"])
        self.assertEqual(payload["summary"]["in_scope"], 1)
        self.assertEqual(payload["summary"]["safe_to_list"], 1)
        self.assertEqual(payload["summary"]["high_risk"], 0)
        self.assertEqual(payload["shortlist"][0]["issue"]["reference"], "example/project#42")
        self.assertEqual(payload["no_go_evidence"], [])
        self.assertEqual(len(payload["client_fit_gaps"]), 1)
        self.assertEqual(payload["client_fit_summary"]["profile_name"], "Async Python buyer")
        self.assertEqual(payload["client_fit_summary"]["status"], "partial_match")
        self.assertEqual(payload["client_fit_summary"]["matching_rows"], 1)
        self.assertEqual(payload["client_fit_summary"]["excluded_rows"], 1)
        self.assertEqual(payload["client_fit_summary"]["gap_counts"]["LANGUAGE_MISMATCH"], 1)
        self.assertEqual(payload["client_fit_gaps"][0]["reference"], "example/toolkit#17")
        self.assertEqual(
            payload["client_fit_gaps"][0]["gap_codes"],
            [
                "LANGUAGE_MISMATCH",
                "OPPORTUNITY_STATE_NOT_ALLOWED",
                "RISK_LEVEL_NOT_ALLOWED",
                "EXCLUDED_RISK_FLAG:spam_attractive",
            ],
        )
        self.assertIn("language outside", payload["client_fit_gaps"][0]["gap_summary"])
        self.assertFalse(payload["requirements"]["network_required"])
        self.assertFalse(payload["requirements"]["github_write_permission_required"])

    def test_funded_issues_shortlist_profile_can_exclude_all_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp) / "profile.json"
            profile.write_text(
                json.dumps(
                    {
                        "schema_version": "patchrail.funded_issues.client_profile.v1",
                        "name": "High threshold Python buyer",
                        "languages": ["python"],
                        "min_usd": 1000,
                        "allowed_opportunity_states": ["active"],
                        "allowed_risk_levels": ["low"],
                        "excluded_risk_flags": [],
                        "read_only": True,
                    }
                ),
                encoding="utf-8",
            )

            proc = run_patchrail(
                [
                    "funded-issues",
                    "shortlist",
                    "--source",
                    "examples/funded-issues-readonly/issues.json",
                    "--profile",
                    str(profile),
                    "--format",
                    "json",
                ]
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["filters"]["profile"]["name"], "High threshold Python buyer")
        self.assertEqual(payload["summary"]["in_scope"], 0)
        self.assertEqual(payload["summary"]["total_scored"], 0)
        self.assertEqual(payload["shortlist"], [])
        self.assertEqual(payload["no_go_evidence"], [])
        self.assertEqual(len(payload["client_fit_gaps"]), 2)
        self.assertEqual(payload["client_fit_summary"]["status"], "no_matching_rows")
        self.assertEqual(payload["client_fit_summary"]["matching_rows"], 0)
        self.assertEqual(payload["client_fit_summary"]["excluded_rows"], 2)
        self.assertIn(
            "Do not pitch this batch",
            payload["client_fit_summary"]["recommended_action"],
        )
        self.assertEqual(payload["client_fit_gaps"][0]["reference"], "example/project#42")
        self.assertEqual(
            payload["client_fit_gaps"][0]["gap_codes"],
            ["FUNDING_BELOW_MIN_USD"],
        )
        self.assertEqual(payload["delivery_budget"]["suggested_package"], "none")

    def test_funded_issues_shortlist_rejects_invalid_limit(self) -> None:
        proc = run_patchrail(
            [
                "funded-issues",
                "shortlist",
                "--source",
                "examples/funded-issues-readonly/issues.json",
                "--limit",
                "0",
            ]
        )

        self.assertEqual(proc.returncode, 1)
        self.assertIn("limit must be >= 1", proc.stderr)

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


class PatchRailFundedIssuesCompetitionCliTests(unittest.TestCase):
    def test_competition_default_source_emits_sorted_json(self) -> None:
        proc = run_patchrail(["funded-issues", "competition", "--format", "json"])

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["schema_version"], "patchrail.funded_issues.competition_batch.v1")
        self.assertTrue(payload["read_only"])
        self.assertEqual(payload["reviewed"], 4)
        self.assertEqual(payload["results"][0]["reference"], "example/toolkit#17")
        self.assertEqual(payload["results"][0]["level"], "high")
        self.assertEqual(payload["summary"]["high"], 1)
        self.assertEqual(payload["summary"]["elevated"], 2)
        self.assertEqual(payload["summary"]["low"], 1)
        self.assertEqual(payload["summary"]["noise_traps"], 3)
        self.assertIn("automatic_claims", payload["blocked_actions"])

    def test_competition_accepts_bare_list_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "obs.json"
            source.write_text(
                json.dumps(
                    [
                        {"reference": "a/b#1", "comment_count": 2},
                        {
                            "reference": "c/d#2",
                            "competing_pr_count": 5,
                            "assigned": True,
                        },
                    ]
                ),
                encoding="utf-8",
            )
            proc = run_patchrail(
                ["funded-issues", "competition", "--source", str(source), "--format", "json"]
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["reviewed"], 2)
        self.assertEqual(payload["summary"]["contested_bounty"], 1)

    def test_competition_markdown_lists_results_table(self) -> None:
        proc = run_patchrail(["funded-issues", "competition"])

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("# PatchRail Funded Issues Competition Signal", proc.stdout)
        self.assertIn("| Reference | Level | Risk flags |", proc.stdout)
        self.assertIn("example/toolkit#17", proc.stdout)

    def test_competition_rejects_invalid_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "bad.json"
            source.write_text(json.dumps([{"competing_pr_count": -1}]), encoding="utf-8")
            proc = run_patchrail(
                ["funded-issues", "competition", "--source", str(source), "--format", "json"]
            )

        self.assertEqual(proc.returncode, 1)
        self.assertIn("Invalid competition observations source", proc.stderr)


class PatchRailFundedIssuesPayoutEffortCliTests(unittest.TestCase):
    def test_payout_effort_default_source_emits_sorted_json(self) -> None:
        proc = run_patchrail(["funded-issues", "payout-effort", "--format", "json"])

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(
            payload["schema_version"], "patchrail.funded_issues.payout_effort_batch.v1"
        )
        self.assertTrue(payload["read_only"])
        self.assertEqual(payload["reviewed"], 5)
        self.assertEqual(payload["results"][0]["reference"], "example/toolkit#17")
        self.assertEqual(payload["results"][0]["level"], "low")
        self.assertEqual(payload["results"][-1]["level"], "strong")
        summary = payload["summary"]
        self.assertEqual(summary["low"], 1)
        self.assertEqual(summary["marginal"], 1)
        self.assertEqual(summary["strong"], 1)
        self.assertEqual(summary["unknown"], 1)
        self.assertEqual(summary["unverified_currency"], 1)
        self.assertEqual(summary["underpaid"], 1)
        self.assertIn("automatic_claims", payload["blocked_actions"])

    def test_payout_effort_accepts_bare_list_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "obs.json"
            source.write_text(
                json.dumps(
                    [
                        {
                            "reference": "a/b#1",
                            "funding_amount": 250,
                            "estimated_effort_hours": 10,
                        },
                        {
                            "reference": "c/d#2",
                            "funding_amount": 2400,
                            "estimated_effort_hours": 12,
                        },
                    ]
                ),
                encoding="utf-8",
            )
            proc = run_patchrail(
                ["funded-issues", "payout-effort", "--source", str(source), "--format", "json"]
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["reviewed"], 2)
        self.assertEqual(payload["summary"]["underpaid"], 1)

    def test_payout_effort_markdown_lists_results_table(self) -> None:
        proc = run_patchrail(["funded-issues", "payout-effort"])

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("# PatchRail Funded Issues Payout-vs-Effort Signal", proc.stdout)
        self.assertIn("| Reference | Level | Risk flags |", proc.stdout)
        self.assertIn("example/toolkit#17", proc.stdout)

    def test_payout_effort_rejects_invalid_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "bad.json"
            source.write_text(
                json.dumps([{"funding_amount": -1, "estimated_effort_hours": 1}]),
                encoding="utf-8",
            )
            proc = run_patchrail(
                ["funded-issues", "payout-effort", "--source", str(source), "--format", "json"]
            )

        self.assertEqual(proc.returncode, 1)
        self.assertIn("Invalid payout-effort observations source", proc.stderr)

    def test_staleness_default_source_emits_sorted_json(self) -> None:
        proc = run_patchrail(["funded-issues", "staleness", "--format", "json"])

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["schema_version"], "patchrail.funded_issues.staleness_batch.v1")
        self.assertTrue(payload["read_only"])
        self.assertEqual(payload["reviewed"], 5)
        self.assertEqual(payload["results"][0]["reference"], "example/cli#210")
        self.assertEqual(payload["results"][0]["level"], "dormant")
        self.assertEqual(payload["results"][-1]["level"], "active")
        summary = payload["summary"]
        self.assertEqual(summary["active"], 1)
        self.assertEqual(summary["stale"], 2)
        self.assertEqual(summary["dormant"], 1)
        self.assertEqual(summary["unknown"], 1)
        self.assertEqual(summary["stale_or_dormant"], 3)
        self.assertIn("automatic_claims", payload["blocked_actions"])

    def test_staleness_accepts_bare_list_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "obs.json"
            source.write_text(
                json.dumps(
                    [
                        {"reference": "a/b#1", "days_since_last_activity": 400},
                        {"reference": "c/d#2", "days_since_last_activity": 5},
                    ]
                ),
                encoding="utf-8",
            )
            proc = run_patchrail(
                ["funded-issues", "staleness", "--source", str(source), "--format", "json"]
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["reviewed"], 2)
        self.assertEqual(payload["summary"]["dormant"], 1)
        self.assertEqual(payload["results"][0]["reference"], "a/b#1")

    def test_staleness_markdown_lists_results_table(self) -> None:
        proc = run_patchrail(["funded-issues", "staleness"])

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("# PatchRail Funded Issues Staleness Signal", proc.stdout)
        self.assertIn("| Reference | Level | Risk flags |", proc.stdout)
        self.assertIn("example/cli#210", proc.stdout)

    def test_staleness_rejects_invalid_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "bad.json"
            source.write_text(
                json.dumps([{"days_since_last_activity": -1}]),
                encoding="utf-8",
            )
            proc = run_patchrail(
                ["funded-issues", "staleness", "--source", str(source), "--format", "json"]
            )

        self.assertEqual(proc.returncode, 1)
        self.assertIn("Invalid staleness observations source", proc.stderr)

    def test_testability_default_source_emits_sorted_json(self) -> None:
        proc = run_patchrail(["funded-issues", "testability", "--format", "json"])

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["schema_version"], "patchrail.funded_issues.testability_batch.v1")
        self.assertTrue(payload["read_only"])
        self.assertEqual(payload["reviewed"], 5)
        self.assertEqual(payload["results"][0]["reference"], "example/cli#210")
        self.assertEqual(payload["results"][0]["level"], "unverifiable")
        self.assertEqual(payload["results"][-1]["level"], "verifiable")
        summary = payload["summary"]
        self.assertEqual(summary["verifiable"], 1)
        self.assertEqual(summary["partially_verifiable"], 2)
        self.assertEqual(summary["unverifiable"], 1)
        self.assertEqual(summary["unknown"], 1)
        self.assertIn("automatic_claims", payload["blocked_actions"])

    def test_testability_accepts_bare_list_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "obs.json"
            source.write_text(
                json.dumps(
                    [
                        {"reference": "a/b#1"},
                        {"reference": "c/d#2", "has_failing_test": True},
                    ]
                ),
                encoding="utf-8",
            )
            proc = run_patchrail(
                ["funded-issues", "testability", "--source", str(source), "--format", "json"]
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["reviewed"], 2)
        self.assertEqual(payload["summary"]["unknown"], 1)
        self.assertEqual(payload["summary"]["verifiable"], 1)
        self.assertEqual(payload["results"][-1]["reference"], "c/d#2")

    def test_testability_markdown_lists_results_table(self) -> None:
        proc = run_patchrail(["funded-issues", "testability"])

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("# PatchRail Funded Issues Testability Signal", proc.stdout)
        self.assertIn("| Reference | Level | Risk flags |", proc.stdout)
        self.assertIn("example/cli#210", proc.stdout)

    def test_testability_rejects_invalid_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "bad.json"
            source.write_text(
                json.dumps([{"has_failing_test": "maybe"}]),
                encoding="utf-8",
            )
            proc = run_patchrail(
                ["funded-issues", "testability", "--source", str(source), "--format", "json"]
            )

        self.assertEqual(proc.returncode, 1)
        self.assertIn("Invalid testability observations source", proc.stderr)


if __name__ == "__main__":
    unittest.main()
