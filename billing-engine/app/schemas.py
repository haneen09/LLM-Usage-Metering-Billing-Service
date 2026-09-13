from pydantic import BaseModel
from typing import Literal


class GenerateRequest(BaseModel):
    tenant_id: str
    type: Literal["api_call", "ai_tokens"]
    quantity: int


class GenerateResponse(BaseModel):
    recorded: bool
    cost_cents: int
    usage_this_month: int


class UsageResponse(BaseModel):
    plan: str
    api_calls_used: int
    api_calls_limit: int
    tokens_used: int
    tokens_limit: int
    cost_this_month_cents: int
