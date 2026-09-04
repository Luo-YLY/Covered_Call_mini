from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
VER3_SRC = ROOT / "ver3" / "src"
for path in (ROOT, VER3_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from src.metrics.ver2_metric_standard import summarize_daily_nav  # noqa: E402
from ver2_downside_protection.config import StrategyConfig, load_config  # noqa: E402
from ver2_downside_protection.strategy_engine import Ver2BacktestResult, run_ver2_backtest  # noqa: E402


EXPERIMENT_ID = "ver3_1_effective_zone_target_delta"
CONFIG_PATH = ROOT / "configs" / "ver2_downside_protection.yaml"
DELTA_OPTION_PATH = ROOT / "data" / "source" / "delta_enriched_options.csv"

MONEYNESS_ROOT = ROOT / "outputs" / "ver3_0_stepA_moneyness_refined_daily_mtm_surface"
MONEYNESS_SUMMARY = MONEYNESS_ROOT / "summary" / "ver3_0_stepA_moneyness_refined_daily_mtm_surface_grid.csv"
MONEYNESS_DAILY = MONEYNESS_ROOT / "daily" / "ver3_0_stepA_moneyness_refined_daily_mtm_daily_paths.csv"

OUT_ROOT = ROOT / "outputs" / EXPERIMENT_ID
SUMMARY_DIR = OUT_ROOT / "summary"
PERIOD_DIR = OUT_ROOT / "period"
DAILY_DIR = OUT_ROOT / "daily"
PORTFOLIO_DIR = OUT_ROOT / "portfolio"
DYNAMIC_DIR = OUT_ROOT / "dynamic"
REPORT_DIR = OUT_ROOT / "reports"
AUDIT_DIR = OUT_ROOT / "audit"

MAIN_START = pd.Timestamp("2022-09-30")
SHORT_START_588000 = pd.Timestamp("2023-06-05")
END_DATE = pd.Timestamp("2026-05-27")
TARGET_DTE = 30
MIN_DTE = 20
MAX_DTE = 45
TRADING_DAYS_PER_YEAR = 252.0

DELTA_GRID: tuple[float, ...] = (0.10, 0.20, 0.30, 0.40, 0.50)
COVERAGE_GRID: tuple[float, ...] = tuple(round(x / 10, 1) for x in range(1, 11))
MAX_ASSIGNMENT_RATE = 0.50
D_STAR_LIST: tuple[float, ...] = (0.18, 0.20, 0.22, 0.25)
WEIGHT_GRID_STEP = 0.01
WEIGHT_LOWER_BOUND = 0.05
WEIGHT_UPPER_BOUND = 0.70
SUPPORTED_LOOKBACKS: tuple[int, ...] = (126, 252)
SUPPORTED_METHODS: tuple[str, ...] = ("anchored_inverse_vol", "pure_inverse_vol", "rolling_min_variance")


@dataclass(frozen=True)
class EtfSpec:
    etf_code: str
    sample_start: pd.Timestamp
    sample_end: pd.Timestamp
    sample_scope: str
    role_note: str


@dataclass(frozen=True)
class DeltaSpec:
    label: str
    target_delta: float

    @property
    def strategy_name(self) -> str:
        return f"{self.label}_100"


@dataclass(frozen=True)
class PortfolioSpec:
    portfolio_name: str
    universe_short: str
    sleeves_by_etf: dict[str, str]
    weights: dict[str, float]
    portfolio_type: str


ETF_SPECS: tuple[EtfSpec, ...] = (
    EtfSpec("510300", MAIN_START, END_DATE, "main_stepA_common_sample", "大盘核心资产；target-delta 执行规则候选。"),
    EtfSpec("510050", MAIN_START, END_DATE, "main_stepA_common_sample", "大盘防御补充；target-delta 执行规则候选。"),
    EtfSpec("510500", MAIN_START, END_DATE, "main_stepA_common_sample", "中盘弹性资产；优先检验是否只适合裸持或轻覆盖。"),
    EtfSpec("159915", MAIN_START, END_DATE, "main_stepA_common_sample", "成长弹性资产；统一纳入 target-delta 轻覆盖候选。"),
    EtfSpec("588000", SHORT_START_588000, END_DATE, "short_sample_extension", "科创成长扩展样本；仅作短样本观察。"),
)

DELTA_SPECS: tuple[DeltaSpec, ...] = tuple(
    DeltaSpec(f"D{int(round(delta * 100)):02d}", delta) for delta in DELTA_GRID
)


def main() -> None:
    args = parse_args()
    ensure_dirs()
    verify_inputs()

    print("loading supporting moneyness surface...")
    moneyness_summary = load_moneyness_summary()
    selection_policy = build_selection_policy()

    print("running target-delta daily-MTM grid...")
    target_daily, target_period, target_summary = run_target_delta_grid(args.rf)
    target_summary = add_target_delta_selection_context(target_summary, selection_policy)

    print("selecting new sleeve candidates...")
    candidate_pool, portfolio_selection = build_candidate_pool(
        moneyness_summary=moneyness_summary,
        target_summary=target_summary,
        selection_policy=selection_policy,
    )

    print("building portfolio layer outputs...")
    selected_daily = build_selected_daily_panel(target_daily, portfolio_selection)
    fixed_portfolios, fixed_summary = run_fixed_weight_portfolios(selected_daily, portfolio_selection, args.rf)
    frontier_grid, frontier_best = run_mdd_frontier(selected_daily, portfolio_selection, args.rf)

    print("running dynamic weighting layer...")
    dynamic_daily, dynamic_weights, dynamic_summary, dynamic_comparison = run_dynamic_weighting(
        selected_daily=selected_daily,
        portfolio_selection=portfolio_selection,
        frontier_best=frontier_best,
        rf=args.rf,
    )

    sanity = build_sanity_checks(
        selection_policy=selection_policy,
        target_daily=target_daily,
        target_period=target_period,
        target_summary=target_summary,
        candidate_pool=candidate_pool,
        fixed_summary=fixed_summary,
        frontier_best=frontier_best,
        dynamic_summary=dynamic_summary,
    )

    write_outputs(
        selection_policy=selection_policy,
        target_daily=target_daily,
        target_period=target_period,
        target_summary=target_summary,
        candidate_pool=candidate_pool,
        portfolio_selection=portfolio_selection,
        selected_daily=selected_daily,
        fixed_portfolios=fixed_portfolios,
        fixed_summary=fixed_summary,
        frontier_grid=frontier_grid,
        frontier_best=frontier_best,
        dynamic_daily=dynamic_daily,
        dynamic_weights=dynamic_weights,
        dynamic_summary=dynamic_summary,
        dynamic_comparison=dynamic_comparison,
        sanity=sanity,
    )
    write_report(
        selection_policy=selection_policy,
        target_summary=target_summary,
        candidate_pool=candidate_pool,
        portfolio_selection=portfolio_selection,
        fixed_summary=fixed_summary,
        frontier_best=frontier_best,
        dynamic_summary=dynamic_summary,
        dynamic_comparison=dynamic_comparison,
        sanity=sanity,
    )
    write_manifest(sanity)

    print(f"wrote outputs: {OUT_ROOT}")
    print(f"sanity checks: {int(sanity['passed'].sum())}/{len(sanity)} passed")
    print(portfolio_selection[["etf_code", "selected_sleeve_name", "selector_type", "portfolio_use"]].to_string(index=False))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run ver3.1 target-delta x coverage experiment without overwriting ver3.0 outputs."
    )
    parser.add_argument("--rf", type=float, default=0.0, help="Annual risk-free rate for daily Sharpe.")
    return parser.parse_args()


def ensure_dirs() -> None:
    for path in (SUMMARY_DIR, PERIOD_DIR, DAILY_DIR, PORTFOLIO_DIR, DYNAMIC_DIR, REPORT_DIR, AUDIT_DIR):
        path.mkdir(parents=True, exist_ok=True)


def verify_inputs() -> None:
    required = [CONFIG_PATH, DELTA_OPTION_PATH, MONEYNESS_SUMMARY, MONEYNESS_DAILY]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing required ver3.1 inputs:\n" + "\n".join(missing))


def load_moneyness_summary() -> pd.DataFrame:
    df = pd.read_csv(MONEYNESS_SUMMARY, dtype={"etf_code": str})
    df["etf_code"] = df["etf_code"].astype(str).str.zfill(6)
    return df


def build_selection_policy() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    full_grid = ";".join(delta.label for delta in DELTA_SPECS)
    coverage_grid = ";".join(coverage_label_from_float(x) for x in COVERAGE_GRID)
    for spec in ETF_SPECS:
        is_core_target_delta = spec.etf_code in {"510300", "510050", "159915"}
        if is_core_target_delta:
            target_delta_scope = "core_target_delta_candidate"
            selection_policy = "full_target_delta_surface"
            portfolio_role = "portfolio_candidate"
            selection_note = "Select directly from the full target-delta x coverage grid with economic filters."
        elif spec.etf_code == "510500":
            target_delta_scope = "buyhold_preferred"
            selection_policy = "buyhold_after_surface_check"
            portfolio_role = "portfolio_candidate"
            selection_note = "Keep BuyHold because covered-call sleeves remain diagnostic rather than mainline."
        else:
            target_delta_scope = "short_sample_baseline"
            selection_policy = "extension_or_baseline"
            portfolio_role = "extension_or_baseline"
            selection_note = "Keep as short-sample extension or baseline only."
        rows.append(
            {
                "etf_code": spec.etf_code,
                "sample_scope": spec.sample_scope,
                "target_delta_scope": target_delta_scope,
                "selection_policy": selection_policy,
                "portfolio_role": portfolio_role,
                "eligible_delta_grid": full_grid if is_core_target_delta else "",
                "eligible_coverage_grid": coverage_grid if is_core_target_delta else "",
                "selection_note": selection_note,
                "role_note": spec.role_note,
            }
        )
    return pd.DataFrame(rows)


def run_target_delta_grid(rf: float) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    all_daily: list[pd.DataFrame] = []
    all_period: list[pd.DataFrame] = []
    all_summary: list[pd.DataFrame] = []
    for spec in ETF_SPECS:
        print(f"  target-delta grid: {spec.etf_code}")
        result = run_target_delta_source_backtest(spec)
        source_daily = canonical_source_daily(result.daily_mtm)
        common_dates = build_common_dates(source_daily, spec)
        daily = build_target_daily_surface(spec, source_daily, common_dates)
        period = build_target_period_surface(spec, result.periods, result.daily_mtm)
        summary = build_target_summary(spec, daily, period, rf)
        all_daily.append(daily)
        all_period.append(period)
        all_summary.append(summary)

    daily_df = pd.concat(all_daily, ignore_index=True).sort_values(["etf_code", "sleeve_name", "date"])
    period_df = pd.concat(all_period, ignore_index=True).sort_values(["etf_code", "sleeve_name", "rebalance_date"])
    summary_df = pd.concat(all_summary, ignore_index=True).sort_values(["etf_code", "parameter_grid_role", "target_delta", "coverage"])
    summary_df = add_buyhold_relative_metrics(summary_df)
    return daily_df.reset_index(drop=True), period_df.reset_index(drop=True), summary_df.reset_index(drop=True)


def run_target_delta_source_backtest(spec: EtfSpec) -> Ver2BacktestResult:
    config = load_config(CONFIG_PATH, ROOT)
    strategies = [StrategyConfig("BuyHold", "buy_hold", 0.0, 0.0, True)]
    strategies.extend(
        StrategyConfig(delta.strategy_name, "target_delta", 1.0, delta.target_delta, True)
        for delta in DELTA_SPECS
    )
    config = replace(
        config,
        etf_codes=(spec.etf_code,),
        paths=replace(config.paths, options=DELTA_OPTION_PATH, output_dir=OUT_ROOT),
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
    for strategy_name, group in daily_mtm.groupby("strategy_name"):
        sort_cols = [col for col in ["date", "period_index"] if col in group.columns]
        g = group.sort_values(sort_cols).drop_duplicates("date", keep="last").copy()
        g["date"] = pd.to_datetime(g["date"], errors="coerce")
        out[str(strategy_name)] = g.set_index("date").sort_index()
    return out


def build_common_dates(source_daily: dict[str, pd.DataFrame], spec: EtfSpec) -> pd.DatetimeIndex:
    required = ["BuyHold"] + [delta.strategy_name for delta in DELTA_SPECS]
    missing = [name for name in required if name not in source_daily]
    if missing:
        raise ValueError(f"{spec.etf_code} missing target-delta source strategies: {missing}")
    common_dates = source_daily["BuyHold"].index
    for name in required[1:]:
        common_dates = common_dates.intersection(source_daily[name].index)
    common_dates = common_dates[(common_dates >= spec.sample_start) & (common_dates <= spec.sample_end)]
    if common_dates.empty:
        raise ValueError(f"{spec.etf_code} has no common target-delta daily MTM dates.")
    return pd.DatetimeIndex(common_dates).sort_values()


def build_target_daily_surface(
    spec: EtfSpec,
    source_daily: dict[str, pd.DataFrame],
    common_dates: pd.DatetimeIndex,
) -> pd.DataFrame:
    buyhold = source_daily["BuyHold"].loc[common_dates].copy()
    buyhold_nav = buyhold["daily_mtm_nav"].astype(float)
    underlying_return = buyhold_nav.pct_change().fillna(0.0)
    underlying_return.iloc[0] = 0.0

    frames: list[pd.DataFrame] = [
        pd.DataFrame(
            {
                "date": common_dates,
                "etf_code": spec.etf_code,
                "sleeve_name": f"{spec.etf_code}_ETF_BuyHold",
                "parameter_grid_role": "buyhold",
                "sample_scope": spec.sample_scope,
                "delta_label": "BuyHold",
                "target_delta": np.nan,
                "coverage": 0.0,
                "coverage_label": "Q0",
                "dte_label": "NA",
                "nav_total": (1.0 + underlying_return).cumprod().values,
                "daily_return_total": underlying_return.values,
                "daily_return_underlying_component": underlying_return.values,
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
            }
        )
    ]

    for delta in DELTA_SPECS:
        src = source_daily[delta.strategy_name].loc[common_dates].copy()
        q100_return = src["daily_mtm_nav"].astype(float).pct_change().fillna(0.0)
        q100_return.iloc[0] = 0.0
        option_return_q100 = q100_return - underlying_return
        active = src["position_state"].astype(str).eq("short_call")
        for coverage in COVERAGE_GRID:
            coverage_label = coverage_label_from_float(coverage)
            sleeve_name = f"{spec.etf_code}_DTE30_{delta.label}_{coverage_label}_Hold"
            option_return = option_return_q100 * coverage
            total_return = underlying_return + option_return
            total_return.iloc[0] = 0.0
            option_return.iloc[0] = 0.0
            frames.append(
                pd.DataFrame(
                    {
                        "date": common_dates,
                        "etf_code": spec.etf_code,
                        "sleeve_name": sleeve_name,
                        "parameter_grid_role": "target_delta_surface",
                        "sample_scope": spec.sample_scope,
                        "delta_label": delta.label,
                        "target_delta": delta.target_delta,
                        "coverage": coverage,
                        "coverage_label": coverage_label,
                        "dte_label": "DTE30",
                        "nav_total": (1.0 + total_return).cumprod().values,
                        "daily_return_total": total_return.values,
                        "daily_return_underlying_component": underlying_return.values,
                        "daily_return_option_leg_component": option_return.values,
                        "option_leg_pnl": option_return.values,
                        "short_call_liability": numeric(src.get("option_liability_return", 0.0)).values * coverage,
                        "short_call_mtm_loss": numeric(src.get("short_call_mtm_loss_return", 0.0)).values * coverage,
                        "active_short_call_flag": active.values,
                        "active_coverage": np.where(active.values, coverage, 0.0),
                        "source_strategy_name": delta.strategy_name,
                        "option_code": src.get("option_code", np.nan).values,
                        "strike": src.get("strike", np.nan).values,
                        "rebalance_date": src.get("rebalance_date", pd.NaT).values,
                        "expiry_date": src.get("expiry_date", pd.NaT).values,
                        "period_index": src.get("period_index", np.nan).values,
                    }
                )
            )
    return pd.concat(frames, ignore_index=True).sort_values(["etf_code", "sleeve_name", "date"]).reset_index(drop=True)


def build_target_period_surface(
    spec: EtfSpec,
    source_period: pd.DataFrame,
    raw_source_daily: pd.DataFrame,
) -> pd.DataFrame:
    stress_lookup = build_period_stress_lookup(raw_source_daily)
    p = source_period.copy()
    p["rebalance_date"] = pd.to_datetime(p["rebalance_date"], errors="coerce")
    rows: list[dict[str, Any]] = []
    for delta in DELTA_SPECS:
        source = p[p["strategy_name"].eq(delta.strategy_name)].copy()
        source = source[(source["rebalance_date"] >= spec.sample_start) & (source["rebalance_date"] <= spec.sample_end)]
        for coverage in COVERAGE_GRID:
            coverage_label = coverage_label_from_float(coverage)
            sleeve_name = f"{spec.etf_code}_DTE30_{delta.label}_{coverage_label}_Hold"
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
                        "source_strategy_name": delta.strategy_name,
                        "delta_label": delta.label,
                        "target_delta": delta.target_delta,
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
                        "selected_iv": row.get("selected_iv", np.nan),
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
    strategy_names = [delta.strategy_name for delta in DELTA_SPECS]
    d = source_daily[source_daily["strategy_name"].isin(strategy_names)].copy()
    if d.empty:
        return lookup
    for (strategy, period_index, option_code), group in d.groupby(["strategy_name", "period_index", "option_code"], dropna=False):
        stress = numeric(group.get("short_call_mtm_loss_return", 0.0))
        lookup[(str(strategy), int(period_index), str(option_code))] = {
            "max": float(stress.max()),
            "p95": float(stress.quantile(0.95)),
            "p99": float(stress.quantile(0.99)),
        }
    return lookup


def build_target_summary(spec: EtfSpec, daily: pd.DataFrame, period: pd.DataFrame, rf: float) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for sleeve_name, group in daily.groupby("sleeve_name"):
        sample = group.sort_values("date").copy()
        p = period[period["sleeve_name"].eq(sleeve_name)].copy()
        metrics = summarize_daily_nav(sample[["date", "nav_total"]], date_col="date", nav_col="nav_total", rf=rf)
        first = sample.iloc[0]
        rows.append(
            {
                "etf_code": spec.etf_code,
                "sleeve_name": sleeve_name,
                "parameter_grid_role": first["parameter_grid_role"],
                "sample_scope": spec.sample_scope,
                "sample_start": pd.to_datetime(sample["date"]).min().date().isoformat(),
                "sample_end": pd.to_datetime(sample["date"]).max().date().isoformat(),
                "n_trading_days": int(len(sample)),
                "delta_label": first["delta_label"],
                "target_delta": first["target_delta"],
                "coverage": first["coverage"],
                "coverage_label": first["coverage_label"],
                **metrics,
                **summarize_option_metrics(sample, p),
                "source_engine": "continuous_30d_daily_mtm_target_delta",
            }
        )
    return pd.DataFrame(rows)


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
            "avg_selected_delta": np.nan,
            "median_selected_delta": np.nan,
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
        "option_leg_annualized_pnl_contribution": float(option_pnl.sum() * TRADING_DAYS_PER_YEAR / max(len(sample), 1)),
        "premium_capture_ratio_agg": safe_div(option_leg.sum(), premium.sum()),
        "payoff_burden_agg": safe_div(payoff.sum(), premium.sum()),
        "positive_option_leg_period_rate": float((option_leg > 0).mean()) if len(option_leg) else np.nan,
        "assignment_rate": float(selected["assignment_flag"].astype(bool).mean()) if not selected.empty else np.nan,
        "p95_short_call_mtm_loss": float(stress.quantile(0.95)),
        "p99_short_call_mtm_loss": float(stress.quantile(0.99)),
        "max_short_call_mtm_loss": float(stress.max()),
        "avg_actual_dte": numeric(selected.get("actual_dte", pd.Series(dtype=float))).mean() if not selected.empty else np.nan,
        "avg_selected_delta": numeric(selected.get("selected_delta", pd.Series(dtype=float))).mean() if not selected.empty else np.nan,
        "median_selected_delta": numeric(selected.get("selected_delta", pd.Series(dtype=float))).median() if not selected.empty else np.nan,
        "avg_realized_moneyness": numeric(selected.get("realized_moneyness", pd.Series(dtype=float))).mean() if not selected.empty else np.nan,
        "median_realized_moneyness": numeric(selected.get("realized_moneyness", pd.Series(dtype=float))).median() if not selected.empty else np.nan,
        "selected_periods": int(selected["option_selected_flag"].sum()) if "option_selected_flag" in selected else 0,
        "skipped_periods": int((period["option_selected_flag"].astype(int) == 0).sum()),
        "avg_active_coverage": float(sample["active_coverage"].astype(float).mean()),
    }


def add_buyhold_relative_metrics(summary: pd.DataFrame) -> pd.DataFrame:
    out = summary.copy()
    out["annualized_return_cagr_vs_buyhold"] = np.nan
    out["sharpe_diff_vs_buyhold"] = np.nan
    out["mdd_improvement_vs_buyhold"] = np.nan
    for etf_code, group in out.groupby("etf_code"):
        buyhold = group[group["parameter_grid_role"].eq("buyhold")]
        if buyhold.empty:
            continue
        b = buyhold.iloc[0]
        idx = out["etf_code"].eq(etf_code)
        out.loc[idx, "annualized_return_cagr_vs_buyhold"] = out.loc[idx, "annualized_return_cagr"] - b["annualized_return_cagr"]
        out.loc[idx, "sharpe_diff_vs_buyhold"] = out.loc[idx, "sharpe_daily_mean"] - b["sharpe_daily_mean"]
        out.loc[idx, "mdd_improvement_vs_buyhold"] = b["max_drawdown"] - out.loc[idx, "max_drawdown"]
    return out


def add_target_delta_selection_context(summary: pd.DataFrame, selection_policy: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "etf_code",
        "target_delta_scope",
        "selection_policy",
        "portfolio_role",
        "eligible_delta_grid",
        "eligible_coverage_grid",
    ]
    out = summary.merge(selection_policy[cols], on="etf_code", how="left")
    out["eligible_target_delta_surface"] = out["parameter_grid_role"].eq("target_delta_surface") & out[
        "target_delta_scope"
    ].eq("core_target_delta_candidate")
    return out


def build_candidate_pool(
    *,
    moneyness_summary: pd.DataFrame,
    target_summary: pd.DataFrame,
    selection_policy: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    portfolio_rows: list[dict[str, Any]] = []
    surface = moneyness_summary[moneyness_summary["parameter_grid_role"].eq("surface")].copy()
    buyholds = moneyness_summary[moneyness_summary["parameter_grid_role"].eq("buyhold")].copy()

    for spec in ETF_SPECS:
        policy = selection_policy[selection_policy["etf_code"].eq(spec.etf_code)].iloc[0].to_dict()
        target_candidate = select_best_target_candidate(target_summary, spec.etf_code, policy)
        fixed_candidate = select_best_fixed_candidate(surface, spec.etf_code)
        buyhold = buyholds[buyholds["etf_code"].eq(spec.etf_code)].iloc[0].to_dict()

        for candidate_type, candidate in [
            ("target_delta_candidate", target_candidate),
            ("fixed_moneyness_candidate", fixed_candidate),
            ("buyhold_baseline", buyhold),
        ]:
            if candidate:
                rows.append(candidate_row(spec.etf_code, candidate_type, candidate, policy))

        selected = portfolio_candidate(spec.etf_code, target_candidate, fixed_candidate, buyhold, policy)
        portfolio_rows.append(
            {
                "etf_code": spec.etf_code,
                "selected_sleeve_name": selected["sleeve_name"],
                "selector_type": selected["selector_type"],
                "selection_reason": selected["selection_reason"],
                "portfolio_use": selected["portfolio_use"],
                "target_delta_scope": policy.get("target_delta_scope", ""),
                "selection_policy": policy.get("selection_policy", ""),
            }
        )

    return pd.DataFrame(rows), pd.DataFrame(portfolio_rows)


def select_best_target_candidate(target_summary: pd.DataFrame, etf_code: str, decision: dict[str, Any]) -> dict[str, Any]:
    scope = str(decision.get("target_delta_scope", ""))
    if scope != "core_target_delta_candidate":
        return {}
    rows = target_summary[
        target_summary["etf_code"].eq(etf_code)
        & target_summary["parameter_grid_role"].eq("target_delta_surface")
    ].copy()
    strict = rows[
        rows["coverage"].astype(float).le(0.70)
        & rows["sharpe_diff_vs_buyhold"].astype(float).ge(0.0)
        & rows["mdd_improvement_vs_buyhold"].astype(float).ge(0.0)
        & rows["option_leg_annualized_pnl_contribution"].astype(float).ge(0.0)
        & rows["assignment_rate"].astype(float).le(MAX_ASSIGNMENT_RATE)
    ].copy()
    if strict.empty:
        strict = rows[
            rows["coverage"].astype(float).le(0.70)
            & rows["sharpe_diff_vs_buyhold"].astype(float).ge(0.0)
            & rows["mdd_improvement_vs_buyhold"].astype(float).ge(0.0)
        ].copy()
    if strict.empty:
        strict = rows.copy()
    if strict.empty:
        return {}
    return strict.sort_values(
        ["sharpe_daily_mean", "annualized_return_cagr", "mdd_improvement_vs_buyhold"],
        ascending=[False, False, False],
    ).iloc[0].to_dict()


def select_best_fixed_candidate(surface: pd.DataFrame, etf_code: str) -> dict[str, Any]:
    rows = surface[surface["etf_code"].eq(etf_code)].copy()
    if rows.empty:
        return {}
    for col in [
        "sharpe_diff_vs_buyhold",
        "mdd_improvement_vs_buyhold",
        "option_leg_annualized_pnl_contribution",
        "coverage",
        "assignment_rate",
    ]:
        rows[col] = pd.to_numeric(rows[col], errors="coerce")
    defensive = rows[
        rows["mdd_improvement_vs_buyhold"].ge(0.0)
        & rows["sharpe_diff_vs_buyhold"].ge(-0.02)
        & rows["option_leg_annualized_pnl_contribution"].ge(-0.02)
        & rows["coverage"].le(0.50)
        & rows["assignment_rate"].le(MAX_ASSIGNMENT_RATE)
    ].copy()
    if defensive.empty:
        defensive = rows.sort_values(["sharpe_daily_mean", "annualized_return_cagr"], ascending=False).head(10)
    return defensive.sort_values(
        ["sharpe_daily_mean", "annualized_return_cagr", "mdd_improvement_vs_buyhold"],
        ascending=[False, False, False],
    ).iloc[0].to_dict()


def portfolio_candidate(
    etf_code: str,
    target_candidate: dict[str, Any],
    fixed_candidate: dict[str, Any],
    buyhold: dict[str, Any],
    decision: dict[str, Any],
) -> dict[str, str]:
    if etf_code in {"510300", "510050", "159915"} and target_candidate:
        return {
            "sleeve_name": str(target_candidate["sleeve_name"]),
            "selector_type": "target_delta",
            "selection_reason": "ETF selected directly from the full target-delta x coverage grid after economic filters",
            "portfolio_use": "portfolio_candidate",
        }
    if etf_code == "510500":
        return {
            "sleeve_name": str(buyhold["sleeve_name"]),
            "selector_type": "buyhold",
            "selection_reason": "mid-cap ETF keeps BuyHold because covered-call surface only shows weak defensive benefit",
            "portfolio_use": "portfolio_candidate",
        }
    return {
        "sleeve_name": str(buyhold["sleeve_name"]),
        "selector_type": "buyhold",
        "selection_reason": "not in main portfolio universe or short-sample extension only",
        "portfolio_use": "extension_or_baseline",
    }


def candidate_row(etf_code: str, candidate_type: str, candidate: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    fields = [
        "sleeve_name",
        "parameter_grid_role",
        "sample_scope",
        "annualized_return_cagr",
        "sharpe_daily_mean",
        "max_drawdown",
        "annualized_volatility",
        "option_leg_annualized_pnl_contribution",
        "assignment_rate",
        "coverage",
        "coverage_label",
        "target_delta",
        "delta_label",
        "moneyness_label",
        "target_moneyness",
        "sharpe_diff_vs_buyhold",
        "mdd_improvement_vs_buyhold",
    ]
    row = {"etf_code": etf_code, "candidate_type": candidate_type}
    for field in fields:
        row[field] = candidate.get(field, np.nan)
    row["target_delta_scope"] = decision.get("target_delta_scope", "")
    row["selection_policy"] = decision.get("selection_policy", "")
    return row


def build_selected_daily_panel(target_daily: pd.DataFrame, portfolio_selection: pd.DataFrame) -> pd.DataFrame:
    needed = set(portfolio_selection["selected_sleeve_name"].astype(str))
    needed.update(f"{code}_ETF_BuyHold" for code in ["510300", "510050", "510500", "159915"])

    target = target_daily[target_daily["sleeve_name"].isin(needed)].copy()
    mny_cols = [
        "date",
        "etf_code",
        "sleeve_name",
        "daily_return_total",
        "daily_return_option_leg_component",
        "nav_total",
        "parameter_grid_role",
    ]
    mny = pd.read_csv(MONEYNESS_DAILY, usecols=mny_cols, dtype={"etf_code": str})
    mny["etf_code"] = mny["etf_code"].astype(str).str.zfill(6)
    mny = mny[mny["sleeve_name"].isin(needed)].copy()
    combined = pd.concat([target[mny_cols], mny[mny_cols]], ignore_index=True, sort=False)
    combined["date"] = pd.to_datetime(combined["date"], errors="coerce")
    combined = combined.drop_duplicates(["date", "etf_code", "sleeve_name"], keep="first")
    return combined.sort_values(["etf_code", "sleeve_name", "date"]).reset_index(drop=True)


def universe_specs_from_selection(portfolio_selection: pd.DataFrame) -> dict[str, dict[str, str]]:
    selected = portfolio_selection.set_index("etf_code")["selected_sleeve_name"].to_dict()
    return {
        "A": {
            "510300": selected["510300"],
            "510500": selected["510500"],
            "159915": selected["159915"],
        },
        "B": {
            "510300": selected["510300"],
            "510050": selected["510050"],
            "159915": selected["159915"],
        },
    }


def run_fixed_weight_portfolios(
    selected_daily: pd.DataFrame,
    portfolio_selection: pd.DataFrame,
    rf: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    universes = universe_specs_from_selection(portfolio_selection)
    specs = [
        PortfolioSpec("A_v31_70_20_10", "A", universes["A"], {"510300": 0.70, "510500": 0.20, "159915": 0.10}, "fixed_weight"),
        PortfolioSpec("A_v31_50_30_20", "A", universes["A"], {"510300": 0.50, "510500": 0.30, "159915": 0.20}, "fixed_weight"),
        PortfolioSpec("B_v31_70_20_10", "B", universes["B"], {"510300": 0.70, "510050": 0.20, "159915": 0.10}, "fixed_weight"),
        PortfolioSpec("B_v31_50_30_20", "B", universes["B"], {"510300": 0.50, "510050": 0.30, "159915": 0.20}, "fixed_weight"),
    ]
    rows: list[pd.DataFrame] = []
    summary_rows: list[dict[str, Any]] = []
    for spec in specs:
        returns = portfolio_returns_for_spec(selected_daily, spec.sleeves_by_etf, spec.weights)
        returns["portfolio_name"] = spec.portfolio_name
        returns["universe_short"] = spec.universe_short
        returns["portfolio_type"] = spec.portfolio_type
        rows.append(returns)
        summary_rows.append(portfolio_summary_row(returns, spec, rf))
    return pd.concat(rows, ignore_index=True), pd.DataFrame(summary_rows).sort_values("portfolio_name").reset_index(drop=True)


def portfolio_returns_for_spec(
    daily: pd.DataFrame,
    sleeves_by_etf: dict[str, str],
    weights: dict[str, float],
) -> pd.DataFrame:
    panel = build_return_matrices(daily, sleeves_by_etf)
    dates = panel["date"]
    ret_cols = [f"return_{etf}" for etf in sleeves_by_etf]
    opt_cols = [f"option_{etf}" for etf in sleeves_by_etf]
    w = np.array([weights[etf] for etf in sleeves_by_etf], dtype=float)
    returns = panel[ret_cols].astype(float).to_numpy() @ w
    option_returns = panel[opt_cols].astype(float).to_numpy() @ w
    nav = np.cumprod(1.0 + returns)
    out = pd.DataFrame(
        {
            "date": dates,
            "daily_return": returns,
            "option_leg_return": option_returns,
            "nav": nav,
        }
    )
    for etf in sleeves_by_etf:
        out[f"weight_{etf}"] = weights[etf]
        out[f"sleeve_{etf}"] = sleeves_by_etf[etf]
    return out


def build_return_matrices(daily: pd.DataFrame, sleeves_by_etf: dict[str, str]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    common_dates: pd.DatetimeIndex | None = None
    for etf, sleeve in sleeves_by_etf.items():
        sample = daily[(daily["etf_code"].eq(etf)) & (daily["sleeve_name"].eq(sleeve))].copy()
        if sample.empty:
            raise ValueError(f"Missing daily returns for {etf} {sleeve}")
        sample = sample.sort_values("date")
        dates = pd.DatetimeIndex(pd.to_datetime(sample["date"]))
        common_dates = dates if common_dates is None else common_dates.intersection(dates)
    assert common_dates is not None
    common_dates = common_dates.sort_values()
    out = pd.DataFrame({"date": common_dates})
    for etf, sleeve in sleeves_by_etf.items():
        sample = daily[(daily["etf_code"].eq(etf)) & (daily["sleeve_name"].eq(sleeve))].copy()
        sample["date"] = pd.to_datetime(sample["date"])
        sample = sample.set_index("date").reindex(common_dates)
        out[f"return_{etf}"] = sample["daily_return_total"].astype(float).fillna(0.0).to_numpy()
        out[f"option_{etf}"] = sample["daily_return_option_leg_component"].astype(float).fillna(0.0).to_numpy()
    return out


def portfolio_summary_row(returns: pd.DataFrame, spec: PortfolioSpec, rf: float) -> dict[str, Any]:
    metrics = summarize_daily_nav(returns[["date", "nav"]], date_col="date", nav_col="nav", rf=rf)
    row = {
        "portfolio_name": spec.portfolio_name,
        "universe_short": spec.universe_short,
        "portfolio_type": spec.portfolio_type,
        "sample_start": pd.to_datetime(returns["date"]).min().date().isoformat(),
        "sample_end": pd.to_datetime(returns["date"]).max().date().isoformat(),
        "n_trading_days": int(len(returns)),
        **metrics,
        "option_leg_annualized_pnl_contribution": float(
            returns["option_leg_return"].astype(float).sum() * TRADING_DAYS_PER_YEAR / max(len(returns), 1)
        ),
        "sleeve_set": " | ".join(f"{etf}:{sleeve}" for etf, sleeve in spec.sleeves_by_etf.items()),
    }
    for etf, weight in spec.weights.items():
        row[f"weight_{etf}"] = weight
    return row


def run_mdd_frontier(
    selected_daily: pd.DataFrame,
    portfolio_selection: pd.DataFrame,
    rf: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    universes = universe_specs_from_selection(portfolio_selection)
    grid_frames: list[pd.DataFrame] = []
    best_rows: list[dict[str, Any]] = []
    for universe_short, sleeves in universes.items():
        panel = build_return_matrices(selected_daily, sleeves)
        etfs = list(sleeves.keys())
        weights = generate_weight_grid(etfs, WEIGHT_GRID_STEP, WEIGHT_LOWER_BOUND, WEIGHT_UPPER_BOUND)
        ret = panel[[f"return_{etf}" for etf in etfs]].astype(float).to_numpy()
        opt = panel[[f"option_{etf}" for etf in etfs]].astype(float).to_numpy()
        w = weights[[f"weight_{etf}" for etf in etfs]].astype(float).to_numpy()
        port_ret = ret @ w.T
        port_opt = opt @ w.T
        metrics = fast_metric_frame(port_ret, port_opt)
        grid = pd.concat([weights.reset_index(drop=True), metrics], axis=1)
        grid.insert(0, "universe_short", universe_short)
        grid["sample_start"] = pd.to_datetime(panel["date"]).min().date().isoformat()
        grid["sample_end"] = pd.to_datetime(panel["date"]).max().date().isoformat()
        grid["n_trading_days"] = int(len(panel))
        grid["sleeve_set"] = " | ".join(f"{etf}:{sleeve}" for etf, sleeve in sleeves.items())
        grid_frames.append(grid)
        for d_star in D_STAR_LIST:
            feasible = grid[grid["max_drawdown"].astype(float).le(d_star)].copy()
            if feasible.empty:
                best_rows.append(
                    {
                        "universe_short": universe_short,
                        "D_star": d_star,
                        "frontier_status": "infeasible",
                        "feasible": False,
                        "feasible_candidate_count": 0,
                        "portfolio_name": f"{universe_short}_v31_D{int(d_star * 100):02d}_NA",
                        "sleeve_set": grid["sleeve_set"].iloc[0] if not grid.empty else "",
                    }
                )
                continue
            best = feasible.sort_values(["sharpe_daily_mean", "max_drawdown", "annualized_return_cagr"], ascending=[False, True, False]).iloc[0]
            row = best.to_dict()
            row.update(
                {
                    "universe_short": universe_short,
                    "D_star": d_star,
                    "frontier_status": "feasible",
                    "feasible": True,
                    "feasible_candidate_count": int(len(feasible)),
                    "portfolio_name": f"{universe_short}_v31_D{int(d_star * 100):02d}_{best['weight_vector_key']}",
                }
            )
            best_rows.append(row)
    return pd.concat(grid_frames, ignore_index=True), pd.DataFrame(best_rows).sort_values(["universe_short", "D_star"]).reset_index(drop=True)


def generate_weight_grid(etfs: list[str], step: float, lower: float, upper: float) -> pd.DataFrame:
    scale = int(round(1.0 / step))
    lower_i = int(np.ceil(lower * scale - 1e-10))
    upper_i = int(np.floor(upper * scale + 1e-10))
    rows: list[dict[str, float]] = []

    def recurse(prefix: list[int], remaining: int) -> None:
        idx = len(prefix)
        slots_left = len(etfs) - idx
        if slots_left == 1:
            value = remaining
            if lower_i <= value <= upper_i:
                units = [*prefix, value]
                rows.append({f"weight_{etf}": unit / scale for etf, unit in zip(etfs, units)})
            return
        min_value = max(lower_i, remaining - upper_i * (slots_left - 1))
        max_value = min(upper_i, remaining - lower_i * (slots_left - 1))
        for value in range(min_value, max_value + 1):
            recurse([*prefix, value], remaining - value)

    recurse([], scale)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["weight_sum"] = out[[f"weight_{etf}" for etf in etfs]].sum(axis=1)
    out["weight_vector_key"] = out.apply(
        lambda row: "_".join(f"{etf}{int(round(float(row[f'weight_{etf}']) * 100)):02d}" for etf in etfs),
        axis=1,
    )
    return out


def fast_metric_frame(portfolio_returns: np.ndarray, option_returns: np.ndarray) -> pd.DataFrame:
    nav = np.cumprod(1.0 + portfolio_returns, axis=0)
    metric_returns = portfolio_returns[1:, :] if portfolio_returns.shape[0] > 1 else portfolio_returns
    mean = np.nanmean(metric_returns, axis=0)
    std = np.nanstd(metric_returns, axis=0, ddof=1) if metric_returns.shape[0] > 1 else np.full(portfolio_returns.shape[1], np.nan)
    vol = std * np.sqrt(TRADING_DAYS_PER_YEAR)
    sharpe = np.divide(mean, std, out=np.full_like(mean, np.nan), where=np.isfinite(std) & (std > 0)) * np.sqrt(TRADING_DAYS_PER_YEAR)
    arithmetic = mean * TRADING_DAYS_PER_YEAR
    first_nav = nav[0, :]
    final_nav = nav[-1, :]
    cumulative = np.divide(final_nav, first_nav, out=np.full_like(final_nav, np.nan), where=first_nav > 0) - 1.0
    cagr = np.power(1.0 + cumulative, TRADING_DAYS_PER_YEAR / max(metric_returns.shape[0], 1)) - 1.0
    peaks = np.maximum.accumulate(nav, axis=0)
    drawdown = 1.0 - np.divide(nav, peaks, out=np.ones_like(nav), where=peaks > 0)
    mdd = np.nanmax(drawdown, axis=0)
    downside = np.minimum(metric_returns, 0.0)
    downside_std = np.nanstd(downside, axis=0, ddof=1) if metric_returns.shape[0] > 1 else np.full(portfolio_returns.shape[1], np.nan)
    downside_dev = downside_std * np.sqrt(TRADING_DAYS_PER_YEAR)
    sortino = np.divide(arithmetic, downside_dev, out=np.full_like(arithmetic, np.nan), where=np.isfinite(downside_dev) & (downside_dev > 0))
    return pd.DataFrame(
        {
            "annualized_return_cagr": cagr,
            "arithmetic_annualized_return": arithmetic,
            "annualized_volatility": vol,
            "sharpe_daily_mean": sharpe,
            "sortino_ratio": sortino,
            "max_drawdown": mdd,
            "calmar_ratio": np.divide(cagr, mdd, out=np.full_like(cagr, np.nan), where=np.isfinite(mdd) & (mdd > 0)),
            "final_nav": final_nav,
            "cumulative_return": cumulative,
            "option_leg_annualized_pnl_contribution": np.nansum(option_returns, axis=0) * TRADING_DAYS_PER_YEAR / max(portfolio_returns.shape[0], 1),
        }
    )


def run_dynamic_weighting(
    *,
    selected_daily: pd.DataFrame,
    portfolio_selection: pd.DataFrame,
    frontier_best: pd.DataFrame,
    rf: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    universes = universe_specs_from_selection(portfolio_selection)
    anchor_weights = dynamic_anchor_weights(frontier_best)
    daily_rows: list[pd.DataFrame] = []
    weight_rows: list[pd.DataFrame] = []
    summary_rows: list[dict[str, Any]] = []
    comparison_rows: list[dict[str, Any]] = []

    for universe_short, sleeves in universes.items():
        panel = build_return_matrices(selected_daily, sleeves)
        etfs = list(sleeves.keys())
        returns = panel[[f"return_{etf}" for etf in etfs]].astype(float).to_numpy()
        options = panel[[f"option_{etf}" for etf in etfs]].astype(float).to_numpy()
        dates = pd.to_datetime(panel["date"]).reset_index(drop=True)
        anchor = np.array([anchor_weights[universe_short].get(etf, 1.0 / len(etfs)) for etf in etfs], dtype=float)
        anchor = bounded_normalize(anchor, WEIGHT_LOWER_BOUND, WEIGHT_UPPER_BOUND)

        for lookback in SUPPORTED_LOOKBACKS:
            if len(dates) <= lookback + 5:
                continue
            for method in SUPPORTED_METHODS:
                strategy_name = f"{universe_short}_{method}_L{lookback}"
                dyn = simulate_dynamic_strategy(dates, returns, options, etfs, anchor, lookback, method)
                dyn["strategy_name"] = strategy_name
                dyn["universe_short"] = universe_short
                dyn["method"] = method
                dyn["lookback"] = lookback
                daily_rows.append(dyn)
                weight_rows.append(dynamic_weight_log(dyn, strategy_name, universe_short, method, lookback, etfs, sleeves))
                spec = PortfolioSpec(strategy_name, universe_short, sleeves, {etf: float(anchor[i]) for i, etf in enumerate(etfs)}, "dynamic_weight")
                summary = portfolio_summary_row(
                    dyn.rename(columns={"dynamic_return": "daily_return", "dynamic_option_return": "option_leg_return", "dynamic_nav": "nav"}),
                    spec,
                    rf,
                )
                summary.update({"method": method, "lookback": lookback, "sample_type": "dynamic_effective_sample"})
                summary_rows.append(summary)

                baseline = static_returns_for_dynamic_sample(dates, returns, options, etfs, anchor, dyn["date"])
                baseline_spec = PortfolioSpec(f"{universe_short}_anchor_same_sample_L{lookback}", universe_short, sleeves, {etf: float(anchor[i]) for i, etf in enumerate(etfs)}, "same_sample_static_anchor")
                base_summary = portfolio_summary_row(baseline, baseline_spec, rf)
                comparison_rows.append(
                    {
                        "strategy_name": strategy_name,
                        "universe_short": universe_short,
                        "method": method,
                        "lookback": lookback,
                        "sample_start": summary["sample_start"],
                        "sample_end": summary["sample_end"],
                        "n_trading_days": summary["n_trading_days"],
                        "dynamic_sharpe": summary["sharpe_daily_mean"],
                        "baseline_sharpe": base_summary["sharpe_daily_mean"],
                        "delta_sharpe_vs_baseline": summary["sharpe_daily_mean"] - base_summary["sharpe_daily_mean"],
                        "dynamic_cagr": summary["annualized_return_cagr"],
                        "baseline_cagr": base_summary["annualized_return_cagr"],
                        "delta_cagr_vs_baseline": summary["annualized_return_cagr"] - base_summary["annualized_return_cagr"],
                        "dynamic_mdd": summary["max_drawdown"],
                        "baseline_mdd": base_summary["max_drawdown"],
                        "delta_mdd_vs_baseline": summary["max_drawdown"] - base_summary["max_drawdown"],
                    }
                )

    return (
        pd.concat(daily_rows, ignore_index=True) if daily_rows else pd.DataFrame(),
        pd.concat(weight_rows, ignore_index=True) if weight_rows else pd.DataFrame(),
        pd.DataFrame(summary_rows).sort_values(["universe_short", "lookback", "method"]).reset_index(drop=True),
        pd.DataFrame(comparison_rows).sort_values(["universe_short", "lookback", "method"]).reset_index(drop=True),
    )


def dynamic_anchor_weights(frontier_best: pd.DataFrame) -> dict[str, dict[str, float]]:
    anchors: dict[str, dict[str, float]] = {}
    for universe_short in ["A", "B"]:
        candidates = frontier_best[
            frontier_best["universe_short"].eq(universe_short)
            & frontier_best["feasible"].astype(bool)
        ].copy()
        preferred_d = 0.25 if universe_short == "A" else 0.20
        chosen = candidates[candidates["D_star"].astype(float).eq(preferred_d)]
        if chosen.empty and not candidates.empty:
            chosen = candidates.sort_values("D_star").tail(1)
        if chosen.empty:
            anchors[universe_short] = {}
            continue
        row = chosen.iloc[0]
        anchors[universe_short] = {
            col.removeprefix("weight_"): float(row[col])
            for col in row.index
            if str(col).startswith("weight_") and col not in {"weight_sum", "weight_vector_key"} and pd.notna(row[col])
        }
    return anchors


def simulate_dynamic_strategy(
    dates: pd.Series,
    returns: np.ndarray,
    options: np.ndarray,
    etfs: list[str],
    anchor: np.ndarray,
    lookback: int,
    method: str,
) -> pd.DataFrame:
    rebal_idx = set(monthly_rebalance_indices(dates, start_idx=lookback))
    weights = anchor.copy()
    rows: list[dict[str, Any]] = []
    nav = 1.0
    for i in range(lookback, len(dates)):
        if i in rebal_idx:
            window = returns[i - lookback : i, :]
            weights = dynamic_weights_from_window(window, anchor, method)
        r = float(np.dot(weights, returns[i, :]))
        opt = float(np.dot(weights, options[i, :]))
        nav *= 1.0 + r
        row = {
            "date": dates.iloc[i],
            "dynamic_return": r,
            "dynamic_option_return": opt,
            "dynamic_nav": nav,
            "is_rebalance_date": bool(i in rebal_idx),
        }
        for j, etf in enumerate(etfs):
            row[f"weight_{etf}"] = float(weights[j])
            row[f"return_{etf}"] = float(returns[i, j])
        rows.append(row)
    return pd.DataFrame(rows)


def monthly_rebalance_indices(dates: pd.Series, start_idx: int) -> list[int]:
    d = pd.DataFrame({"idx": range(len(dates)), "date": pd.to_datetime(dates)})
    d = d[d["idx"].ge(start_idx)].copy()
    d["month"] = d["date"].dt.to_period("M")
    return d.groupby("month")["idx"].min().astype(int).tolist()


def dynamic_weights_from_window(window: np.ndarray, anchor: np.ndarray, method: str) -> np.ndarray:
    vol = np.nanstd(window, axis=0, ddof=1)
    vol = np.where(np.isfinite(vol) & (vol > 0), vol, np.nanmedian(vol[np.isfinite(vol) & (vol > 0)]))
    vol = np.where(np.isfinite(vol) & (vol > 0), vol, 1.0)
    if method == "pure_inverse_vol":
        raw = 1.0 / vol
    elif method == "anchored_inverse_vol":
        raw = anchor / vol
    elif method == "rolling_min_variance":
        cov = np.cov(window, rowvar=False)
        try:
            raw = np.linalg.pinv(cov) @ np.ones(window.shape[1])
            raw = np.where(np.isfinite(raw) & (raw > 0), raw, 0.0)
            if raw.sum() <= 0:
                raw = 1.0 / vol
        except np.linalg.LinAlgError:
            raw = 1.0 / vol
    else:
        raise ValueError(f"Unsupported method: {method}")
    return bounded_normalize(raw, WEIGHT_LOWER_BOUND, WEIGHT_UPPER_BOUND)


def bounded_normalize(raw: np.ndarray, lower: float, upper: float) -> np.ndarray:
    w = np.asarray(raw, dtype=float)
    w = np.where(np.isfinite(w) & (w > 0), w, 0.0)
    if w.sum() <= 0:
        w = np.ones_like(w)
    w = w / w.sum()
    fixed = np.zeros_like(w, dtype=bool)
    for _ in range(20):
        below = (w < lower) & ~fixed
        above = (w > upper) & ~fixed
        if not below.any() and not above.any():
            break
        w[below] = lower
        w[above] = upper
        fixed = fixed | below | above
        remaining = 1.0 - w[fixed].sum()
        free = ~fixed
        if not free.any():
            break
        base = np.asarray(raw, dtype=float)[free]
        base = np.where(np.isfinite(base) & (base > 0), base, 1.0)
        w[free] = remaining * base / base.sum()
    w = np.clip(w, lower, upper)
    return w / w.sum()


def dynamic_weight_log(
    dynamic_daily: pd.DataFrame,
    strategy_name: str,
    universe_short: str,
    method: str,
    lookback: int,
    etfs: list[str],
    sleeves: dict[str, str],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    rebal = dynamic_daily[dynamic_daily["is_rebalance_date"].astype(bool)].copy()
    for _, row in rebal.iterrows():
        for etf in etfs:
            rows.append(
                {
                    "strategy_name": strategy_name,
                    "universe_short": universe_short,
                    "method": method,
                    "lookback": lookback,
                    "date": row["date"],
                    "etf_code": etf,
                    "sleeve_name": sleeves[etf],
                    "weight": row[f"weight_{etf}"],
                }
            )
    return pd.DataFrame(rows)


def static_returns_for_dynamic_sample(
    dates: pd.Series,
    returns: np.ndarray,
    options: np.ndarray,
    etfs: list[str],
    anchor: np.ndarray,
    dynamic_dates: pd.Series,
) -> pd.DataFrame:
    date_index = pd.Series(range(len(dates)), index=pd.to_datetime(dates))
    idx = date_index.loc[pd.to_datetime(dynamic_dates)].astype(int).to_numpy()
    r = returns[idx, :] @ anchor
    opt = options[idx, :] @ anchor
    return pd.DataFrame(
        {
            "date": pd.to_datetime(dynamic_dates).to_numpy(),
            "daily_return": r,
            "option_leg_return": opt,
            "nav": np.cumprod(1.0 + r),
        }
    )


def build_sanity_checks(
    *,
    selection_policy: pd.DataFrame,
    target_daily: pd.DataFrame,
    target_period: pd.DataFrame,
    target_summary: pd.DataFrame,
    candidate_pool: pd.DataFrame,
    fixed_summary: pd.DataFrame,
    frontier_best: pd.DataFrame,
    dynamic_summary: pd.DataFrame,
) -> pd.DataFrame:
    checks = [
        (
            "core_target_delta_etfs_present",
            {"510300", "510050"}.issubset(
                set(selection_policy[selection_policy["target_delta_scope"].eq("core_target_delta_candidate")]["etf_code"])
            ),
            str(selection_policy[["etf_code", "target_delta_scope", "selection_policy"]].to_dict(orient="records")),
        ),
        (
            "target_summary_row_count",
            len(target_summary) == len(ETF_SPECS) * (len(DELTA_SPECS) * len(COVERAGE_GRID) + 1),
            f"expected={len(ETF_SPECS) * (len(DELTA_SPECS) * len(COVERAGE_GRID) + 1)}; actual={len(target_summary)}",
        ),
        (
            "target_daily_no_duplicates",
            not target_daily.duplicated(["etf_code", "sleeve_name", "date"]).any(),
            f"duplicated={int(target_daily.duplicated(['etf_code', 'sleeve_name', 'date']).sum())}",
        ),
        ("candidate_pool_nonempty", not candidate_pool.empty, f"rows={len(candidate_pool)}"),
        ("fixed_summary_nonempty", not fixed_summary.empty, f"rows={len(fixed_summary)}"),
        ("frontier_best_nonempty", not frontier_best.empty, f"rows={len(frontier_best)}"),
        ("dynamic_summary_nonempty", not dynamic_summary.empty, f"rows={len(dynamic_summary)}"),
        (
            "target_period_reopens_immediately",
            check_immediate_reopen(target_period),
            "consecutive period end/rebalance gaps are zero trading days within each sleeve",
        ),
    ]
    return pd.DataFrame([{"check_name": name, "passed": bool(passed), "detail": detail} for name, passed, detail in checks])


def check_immediate_reopen(period: pd.DataFrame) -> bool:
    p = period[period["option_selected_flag"].astype(int).eq(1)].copy()
    if p.empty:
        return False
    p["rebalance_date"] = pd.to_datetime(p["rebalance_date"], errors="coerce")
    p["period_end_date"] = pd.to_datetime(p["period_end_date"], errors="coerce")
    diffs: list[int] = []
    for _, group in p.sort_values(["sleeve_name", "rebalance_date"]).groupby("sleeve_name"):
        g = group.sort_values("rebalance_date")
        prev_end = g["period_end_date"].shift(1)
        current_start = g["rebalance_date"]
        gap = (current_start - prev_end).dt.days.dropna()
        diffs.extend(gap.astype(int).tolist())
    return bool(diffs) and max(abs(x) for x in diffs) == 0


def write_outputs(**tables: pd.DataFrame) -> None:
    output_map = {
        "selection_policy": SUMMARY_DIR / "ver3_1_target_delta_selection_policy_by_etf.csv",
        "target_daily": DAILY_DIR / "ver3_1_target_delta_daily_paths.csv",
        "target_period": PERIOD_DIR / "ver3_1_target_delta_period_paths.csv",
        "target_summary": SUMMARY_DIR / "ver3_1_target_delta_surface_grid.csv",
        "candidate_pool": SUMMARY_DIR / "ver3_1_candidate_pool.csv",
        "portfolio_selection": SUMMARY_DIR / "ver3_1_portfolio_sleeve_selection.csv",
        "selected_daily": DAILY_DIR / "ver3_1_selected_sleeve_daily_panel.csv",
        "fixed_portfolios": PORTFOLIO_DIR / "ver3_1_fixed_weight_daily_returns.csv",
        "fixed_summary": PORTFOLIO_DIR / "ver3_1_fixed_weight_summary.csv",
        "frontier_grid": PORTFOLIO_DIR / "ver3_1_mdd_frontier_grid.csv",
        "frontier_best": PORTFOLIO_DIR / "ver3_1_mdd_frontier_best_by_dstar.csv",
        "dynamic_daily": DYNAMIC_DIR / "ver3_1_dynamic_daily_returns.csv",
        "dynamic_weights": DYNAMIC_DIR / "ver3_1_dynamic_weight_paths.csv",
        "dynamic_summary": DYNAMIC_DIR / "ver3_1_dynamic_strategy_summary.csv",
        "dynamic_comparison": DYNAMIC_DIR / "ver3_1_dynamic_vs_same_sample_static.csv",
        "sanity": AUDIT_DIR / "ver3_1_sanity_checks.csv",
    }
    for name, path in output_map.items():
        df = tables[name]
        df.to_csv(path, index=False, encoding="utf-8-sig")


def write_report(
    *,
    selection_policy: pd.DataFrame,
    target_summary: pd.DataFrame,
    candidate_pool: pd.DataFrame,
    portfolio_selection: pd.DataFrame,
    fixed_summary: pd.DataFrame,
    frontier_best: pd.DataFrame,
    dynamic_summary: pd.DataFrame,
    dynamic_comparison: pd.DataFrame,
    sanity: pd.DataFrame,
) -> None:
    target_top = target_summary[target_summary["parameter_grid_role"].eq("target_delta_surface")].sort_values(
        ["etf_code", "sharpe_daily_mean"], ascending=[True, False]
    )
    dyn_top = dynamic_summary.sort_values(["sharpe_daily_mean", "annualized_return_cagr"], ascending=False).head(8)
    dyn_cmp = dynamic_comparison.sort_values(
        ["delta_sharpe_vs_baseline", "delta_mdd_vs_baseline"], ascending=[False, True]
    ).head(8)
    lines = [
        "# ver3.1 Target-Delta x Coverage Experiment Report",
        "",
        f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 1. Experiment Positioning",
        "",
        "This sidecar keeps ver3.0 outputs intact. The current evidence layer is the direct target-delta x coverage parameter surface. Target-delta selection no longer uses the earlier fixed-moneyness mapping as a hard filter.",
        "",
        "## 2. Selection Policy",
        "",
        md_table(
            selection_policy[
                [
                    "etf_code",
                    "target_delta_scope",
                    "selection_policy",
                    "portfolio_role",
                    "eligible_delta_grid",
                    "eligible_coverage_grid",
                    "selection_note",
                ]
            ]
        ),
        "",
        "For 510300, 510050 and 159915, target-delta candidates are selected from the full D10/D20/D30/D40/D50 x Q10-Q100 grid after economic filters. No mapped delta band is used.",
        "",
        "## 3. Target-Delta Single-ETF Grid",
        "",
        md_table(
            target_top.groupby("etf_code").head(5)[
                [
                    "etf_code",
                    "sleeve_name",
                    "annualized_return_cagr",
                    "sharpe_daily_mean",
                    "max_drawdown",
                    "option_leg_annualized_pnl_contribution",
                    "assignment_rate",
                    "eligible_target_delta_surface",
                ]
            ],
            pct_cols=[
                "annualized_return_cagr",
                "max_drawdown",
                "option_leg_annualized_pnl_contribution",
                "assignment_rate",
            ],
            num_cols=["sharpe_daily_mean"],
        ),
        "",
        "## 4. Candidate Pool",
        "",
        md_table(candidate_pool),
        "",
        "## 5. Portfolio Sleeve Selection",
        "",
        md_table(portfolio_selection),
        "",
        "## 6. Fixed-Weight Results",
        "",
        md_table(
            fixed_summary[
                [
                    "portfolio_name",
                    "universe_short",
                    "annualized_return_cagr",
                    "sharpe_daily_mean",
                    "max_drawdown",
                    "annualized_volatility",
                    "option_leg_annualized_pnl_contribution",
                ]
            ],
            pct_cols=[
                "annualized_return_cagr",
                "max_drawdown",
                "annualized_volatility",
                "option_leg_annualized_pnl_contribution",
            ],
            num_cols=["sharpe_daily_mean"],
        ),
        "",
        "## 7. MDD-Constrained Sharpe Frontier",
        "",
        md_table(
            frontier_best[
                [
                    "universe_short",
                    "D_star",
                    "frontier_status",
                    "portfolio_name",
                    "annualized_return_cagr",
                    "sharpe_daily_mean",
                    "max_drawdown",
                ]
            ],
            pct_cols=["D_star", "annualized_return_cagr", "max_drawdown"],
            num_cols=["sharpe_daily_mean"],
        ),
        "",
        "## 8. Dynamic Weighting Results",
        "",
        md_table(
            dyn_top[
                [
                    "portfolio_name",
                    "universe_short",
                    "method",
                    "lookback",
                    "sample_start",
                    "sample_end",
                    "annualized_return_cagr",
                    "sharpe_daily_mean",
                    "max_drawdown",
                ]
            ],
            pct_cols=["annualized_return_cagr", "max_drawdown"],
            num_cols=["sharpe_daily_mean"],
        ),
        "",
        "Same-sample static benchmark comparison:",
        "",
        md_table(
            dyn_cmp,
            pct_cols=[
                "dynamic_cagr",
                "baseline_cagr",
                "delta_cagr_vs_baseline",
                "dynamic_mdd",
                "baseline_mdd",
                "delta_mdd_vs_baseline",
            ],
            num_cols=["dynamic_sharpe", "baseline_sharpe", "delta_sharpe_vs_baseline"],
        ),
        "",
        "## 9. Sanity Checks",
        "",
        md_table(sanity),
    ]
    (REPORT_DIR / "ver3_1_effective_zone_target_delta_report.md").write_text("\n".join(lines), encoding="utf-8")


def write_manifest(sanity: pd.DataFrame) -> None:
    manifest = {
        "experiment_id": EXPERIMENT_ID,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "execution_mode": "continuous_30d_daily_mtm",
        "input_moneyness_surface": rel_path(MONEYNESS_SUMMARY),
        "input_delta_options": rel_path(DELTA_OPTION_PATH),
        "delta_grid": [delta.label for delta in DELTA_SPECS],
        "coverage_grid": [coverage_label_from_float(x) for x in COVERAGE_GRID],
        "outputs": {
            "report": rel_path(REPORT_DIR / "ver3_1_effective_zone_target_delta_report.md"),
            "selection_policy": rel_path(SUMMARY_DIR / "ver3_1_target_delta_selection_policy_by_etf.csv"),
            "target_delta_grid": rel_path(SUMMARY_DIR / "ver3_1_target_delta_surface_grid.csv"),
            "portfolio_selection": rel_path(SUMMARY_DIR / "ver3_1_portfolio_sleeve_selection.csv"),
            "frontier_best": rel_path(PORTFOLIO_DIR / "ver3_1_mdd_frontier_best_by_dstar.csv"),
            "dynamic_summary": rel_path(DYNAMIC_DIR / "ver3_1_dynamic_strategy_summary.csv"),
        },
        "sanity_passed": int(sanity["passed"].sum()),
        "sanity_total": int(len(sanity)),
    }
    (OUT_ROOT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    readme = [
        "# ver3.1 target-delta x coverage experiment",
        "",
        "This sidecar experiment keeps ver3.0 outputs intact.",
        "The output directory name is retained for compatibility; the active selection logic no longer uses the earlier fixed-moneyness delta mapping.",
        "",
        "Main flow:",
        "",
        "1. Run target-delta daily-MTM grids for D10/D20/D30/D40/D50 x Q10..Q100.",
        "2. Select core ETF sleeves directly from the full target-delta x coverage grid after economic filters.",
        "3. Keep non-core sleeves in their explicit fixed-moneyness or BuyHold roles.",
        "4. Rebuild fixed-weight, MDD-constrained Sharpe frontier, and dynamic-weight comparisons.",
        "",
        f"Report: `{rel_path(REPORT_DIR / 'ver3_1_effective_zone_target_delta_report.md')}`",
    ]
    (OUT_ROOT / "README.md").write_text("\n".join(readme), encoding="utf-8")


def coverage_label_from_float(value: float) -> str:
    return f"Q{int(round(float(value) * 100))}"


def numeric(values: Any) -> pd.Series:
    if isinstance(values, pd.Series):
        return pd.to_numeric(values, errors="coerce").fillna(0.0)
    return pd.Series(values)


def safe_div(numerator: float, denominator: float) -> float:
    if pd.isna(denominator) or abs(float(denominator)) < 1e-12:
        return np.nan
    return float(numerator) / float(denominator)


def date_iso(value: Any) -> str:
    if pd.isna(value):
        return ""
    return pd.Timestamp(value).date().isoformat()


def rel_path(path: Path | str) -> str:
    p = Path(path)
    try:
        return str(p.resolve().relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(p)


def fmt_pct(value: Any) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value):.2%}"


def fmt_num(value: Any) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value):.3f}"


def md_table(df: pd.DataFrame, pct_cols: list[str] | None = None, num_cols: list[str] | None = None) -> str:
    if df.empty:
        return "_No rows._"
    pct_cols = pct_cols or []
    num_cols = num_cols or []
    out = df.copy()
    for col in pct_cols:
        if col in out:
            out[col] = out[col].map(fmt_pct)
    for col in num_cols:
        if col in out:
            out[col] = out[col].map(fmt_num)
    out = out.fillna("")
    return out.to_markdown(index=False)


if __name__ == "__main__":
    main()
