"""USD per 1M tokens. One table; a model missing here gets cost NULL, never 0.

Source: https://developers.openai.com/api/docs/models/gpt-5.4-mini and
https://azure.microsoft.com/pricing/details/azure-openai/ (checked 2026-11-21). Azure's page did
not render its rates that day; Global Standard is assumed to match OpenAI's list price.
"""

PRICES_PER_1M: dict[str, dict[str, float]] = {
    "gpt-5.4-mini": {"input": 0.75, "output": 4.50},
    "text-embedding-3-small": {"input": 0.02, "output": 0.0},
}


def cost_usd(model: str, prompt_tokens: int, completion_tokens: int = 0) -> float | None:
    # the API reports dated names such as gpt-5.4-mini-2026-03-17
    price = next((p for name, p in PRICES_PER_1M.items() if model.startswith(name)), None)
    if price is None:
        return None
    return (prompt_tokens * price["input"] + completion_tokens * price["output"]) / 1_000_000
