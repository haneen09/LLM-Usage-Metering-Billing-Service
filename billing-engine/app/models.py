import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


def new_uuid():
    return str(uuid.uuid4())


def utcnow():
    return datetime.now(timezone.utc)


class Plan(Base):
    """Lookup table — one row per plan type, not per tenant."""
    __tablename__ = "plans"

    id = Column(String, primary_key=True)  # "free" or "pro"
    name = Column(String, nullable=False)
    api_call_limit = Column(Integer, nullable=False)
    token_limit = Column(Integer, nullable=False)
    price_cents = Column(Integer, nullable=False)  # integer cents, never a float


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(String, primary_key=True, default=new_uuid)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    created_at = Column(DateTime, default=utcnow)

    subscriptions = relationship("Subscription", back_populates="tenant")
    usage_events = relationship("UsageEvent", back_populates="tenant")


class Subscription(Base):
    """Mirrors what Stripe thinks is true. Updated only by verified webhooks."""
    __tablename__ = "subscriptions"

    id = Column(String, primary_key=True, default=new_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    plan_id = Column(String, ForeignKey("plans.id"), nullable=False)
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)
    status = Column(String, default="active")  # active / past_due / canceled
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    tenant = relationship("Tenant", back_populates="subscriptions")
    plan = relationship("Plan")


class UsageEvent(Base):
    """
    One row per billable action. The UNIQUE constraint on idempotency_key
    is what actually prevents double-counting — the database rejects a
    second insert with the same key before our application code even
    has to think about it.
    """
    __tablename__ = "usage_events"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_idempotency_key"),)

    id = Column(String, primary_key=True, default=new_uuid)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False)
    type = Column(String, nullable=False)  # "api_call" or "ai_tokens"
    quantity = Column(Integer, nullable=False)
    idempotency_key = Column(String, nullable=False)
    cost_cents = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=utcnow)

    tenant = relationship("Tenant", back_populates="usage_events")
