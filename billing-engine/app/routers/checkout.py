"""
Checkout flow: customer picks Pro -> we create a Stripe Checkout
Session -> Stripe hosts the actual payment page -> customer pays with
a test card -> Stripe sends us a webhook telling us it worked.

We never touch card details ourselves — that's the whole point of
using Stripe Checkout instead of building our own payment form.
"""

import os
import stripe
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Tenant, Subscription, Plan

router = APIRouter()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")


@router.post("/checkout")
def create_checkout_session(tenant_id: str, db: Session = Depends(get_db)):
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found.")

    pro_plan = db.query(Plan).filter(Plan.id == "pro").first()

    # We pass tenant_id in metadata so that when the webhook fires later,
    # we know exactly which tenant to upgrade — Stripe has no idea what
    # a "tenant" is, this is how we thread our own data through.
    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[
            {
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": "Pro Plan"},
                    "unit_amount": pro_plan.price_cents,
                    "recurring": {"interval": "month"},
                },
                "quantity": 1,
            }
        ],
        metadata={"tenant_id": tenant_id},
        success_url="http://localhost:8000/checkout-success",
        cancel_url="http://localhost:8000/checkout-cancelled",
    )

    return {"checkout_url": session.url}
