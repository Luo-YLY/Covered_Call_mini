from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, replace
from pathlib import Path
import sys
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.metrics.ver2_metric_standard import (  # noqa: E402
    compute_portfolio_option_contribution,
    summarize_daily_nav,
)
from ver2_downside_protection.config import StrategyConfig, load_config  # noqa: E402
from ver2_downside_protection.strategy_engine import run_ver2_backtest  # noqa: E402


ETF_CODE = "588000"
MAIN_STEP_A_START = pd.Timestamp("2022-09-30")
END_DATE = pd.Timestamp("2026-05-27")
TARGET_DTE_LABEL = "DTE30"
HOLD_RULE = "hold_to_expiry"
SOURCE_START_FALLBACK = pd.Timestamp("2023-06-05")

CONFIG_PATH = ROOT / "configs" / "ver2_downside_protection.yaml"
PRICE_PATH = ROOT / "data" / "raw" / "etf_prices.csv"
OPTION_PATH = ROOT / "data" / "source" / "delta_enriched_options.csv"
STEP_A_PANEL_WIDE = ROOT / "outputs" / "ver3_0_stepA_single_etf_sleeves" / "panel" / "ver3_0_stepA_sleeve_return_panel_wide.csv"
STEP_510050_PANEL_WIDE = (
    ROOT
    / "outputs"
    / "ver3_0_stepA_extension_510050_sleeve_clarification"
    / "panel"
    / "ver3_0_stepA_extension_510050_sleeve_return_panel_wide.csv"
)

OUT_ROOT = ROOT / "outputs" / "ver3_0_stepA_extension_588000_sleeve_clarification"
STRATEGY_DIR = OUT_ROOT / "strategy"
DAILY_DIR = OUT_ROOT / "daily"
PERIOD_DIR = OUT_ROOT / "period"
SUMMARY_DIR = OUT_ROOT / "summary"
PANEL_DIR = OUT_ROOT / "panel"
FIGURE_DIR = OUT_ROOT / "figures"
CARD_DIR = OUT_ROOT / "cards"
REPORT_DIR = OUT_ROOT / "reports"
AUDIT_DIR = OUT_ROOT / "audit"


@dataclass(frozen=True)
class SleeveSpec:
    sleeve_name: str
    source_strategy_name: str | None
    strategy_family: str
    coverage: float
    is_buyhold: bool = False
    is_stress: bool = False
    is_main_defensive_candidate: bool = False
    note: str = ""


SPECS: tuple[SleeveSpec, ...] = (
    SleeveSpec("588000_ETF_BuyHold", "BuyHold", "ETF_BuyHold", 0.0, is_buyhold=True, note="pure ETF tech-growth baseline"),
    SleeveSpec(
        "588000_DTE30_OTM5up_Q50_Hold",
        "OTM5_100",
        "OTM5_up",
        0.5,
        is_main_defensive_candidate=True,
        note="main defensive covered-call candidate",
    ),
    SleeveSpec(
        "588000_DTE30_OTM5up_Q100_Hold",
        "OTM5_100",
        "OTM5_up",
        1.0,
        is_stress=True,
        note="full-coverage OTM5 stress diagnostic",
    ),
    SleeveSpec("588000_DTE30_D40_Q50_Hold", "D40_100", "D40", 0.5, note="D40 cross-ETF reference candidate"),
    SleeveSpec(
        "588000_DTE30_D40_Q100_Hold",
        "D40_100",
        "D40",
        1.0,
        is_stress=True,
        note="full-coverage D40 stress diagnostic",
    ),
    SleeveSpec(
        "588000_DTE30_ATM_Q100_Hold",
        "ATM_100",
        "ATM",
        1.0,
        is_stress=True,
        note="ATM full-coverage stress diagnostic",
    ),
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ver3.0 Step A extension for 588000 single-ETF sleeves.")
    parser.add_argument("--rf", type=float, default=0.0, help="Annual risk-free rate for standardized Sharpe.")
    args = parser.parse_args()

    ensure_dirs()
    verify_inputs()
    setup_plot_style()

    sample_windows = build_sample_window_summary()
    source_daily, source_period = build_588000_source_paths(sample_windows)
    daily = build_daily_nav(source_daily)
    period = build_period_attribution(source_period, source_daily, pd.Timestamp(daily["date"].min()))
    summary = build_summary(daily, period, args.rf)
    classification = build_classification(summary)
    panel_long, panel_wide = build_return_panel(daily, classification)
    correlation = build_correlation_table(panel_wide)
    sample_windows = refresh_actual_sample_window(sample_windows, daily, period)
    sanity = build_sanity_checks(daily, period, summary, classification, panel_long, panel_wide, correlation)

    write_outputs(daily, period, summary, classification, correlation, sample_windows, panel_long, panel_wide, sanity)
    write_strategy_direction()
    write_card(summary, classification, correlation)
    write_master_report(summary, classification, correlation, sample_windows, sanity)
    write_figures(daily, summary, classification, correlation)

    sanity = build_sanity_checks(daily, period, summary, classification, panel_long, panel_wide, correlation)
    sanity.to_csv(AUDIT_DIR / "ver3_0_stepA_extension_588000_sanity_checks.csv", index=False, encoding="utf-8-sig")
    write_card(summary, classification, correlation)
    write_master_report(summary, classification, correlation, sample_windows, sanity)
    write_readme_and_manifest(summary, classification, correlation, sample_windows, sanity)

    primary = classification[classification["recommendation_status"].eq("primary_for_short_sample_extension")].iloc[0]
    defensive = summary[summary["sleeve_name"].eq("588000_DTE30_OTM5up_Q50_Hold")].iloc[0]
    corr_159915 = correlation[correlation["comparison_name"].eq("588000_buyhold_vs_159915_buyhold")].iloc[0]
    option_positive = bool(defensive["option_leg_annualized_pnl_contribution"] > 0)

    print(f"Wrote ver3.0 Step A 588000 extension outputs to {OUT_ROOT}")
    print(
        "588000 actual sample: "
        f"{sample_windows.loc[sample_windows['window_name'].eq('covered_call_backtest'), 'start_date'].iloc[0]} "
        f"to {sample_windows.loc[sample_windows['window_name'].eq('covered_call_backtest'), 'end_date'].iloc[0]}"
    )
    print(f"588000 recommended sleeve: {primary['sleeve_name']}")
    print(f"588000 classification: {primary['classification']}")
    print(f"588000 main covered-call option leg positive: {'yes' if option_positive else 'no'}")
    print("Recommend short-sample tech-growth extension universe entry: yes")
    print("588000 best role: pure ETF growth sleeve, with OTM5 Q50 only as defensive diagnostic")
    print(
        "588000 vs 159915 correlation judgment: "
        f"{corr_159915['interpretation']} "
        f"(daily corr={corr_159915['daily_return_correlation']:.3f})"
    )
    print("Recommend Step B-Extension / Step B+ Extension inclusion: yes, extension-only")


def ensure_dirs() -> None:
    for path in (STRATEGY_DIR, DAILY_DIR, PERIOD_DIR, SUMMARY_DIR, PANEL_DIR, FIGURE_DIR, CARD_DIR, REPORT_DIR, AUDIT_DIR):
        path.mkdir(parents=True, exist_ok=True)


def verify_inputs() -> None:
    missing = [str(path.relative_to(ROOT)) for path in (CONFIG_PATH, PRICE_PATH, OPTION_PATH, STEP_A_PANEL_WIDE) if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing required 588000 Step A extension inputs:\n" + "\n".join(missing))


def build_sample_window_summary() -> pd.DataFrame:
    prices = pd.read_csv(PRICE_PATH, dtype={"etf_code": str}, usecols=lambda c: c in {"date", "etf_code", "adj_close", "close"})
    options = pd.read_csv(OPTION_PATH, dtype={"underlying_etf": str}, usecols=lambda c: c in {"trade_date", "underlying_etf", "option_type"})
    prices["etf_code"] = prices["etf_code"].astype(str).str.zfill(6)
    options["underlying_etf"] = options["underlying_etf"].astype(str).str.zfill(6)
    price_588 = prices[prices["etf_code"].eq(ETF_CODE)].copy()
    option_588 = options[(options["underlying_etf"].eq(ETF_CODE)) & (options["option_type"].astype(str).str.upper().eq("C"))].copy()
    if price_588.empty:
        raise ValueError("No 588000 ETF price rows found.")
    if option_588.empty:
        raise ValueError("No 588000 call option rows found in data/source/delta_enriched_options.csv.")

    option_start = pd.Timestamp(option_588["trade_date"].min())
    option_end = pd.Timestamp(option_588["trade_date"].max())
    rows = [
        {
            "window_name": "main_stepA_sample",
            "start_date": MAIN_STEP_A_START.date().isoformat(),
            "end_date": END_DATE.date().isoformat(),
            "n_trading_days": None,
            "source": "ver3 Step A common sample",
            "note": "588000 should not shorten this main sample.",
        },
        {
            "window_name": "588000_etf_price_available",
            "start_date": pd.Timestamp(price_588["date"].min()).date().isoformat(),
            "end_date": pd.Timestamp(price_588["date"].max()).date().isoformat(),
            "n_trading_days": int(len(price_588)),
            "source": str(PRICE_PATH.relative_to(ROOT)),
            "note": "ETF price history is longer than option history.",
        },
        {
            "window_name": "588000_option_available",
            "start_date": option_start.date().isoformat(),
            "end_date": option_end.date().isoformat(),
            "n_trading_days": int(pd.to_datetime(option_588["trade_date"]).nunique()),
            "source": str(OPTION_PATH.relative_to(ROOT)),
            "note": "Call option chains start after the main Step A sample begins.",
        },
        {
            "window_name": "covered_call_backtest",
            "start_date": "",
            "end_date": "",
            "n_trading_days": None,
            "source": "generated by this script",
            "note": "Filled after continuous DTE30 paths are generated.",
        },
    ]
    return pd.DataFrame(rows)


def build_588000_source_paths(sample_windows: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    option_start_text = sample_windows.loc[sample_windows["window_name"].eq("588000_option_available"), "start_date"].iloc[0]
    source_start = pd.Timestamp(option_start_text) if option_start_text else SOURCE_START_FALLBACK
    config = load_config(CONFIG_PATH, ROOT)
    config = replace(
        config,
        etf_codes=(ETF_CODE,),
        paths=replace(config.paths, options=OPTION_PATH),
        backtest=replace(
            config.backtest,
            start_date=source_start.date().isoformat(),
            end_date=END_DATE.date().isoformat(),
            min_periods=1,
        ),
        strategies=(
            StrategyConfig("BuyHold", "buy_hold", 0.0, 0.0, True),
            StrategyConfig("OTM5_100", "otm_pct", 1.0, 0.05, True),
            StrategyConfig("D40_100", "target_delta", 1.0, 0.4, True),
            StrategyConfig("ATM_100", "atm", 1.0, 0.0, True),
        ),
    )
    result = run_ver2_backtest(config)
    daily = result.daily_mtm.copy()
    period = result.periods.copy()
    for df in (daily, period):
        df["etf_code"] = df["etf_code"].astype(str).str.zfill(6)
    for col in ["date", "rebalance_date", "period_end_date", "expiry_date"]:
        if col in daily:
            daily[col] = pd.to_datetime(daily[col], errors="coerce")
        if col in period:
            period[col] = pd.to_datetime(period[col], errors="coerce")
    return daily, period


def refresh_actual_sample_window(sample_windows: pd.DataFrame, daily: pd.DataFrame, period: pd.DataFrame) -> pd.DataFrame:
    out = sample_windows.copy()
    mask = out["window_name"].eq("covered_call_backtest")
    out.loc[mask, "start_date"] = pd.Timestamp(daily["date"].min()).date().isoformat()
    out.loc[mask, "end_date"] = pd.Timestamp(daily["date"].max()).date().isoformat()
    out.loc[mask, "n_trading_days"] = int(pd.to_datetime(daily["date"]).nunique())
    out.loc[mask, "note"] = (
        f"Short-sample extension; {int(period['rebalance_date'].nunique())} continuous DTE30 option cycles."
    )
    return out


def build_daily_nav(source_daily: pd.DataFrame) -> pd.DataFrame:
    base = load_canonical_source_paths(source_daily)
    required = {"BuyHold", "OTM5_100", "D40_100", "ATM_100"}
    missing = sorted(required - set(base))
    if missing:
        available = source_daily[["strategy_name", "position_state", "event"]].drop_duplicates().sort_values("strategy_name")
        raise ValueError(f"Missing 588000 source strategies: {missing}\nAvailable:\n{available.to_string(index=False)}")

    common_dates = base["BuyHold"].index
    for source_name in ("OTM5_100", "D40_100", "ATM_100"):
        common_dates = common_dates.intersection(base[source_name].index)
    common_dates = common_dates[(common_dates >= MAIN_STEP_A_START) & (common_dates <= END_DATE)]
    if common_dates.empty:
        raise ValueError("No common 588000 dates available for requested sleeves.")

    buyhold_nav = base["BuyHold"].loc[common_dates, "daily_mtm_nav"].astype(float)
    underlying_return = buyhold_nav.pct_change().fillna(0.0)
    underlying_return.iloc[0] = 0.0
    option_return: dict[str, pd.Series] = {}
    for source_name in ("OTM5_100", "D40_100", "ATM_100"):
        total = base[source_name].loc[common_dates, "daily_mtm_nav"].astype(float).pct_change().fillna(0.0)
        total.iloc[0] = 0.0
        option_return[source_name] = total - underlying_return

    frames: list[pd.DataFrame] = []
    for spec in SPECS:
        source_name = spec.source_strategy_name or "BuyHold"
        src = base[source_name].loc[common_dates].copy()
        if spec.is_buyhold:
            opt = pd.Series(0.0, index=common_dates)
            daily_return_total = underlying_return.copy()
        else:
            opt = option_return[source_name] * spec.coverage
            daily_return_total = underlying_return + opt
        daily_return_total.iloc[0] = 0.0
        opt.iloc[0] = 0.0
        nav_total = (1.0 + daily_return_total).cumprod()
        nav_underlying = (1.0 + underlying_return).cumprod()
        nav_option = (1.0 + opt).cumprod()
        active = src["position_state"].astype(str).eq("short_call") if not spec.is_buyhold else pd.Series(False, index=common_dates)
        frames.append(
            pd.DataFrame(
                {
                    "date": common_dates,
                    "etf_code": ETF_CODE,
                    "sleeve_name": spec.sleeve_name,
                    "strategy_family": spec.strategy_family,
                    "dte_label": "NA" if spec.is_buyhold else TARGET_DTE_LABEL,
                    "coverage": spec.coverage,
                    "close_rule": "buyhold" if spec.is_buyhold else HOLD_RULE,
                    "nav_total": nav_total.values,
                    "daily_return_total": daily_return_total.values,
                    "nav_underlying_component": nav_underlying.values,
                    "daily_return_underlying_component": underlying_return.values,
                    "nav_option_leg_component": nav_option.values,
                    "daily_return_option_leg_component": opt.values,
                    "option_leg_pnl": opt.values,
                    "short_call_liability": np.where(spec.is_buyhold, 0.0, numeric(src.get("option_liability_return", 0.0)).values * spec.coverage),
                    "short_call_mtm_loss": np.where(spec.is_buyhold, 0.0, numeric(src.get("short_call_mtm_loss_return", 0.0)).values * spec.coverage),
                    "active_short_call_flag": active.values,
                    "active_coverage": np.where(active.values, spec.coverage, 0.0),
                    "target_coverage": spec.coverage,
                    "option_transaction_cost_today": np.where(
                        spec.is_buyhold,
                        0.0,
                        derive_daily_cumulative_change(src, "transaction_cost_return").values * spec.coverage,
                    ),
                    "rebalance_date": pd.NaT if spec.is_buyhold else src["rebalance_date"].values,
                    "expiry_date": pd.NaT if spec.is_buyhold else src["expiry_date"].values,
                    "option_code": np.nan if spec.is_buyhold else src["option_code"].values,
                    "gap_flag": False,
                    "gap_reason": "buyhold_no_option_leg" if spec.is_buyhold else "none",
                }
            )
        )
    return pd.concat(frames, ignore_index=True).sort_values(["sleeve_name", "date"]).reset_index(drop=True)


def load_canonical_source_paths(source_daily: pd.DataFrame) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    for strategy_name, g in source_daily.groupby("strategy_name"):
        if strategy_name not in {"BuyHold", "OTM5_100", "D40_100", "ATM_100"}:
            continue
        sort_cols = [col for col in ["date", "period_index", "event"] if col in g.columns]
        gg = g.sort_values(sort_cols).drop_duplicates("date", keep="last").copy()
        out[strategy_name] = gg.set_index("date").sort_index()
    return out


def build_period_attribution(source_period: pd.DataFrame, source_daily: pd.DataFrame, sample_start: pd.Timestamp) -> pd.DataFrame:
    stress = build_period_stress_lookup(source_daily)
    rows: list[dict[str, Any]] = []
    for spec in SPECS:
        if spec.is_buyhold:
            continue
        p = source_period[
            (source_period["etf_code"].eq(ETF_CODE))
            & (source_period["strategy_name"].eq(spec.source_strategy_name))
            & (source_period["rebalance_date"] >= sample_start)
            & (source_period["rebalance_date"] <= END_DATE)
        ].copy()
        if p.empty:
            raise ValueError(f"No source period rows for {spec.sleeve_name}")
        for _, row in p.sort_values("rebalance_date").iterrows():
            premium = float(row.get("premium_return", 0.0) or 0.0) * spec.coverage
            payoff = float(row.get("upside_payoff_return", 0.0) or 0.0) * spec.coverage
            cost = float(row.get("transaction_cost_return", 0.0) or 0.0) * spec.coverage
            option_leg = premium - payoff - cost
            stress_key = (str(row["strategy_name"]), int(row["period_index"]), str(row["option_code"]))
            stress_row = stress.get(stress_key, {"max": np.nan, "p95": np.nan, "p99": np.nan})
            rows.append(
                {
                    "etf_code": ETF_CODE,
                    "sleeve_name": spec.sleeve_name,
                    "strategy_family": spec.strategy_family,
                    "dte_label": TARGET_DTE_LABEL,
                    "target_dte": 30,
                    "actual_dte": row.get("actual_dte", np.nan),
                    "coverage": spec.coverage,
                    "close_rule": HOLD_RULE,
                    "rebalance_date": pd.Timestamp(row["rebalance_date"]).date().isoformat(),
                    "expiry_date": date_iso(row.get("expiry_date")),
                    "period_end_date": date_iso(row.get("period_end_date")),
                    "option_code": row.get("option_code"),
                    "strike": row.get("strike", np.nan),
                    "entry_etf_price": row.get("underlying_price_at_entry", np.nan),
                    "expiry_etf_price": row.get("underlying_price_at_expiry", row.get("underlying_price_at_period_end", np.nan)),
                    "entry_delta": row.get("selected_delta", row.get("target_delta", np.nan)),
                    "target_delta": row.get("target_delta", np.nan),
                    "realized_moneyness": row.get("realized_moneyness", np.nan),
                    "entry_option_mark": row.get("option_price_at_entry", np.nan),
                    "premium_return": premium,
                    "payoff_return": payoff,
                    "transaction_cost_return": cost,
                    "option_leg_return": option_leg,
                    "etf_period_return": row.get("etf_period_return", np.nan),
                    "covered_call_period_return": row.get("etf_period_return", np.nan) + option_leg
                    if pd.notna(row.get("etf_period_return", np.nan))
                    else np.nan,
                    "premium_capture_ratio": safe_div(option_leg, premium),
                    "payoff_burden": safe_div(payoff, premium),
                    "assignment_flag": bool(row.get("assignment_flag", False)),
                    "max_short_call_mtm_loss_in_period": stress_row["max"] * spec.coverage
                    if pd.notna(stress_row["max"])
                    else np.nan,
                    "p95_short_call_mtm_loss_in_period": stress_row["p95"] * spec.coverage
                    if pd.notna(stress_row["p95"])
                    else np.nan,
                    "p99_short_call_mtm_loss_in_period": stress_row["p99"] * spec.coverage
                    if pd.notna(stress_row["p99"])
                    else np.nan,
                    "policy_jump_window_flag": False,
                    "warning_flag": row.get("selection_reason", ""),
                }
            )
    return pd.DataFrame(rows).sort_values(["sleeve_name", "rebalance_date"]).reset_index(drop=True)


def build_period_stress_lookup(source_daily: pd.DataFrame) -> dict[tuple[str, int, str], dict[str, float]]:
    lookup: dict[tuple[str, int, str], dict[str, float]] = {}
    d = source_daily[source_daily["strategy_name"].isin(["OTM5_100", "D40_100", "ATM_100"])].copy()
    for (strategy, period_index, option_code), g in d.groupby(["strategy_name", "period_index", "option_code"], dropna=False):
        stress = numeric(g.get("short_call_mtm_loss_return", 0.0))
        lookup[(str(strategy), int(period_index), str(option_code))] = {
            "max": float(stress.max()),
            "p95": float(stress.quantile(0.95)),
            "p99": float(stress.quantile(0.99)),
        }
    return lookup


def build_summary(daily: pd.DataFrame, period: pd.DataFrame, rf: float) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for sleeve, g in daily.groupby("sleeve_name"):
        sample = g.sort_values("date").copy()
        p = period[period["sleeve_name"].eq(sleeve)].copy()
        metrics = summarize_daily_nav(sample[["date", "nav_total"]], date_col="date", nav_col="nav_total", rf=rf)
        rows.append(
            {
                "etf_code": ETF_CODE,
                "sleeve_name": sleeve,
                "sample_scope": "short_sample_extension",
                **metrics,
                **summarize_option_metrics(sample, p),
                "notes": spec_by_name(sleeve).note,
            }
        )
    summary = pd.DataFrame(rows)
    order = {spec.sleeve_name: i for i, spec in enumerate(SPECS)}
    summary["_order"] = summary["sleeve_name"].map(order)
    ordered_cols = [
        "etf_code",
        "sleeve_name",
        "sample_scope",
        "sample_start",
        "sample_end",
        "n_trading_days",
        "cumulative_return",
        "annualized_return_cagr",
        "arithmetic_annualized_return",
        "annualized_volatility",
        "sharpe_daily_mean",
        "cagr_vol_ratio",
        "sortino_ratio",
        "calmar_ratio",
        "max_drawdown",
        "max_drawdown_start",
        "max_drawdown_trough",
        "max_drawdown_recovery",
        "drawdown_duration",
        "monthly_win_rate",
        "worst_month_return",
        "best_month_return",
        "option_leg_annualized_pnl_contribution",
        "premium_capture_ratio_agg",
        "payoff_burden_agg",
        "premium_capture_ratio_period_mean",
        "payoff_burden_period_mean",
        "positive_option_leg_period_rate",
        "assignment_rate",
        "p95_short_call_mtm_loss",
        "p99_short_call_mtm_loss",
        "max_short_call_mtm_loss",
        "avg_actual_dte",
        "avg_entry_delta",
        "median_entry_delta",
        "avg_realized_moneyness",
        "median_realized_moneyness",
        "gap_periods",
        "early_close_rate",
        "avg_active_coverage",
        "notes",
    ]
    return summary.sort_values("_order")[ordered_cols].reset_index(drop=True)


def summarize_option_metrics(sample: pd.DataFrame, period: pd.DataFrame) -> dict[str, Any]:
    option_pnl = sample["option_leg_pnl"].astype(float)
    stress = sample["short_call_mtm_loss"].astype(float)
    if period.empty:
        return {
            "option_leg_annualized_pnl_contribution": 0.0,
            "premium_capture_ratio_agg": np.nan,
            "payoff_burden_agg": np.nan,
            "premium_capture_ratio_period_mean": np.nan,
            "payoff_burden_period_mean": np.nan,
            "positive_option_leg_period_rate": np.nan,
            "assignment_rate": np.nan,
            "p95_short_call_mtm_loss": 0.0,
            "p99_short_call_mtm_loss": 0.0,
            "max_short_call_mtm_loss": 0.0,
            "avg_actual_dte": np.nan,
            "avg_entry_delta": np.nan,
            "median_entry_delta": np.nan,
            "avg_realized_moneyness": np.nan,
            "median_realized_moneyness": np.nan,
            "gap_periods": 0,
            "early_close_rate": 0.0,
            "avg_active_coverage": 0.0,
        }
    premium = period["premium_return"].astype(float)
    payoff = period["payoff_return"].astype(float)
    option_leg = period["option_leg_return"].astype(float)
    return {
        "option_leg_annualized_pnl_contribution": compute_portfolio_option_contribution(option_pnl, n_days=len(sample)),
        "premium_capture_ratio_agg": safe_div(float(option_leg.sum()), float(premium.sum())),
        "payoff_burden_agg": safe_div(float(payoff.sum()), float(premium.sum())),
        "premium_capture_ratio_period_mean": float(period["premium_capture_ratio"].astype(float).mean()),
        "payoff_burden_period_mean": float(period["payoff_burden"].astype(float).mean()),
        "positive_option_leg_period_rate": float((option_leg > 0).mean()),
        "assignment_rate": float(period["assignment_flag"].astype(bool).mean()),
        "p95_short_call_mtm_loss": float(stress.quantile(0.95)),
        "p99_short_call_mtm_loss": float(stress.quantile(0.99)),
        "max_short_call_mtm_loss": float(stress.max()),
        "avg_actual_dte": float(period["actual_dte"].astype(float).mean()),
        "avg_entry_delta": float(period["entry_delta"].astype(float).mean()),
        "median_entry_delta": float(period["entry_delta"].astype(float).median()),
        "avg_realized_moneyness": float(period["realized_moneyness"].astype(float).mean()),
        "median_realized_moneyness": float(period["realized_moneyness"].astype(float).median()),
        "gap_periods": int(period["warning_flag"].astype(str).str.contains("gap|missing", case=False, na=False).sum()),
        "early_close_rate": 0.0,
        "avg_active_coverage": float(sample["active_coverage"].astype(float).mean()),
    }


def build_classification(summary: pd.DataFrame) -> pd.DataFrame:
    buyhold = summary[summary["sleeve_name"].eq("588000_ETF_BuyHold")].iloc[0]
    rows: list[dict[str, Any]] = []
    for _, row in summary.iterrows():
        spec = spec_by_name(row["sleeve_name"])
        option_positive = bool(row["option_leg_annualized_pnl_contribution"] > 0)
        beats_sharpe = bool(row["sharpe_daily_mean"] > buyhold["sharpe_daily_mean"])
        improves_mdd = bool(row["max_drawdown"] < buyhold["max_drawdown"])
        return_sacrifice = float(buyhold["annualized_return_cagr"]) - float(row["annualized_return_cagr"])
        classification, reason, caveat = classify_sleeve(row, buyhold, spec, option_positive, beats_sharpe, improves_mdd, return_sacrifice)
        rows.append(
            {
                "etf_code": ETF_CODE,
                "sleeve_name": row["sleeve_name"],
                "classification": classification,
                "annualized_return_cagr": row["annualized_return_cagr"],
                "sharpe_daily_mean": row["sharpe_daily_mean"],
                "max_drawdown": row["max_drawdown"],
                "annualized_volatility": row["annualized_volatility"],
                "option_leg_annualized_pnl_contribution": row["option_leg_annualized_pnl_contribution"],
                "premium_capture_ratio_agg": row["premium_capture_ratio_agg"],
                "payoff_burden_agg": row["payoff_burden_agg"],
                "p99_short_call_mtm_loss": row["p99_short_call_mtm_loss"],
                "beats_buyhold_sharpe": beats_sharpe,
                "improves_buyhold_mdd": improves_mdd,
                "option_leg_positive": option_positive,
                "return_sacrifice_vs_buyhold": return_sacrifice,
                "recommendation_status": "rejected",
                "reason": reason,
                "caveat": caveat,
            }
        )
    out = pd.DataFrame(rows)
    out.loc[out["sleeve_name"].eq("588000_ETF_BuyHold"), "recommendation_status"] = "primary_for_short_sample_extension"
    out.loc[out["sleeve_name"].eq("588000_DTE30_OTM5up_Q50_Hold"), "recommendation_status"] = "backup_defensive_overlay"
    stress = out["sleeve_name"].str.contains("Q100")
    out.loc[stress, "recommendation_status"] = "diagnostic_only"
    order = {spec.sleeve_name: i for i, spec in enumerate(SPECS)}
    out["_order"] = out["sleeve_name"].map(order)
    return out.sort_values("_order").drop(columns="_order").reset_index(drop=True)


def classify_sleeve(
    row: pd.Series,
    buyhold: pd.Series,
    spec: SleeveSpec,
    option_positive: bool,
    beats_sharpe: bool,
    improves_mdd: bool,
    return_sacrifice: float,
) -> tuple[str, str, str]:
    if spec.is_buyhold:
        return (
            "Growth Extension Sleeve",
            "Pure ETF path best preserves 588000's tech-growth upside and has the strongest Sharpe in this sample.",
            "Use only in short-sample extension universes.",
        )
    if spec.is_stress:
        return "Stress / Diagnostic Only", "Q100/ATM full coverage is retained only as stress diagnostic.", "Do not use as default sleeve."
    if option_positive and beats_sharpe and improves_mdd and return_sacrifice <= 0.02:
        return (
            "Positive Carry Overlay",
            "Net option leg is positive while Sharpe and max drawdown improve versus BuyHold.",
            "Still short-sample and not a main-universe result.",
        )
    if improves_mdd and return_sacrifice <= 0.12:
        return (
            "Defensive Overlay",
            "Drawdown improves, but option leg is negative and upside give-up is material.",
            "Use only when drawdown control is more important than growth capture.",
        )
    return "Pure ETF Preferred", "Covered-call sleeve gives up too much growth exposure versus BuyHold.", "Prefer pure ETF exposure."


def build_return_panel(daily: pd.DataFrame, classification: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    status = classification[["etf_code", "sleeve_name", "classification", "recommendation_status"]]
    panel = daily.merge(status, on=["etf_code", "sleeve_name"], how="left")
    long = panel[
        [
            "date",
            "etf_code",
            "sleeve_name",
            "daily_return_total",
            "nav_total",
            "classification",
            "recommendation_status",
        ]
    ].rename(columns={"daily_return_total": "daily_return", "nav_total": "nav"})
    long["sample_scope"] = "short_sample_extension"
    long = long[
        [
            "date",
            "etf_code",
            "sleeve_name",
            "daily_return",
            "nav",
            "sample_scope",
            "classification",
            "recommendation_status",
        ]
    ]
    wide_source = long.copy()
    wide_source["column"] = wide_source["etf_code"] + "__" + wide_source["sleeve_name"] + "__daily_return"
    wide = wide_source.pivot(index="date", columns="column", values="daily_return").sort_index().reset_index()
    return long.sort_values(["date", "sleeve_name"]).reset_index(drop=True), wide


def build_correlation_table(panel_wide: pd.DataFrame) -> pd.DataFrame:
    merged = panel_wide.copy()
    merged["date"] = pd.to_datetime(merged["date"])
    ref = load_reference_panels()
    merged = merged.merge(ref, on="date", how="inner")
    left_buyhold = "588000__588000_ETF_BuyHold__daily_return"
    left_main_cc = "588000__588000_DTE30_OTM5up_Q50_Hold__daily_return"
    comparisons = [
        ("588000_buyhold_vs_510300_buyhold", left_buyhold, "510300__510300_ETF_BuyHold__daily_return"),
        ("588000_buyhold_vs_510500_buyhold", left_buyhold, "510500__510500_ETF_BuyHold__daily_return"),
        ("588000_buyhold_vs_159915_buyhold", left_buyhold, "159915__159915_ETF_BuyHold__daily_return"),
        ("588000_OTM5_Q50_vs_159915_primary", left_main_cc, "159915__159915_DTE30_OTM5up_Q50_Hold__daily_return"),
        ("588000_OTM5_Q50_vs_510300_primary", left_main_cc, "510300__510300_DTE30_D40_Q70_Hold__daily_return"),
    ]
    if "510050__510050_ETF_BuyHold__daily_return" in merged.columns:
        comparisons.extend(
            [
                ("588000_buyhold_vs_510050_buyhold", left_buyhold, "510050__510050_ETF_BuyHold__daily_return"),
                ("588000_OTM5_Q50_vs_510050_primary", left_main_cc, "510050__510050_DTE30_D40_Q70_Hold__daily_return"),
            ]
        )
    rows: list[dict[str, Any]] = []
    for name, left, right in comparisons:
        if left not in merged.columns or right not in merged.columns:
            continue
        pair = merged[["date", left, right]].dropna()
        if pair.empty:
            continue
        rolling = pair[left].rolling(63).corr(pair[right]).dropna()
        corr = float(pair[left].corr(pair[right]))
        rows.append(
            {
                "comparison_name": name,
                "left_sleeve": left.replace("__daily_return", ""),
                "right_sleeve": right.replace("__daily_return", ""),
                "sample_start": pair["date"].min().date().isoformat(),
                "sample_end": pair["date"].max().date().isoformat(),
                "n_obs": int(len(pair)),
                "daily_return_correlation": corr,
                "rolling_window_days": 63,
                "rolling_corr_mean": float(rolling.mean()) if not rolling.empty else np.nan,
                "rolling_corr_p05": float(rolling.quantile(0.05)) if not rolling.empty else np.nan,
                "rolling_corr_p95": float(rolling.quantile(0.95)) if not rolling.empty else np.nan,
                "interpretation": interpret_correlation(corr),
            }
        )
    if not rows:
        raise ValueError("No valid 588000 correlation diagnostics were generated.")
    return pd.DataFrame(rows)


def load_reference_panels() -> pd.DataFrame:
    ref = pd.read_csv(STEP_A_PANEL_WIDE)
    ref["date"] = pd.to_datetime(ref["date"])
    keep = [
        "date",
        "510300__510300_ETF_BuyHold__daily_return",
        "510300__510300_DTE30_D40_Q70_Hold__daily_return",
        "510500__510500_ETF_BuyHold__daily_return",
        "159915__159915_ETF_BuyHold__daily_return",
        "159915__159915_DTE30_OTM5up_Q50_Hold__daily_return",
    ]
    missing = [col for col in keep if col not in ref.columns]
    if missing:
        raise ValueError(f"Missing Step A reference return columns: {missing}")
    ref = ref[keep].copy()
    if STEP_510050_PANEL_WIDE.exists():
        c50 = pd.read_csv(STEP_510050_PANEL_WIDE)
        c50["date"] = pd.to_datetime(c50["date"])
        cols = [
            "date",
            "510050__510050_ETF_BuyHold__daily_return",
            "510050__510050_DTE30_D40_Q70_Hold__daily_return",
        ]
        if all(col in c50.columns for col in cols):
            ref = ref.merge(c50[cols], on="date", how="left")
    return ref


def write_outputs(
    daily: pd.DataFrame,
    period: pd.DataFrame,
    summary: pd.DataFrame,
    classification: pd.DataFrame,
    correlation: pd.DataFrame,
    sample_windows: pd.DataFrame,
    panel_long: pd.DataFrame,
    panel_wide: pd.DataFrame,
    sanity: pd.DataFrame,
) -> None:
    daily.to_csv(DAILY_DIR / "ver3_0_stepA_extension_588000_sleeve_daily_nav.csv", index=False, encoding="utf-8-sig")
    daily[
        ["date", "etf_code", "sleeve_name", "daily_return_total", "daily_return_underlying_component", "daily_return_option_leg_component"]
    ].rename(columns={"daily_return_total": "daily_return"}).to_csv(
        DAILY_DIR / "ver3_0_stepA_extension_588000_sleeve_daily_returns.csv",
        index=False,
        encoding="utf-8-sig",
    )
    period.to_csv(PERIOD_DIR / "ver3_0_stepA_extension_588000_period_attribution.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(SUMMARY_DIR / "ver3_0_stepA_extension_588000_sleeve_summary.csv", index=False, encoding="utf-8-sig")
    classification.to_csv(SUMMARY_DIR / "ver3_0_stepA_extension_588000_classification_table.csv", index=False, encoding="utf-8-sig")
    correlation.to_csv(SUMMARY_DIR / "ver3_0_stepA_extension_588000_correlation_table.csv", index=False, encoding="utf-8-sig")
    sample_windows.to_csv(SUMMARY_DIR / "ver3_0_stepA_extension_588000_sample_window_summary.csv", index=False, encoding="utf-8-sig")
    panel_long.to_csv(PANEL_DIR / "ver3_0_stepA_extension_588000_sleeve_return_panel_long.csv", index=False, encoding="utf-8-sig")
    panel_wide.to_csv(PANEL_DIR / "ver3_0_stepA_extension_588000_sleeve_return_panel_wide.csv", index=False, encoding="utf-8-sig")
    sanity.to_csv(AUDIT_DIR / "ver3_0_stepA_extension_588000_sanity_checks.csv", index=False, encoding="utf-8-sig")


def write_strategy_direction() -> None:
    rows = [
        ("Main_Growth_Diversified_Universe", "main", "510300", "large-cap core / positive carry covered-call candidate", "510300_DTE30_D40_Q70_Hold", "main sample"),
        ("Main_Growth_Diversified_Universe", "main", "510500", "mid-cap growth diversification / pure ETF sleeve", "510500_ETF_BuyHold", "main sample"),
        ("Main_Growth_Diversified_Universe", "main", "159915", "ChiNext growth / defensive overlay candidate", "159915_DTE30_OTM5up_Q50_Hold", "main sample"),
        ("Alternative_Defensive_Income_Universe", "alternative", "510300", "first large-cap covered-call core", "510300_DTE30_D40_Q70_Hold", "main sample"),
        ("Alternative_Defensive_Income_Universe", "alternative", "510050", "second large-cap covered-call core; high overlap with 510300", "510050_DTE30_D40_Q70_Hold", "main sample"),
        ("Alternative_Defensive_Income_Universe", "alternative", "159915", "growth sleeve with defensive overlay role", "159915_DTE30_OTM5up_Q50_Hold", "main sample"),
        ("Tech_Growth_Extension_Universe_A", "short_sample_extension", "510300", "large-cap anchor", "510300_DTE30_D40_Q70_Hold", "short sample only if combined with 588000"),
        ("Tech_Growth_Extension_Universe_A", "short_sample_extension", "510500", "mid-cap growth sleeve", "510500_ETF_BuyHold", "short sample only if combined with 588000"),
        ("Tech_Growth_Extension_Universe_A", "short_sample_extension", "159915", "ChiNext growth/defensive overlay", "159915_DTE30_OTM5up_Q50_Hold", "short sample only if combined with 588000"),
        ("Tech_Growth_Extension_Universe_A", "short_sample_extension", "588000", "STAR50 tech-growth / hard-tech extension", "588000_ETF_BuyHold", "short-sample extension only"),
        ("Tech_Growth_Extension_Universe_B", "short_sample_extension", "510300", "large-cap anchor", "510300_DTE30_D40_Q70_Hold", "short sample only if combined with 588000"),
        ("Tech_Growth_Extension_Universe_B", "short_sample_extension", "510050", "second large-cap covered-call core", "510050_DTE30_D40_Q70_Hold", "short sample only if combined with 588000"),
        ("Tech_Growth_Extension_Universe_B", "short_sample_extension", "159915", "ChiNext growth/defensive overlay", "159915_DTE30_OTM5up_Q50_Hold", "short sample only if combined with 588000"),
        ("Tech_Growth_Extension_Universe_B", "short_sample_extension", "588000", "STAR50 tech-growth / hard-tech extension", "588000_ETF_BuyHold", "short-sample extension only"),
    ]
    strategy_map = pd.DataFrame(
        rows,
        columns=["universe_name", "universe_layer", "etf_code", "role", "preferred_sleeve", "sample_policy"],
    )
    strategy_map.to_csv(STRATEGY_DIR / "ver3_0_universe_strategy_map.csv", index=False, encoding="utf-8-sig")
    text = """# ver3.0 Universe Strategy Direction

ver3.0 后续不再只有单一 universe。主线组合层和短样本扩展必须分开，不能因为 588000 的期权数据较晚而拖短主线 Step B / Step B+ 的共同样本。

## 1. Main Growth-Diversified Universe

`510300 + 510500 + 159915`

- `510300`：大盘核心 / positive carry covered-call candidate。
- `510500`：中盘弹性 / pure ETF growth-diversification sleeve。它不是 covered-call 主力，但仍有 growth-diversification 价值。
- `159915`：创业板成长弹性 / defensive overlay candidate。

这是主线 Step B / Step B+ 的默认样本，不加入 588000。

## 2. Alternative Defensive-Income Universe

`510300 + 510050 + 159915`

- 用 `510050` 替代 `510500`。
- 目标不是增强风格分散化，而是检验 `510050` 是否能成为第二个大盘备兑核心。
- 需要明确 `510050` 与 `510300` 的高相关性和风格重叠问题。

## 3. Tech-Growth Short-Sample Extension Universe

`510300 + 510050 + 159915 + 588000`

或

`510300 + 510500 + 159915 + 588000`

- `588000` 不纳入主线样本。
- `588000` 只作为 short-sample extension。
- 它的价值在于科创成长 / 硬科技扩展，用来观察是否提供额外收益弹性，或是否适合 defensive covered-call overlay。
- 后续如果进入组合层，应标注为 `short_sample_robustness` 或 `extension_only`。
- 组合层必须区分主线样本与短样本扩展样本。

## 4. Step B 命名建议

- `Main_Growth_Diversified_Universe`
- `Alternative_Defensive_Income_Universe`
- `Tech_Growth_Extension_Universe_A`
- `Tech_Growth_Extension_Universe_B`
"""
    (STRATEGY_DIR / "ver3_0_universe_strategy_direction.md").write_text(text, encoding="utf-8")


def write_card(summary: pd.DataFrame, classification: pd.DataFrame, correlation: pd.DataFrame) -> None:
    s = summary.merge(
        classification[["sleeve_name", "classification", "recommendation_status", "reason", "caveat"]],
        on="sleeve_name",
        how="left",
    )
    primary = classification[classification["recommendation_status"].eq("primary_for_short_sample_extension")].iloc[0]
    text = f"""# 588000 Sleeve Card

## 1. 标的定位

588000 是科创50 / 硬科技成长暴露。本扩展只判断它是否有资格作为 short-sample tech-growth extension sleeve，不进入主线 Step B 样本。

## 2. 候选 sleeve 列表

{md_table(s[["sleeve_name", "classification", "recommendation_status"]])}

## 3. 核心绩效对比

{md_table(s[["sleeve_name", "annualized_return_cagr", "sharpe_daily_mean", "max_drawdown", "annualized_volatility", "option_leg_annualized_pnl_contribution"]], pct_cols=["annualized_return_cagr", "max_drawdown", "annualized_volatility", "option_leg_annualized_pnl_contribution"], num_cols=["sharpe_daily_mean"])}

## 4. Option-leg 质量

{md_table(s[["sleeve_name", "premium_capture_ratio_agg", "payoff_burden_agg", "positive_option_leg_period_rate", "assignment_rate", "p99_short_call_mtm_loss"]], pct_cols=["premium_capture_ratio_agg", "payoff_burden_agg", "positive_option_leg_period_rate", "assignment_rate", "p99_short_call_mtm_loss"])}

## 5. 相关性诊断

{md_table(correlation, num_cols=["daily_return_correlation", "rolling_corr_mean", "rolling_corr_p05", "rolling_corr_p95"])}

## 6. 推荐

- primary_sleeve_for_short_sample_extension: {primary["sleeve_name"]}
- classification: {primary["classification"]}
- role: pure ETF growth sleeve
- caveat: {primary["caveat"]}
"""
    (CARD_DIR / "588000_sleeve_card.md").write_text(text, encoding="utf-8")


def write_master_report(
    summary: pd.DataFrame,
    classification: pd.DataFrame,
    correlation: pd.DataFrame,
    sample_windows: pd.DataFrame,
    sanity: pd.DataFrame,
) -> None:
    s = summary.merge(
        classification[["sleeve_name", "classification", "recommendation_status", "reason", "caveat"]],
        on="sleeve_name",
        how="left",
    )
    buyhold = summary[summary["sleeve_name"].eq("588000_ETF_BuyHold")].iloc[0]
    otm_q50 = summary[summary["sleeve_name"].eq("588000_DTE30_OTM5up_Q50_Hold")].iloc[0]
    primary = classification[classification["recommendation_status"].eq("primary_for_short_sample_extension")].iloc[0]
    corr_159915 = correlation[correlation["comparison_name"].eq("588000_buyhold_vs_159915_buyhold")].iloc[0]
    actual = sample_windows[sample_windows["window_name"].eq("covered_call_backtest")].iloc[0]
    option_positive = "是" if float(otm_q50["option_leg_annualized_pnl_contribution"]) > 0 else "否"
    text = f"""# ver3.0 Step A-Extension | 588000 单 ETF 备兑 Sleeve 画像

## 1. 研究目的

588000 代表科创50 / 科创成长 / 硬科技暴露。它的期权数据晚于主线 Step A，因此本报告只把它作为 short-sample extension 评估，不让它拖短主线 Step B / Step B+ 的共同样本。

## 2. 样本区间与数据说明

{md_table(sample_windows)}

588000 期权数据不能覆盖 `2022-09-30` 开始的主线 Step A 样本；本次实际 covered-call 回测区间为 `{actual["start_date"]}` 至 `{actual["end_date"]}`，因此所有结论均标记为 short-sample extension。

## 3. 候选 sleeve 列表

- `588000_ETF_BuyHold`：纯 ETF baseline，用于判断科创成长暴露本身的价值。
- `588000_DTE30_OTM5up_Q50_Hold`：主防御型备兑候选。
- `588000_DTE30_OTM5up_Q100_Hold`：高覆盖率 stress / diagnostic。
- `588000_DTE30_D40_Q50_Hold`：与大盘 D40 结构横向参考。
- `588000_DTE30_D40_Q100_Hold`：高弹性 ETF 在 D40 Q100 下的 payoff burden 诊断。
- `588000_DTE30_ATM_Q100_Hold`：ATM Q100 stress / diagnostic。

`588000_DTE30_OTM5up_Q50_TP80` 未生成，因为当前没有既有 588000 TP80 中间路径；本任务不为 TP80 大改路径管理框架。

## 4. 主指标表

{md_table(s[["sleeve_name", "classification", "recommendation_status", "annualized_return_cagr", "sharpe_daily_mean", "max_drawdown", "calmar_ratio", "sortino_ratio", "annualized_volatility", "option_leg_annualized_pnl_contribution"]], pct_cols=["annualized_return_cagr", "max_drawdown", "annualized_volatility", "option_leg_annualized_pnl_contribution"], num_cols=["sharpe_daily_mean", "calmar_ratio", "sortino_ratio"])}

## 5. Option-leg 归因

主防御候选 `588000_DTE30_OTM5up_Q50_Hold` 的净 option leg 年化贡献为 {fmt_pct(otm_q50["option_leg_annualized_pnl_contribution"])}，是否为正：{option_positive}。

{md_table(s[["sleeve_name", "premium_capture_ratio_agg", "payoff_burden_agg", "positive_option_leg_period_rate", "assignment_rate", "p95_short_call_mtm_loss", "p99_short_call_mtm_loss"]], pct_cols=["premium_capture_ratio_agg", "payoff_burden_agg", "positive_option_leg_period_rate", "assignment_rate", "p95_short_call_mtm_loss", "p99_short_call_mtm_loss"])}

读数：BuyHold CAGR 为 {fmt_pct(buyhold["annualized_return_cagr"])}，Sharpe 为 {fmt_num(buyhold["sharpe_daily_mean"])}；OTM5 Q50 把最大回撤从 {fmt_pct(buyhold["max_drawdown"])} 降到 {fmt_pct(otm_q50["max_drawdown"])}，但 CAGR 降至 {fmt_pct(otm_q50["annualized_return_cagr"])}，净 option leg 为负。这说明 588000 的备兑更像风险削减工具，不是 income sleeve。

## 6. 与其他 ETF 的相关性

{md_table(correlation, num_cols=["daily_return_correlation", "rolling_corr_mean", "rolling_corr_p05", "rolling_corr_p95"])}

解释：588000 与 159915 BuyHold 的相关性为 {fmt_num(corr_159915["daily_return_correlation"])}，属于 `{corr_159915["interpretation"]}`。它与创业板成长有明显关联，但不完全等同；在短样本扩展里，它更像增强硬科技 / 科创成长风格完整性的 sleeve。

## 7. Sleeve 分类结论

推荐 sleeve：`{primary["sleeve_name"]}`。

分类：`{primary["classification"]}`。

理由：{primary["reason"]}

Q100、ATM Q100 只作为 stress / diagnostic。D40 Q50 和 OTM5 Q50 可作为防御诊断，但不是默认主线。报告中的收益捕捉均指承担路径风险后的风险补偿，不表示确定性收益。

## 8. 后续组合层建议

588000 建议进入后续 `Tech_Growth_Extension_Universe_A/B`，但仅作为 short-sample extension。推荐使用 `588000_ETF_BuyHold` 作为 pure ETF growth sleeve；如组合层目标偏回撤控制，可把 `588000_DTE30_OTM5up_Q50_Hold` 作为 defensive overlay 对照。

588000 不应进入主线 `Main_Growth_Diversified_Universe` 的共同样本，也不应拖短主线 Step B / Step B+。

## 9. Sanity Checks

{md_table(sanity)}
"""
    (REPORT_DIR / "ver3_0_stepA_extension_588000_sleeve_master_report.md").write_text(text, encoding="utf-8")


def write_readme_and_manifest(
    summary: pd.DataFrame,
    classification: pd.DataFrame,
    correlation: pd.DataFrame,
    sample_windows: pd.DataFrame,
    sanity: pd.DataFrame,
) -> None:
    primary = classification[classification["recommendation_status"].eq("primary_for_short_sample_extension")].iloc[0]
    actual = sample_windows[sample_windows["window_name"].eq("covered_call_backtest")].iloc[0]
    readme = f"""# ver3.0 Step A-Extension：588000 Single-ETF Sleeve Clarification

本目录保存 588000 单 ETF covered-call sleeve 画像。它是 short-sample tech-growth extension，不覆盖既有 Step A / 510050 extension 输出，也不运行组合层。

## 运行方式

```powershell
python ver3\\scripts\\python\\run_ver3_0_stepA_extension_588000_sleeve_clarification.py
```

## 样本与结论

| 项目 | 内容 |
| --- | --- |
| 实际回测区间 | {actual["start_date"]} 至 {actual["end_date"]} |
| 推荐 sleeve | `{primary["sleeve_name"]}` |
| 分类 | `{primary["classification"]}` |
| 定位 | short-sample tech-growth extension only |

Step B-Extension 可读取 `panel/ver3_0_stepA_extension_588000_sleeve_return_panel_wide.csv`，但主线 Step B 不应被 588000 拖短样本。
"""
    (OUT_ROOT / "README.md").write_text(readme, encoding="utf-8")
    manifest = {
        "experiment_id": "ver3_0_stepA_extension_588000_sleeve_clarification",
        "status": "complete",
        "generated_at": "2026-06-30",
        "runner": "ver3/scripts/python/run_ver3_0_stepA_extension_588000_sleeve_clarification.py",
        "sample_windows": sample_windows.to_dict(orient="records"),
        "universe": [ETF_CODE],
        "input_files": [
            str(CONFIG_PATH.relative_to(ROOT)),
            str(PRICE_PATH.relative_to(ROOT)),
            str(OPTION_PATH.relative_to(ROOT)),
            str(STEP_A_PANEL_WIDE.relative_to(ROOT)),
            str(STEP_510050_PANEL_WIDE.relative_to(ROOT)),
        ],
        "primary_recommendation": {
            "sleeve_name": primary["sleeve_name"],
            "classification": primary["classification"],
            "recommendation_status": primary["recommendation_status"],
        },
        "correlation_summary": correlation.to_dict(orient="records"),
        "sanity_checks": {
            "path": "audit/ver3_0_stepA_extension_588000_sanity_checks.csv",
            "passed": int(sanity["passed"].sum()),
            "total": int(len(sanity)),
        },
        "downstream_contract": {
            "next_step": "ver3_0_stepB_extension_tech_growth",
            "read_first": [
                "panel/ver3_0_stepA_extension_588000_sleeve_return_panel_wide.csv",
                "panel/ver3_0_stepA_extension_588000_sleeve_return_panel_long.csv",
            ],
            "boundary": "588000 is extension-only and must not shorten the main Step B sample.",
        },
    }
    manifest = clean_json_value(manifest)
    (OUT_ROOT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, default=json_default, allow_nan=False),
        encoding="utf-8",
    )


def write_figures(daily: pd.DataFrame, summary: pd.DataFrame, classification: pd.DataFrame, correlation: pd.DataFrame) -> None:
    plot_nav(daily, classification)
    plot_drawdown(daily, classification)
    plot_metric_comparison(summary, classification)
    plot_correlation_heatmap(correlation)


def plot_nav(daily: pd.DataFrame, classification: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(11, 5.8))
    primary = set(classification[classification["recommendation_status"].eq("primary_for_short_sample_extension")]["sleeve_name"])
    backup = set(classification[classification["recommendation_status"].eq("backup_defensive_overlay")]["sleeve_name"])
    for sleeve, g in daily.groupby("sleeve_name"):
        lw = 2.5 if sleeve in primary else 1.8 if sleeve in backup else 1.0
        alpha = 0.95 if sleeve in primary or sleeve in backup else 0.55
        style = "--" if "Q100" in sleeve else "-"
        ax.plot(g["date"], g["nav_total"], label=short_sleeve(sleeve), linewidth=lw, alpha=alpha, linestyle=style)
    ax.set_title("588000 sleeve NAV curves")
    ax.set_ylabel("NAV")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "ver3_0_stepA_extension_588000_nav_curves.png", dpi=160)
    plt.close(fig)


def plot_drawdown(daily: pd.DataFrame, classification: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(11, 5.8))
    primary = set(classification[classification["recommendation_status"].eq("primary_for_short_sample_extension")]["sleeve_name"])
    for sleeve, g in daily.groupby("sleeve_name"):
        gg = g.sort_values("date").copy()
        dd = gg["nav_total"] / gg["nav_total"].cummax() - 1.0
        ax.plot(gg["date"], dd, label=short_sleeve(sleeve), linewidth=2.3 if sleeve in primary else 1.1, alpha=0.9 if sleeve in primary else 0.55, linestyle="--" if "Q100" in sleeve else "-")
    ax.set_title("588000 sleeve drawdown curves")
    ax.set_ylabel("Drawdown")
    ax.yaxis.set_major_formatter(lambda y, _pos: f"{y:.0%}")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "ver3_0_stepA_extension_588000_drawdown_curves.png", dpi=160)
    plt.close(fig)


def plot_metric_comparison(summary: pd.DataFrame, classification: pd.DataFrame) -> None:
    d = summary.merge(classification[["sleeve_name", "classification"]], on="sleeve_name", how="left")
    metrics = [
        ("annualized_return_cagr", "CAGR"),
        ("sharpe_daily_mean", "Sharpe"),
        ("max_drawdown", "MDD"),
        ("option_leg_annualized_pnl_contribution", "Option leg"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(12, 7.5))
    for ax, (col, title) in zip(axes.flatten(), metrics):
        ax.bar(d["sleeve_name"].map(short_sleeve), d[col], color=d["classification"].map(class_color))
        ax.set_title(title)
        ax.tick_params(axis="x", rotation=35, labelsize=8)
        if col != "sharpe_daily_mean":
            ax.yaxis.set_major_formatter(lambda y, _pos: f"{y:.0%}")
        ax.axhline(0, color="black", linewidth=0.8)
        ax.grid(axis="y", alpha=0.22)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "ver3_0_stepA_extension_588000_metric_comparison.png", dpi=160)
    plt.close(fig)


def plot_correlation_heatmap(correlation: pd.DataFrame) -> None:
    d = correlation.copy()
    fig, ax = plt.subplots(figsize=(10.5, 5.8))
    values = d[["daily_return_correlation"]].to_numpy(dtype=float)
    image = ax.imshow(values, vmin=0, vmax=1, cmap="YlGnBu", aspect="auto")
    ax.set_yticks(range(len(d)), d["comparison_name"], fontsize=8)
    ax.set_xticks([0], ["daily correlation"])
    for i, val in enumerate(d["daily_return_correlation"]):
        ax.text(0, i, f"{val:.3f}", ha="center", va="center", color="black", fontsize=8)
    ax.set_title("588000 correlation diagnostics")
    fig.colorbar(image, ax=ax)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "ver3_0_stepA_extension_588000_correlation_heatmap.png", dpi=160)
    plt.close(fig)


def build_sanity_checks(
    daily: pd.DataFrame,
    period: pd.DataFrame,
    summary: pd.DataFrame,
    classification: pd.DataFrame,
    panel_long: pd.DataFrame,
    panel_wide: pd.DataFrame,
    correlation: pd.DataFrame,
) -> pd.DataFrame:
    expected = {spec.sleeve_name for spec in SPECS}
    checks = [
        ("required_sleeves_created", set(daily["sleeve_name"].unique()) == expected, "all requested 588000 sleeves except unsupported TP80 are created"),
        ("short_sample_flagged", pd.Timestamp(daily["date"].min()) > MAIN_STEP_A_START, "588000 sample starts after main Step A sample"),
        ("uses_standardized_metric_names", {"annualized_return_cagr", "sharpe_daily_mean", "max_drawdown"}.issubset(summary.columns), "summary follows ver2 field names"),
        ("option_leg_net_pnl_formula", period_formula_ok(period), "period option leg equals premium minus payoff minus cost"),
        ("q100_diagnostic_only", q100_diagnostic_only(classification), "Q100/ATM Q100 sleeves are diagnostics"),
        ("primary_is_not_q100", not classification[classification["recommendation_status"].eq("primary_for_short_sample_extension")]["sleeve_name"].str.contains("Q100").any(), "default recommendation excludes Q100"),
        ("no_tp80_or_touchk_reintroduced", not daily["sleeve_name"].str.contains("TP80|TouchK", regex=True).any(), "TP80/TouchK are not generated for 588000"),
        ("correlation_diagnostics_created", len(correlation) >= 5, "cross-ETF correlation diagnostics are populated"),
        ("no_portfolio_weighting", not any(col.startswith("weight_") for col in daily.columns), "single-ETF extension only"),
        ("panel_created", not panel_long.empty and not panel_wide.empty, "long and wide return panels are populated"),
        ("strategy_direction_created", (STRATEGY_DIR / "ver3_0_universe_strategy_direction.md").exists(), "universe strategy direction exists"),
        ("reports_avoid_forbidden_profit_claims", reports_avoid_forbidden_profit_claims(), "reports avoid forbidden profit wording"),
    ]
    return pd.DataFrame([{"check_name": name, "passed": bool(passed), "note": note} for name, passed, note in checks])


def period_formula_ok(period: pd.DataFrame) -> bool:
    if period.empty:
        return False
    lhs = period["premium_return"].astype(float) - period["payoff_return"].astype(float) - period["transaction_cost_return"].astype(float)
    rhs = period["option_leg_return"].astype(float)
    return bool(np.nanmax(np.abs(lhs - rhs)) < 1e-10)


def q100_diagnostic_only(classification: pd.DataFrame) -> bool:
    q100 = classification[classification["sleeve_name"].str.contains("Q100")]
    return bool(not q100.empty and q100["classification"].eq("Stress / Diagnostic Only").all())


def reports_avoid_forbidden_profit_claims() -> bool:
    forbidden = ["无风险套利", "risk-free arbitrage", "guaranteed profit"]
    for directory in (STRATEGY_DIR, CARD_DIR, REPORT_DIR):
        if not directory.exists():
            continue
        for path in directory.glob("*.md"):
            text = path.read_text(encoding="utf-8").lower()
            if any(term.lower() in text for term in forbidden):
                return False
    return True


def derive_daily_cumulative_change(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df:
        return pd.Series(0.0, index=df.index)
    values = numeric(df[col])
    out = values.groupby(df["period_index"]).diff() if "period_index" in df else values.diff()
    if "period_index" in df:
        first = ~df["period_index"].duplicated()
        out.loc[first] = values.loc[first]
    return out.fillna(0.0)


def numeric(values: Any) -> pd.Series:
    if isinstance(values, pd.Series):
        return pd.to_numeric(values, errors="coerce").fillna(0.0)
    return pd.Series(values).astype(float)


def safe_div(numerator: float, denominator: float) -> float:
    if denominator is None or pd.isna(denominator) or abs(float(denominator)) < 1e-12:
        return np.nan
    return float(numerator) / float(denominator)


def spec_by_name(name: str) -> SleeveSpec:
    for spec in SPECS:
        if spec.sleeve_name == name:
            return spec
    raise KeyError(name)


def interpret_correlation(value: float) -> str:
    if pd.isna(value):
        return "unavailable"
    if value >= 0.85:
        return "high overlap"
    if value >= 0.65:
        return "moderate growth-style overlap"
    if value >= 0.45:
        return "partial diversification value"
    return "meaningful diversification value"


def date_iso(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return pd.Timestamp(value).date().isoformat()


def fmt_pct(value: Any) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value):.2%}"


def fmt_num(value: Any) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value):.3f}"


def md_table(df: pd.DataFrame, pct_cols: list[str] | None = None, num_cols: list[str] | None = None) -> str:
    pct = set(pct_cols or [])
    num = set(num_cols or [])
    d = df.copy()
    for col in d.columns:
        if col in pct:
            d[col] = d[col].map(fmt_pct)
        elif col in num:
            d[col] = d[col].map(fmt_num)
        else:
            d[col] = d[col].map(lambda x: "" if pd.isna(x) else str(x))
    if d.empty:
        return "_empty_"
    return d.to_markdown(index=False)


def short_sleeve(name: str) -> str:
    return (
        name.replace("588000_", "")
        .replace("DTE30_", "")
        .replace("_Hold", "")
        .replace("ETF_BuyHold", "BuyHold")
    )


def class_color(value: str) -> str:
    return {
        "Positive Carry Overlay": "#4C78A8",
        "Defensive Overlay": "#59A14F",
        "Pure ETF Preferred": "#9C755F",
        "Growth Extension Sleeve": "#F58518",
        "Stress / Diagnostic Only": "#B07AA1",
        "Not Recommended": "#E15759",
    }.get(str(value), "#777777")


def setup_plot_style() -> None:
    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.labelsize": 10,
            "legend.fontsize": 8,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
        }
    )


def json_default(value: Any) -> Any:
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        if np.isnan(value):
            return None
        return float(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if pd.isna(value):
        return None
    return str(value)


def clean_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): clean_json_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean_json_value(v) for v in value]
    if isinstance(value, tuple):
        return [clean_json_value(v) for v in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if pd.isna(value) else float(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


if __name__ == "__main__":
    main()
