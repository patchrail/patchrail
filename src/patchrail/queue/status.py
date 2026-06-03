from __future__ import annotations

from collections import Counter
from pathlib import Path
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


def queue_status_payload(
    db_path: Path = DEFAULT_QUEUE_PATH,
    *,
    include_api_compat: bool = False,
) -> dict[str, Any]:
    init_result = init_queue(db_path)
    work_items = [item.to_dict() for item in list_work_items(db_path=db_path)]
    proposals = [proposal.to_dict() for proposal in list_proposals(db_path=db_path)]
    audit_events = export_audit_events(db_path=db_path)["audit_events"]
    work_item_approval_counts = Counter(item["approval_state"] for item in work_items)
    work_item_status_counts = Counter(item["status"] for item in work_items)
    proposal_approval_counts = Counter(proposal["approval_state"] for proposal in proposals)
    latest_audit_event = audit_events[-1] if audit_events else None
    payload: dict[str, Any] = {
        "schema_version": QUEUE_STATUS_SCHEMA_VERSION,
        "queue_schema_version": init_result["schema_version"],
        "patchrail_version": __version__,
        "db_path": str(db_path),
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
