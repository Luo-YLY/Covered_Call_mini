from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
VER3_SRC = ROOT / "ver3" / "src"
for candidate in (ROOT, VER3_SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from covered_call_mini_ver3.diagnostics.phase_sensitivity.config import (  # noqa: E402
    PhasePaths,
    PhaseRunConfig,
    TargetSleeve,
)
from covered_call_mini_ver3.diagnostics.phase_sensitivity.cycle_attribution import (  # noqa: E402
    compute_option_cycle_concentration,
)
from covered_call_mini_ver3.diagnostics.phase_sensitivity.io import (  # noqa: E402
    load_required_market_data,
)
from covered_call_mini_ver3.diagnostics.phase_sensitivity.metrics import (  # noqa: E402
    common_window_start,
    compute_phase_metrics,
    compute_phase_robustness_summary,
    sleeve_buyhold_comparison,
)
from covered_call_mini_ver3.diagnostics.phase_sensitivity.phase_grid import (  # noqa: E402
    generate_phase_shift_grid,
    map_phase_to_inception_dates,
)
from covered_call_mini_ver3.diagnostics.phase_sensitivity.sleeve_runner import (  # noqa: E402
    run_all_phase_sleeves,
)
from covered_call_mini_ver3.stepC_robustness.config import (  # noqa: E402
    manual_event_windows,
)
from src.metrics.ver2_metric_standard import (  # noqa: E402
    compute_portfolio_option_contribution,
    summarize_daily_nav,
)


EXPERIMENT_ROOT = ROOT / "outputs" / "ver3_1_effective_zone_target_delta"
SELECTION_ROOT = EXPERIMENT_ROOT / "analysis" / "candidate_selection" / "summary"
SELECTED_CANDIDATES = SELECTION_ROOT / "candidate_pool_selected.csv"
TARGET_DAILY = EXPERIMENT_ROOT / "daily" / "ver3_1_target_delta_daily_paths.csv"
TARGET_PERIOD = EXPERIMENT_ROOT / "period" / "ver3_1_target_delta_period_paths.csv"
MONEYNESS_ROOT = ROOT / "outputs" / "ver3_0_stepA_moneyness_refined_daily_mtm_surface"
MONEYNESS_DAILY = MONEYNESS_ROOT / "daily" / "ver3_0_stepA_moneyness_refined_daily_mtm_daily_paths.csv"
MONEYNESS_PERIOD = MONEYNESS_ROOT / "period" / "ver3_0_stepA_moneyness_refined_daily_mtm_period_paths.csv"

OUT_ROOT = EXPERIMENT_ROOT / "analysis" / "candidate_robustness"
CONFIG_DIR = OUT_ROOT / "config"
DAILY_DIR = OUT_ROOT / "daily"
PERIOD_DIR = OUT_ROOT / "period"
PHASE_DIR = OUT_ROOT / "phase"
EVENT_DIR = OUT_ROOT / "events"
COST_DIR = OUT_ROOT / "cost"
CYCLE_DIR = OUT_ROOT / "cycle"
SUMMARY_DIR = OUT_ROOT / "summary"
REPORT_DIR = OUT_ROOT / "reports"

MAIN_SAMPLE_START = "2022-09-30"
MAIN_SAMPLE_END = "2026-05-27"
SHORT_SAMPLE_START = "2023-06-30"
SHORT_SAMPLE_ETFS = {"588000"}
TRADING_DAYS = 252.0
COST_BPS = [0.0, 5.0, 10.0, 20.0, 30.0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run ver3.1 third-layer robustness diagnostics for selected ETF covered-call candidates."
    )
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--ver3-root", type=Path, default=ROOT / "ver3")
    parser.add_argument("--output-dir", type=Path, default=OUT_ROOT)
    parser.add_argument("--max-phase-shift", type=int, default=20)
    parser.add_argument("--phase-step", type=int, default=1)
    parser.add_argument("--skip-phase", action="store_true")
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def ensure_dirs() -> None:
    for path in [CONFIG_DIR, DAILY_DIR, PERIOD_DIR, PHASE_DIR, EVENT_DIR, COST_DIR, CYCLE_DIR, SUMMARY_DIR, REPORT_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path.relative_to(ROOT)}")
    return pd.read_csv(path, dtype={"etf_code": str})


def write_csv(df: pd.DataFrame, path: Path) -> None:
    if df.empty:
        raise ValueError(f"Refusing to write empty CSV: {path.relative_to(ROOT)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def normalize_etf_code(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "etf_code" in out.columns:
        out["etf_code"] = out["etf_code"].astype(str).str.replace(".0", "", regex=False).str.zfill(6)
    return out


def numeric(df: pd.DataFrame, column: str, default: float = np.nan) -> pd.Series:
    if column not in df.columns:
        return pd.Series(default, index=df.index, dtype="float64")
    return pd.to_numeric(df[column], errors="coerce")


def load_selected_candidates() -> pd.DataFrame:
    candidates = normalize_etf_code(read_csv(SELECTED_CANDIDATES))
    candidates = candidates[candidates["selected_flag"].astype(str).str.lower().eq("true")].copy()
    if candidates.empty:
        raise ValueError("No selected candidate rows found.")
    for column in ["coverage", "target_delta", "target_moneyness", "annualized_return_cagr", "sharpe_daily_mean", "max_drawdown"]:
        candidates[column] = numeric(candidates, column)
    candidates["sample_scope_for_robustness"] = np.where(
        candidates["etf_code"].isin(SHORT_SAMPLE_ETFS), "short_sample_research", "main_common_sample"
    )
    candidates["robustness_sample_start"] = np.where(
        candidates["etf_code"].isin(SHORT_SAMPLE_ETFS), SHORT_SAMPLE_START, MAIN_SAMPLE_START
    )
    candidates["robustness_sample_end"] = MAIN_SAMPLE_END
    return candidates.reset_index(drop=True)


def load_candidate_paths(candidates: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    target_daily = normalize_etf_code(read_csv(TARGET_DAILY))
    target_period = normalize_etf_code(read_csv(TARGET_PERIOD))
    moneyness_daily = normalize_etf_code(read_csv(MONEYNESS_DAILY))
    moneyness_period = normalize_etf_code(read_csv(MONEYNESS_PERIOD))

    daily = pd.concat([target_daily, moneyness_daily], ignore_index=True, sort=False)
    period = pd.concat([target_period, moneyness_period], ignore_index=True, sort=False)

    keys = candidates[
        [
            "candidate_id",
            "etf_code",
            "sleeve_name",
            "candidate_family",
            "selector_type",
            "rule_label",
            "coverage_label",
            "coverage",
            "target_delta",
            "selected_reason",
            "candidate_role",
            "sample_scope_for_robustness",
            "robustness_sample_start",
            "robustness_sample_end",
        ]
    ].copy()

    daily = daily.merge(keys, on=["etf_code", "sleeve_name"], how="inner", suffixes=("", "_candidate"))
    period = period.merge(keys, on=["etf_code", "sleeve_name"], how="inner", suffixes=("", "_candidate"))
    if daily.empty or period.empty:
        raise ValueError("No selected candidate paths were found after merging daily and period inputs.")

    daily["date"] = pd.to_datetime(daily["date"], errors="coerce")
    period["rebalance_date"] = pd.to_datetime(period["rebalance_date"], errors="coerce")
    for column in ["expiry_date", "period_end_date"]:
        if column in period.columns:
            period[column] = pd.to_datetime(period[column], errors="coerce")
    for column in [
        "nav_total",
        "daily_return_total",
        "daily_return_option_leg_component",
        "option_leg_pnl",
        "active_coverage",
        "coverage",
        "target_delta",
    ]:
        daily[column] = numeric(daily, column, 0.0)
    for column in [
        "option_leg_return",
        "premium_return",
        "payoff_return",
        "transaction_cost_return",
        "covered_call_period_return",
        "assignment_flag",
        "actual_dte",
        "selected_delta",
        "realized_moneyness",
        "max_short_call_mtm_loss_in_period",
    ]:
        period[column] = numeric(period, column, 0.0)

    daily = daily.sort_values(["candidate_id", "date"]).reset_index(drop=True)
    period = period.sort_values(["candidate_id", "rebalance_date"]).reset_index(drop=True)
    return daily, period


def compute_natural_summary(daily: pd.DataFrame, period: pd.DataFrame, candidates: pd.DataFrame) -> pd.DataFrame:
    period_lookup = {k: g.copy() for k, g in period.groupby("candidate_id", sort=False)}
    rows: list[dict[str, Any]] = []
    meta_lookup = candidates.set_index("candidate_id")
    for candidate_id, group in daily.groupby("candidate_id", sort=True):
        g = group.sort_values("date")
        metrics = summarize_daily_nav(g[["date", "nav_total"]], date_col="date", nav_col="nav_total", rf=0.0)
        option = compute_portfolio_option_contribution(g["daily_return_option_leg_component"], n_days=len(g))
        periods = period_lookup.get(candidate_id, pd.DataFrame())
        meta = meta_lookup.loc[candidate_id].to_dict()
        rows.append(
            {
                "candidate_id": candidate_id,
                "etf_code": meta["etf_code"],
                "sleeve_name": meta["sleeve_name"],
                "candidate_family": meta["candidate_family"],
                "selector_type": meta["selector_type"],
                "rule_label": meta["rule_label"],
                "coverage_label": meta["coverage_label"],
                "coverage": float(meta["coverage"]),
                "target_delta": meta.get("target_delta", np.nan),
                "candidate_role": meta.get("candidate_role", ""),
                "sample_scope_for_robustness": meta["sample_scope_for_robustness"],
                "selected_reason": meta.get("selected_reason", ""),
                **metrics,
                "final_nav": float(g["nav_total"].iloc[-1]),
                "option_leg_annualized_pnl_contribution": option,
                "selected_periods": int(len(periods)),
                "assignment_count": int(periods["assignment_flag"].astype(bool).sum()) if not periods.empty else 0,
                "assignment_fraction": f"{int(periods['assignment_flag'].astype(bool).sum())}/{len(periods)}" if not periods.empty else "",
                "assignment_rate": float(periods["assignment_flag"].astype(bool).mean()) if not periods.empty else np.nan,
                "avg_selected_delta": _mean(periods, "selected_delta"),
                "avg_realized_moneyness": _mean(periods, "realized_moneyness"),
            }
        )
    return pd.DataFrame(rows)


def evaluate_event_exclusion(daily: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    manual = manual_event_windows()
    event_config = pd.DataFrame([asdict(item) for item in manual])
    if event_config.empty:
        return event_config, pd.DataFrame()

    cases = [
        ("full_sample", set(), "full_path"),
        (
            "exclude_upside_policy",
            _event_dates(event_config[event_config["event_type"].astype(str).str.contains("upside", na=False)]),
            "sensitivity_path",
        ),
        (
            "exclude_downside_market",
            _event_dates(event_config[event_config["event_type"].astype(str).str.contains("downside", na=False)]),
            "sensitivity_path",
        ),
        ("exclude_all_manual_events", _event_dates(event_config), "sensitivity_path"),
    ]
    rows: list[dict[str, Any]] = []
    full_lookup: dict[str, dict[str, Any]] = {}
    for candidate_id, group in daily.groupby("candidate_id", sort=True):
        full_metrics = _metrics_from_daily_returns(group)
        full_lookup[candidate_id] = full_metrics
        for case_name, dates_to_remove, note in cases:
            if dates_to_remove:
                sample = group[~group["date"].dt.date.astype(str).isin(dates_to_remove)].copy()
            else:
                sample = group.copy()
            if len(sample) < 3:
                continue
            metrics = _metrics_from_daily_returns(sample)
            rows.append(
                {
                    "candidate_id": candidate_id,
                    "diagnostic_case": case_name,
                    "note": note,
                    "removed_trading_days": int(len(group) - len(sample)),
                    **metrics,
                    "delta_sharpe_vs_full_sample": metrics["sharpe_daily_mean"] - full_metrics["sharpe_daily_mean"],
                    "delta_mdd_vs_full_sample": metrics["max_drawdown"] - full_metrics["max_drawdown"],
                    "delta_cagr_vs_full_sample": metrics["annualized_return_cagr"] - full_metrics["annualized_return_cagr"],
                }
            )
    return event_config, pd.DataFrame(rows)


def evaluate_cost_sensitivity(daily: pd.DataFrame, cost_bps: list[float]) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    for bps in cost_bps:
        for candidate_id, group in daily.groupby("candidate_id", sort=True):
            g = group.copy()
            active_coverage = g["active_coverage"].fillna(g["coverage"]).astype(float).clip(lower=0.0)
            drag = float(bps) / 10000.0 / TRADING_DAYS * active_coverage
            g["daily_return_total_stressed"] = g["daily_return_total"].astype(float) - drag
            g["daily_return_option_leg_component_stressed"] = g["daily_return_option_leg_component"].astype(float) - drag
            metrics = _metrics_from_returns_frame(
                g,
                return_col="daily_return_total_stressed",
                option_col="daily_return_option_leg_component_stressed",
            )
            rows.append(
                {
                    "candidate_id": candidate_id,
                    "cost_scenario": "base" if abs(float(bps)) < 1e-12 else f"option_cost_plus_{int(bps)}bps",
                    "extra_option_cost_bps_annualized": float(bps),
                    "cost_model": "annualized_bps_drag_scaled_by_active_coverage",
                    **metrics,
                }
            )
    summary = pd.DataFrame(rows)
    base = summary[summary["cost_scenario"].eq("base")].set_index("candidate_id")
    robustness_rows: list[dict[str, Any]] = []
    for candidate_id, group in summary.groupby("candidate_id", sort=True):
        base_row = base.loc[candidate_id]
        g = group.copy()
        g["delta_sharpe_vs_base"] = g["sharpe_daily_mean"].astype(float) - float(base_row["sharpe_daily_mean"])
        g["delta_cagr_vs_base"] = g["annualized_return_cagr"].astype(float) - float(base_row["annualized_return_cagr"])
        g["delta_mdd_vs_base"] = g["max_drawdown"].astype(float) - float(base_row["max_drawdown"])
        worst = g.sort_values("extra_option_cost_bps_annualized", ascending=False).iloc[0]
        robustness_rows.append(
            {
                "candidate_id": candidate_id,
                "worst_cost_scenario": worst["cost_scenario"],
                "worst_cost_sharpe": float(worst["sharpe_daily_mean"]),
                "worst_cost_cagr": float(worst["annualized_return_cagr"]),
                "worst_cost_mdd": float(worst["max_drawdown"]),
                "worst_delta_sharpe_vs_base": float(worst["delta_sharpe_vs_base"]),
                "worst_delta_cagr_vs_base": float(worst["delta_cagr_vs_base"]),
                "worst_delta_mdd_vs_base": float(worst["delta_mdd_vs_base"]),
                "option_leg_positive_under_worst_cost": bool(float(worst["option_leg_annualized_pnl_contribution"]) > 0),
            }
        )
        summary.loc[g.index, ["delta_sharpe_vs_base", "delta_cagr_vs_base", "delta_mdd_vs_base"]] = g[
            ["delta_sharpe_vs_base", "delta_cagr_vs_base", "delta_mdd_vs_base"]
        ]
    return summary, pd.DataFrame(robustness_rows)


def compute_cycle_concentration_natural(period: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for candidate_id, group in period.groupby("candidate_id", sort=True):
        g = group.sort_values("rebalance_date").copy()
        option_leg = g["option_leg_return"].astype(float)
        abs_leg = option_leg.abs()
        denom = float(abs_leg.sum())
        weights = abs_leg / denom if denom > 0 else pd.Series(0.0, index=g.index)
        worst_idx = option_leg.idxmin() if not option_leg.empty else None
        best_idx = option_leg.idxmax() if not option_leg.empty else None
        rows.append(
            {
                "candidate_id": candidate_id,
                "option_cycle_count": int(len(g)),
                "cycle_option_pnl_sum": float(option_leg.sum()),
                "cycle_option_pnl_mean": float(option_leg.mean()) if len(option_leg) else np.nan,
                "cycle_option_pnl_std": float(option_leg.std(ddof=1)) if len(option_leg) > 1 else 0.0,
                "top_1_abs_cycle_pnl_share": _top_share(abs_leg, 1),
                "top_3_abs_cycle_pnl_share": _top_share(abs_leg, 3),
                "top_5_abs_cycle_pnl_share": _top_share(abs_leg, 5),
                "option_cycle_hhi": float((weights**2).sum()) if denom > 0 else np.nan,
                "positive_cycle_rate": float((option_leg > 0).mean()) if len(option_leg) else np.nan,
                "assignment_rate": float(g["assignment_flag"].astype(bool).mean()) if len(g) else np.nan,
                "worst_cycle_pnl": float(option_leg.min()) if len(option_leg) else np.nan,
                "worst_cycle_start": _date(g.loc[worst_idx, "rebalance_date"]) if worst_idx is not None else "",
                "worst_cycle_end": _date(g.loc[worst_idx, "period_end_date"]) if worst_idx is not None else "",
                "best_cycle_pnl": float(option_leg.max()) if len(option_leg) else np.nan,
                "best_cycle_start": _date(g.loc[best_idx, "rebalance_date"]) if best_idx is not None else "",
                "best_cycle_end": _date(g.loc[best_idx, "period_end_date"]) if best_idx is not None else "",
            }
        )
    return pd.DataFrame(rows)


def run_phase_layer(
    candidates: pd.DataFrame,
    *,
    project_root: Path,
    ver3_root: Path,
    output_root: Path,
    max_phase_shift: int,
    phase_step: int,
    strict: bool,
) -> dict[str, pd.DataFrame]:
    all_daily: list[pd.DataFrame] = []
    all_returns: list[pd.DataFrame] = []
    all_periods: list[pd.DataFrame] = []
    all_status: list[pd.DataFrame] = []
    all_metrics: list[pd.DataFrame] = []
    all_robustness: list[pd.DataFrame] = []
    all_cycles: list[pd.DataFrame] = []
    phase_configs: list[pd.DataFrame] = []

    for sample_scope, group in candidates.groupby("sample_scope_for_robustness", sort=True):
        sample_start = str(group["robustness_sample_start"].iloc[0])
        sample_end = str(group["robustness_sample_end"].iloc[0])
        target_etfs = sorted(group["etf_code"].unique())
        sleeves = build_phase_sleeves(group)
        phase_paths = PhasePaths(project_root=project_root, ver3_root=ver3_root, output_root=output_root / sample_scope)
        phase_paths.ensure_output_dirs()
        base_config, data = load_required_market_data(phase_paths, target_etfs)
        shift_grid = generate_phase_shift_grid(max_phase_shift, phase_step)
        inception_grid = map_phase_to_inception_dates(
            data.prices,
            shift_grid,
            sample_start=sample_start,
            etf_codes=target_etfs,
        )
        phase_grid = shift_grid.merge(inception_grid, on=["phase_id", "phase_shift"], how="left")
        phase_grid["sample_scope_for_robustness"] = sample_scope
        phase_grid["sample_start"] = sample_start
        phase_grid["sample_end"] = sample_end
        phase_configs.append(phase_grid)

        print(
            f"phase_scope={sample_scope} etfs={','.join(target_etfs)} sleeves={len(sleeves)} phases={len(phase_grid)} "
            f"sample={sample_start}->{sample_end}",
            flush=True,
        )
        runs = run_all_phase_sleeves(data, base_config, sleeves, phase_grid, end_date=sample_end, strict=strict)
        for frame in [runs.daily_nav, runs.daily_returns, runs.period_map, runs.run_status]:
            frame["sample_scope_for_robustness"] = sample_scope
        all_daily.append(runs.daily_nav)
        all_returns.append(runs.daily_returns)
        if not runs.period_map.empty:
            all_periods.append(runs.period_map)
            cycles = compute_option_cycle_concentration(runs.period_map)
            cycles["sample_scope_for_robustness"] = sample_scope
            all_cycles.append(cycles)
        all_status.append(runs.run_status)

        common_start = common_window_start(runs.daily_nav, "sleeve_key")
        metrics = pd.concat(
            [
                compute_phase_metrics(runs.daily_nav, runs.period_map, rf=0.0, common_start=common_start, window_mode="natural"),
                compute_phase_metrics(runs.daily_nav, runs.period_map, rf=0.0, common_start=common_start, window_mode="common"),
            ],
            ignore_index=True,
        )
        metrics["sample_scope_for_robustness"] = sample_scope
        comp = sleeve_buyhold_comparison(metrics, sleeves)
        robust = compute_phase_robustness_summary(metrics, entity_col="sleeve_name", buyhold_comparison=comp)
        robust["sample_scope_for_robustness"] = sample_scope
        all_metrics.append(metrics)
        all_robustness.append(robust)

    daily_nav = pd.concat(all_daily, ignore_index=True, sort=False)
    daily_returns = pd.concat(all_returns, ignore_index=True, sort=False)
    period_map = pd.concat(all_periods, ignore_index=True, sort=False) if all_periods else pd.DataFrame()
    run_status = pd.concat(all_status, ignore_index=True, sort=False)
    metrics = pd.concat(all_metrics, ignore_index=True, sort=False)
    robustness = pd.concat(all_robustness, ignore_index=True, sort=False)
    cycles = pd.concat(all_cycles, ignore_index=True, sort=False) if all_cycles else pd.DataFrame()
    phase_grid = pd.concat(phase_configs, ignore_index=True, sort=False)

    candidate_meta = candidates[["candidate_id", "etf_code", "sleeve_name"]].copy()
    metrics = metrics.merge(candidate_meta, on=["etf_code", "sleeve_name"], how="left")
    robustness = robustness.merge(candidate_meta[["candidate_id", "sleeve_name"]], on="sleeve_name", how="left")
    cycles = cycles.merge(candidate_meta[["candidate_id", "sleeve_name"]], on="sleeve_name", how="left") if not cycles.empty else cycles
    return {
        "phase_grid": phase_grid,
        "daily_nav": daily_nav,
        "daily_returns": daily_returns,
        "period_map": period_map,
        "run_status": run_status,
        "metrics": metrics,
        "robustness": robustness,
        "cycle_concentration": cycles,
    }


def build_phase_sleeves(candidates: pd.DataFrame) -> list[TargetSleeve]:
    sleeves: list[TargetSleeve] = []
    for row in candidates.itertuples(index=False):
        selector_type = str(row.selector_type)
        rule_label = str(row.rule_label)
        coverage_label = str(row.coverage_label)
        strategy_name = f"{rule_label}_{coverage_label}"
        if selector_type == "target_delta":
            strategy_kind = "target_delta"
            target_moneyness = float(row.target_delta)
            family = rule_label
        elif selector_type == "atm_strike":
            strategy_kind = "atm"
            target_moneyness = 0.0
            family = "ATM"
        else:
            raise ValueError(f"Unsupported selector_type for phase run: {selector_type}")
        sleeves.append(
            TargetSleeve(
                etf_code=str(row.etf_code),
                sleeve_name=str(row.sleeve_name),
                role=str(getattr(row, "candidate_role", "")),
                is_buyhold=False,
                strategy_name=strategy_name,
                strategy_kind=strategy_kind,
                coverage=float(row.coverage),
                target_moneyness=target_moneyness,
                strategy_family=family,
            )
        )
    for etf_code in sorted(candidates["etf_code"].unique()):
        sleeves.append(TargetSleeve(etf_code, f"{etf_code}_ETF_BuyHold", "same ETF buyhold baseline", True))
    return sleeves


def build_decision_table(
    natural: pd.DataFrame,
    phase_robustness: pd.DataFrame,
    event_exclusion: pd.DataFrame,
    cost_robustness: pd.DataFrame,
    cycle: pd.DataFrame,
) -> pd.DataFrame:
    out = natural.copy()
    phase_cols = [
        "candidate_id",
        "phase_count",
        "phase_success_count",
        "sharpe_median",
        "sharpe_p25",
        "sharpe_min",
        "sharpe_std",
        "mdd_p75",
        "mdd_max",
        "phase_hit_rate_vs_buyhold",
        "phase_hit_rate_mdd_below_buyhold",
        "phase_robustness_label",
    ]
    phase = phase_robustness[phase_robustness["candidate_id"].notna()].copy()
    out = out.merge(phase[[col for col in phase_cols if col in phase.columns]], on="candidate_id", how="left")

    event_all = event_exclusion[event_exclusion["diagnostic_case"].eq("exclude_all_manual_events")].copy()
    event_all = event_all[
        [
            "candidate_id",
            "removed_trading_days",
            "sharpe_daily_mean",
            "max_drawdown",
            "annualized_return_cagr",
            "delta_sharpe_vs_full_sample",
            "delta_mdd_vs_full_sample",
            "delta_cagr_vs_full_sample",
        ]
    ].rename(
        columns={
            "removed_trading_days": "event_removed_trading_days",
            "sharpe_daily_mean": "ex_event_sharpe",
            "max_drawdown": "ex_event_mdd",
            "annualized_return_cagr": "ex_event_cagr",
            "delta_sharpe_vs_full_sample": "event_delta_sharpe",
            "delta_mdd_vs_full_sample": "event_delta_mdd",
            "delta_cagr_vs_full_sample": "event_delta_cagr",
        }
    )
    out = out.merge(event_all, on="candidate_id", how="left")
    out = out.merge(cost_robustness, on="candidate_id", how="left")
    out = out.merge(
        cycle[
            [
                "candidate_id",
                "top_1_abs_cycle_pnl_share",
                "top_3_abs_cycle_pnl_share",
                "option_cycle_hhi",
                "positive_cycle_rate",
                "worst_cycle_pnl",
                "worst_cycle_start",
                "worst_cycle_end",
                "best_cycle_pnl",
                "best_cycle_start",
                "best_cycle_end",
            ]
        ],
        on="candidate_id",
        how="left",
    )
    out["third_layer_flags"] = out.apply(_third_layer_flags, axis=1)
    out["third_layer_decision"] = out.apply(_third_layer_decision, axis=1)
    out["third_layer_interpretation"] = out.apply(_third_layer_interpretation, axis=1)
    return out.sort_values(["etf_code", "third_layer_decision", "sharpe_daily_mean"], ascending=[True, True, False])


def _third_layer_flags(row: pd.Series) -> str:
    flags: list[str] = []
    if str(row.get("sample_scope_for_robustness")) == "short_sample_research":
        flags.append("short_sample")
    if pd.notna(row.get("sharpe_p25")) and float(row["sharpe_p25"]) <= 0:
        flags.append("phase_p25_not_positive")
    if pd.notna(row.get("sharpe_std")) and float(row["sharpe_std"]) > 0.18:
        flags.append("phase_dispersion_high")
    if pd.notna(row.get("event_delta_sharpe")) and float(row["event_delta_sharpe"]) < -0.15:
        flags.append("event_exclusion_sharpe_drop")
    if pd.notna(row.get("event_delta_mdd")) and float(row["event_delta_mdd"]) > 0.03:
        flags.append("event_exclusion_mdd_worse")
    if pd.notna(row.get("worst_delta_sharpe_vs_base")) and float(row["worst_delta_sharpe_vs_base"]) < -0.08:
        flags.append("cost_sensitivity_high")
    if pd.notna(row.get("top_3_abs_cycle_pnl_share")) and float(row["top_3_abs_cycle_pnl_share"]) > 0.60:
        flags.append("cycle_concentration_high")
    return ";".join(flags)


def _third_layer_decision(row: pd.Series) -> str:
    flags = set(str(row.get("third_layer_flags", "")).split(";")) if str(row.get("third_layer_flags", "")) else set()
    if "short_sample" in flags:
        return "research_only_short_sample"
    severe = {"phase_p25_not_positive", "event_exclusion_sharpe_drop", "event_exclusion_mdd_worse"}
    if flags & severe:
        return "defer_or_recheck"
    caveats = {"phase_dispersion_high", "cost_sensitivity_high", "cycle_concentration_high"}
    if flags & caveats:
        return "pass_with_caveat"
    return "pass_to_portfolio_test"


def _third_layer_interpretation(row: pd.Series) -> str:
    decision = str(row.get("third_layer_decision", ""))
    if decision == "pass_to_portfolio_test":
        return "相位、事件、成本和周期集中度未显示显著依赖，适合进入组合层验证。"
    if decision == "pass_with_caveat":
        return f"基本可进入组合层，但需携带稳健性提示：{row.get('third_layer_flags', '')}。"
    if decision == "research_only_short_sample":
        return "588000 使用短样本，只作为研究观察，不与主样本候选同等级晋级。"
    return f"第三层出现关键稳健性问题，建议暂缓作为主线候选：{row.get('third_layer_flags', '')}。"


def write_report(decision: pd.DataFrame, phase_status: pd.DataFrame | None) -> None:
    main_cols = [
        "etf_code",
        "candidate_id",
        "rule_label",
        "coverage_label",
        "sample_scope_for_robustness",
        "annualized_return_cagr",
        "sharpe_daily_mean",
        "max_drawdown",
        "sharpe_p25",
        "sharpe_std",
        "event_delta_sharpe",
        "worst_delta_sharpe_vs_base",
        "top_3_abs_cycle_pnl_share",
        "third_layer_decision",
        "third_layer_flags",
    ]
    status_text = "not_run"
    if phase_status is not None and not phase_status.empty:
        success_rate = float(phase_status["status"].eq("success").mean())
        status_text = f"{success_rate:.2%} success, {len(phase_status)} sleeve-phase runs"
    lines = [
        "# ver3.1 Third-Layer Candidate Robustness Diagnostics",
        "",
        "本报告承接第二层候选池，不重新选择参数，也不修改 Step B/C/D 主线输出。第三层只回答一个问题：候选 sleeve 是否对相位、少数事件、成本假设或个别交易周期过度敏感。",
        "",
        "## 方法口径",
        "",
        "- 输入：`candidate_pool_selected.csv` 中的入选候选。",
        "- 自然样本：直接读取 target-delta 与 ATM 参数路径的日频/周期结果。",
        "- 相位检验：改变首期开仓交易日后重跑连续 30D 备兑路径，而不是裁剪旧净值。",
        "- 事件剔除：沿用 Step C 手工事件窗口，仅作为敏感性诊断，不作为择时信号。",
        "- 成本压力：对活跃覆盖率施加年化 bps 拖累，观察期权腿和 Sharpe 的抗压性。",
        "- 周期集中度：检查期权腿盈亏是否由少数交易周期主导。",
        "",
        f"Phase run status: {status_text}",
        "",
        "## 第三层诊断结论表",
        "",
        md_table(decision[[col for col in main_cols if col in decision.columns]]),
        "",
        "## 输出文件",
        "",
        "- `summary/candidate_third_layer_decision.csv`",
        "- `summary/candidate_natural_sample_summary.csv`",
        "- `phase/candidate_phase_robustness_summary.csv`",
        "- `events/candidate_event_exclusion_summary.csv`",
        "- `cost/candidate_cost_robustness.csv`",
        "- `cycle/candidate_cycle_concentration.csv`",
    ]
    (REPORT_DIR / "candidate_robustness_report.md").write_text("\n".join(lines), encoding="utf-8")


def md_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_No rows._"
    out = df.copy()
    pct_cols = ["annualized_return_cagr", "max_drawdown", "top_3_abs_cycle_pnl_share"]
    num_cols = ["sharpe_daily_mean", "sharpe_p25", "sharpe_std", "event_delta_sharpe", "worst_delta_sharpe_vs_base"]
    for col in out.columns:
        if col in pct_cols:
            out[col] = out[col].map(lambda x: "" if pd.isna(x) else f"{float(x):.2%}")
        elif col in num_cols:
            out[col] = out[col].map(lambda x: "" if pd.isna(x) else f"{float(x):.3f}")
    out = out.fillna("").replace({"nan": "", "NaN": ""})
    return out.to_markdown(index=False)


def _metrics_from_daily_returns(group: pd.DataFrame) -> dict[str, Any]:
    return _metrics_from_returns_frame(group, return_col="daily_return_total", option_col="daily_return_option_leg_component")


def _metrics_from_returns_frame(group: pd.DataFrame, *, return_col: str, option_col: str) -> dict[str, Any]:
    g = group.sort_values("date").copy()
    returns = g[return_col].astype(float).fillna(0.0)
    nav = (1.0 + returns).cumprod()
    metrics = summarize_daily_nav(pd.DataFrame({"date": g["date"].values, "nav": nav.values}), date_col="date", nav_col="nav", rf=0.0)
    metrics["final_nav"] = float(nav.iloc[-1]) if len(nav) else np.nan
    metrics["option_leg_annualized_pnl_contribution"] = compute_portfolio_option_contribution(g[option_col], n_days=len(g))
    return metrics


def _event_dates(events: pd.DataFrame) -> set[str]:
    dates: set[str] = set()
    for _, row in events.iterrows():
        for item in pd.date_range(row["start_date"], row["end_date"], freq="D"):
            dates.add(item.date().isoformat())
    return dates


def _mean(df: pd.DataFrame, column: str) -> float:
    if df.empty or column not in df.columns:
        return np.nan
    series = pd.to_numeric(df[column], errors="coerce").replace(0.0, np.nan)
    return float(series.mean()) if not series.dropna().empty else np.nan


def _top_share(values: pd.Series, n: int) -> float:
    denom = float(values.sum())
    return float(values.sort_values(ascending=False).head(n).sum() / denom) if denom > 0 else np.nan


def _date(value: Any) -> str:
    return pd.Timestamp(value).date().isoformat() if pd.notna(value) else ""


def main() -> None:
    args = parse_args()
    global OUT_ROOT, CONFIG_DIR, DAILY_DIR, PERIOD_DIR, PHASE_DIR, EVENT_DIR, COST_DIR, CYCLE_DIR, SUMMARY_DIR, REPORT_DIR
    OUT_ROOT = args.output_dir.resolve()
    CONFIG_DIR = OUT_ROOT / "config"
    DAILY_DIR = OUT_ROOT / "daily"
    PERIOD_DIR = OUT_ROOT / "period"
    PHASE_DIR = OUT_ROOT / "phase"
    EVENT_DIR = OUT_ROOT / "events"
    COST_DIR = OUT_ROOT / "cost"
    CYCLE_DIR = OUT_ROOT / "cycle"
    SUMMARY_DIR = OUT_ROOT / "summary"
    REPORT_DIR = OUT_ROOT / "reports"
    ensure_dirs()

    candidates = load_selected_candidates()
    daily, period = load_candidate_paths(candidates)
    natural = compute_natural_summary(daily, period, candidates)
    event_config, event_exclusion = evaluate_event_exclusion(daily)
    cost_summary, cost_robustness = evaluate_cost_sensitivity(daily, COST_BPS)
    cycle = compute_cycle_concentration_natural(period)

    write_csv(candidates, CONFIG_DIR / "candidate_robustness_input_candidates.csv")
    write_csv(event_config, CONFIG_DIR / "manual_event_windows.csv")
    write_csv(daily, DAILY_DIR / "candidate_natural_daily_paths.csv")
    write_csv(period, PERIOD_DIR / "candidate_natural_period_paths.csv")
    write_csv(natural, SUMMARY_DIR / "candidate_natural_sample_summary.csv")
    write_csv(event_exclusion, EVENT_DIR / "candidate_event_exclusion_summary.csv")
    write_csv(cost_summary, COST_DIR / "candidate_cost_sensitivity_summary.csv")
    write_csv(cost_robustness, COST_DIR / "candidate_cost_robustness.csv")
    write_csv(cycle, CYCLE_DIR / "candidate_cycle_concentration.csv")

    phase_outputs: dict[str, pd.DataFrame] = {}
    if not args.skip_phase:
        phase_outputs = run_phase_layer(
            candidates,
            project_root=args.project_root.resolve(),
            ver3_root=args.ver3_root.resolve(),
            output_root=PHASE_DIR,
            max_phase_shift=args.max_phase_shift,
            phase_step=args.phase_step,
            strict=args.strict,
        )
        write_csv(phase_outputs["phase_grid"], PHASE_DIR / "candidate_phase_grid.csv")
        write_csv(phase_outputs["run_status"], PHASE_DIR / "candidate_phase_run_status.csv")
        write_csv(phase_outputs["daily_nav"], PHASE_DIR / "candidate_phase_daily_nav.csv")
        write_csv(phase_outputs["daily_returns"], PHASE_DIR / "candidate_phase_daily_returns.csv")
        if not phase_outputs["period_map"].empty:
            write_csv(phase_outputs["period_map"], PHASE_DIR / "candidate_phase_period_map.csv")
        write_csv(phase_outputs["metrics"], PHASE_DIR / "candidate_phase_metrics_by_phase.csv")
        write_csv(phase_outputs["robustness"], PHASE_DIR / "candidate_phase_robustness_summary.csv")
        if not phase_outputs["cycle_concentration"].empty:
            write_csv(phase_outputs["cycle_concentration"], PHASE_DIR / "candidate_phase_cycle_concentration.csv")
        phase_robustness = phase_outputs["robustness"]
        phase_status = phase_outputs["run_status"]
    else:
        phase_robustness = pd.DataFrame(columns=["candidate_id"])
        phase_status = None

    decision = build_decision_table(natural, phase_robustness, event_exclusion, cost_robustness, cycle)
    write_csv(decision, SUMMARY_DIR / "candidate_third_layer_decision.csv")
    write_report(decision, phase_status)
    manifest = {
        "experiment_id": "ver3_1_candidate_robustness",
        "output_root": str(OUT_ROOT),
        "candidate_count": int(len(candidates)),
        "phase_skipped": bool(args.skip_phase),
        "max_phase_shift": int(args.max_phase_shift),
        "phase_step": int(args.phase_step),
        "cost_bps": COST_BPS,
    }
    (OUT_ROOT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"wrote {OUT_ROOT.relative_to(ROOT)}")
    print(f"candidate_count={len(candidates)}")
    if phase_status is not None:
        print(f"phase_success_rate={phase_status['status'].eq('success').mean():.2%}")
    print(decision[["etf_code", "candidate_id", "third_layer_decision", "third_layer_flags"]].to_string(index=False))


if __name__ == "__main__":
    main()
