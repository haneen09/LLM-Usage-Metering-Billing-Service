from fastapi import FastAPI

from app.database import Base, engine
from app.routers import generate, usage

# Create tables on startup if they don't exist yet.
# For a real production system you'd use Alembic migrations instead —
# this is fine for a self-paced capstone.
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Usage Metering & Billing Engine")

app.include_router(generate.router)
app.include_router(usage.router)


@app.get("/")
def root():
    return {"status": "ok", "service": "usage-metering-billing-engine"}
