from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
from typing import Any

from patchrail import __version__
from patchrail.queue.store import (
    DEFAULT_QUEUE_PATH,
    export_audit_events,
    init_queue,
    list_proposals,
    list_work_items,
)

QUEUE_STATUS_SCHEMA_VERSION = "patchrail.queue_status.v1"
QUEUE_AUDIT_SUMMARY_SCHEMA_VERSION = "patchrail.queue_audit_summary.v1"
QUEUE_BUNDLE_SCHEMA_VERSION = "patchrail.queue_bundle.v1"

DEFAULT_REQUIRED_AUDIT_EVENTS = [
    "work_item_added",
    "proposal_added",
    "proposal_approved",
    "proposal_rejected",
    "work_item_approved",
    "work_item_rejected",
    "work_items_exported",
]

SAFE_QUEUE_REQUIREMENTS = {
    "billing_required": False,
    "external_model_required": False,
    "network_required": False,
    "github_write_permission_required": False,
    "write_actions_allowed_by_default": False,
}

SAFE_QUEUE_STATUS = {
    **SAFE_QUEUE_REQUIREMENTS,
    "approval_records_execute_actions": False,
}

LOCAL_PATH_PATTERN = re.compile(r"(/Volumes|/Users|/home)/[^\s\"'`]+")


def _redact_local_paths(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _redact_local_paths(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_local_paths(item) for item in value]
    if isinstance(value, str):
        return LOCAL_PATH_PATTERN.sub(
            lambda match: f"<local-path>/{Path(match.group(0)).name}",
            value,
        )
    return value


def queue_status_payload(
    db_path: Path = DEFAULT_QUEUE_PATH,
    *,
    include_api_compat: bool = False,
) -> dict[str, Any]:
    init_result = init_queue(db_path)
    work_items = _redact_local_paths([item.to_dict() for item in list_work_items(db_path=db_path)])
    proposals = _redact_local_paths(
        [proposal.to_dict() for proposal in list_proposals(db_path=db_path)]
    )
    audit_events = _redact_local_paths(export_audit_events(db_path=db_path)["audit_events"])
    work_item_approval_counts = Counter(item["approval_state"] for item in work_items)
    work_item_status_counts = Counter(item["status"] for item in work_items)
    proposal_approval_counts = Counter(proposal["approval_state"] for proposal in proposals)
    latest_audit_event = audit_events[-1] if audit_events else None
    payload: dict[str, Any] = {
        "schema_version": QUEUE_STATUS_SCHEMA_VERSION,
        "queue_schema_version": init_result["schema_version"],
        "patchrail_version": __version__,
        "db_path": _redact_local_paths(str(db_path)),
        "local_first": True,
        "host_boundary": "127.0.0.1 only by default",
        "counts": {
            "work_items_total": len(work_items),
            "work_items_by_status": dict(sorted(work_item_status_counts.items())),
            "work_items_by_approval_state": dict(sorted(work_item_approval_counts.items())),
            "proposals_total": len(proposals),
            "proposals_by_approval_state": dict(sorted(proposal_approval_counts.items())),
            "audit_events_total": len(audit_events),
        },
        "latest_audit_event": latest_audit_event,
        "safety": SAFE_QUEUE_STATUS,
    }
    if include_api_compat:
        payload["requirements"] = SAFE_QUEUE_REQUIREMENTS
        payload["queue"] = {
            "schema_version": init_result["schema_version"],
            "work_items": len(work_items),
            "pending_work_items": work_item_approval_counts.get("pending", 0),
            "proposals": len(proposals),
            "pending_proposals": proposal_approval_counts.get("pending", 0),
        }
    return payload


def queue_audit_summary_payload(
    db_path: Path = DEFAULT_QUEUE_PATH,
    *,
    required_events: list[str] | None = None,
) -> dict[str, Any]:
    init_result = init_queue(db_path)
    audit_events = export_audit_events(db_path=db_path)["audit_events"]
    work_items = [item.to_dict() for item in list_work_items(db_path=db_path)]
    proposals = [proposal.to_dict() for proposal in list_proposals(db_path=db_path)]
    event_counts = Counter(event["event_type"] for event in audit_events)
    required = required_events or DEFAULT_REQUIRED_AUDIT_EVENTS
    missing_required_events = [event for event in required if event_counts.get(event, 0) == 0]
    affected_work_items = sorted(
        {
            str(event["work_item_id"])
            for event in audit_events
            if event.get("work_item_id") is not None
        }
    )
    gates = {
        "work_item_approval_gate_exercised": event_counts.get("work_item_approved", 0) > 0,
        "work_item_rejection_gate_exercised": event_counts.get("work_item_rejected", 0) > 0,
        "proposal_approval_gate_exercised": event_counts.get("proposal_approved", 0) > 0,
        "proposal_rejection_gate_exercised": event_counts.get("proposal_rejected", 0) > 0,
        "queue_export_recorded": event_counts.get("work_items_exported", 0) > 0,
    }
    return {
        "schema_version": QUEUE_AUDIT_SUMMARY_SCHEMA_VERSION,
        "queue_schema_version": init_result["schema_version"],
        "patchrail_version": __version__,
        "db_path": _redact_local_paths(str(db_path)),
        "local_first": True,
        "status": "human_gates_exercised"
        if not missing_required_events
        else "needs_more_audit_evidence",
        "counts": {
            "audit_events_total": len(audit_events),
            "event_types": dict(sorted(event_counts.items())),
            "work_items_total": len(work_items),
            "proposals_total": len(proposals),
            "affected_work_items": len(affected_work_items),
        },
        "required_events": required,
        "missing_required_events": missing_required_events,
        "gates": gates,
        "affected_work_item_ids": affected_work_items,
        "latest_audit_event": audit_events[-1] if audit_events else None,
        "safety": SAFE_QUEUE_STATUS,
    }


def queue_bundle_payload(
    db_path: Path = DEFAULT_QUEUE_PATH,
    *,
    required_events: list[str] | None = None,
) -> dict[str, Any]:
    status = _redact_local_paths(queue_status_payload(db_path))
    audit_summary = _redact_local_paths(
        queue_audit_summary_payload(db_path, required_events=required_events)
    )
    work_items = _redact_local_paths([item.to_dict() for item in list_work_items(db_path=db_path)])
    proposals = _redact_local_paths(
        [proposal.to_dict() for proposal in list_proposals(db_path=db_path)]
    )
    audit_events = _redact_local_paths(export_audit_events(db_path=db_path)["audit_events"])
    ready = audit_summary["status"] == "human_gates_exercised"
    return {
        "schema_version": QUEUE_BUNDLE_SCHEMA_VERSION,
        "queue_schema_version": status["queue_schema_version"],
        "patchrail_version": __version__,
        "db_path": _redact_local_paths(str(db_path)),
        "local_first": True,
        "status": "ready_for_handoff" if ready else "needs_more_gate_evidence",
        "counts": {
            "work_items_total": len(work_items),
            "proposals_total": len(proposals),
            "audit_events_total": len(audit_events),
        },
        "status_summary": status,
        "audit_summary": audit_summary,
        "work_items": work_items,
        "proposals": proposals,
        "audit_events": audit_events,
        "safety": {
            **SAFE_QUEUE_STATUS,
            "bundle_is_read_only": True,
            "bundle_records_audit_event": False,
            "local_paths_redacted": True,
        },
        "remaining_gate_gaps": audit_summary["missing_required_events"],
    }
