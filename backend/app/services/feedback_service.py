"""One customer-experience rating per chatbot conversation.

Rules enforced here (not in the router) so they hold for every caller:

* a rating must be 1, 2 or 3;
* ``conversation_id`` must be a canonical UUID;
* a conversation may only ever be rated once;
* the owner is taken from the authenticated JWT user, never from the payload.
"""
from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import ChatFeedback, User
from app.services import audit_service


def normalize_conversation_id(raw: str) -> str:
    """Return the canonical UUID string, or raise 400 for anything else.

    Canonical form is required so ``conversation_id`` stays a single stable key
    and the unique constraint cannot be sidestepped with alternate spellings
    such as braces or ``urn:uuid:`` prefixes.
    """
    if not isinstance(raw, str):
        raise HTTPException(400, "Invalid conversation_id.")
    candidate = raw.strip()
    try:
        parsed = uuid.UUID(candidate)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(400, "Invalid conversation_id.")
    if candidate.lower() != str(parsed):
        raise HTTPException(400, "Invalid conversation_id.")
    return str(parsed)


def create_feedback(
    db: Session,
    conversation_id: str,
    rating: int,
    user: User | None = None,
) -> ChatFeedback:
    """Store one rating for ``conversation_id`` and write its audit event."""
    conversation_id = normalize_conversation_id(conversation_id)

    try:
        rating = int(rating)
    except (TypeError, ValueError):
        raise HTTPException(422, "Rating must be 1, 2 or 3.")
    if rating not in audit_service.EXPERIENCE_LABELS:
        raise HTTPException(422, "Rating must be 1, 2 or 3.")

    existing = db.query(ChatFeedback).filter_by(conversation_id=conversation_id).first()
    if existing:
        raise HTTPException(409, "Feedback already submitted for this conversation.")

    user_id = user.id if user else None
    row = ChatFeedback(conversation_id=conversation_id, rating=rating, user_id=user_id)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        # Concurrent duplicate - the unique constraint is the source of truth.
        db.rollback()
        raise HTTPException(409, "Feedback already submitted for this conversation.")
    db.refresh(row)

    label = audit_service.EXPERIENCE_LABELS[rating]
    audit_service.record(
        db,
        audit_service.ACTION_CHATBOT_FEEDBACK,
        f"Rating: {rating} ({label}); Conversation: {conversation_id}",
        user_id=user_id,
    )
    return row


__all__ = ["create_feedback", "normalize_conversation_id"]