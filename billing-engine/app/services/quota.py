"""
QuotaService — decides whether a billable action is allowed before it happens.

Two distinct rejection reasons, matching the brief exactly:
  - 402 Payment Required: the tenant's subscription isn't in good
    standing (e.g. past_due or canceled) — they need to pay/fix billing.
  - 429 Too Many Requests: the subscription is fine, but this action
    would push them over their plan's monthly quota.
"""

from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models import Tenant, Subscription, Plan, UsageEvent


class SubscriptionInactive(Exception):
    """Tenant's subscription isn't active — this maps to 402."""
    def __init__(self, status: str):
        self.status = status


class QuotaExceeded(Exception):
    """Tenant is over their plan's limit for this usage type — maps to 429."""
    def __init__(self, usage_type: str, used: int, limit: int):
        self.usage_type = usage_type
        self.used = used
        self.limit = limit


def _month_start():
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def get_usage_this_month(db: Session, tenant_id: str, usage_type: str) -> int:
    events = (
        db.query(UsageEvent)
        .filter(
            UsageEvent.tenant_id == tenant_id,
            UsageEvent.type == usage_type,
            UsageEvent.created_at >= _month_start(),
        )
        .all()
    )
    return sum(e.quantity for e in events)


def check_quota(db: Session, tenant_id: str, usage_type: str, quantity: int) -> None:
    """
    Raises SubscriptionInactive or QuotaExceeded if the request should be
    blocked. Returns None (silently) if the request is allowed.
    """
    subscription = (
        db.query(Subscription)
        .filter(Subscription.tenant_id == tenant_id)
        .first()
    )
    if subscription is None:
        # No subscription row at all — treat like an inactive account.
        raise SubscriptionInactive(status="none")

    if subscription.status != "active":
        raise SubscriptionInactive(status=subscription.status)

    plan = db.query(Plan).filter(Plan.id == subscription.plan_id).first()
    limit = plan.api_call_limit if usage_type == "api_call" else plan.token_limit

    current_usage = get_usage_this_month(db, tenant_id, usage_type)
    if current_usage + quantity > limit:
        raise QuotaExceeded(usage_type=usage_type, used=current_usage, limit=limit)
