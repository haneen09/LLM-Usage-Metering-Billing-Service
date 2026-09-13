"""
Pricing constants and cost calculation.

NOTE: This is the Stage 2 version — just enough to support quota
enforcement. The real AI-token pricing rules (cached input tokens,
reasoning tokens counting as output, categories not simply additive)
get built out in Stage 4. For now, ai_tokens uses one flat rate so
/generate can return a cost figure while we build the core logic.
"""

# Pinned pricing constants — cents per unit
CENTS_PER_API_CALL = 1          # 1 cent per API call
CENTS_PER_1K_TOKENS = 2         # placeholder flat rate, refined in Stage 4


def calculate_cost_cents(usage_type: str, quantity: int) -> int:
    if usage_type == "api_call":
        return quantity * CENTS_PER_API_CALL
    elif usage_type == "ai_tokens":
        return round((quantity / 1000) * CENTS_PER_1K_TOKENS)
    else:
        raise ValueError(f"Unknown usage type: {usage_type}")
