"""Append-only audit trail shared by every milestone that needs one.

The Admin Portal reads these rows through ``/api/admin/audit-logs``; nothing
else in the app may read them.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog

# --- chatbot experience feedback ---------------------------------------

ACTION_CHATBOT_FEEDBACK = "CHATBOT_EXPERIENCE_FEEDBACK"

#: Customer-facing experience label for each stored rating.
EXPERIENCE_LABELS = {1: "Bad", 2: "Neutral", 3: "Excellent"}


def record(db: Session, action: str, details: str, user_id: int | None = None) -> AuditLog:
    """Append one audit event. Never raises - auditing must not break a request."""
    try:
        entry = AuditLog(action=action, details=details, user_id=user_id)
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry
    except Exception:  # noqa: BLE001 - audit failure must not surface to the customer
        db.rollback()
        return None


def list_recent(db: Session, limit: int = 50, action: str | None = None) -> list[AuditLog]:
    """Most recent events first, optionally filtered to a single action."""
    limit = max(1, min(int(limit), 200))
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    return list(db.execute(stmt).scalars())


__all__ = [
    "ACTION_CHATBOT_FEEDBACK",
    "EXPERIENCE_LABELS",
    "record",
    "list_recent",
]