from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.tri as mtri
import numpy as np
import pandas as pd
from matplotlib.ticker import PercentFormatter


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.metrics.ver2_metric_standard import (  # noqa: E402
    compute_portfolio_option_contribution,
    summarize_daily_nav,
)
from ver2_downside_protection.config import StrategyConfig, load_config  # noqa: E402
from ver2_downside_protection.strategy_engine import Ver2BacktestResult, run_ver2_backtest  # noqa: E402


CONFIG_PATH = ROOT / "configs" / "ver2_downside_protection.yaml"
OPTION_PATH = ROOT / "data" / "raw" / "options_daily.csv"
OUT_ROOT = ROOT / "outputs" / "ver3_0_stepA_moneyness_refined_daily_mtm_surface"
DAILY_DIR = OUT_ROOT / "daily"
PERIOD_DIR = OUT_ROOT / "period"
SUMMARY_DIR = OUT_ROOT / "summary"
FIGURE_DIR = OUT_ROOT / "figures"
REPORT_DIR = OUT_ROOT / "reports"
AUDIT_DIR = OUT_ROOT / "audit"

FILE_PREFIX = "ver3_0_stepA_moneyness_refined_daily_mtm"
MASTER_REPORT_NAME = "ver3_0_stepA_moneyness_refined_daily_mtm_surface_report.md"

MAIN_START = pd.Timestamp("2022-09-30")
SHORT_START_588000 = pd.Timestamp("2023-06-05")
END_DATE = pd.Timestamp("2026-05-27")
TARGET_DTE = 30
MIN_DTE = 20
MAX_DTE = 45
TRADING_DAYS_PER_YEAR = 252.0


@dataclass(frozen=True)
class EtfSpec:
    etf_code: str
    sample_start: pd.Timestamp
    sample_end: pd.Timestamp
    sample_scope: str
    role_note: str


@dataclass(frozen=True)
class MoneynessSpec:
    label: str
    target_moneyness: float

    @property
    def strategy_name(self) -> str:
        return f"{self.label}_100"

    @property
    def strategy_kind(self) -> str:
        return "atm" if abs(self.target_moneyness) < 1e-12 else "otm_pct"


ETF_SPECS: tuple[EtfSpec, ...] = (
    EtfSpec("510300", MAIN_START, END_DATE, "main_stepA_common_sample", "大盘核心资产；用于检验更细 OTM 梯度是否改变 510300 的 Step A 画像。"),
    EtfSpec("510050", MAIN_START, END_DATE, "main_stepA_common_sample", "大盘偏蓝筹资产；作为更防御型 ETF 的同标尺 moneyness 参照。"),
    EtfSpec("510500", MAIN_START, END_DATE, "main_stepA_common_sample", "中盘弹性资产；重点观察轻度 OTM 与低覆盖率能否改善此前较差的备兑结果。"),
    EtfSpec("159915", MAIN_START, END_DATE, "main_stepA_common_sample", "成长弹性资产；重点观察保留上行后的备兑曲面是否仍被期权腿拖累。"),
    EtfSpec("588000", SHORT_START_588000, END_DATE, "short_sample_extension", "科创成长扩展样本；期权数据从 2023-06-05 起，只作 extension 诊断。"),
)

MONEYNESS_GRID: tuple[MoneynessSpec, ...] = (
    MoneynessSpec("ATM", 0.00),
    MoneynessSpec("OTM1", 0.01),
    MoneynessSpec("OTM2", 0.02),
    MoneynessSpec("OTM3", 0.03),
    MoneynessSpec("OTM4", 0.04),
    MoneynessSpec("OTM5", 0.05),
    MoneynessSpec("OTM7", 0.07),
)
COVERAGE_GRID: tuple[float, ...] = tuple(round(x / 10, 1) for x in range(1, 11))

SUMMARY_COLUMNS = [
    "etf_code",
    "sleeve_name",
    "parameter_grid_role",
    "sample_scope",
    "sample_start",
    "sample_end",
    "n_trading_days",
    "moneyness_label",
    "target_moneyness",
    "coverage",
    "coverage_label",
    "annualized_return_cagr",
    "arithmetic_annualized_return",
    "annualized_volatility",
    "sharpe_daily_mean",
    "sortino_ratio",
    "calmar_ratio",
    "max_drawdown",
    "monthly_win_rate",
    "worst_month_return",
    "best_month_return",
    "option_leg_annualized_pnl_contribution",
    "premium_capture_ratio_agg",
    "payoff_burden_agg",
    "positive_option_leg_period_rate",
    "assignment_rate",
    "p95_short_call_mtm_loss",
    "p99_short_call_mtm_loss",
    "max_short_call_mtm_loss",
    "avg_actual_dte",
    "avg_realized_moneyness",
    "median_realized_moneyness",
    "selected_periods",
    "skipped_periods",
    "avg_active_coverage",
    "annualized_return_cagr_vs_buyhold",
    "sharpe_diff_vs_buyhold",
    "mdd_improvement_vs_buyhold",
    "option_leg_verdict",
    "recommendation_read",
    "source_engine",
]


def main() -> None:
    args = parse_args()
    ensure_dirs()
    setup_plot_style()

    all_daily: list[pd.DataFrame] = []
    all_period: list[pd.DataFrame] = []
    all_summary: list[pd.DataFrame] = []
    all_diagnostics: list[pd.DataFrame] = []

    for spec in ETF_SPECS:
        print(f"running daily-MTM moneyness surface: {spec.etf_code}")
        result = run_etf_source_backtest(spec, args.option_path)
        source_daily = canonical_source_daily(result.daily_mtm)
        common_dates = build_common_dates(source_daily, spec)
        daily = build_etf_daily_surface(spec, source_daily, common_dates)
        period = build_etf_period_surface(spec, result.periods, result.daily_mtm)
        summary = build_summary(spec, daily, period, args.rf)
        diagnostics = build_diagnostics(spec, result, daily, period, common_dates, args.option_path)

        all_daily.append(daily)
        all_period.append(period)
        all_summary.append(summary)
        all_diagnostics.append(diagnostics)

    daily_df = pd.concat(all_daily, ignore_index=True).sort_values(["etf_code", "sleeve_name", "date"])
    period_df = pd.concat(all_period, ignore_index=True).sort_values(["etf_code", "sleeve_name", "rebalance_date"])
    summary_df = pd.concat(all_summary, ignore_index=True).sort_values(["etf_code", "parameter_grid_role", "target_moneyness", "coverage"])
    diagnostics_df = pd.concat(all_diagnostics, ignore_index=True)
    summary_df = add_buyhold_relative_metrics(summary_df)
    summary_df = add_verdicts(summary_df)
    summary_df.insert(0, "surface_point_id", make_surface_ids(summary_df))

    write_tables(daily_df, period_df, summary_df, diagnostics_df)
    figure_df = write_figures(summary_df, daily_df)
    sanity_df = build_sanity_checks(summary_df, daily_df, period_df, diagnostics_df, figure_df)
    sanity_df.to_csv(AUDIT_DIR / f"{FILE_PREFIX}_sanity_checks.csv", index=False, encoding="utf-8-sig")

    write_reports(summary_df, diagnostics_df, figure_df)
    write_manifest(summary_df, daily_df, period_df, diagnostics_df, figure_df, sanity_df, args.option_path)
    write_readme(summary_df, sanity_df)

    print(f"wrote outputs: {OUT_ROOT}")
    print(f"surface rows: {len(summary_df[summary_df['parameter_grid_role'].eq('surface')])}")
    print(f"sanity checks: {int(sanity_df['passed'].sum())}/{len(sanity_df)} passed")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build ver3 Step A moneyness x coverage refined surfaces with continuous DTE30 daily MTM."
    )
    parser.add_argument("--rf", type=float, default=0.0, help="Annual risk-free rate for daily Sharpe.")
    parser.add_argument(
        "--option-path",
        type=Path,
        default=OPTION_PATH,
        help="Daily option chain path. Defaults to data/raw/options_daily.csv.",
    )
    return parser.parse_args()


def ensure_dirs() -> None:
    for path in (DAILY_DIR, PERIOD_DIR, SUMMARY_DIR, FIGURE_DIR, REPORT_DIR, AUDIT_DIR):
        path.mkdir(parents=True, exist_ok=True)


def run_etf_source_backtest(spec: EtfSpec, option_path: Path) -> Ver2BacktestResult:
    config = load_config(CONFIG_PATH, ROOT)
    strategies = [StrategyConfig("BuyHold", "buy_hold", 0.0, 0.0, True)]
    strategies.extend(
        StrategyConfig(m.strategy_name, m.strategy_kind, 1.0, m.target_moneyness, True)
        for m in MONEYNESS_GRID
    )
    config = replace(
        config,
        etf_codes=(spec.etf_code,),
        paths=replace(config.paths, options=option_path, output_dir=OUT_ROOT),
        backtest=replace(
            config.backtest,
            start_date=spec.sample_start.date().isoformat(),
            end_date=spec.sample_end.date().isoformat(),
            initial_nav=1.0,
            execution_mode="continuous_30d",
            roll_frequency="monthly",
            target_dte=TARGET_DTE,
            min_days_to_expiry=MIN_DTE,
            max_days_to_expiry=MAX_DTE,
            min_periods=1,
            require_expiry_within_period=False,
            dte_fallback_mode="strict_window",
        ),
        strategies=tuple(strategies),
    )
    return run_ver2_backtest(config)


def canonical_source_daily(daily_mtm: pd.DataFrame) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    for strategy_name, g in daily_mtm.groupby("strategy_name"):
        sort_cols = [col for col in ["date", "period_index"] if col in g.columns]
        gg = g.sort_values(sort_cols).drop_duplicates("date", keep="last").copy()
        gg["date"] = pd.to_datetime(gg["date"], errors="coerce")
        out[str(strategy_name)] = gg.set_index("date").sort_index()
    return out


def build_common_dates(source_daily: dict[str, pd.DataFrame], spec: EtfSpec) -> pd.DatetimeIndex:
    required = ["BuyHold"] + [m.strategy_name for m in MONEYNESS_GRID]
    missing = [name for name in required if name not in source_daily]
    if missing:
        raise ValueError(f"{spec.etf_code} missing source strategies: {missing}")

    common_dates = source_daily["BuyHold"].index
    for name in required[1:]:
        common_dates = common_dates.intersection(source_daily[name].index)
    common_dates = common_dates[(common_dates >= spec.sample_start) & (common_dates <= spec.sample_end)]
    if common_dates.empty:
        raise ValueError(f"{spec.etf_code} has no common daily MTM dates.")
    return pd.DatetimeIndex(common_dates).sort_values()


def build_etf_daily_surface(
    spec: EtfSpec,
    source_daily: dict[str, pd.DataFrame],
    common_dates: pd.DatetimeIndex,
) -> pd.DataFrame:
    buyhold = source_daily["BuyHold"].loc[common_dates].copy()
    buyhold_nav = buyhold["daily_mtm_nav"].astype(float)
    underlying_return = buyhold_nav.pct_change().fillna(0.0)
    underlying_return.iloc[0] = 0.0

    frames: list[pd.DataFrame] = []
    frames.append(
        pd.DataFrame(
            {
                "date": common_dates,
                "etf_code": spec.etf_code,
                "sleeve_name": f"{spec.etf_code}_ETF_BuyHold",
                "parameter_grid_role": "buyhold",
                "sample_scope": spec.sample_scope,
                "moneyness_label": "BuyHold",
                "target_moneyness": np.nan,
                "coverage": 0.0,
                "coverage_label": "Q0",
                "dte_label": "NA",
                "close_rule": "buyhold",
                "nav_total": (1.0 + underlying_return).cumprod().values,
                "daily_return_total": underlying_return.values,
                "nav_underlying_component": (1.0 + underlying_return).cumprod().values,
                "daily_return_underlying_component": underlying_return.values,
                "nav_option_leg_component": 1.0,
                "daily_return_option_leg_component": 0.0,
                "option_leg_pnl": 0.0,
                "short_call_liability": 0.0,
                "short_call_mtm_loss": 0.0,
                "active_short_call_flag": False,
                "active_coverage": 0.0,
                "source_strategy_name": "BuyHold",
                "option_code": np.nan,
                "strike": np.nan,
                "rebalance_date": pd.NaT,
                "expiry_date": pd.NaT,
                "period_index": np.nan,
                "option_price_source": "none",
            }
        )
    )

    for m in MONEYNESS_GRID:
        src = source_daily[m.strategy_name].loc[common_dates].copy()
        q100_return = src["daily_mtm_nav"].astype(float).pct_change().fillna(0.0)
        q100_return.iloc[0] = 0.0
        option_return_q100 = q100_return - underlying_return
        for coverage in COVERAGE_GRID:
            coverage_label = f"Q{int(round(coverage * 100))}"
            sleeve_name = f"{spec.etf_code}_DTE30_{m.label}_{coverage_label}_Hold"
            option_return = option_return_q100 * coverage
            total_return = underlying_return + option_return
            total_return.iloc[0] = 0.0
            option_return.iloc[0] = 0.0
            active = src["position_state"].astype(str).eq("short_call")
            frames.append(
                pd.DataFrame(
                    {
                        "date": common_dates,
                        "etf_code": spec.etf_code,
                        "sleeve_name": sleeve_name,
                        "parameter_grid_role": "surface",
                        "sample_scope": spec.sample_scope,
                        "moneyness_label": m.label,
                        "target_moneyness": m.target_moneyness,
                        "coverage": coverage,
                        "coverage_label": coverage_label,
                        "dte_label": "DTE30",
                        "close_rule": "hold_to_expiry",
                        "nav_total": (1.0 + total_return).cumprod().values,
                        "daily_return_total": total_return.values,
                        "nav_underlying_component": (1.0 + underlying_return).cumprod().values,
                        "daily_return_underlying_component": underlying_return.values,
                        "nav_option_leg_component": (1.0 + option_return).cumprod().values,
                        "daily_return_option_leg_component": option_return.values,
                        "option_leg_pnl": option_return.values,
                        "short_call_liability": numeric(src.get("option_liability_return", 0.0)).values * coverage,
                        "short_call_mtm_loss": numeric(src.get("short_call_mtm_loss_return", 0.0)).values * coverage,
                        "active_short_call_flag": active.values,
                        "active_coverage": np.where(active.values, coverage, 0.0),
                        "source_strategy_name": m.strategy_name,
                        "option_code": src.get("option_code", np.nan).values,
                        "strike": src.get("strike", np.nan).values,
                        "rebalance_date": src.get("rebalance_date", pd.NaT).values,
                        "expiry_date": src.get("expiry_date", pd.NaT).values,
                        "period_index": src.get("period_index", np.nan).values,
                        "option_price_source": src.get("option_price_source", "none").values
                        if "option_price_source" in src
                        else "none",
                    }
                )
            )

    daily = pd.concat(frames, ignore_index=True)
    return daily.sort_values(["etf_code", "sleeve_name", "date"]).reset_index(drop=True)


def build_etf_period_surface(
    spec: EtfSpec,
    source_period: pd.DataFrame,
    raw_source_daily: pd.DataFrame,
) -> pd.DataFrame:
    stress_lookup = build_period_stress_lookup(raw_source_daily)
    rows: list[dict[str, Any]] = []
    p = source_period.copy()
    p["rebalance_date"] = pd.to_datetime(p["rebalance_date"], errors="coerce")
    for m in MONEYNESS_GRID:
        source = p[p["strategy_name"].eq(m.strategy_name)].copy()
        source = source[(source["rebalance_date"] >= spec.sample_start) & (source["rebalance_date"] <= spec.sample_end)]
        for coverage in COVERAGE_GRID:
            coverage_label = f"Q{int(round(coverage * 100))}"
            sleeve_name = f"{spec.etf_code}_DTE30_{m.label}_{coverage_label}_Hold"
            for _, row in source.sort_values("rebalance_date").iterrows():
                selected = bool(int(row.get("option_selected_flag", 0)))
                premium = float(row.get("premium_return", 0.0) or 0.0) * coverage
                payoff = float(row.get("upside_payoff_return", 0.0) or 0.0) * coverage
                cost = float(row.get("transaction_cost_return", 0.0) or 0.0) * coverage
                option_leg = premium - payoff - cost
                stress_key = (str(row.get("strategy_name")), int(row.get("period_index", 0)), str(row.get("option_code")))
                stress = stress_lookup.get(stress_key, {"max": np.nan, "p95": np.nan, "p99": np.nan})
                rows.append(
                    {
                        "etf_code": spec.etf_code,
                        "sleeve_name": sleeve_name,
                        "source_strategy_name": m.strategy_name,
                        "moneyness_label": m.label,
                        "target_moneyness": m.target_moneyness,
                        "coverage": coverage,
                        "coverage_label": coverage_label,
                        "dte_label": "DTE30",
                        "target_dte": TARGET_DTE,
                        "period_index": row.get("period_index", np.nan),
                        "rebalance_date": date_iso(row.get("rebalance_date")),
                        "expiry_date": date_iso(row.get("expiry_date")),
                        "period_end_date": date_iso(row.get("period_end_date")),
                        "option_code": row.get("option_code", np.nan),
                        "option_selected_flag": int(selected),
                        "selection_reason": row.get("selection_reason", ""),
                        "actual_dte": row.get("actual_dte", np.nan),
                        "strike": row.get("strike", np.nan),
                        "underlying_price_at_entry": row.get("underlying_price_at_entry", np.nan),
                        "underlying_price_at_expiry": row.get("underlying_price_at_expiry", np.nan),
                        "realized_moneyness": row.get("realized_moneyness", np.nan),
                        "selected_delta": row.get("selected_delta", np.nan),
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
                        "max_short_call_mtm_loss_in_period": stress["max"] * coverage if pd.notna(stress["max"]) else np.nan,
                        "p95_short_call_mtm_loss_in_period": stress["p95"] * coverage if pd.notna(stress["p95"]) else np.nan,
                        "p99_short_call_mtm_loss_in_period": stress["p99"] * coverage if pd.notna(stress["p99"]) else np.nan,
                    }
                )
    return pd.DataFrame(rows).sort_values(["sleeve_name", "rebalance_date"]).reset_index(drop=True)


def build_period_stress_lookup(source_daily: pd.DataFrame) -> dict[tuple[str, int, str], dict[str, float]]:
    lookup: dict[tuple[str, int, str], dict[str, float]] = {}
    d = source_daily[source_daily["strategy_name"].isin([m.strategy_name for m in MONEYNESS_GRID])].copy()
    if d.empty:
        return lookup
    for (strategy, period_index, option_code), g in d.groupby(["strategy_name", "period_index", "option_code"], dropna=False):
        stress = numeric(g.get("short_call_mtm_loss_return", 0.0))
        lookup[(str(strategy), int(period_index), str(option_code))] = {
            "max": float(stress.max()),
            "p95": float(stress.quantile(0.95)),
            "p99": float(stress.quantile(0.99)),
        }
    return lookup


def build_summary(spec: EtfSpec, daily: pd.DataFrame, period: pd.DataFrame, rf: float) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for sleeve_name, g in daily.groupby("sleeve_name"):
        sample = g.sort_values("date").copy()
        p = period[period["sleeve_name"].eq(sleeve_name)].copy()
        metrics = summarize_daily_nav(sample[["date", "nav_total"]], date_col="date", nav_col="nav_total", rf=rf)
        first = sample.iloc[0]
        rows.append(
            {
                "etf_code": spec.etf_code,
                "sleeve_name": sleeve_name,
                "parameter_grid_role": first["parameter_grid_role"],
                "sample_scope": spec.sample_scope,
                "moneyness_label": first["moneyness_label"],
                "target_moneyness": first["target_moneyness"],
                "coverage": first["coverage"],
                "coverage_label": first["coverage_label"],
                **metrics,
                **summarize_option_metrics(sample, p),
                "source_engine": "continuous_30d_daily_mtm",
            }
        )
    out = pd.DataFrame(rows)
    for col in SUMMARY_COLUMNS:
        if col not in out:
            out[col] = np.nan
    return out[SUMMARY_COLUMNS]


def summarize_option_metrics(sample: pd.DataFrame, period: pd.DataFrame) -> dict[str, Any]:
    option_pnl = sample["option_leg_pnl"].astype(float)
    stress = sample["short_call_mtm_loss"].astype(float)
    if period.empty:
        return {
            "option_leg_annualized_pnl_contribution": 0.0,
            "premium_capture_ratio_agg": np.nan,
            "payoff_burden_agg": np.nan,
            "positive_option_leg_period_rate": np.nan,
            "assignment_rate": np.nan,
            "p95_short_call_mtm_loss": 0.0,
            "p99_short_call_mtm_loss": 0.0,
            "max_short_call_mtm_loss": 0.0,
            "avg_actual_dte": np.nan,
            "avg_realized_moneyness": np.nan,
            "median_realized_moneyness": np.nan,
            "selected_periods": 0,
            "skipped_periods": 0,
            "avg_active_coverage": 0.0,
        }
    selected = period[period["option_selected_flag"].astype(int).eq(1)].copy()
    premium = period["premium_return"].astype(float)
    payoff = period["payoff_return"].astype(float)
    option_leg = period["option_leg_return"].astype(float)
    return {
        "option_leg_annualized_pnl_contribution": compute_portfolio_option_contribution(option_pnl, n_days=len(sample)),
        "premium_capture_ratio_agg": safe_div(float(option_leg.sum()), float(premium.sum())),
        "payoff_burden_agg": safe_div(float(payoff.sum()), float(premium.sum())),
        "positive_option_leg_period_rate": float((option_leg > 0).mean()),
        "assignment_rate": float(period["assignment_flag"].astype(bool).mean()),
        "p95_short_call_mtm_loss": float(stress.quantile(0.95)),
        "p99_short_call_mtm_loss": float(stress.quantile(0.99)),
        "max_short_call_mtm_loss": float(stress.max()),
        "avg_actual_dte": float(selected["actual_dte"].astype(float).mean()) if not selected.empty else np.nan,
        "avg_realized_moneyness": float(selected["realized_moneyness"].astype(float).mean()) if not selected.empty else np.nan,
        "median_realized_moneyness": float(selected["realized_moneyness"].astype(float).median()) if not selected.empty else np.nan,
        "selected_periods": int(selected["option_selected_flag"].sum()) if not selected.empty else 0,
        "skipped_periods": int((period["option_selected_flag"].astype(int) == 0).sum()),
        "avg_active_coverage": float(sample["active_coverage"].astype(float).mean()),
    }


def add_buyhold_relative_metrics(summary: pd.DataFrame) -> pd.DataFrame:
    out = summary.copy()
    buyhold = out[out["parameter_grid_role"].eq("buyhold")].set_index("etf_code")
    for idx, row in out.iterrows():
        b = buyhold.loc[row["etf_code"]]
        out.loc[idx, "annualized_return_cagr_vs_buyhold"] = row["annualized_return_cagr"] - b["annualized_return_cagr"]
        out.loc[idx, "sharpe_diff_vs_buyhold"] = row["sharpe_daily_mean"] - b["sharpe_daily_mean"]
        out.loc[idx, "mdd_improvement_vs_buyhold"] = b["max_drawdown"] - row["max_drawdown"]
    return out[["surface_point_id"] + [c for c in SUMMARY_COLUMNS if c in out.columns]] if "surface_point_id" in out else out[SUMMARY_COLUMNS]


def add_verdicts(summary: pd.DataFrame) -> pd.DataFrame:
    out = summary.copy()
    out["option_leg_verdict"] = out["option_leg_verdict"].astype("object")
    out["recommendation_read"] = out["recommendation_read"].astype("object")
    for idx, row in out.iterrows():
        if row["parameter_grid_role"] == "buyhold":
            out.loc[idx, "option_leg_verdict"] = "pure ETF baseline"
            out.loc[idx, "recommendation_read"] = "baseline"
            continue
        option_leg = float(row["option_leg_annualized_pnl_contribution"])
        cagr_delta = float(row["annualized_return_cagr_vs_buyhold"])
        sharpe_delta = float(row["sharpe_diff_vs_buyhold"])
        mdd_improvement = float(row["mdd_improvement_vs_buyhold"])
        if option_leg > 0:
            option_verdict = "positive option leg"
        elif option_leg > -0.01:
            option_verdict = "near-flat option leg"
        else:
            option_verdict = "negative option leg"
        if cagr_delta > 0 and sharpe_delta > 0 and mdd_improvement > 0:
            read = "dominates buyhold in this diagnostic grid"
        elif sharpe_delta > 0 and mdd_improvement > 0:
            read = "risk-adjusted defensive tradeoff, not a return upgrade"
        elif mdd_improvement > 0:
            read = "drawdown cushion with visible return cost"
        else:
            read = "diagnostic only, no clear improvement"
        out.loc[idx, "option_leg_verdict"] = option_verdict
        out.loc[idx, "recommendation_read"] = read
    return out


def build_diagnostics(
    spec: EtfSpec,
    result: Ver2BacktestResult,
    daily: pd.DataFrame,
    period: pd.DataFrame,
    common_dates: pd.DatetimeIndex,
    option_path: Path,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    rows.append(
        {
            "etf_code": spec.etf_code,
            "check_name": "sample_window",
            "value": f"{common_dates.min().date().isoformat()} to {common_dates.max().date().isoformat()}",
            "passed": True,
            "note": spec.sample_scope,
        }
    )
    rows.append(
        {
            "etf_code": spec.etf_code,
            "check_name": "source_engine",
            "value": "ver2_downside_protection.strategy_engine.run_ver2_backtest",
            "passed": True,
            "note": "continuous_30d daily MTM, not src.backtest.custom monthly segmented NAV",
        }
    )
    rows.append(
        {
            "etf_code": spec.etf_code,
            "check_name": "option_source",
            "value": rel_path(option_path),
            "passed": Path(option_path).exists(),
            "note": "daily option chain",
        }
    )
    for m in MONEYNESS_GRID:
        p = result.periods[result.periods["strategy_name"].eq(m.strategy_name)].copy()
        selected = int(p.get("option_selected_flag", pd.Series(dtype=int)).astype(int).sum()) if not p.empty else 0
        skipped = int((p.get("option_selected_flag", pd.Series(dtype=int)).astype(int) == 0).sum()) if not p.empty else 0
        realized = p.loc[p.get("option_selected_flag", 0).astype(int).eq(1), "realized_moneyness"] if not p.empty else pd.Series(dtype=float)
        rows.append(
            {
                "etf_code": spec.etf_code,
                "check_name": f"{m.label}_selection",
                "value": f"selected={selected}; skipped={skipped}; avg_realized_moneyness={numeric(realized).mean():.4f}"
                if not realized.empty
                else f"selected={selected}; skipped={skipped}",
                "passed": selected > 0,
                "note": f"target_moneyness={m.target_moneyness:.2%}",
            }
        )
    rows.append(
        {
            "etf_code": spec.etf_code,
            "check_name": "daily_rows",
            "value": int(len(daily)),
            "passed": len(daily) > 0,
            "note": f"{daily['sleeve_name'].nunique()} sleeves including BuyHold",
        }
    )
    rows.append(
        {
            "etf_code": spec.etf_code,
            "check_name": "period_rows",
            "value": int(len(period)),
            "passed": len(period) > 0,
            "note": "surface period attribution rows",
        }
    )
    return pd.DataFrame(rows)


def write_tables(
    daily: pd.DataFrame,
    period: pd.DataFrame,
    summary: pd.DataFrame,
    diagnostics: pd.DataFrame,
) -> None:
    daily.to_csv(DAILY_DIR / f"{FILE_PREFIX}_daily_paths.csv", index=False, encoding="utf-8-sig")
    period.to_csv(PERIOD_DIR / f"{FILE_PREFIX}_period_paths.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(SUMMARY_DIR / f"{FILE_PREFIX}_surface_grid.csv", index=False, encoding="utf-8-sig")
    summary[summary["parameter_grid_role"].eq("buyhold")].to_csv(
        SUMMARY_DIR / f"{FILE_PREFIX}_buyhold_baseline.csv", index=False, encoding="utf-8-sig"
    )
    diagnostics.to_csv(AUDIT_DIR / f"{FILE_PREFIX}_run_diagnostics.csv", index=False, encoding="utf-8-sig")


def write_figures(summary: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    surface = summary[summary["parameter_grid_role"].eq("surface")].copy()
    metric_specs = [
        ("sharpe_daily_mean", "Daily Sharpe", None),
        ("annualized_return_cagr", "CAGR", "pct"),
        ("max_drawdown", "Max drawdown", "pct"),
        ("option_leg_annualized_pnl_contribution", "Option leg annual PnL", "pct"),
    ]
    for etf_code in [spec.etf_code for spec in ETF_SPECS]:
        etf_surface = surface[surface["etf_code"].eq(etf_code)].copy()
        for metric, title, fmt_kind in metric_specs:
            path = FIGURE_DIR / f"{etf_code}_{metric}_surface.png"
            plot_heatmap(etf_surface, metric, f"{etf_code} {title}", path, fmt_kind)
            rows.append(
                {
                    "etf_code": etf_code,
                    "figure_type": metric,
                    "metric_name": metric,
                    "figure_kind": "heatmap",
                    "path": rel_path(path),
                }
            )
            surface_3d_path = FIGURE_DIR / f"{etf_code}_{metric}_3d_surface.png"
            plot_3d_surface(etf_surface, metric, f"{etf_code} {title}", surface_3d_path, fmt_kind)
            rows.append(
                {
                    "etf_code": etf_code,
                    "figure_type": f"{metric}_3d_surface",
                    "metric_name": metric,
                    "figure_kind": "surface_3d",
                    "path": rel_path(surface_3d_path),
                }
            )
        nav_path = FIGURE_DIR / f"{etf_code}_selected_nav_paths.png"
        plot_selected_nav_paths(summary, daily, etf_code, nav_path)
        rows.append(
            {
                "etf_code": etf_code,
                "figure_type": "selected_nav_paths",
                "metric_name": "",
                "figure_kind": "nav_paths",
                "path": rel_path(nav_path),
            }
        )
    figure_df = pd.DataFrame(rows)
    figure_df.to_csv(SUMMARY_DIR / f"{FILE_PREFIX}_figures.csv", index=False, encoding="utf-8-sig")
    return figure_df


def plot_heatmap(df: pd.DataFrame, metric: str, title: str, path: Path, fmt_kind: str | None) -> None:
    pivot = df.pivot_table(index="coverage", columns="target_moneyness", values=metric, aggfunc="first")
    pivot = pivot.reindex(index=sorted(pivot.index, reverse=True), columns=[m.target_moneyness for m in MONEYNESS_GRID])
    fig, ax = plt.subplots(figsize=(8.6, 5.2))
    values = pivot.to_numpy(dtype=float)
    im = ax.imshow(values, aspect="auto", cmap="RdYlGn")
    ax.set_title(title)
    ax.set_xlabel("Target moneyness")
    ax.set_ylabel("Coverage")
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels([f"{x:.0%}" for x in pivot.columns])
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels([f"{x:.0%}" for x in pivot.index])
    cbar = fig.colorbar(im, ax=ax)
    if fmt_kind == "pct":
        cbar.ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    for i in range(values.shape[0]):
        for j in range(values.shape[1]):
            value = values[i, j]
            if pd.isna(value):
                text = ""
            elif fmt_kind == "pct":
                text = f"{value:.1%}"
            else:
                text = f"{value:.2f}"
            ax.text(j, i, text, ha="center", va="center", fontsize=7, color="#111111")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_3d_surface(df: pd.DataFrame, metric: str, title: str, path: Path, fmt_kind: str | None) -> None:
    data = df.dropna(subset=["target_moneyness", "coverage", metric]).copy()
    fig = plt.figure(figsize=(9.2, 6.2))
    ax = fig.add_subplot(111, projection="3d")
    if len(data) >= 3:
        x = data["target_moneyness"].astype(float).to_numpy()
        y = data["coverage"].astype(float).to_numpy()
        z = data[metric].astype(float).to_numpy()
        cmap = "RdYlGn_r" if metric == "max_drawdown" else "RdYlGn"
        try:
            triang = mtri.Triangulation(x, y)
            refiner = mtri.UniformTriRefiner(triang)
            refined_tri, refined_z = refiner.refine_field(z, subdiv=2)
            trisurf = ax.plot_trisurf(
                refined_tri,
                refined_z,
                cmap=cmap,
                alpha=0.72,
                linewidth=0.12,
                edgecolor="#f5f7fa",
                antialiased=True,
            )
        except (RuntimeError, ValueError):
            trisurf = ax.plot_trisurf(
                x,
                y,
                z,
                cmap=cmap,
                alpha=0.66,
                linewidth=0.2,
                edgecolor="#f5f7fa",
                antialiased=True,
            )
        fig.colorbar(trisurf, ax=ax, shrink=0.58, pad=0.08, label=title.split(" ", 1)[-1])
        ax.scatter(x, y, z, s=24, color="#17212f", alpha=0.88, edgecolor="white", linewidth=0.35, label="backtest points")
        best = choose_surface_best_row(data, metric)
        if best is not None:
            ax.scatter(
                [float(best["target_moneyness"])],
                [float(best["coverage"])],
                [float(best[metric])],
                s=150,
                marker="*",
                color="#bd4b43",
                edgecolor="white",
                linewidth=0.8,
                label="best grid point",
            )
            ax.text(
                float(best["target_moneyness"]),
                float(best["coverage"]),
                float(best[metric]),
                f" {best['moneyness_label']} {best['coverage_label']}",
                fontsize=8,
                color="#2d3d4d",
            )
    ax.set_title(f"{title}: target moneyness x coverage x metric", pad=18, fontsize=13, fontweight="bold")
    ax.set_xlabel("Target moneyness")
    ax.set_ylabel("Coverage")
    ax.set_zlabel(title.split(" ", 1)[-1])
    ax.xaxis.set_major_formatter(PercentFormatter(1.0))
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    if fmt_kind == "pct":
        ax.zaxis.set_major_formatter(PercentFormatter(1.0))
    ax.view_init(elev=25, azim=-55)
    ax.grid(True, alpha=0.24)
    ax.legend(loc="upper left", bbox_to_anchor=(0.02, 0.98), fontsize=8, frameon=True)
    fig.text(
        0.5,
        0.02,
        "Surface is interpolated for visualization only; strategy interpretation still uses the true daily-MTM grid points.",
        ha="center",
        fontsize=8.5,
        color="#4c5b6b",
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def choose_surface_best_row(data: pd.DataFrame, metric: str) -> pd.Series | None:
    if data.empty or metric not in data.columns:
        return None
    valid = data.dropna(subset=[metric]).copy()
    if valid.empty:
        return None
    ascending = metric == "max_drawdown"
    return valid.sort_values([metric, "sharpe_daily_mean"], ascending=[ascending, False]).iloc[0]


def plot_selected_nav_paths(summary: pd.DataFrame, daily: pd.DataFrame, etf_code: str, path: Path) -> None:
    etf_summary = summary[summary["etf_code"].eq(etf_code)].copy()
    buyhold_name = f"{etf_code}_ETF_BuyHold"
    surface = etf_summary[etf_summary["parameter_grid_role"].eq("surface")].copy()
    candidates = surface.sort_values(["sharpe_daily_mean", "annualized_return_cagr"], ascending=False).head(3)[
        "sleeve_name"
    ].tolist()
    names = [buyhold_name] + candidates
    sample = daily[(daily["etf_code"].eq(etf_code)) & (daily["sleeve_name"].isin(names))].copy()
    fig, ax = plt.subplots(figsize=(9.2, 4.8))
    for sleeve_name, g in sample.groupby("sleeve_name"):
        label = sleeve_name.replace(f"{etf_code}_", "")
        ax.plot(pd.to_datetime(g["date"]), g["nav_total"].astype(float), label=label, linewidth=1.4)
    ax.set_title(f"{etf_code} selected daily MTM NAV paths")
    ax.set_ylabel("NAV")
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def build_sanity_checks(
    summary: pd.DataFrame,
    daily: pd.DataFrame,
    period: pd.DataFrame,
    diagnostics: pd.DataFrame,
    figures: pd.DataFrame,
) -> pd.DataFrame:
    expected_surface_rows = len(ETF_SPECS) * len(MONEYNESS_GRID) * len(COVERAGE_GRID)
    checks = [
        {
            "check_name": "surface_row_count",
            "passed": int(summary["parameter_grid_role"].eq("surface").sum()) == expected_surface_rows,
            "detail": f"expected={expected_surface_rows}; actual={int(summary['parameter_grid_role'].eq('surface').sum())}",
        },
        {
            "check_name": "buyhold_row_count",
            "passed": int(summary["parameter_grid_role"].eq("buyhold").sum()) == len(ETF_SPECS),
            "detail": f"expected={len(ETF_SPECS)}; actual={int(summary['parameter_grid_role'].eq('buyhold').sum())}",
        },
        {
            "check_name": "daily_no_duplicate_sleeve_dates",
            "passed": not daily.duplicated(["etf_code", "sleeve_name", "date"]).any(),
            "detail": f"duplicated={int(daily.duplicated(['etf_code', 'sleeve_name', 'date']).sum())}",
        },
        {
            "check_name": "period_rows_present",
            "passed": len(period) > 0,
            "detail": f"period_rows={len(period)}",
        },
        {
            "check_name": "diagnostics_pass",
            "passed": bool(diagnostics["passed"].fillna(False).all()),
            "detail": f"passed={int(diagnostics['passed'].sum())}/{len(diagnostics)}",
        },
        {
            "check_name": "figures_exist",
            "passed": all((ROOT / str(path)).exists() for path in figures["path"]),
            "detail": f"figures={len(figures)}",
        },
        {
            "check_name": "source_engine_not_monthly_custom",
            "passed": summary["source_engine"].dropna().eq("continuous_30d_daily_mtm").all(),
            "detail": "ver3 refined entry uses run_ver2_backtest daily MTM",
        },
    ]
    return pd.DataFrame(checks)


def write_reports(summary: pd.DataFrame, diagnostics: pd.DataFrame, figures: pd.DataFrame) -> None:
    sections: list[str] = []
    sections.append("# ver3.0 Step A moneyness refined daily-MTM surface report")
    sections.append("")
    sections.append("## 口径边界")
    sections.append("")
    sections.append("- 本报告接替此前未完成的 moneyness 细网格任务，但不沿用 Monthly custom 回测。")
    sections.append("- 选券与日频 NAV 均来自 `ver2_downside_protection.strategy_engine.run_ver2_backtest` 的 `continuous_30d` 日频 MTM 口径。")
    sections.append("- moneyness 维度重新选券；coverage 维度在同一 Q100 选券路径上缩放 option leg，用于观察虚值程度 x 覆盖率曲面。")
    sections.append("- 588000 因期权数据起点较晚，仍为 short-sample extension，不进入同样本主线替代结论。")
    sections.append("")
    overview = build_overview_table(summary)
    sections.append("## 总览")
    sections.append("")
    sections.append(md_table(overview, pct_cols=["buyhold_cagr", "best_cagr", "best_mdd", "best_option_leg"], num_cols=["buyhold_sharpe", "best_sharpe"]))
    sections.append("")
    for spec in ETF_SPECS:
        etf_section = build_etf_report_section(spec, summary, diagnostics, figures)
        sections.append(etf_section)
        (REPORT_DIR / f"{spec.etf_code}_moneyness_refined_daily_mtm_report.md").write_text(etf_section, encoding="utf-8")
    (REPORT_DIR / MASTER_REPORT_NAME).write_text("\n".join(sections), encoding="utf-8")


def build_overview_table(summary: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for spec in ETF_SPECS:
        etf = summary[summary["etf_code"].eq(spec.etf_code)].copy()
        buyhold = etf[etf["parameter_grid_role"].eq("buyhold")].iloc[0]
        best = etf[etf["parameter_grid_role"].eq("surface")].sort_values(
            ["sharpe_daily_mean", "annualized_return_cagr"], ascending=False
        ).iloc[0]
        rows.append(
            {
                "etf_code": spec.etf_code,
                "sample_scope": spec.sample_scope,
                "buyhold_sharpe": buyhold["sharpe_daily_mean"],
                "buyhold_cagr": buyhold["annualized_return_cagr"],
                "best_point": f"{best['moneyness_label']} {best['coverage_label']}",
                "best_sharpe": best["sharpe_daily_mean"],
                "best_cagr": best["annualized_return_cagr"],
                "best_mdd": best["max_drawdown"],
                "best_option_leg": best["option_leg_annualized_pnl_contribution"],
                "read": best["recommendation_read"],
            }
        )
    return pd.DataFrame(rows)


def build_etf_report_section(
    spec: EtfSpec,
    summary: pd.DataFrame,
    diagnostics: pd.DataFrame,
    figures: pd.DataFrame,
) -> str:
    etf = summary[summary["etf_code"].eq(spec.etf_code)].copy()
    buyhold = etf[etf["parameter_grid_role"].eq("buyhold")].iloc[0]
    surface = etf[etf["parameter_grid_role"].eq("surface")].copy()
    best_sharpe = surface.sort_values(["sharpe_daily_mean", "annualized_return_cagr"], ascending=False).head(5)
    best_option = surface.sort_values(["option_leg_annualized_pnl_contribution", "sharpe_daily_mean"], ascending=False).head(5)
    by_moneyness = (
        surface.sort_values(["moneyness_label", "sharpe_daily_mean"], ascending=[True, False])
        .groupby("moneyness_label", as_index=False)
        .head(1)
        .sort_values("target_moneyness")
    )
    diag = diagnostics[diagnostics["etf_code"].eq(spec.etf_code)].copy()
    fig = figures[figures["etf_code"].eq(spec.etf_code)].copy()

    lines: list[str] = []
    lines.append(f"## {spec.etf_code}")
    lines.append("")
    lines.append(spec.role_note)
    lines.append("")
    lines.append(
        f"- 样本: {buyhold['sample_start']} 至 {buyhold['sample_end']}；范围: {spec.sample_scope}。"
    )
    lines.append(
        f"- BuyHold: Sharpe {fmt_num(buyhold['sharpe_daily_mean'])}，CAGR {fmt_pct(buyhold['annualized_return_cagr'])}，MDD {fmt_pct(buyhold['max_drawdown'])}。"
    )
    top = best_sharpe.iloc[0]
    lines.append(
        f"- Sharpe 最高点: {top['moneyness_label']} {top['coverage_label']}，Sharpe {fmt_num(top['sharpe_daily_mean'])}，CAGR {fmt_pct(top['annualized_return_cagr'])}，MDD {fmt_pct(top['max_drawdown'])}，期权腿 {fmt_pct(top['option_leg_annualized_pnl_contribution'])}。"
    )
    lines.append(f"- 读取: {top['recommendation_read']}；期权腿判断: {top['option_leg_verdict']}。")
    lines.append("")
    lines.append("### Sharpe 前五")
    lines.append("")
    lines.append(
        md_table(
            best_sharpe[
                [
                    "moneyness_label",
                    "coverage_label",
                    "sharpe_daily_mean",
                    "annualized_return_cagr",
                    "max_drawdown",
                    "option_leg_annualized_pnl_contribution",
                    "avg_realized_moneyness",
                    "recommendation_read",
                ]
            ],
            pct_cols=[
                "annualized_return_cagr",
                "max_drawdown",
                "option_leg_annualized_pnl_contribution",
                "avg_realized_moneyness",
            ],
            num_cols=["sharpe_daily_mean"],
        )
    )
    lines.append("")
    lines.append("### 各 moneyness 的最优覆盖率")
    lines.append("")
    lines.append(
        md_table(
            by_moneyness[
                [
                    "moneyness_label",
                    "coverage_label",
                    "sharpe_daily_mean",
                    "annualized_return_cagr",
                    "max_drawdown",
                    "option_leg_annualized_pnl_contribution",
                    "avg_realized_moneyness",
                ]
            ],
            pct_cols=[
                "annualized_return_cagr",
                "max_drawdown",
                "option_leg_annualized_pnl_contribution",
                "avg_realized_moneyness",
            ],
            num_cols=["sharpe_daily_mean"],
        )
    )
    lines.append("")
    lines.append("### 期权腿前五")
    lines.append("")
    lines.append(
        md_table(
            best_option[
                [
                    "moneyness_label",
                    "coverage_label",
                    "option_leg_annualized_pnl_contribution",
                    "premium_capture_ratio_agg",
                    "payoff_burden_agg",
                    "positive_option_leg_period_rate",
                    "assignment_rate",
                    "sharpe_daily_mean",
                ]
            ],
            pct_cols=[
                "option_leg_annualized_pnl_contribution",
                "premium_capture_ratio_agg",
                "payoff_burden_agg",
                "positive_option_leg_period_rate",
                "assignment_rate",
            ],
            num_cols=["sharpe_daily_mean"],
        )
    )
    lines.append("")
    lines.append("### 选券审计")
    lines.append("")
    lines.append(md_table(diag[["check_name", "value", "passed", "note"]]))
    lines.append("")
    lines.append("### 图表")
    lines.append("")
    for _, row in fig.iterrows():
        lines.append(f"- {row['figure_type']}: `{row['path']}`")
    lines.append("")
    return "\n".join(lines)


def write_manifest(
    summary: pd.DataFrame,
    daily: pd.DataFrame,
    period: pd.DataFrame,
    diagnostics: pd.DataFrame,
    figures: pd.DataFrame,
    sanity: pd.DataFrame,
    option_path: Path,
) -> None:
    manifest = {
        "experiment_id": "ver3_0_stepA_moneyness_refined_daily_mtm_surface",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "complete",
        "source_engine": "ver2_downside_protection.strategy_engine.run_ver2_backtest",
        "execution_mode": "continuous_30d_daily_mtm",
        "deprecated_path_not_used": "scripts/build_adhoc_moneyness_surface_refinement_5etf.py",
        "option_source": rel_path(option_path),
        "sample_end": END_DATE.date().isoformat(),
        "moneyness_grid": [m.label for m in MONEYNESS_GRID],
        "coverage_grid": [f"Q{int(x * 100)}" for x in COVERAGE_GRID],
        "output_files": {
            "master_report": rel_path(REPORT_DIR / MASTER_REPORT_NAME),
            "surface_grid": rel_path(SUMMARY_DIR / f"{FILE_PREFIX}_surface_grid.csv"),
            "buyhold_baseline": rel_path(SUMMARY_DIR / f"{FILE_PREFIX}_buyhold_baseline.csv"),
            "daily_paths": rel_path(DAILY_DIR / f"{FILE_PREFIX}_daily_paths.csv"),
            "period_paths": rel_path(PERIOD_DIR / f"{FILE_PREFIX}_period_paths.csv"),
            "run_diagnostics": rel_path(AUDIT_DIR / f"{FILE_PREFIX}_run_diagnostics.csv"),
            "sanity_checks": rel_path(AUDIT_DIR / f"{FILE_PREFIX}_sanity_checks.csv"),
            "figures": rel_path(FIGURE_DIR),
        },
        "row_counts": {
            "summary": int(len(summary)),
            "surface": int(summary["parameter_grid_role"].eq("surface").sum()),
            "daily": int(len(daily)),
            "period": int(len(period)),
            "diagnostics": int(len(diagnostics)),
            "figures": int(len(figures)),
        },
        "sanity": {
            "passed": int(sanity["passed"].sum()),
            "total": int(len(sanity)),
        },
    }
    (OUT_ROOT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def write_readme(summary: pd.DataFrame, sanity: pd.DataFrame) -> None:
    readme = [
        "# ver3.0 Step A moneyness refined daily-MTM surface",
        "",
        "This output replaces the interrupted moneyness-surface task with the current ver3 daily-MTM semantics.",
        "",
        "- Source engine: `ver2_downside_protection.strategy_engine.run_ver2_backtest`",
        "- Execution mode: `continuous_30d_daily_mtm`",
        "- Not used: `scripts/build_adhoc_moneyness_surface_refinement_5etf.py` monthly custom backtest",
        f"- Surface rows: {int(summary['parameter_grid_role'].eq('surface').sum())}",
        f"- Sanity checks: {int(sanity['passed'].sum())}/{len(sanity)} passed",
        "",
        "Main report:",
        f"- `reports/{MASTER_REPORT_NAME}`",
    ]
    (OUT_ROOT / "README.md").write_text("\n".join(readme), encoding="utf-8")


def make_surface_ids(summary: pd.DataFrame) -> list[str]:
    ids: list[str] = []
    counter = 1
    for _, row in summary.iterrows():
        if row["parameter_grid_role"] == "buyhold":
            ids.append(f"{row['etf_code']}_buyhold")
        else:
            ids.append(f"mny_daily_{counter:04d}")
            counter += 1
    return ids


def numeric(values: Any) -> pd.Series:
    if isinstance(values, pd.Series):
        return pd.to_numeric(values, errors="coerce").fillna(0.0)
    if isinstance(values, np.ndarray):
        return pd.Series(values).astype(float)
    return pd.Series(values).astype(float)


def safe_div(numerator: float, denominator: float) -> float:
    if denominator is None or pd.isna(denominator) or abs(float(denominator)) < 1e-12:
        return np.nan
    return float(numerator) / float(denominator)


def date_iso(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return pd.Timestamp(value).date().isoformat()


def rel_path(path: Path | str) -> str:
    p = Path(path)
    try:
        return str(p.resolve().relative_to(ROOT)).replace("\\", "/")
    except Exception:
        return str(p).replace("\\", "/")


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
    return d.to_markdown(index=False) if not d.empty else "_empty_"


def setup_plot_style() -> None:
    plt.rcParams.update(
        {
            "font.size": 9,
            "axes.titlesize": 12,
            "axes.labelsize": 10,
            "legend.fontsize": 8,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": "#666666",
            "grid.color": "#CFCFCF",
        }
    )


if __name__ == "__main__":
    main()
