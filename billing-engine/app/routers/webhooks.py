"""
Receives events FROM Stripe. Three things this must get right, in order:

  1. Verify the signature. If it doesn't check out, this wasn't really
     sent by Stripe -> reject with 400, do nothing else.
  2. Check if we've already processed this exact event ID before. If
     yes, ignore it silently (return 200 so Stripe stops retrying, but
     don't apply the change twice).
  3. Only then, act on the event: update the tenant's subscription.
"""

import os
import stripe
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Subscription, ProcessedStripeEvent

router = APIRouter()

STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    # Step 1: verify this really came from Stripe.
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid webhook signature.")

    event_id = event["id"]
    event_type = event["type"]

    # Step 2: have we already handled this exact event before? Stripe
    # retries delivery, so the same event_id can arrive more than once.
    already_processed = (
        db.query(ProcessedStripeEvent).filter(ProcessedStripeEvent.id == event_id).first()
    )
    if already_processed:
        return {"status": "ignored_duplicate"}

    data = event["data"]["object"]

    # Step 3: act on the event type.
    if event_type == "checkout.session.completed":
        tenant_id = data["metadata"]["tenant_id"]
        stripe_customer_id = data["customer"]
        stripe_subscription_id = data["subscription"]

        subscription = (
            db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
        )
        subscription.plan_id = "pro"
        subscription.status = "active"
        subscription.stripe_customer_id = stripe_customer_id
        subscription.stripe_subscription_id = stripe_subscription_id
        db.commit()

    elif event_type == "customer.subscription.updated":
        stripe_subscription_id = data["id"]
        new_status = data["status"]  # e.g. "active", "past_due", "canceled"

        subscription = (
            db.query(Subscription)
            .filter(Subscription.stripe_subscription_id == stripe_subscription_id)
            .first()
        )
        if subscription:
            subscription.status = new_status
            db.commit()

    elif event_type == "customer.subscription.deleted":
        stripe_subscription_id = data["id"]

        subscription = (
            db.query(Subscription)
            .filter(Subscription.stripe_subscription_id == stripe_subscription_id)
            .first()
        )
        if subscription:
            subscription.plan_id = "free"
            subscription.status = "canceled"
            db.commit()

    # Record that we've handled this event, so a retried delivery of the
    # same event_id gets caught by the Step 2 check next time.
    db.add(ProcessedStripeEvent(id=event_id))
    db.commit()

    return {"status": "processed"}
