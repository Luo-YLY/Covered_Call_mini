from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd

from src.metrics.ver2_metric_standard import summarize_daily_nav

from .config import DiagnosticConfig


def compute_actual_effective_delta(period_detail: pd.DataFrame, config: DiagnosticConfig) -> pd.DataFrame:
    """Summarize realized entry delta and realized effective delta tracking."""

    if period_detail.empty:
        return pd.DataFrame()
    rows = []
    for keys, group in period_detail.groupby(["etf_code", "implementation_name"]):
        etf_code, implementation_name = keys
        selected = group[group["option_selected_flag"].astype(int).eq(1)].copy()
        actual_delta = pd.to_numeric(selected["actual_entry_delta"], errors="coerce").dropna()
        actual_eff = pd.to_numeric(selected["actual_effective_delta"], errors="coerce").dropna()
        first = group.iloc[0]
        rows.append(
            {
                "etf_code": etf_code,
                "implementation_name": implementation_name,
                "target_effective_delta": config.target_effective_delta,
                "target_call_delta": float(first["target_call_delta"]),
                "coverage": float(first["coverage"]),
                "expected_overlay_delta": float(first["expected_overlay_delta"]),
                "expected_effective_delta": float(first["expected_effective_delta"]),
                "actual_entry_delta_mean": _mean(actual_delta),
                "actual_entry_delta_median": _median(actual_delta),
                "actual_entry_delta_std": _std(actual_delta),
                "actual_effective_delta_mean": _mean(actual_eff),
                "actual_effective_delta_median": _median(actual_eff),
                "actual_effective_delta_std": _std(actual_eff),
                "actual_effective_delta_min": _min(actual_eff),
                "actual_effective_delta_max": _max(actual_eff),
                "effective_delta_tracking_error": _mean(actual_eff) - config.target_effective_delta
                if len(actual_eff)
                else np.nan,
                "selected_periods": int(len(selected)),
                "total_periods": int(len(group)),
            }
        )
    return pd.DataFrame(rows)


def compute_performance_metrics(
    daily_nav: pd.DataFrame,
    tracking_summary: pd.DataFrame,
    option_quality: pd.DataFrame,
    mtm_stress: pd.DataFrame,
    config: DiagnosticConfig,
) -> pd.DataFrame:
    """Compute the core summary table required by the diagnostic."""

    rows = []
    for keys, group in daily_nav.groupby(["etf_code", "implementation_name"]):
        etf_code, implementation_name = keys
        sample = group.sort_values("date").copy()
        metrics = summarize_daily_nav(sample[["date", "nav"]], date_col="date", nav_col="nav", rf=config.rf)
        first_tracking = _first_match(tracking_summary, etf_code, implementation_name)
        first_quality = _first_match(option_quality, etf_code, implementation_name)
        first_stress = _first_match(mtm_stress, etf_code, implementation_name)
        row = {
            "etf_code": etf_code,
            "implementation_name": implementation_name,
            **first_tracking,
            **metrics,
            **first_quality,
            **first_stress,
            "final_nav": float(sample["nav"].iloc[-1]) if not sample.empty else np.nan,
            "source_engine": "ver2_downside_protection.continuous_30d_daily_mtm",
        }
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["etf_code", "implementation_name"]).reset_index(drop=True)


def compute_pairwise_implementation_comparison(summary: pd.DataFrame) -> pd.DataFrame:
    """Compare implementations pairwise inside each ETF without declaring a winner."""

    rows = []
    for etf_code, group in summary.groupby("etf_code"):
        lookup = {str(row["implementation_name"]): row for _, row in group.iterrows()}
        for left, right in combinations(sorted(lookup), 2):
            a = lookup[left]
            b = lookup[right]
            rows.append(
                {
                    "etf_code": etf_code,
                    "left_implementation": left,
                    "right_implementation": right,
                    "delta_cagr_left_minus_right": _diff(a, b, "annualized_return_cagr"),
                    "delta_sharpe_left_minus_right": _diff(a, b, "sharpe_daily_mean"),
                    "delta_vol_left_minus_right": _diff(a, b, "annualized_volatility"),
                    "delta_mdd_left_minus_right": _diff(a, b, "max_drawdown"),
                    "delta_option_leg_left_minus_right": _diff(a, b, "option_leg_annualized_pnl_contribution"),
                    "delta_premium_capture_left_minus_right": _diff(a, b, "premium_capture_ratio_agg"),
                    "delta_payoff_burden_left_minus_right": _diff(a, b, "payoff_burden_agg"),
                    "delta_p99_mtm_stress_left_minus_right": _diff(a, b, "p99_short_call_mtm_loss"),
                    "delta_tracking_error_abs_left_minus_right": abs(float(a["effective_delta_tracking_error"]))
                    - abs(float(b["effective_delta_tracking_error"])),
                }
            )
    return pd.DataFrame(rows)


def build_recommendation_diagnostic(summary: pd.DataFrame, phase_summary: pd.DataFrame) -> pd.DataFrame:
    """Build qualitative appendix/mainline support diagnostics, not a score."""

    rows = []
    phase_lookup = {}
    if not phase_summary.empty:
        phase_lookup = {
            (str(row["etf_code"]), str(row["implementation_name"])): row
            for _, row in phase_summary.iterrows()
        }
    for etf_code, group in summary.groupby("etf_code"):
        d40 = _row_by_name(group, "D40_Q70")
        d28 = _row_by_name(group, "D28_Q100")
        d35 = _row_by_name(group, "D35_Q80")
        if d40.empty:
            continue
        best_sharpe = float(group["sharpe_daily_mean"].max())
        lowest_mdd = float(group["max_drawdown"].min())
        d40_row = d40.iloc[0]
        d28_row = d28.iloc[0] if not d28.empty else None
        d35_row = d35.iloc[0] if not d35.empty else None
        d40_phase = phase_lookup.get((etf_code, "D40_Q70"))
        phase_note = "phase-lite unavailable"
        if d40_phase is not None:
            phase_note = (
                f"phase median Sharpe {float(d40_phase['phase_lite_sharpe_median']):.3f}, "
                f"std {float(d40_phase['phase_lite_sharpe_std']):.3f}"
            )
        d40_supported = (
            float(d40_row["sharpe_daily_mean"]) >= best_sharpe - 0.08
            and float(d40_row["max_drawdown"]) <= lowest_mdd + 0.04
        )
        d28_appendix = d28_row is not None and (
            float(d28_row["max_drawdown"]) <= float(d40_row["max_drawdown"])
            or float(d28_row["p99_short_call_mtm_loss"]) <= float(d40_row["p99_short_call_mtm_loss"])
        )
        d35_alternative = d35_row is not None and (
            abs(float(d35_row["sharpe_daily_mean"]) - float(d40_row["sharpe_daily_mean"])) <= 0.08
        )
        rows.append(
            {
                "etf_code": etf_code,
                "d40_q70_support_state": "supports_current_mainline_interpretation" if d40_supported else "requires_appendix_caution",
                "d28_q100_appendix_state": "worth_appendix" if d28_appendix else "not_primary_appendix",
                "d35_q80_alternative_state": "balanced_alternative" if d35_alternative else "not_balanced_alternative",
                "final_appendix_recommended": bool(d28_appendix or d35_alternative or not d40_supported),
                "mainline_replacement_recommended": False,
                "phase_lite_note": phase_note,
                "interpretation": (
                    "Implementation form changes payoff shape even when entry effective delta is matched; "
                    "use as robustness evidence, not automatic parameter replacement."
                ),
            }
        )
    return pd.DataFrame(rows)


def _first_match(df: pd.DataFrame, etf_code: str, implementation_name: str) -> dict[str, object]:
    if df.empty:
        return {}
    match = df[df["etf_code"].eq(etf_code) & df["implementation_name"].eq(implementation_name)]
    return match.iloc[0].to_dict() if not match.empty else {}


def _row_by_name(group: pd.DataFrame, name: str) -> pd.DataFrame:
    return group[group["implementation_name"].eq(name)]


def _diff(a: pd.Series, b: pd.Series, col: str) -> float:
    return float(a[col]) - float(b[col])


def _mean(series: pd.Series) -> float:
    return float(series.mean()) if len(series) else np.nan


def _median(series: pd.Series) -> float:
    return float(series.median()) if len(series) else np.nan


def _std(series: pd.Series) -> float:
    return float(series.std(ddof=1)) if len(series) > 1 else np.nan


def _min(series: pd.Series) -> float:
    return float(series.min()) if len(series) else np.nan


def _max(series: pd.Series) -> float:
    return float(series.max()) if len(series) else np.nan
