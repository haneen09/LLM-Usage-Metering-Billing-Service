from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Subscription, Plan, UsageEvent
from app.schemas import UsageResponse
from app.services.quota import get_usage_this_month

router = APIRouter()


@router.get("/usage", response_model=UsageResponse)
def get_usage(
    tenant_id: str = Query(...),
    db: Session = Depends(get_db),
):
    subscription = (
        db.query(Subscription)
        .filter(Subscription.tenant_id == tenant_id)
        .first()
    )

    if subscription is None:
        raise HTTPException(
            status_code=404,
            detail="No subscription found for this tenant.",
        )

    plan = db.query(Plan).filter(Plan.id == subscription.plan_id).first()

    api_calls_used = get_usage_this_month(
        db,
        tenant_id,
        "api_call",
    )

    tokens_used = get_usage_this_month(
        db,
        tenant_id,
        "ai_tokens",
    )

    cost_this_month = (
        db.query(UsageEvent)
        .filter(
            UsageEvent.tenant_id == tenant_id,
            UsageEvent.created_at >= __import__("app.services.quota", fromlist=["_month_start"])._month_start(),
        )
        .all()
    )

    total_cost_cents = sum(event.cost_cents for event in cost_this_month)

    return UsageResponse(
        plan=plan.id,
        api_calls_used=api_calls_used,
        api_calls_limit=plan.api_call_limit,
        tokens_used=tokens_used,
        tokens_limit=plan.token_limit,
        cost_this_month_cents=total_cost_cents,
    )
