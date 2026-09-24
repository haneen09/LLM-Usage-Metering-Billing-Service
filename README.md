# LLM Usage Metering & Billing Service

A FastAPI backend service that tracks customer usage, calculates billable cost, enforces monthly quotas, and synchronizes subscription state with Stripe in test mode.

## Features

* Idempotent usage metering using `Idempotency-Key`
* Database-level protection against duplicate usage events
* Monthly API-call quotas
* Monthly AI-token quotas
* Exact quota boundary enforcement
* Integer-cent cost calculation
* Separate pricing for normal input, cached input, output, and reasoning tokens
* Stripe Checkout in test mode
* Stripe webhook signature verification
* Stripe webhook event deduplication
* Subscription lifecycle synchronization
* Background usage reconciliation with retries and failure logging
* SQLite persistence for local development
* Alembic database migrations
* Tenant-scoped usage and subscription data

---

## Architecture

```text
                         +------------------+
                         |      Client      |
                         +--------+---------+
                                  |
                                  v
                         +------------------+
                         |     FastAPI      |
                         +--------+---------+
                                  |
              +-------------------+-------------------+
              |                   |                   |
              v                   v                   v
         /generate             /usage             /checkout
              |                                       |
              v                                       v
       Quota / Metering                         Stripe Checkout
              |
              v
       Pricing Calculation
              |
              v
          SQLAlchemy
              |
              v
           SQLite
              ^
              |
       Stripe Webhooks
              |
              v
     Signature Verification
              |
              v
     Event Deduplication
              |
              v
     Subscription Update

Successful /generate requests
              |
              v
    Background Reconciliation
```

The application is organized into:

* **Routers** for HTTP/API handling
* **Services** for metering, quota enforcement, and background processing
* **Pricing logic** for deterministic integer-cent cost calculation
* **SQLAlchemy models** for persistence
* **Alembic** for database schema migrations

---

## Project Structure

```text
LLM-Usage-Metering-Billing-Service/
│
├── README.md
├── design.md
├── EVIDENCE.md
├── BUILDLOG.md
├── capstone.yaml
├── .gitignore
│
└── billing-engine/
    ├── .env.example
    ├── requirements.txt
    ├── seed.py
    ├── alembic.ini
    │
    ├── alembic/
    │   ├── env.py
    │   └── versions/
    │       └── c5b9fc6cf021_create_billing_schema.py
    │
    └── app/
        ├── main.py
        ├── database.py
        ├── models.py
        ├── pricing.py
        ├── schemas.py
        │
        ├── routers/
        │   ├── generate.py
        │   ├── usage.py
        │   ├── checkout.py
        │   └── webhooks.py
        │
        └── services/
            ├── meter.py
            ├── quota.py
            └── background.py
```

---

## Plans

The seeded plans are:

| Plan | API calls / month | AI tokens / month |       Price |
| ---- | ----------------: | ----------------: | ----------: |
| Free |             1,000 |           100,000 |     0 cents |
| Pro  |            10,000 |         1,000,000 | 2,900 cents |

The Pro plan therefore costs **$29.00** in Stripe test-mode configuration.

---

## Usage Metering

The main billable endpoint is:

```text
POST /generate
```

Every billable request requires an `Idempotency-Key` header.

Example:

```text
Idempotency-Key: my-unique-request-id
```

The key is stored with each usage event and has a database-level unique constraint.

If the same request is submitted again with the same key, the service returns the original usage result instead of recording another event.

This prevents double-counting when clients retry requests.

---

## API Call Usage

An API-call request has the following structure:

```json
{
  "tenant_id": "demo-tenant-1",
  "type": "api_call",
  "quantity": 1
}
```

The API-call price is:

```text
1 cent per API call
```

Token fields must be zero for an `api_call` request.

---

## AI Token Usage

AI-token requests support four token categories:

* Normal input tokens
* Cached input tokens
* Output tokens
* Reasoning tokens

Example:

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

For AI-token usage, `quantity` is not provided.

The service calculates the billable token quantity as:

```text
input_tokens + output_tokens + reasoning_tokens
```

Cached input is a subset of input tokens and is therefore **not added again** to the usage quantity.

---

## Pricing

All monetary values are represented as integer cents. Floating-point money calculations are not used.

The current pinned pricing constants are:

| Usage        |                  Price |
| ------------ | ---------------------: |
| API call     |          1 cent / call |
| Normal input | 3 cents / 1,000 tokens |
| Cached input |  1 cent / 1,000 tokens |
| Output       | 6 cents / 1,000 tokens |
| Reasoning    | 6 cents / 1,000 tokens |

The calculation is:

```text
normal_input_tokens = input_tokens - cached_input_tokens

billable_output_tokens =
    output_tokens + reasoning_tokens
```

Then:

```text
total =
    normal_input_tokens × input_price
    + cached_input_tokens × cached_input_price
    + billable_output_tokens × output_price
```

The result is converted to integer cents.

### Example

For:

```text
input tokens:          1,000
cached input tokens:     200
output tokens:           500
reasoning tokens:        300
```

The calculation is:

```text
Normal input:
(1000 - 200) × 3 / 1000 = 2.4 cents

Cached input:
200 × 1 / 1000 = 0.2 cents

Output:
500 × 6 / 1000 = 3.0 cents

Reasoning:
300 × 6 / 1000 = 1.8 cents

Total:
7.4 cents
```

The service stores the resulting amount as integer cents.

---

## Quota Enforcement

Usage limits are calculated for the current UTC calendar month.

For each request, the service checks:

```text
current_usage + requested_usage <= monthly_limit
```

Therefore, the exact quota boundary is allowed.

For example, if a tenant has:

```text
999 / 1000 API calls used
```

a request for one additional API call is allowed.

The next request is rejected because it would exceed the limit.

### Responses

If the subscription is inactive:

```text
402 Payment Required
```

If the monthly quota would be exceeded:

```text
429 Too Many Requests
```

Invalid request data returns an appropriate `4xx` response.

---

## Idempotency

The `usage_events` table contains a unique constraint on:

```text
idempotency_key
```

The request flow is:

```text
POST /generate
       |
       v
Check Idempotency-Key
       |
       +---- existing event ----> return original result
       |
       +---- new request -------> quota check
                                      |
                                      v
                                calculate cost
                                      |
                                      v
                                record usage
                                      |
                                      v
                                  return result
```

The database uniqueness constraint also protects against duplicate records caused by concurrent requests.

---

## Usage Endpoint

The current usage summary can be retrieved with:

```text
GET /usage?tenant_id=demo-tenant-1
```

Example response:

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

The response includes:

* Current plan
* API calls used
* API call limit
* AI tokens used
* AI token limit
* Total recorded cost for the current month

---

## Stripe Integration

Stripe is used in **test mode**.

The application provides:

```text
POST /checkout?tenant_id=<tenant-id>
```

The checkout endpoint creates a Stripe Checkout Session for a subscription.

The application handles these Stripe webhook events:

```text
checkout.session.completed
customer.subscription.updated
customer.subscription.deleted
```

### Webhook processing

The webhook flow is:

```text
Stripe Event
     |
     v
Verify Stripe Signature
     |
     +---- invalid ----> 400
     |
     v
Check Event ID
     |
     +---- already processed ----> ignore duplicate
     |
     v
Process Event
     |
     v
Update Subscription
```

Stripe event IDs are stored in the `processed_stripe_events` table so that the same event is not processed multiple times.

The local database mirrors subscription state from verified Stripe events.

---

## Background Processing

After a successful usage request, a background reconciliation task is scheduled.

The task:

* runs outside the main request processing path
* creates its own database session
* checks the tenant's stored usage events
* retries failed reconciliation attempts
* logs an alert if all retry attempts fail

The implementation is located at:

```text
billing-engine/app/services/background.py
```

The background task is intentionally lightweight for this capstone. A production system could replace it with a distributed job queue and worker system.

---

## Database

SQLite is used for local development:

```text
sqlite:///./billing.db
```

The database layer is implemented using SQLAlchemy.

The main database entities are:

### `tenants`

Stores customer/tenant information.

### `plans`

Stores plan limits and pricing.

### `subscriptions`

Stores the tenant's current subscription and Stripe identifiers.

### `usage_events`

Stores individual billable usage events and their calculated cost.

### `processed_stripe_events`

Stores processed Stripe event IDs for webhook deduplication.

---

## Database Migrations

Alembic is used for database schema migrations.

The initial migration is:

```text
c5b9fc6cf021_create_billing_schema.py
```

The existing development database already matched the SQLAlchemy models when Alembic was introduced, so it was stamped at the initial migration as the existing schema baseline.

For a clean database, migrations can be applied with:

```powershell
cd billing-engine
python -m alembic upgrade head
```

The application does not rely on `Base.metadata.create_all()` at startup. Alembic is the source of truth for schema creation and future schema changes.

---

## Setup

### Requirements

* Python 3.10+
* Stripe test-mode account/credentials
* PowerShell or another terminal
* Git

### 1. Clone the repository

```powershell
git clone <repository-url>
cd LLM-Usage-Metering-Billing-Service
```

### 2. Create a virtual environment

From the repository root:

```powershell
cd billing-engine
python -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file inside `billing-engine` based on `.env.example`.

The file should contain:

```text
DATABASE_URL=sqlite:///./billing.db
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
```

Only use Stripe test-mode credentials.

**Never commit `.env` or real Stripe credentials.**

### 5. Create the database schema

For a clean database:

```powershell
python -m alembic upgrade head
```

### 6. Seed demo data

```powershell
python seed.py
```

The seed script creates the Free and Pro plans and the demo tenants used for testing.

### 7. Start the API

```powershell
python -m uvicorn app.main:app --reload
```

The API will be available at:

```text
http://127.0.0.1:8000
```

Swagger documentation:

```text
http://127.0.0.1:8000/docs
```

---

## Running the Stripe Webhook Locally

With the API running, the Stripe CLI can forward test webhook events to:

```text
http://localhost:8000/webhooks/stripe
```

The webhook signing secret must be stored in `.env`:

```text
STRIPE_WEBHOOK_SECRET=whsec_...
```

Do not commit the actual signing secret.

---

## API Endpoints

| Method | Endpoint              | Purpose                          |
| ------ | --------------------- | -------------------------------- |
| `GET`  | `/`                   | Service health/basic information |
| `POST` | `/generate`           | Record billable usage            |
| `GET`  | `/usage`              | Retrieve monthly usage and cost  |
| `POST` | `/checkout`           | Create Stripe Checkout Session   |
| `POST` | `/webhooks/stripe`    | Process verified Stripe events   |
| `GET`  | `/checkout-success`   | Checkout success response        |
| `GET`  | `/checkout-cancelled` | Checkout cancellation response   |

---

## Testing

The implementation was tested locally using the FastAPI Swagger interface, direct API requests, SQLite persistence, and Stripe test mode.

The acceptance evidence is documented in:

```text
EVIDENCE.md
```

The evidence covers:

* Idempotent metering
* Quota boundary enforcement
* AI token pricing
* Stripe Checkout and subscription upgrade
* Stripe webhook verification and deduplication
* Background processing
* Database migrations
* Request validation
* Tenant-scoped persistence

---

## Security and Secrets

Sensitive configuration is provided through environment variables.

The following values must never be committed:

```text
STRIPE_SECRET_KEY
STRIPE_WEBHOOK_SECRET
.env
```

The repository contains `.env.example` with placeholders only.

Webhook requests are verified using Stripe's signing mechanism before event processing.

---

## Limitations

This project is a capstone implementation and is intentionally limited in scope.

It does not implement:

* Invoicing
* Proration
* Overage billing
* Production payment processing
* A distributed production job queue
* Production-grade horizontal scaling
* Advanced authentication/authorization

SQLite is used for local development. A production deployment would use a production database such as PostgreSQL and a dedicated background worker system.

---

## Submission Files

| File            | Purpose                                   |
| --------------- | ----------------------------------------- |
| `README.md`     | Setup, architecture, API, and limitations |
| `design.md`     | Detailed system design                    |
| `EVIDENCE.md`   | Acceptance-test evidence                  |
| `BUILDLOG.md`   | AI-assisted development log               |
| `capstone.yaml` | Run, seed, and endpoint configuration     |
| `.env.example`  | Safe environment-variable template        |

---

## Project Status

The core usage metering, quota enforcement, integer-based pricing, Stripe test-mode integration, background processing, and database migration setup have been implemented and verified locally.
