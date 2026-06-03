from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

SCHEMA_VERSION = "patchrail.queue.v1"
DEFAULT_QUEUE_PATH = Path(".patchrail") / "queue.sqlite"

VALID_APPROVAL_STATES = {"pending", "approved", "rejected"}


@dataclass(frozen=True)
class QueueItem:
    id: str
    kind: str
    title: str
    source: str
    status: str
    approval_state: str
    write_actions_allowed: bool
    created_at: str
    updated_at: str
    payload: dict[str, Any]
    decision_note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "source": self.source,
            "status": self.status,
            "approval_state": self.approval_state,
            "write_actions_allowed": self.write_actions_allowed,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "payload": self.payload,
            "decision_note": self.decision_note,
        }


@dataclass(frozen=True)
class AuditEvent:
    id: int
    ts: str
    event_type: str
    work_item_id: str | None
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ts": self.ts,
            "event_type": self.event_type,
            "work_item_id": self.work_item_id,
            "payload": self.payload,
        }


@dataclass(frozen=True)
class ProposalRecord:
    id: str
    work_item_id: str
    title: str
    summary: str
    patch_plan: str
    risk_level: str
    approval_state: str
    created_at: str
    updated_at: str
    decision_note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "work_item_id": self.work_item_id,
            "title": self.title,
            "summary": self.summary,
            "patch_plan": self.patch_plan,
            "risk_level": self.risk_level,
            "approval_state": self.approval_state,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "decision_note": self.decision_note,
        }


def _now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_queue(db_path: Path = DEFAULT_QUEUE_PATH) -> dict[str, Any]:
    with _connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS metadata (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS work_items (
              id TEXT PRIMARY KEY,
              kind TEXT NOT NULL,
              title TEXT NOT NULL,
              source TEXT NOT NULL,
              status TEXT NOT NULL,
              approval_state TEXT NOT NULL,
              write_actions_allowed INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              decision_note TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ts TEXT NOT NULL,
              event_type TEXT NOT NULL,
              work_item_id TEXT,
              payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS proposals (
              id TEXT PRIMARY KEY,
              work_item_id TEXT NOT NULL,
              title TEXT NOT NULL,
              summary TEXT NOT NULL,
              patch_plan TEXT NOT NULL,
              risk_level TEXT NOT NULL,
              approval_state TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              decision_note TEXT,
              FOREIGN KEY(work_item_id) REFERENCES work_items(id)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO metadata(key, value)
            VALUES('schema_version', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (SCHEMA_VERSION,),
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "db_path": str(db_path),
        "local_first": True,
        "write_actions_allowed_by_default": False,
    }


def _row_to_item(row: sqlite3.Row) -> QueueItem:
    return QueueItem(
        id=str(row["id"]),
        kind=str(row["kind"]),
        title=str(row["title"]),
        source=str(row["source"]),
        status=str(row["status"]),
        approval_state=str(row["approval_state"]),
        write_actions_allowed=bool(row["write_actions_allowed"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        payload=json.loads(str(row["payload_json"])),
        decision_note=row["decision_note"],
    )


def _row_to_audit_event(row: sqlite3.Row) -> AuditEvent:
    return AuditEvent(
        id=int(row["id"]),
        ts=str(row["ts"]),
        event_type=str(row["event_type"]),
        work_item_id=row["work_item_id"],
        payload=json.loads(str(row["payload_json"])),
    )


def _row_to_proposal(row: sqlite3.Row) -> ProposalRecord:
    return ProposalRecord(
        id=str(row["id"]),
        work_item_id=str(row["work_item_id"]),
        title=str(row["title"]),
        summary=str(row["summary"]),
        patch_plan=str(row["patch_plan"]),
        risk_level=str(row["risk_level"]),
        approval_state=str(row["approval_state"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        decision_note=row["decision_note"],
    )


def _write_audit_event(
    conn: sqlite3.Connection,
    *,
    event_type: str,
    work_item_id: str | None,
    payload: dict[str, Any],
) -> None:
    conn.execute(
        """
        INSERT INTO audit_events(ts, event_type, work_item_id, payload_json)
        VALUES(?, ?, ?, ?)
        """,
        (_now(), event_type, work_item_id, json.dumps(payload, sort_keys=True)),
    )


def add_work_item(
    *,
    db_path: Path = DEFAULT_QUEUE_PATH,
    kind: str,
    title: str,
    source: str = "manual",
    payload: dict[str, Any] | None = None,
) -> QueueItem:
    init_queue(db_path)
    item_id = f"prq_{uuid4().hex[:12]}"
    ts = _now()
    safe_payload = payload or {}
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO work_items(
              id, kind, title, source, status, approval_state,
              write_actions_allowed, created_at, updated_at, payload_json
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                kind,
                title,
                source,
                "open",
                "pending",
                0,
                ts,
                ts,
                json.dumps(safe_payload, sort_keys=True),
            ),
        )
        _write_audit_event(
            conn,
            event_type="work_item_added",
            work_item_id=item_id,
            payload={"kind": kind, "source": source, "approval_state": "pending"},
        )
    return show_work_item(db_path=db_path, item_id=item_id)


def list_work_items(
    *,
    db_path: Path = DEFAULT_QUEUE_PATH,
    status: str | None = None,
    approval_state: str | None = None,
) -> list[QueueItem]:
    init_queue(db_path)
    clauses: list[str] = []
    values: list[str] = []
    if status:
        clauses.append("status = ?")
        values.append(status)
    if approval_state:
        if approval_state not in VALID_APPROVAL_STATES:
            raise ValueError(f"unknown approval state: {approval_state}")
        clauses.append("approval_state = ?")
        values.append(approval_state)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM work_items {where} ORDER BY created_at DESC, id DESC",
            values,
        ).fetchall()
    return [_row_to_item(row) for row in rows]


def show_work_item(*, db_path: Path = DEFAULT_QUEUE_PATH, item_id: str) -> QueueItem:
    init_queue(db_path)
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM work_items WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        raise KeyError(item_id)
    return _row_to_item(row)


def _set_approval_state(
    *,
    db_path: Path,
    item_id: str,
    approval_state: str,
    decision_note: str | None,
) -> QueueItem:
    if approval_state not in VALID_APPROVAL_STATES:
        raise ValueError(f"unknown approval state: {approval_state}")
    init_queue(db_path)
    ts = _now()
    status = "open" if approval_state == "approved" else approval_state
    with _connect(db_path) as conn:
        current = conn.execute("SELECT id FROM work_items WHERE id = ?", (item_id,)).fetchone()
        if current is None:
            raise KeyError(item_id)
        conn.execute(
            """
            UPDATE work_items
            SET approval_state = ?, status = ?, decision_note = ?, updated_at = ?
            WHERE id = ?
            """,
            (approval_state, status, decision_note, ts, item_id),
        )
        _write_audit_event(
            conn,
            event_type=f"work_item_{approval_state}",
            work_item_id=item_id,
            payload={"decision_note": decision_note},
        )
    return show_work_item(db_path=db_path, item_id=item_id)


def approve_work_item(
    *,
    db_path: Path = DEFAULT_QUEUE_PATH,
    item_id: str,
    decision_note: str | None = None,
) -> QueueItem:
    return _set_approval_state(
        db_path=db_path,
        item_id=item_id,
        approval_state="approved",
        decision_note=decision_note,
    )


def reject_work_item(
    *,
    db_path: Path = DEFAULT_QUEUE_PATH,
    item_id: str,
    decision_note: str | None = None,
) -> QueueItem:
    return _set_approval_state(
        db_path=db_path,
        item_id=item_id,
        approval_state="rejected",
        decision_note=decision_note,
    )


def skip_work_item(
    *,
    db_path: Path = DEFAULT_QUEUE_PATH,
    item_id: str,
    decision_note: str,
) -> QueueItem:
    init_queue(db_path)
    ts = _now()
    with _connect(db_path) as conn:
        current = conn.execute("SELECT id FROM work_items WHERE id = ?", (item_id,)).fetchone()
        if current is None:
            raise KeyError(item_id)
        conn.execute(
            """
            UPDATE work_items
            SET approval_state = ?, status = ?, decision_note = ?, updated_at = ?
            WHERE id = ?
            """,
            ("rejected", "skipped", decision_note, ts, item_id),
        )
        _write_audit_event(
            conn,
            event_type="work_item_skipped",
            work_item_id=item_id,
            payload={
                "approval_state": "rejected",
                "status": "skipped",
                "decision_note": decision_note,
            },
        )
    return show_work_item(db_path=db_path, item_id=item_id)


def add_proposal(
    *,
    db_path: Path = DEFAULT_QUEUE_PATH,
    work_item_id: str,
    title: str,
    summary: str,
    patch_plan: str,
    risk_level: str = "medium",
) -> ProposalRecord:
    init_queue(db_path)
    show_work_item(db_path=db_path, item_id=work_item_id)
    proposal_id = f"prp_{uuid4().hex[:12]}"
    ts = _now()
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO proposals(
              id, work_item_id, title, summary, patch_plan, risk_level,
              approval_state, created_at, updated_at
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proposal_id,
                work_item_id,
                title,
                summary,
                patch_plan,
                risk_level,
                "pending",
                ts,
                ts,
            ),
        )
        _write_audit_event(
            conn,
            event_type="proposal_added",
            work_item_id=work_item_id,
            payload={
                "proposal_id": proposal_id,
                "risk_level": risk_level,
                "approval_state": "pending",
            },
        )
    return show_proposal(db_path=db_path, proposal_id=proposal_id)


def list_proposals(
    *,
    db_path: Path = DEFAULT_QUEUE_PATH,
    work_item_id: str | None = None,
    approval_state: str | None = None,
) -> list[ProposalRecord]:
    init_queue(db_path)
    clauses: list[str] = []
    values: list[str] = []
    if work_item_id:
        clauses.append("work_item_id = ?")
        values.append(work_item_id)
    if approval_state:
        if approval_state not in VALID_APPROVAL_STATES:
            raise ValueError(f"unknown approval state: {approval_state}")
        clauses.append("approval_state = ?")
        values.append(approval_state)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM proposals {where} ORDER BY created_at DESC, id DESC",
            values,
        ).fetchall()
    return [_row_to_proposal(row) for row in rows]


def show_proposal(*, db_path: Path = DEFAULT_QUEUE_PATH, proposal_id: str) -> ProposalRecord:
    init_queue(db_path)
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
    if row is None:
        raise KeyError(proposal_id)
    return _row_to_proposal(row)


def _set_proposal_approval_state(
    *,
    db_path: Path,
    proposal_id: str,
    approval_state: str,
    decision_note: str | None,
) -> ProposalRecord:
    if approval_state not in VALID_APPROVAL_STATES:
        raise ValueError(f"unknown approval state: {approval_state}")
    init_queue(db_path)
    ts = _now()
    with _connect(db_path) as conn:
        current = conn.execute(
            "SELECT id, work_item_id FROM proposals WHERE id = ?",
            (proposal_id,),
        ).fetchone()
        if current is None:
            raise KeyError(proposal_id)
        conn.execute(
            """
            UPDATE proposals
            SET approval_state = ?, decision_note = ?, updated_at = ?
            WHERE id = ?
            """,
            (approval_state, decision_note, ts, proposal_id),
        )
        _write_audit_event(
            conn,
            event_type=f"proposal_{approval_state}",
            work_item_id=str(current["work_item_id"]),
            payload={"proposal_id": proposal_id, "decision_note": decision_note},
        )
    return show_proposal(db_path=db_path, proposal_id=proposal_id)


def approve_proposal(
    *,
    db_path: Path = DEFAULT_QUEUE_PATH,
    proposal_id: str,
    decision_note: str | None = None,
) -> ProposalRecord:
    return _set_proposal_approval_state(
        db_path=db_path,
        proposal_id=proposal_id,
        approval_state="approved",
        decision_note=decision_note,
    )


def reject_proposal(
    *,
    db_path: Path = DEFAULT_QUEUE_PATH,
    proposal_id: str,
    decision_note: str | None = None,
) -> ProposalRecord:
    return _set_proposal_approval_state(
        db_path=db_path,
        proposal_id=proposal_id,
        approval_state="rejected",
        decision_note=decision_note,
    )


def export_work_items(*, db_path: Path = DEFAULT_QUEUE_PATH) -> dict[str, Any]:
    work_items = [item.to_dict() for item in list_work_items(db_path=db_path)]
    with _connect(db_path) as conn:
        _write_audit_event(
            conn,
            event_type="work_items_exported",
            work_item_id=None,
            payload={"count": len(work_items), "export": "work_items"},
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "db_path": str(db_path),
        "local_first": True,
        "work_items": work_items,
    }


def list_audit_events(
    *,
    db_path: Path = DEFAULT_QUEUE_PATH,
    work_item_id: str | None = None,
) -> list[AuditEvent]:
    init_queue(db_path)
    clauses: list[str] = []
    values: list[str] = []
    if work_item_id:
        clauses.append("work_item_id = ?")
        values.append(work_item_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM audit_events {where} ORDER BY id ASC",
            values,
        ).fetchall()
    return [_row_to_audit_event(row) for row in rows]


def export_audit_events(
    *,
    db_path: Path = DEFAULT_QUEUE_PATH,
    work_item_id: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "db_path": str(db_path),
        "local_first": True,
        "audit_events": [
            event.to_dict()
            for event in list_audit_events(db_path=db_path, work_item_id=work_item_id)
        ],
    }
