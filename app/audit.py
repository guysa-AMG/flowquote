"""Audit logging utilities.

Non-negotiable rule (PLAN.md §3):
Every single decision, override, extraction, and approval is immutably logged.
"""
import json
import sqlite3
from typing import Any


def log_audit_event(
    conn: sqlite3.Connection,
    business_id: str,
    entity: str,
    entity_id: str,
    event: str,
    payload: dict[str, Any],
    actor: str = "system",
) -> int:
    """Inserts a structured audit event into the audit_log table."""
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO audit_log (business_id, entity, entity_id, event, payload_json, actor)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (business_id, entity, entity_id, event, json.dumps(payload), actor),
    )
    return cursor.lastrowid or 0

def fetch_audit_trail(conn: sqlite3.Connection, entity: str, entity_id: str) -> list[dict[str, Any]]:
    """Retrieves chronological audit events for an entity."""
    cursor = conn.cursor()
    cursor.execute(
        """SELECT id, ts, business_id, entity, entity_id, event, payload_json, actor
           FROM audit_log
           WHERE entity = ? AND entity_id = ?
           ORDER BY ts ASC, id ASC""",
        (entity, entity_id),
    )
    rows = cursor.fetchall()
    return [
        {
            "id": r["id"],
            "timestamp": r["ts"],
            "business_id": r["business_id"],
            "entity": r["entity"],
            "entity_id": r["entity_id"],
            "event": r["event"],
            "payload": json.loads(r["payload_json"]),
            "actor": r["actor"],
        }
        for r in rows
    ]
