from pydantic import BaseModel, Field
from typing import Literal


class GenerateRequest(BaseModel):
    tenant_id: str
    type: Literal["api_call", "ai_tokens"]

    # Used for api_call requests.
    quantity: int | None = Field(default=None, ge=1)

    # Used for ai_tokens requests.
    input_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)


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
