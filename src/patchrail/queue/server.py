from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from patchrail.queue.status import SAFE_QUEUE_REQUIREMENTS, queue_status_payload
from patchrail.queue.store import (
    DEFAULT_QUEUE_PATH,
    SCHEMA_VERSION,
    add_proposal,
    add_work_item,
    approve_proposal,
    approve_work_item,
    export_audit_events,
    init_queue,
    list_proposals,
    list_work_items,
    reject_proposal,
    reject_work_item,
    show_proposal,
    show_work_item,
)


def _json_response(payload: dict[str, Any], status: int = 200) -> tuple[int, dict[str, Any]]:
    return status, payload


def _not_found(message: str) -> tuple[int, dict[str, Any]]:
    return _json_response({"error": message}, 404)


def _bad_request(message: str) -> tuple[int, dict[str, Any]]:
    return _json_response({"error": message}, 400)


def _approval_note(payload: dict[str, Any]) -> str | None:
    note = payload.get("note")
    return str(note) if note is not None else None


def _decode_json_body(body: bytes) -> dict[str, Any]:
    if not body:
        return {}
    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("request body must be a JSON object")
    return payload


def handle_queue_api_request(
    *,
    method: str,
    raw_path: str,
    body: bytes = b"",
    db_path: Path = DEFAULT_QUEUE_PATH,
) -> tuple[int, dict[str, Any]]:
    parsed = urlparse(raw_path)
    path_parts = [part for part in parsed.path.strip("/").split("/") if part]
    query = parse_qs(parsed.query)

    try:
        payload = _decode_json_body(body)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return _bad_request(f"invalid JSON body: {exc}")

    if method == "GET" and path_parts == ["health"]:
        return _json_response(
            {
                "status": "ok",
                "schema_version": "patchrail.queue_api.v1",
                "local_first": True,
                "requirements": SAFE_QUEUE_REQUIREMENTS,
            }
        )

    if method == "GET" and path_parts == ["status"]:
        return _json_response(queue_status_payload(db_path, include_api_compat=True))

    if method == "GET" and path_parts == ["work-items"]:
        try:
            items = [
                item.to_dict()
                for item in list_work_items(
                    db_path=db_path,
                    status=(query.get("status") or [None])[0],
                    approval_state=(query.get("approval_state") or [None])[0],
                )
            ]
        except ValueError as exc:
            return _bad_request(str(exc))
        return _json_response(
            {
                "schema_version": SCHEMA_VERSION,
                "local_first": True,
                "work_items": items,
            }
        )

    if method == "POST" and path_parts == ["work-items"]:
        kind = str(payload.get("kind") or "")
        title = str(payload.get("title") or "")
        if not kind or not title:
            return _bad_request("work item requires kind and title")
        item = add_work_item(
            db_path=db_path,
            kind=kind,
            title=title,
            source=str(payload.get("source") or "api"),
            payload=dict(payload.get("payload") or {}),
        )
        return _json_response(item.to_dict(), 201)

    if len(path_parts) == 2 and path_parts[0] == "work-items":
        item_id = path_parts[1]
        if method == "GET":
            try:
                return _json_response(show_work_item(db_path=db_path, item_id=item_id).to_dict())
            except KeyError:
                return _not_found(f"unknown work item: {item_id}")

    if len(path_parts) == 3 and path_parts[0] == "work-items":
        item_id = path_parts[1]
        action = path_parts[2]
        if method == "POST" and action == "approve":
            try:
                item = approve_work_item(
                    db_path=db_path,
                    item_id=item_id,
                    decision_note=_approval_note(payload),
                )
                return _json_response(item.to_dict())
            except KeyError:
                return _not_found(f"unknown work item: {item_id}")
        if method == "POST" and action == "reject":
            try:
                item = reject_work_item(
                    db_path=db_path,
                    item_id=item_id,
                    decision_note=_approval_note(payload),
                )
                return _json_response(item.to_dict())
            except KeyError:
                return _not_found(f"unknown work item: {item_id}")

    if method == "GET" and path_parts == ["proposals"]:
        try:
            proposals = [
                proposal.to_dict()
                for proposal in list_proposals(
                    db_path=db_path,
                    work_item_id=(query.get("work_item_id") or [None])[0],
                    approval_state=(query.get("approval_state") or [None])[0],
                )
            ]
        except ValueError as exc:
            return _bad_request(str(exc))
        return _json_response(
            {
                "schema_version": SCHEMA_VERSION,
                "local_first": True,
                "proposals": proposals,
            }
        )

    if method == "POST" and path_parts == ["proposals"]:
        work_item_id = str(payload.get("work_item_id") or "")
        title = str(payload.get("title") or "")
        summary = str(payload.get("summary") or "")
        patch_plan = str(payload.get("patch_plan") or "")
        if not work_item_id or not title or not summary or not patch_plan:
            return _bad_request("proposal requires work_item_id, title, summary and patch_plan")
        try:
            proposal = add_proposal(
                db_path=db_path,
                work_item_id=work_item_id,
                title=title,
                summary=summary,
                patch_plan=patch_plan,
                risk_level=str(payload.get("risk_level") or "medium"),
            )
            return _json_response(proposal.to_dict(), 201)
        except KeyError:
            return _not_found(f"unknown work item: {work_item_id}")

    if len(path_parts) == 2 and path_parts[0] == "proposals":
        proposal_id = path_parts[1]
        if method == "GET":
            try:
                return _json_response(
                    show_proposal(db_path=db_path, proposal_id=proposal_id).to_dict()
                )
            except KeyError:
                return _not_found(f"unknown proposal: {proposal_id}")

    if len(path_parts) == 3 and path_parts[0] == "proposals":
        proposal_id = path_parts[1]
        action = path_parts[2]
        if method == "POST" and action == "approve":
            try:
                proposal = approve_proposal(
                    db_path=db_path,
                    proposal_id=proposal_id,
                    decision_note=_approval_note(payload),
                )
                return _json_response(proposal.to_dict())
            except KeyError:
                return _not_found(f"unknown proposal: {proposal_id}")
        if method == "POST" and action == "reject":
            try:
                proposal = reject_proposal(
                    db_path=db_path,
                    proposal_id=proposal_id,
                    decision_note=_approval_note(payload),
                )
                return _json_response(proposal.to_dict())
            except KeyError:
                return _not_found(f"unknown proposal: {proposal_id}")

    if method == "GET" and path_parts == ["audit-events"]:
        events = export_audit_events(
            db_path=db_path,
            work_item_id=(query.get("work_item_id") or [None])[0],
        )
        return _json_response(events)

    return _not_found(f"unknown route: {method} {parsed.path}")


def make_queue_api_handler(db_path: Path) -> type[BaseHTTPRequestHandler]:
    class QueueAPIHandler(BaseHTTPRequestHandler):
        server_version = "PatchRailQueueAPI/0.1"

        def do_GET(self) -> None:  # noqa: N802
            self._handle()

        def do_POST(self) -> None:  # noqa: N802
            self._handle()

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _handle(self) -> None:
            length = int(self.headers.get("Content-Length", "0") or "0")
            body = self.rfile.read(length) if length else b""
            status, payload = handle_queue_api_request(
                method=self.command,
                raw_path=self.path,
                body=body,
                db_path=db_path,
            )
            encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return QueueAPIHandler


def serve_queue_api(*, host: str = "127.0.0.1", port: int = 8765, db_path: Path) -> None:
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("PatchRail queue API is local-only; use host 127.0.0.1 or localhost")
    init_queue(db_path)
    server = ThreadingHTTPServer((host, port), make_queue_api_handler(db_path))
    try:
        server.serve_forever()
    finally:
        server.server_close()
