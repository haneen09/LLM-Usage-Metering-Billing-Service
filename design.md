# Design Doc — Usage Metering & Billing Engine

## Problem

Every SaaS product needs to answer three questions for each customer:
how much have they used, what should they be charged, and have they
hit their plan's limit? This service answers all three. It meters
billable actions, enforces monthly quotas, calculates cost (including
AI-token pricing rules), and syncs subscription state with Stripe in
test mode.

## Non-goal

This system does **not** handle invoicing, proration, or overage
billing. Those are explicitly out of scope for the core build and are
left as stretch goals if time allows.

## Data Model

**tenants**
| field | type | notes |
|---|---|---|
| id | uuid | primary key |
| name | text | customer/company name |
| email | text | contact email |
| created_at | timestamp | |

**plans**
| field | type | notes |
|---|---|---|
| id | text | "free" or "pro" |
| name | text | "Free", "Pro" |
| api_call_limit | int | 1,000 for free |
| token_limit | int | 100,000 for free |
| price_cents | int | 0 for free, 2900 for pro |

**subscriptions**
| field | type | notes |
|---|---|---|
| id | uuid | primary key |
| tenant_id | uuid | FK -> tenants |
| plan_id | text | FK -> plans |
| stripe_customer_id | text | from Stripe |
| stripe_subscription_id | text | from Stripe |
| status | text | active / canceled / past_due |
| updated_at | timestamp | last webhook update |

**usage_events**
| field | type | notes |
|---|---|---|
| id | uuid | primary key |
| tenant_id | uuid | FK -> tenants |
| type | text | "api_call" or "ai_tokens" |
| quantity | int | count or token amount |
| idempotency_key | text | **UNIQUE constraint** — prevents double-counting |
| created_at | timestamp | |

## Plans

| Plan | API calls / month | AI tokens / month | Price |
|---|---|---|---|
| Free | 1,000 | 100,000 | $0 |
| Pro | 10,000 | 1,000,000 | $29.00 (2900 cents) |

Money is always stored as integer cents, never floats.

## Idempotency Strategy

Every billable request to `POST /generate` must include an
`Idempotency-Key` header (client-generated UUID).

- The `idempotency_key` column on `usage_events` has a UNIQUE
  constraint — this is the actual enforcement mechanism, not just
  application logic.
- On each request: attempt to insert a new `usage_events` row with
  that key.
  - Insert succeeds → new action. Record it, check quota, calculate
    cost, return the result.
  - Insert fails (key already exists) → this is a retry. Do not
    record anything new. Look up the original event and return the
    same response given the first time.
- A request with no `Idempotency-Key` header is rejected with `400`.

## API Surface

### `POST /generate`
The one billable action in the system.

Request:
```
Headers: Idempotency-Key: <uuid>
Body: { "tenant_id": "...", "type": "api_call" | "ai_tokens", "quantity": 1 }
```

Flow: check idempotency key -> check quota -> reject with 429/402 if
over limit -> else record usage_event, calculate cost, respond.

Response:
```json
{ "recorded": true, "cost_cents": 12, "usage_this_month": 451 }
```

### `GET /usage`
Read-only rollup of a tenant's usage this month.

Request: `GET /usage?tenant_id=...`

Response:
```json
{
  "plan": "free",
  "api_calls_used": 451,
  "api_calls_limit": 1000,
  "tokens_used": 32000,
  "tokens_limit": 100000,
  "cost_this_month_cents": 340
}
```

### `POST /webhooks/stripe`
Receives Stripe events. Verifies signature first (bad signature ->
`400`, nothing else happens). Deduplicates by Stripe event ID before
processing. Handles:
- `checkout.session.completed` -> new subscription, update tenant plan
- `customer.subscription.updated` -> update plan/status
- `customer.subscription.deleted` -> tenant drops back to Free

## Architecture Sketch

```
Client --> POST /generate
             |
             v
      MeterService.record(tenant, type, qty, idempotencyKey)
             |
     duplicate key? --yes--> return original result
             |no
             v
      store usage_event
             |
             v
      Quota Check --allowed--> calculate cost --> respond
             |
        exceeded --> 402 / 429 + message

GET /usage --> rollup(usage_events) --> { used, limit, cost }

Stripe Checkout (test mode) --> subscription created
Stripe --signed webhook--> /webhooks/stripe
     verify signature (bad --> 400)
     dedupe event (replay --> ignored)
     update tenant plan / status
```