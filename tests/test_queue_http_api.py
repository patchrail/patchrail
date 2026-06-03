from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from patchrail.queue.server import make_queue_api_handler, serve_queue_api


def _json_request(url: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


class PatchRailQueueHTTPAPITests(unittest.TestCase):
    def test_local_http_api_exposes_queue_proposals_approvals_and_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "queue.sqlite"
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_queue_api_handler(db))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"

            try:
                health = _json_request(f"{base_url}/health")
                self.assertEqual(health["status"], "ok")
                self.assertEqual(health["local_first"], True)
                self.assertEqual(health["requirements"]["network_required"], False)
                self.assertEqual(
                    health["requirements"]["github_write_permission_required"],
                    False,
                )

                item = _json_request(
                    f"{base_url}/work-items",
                    {
                        "kind": "ci_failure",
                        "title": "Review failing dependency install",
                        "source": "local-api-test",
                        "payload": {"report": "ci-result.json"},
                    },
                )
                self.assertEqual(item["approval_state"], "pending")
                self.assertEqual(item["write_actions_allowed"], False)

                proposal = _json_request(
                    f"{base_url}/proposals",
                    {
                        "work_item_id": item["id"],
                        "title": "Relax dependency upper bound",
                        "summary": "Small local patch proposal for maintainer review.",
                        "patch_plan": "Reproduce, patch dependency bound, rerun fixture tests.",
                        "risk_level": "low",
                    },
                )
                self.assertEqual(proposal["work_item_id"], item["id"])
                self.assertEqual(proposal["approval_state"], "pending")

                approved_proposal = _json_request(
                    f"{base_url}/proposals/{proposal['id']}/approve",
                    {"note": "Maintainer approved local proposal only."},
                )
                self.assertEqual(approved_proposal["approval_state"], "approved")

                approved_item = _json_request(
                    f"{base_url}/work-items/{item['id']}/approve",
                    {"note": "Maintainer approved queue handoff."},
                )
                self.assertEqual(approved_item["approval_state"], "approved")
                self.assertEqual(approved_item["write_actions_allowed"], False)

                status = _json_request(f"{base_url}/status")
                self.assertEqual(status["schema_version"], "patchrail.queue_status.v1")
                self.assertEqual(status["counts"]["work_items_total"], 1)
                self.assertEqual(status["counts"]["work_items_by_approval_state"]["approved"], 1)
                self.assertEqual(status["counts"]["proposals_total"], 1)
                self.assertEqual(status["counts"]["proposals_by_approval_state"]["approved"], 1)
                self.assertEqual(status["counts"]["audit_events_total"], 4)
                self.assertEqual(status["latest_audit_event"]["event_type"], "work_item_approved")
                self.assertEqual(status["human_gate_summary"]["status"], "no_pending_decisions")
                self.assertEqual(status["human_gate_summary"]["total_pending_decisions"], 0)
                self.assertEqual(status["human_gate_summary"]["approved_work_items"], 1)
                self.assertEqual(status["human_gate_summary"]["approved_proposals"], 1)
                self.assertEqual(status["human_gate_summary"]["write_actions_unlocked"], False)
                self.assertEqual(status["safety"]["network_required"], False)
                self.assertEqual(status["safety"]["external_model_required"], False)
                self.assertEqual(status["safety"]["approval_records_execute_actions"], False)
                self.assertEqual(status["queue"]["work_items"], 1)
                self.assertEqual(status["queue"]["proposals"], 1)
                self.assertEqual(status["requirements"]["external_model_required"], False)

                audit = _json_request(f"{base_url}/audit-events?work_item_id={item['id']}")
                self.assertEqual(
                    [event["event_type"] for event in audit["audit_events"]],
                    [
                        "work_item_added",
                        "proposal_added",
                        "proposal_approved",
                        "work_item_approved",
                    ],
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_local_http_api_rejects_bad_payload_and_unknown_routes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "queue.sqlite"
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_queue_api_handler(db))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"

            try:
                with self.assertRaises(HTTPError) as missing_fields:
                    _json_request(f"{base_url}/work-items", {"kind": "ci_failure"})
                self.assertEqual(missing_fields.exception.code, 400)

                with self.assertRaises(HTTPError) as missing_route:
                    _json_request(f"{base_url}/third-party-write")
                self.assertEqual(missing_route.exception.code, 404)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_serve_queue_api_rejects_non_local_bind_host(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ValueError):
                serve_queue_api(host="0.0.0.0", port=0, db_path=Path(tmpdir) / "queue.sqlite")


if __name__ == "__main__":
    unittest.main()
