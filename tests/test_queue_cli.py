from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from patchrail.queue.status import _redact_local_paths


def run_patchrail(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "patchrail", *args],
        text=True,
        capture_output=True,
        check=False,
    )


class PatchRailQueueTests(unittest.TestCase):
    def test_queue_status_redaction_masks_local_paths_in_public_payloads(self) -> None:
        payload = {
            "db_path": "/Volumes/CorsairSSD/OpenClaw/tmp/queue.sqlite",
            "work_items": [
                {
                    "payload": {
                        "report": "/Users/pablo/project/report.md",
                        "notes": "runner path /home/runner/work/patchrail/report.json",
                    }
                }
            ],
        }

        redacted = _redact_local_paths(payload)
        serialized = json.dumps(redacted)

        self.assertEqual(redacted["db_path"], "<local-path>/queue.sqlite")
        self.assertEqual(redacted["work_items"][0]["payload"]["report"], "<local-path>/report.md")
        self.assertIn("<local-path>/report.json", redacted["work_items"][0]["payload"]["notes"])
        self.assertNotIn("/Volumes/", serialized)
        self.assertNotIn("/Users/", serialized)
        self.assertNotIn("/home/", serialized)

    def test_queue_schema_command_exposes_public_control_plane_contracts(self) -> None:
        expected_titles = {
            "queue-status": "PatchRail Queue Status",
            "queue-work-item": "PatchRail Queue Work Item",
            "queue-proposal": "PatchRail Queue Proposal",
            "queue-audit-event": "PatchRail Queue Audit Event",
            "queue-audit-summary": "PatchRail Queue Audit Summary",
        }
        for schema_name, title in expected_titles.items():
            proc = run_patchrail(["schema", schema_name])

            self.assertEqual(proc.returncode, 0, proc.stderr)
            schema = json.loads(proc.stdout)
            self.assertEqual(schema["title"], title)
            self.assertIn("https://patchrail.dev/schemas/", schema["$id"])
            if schema_name == "queue-status":
                self.assertIn("human_gate_summary", schema["required"])
                self.assertEqual(
                    schema["properties"]["human_gate_summary"]["properties"][
                        "write_actions_unlocked"
                    ]["const"],
                    False,
                )

    def test_queue_flow_keeps_work_items_local_and_human_gated(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "queue.sqlite"

            init_proc = run_patchrail(["queue", "--db", str(db), "init"])
            self.assertEqual(init_proc.returncode, 0, init_proc.stderr)
            init_payload = json.loads(init_proc.stdout)
            self.assertEqual(init_payload["schema_version"], "patchrail.queue.v1")
            self.assertEqual(init_payload["write_actions_allowed_by_default"], False)

            add_proc = run_patchrail(
                [
                    "queue",
                    "--db",
                    str(db),
                    "add",
                    "--kind",
                    "ci_failure",
                    "--title",
                    "Investigate failing dependency install",
                    "--source",
                    "local-fixture",
                    "--payload-json",
                    '{"report": "patchrail-ci-report.md"}',
                ]
            )
            self.assertEqual(add_proc.returncode, 0, add_proc.stderr)
            added = json.loads(add_proc.stdout)
            self.assertEqual(added["approval_state"], "pending")
            self.assertEqual(added["write_actions_allowed"], False)
            self.assertEqual(added["payload"]["report"], "patchrail-ci-report.md")

            list_proc = run_patchrail(
                [
                    "queue",
                    "--db",
                    str(db),
                    "list",
                    "--approval-state",
                    "pending",
                    "--format",
                    "json",
                ]
            )
            self.assertEqual(list_proc.returncode, 0, list_proc.stderr)
            listed = json.loads(list_proc.stdout)
            self.assertEqual(len(listed["work_items"]), 1)
            self.assertEqual(listed["work_items"][0]["id"], added["id"])

            approve_proc = run_patchrail(
                [
                    "queue",
                    "--db",
                    str(db),
                    "approve",
                    added["id"],
                    "--note",
                    "Maintainer reviewed the local report.",
                ]
            )
            self.assertEqual(approve_proc.returncode, 0, approve_proc.stderr)
            approved = json.loads(approve_proc.stdout)
            self.assertEqual(approved["approval_state"], "approved")
            self.assertEqual(approved["status"], "open")
            self.assertEqual(approved["write_actions_allowed"], False)

            export_proc = run_patchrail(["queue", "--db", str(db), "export", "--format", "jsonl"])
            self.assertEqual(export_proc.returncode, 0, export_proc.stderr)
            exported = [json.loads(line) for line in export_proc.stdout.splitlines()]
            self.assertEqual(exported[0]["id"], added["id"])

            audit_proc = run_patchrail(["queue", "--db", str(db), "audit", "--format", "json"])
            self.assertEqual(audit_proc.returncode, 0, audit_proc.stderr)
            audit = json.loads(audit_proc.stdout)
            self.assertEqual(
                [event["event_type"] for event in audit["audit_events"]],
                ["work_item_added", "work_item_approved", "work_items_exported"],
            )
            self.assertEqual(audit["audit_events"][0]["work_item_id"], added["id"])
            self.assertEqual(
                audit["audit_events"][1]["payload"]["decision_note"], approved["decision_note"]
            )
            self.assertEqual(audit["audit_events"][2]["payload"]["count"], 1)

            audit_summary_proc = run_patchrail(
                [
                    "queue",
                    "--db",
                    str(db),
                    "audit-summary",
                    "--format",
                    "json",
                    "--require-event",
                    "work_item_added",
                    "--require-event",
                    "work_item_approved",
                    "--require-event",
                    "work_items_exported",
                ]
            )
            self.assertEqual(audit_summary_proc.returncode, 0, audit_summary_proc.stderr)
            audit_summary = json.loads(audit_summary_proc.stdout)
            self.assertEqual(
                audit_summary["schema_version"],
                "patchrail.queue_audit_summary.v1",
            )
            self.assertEqual(audit_summary["status"], "human_gates_exercised")
            self.assertEqual(audit_summary["missing_required_events"], [])
            self.assertEqual(audit_summary["counts"]["audit_events_total"], 3)
            self.assertEqual(audit_summary["counts"]["event_types"]["work_item_added"], 1)
            self.assertEqual(audit_summary["counts"]["affected_work_items"], 1)
            self.assertEqual(audit_summary["gates"]["work_item_approval_gate_exercised"], True)
            self.assertEqual(audit_summary["gates"]["queue_export_recorded"], True)
            self.assertEqual(
                audit_summary["safety"]["approval_records_execute_actions"],
                False,
            )

            item_audit_proc = run_patchrail(
                [
                    "queue",
                    "--db",
                    str(db),
                    "audit",
                    "--item-id",
                    added["id"],
                    "--format",
                    "jsonl",
                ]
            )
            self.assertEqual(item_audit_proc.returncode, 0, item_audit_proc.stderr)
            item_events = [json.loads(line) for line in item_audit_proc.stdout.splitlines()]
            self.assertEqual(
                [event["event_type"] for event in item_events],
                ["work_item_added", "work_item_approved"],
            )

    def test_queue_outputs_match_public_schema_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "queue.sqlite"
            add_proc = run_patchrail(
                [
                    "queue",
                    "--db",
                    str(db),
                    "add",
                    "--kind",
                    "ci_failure",
                    "--title",
                    "Review failing dependency install",
                    "--payload-json",
                    '{"report": "ci-result.json"}',
                ]
            )
            self.assertEqual(add_proc.returncode, 0, add_proc.stderr)
            item = json.loads(add_proc.stdout)

            proposal_proc = run_patchrail(
                [
                    "queue",
                    "--db",
                    str(db),
                    "proposal",
                    "add",
                    "--item-id",
                    item["id"],
                    "--title",
                    "Patch dependency range",
                    "--summary",
                    "Prepare a local patch plan for maintainer review.",
                    "--patch-plan",
                    "1. Reproduce.\n2. Patch.\n3. Test.",
                    "--risk-level",
                    "low",
                ]
            )
            self.assertEqual(proposal_proc.returncode, 0, proposal_proc.stderr)
            proposal = json.loads(proposal_proc.stdout)

            audit_proc = run_patchrail(["queue", "--db", str(db), "audit", "--format", "json"])
            self.assertEqual(audit_proc.returncode, 0, audit_proc.stderr)
            audit_event = json.loads(audit_proc.stdout)["audit_events"][0]

            item_schema = json.loads(run_patchrail(["schema", "queue-work-item"]).stdout)
            proposal_schema = json.loads(run_patchrail(["schema", "queue-proposal"]).stdout)
            audit_schema = json.loads(run_patchrail(["schema", "queue-audit-event"]).stdout)

            self.assertEqual(sorted(item_schema["required"]), sorted(item))
            self.assertEqual(sorted(proposal_schema["required"]), sorted(proposal))
            self.assertEqual(sorted(audit_schema["required"]), sorted(audit_event))
            self.assertEqual(item["write_actions_allowed"], False)
            self.assertEqual(item_schema["properties"]["write_actions_allowed"]["const"], False)
            self.assertEqual(item["approval_state"], "pending")
            self.assertEqual(proposal["approval_state"], "pending")

    def test_queue_audit_summary_requires_gate_events_for_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "queue.sqlite"
            add_proc = run_patchrail(
                [
                    "queue",
                    "--db",
                    str(db),
                    "add",
                    "--kind",
                    "ci_failure",
                    "--title",
                    "Review failing dependency install",
                ]
            )
            self.assertEqual(add_proc.returncode, 0, add_proc.stderr)

            summary_proc = run_patchrail(
                ["queue", "--db", str(db), "audit-summary", "--format", "json"]
            )

            self.assertEqual(summary_proc.returncode, 1)
            summary = json.loads(summary_proc.stdout)
            self.assertEqual(summary["status"], "needs_more_audit_evidence")
            self.assertIn("proposal_approved", summary["missing_required_events"])
            self.assertIn("work_items_exported", summary["missing_required_events"])
            self.assertEqual(summary["gates"]["work_item_approval_gate_exercised"], False)
            self.assertEqual(summary["safety"]["github_write_permission_required"], False)
            self.assertEqual(summary["safety"]["network_required"], False)

    def test_queue_status_summarizes_local_control_plane_without_write_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "queue.sqlite"
            add_proc = run_patchrail(
                [
                    "queue",
                    "--db",
                    str(db),
                    "add",
                    "--kind",
                    "ci_failure",
                    "--title",
                    "Review failing dependency install",
                    "--payload-json",
                    '{"report": "ci-result.json"}',
                ]
            )
            self.assertEqual(add_proc.returncode, 0, add_proc.stderr)
            item = json.loads(add_proc.stdout)

            proposal_proc = run_patchrail(
                [
                    "queue",
                    "--db",
                    str(db),
                    "proposal",
                    "add",
                    "--item-id",
                    item["id"],
                    "--title",
                    "Patch dependency range",
                    "--summary",
                    "Prepare a local patch plan.",
                    "--patch-plan",
                    "1. Reproduce.\n2. Patch.\n3. Test.",
                    "--risk-level",
                    "low",
                ]
            )
            self.assertEqual(proposal_proc.returncode, 0, proposal_proc.stderr)

            status_proc = run_patchrail(["queue", "--db", str(db), "status", "--format", "json"])
            self.assertEqual(status_proc.returncode, 0, status_proc.stderr)
            status = json.loads(status_proc.stdout)

            self.assertEqual(status["schema_version"], "patchrail.queue_status.v1")
            self.assertEqual(status["counts"]["work_items_total"], 1)
            self.assertEqual(status["counts"]["work_items_by_approval_state"]["pending"], 1)
            self.assertEqual(status["counts"]["proposals_total"], 1)
            self.assertEqual(status["counts"]["proposals_by_approval_state"]["pending"], 1)
            self.assertEqual(status["counts"]["audit_events_total"], 2)
            self.assertEqual(status["latest_audit_event"]["event_type"], "proposal_added")
            self.assertEqual(status["latest_audit_event"]["work_item_id"], item["id"])
            self.assertEqual(status["human_gate_summary"]["status"], "awaiting_human_review")
            self.assertEqual(status["human_gate_summary"]["pending_work_items"], 1)
            self.assertEqual(status["human_gate_summary"]["pending_proposals"], 1)
            self.assertEqual(status["human_gate_summary"]["total_pending_decisions"], 2)
            self.assertEqual(status["human_gate_summary"]["write_actions_unlocked"], False)
            self.assertEqual(status["safety"]["write_actions_allowed_by_default"], False)
            self.assertEqual(status["safety"]["github_write_permission_required"], False)
            self.assertEqual(status["safety"]["network_required"], False)
            self.assertEqual(status["safety"]["external_model_required"], False)
            self.assertEqual(status["safety"]["billing_required"], False)
            self.assertEqual(status["safety"]["approval_records_execute_actions"], False)

            markdown_proc = run_patchrail(
                ["queue", "--db", str(db), "status", "--format", "markdown"]
            )
            self.assertEqual(markdown_proc.returncode, 0, markdown_proc.stderr)
            self.assertIn("# PatchRail Queue Status", markdown_proc.stdout)
            self.assertIn("## Human Gate Summary", markdown_proc.stdout)
            self.assertIn("Total pending decisions: `2`", markdown_proc.stdout)
            self.assertIn("Write actions allowed by default: `False`", markdown_proc.stdout)
            self.assertIn("Approval records execute actions: `False`", markdown_proc.stdout)

    def test_queue_bundle_exports_read_only_handoff_packet(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "queue.sqlite"

            approved_item_proc = run_patchrail(
                [
                    "queue",
                    "--db",
                    str(db),
                    "add",
                    "--kind",
                    "ci_failure",
                    "--title",
                    "Review dependency failure",
                ]
            )
            self.assertEqual(approved_item_proc.returncode, 0, approved_item_proc.stderr)
            approved_item = json.loads(approved_item_proc.stdout)

            rejected_item_proc = run_patchrail(
                [
                    "queue",
                    "--db",
                    str(db),
                    "add",
                    "--kind",
                    "ci_failure",
                    "--title",
                    "Reject duplicate report",
                ]
            )
            self.assertEqual(rejected_item_proc.returncode, 0, rejected_item_proc.stderr)
            rejected_item = json.loads(rejected_item_proc.stdout)

            proposal_proc = run_patchrail(
                [
                    "queue",
                    "--db",
                    str(db),
                    "proposal",
                    "add",
                    "--item-id",
                    approved_item["id"],
                    "--title",
                    "Patch dependency range",
                    "--summary",
                    "Prepare a local patch plan.",
                    "--patch-plan",
                    "1. Reproduce.\n2. Patch.\n3. Test.",
                    "--risk-level",
                    "low",
                ]
            )
            self.assertEqual(proposal_proc.returncode, 0, proposal_proc.stderr)
            proposal = json.loads(proposal_proc.stdout)

            rejected_proposal_proc = run_patchrail(
                [
                    "queue",
                    "--db",
                    str(db),
                    "proposal",
                    "add",
                    "--item-id",
                    rejected_item["id"],
                    "--title",
                    "Open an automatic pull request",
                    "--summary",
                    "This proposal skips the maintainer gate.",
                    "--patch-plan",
                    "1. Generate patch.\n2. Open PR automatically.",
                    "--risk-level",
                    "high",
                ]
            )
            self.assertEqual(rejected_proposal_proc.returncode, 0, rejected_proposal_proc.stderr)
            rejected_proposal = json.loads(rejected_proposal_proc.stdout)

            self.assertEqual(
                run_patchrail(
                    [
                        "queue",
                        "--db",
                        str(db),
                        "proposal",
                        "approve",
                        proposal["id"],
                    ]
                ).returncode,
                0,
            )
            self.assertEqual(
                run_patchrail(
                    [
                        "queue",
                        "--db",
                        str(db),
                        "proposal",
                        "reject",
                        rejected_proposal["id"],
                    ]
                ).returncode,
                0,
            )
            self.assertEqual(
                run_patchrail(
                    ["queue", "--db", str(db), "approve", approved_item["id"]]
                ).returncode,
                0,
            )
            self.assertEqual(
                run_patchrail(["queue", "--db", str(db), "reject", rejected_item["id"]]).returncode,
                0,
            )
            self.assertEqual(
                run_patchrail(["queue", "--db", str(db), "export", "--format", "jsonl"]).returncode,
                0,
            )

            audit_before_proc = run_patchrail(
                ["queue", "--db", str(db), "audit", "--format", "json"]
            )
            self.assertEqual(audit_before_proc.returncode, 0, audit_before_proc.stderr)
            audit_before = json.loads(audit_before_proc.stdout)

            bundle_proc = run_patchrail(["queue", "--db", str(db), "bundle", "--format", "json"])
            self.assertEqual(bundle_proc.returncode, 0, bundle_proc.stderr)
            bundle = json.loads(bundle_proc.stdout)

            self.assertEqual(bundle["schema_version"], "patchrail.queue_bundle.v1")
            self.assertEqual(bundle["status"], "ready_for_handoff")
            self.assertEqual(bundle["counts"]["work_items_total"], 2)
            self.assertEqual(bundle["counts"]["proposals_total"], 2)
            self.assertEqual(bundle["audit_summary"]["status"], "human_gates_exercised")
            self.assertEqual(bundle["remaining_gate_gaps"], [])
            self.assertEqual(bundle["safety"]["bundle_is_read_only"], True)
            self.assertEqual(bundle["safety"]["bundle_records_audit_event"], False)
            self.assertEqual(bundle["safety"]["local_paths_redacted"], True)
            self.assertEqual(bundle["safety"]["approval_records_execute_actions"], False)
            self.assertEqual(bundle["work_items"][0]["write_actions_allowed"], False)
            self.assertEqual(
                {proposal["approval_state"] for proposal in bundle["proposals"]},
                {"approved", "rejected"},
            )
            self.assertNotIn("/Volumes/", bundle_proc.stdout)
            self.assertNotIn("/Users/", bundle_proc.stdout)
            self.assertNotIn("/home/", bundle_proc.stdout)

            audit_after_proc = run_patchrail(
                ["queue", "--db", str(db), "audit", "--format", "json"]
            )
            self.assertEqual(audit_after_proc.returncode, 0, audit_after_proc.stderr)
            audit_after = json.loads(audit_after_proc.stdout)
            self.assertEqual(
                len(audit_after["audit_events"]),
                len(audit_before["audit_events"]),
            )

            markdown_proc = run_patchrail(
                ["queue", "--db", str(db), "bundle", "--format", "markdown"]
            )
            self.assertEqual(markdown_proc.returncode, 0, markdown_proc.stderr)
            self.assertIn("# PatchRail Queue Bundle", markdown_proc.stdout)
            self.assertIn("Bundle is read-only: `True`", markdown_proc.stdout)
            self.assertIn("Bundle records audit event: `False`", markdown_proc.stdout)
            self.assertIn("Local paths redacted: `True`", markdown_proc.stdout)

    def test_queue_reject_marks_item_closed_locally(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "queue.sqlite"
            add_proc = run_patchrail(
                [
                    "queue",
                    "--db",
                    str(db),
                    "add",
                    "--kind",
                    "release_prep",
                    "--title",
                    "Prepare release checklist",
                ]
            )
            self.assertEqual(add_proc.returncode, 0, add_proc.stderr)
            item_id = json.loads(add_proc.stdout)["id"]

            reject_proc = run_patchrail(
                ["queue", "--db", str(db), "reject", item_id, "--note", "Needs more evidence."]
            )

            self.assertEqual(reject_proc.returncode, 0, reject_proc.stderr)
            rejected = json.loads(reject_proc.stdout)
            self.assertEqual(rejected["approval_state"], "rejected")
            self.assertEqual(rejected["status"], "rejected")
            self.assertIn("Needs more evidence", rejected["decision_note"])

    def test_queue_skip_preserves_retired_work_with_audit_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "queue.sqlite"
            add_proc = run_patchrail(
                [
                    "queue",
                    "--db",
                    str(db),
                    "add",
                    "--kind",
                    "retired_workflow",
                    "--title",
                    "Skip work that is outside current maintainer policy",
                ]
            )
            self.assertEqual(add_proc.returncode, 0, add_proc.stderr)
            item_id = json.loads(add_proc.stdout)["id"]

            skip_proc = run_patchrail(
                [
                    "queue",
                    "--db",
                    str(db),
                    "skip",
                    item_id,
                    "--reason",
                    "retired by current maintainer policy",
                ]
            )

            self.assertEqual(skip_proc.returncode, 0, skip_proc.stderr)
            skipped = json.loads(skip_proc.stdout)
            self.assertEqual(skipped["approval_state"], "rejected")
            self.assertEqual(skipped["status"], "skipped")
            self.assertEqual(skipped["write_actions_allowed"], False)
            self.assertEqual(skipped["decision_note"], "retired by current maintainer policy")

            list_proc = run_patchrail(
                ["queue", "--db", str(db), "list", "--status", "skipped", "--format", "json"]
            )
            self.assertEqual(list_proc.returncode, 0, list_proc.stderr)
            listed = json.loads(list_proc.stdout)["work_items"]
            self.assertEqual([item["id"] for item in listed], [item_id])

            status_proc = run_patchrail(["queue", "--db", str(db), "status", "--format", "json"])
            self.assertEqual(status_proc.returncode, 0, status_proc.stderr)
            status = json.loads(status_proc.stdout)
            self.assertEqual(status["counts"]["work_items_by_status"]["skipped"], 1)
            self.assertEqual(status["counts"]["work_items_by_approval_state"]["rejected"], 1)
            self.assertEqual(status["safety"]["approval_records_execute_actions"], False)

            audit_proc = run_patchrail(
                ["queue", "--db", str(db), "audit", "--item-id", item_id, "--format", "json"]
            )
            self.assertEqual(audit_proc.returncode, 0, audit_proc.stderr)
            audit_events = json.loads(audit_proc.stdout)["audit_events"]
            self.assertEqual(
                [event["event_type"] for event in audit_events],
                ["work_item_added", "work_item_skipped"],
            )
            self.assertEqual(
                audit_events[1]["payload"]["decision_note"],
                "retired by current maintainer policy",
            )

            summary_proc = run_patchrail(
                [
                    "queue",
                    "--db",
                    str(db),
                    "audit-summary",
                    "--format",
                    "json",
                    "--require-event",
                    "work_item_skipped",
                ]
            )
            self.assertEqual(summary_proc.returncode, 0, summary_proc.stderr)
            summary = json.loads(summary_proc.stdout)
            self.assertEqual(summary["status"], "human_gates_exercised")
            self.assertEqual(summary["gates"]["work_item_skip_gate_exercised"], True)

    def test_queue_add_from_ci_result_keeps_import_local_and_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "queue.sqlite"
            ci_result = Path(tmpdir) / "ci-result.json"
            classify_proc = run_patchrail(
                [
                    "ci",
                    "classify",
                    "--log",
                    "examples/ci-triage/dependency-failure.log",
                    "--format",
                    "json",
                    "--out",
                    str(ci_result),
                ]
            )
            self.assertEqual(classify_proc.returncode, 0, classify_proc.stderr)

            add_proc = run_patchrail(
                [
                    "queue",
                    "--db",
                    str(db),
                    "add",
                    "--from-ci-result",
                    str(ci_result),
                ]
            )

            self.assertEqual(add_proc.returncode, 0, add_proc.stderr)
            added = json.loads(add_proc.stdout)
            self.assertEqual(added["kind"], "ci_failure")
            self.assertEqual(added["title"], "Review python_dependency_resolution CI failure")
            self.assertEqual(added["source"], str(ci_result))
            self.assertEqual(added["approval_state"], "pending")
            self.assertEqual(added["write_actions_allowed"], False)
            self.assertEqual(added["payload"]["failure_class"], "python_dependency_resolution")
            self.assertEqual(
                added["payload"]["ci_result"]["schema_version"],
                "patchrail.ci_result.v1",
            )
            self.assertEqual(
                added["payload"]["ci_result"]["requirements"]["external_model_required"],
                False,
            )

    def test_queue_add_from_pilot_pack_keeps_pack_local_and_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "queue.sqlite"
            pack_dir = Path(tmpdir) / "pilot-pack"
            pack_proc = run_patchrail(
                [
                    "ci",
                    "pilot-pack",
                    "--log",
                    "examples/ci-triage/dependency-failure.log",
                    "--out-dir",
                    str(pack_dir),
                ]
            )
            self.assertEqual(pack_proc.returncode, 0, pack_proc.stderr)

            add_proc = run_patchrail(
                [
                    "queue",
                    "--db",
                    str(db),
                    "add",
                    "--from-pilot-pack",
                    str(pack_dir),
                ]
            )

            self.assertEqual(add_proc.returncode, 0, add_proc.stderr)
            added = json.loads(add_proc.stdout)
            self.assertEqual(added["kind"], "ci_failure")
            self.assertEqual(added["title"], "Review python_dependency_resolution CI pilot pack")
            self.assertEqual(added["source"], str(pack_dir / "pilot-manifest.json"))
            self.assertEqual(added["approval_state"], "pending")
            self.assertEqual(added["write_actions_allowed"], False)
            self.assertEqual(added["payload"]["failure_class"], "python_dependency_resolution")
            self.assertEqual(
                added["payload"]["ci_result"]["schema_version"],
                "patchrail.ci_result.v1",
            )
            self.assertEqual(
                added["payload"]["pilot_pack"]["manifest"]["schema_version"],
                "patchrail.ci_pilot_pack.v1",
            )
            self.assertEqual(added["payload"]["pilot_pack"]["raw_log_copied"], False)
            self.assertEqual(
                added["payload"]["pilot_pack"]["maintainer_review_required_before_sharing"],
                True,
            )
            self.assertEqual(
                added["payload"]["pilot_pack"]["files"]["redacted_log"],
                "failed-ci.redacted.log",
            )
            self.assertEqual(
                added["payload"]["pilot_pack"]["files"]["markdown_report"],
                "patchrail-report.md",
            )
            self.assertEqual(
                added["payload"]["pilot_pack"]["manifest"]["requirements"][
                    "github_write_permission_required"
                ],
                False,
            )

    def test_queue_add_from_pilot_pack_manifest_path_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "queue.sqlite"
            pack_dir = Path(tmpdir) / "pilot-pack"
            pack_proc = run_patchrail(
                [
                    "ci",
                    "pilot-pack",
                    "--log",
                    "examples/ci-triage/dependency-failure.log",
                    "--out-dir",
                    str(pack_dir),
                ]
            )
            self.assertEqual(pack_proc.returncode, 0, pack_proc.stderr)

            add_proc = run_patchrail(
                [
                    "queue",
                    "--db",
                    str(db),
                    "add",
                    "--from-pilot-pack",
                    str(pack_dir / "pilot-manifest.json"),
                ]
            )

            self.assertEqual(add_proc.returncode, 0, add_proc.stderr)
            added = json.loads(add_proc.stdout)
            self.assertEqual(added["source"], str(pack_dir / "pilot-manifest.json"))
            self.assertEqual(
                added["payload"]["report_source"], str(pack_dir / "patchrail-result.json")
            )

    def test_queue_add_from_pilot_pack_rejects_raw_log_copy_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_dir = Path(tmpdir) / "pilot-pack"
            pack_proc = run_patchrail(
                [
                    "ci",
                    "pilot-pack",
                    "--log",
                    "examples/ci-triage/dependency-failure.log",
                    "--out-dir",
                    str(pack_dir),
                ]
            )
            self.assertEqual(pack_proc.returncode, 0, pack_proc.stderr)
            manifest_path = pack_dir / "pilot-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["source"]["raw_log_copied"] = True
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            add_proc = run_patchrail(["queue", "add", "--from-pilot-pack", str(pack_dir)])

            self.assertEqual(add_proc.returncode, 1)
            self.assertIn("must not copy the raw CI log", add_proc.stderr)

    def test_queue_add_rejects_multiple_import_sources(self) -> None:
        proc = run_patchrail(
            [
                "queue",
                "add",
                "--from-ci-result",
                "patchrail-result.json",
                "--from-pilot-pack",
                "pilot-pack",
            ]
        )

        self.assertEqual(proc.returncode, 1)
        self.assertIn("only one import source", proc.stderr)

    def test_queue_proposal_flow_records_reviewable_patch_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "queue.sqlite"
            add_proc = run_patchrail(
                [
                    "queue",
                    "--db",
                    str(db),
                    "add",
                    "--kind",
                    "ci_failure",
                    "--title",
                    "Review dependency failure",
                    "--payload-json",
                    '{"report": "ci-result.json"}',
                ]
            )
            self.assertEqual(add_proc.returncode, 0, add_proc.stderr)
            item = json.loads(add_proc.stdout)

            proposal_proc = run_patchrail(
                [
                    "queue",
                    "--db",
                    str(db),
                    "proposal",
                    "add",
                    "--item-id",
                    item["id"],
                    "--title",
                    "Pin compatible dependency range",
                    "--summary",
                    "Adjust the dependency range and re-run the failing CI matrix.",
                    "--patch-plan",
                    "1. Reproduce install failure.\n2. Update dependency bounds.\n3. Run tests.",
                    "--risk-level",
                    "low",
                ]
            )
            self.assertEqual(proposal_proc.returncode, 0, proposal_proc.stderr)
            proposal = json.loads(proposal_proc.stdout)
            self.assertEqual(proposal["work_item_id"], item["id"])
            self.assertEqual(proposal["approval_state"], "pending")
            self.assertEqual(proposal["risk_level"], "low")

            list_proc = run_patchrail(
                [
                    "queue",
                    "--db",
                    str(db),
                    "proposal",
                    "list",
                    "--item-id",
                    item["id"],
                    "--format",
                    "json",
                ]
            )
            self.assertEqual(list_proc.returncode, 0, list_proc.stderr)
            listed = json.loads(list_proc.stdout)
            self.assertEqual([entry["id"] for entry in listed["proposals"]], [proposal["id"]])

            show_proc = run_patchrail(
                [
                    "queue",
                    "--db",
                    str(db),
                    "proposal",
                    "show",
                    proposal["id"],
                    "--format",
                    "markdown",
                ]
            )
            self.assertEqual(show_proc.returncode, 0, show_proc.stderr)
            self.assertIn("## Patch Plan", show_proc.stdout)
            self.assertIn("does not push commits", show_proc.stdout)

            approve_proposal_proc = run_patchrail(
                [
                    "queue",
                    "--db",
                    str(db),
                    "proposal",
                    "approve",
                    proposal["id"],
                    "--note",
                    "Maintainer approved the local plan only.",
                ]
            )
            self.assertEqual(approve_proposal_proc.returncode, 0, approve_proposal_proc.stderr)
            approved_proposal = json.loads(approve_proposal_proc.stdout)
            self.assertEqual(approved_proposal["approval_state"], "approved")
            self.assertIn("local plan", approved_proposal["decision_note"])

            approve_item_proc = run_patchrail(
                [
                    "queue",
                    "--db",
                    str(db),
                    "approve",
                    item["id"],
                    "--note",
                    "Maintainer approved handoff after reviewing proposal.",
                ]
            )
            self.assertEqual(approve_item_proc.returncode, 0, approve_item_proc.stderr)
            approved_item = json.loads(approve_item_proc.stdout)
            self.assertEqual(approved_item["approval_state"], "approved")
            self.assertEqual(approved_item["write_actions_allowed"], False)

            audit_proc = run_patchrail(
                [
                    "queue",
                    "--db",
                    str(db),
                    "audit",
                    "--item-id",
                    item["id"],
                    "--format",
                    "json",
                ]
            )
            self.assertEqual(audit_proc.returncode, 0, audit_proc.stderr)
            audit = json.loads(audit_proc.stdout)
            self.assertEqual(
                [event["event_type"] for event in audit["audit_events"]],
                [
                    "work_item_added",
                    "proposal_added",
                    "proposal_approved",
                    "work_item_approved",
                ],
            )
            self.assertEqual(
                audit["audit_events"][1]["payload"]["proposal_id"],
                proposal["id"],
            )

    def test_queue_proposal_add_requires_existing_work_item(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "queue.sqlite"
            proc = run_patchrail(
                [
                    "queue",
                    "--db",
                    str(db),
                    "proposal",
                    "add",
                    "--item-id",
                    "prq_missing",
                    "--title",
                    "Missing item proposal",
                    "--summary",
                    "Cannot link to a missing item.",
                    "--patch-plan",
                    "Do nothing.",
                ]
            )

            self.assertEqual(proc.returncode, 1)
            self.assertIn("Unknown work item: prq_missing", proc.stderr)

    def test_queue_add_requires_manual_kind_and_title_without_import(self) -> None:
        proc = run_patchrail(["queue", "add", "--payload-json", "{}"])

        self.assertEqual(proc.returncode, 1)
        self.assertIn("requires --kind and --title", proc.stderr)

    def test_queue_show_unknown_item_fails_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "queue.sqlite"
            proc = run_patchrail(["queue", "--db", str(db), "show", "prq_missing"])

            self.assertEqual(proc.returncode, 1)
            self.assertIn("Unknown work item", proc.stderr)


if __name__ == "__main__":
    unittest.main()
