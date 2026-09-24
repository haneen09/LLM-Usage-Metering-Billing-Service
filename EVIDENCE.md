# EVIDENCE

## 1. Idempotent metering (no double-counting on retry)

Sent the same request twice using the same `Idempotency-Key: test-key-1`.

Request 1:

```text
{ recorded: True, cost_cents: 1, usage_this_month: 1 }
```

Request 2:

```text
{ recorded: True, cost_cents: 1, usage_this_month: 1 }
```

`GET /usage?tenant_id=demo-tenant-1` confirmed that only one usage event was counted:

```text
{
  api_calls_used: 1,
  api_calls_limit: 1000,
  ...
}
```

The database also enforces uniqueness on the idempotency key.

---

## 2. Quota boundary enforcement

Tenant was seeded at 999/1000 API calls.

Call #1000 at the exact boundary:

```text
200 OK

{
  recorded: True,
  cost_cents: 1,
  usage_this_month: 1000
}
```

Call #1001 over the limit:

```text
429 Too Many Requests

{
  "detail": "Usage quota exceeded for api_call: 1000 used, limit is 1000 this month."
}
```

The application also returns `402 Payment Required` when the tenant subscription is inactive.

---

## 3. AI token pricing

Tested a token request containing normal input, cached input, output, and reasoning tokens:

```json
{
  "tenant_id": "demo-tenant-1",
  "type": "ai_tokens",
  "input_tokens": 1000,
  "cached_input_tokens": 200,
  "output_tokens": 500,
  "reasoning_tokens": 300
}
```

Response:

```json
{
  "recorded": true,
  "cost_cents": 7,
  "usage_this_month": 1800
}
```

Pricing calculation:

```text
800 normal input tokens × 3 cents / 1K = 2.4 cents
200 cached input tokens × 1 cent / 1K = 0.2 cents
500 output tokens × 6 cents / 1K = 3.0 cents
300 reasoning tokens × 6 cents / 1K = 1.8 cents

Total = 7.4 cents
Integer-cent result = 7 cents
```

Reasoning tokens are charged using the output-token rate.

Cached input is separated from normal input so the same token is not charged twice.

Pricing constants are pinned in `billing-engine/app/pricing.py`.

---

## 4. Usage reporting

`GET /usage?tenant_id=demo-tenant-1` reports:

* Current plan
* API calls used and API call limit
* Tokens used and token limit
* Cost for the current month

The reported monthly cost is calculated from the stored `UsageEvent.cost_cents` values.

---

## 5. Stripe Checkout

Stripe test-mode Checkout was successfully tested.

Flow:

```text
POST /checkout?tenant_id=demo-tenant-1
        ↓
Stripe Checkout
        ↓
checkout.session.completed
        ↓
POST /webhooks/stripe
        ↓
Tenant subscription updated
        ↓
GET /usage
```

Successful webhook response:

```text
200 OK
```

After payment, `/usage` showed:

```text
plan                  : pro
api_calls_used        : 0
api_calls_limit       : 10000
tokens_used           : 0
tokens_limit          : 1000000
cost_this_month_cents : 0
```

This confirmed the tenant changed from the Free plan to the Pro plan after the Stripe Checkout flow.

---

## 6. Stripe webhook security and deduplication

Stripe webhook requests are verified using the Stripe webhook signature before processing.

The application handles:

```text
checkout.session.completed
customer.subscription.updated
customer.subscription.deleted
```

Processed Stripe event IDs are stored in the `processed_stripe_events` table.

If the same Stripe event is received again, the stored event ID prevents duplicate processing.

Stripe remains the payment-system source of truth, while the local database mirrors verified subscription events.

---

## 7. Background processing

A background reconciliation task is triggered after usage is recorded.

The task:

* Runs outside the main request processing path.
* Reads the tenant's stored usage events.
* Validates that stored quantities and costs are not negative.
* Retries failed processing up to three times.
* Logs an alert if all retry attempts fail.

Implementation:

```text
POST /generate
      ↓
Record usage
      ↓
Return API response
      ↓
Background reconciliation task
```

The implementation is in:

```text
billing-engine/app/services/background.py
```

---

## 8. Database persistence and migrations

The application uses SQLAlchemy for persistent database access.

The database schema contains:

```text
plans
tenants
subscriptions
usage_events
processed_stripe_events
```

Alembic was added for schema migrations.

The existing database was established as the migration baseline using:

```text
python -m alembic stamp head
```

The current migration revision is:

```text
c5b9fc6cf021
```

The application no longer creates the database schema automatically at FastAPI startup. Schema changes are intended to be managed through Alembic migrations.

---

## 9. Request validation

The API validates invalid requests at the HTTP boundary.

Examples include:

* Missing `Idempotency-Key` → `400`
* Missing API-call quantity → `400`
* Token fields supplied for an API-call request → `400`
* Quantity supplied for an AI-token request → `400`
* Cached input greater than total input → `400`
* AI-token request with no billable tokens → `400`
* Negative token values → validation error

Pydantic request schemas are defined in:

```text
billing-engine/app/schemas.py
```

---

## 10. Tenant isolation

Usage events are associated with a specific tenant through `tenant_id`.

Usage reporting and quota calculations filter usage by tenant.

Subscription records are also associated with their tenant.

This prevents usage totals from being calculated across unrelated tenants during normal API operations.

---

## 11. Secrets and configuration

Secrets are loaded from environment variables rather than hard-coded in the application.

The project uses:

```text
DATABASE_URL
STRIPE_SECRET_KEY
STRIPE_WEBHOOK_SECRET
```

`.env` is excluded from Git.

`.env.example` contains safe placeholder values and does not contain real Stripe credentials.

---

## 12. Repository and setup

The repository contains:

```text
README.md
BUILDLOG.md
EVIDENCE.md
design.md
capstone.yaml
billing-engine/
```

The README documents:

* System purpose
* Architecture
* Project structure
* Environment setup
* Database migration commands
* Seed command
* Application startup
* Stripe webhook testing
* API endpoints
* Known limitations

The project is designed to be run from a clean checkout using the documented setup instructions.
