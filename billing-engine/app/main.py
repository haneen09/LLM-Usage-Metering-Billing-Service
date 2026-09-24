from fastapi import FastAPI

from app.database import Base
from app.routers import generate, usage, checkout, webhooks

# Create tables on startup if they don't exist yet.
# For a real production system you'd use Alembic migrations instead —
# this is fine for a self-paced capstone.


app = FastAPI(title="Usage Metering & Billing Engine")

app.include_router(generate.router)
app.include_router(usage.router)
app.include_router(checkout.router)
app.include_router(webhooks.router)


@app.get("/checkout-success")
def checkout_success():
    return {"message": "Checkout complete! Check GET /usage to confirm your plan upgraded."}


@app.get("/checkout-cancelled")
def checkout_cancelled():
    return {"message": "Checkout was cancelled."}


@app.get("/")
def root():
    return {"status": "ok", "service": "usage-metering-billing-engine"}
