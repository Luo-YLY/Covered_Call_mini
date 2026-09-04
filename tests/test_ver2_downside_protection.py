from __future__ import annotations

import math

import numpy as np
import pandas as pd

from src.backtest.accounting import covered_call_period_return
from ver2_downside_protection.config import (
    BacktestConfig,
    ExperimentConfig,
    PathsConfig,
    StrategyConfig,
    with_transaction_cost_overrides,
)
from ver2_downside_protection.cost_model import calculate_transaction_cost
from ver2_downside_protection.data_adapter import Ver2DataBundle
from ver2_downside_protection.metrics import (
    add_period_diagnostics,
    max_drawdown_improvement,
    protection_cost_ratio,
)
from ver2_downside_protection.moneyness_gradient import (
    build_moneyness_correlation,
    build_moneyness_gradient_long,
    build_moneyness_gradient_summary,
    run_moneyness_sanity_checks,
)
from ver2_downside_protection.option_selector import select_ver2_option
from ver2_downside_protection.option_leg_time_carry_510300 import build_option_leg_period_dataset
from ver2_downside_protection.premium_income_defensive import (
    add_premium_decomposition,
    build_defensive_strategy_ranking,
)
from ver2_downside_protection.regime_refinement_510300 import (
    assign_refined_primary_regime,
    build_refined_period_dataset,
    classify_regime_conflict_type,
)
from ver2_downside_protection.sharpe_bridge_510300 import build_sharpe_bridge_tables
from ver2_downside_protection.step1_regime_attribution_510300 import (
    assign_primary_regime,
    run_sanity_checks,
)
from ver2_downside_protection.strategy_engine import run_ver2_backtest
from ver2_downside_protection.ver2_1_dte_regime import (
    DTE_SPECS,
    attach_regime_features,
    build_candidate_shortlist,
    build_effective_coverage_summary,
    build_down_then_rebound_events,
    build_dte_robustness_ranking,
    build_standard_performance_summary,
    classify_skipped_periods,
)
from ver2_downside_protection.ver2_1b_short_tenor import (
    build_actual_dte_distribution,
    build_candidate_ranking,
)


def test_down_otm_call_return_equals_etf_plus_premium() -> None:
    result = covered_call_period_return(
        spot_start=100.0,
        spot_end=95.0,
        strike=105.0,
        premium=2.0,
        coverage_ratio=1.0,
        transaction_cost=0.0,
        option_settlement_spot=95.0,
    )
    assert result["upside_cost"] == 0.0
    assert result["R_cc"] == result["R_etf"] + result["premium_yield"]
    assert math.isclose(result["R_cc"], -0.03)


def test_large_up_move_has_upside_truncation() -> None:
    result = covered_call_period_return(
        spot_start=100.0,
        spot_end=115.0,
        strike=105.0,
        premium=2.0,
        coverage_ratio=1.0,
        transaction_cost=0.0,
        option_settlement_spot=115.0,
    )
    assert math.isclose(result["R_etf"], 0.15)
    assert math.isclose(result["upside_cost"], 0.10)
    assert result["R_cc"] < result["R_etf"]


def test_sharpe_bridge_uses_current_daily_mtm_nav_without_level4() -> None:
    periods = pd.DataFrame(
        [
            {
                "etf_code": "510300",
                "dte_label": "DTE30",
                "strategy_name": "ATM_100",
                "period_index": 1,
                "rebalance_date": "2021-01-01",
                "period_end_date": "2021-01-05",
                "underlying_price_at_entry": 100.0,
                "underlying_price_at_period_end": 102.0,
                "coverage_ratio": 1.0,
                "option_selected_flag": 1,
                "premium_return": 0.02,
                "upside_payoff_return": 0.0,
                "transaction_cost_return": 0.003,
                "etf_period_return": 0.02,
                "strategy_period_return": 0.037,
                "assignment_flag": 0,
                "option_code": "C1",
                "strike": 105.0,
                "actual_dte": 30,
                "selected_delta": 0.5,
            },
            {
                "etf_code": "510300",
                "dte_label": "DTE30",
                "strategy_name": "ATM_100",
                "period_index": 2,
                "rebalance_date": "2021-01-06",
                "period_end_date": "2021-01-10",
                "underlying_price_at_entry": 102.0,
                "underlying_price_at_period_end": 101.0,
                "coverage_ratio": 1.0,
                "option_selected_flag": 1,
                "premium_return": 0.015,
                "upside_payoff_return": 0.0,
                "transaction_cost_return": 0.003,
                "etf_period_return": -0.009804,
                "strategy_period_return": 0.002196,
                "assignment_flag": 0,
                "option_code": "C2",
                "strike": 106.0,
                "actual_dte": 30,
                "selected_delta": 0.5,
            },
        ]
    )
    daily_mtm = pd.DataFrame(
        [
            ("2021-01-01", 1, 0.000, 0.020, 1.000 * (1 - 0.003)),
            ("2021-01-02", 1, 0.010, 0.050, 1.000 * (1 + 0.010 + 0.020 - 0.050 - 0.003)),
            ("2021-01-03", 1, 0.015, 0.060, 1.000 * (1 + 0.015 + 0.020 - 0.060 - 0.003)),
            ("2021-01-04", 1, 0.018, 0.045, 1.000 * (1 + 0.018 + 0.020 - 0.045 - 0.003)),
            ("2021-01-05", 1, 0.020, 0.000, 1.000 * (1 + 0.020 + 0.020 - 0.000 - 0.003)),
            ("2021-01-06", 2, 0.000, 0.015, 1.037 * (1 - 0.003)),
            ("2021-01-07", 2, -0.003, 0.012, 1.037 * (1 - 0.003 + 0.015 - 0.012 - 0.003)),
            ("2021-01-08", 2, -0.006, 0.010, 1.037 * (1 - 0.006 + 0.015 - 0.010 - 0.003)),
            ("2021-01-09", 2, -0.008, 0.006, 1.037 * (1 - 0.008 + 0.015 - 0.006 - 0.003)),
            ("2021-01-10", 2, -0.009804, 0.000, 1.037 * (1 - 0.009804 + 0.015 - 0.000 - 0.003)),
        ],
        columns=["date", "period_index", "underlying_return_since_entry", "option_liability_return", "daily_mtm_nav"],
    )
    daily_mtm["etf_code"] = "510300"
    daily_mtm["dte_label"] = "DTE30"
    daily_mtm["strategy_name"] = "ATM_100"
    daily_mtm["rebalance_date"] = np.where(daily_mtm["period_index"] == 1, "2021-01-01", "2021-01-06")
    daily_mtm["period_end_date"] = np.where(daily_mtm["period_index"] == 1, "2021-01-05", "2021-01-10")
    daily_mtm["premium_return"] = np.where(daily_mtm["period_index"] == 1, 0.02, 0.015)
    daily_mtm["transaction_cost_return"] = 0.003
    daily_mtm["period_mtm_return"] = (
        daily_mtm["underlying_return_since_entry"]
        + daily_mtm["premium_return"]
        - daily_mtm["option_liability_return"]
        - daily_mtm["transaction_cost_return"]
    )

    long, summary = build_sharpe_bridge_tables(periods, daily_mtm, candidates=(("DTE30", "ATM_100"),))

    assert set(long["bridge_level"]) == {
        "period_settlement",
        "daily_step_settlement",
        "daily_etf_only_marking",
        "daily_mtm_nav",
    }
    assert "execution_adjusted_daily_mtm" not in set(long["bridge_level"])
    assert "execution_sharpe_drag" not in summary.columns
    assert "annualized_return_execution_adjusted_daily_mtm" not in summary.columns
    row = summary.iloc[0]
    assert "strict_sharpe_no_rf_daily_mtm_nav" in summary.columns
    assert "strict_sharpe_rf_2pct_daily_mtm_nav" in summary.columns
    assert row["strict_sharpe_rf_2pct_daily_mtm_nav"] < row["strict_sharpe_no_rf_daily_mtm_nav"]
    assert row["option_mtm_sharpe_drag"] > 0
    assert row["annualized_return_daily_mtm_nav"] < row["annualized_return_period_settlement"]


def test_downside_cushion_ratio_only_for_negative_etf_periods() -> None:
    periods = pd.DataFrame(
        {
            "etf_period_return": [-0.05, 0.04],
            "strategy_period_return": [-0.03, 0.02],
        }
    )
    out = add_period_diagnostics(periods)
    assert math.isclose(out.loc[0, "downside_cushion_ratio"], 0.4)
    assert np.isnan(out.loc[1, "downside_cushion_ratio"])


def test_protection_cost_ratio_zero_denominator_returns_nan() -> None:
    assert np.isnan(protection_cost_ratio(0.01, 0.0))


def test_max_drawdown_improvement_positive_when_strategy_mdd_is_smaller() -> None:
    assert math.isclose(max_drawdown_improvement(0.30, 0.25), 0.05)


def test_continuous_rebalances_on_previous_expiry_date(tmp_path) -> None:
    dates = pd.bdate_range("2021-01-29", "2021-03-24")
    prices = pd.DataFrame(
        {
            "date": dates,
            "etf_code": "510300",
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
            "adj_close": 100.0,
            "volume": 1_000_000.0,
            "amount": 100_000_000.0,
        }
    )
    options = pd.DataFrame(
        [
            {
                "trade_date": pd.Timestamp("2021-01-29"),
                "option_code": "OPT_FEB",
                "underlying_etf": "510300",
                "option_type": "C",
                "expiry": pd.Timestamp("2021-02-24"),
                "strike": 100.0,
                "close": 2.0,
                "volume": 100.0,
                "open_interest": 100.0,
            },
            {
                "trade_date": pd.Timestamp("2021-02-24"),
                "option_code": "OPT_FEB",
                "underlying_etf": "510300",
                "option_type": "C",
                "expiry": pd.Timestamp("2021-02-24"),
                "strike": 100.0,
                "close": 3.0,
                "volume": 100.0,
                "open_interest": 100.0,
            },
            {
                "trade_date": pd.Timestamp("2021-02-24"),
                "option_code": "OPT_MAR",
                "underlying_etf": "510300",
                "option_type": "C",
                "expiry": pd.Timestamp("2021-03-24"),
                "strike": 100.0,
                "close": 2.0,
                "volume": 100.0,
                "open_interest": 100.0,
            },
        ]
    )
    config = ExperimentConfig(
        experiment_name="test",
        etf_codes=("510300",),
        paths=PathsConfig(
            etf_prices=tmp_path / "prices.csv",
            options=tmp_path / "options.csv",
            metadata=None,
            output_dir=tmp_path / "outputs",
        ),
        backtest=BacktestConfig(
            start_date=None,
            end_date=None,
            initial_nav=1.0,
            execution_mode="continuous_30d",
            roll_frequency="monthly",
            target_dte=30,
            min_days_to_expiry=20,
            max_days_to_expiry=45,
            min_periods=1,
            require_expiry_within_period=False,
        ),
        strategies=(
            StrategyConfig("BuyHold", "buy_hold", 0.0),
            StrategyConfig("ATM_100", "atm", 1.0),
        ),
        liquidity_filters={"min_option_volume": 0, "min_open_interest": 0, "max_bid_ask_spread_pct": 1.0},
        transaction_costs={"option_slippage_bps": 0, "use_bid_ask_spread_cost": False},
        assumptions={},
    )
    data = Ver2DataBundle(prices=prices, options=options, metadata=pd.DataFrame({"etf_code": ["510300"]}))

    result = run_ver2_backtest(config, data)
    atm = result.periods[result.periods["strategy_name"] == "ATM_100"].sort_values("period_index")

    assert list(pd.to_datetime(atm["rebalance_date"]).dt.strftime("%Y-%m-%d"))[:2] == [
        "2021-01-29",
        "2021-02-24",
    ]
    assert pd.Timestamp(atm.iloc[0]["period_end_date"]) == pd.Timestamp("2021-02-24")


def test_continuous_stops_when_tail_sample_is_shorter_than_target_dte(tmp_path) -> None:
    dates = pd.bdate_range("2021-01-29", "2021-03-10")
    prices = pd.DataFrame(
        {
            "date": dates,
            "etf_code": "510300",
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
            "adj_close": 100.0,
            "volume": 1_000_000.0,
            "amount": 100_000_000.0,
        }
    )
    options = pd.DataFrame(
        [
            {
                "trade_date": pd.Timestamp("2021-01-29"),
                "option_code": "OPT_FEB",
                "underlying_etf": "510300",
                "option_type": "C",
                "expiry": pd.Timestamp("2021-02-24"),
                "strike": 100.0,
                "close": 2.0,
                "volume": 100.0,
                "open_interest": 100.0,
            },
            {
                "trade_date": pd.Timestamp("2021-02-24"),
                "option_code": "OPT_FEB",
                "underlying_etf": "510300",
                "option_type": "C",
                "expiry": pd.Timestamp("2021-02-24"),
                "strike": 100.0,
                "close": 0.0,
                "volume": 100.0,
                "open_interest": 100.0,
            },
        ]
    )
    config = ExperimentConfig(
        experiment_name="test",
        etf_codes=("510300",),
        paths=PathsConfig(
            etf_prices=tmp_path / "prices.csv",
            options=tmp_path / "options.csv",
            metadata=None,
            output_dir=tmp_path / "outputs",
        ),
        backtest=BacktestConfig(
            start_date=None,
            end_date=None,
            initial_nav=1.0,
            execution_mode="continuous_30d",
            roll_frequency="monthly",
            target_dte=30,
            min_days_to_expiry=20,
            max_days_to_expiry=45,
            min_periods=1,
            require_expiry_within_period=False,
        ),
        strategies=(
            StrategyConfig("BuyHold", "buy_hold", 0.0),
            StrategyConfig("ATM_100", "atm", 1.0),
        ),
        liquidity_filters={"min_option_volume": 0, "min_open_interest": 0, "max_bid_ask_spread_pct": 1.0},
        transaction_costs={"option_slippage_bps": 0, "use_bid_ask_spread_cost": False},
        assumptions={},
    )
    data = Ver2DataBundle(prices=prices, options=options, metadata=pd.DataFrame({"etf_code": ["510300"]}))

    result = run_ver2_backtest(config, data)
    atm = result.periods[result.periods["strategy_name"] == "ATM_100"]

    assert len(atm) == 1
    assert result.skipped_periods.empty


def test_daily_mtm_records_short_call_mark_to_market_loss(tmp_path) -> None:
    dates = pd.bdate_range("2021-01-29", "2021-02-24")
    prices = pd.DataFrame(
        {
            "date": dates,
            "etf_code": "510300",
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
            "adj_close": 100.0,
            "volume": 1_000_000.0,
            "amount": 100_000_000.0,
        }
    )
    options = pd.DataFrame(
        [
            {
                "trade_date": pd.Timestamp("2021-01-29"),
                "option_code": "OPT_FEB",
                "underlying_etf": "510300",
                "option_type": "C",
                "expiry": pd.Timestamp("2021-02-24"),
                "strike": 100.0,
                "close": 2.0,
                "volume": 100.0,
                "open_interest": 100.0,
            },
            {
                "trade_date": pd.Timestamp("2021-02-01"),
                "option_code": "OPT_FEB",
                "underlying_etf": "510300",
                "option_type": "C",
                "expiry": pd.Timestamp("2021-02-24"),
                "strike": 100.0,
                "close": 3.0,
                "volume": 100.0,
                "open_interest": 100.0,
            },
        ]
    )
    config = ExperimentConfig(
        experiment_name="test",
        etf_codes=("510300",),
        paths=PathsConfig(
            etf_prices=tmp_path / "prices.csv",
            options=tmp_path / "options.csv",
            metadata=None,
            output_dir=tmp_path / "outputs",
        ),
        backtest=BacktestConfig(
            start_date=None,
            end_date=None,
            initial_nav=1.0,
            execution_mode="continuous_30d",
            roll_frequency="monthly",
            target_dte=30,
            min_days_to_expiry=20,
            max_days_to_expiry=45,
            min_periods=1,
            require_expiry_within_period=False,
        ),
        strategies=(
            StrategyConfig("BuyHold", "buy_hold", 0.0),
            StrategyConfig("ATM_100", "atm", 1.0),
        ),
        liquidity_filters={"min_option_volume": 0, "min_open_interest": 0, "max_bid_ask_spread_pct": 1.0},
        transaction_costs={"option_slippage_bps": 0, "use_bid_ask_spread_cost": False},
        assumptions={},
    )
    data = Ver2DataBundle(prices=prices, options=options, metadata=pd.DataFrame({"etf_code": ["510300"]}))

    result = run_ver2_backtest(config, data)
    row = result.daily_mtm[
        (result.daily_mtm["strategy_name"] == "ATM_100")
        & (pd.to_datetime(result.daily_mtm["date"]) == pd.Timestamp("2021-02-01"))
    ].iloc[0]

    assert math.isclose(row["option_mark_price"], 3.0)
    assert math.isclose(row["short_call_mtm_loss_return"], 0.01)


def test_itm_pct_selector_targets_below_spot_strike() -> None:
    options = pd.DataFrame(
        [
            {
                "trade_date": pd.Timestamp("2021-01-29"),
                "option_code": "C95",
                "underlying_etf": "510300",
                "option_type": "C",
                "expiry": pd.Timestamp("2021-02-24"),
                "strike": 95.0,
                "close": 7.0,
                "volume": 100.0,
                "open_interest": 100.0,
            },
            {
                "trade_date": pd.Timestamp("2021-01-29"),
                "option_code": "C98",
                "underlying_etf": "510300",
                "option_type": "C",
                "expiry": pd.Timestamp("2021-02-24"),
                "strike": 98.0,
                "close": 4.0,
                "volume": 100.0,
                "open_interest": 100.0,
            },
        ]
    )
    backtest = BacktestConfig(
        start_date=None,
        end_date=None,
        initial_nav=1.0,
        execution_mode="continuous_30d",
        roll_frequency="monthly",
        target_dte=30,
        min_days_to_expiry=20,
        max_days_to_expiry=45,
        min_periods=1,
        require_expiry_within_period=False,
    )

    result = select_ver2_option(
        options=options,
        trade_date=pd.Timestamp("2021-01-29"),
        etf_code="510300",
        spot=100.0,
        period_end=pd.Timestamp("2021-03-31"),
        strategy=StrategyConfig("ITM5_100", "itm_pct", 1.0, -0.05),
        backtest=backtest,
        liquidity_filters={"min_option_volume": 0, "min_open_interest": 0, "max_bid_ask_spread_pct": 1.0},
    )

    assert result.selected
    assert result.option is not None
    assert result.option["option_code"] == "C95"


def test_premium_decomposition_splits_itm_intrinsic_and_extrinsic() -> None:
    periods = pd.DataFrame(
        {
            "option_selected_flag": [1],
            "underlying_price_at_entry": [100.0],
            "strike": [95.0],
            "coverage_ratio": [1.0],
            "option_price_at_entry": [7.0],
            "option_payoff_return_at_expiry": [0.03],
        }
    )

    out = add_premium_decomposition(periods).iloc[0]

    assert math.isclose(out["total_premium"], 7.0)
    assert math.isclose(out["intrinsic_value_at_entry"], 5.0)
    assert math.isclose(out["extrinsic_value_at_entry"], 2.0)
    assert math.isclose(out["total_premium_yield"], 0.07)
    assert math.isclose(out["intrinsic_premium_yield"], 0.05)
    assert math.isclose(out["extrinsic_premium_yield"], 0.02)
    assert math.isclose(out["premium_capture_period"], (0.07 - 0.03) / 0.07)


def test_defensive_ranking_uses_requested_primary_score_formula() -> None:
    summary = pd.DataFrame(
        {
            "etf_code": ["510300", "510300"],
            "strategy_name": ["A", "B"],
            "annualized_extrinsic_premium_yield": [0.10, 0.20],
            "downside_cushion_ratio_mean": [0.20, 0.10],
            "max_drawdown_improvement": [0.10, 0.20],
            "premium_capture_ratio": [0.50, 0.40],
        }
    )

    ranking = build_defensive_strategy_ranking(summary)

    assert ranking.iloc[0]["strategy_name"] == "B"
    assert math.isclose(ranking.iloc[0]["primary_score"], 0.80)
    assert math.isclose(ranking.iloc[1]["primary_score"], 0.70)


def test_assumed_bid_ask_spread_adds_half_spread_cost_when_market_spread_missing() -> None:
    cost = calculate_transaction_cost(
        option_premium=2.0,
        spot=100.0,
        coverage_ratio=1.0,
        transaction_costs={
            "option_slippage_bps": 0,
            "use_bid_ask_spread_cost": True,
            "use_assumed_bid_ask_spread_when_missing": True,
            "assumed_bid_ask_spread_pct": 0.05,
        },
        raw_bid_ask_spread_pct=np.nan,
    )

    assert math.isclose(cost.bid_ask_spread_cost_return, 0.0005)
    assert math.isclose(cost.total_cost_return, 0.0005)
    assert math.isclose(cost.effective_bid_ask_spread_pct, 0.05)
    assert cost.bid_ask_spread_source == "assumed"


def test_transaction_cost_override_makes_spread_dashboard_adjustable(tmp_path) -> None:
    config = ExperimentConfig(
        experiment_name="test",
        etf_codes=("510300",),
        paths=PathsConfig(
            etf_prices=tmp_path / "prices.csv",
            options=tmp_path / "options.csv",
            metadata=None,
            output_dir=tmp_path / "outputs",
        ),
        backtest=BacktestConfig(
            start_date=None,
            end_date=None,
            initial_nav=1.0,
            execution_mode="continuous_30d",
            roll_frequency="monthly",
            target_dte=30,
            min_days_to_expiry=20,
            max_days_to_expiry=45,
            min_periods=1,
            require_expiry_within_period=False,
        ),
        strategies=(StrategyConfig("BuyHold", "buy_hold", 0.0),),
        liquidity_filters={},
        transaction_costs={
            "use_bid_ask_spread_cost": True,
            "use_assumed_bid_ask_spread_when_missing": True,
            "assumed_bid_ask_spread_pct": 0.05,
        },
        assumptions={},
    )

    updated = with_transaction_cost_overrides(config, assumed_bid_ask_spread_pct=0.10)

    assert config.transaction_costs["assumed_bid_ask_spread_pct"] == 0.05
    assert updated.transaction_costs["assumed_bid_ask_spread_pct"] == 0.10


def _sample_moneyness_tables() -> dict[str, pd.DataFrame]:
    strategies = ["ITM5_100", "ITM2_100", "ATM_100", "OTM2_100", "OTM5_100"]
    target = [-0.05, -0.02, 0.0, 0.02, 0.05]
    rows = [
        {
            "etf_code": "510300",
            "strategy_name": "BuyHold",
            "num_periods": 5,
            "cumulative_return": 0.0,
            "annualized_return": 0.0,
            "annualized_volatility": 0.10,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.30,
            "assignment_rate": np.nan,
            "downside_excess_mean": 0.0,
            "downside_win_rate": 0.0,
            "downside_cushion_ratio_mean": 0.0,
            "average_downside_benefit": 0.0,
            "upside_cost_mean": 0.0,
            "protection_cost_ratio": np.nan,
            "max_drawdown_improvement": 0.0,
        }
    ]
    for i, (strategy, moneyness) in enumerate(zip(strategies, target), start=1):
        max_dd = 0.30 - i * 0.02
        rows.append(
            {
                "etf_code": "510300",
                "strategy_name": strategy,
                "num_periods": 5,
                "cumulative_return": 0.01 * i,
                "annualized_return": 0.01 * i,
                "annualized_volatility": 0.10 + 0.01 * i,
                "sharpe_ratio": 0.1 * i,
                "max_drawdown": max_dd,
                "assignment_rate": 1.0 - 0.1 * i,
                "downside_excess_mean": 0.01,
                "downside_win_rate": 0.8,
                "downside_cushion_ratio_mean": 1.0 - 0.1 * i,
                "average_downside_benefit": 0.01,
                "upside_cost_mean": 0.02,
                "protection_cost_ratio": 2.0,
                "max_drawdown_improvement": 0.30 - max_dd,
            }
        )
    summary = pd.DataFrame(rows)
    premium = pd.DataFrame(
        {
            "etf_code": ["510300"] * 5,
            "strategy_name": strategies,
            "average_total_premium_yield": [0.06, 0.04, 0.025, 0.015, 0.008],
            "annualized_extrinsic_premium_yield": [0.05, 0.08, 0.10, 0.07, 0.03],
            "premium_capture_ratio": [0.05, 0.10, 0.20, 0.40, 0.60],
        }
    )
    ranking = pd.DataFrame(
        {
            "etf_code": ["510300"] * 5,
            "strategy_name": strategies,
            "primary_score": [0.5, 0.7, 0.9, 0.6, 0.4],
        }
    )
    decomp = pd.DataFrame(
        {
            "etf_code": ["510300"] * 5,
            "strategy_name": strategies,
            "strike": [95.0, 98.0, 100.0, 102.0, 105.0],
            "underlying_price_at_entry": [100.0] * 5,
        }
    )
    return {
        "summary": summary,
        "premium_summary": premium,
        "defensive_ranking": ranking,
        "premium_decomposition": decomp,
    }


def test_moneyness_gradient_summary_sorts_and_excludes_buyhold() -> None:
    tables = _sample_moneyness_tables()
    gradient, warnings = build_moneyness_gradient_summary(tables)
    run_moneyness_sanity_checks(gradient, tables)

    assert warnings == []
    assert list(gradient["target_moneyness"]) == [-0.05, -0.02, 0.0, 0.02, 0.05]
    assert "BuyHold" not in set(gradient["strategy_name"])
    assert gradient.loc[gradient["strategy_name"] == "ITM5_100", "target_moneyness"].iloc[0] < 0
    assert gradient.loc[gradient["strategy_name"] == "OTM5_100", "target_moneyness"].iloc[0] > 0
    atm = gradient[gradient["strategy_name"] == "ATM_100"].iloc[0]
    assert math.isclose(atm["realized_moneyness_mean"], 0.0)
    assert math.isclose(atm["annualized_extrinsic_premium_yield"], 0.10)
    assert not math.isclose(atm["annualized_extrinsic_premium_yield"], atm["average_total_premium_yield"])


def test_moneyness_gradient_long_and_correlation_have_expected_metrics() -> None:
    tables = _sample_moneyness_tables()
    gradient, _ = build_moneyness_gradient_summary(tables)
    long_table = build_moneyness_gradient_long(gradient)
    corr = build_moneyness_correlation(gradient)

    assert "BuyHold" not in set(long_table["strategy_name"])
    assert set(["annualized_extrinsic_premium_yield", "primary_score"]).issubset(set(long_table["metric_name"]))
    assignment = corr[
        (corr["etf_code"] == "510300")
        & (corr["metric_name"] == "assignment_rate")
    ].iloc[0]
    assert assignment["monotonic_direction"] == "decreasing"


def test_ver2_1_dte_specs_match_requested_windows() -> None:
    assert [
        (spec.label, spec.target_dte, spec.min_days_to_expiry, spec.max_days_to_expiry, spec.dte_fallback_mode)
        for spec in DTE_SPECS
    ] == [
        ("DTE14_strict_window", 14, 7, 21, "strict_window"),
        ("DTE14_nearest_continuous", 14, 7, 21, "nearest_available"),
        ("DTE30", 30, 20, 45, "strict_window"),
        ("DTE45", 45, 35, 60, "strict_window"),
        ("DTE60", 60, 50, 75, "strict_window"),
    ]


def test_target_delta_selector_uses_model_delta_when_available() -> None:
    options = pd.DataFrame(
        [
            {
                "trade_date": pd.Timestamp("2021-01-29"),
                "option_code": "D30",
                "underlying_etf": "510300",
                "option_type": "C",
                "expiry": pd.Timestamp("2021-02-24"),
                "strike": 105.0,
                "close": 1.0,
                "model_delta": 0.30,
                "volume": 100.0,
                "open_interest": 100.0,
            },
            {
                "trade_date": pd.Timestamp("2021-01-29"),
                "option_code": "D50",
                "underlying_etf": "510300",
                "option_type": "C",
                "expiry": pd.Timestamp("2021-02-24"),
                "strike": 100.0,
                "close": 2.0,
                "model_delta": 0.50,
                "volume": 100.0,
                "open_interest": 100.0,
            },
        ]
    )
    backtest = BacktestConfig(
        start_date=None,
        end_date=None,
        initial_nav=1.0,
        execution_mode="continuous_30d",
        roll_frequency="monthly",
        target_dte=30,
        min_days_to_expiry=20,
        max_days_to_expiry=45,
        min_periods=1,
        require_expiry_within_period=False,
    )

    result = select_ver2_option(
        options=options,
        trade_date=pd.Timestamp("2021-01-29"),
        etf_code="510300",
        spot=100.0,
        period_end=pd.Timestamp("2021-03-31"),
        strategy=StrategyConfig("D30_100", "target_delta", 1.0, 0.30),
        backtest=backtest,
        liquidity_filters={"min_option_volume": 0, "min_open_interest": 0, "max_bid_ask_spread_pct": 1.0},
    )

    assert result.selected
    assert result.option is not None
    assert result.option["option_code"] == "D30"


def test_dte14_nearest_continuous_falls_back_to_nearest_positive_expiry() -> None:
    options = pd.DataFrame(
        [
            {
                "trade_date": pd.Timestamp("2021-01-29"),
                "option_code": "C28",
                "underlying_etf": "510300",
                "option_type": "C",
                "expiry": pd.Timestamp("2021-02-26"),
                "strike": 100.0,
                "close": 2.0,
                "volume": 100.0,
                "open_interest": 100.0,
            },
            {
                "trade_date": pd.Timestamp("2021-01-29"),
                "option_code": "C91",
                "underlying_etf": "510300",
                "option_type": "C",
                "expiry": pd.Timestamp("2021-04-30"),
                "strike": 100.0,
                "close": 5.0,
                "volume": 100.0,
                "open_interest": 100.0,
            },
        ]
    )
    strict = BacktestConfig(
        start_date=None,
        end_date=None,
        initial_nav=1.0,
        execution_mode="continuous_30d",
        roll_frequency="monthly",
        target_dte=14,
        min_days_to_expiry=7,
        max_days_to_expiry=21,
        min_periods=1,
        require_expiry_within_period=False,
    )
    nearest = BacktestConfig(
        start_date=None,
        end_date=None,
        initial_nav=1.0,
        execution_mode="continuous_30d",
        roll_frequency="monthly",
        target_dte=14,
        min_days_to_expiry=7,
        max_days_to_expiry=21,
        min_periods=1,
        require_expiry_within_period=False,
        dte_fallback_mode="nearest_available",
    )
    strategy = StrategyConfig("ATM_100", "atm", 1.0, 0.0)
    filters = {"min_option_volume": 0, "min_open_interest": 0, "max_bid_ask_spread_pct": 1.0}

    strict_result = select_ver2_option(
        options,
        pd.Timestamp("2021-01-29"),
        "510300",
        100.0,
        pd.Timestamp("2021-12-31"),
        strategy,
        strict,
        filters,
    )
    nearest_result = select_ver2_option(
        options,
        pd.Timestamp("2021-01-29"),
        "510300",
        100.0,
        pd.Timestamp("2021-12-31"),
        strategy,
        nearest,
        filters,
    )

    assert not strict_result.selected
    assert nearest_result.selected
    assert nearest_result.option is not None
    assert nearest_result.option["option_code"] == "C28"
    assert nearest_result.fallback_flag == "nearest_available_expiry_outside_window"


def test_ver2_1_regime_features_use_entry_history_only() -> None:
    dates = pd.bdate_range("2021-01-01", periods=80)
    prices = pd.DataFrame(
        {
            "date": dates,
            "etf_code": "510300",
            "adj_close": np.linspace(100.0, 120.0, len(dates)),
        }
    )
    periods = pd.DataFrame(
        {
            "etf_code": ["510300"],
            "strategy_name": ["ATM_100"],
            "dte_label": ["DTE30"],
            "rebalance_date": [dates[60]],
            "period_end_date": [dates[70]],
            "selected_iv": [0.20],
            "etf_period_return": [0.05],
            "strategy_period_return": [0.03],
            "excess_return_vs_etf": [-0.02],
        }
    )

    out = attach_regime_features(periods, prices).iloc[0]
    expected_trend = prices.loc[60, "adj_close"] / prices.loc[40, "adj_close"] - 1.0

    assert math.isclose(out["trend_20d"], expected_trend)
    assert out["iv_percentile"] == 1.0


def test_ver2_1_classifies_no_eligible_expiry_separately_from_terminal() -> None:
    prices = pd.DataFrame(
        {
            "date": pd.to_datetime(["2021-03-24", "2021-07-01"]),
            "etf_code": ["510300", "510300"],
            "adj_close": [100.0, 100.0],
        }
    )
    options = pd.DataFrame(
        {
            "trade_date": [pd.Timestamp("2021-03-24"), pd.Timestamp("2021-03-24")],
            "underlying_etf": ["510300", "510300"],
            "option_type": ["C", "C"],
            "expiry": [pd.Timestamp("2021-04-28"), pd.Timestamp("2021-06-23")],
            "strike": [100.0, 100.0],
            "close": [2.0, 3.0],
        }
    )
    skipped = pd.DataFrame(
        {
            "etf_code": ["510300", "510300"],
            "dte_label": ["DTE60", "DTE60"],
            "strategy_name": ["ATM_100", "ATM_100"],
            "rebalance_date": [pd.Timestamp("2021-03-24"), pd.Timestamp("2021-06-25")],
            "selection_reason": ["no_contract_in_dte_window", "no_contract_in_dte_window"],
        }
    )

    out = classify_skipped_periods(skipped, options, prices)

    assert out.loc[0, "skip_category"] == "no_eligible_expiry_in_window"
    assert out.loc[1, "skip_category"] == "terminal_insufficient_horizon"


def test_ver2_1_effective_coverage_counts_active_short_call_days() -> None:
    prices = pd.DataFrame(
        {
            "date": pd.to_datetime(["2021-01-01", "2021-01-05"]),
            "etf_code": ["510300", "510300"],
            "adj_close": [100.0, 101.0],
        }
    )
    periods = pd.DataFrame(
        {
            "etf_code": ["510300", "510300"],
            "dte_label": ["DTE14_strict_window", "DTE14_strict_window"],
            "strategy_name": ["ATM_100", "ATM_100"],
            "strategy_family": ["moneyness", "moneyness"],
            "rebalance_date": [pd.Timestamp("2021-01-01"), pd.Timestamp("2021-01-04")],
            "period_end_date": [pd.Timestamp("2021-01-04"), pd.Timestamp("2021-01-05")],
            "option_selected_flag": [1, 0],
        }
    )
    daily_mtm = pd.DataFrame(
        {
            "date": pd.to_datetime(["2021-01-01", "2021-01-04", "2021-01-05"]),
            "etf_code": ["510300", "510300", "510300"],
            "dte_label": ["DTE14_strict_window", "DTE14_strict_window", "DTE14_strict_window"],
            "strategy_name": ["ATM_100", "ATM_100", "ATM_100"],
            "position_state": ["short_call", "short_call", "no_option"],
        }
    )
    skipped = pd.DataFrame(
        {
            "etf_code": ["510300"],
            "dte_label": ["DTE14_strict_window"],
            "strategy_name": ["ATM_100"],
            "skip_category": ["no_eligible_expiry_in_window"],
        }
    )

    coverage = build_effective_coverage_summary(periods, daily_mtm, skipped, prices).iloc[0]

    assert coverage["total_backtest_days"] == 3
    assert coverage["active_short_call_days"] == 2
    assert coverage["etf_only_gap_days"] == 1
    assert math.isclose(coverage["effective_option_coverage_ratio"], 2 / 3)
    assert coverage["valid_option_cycle_count"] == 1
    assert coverage["skipped_period_count"] == 1
    assert coverage["no_eligible_expiry_count"] == 1


def test_ver2_1_down_then_rebound_event_measures_missed_rebound() -> None:
    periods = pd.DataFrame(
        {
            "etf_code": ["510300", "510300"],
            "dte_label": ["DTE30", "DTE30"],
            "strategy_name": ["ATM_100", "ATM_100"],
            "strategy_family": ["moneyness", "moneyness"],
            "rebalance_date": [pd.Timestamp("2021-01-29"), pd.Timestamp("2021-02-24")],
            "period_end_date": [pd.Timestamp("2021-02-24"), pd.Timestamp("2021-03-24")],
            "etf_period_return": [-0.04, 0.08],
            "strategy_period_return": [-0.02, 0.05],
            "excess_return_vs_etf": [0.02, -0.03],
            "policy_jump_like": [0, 0],
        }
    )

    events = build_down_then_rebound_events(periods)

    assert len(events) == 1
    assert math.isclose(events.iloc[0]["recovery_capture"], 0.625)
    assert math.isclose(events.iloc[0]["missed_rebound_return"], 0.03)


def test_ver2_1_ranking_rewards_lower_daily_mtm_and_missed_rebound() -> None:
    summary = pd.DataFrame(
        {
            "etf_code": ["510300", "510300"],
            "dte_label": ["DTE30", "DTE45"],
            "strategy_name": ["ATM_100", "OTM5_100"],
            "annualized_extrinsic_premium_yield": [0.10, 0.08],
            "downside_cushion_ratio_mean": [0.30, 0.20],
            "max_drawdown_improvement": [0.04, 0.02],
            "premium_capture_ratio": [0.60, 0.50],
            "daily_mtm_max_drawdown": [0.05, 0.20],
            "max_short_call_mtm_loss": [0.03, 0.10],
            "missed_rebound_return": [0.01, 0.05],
            "effective_option_coverage_ratio": [0.98, 0.80],
            "etf_only_gap_days": [2, 20],
            "valid_option_cycle_count": [50, 30],
        }
    )

    ranking = build_dte_robustness_ranking(summary)

    assert ranking.iloc[0]["strategy_name"] == "ATM_100"
    assert ranking.iloc[0]["robustness_score"] > ranking.iloc[1]["robustness_score"]
    assert "effective_option_coverage_ratio" in ranking.columns
    assert "etf_only_gap_days" in ranking.columns
    assert "valid_option_cycle_count" in ranking.columns


def test_ver2_1_standard_performance_uses_daily_nav_and_deduplicates_dates() -> None:
    daily_mtm = pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2021-01-01", "2021-01-04", "2021-01-04", "2021-01-05", "2021-02-01"]
            ),
            "etf_code": ["510300"] * 5,
            "dte_label": ["DTE30"] * 5,
            "strategy_name": ["ATM_100"] * 5,
            "period_index": [1, 1, 2, 2, 2],
            "daily_mtm_nav": [1.00, 1.01, 1.02, 1.01, 1.04],
        }
    )

    summary = build_standard_performance_summary(daily_mtm)
    row = summary.iloc[0]

    assert row["daily_nav_observations"] == 4
    assert math.isclose(row["cumulative_return_daily_nav"], 0.04)
    assert math.isclose(row["max_drawdown"], 1.0 - 1.01 / 1.02)
    assert row["drawdown_duration"] == 27.0
    assert row["monthly_win_rate"] == 1.0
    assert "sharpe_ratio_daily_nav" in summary.columns
    assert "sortino_ratio_daily_nav" in summary.columns


def test_ver2_1_candidate_shortlist_filters_coverage_strategy_protection_and_mtm() -> None:
    ranking = pd.DataFrame(
        {
            "etf_code": ["510300"] * 6,
            "dte_label": ["DTE30", "DTE45", "DTE60", "DTE14_nearest_continuous", "DTE30", "DTE14_strict_window"],
            "strategy_name": ["ATM_100", "D50_100", "D40_100", "OTM2_100", "OTM5_100", "ATM_100"],
            "robustness_score": [0.90, 0.80, 0.70, 0.60, 0.95, 0.88],
            "annualized_extrinsic_premium_yield": [0.08, 0.07, 0.06, 0.05, 0.04, 0.09],
            "downside_cushion_ratio_mean": [0.30, 0.25, 0.05, 0.20, 0.40, 0.35],
            "max_drawdown_improvement": [0.03, 0.02, 0.01, 0.02, 0.04, 0.03],
            "premium_capture_ratio": [0.50, 0.55, 0.60, 0.65, 0.70, 0.50],
            "max_short_call_mtm_loss": [0.03, 0.04, 0.05, 0.12, 0.02, 0.03],
            "missed_rebound_return": [0.01, 0.02, 0.03, 0.04, 0.01, 0.01],
            "effective_option_coverage_ratio": [0.98, 0.97, 1.00, 0.99, 1.00, 0.74],
            "coverage_comparability_flag": [
                "comparable_continuous_overlay",
                "comparable_continuous_overlay",
                "comparable_continuous_overlay",
                "comparable_continuous_overlay",
                "comparable_continuous_overlay",
                "near_expiry_overlay_separate",
            ],
            "etf_only_gap_days": [1, 2, 0, 1, 0, 320],
            "valid_option_cycle_count": [50, 45, 40, 60, 50, 60],
        }
    )
    standard = pd.DataFrame(
        {
            "etf_code": ["510300"] * 6,
            "dte_label": ranking["dte_label"],
            "strategy_name": ranking["strategy_name"],
            "annualized_return_daily_nav": [0.05] * 6,
            "annualized_volatility_daily_nav": [0.12] * 6,
            "sharpe_ratio_daily_nav": [0.40] * 6,
            "sortino_ratio_daily_nav": [0.60] * 6,
            "calmar_ratio_daily_nav": [0.50] * 6,
            "max_drawdown": [0.10] * 6,
            "drawdown_duration": [30.0] * 6,
            "monthly_win_rate": [0.55] * 6,
            "worst_month_return": [-0.04] * 6,
            "skewness": [0.0] * 6,
            "kurtosis": [0.0] * 6,
        }
    )

    shortlist = build_candidate_shortlist(ranking, standard)

    assert shortlist["strategy_name"].tolist() == ["ATM_100", "D50_100"]
    assert shortlist["shortlist_rank"].tolist() == [1, 2]
    assert (shortlist["effective_option_coverage_ratio"] >= 0.95).all()
    assert "annualized_return_daily_nav" in shortlist.columns


def test_ver2_1b_stc_selection_uses_shortest_expiry_above_min_dte() -> None:
    options = pd.DataFrame(
        {
            "trade_date": [pd.Timestamp("2021-01-01")] * 4,
            "underlying_etf": ["510300"] * 4,
            "option_type": ["C"] * 4,
            "expiry": pd.to_datetime(["2021-01-06", "2021-01-09", "2021-01-11", "2021-01-29"]),
            "strike": [100.0] * 4,
            "close": [1.0, 1.1, 1.2, 2.0],
            "option_code": ["C5", "C8", "C10", "C28"],
            "model_delta": [0.5] * 4,
        }
    )
    strategy = StrategyConfig("ATM_100", "atm", 1.0, 0.0, True)
    stc_min10 = BacktestConfig(
        start_date=None,
        end_date=None,
        initial_nav=1.0,
        execution_mode="continuous_30d",
        roll_frequency="monthly",
        target_dte=10,
        min_days_to_expiry=10,
        max_days_to_expiry=9999,
        min_periods=1,
        require_expiry_within_period=False,
        dte_fallback_mode="strict_window",
    )

    selected = select_ver2_option(
        options,
        pd.Timestamp("2021-01-01"),
        "510300",
        100.0,
        pd.Timestamp("2021-12-31"),
        strategy,
        stc_min10,
        {},
    )

    assert selected.selected
    assert selected.option is not None
    assert selected.option["option_code"] == "C10"


def test_ver2_1b_actual_dte_distribution_flags_dte30_like_stc() -> None:
    periods = pd.DataFrame(
        {
            "etf_code": ["510300", "510300", "510300"],
            "tenor_rule": ["STC_min14", "STC_min14", "STC_min14"],
            "dte_label": ["STC_min14", "STC_min14", "STC_min14"],
            "strategy_name": ["ATM_100", "ATM_100", "ATM_100"],
            "option_selected_flag": [1, 1, 1],
            "actual_dte": [28, 30, 32],
        }
    )

    dist = build_actual_dte_distribution(periods)
    row = dist.iloc[0]

    assert row["actual_dte_min"] == 28
    assert row["actual_dte_bucket_21_35_count"] == 3
    assert "DTE30-like" in row["actual_dte_distribution_note"]


def test_ver2_1b_candidate_ranking_excludes_low_coverage_and_appendix_tenors() -> None:
    full = pd.DataFrame(
        {
            "etf_code": ["510300", "510300", "510300", "510300"],
            "tenor_rule": ["STC_min7", "DTE30", "DTE14_strict_window", "STC_min10"],
            "dte_label": ["STC_min7", "DTE30", "DTE14_strict_window", "STC_min10"],
            "strategy_name": ["ATM_100", "D50_100", "ATM_100", "OTM5_100"],
            "effective_option_coverage_ratio": [0.99, 0.80, 0.99, 1.00],
            "coverage_comparability_flag": [
                "comparable_continuous_overlay",
                "low_coverage_not_directly_comparable",
                "near_expiry_overlay_separate",
                "comparable_continuous_overlay",
            ],
            "annualized_extrinsic_premium_yield": [0.20, 0.30, 0.40, 0.50],
            "downside_cushion_ratio_mean": [1.0, 2.0, 3.0, 4.0],
            "max_drawdown_improvement": [0.10, 0.20, 0.30, 0.40],
            "premium_capture_ratio": [0.30, 0.40, 0.50, 0.60],
            "daily_mtm_max_drawdown": [0.10, 0.20, 0.30, 0.40],
            "missed_rebound_return_mean": [0.02, 0.01, 0.03, 0.04],
        }
    )

    ranking = build_candidate_ranking(full)

    assert ranking["tenor_rule"].tolist() == ["STC_min7"]
    assert ranking["strategy_name"].tolist() == ["ATM_100"]


def test_ver2_2_primary_regime_priority_ignores_ex_post_labels() -> None:
    post_row = pd.Series(
        {
            "trend_5d": 0.02,
            "trend_20d": 0.05,
            "ma_gap_60": 0.03,
            "drawdown_from_rolling_high_252": -0.10,
            "policy_jump_like": 1,
            "down_then_rebound": 1,
        }
    )
    neutral_row = pd.Series(
        {
            "trend_5d": -0.01,
            "trend_20d": 0.01,
            "ma_gap_60": -0.05,
            "drawdown_from_rolling_high_252": -0.02,
            "policy_jump_like": 1,
            "down_then_rebound": 1,
        }
    )

    assert assign_primary_regime(post_row) == "post_drawdown_rebound_risk"
    assert assign_primary_regime(neutral_row) == "neutral"


def test_ver2_2_sanity_checks_keep_dte60_as_appendix_only() -> None:
    period_dataset = pd.DataFrame(
        {
            "etf_code": ["510300", "510300", "510300"],
            "dte_label": ["DTE30", "DTE30", "DTE60"],
            "strategy_name": ["BuyHold", "DTE30_D40_100", "DTE60_ATM_100"],
            "candidate_role": ["benchmark", "current_main_candidate", "appendix_reference"],
        }
    )
    candidate_comparison = pd.DataFrame(
        {
            "strategy_name": ["BuyHold", "DTE30_D40_100"],
            "sharpe_ratio_daily_nav": [0.0, 0.2],
        }
    )
    regime_performance = pd.DataFrame({"low_sample_warning": [False, True]})

    checks = run_sanity_checks(period_dataset, candidate_comparison, regime_performance)

    assert checks["passed"].all()


def test_ver2_2_1_refined_regime_classifier_handles_mixed_signals() -> None:
    deep_recovery = pd.Series(
        {
            "trend_20d": 0.025,
            "ma_gap_60": -0.01,
            "drawdown_from_rolling_high_252": -0.12,
        }
    )
    pullback = pd.Series(
        {
            "trend_20d": -0.025,
            "ma_gap_60": 0.01,
            "drawdown_from_rolling_high_252": -0.04,
        }
    )
    neutral_below = pd.Series(
        {
            "trend_20d": -0.01,
            "ma_gap_60": -0.01,
            "drawdown_from_rolling_high_252": -0.03,
        }
    )

    assert assign_refined_primary_regime(deep_recovery) == "deep_drawdown_recovery"
    assert classify_regime_conflict_type(deep_recovery) == "short_up_medium_below_ma_deep_drawdown"
    assert assign_refined_primary_regime(pullback) == "pullback_above_ma"
    assert classify_regime_conflict_type(pullback) == "short_down_medium_above_ma"
    assert assign_refined_primary_regime(neutral_below) == "neutral_below_ma"


def test_ver2_2_1_refined_dataset_keeps_main_candidates_and_old_regime() -> None:
    step1 = pd.DataFrame(
        {
            "etf_code": ["510300", "510300", "510300", "510300"],
            "strategy_name": ["BuyHold", "DTE30_D40_100", "DTE60_ATM_100", "DTE30_ITM2_100"],
            "candidate_role": ["benchmark", "current_main_candidate", "appendix_reference", "appendix_reference"],
            "dte_label": ["DTE30", "DTE30", "DTE60", "DTE30"],
            "primary_regime": ["weak_downtrend", "weak_downtrend", "strong_uptrend", "neutral"],
            "rebalance_date": ["2021-01-01"] * 4,
            "expiry_date": ["2021-02-01"] * 4,
            "period_end_date": ["2021-02-01"] * 4,
            "trend_5d": [0.0, 0.0, 0.0, 0.0],
            "trend_20d": [-0.04, -0.04, 0.05, 0.01],
            "ma_gap_60": [-0.02, -0.02, 0.03, 0.01],
            "drawdown_from_rolling_high_252": [-0.10, -0.10, -0.02, -0.01],
            "rv_20d": [0.2] * 4,
            "iv_at_entry": [0.2] * 4,
            "iv_percentile_252": [0.5] * 4,
            "iv_minus_rv20": [0.0] * 4,
            "policy_jump_like": [0] * 4,
            "down_then_rebound": [0] * 4,
            "etf_period_return": [-0.02] * 4,
            "strategy_period_return": [-0.01] * 4,
            "excess_return_vs_buyhold": [0.0, 0.01, 0.02, 0.03],
            "premium_return": [0.0, 0.01, 0.02, 0.03],
            "payoff_return": [0.0] * 4,
            "premium_capture_ratio_period": [np.nan, 1.0, 1.0, 1.0],
            "assignment_flag": [0] * 4,
            "downside_excess": [0.0, 0.01, 0.02, 0.03],
            "downside_cushion_ratio": [0.0, 0.5, 0.6, 0.7],
            "upside_cost": [0.0] * 4,
            "missed_rebound_return": [0.0] * 4,
            "recovery_capture": [np.nan] * 4,
            "daily_mtm_nav_start": [1.0] * 4,
            "daily_mtm_nav_end": [1.0] * 4,
            "max_short_call_mtm_loss_in_period": [0.0] * 4,
            "daily_mtm_drawdown_in_period": [0.0] * 4,
        }
    )

    refined = build_refined_period_dataset(step1)

    assert refined["strategy_name"].tolist() == ["BuyHold", "DTE30_D40_100"]
    assert set(refined["old_primary_regime"]) == {"weak_downtrend"}
    assert set(refined["refined_primary_regime"]) == {"confirmed_downtrend"}


def test_ver2_3_option_leg_dataset_keeps_gap_extrinsic_at_zero() -> None:
    periods = pd.DataFrame(
        {
            "etf_code": ["510300", "510300"],
            "strategy_name": ["D40_100", "D40_100"],
            "period_index": [1, 2],
            "rebalance_date": ["2021-01-01", "2021-02-01"],
            "period_end_date": ["2021-01-31", "2021-02-28"],
            "underlying_price_at_entry": [100.0, 101.0],
            "underlying_price_at_period_end": [101.0, 100.0],
            "coverage_ratio": [1.0, 1.0],
            "premium_return": [0.02, 0.0],
            "upside_payoff_return": [0.01, 0.0],
            "transaction_cost_return": [0.001, 0.0],
            "etf_period_return": [0.01, -0.01],
            "strategy_period_return": [0.019, -0.01],
            "assignment_flag": [1, 0],
            "expiry_date": ["2021-01-31", None],
            "actual_dte": [30.0, np.nan],
            "strike": [100.0, np.nan],
            "option_price_at_entry": [2.0, np.nan],
            "realized_moneyness": [0.0, np.nan],
            "underlying_price_at_expiry": [101.0, 100.0],
            "option_payoff_return_at_expiry": [0.01, 0.0],
            "selected_delta": [0.4, np.nan],
            "selected_iv": [0.2, np.nan],
            "dte_label": ["DTE30", "DTE30"],
            "target_delta": [0.4, 0.4],
            "trend_5d": [0.0, 0.0],
            "trend_20d": [0.0, 0.0],
            "ma_gap_60": [0.0, 0.0],
            "drawdown_from_rolling_high": [0.0, 0.0],
            "rv_20d": [0.2, 0.2],
            "iv_at_entry": [0.2, np.nan],
            "iv_minus_rv": [0.0, np.nan],
            "policy_jump_like": [0, 0],
        }
    )
    daily = pd.DataFrame(
        {
            "date": ["2021-01-01", "2021-01-31", "2021-02-01", "2021-02-28"],
            "etf_code": ["510300"] * 4,
            "strategy_name": ["D40_100"] * 4,
            "period_index": [1, 1, 2, 2],
            "rebalance_date": ["2021-01-01", "2021-01-01", "2021-02-01", "2021-02-01"],
            "period_end_date": ["2021-01-31", "2021-01-31", "2021-02-28", "2021-02-28"],
            "option_liability_return": [0.02, 0.01, 0.0, 0.0],
            "short_call_mtm_loss_return": [0.0, 0.0, 0.0, 0.0],
            "premium_return": [0.02, 0.02, 0.0, 0.0],
            "transaction_cost_return": [0.001, 0.001, 0.0, 0.0],
            "daily_mtm_nav": [0.999, 1.019, 1.019, 1.009],
            "dte_label": ["DTE30"] * 4,
        }
    )
    step1 = pd.DataFrame()

    result = build_option_leg_period_dataset(periods, daily, step1)
    gap = result[result["period_index"].eq(2)].iloc[0] if "period_index" in result.columns else result.iloc[1]

    assert math.isclose(result.loc[0, "option_leg_return"], 0.009)
    assert gap["premium_return"] == 0.0
    assert gap["extrinsic_premium_yield"] == 0.0
    assert math.isnan(gap["payoff_burden"])
