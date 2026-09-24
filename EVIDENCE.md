## Requirement: Idempotent metering (no double-counting on retry)

Sent the same request twice with Idempotency-Key: test-key-1

Request 1: { recorded: True, cost_cents: 1, usage_this_month: 1 }
Request 2: { recorded: True, cost_cents: 1, usage_this_month: 1 }

GET /usage?tenant_id=demo-tenant-1 confirms only 1 event was recorded:
{ api_calls_used: 1, api_calls_limit: 1000, ... }

## Requirement: Quota boundary enforcement (429/402)

Tenant seeded at 999/1000 api_calls.

Call #1000 (at the boundary): 200 OK
{ recorded: True, cost_cents: 1, usage_this_month: 1000 }

Call #1001 (over the limit): 429 Too Many Requests
{"detail":"Usage quota exceeded for api_call: 1000 used, limit is 1000 this month."}