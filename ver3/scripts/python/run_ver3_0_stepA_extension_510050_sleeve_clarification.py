from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
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


ETF_CODE = "510050"
REFERENCE_ETF = "510300"
START_DATE = pd.Timestamp("2022-09-30")
END_DATE = pd.Timestamp("2026-05-27")
TARGET_DTE_LABEL = "DTE30"
HOLD_RULE = "hold_to_expiry"
TRADING_DAYS_PER_YEAR = 252.0

FROZEN_INPUT_ROOT = ROOT / "data" / "frozen_inputs" / "ver3_0_510050"
INPUT_DAILY = FROZEN_INPUT_ROOT / "ver2_1_daily_mtm.csv"
INPUT_PERIOD = FROZEN_INPUT_ROOT / "ver2_1_periods_with_regime.csv"
STEP_A_PANEL_WIDE = ROOT / "outputs" / "ver3_0_stepA_single_etf_sleeves" / "panel" / "ver3_0_stepA_sleeve_return_panel_wide.csv"

OUT_ROOT = ROOT / "outputs" / "ver3_0_stepA_extension_510050_sleeve_clarification"
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
    source_strategy_family: str
    coverage: float
    is_buyhold: bool = False
    is_stress: bool = False
    note: str = ""


SPECS: tuple[SleeveSpec, ...] = (
    SleeveSpec("510050_ETF_BuyHold", "BuyHold", "benchmark", 0.0, is_buyhold=True, note="pure ETF baseline"),
    SleeveSpec("510050_DTE30_D40_Q50_Hold", "D40_100", "delta", 0.5, note="medium coverage D40 candidate"),
    SleeveSpec("510050_DTE30_D40_Q70_Hold", "D40_100", "delta", 0.7, note="main 510050 covered-call candidate"),
    SleeveSpec("510050_DTE30_D40_Q100_Hold", "D40_100", "delta", 1.0, is_stress=True, note="full coverage D40 stress diagnostic"),
    SleeveSpec("510050_DTE30_ATM_Q100_Hold", "ATM_100", "moneyness", 1.0, is_stress=True, note="ATM full coverage stress diagnostic"),
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ver3.0 Step A extension for 510050 single-ETF sleeves.")
    parser.add_argument("--rf", type=float, default=0.0, help="Annual risk-free rate for standardized Sharpe.")
    args = parser.parse_args()

    ensure_dirs()
    verify_inputs()
    _setup_plot_style()

    source_daily, source_period = load_inputs()
    full_source_range = get_full_source_range(source_daily)
    daily = build_daily_nav(source_daily)
    period = build_period_attribution(source_period, source_daily)
    summary = build_summary(daily, period, args.rf)
    classification = build_classification(summary)
    panel_long, panel_wide = build_return_panel(daily, classification)
    corr_summary, rolling_corr = build_correlation_diagnostics(panel_wide)
    sanity = build_sanity_checks(daily, period, summary, classification, panel_long, panel_wide, corr_summary)

    write_outputs(daily, period, summary, classification, corr_summary, rolling_corr, panel_long, panel_wide, sanity)
    write_card(summary, classification, corr_summary)
    write_master_report(summary, classification, corr_summary, sanity, full_source_range)
    write_figures(daily, summary, classification, corr_summary, rolling_corr)

    # Recompute after report/card files exist, then refresh user-facing metadata.
    sanity = build_sanity_checks(daily, period, summary, classification, panel_long, panel_wide, corr_summary)
    sanity.to_csv(AUDIT_DIR / "ver3_0_stepA_extension_510050_sanity_checks.csv", index=False, encoding="utf-8-sig")
    write_master_report(summary, classification, corr_summary, sanity, full_source_range)
    write_readme_and_manifest(summary, classification, corr_summary, full_source_range, sanity)

    primary = classification[classification["recommendation_status"].eq("primary_for_portfolio_layer")].iloc[0]
    corr_row = corr_summary[corr_summary["comparison_name"].eq("D40_Q70_pair")].iloc[0]
    alt_universe = "yes" if primary["classification"] in {"Positive Carry Overlay", "Defensive Overlay"} else "no"
    step_b = "yes" if alt_universe == "yes" else "no"

    print(f"Wrote ver3.0 Step A extension outputs to {OUT_ROOT}")
    print(f"510050 recommended sleeve: {primary['sleeve_name']}")
    print(f"510050 classification: {primary['classification']}")
    print(f"Recommend alternative universe entry: {alt_universe}")
    print(
        "510050 vs 510300 correlation judgment: "
        f"{corr_row['interpretation']} "
        f"(daily corr={corr_row['daily_return_correlation']:.3f}, "
        f"rolling63 mean={corr_row['rolling_corr_mean']:.3f})"
    )
    print(f"Recommend Step B / Step B+ inclusion: {step_b}")


def ensure_dirs() -> None:
    for path in (DAILY_DIR, PERIOD_DIR, SUMMARY_DIR, PANEL_DIR, FIGURE_DIR, CARD_DIR, REPORT_DIR, AUDIT_DIR):
        path.mkdir(parents=True, exist_ok=True)


def verify_inputs() -> None:
    missing = [str(path.relative_to(ROOT)) for path in (INPUT_DAILY, INPUT_PERIOD) if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing required 510050 Step A extension inputs:\n" + "\n".join(missing))


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    daily = pd.read_csv(INPUT_DAILY, dtype={"etf_code": str})
    period = pd.read_csv(INPUT_PERIOD, dtype={"etf_code": str})
    for df in (daily, period):
        df["etf_code"] = df["etf_code"].astype(str).str.zfill(6)
    for col in ["date", "rebalance_date", "period_end_date", "expiry_date"]:
        if col in daily:
            daily[col] = pd.to_datetime(daily[col], errors="coerce")
        if col in period:
            period[col] = pd.to_datetime(period[col], errors="coerce")
    return daily, period


def get_full_source_range(source_daily: pd.DataFrame) -> dict[str, str]:
    d = source_daily[
        (source_daily["etf_code"].eq(ETF_CODE))
        & (source_daily["dte_label"].eq(TARGET_DTE_LABEL))
        & (source_daily["strategy_name"].isin(["BuyHold", "D40_100", "ATM_100"]))
    ].copy()
    if d.empty:
        return {"source_start": "", "source_end": ""}
    return {
        "source_start": pd.Timestamp(d["date"].min()).date().isoformat(),
        "source_end": pd.Timestamp(d["date"].max()).date().isoformat(),
    }


def build_daily_nav(source_daily: pd.DataFrame) -> pd.DataFrame:
    base = load_canonical_source_paths(source_daily, ETF_CODE)
    required = {"BuyHold", "D40_100", "ATM_100"}
    missing = sorted(required - set(base))
    if missing:
        available = source_daily[
            (source_daily["etf_code"].eq(ETF_CODE)) & (source_daily["dte_label"].eq(TARGET_DTE_LABEL))
        ][["dte_label", "strategy_name", "strategy_family"]].drop_duplicates()
        raise ValueError(f"Missing 510050 source strategies: {missing}\nAvailable:\n{available.to_string(index=False)}")

    common_dates = base["BuyHold"].index.intersection(base["D40_100"].index).intersection(base["ATM_100"].index)
    common_dates = common_dates[(common_dates >= START_DATE) & (common_dates <= END_DATE)]
    if common_dates.empty:
        raise ValueError("No common 510050 DTE30 dates inside Step A common sample.")

    buyhold_nav = base["BuyHold"].loc[common_dates, "daily_mtm_nav"].astype(float)
    underlying_return = buyhold_nav.pct_change().fillna(0.0)
    underlying_return.iloc[0] = 0.0

    option_return: dict[str, pd.Series] = {}
    for source_name in ("D40_100", "ATM_100"):
        total = base[source_name].loc[common_dates, "daily_mtm_nav"].astype(float).pct_change().fillna(0.0)
        total.iloc[0] = 0.0
        option_return[source_name] = total - underlying_return

    frames: list[pd.DataFrame] = []
    for spec in SPECS:
        src_name = spec.source_strategy_name or "BuyHold"
        src = base[src_name].loc[common_dates].copy()
        if spec.is_buyhold:
            opt = pd.Series(0.0, index=common_dates)
            daily_return_total = underlying_return.copy()
            strategy_family = "ETF_BuyHold"
        else:
            opt = option_return[src_name] * spec.coverage
            daily_return_total = underlying_return + opt
            strategy_family = "ATM" if src_name == "ATM_100" else "D40"
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
                    "strategy_family": strategy_family,
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
                    "short_call_liability": np.where(spec.is_buyhold, 0.0, _numeric(src.get("option_liability_return", 0.0)).values * spec.coverage),
                    "short_call_mtm_loss": np.where(spec.is_buyhold, 0.0, _numeric(src.get("short_call_mtm_loss_return", 0.0)).values * spec.coverage),
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


def load_canonical_source_paths(source_daily: pd.DataFrame, etf: str) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    d = source_daily[(source_daily["etf_code"].eq(etf)) & (source_daily["dte_label"].eq(TARGET_DTE_LABEL))].copy()
    for strategy_name, g in d.groupby("strategy_name"):
        if strategy_name not in {"BuyHold", "D40_100", "ATM_100"}:
            continue
        sort_cols = [c for c in ["date", "period_index", "event"] if c in g.columns]
        gg = g.sort_values(sort_cols).drop_duplicates("date", keep="last").copy()
        gg = gg.set_index("date").sort_index()
        out[strategy_name] = gg
    return out


def build_period_attribution(source_period: pd.DataFrame, source_daily: pd.DataFrame) -> pd.DataFrame:
    stress = build_period_stress_lookup(source_daily)
    rows: list[dict[str, Any]] = []
    for spec in SPECS:
        if spec.is_buyhold:
            continue
        p = source_period[
            (source_period["etf_code"].eq(ETF_CODE))
            & (source_period["dte_label"].eq(TARGET_DTE_LABEL))
            & (source_period["strategy_name"].eq(spec.source_strategy_name))
            & (source_period["rebalance_date"] >= START_DATE)
            & (source_period["rebalance_date"] <= END_DATE)
        ].copy()
        if p.empty:
            raise ValueError(f"No source period rows for {spec.sleeve_name}")
        for _, row in p.sort_values("rebalance_date").iterrows():
            premium = float(row.get("premium_return", 0.0) or 0.0) * spec.coverage
            payoff = float(row.get("upside_payoff_return", 0.0) or 0.0) * spec.coverage
            cost = float(row.get("transaction_cost_return", 0.0) or 0.0) * spec.coverage
            option_leg = premium - payoff - cost
            stress_key = (
                str(row.get("strategy_name")),
                int(row.get("period_index")),
                str(row.get("option_code")),
            )
            stress_row = stress.get(stress_key, {"max": np.nan, "p95": np.nan, "p99": np.nan})
            rows.append(
                {
                    "etf_code": ETF_CODE,
                    "sleeve_name": spec.sleeve_name,
                    "strategy_family": "ATM" if spec.source_strategy_name == "ATM_100" else "D40",
                    "dte_label": TARGET_DTE_LABEL,
                    "target_dte": 30,
                    "actual_dte": row.get("actual_dte", np.nan),
                    "coverage": spec.coverage,
                    "close_rule": HOLD_RULE,
                    "rebalance_date": pd.Timestamp(row["rebalance_date"]).date().isoformat(),
                    "expiry_date": _date_iso(row.get("expiry_date")),
                    "period_end_date": _date_iso(row.get("period_end_date")),
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
                    "premium_capture_ratio": _safe_div(option_leg, premium),
                    "payoff_burden": _safe_div(payoff, premium),
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
                    "policy_jump_window_flag": bool(row.get("policy_jump_like", False)),
                    "warning_flag": row.get("selection_reason", ""),
                }
            )
    return pd.DataFrame(rows).sort_values(["sleeve_name", "rebalance_date"]).reset_index(drop=True)


def build_period_stress_lookup(source_daily: pd.DataFrame) -> dict[tuple[str, int, str], dict[str, float]]:
    d = source_daily[
        (source_daily["etf_code"].eq(ETF_CODE))
        & (source_daily["dte_label"].eq(TARGET_DTE_LABEL))
        & (source_daily["strategy_name"].isin(["D40_100", "ATM_100"]))
    ].copy()
    lookup: dict[tuple[str, int, str], dict[str, float]] = {}
    for (strategy, period_index, option_code), g in d.groupby(["strategy_name", "period_index", "option_code"], dropna=False):
        stress = _numeric(g.get("short_call_mtm_loss_return", 0.0))
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
                "sample_scope": "common_portfolio_sample",
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
        "premium_capture_ratio_agg": _safe_div(float(option_leg.sum()), float(premium.sum())),
        "payoff_burden_agg": _safe_div(float(payoff.sum()), float(premium.sum())),
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
    buyhold = summary[summary["sleeve_name"].eq("510050_ETF_BuyHold")].iloc[0]
    rows: list[dict[str, Any]] = []
    for _, row in summary.iterrows():
        spec = spec_by_name(row["sleeve_name"])
        option_positive = bool(row["option_leg_annualized_pnl_contribution"] > 0)
        beats_sharpe = bool(row["sharpe_daily_mean"] > buyhold["sharpe_daily_mean"])
        improves_mdd = bool(row["max_drawdown"] < buyhold["max_drawdown"])
        return_ok = bool(row["annualized_return_cagr"] >= buyhold["annualized_return_cagr"] - 0.01)
        classification, reason, caveat = classify_sleeve(row, buyhold, spec, option_positive, beats_sharpe, improves_mdd, return_ok)
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
                "return_not_materially_worse": return_ok,
                "recommendation_status": "rejected",
                "reason": reason,
                "caveat": caveat,
            }
        )
    out = pd.DataFrame(rows)
    eligible = out[
        out["classification"].isin(["Positive Carry Overlay", "Defensive Overlay"])
        & ~out["sleeve_name"].str.contains("Q100")
    ].copy()
    if eligible.empty:
        primary = "510050_ETF_BuyHold"
        backup = ""
    else:
        rank_class = {"Positive Carry Overlay": 0, "Defensive Overlay": 1}
        eligible["_rank_class"] = eligible["classification"].map(rank_class)
        eligible = eligible.sort_values(
            ["_rank_class", "sharpe_daily_mean", "max_drawdown", "annualized_return_cagr"],
            ascending=[True, False, True, False],
        )
        primary = str(eligible.iloc[0]["sleeve_name"])
        backup = str(eligible.iloc[1]["sleeve_name"]) if len(eligible) > 1 else "510050_ETF_BuyHold"
    out.loc[out["sleeve_name"].eq(primary), "recommendation_status"] = "primary_for_portfolio_layer"
    if backup:
        out.loc[out["sleeve_name"].eq(backup), "recommendation_status"] = "backup_for_portfolio_layer"
    stress_mask = out["sleeve_name"].str.contains("Q100")
    out.loc[stress_mask, "recommendation_status"] = "diagnostic_only"
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
    return_ok: bool,
) -> tuple[str, str, str]:
    if spec.is_buyhold:
        return "Pure ETF Preferred", "ETF-only baseline for comparison.", "No option leg."
    if spec.is_stress:
        return "Stress / Diagnostic Only", "Q100 is retained as a stress diagnostic, not a default sleeve.", "Do not promote Q100 by default."
    if option_positive and beats_sharpe and improves_mdd and return_ok:
        return (
            "Positive Carry Overlay",
            "Net option leg is positive while Sharpe improves and max drawdown is lower than BuyHold.",
            "This is structural risk compensation with path and sample risk.",
        )
    mdd_improvement = float(buyhold["max_drawdown"]) - float(row["max_drawdown"])
    sharpe_gap = float(row["sharpe_daily_mean"]) - float(buyhold["sharpe_daily_mean"])
    if improves_mdd and sharpe_gap >= -0.05 and return_ok:
        return (
            "Defensive Overlay",
            "Drawdown improves with acceptable Sharpe/return trade-off.",
            "Use as risk-control sleeve rather than pure income sleeve.",
        )
    return "Pure ETF Preferred", "Covered-call sleeve does not improve BuyHold enough.", "Keep as diagnostic or use ETF-only exposure."


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
    long["sample_scope"] = "common_portfolio_sample"
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


def build_correlation_diagnostics(panel_wide: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    own = panel_wide.copy()
    own["date"] = pd.to_datetime(own["date"])
    ref = load_510300_reference_returns()
    merged = own.merge(ref, on="date", how="inner")
    if merged.empty:
        raise ValueError("No overlapping daily returns for 510050 vs 510300 correlation diagnostics.")

    comparisons = [
        (
            "ETF_BuyHold_pair",
            "510050__510050_ETF_BuyHold__daily_return",
            "510300__510300_ETF_BuyHold__daily_return",
        ),
        (
            "D40_Q70_pair",
            "510050__510050_DTE30_D40_Q70_Hold__daily_return",
            "510300__510300_DTE30_D40_Q70_Hold__daily_return",
        ),
    ]
    rows: list[dict[str, Any]] = []
    rolling_frames: list[pd.DataFrame] = []
    for name, left, right in comparisons:
        if left not in merged.columns or right not in merged.columns:
            raise ValueError(f"Missing correlation columns for {name}: {left}, {right}\nAvailable: {list(merged.columns)}")
        pair = merged[["date", left, right]].dropna().copy()
        corr = float(pair[left].corr(pair[right]))
        rolling = pair[left].rolling(63).corr(pair[right])
        rolling_valid = rolling.dropna()
        rolling_frames.append(
            pd.DataFrame(
                {
                    "date": pair["date"],
                    "comparison_name": name,
                    "rolling_window_days": 63,
                    "rolling_correlation": rolling,
                }
            )
        )
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
                "rolling_corr_mean": float(rolling_valid.mean()) if not rolling_valid.empty else np.nan,
                "rolling_corr_median": float(rolling_valid.median()) if not rolling_valid.empty else np.nan,
                "rolling_corr_p05": float(rolling_valid.quantile(0.05)) if not rolling_valid.empty else np.nan,
                "rolling_corr_p95": float(rolling_valid.quantile(0.95)) if not rolling_valid.empty else np.nan,
                "rolling_corr_min": float(rolling_valid.min()) if not rolling_valid.empty else np.nan,
                "rolling_corr_max": float(rolling_valid.max()) if not rolling_valid.empty else np.nan,
                "interpretation": interpret_correlation(corr),
            }
        )
    return pd.DataFrame(rows), pd.concat(rolling_frames, ignore_index=True)


def load_510300_reference_returns() -> pd.DataFrame:
    if STEP_A_PANEL_WIDE.exists():
        ref = pd.read_csv(STEP_A_PANEL_WIDE)
        ref["date"] = pd.to_datetime(ref["date"])
        needed = [
            "date",
            "510300__510300_ETF_BuyHold__daily_return",
            "510300__510300_DTE30_D40_Q70_Hold__daily_return",
        ]
        missing = [col for col in needed if col not in ref.columns]
        if not missing:
            return ref[needed].copy()
    return build_510300_reference_from_ver21()


def build_510300_reference_from_ver21() -> pd.DataFrame:
    source_daily, _ = load_inputs()
    base = load_canonical_source_paths(source_daily, REFERENCE_ETF)
    common_dates = base["BuyHold"].index.intersection(base["D40_100"].index)
    common_dates = common_dates[(common_dates >= START_DATE) & (common_dates <= END_DATE)]
    buyhold_nav = base["BuyHold"].loc[common_dates, "daily_mtm_nav"].astype(float)
    underlying = buyhold_nav.pct_change().fillna(0.0)
    d40_total = base["D40_100"].loc[common_dates, "daily_mtm_nav"].astype(float).pct_change().fillna(0.0)
    d40_q70 = underlying + 0.7 * (d40_total - underlying)
    underlying.iloc[0] = 0.0
    d40_q70.iloc[0] = 0.0
    return pd.DataFrame(
        {
            "date": common_dates,
            "510300__510300_ETF_BuyHold__daily_return": underlying.values,
            "510300__510300_DTE30_D40_Q70_Hold__daily_return": d40_q70.values,
        }
    )


def build_sanity_checks(
    daily: pd.DataFrame,
    period: pd.DataFrame,
    summary: pd.DataFrame,
    classification: pd.DataFrame,
    panel_long: pd.DataFrame,
    panel_wide: pd.DataFrame,
    corr_summary: pd.DataFrame,
) -> pd.DataFrame:
    expected_sleeves = {spec.sleeve_name for spec in SPECS}
    checks = [
        ("required_sleeves_created", set(daily["sleeve_name"].unique()) == expected_sleeves, "all requested 510050 sleeves exist"),
        ("common_sample_matches_stepA", daily["date"].min() == START_DATE and daily["date"].max() == END_DATE, "metrics use Step A common sample"),
        ("uses_standardized_metric_names", {"annualized_return_cagr", "sharpe_daily_mean", "max_drawdown"}.issubset(summary.columns), "summary follows ver2 field names"),
        ("option_leg_net_pnl_formula", period_formula_ok(period), "period option leg equals premium minus payoff minus cost"),
        ("q100_diagnostic_only", q100_diagnostic_only(classification), "Q100 sleeves are not default recommendations"),
        ("primary_not_q100", not classification[classification["recommendation_status"].eq("primary_for_portfolio_layer")]["sleeve_name"].str.contains("Q100").any(), "primary sleeve excludes Q100"),
        ("correlation_diagnostics_created", {"ETF_BuyHold_pair", "D40_Q70_pair"}.issubset(set(corr_summary["comparison_name"])), "510050 vs 510300 correlations are populated"),
        ("no_portfolio_weighting_in_stepA_extension", not any(col.startswith("weight_") for col in daily.columns), "single-ETF extension only"),
        ("panel_created", not panel_long.empty and not panel_wide.empty, "long and wide return panels are populated"),
        ("reports_avoid_forbidden_profit_claims", reports_avoid_forbidden_profit_claims(), "reports avoid guaranteed-profit wording"),
    ]
    return pd.DataFrame([{"check_name": name, "passed": bool(passed), "note": note} for name, passed, note in checks])


def write_outputs(
    daily: pd.DataFrame,
    period: pd.DataFrame,
    summary: pd.DataFrame,
    classification: pd.DataFrame,
    corr_summary: pd.DataFrame,
    rolling_corr: pd.DataFrame,
    panel_long: pd.DataFrame,
    panel_wide: pd.DataFrame,
    sanity: pd.DataFrame,
) -> None:
    daily.to_csv(DAILY_DIR / "ver3_0_stepA_extension_510050_sleeve_daily_nav.csv", index=False, encoding="utf-8-sig")
    daily[
        ["date", "etf_code", "sleeve_name", "daily_return_total", "daily_return_underlying_component", "daily_return_option_leg_component"]
    ].rename(columns={"daily_return_total": "daily_return"}).to_csv(
        DAILY_DIR / "ver3_0_stepA_extension_510050_sleeve_daily_returns.csv",
        index=False,
        encoding="utf-8-sig",
    )
    period.to_csv(PERIOD_DIR / "ver3_0_stepA_extension_510050_period_attribution.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(SUMMARY_DIR / "ver3_0_stepA_extension_510050_sleeve_summary.csv", index=False, encoding="utf-8-sig")
    classification.to_csv(SUMMARY_DIR / "ver3_0_stepA_extension_510050_classification_table.csv", index=False, encoding="utf-8-sig")
    corr_summary.to_csv(SUMMARY_DIR / "ver3_0_stepA_extension_510050_vs_510300_correlation.csv", index=False, encoding="utf-8-sig")
    rolling_corr.to_csv(SUMMARY_DIR / "ver3_0_stepA_extension_510050_vs_510300_rolling_correlation.csv", index=False, encoding="utf-8-sig")
    panel_long.to_csv(PANEL_DIR / "ver3_0_stepA_extension_510050_sleeve_return_panel_long.csv", index=False, encoding="utf-8-sig")
    panel_wide.to_csv(PANEL_DIR / "ver3_0_stepA_extension_510050_sleeve_return_panel_wide.csv", index=False, encoding="utf-8-sig")
    sanity.to_csv(AUDIT_DIR / "ver3_0_stepA_extension_510050_sanity_checks.csv", index=False, encoding="utf-8-sig")


def write_card(summary: pd.DataFrame, classification: pd.DataFrame, corr_summary: pd.DataFrame) -> None:
    s = summary.merge(
        classification[["sleeve_name", "classification", "recommendation_status", "reason", "caveat"]],
        on="sleeve_name",
        how="left",
    )
    primary = classification[classification["recommendation_status"].eq("primary_for_portfolio_layer")].iloc[0]
    q70_corr = corr_summary[corr_summary["comparison_name"].eq("D40_Q70_pair")].iloc[0]
    text = f"""# 510050 Sleeve Card

## 1. 标的定位

510050 是大盘蓝筹 / 金融权重风格 ETF。本扩展只判断它能否作为 510500 的备选，进入 `510300 + 510050 + 159915` defensive-income universe。

## 2. 候选 sleeve 列表

{_md_table(s[["sleeve_name", "classification", "recommendation_status"]])}

## 3. 核心绩效对比

{_md_table(s[["sleeve_name", "annualized_return_cagr", "sharpe_daily_mean", "max_drawdown", "annualized_volatility", "option_leg_annualized_pnl_contribution"]], pct_cols=["annualized_return_cagr", "max_drawdown", "annualized_volatility", "option_leg_annualized_pnl_contribution"], num_cols=["sharpe_daily_mean"])}

## 4. Option-leg 质量

{_md_table(s[["sleeve_name", "premium_capture_ratio_agg", "payoff_burden_agg", "positive_option_leg_period_rate", "assignment_rate", "p99_short_call_mtm_loss"]], pct_cols=["premium_capture_ratio_agg", "payoff_burden_agg", "positive_option_leg_period_rate", "assignment_rate", "p99_short_call_mtm_loss"])}

## 5. 与 510300 的相关性

{_md_table(corr_summary, pct_cols=[], num_cols=["daily_return_correlation", "rolling_corr_mean", "rolling_corr_p05", "rolling_corr_p95"])}

## 6. 推荐进入组合层的 sleeve

- primary_sleeve_for_portfolio_layer: {primary["sleeve_name"]}
- classification: {primary["classification"]}
- correlation_judgment: {q70_corr["interpretation"]}
- caveat: {primary["caveat"]}
"""
    (CARD_DIR / "510050_sleeve_card.md").write_text(text, encoding="utf-8")


def write_master_report(
    summary: pd.DataFrame,
    classification: pd.DataFrame,
    corr_summary: pd.DataFrame,
    sanity: pd.DataFrame,
    full_source_range: dict[str, str],
) -> None:
    s = summary.merge(
        classification[["sleeve_name", "classification", "recommendation_status", "reason", "caveat"]],
        on="sleeve_name",
        how="left",
    )
    primary = classification[classification["recommendation_status"].eq("primary_for_portfolio_layer")].iloc[0]
    buyhold = summary[summary["sleeve_name"].eq("510050_ETF_BuyHold")].iloc[0]
    q70 = summary[summary["sleeve_name"].eq("510050_DTE30_D40_Q70_Hold")].iloc[0]
    q70_corr = corr_summary[corr_summary["comparison_name"].eq("D40_Q70_pair")].iloc[0]
    option_positive = "是" if float(q70["option_leg_annualized_pnl_contribution"]) > 0 else "否"
    alt_universe = primary["classification"] in {"Positive Carry Overlay", "Defensive Overlay"}
    alt_text = "建议进入" if alt_universe else "暂不建议进入"
    text = f"""# ver3.0 Step A-Extension | 510050 单 ETF 备兑 Sleeve 画像

## 1. 研究目的

此前 Step A 显示 510500 更适合作为 pure ETF BuyHold，而不是强行做 covered call。本扩展补充考察 510050：它是否能像 510300 一样，成为较稳定的 covered-call income / risk-control sleeve，并服务于备选 universe `510300 + 510050 + 159915`。

本报告只做单 ETF sleeve clarification，不做 fixed-weight portfolio、不做动态权重、不做均值方差优化。

## 2. 样本区间与数据说明

- 510050 DTE30 源数据可用区间：{full_source_range["source_start"]} 至 {full_source_range["source_end"]}
- 本次正式指标区间：{START_DATE.date().isoformat()} 至 {END_DATE.date().isoformat()}
- 期权路径来源：`data/frozen_inputs/ver3_0_510050/`（从已验收的早期引擎结果冻结迁移，不再依赖旧 outputs 目录）
- 510300 相关性参照：优先读取既有 Step A return panel，不修改其输出文件。

510050 可以覆盖 Step A 共同样本，因此没有强行填补期权交易数据。

## 3. 候选 sleeve 列表

- `510050_ETF_BuyHold`：纯 ETF baseline。
- `510050_DTE30_D40_Q50_Hold`：DTE30、目标 Delta 约 40、50% 覆盖率。
- `510050_DTE30_D40_Q70_Hold`：DTE30、目标 Delta 约 40、70% 覆盖率，主候选。
- `510050_DTE30_D40_Q100_Hold`：D40 全覆盖 stress / diagnostic。
- `510050_DTE30_ATM_Q100_Hold`：ATM 全覆盖 stress / diagnostic。

## 4. 主指标表

{_md_table(s[["sleeve_name", "classification", "recommendation_status", "annualized_return_cagr", "sharpe_daily_mean", "max_drawdown", "calmar_ratio", "sortino_ratio", "annualized_volatility", "option_leg_annualized_pnl_contribution"]], pct_cols=["annualized_return_cagr", "max_drawdown", "annualized_volatility", "option_leg_annualized_pnl_contribution"], num_cols=["sharpe_daily_mean", "calmar_ratio", "sortino_ratio"])}

## 5. Option-leg 归因

`510050_DTE30_D40_Q70_Hold` 的净 option leg 年化贡献为 {_fmt_pct(q70["option_leg_annualized_pnl_contribution"])}，是否为正：{option_positive}。

{_md_table(s[["sleeve_name", "premium_capture_ratio_agg", "payoff_burden_agg", "positive_option_leg_period_rate", "assignment_rate", "p95_short_call_mtm_loss", "p99_short_call_mtm_loss"]], pct_cols=["premium_capture_ratio_agg", "payoff_burden_agg", "positive_option_leg_period_rate", "assignment_rate", "p95_short_call_mtm_loss", "p99_short_call_mtm_loss"])}

读数：D40 Q70 相对 BuyHold 的 Sharpe 从 {_fmt_num(buyhold["sharpe_daily_mean"])} 提升到 {_fmt_num(q70["sharpe_daily_mean"])}，最大回撤从 {_fmt_pct(buyhold["max_drawdown"])} 降到 {_fmt_pct(q70["max_drawdown"])}。这支持把 510050 视为 positive carry / risk-control 候选，而不是单纯的 premium illusion。

## 6. 与 510300 的相关性

{_md_table(corr_summary, num_cols=["daily_return_correlation", "rolling_corr_mean", "rolling_corr_median", "rolling_corr_p05", "rolling_corr_p95", "rolling_corr_min", "rolling_corr_max"])}

解释：510050 与 510300 的 Q70 sleeve 相关性为 {_fmt_num(q70_corr["daily_return_correlation"])}，属于 `{q70_corr["interpretation"]}`。它提供的是相似的大盘低波动 / 金融权重暴露，分散化价值有限；但如果 option carry 更稳定，可以作为第二个大盘备兑核心，组合层需要控制风格重叠。

## 7. Sleeve 分类结论

推荐 sleeve：`{primary["sleeve_name"]}`。

分类：`{primary["classification"]}`。

理由：{primary["reason"]}

约束：Q100 和 ATM Q100 只保留为 stress / diagnostic，不作为默认组合层主候选。本报告中的收益捕捉指结构性风险补偿，不表示确定性收益。

## 8. 后续组合层建议

510050 {alt_text} 后续 Step B / Step B+ 的 alternative universe：`510300 + 510050 + 159915`。

推荐定位：defensive-income universe。510300 仍是第一大盘备兑核心；510050 可以作为第二个大盘备兑核心，但与 510300 高相关，组合层应把它看成同类风格增强，而不是独立分散化资产。

## 9. Sanity Checks

{_md_table(sanity)}
"""
    (REPORT_DIR / "ver3_0_stepA_extension_510050_sleeve_master_report.md").write_text(text, encoding="utf-8")


def write_readme_and_manifest(
    summary: pd.DataFrame,
    classification: pd.DataFrame,
    corr_summary: pd.DataFrame,
    full_source_range: dict[str, str],
    sanity: pd.DataFrame,
) -> None:
    primary = classification[classification["recommendation_status"].eq("primary_for_portfolio_layer")].iloc[0]
    q70_corr = corr_summary[corr_summary["comparison_name"].eq("D40_Q70_pair")].iloc[0]
    readme = f"""# ver3.0 Step A-Extension：510050 Single-ETF Sleeve Clarification

本目录保存 510050 单 ETF covered-call sleeve 画像。它是 Step A 的扩展，不覆盖既有 `510300/510500/159915` 输出，也不进入组合层。

## 运行方式

```powershell
python ver3\\scripts\\python\\run_ver3_0_stepA_extension_510050_sleeve_clarification.py
```

## 样本与结论

| 项目 | 内容 |
| --- | --- |
| 源数据可用区间 | {full_source_range["source_start"]} 至 {full_source_range["source_end"]} |
| 正式指标区间 | {START_DATE.date().isoformat()} 至 {END_DATE.date().isoformat()} |
| 推荐 sleeve | `{primary["sleeve_name"]}` |
| 分类 | `{primary["classification"]}` |
| 510300 相关性判断 | {q70_corr["interpretation"]} |

Step B / Step B+ 可把该 panel 作为 alternative universe 的候选输入，但固定权重和组合层指标不在本步骤计算。
"""
    (OUT_ROOT / "README.md").write_text(readme, encoding="utf-8")

    manifest = {
        "experiment_id": "ver3_0_stepA_extension_510050_sleeve_clarification",
        "status": "complete",
        "generated_at": "2026-06-30",
        "runner": "ver3/scripts/python/run_ver3_0_stepA_extension_510050_sleeve_clarification.py",
        "sample_start": START_DATE.date().isoformat(),
        "sample_end": END_DATE.date().isoformat(),
        "source_start": full_source_range["source_start"],
        "source_end": full_source_range["source_end"],
        "universe": [ETF_CODE],
        "reference_etf_for_correlation": REFERENCE_ETF,
        "input_files": [
            str(INPUT_DAILY.relative_to(ROOT)),
            str(INPUT_PERIOD.relative_to(ROOT)),
            str(STEP_A_PANEL_WIDE.relative_to(ROOT)),
        ],
        "primary_recommendation": {
            "sleeve_name": primary["sleeve_name"],
            "classification": primary["classification"],
            "recommendation_status": primary["recommendation_status"],
        },
        "correlation_summary": corr_summary.to_dict(orient="records"),
        "sanity_checks": {
            "path": "audit/ver3_0_stepA_extension_510050_sanity_checks.csv",
            "passed": int(sanity["passed"].sum()),
            "total": int(len(sanity)),
        },
        "downstream_contract": {
            "next_step": "ver3_0_stepB_fixed_weight_portfolios",
            "read_first": [
                "panel/ver3_0_stepA_extension_510050_sleeve_return_panel_wide.csv",
                "panel/ver3_0_stepA_extension_510050_sleeve_return_panel_long.csv",
            ],
            "boundary": "This extension produces 510050 sleeve diagnostics only; portfolio weights begin in Step B.",
        },
    }
    (OUT_ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=_json_default), encoding="utf-8")


def write_figures(
    daily: pd.DataFrame,
    summary: pd.DataFrame,
    classification: pd.DataFrame,
    corr_summary: pd.DataFrame,
    rolling_corr: pd.DataFrame,
) -> None:
    plot_nav(daily, classification)
    plot_drawdown(daily, classification)
    plot_metric_comparison(summary, classification)
    plot_correlation(corr_summary, rolling_corr)


def plot_nav(daily: pd.DataFrame, classification: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(11, 5.8))
    primary = set(classification[classification["recommendation_status"].eq("primary_for_portfolio_layer")]["sleeve_name"])
    backup = set(classification[classification["recommendation_status"].eq("backup_for_portfolio_layer")]["sleeve_name"])
    for sleeve, g in daily.groupby("sleeve_name"):
        lw = 2.5 if sleeve in primary else 1.8 if sleeve in backup else 1.0
        alpha = 0.95 if sleeve in primary or sleeve in backup else 0.55
        style = "--" if "Q100" in sleeve else "-"
        ax.plot(g["date"], g["nav_total"], label=short_sleeve(sleeve), linewidth=lw, alpha=alpha, linestyle=style)
    ax.set_title("510050 sleeve NAV curves")
    ax.set_ylabel("NAV")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "ver3_0_stepA_extension_510050_nav_curves.png", dpi=160)
    plt.close(fig)


def plot_drawdown(daily: pd.DataFrame, classification: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(11, 5.8))
    primary = set(classification[classification["recommendation_status"].eq("primary_for_portfolio_layer")]["sleeve_name"])
    for sleeve, g in daily.groupby("sleeve_name"):
        gg = g.sort_values("date").copy()
        dd = gg["nav_total"] / gg["nav_total"].cummax() - 1.0
        lw = 2.4 if sleeve in primary else 1.1
        alpha = 0.9 if sleeve in primary else 0.55
        style = "--" if "Q100" in sleeve else "-"
        ax.plot(gg["date"], dd, label=short_sleeve(sleeve), linewidth=lw, alpha=alpha, linestyle=style)
    ax.set_title("510050 sleeve drawdown curves")
    ax.set_ylabel("Drawdown")
    ax.yaxis.set_major_formatter(lambda y, _pos: f"{y:.0%}")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "ver3_0_stepA_extension_510050_drawdown_curves.png", dpi=160)
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
    fig.savefig(FIGURE_DIR / "ver3_0_stepA_extension_510050_metric_comparison.png", dpi=160)
    plt.close(fig)


def plot_correlation(corr_summary: pd.DataFrame, rolling_corr: pd.DataFrame) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(10.5, 7.2), height_ratios=[1, 2])
    axes[0].bar(corr_summary["comparison_name"], corr_summary["daily_return_correlation"], color=["#4C78A8", "#F58518"])
    axes[0].set_ylim(0, 1)
    axes[0].set_title("510050 vs 510300 daily return correlation")
    axes[0].grid(axis="y", alpha=0.22)
    for name, g in rolling_corr.groupby("comparison_name"):
        axes[1].plot(g["date"], g["rolling_correlation"], label=name, linewidth=1.6)
    axes[1].axhline(0.85, color="#666666", linestyle="--", linewidth=0.9)
    axes[1].set_ylim(0, 1)
    axes[1].set_title("63-day rolling correlation")
    axes[1].grid(alpha=0.25)
    axes[1].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "ver3_0_stepA_extension_510050_vs_510300_correlation.png", dpi=160)
    plt.close(fig)


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
    for directory in (CARD_DIR, REPORT_DIR):
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
    values = _numeric(df[col])
    if "period_index" not in df:
        return values.diff().fillna(values)
    out = values.groupby(df["period_index"]).diff()
    first = ~df["period_index"].duplicated()
    out.loc[first] = values.loc[first]
    return out.fillna(0.0)


def _numeric(values: Any) -> pd.Series:
    if isinstance(values, pd.Series):
        return pd.to_numeric(values, errors="coerce").fillna(0.0)
    return pd.Series(values).astype(float)


def _safe_div(numerator: float, denominator: float) -> float:
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
    if value >= 0.9:
        return "very high overlap; mainly repeated large-cap exposure"
    if value >= 0.8:
        return "high overlap; limited diversification but usable as second core"
    if value >= 0.65:
        return "moderate overlap; some diversification value"
    return "meaningful diversification value"


def _date_iso(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return pd.Timestamp(value).date().isoformat()


def _fmt_pct(value: Any) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value):.2%}"


def _fmt_num(value: Any) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value):.3f}"


def _md_table(df: pd.DataFrame, pct_cols: list[str] | None = None, num_cols: list[str] | None = None) -> str:
    pct = set(pct_cols or [])
    num = set(num_cols or [])
    d = df.copy()
    for col in d.columns:
        if col in pct:
            d[col] = d[col].map(_fmt_pct)
        elif col in num:
            d[col] = d[col].map(_fmt_num)
        else:
            d[col] = d[col].map(lambda x: "" if pd.isna(x) else str(x))
    if d.empty:
        return "_empty_"
    return d.to_markdown(index=False)


def short_sleeve(name: str) -> str:
    return (
        name.replace("510050_", "")
        .replace("DTE30_", "")
        .replace("_Hold", "")
        .replace("ETF_BuyHold", "BuyHold")
    )


def class_color(value: str) -> str:
    return {
        "Positive Carry Overlay": "#4C78A8",
        "Defensive Overlay": "#59A14F",
        "Pure ETF Preferred": "#9C755F",
        "Stress / Diagnostic Only": "#B07AA1",
        "Not Recommended": "#E15759",
    }.get(str(value), "#777777")


def _setup_plot_style() -> None:
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


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        if np.isnan(value):
            return None
        return float(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if pd.isna(value):
        return None
    return str(value)


if __name__ == "__main__":
    main()
