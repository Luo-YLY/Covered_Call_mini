from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class TransactionCostBreakdown:
    total_cost_return: float
    option_slippage_cost_return: float
    etf_slippage_cost_return: float
    option_commission_cost_return: float
    bid_ask_spread_cost_return: float
    effective_bid_ask_spread_pct: float
    bid_ask_spread_source: str


def _valid_spread(value: Any) -> bool:
    try:
        spread = float(value)
    except (TypeError, ValueError):
        return False
    return np.isfinite(spread) and spread > 0


def resolve_bid_ask_spread_pct(
    raw_bid_ask_spread_pct: Any,
    transaction_costs: dict[str, Any],
) -> tuple[float, str]:
    """Resolve the bid/ask spread used for cost accounting.

    Market spread wins when present. When it is missing, ver2 can inject an
    assumed spread so dashboards can rerun the experiment with adjustable
    execution-cost assumptions.
    """

    if not transaction_costs.get("use_bid_ask_spread_cost", False):
        return np.nan, "disabled"
    if _valid_spread(raw_bid_ask_spread_pct):
        return float(raw_bid_ask_spread_pct), "market"
    if transaction_costs.get("use_assumed_bid_ask_spread_when_missing", False):
        assumed = transaction_costs.get("assumed_bid_ask_spread_pct", np.nan)
        if _valid_spread(assumed):
            return float(assumed), "assumed"
    return np.nan, "missing"


def calculate_transaction_cost(
    option_premium: float,
    spot: float,
    coverage_ratio: float,
    transaction_costs: dict[str, Any],
    raw_bid_ask_spread_pct: Any = None,
) -> TransactionCostBreakdown:
    """Calculate ver2 transaction cost as a return on ETF entry notional."""

    if spot == 0:
        raise ValueError("spot must be non-zero when calculating transaction costs.")
    if coverage_ratio == 0 or option_premium == 0:
        return TransactionCostBreakdown(
            total_cost_return=0.0,
            option_slippage_cost_return=0.0,
            etf_slippage_cost_return=0.0,
            option_commission_cost_return=0.0,
            bid_ask_spread_cost_return=0.0,
            effective_bid_ask_spread_pct=np.nan,
            bid_ask_spread_source="none",
        )

    premium_yield = coverage_ratio * option_premium / spot
    option_slippage = transaction_costs.get("option_slippage_bps", 0) / 10_000 * premium_yield
    etf_slippage = (
        transaction_costs.get("etf_slippage_bps", 0) / 10_000
        if transaction_costs.get("charge_etf_slippage_on_roll", False)
        else 0.0
    )
    commission = transaction_costs.get("option_commission_per_contract", 0) / spot * coverage_ratio
    effective_spread, spread_source = resolve_bid_ask_spread_pct(raw_bid_ask_spread_pct, transaction_costs)
    spread_cost = 0.0
    if _valid_spread(effective_spread):
        spread_cost = 0.5 * effective_spread * premium_yield

    total = float(option_slippage + etf_slippage + commission + spread_cost)
    return TransactionCostBreakdown(
        total_cost_return=total,
        option_slippage_cost_return=float(option_slippage),
        etf_slippage_cost_return=float(etf_slippage),
        option_commission_cost_return=float(commission),
        bid_ask_spread_cost_return=float(spread_cost),
        effective_bid_ask_spread_pct=float(effective_spread) if _valid_spread(effective_spread) else np.nan,
        bid_ask_spread_source=spread_source,
    )
