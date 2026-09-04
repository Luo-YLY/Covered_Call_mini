from __future__ import annotations

from dataclasses import dataclass, replace
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ver2_downside_protection.config import ExperimentConfig, PathsConfig, StrategyConfig
from ver2_downside_protection.metrics import (
    add_period_diagnostics,
    annual_factor,
    annualized_return,
    max_drawdown_magnitude,
    protection_cost_ratio,
)
from ver2_downside_protection.premium_income_defensive import add_premium_decomposition
from ver2_downside_protection.strategy_engine import Ver2BacktestResult, run_ver2_backtest
from ver2_downside_protection.ver2_1_dte_regime import (
    attach_regime_features,
    build_active_overlay_metrics,
    build_down_then_rebound_events,
    build_dte_moneyness_summary,
    _candidate_delta_options_path,
    _has_usable_delta,
    _has_usable_iv,
)

LOGGER = logging.getLogger(__name__)

TRADING_DAYS_PER_YEAR = 252.0
MAX_STC_EXPIRY_WINDOW = 9999
CORE_REPORT_STRATEGIES = {"ATM_100", "D50_100", "D40_100", "OTM2_100"}
RANKING_TENORS = {"STC_min7", "STC_min10", "STC_min14", "DTE30", "DTE60"}


@dataclass(frozen=True)
class TenorSpec:
    label: str
    target_dte: int
    min_days_to_expiry: int
    max_days_to_expiry: int
    comparison_group: str
    dte_fallback_mode: str = "strict_window"


TENOR_SPECS: tuple[TenorSpec, ...] = (
    TenorSpec("STC_min7", 7, 7, MAX_STC_EXPIRY_WINDOW, "short_tenor_priority_continuous"),
    TenorSpec("STC_min10", 10, 10, MAX_STC_EXPIRY_WINDOW, "short_tenor_priority_continuous"),
    TenorSpec("STC_min14", 14, 14, MAX_STC_EXPIRY_WINDOW, "short_tenor_priority_continuous"),
    TenorSpec("DTE30", 30, 20, 45, "continuous_covered_call_benchmark"),
    TenorSpec("DTE60", 60, 50, 75, "low_roll_frequency_benchmark"),
    TenorSpec("DTE45", 45, 35, 60, "intermediate_tenor_appendix"),
    TenorSpec("DTE14_strict_window", 14, 7, 21, "near_expiry_overlay_appendix"),
)

TENOR_ORDER = {spec.label: idx for idx, spec in enumerate(TENOR_SPECS)}
SPEC_LOOKUP = {spec.label: spec for spec in TENOR_SPECS}

MONEYNESS_STRATEGIES: tuple[StrategyConfig, ...] = (
    StrategyConfig("BuyHold", "buy_hold", 0.0, 0.0, True),
    StrategyConfig("ATM_100", "atm", 1.0, 0.0, True),
    StrategyConfig("OTM2_100", "otm_pct", 1.0, 0.02, True),
    StrategyConfig("OTM5_100", "otm_pct", 1.0, 0.05, True),
)

DELTA_STRATEGIES: tuple[StrategyConfig, ...] = (
    StrategyConfig("D50_100", "target_delta", 1.0, 0.50, True),
    StrategyConfig("D40_100", "target_delta", 1.0, 0.40, True),
    StrategyConfig("D30_100", "target_delta", 1.0, 0.30, True),
    StrategyConfig("D20_100", "target_delta", 1.0, 0.20, True),
)

STRATEGY_ORDER = {
    "BuyHold": 0,
    "ATM_100": 1,
    "D50_100": 2,
    "D40_100": 3,
    "D30_100": 4,
    "OTM2_100": 5,
    "OTM5_100": 6,
    "D20_100": 7,
}

TARGET_MONEYNESS = {
    "ATM_100": 0.0,
    "OTM2_100": 0.02,
    "OTM5_100": 0.05,
}

TARGET_DELTA = {
    "D50_100": 0.50,
    "D40_100": 0.40,
    "D30_100": 0.30,
    "D20_100": 0.20,
}


@dataclass(frozen=True)
class Ver21bTables:
    periods: pd.DataFrame
    nav: pd.DataFrame
    daily_mtm: pd.DataFrame
    skipped_periods: pd.DataFrame
    actual_dte_distribution: pd.DataFrame
    effective_coverage_summary: pd.DataFrame
    standard_performance_summary: pd.DataFrame
    premium_downside_summary: pd.DataFrame
    daily_mtm_stress_summary: pd.DataFrame
    rebound_event_summary: pd.DataFrame
    full_account_metrics: pd.DataFrame
    active_overlay_metrics: pd.DataFrame
    candidate_ranking: pd.DataFrame
    down_then_rebound_events: pd.DataFrame
    metadata: dict[str, Any]


def _strategy_family(strategy_name: str) -> str:
    if strategy_name == "BuyHold":
        return "benchmark"
    if strategy_name in TARGET_DELTA:
        return "delta"
    return "moneyness"


def _strategy_configs(delta_available: bool) -> tuple[StrategyConfig, ...]:
    return MONEYNESS_STRATEGIES + (DELTA_STRATEGIES if delta_available else tuple())


def _sort_21b(df: pd.DataFrame, extra_cols: list[str] | None = None) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    out = df.copy()
    if "tenor_rule" not in out.columns and "dte_label" in out.columns:
        out["tenor_rule"] = out["dte_label"]
    out["_tenor_order"] = out.get("tenor_rule", pd.Series(index=out.index, dtype=object)).map(TENOR_ORDER).fillna(999)
    out["_strategy_order"] = out.get("strategy_name", pd.Series(index=out.index, dtype=object)).map(
        STRATEGY_ORDER
    ).fillna(999)
    cols = [col for col in ["etf_code", "_tenor_order", "tenor_rule", "_strategy_order", "strategy_name"] if col in out.columns]
    if extra_cols:
        cols.extend([col for col in extra_cols if col in out.columns])
    return out.sort_values(cols).drop(columns=["_tenor_order", "_strategy_order"], errors="ignore").reset_index(drop=True)


def _config_for_tenor(
    base_config: ExperimentConfig,
    *,
    spec: TenorSpec,
    strategies: tuple[StrategyConfig, ...],
    output_dir: Path,
    options_path: Path,
) -> ExperimentConfig:
    backtest = replace(
        base_config.backtest,
        execution_mode="continuous_30d",
        target_dte=spec.target_dte,
        min_days_to_expiry=spec.min_days_to_expiry,
        max_days_to_expiry=spec.max_days_to_expiry,
        require_expiry_within_period=False,
        dte_fallback_mode=spec.dte_fallback_mode,
    )
    paths = PathsConfig(
        etf_prices=base_config.paths.etf_prices,
        options=options_path,
        metadata=base_config.paths.metadata,
        output_dir=output_dir,
    )
    return replace(
        base_config,
        experiment_name="ver2_1b_short_tenor_priority",
        paths=paths,
        backtest=backtest,
        strategies=strategies,
    )


def _tag_result_frame(df: pd.DataFrame, spec: TenorSpec, option_source: Path) -> pd.DataFrame:
    out = df.copy()
    out["version"] = "ver2.1b"
    out["tenor_rule"] = spec.label
    out["dte_label"] = spec.label
    out["target_dte"] = spec.target_dte
    out["min_dte_threshold"] = spec.min_days_to_expiry
    out["dte_window_min"] = spec.min_days_to_expiry
    out["dte_window_max"] = spec.max_days_to_expiry
    out["dte_fallback_mode"] = spec.dte_fallback_mode
    out["tenor_comparison_group"] = spec.comparison_group
    out["dte_comparison_group"] = spec.comparison_group
    out["option_source"] = str(option_source)
    if "strategy_name" in out.columns:
        out["strategy_family"] = out["strategy_name"].map(_strategy_family)
        out["target_moneyness_spec"] = out["strategy_name"].map(TARGET_MONEYNESS)
        out["target_delta"] = out["strategy_name"].map(TARGET_DELTA)
    return out


def _run_tenor_backtests(
    base_config: ExperimentConfig,
    *,
    data: Any,
    data_options_path: Path,
    delta_available: bool,
) -> tuple[list[Ver2BacktestResult], dict[str, Any]]:
    strategies = _strategy_configs(delta_available)
    output_dir = base_config.paths.output_dir / "ver2_1b_short_tenor_priority"
    results: list[Ver2BacktestResult] = []
    for spec in TENOR_SPECS:
        LOGGER.info("Running ver2.1b %s.", spec.label)
        config = _config_for_tenor(
            base_config,
            spec=spec,
            strategies=strategies,
            output_dir=output_dir,
            options_path=data_options_path,
        )
        result = run_ver2_backtest(config, data=data)
        result = replace(
            result,
            periods=_tag_result_frame(result.periods, spec, data_options_path),
            nav=_tag_result_frame(result.nav, spec, data_options_path),
            daily_mtm=_tag_result_frame(result.daily_mtm, spec, data_options_path),
            summary=_tag_result_frame(result.summary, spec, data_options_path),
            skipped_periods=_tag_result_frame(result.skipped_periods, spec, data_options_path),
        )
        results.append(result)
    metadata = {
        "strategies": [strategy.name for strategy in strategies],
        "tenor_specs": [spec.__dict__ for spec in TENOR_SPECS],
    }
    return results, metadata


def _combine_result_attr(results: list[Ver2BacktestResult], attr: str) -> pd.DataFrame:
    frames = [getattr(result, attr) for result in results if not getattr(result, attr).empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def classify_skipped_periods_1b(skipped: pd.DataFrame, options: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """Classify STC selection failures without mixing terminal truncation with missing chains."""

    if skipped.empty:
        out = skipped.copy()
        out["skip_category"] = pd.Series(dtype=object)
        return out
    out = skipped.copy()
    out["rebalance_date"] = pd.to_datetime(out["rebalance_date"])
    out["etf_code"] = out["etf_code"].astype(str).str.zfill(6)
    if "tenor_rule" not in out.columns:
        out["tenor_rule"] = out["dte_label"]

    price_last = prices.groupby("etf_code")["date"].max().to_dict()
    out["_last_price_date"] = out["etf_code"].map(price_last)
    out["_days_to_sample_end"] = (pd.to_datetime(out["_last_price_date"]) - out["rebalance_date"]).dt.days

    needed_dates = pd.DatetimeIndex(out["rebalance_date"].dropna().unique())
    needed_etfs = set(out["etf_code"].dropna().astype(str))
    calls = options[
        options["underlying_etf"].astype(str).str.zfill(6).isin(needed_etfs)
        & pd.to_datetime(options["trade_date"]).isin(needed_dates)
        & (options["option_type"].astype(str).str.upper() == "C")
    ].copy()
    if calls.empty:
        stats = pd.DataFrame(
            columns=["etf_code", "rebalance_date", "option_call_chain_rows", "available_expiry_count", "available_dte_min", "available_dte_max"]
        )
    else:
        calls["trade_date"] = pd.to_datetime(calls["trade_date"])
        calls["underlying_etf"] = calls["underlying_etf"].astype(str).str.zfill(6)
        calls["days_to_expiry"] = (pd.to_datetime(calls["expiry"]) - calls["trade_date"]).dt.days
        stats = (
            calls.groupby(["underlying_etf", "trade_date"])["days_to_expiry"]
            .agg(
                option_call_chain_rows="size",
                available_expiry_count=lambda s: int(s.dropna().nunique()),
                available_dte_min="min",
                available_dte_max="max",
            )
            .reset_index()
            .rename(columns={"underlying_etf": "etf_code", "trade_date": "rebalance_date"})
        )
    out = out.merge(stats, on=["etf_code", "rebalance_date"], how="left")
    out["option_call_chain_rows"] = out["option_call_chain_rows"].fillna(0).astype(int)
    out["available_expiry_count"] = out["available_expiry_count"].fillna(0).astype(int)
    out["_window_min"] = out["tenor_rule"].map(lambda label: SPEC_LOOKUP[str(label)].min_days_to_expiry)
    out["skip_category"] = "other_selection_failure"

    terminal = out["_days_to_sample_end"] < out["_window_min"]
    no_chain = (out["selection_reason"] == "no_chain_on_trade_date") | (out["option_call_chain_rows"] <= 0)
    no_window = (out["selection_reason"] == "no_contract_in_dte_window") & (~terminal) & (~no_chain)
    out.loc[terminal, "skip_category"] = "terminal_insufficient_horizon"
    out.loc[no_chain & (~terminal), "skip_category"] = "data_missing_or_chain_unavailable"
    out.loc[no_window, "skip_category"] = "no_eligible_expiry_in_window"
    out["selection_reason_reclassified"] = out["skip_category"]
    return out.drop(columns=["_last_price_date", "_days_to_sample_end", "_window_min"])


def _natural_terminal_count(period_g: pd.DataFrame, prices: pd.DataFrame) -> int:
    if period_g.empty:
        return 0
    etf_code = str(period_g["etf_code"].iloc[0]).zfill(6)
    tenor_rule = str(period_g["tenor_rule"].iloc[0])
    spec = SPEC_LOOKUP.get(tenor_rule)
    if spec is None:
        return 0
    last_price_date = prices.loc[prices["etf_code"] == etf_code, "date"].max()
    if pd.isna(last_price_date):
        return 0
    last_period_end = pd.to_datetime(period_g["period_end_date"]).max()
    remaining_days = (pd.Timestamp(last_price_date) - pd.Timestamp(last_period_end)).days
    return int(last_period_end < pd.Timestamp(last_price_date) and remaining_days < spec.min_days_to_expiry)


def build_effective_coverage_summary_1b(
    periods: pd.DataFrame,
    daily_mtm: pd.DataFrame,
    skipped: pd.DataFrame,
    prices: pd.DataFrame,
) -> pd.DataFrame:
    """Measure active short-call coverage and roll cadence for each STC path."""

    if periods.empty:
        return pd.DataFrame()
    skip_counts = pd.DataFrame()
    if not skipped.empty and "skip_category" in skipped.columns:
        skip_counts = (
            skipped.groupby(["etf_code", "tenor_rule", "strategy_name", "skip_category"])
            .size()
            .unstack("skip_category", fill_value=0)
            .reset_index()
        )
    mtm_lookup = {
        (str(etf), str(tenor), str(strategy)): g.copy()
        for (etf, tenor, strategy), g in daily_mtm.groupby(["etf_code", "tenor_rule", "strategy_name"])
    }
    rows: list[dict[str, Any]] = []
    for (etf_code, tenor_rule, strategy_name), period_g in periods.groupby(["etf_code", "tenor_rule", "strategy_name"]):
        if strategy_name == "BuyHold":
            continue
        mtm_g = mtm_lookup.get((str(etf_code), str(tenor_rule), str(strategy_name)), pd.DataFrame())
        if mtm_g.empty:
            total_days = 0
            active_days = 0
        else:
            day_state = (
                mtm_g.assign(date=pd.to_datetime(mtm_g["date"]))
                .groupby("date")["position_state"]
                .apply(lambda s: bool((s == "short_call").any()))
            )
            total_days = int(len(day_state))
            active_days = int(day_state.sum())
        selected = period_g[period_g["option_selected_flag"].fillna(0).astype(int) == 1].sort_values("rebalance_date")
        skipped_period_count = int((period_g["option_selected_flag"].fillna(0).astype(int) == 0).sum())
        roll_diffs = pd.to_datetime(selected["rebalance_date"]).diff().dt.days.dropna()
        span_days = (
            (pd.to_datetime(period_g["period_end_date"]).max() - pd.to_datetime(period_g["rebalance_date"]).min()).days
            if not period_g.empty
            else np.nan
        )
        coverage = active_days / total_days if total_days else np.nan
        comparison_group = str(period_g["tenor_comparison_group"].iloc[0])
        rows.append(
            {
                "etf_code": etf_code,
                "tenor_rule": tenor_rule,
                "dte_label": tenor_rule,
                "strategy_name": strategy_name,
                "strategy_family": _strategy_family(str(strategy_name)),
                "tenor_comparison_group": comparison_group,
                "total_backtest_days": total_days,
                "active_short_call_days": active_days,
                "etf_only_gap_days": int(max(total_days - active_days, 0)),
                "effective_option_coverage_ratio": coverage,
                "valid_option_cycle_count": int(len(selected)),
                "skipped_period_count": skipped_period_count,
                "terminal_insufficient_horizon_count": _natural_terminal_count(period_g, prices),
                "no_eligible_expiry_count": 0,
                "data_missing_or_chain_unavailable_count": 0,
                "other_selection_failure_count": 0,
                "roll_count_per_year": float(len(selected) / max(span_days / 365.25, 1e-12))
                if pd.notna(span_days)
                else np.nan,
                "average_days_between_rolls": float(roll_diffs.mean()) if not roll_diffs.empty else np.nan,
                "median_days_between_rolls": float(roll_diffs.median()) if not roll_diffs.empty else np.nan,
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    if not skip_counts.empty:
        rename = {
            "terminal_insufficient_horizon": "terminal_insufficient_horizon_count_skip",
            "no_eligible_expiry_in_window": "no_eligible_expiry_count",
            "data_missing_or_chain_unavailable": "data_missing_or_chain_unavailable_count",
            "other_selection_failure": "other_selection_failure_count",
        }
        skip_counts = skip_counts.rename(columns=rename)
        out = out.merge(skip_counts, on=["etf_code", "tenor_rule", "strategy_name"], how="left")
        if "terminal_insufficient_horizon_count_skip" in out.columns:
            out["terminal_insufficient_horizon_count"] = out["terminal_insufficient_horizon_count"].fillna(0) + out[
                "terminal_insufficient_horizon_count_skip"
            ].fillna(0)
            out = out.drop(columns=["terminal_insufficient_horizon_count_skip"])
        for col in [
            "no_eligible_expiry_count",
            "data_missing_or_chain_unavailable_count",
            "other_selection_failure_count",
        ]:
            x_col = f"{col}_x"
            y_col = f"{col}_y"
            if x_col in out.columns or y_col in out.columns:
                base_count = out[x_col] if x_col in out.columns else pd.Series(0, index=out.index)
                skip_count = out[y_col] if y_col in out.columns else pd.Series(0, index=out.index)
                out[col] = base_count.fillna(0) + skip_count.fillna(0)
                out = out.drop(columns=[c for c in [x_col, y_col] if c in out.columns])
    for col in [
        "terminal_insufficient_horizon_count",
        "no_eligible_expiry_count",
        "data_missing_or_chain_unavailable_count",
        "other_selection_failure_count",
    ]:
        if col not in out.columns:
            out[col] = 0
        out[col] = out[col].fillna(0).astype(int)
    out["coverage_comparability_flag"] = np.select(
        [
            out["effective_option_coverage_ratio"] < 0.95,
            out["tenor_comparison_group"] == "near_expiry_overlay_appendix",
        ],
        [
            "low_coverage_not_directly_comparable",
            "near_expiry_overlay_separate",
        ],
        default="comparable_continuous_overlay",
    )
    return _sort_21b(out)


def _premium_capture_ratio(selected: pd.DataFrame) -> float:
    if selected.empty:
        return np.nan
    premium_received = float(selected["total_premium_yield"].fillna(0.0).sum())
    payoff_paid = float(selected["option_payoff_return_at_expiry"].fillna(0.0).sum())
    return (premium_received - payoff_paid) / premium_received if premium_received else np.nan


def build_actual_dte_distribution(periods: pd.DataFrame) -> pd.DataFrame:
    """Summarize whether STC rules actually achieve short-tenor exposure."""

    if periods.empty:
        return pd.DataFrame()
    selected_periods = periods[
        (periods["strategy_name"] != "BuyHold")
        & (periods["option_selected_flag"].fillna(0).astype(int) == 1)
    ].copy()
    rows: list[dict[str, Any]] = []
    for (etf_code, tenor_rule, strategy_name), g in selected_periods.groupby(["etf_code", "tenor_rule", "strategy_name"]):
        actual_dte = pd.to_numeric(g["actual_dte"], errors="coerce").dropna()
        if actual_dte.empty:
            note = "no_selected_option_cycles"
        else:
            median = float(actual_dte.median())
            if str(tenor_rule).startswith("STC") and 25 <= median <= 35:
                note = "DTE30-like exposure; short-tenor priority did not create distinct short-tenor exposure"
            elif str(tenor_rule).startswith("STC") and median <= 21:
                note = "short-tenor exposure observed"
            elif median >= 50:
                note = "long-tenor exposure"
            else:
                note = "mixed tenor exposure"
        rows.append(
            {
                "etf_code": etf_code,
                "tenor_rule": tenor_rule,
                "dte_label": tenor_rule,
                "strategy_name": strategy_name,
                "strategy_family": _strategy_family(str(strategy_name)),
                "selected_cycle_count": int(len(actual_dte)),
                "actual_dte_mean": float(actual_dte.mean()) if not actual_dte.empty else np.nan,
                "actual_dte_median": float(actual_dte.median()) if not actual_dte.empty else np.nan,
                "actual_dte_std": float(actual_dte.std(ddof=1)) if len(actual_dte) > 1 else np.nan,
                "actual_dte_min": float(actual_dte.min()) if not actual_dte.empty else np.nan,
                "actual_dte_max": float(actual_dte.max()) if not actual_dte.empty else np.nan,
                "actual_dte_p25": float(actual_dte.quantile(0.25)) if not actual_dte.empty else np.nan,
                "actual_dte_p75": float(actual_dte.quantile(0.75)) if not actual_dte.empty else np.nan,
                "actual_dte_bucket_0_7_count": int((actual_dte < 7).sum()),
                "actual_dte_bucket_7_14_count": int(((actual_dte >= 7) & (actual_dte < 14)).sum()),
                "actual_dte_bucket_14_21_count": int(((actual_dte >= 14) & (actual_dte < 21)).sum()),
                "actual_dte_bucket_21_35_count": int(((actual_dte >= 21) & (actual_dte < 35)).sum()),
                "actual_dte_bucket_35_60_count": int(((actual_dte >= 35) & (actual_dte < 60)).sum()),
                "actual_dte_bucket_60_plus_count": int((actual_dte >= 60).sum()),
                "actual_dte_distribution_note": note,
            }
        )
    return _sort_21b(pd.DataFrame(rows))


def _daily_nav_series(group: pd.DataFrame) -> pd.Series:
    if group.empty or "daily_mtm_nav" not in group.columns:
        return pd.Series(dtype=float)
    work = group.copy()
    work["date"] = pd.to_datetime(work["date"])
    work["_row_order"] = np.arange(len(work))
    sort_cols = ["date"]
    if "period_index" in work.columns:
        sort_cols.append("period_index")
    sort_cols.append("_row_order")
    daily = work.sort_values(sort_cols).groupby("date", as_index=False).tail(1).sort_values("date")
    return pd.Series(daily["daily_mtm_nav"].astype(float).to_numpy(), index=pd.DatetimeIndex(daily["date"])).dropna()


def _drawdown_duration_from_nav(nav: pd.Series) -> float:
    nav = nav.dropna().astype(float)
    if nav.empty:
        return np.nan
    drawdown = nav / nav.cummax() - 1.0
    underwater = drawdown < -1e-12
    max_days = 0.0
    start: pd.Timestamp | None = None
    for date, is_underwater in underwater.items():
        current_date = pd.Timestamp(date)
        if is_underwater and start is None:
            start = current_date
        elif not is_underwater and start is not None:
            max_days = max(max_days, float((current_date - start).days))
            start = None
    if start is not None:
        max_days = max(max_days, float((pd.Timestamp(nav.index[-1]) - start).days))
    return max_days


def _monthly_returns(daily_returns: pd.Series) -> pd.Series:
    if daily_returns.empty:
        return pd.Series(dtype=float)
    return daily_returns.groupby(daily_returns.index.to_period("M")).apply(lambda s: float((1.0 + s).prod() - 1.0))


def build_standard_performance_summary_1b(daily_mtm: pd.DataFrame) -> pd.DataFrame:
    """Compute daily-NAV standard performance with Sharpe based on daily mean/std."""

    if daily_mtm.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for (etf_code, tenor_rule, strategy_name), g in daily_mtm.groupby(["etf_code", "tenor_rule", "strategy_name"]):
        nav = _daily_nav_series(g)
        daily_returns = nav.pct_change().dropna()
        if len(nav) >= 2 and nav.iloc[0] > 0:
            years = (pd.Timestamp(nav.index[-1]) - pd.Timestamp(nav.index[0])).days / 365.25
            if years <= 0:
                years = max((len(nav) - 1) / TRADING_DAYS_PER_YEAR, 1e-12)
            ann_return = float((nav.iloc[-1] / nav.iloc[0]) ** (1.0 / years) - 1.0)
            cumulative = float(nav.iloc[-1] / nav.iloc[0] - 1.0)
        else:
            ann_return = np.nan
            cumulative = np.nan
        vol = float(daily_returns.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)) if len(daily_returns) > 1 else np.nan
        sharpe = (
            float(daily_returns.mean() / daily_returns.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))
            if len(daily_returns) > 1 and daily_returns.std(ddof=1) > 0
            else np.nan
        )
        downside = daily_returns[daily_returns < 0]
        sortino = (
            float(daily_returns.mean() / downside.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))
            if len(downside) > 1 and downside.std(ddof=1) > 0
            else np.nan
        )
        mdd = max_drawdown_magnitude(nav)
        monthly = _monthly_returns(daily_returns)
        rows.append(
            {
                "etf_code": etf_code,
                "tenor_rule": tenor_rule,
                "dte_label": tenor_rule,
                "strategy_name": strategy_name,
                "strategy_family": _strategy_family(str(strategy_name)),
                "tenor_comparison_group": g["tenor_comparison_group"].iloc[0],
                "start_date": nav.index.min() if not nav.empty else pd.NaT,
                "end_date": nav.index.max() if not nav.empty else pd.NaT,
                "daily_nav_observations": int(len(nav)),
                "cumulative_return_daily_nav": cumulative,
                "annualized_return_daily_nav": ann_return,
                "annualized_volatility_daily_nav": vol,
                "sharpe_ratio_daily_nav": sharpe,
                "sortino_ratio_daily_nav": sortino,
                "calmar_ratio_daily_nav": float(ann_return / mdd) if pd.notna(ann_return) and mdd and mdd > 0 else np.nan,
                "max_drawdown_daily_nav": mdd,
                "drawdown_duration": _drawdown_duration_from_nav(nav),
                "monthly_win_rate": float((monthly > 0).mean()) if not monthly.empty else np.nan,
                "worst_month_return": float(monthly.min()) if not monthly.empty else np.nan,
                "best_month_return": float(monthly.max()) if not monthly.empty else np.nan,
                "skewness": float(daily_returns.skew()) if len(daily_returns) > 2 else np.nan,
                "kurtosis": float(daily_returns.kurt()) if len(daily_returns) > 3 else np.nan,
            }
        )
    return _sort_21b(pd.DataFrame(rows))


def build_premium_downside_summary(periods: pd.DataFrame, base_summary: pd.DataFrame) -> pd.DataFrame:
    """Compute premium-income and downside-protection metrics for ver2.1b."""

    if periods.empty:
        return pd.DataFrame()
    decomposed = add_premium_decomposition(add_period_diagnostics(periods))
    base_lookup = (
        base_summary.set_index(["etf_code", "tenor_rule", "strategy_name"]).to_dict(orient="index")
        if not base_summary.empty
        else {}
    )
    rows: list[dict[str, Any]] = []
    for (etf_code, tenor_rule, strategy_name), g in decomposed.groupby(["etf_code", "tenor_rule", "strategy_name"]):
        selected = g[g["option_selected_flag"].fillna(0).astype(int) == 1]
        down = g[g["etf_period_return"] < 0]
        up = g[g["etf_period_return"] > 0]
        factor = annual_factor(g) if not g.empty else np.nan
        base = base_lookup.get((etf_code, tenor_rule, strategy_name), {})
        avg_downside_benefit = float(down["downside_benefit"].mean()) if not down.empty else np.nan
        upside_cost_mean = float(up["upside_cost"].mean()) if not up.empty else np.nan
        rows.append(
            {
                "etf_code": etf_code,
                "tenor_rule": tenor_rule,
                "dte_label": tenor_rule,
                "strategy_name": strategy_name,
                "strategy_family": _strategy_family(str(strategy_name)),
                "tenor_comparison_group": g["tenor_comparison_group"].iloc[0],
                "num_periods": int(len(g)),
                "selected_periods": int(len(selected)),
                "annualized_extrinsic_premium_yield": float(selected["extrinsic_premium_yield"].mean() * factor)
                if not selected.empty
                else np.nan,
                "average_total_premium_yield": float(selected["total_premium_yield"].mean()) if not selected.empty else np.nan,
                "average_extrinsic_premium_yield": float(selected["extrinsic_premium_yield"].mean())
                if not selected.empty
                else np.nan,
                "premium_capture_ratio": _premium_capture_ratio(selected),
                "payoff_return_mean": float(selected["option_payoff_return_at_expiry"].mean()) if not selected.empty else np.nan,
                "payoff_return_max": float(selected["option_payoff_return_at_expiry"].max()) if not selected.empty else np.nan,
                "assignment_rate": float(selected["assignment_flag"].fillna(0).astype(int).mean())
                if strategy_name != "BuyHold" and not selected.empty
                else np.nan,
                "downside_excess_mean": float(down["excess_return_vs_etf"].mean()) if not down.empty else np.nan,
                "downside_win_rate": float((down["strategy_period_return"] > down["etf_period_return"]).mean())
                if not down.empty
                else np.nan,
                "downside_cushion_ratio_mean": float(down["downside_cushion_ratio"].mean()) if not down.empty else np.nan,
                "downside_cushion_ratio_median": float(down["downside_cushion_ratio"].median()) if not down.empty else np.nan,
                "max_drawdown_improvement": base.get("max_drawdown_improvement", np.nan),
                "upside_cost_mean": upside_cost_mean,
                "protection_cost_ratio": protection_cost_ratio(upside_cost_mean, avg_downside_benefit),
            }
        )
    return _sort_21b(pd.DataFrame(rows))


def build_daily_mtm_stress_summary_1b(daily_mtm: pd.DataFrame) -> pd.DataFrame:
    """Summarize daily MTM and heuristic gamma stress for short-call overlays."""

    if daily_mtm.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for (etf_code, tenor_rule, strategy_name), g in daily_mtm.groupby(["etf_code", "tenor_rule", "strategy_name"]):
        work = g.copy()
        work["date"] = pd.to_datetime(work["date"])
        work = work.sort_values(["date", "period_index"] if "period_index" in work.columns else ["date"])
        day = work.groupby("date", as_index=False).tail(1).sort_values("date")
        nav = day["daily_mtm_nav"].astype(float)
        daily_return = nav.pct_change()
        underlying_return = day["underlying_price"].astype(float).pct_change() if "underlying_price" in day.columns else pd.Series(np.nan, index=day.index)
        loss = day["short_call_mtm_loss_return"].fillna(0.0).astype(float)
        p90_loss = float(loss.quantile(0.90)) if len(loss) else np.nan
        if "expiry_date" in day.columns:
            remaining_dte = (pd.to_datetime(day["expiry_date"]) - day["date"]).dt.days
        else:
            remaining_dte = pd.Series(np.nan, index=day.index)
        gamma_mask = ((remaining_dte <= 14) & (underlying_return.abs() > 0.02)) | (loss > p90_loss)
        stress_mask = loss > p90_loss if pd.notna(p90_loss) and p90_loss > 0 else loss > 0
        liability = day["option_liability_return"].fillna(0.0).astype(float) if "option_liability_return" in day.columns else pd.Series(0.0, index=day.index)
        rows.append(
            {
                "etf_code": etf_code,
                "tenor_rule": tenor_rule,
                "dte_label": tenor_rule,
                "strategy_name": strategy_name,
                "strategy_family": _strategy_family(str(strategy_name)),
                "tenor_comparison_group": day["tenor_comparison_group"].iloc[0],
                "daily_rows": int(len(day)),
                "daily_mtm_max_drawdown": max_drawdown_magnitude(nav),
                "max_short_call_mtm_loss": float(loss.max()) if len(loss) else np.nan,
                "average_short_call_mtm_loss": float(loss.mean()) if len(loss) else np.nan,
                "mtm_stress_days_count": int(stress_mask.sum()) if len(loss) else 0,
                "mtm_stress_days_ratio": float(stress_mask.mean()) if len(loss) else np.nan,
                "max_one_day_nav_loss": float(max(-daily_return.min(), 0.0)) if len(daily_return.dropna()) else np.nan,
                "short_call_liability_max": float(liability.max()) if len(liability) else np.nan,
                "short_call_liability_mean": float(liability.mean()) if len(liability) else np.nan,
                "gamma_stress_proxy": float(gamma_mask.mean()) if len(gamma_mask) else np.nan,
                "gamma_stress_proxy_count": int(gamma_mask.sum()) if len(gamma_mask) else 0,
                "gamma_stress_proxy_note": "remaining_dte<=14 and abs(etf_daily_return)>2%, or short_call_mtm_loss_return above group p90",
            }
        )
    return _sort_21b(pd.DataFrame(rows))


def build_rebound_event_summary(events: pd.DataFrame, daily_mtm: pd.DataFrame) -> pd.DataFrame:
    """Aggregate rebound truncation and event attribution diagnostics."""

    columns = [
        "etf_code",
        "tenor_rule",
        "strategy_name",
        "event_count",
        "missed_rebound_return_mean",
        "missed_rebound_return_max",
        "recovery_capture_mean",
        "recovery_capture_median",
        "recovery_capture_min",
        "payoff_return_mean_in_rebound",
        "max_short_call_mtm_loss_in_rebound",
        "policy_jump_event_excess_return",
        "policy_jump_event_missed_rebound",
    ]
    if events.empty:
        return pd.DataFrame(columns=columns)
    events = events.copy()
    if "tenor_rule" not in events.columns and "dte_label" in events.columns:
        events["tenor_rule"] = events["dte_label"]
    mtm = daily_mtm.copy()
    if not mtm.empty:
        mtm["date"] = pd.to_datetime(mtm["date"])
    rows: list[dict[str, Any]] = []
    for (etf_code, tenor_rule, strategy_name), g in events.groupby(["etf_code", "tenor_rule", "strategy_name"]):
        event_losses: list[float] = []
        if not mtm.empty:
            mtm_g = mtm[
                (mtm["etf_code"] == etf_code)
                & (mtm["tenor_rule"] == tenor_rule)
                & (mtm["strategy_name"] == strategy_name)
            ]
            for _, event in g.iterrows():
                win = mtm_g[
                    (mtm_g["date"] >= pd.Timestamp(event["event_date"]))
                    & (mtm_g["date"] <= pd.Timestamp(event["period_end_date"]))
                ]
                if not win.empty:
                    event_losses.append(float(win["short_call_mtm_loss_return"].fillna(0.0).max()))
        policy = g[g["policy_jump_like"].fillna(0).astype(int) == 1]
        rows.append(
            {
                "etf_code": etf_code,
                "tenor_rule": tenor_rule,
                "dte_label": tenor_rule,
                "strategy_name": strategy_name,
                "strategy_family": _strategy_family(str(strategy_name)),
                "event_count": int(len(g)),
                "missed_rebound_return_mean": float(g["missed_rebound_return"].mean()),
                "missed_rebound_return_max": float(g["missed_rebound_return"].max()),
                "recovery_capture_mean": float(g["recovery_capture"].mean()),
                "recovery_capture_median": float(g["recovery_capture"].median()),
                "recovery_capture_min": float(g["recovery_capture"].min()),
                "payoff_return_mean_in_rebound": float(g["payoff_return"].mean()) if "payoff_return" in g.columns else np.nan,
                "max_short_call_mtm_loss_in_rebound": max(event_losses) if event_losses else np.nan,
                "policy_jump_event_excess_return": float(policy["excess_return_vs_etf"].mean()) if not policy.empty else np.nan,
                "policy_jump_event_missed_rebound": float(policy["missed_rebound_return"].mean()) if not policy.empty else np.nan,
            }
        )
    return _sort_21b(pd.DataFrame(rows))


def _merge_on_keys(left: pd.DataFrame, right: pd.DataFrame) -> pd.DataFrame:
    if right.empty:
        return left
    keys = ["etf_code", "tenor_rule", "strategy_name"]
    cols = [col for col in right.columns if col not in left.columns or col in keys]
    return left.merge(right[cols], on=keys, how="left")


def build_full_account_metrics(
    premium: pd.DataFrame,
    standard: pd.DataFrame,
    coverage: pd.DataFrame,
    stress: pd.DataFrame,
    actual_dte: pd.DataFrame,
    rebound: pd.DataFrame,
) -> pd.DataFrame:
    out = premium.copy()
    out = _merge_on_keys(out, standard)
    out = _merge_on_keys(out, coverage)
    out = _merge_on_keys(out, stress)
    out = _merge_on_keys(out, actual_dte)
    out = _merge_on_keys(out, rebound)
    out["metric_scope"] = "full_account"
    return _sort_21b(out)


def _rank_pct(series: pd.Series, *, higher_is_better: bool) -> pd.Series:
    if series.dropna().empty:
        return pd.Series(0.0, index=series.index)
    return series.rank(method="average", pct=True, ascending=higher_is_better).fillna(0.0)


def build_candidate_ranking(full_metrics: pd.DataFrame) -> pd.DataFrame:
    """Rank comparable STC/DTE30/DTE60 candidates for diagnostic use only."""

    if full_metrics.empty:
        return pd.DataFrame()
    ranked = full_metrics[
        (full_metrics["effective_option_coverage_ratio"] >= 0.95)
        & (full_metrics["coverage_comparability_flag"] == "comparable_continuous_overlay")
        & (full_metrics["strategy_name"].isin(CORE_REPORT_STRATEGIES))
        & (full_metrics["tenor_rule"].isin(RANKING_TENORS))
    ].copy()
    if ranked.empty:
        return ranked
    rank_specs = {
        "annualized_extrinsic_premium_yield": ("annualized_extrinsic_premium_yield_rank", True),
        "downside_cushion_ratio_mean": ("downside_cushion_ratio_rank", True),
        "max_drawdown_improvement": ("max_drawdown_improvement_rank", True),
        "premium_capture_ratio": ("premium_capture_ratio_rank", True),
        "daily_mtm_max_drawdown": ("daily_mtm_max_drawdown_rank", False),
        "missed_rebound_return_mean": ("missed_rebound_return_rank", False),
    }
    for source_col, (rank_col, higher_is_better) in rank_specs.items():
        ranked[rank_col] = ranked.groupby("etf_code", group_keys=False)[source_col].apply(
            lambda s: _rank_pct(s, higher_is_better=higher_is_better)
        )
    ranked["score"] = (
        0.25 * ranked["annualized_extrinsic_premium_yield_rank"]
        + 0.20 * ranked["downside_cushion_ratio_rank"]
        + 0.20 * ranked["max_drawdown_improvement_rank"]
        + 0.15 * ranked["premium_capture_ratio_rank"]
        + 0.10 * ranked["daily_mtm_max_drawdown_rank"]
        + 0.10 * ranked["missed_rebound_return_rank"]
    )
    ranked["rank"] = ranked.groupby("etf_code")["score"].rank(method="first", ascending=False).astype(int)
    return ranked.sort_values(["etf_code", "rank"]).reset_index(drop=True)


def run_ver2_1b_short_tenor(base_config: ExperimentConfig, root: Path | None = None) -> Ver21bTables:
    """Run the ver2.1b short-tenor-priority continuous overlay diagnostic."""

    options_path = _candidate_delta_options_path(base_config, root)
    probe_config = replace(
        base_config,
        paths=replace(base_config.paths, options=options_path, output_dir=base_config.paths.output_dir / "ver2_1b_short_tenor_priority"),
    )
    from ver2_downside_protection.data_adapter import load_ver2_data

    data = load_ver2_data(probe_config)
    delta_available = _has_usable_delta(data.options)
    iv_available = _has_usable_iv(data.options)
    if not delta_available:
        LOGGER.warning("Delta data is unavailable; D50/D40/D30/D20 strategies will be skipped.")

    results, run_metadata = _run_tenor_backtests(
        base_config,
        data=data,
        data_options_path=options_path,
        delta_available=delta_available,
    )
    periods = attach_regime_features(_combine_result_attr(results, "periods"), data.prices)
    nav = _combine_result_attr(results, "nav")
    daily_mtm = _combine_result_attr(results, "daily_mtm")
    base_summary = _combine_result_attr(results, "summary")
    skipped = classify_skipped_periods_1b(_combine_result_attr(results, "skipped_periods"), data.options, data.prices)

    actual_dte = build_actual_dte_distribution(periods)
    coverage = build_effective_coverage_summary_1b(periods, daily_mtm, skipped, data.prices)
    standard = build_standard_performance_summary_1b(daily_mtm)
    premium = build_premium_downside_summary(periods, base_summary)
    stress = build_daily_mtm_stress_summary_1b(daily_mtm)
    events = build_down_then_rebound_events(periods)
    rebound = build_rebound_event_summary(events, daily_mtm)
    active = build_active_overlay_metrics(periods)
    if not active.empty and "tenor_rule" not in active.columns:
        active["tenor_rule"] = active["dte_label"]
    full = build_full_account_metrics(premium, standard, coverage, stress, actual_dte, rebound)
    ranking = build_candidate_ranking(full)
    metadata = {
        "experiment_name": "ver2_1b_short_tenor_priority",
        "version": "ver2.1b",
        "option_source": str(options_path),
        "delta_available": delta_available,
        "iv_available": iv_available,
        "policy_jump_like_usage": "ex_post_attribution_only",
        "down_then_rebound_usage": "ex_post_attribution_only",
        "sharpe_definition": "mean(daily_return) / std(daily_return) * sqrt(252), risk_free_rate=0",
        **run_metadata,
    }
    return Ver21bTables(
        periods=_sort_21b(periods, ["rebalance_date"]),
        nav=_sort_21b(nav, ["date"]),
        daily_mtm=_sort_21b(daily_mtm, ["date"]),
        skipped_periods=_sort_21b(skipped, ["rebalance_date"]),
        actual_dte_distribution=actual_dte,
        effective_coverage_summary=coverage,
        standard_performance_summary=standard,
        premium_downside_summary=premium,
        daily_mtm_stress_summary=stress,
        rebound_event_summary=rebound,
        full_account_metrics=full,
        active_overlay_metrics=_sort_21b(active),
        candidate_ranking=ranking,
        down_then_rebound_events=_sort_21b(events, ["event_date"]),
        metadata=metadata,
    )


def _write_csv(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def _format_percent(value: Any) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value):.2%}"


def _format_float(value: Any) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value):.3f}"


def _markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_No rows._"
    header = "| " + " | ".join(map(str, df.columns)) + " |"
    divider = "| " + " | ".join(["---"] * len(df.columns)) + " |"
    rows = ["| " + " | ".join(str(v) for v in row) + " |" for row in df.astype(str).values]
    return "\n".join([header, divider, *rows])


def _format_table(
    df: pd.DataFrame,
    *,
    percent_cols: list[str] | None = None,
    float_cols: list[str] | None = None,
    int_cols: list[str] | None = None,
) -> str:
    out = df.copy()
    for col in percent_cols or []:
        if col in out.columns:
            out[col] = out[col].map(_format_percent)
    for col in float_cols or []:
        if col in out.columns:
            out[col] = out[col].map(_format_float)
    for col in int_cols or []:
        if col in out.columns:
            out[col] = out[col].map(lambda value: "" if pd.isna(value) else str(int(value)))
    return _markdown_table(out)


def _top_candidates(ranking: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    if ranking.empty:
        return ranking.copy()
    return ranking.sort_values(["etf_code", "rank"]).groupby("etf_code", group_keys=False).head(n).reset_index(drop=True)


def _key_strength(row: pd.Series) -> str:
    candidates = {
        "annualized_extrinsic_premium_yield_rank": "extrinsic premium",
        "downside_cushion_ratio_rank": "downside cushion",
        "max_drawdown_improvement_rank": "drawdown control",
        "premium_capture_ratio_rank": "premium capture",
    }
    values = {label: float(row[col]) for col, label in candidates.items() if col in row and pd.notna(row[col])}
    return max(values.items(), key=lambda item: item[1])[0] if values else "balanced profile"


def _key_risk(row: pd.Series) -> str:
    note = str(row.get("actual_dte_distribution_note", ""))
    if "DTE30-like" in note:
        return "DTE30-like exposure"
    mtm = row.get("max_short_call_mtm_loss", np.nan)
    if pd.notna(mtm) and float(mtm) > 0.20:
        return "daily MTM pressure"
    missed = row.get("missed_rebound_return_mean", np.nan)
    if pd.notna(missed) and float(missed) > 0.04:
        return "rebound truncation"
    capture = row.get("premium_capture_ratio", np.nan)
    if pd.notna(capture) and float(capture) < 0.20:
        return "low premium capture"
    return "needs out-of-sample check"


def _actual_dte_report_table(actual_dte: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "etf_code",
        "tenor_rule",
        "strategy_name",
        "actual_dte_mean",
        "actual_dte_median",
        "actual_dte_min",
        "actual_dte_p25",
        "actual_dte_p75",
        "actual_dte_max",
        "actual_dte_distribution_note",
    ]
    data = actual_dte[
        actual_dte["tenor_rule"].isin(["STC_min7", "STC_min10", "STC_min14", "DTE30", "DTE60"])
        & actual_dte["strategy_name"].isin(["ATM_100"])
    ][[col for col in cols if col in actual_dte.columns]].copy()
    return data


def _executive_table(top: pd.DataFrame) -> pd.DataFrame:
    if top.empty:
        return pd.DataFrame()
    out = pd.DataFrame(
        {
            "ETF": top["etf_code"],
            "rank": top["rank"],
            "tenor_rule": top["tenor_rule"],
            "strategy_name": top["strategy_name"],
            "score": top["score"],
            "actual_dte_median": top["actual_dte_median"],
            "annualized_return": top["annualized_return_daily_nav"],
            "sharpe": top["sharpe_ratio_daily_nav"],
            "max_drawdown": top["max_drawdown_daily_nav"],
            "key_strength": top.apply(_key_strength, axis=1),
            "key_risk": top.apply(_key_risk, axis=1),
        }
    )
    return out


def write_readable_report(tables: Ver21bTables, report_path: Path) -> Path:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    top = _top_candidates(tables.candidate_ranking)
    actual_table = _actual_dte_report_table(tables.actual_dte_distribution)
    stc_actual = tables.actual_dte_distribution[
        tables.actual_dte_distribution["tenor_rule"].isin(["STC_min7", "STC_min10", "STC_min14"])
        & tables.actual_dte_distribution["strategy_name"].isin(CORE_REPORT_STRATEGIES)
    ]
    dte30_like = bool(stc_actual["actual_dte_distribution_note"].astype(str).str.contains("DTE30-like").any()) if not stc_actual.empty else False
    dte_note = (
        "当前 STC 规则出现 DTE30-like exposure 提示：短期限优先在当前样本中并未稳定形成独立的短期限暴露。"
        if dte30_like
        else "当前 STC 规则在部分组合中实现了比 DTE30 更短的实际期限，但仍需结合覆盖率和 MTM 风险解释。"
    )
    performance = top[
        [
            "etf_code",
            "tenor_rule",
            "strategy_name",
            "annualized_return_daily_nav",
            "annualized_volatility_daily_nav",
            "sharpe_ratio_daily_nav",
            "sortino_ratio_daily_nav",
            "calmar_ratio_daily_nav",
            "max_drawdown_daily_nav",
        ]
    ].copy() if not top.empty else pd.DataFrame()
    premium = top[
        [
            "etf_code",
            "tenor_rule",
            "strategy_name",
            "annualized_extrinsic_premium_yield",
            "premium_capture_ratio",
            "downside_cushion_ratio_mean",
            "max_drawdown_improvement",
        ]
    ].copy() if not top.empty else pd.DataFrame()
    risk = top[
        [
            "etf_code",
            "tenor_rule",
            "strategy_name",
            "daily_mtm_max_drawdown",
            "max_short_call_mtm_loss",
            "missed_rebound_return_mean",
            "recovery_capture_mean",
        ]
    ].copy() if not top.empty else pd.DataFrame()
    text = f"""# ver2.1b｜短期限优先连续覆盖诊断实验

## 1. 实验定位

ver2.1b 是机制诊断，不是最终动态策略。本版本只检验 short-tenor-priority continuous covered call 是否真正可执行，以及它是否改善外在价值权利金收入、下跌保护和回撤控制。

所有排序只用于候选观察，不代表最终最优。`policy_jump_like` 与 `down_then_rebound` 只用于事后归因，不用于选券或入场信号。Sharpe、Sortino、Calmar 均基于 daily MTM NAV 计算，risk-free rate 暂设为 0。

## 2. 策略定义

- STC_min7 / STC_min10 / STC_min14：在 rebalance_date 当日可见到期日中，先保留 actual_dte >= 最低阈值的 call，再选择 actual_dte 最小的到期日，并在该到期日内按 ATM / delta / OTM 规则选券。
- DTE30 benchmark：target_dte=30, window=20-45，是当前最干净的连续覆盖基准。
- DTE60 benchmark：target_dte=60, window=50-75，是低展期频率对照。
- DTE45 仅作中间期限 appendix。
- DTE14_strict_window 仅作 near-expiry overlay appendix，不进入主 ranking。

## 3. Actual DTE 分布

{dte_note}

{_format_table(actual_table, float_cols=["actual_dte_mean", "actual_dte_median", "actual_dte_min", "actual_dte_p25", "actual_dte_p75", "actual_dte_max"])}

## 4. Executive candidate table

{_format_table(
        _executive_table(top),
        percent_cols=["annualized_return", "max_drawdown"],
        float_cols=["score", "actual_dte_median", "sharpe"],
        int_cols=["rank"],
    )}

## 5. Performance table

{_format_table(
        performance,
        percent_cols=["annualized_return_daily_nav", "annualized_volatility_daily_nav", "max_drawdown_daily_nav"],
        float_cols=["sharpe_ratio_daily_nav", "sortino_ratio_daily_nav", "calmar_ratio_daily_nav"],
    )}

## 6. Premium and downside table

{_format_table(
        premium,
        percent_cols=[
            "annualized_extrinsic_premium_yield",
            "premium_capture_ratio",
            "downside_cushion_ratio_mean",
            "max_drawdown_improvement",
        ],
    )}

## 7. MTM and rebound risk table

{_format_table(
        risk,
        percent_cols=[
            "daily_mtm_max_drawdown",
            "max_short_call_mtm_loss",
            "missed_rebound_return_mean",
            "recovery_capture_mean",
        ],
    )}

## 8. 初步机制结论

1. 是否真正实现短 DTE，需要首先看 actual_dte_median 和分布桶；若 STC 大量落在 25-35 天，就只能解释为 DTE30-like exposure。
2. STC 若提高 annualized extrinsic premium yield，也必须同时观察 premium capture、daily MTM stress 和 missed rebound。
3. 与 DTE30 相比，STC 的独立价值只在“实际 DTE 明显更短且风险没有同步恶化”时成立。
4. 与 DTE60 相比，STC 更像提高展期频率和权利金周转的实验；DTE60 更像低频、低反弹暴露对照。
5. 510300 与 510050 的差异应通过候选表和风险表分别判断，不应合并成单一结论。

## 9. 局限性

1. 中国 ETF 期权到期日离散，短期限优先不等于固定 DTE14。
2. 本版本仍只包含 510300 与 510050。
3. 所有规则仍是静态 overlay，不是最终动态策略。
4. `policy_jump_like` 和 `down_then_rebound` 只做事后归因。
5. 交易成本仍需进一步做 bid/ask sensitivity。
6. 后续需要结合状态变量进入 ver2.2 动态规则原型。

## 10. 下一步建议

- Core continuous benchmark: DTE30 ATM / D50。
- Short-tenor priority candidate: STC_min7 或 STC_min10 的 ATM / D50 / D40，仅在 actual DTE 真正更短时进入 ver2.2。
- Low rebound-truncation candidate: DTE60 ATM / D50。
- Upside-balanced candidate: D40 / OTM2，尤其用于观察 510300。

## 完整输出

- `ver2_1b_actual_dte_distribution.csv`
- `ver2_1b_effective_coverage_summary.csv`
- `ver2_1b_standard_performance_summary.csv`
- `ver2_1b_premium_downside_summary.csv`
- `ver2_1b_daily_mtm_stress_summary.csv`
- `ver2_1b_rebound_event_summary.csv`
- `ver2_1b_full_account_metrics.csv`
- `ver2_1b_active_overlay_metrics.csv`
- `ver2_1b_candidate_ranking.csv`
"""
    report_path.write_text(text, encoding="utf-8")
    return report_path


def _plot_metric_bar(
    df: pd.DataFrame,
    *,
    metric: str,
    title: str,
    output_path: Path,
    percent: bool = True,
) -> None:
    import matplotlib.pyplot as plt

    data = df[
        df["tenor_rule"].isin(["STC_min7", "STC_min10", "STC_min14", "DTE30", "DTE60"])
        & df["strategy_name"].isin(CORE_REPORT_STRATEGIES)
    ].copy()
    if data.empty or metric not in data.columns:
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    labels = data["etf_code"].astype(str) + " " + data["tenor_rule"].astype(str) + " " + data["strategy_name"].astype(str)
    values = data[metric].astype(float) * (100 if percent else 1)
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.bar(np.arange(len(data)), values)
    ax.set_xticks(np.arange(len(data)))
    ax.set_xticklabels(labels, rotation=75, ha="right", fontsize=8)
    ax.set_title(title)
    ax.set_ylabel(f"{metric} ({'%' if percent else 'value'})")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def write_figures(tables: Ver21bTables, output_dir: Path) -> dict[str, Path]:
    import matplotlib.pyplot as plt

    fig_dir = output_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    selected_periods = tables.periods[
        (tables.periods["option_selected_flag"].fillna(0).astype(int) == 1)
        & (tables.periods["strategy_name"].isin(CORE_REPORT_STRATEGIES))
        & (tables.periods["tenor_rule"].isin(["STC_min7", "STC_min10", "STC_min14", "DTE30", "DTE60"]))
    ].copy()
    if not selected_periods.empty:
        p = fig_dir / "actual_dte_distribution_by_tenor.png"
        fig, ax = plt.subplots(figsize=(10, 5))
        for tenor, g in selected_periods.groupby("tenor_rule"):
            ax.hist(g["actual_dte"].dropna().astype(float), bins=20, alpha=0.45, label=tenor)
        ax.set_title("Actual DTE distribution by tenor")
        ax.set_xlabel("Actual DTE")
        ax.set_ylabel("Count")
        ax.legend(fontsize=8)
        ax.grid(axis="y", alpha=0.25)
        fig.tight_layout()
        fig.savefig(p, dpi=160)
        plt.close(fig)
        paths["actual_dte_distribution_by_tenor"] = p

        p = fig_dir / "actual_dte_boxplot_by_tenor.png"
        fig, ax = plt.subplots(figsize=(9, 5))
        tenors = [t for t in ["STC_min7", "STC_min10", "STC_min14", "DTE30", "DTE60"] if t in set(selected_periods["tenor_rule"])]
        ax.boxplot([selected_periods.loc[selected_periods["tenor_rule"] == t, "actual_dte"].dropna() for t in tenors], labels=tenors)
        ax.set_title("Actual DTE boxplot by tenor")
        ax.set_ylabel("Actual DTE")
        ax.grid(axis="y", alpha=0.25)
        fig.tight_layout()
        fig.savefig(p, dpi=160)
        plt.close(fig)
        paths["actual_dte_boxplot_by_tenor"] = p

    metric_plots = [
        (tables.premium_downside_summary, "annualized_extrinsic_premium_yield", "Annualized extrinsic premium yield", "annualized_extrinsic_premium_yield_by_tenor_strategy.png"),
        (tables.premium_downside_summary, "downside_cushion_ratio_mean", "Downside cushion by tenor/strategy", "downside_cushion_by_tenor_strategy.png"),
        (tables.standard_performance_summary, "sharpe_ratio_daily_nav", "Sharpe by tenor/strategy", "sharpe_by_tenor_strategy.png", False),
        (tables.standard_performance_summary, "max_drawdown_daily_nav", "Max drawdown by tenor/strategy", "max_drawdown_by_tenor_strategy.png"),
        (tables.daily_mtm_stress_summary, "max_short_call_mtm_loss", "Daily MTM stress by tenor/strategy", "daily_mtm_stress_by_tenor_strategy.png"),
        (tables.rebound_event_summary, "missed_rebound_return_mean", "Missed rebound by tenor/strategy", "missed_rebound_by_tenor_strategy.png"),
        (tables.effective_coverage_summary, "effective_option_coverage_ratio", "Effective coverage by tenor", "effective_coverage_by_tenor.png"),
    ]
    for item in metric_plots:
        df, metric, title, filename, *rest = item
        p = fig_dir / filename
        _plot_metric_bar(df, metric=metric, title=title, output_path=p, percent=rest[0] if rest else True)
        if p.exists():
            paths[filename.removesuffix(".png")] = p

    if not tables.candidate_ranking.empty:
        p = fig_dir / "candidate_ranking_top5_by_etf.png"
        top = _top_candidates(tables.candidate_ranking)
        labels = top["etf_code"].astype(str) + " " + top["tenor_rule"].astype(str) + " " + top["strategy_name"].astype(str)
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.bar(np.arange(len(top)), top["score"].astype(float))
        ax.set_xticks(np.arange(len(top)))
        ax.set_xticklabels(labels, rotation=75, ha="right", fontsize=8)
        ax.set_title("Candidate ranking top 5 by ETF")
        ax.set_ylabel("diagnostic score")
        ax.grid(axis="y", alpha=0.25)
        fig.tight_layout()
        fig.savefig(p, dpi=160)
        plt.close(fig)
        paths["candidate_ranking_top5_by_etf"] = p
    return paths


def write_ver2_1b_outputs(base_config: ExperimentConfig, tables: Ver21bTables) -> dict[str, Path]:
    output_dir = base_config.paths.output_dir / "ver2_1b_short_tenor_priority"
    paths = {
        "actual_dte_distribution": _write_csv(tables.actual_dte_distribution, output_dir / "ver2_1b_actual_dte_distribution.csv"),
        "effective_coverage_summary": _write_csv(tables.effective_coverage_summary, output_dir / "ver2_1b_effective_coverage_summary.csv"),
        "standard_performance_summary": _write_csv(tables.standard_performance_summary, output_dir / "ver2_1b_standard_performance_summary.csv"),
        "premium_downside_summary": _write_csv(tables.premium_downside_summary, output_dir / "ver2_1b_premium_downside_summary.csv"),
        "daily_mtm_stress_summary": _write_csv(tables.daily_mtm_stress_summary, output_dir / "ver2_1b_daily_mtm_stress_summary.csv"),
        "rebound_event_summary": _write_csv(tables.rebound_event_summary, output_dir / "ver2_1b_rebound_event_summary.csv"),
        "full_account_metrics": _write_csv(tables.full_account_metrics, output_dir / "ver2_1b_full_account_metrics.csv"),
        "active_overlay_metrics": _write_csv(tables.active_overlay_metrics, output_dir / "ver2_1b_active_overlay_metrics.csv"),
        "candidate_ranking": _write_csv(tables.candidate_ranking, output_dir / "ver2_1b_candidate_ranking.csv"),
        "periods": _write_csv(tables.periods, output_dir / "ver2_1b_periods.csv"),
        "daily_mtm": _write_csv(tables.daily_mtm, output_dir / "ver2_1b_daily_mtm.csv"),
        "skipped_periods": _write_csv(tables.skipped_periods, output_dir / "ver2_1b_skipped_periods.csv"),
        "down_then_rebound_events": _write_csv(tables.down_then_rebound_events, output_dir / "ver2_1b_down_then_rebound_events.csv"),
    }
    manifest_path = output_dir / "ver2_1b_manifest.json"
    manifest_path.write_text(json.dumps(tables.metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    paths["manifest"] = manifest_path
    paths.update({f"figure_{key}": value for key, value in write_figures(tables, output_dir).items()})
    paths["readable_report"] = write_readable_report(
        tables,
        output_dir / "reports" / "ver2_1b_short_tenor_priority_readable.md",
    )
    return paths
