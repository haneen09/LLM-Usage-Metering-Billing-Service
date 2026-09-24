import logging

from app.database import SessionLocal
from app.models import UsageEvent

logger = logging.getLogger("billing.background")


def reconcile_usage(tenant_id: str, attempts: int = 3) -> bool:
    db = SessionLocal()

    try:
        for attempt in range(1, attempts + 1):
            try:
                events = (
                    db.query(UsageEvent)
                    .filter(UsageEvent.tenant_id == tenant_id)
                    .all()
                )

                for event in events:
                    if event.quantity < 0 or event.cost_cents < 0:
                        raise ValueError(
                            f"Invalid usage event {event.id}: "
                            "quantity/cost cannot be negative."
                        )

                logger.info(
                    "Usage reconciliation succeeded for tenant %s",
                    tenant_id,
                )
                return True

            except Exception as exc:
                logger.warning(
                    "Usage reconciliation attempt %s/%s failed for tenant %s: %s",
                    attempt,
                    attempts,
                    tenant_id,
                    exc,
                )

                if attempt == attempts:
                    logger.error(
                        "ALERT: usage reconciliation failed after %s attempts "
                        "for tenant %s",
                        attempts,
                        tenant_id,
                    )
                    return False

        return False

    finally:
        db.close()