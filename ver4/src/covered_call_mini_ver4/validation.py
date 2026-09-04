from __future__ import annotations

import numpy as np
import pandas as pd

from .config import CycleExperimentConfig
from .engine_adapter import static_strategy_count


def _row(name: str, passed: bool, detail: str) -> dict[str, object]:
    return {"check_name": name, "passed": bool(passed), "detail": detail}


def build_validation_summary(
    ledger: pd.DataFrame,
    daily_mtm: pd.DataFrame,
    summary: pd.DataFrame,
    rolling: pd.DataFrame,
    regime: pd.DataFrame,
    config: CycleExperimentConfig,
) -> pd.DataFrame:
    """Validate the ver4.0 fixed-notional accounting contract."""

    if ledger.empty:
        return pd.DataFrame([_row("cycle_ledger_nonempty", False, "No cycle rows were produced.")])
    net_rebuilt = ledger["gross_premium_yield"] - ledger["exercise_or_close_cost_yield"] - ledger["transaction_cost_yield"]
    covered_rebuilt = ledger["etf_period_return"] + ledger["net_option_yield"]
    relative_rebuilt = ledger["covered_call_period_return"] - ledger["etf_period_return"]
    expected_grid_rows = static_strategy_count(config)
    strategy_count = ledger["strategy_name"].nunique()
    rows = [
        _row("cycle_ledger_nonempty", not ledger.empty, f"rows={len(ledger)}"),
        _row("single_etf_only", ledger["etf_code"].nunique() == 1 and ledger["etf_code"].iloc[0] == config.etf.etf_code, f"etfs={ledger['etf_code'].unique().tolist()}"),
        _row("static_grid_strategy_count", strategy_count == expected_grid_rows, f"expected={expected_grid_rows}; actual={strategy_count}"),
        _row("fixed_notional_constant", bool(np.isclose(ledger["fixed_notional"].astype(float), config.fixed_notional).all()), f"notional={config.fixed_notional}"),
        _row("net_option_cash_identity", bool(np.isclose(ledger["net_option_yield"], net_rebuilt, atol=1e-12).all()), "premium - exercise_or_close_cost - transaction_cost"),
        _row("covered_call_return_identity", bool(np.isclose(ledger["covered_call_period_return"], covered_rebuilt, atol=1e-12).all()), "ETF return + net option yield"),
        _row("relative_buyhold_identity", bool(np.isclose(ledger["relative_to_buyhold_return"], relative_rebuilt, atol=1e-12).all()), "covered-call return - ETF return"),
        _row("no_compounded_nav_column", "nav" not in ledger.columns and "cagr" not in "|".join(summary.columns).lower(), "main ledger and summary do not expose compounded NAV/CAGR"),
        _row("daily_mtm_cycle_rebased", daily_mtm.empty or bool(np.isclose(daily_mtm["cycle_mtm_pnl_cash"], daily_mtm["fixed_notional"] * daily_mtm["period_mtm_return"], atol=1e-12).all()), "daily MTM is rebased within a cycle"),
        _row("summary_nonempty", not summary.empty, f"rows={len(summary)}"),
        _row("rolling_cashflow_available_or_short_sample", not rolling.empty or ledger["cycle_sequence"].max() < config.rolling_cashflow_cycles, f"window={config.rolling_cashflow_cycles}; rows={len(rolling)}"),
        _row("regime_attribution_nonempty", not regime.empty, f"rows={len(regime)}"),
    ]
    return pd.DataFrame(rows)
