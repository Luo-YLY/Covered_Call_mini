from __future__ import annotations

from dataclasses import dataclass, replace
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ver2_downside_protection.config import BacktestConfig, ExperimentConfig, PathsConfig, StrategyConfig
from ver2_downside_protection.data_adapter import Ver2DataBundle, load_ver2_data
from ver2_downside_protection.metrics import annual_factor, annualized_return, max_drawdown_magnitude
from ver2_downside_protection.premium_income_defensive import add_premium_decomposition
from ver2_downside_protection.strategy_engine import Ver2BacktestResult, run_ver2_backtest

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class DteSpec:
    label: str
    target_dte: int
    min_days_to_expiry: int
    max_days_to_expiry: int
    dte_fallback_mode: str = "strict_window"


DTE_SPECS: tuple[DteSpec, ...] = (
    DteSpec("DTE14_strict_window", 14, 7, 21, "strict_window"),
    DteSpec("DTE14_nearest_continuous", 14, 7, 21, "nearest_available"),
    DteSpec("DTE30", 30, 20, 45),
    DteSpec("DTE45", 45, 35, 60),
    DteSpec("DTE60", 60, 50, 75),
)

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

STRATEGY_ORDER_21 = {
    "BuyHold": 0,
    "ATM_100": 1,
    "OTM2_100": 2,
    "OTM5_100": 3,
    "D50_100": 4,
    "D40_100": 5,
    "D30_100": 6,
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

REGIME_BUCKET_COLUMNS = [
    "trend_20d_bucket",
    "drawdown_bucket",
    "rv_20d_bucket",
    "iv_percentile_bucket",
    "post_drawdown_rebound_risk_bucket",
    "policy_jump_like_bucket",
]

DTE_ORDER = {spec.label: idx for idx, spec in enumerate(DTE_SPECS)}
TRADING_DAYS_PER_YEAR = 252.0
SHORTLIST_ALLOWED_STRATEGIES = {"ATM_100", "D50_100", "D40_100", "OTM2_100"}
MAIN_REPORT_DTES = {"DTE30", "DTE60"}


@dataclass(frozen=True)
class Ver21Tables:
    periods: pd.DataFrame
    nav: pd.DataFrame
    daily_mtm: pd.DataFrame
    summary: pd.DataFrame
    regime_conditional_performance: pd.DataFrame
    down_then_rebound_events: pd.DataFrame
    dte_robustness_ranking: pd.DataFrame
    daily_mtm_stress_summary: pd.DataFrame
    effective_coverage_summary: pd.DataFrame
    active_overlay_metrics: pd.DataFrame
    standard_performance_summary: pd.DataFrame
    candidate_shortlist: pd.DataFrame
    skipped_periods: pd.DataFrame
    metadata: dict[str, Any]


def _sort_ver21(df: pd.DataFrame, extra_cols: list[str] | None = None) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    out = df.copy()
    out["_strategy_order"] = out.get("strategy_name", pd.Series(index=out.index, dtype=object)).map(
        STRATEGY_ORDER_21
    ).fillna(999)
    if "dte_label" in out.columns:
        out["_dte_order"] = out["dte_label"].map(DTE_ORDER).fillna(999)
    cols = [col for col in ["etf_code", "_dte_order", "dte_label", "_strategy_order", "strategy_name"] if col in out.columns]
    if extra_cols:
        cols.extend([col for col in extra_cols if col in out.columns])
    return out.sort_values(cols).drop(columns=["_strategy_order", "_dte_order"], errors="ignore").reset_index(drop=True)


def _infer_repo_root(config: ExperimentConfig) -> Path:
    price_path = Path(config.paths.etf_prices).resolve()
    if len(price_path.parents) >= 3 and price_path.parents[1].name == "data":
        return price_path.parents[2]
    return Path.cwd()


def _candidate_delta_options_path(config: ExperimentConfig, root: Path | None = None) -> Path:
    repo_root = Path(root) if root is not None else _infer_repo_root(config)
    candidate = repo_root / "data" / "source" / "delta_enriched_options.csv"
    return candidate if candidate.exists() else config.paths.options


def _has_usable_delta(options: pd.DataFrame) -> bool:
    for col in ["model_delta", "delta"]:
        if col in options.columns and options[col].notna().any():
            return True
    return False


def _has_usable_iv(options: pd.DataFrame) -> bool:
    for col in ["model_iv", "implied_vol", "raw_implied_vol"]:
        if col in options.columns and options[col].notna().any():
            return True
    return False


def _strategy_family(strategy_name: str) -> str:
    if strategy_name == "BuyHold":
        return "benchmark"
    if strategy_name in TARGET_DELTA:
        return "delta"
    return "moneyness"


def _strategy_configs(delta_available: bool) -> tuple[StrategyConfig, ...]:
    return MONEYNESS_STRATEGIES + (DELTA_STRATEGIES if delta_available else tuple())


def _dte_comparison_group(dte_label: str) -> str:
    if dte_label == "DTE14_strict_window":
        return "near_expiry_overlay_strategy"
    if dte_label == "DTE14_nearest_continuous":
        return "continuous_near_expiry_comparison"
    return "continuous_covered_call_comparison"


def _config_for_dte(
    base_config: ExperimentConfig,
    *,
    spec: DteSpec,
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
        experiment_name="ver2_1_non_itm_dte_regime_diagnostic",
        paths=paths,
        backtest=backtest,
        strategies=strategies,
    )


def _tag_result_frame(df: pd.DataFrame, spec: DteSpec, option_source: Path) -> pd.DataFrame:
    out = df.copy()
    out["version"] = "ver2.1"
    out["dte_label"] = spec.label
    out["target_dte"] = spec.target_dte
    out["dte_window_min"] = spec.min_days_to_expiry
    out["dte_window_max"] = spec.max_days_to_expiry
    out["dte_fallback_mode"] = spec.dte_fallback_mode
    out["dte_comparison_group"] = _dte_comparison_group(spec.label)
    out["option_source"] = str(option_source)
    if "strategy_name" in out.columns:
        out["strategy_family"] = out["strategy_name"].map(_strategy_family)
        out["target_moneyness_spec"] = out["strategy_name"].map(TARGET_MONEYNESS)
        out["target_delta"] = out["strategy_name"].map(TARGET_DELTA)
    return out


def _run_dte_backtests(
    base_config: ExperimentConfig,
    *,
    data: Ver2DataBundle,
    output_dir: Path,
    options_path: Path,
    delta_available: bool,
) -> tuple[list[Ver2BacktestResult], dict[str, Any]]:
    strategies = _strategy_configs(delta_available)
    results: list[Ver2BacktestResult] = []
    for spec in DTE_SPECS:
        LOGGER.info(
            "Running ver2.1 %s with DTE window %s-%s.",
            spec.label,
            spec.min_days_to_expiry,
            spec.max_days_to_expiry,
        )
        config = _config_for_dte(
            base_config,
            spec=spec,
            strategies=strategies,
            output_dir=output_dir,
            options_path=options_path,
        )
        result = run_ver2_backtest(config, data=data)
        result = replace(
            result,
            periods=_tag_result_frame(result.periods, spec, options_path),
            nav=_tag_result_frame(result.nav, spec, options_path),
            daily_mtm=_tag_result_frame(result.daily_mtm, spec, options_path),
            summary=_tag_result_frame(result.summary, spec, options_path),
            skipped_periods=_tag_result_frame(result.skipped_periods, spec, options_path),
        )
        results.append(result)
    metadata = {
        "strategies": [strategy.name for strategy in strategies],
        "delta_strategies_enabled": delta_available,
        "dte_specs": [spec.__dict__ for spec in DTE_SPECS],
    }
    return results, metadata


def _combine_result_attr(results: list[Ver2BacktestResult], attr: str) -> pd.DataFrame:
    frames = [getattr(result, attr) for result in results if not getattr(result, attr).empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _dte_spec_lookup() -> dict[str, DteSpec]:
    return {spec.label: spec for spec in DTE_SPECS}


def classify_skipped_periods(skipped: pd.DataFrame, options: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """Split raw option-selection failures into ver2.1 diagnostic categories."""

    if skipped.empty:
        out = skipped.copy()
        out["skip_category"] = pd.Series(dtype=object)
        return out

    out = skipped.copy()
    out["rebalance_date"] = pd.to_datetime(out["rebalance_date"])
    out["etf_code"] = out["etf_code"].astype(str).str.zfill(6)
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
    if not calls.empty:
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
    else:
        stats = pd.DataFrame(
            columns=[
                "etf_code",
                "rebalance_date",
                "option_call_chain_rows",
                "available_expiry_count",
                "available_dte_min",
                "available_dte_max",
            ]
        )
    out = out.merge(stats, on=["etf_code", "rebalance_date"], how="left")
    out["option_call_chain_rows"] = out["option_call_chain_rows"].fillna(0).astype(int)
    out["available_expiry_count"] = out["available_expiry_count"].fillna(0).astype(int)

    spec_lookup = _dte_spec_lookup()
    out["_window_min"] = out["dte_label"].map(lambda label: spec_lookup[str(label)].min_days_to_expiry)
    out["_window_max"] = out["dte_label"].map(lambda label: spec_lookup[str(label)].max_days_to_expiry)
    out["skip_category"] = "other_selection_failure"

    terminal = out["_days_to_sample_end"] < out["_window_min"]
    no_chain = (out["selection_reason"] == "no_chain_on_trade_date") | (out["option_call_chain_rows"] <= 0)
    no_window = (out["selection_reason"] == "no_contract_in_dte_window") & (~terminal) & (~no_chain)

    out.loc[terminal, "skip_category"] = "terminal_insufficient_horizon"
    out.loc[no_chain & (~terminal), "skip_category"] = "data_missing_or_chain_unavailable"
    out.loc[no_window, "skip_category"] = "no_eligible_expiry_in_window"
    out["selection_reason_reclassified"] = out["skip_category"]
    return out.drop(columns=["_last_price_date", "_days_to_sample_end", "_window_min", "_window_max"])


def _terminal_insufficient_horizon_count(period_g: pd.DataFrame, prices: pd.DataFrame) -> int:
    if period_g.empty:
        return 0
    etf_code = str(period_g["etf_code"].iloc[0]).zfill(6)
    dte_label = str(period_g["dte_label"].iloc[0])
    last_price_date = prices.loc[prices["etf_code"] == etf_code, "date"].max()
    if pd.isna(last_price_date):
        return 0
    spec = _dte_spec_lookup().get(dte_label)
    if spec is None:
        return 0
    last_period_end = pd.to_datetime(period_g["period_end_date"]).max()
    remaining_days = (pd.Timestamp(last_price_date) - pd.Timestamp(last_period_end)).days
    return int(last_period_end < pd.Timestamp(last_price_date) and remaining_days < spec.min_days_to_expiry)


def build_effective_coverage_summary(
    periods: pd.DataFrame,
    daily_mtm: pd.DataFrame,
    skipped: pd.DataFrame,
    prices: pd.DataFrame,
) -> pd.DataFrame:
    """Measure how much of each DTE path actually carries a short call."""

    if periods.empty:
        return pd.DataFrame()

    skip_counts = pd.DataFrame()
    if not skipped.empty and "skip_category" in skipped.columns:
        skip_counts = (
            skipped.groupby(["etf_code", "dte_label", "strategy_name", "skip_category"])
            .size()
            .unstack("skip_category", fill_value=0)
            .reset_index()
        )

    mtm_lookup = {
        (str(etf), str(dte), str(strategy)): g.copy()
        for (etf, dte, strategy), g in daily_mtm.groupby(["etf_code", "dte_label", "strategy_name"])
    }
    rows: list[dict[str, Any]] = []
    for (etf_code, dte_label, strategy_name), period_g in periods.groupby(["etf_code", "dte_label", "strategy_name"]):
        if strategy_name == "BuyHold":
            continue
        period_g = period_g.sort_values("rebalance_date")
        mtm_g = mtm_lookup.get((str(etf_code), str(dte_label), str(strategy_name)), pd.DataFrame())
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

        selected = period_g[period_g["option_selected_flag"].fillna(0).astype(int) == 1]
        skipped_period_count = int((period_g["option_selected_flag"].fillna(0).astype(int) == 0).sum())
        terminal_count = _terminal_insufficient_horizon_count(period_g, prices)
        rows.append(
            {
                "etf_code": etf_code,
                "dte_label": dte_label,
                "strategy_name": strategy_name,
                "strategy_family": _strategy_family(str(strategy_name)),
                "dte_comparison_group": _dte_comparison_group(str(dte_label)),
                "total_backtest_days": total_days,
                "active_short_call_days": active_days,
                "etf_only_gap_days": int(max(total_days - active_days, 0)),
                "effective_option_coverage_ratio": active_days / total_days if total_days else np.nan,
                "valid_option_cycle_count": int(len(selected)),
                "skipped_period_count": skipped_period_count,
                "no_eligible_expiry_count": 0,
                "terminal_insufficient_horizon_count": terminal_count,
                "data_missing_or_chain_unavailable_count": 0,
                "other_selection_failure_count": 0,
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    if not skip_counts.empty:
        rename = {
            "no_eligible_expiry_in_window": "no_eligible_expiry_count",
            "terminal_insufficient_horizon": "terminal_insufficient_horizon_count",
            "data_missing_or_chain_unavailable": "data_missing_or_chain_unavailable_count",
            "other_selection_failure": "other_selection_failure_count",
        }
        skip_counts = skip_counts.rename(columns=rename)
        out = out.drop(columns=[col for col in rename.values() if col in out.columns and col != "terminal_insufficient_horizon_count"])
        out = out.merge(skip_counts, on=["etf_code", "dte_label", "strategy_name"], how="left", suffixes=("", "_skip"))
        if "terminal_insufficient_horizon_count_skip" in out.columns:
            out["terminal_insufficient_horizon_count"] = (
                out["terminal_insufficient_horizon_count"].fillna(0)
                + out["terminal_insufficient_horizon_count_skip"].fillna(0)
            )
            out = out.drop(columns=["terminal_insufficient_horizon_count_skip"])
    for col in [
        "no_eligible_expiry_count",
        "data_missing_or_chain_unavailable_count",
        "other_selection_failure_count",
        "terminal_insufficient_horizon_count",
    ]:
        if col not in out.columns:
            out[col] = 0
        out[col] = out[col].fillna(0).astype(int)
    return _sort_ver21(out)


def build_active_overlay_metrics(periods: pd.DataFrame) -> pd.DataFrame:
    """Compute metrics only on periods with an active short-call overlay."""

    if periods.empty:
        return pd.DataFrame()
    decomposed = add_premium_decomposition(periods)
    rows: list[dict[str, Any]] = []
    for (etf_code, dte_label, strategy_name), g in decomposed.groupby(["etf_code", "dte_label", "strategy_name"]):
        if strategy_name == "BuyHold":
            continue
        selected = g[g["option_selected_flag"].fillna(0).astype(int) == 1].sort_values("rebalance_date")
        if selected.empty:
            rows.append(
                {
                    "etf_code": etf_code,
                    "dte_label": dte_label,
                    "strategy_name": strategy_name,
                    "strategy_family": _strategy_family(str(strategy_name)),
                    "dte_comparison_group": _dte_comparison_group(str(dte_label)),
                    "metric_scope": "active_overlay",
                    "active_option_cycle_count": 0,
                }
            )
            continue
        factor = annual_factor(selected)
        returns = selected["strategy_period_return"].astype(float)
        down = selected[selected["etf_period_return"] < 0]
        up = selected[selected["etf_period_return"] > 0]
        active_nav = (1.0 + returns).cumprod()
        rows.append(
            {
                "etf_code": etf_code,
                "dte_label": dte_label,
                "strategy_name": strategy_name,
                "strategy_family": _strategy_family(str(strategy_name)),
                "dte_comparison_group": _dte_comparison_group(str(dte_label)),
                "metric_scope": "active_overlay",
                "active_option_cycle_count": int(len(selected)),
                "active_overlay_cumulative_return": float((1.0 + returns).prod() - 1.0),
                "active_overlay_annualized_return": annualized_return(returns, factor),
                "active_overlay_max_drawdown": max_drawdown_magnitude(active_nav),
                "active_overlay_annualized_extrinsic_premium_yield": float(
                    selected["extrinsic_premium_yield"].mean() * factor
                ),
                "active_overlay_premium_capture_ratio": _premium_capture_ratio(selected),
                "active_overlay_payoff_return_mean": float(selected["option_payoff_return_at_expiry"].mean()),
                "active_overlay_downside_excess_mean": float(down["excess_return_vs_etf"].mean())
                if not down.empty
                else np.nan,
                "active_overlay_downside_cushion_ratio_mean": float(down["downside_cushion_ratio"].mean())
                if not down.empty
                else np.nan,
                "active_overlay_upside_cost_mean": float(up["upside_cost"].mean()) if not up.empty else np.nan,
            }
        )
    return _sort_ver21(pd.DataFrame(rows))


def _state_features(prices: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for etf_code, g in prices.sort_values(["etf_code", "date"]).groupby("etf_code"):
        out = g[["date", "etf_code", "adj_close"]].copy()
        close = out["adj_close"].astype(float)
        daily_ret = close.pct_change()
        out["trend_5d"] = close / close.shift(5) - 1.0
        out["trend_20d"] = close / close.shift(20) - 1.0
        out["trend_60d"] = close / close.shift(60) - 1.0
        out["ma_gap_20"] = close / close.rolling(20, min_periods=5).mean() - 1.0
        out["ma_gap_60"] = close / close.rolling(60, min_periods=20).mean() - 1.0
        rolling_high = close.rolling(252, min_periods=20).max()
        out["drawdown_from_rolling_high"] = close / rolling_high - 1.0
        out["rv_20d"] = daily_ret.rolling(20, min_periods=10).std(ddof=1) * np.sqrt(252.0)
        out["rv_60d"] = daily_ret.rolling(60, min_periods=20).std(ddof=1) * np.sqrt(252.0)
        out["post_drawdown_rebound_risk"] = (
            (out["drawdown_from_rolling_high"] <= -0.08)
            & (out["trend_5d"] > 0.0)
            & (out["trend_20d"] > -0.03)
        ).astype(int)
        rows.append(out.drop(columns=["adj_close"]))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _expanding_percentile(values: pd.Series) -> pd.Series:
    result: list[float] = []
    history: list[float] = []
    for value in values:
        if pd.isna(value):
            result.append(np.nan)
            continue
        numeric = float(value)
        history.append(numeric)
        result.append(float(np.mean(np.asarray(history) <= numeric)))
    return pd.Series(result, index=values.index, dtype=float)


def _bucket_by_tercile(series: pd.Series) -> pd.Series:
    out = pd.Series("unavailable", index=series.index, dtype=object)
    valid = series.dropna()
    if valid.empty:
        return out
    ranks = valid.rank(method="average", pct=True)
    out.loc[ranks.index] = np.select(
        [ranks <= 1.0 / 3.0, ranks <= 2.0 / 3.0],
        ["low", "mid"],
        default="high",
    )
    return out


def attach_regime_features(periods: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """Attach entry-date state variables to period rows without using future data."""

    if periods.empty:
        return periods.copy()
    features = _state_features(prices)
    out = periods.copy()
    out["rebalance_date"] = pd.to_datetime(out["rebalance_date"])
    features["date"] = pd.to_datetime(features["date"])
    out = out.merge(
        features,
        left_on=["etf_code", "rebalance_date"],
        right_on=["etf_code", "date"],
        how="left",
    ).drop(columns=["date"], errors="ignore")

    out["iv_at_entry"] = out["selected_iv"] if "selected_iv" in out.columns else np.nan
    out["iv_percentile"] = (
        out.sort_values(["etf_code", "strategy_name", "dte_label", "rebalance_date"])
        .groupby(["etf_code", "strategy_name", "dte_label"], group_keys=False)["iv_at_entry"]
        .apply(_expanding_percentile)
        .reindex(out.index)
    )
    out["iv_minus_rv"] = out["iv_at_entry"] - out["rv_20d"]

    period_days = (
        pd.to_datetime(out["period_end_date"]) - pd.to_datetime(out["rebalance_date"])
    ).dt.days.clip(lower=1)
    rv_jump_threshold = 2.0 * out["rv_20d"].fillna(0.0) * np.sqrt(period_days / 365.0)
    hard_jump = out["etf_period_return"] >= np.maximum(0.08, rv_jump_threshold)
    policy_window = (
        (pd.to_datetime(out["rebalance_date"]) <= pd.Timestamp("2024-10-08"))
        & (pd.to_datetime(out["period_end_date"]) >= pd.Timestamp("2024-09-24"))
    )
    out["policy_jump_like"] = (hard_jump | policy_window).astype(int)

    out["trend_20d_bucket"] = np.select(
        [out["trend_20d"] <= -0.03, out["trend_20d"] >= 0.03],
        ["down", "up"],
        default="flat",
    )
    out.loc[out["trend_20d"].isna(), "trend_20d_bucket"] = "unavailable"
    out["drawdown_bucket"] = np.select(
        [out["drawdown_from_rolling_high"] <= -0.08, out["drawdown_from_rolling_high"] <= -0.03],
        ["deep_drawdown", "mild_drawdown"],
        default="near_high",
    )
    out.loc[out["drawdown_from_rolling_high"].isna(), "drawdown_bucket"] = "unavailable"
    out["rv_20d_bucket"] = (
        out.groupby("etf_code", group_keys=False)["rv_20d"].apply(_bucket_by_tercile).reindex(out.index)
    )
    out["iv_percentile_bucket"] = np.select(
        [out["iv_percentile"] <= 1.0 / 3.0, out["iv_percentile"] <= 2.0 / 3.0],
        ["low", "mid"],
        default="high",
    )
    out.loc[out["iv_percentile"].isna(), "iv_percentile_bucket"] = "unavailable"
    out["post_drawdown_rebound_risk_bucket"] = np.where(
        out["post_drawdown_rebound_risk"].fillna(0).astype(int) == 1,
        "high",
        "low",
    )
    out["policy_jump_like_bucket"] = np.where(out["policy_jump_like"].astype(int) == 1, "policy_jump_like", "normal")
    return out


def _premium_capture_ratio(selected: pd.DataFrame) -> float:
    if selected.empty:
        return np.nan
    premium_received = float(selected["total_premium_yield"].fillna(0.0).sum())
    payoff_paid = float(selected["option_payoff_return_at_expiry"].fillna(0.0).sum())
    return (premium_received - payoff_paid) / premium_received if premium_received != 0 else np.nan


def _low_strike_reset_count(selected: pd.DataFrame) -> int:
    if selected.empty or "strike" not in selected.columns:
        return 0
    strikes = selected.sort_values("rebalance_date")["strike"].astype(float).dropna()
    return int((strikes.diff() < 0).sum()) if len(strikes) else 0


def _drawdown_duration(nav_g: pd.DataFrame) -> float:
    if nav_g.empty:
        return np.nan
    g = nav_g.sort_values("date").copy()
    nav = g["nav"].astype(float).reset_index(drop=True)
    dates = pd.to_datetime(g["date"]).reset_index(drop=True)
    drawdown = nav / nav.cummax() - 1.0
    underwater = drawdown < -1e-12
    max_days = 0.0
    start = None
    for idx, is_underwater in enumerate(underwater):
        if is_underwater and start is None:
            start = dates.iloc[idx]
        elif not is_underwater and start is not None:
            max_days = max(max_days, float((dates.iloc[idx] - start).days))
            start = None
    if start is not None:
        max_days = max(max_days, float((dates.iloc[-1] - start).days))
    return max_days


def build_down_then_rebound_events(periods: pd.DataFrame) -> pd.DataFrame:
    """Identify post-decline rebound windows and measure call truncation."""

    if periods.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    group_cols = ["etf_code", "dte_label", "strategy_name"]
    for (etf_code, dte_label, strategy_name), g in periods.sort_values(group_cols + ["rebalance_date"]).groupby(group_cols):
        g = g.reset_index(drop=True)
        prev_etf = g["etf_period_return"].shift(1)
        event_mask = ((prev_etf <= -0.03) & (g["etf_period_return"] >= 0.03)) | (
            g["policy_jump_like"].fillna(0).astype(int) == 1
        )
        for idx in g.index[event_mask]:
            row = g.loc[idx]
            etf_return = float(row["etf_period_return"])
            strategy_return = float(row["strategy_period_return"])
            rows.append(
                {
                    "etf_code": etf_code,
                    "dte_label": dte_label,
                    "strategy_name": strategy_name,
                    "strategy_family": row.get("strategy_family"),
                    "event_date": row["rebalance_date"],
                    "period_end_date": row["period_end_date"],
                    "previous_etf_period_return": float(prev_etf.loc[idx]) if pd.notna(prev_etf.loc[idx]) else np.nan,
                    "etf_rebound_return": etf_return,
                    "strategy_return": strategy_return,
                    "excess_return_vs_etf": float(row["excess_return_vs_etf"]),
                    "recovery_capture": strategy_return / etf_return if etf_return > 0 else np.nan,
                    "missed_rebound_return": max(etf_return - strategy_return, 0.0) if etf_return > 0 else np.nan,
                    "premium_return": row.get("premium_return", np.nan),
                    "payoff_return": row.get("option_payoff_return_at_expiry", np.nan),
                    "policy_jump_like": int(row.get("policy_jump_like", 0)),
                    "drawdown_from_rolling_high": row.get("drawdown_from_rolling_high", np.nan),
                    "rv_20d": row.get("rv_20d", np.nan),
                    "iv_at_entry": row.get("iv_at_entry", np.nan),
                }
            )
    return _sort_ver21(pd.DataFrame(rows), ["event_date"])


def build_daily_mtm_stress_summary(daily_mtm: pd.DataFrame) -> pd.DataFrame:
    if daily_mtm.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for keys, g in daily_mtm.groupby(["etf_code", "dte_label", "strategy_name"]):
        etf_code, dte_label, strategy_name = keys
        loss = g["short_call_mtm_loss_return"].fillna(0.0).astype(float)
        rows.append(
            {
                "etf_code": etf_code,
                "dte_label": dte_label,
                "strategy_name": strategy_name,
                "strategy_family": _strategy_family(str(strategy_name)),
                "daily_rows": int(len(g)),
                "daily_mtm_max_drawdown": max_drawdown_magnitude(g.sort_values("date")["daily_mtm_nav"].astype(float)),
                "max_short_call_mtm_loss": float(loss.max()) if len(loss) else np.nan,
                "avg_short_call_mtm_loss": float(loss.mean()) if len(loss) else np.nan,
                "p95_short_call_mtm_loss": float(loss.quantile(0.95)) if len(loss) else np.nan,
                "mtm_loss_days": int((loss > 0).sum()),
                "max_effective_bid_ask_spread_pct": float(g["effective_bid_ask_spread_pct"].max())
                if "effective_bid_ask_spread_pct" in g.columns
                else np.nan,
                "assumed_spread_day_ratio": float((g.get("bid_ask_spread_source", "") == "assumed").mean())
                if "bid_ask_spread_source" in g.columns
                else np.nan,
            }
        )
    return _sort_ver21(pd.DataFrame(rows))


def _daily_nav_series(group: pd.DataFrame) -> pd.Series:
    """Return one daily MTM NAV observation per trading date."""

    if group.empty or "daily_mtm_nav" not in group.columns:
        return pd.Series(dtype=float)
    work = group.copy()
    work["date"] = pd.to_datetime(work["date"])
    work["_row_order"] = np.arange(len(work))
    sort_cols = ["date"]
    if "period_index" in work.columns:
        sort_cols.append("period_index")
    sort_cols.append("_row_order")
    work = work.sort_values(sort_cols)
    daily = work.groupby("date", as_index=False).tail(1).sort_values("date")
    nav = pd.Series(daily["daily_mtm_nav"].astype(float).to_numpy(), index=pd.DatetimeIndex(daily["date"]))
    return nav.dropna()


def _drawdown_duration_from_nav(nav: pd.Series) -> float:
    """Return the longest calendar-day drawdown duration for a NAV series."""

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


def _annualized_return_from_daily_nav(nav: pd.Series) -> float:
    nav = nav.dropna().astype(float)
    if len(nav) < 2 or nav.iloc[0] <= 0 or nav.iloc[-1] <= 0:
        return np.nan
    years = (pd.Timestamp(nav.index[-1]) - pd.Timestamp(nav.index[0])).days / 365.25
    if years <= 0:
        years = max((len(nav) - 1) / TRADING_DAYS_PER_YEAR, 1e-12)
    return float((nav.iloc[-1] / nav.iloc[0]) ** (1.0 / years) - 1.0)


def _monthly_returns_from_daily_returns(daily_returns: pd.Series) -> pd.Series:
    if daily_returns.empty:
        return pd.Series(dtype=float)
    return daily_returns.groupby(daily_returns.index.to_period("M")).apply(lambda s: float((1.0 + s).prod() - 1.0))


def build_standard_performance_summary(daily_mtm: pd.DataFrame) -> pd.DataFrame:
    """Compute standard performance metrics from daily MTM NAV."""

    columns = [
        "etf_code",
        "dte_label",
        "strategy_name",
        "strategy_family",
        "dte_comparison_group",
        "start_date",
        "end_date",
        "daily_nav_observations",
        "cumulative_return_daily_nav",
        "annualized_return_daily_nav",
        "annualized_volatility_daily_nav",
        "sharpe_ratio_daily_nav",
        "sortino_ratio_daily_nav",
        "calmar_ratio_daily_nav",
        "max_drawdown",
        "drawdown_duration",
        "monthly_win_rate",
        "worst_month_return",
        "skewness",
        "kurtosis",
    ]
    if daily_mtm.empty:
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, Any]] = []
    group_cols = ["etf_code", "dte_label", "strategy_name"]
    for (etf_code, dte_label, strategy_name), g in daily_mtm.groupby(group_cols):
        nav = _daily_nav_series(g)
        daily_returns = nav.pct_change().dropna()
        annualized_ret = _annualized_return_from_daily_nav(nav)
        annualized_vol = (
            float(daily_returns.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))
            if len(daily_returns.dropna()) > 1
            else np.nan
        )
        downside_returns = daily_returns[daily_returns < 0]
        downside_vol = (
            float(downside_returns.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))
            if len(downside_returns.dropna()) > 1
            else np.nan
        )
        mdd = max_drawdown_magnitude(nav)
        monthly_returns = _monthly_returns_from_daily_returns(daily_returns)
        rows.append(
            {
                "etf_code": etf_code,
                "dte_label": dte_label,
                "strategy_name": strategy_name,
                "strategy_family": _strategy_family(str(strategy_name)),
                "dte_comparison_group": _dte_comparison_group(str(dte_label)),
                "start_date": nav.index.min() if not nav.empty else pd.NaT,
                "end_date": nav.index.max() if not nav.empty else pd.NaT,
                "daily_nav_observations": int(len(nav)),
                "cumulative_return_daily_nav": float(nav.iloc[-1] / nav.iloc[0] - 1.0)
                if len(nav) >= 2 and nav.iloc[0] != 0
                else np.nan,
                "annualized_return_daily_nav": annualized_ret,
                "annualized_volatility_daily_nav": annualized_vol,
                "sharpe_ratio_daily_nav": float(annualized_ret / annualized_vol)
                if pd.notna(annualized_ret) and annualized_vol and annualized_vol > 0
                else np.nan,
                "sortino_ratio_daily_nav": float(annualized_ret / downside_vol)
                if pd.notna(annualized_ret) and downside_vol and downside_vol > 0
                else np.nan,
                "calmar_ratio_daily_nav": float(annualized_ret / mdd) if pd.notna(annualized_ret) and mdd and mdd > 0 else np.nan,
                "max_drawdown": mdd,
                "drawdown_duration": _drawdown_duration_from_nav(nav),
                "monthly_win_rate": float((monthly_returns > 0).mean()) if not monthly_returns.empty else np.nan,
                "worst_month_return": float(monthly_returns.min()) if not monthly_returns.empty else np.nan,
                "skewness": float(daily_returns.skew()) if len(daily_returns.dropna()) > 2 else np.nan,
                "kurtosis": float(daily_returns.kurt()) if len(daily_returns.dropna()) > 3 else np.nan,
            }
        )
    return _sort_ver21(pd.DataFrame(rows, columns=columns))


def build_candidate_shortlist(ranking: pd.DataFrame, standard_performance: pd.DataFrame) -> pd.DataFrame:
    """Filter the ver2.1 ranking down to comparable, readable strategy candidates."""

    if ranking.empty:
        return pd.DataFrame()

    keys = ["etf_code", "dte_label", "strategy_name"]
    perf_cols = [
        *keys,
        "annualized_return_daily_nav",
        "annualized_volatility_daily_nav",
        "sharpe_ratio_daily_nav",
        "sortino_ratio_daily_nav",
        "calmar_ratio_daily_nav",
        "max_drawdown",
        "drawdown_duration",
        "monthly_win_rate",
        "worst_month_return",
        "skewness",
        "kurtosis",
    ]
    merged = ranking.copy()
    if not standard_performance.empty:
        perf = standard_performance[[col for col in perf_cols if col in standard_performance.columns]].copy()
        perf = perf.rename(
            columns={
                "max_drawdown": "max_drawdown_daily_nav",
                "drawdown_duration": "drawdown_duration_daily_nav",
            }
        )
        merged = merged.merge(perf, on=keys, how="left")

    base = merged[
        (merged["strategy_name"].isin(SHORTLIST_ALLOWED_STRATEGIES))
        & (merged.get("effective_option_coverage_ratio", np.nan) >= 0.95)
        & (merged.get("coverage_comparability_flag", "") == "comparable_continuous_overlay")
    ].copy()
    if base.empty:
        return _sort_ver21(base)

    def _protection_floor(series: pd.Series) -> float:
        clean = series.dropna().astype(float)
        if clean.empty:
            return np.nan
        if len(clean) >= 4:
            return float(max(0.0, clean.quantile(0.25)))
        return 0.0

    def _mtm_ceiling(series: pd.Series) -> float:
        clean = series.dropna().astype(float)
        if clean.empty:
            return np.nan
        if len(clean) >= 4:
            return float(clean.quantile(0.75))
        return np.inf

    base["shortlist_downside_cushion_floor"] = base.groupby("etf_code")["downside_cushion_ratio_mean"].transform(
        _protection_floor
    )
    base["shortlist_mtm_pressure_ceiling"] = base.groupby("etf_code")["max_short_call_mtm_loss"].transform(
        _mtm_ceiling
    )
    protection_ok = base["downside_cushion_ratio_mean"].fillna(-np.inf) >= base[
        "shortlist_downside_cushion_floor"
    ].fillna(-np.inf)
    mtm_ok = base["max_short_call_mtm_loss"].isna() | base["shortlist_mtm_pressure_ceiling"].isna() | (
        base["max_short_call_mtm_loss"] <= base["shortlist_mtm_pressure_ceiling"] + 1e-12
    )
    out = base[protection_ok & mtm_ok].copy()
    if out.empty:
        return _sort_ver21(out)

    out["shortlist_rank"] = out.groupby("etf_code")["robustness_score"].rank(
        method="first", ascending=False
    ).astype(int)
    out["shortlist_filter_note"] = (
        "coverage>=0.95; comparable_continuous_overlay; allowed strategy; "
        "not bottom-quartile downside cushion; not top-quartile MTM pressure"
    )
    return out.sort_values(["etf_code", "shortlist_rank", "dte_label", "strategy_name"]).reset_index(drop=True)


def _event_summary(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame(
            columns=[
                "etf_code",
                "dte_label",
                "strategy_name",
                "recovery_capture",
                "missed_rebound_return",
                "rebound_event_count",
            ]
        )
    return (
        events.groupby(["etf_code", "dte_label", "strategy_name"])
        .agg(
            recovery_capture=("recovery_capture", "mean"),
            missed_rebound_return=("missed_rebound_return", "mean"),
            rebound_event_count=("event_date", "count"),
        )
        .reset_index()
    )


def build_dte_moneyness_summary(
    periods: pd.DataFrame,
    nav: pd.DataFrame,
    base_summary: pd.DataFrame,
    daily_stress: pd.DataFrame,
    events: pd.DataFrame,
    effective_coverage: pd.DataFrame,
) -> pd.DataFrame:
    """Build the main ver2.1 DTE x strategy diagnostic summary."""

    if base_summary.empty:
        return base_summary.copy()
    decomposed = add_premium_decomposition(periods)
    rows: list[dict[str, Any]] = []
    nav_lookup = {
        (str(etf), str(dte), str(strategy)): g
        for (etf, dte, strategy), g in nav.groupby(["etf_code", "dte_label", "strategy_name"])
    }
    for (etf_code, dte_label, strategy_name), g in decomposed.groupby(["etf_code", "dte_label", "strategy_name"]):
        g = g.sort_values("rebalance_date")
        selected = g[g["option_selected_flag"].fillna(0).astype(int) == 1]
        factor = annual_factor(g)
        nav_g = nav_lookup.get((str(etf_code), str(dte_label), str(strategy_name)), pd.DataFrame())
        rows.append(
            {
                "etf_code": etf_code,
                "dte_label": dte_label,
                "strategy_name": strategy_name,
                "strategy_family": _strategy_family(str(strategy_name)),
                "target_moneyness_spec": TARGET_MONEYNESS.get(str(strategy_name), np.nan),
                "target_delta": TARGET_DELTA.get(str(strategy_name), np.nan),
                "selected_periods": int(len(selected)),
                "average_actual_dte": float(selected["actual_dte"].mean()) if not selected.empty else np.nan,
                "realized_moneyness_mean": float(selected["realized_moneyness"].mean())
                if not selected.empty
                else np.nan,
                "selected_delta_mean": float(selected["selected_delta"].mean()) if not selected.empty else np.nan,
                "iv_at_entry_mean": float(selected["iv_at_entry"].mean()) if not selected.empty else np.nan,
                "average_total_premium_yield": float(selected["total_premium_yield"].mean())
                if not selected.empty
                else np.nan,
                "average_extrinsic_premium_yield": float(selected["extrinsic_premium_yield"].mean())
                if not selected.empty
                else np.nan,
                "annualized_total_premium_yield": float(selected["total_premium_yield"].mean() * factor)
                if not selected.empty
                else np.nan,
                "annualized_extrinsic_premium_yield": float(selected["extrinsic_premium_yield"].mean() * factor)
                if not selected.empty
                else np.nan,
                "premium_capture_ratio": _premium_capture_ratio(selected),
                "payoff_return_mean": float(selected["option_payoff_return_at_expiry"].mean())
                if not selected.empty
                else np.nan,
                "assignment_rate": float(selected["assignment_flag"].fillna(0).astype(int).mean())
                if not selected.empty and strategy_name != "BuyHold"
                else np.nan,
                "roll_count_per_year": float(len(selected) / max((g["period_end_date"].max() - g["rebalance_date"].min()).days / 365.25, 1e-12))
                if not selected.empty
                else np.nan,
                "low_strike_reset_count": _low_strike_reset_count(selected),
                "drawdown_duration": _drawdown_duration(nav_g),
            }
        )

    add_on = pd.DataFrame(rows)
    summary = base_summary.merge(
        add_on,
        on=["etf_code", "dte_label", "strategy_name"],
        how="left",
        suffixes=("", "_ver21"),
    )
    for col in ["strategy_family", "target_moneyness_spec", "target_delta"]:
        alt = f"{col}_ver21"
        if alt in summary.columns:
            summary[col] = summary[col].combine_first(summary[alt]) if col in summary.columns else summary[alt]
            summary = summary.drop(columns=[alt])

    event_summary = _event_summary(events)
    summary = summary.merge(event_summary, on=["etf_code", "dte_label", "strategy_name"], how="left")
    stress_cols = [
        "etf_code",
        "dte_label",
        "strategy_name",
        "daily_mtm_max_drawdown",
        "max_short_call_mtm_loss",
        "p95_short_call_mtm_loss",
        "mtm_loss_days",
        "assumed_spread_day_ratio",
    ]
    summary = summary.merge(
        daily_stress[[col for col in stress_cols if col in daily_stress.columns]],
        on=["etf_code", "dte_label", "strategy_name"],
        how="left",
    )
    coverage_cols = [
        "etf_code",
        "dte_label",
        "strategy_name",
        "total_backtest_days",
        "active_short_call_days",
        "etf_only_gap_days",
        "effective_option_coverage_ratio",
        "valid_option_cycle_count",
        "skipped_period_count",
        "no_eligible_expiry_count",
        "terminal_insufficient_horizon_count",
        "data_missing_or_chain_unavailable_count",
        "other_selection_failure_count",
    ]
    if not effective_coverage.empty:
        summary = summary.merge(
            effective_coverage[[col for col in coverage_cols if col in effective_coverage.columns]],
            on=["etf_code", "dte_label", "strategy_name"],
            how="left",
        )
    summary["metric_scope"] = "full_account"
    if "dte_comparison_group" not in summary.columns:
        summary["dte_comparison_group"] = summary["dte_label"].map(_dte_comparison_group)
    else:
        summary["dte_comparison_group"] = summary["dte_comparison_group"].combine_first(
            summary["dte_label"].map(_dte_comparison_group)
        )
    if "effective_option_coverage_ratio" in summary.columns:
        summary["coverage_comparability_flag"] = np.select(
            [
                summary["effective_option_coverage_ratio"] < 0.90,
                summary["dte_comparison_group"] == "near_expiry_overlay_strategy",
            ],
            [
                "low_coverage_not_directly_comparable",
                "near_expiry_overlay_separate",
            ],
            default="comparable_continuous_overlay",
        )
    return _sort_ver21(summary)


def _conditional_row(g: pd.DataFrame, regime_variable: str, regime_bucket: str) -> dict[str, Any]:
    returns = g["strategy_period_return"].astype(float)
    selected = g[g["option_selected_flag"].fillna(0).astype(int) == 1]
    down = g[g["etf_period_return"] < 0]
    up = g[g["etf_period_return"] > 0]
    factor = annual_factor(g) if not g.empty else np.nan
    return {
        "etf_code": g["etf_code"].iloc[0],
        "dte_label": g["dte_label"].iloc[0],
        "strategy_name": g["strategy_name"].iloc[0],
        "strategy_family": g["strategy_family"].iloc[0],
        "regime_variable": regime_variable,
        "regime_bucket": regime_bucket,
        "count": int(len(g)),
        "etf_return_mean": float(g["etf_period_return"].mean()),
        "strategy_return_mean": float(returns.mean()),
        "excess_return_mean": float(g["excess_return_vs_etf"].mean()),
        "annualized_return": annualized_return(returns, factor),
        "annualized_extrinsic_premium_yield": float(selected["extrinsic_premium_yield"].mean() * factor)
        if not selected.empty
        else np.nan,
        "premium_capture_ratio": _premium_capture_ratio(selected),
        "downside_excess_mean": float(down["excess_return_vs_etf"].mean()) if not down.empty else np.nan,
        "downside_cushion_ratio_mean": float(down["downside_cushion_ratio"].mean()) if not down.empty else np.nan,
        "downside_win_rate": float((down["strategy_period_return"] > down["etf_period_return"]).mean())
        if not down.empty
        else np.nan,
        "payoff_return_mean": float(selected["option_payoff_return_at_expiry"].mean())
        if not selected.empty
        else np.nan,
        "upside_cost_mean": float(up["upside_cost"].mean()) if not up.empty else np.nan,
    }


def build_regime_conditional_performance(periods: pd.DataFrame) -> pd.DataFrame:
    """Aggregate strategy performance under entry-date regime buckets."""

    if periods.empty:
        return pd.DataFrame()
    decomposed = add_premium_decomposition(periods)
    rows: list[dict[str, Any]] = []
    for regime_col in REGIME_BUCKET_COLUMNS:
        if regime_col not in decomposed.columns:
            continue
        for bucket, bucket_g in decomposed.groupby(regime_col, dropna=False):
            bucket_name = str(bucket)
            for _, g in bucket_g.groupby(["etf_code", "dte_label", "strategy_name"]):
                rows.append(_conditional_row(g, regime_col, bucket_name))
    return _sort_ver21(pd.DataFrame(rows), ["regime_variable", "regime_bucket"])


def _rank_pct(series: pd.Series, *, higher_is_better: bool) -> pd.Series:
    if series.dropna().empty:
        return pd.Series(0.0, index=series.index)
    return series.rank(method="average", pct=True, ascending=higher_is_better).fillna(0.0)


def build_dte_robustness_ranking(summary: pd.DataFrame) -> pd.DataFrame:
    """Rank non-ITM strategies by defensive income robustness across DTE choices."""

    if summary.empty:
        return pd.DataFrame()
    ranked = summary[summary["strategy_name"] != "BuyHold"].copy()
    if ranked.empty:
        return ranked
    rank_specs = {
        "annualized_extrinsic_premium_yield": ("annualized_extrinsic_premium_yield_rank", True),
        "downside_cushion_ratio_mean": ("downside_cushion_ratio_rank", True),
        "max_drawdown_improvement": ("max_drawdown_improvement_rank", True),
        "premium_capture_ratio": ("premium_capture_ratio_rank", True),
        "daily_mtm_max_drawdown": ("daily_mtm_max_drawdown_rank", False),
        "max_short_call_mtm_loss": ("max_short_call_mtm_loss_rank", False),
        "missed_rebound_return": ("missed_rebound_return_rank", False),
    }
    for source_col, (rank_col, higher_is_better) in rank_specs.items():
        if source_col not in ranked.columns:
            ranked[rank_col] = 0.0
            continue
        ranked[rank_col] = ranked.groupby("etf_code", group_keys=False)[source_col].apply(
            lambda s: _rank_pct(s, higher_is_better=higher_is_better)
        )

    ranked["robustness_score"] = (
        0.20 * ranked["annualized_extrinsic_premium_yield_rank"]
        + 0.20 * ranked["downside_cushion_ratio_rank"]
        + 0.20 * ranked["max_drawdown_improvement_rank"]
        + 0.15 * ranked["premium_capture_ratio_rank"]
        + 0.10 * ranked["daily_mtm_max_drawdown_rank"]
        + 0.10 * ranked["max_short_call_mtm_loss_rank"]
        + 0.05 * ranked["missed_rebound_return_rank"]
    )
    return ranked.sort_values(["etf_code", "robustness_score"], ascending=[True, False]).reset_index(drop=True)


def run_ver2_1_diagnostic(base_config: ExperimentConfig, root: Path | None = None) -> Ver21Tables:
    """Run the ver2.1 non-ITM DTE x regime diagnostic experiment."""

    output_dir = base_config.paths.output_dir / "ver2_1_dte_regime"
    options_path = _candidate_delta_options_path(base_config, root)
    probe_config = replace(base_config, paths=replace(base_config.paths, options=options_path, output_dir=output_dir))
    data = load_ver2_data(probe_config)
    delta_available = _has_usable_delta(data.options)
    iv_available = _has_usable_iv(data.options)
    if not delta_available:
        LOGGER.warning("Delta data is unavailable; D50/D40/D30/D20 strategies will be skipped.")

    results, run_metadata = _run_dte_backtests(
        base_config,
        data=data,
        output_dir=output_dir,
        options_path=options_path,
        delta_available=delta_available,
    )
    periods = _combine_result_attr(results, "periods")
    nav = _combine_result_attr(results, "nav")
    daily_mtm = _combine_result_attr(results, "daily_mtm")
    base_summary = _combine_result_attr(results, "summary")
    skipped = _combine_result_attr(results, "skipped_periods")

    periods = attach_regime_features(periods, data.prices)
    skipped = classify_skipped_periods(skipped, data.options, data.prices)
    daily_stress = build_daily_mtm_stress_summary(daily_mtm)
    events = build_down_then_rebound_events(periods)
    effective_coverage = build_effective_coverage_summary(periods, daily_mtm, skipped, data.prices)
    active_overlay_metrics = build_active_overlay_metrics(periods)
    summary = build_dte_moneyness_summary(periods, nav, base_summary, daily_stress, events, effective_coverage)
    regime = build_regime_conditional_performance(periods)
    ranking = build_dte_robustness_ranking(summary)
    standard_performance = build_standard_performance_summary(daily_mtm)
    candidate_shortlist = build_candidate_shortlist(ranking, standard_performance)

    metadata = {
        "experiment_name": "ver2_1_non_itm_dte_regime_diagnostic",
        "version": "ver2.1",
        "option_source": str(options_path),
        "delta_available": delta_available,
        "iv_available": iv_available,
        "policy_jump_like_usage": "ex_post_attribution_only",
        "liquidity_usage": "execution_quality_diagnostic_only",
        **run_metadata,
    }
    return Ver21Tables(
        periods=_sort_ver21(periods, ["rebalance_date"]),
        nav=_sort_ver21(nav, ["date"]),
        daily_mtm=_sort_ver21(daily_mtm, ["date"]),
        summary=summary,
        regime_conditional_performance=regime,
        down_then_rebound_events=events,
        dte_robustness_ranking=ranking,
        daily_mtm_stress_summary=daily_stress,
        effective_coverage_summary=effective_coverage,
        active_overlay_metrics=active_overlay_metrics,
        standard_performance_summary=standard_performance,
        candidate_shortlist=candidate_shortlist,
        skipped_periods=_sort_ver21(skipped, ["rebalance_date"]),
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


def _head_per_etf(df: pd.DataFrame, n: int) -> pd.DataFrame:
    if df.empty or "etf_code" not in df.columns:
        return df.head(n).reset_index(drop=True)
    return df.groupby("etf_code", group_keys=False).head(n).reset_index(drop=True)


def _summary_preview(summary: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "etf_code",
        "dte_label",
        "strategy_name",
        "dte_comparison_group",
        "annualized_return",
        "annualized_extrinsic_premium_yield",
        "premium_capture_ratio",
        "downside_cushion_ratio_mean",
        "max_drawdown",
        "max_drawdown_improvement",
        "daily_mtm_max_drawdown",
        "max_short_call_mtm_loss",
        "missed_rebound_return",
        "effective_option_coverage_ratio",
        "etf_only_gap_days",
        "coverage_comparability_flag",
    ]
    out = summary[[col for col in cols if col in summary.columns]].copy()
    for col in [
        "annualized_return",
        "annualized_extrinsic_premium_yield",
        "premium_capture_ratio",
        "downside_cushion_ratio_mean",
        "max_drawdown",
        "max_drawdown_improvement",
        "daily_mtm_max_drawdown",
        "max_short_call_mtm_loss",
        "missed_rebound_return",
        "effective_option_coverage_ratio",
    ]:
        if col in out.columns:
            out[col] = out[col].map(_format_percent)
    return _head_per_etf(out, 18)


def _ranking_preview(ranking: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "etf_code",
        "dte_label",
        "strategy_name",
        "dte_comparison_group",
        "robustness_score",
        "annualized_extrinsic_premium_yield",
        "downside_cushion_ratio_mean",
        "max_drawdown_improvement",
        "premium_capture_ratio",
        "missed_rebound_return",
        "effective_option_coverage_ratio",
        "etf_only_gap_days",
        "valid_option_cycle_count",
        "coverage_comparability_flag",
    ]
    out = ranking[[col for col in cols if col in ranking.columns]].copy()
    if "robustness_score" in out.columns:
        out["robustness_score"] = out["robustness_score"].map(_format_float)
    for col in [
        "annualized_extrinsic_premium_yield",
        "downside_cushion_ratio_mean",
        "max_drawdown_improvement",
        "premium_capture_ratio",
        "missed_rebound_return",
        "effective_option_coverage_ratio",
    ]:
        if col in out.columns:
            out[col] = out[col].map(_format_percent)
    return _head_per_etf(out, 12)


def _coverage_preview(coverage: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "etf_code",
        "dte_label",
        "strategy_name",
        "dte_comparison_group",
        "effective_option_coverage_ratio",
        "total_backtest_days",
        "active_short_call_days",
        "etf_only_gap_days",
        "valid_option_cycle_count",
        "skipped_period_count",
        "no_eligible_expiry_count",
        "terminal_insufficient_horizon_count",
    ]
    if coverage.empty:
        return pd.DataFrame(columns=cols)
    out = coverage[[col for col in cols if col in coverage.columns]].copy()
    if "effective_option_coverage_ratio" in out.columns:
        out["effective_option_coverage_ratio"] = out["effective_option_coverage_ratio"].map(_format_percent)
    return _head_per_etf(out, 28)


def _active_overlay_preview(active: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "etf_code",
        "dte_label",
        "strategy_name",
        "active_option_cycle_count",
        "active_overlay_annualized_return",
        "active_overlay_annualized_extrinsic_premium_yield",
        "active_overlay_premium_capture_ratio",
        "active_overlay_downside_cushion_ratio_mean",
        "active_overlay_upside_cost_mean",
    ]
    if active.empty:
        return pd.DataFrame(columns=cols)
    out = active[[col for col in cols if col in active.columns]].copy()
    for col in [
        "active_overlay_annualized_return",
        "active_overlay_annualized_extrinsic_premium_yield",
        "active_overlay_premium_capture_ratio",
        "active_overlay_downside_cushion_ratio_mean",
        "active_overlay_upside_cost_mean",
    ]:
        if col in out.columns:
            out[col] = out[col].map(_format_percent)
    return _head_per_etf(out, 16)


def _merge_standard_for_report(source: pd.DataFrame, standard: pd.DataFrame) -> pd.DataFrame:
    if source.empty or standard.empty or "max_drawdown_daily_nav" in source.columns:
        return source.copy()
    keys = ["etf_code", "dte_label", "strategy_name"]
    cols = [
        *keys,
        "annualized_return_daily_nav",
        "annualized_volatility_daily_nav",
        "sharpe_ratio_daily_nav",
        "sortino_ratio_daily_nav",
        "calmar_ratio_daily_nav",
        "max_drawdown",
        "drawdown_duration",
        "monthly_win_rate",
        "worst_month_return",
        "skewness",
        "kurtosis",
    ]
    perf = standard[[col for col in cols if col in standard.columns]].rename(
        columns={
            "max_drawdown": "max_drawdown_daily_nav",
            "drawdown_duration": "drawdown_duration_daily_nav",
        }
    )
    return source.merge(perf, on=keys, how="left")


def _top_candidate_rows(tables: Ver21Tables, n: int = 5) -> pd.DataFrame:
    source = tables.candidate_shortlist.copy()
    if not source.empty and "dte_label" in source.columns:
        source = source[source["dte_label"].isin(MAIN_REPORT_DTES)].copy()
    if source.empty:
        source = tables.dte_robustness_ranking[
            (tables.dte_robustness_ranking["strategy_name"].isin(SHORTLIST_ALLOWED_STRATEGIES))
            & (tables.dte_robustness_ranking.get("effective_option_coverage_ratio", np.nan) >= 0.95)
            & (tables.dte_robustness_ranking.get("coverage_comparability_flag", "") == "comparable_continuous_overlay")
            & (tables.dte_robustness_ranking["dte_label"].isin(MAIN_REPORT_DTES))
        ].copy()
    source = _merge_standard_for_report(source, tables.standard_performance_summary)
    if source.empty:
        return source
    if "shortlist_rank" not in source.columns:
        source = source.sort_values(["etf_code", "robustness_score"], ascending=[True, False]).copy()
        source["shortlist_rank"] = source.groupby("etf_code").cumcount() + 1
    top = source.sort_values(["etf_code", "shortlist_rank"]).groupby("etf_code", group_keys=False).head(n).copy()
    top["report_rank"] = top.groupby("etf_code").cumcount() + 1
    return top.reset_index(drop=True)


def _key_strength(row: pd.Series) -> str:
    choices = {
        "annualized_extrinsic_premium_yield_rank": "extrinsic premium yield",
        "downside_cushion_ratio_rank": "downside cushion",
        "max_drawdown_improvement_rank": "drawdown control",
        "premium_capture_ratio_rank": "premium capture",
    }
    scores = {
        label: float(row.get(rank_col))
        for rank_col, label in choices.items()
        if pd.notna(row.get(rank_col))
    }
    if not scores:
        return "balanced profile"
    return max(scores.items(), key=lambda item: item[1])[0]


def _key_risk(row: pd.Series) -> str:
    coverage = row.get("effective_option_coverage_ratio", np.nan)
    if pd.notna(coverage) and float(coverage) < 0.95:
        return "coverage gap"
    if row.get("coverage_comparability_flag") != "comparable_continuous_overlay":
        return "not directly comparable"
    mtm_loss = row.get("max_short_call_mtm_loss", np.nan)
    if pd.notna(mtm_loss) and float(mtm_loss) > 0.08:
        return "daily MTM pressure"
    missed_rebound = row.get("missed_rebound_return", np.nan)
    if pd.notna(missed_rebound) and float(missed_rebound) > 0.02:
        return "rebound truncation"
    premium_capture = row.get("premium_capture_ratio", np.nan)
    if pd.notna(premium_capture) and float(premium_capture) < 0.30:
        return "low premium capture"
    return "needs out-of-sample check"


def _format_report_table(
    df: pd.DataFrame,
    *,
    percent_cols: list[str] | None = None,
    float_cols: list[str] | None = None,
    int_cols: list[str] | None = None,
) -> str:
    if df.empty:
        return "_No rows._"
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


def _executive_top_candidates_table(top: pd.DataFrame) -> pd.DataFrame:
    if top.empty:
        return pd.DataFrame(
            columns=[
                "ETF",
                "rank",
                "dte_label",
                "strategy_name",
                "robustness_score",
                "annualized_return",
                "sharpe_ratio",
                "max_drawdown",
                "key_strength",
                "key_risk",
            ]
        )
    return pd.DataFrame(
        {
            "ETF": top["etf_code"],
            "rank": top["report_rank"],
            "dte_label": top["dte_label"],
            "strategy_name": top["strategy_name"],
            "robustness_score": top["robustness_score"],
            "annualized_return": top["annualized_return_daily_nav"],
            "sharpe_ratio": top["sharpe_ratio_daily_nav"],
            "max_drawdown": top.get("max_drawdown_daily_nav", top.get("max_drawdown")),
            "key_strength": top.apply(_key_strength, axis=1),
            "key_risk": top.apply(_key_risk, axis=1),
        }
    )


def _select_report_columns(top: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if top.empty:
        return pd.DataFrame(columns=columns)
    return top[[col for col in columns if col in top.columns]].copy()


def write_ver2_1_readable_report(tables: Ver21Tables, report_path: Path) -> Path:
    """Write a compact, human-readable ver2.1 report."""

    report_path.parent.mkdir(parents=True, exist_ok=True)
    top = _top_candidate_rows(tables, n=5)
    executive = _executive_top_candidates_table(top)
    performance = _select_report_columns(
        top,
        [
            "etf_code",
            "dte_label",
            "strategy_name",
            "annualized_return_daily_nav",
            "annualized_volatility_daily_nav",
            "sharpe_ratio_daily_nav",
            "sortino_ratio_daily_nav",
            "calmar_ratio_daily_nav",
            "max_drawdown_daily_nav",
        ],
    )
    premium = _select_report_columns(
        top,
        [
            "etf_code",
            "dte_label",
            "strategy_name",
            "annualized_extrinsic_premium_yield",
            "premium_capture_ratio",
            "payoff_return_mean",
        ],
    )
    downside = _select_report_columns(
        top,
        [
            "etf_code",
            "dte_label",
            "strategy_name",
            "downside_cushion_ratio_mean",
            "downside_excess_mean",
            "max_drawdown_improvement",
        ],
    )
    rebound = _select_report_columns(
        top,
        [
            "etf_code",
            "dte_label",
            "strategy_name",
            "missed_rebound_return",
            "recovery_capture",
            "max_short_call_mtm_loss",
        ],
    )
    coverage = _select_report_columns(
        top,
        [
            "etf_code",
            "dte_label",
            "strategy_name",
            "effective_option_coverage_ratio",
            "etf_only_gap_days",
            "valid_option_cycle_count",
            "coverage_comparability_flag",
        ],
    )

    text = f"""# ver2.1 Non-ITM Covered Call DTE x Regime Diagnostic - Final Main Report

## 实验定位

ver2.1 是优化前的机制诊断，不是最终动态策略。它用来回答：在非 ITM 策略空间内，DTE 与市场状态如何影响 ATM / OTM / 低 delta call 的权利金收入、下跌缓冲、回撤控制和反弹截断风险。

本报告正文只展示候选池短表。完整大表保留在 CSV 中，避免把二级指标和逐期诊断全部塞进正文。

## 关键口径

- ETF: 510300, 510050。
- rolling mode: continuous rolling / hold to expiry。
- coverage ratio: 100%。
- 主策略空间: ATM_100, OTM2_100, OTM5_100, D50_100, D40_100, D30_100, D20_100。
- 候选池筛选: effective_option_coverage_ratio >= 0.95，coverage_comparability_flag = comparable_continuous_overlay，strategy in ATM_100 / D50_100 / D40_100 / OTM2_100，并剔除同 ETF 内下跌保护明显偏低或 daily MTM 压力明显偏高的组合。
- Sharpe、Sortino、Calmar、monthly win rate 等标准绩效指标均基于 daily MTM NAV 计算，不是基于到期周期收益计算。
- DTE14_strict_window 属于 near-expiry overlay strategy，存在 ETF-only gap，不与连续覆盖策略直接横向比较。
- upside_cost_mean 和 protection_cost_ratio 继续保留在完整 CSV 中，作为辅助诊断，不进入本报告候选池主排序。

## Final DTE scope

本版 ver2.1 主报告只保留 DTE30 与 DTE60 两类 DTE：

- DTE30 是当前最干净的月度连续覆盖基准，effective coverage 高，展期路径最可解释。
- DTE60 是低展期频率对照，用于观察更长持有期是否降低反弹截断和日频 MTM 压力。
- DTE14_strict_window、DTE14_nearest_continuous、DTE45 仅保留在完整 CSV 和 appendix 诊断中，不进入主候选表，也不作为最终 DTE 结论来源。

因此，下面所有正文短表只展示 DTE30 / DTE60；完整机制诊断仍可在 `ver2_1_dte_moneyness_summary.csv`、`ver2_1_dte_robustness_ranking.csv` 与 `ver2_1_effective_coverage_summary.csv` 中查看。

## Executive top candidates

{_format_report_table(
        executive,
        percent_cols=["annualized_return", "max_drawdown"],
        float_cols=["robustness_score", "sharpe_ratio"],
        int_cols=["rank"],
    )}

## Performance table

{_format_report_table(
        performance,
        percent_cols=[
            "annualized_return_daily_nav",
            "annualized_volatility_daily_nav",
            "max_drawdown_daily_nav",
        ],
        float_cols=["sharpe_ratio_daily_nav", "sortino_ratio_daily_nav", "calmar_ratio_daily_nav"],
    )}

## Premium income table

{_format_report_table(
        premium,
        percent_cols=[
            "annualized_extrinsic_premium_yield",
            "premium_capture_ratio",
            "payoff_return_mean",
        ],
    )}

## Downside protection table

{_format_report_table(
        downside,
        percent_cols=[
            "downside_cushion_ratio_mean",
            "downside_excess_mean",
            "max_drawdown_improvement",
        ],
    )}

## Rebound risk table

{_format_report_table(
        rebound,
        percent_cols=[
            "missed_rebound_return",
            "recovery_capture",
            "max_short_call_mtm_loss",
        ],
    )}

## Coverage quality table

{_format_report_table(
        coverage,
        percent_cols=["effective_option_coverage_ratio"],
        int_cols=["etf_only_gap_days", "valid_option_cycle_count"],
    )}

## 阅读结论

1. DTE 作为变量的有效主比较收束到 DTE30 与 DTE60：DTE30 是主基准，DTE60 是低频对照。
2. DTE14_nearest_continuous 在实际 DTE 上高度接近 DTE30，不能解释为独立短期限策略证据。
3. DTE14_strict_window 的低覆盖率会混入 ETF-only path，因此只适合作为 near-expiry overlay appendix。
4. DTE45 仅保留为中间期限诊断，不进入主报告候选池。
5. 真正值得进入 ver2.2 的组合，应同时满足：extrinsic premium yield 不薄、premium capture 不差、downside cushion 稳定、daily MTM 压力不过高。

## 完整输出路径

- `outputs/ver2_downside_protection/ver2_1_standard_performance_summary.csv`
- `outputs/ver2_downside_protection/ver2_1_candidate_shortlist.csv`
- `outputs/ver2_downside_protection/ver2_1_full_account_metrics.csv`
- `outputs/ver2_downside_protection/ver2_1_active_overlay_metrics.csv`
- `outputs/ver2_downside_protection/ver2_1_effective_coverage_summary.csv`
- `outputs/ver2_downside_protection/ver2_1_dte_regime/ver2_1_dte_moneyness_summary.csv`
- `outputs/ver2_downside_protection/ver2_1_dte_regime/ver2_1_dte_robustness_ranking.csv`
- `outputs/ver2_downside_protection/ver2_1_dte_regime/ver2_1_daily_mtm_stress_summary.csv`
- `outputs/ver2_downside_protection/ver2_1_dte_regime/ver2_1_regime_conditional_performance.csv`
- `outputs/ver2_downside_protection/ver2_1_dte_regime/ver2_1_daily_mtm.csv`
"""
    report_path.write_text(text, encoding="utf-8")
    return report_path


def write_ver2_1_report(tables: Ver21Tables, report_path: Path) -> Path:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    skipped = tables.skipped_periods
    skipped_section = "_No skipped periods._"
    if not skipped.empty:
        skipped_summary = (
            skipped.groupby(["etf_code", "dte_label", "strategy_name", "skip_category"])
            .size()
            .reset_index(name="count")
        )
        skipped_section = _markdown_table(_head_per_etf(skipped_summary, 30))
    metadata = tables.metadata
    text = f"""# ver2.1 Non-ITM Covered Call DTE x Regime Diagnostic

## 实验定位

ver2.1 不是最终动态策略，而是优化前的机制诊断。它用于回答：在非 ITM 策略空间内，DTE 与市场状态如何影响 ATM/OTM/低 delta call 的权利金收入、下跌缓冲、回撤控制和反弹截断风险。

## 实验设定

- ETF: 510300, 510050
- rolling mode: continuous rolling / hold to expiry，到期结算后立即尝试再开仓
- coverage ratio: 100%
- DTE: DTE14_strict_window target 14/window 7-21; DTE14_nearest_continuous target 14/window 7-21 with nearest-available fallback; DTE30 window 20-45; DTE45 window 35-60; DTE60 window 50-75
- 主策略: ATM_100, OTM2_100, OTM5_100
- Delta 策略: D50_100, D40_100, D30_100, D20_100
- 期权数据源: `{metadata.get("option_source")}`
- Delta 可用: `{metadata.get("delta_available")}`; IV 可用: `{metadata.get("iv_available")}`

ITM 策略不进入 ver2.1 主策略空间。ver2.0 中 ITM 的高总权利金包含较多 intrinsic value，且 assignment rate 高、premium capture 低，因此这里只把非实值与低 delta call 作为机制诊断主体。

## 状态变量说明

- trend_5d / trend_20d / trend_60d: 入场日向前看的 ETF 累计收益。
- ma_gap_20 / ma_gap_60: 入场价格相对均线的偏离。
- drawdown_from_rolling_high: 入场日相对 252 日滚动高点的回撤。
- post_drawdown_rebound_risk: 深回撤后短期反弹迹象的启发式标签。
- rv_20d / rv_60d: 入场日前历史收益计算的年化实现波动率。
- iv_at_entry / iv_percentile / iv_minus_rv: 仅在选中期权有 IV 字段时计算。
- policy_jump_like: 只用于事后归因，不作为可交易择时信号。
- 流动性字段不作为核心 regime variable，仅作为 execution quality diagnostics。

## 核心结果预览

{_markdown_table(_summary_preview(tables.summary))}

## Metric scopes

- full_account_metrics: 包含 ETF-only gap，反映真实账户路径。
- active_overlay_metrics: 只统计 option_selected_flag = 1 的 short call 覆盖周期，用来观察 overlay 本身的收入、payoff 和下跌缓冲特征。

{_markdown_table(_active_overlay_preview(tables.active_overlay_metrics))}

## DTE robustness ranking

{_markdown_table(_ranking_preview(tables.dte_robustness_ranking))}

ranking score 仅用于诊断排序：年化 extrinsic premium yield、下跌缓冲、最大回撤改善、premium capture 越高越好；daily MTM 最大回撤、short call MTM 最大亏损、missed rebound return 越低越好。upside_cost_mean 保留为辅助诊断，不进入主排序。

如果某一 DTE 的 effective_option_coverage_ratio < 90%，则其 missed_rebound_return、max_drawdown 和 annualized_return 不能直接与连续覆盖策略横向比较。覆盖率较低可能意味着该 DTE 有更多时间只是持有 ETF，而不是持续持有 short call 风险暴露。

DTE14_strict_window 单独归类为 near-expiry overlay strategy；DTE30 / DTE45 / DTE60 属于 continuous covered-call comparison；DTE14_nearest_continuous 是为了观察近月短期限在接近连续覆盖时的机制表现。因此本报告保持克制，只把 DTE ranking 作为机制线索，不直接宣布 DTE60 或任何单一 DTE 最优。

## Effective option coverage diagnostics

{_markdown_table(_coverage_preview(tables.effective_coverage_summary))}

effective_option_coverage_ratio = active_short_call_days / total_backtest_days。ETF-only gap days 主要来自严格 DTE window 下没有合格到期日的短暂空窗；terminal_insufficient_horizon 表示样本末端剩余天数不足以开启下一轮合格 DTE 周期，不能与真正无合约混在一起。

## Down-then-rebound events

事件定义包含两类：上一周期 ETF 下跌超过 3% 后本周期反弹超过 3%，或本周期被标记为 policy_jump_like。该表用于观察 covered call 在反弹阶段的 recovery capture 与 missed rebound return。

事件数量: `{len(tables.down_then_rebound_events)}`

## Skipped periods

{skipped_section}

当前 skipped periods 使用 reclassified skip_category：

- terminal_insufficient_horizon: 样本末端剩余天数不足以开启下一轮合格 DTE 周期。
- no_eligible_expiry_in_window: 当天有期权链，但没有到期日落在该 DTE window。
- data_missing_or_chain_unavailable: 当天缺少可用 call 链。
- other_selection_failure: 其他选券失败。

DTE45/DTE60 的 skipped 多数属于 no_eligible_expiry_in_window，原因是交易所到期日离散，某些 roll date 附近可用 DTE 会从窗口短端直接跳到窗口长端之外。该问题会降低有效 short call 覆盖比例，所以 DTE ranking 必须结合 coverage diagnostics 一起读。

## 输出文件

- `ver2_1_dte_moneyness_summary.csv`
- `ver2_1_regime_conditional_performance.csv`
- `ver2_1_down_then_rebound_events.csv`
- `ver2_1_dte_robustness_ranking.csv`
- `ver2_1_daily_mtm_stress_summary.csv`
- `ver2_1_effective_coverage_summary.csv`
- `ver2_1_full_account_metrics.csv`
- `ver2_1_active_overlay_metrics.csv`
- `ver2_1_periods_with_regime.csv`
- `ver2_1_daily_mtm.csv`
- `ver2_1_skipped_periods.csv`

## 后续扩展

1. 用 ver2.1 的 regime diagnostics 选择少量候选 DTE 与 moneyness/delta 组合。
2. 在 ver2.2 中再引入动态覆盖率或择时规则，但必须只使用入场日前可见信息。
3. 把 bid/ask spread、成交量和 open interest 放进 execution quality dashboard，而不是把它们混入市场状态变量。
"""
    report_path.write_text(text, encoding="utf-8")
    return report_path


def write_ver2_1_outputs(base_config: ExperimentConfig, tables: Ver21Tables) -> dict[str, Path]:
    output_dir = base_config.paths.output_dir / "ver2_1_dte_regime"
    report_dir = base_config.paths.output_dir / "reports"
    paths = {
        "summary": _write_csv(tables.summary, output_dir / "ver2_1_dte_moneyness_summary.csv"),
        "regime_conditional_performance": _write_csv(
            tables.regime_conditional_performance,
            output_dir / "ver2_1_regime_conditional_performance.csv",
        ),
        "down_then_rebound_events": _write_csv(
            tables.down_then_rebound_events,
            output_dir / "ver2_1_down_then_rebound_events.csv",
        ),
        "dte_robustness_ranking": _write_csv(
            tables.dte_robustness_ranking,
            output_dir / "ver2_1_dte_robustness_ranking.csv",
        ),
        "daily_mtm_stress_summary": _write_csv(
            tables.daily_mtm_stress_summary,
            output_dir / "ver2_1_daily_mtm_stress_summary.csv",
        ),
        "effective_coverage_summary": _write_csv(
            tables.effective_coverage_summary,
            base_config.paths.output_dir / "ver2_1_effective_coverage_summary.csv",
        ),
        "full_account_metrics": _write_csv(
            tables.summary,
            base_config.paths.output_dir / "ver2_1_full_account_metrics.csv",
        ),
        "active_overlay_metrics": _write_csv(
            tables.active_overlay_metrics,
            base_config.paths.output_dir / "ver2_1_active_overlay_metrics.csv",
        ),
        "standard_performance_summary": _write_csv(
            tables.standard_performance_summary,
            base_config.paths.output_dir / "ver2_1_standard_performance_summary.csv",
        ),
        "candidate_shortlist": _write_csv(
            tables.candidate_shortlist,
            base_config.paths.output_dir / "ver2_1_candidate_shortlist.csv",
        ),
        "periods_with_regime": _write_csv(tables.periods, output_dir / "ver2_1_periods_with_regime.csv"),
        "daily_mtm": _write_csv(tables.daily_mtm, output_dir / "ver2_1_daily_mtm.csv"),
        "skipped_periods": _write_csv(tables.skipped_periods, output_dir / "ver2_1_skipped_periods.csv"),
    }
    manifest_path = output_dir / "ver2_1_manifest.json"
    manifest_path.write_text(json.dumps(tables.metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    paths["manifest"] = manifest_path
    paths["report"] = write_ver2_1_report(
        tables,
        report_dir / "ver2_1_non_itm_dte_regime_diagnostic.md",
    )
    paths["readable_report"] = write_ver2_1_readable_report(
        tables,
        report_dir / "ver2_1_non_itm_dte_regime_diagnostic_readable.md",
    )
    paths["final_main_report"] = write_ver2_1_readable_report(
        tables,
        report_dir / "ver2_1_final_main_report.md",
    )
    return paths
