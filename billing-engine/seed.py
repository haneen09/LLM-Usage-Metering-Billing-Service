"""
Run this once to set up demo data:  python seed.py

Creates:
  - the Free and Pro plans (matching DESIGN.md)
  - one demo tenant, subscribed to Free, with plenty of room left this
    month, so you can test /generate and /usage right away
  - a second demo tenant already sitting one call under its Free limit,
    so you can test the 429 boundary immediately
"""

from app.database import Base, engine, SessionLocal
from app.models import Plan, Tenant, Subscription, UsageEvent

Base.metadata.create_all(bind=engine)

db = SessionLocal()

# --- Plans ---
if not db.query(Plan).filter(Plan.id == "free").first():
    db.add(Plan(id="free", name="Free", api_call_limit=1000, token_limit=100_000, price_cents=0))

if not db.query(Plan).filter(Plan.id == "pro").first():
    db.add(Plan(id="pro", name="Pro", api_call_limit=10_000, token_limit=1_000_000, price_cents=2900))

db.commit()

# --- Demo tenant #1: plenty of quota left ---
demo = Tenant(id="demo-tenant-1", name="Acme Inc", email="billing@acme.test")
db.merge(demo)
db.commit()

if not db.query(Subscription).filter(Subscription.tenant_id == "demo-tenant-1").first():
    db.add(Subscription(tenant_id="demo-tenant-1", plan_id="free", status="active"))
    db.commit()

# --- Demo tenant #2: sitting exactly one call under the Free limit ---
boundary_tenant = Tenant(id="demo-tenant-2", name="Boundary Co", email="billing@boundary.test")
db.merge(boundary_tenant)
db.commit()

if not db.query(Subscription).filter(Subscription.tenant_id == "demo-tenant-2").first():
    db.add(Subscription(tenant_id="demo-tenant-2", plan_id="free", status="active"))
    db.commit()

# Backfill 999 api_call usage events for tenant 2 so the 1000th call
# is the boundary and the 1001st should be rejected.
existing_count = (
    db.query(UsageEvent)
    .filter(UsageEvent.tenant_id == "demo-tenant-2", UsageEvent.type == "api_call")
    .count()
)
if existing_count == 0:
    for i in range(999):
        db.add(
            UsageEvent(
                tenant_id="demo-tenant-2",
                type="api_call",
                quantity=1,
                idempotency_key=f"seed-backfill-{i}",
                cost_cents=1,
            )
        )
    db.commit()

print("Seed complete.")
print("  demo-tenant-1: fresh Free plan, 0 usage")
print("  demo-tenant-2: Free plan, 999/1000 api_calls used (test the boundary here)")
