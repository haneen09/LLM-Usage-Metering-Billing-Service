from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import GenerateRequest, GenerateResponse
from app.pricing import calculate_cost_cents
from app.services import meter, quota

router = APIRouter()


@router.post("/generate", response_model=GenerateResponse)
def generate(
    body: GenerateRequest,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required.")

    # Step 1: has this exact request already been done? If so, replay the
    # original result — no new event, no quota re-check, no double cost.
    existing = meter.find_by_idempotency_key(db, idempotency_key)
    if existing is not None:
        usage_this_month = quota.get_usage_this_month(db, body.tenant_id, existing.type)
        return GenerateResponse(
            recorded=True,
            cost_cents=existing.cost_cents,
            usage_this_month=usage_this_month,
        )

    # Step 2: genuinely new request — check the tenant is allowed to do this.
    try:
        quota.check_quota(db, body.tenant_id, body.type, body.quantity)
    except quota.SubscriptionInactive as e:
        raise HTTPException(
            status_code=402,
            detail=f"Payment required: subscription status is '{e.status}'. "
                   f"Update billing to continue.",
        )
    except quota.QuotaExceeded as e:
        raise HTTPException(
            status_code=429,
            detail=f"Usage quota exceeded for {e.usage_type}: "
                   f"{e.used} used, limit is {e.limit} this month.",
        )

    # Step 3: allowed — calculate cost and record it.
    cost_cents = calculate_cost_cents(body.type, body.quantity)
    try:
        event = meter.record_usage(
            db, body.tenant_id, body.type, body.quantity, idempotency_key, cost_cents
        )
    except meter.DuplicateRequest as e:
        # Extremely rare race: two identical requests landed at the same
        # instant and both passed the Step 1 check. The database's
        # UNIQUE constraint is the real backstop here.
        event = e.existing_event

    usage_this_month = quota.get_usage_this_month(db, body.tenant_id, event.type)
    return GenerateResponse(
        recorded=True,
        cost_cents=event.cost_cents,
        usage_this_month=usage_this_month,
    )
