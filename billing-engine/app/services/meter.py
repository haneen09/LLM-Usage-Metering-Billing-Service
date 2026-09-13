"""
MeterService — the idempotency heart of the whole system.

The flow, exactly as sketched in DESIGN.md:
  1. Try to insert a new usage_events row with the given idempotency key.
  2. If it succeeds -> this is a genuinely new action.
  3. If it fails because that key already exists -> this is a retry.
     Don't record anything new. Look up the original row and return
     the same result we gave the first time.
"""

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models import UsageEvent


class DuplicateRequest(Exception):
    """Raised when an idempotency key was already used — carries the original event."""
    def __init__(self, existing_event: UsageEvent):
        self.existing_event = existing_event


def find_by_idempotency_key(db: Session, idempotency_key: str) -> UsageEvent | None:
    """
    Look this up BEFORE running any quota check. If we ran the quota
    check on every retry, a request sitting exactly at the boundary
    would get double-counted against its own limit on the second try —
    the point of idempotency is that a retry does no new work at all.
    """
    return (
        db.query(UsageEvent)
        .filter(UsageEvent.idempotency_key == idempotency_key)
        .first()
    )


def record_usage(db: Session, tenant_id: str, usage_type: str, quantity: int,
                  idempotency_key: str, cost_cents: int) -> UsageEvent:
    """
    Attempt to record a new usage event. Raises DuplicateRequest if this
    idempotency key was already used — callers should catch that and
    replay the original response instead of treating it as an error.
    """
    event = UsageEvent(
        tenant_id=tenant_id,
        type=usage_type,
        quantity=quantity,
        idempotency_key=idempotency_key,
        cost_cents=cost_cents,
    )
    db.add(event)
    try:
        db.commit()
        db.refresh(event)
        return event
    except IntegrityError:
        # The UNIQUE constraint on idempotency_key fired — this key was
        # already used. Roll back our failed insert, then fetch and
        # return the original event instead.
        db.rollback()
        existing = (
            db.query(UsageEvent)
            .filter(UsageEvent.idempotency_key == idempotency_key)
            .first()
        )
        raise DuplicateRequest(existing)
