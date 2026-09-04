from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / "ver4" / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from covered_call_mini_ver4.config import build_cycle_experiment_config  # noqa: E402
from covered_call_mini_ver4.engine_adapter import strategy_metadata  # noqa: E402
from covered_call_mini_ver4.ledger import (  # noqa: E402
    attach_cycle_market_context,
    build_cycle_daily_mtm_ledger,
    build_cycle_ledger,
)
from covered_call_mini_ver4.metrics import (  # noqa: E402
    attach_rolling_cashflow_summary,
    build_cycle_cashflow_summary,
    build_rolling_cycle_cashflow,
)
from covered_call_mini_ver4.regime import build_cycle_regime_attribution  # noqa: E402
from covered_call_mini_ver4.validation import build_validation_summary  # noqa: E402


def main() -> None:
    config = build_cycle_experiment_config(ROOT, etf_code="510300")
    meta = strategy_metadata(config)
    periods = pd.DataFrame(
        [
            {
                "etf_code": "510300", "strategy_name": "BuyHold", "period_index": 1,
                "rebalance_date": "2024-01-02", "period_end_date": "2024-01-31",
                "option_selected_flag": 0, "assignment_flag": False, "etf_period_return": 0.03,
                "premium_return": 0.0, "upside_payoff_return": 0.0, "transaction_cost_return": 0.0,
            },
            {
                "etf_code": "510300", "strategy_name": "D30_Q100", "period_index": 1,
                "rebalance_date": "2024-01-02", "period_end_date": "2024-01-31",
                "option_selected_flag": 1, "assignment_flag": False, "etf_period_return": 0.03,
                "premium_return": 0.012, "upside_payoff_return": 0.004, "transaction_cost_return": 0.001,
                "option_code": "TEST.C", "selected_iv": 0.25, "underlying_price_at_entry": 100.0,
            },
            {
                "etf_code": "510300", "strategy_name": "D30_Q100", "period_index": 2,
                "rebalance_date": "2024-02-01", "period_end_date": "2024-02-28",
                "option_selected_flag": 1, "assignment_flag": True, "etf_period_return": 0.05,
                "premium_return": 0.04, "upside_payoff_return": 0.05, "transaction_cost_return": 0.0,
                "option_code": "TEST2.C", "selected_iv": 0.25, "underlying_price_at_entry": 100.0,
            },
        ]
    )
    ledger = build_cycle_ledger(periods, meta, config)
    covered = ledger[ledger["strategy_name"].eq("D30_Q100")].iloc[0]
    assert abs(float(covered["net_option_yield"]) - 0.007) < 1e-12
    assert abs(float(covered["covered_call_period_return"]) - 0.037) < 1e-12
    assert abs(float(covered["strategy_net_return"]) - 0.037) < 1e-12
    assert abs(float(covered["net_option_pnl_cash"]) - 0.7) < 1e-12
    assert abs(float(covered["strategy_net_pnl_cash"]) - 3.7) < 1e-12
    assert abs(float(covered["relative_to_buyhold_pnl_cash"]) - 0.7) < 1e-12

    assigned = ledger[(ledger["strategy_name"].eq("D30_Q100")) & (ledger["period_index"].eq(2))].iloc[0]
    assert abs(float(assigned["net_option_yield"]) + 0.01) < 1e-12
    assert abs(float(assigned["strategy_net_return"]) - 0.04) < 1e-12

    dates = pd.bdate_range("2023-12-01", "2024-01-31")
    prices = pd.DataFrame(
        {
            "date": dates,
            "etf_code": "510300",
            "adj_close": [100.0 + index * index * 0.01 for index in range(len(dates))],
            "high": [101.0 + index * index * 0.01 for index in range(len(dates))],
            "low": [99.0 + index * index * 0.01 for index in range(len(dates))],
        }
    )
    options = pd.DataFrame(
        [
            {"trade_date": "2024-01-02", "option_code": "TEST.C", "model_iv": 0.25, "days_to_expiry": 29},
            {"trade_date": "2024-01-30", "option_code": "TEST.C", "model_iv": 0.31, "days_to_expiry": 1},
        ]
    )
    enriched = attach_cycle_market_context(ledger, etf_prices=prices, option_chain=options)
    enriched_covered = enriched[enriched["strategy_name"].eq("D30_Q100")].iloc[0]
    assert abs(float(enriched_covered["entry_iv"]) - 0.25) < 1e-12
    assert abs(float(enriched_covered["pre_settlement_iv"]) - 0.31) < 1e-12
    assert pd.notna(enriched_covered["entry_rv20"])
    assert pd.notna(enriched_covered["holding_realized_vol"])
    expected_vrp = float(enriched_covered["entry_iv"]) ** 2 - float(enriched_covered["holding_realized_vol"]) ** 2
    assert abs(float(enriched_covered["ex_post_variance_risk_premium"]) - expected_vrp) < 1e-12
    assert float(enriched_covered["holding_max_upside_return"]) > 0.0
    assert pd.notna(enriched_covered["holding_max_drawdown_return"])
    assert float(enriched_covered["holding_range_return"]) > 0.0

    daily = pd.DataFrame(
        [{"etf_code": "510300", "strategy_name": "D30_Q100", "period_index": 1, "date": "2024-01-15", "rebalance_date": "2024-01-02", "period_end_date": "2024-01-31", "period_mtm_return": 0.015}]
    )
    daily_ledger = build_cycle_daily_mtm_ledger(daily, meta, config)
    assert abs(float(daily_ledger["cycle_mtm_pnl_cash"].iloc[0]) - 1.5) < 1e-12

    summary = build_cycle_cashflow_summary(ledger, config)
    rolling = build_rolling_cycle_cashflow(ledger, config)
    summary = attach_rolling_cashflow_summary(summary, rolling, config)
    regime = build_cycle_regime_attribution(ledger, config)
    validation = build_validation_summary(ledger, daily_ledger, summary, rolling, regime, config)
    assert validation.loc[validation["check_name"].eq("net_option_cash_identity"), "passed"].iloc[0]
    assert validation.loc[validation["check_name"].eq("no_compounded_nav_column"), "passed"].iloc[0]
    print("ver4.0 cycle-ledger smoke test passed.")


if __name__ == "__main__":
    main()
