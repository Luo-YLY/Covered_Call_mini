from __future__ import annotations

import numpy as np


def covered_call_period_return(
    spot_start: float,
    spot_end: float,
    strike: float | None,
    premium: float,
    coverage_ratio: float,
    transaction_cost: float,
    option_settlement_spot: float | None = None,
) -> dict[str, float | int]:
    r_etf = (spot_end - spot_start) / spot_start
    if strike is None or coverage_ratio == 0:
        upside_cost = 0.0
        assignment_flag = 0
    else:
        payoff_spot = spot_end if option_settlement_spot is None else option_settlement_spot
        upside_cost = coverage_ratio * max(payoff_spot - strike, 0.0) / spot_start
        assignment_flag = int(payoff_spot > strike)
    premium_yield = coverage_ratio * premium / spot_start
    r_cc = r_etf + premium_yield - upside_cost - transaction_cost
    excess_return = r_cc - r_etf
    return {
        "R_etf": float(r_etf),
        "premium_yield": float(premium_yield),
        "upside_cost": float(upside_cost),
        "cost": float(transaction_cost),
        "R_cc": float(r_cc),
        "excess_return": float(excess_return),
        "assignment_flag": assignment_flag,
        "premium_contribution": float(premium_yield),
        "upside_cost_contribution": float(-upside_cost),
        "transaction_cost_contribution": float(-transaction_cost),
        "net_option_contribution": float(premium_yield - upside_cost - transaction_cost),
    }


def assert_accounting_identity(row: dict, tolerance: float = 1e-10) -> None:
    lhs = row["R_cc"]
    rhs = row["R_etf"] + row["premium_yield"] - row["upside_cost"] - row["cost"]
    if not np.isclose(lhs, rhs, atol=tolerance):
        raise AssertionError(f"Covered call accounting identity failed: {lhs} != {rhs}")
