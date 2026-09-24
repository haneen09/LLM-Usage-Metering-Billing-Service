"""
Pinned pricing constants and integer-based cost calculation.

All prices are stored as integer cents per 1,000 tokens.
Cached input tokens are cheaper than normal input tokens.
Reasoning tokens are charged at the output-token rate.
"""

CENTS_PER_API_CALL = 1

# AI token pricing, cents per 1,000 tokens
CENTS_PER_1K_INPUT_TOKENS = 3
CENTS_PER_1K_CACHED_INPUT_TOKENS = 1
CENTS_PER_1K_OUTPUT_TOKENS = 6


def calculate_token_cost_cents(
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    reasoning_tokens: int,
) -> int:
    """
    Calculate AI cost using the pinned pricing rules.

    Cached input tokens are part of the input total, so they are NOT
    charged again at the normal input rate.

    Reasoning tokens are charged as output tokens.

    Integer arithmetic is used throughout.
    """
    if min(
        input_tokens,
        cached_input_tokens,
        output_tokens,
        reasoning_tokens,
    ) < 0:
        raise ValueError("Token counts cannot be negative.")

    if cached_input_tokens > input_tokens:
        raise ValueError("Cached input tokens cannot exceed input tokens.")

    normal_input_tokens = input_tokens - cached_input_tokens
    billable_output_tokens = output_tokens + reasoning_tokens

    total_token_cost_units = (
        normal_input_tokens * CENTS_PER_1K_INPUT_TOKENS
        + cached_input_tokens * CENTS_PER_1K_CACHED_INPUT_TOKENS
        + billable_output_tokens * CENTS_PER_1K_OUTPUT_TOKENS
    )

    # Convert cents-per-1,000-token units to cents.
    # Round half up using integer arithmetic.
    return (total_token_cost_units + 500) // 1000


def calculate_cost_cents(usage_type: str, quantity: int) -> int:
    """
    Backwards-compatible cost calculation for simple API-call usage.
    AI-token requests should use calculate_token_cost_cents().
    """
    if usage_type == "api_call":
        return quantity * CENTS_PER_API_CALL
    else:
        raise ValueError(
            "AI token usage requires detailed token categories."
        )
