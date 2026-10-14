"""Estimated USD cost from token counts and the configured price table."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ModelPrice:
    name: str
    input_price_per_million: float
    output_price_per_million: float


def estimate_cost_usd(
    price: ModelPrice, input_tokens: int, output_tokens: int
) -> float:
    cost = (
        Decimal(input_tokens) * Decimal(str(price.input_price_per_million))
        + Decimal(output_tokens) * Decimal(str(price.output_price_per_million))
    ) / Decimal(1_000_000)
    return float(cost.quantize(Decimal("0.00000001")))
