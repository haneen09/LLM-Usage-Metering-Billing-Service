from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import GenerateRequest, GenerateResponse
from app.pricing import calculate_cost_cents, calculate_token_cost_cents
from app.services import meter, quota, background

router = APIRouter()


@router.post("/generate", response_model=GenerateResponse)
def generate(
    body: GenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if not idempotency_key:
        raise HTTPException(
            status_code=400,
            detail="Idempotency-Key header is required.",
        )

    # Validate the request and determine the billable quantity.
    if body.type == "api_call":
        if body.quantity is None:
            raise HTTPException(
                status_code=400,
                detail="quantity is required for api_call.",
            )

        if any(
            [
                body.input_tokens,
                body.cached_input_tokens,
                body.output_tokens,
                body.reasoning_tokens,
            ]
        ):
            raise HTTPException(
                status_code=400,
                detail="Token fields must be zero for api_call.",
            )

        billable_quantity = body.quantity

    else:
        if body.quantity is not None:
            raise HTTPException(
                status_code=400,
                detail="quantity must not be provided for ai_tokens.",
            )

        if body.cached_input_tokens > body.input_tokens:
            raise HTTPException(
                status_code=400,
                detail="cached_input_tokens cannot exceed input_tokens.",
            )

        billable_quantity = (
            body.input_tokens
            + body.output_tokens
            + body.reasoning_tokens
        )

        if billable_quantity <= 0:
            raise HTTPException(
                status_code=400,
                detail="At least one token count must be greater than zero.",
            )

    # Step 1: replay an existing idempotent request.
    existing = meter.find_by_idempotency_key(db, idempotency_key)

    if existing is not None:
        usage_this_month = quota.get_usage_this_month(
            db,
            body.tenant_id,
            existing.type,
        )

        return GenerateResponse(
            recorded=True,
            cost_cents=existing.cost_cents,
            usage_this_month=usage_this_month,
        )

    # Step 2: check quota before recording new usage.
    try:
        quota.check_quota(
            db,
            body.tenant_id,
            body.type,
            billable_quantity,
        )

    except quota.SubscriptionInactive as e:
        raise HTTPException(
            status_code=402,
            detail=(
                f"Payment required: subscription status is '{e.status}'. "
                f"Update billing to continue."
            ),
        )

    except quota.QuotaExceeded as e:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Usage quota exceeded for {e.usage_type}: "
                f"{e.used} used, limit is {e.limit} this month."
            ),
        )

    # Step 3: calculate the actual cost.
    if body.type == "api_call":
        cost_cents = calculate_cost_cents(
            "api_call",
            billable_quantity,
        )
    else:
        try:
            cost_cents = calculate_token_cost_cents(
                input_tokens=body.input_tokens,
                cached_input_tokens=body.cached_input_tokens,
                output_tokens=body.output_tokens,
                reasoning_tokens=body.reasoning_tokens,
            )
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=str(e),
            )

    # Step 4: record exactly one usage event.
    try:
        event = meter.record_usage(
            db,
            body.tenant_id,
            body.type,
            billable_quantity,
            idempotency_key,
            cost_cents,
        )

    except meter.DuplicateRequest as e:
        event = e.existing_event

    usage_this_month = quota.get_usage_this_month(
        db,
        body.tenant_id,
        event.type,
    )

    background_tasks.add_task(
        background.reconcile_usage,
        db,
        body.tenant_id,
    )

    return GenerateResponse(
        recorded=True,
        cost_cents=event.cost_cents,
        usage_this_month=usage_this_month,
    )
