from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / "outputs" / "ver3_0_dashboard_data"
OUT_JS = OUT_DIR / "ver3_dashboard_data.js"
OUT_MANIFEST = OUT_DIR / "manifest.json"

STEP_A = ROOT / "outputs" / "ver3_0_stepA_single_etf_sleeves"
STEP_A_510050 = ROOT / "outputs" / "ver3_0_stepA_extension_510050_sleeve_clarification"
STEP_A_588000 = ROOT / "outputs" / "ver3_0_stepA_extension_588000_sleeve_clarification"
STEP_A_REFINED_SURFACE = ROOT / "outputs" / "ver3_0_stepA_moneyness_refined_daily_mtm_surface"
TARGET_DELTA_SURFACE = ROOT / "outputs" / "ver3_1_effective_zone_target_delta"
TARGET_DELTA_CONTOURS = TARGET_DELTA_SURFACE / "analysis" / "target_delta_surface_contours"
DELTA_VS_MONEYNESS_PHASE = ROOT / "outputs" / "ver3_0_delta_vs_moneyness_phase_sensitivity"
STEP_B = ROOT / "outputs" / "ver3_0_stepB_fixed_weight_universe_comparison"
STEP_B_PLUS = ROOT / "outputs" / "ver3_0_stepB_plus_mdd_constrained_sharpe_frontier"
STEP_C = ROOT / "outputs" / "ver3_0_stepC_robustness_stability_diagnostics"
SUMMARY_REPORT = ROOT / "outputs" / "ver3_0_current_experiment_summary" / "reports" / "ver3_0_current_experiment_summary_report.md"
MAIN_SAMPLE_START = "2022-09-30"
MAIN_SAMPLE_END = "2026-05-27"
MAIN_SAMPLE_N = 881
V31_PRIMARY_CANDIDATE = "B_v31_D20_51030070_51005014_15991516"
V31_MAIN_ETFS = ["510300", "510050", "510500", "159915"]


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def clean_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df.empty:
        return []
    out = df.copy()
    out = out.replace([float("inf"), float("-inf")], pd.NA)
    out = out.where(pd.notna(out), None)
    records = out.to_dict(orient="records")
    for record in records:
        for key, value in list(record.items()):
            if isinstance(value, float) and not math.isfinite(value):
                record[key] = None
    return records


def select_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if df.empty:
        return df
    return df[[col for col in columns if col in df.columns]].copy()


def add_source(df: pd.DataFrame, source_label: str) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out.insert(0, "source_group", source_label)
    return out


def ensure_sample_window(
    df: pd.DataFrame,
    *,
    start: str = MAIN_SAMPLE_START,
    end: str = MAIN_SAMPLE_END,
    n_obs: int = MAIN_SAMPLE_N,
) -> pd.DataFrame:
    """Attach a dashboard-visible backtest window when an artifact omits it."""

    if df.empty:
        return df
    out = df.copy()
    if "sample_start" not in out.columns:
        out["sample_start"] = start
    else:
        out["sample_start"] = out["sample_start"].fillna(start)
    if "sample_end" not in out.columns:
        out["sample_end"] = end
    else:
        out["sample_end"] = out["sample_end"].fillna(end)
    if "n_trading_days" not in out.columns:
        out["n_trading_days"] = n_obs
    else:
        out["n_trading_days"] = out["n_trading_days"].fillna(n_obs)
    if "backtest_period" not in out.columns:
        out["backtest_period"] = out["sample_start"].astype(str) + " to " + out["sample_end"].astype(str)
    return out


def dedupe_sleeve_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Keep one display row for each source/ETF/sleeve in the dashboard."""

    if df.empty:
        return df
    out = df.copy()
    priority = {
        "common_portfolio_sample": 0,
        "covered_call_backtest": 1,
        "full_available_sample_by_etf": 2,
    }
    out["_sample_priority"] = out.get("sample_scope", pd.Series(index=out.index, dtype=object)).map(priority).fillna(9)
    sort_cols = ["source_group", "etf_code", "sleeve_name", "_sample_priority"]
    out = out.sort_values(sort_cols, kind="stable")
    out = out.drop_duplicates(["source_group", "etf_code", "sleeve_name"], keep="first")
    return out.drop(columns=["_sample_priority"]).reset_index(drop=True)


def prepare_refined_surface_grid(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    if "parameter_grid_role" not in df.columns:
        return pd.DataFrame()
    out = df[df["parameter_grid_role"].eq("surface")].copy()
    if out.empty:
        return out
    out["moneyness_axis"] = pd.to_numeric(out.get("target_moneyness"), errors="coerce")
    out["coverage_axis"] = pd.to_numeric(out.get("coverage"), errors="coerce")
    out["coverage"] = out["coverage_axis"]
    out["moneyness_depth"] = out["moneyness_axis"].clip(lower=0)
    out["parameter_depth"] = out["moneyness_depth"] * out["coverage_axis"].fillna(0.0)
    out["selected_periods"] = pd.to_numeric(out.get("selected_periods"), errors="coerce")
    out["assignment_rate"] = pd.to_numeric(out.get("assignment_rate"), errors="coerce")
    out["assignment_count"] = (out["selected_periods"] * out["assignment_rate"]).round()
    out["backtest_period"] = out["sample_start"].astype(str) + " to " + out["sample_end"].astype(str)
    out["source_detail"] = "ver3 Step A refined daily-MTM moneyness x coverage grid"
    if "surface_point_id" not in out.columns:
        out.insert(0, "surface_point_id", [f"refined_surface_{i:04d}" for i in range(1, len(out) + 1)])
    return out


def build_refined_surface_metadata(surface: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "etf_code",
        "available_moneyness_rules",
        "surface_points",
        "sample_scope",
        "sample_start",
        "sample_end",
        "backtest_note",
    ]
    if surface.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for etf_code, group in surface.groupby("etf_code", sort=True):
        ordered = (
            group[["moneyness_label", "moneyness_axis"]]
            .drop_duplicates()
            .sort_values("moneyness_axis")
        )
        rows.append(
            {
                "etf_code": str(etf_code),
                "available_moneyness_rules": " / ".join(ordered["moneyness_label"].astype(str)),
                "surface_points": int(len(group)),
                "sample_scope": str(group["sample_scope"].iloc[0]) if "sample_scope" in group else "",
                "sample_start": str(group["sample_start"].iloc[0]) if "sample_start" in group else "",
                "sample_end": str(group["sample_end"].iloc[0]) if "sample_end" in group else "",
                "backtest_note": "continuous DTE30 daily-MTM refined grid; coverage is scaled on each Q100 selection path",
            }
        )
    return pd.DataFrame(rows, columns=columns)


def prepare_target_delta_surface_grid(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    if "parameter_grid_role" not in df.columns:
        return pd.DataFrame()
    out = df[df["parameter_grid_role"].eq("target_delta_surface")].copy()
    if out.empty:
        return out
    out["target_delta"] = pd.to_numeric(out.get("target_delta"), errors="coerce")
    out["coverage_axis"] = pd.to_numeric(out.get("coverage"), errors="coerce")
    out["coverage"] = out["coverage_axis"]
    out["moneyness_axis"] = out["target_delta"]
    out["moneyness_depth"] = out["target_delta"]
    out["short_call_effective_delta"] = out["target_delta"] * out["coverage_axis"]
    out["parameter_depth"] = out["short_call_effective_delta"]
    out["moneyness_label"] = out.get("delta_label", out["target_delta"].map(lambda value: f"D{int(round(value * 100)):02d}" if pd.notna(value) else "D--"))
    out["selected_periods"] = pd.to_numeric(out.get("selected_periods"), errors="coerce")
    out["assignment_rate"] = pd.to_numeric(out.get("assignment_rate"), errors="coerce")
    out["assignment_count"] = (out["selected_periods"] * out["assignment_rate"]).round()
    out["backtest_period"] = out["sample_start"].astype(str) + " to " + out["sample_end"].astype(str)
    out["source_detail"] = "ver3.1 target-delta x coverage continuous DTE30 daily-MTM grid"
    out["surface_axis_type"] = "target_delta"
    if "surface_point_id" not in out.columns:
        out.insert(0, "surface_point_id", [f"target_delta_surface_{i:04d}" for i in range(1, len(out) + 1)])
    return out


def prepare_target_delta_buyhold_baseline(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "parameter_grid_role" not in df.columns:
        return pd.DataFrame()
    out = df[df["parameter_grid_role"].eq("buyhold")].copy()
    if out.empty:
        return out
    out["etf_code"] = out["etf_code"].astype(str).str.zfill(6)
    out["coverage"] = 0.0
    out["coverage_label"] = "Q0"
    out["moneyness_label"] = "BuyHold"
    out["target_delta"] = pd.NA
    out["moneyness_axis"] = pd.NA
    out["coverage_axis"] = 0.0
    out["moneyness_depth"] = 0.0
    out["parameter_depth"] = 0.0
    out["assignment_count"] = 0
    out["backtest_period"] = out["sample_start"].astype(str) + " to " + out["sample_end"].astype(str)
    out["source_detail"] = "ver3.1 target-delta surface BuyHold baseline"
    out["surface_axis_type"] = "target_delta"
    if "surface_point_id" not in out.columns:
        out.insert(0, "surface_point_id", [f"target_delta_buyhold_{i:04d}" for i in range(1, len(out) + 1)])
    return out


def build_target_delta_surface_metadata(surface: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "etf_code",
        "available_delta_rules",
        "available_moneyness_rules",
        "surface_points",
        "sample_scope",
        "sample_start",
        "sample_end",
        "backtest_note",
    ]
    if surface.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for etf_code, group in surface.groupby("etf_code", sort=True):
        ordered = (
            group[["moneyness_label", "target_delta"]]
            .drop_duplicates()
            .sort_values("target_delta")
        )
        rows.append(
            {
                "etf_code": str(etf_code),
                "available_delta_rules": " / ".join(ordered["moneyness_label"].astype(str)),
                "available_moneyness_rules": " / ".join(ordered["moneyness_label"].astype(str)),
                "surface_points": int(len(group)),
                "sample_scope": str(group["sample_scope"].iloc[0]) if "sample_scope" in group else "",
                "sample_start": str(group["sample_start"].iloc[0]) if "sample_start" in group else "",
                "sample_end": str(group["sample_end"].iloc[0]) if "sample_end" in group else "",
                "backtest_note": "continuous DTE30 daily-MTM target-delta x coverage grid; current main grid uses D10/D20/D30/D40/D50 and Q10-Q100; contour lines use coverage * target_delta as short-call effective delta exposure",
            }
        )
    return pd.DataFrame(rows, columns=columns)


def build_current_sleeve_ranking(refined_raw: pd.DataFrame, delta_metrics: pd.DataFrame) -> pd.DataFrame:
    """Build the dashboard's current single-ETF sleeve ranking contract.

    The main ranking uses the refined fixed-moneyness grid. D40 is kept as a
    target-delta anchor only when an aligned 2022-09-30 daily-MTM row exists.
    TP80 and Touch-K are intentionally absent from this contract.
    """

    columns = [
        "ranking_row_id",
        "etf_code",
        "sleeve_name",
        "source_group",
        "ranking_role",
        "selector_type",
        "moneyness_label",
        "rule_label",
        "coverage",
        "coverage_label",
        "target_moneyness",
        "target_delta",
        "sample_scope",
        "sample_start",
        "sample_end",
        "n_trading_days",
        "backtest_period",
        "annualized_return_cagr",
        "annualized_volatility",
        "sharpe_daily_mean",
        "max_drawdown",
        "option_leg_annualized_pnl_contribution",
        "monthly_win_rate",
        "assignment_rate",
        "selected_periods",
        "avg_realized_moneyness",
        "avg_selected_delta",
        "source_detail",
        "notes",
    ]
    frames: list[pd.DataFrame] = []
    if not refined_raw.empty and "parameter_grid_role" in refined_raw.columns:
        keep = refined_raw[refined_raw["parameter_grid_role"].isin(["surface", "buyhold"])].copy()
        if not keep.empty:
            keep["ranking_role"] = keep["parameter_grid_role"].map(
                {
                    "surface": "fixed_moneyness_grid",
                    "buyhold": "buyhold_baseline",
                }
            )
            keep["selector_type"] = keep["parameter_grid_role"].map(
                {
                    "surface": "fixed_moneyness",
                    "buyhold": "buyhold",
                }
            )
            keep["rule_label"] = keep.get("moneyness_label", "")
            keep["target_delta"] = pd.NA
            keep["avg_selected_delta"] = pd.NA
            keep["source_group"] = keep["ranking_role"].map(
                {
                    "fixed_moneyness_grid": "Fixed moneyness grid",
                    "buyhold_baseline": "BuyHold baseline",
                }
            )
            keep["source_detail"] = keep["ranking_role"].map(
                {
                    "fixed_moneyness_grid": "ver3 refined daily-MTM fixed-moneyness grid",
                    "buyhold_baseline": "ver3 refined daily-MTM ETF baseline",
                }
            )
            keep["notes"] = keep["ranking_role"].map(
                {
                    "fixed_moneyness_grid": "current fixed-moneyness ranking point",
                    "buyhold_baseline": "aligned ETF buy-hold baseline",
                }
            )
            keep["ranking_row_id"] = keep["surface_point_id"].astype(str)
            frames.append(keep)

    if not delta_metrics.empty:
        d40 = delta_metrics.copy()
        required = {"window_mode", "phase_id", "sample_start", "sleeve_name"}
        if required.issubset(d40.columns):
            d40 = d40[
                d40["window_mode"].astype(str).eq("natural")
                & d40["sample_start"].astype(str).eq("2022-09-30")
                & d40["sleeve_name"].astype(str).str.contains("D40_Q70_Hold", regex=False)
            ].copy()
            if not d40.empty:
                d40["ranking_row_id"] = "delta_anchor_" + d40["etf_code"].astype(str) + "_D40_Q70"
                d40["source_group"] = "Delta anchor"
                d40["ranking_role"] = "delta_anchor"
                d40["selector_type"] = "target_delta"
                d40["moneyness_label"] = "D40"
                d40["rule_label"] = "D40"
                d40["coverage_label"] = d40["coverage"].astype(float).map(lambda value: f"Q{int(round(value * 100))}")
                d40["target_moneyness"] = pd.NA
                d40["target_delta"] = 0.40
                d40["avg_realized_moneyness"] = pd.NA
                d40["avg_selected_delta"] = pd.NA
                d40["sample_scope"] = "main_stepA_common_sample"
                d40["source_detail"] = "ver3 target-delta D40 anchor rebuilt on the refined-surface sample start"
                d40["notes"] = "D40 target-delta anchor; excluded from fixed-moneyness surface interpolation"
                frames.append(d40)

    if not frames:
        return pd.DataFrame(columns=columns)
    out = pd.concat(frames, ignore_index=True, sort=False)
    if "backtest_period" not in out.columns:
        out["backtest_period"] = out["sample_start"].astype(str) + " to " + out["sample_end"].astype(str)
    else:
        out["backtest_period"] = out["backtest_period"].fillna(
            out["sample_start"].astype(str) + " to " + out["sample_end"].astype(str)
        )
    out = select_columns(out, columns)
    for col in columns:
        if col not in out.columns:
            out[col] = pd.NA
    out["_role_order"] = out["ranking_role"].map(
        {
            "fixed_moneyness_grid": 0,
            "delta_anchor": 1,
            "buyhold_baseline": 2,
        }
    ).fillna(9)
    out = out.sort_values(["etf_code", "_role_order", "coverage", "target_moneyness", "sleeve_name"], kind="stable")
    return out.drop(columns=["_role_order"]).reset_index(drop=True)


def read_step_a_sleeves() -> pd.DataFrame:
    columns = [
        "source_group",
        "etf_code",
        "sleeve_name",
        "sample_scope",
        "sample_start",
        "sample_end",
        "n_trading_days",
        "annualized_return_cagr",
        "sharpe_daily_mean",
        "annualized_volatility",
        "max_drawdown",
        "calmar_ratio",
        "sortino_ratio",
        "option_leg_annualized_pnl_contribution",
        "monthly_win_rate",
        "assignment_rate",
        "avg_active_coverage",
        "notes",
    ]
    frames = [
        add_source(
            read_csv(STEP_A / "summary" / "ver3_0_stepA_single_etf_sleeve_summary.csv"),
            "主样本",
        ),
        add_source(
            read_csv(STEP_A_510050 / "summary" / "ver3_0_stepA_extension_510050_sleeve_summary.csv"),
            "510050 补充实验",
        ),
        add_source(
            read_csv(STEP_A_588000 / "summary" / "ver3_0_stepA_extension_588000_sleeve_summary.csv"),
            "588000 补充实验",
        ),
    ]
    frames = [select_columns(frame, columns) for frame in frames if not frame.empty]
    if not frames:
        return pd.DataFrame(columns=columns)
    out = dedupe_sleeve_rows(pd.concat(frames, ignore_index=True, sort=False))
    if "sample_start" in out.columns:
        start = pd.to_datetime(out["sample_start"], errors="coerce")
        out = out[start.isna() | (start >= pd.Timestamp(MAIN_SAMPLE_START))].copy()
    return out.reset_index(drop=True)


def drawdowns_from_nav(nav: pd.DataFrame) -> pd.DataFrame:
    if nav.empty:
        return pd.DataFrame(columns=["date", "portfolio_name", "drawdown", "drawdown_magnitude", "rolling_peak_nav"])
    frames = []
    for name, group in nav.groupby("portfolio_name", sort=False):
        out = group[["date", "portfolio_name", "nav"]].copy()
        out = out.sort_values("date")
        out["rolling_peak_nav"] = out["nav"].astype(float).cummax()
        out["drawdown"] = out["nav"].astype(float) / out["rolling_peak_nav"] - 1.0
        out["drawdown_magnitude"] = -out["drawdown"]
        frames.append(out[["date", "portfolio_name", "drawdown", "drawdown_magnitude", "rolling_peak_nav"]])
    return pd.concat(frames, ignore_index=True, sort=False)


def parse_sleeve_set(value: Any) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in str(value or "").split("|"):
        if ":" not in item:
            continue
        etf_code, sleeve_name = item.split(":", 1)
        mapping[etf_code.strip()] = sleeve_name.strip()
    return mapping


def build_portfolio_weight_rows(portfolios: pd.DataFrame) -> pd.DataFrame:
    columns = ["portfolio_name", "etf_code", "sleeve_name", "weight"]
    if portfolios.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for _, row in portfolios.iterrows():
        sleeve_map = parse_sleeve_set(row.get("sleeve_set"))
        for etf_code in V31_MAIN_ETFS:
            weight = pd.to_numeric(row.get(f"weight_{etf_code}"), errors="coerce")
            if pd.isna(weight) or float(weight) <= 0:
                continue
            rows.append(
                {
                    "portfolio_name": row.get("portfolio_name"),
                    "etf_code": etf_code,
                    "sleeve_name": sleeve_map.get(etf_code, ""),
                    "weight": float(weight),
                }
            )
    return pd.DataFrame(rows, columns=columns)


def build_frontier_daily_nav(frontier: pd.DataFrame, sleeve_daily: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    columns = ["date", "portfolio_name", "nav", "daily_return", "option_leg_return"]
    if frontier.empty or sleeve_daily.empty:
        empty = pd.DataFrame(columns=columns)
        return empty, drawdowns_from_nav(empty)
    data = sleeve_daily.copy()
    data["etf_code"] = data["etf_code"].astype(str).str.zfill(6)
    data["sleeve_key"] = data["etf_code"] + "|" + data["sleeve_name"].astype(str)
    return_panel = data.pivot_table(
        index="date",
        columns="sleeve_key",
        values="daily_return_total",
        aggfunc="first",
    ).sort_index()
    option_panel = data.pivot_table(
        index="date",
        columns="sleeve_key",
        values="daily_return_option_leg_component",
        aggfunc="first",
    ).reindex(return_panel.index)

    frames = []
    feasible = frontier[frontier.get("frontier_status", "").astype(str).eq("feasible")].copy()
    for _, row in feasible.iterrows():
        sleeve_map = parse_sleeve_set(row.get("sleeve_set"))
        weighted_returns = pd.Series(0.0, index=return_panel.index)
        weighted_option = pd.Series(0.0, index=return_panel.index)
        used_weight = 0.0
        for etf_code in V31_MAIN_ETFS:
            weight = pd.to_numeric(row.get(f"weight_{etf_code}"), errors="coerce")
            if pd.isna(weight) or float(weight) <= 0:
                continue
            key = f"{etf_code}|{sleeve_map.get(etf_code, '')}"
            if key not in return_panel.columns:
                continue
            weighted_returns = weighted_returns.add(return_panel[key].astype(float).fillna(0.0) * float(weight), fill_value=0.0)
            weighted_option = weighted_option.add(option_panel[key].astype(float).fillna(0.0) * float(weight), fill_value=0.0)
            used_weight += float(weight)
        if used_weight <= 0:
            continue
        out = pd.DataFrame(
            {
                "date": return_panel.index,
                "portfolio_name": row["portfolio_name"],
                "nav": (1.0 + weighted_returns).cumprod().to_numpy(),
                "daily_return": weighted_returns.to_numpy(),
                "option_leg_return": weighted_option.to_numpy(),
            }
        )
        frames.append(out)
    nav = pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame(columns=columns)
    return nav, drawdowns_from_nav(nav)


def build_v31_mainline_payload(
    frontier: pd.DataFrame,
    fixed_summary: pd.DataFrame,
    sleeve_daily: pd.DataFrame,
    dynamic_summary: pd.DataFrame,
    dynamic_same_sample: pd.DataFrame,
) -> dict[str, Any]:
    if frontier.empty:
        return {
            "full_sample": [],
            "candidate_weights": [],
            "daily_nav": [],
            "drawdowns": [],
            "recommendations": [],
            "fixed_weight_summary": clean_records(fixed_summary),
            "frontier": [],
            "dynamic_summary": clean_records(dynamic_summary),
            "dynamic_same_sample": clean_records(dynamic_same_sample),
        }
    main = frontier[frontier.get("frontier_status", "").astype(str).eq("feasible")].copy()
    main["role"] = main["portfolio_name"].astype(str).map(
        lambda name: "3.1 main MDD-budget candidate" if name == V31_PRIMARY_CANDIDATE else "3.1 MDD-budget comparison"
    )
    main["portfolio_type"] = "mdd_budget_optimized"
    main["sample_scope"] = "ver3.1 target-delta mainline sample"
    main["backtest_period"] = main["sample_start"].astype(str) + " to " + main["sample_end"].astype(str)
    nav, drawdowns = build_frontier_daily_nav(main, sleeve_daily)
    weights = build_portfolio_weight_rows(main)
    recommendations = main[main["portfolio_name"].astype(str).eq(V31_PRIMARY_CANDIDATE)].copy()
    if recommendations.empty:
        recommendations = main.sort_values(["universe_short", "D_star"], kind="stable").head(1).copy()
    return {
        "full_sample": clean_records(main),
        "candidate_weights": clean_records(weights),
        "daily_nav": clean_records(nav),
        "drawdowns": clean_records(drawdowns),
        "recommendations": clean_records(recommendations),
        "fixed_weight_summary": clean_records(fixed_summary),
        "frontier": clean_records(frontier),
        "dynamic_summary": clean_records(dynamic_summary),
        "dynamic_same_sample": clean_records(dynamic_same_sample),
    }


def read_single_etf_buyhold_nav() -> pd.DataFrame:
    frames = []
    sources = [
        read_csv(STEP_A / "daily" / "ver3_0_stepA_single_etf_sleeve_daily_nav.csv"),
        read_csv(STEP_A_510050 / "daily" / "ver3_0_stepA_extension_510050_sleeve_daily_nav.csv"),
    ]
    for source in sources:
        if source.empty:
            continue
        for etf_code in ["510300", "510050", "510500", "159915"]:
            sleeve_name = f"{etf_code}_ETF_BuyHold"
            mask = source["etf_code"].astype(str).eq(etf_code) & source["sleeve_name"].astype(str).eq(sleeve_name)
            data = source.loc[mask, ["date", "etf_code", "sleeve_name", "nav_total"]].copy()
            if data.empty:
                continue
            data = data[pd.to_datetime(data["date"], errors="coerce") >= pd.Timestamp(MAIN_SAMPLE_START)].copy()
            if data.empty:
                continue
            data = data.sort_values("date")
            data["portfolio_name"] = f"{etf_code}_ETF_BuyHold"
            base_nav = float(data["nav_total"].astype(float).iloc[0])
            data["nav"] = data["nav_total"].astype(float) / base_nav
            data["comparison_type"] = "single_etf_buyhold"
            frames.append(data[["date", "portfolio_name", "comparison_type", "etf_code", "sleeve_name", "nav"]])
    if not frames:
        return pd.DataFrame(columns=["date", "portfolio_name", "comparison_type", "etf_code", "sleeve_name", "nav"])
    out = pd.concat(frames, ignore_index=True, sort=False)
    return out.drop_duplicates(["date", "portfolio_name"], keep="first")


def build_overview_comparisons(step_b_summary: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    step_b_nav = read_csv(STEP_B / "daily" / "ver3_0_stepB_portfolio_daily_nav.csv")
    step_b_drawdown = read_csv(STEP_B / "daily" / "ver3_0_stepB_portfolio_drawdowns.csv")

    pure_names: set[str] = set()
    if not step_b_summary.empty and "portfolio_type" in step_b_summary.columns:
        pure_names = set(step_b_summary.loc[step_b_summary["portfolio_type"].eq("Pure_ETF"), "portfolio_name"].astype(str))

    pure_nav = pd.DataFrame()
    if not step_b_nav.empty and pure_names:
        pure_nav = step_b_nav[step_b_nav["portfolio_name"].astype(str).isin(pure_names)].copy()
        pure_nav["comparison_type"] = "pure_etf_fixed_weight"
        pure_nav = select_columns(
            pure_nav,
            ["date", "portfolio_name", "comparison_type", "universe_short", "portfolio_type", "weight_scheme", "nav"],
        )

    pure_drawdown = pd.DataFrame()
    if not step_b_drawdown.empty and pure_names:
        pure_drawdown = step_b_drawdown[step_b_drawdown["portfolio_name"].astype(str).isin(pure_names)].copy()
        pure_drawdown["comparison_type"] = "pure_etf_fixed_weight"
        pure_drawdown = select_columns(
            pure_drawdown,
            ["date", "portfolio_name", "comparison_type", "drawdown", "drawdown_magnitude", "rolling_peak_nav"],
        )

    single_nav = read_single_etf_buyhold_nav()
    single_drawdown = drawdowns_from_nav(single_nav)
    if not single_drawdown.empty:
        single_drawdown["comparison_type"] = "single_etf_buyhold"

    nav_frames = [frame for frame in [pure_nav, single_nav] if not frame.empty]
    dd_frames = [frame for frame in [pure_drawdown, single_drawdown] if not frame.empty]
    comparison_nav = pd.concat(nav_frames, ignore_index=True, sort=False) if nav_frames else pd.DataFrame()
    comparison_drawdown = pd.concat(dd_frames, ignore_index=True, sort=False) if dd_frames else pd.DataFrame()

    options = []
    if not step_b_summary.empty:
        pure = step_b_summary[step_b_summary["portfolio_type"].eq("Pure_ETF")].copy()
        pure["_order_universe"] = pure["universe_short"].map({"B": 0, "A": 1}).fillna(9)
        pure["_order_weight"] = pure["weight_scheme"].map({"70_20_10": 0, "50_30_20": 1, "40_40_20": 2}).fillna(9)
        for _, row in pure.sort_values(["_order_universe", "_order_weight"]).iterrows():
            scheme = str(row["weight_scheme"]).replace("_", "/")
            universe = str(row["universe_short"])
            key = str(row["portfolio_name"])
            options.append(
                {
                    "key": key,
                    "label": f"{universe}组 纯ETF {scheme}",
                    "group": "Pure ETF fixed-weight",
                    "default_selected": key == "B_Pure_ETF_70_20_10",
                }
            )
    for etf_code in ["510300", "510050", "510500", "159915"]:
        key = f"{etf_code}_ETF_BuyHold"
        if not comparison_nav.empty and comparison_nav["portfolio_name"].astype(str).eq(key).any():
            options.append(
                {
                    "key": key,
                    "label": f"{etf_code} 裸持ETF",
                    "group": "Single ETF buy-hold",
                    "default_selected": key == "510300_ETF_BuyHold",
                }
            )

    return pd.DataFrame(options), comparison_nav, comparison_drawdown


def build_payload() -> dict[str, Any]:
    step_a_sleeves = read_step_a_sleeves()
    step_a_588000_window = read_csv(
        STEP_A_588000 / "summary" / "ver3_0_stepA_extension_588000_sample_window_summary.csv"
    )
    if not step_a_588000_window.empty and "window_name" in step_a_588000_window.columns:
        mask = step_a_588000_window["window_name"].astype(str).eq("main_stepA_sample")
        step_a_588000_window.loc[mask, "start_date"] = MAIN_SAMPLE_START
        step_a_588000_window.loc[mask, "source"] = "ver3 Step A current common sample"
        step_a_588000_window.loc[mask, "note"] = "588000 should not shorten the 2022-09-30 aligned main sample."
    step_a_refined_surface_raw = read_csv(
        STEP_A_REFINED_SURFACE / "summary" / "ver3_0_stepA_moneyness_refined_daily_mtm_surface_grid.csv"
    )
    step_a_refined_surface_grid = prepare_refined_surface_grid(step_a_refined_surface_raw)
    step_a_refined_surface_metadata = build_refined_surface_metadata(step_a_refined_surface_grid)
    step_a_refined_surface_figures = read_csv(
        STEP_A_REFINED_SURFACE / "summary" / "ver3_0_stepA_moneyness_refined_daily_mtm_figures.csv"
    )
    target_delta_surface_raw = read_csv(
        TARGET_DELTA_SURFACE / "summary" / "ver3_1_target_delta_surface_grid.csv"
    )
    target_delta_surface_grid = prepare_target_delta_surface_grid(target_delta_surface_raw)
    target_delta_surface_buyhold = prepare_target_delta_buyhold_baseline(target_delta_surface_raw)
    target_delta_surface_metadata = build_target_delta_surface_metadata(target_delta_surface_grid)
    target_delta_surface_figures = read_csv(
        TARGET_DELTA_CONTOURS / "summary" / "target_delta_surface_contour_figure_index.csv"
    )
    target_delta_candidate_pool = read_csv(
        TARGET_DELTA_SURFACE / "summary" / "ver3_1_candidate_pool.csv"
    )
    portfolio_sleeve_selection = read_csv(
        TARGET_DELTA_SURFACE / "summary" / "ver3_1_portfolio_sleeve_selection.csv"
    )
    step_a_moneyness_coverage_3d = pd.DataFrame()
    step_a_parameter_surface_grid = step_a_refined_surface_grid
    step_a_parameter_surface_metadata = step_a_refined_surface_metadata
    step_a_parameter_surface_figures = pd.DataFrame()
    step_a_parameter_surface_best = pd.DataFrame()
    delta_vs_moneyness_metrics = read_csv(
        DELTA_VS_MONEYNESS_PHASE / "summary" / "ver3_0_delta_vs_moneyness_metrics_by_phase.csv"
    )
    step_a_sleeve_ranking_current = build_current_sleeve_ranking(
        step_a_refined_surface_raw,
        delta_vs_moneyness_metrics,
    )

    step_b_summary = ensure_sample_window(read_csv(STEP_B / "summary" / "ver3_0_stepB_portfolio_summary.csv"))
    step_b_selected_vs_pure = ensure_sample_window(read_csv(STEP_B / "summary" / "ver3_0_stepB_selected_vs_pure_baseline.csv"))
    step_b_universe_compare = ensure_sample_window(read_csv(STEP_B / "summary" / "ver3_0_stepB_universeA_vs_universeB_comparison.csv"))
    comparison_options, comparison_nav, comparison_drawdown = build_overview_comparisons(step_b_summary)

    step_b_plus_default = ensure_sample_window(read_csv(STEP_B_PLUS / "summary" / "ver3_0_stepB_plus_frontier_summary_default.csv"))
    step_b_plus_relaxed = ensure_sample_window(read_csv(STEP_B_PLUS / "summary" / "ver3_0_stepB_plus_frontier_summary_relaxed.csv"))
    step_b_plus_weights = ensure_sample_window(read_csv(STEP_B_PLUS / "summary" / "ver3_0_stepB_plus_best_weights_by_drawdown_target.csv"))
    step_b_plus_universe = ensure_sample_window(
        read_csv(STEP_B_PLUS / "summary" / "ver3_0_stepB_plus_universeA_vs_universeB_frontier_comparison.csv")
    )
    step_b_plus_window = read_csv(STEP_B_PLUS / "summary" / "ver3_0_stepB_plus_sample_window_summary.csv")
    if not step_b_plus_window.empty and "window_name" in step_b_plus_window.columns:
        mask = step_b_plus_window["window_name"].astype(str).eq("requested_main_stepB_plus_sample")
        step_b_plus_window.loc[mask, "sample_start"] = MAIN_SAMPLE_START
        step_b_plus_window.loc[mask, "note"] = "Current dashboard uses the aligned common sample start."

    step_c_weights = read_csv(STEP_C / "config" / "ver3_0_stepC_candidate_weights.csv")
    step_c_full = ensure_sample_window(read_csv(STEP_C / "summary" / "ver3_0_stepC_candidate_full_sample_summary.csv"))
    step_c_score = ensure_sample_window(read_csv(STEP_C / "summary" / "ver3_0_stepC_stability_scorecard.csv"))
    step_c_recommend = ensure_sample_window(read_csv(STEP_C / "summary" / "ver3_0_stepC_recommended_candidate_table.csv"))
    step_c_validation = read_csv(STEP_C / "summary" / "ver3_0_stepC_validation_summary.csv")
    step_c_daily_nav = read_csv(STEP_C / "daily" / "ver3_0_stepC_candidate_daily_nav.csv")
    step_c_drawdowns = read_csv(STEP_C / "daily" / "ver3_0_stepC_candidate_drawdowns.csv")
    step_c_rolling_252 = read_csv(STEP_C / "rolling" / "ver3_0_stepC_rolling_252d_metrics.csv")
    step_c_rolling_504 = read_csv(STEP_C / "rolling" / "ver3_0_stepC_rolling_504d_metrics.csv")
    step_c_rolling_summary = ensure_sample_window(read_csv(STEP_C / "rolling" / "ver3_0_stepC_rolling_stability_summary.csv"))
    step_c_events = ensure_sample_window(read_csv(STEP_C / "events" / "ver3_0_stepC_event_exclusion_summary.csv"))
    step_c_cost = ensure_sample_window(read_csv(STEP_C / "cost" / "ver3_0_stepC_cost_sensitivity_summary.csv"))
    step_c_cost_robust = ensure_sample_window(read_csv(STEP_C / "cost" / "ver3_0_stepC_option_leg_cost_robustness.csv"))

    v31_fixed_summary = ensure_sample_window(
        read_csv(TARGET_DELTA_SURFACE / "portfolio" / "ver3_1_fixed_weight_summary.csv")
    )
    v31_frontier = ensure_sample_window(
        read_csv(TARGET_DELTA_SURFACE / "portfolio" / "ver3_1_mdd_frontier_best_by_dstar.csv")
    )
    v31_sleeve_daily = read_csv(TARGET_DELTA_SURFACE / "daily" / "ver3_1_selected_sleeve_daily_panel.csv")
    v31_dynamic_summary = read_csv(TARGET_DELTA_SURFACE / "dynamic" / "ver3_1_dynamic_strategy_summary.csv")
    v31_dynamic_same_sample = read_csv(TARGET_DELTA_SURFACE / "dynamic" / "ver3_1_dynamic_vs_same_sample_static.csv")
    v31_mainline = build_v31_mainline_payload(
        v31_frontier,
        v31_fixed_summary,
        v31_sleeve_daily,
        v31_dynamic_summary,
        v31_dynamic_same_sample,
    )

    primary = V31_PRIMARY_CANDIDATE
    if v31_frontier.empty or not v31_frontier["portfolio_name"].astype(str).eq(V31_PRIMARY_CANDIDATE).any():
        if not step_c_recommend.empty and "portfolio_name" in step_c_recommend.columns:
            primary = str(step_c_recommend.iloc[0]["portfolio_name"])

    payload = {
        "generated_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
        "experiment_id": "ver3_1_dashboard",
        "primary_candidate": primary,
        "sample": {
            "start": MAIN_SAMPLE_START,
            "end": MAIN_SAMPLE_END,
            "n_obs": MAIN_SAMPLE_N,
        },
        "source_paths": {
            "summary_report": str(SUMMARY_REPORT.relative_to(ROOT)),
            "stepA": str(STEP_A.relative_to(ROOT)),
            "stepA_moneyness_refined_daily_mtm": str(STEP_A_REFINED_SURFACE.relative_to(ROOT)),
            "stepA_target_delta_surface": str(TARGET_DELTA_SURFACE.relative_to(ROOT)),
            "delta_vs_moneyness_phase": str(DELTA_VS_MONEYNESS_PHASE.relative_to(ROOT)),
            "stepB": str(STEP_B.relative_to(ROOT)),
            "stepB_plus": str(STEP_B_PLUS.relative_to(ROOT)),
            "stepC": str(STEP_C.relative_to(ROOT)),
            "ver3_1_target_delta_mainline": str(TARGET_DELTA_SURFACE.relative_to(ROOT)),
        },
        "figure_paths": {
            "nav": str((STEP_C / "figures" / "ver3_0_stepC_candidate_nav_curves.png").relative_to(ROOT)),
            "drawdown": str((STEP_C / "figures" / "ver3_0_stepC_candidate_drawdown_curves.png").relative_to(ROOT)),
            "rolling_sharpe": str((STEP_C / "figures" / "ver3_0_stepC_rolling_sharpe.png").relative_to(ROOT)),
            "rolling_mdd": str((STEP_C / "figures" / "ver3_0_stepC_rolling_mdd.png").relative_to(ROOT)),
            "cost": str((STEP_C / "figures" / "ver3_0_stepC_cost_sensitivity.png").relative_to(ROOT)),
            "stability": str((STEP_C / "figures" / "ver3_0_stepC_stability_scorecard.png").relative_to(ROOT)),
        },
        "stepA": {
            "sleeves": clean_records(step_a_sleeves),
            "sample_588000": clean_records(step_a_588000_window),
            "moneyness_coverage_3d": clean_records(step_a_moneyness_coverage_3d),
            "parameter_surface_grid": clean_records(step_a_parameter_surface_grid),
            "parameter_surface_metadata": clean_records(step_a_parameter_surface_metadata),
            "parameter_surface_figures": clean_records(step_a_parameter_surface_figures),
            "parameter_surface_best_points": clean_records(step_a_parameter_surface_best),
            "moneyness_refined_surface_grid": clean_records(step_a_refined_surface_grid),
            "moneyness_refined_surface_metadata": clean_records(step_a_refined_surface_metadata),
            "moneyness_refined_surface_figures": clean_records(step_a_refined_surface_figures),
            "target_delta_surface_grid": clean_records(target_delta_surface_grid),
            "target_delta_surface_buyhold": clean_records(target_delta_surface_buyhold),
            "target_delta_surface_metadata": clean_records(target_delta_surface_metadata),
            "target_delta_surface_figures": clean_records(target_delta_surface_figures),
            "target_delta_candidate_pool": clean_records(target_delta_candidate_pool),
            "portfolio_sleeve_selection": clean_records(portfolio_sleeve_selection),
            "sleeve_ranking_current": clean_records(step_a_sleeve_ranking_current),
        },
        "stepB": {
            "portfolio_summary": v31_mainline["fixed_weight_summary"] or clean_records(step_b_summary),
            "legacy_portfolio_summary": clean_records(step_b_summary),
            "selected_vs_pure": clean_records(step_b_selected_vs_pure),
            "legacy_selected_vs_pure": clean_records(step_b_selected_vs_pure),
            "universe_comparison": clean_records(step_b_universe_compare),
        },
        "overviewComparisons": {
            "options": clean_records(comparison_options),
            "daily_nav": clean_records(comparison_nav),
            "drawdowns": clean_records(comparison_drawdown),
        },
        "stepBPlus": {
            "frontier_default": v31_mainline["frontier"] or clean_records(step_b_plus_default),
            "frontier_relaxed": [],
            "legacy_frontier_default": clean_records(step_b_plus_default),
            "legacy_frontier_relaxed": clean_records(step_b_plus_relaxed),
            "best_weights": clean_records(step_b_plus_weights),
            "universe_comparison": clean_records(step_b_plus_universe),
            "sample_window": clean_records(step_b_plus_window),
        },
        "mainLine": v31_mainline,
        "stepD": {
            "dynamic_summary": v31_mainline["dynamic_summary"],
            "dynamic_same_sample": v31_mainline["dynamic_same_sample"],
        },
        "stepC": {
            "candidate_weights": clean_records(step_c_weights),
            "full_sample": clean_records(step_c_full),
            "stability_scorecard": clean_records(step_c_score),
            "recommendations": clean_records(step_c_recommend),
            "validation": clean_records(step_c_validation),
            "daily_nav": clean_records(step_c_daily_nav),
            "drawdowns": clean_records(step_c_drawdowns),
            "rolling_252": clean_records(step_c_rolling_252),
            "rolling_504": clean_records(step_c_rolling_504),
            "rolling_summary": clean_records(step_c_rolling_summary),
            "event_exclusion": clean_records(step_c_events),
            "cost_sensitivity": clean_records(step_c_cost),
            "cost_robustness": clean_records(step_c_cost_robust),
        },
    }
    return payload


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_payload()
    OUT_JS.write_text(
        "window.VER3_DASHBOARD_DATA = "
        + json.dumps(payload, ensure_ascii=False, allow_nan=False)
        + ";\n",
        encoding="utf-8",
    )
    OUT_MANIFEST.write_text(
        json.dumps(
            {
                "experiment_id": payload["experiment_id"],
                "generated_at": payload["generated_at"],
                "data_file": str(OUT_JS.relative_to(ROOT)),
                "primary_candidate": payload["primary_candidate"],
                "sample": payload["sample"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {OUT_JS}")
    print(f"Wrote {OUT_MANIFEST}")


if __name__ == "__main__":
    main()
