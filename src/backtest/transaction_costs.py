from __future__ import annotations


def proportional_cost(
    option_premium: float,
    spot: float,
    coverage_ratio: float,
    config: dict,
    bid_ask_spread_pct: float | None = None,
) -> float:
    option_slippage = config.get("option_slippage_bps", 0) / 10_000 * coverage_ratio * option_premium / spot
    etf_slippage = 0.0
    if config.get("charge_etf_slippage_on_roll", False):
        etf_slippage = config.get("etf_slippage_bps", 0) / 10_000
    commission = config.get("option_commission_per_contract", 0) / spot * coverage_ratio
    spread_cost = 0.0
    if config.get("use_bid_ask_spread_cost", False) and bid_ask_spread_pct is not None:
        if bid_ask_spread_pct == bid_ask_spread_pct and bid_ask_spread_pct > 0:
            spread_cost = 0.5 * bid_ask_spread_pct * coverage_ratio * option_premium / spot
    return float(option_slippage + etf_slippage + commission + spread_cost)
