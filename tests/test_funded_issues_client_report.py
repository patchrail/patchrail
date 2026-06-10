from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from patchrail.funded_issues import client_report_funded_issues, load_funded_issues


def run_patchrail(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "patchrail", *args],
        text=True,
        capture_output=True,
        check=False,
    )


SECTION_HEADERS = [
    "## 1. Executive summary",
    "## 2. Top recommendations",
    "## 3. Watchlist",
    "## 4. No-go list",
    "## 5. No-go moat evidence",
    "## 6. Patterns observed",
    "## 7. Recommended operating procedure",
    "## 8. Disclaimer",
]

DISCLAIMER = (
    "This report is read-only opportunity intelligence. It does not guarantee bounty "
    "availability, merge acceptance, payout, or maintainer response. No claims, comments, "
    "outreach, or PR submissions were made by PatchRail unless explicitly authorized in writing."
)

INTERNAL_SECTIONS = {
    "delivery_budget",
    "delivery_pack",
    "source_quality",
    "recheck_plan",
    "evidence_debt",
    "intake_followup",
    "cash_path_status",
    "operator_next_steps",
}


def _fixture_payload() -> dict:
    return {
        "schema_version": "patchrail.funded_issues.v1",
        "issues": [
            {
                "id": "polar-go-1",
                "platform": "polar",
                "repository": "example/go-pick",
                "issue_number": 11,
                "title": "Fix unicode parser edge case",
                "url": "https://github.com/example/go-pick/issues/11",
                "funding": {"amount": 1000, "currency": "USD"},
                "language": "python",
                "labels": ["bug"],
                "opportunity_state": "active",
                "contribution_signals": [
                    "reproduction included",
                    "failing test path identified",
                    "tests documented",
                ],
                "risk_flags": [],
                "maintainer_permission": "public_issue_only",
                "contribution_guidelines_url": "https://github.com/example/go-pick/blob/main/CONTRIBUTING.md",
            },
            {
                "id": "polar-watch-1",
                "platform": "polar",
                "repository": "example/watch-pick",
                "issue_number": 22,
                "title": "Clarify date formatting behavior",
                "url": "https://github.com/example/watch-pick/issues/22",
                "funding": {"amount": 500, "currency": "USD"},
                "language": "typescript",
                "labels": ["needs-discussion"],
                "opportunity_state": "active",
                "contribution_signals": [],
                "risk_flags": [],
                "maintainer_permission": "public_issue_only",
            },
            {
                "id": "algora-nogo-1",
                "platform": "algora",
                "repository": "example/nogo-pick",
                "issue_number": 33,
                "title": "Rewrite the plugin system",
                "url": "https://github.com/example/nogo-pick/issues/33",
                "funding": {"amount": 2500, "currency": "USD"},
                "language": "rust",
                "labels": ["architecture", "stale"],
                "opportunity_state": "stale",
                "contribution_signals": ["large design surface"],
                "risk_flags": ["ambiguous_scope", "spam_attractive"],
                "maintainer_permission": "public_issue_only",
            },
        ],
    }


def _build_payload() -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "issues.json"
        source.write_text(json.dumps(_fixture_payload()), encoding="utf-8")
        issues = load_funded_issues(source)
    return client_report_funded_issues(
        issues,
        client_name="Acme Corp",
        report_date="2026-06-09",
    )


class ClientReportPayloadTests(unittest.TestCase):
    def test_payload_structure_and_metadata(self) -> None:
        payload = _build_payload()
        self.assertEqual(payload["schema_version"], "patchrail.funded_issues.client_report.v1")
        self.assertEqual(payload["source_schema_version"], "patchrail.funded_issues.v1")
        self.assertTrue(payload["read_only"])
        self.assertEqual(payload["client_name"], "Acme Corp")
        self.assertEqual(payload["prepared_by"], "PatchRail Opportunity Desk")
        self.assertEqual(payload["date"], "2026-06-09")
        self.assertFalse(payload["requirements"]["network_required"])
        self.assertFalse(payload["requirements"]["billing_required"])

    def test_executive_summary_counts(self) -> None:
        payload = _build_payload()
        summary = payload["executive_summary"]
        self.assertEqual(summary["reviewed"], 3)
        self.assertEqual(summary["go"], 1)
        self.assertEqual(summary["watchlist"], 1)
        self.assertEqual(summary["no_go"], 1)
        self.assertEqual(summary["actionable_percent"], round(100 * 1 / 3, 1))
        self.assertEqual(summary["top_recommendation"], "example/go-pick#11 (1000 USD, Go)")
        self.assertIsNotNone(summary["dominant_no_go_reason"])
        self.assertEqual(summary["dominant_no_go_reason"]["of_total"], 1)

    def test_go_watchlist_no_go_mapping(self) -> None:
        payload = _build_payload()
        self.assertEqual(len(payload["top_recommendations"]), 1)
        self.assertEqual(payload["top_recommendations"][0]["reference"], "example/go-pick#11")
        self.assertEqual(payload["top_recommendations"][0]["decision"], "Go")
        self.assertEqual(payload["top_recommendations"][0]["payout"], "1000 USD")
        self.assertEqual(len(payload["watchlist"]), 1)
        self.assertEqual(payload["watchlist"][0]["reference"], "example/watch-pick#22")
        self.assertIn("trigger_to_promote", payload["watchlist"][0])
        self.assertEqual(len(payload["no_go_list"]), 1)
        self.assertEqual(payload["no_go_list"][0]["reference"], "example/nogo-pick#33")
        self.assertIn("STALE_NO_MAINTAINER_SIGNAL", payload["no_go_list"][0]["reason_codes"])

    def test_no_go_moat_evidence_counts(self) -> None:
        payload = _build_payload()
        moat = payload["no_go_moat_evidence"]
        self.assertEqual(moat["raw_results_reviewed"], 3)
        self.assertEqual(moat["in_scope_reviewed"], 3)
        self.assertEqual(moat["final_go_candidates"], 1)
        self.assertEqual(moat["stale_or_closed"], 1)
        self.assertEqual(moat["ambiguous_scope"], 1)
        self.assertEqual(moat["spam_attractive"], 1)

    def test_patterns_observed_derived_from_payload(self) -> None:
        payload = _build_payload()
        patterns = payload["patterns_observed"]
        self.assertIn("STALE_NO_MAINTAINER_SIGNAL", patterns["no_go_reason_code_counts"])
        self.assertEqual(patterns["go_platform_counts"], {"polar": 1})
        self.assertEqual(patterns["go_language_counts"], {"python": 1})
        self.assertEqual(patterns["no_go_platform_counts"], {"algora": 1})

    def test_recommended_operating_procedure_derived(self) -> None:
        payload = _build_payload()
        steps = payload["recommended_operating_procedure"]
        self.assertTrue(any("example/go-pick#11" in step for step in steps))
        self.assertTrue(any("No-go list" in step for step in steps))

    def test_disclaimer_present_and_fixed(self) -> None:
        payload = _build_payload()
        self.assertEqual(payload["disclaimer"], DISCLAIMER)

    def test_excludes_internal_operator_sections(self) -> None:
        payload = _build_payload()
        self.assertEqual(INTERNAL_SECTIONS & set(payload), set())

    def test_requires_client_name_and_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "issues.json"
            source.write_text(json.dumps(_fixture_payload()), encoding="utf-8")
            issues = load_funded_issues(source)
        with self.assertRaises(ValueError):
            client_report_funded_issues(issues, client_name="  ", report_date="2026-06-09")
        with self.assertRaises(ValueError):
            client_report_funded_issues(issues, client_name="Acme", report_date="")

    def test_rejects_malformed_report_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "issues.json"
            source.write_text(json.dumps(_fixture_payload()), encoding="utf-8")
            issues = load_funded_issues(source)
        for bad in ("next tuesday", "2026-13-45", "06/09/2026", "2026-6-9x"):
            with self.assertRaises(ValueError):
                client_report_funded_issues(issues, client_name="Acme", report_date=bad)

    def test_normalizes_valid_report_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "issues.json"
            source.write_text(json.dumps(_fixture_payload()), encoding="utf-8")
            issues = load_funded_issues(source)
        payload = client_report_funded_issues(
            issues, client_name="Acme", report_date="  2026-06-09  "
        )
        self.assertEqual(payload["date"], "2026-06-09")


class ClientReportCliTests(unittest.TestCase):
    def _write_fixture(self, tmp: str) -> Path:
        source = Path(tmp) / "issues.json"
        source.write_text(json.dumps(_fixture_payload()), encoding="utf-8")
        return source

    def test_cli_markdown_contains_all_eight_section_headers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = self._write_fixture(tmp)
            proc = run_patchrail(
                [
                    "funded-issues",
                    "client-report",
                    "--source",
                    str(source),
                    "--client-name",
                    "Acme Corp",
                    "--date",
                    "2026-06-09",
                    "--format",
                    "markdown",
                ]
            )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        for header in SECTION_HEADERS:
            self.assertIn(header, proc.stdout)
        self.assertIn("Prepared for: Acme Corp", proc.stdout)
        self.assertIn(DISCLAIMER, proc.stdout)

    def test_cli_json_matches_schema_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = self._write_fixture(tmp)
            payload_proc = run_patchrail(
                [
                    "funded-issues",
                    "client-report",
                    "--source",
                    str(source),
                    "--client-name",
                    "Acme Corp",
                    "--date",
                    "2026-06-09",
                    "--prepared-by",
                    "PatchRail Opportunity Desk",
                    "--format",
                    "json",
                ]
            )
        schema_proc = run_patchrail(["schema", "funded-issues-client-report"])

        self.assertEqual(payload_proc.returncode, 0, payload_proc.stderr)
        self.assertEqual(schema_proc.returncode, 0, schema_proc.stderr)
        payload = json.loads(payload_proc.stdout)
        schema = json.loads(schema_proc.stdout)
        self.assertEqual(
            schema["$id"],
            "https://patchrail.dev/schemas/funded-issues-client-report.v1.schema.json",
        )
        self.assertEqual(
            schema["properties"]["schema_version"]["const"],
            "patchrail.funded_issues.client_report.v1",
        )
        self.assertEqual(schema["properties"]["read_only"]["const"], True)
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(sorted(schema["required"]), sorted(payload.keys()))
        self.assertEqual(
            sorted(schema["$defs"]["executive_summary"]["required"]),
            sorted(payload["executive_summary"].keys()),
        )
        self.assertEqual(
            sorted(schema["$defs"]["recommendation"]["required"]),
            sorted(payload["top_recommendations"][0].keys()),
        )
        self.assertEqual(
            sorted(schema["$defs"]["watchlist_row"]["required"]),
            sorted(payload["watchlist"][0].keys()),
        )
        self.assertEqual(
            sorted(schema["$defs"]["no_go_row"]["required"]),
            sorted(payload["no_go_list"][0].keys()),
        )
        self.assertEqual(
            sorted(schema["$defs"]["no_go_moat_evidence"]["required"]),
            sorted(payload["no_go_moat_evidence"].keys()),
        )
        self.assertEqual(
            sorted(schema["$defs"]["patterns_observed"]["required"]),
            sorted(payload["patterns_observed"].keys()),
        )
        for section in INTERNAL_SECTIONS:
            self.assertNotIn(section, schema["required"])

    def test_cli_requires_client_name_and_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = self._write_fixture(tmp)
            proc = run_patchrail(
                [
                    "funded-issues",
                    "client-report",
                    "--source",
                    str(source),
                ]
            )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("--client-name", proc.stderr)


if __name__ == "__main__":
    unittest.main()
