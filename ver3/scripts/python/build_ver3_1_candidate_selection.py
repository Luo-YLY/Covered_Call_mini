from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]

EXPERIMENT_ROOT = ROOT / "outputs" / "ver3_1_effective_zone_target_delta"
TARGET_GRID_PATH = EXPERIMENT_ROOT / "summary" / "ver3_1_target_delta_surface_grid.csv"
MONEYNESS_GRID_PATH = (
    ROOT
    / "outputs"
    / "ver3_0_stepA_moneyness_refined_daily_mtm_surface"
    / "summary"
    / "ver3_0_stepA_moneyness_refined_daily_mtm_surface_grid.csv"
)

OUT_ROOT = EXPERIMENT_ROOT / "analysis" / "candidate_selection"
SUMMARY_DIR = OUT_ROOT / "summary"
REPORT_DIR = OUT_ROOT / "reports"

MAIN_SAMPLE_START = "2022-09-30"
MAIN_SAMPLE_END = "2026-05-27"
MAIN_EXPECTED_PERIODS = 44
SHORT_EXPECTED_PERIODS = 35

CORE_ETFS = {"510300", "510050"}
SHORT_SAMPLE_ETFS = {"588000"}
DEFENSIVE_ETFS = {"510500", "159915", "588000"}

METRIC_COLUMNS = [
    "annualized_return_cagr",
    "annualized_volatility",
    "sharpe_daily_mean",
    "max_drawdown",
    "option_leg_annualized_pnl_contribution",
    "assignment_rate",
    "selected_periods",
    "skipped_periods",
    "avg_actual_dte",
    "avg_realized_moneyness",
    "p95_short_call_mtm_loss",
    "p99_short_call_mtm_loss",
    "max_short_call_mtm_loss",
]

DISPLAY_COLUMNS = [
    "etf_code",
    "candidate_family",
    "rule_label",
    "coverage_label",
    "sleeve_name",
    "candidate_role",
    "selected_flag",
    "selected_reason",
    "annualized_return_cagr",
    "sharpe_daily_mean",
    "max_drawdown",
    "option_leg_annualized_pnl_contribution",
    "sharpe_diff_vs_buyhold",
    "mdd_improvement_vs_buyhold",
    "cagr_diff_vs_buyhold",
    "assignment_rate",
    "assignment_fraction",
    "effective_short_delta",
    "atm_sharpe_minus_best_d45_d50",
    "atm_mdd_minus_best_d45_d50",
    "local_support_count",
    "warning_flags",
    "rejection_reasons",
]


def ensure_dirs() -> None:
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path.relative_to(ROOT)}")
    return pd.read_csv(path, dtype={"etf_code": str})


def normalize_etf_code(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "etf_code" in out.columns:
        out["etf_code"] = out["etf_code"].astype(str).str.replace(".0", "", regex=False).str.zfill(6)
    return out


def num_series(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype="float64")
    return pd.to_numeric(df[column], errors="coerce")


def build_buyhold_baselines(target_grid: pd.DataFrame, moneyness_grid: pd.DataFrame) -> pd.DataFrame:
    target_buyhold = target_grid[target_grid["parameter_grid_role"].eq("buyhold")].copy()
    fixed_buyhold = moneyness_grid[moneyness_grid["parameter_grid_role"].eq("buyhold")].copy()
    buyhold = pd.concat([target_buyhold, fixed_buyhold], ignore_index=True, sort=False)
    buyhold = normalize_etf_code(buyhold)
    if buyhold.empty:
        raise ValueError("No BuyHold baselines found in target or moneyness grids.")
    buyhold = buyhold.sort_values(["etf_code", "sample_start", "sample_end"]).drop_duplicates("etf_code", keep="first")
    keep = [
        "etf_code",
        "sleeve_name",
        "sample_scope",
        "sample_start",
        "sample_end",
        "annualized_return_cagr",
        "annualized_volatility",
        "sharpe_daily_mean",
        "max_drawdown",
    ]
    buyhold = buyhold[[col for col in keep if col in buyhold.columns]].copy()
    return buyhold.rename(
        columns={
            "sleeve_name": "buyhold_sleeve_name",
            "sample_scope": "buyhold_sample_scope",
            "sample_start": "buyhold_sample_start",
            "sample_end": "buyhold_sample_end",
            "annualized_return_cagr": "buyhold_annualized_return_cagr",
            "annualized_volatility": "buyhold_annualized_volatility",
            "sharpe_daily_mean": "buyhold_sharpe_daily_mean",
            "max_drawdown": "buyhold_max_drawdown",
        }
    )


def normalize_target_delta_candidates(target_grid: pd.DataFrame) -> pd.DataFrame:
    rows = target_grid[target_grid["parameter_grid_role"].eq("target_delta_surface")].copy()
    rows = normalize_etf_code(rows)
    rows["candidate_family"] = "target_delta_surface"
    rows["selector_type"] = "target_delta"
    rows["rule_label"] = rows.get("delta_label", "").astype(str)
    rows["target_delta"] = num_series(rows, "target_delta")
    rows["target_moneyness"] = np.nan
    rows["effective_short_delta"] = rows["target_delta"] * num_series(rows, "coverage")
    rows["candidate_id"] = (
        rows["etf_code"].astype(str)
        + "_TD_"
        + rows["rule_label"].astype(str)
        + "_"
        + rows["coverage_label"].astype(str)
    )
    return rows


def normalize_atm_boundary_candidates(moneyness_grid: pd.DataFrame) -> pd.DataFrame:
    rows = moneyness_grid[
        moneyness_grid["parameter_grid_role"].eq("surface")
        & moneyness_grid["moneyness_label"].astype(str).eq("ATM")
    ].copy()
    rows = normalize_etf_code(rows)
    rows["candidate_family"] = "atm_boundary"
    rows["selector_type"] = "atm_strike"
    rows["rule_label"] = "ATM"
    rows["delta_label"] = pd.NA
    rows["target_delta"] = np.nan
    rows["effective_short_delta"] = np.nan
    rows["candidate_id"] = rows["etf_code"].astype(str) + "_ATM_" + rows["coverage_label"].astype(str)
    return rows


def build_raw_candidate_pool(target_grid: pd.DataFrame, moneyness_grid: pd.DataFrame) -> pd.DataFrame:
    target_rows = normalize_target_delta_candidates(target_grid)
    atm_rows = normalize_atm_boundary_candidates(moneyness_grid)
    candidates = pd.concat([target_rows, atm_rows], ignore_index=True, sort=False)
    candidates = normalize_etf_code(candidates)
    for column in METRIC_COLUMNS + [
        "coverage",
        "target_delta",
        "target_moneyness",
        "effective_short_delta",
        "premium_capture_ratio_agg",
        "payoff_burden_agg",
        "positive_option_leg_period_rate",
    ]:
        candidates[column] = num_series(candidates, column)
    return candidates


def attach_buyhold_context(candidates: pd.DataFrame, buyhold: pd.DataFrame) -> pd.DataFrame:
    out = candidates.merge(buyhold, on="etf_code", how="left")
    out["cagr_diff_vs_buyhold"] = (
        out["annualized_return_cagr"] - pd.to_numeric(out["buyhold_annualized_return_cagr"], errors="coerce")
    )
    out["sharpe_diff_vs_buyhold"] = (
        out["sharpe_daily_mean"] - pd.to_numeric(out["buyhold_sharpe_daily_mean"], errors="coerce")
    )
    out["mdd_improvement_vs_buyhold"] = (
        pd.to_numeric(out["buyhold_max_drawdown"], errors="coerce") - out["max_drawdown"]
    )
    out["vol_reduction_vs_buyhold"] = (
        pd.to_numeric(out["buyhold_annualized_volatility"], errors="coerce") - out["annualized_volatility"]
    )
    return out


def hard_filter_reasons(row: pd.Series) -> list[str]:
    reasons: list[str] = []
    for column in ["annualized_return_cagr", "sharpe_daily_mean", "max_drawdown", "selected_periods"]:
        if pd.isna(row.get(column)):
            reasons.append(f"missing_{column}")
    expected_periods = SHORT_EXPECTED_PERIODS if str(row.get("etf_code")) in SHORT_SAMPLE_ETFS else MAIN_EXPECTED_PERIODS
    selected_periods = row.get("selected_periods")
    if pd.notna(selected_periods) and float(selected_periods) < expected_periods:
        reasons.append(f"incomplete_selected_periods_{int(float(selected_periods))}_lt_{expected_periods}")
    skipped_periods = row.get("skipped_periods")
    if pd.notna(skipped_periods) and float(skipped_periods) > 0:
        reasons.append(f"skipped_periods_{int(float(skipped_periods))}")
    if not str(row.get("sample_start", "")):
        reasons.append("missing_sample_start")
    if not str(row.get("sample_end", "")):
        reasons.append("missing_sample_end")
    return reasons


def attach_hard_filters(candidates: pd.DataFrame) -> pd.DataFrame:
    out = candidates.copy()
    reasons = out.apply(hard_filter_reasons, axis=1)
    out["hard_filter_reasons"] = reasons.map(lambda items: ";".join(items))
    out["hard_filter_pass"] = reasons.map(lambda items: len(items) == 0)
    return out


def attach_atm_neighbor_context(candidates: pd.DataFrame) -> pd.DataFrame:
    out = candidates.copy()
    out["atm_neighbor_best_rule"] = pd.NA
    out["atm_neighbor_best_sharpe"] = np.nan
    out["atm_neighbor_min_mdd"] = np.nan
    out["atm_neighbor_best_option_leg"] = np.nan
    out["atm_sharpe_minus_best_d45_d50"] = np.nan
    out["atm_mdd_minus_best_d45_d50"] = np.nan
    out["atm_option_leg_minus_best_d45_d50"] = np.nan

    target = out[
        out["candidate_family"].eq("target_delta_surface")
        & out["rule_label"].isin(["D45", "D50"])
    ].copy()
    for idx, row in out[out["candidate_family"].eq("atm_boundary")].iterrows():
        peers = target[
            target["etf_code"].eq(row["etf_code"])
            & np.isclose(target["coverage"].astype(float), float(row["coverage"]), atol=1e-9)
        ].copy()
        if peers.empty:
            continue
        best_peer = peers.sort_values(["sharpe_daily_mean", "annualized_return_cagr"], ascending=False).iloc[0]
        min_mdd = float(peers["max_drawdown"].min())
        best_option_leg = float(peers["option_leg_annualized_pnl_contribution"].max())
        out.at[idx, "atm_neighbor_best_rule"] = str(best_peer["rule_label"])
        out.at[idx, "atm_neighbor_best_sharpe"] = float(best_peer["sharpe_daily_mean"])
        out.at[idx, "atm_neighbor_min_mdd"] = min_mdd
        out.at[idx, "atm_neighbor_best_option_leg"] = best_option_leg
        out.at[idx, "atm_sharpe_minus_best_d45_d50"] = float(row["sharpe_daily_mean"]) - float(best_peer["sharpe_daily_mean"])
        out.at[idx, "atm_mdd_minus_best_d45_d50"] = float(row["max_drawdown"]) - min_mdd
        out.at[idx, "atm_option_leg_minus_best_d45_d50"] = (
            float(row["option_leg_annualized_pnl_contribution"]) - best_option_leg
        )
    return out


def attach_local_support(candidates: pd.DataFrame) -> pd.DataFrame:
    out = candidates.copy()
    out["local_support_count"] = 0
    for idx, row in out.iterrows():
        group = out[
            out["etf_code"].eq(row["etf_code"])
            & out["candidate_family"].eq(row["candidate_family"])
            & out["hard_filter_pass"].astype(bool)
        ].copy()
        if group.empty or pd.isna(row.get("sharpe_daily_mean")):
            continue
        if row["candidate_family"] == "target_delta_surface":
            group = group[
                (group["target_delta"] - float(row["target_delta"])).abs().le(0.0500001)
                & (group["coverage"] - float(row["coverage"])).abs().le(0.1000001)
            ]
        else:
            group = group[(group["coverage"] - float(row["coverage"])).abs().le(0.1000001)]
        supported = group[group["sharpe_daily_mean"].ge(float(row["sharpe_daily_mean"]) - 0.06)]
        out.at[idx, "local_support_count"] = int(len(supported))
    return out


def eligibility_labels(row: pd.Series) -> list[str]:
    if not bool(row.get("hard_filter_pass")):
        return []

    labels: list[str] = []
    sharpe_diff = float(row.get("sharpe_diff_vs_buyhold", np.nan))
    mdd_improvement = float(row.get("mdd_improvement_vs_buyhold", np.nan))
    cagr_diff = float(row.get("cagr_diff_vs_buyhold", np.nan))
    option_leg = float(row.get("option_leg_annualized_pnl_contribution", np.nan))
    assignment_rate = float(row.get("assignment_rate", np.nan))
    coverage = float(row.get("coverage", np.nan))
    effective_delta = row.get("effective_short_delta", np.nan)

    dominates_buyhold = sharpe_diff >= 0 and mdd_improvement >= 0 and cagr_diff >= -0.005
    income_logic = option_leg >= 0
    assignment_ok = pd.isna(assignment_rate) or assignment_rate <= 0.65

    if str(row.get("etf_code")) in CORE_ETFS and dominates_buyhold and income_logic and assignment_ok:
        labels.append("income_enhancement_eligible")

    effective_delta_ok = pd.notna(effective_delta) and float(effective_delta) <= 0.15
    atm_light_cover = row.get("candidate_family") == "atm_boundary" and coverage <= 0.20
    if (
        mdd_improvement >= 0.005
        and sharpe_diff >= -0.025
        and cagr_diff >= -0.030
        and option_leg >= -0.030
        and (effective_delta_ok or atm_light_cover)
    ):
        labels.append("defensive_cover_eligible")

    if row.get("candidate_family") == "atm_boundary":
        atm_advantage = row.get("atm_sharpe_minus_best_d45_d50", np.nan)
        atm_mdd_gap = row.get("atm_mdd_minus_best_d45_d50", np.nan)
        if (
            dominates_buyhold
            and income_logic
            and assignment_ok
            and pd.notna(atm_advantage)
            and float(atm_advantage) >= 0.05
            and pd.notna(atm_mdd_gap)
            and float(atm_mdd_gap) <= 0.005
        ):
            labels.append("atm_boundary_exception_eligible")

    if coverage >= 0.90 or (pd.notna(assignment_rate) and assignment_rate >= 0.55):
        labels.append("pressure_reference")

    if str(row.get("etf_code")) in SHORT_SAMPLE_ETFS:
        labels.append("short_sample_research_only")

    return labels


def attach_role_labels(candidates: pd.DataFrame) -> pd.DataFrame:
    out = candidates.copy()
    labels = out.apply(eligibility_labels, axis=1)
    out["eligibility_labels"] = labels.map(lambda items: ";".join(items))
    out["warning_flags"] = out.apply(warning_flags, axis=1)
    out["candidate_role"] = labels.map(primary_role)
    return out


def primary_role(labels: list[str]) -> str:
    if "short_sample_research_only" in labels and any(label.endswith("_eligible") for label in labels):
        return "short_sample_research_candidate"
    for label, role in [
        ("atm_boundary_exception_eligible", "atm_boundary_exception"),
        ("income_enhancement_eligible", "income_enhancement"),
        ("defensive_cover_eligible", "defensive_cover"),
        ("pressure_reference", "pressure_reference"),
        ("short_sample_research_only", "short_sample_research_only"),
    ]:
        if label in labels:
            return role
    return "not_eligible"


def warning_flags(row: pd.Series) -> str:
    flags: list[str] = []
    coverage = row.get("coverage", np.nan)
    assignment_rate = row.get("assignment_rate", np.nan)
    support_count = row.get("local_support_count", np.nan)
    if pd.notna(coverage) and float(coverage) >= 0.90:
        flags.append("high_coverage")
    if pd.notna(assignment_rate) and float(assignment_rate) >= 0.55:
        flags.append("high_assignment")
    if pd.notna(support_count) and int(support_count) <= 1:
        flags.append("weak_local_support")
    if str(row.get("etf_code")) in SHORT_SAMPLE_ETFS:
        flags.append("short_sample")
    return ";".join(flags)


def select_rows_for_etf(group: pd.DataFrame) -> list[tuple[str, pd.Series]]:
    etf_code = str(group["etf_code"].iloc[0])
    hard = group[group["hard_filter_pass"].astype(bool)].copy()
    selections: list[tuple[str, pd.Series]] = []

    def add(label: str, rows: pd.DataFrame, n: int = 1) -> None:
        nonlocal selections
        if rows.empty:
            return
        seen = {str(row["candidate_id"]) for _, row in selections}
        candidates = rows[~rows["candidate_id"].astype(str).isin(seen)].copy()
        for _, selected in candidates.head(n).iterrows():
            selections.append((label, selected))

    if etf_code == "510050":
        atm = hard[hard["eligibility_labels"].str.contains("atm_boundary_exception_eligible", na=False)].copy()
        atm = atm.sort_values(["sharpe_daily_mean", "mdd_improvement_vs_buyhold"], ascending=False)
        add("ATM boundary exception: beats D45/D50 same-coverage neighbor", atm, 2)

        target = hard[
            hard["eligibility_labels"].str.contains("income_enhancement_eligible", na=False)
            & hard["candidate_family"].eq("target_delta_surface")
            & hard["target_delta"].between(0.35, 0.50)
        ].copy()
        target = target.sort_values(["sharpe_daily_mean", "mdd_improvement_vs_buyhold"], ascending=False)
        add("Target-delta income candidate in D35-D50 range", target, 2)
        return selections[:4]

    if etf_code == "510300":
        target = hard[
            hard["eligibility_labels"].str.contains("income_enhancement_eligible", na=False)
            & hard["candidate_family"].eq("target_delta_surface")
            & hard["target_delta"].between(0.35, 0.45)
        ].copy()
        target_best = target.sort_values(["sharpe_daily_mean", "annualized_return_cagr"], ascending=False)
        add("Best target-delta income candidate", target_best, 1)

        balanced = target[target["coverage"].le(0.80)].sort_values(
            ["sharpe_daily_mean", "mdd_improvement_vs_buyhold"], ascending=False
        )
        add("Balanced target-delta candidate with coverage <= Q80", balanced, 1)

        anchor = target[target["rule_label"].eq("D40") & target["coverage_label"].eq("Q70")]
        add("Legacy D40Q70 anchor retained for robustness comparison", anchor, 1)
        return selections[:3]

    if etf_code in DEFENSIVE_ETFS:
        defensive = hard[
            hard["eligibility_labels"].str.contains("defensive_cover_eligible", na=False)
        ].copy()
        if defensive.empty:
            defensive = hard.sort_values(["mdd_improvement_vs_buyhold", "sharpe_daily_mean"], ascending=False)
        defensive = defensive.sort_values(
            ["sharpe_diff_vs_buyhold", "mdd_improvement_vs_buyhold", "annualized_return_cagr"],
            ascending=False,
        )
        label = "Short-sample defensive research candidate" if etf_code in SHORT_SAMPLE_ETFS else "Defensive-cover candidate"
        add(label, defensive, 3)
        return selections[:3]

    fallback = hard.sort_values(["sharpe_daily_mean", "mdd_improvement_vs_buyhold"], ascending=False)
    add("Fallback highest Sharpe candidate", fallback, 2)
    return selections


def attach_selection(candidates: pd.DataFrame) -> pd.DataFrame:
    out = candidates.copy()
    out["selected_flag"] = False
    out["selected_reason"] = ""
    out["selection_order_within_etf"] = np.nan
    for etf_code, group in out.groupby("etf_code", sort=True):
        selections = select_rows_for_etf(group)
        for order, (reason, selected) in enumerate(selections, start=1):
            mask = out["candidate_id"].astype(str).eq(str(selected["candidate_id"]))
            out.loc[mask, "selected_flag"] = True
            out.loc[mask, "selected_reason"] = reason
            out.loc[mask, "selection_order_within_etf"] = order
    out["assignment_count"] = (out["selected_periods"] * out["assignment_rate"]).round()
    out["assignment_fraction"] = out.apply(format_assignment_fraction, axis=1)
    out["rejection_reasons"] = out.apply(rejection_reasons, axis=1)
    return out


def rejection_reasons(row: pd.Series) -> str:
    if bool(row.get("selected_flag")):
        return ""
    reasons: list[str] = []
    hard = str(row.get("hard_filter_reasons", ""))
    if hard:
        reasons.append(f"hard_filter_failed:{hard}")
    labels = str(row.get("eligibility_labels", ""))
    if not labels or labels == "pressure_reference" or labels == "short_sample_research_only":
        reasons.extend(role_rejection_reasons(row))
    elif "pressure_reference" in labels:
        reasons.append("pressure_reference_not_selected")
    if not reasons and bool(row.get("hard_filter_pass")):
        reasons.append("eligible_but_lower_priority_than_selected_candidates")
    return ";".join(dict.fromkeys(reasons))


def role_rejection_reasons(row: pd.Series) -> list[str]:
    reasons: list[str] = []
    if float(row.get("sharpe_diff_vs_buyhold", np.nan)) < 0:
        reasons.append("sharpe_not_above_buyhold")
    if float(row.get("mdd_improvement_vs_buyhold", np.nan)) < 0:
        reasons.append("mdd_not_improved_vs_buyhold")
    if float(row.get("cagr_diff_vs_buyhold", np.nan)) < -0.030:
        reasons.append("cagr_sacrifice_too_large")
    if float(row.get("option_leg_annualized_pnl_contribution", np.nan)) < -0.030:
        reasons.append("option_leg_drag_too_large")
    if row.get("candidate_family") == "atm_boundary":
        atm_advantage = row.get("atm_sharpe_minus_best_d45_d50", np.nan)
        if pd.notna(atm_advantage) and float(atm_advantage) < 0.05:
            reasons.append("atm_does_not_beat_d45_d50_neighbor")
    return reasons or ["fails_role_criteria"]


def format_assignment_fraction(row: pd.Series) -> str:
    periods = row.get("selected_periods", np.nan)
    rate = row.get("assignment_rate", np.nan)
    if pd.isna(periods) or pd.isna(rate) or float(periods) <= 0:
        return ""
    return f"{int(round(float(periods) * float(rate)))}/{int(round(float(periods)))}"


def select_display_columns(df: pd.DataFrame) -> pd.DataFrame:
    columns = [col for col in DISPLAY_COLUMNS if col in df.columns]
    out = df[columns].copy()
    return out


def build_method_summary(candidates: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for etf_code, group in candidates.groupby("etf_code", sort=True):
        rows.append(
            {
                "etf_code": etf_code,
                "total_candidates": int(len(group)),
                "hard_filter_pass": int(group["hard_filter_pass"].sum()),
                "selected_candidates": int(group["selected_flag"].sum()),
                "atm_boundary_candidates": int(group["candidate_family"].eq("atm_boundary").sum()),
                "target_delta_candidates": int(group["candidate_family"].eq("target_delta_surface").sum()),
                "income_eligible": int(group["eligibility_labels"].str.contains("income_enhancement_eligible", na=False).sum()),
                "defensive_eligible": int(group["eligibility_labels"].str.contains("defensive_cover_eligible", na=False).sum()),
                "atm_exception_eligible": int(group["eligibility_labels"].str.contains("atm_boundary_exception_eligible", na=False).sum()),
            }
        )
    return pd.DataFrame(rows)


def fmt_pct(value: Any, digits: int = 2) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value) * 100:.{digits}f}%"


def fmt_num(value: Any, digits: int = 3) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value):.{digits}f}"


def md_table(df: pd.DataFrame, columns: list[str]) -> str:
    if df.empty:
        return "_No rows._"
    data = df[[col for col in columns if col in df.columns]].copy()
    percent_cols = {
        "annualized_return_cagr",
        "max_drawdown",
        "option_leg_annualized_pnl_contribution",
        "mdd_improvement_vs_buyhold",
        "cagr_diff_vs_buyhold",
        "assignment_rate",
    }
    numeric_cols = {
        "sharpe_daily_mean",
        "sharpe_diff_vs_buyhold",
        "effective_short_delta",
        "atm_sharpe_minus_best_d45_d50",
        "atm_mdd_minus_best_d45_d50",
    }
    for col in data.columns:
        if col in percent_cols:
            data[col] = data[col].map(fmt_pct)
        elif col in numeric_cols:
            data[col] = data[col].map(fmt_num)
    return data.to_markdown(index=False)


def write_report(candidates: pd.DataFrame, selected: pd.DataFrame, method: pd.DataFrame) -> None:
    selected_columns = [
        "etf_code",
        "candidate_family",
        "rule_label",
        "coverage_label",
        "candidate_role",
        "annualized_return_cagr",
        "sharpe_daily_mean",
        "max_drawdown",
        "option_leg_annualized_pnl_contribution",
        "assignment_fraction",
        "selected_reason",
    ]
    lines = [
        "# ver3.1 Candidate Selection Layer",
        "",
        "本报告对应第二层择优规则：从 `target-delta x coverage` 曲面与 `ATM boundary` 参照带中筛选可进入第三层稳健性检验的候选 sleeve。",
        "",
        "## 方法口径",
        "",
        "- 主曲面：D25/D30/D35/D40/D45/D50 x Q10-Q100。",
        "- ATM：作为 strike-space boundary 单独进入候选池，不参与 target-delta 曲面插值。",
        "- BuyHold：只作为相对基准，不作为 covered-call 候选。",
        "- 第二层不直接确定最终主线，只输出候选池与剔除原因。",
        "- 588000 使用短样本标签，不能与 2022-09-30 起点主样本同等级比较。",
        "",
        "## 候选池审计",
        "",
        md_table(method, list(method.columns)),
        "",
        "## 入选候选",
        "",
        md_table(selected, selected_columns),
        "",
        "## 510050 ATM 边界说明",
        "",
        "510050 的 ATM boundary 满足独立例外规则：相对同覆盖率 D45/D50 邻域，ATM 具有更高 Sharpe，MDD 不劣于邻域，并且 option leg 为正。因此 ATM_Q90/Q100 被纳入候选池，而不是被当作 D50 的普通格点处理。",
        "",
        "## 输出文件",
        "",
        "- `summary/candidate_pool_all.csv`",
        "- `summary/candidate_pool_selected.csv`",
        "- `summary/candidate_rejection_reasons.csv`",
        "- `summary/candidate_selection_method_summary.csv`",
    ]
    (REPORT_DIR / "candidate_selection_report.md").write_text("\n".join(lines), encoding="utf-8")


def write_outputs(candidates: pd.DataFrame) -> None:
    selected = candidates[candidates["selected_flag"].astype(bool)].copy()
    selected = selected.sort_values(["etf_code", "selection_order_within_etf"])
    rejected = candidates[~candidates["selected_flag"].astype(bool)].copy()
    rejected = rejected[rejected["rejection_reasons"].astype(str).ne("")]
    method = build_method_summary(candidates)

    candidates.to_csv(SUMMARY_DIR / "candidate_pool_all.csv", index=False, encoding="utf-8-sig")
    selected.to_csv(SUMMARY_DIR / "candidate_pool_selected.csv", index=False, encoding="utf-8-sig")
    rejected.to_csv(SUMMARY_DIR / "candidate_rejection_reasons.csv", index=False, encoding="utf-8-sig")
    method.to_csv(SUMMARY_DIR / "candidate_selection_method_summary.csv", index=False, encoding="utf-8-sig")
    write_report(candidates, selected, method)


def build_candidate_selection() -> pd.DataFrame:
    target_grid = normalize_etf_code(read_csv(TARGET_GRID_PATH))
    moneyness_grid = normalize_etf_code(read_csv(MONEYNESS_GRID_PATH))
    buyhold = build_buyhold_baselines(target_grid, moneyness_grid)
    candidates = build_raw_candidate_pool(target_grid, moneyness_grid)
    candidates = attach_buyhold_context(candidates, buyhold)
    candidates = attach_hard_filters(candidates)
    candidates = attach_atm_neighbor_context(candidates)
    candidates = attach_local_support(candidates)
    candidates = attach_role_labels(candidates)
    candidates = attach_selection(candidates)
    candidates = candidates.sort_values(
        ["etf_code", "selected_flag", "selection_order_within_etf", "candidate_family", "coverage", "target_delta"],
        ascending=[True, False, True, True, True, True],
        kind="stable",
    ).reset_index(drop=True)
    return candidates


def main() -> None:
    ensure_dirs()
    candidates = build_candidate_selection()
    write_outputs(candidates)
    selected = candidates[candidates["selected_flag"].astype(bool)]
    print(f"wrote {OUT_ROOT.relative_to(ROOT)}")
    print(f"candidate_rows={len(candidates)} selected_rows={len(selected)}")
    print(
        select_display_columns(selected.sort_values(["etf_code", "selection_order_within_etf"]))
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
