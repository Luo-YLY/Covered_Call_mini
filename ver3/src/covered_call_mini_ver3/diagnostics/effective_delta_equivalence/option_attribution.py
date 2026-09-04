from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252.0


def compute_option_leg_attribution(period_detail: pd.DataFrame) -> pd.DataFrame:
    """Return period-level option-leg attribution with explicit premium and payoff fields."""

    if period_detail.empty:
        return pd.DataFrame()
    out = period_detail.copy()
    out["net_option_leg_return"] = pd.to_numeric(out["option_leg_return"], errors="coerce")
    out["premium_capture_ratio_period"] = _safe_div_series(out["net_option_leg_return"], out["premium_return"])
    out["payoff_burden_period"] = _safe_div_series(out["payoff_return"], out["premium_return"])
    return out[
        [
            "etf_code",
            "implementation_name",
            "phase_shift",
            "rebalance_date",
            "period_end_date",
            "option_code",
            "target_call_delta",
            "coverage",
            "actual_entry_delta",
            "actual_effective_delta",
            "premium_return",
            "payoff_return",
            "transaction_cost_return",
            "net_option_leg_return",
            "premium_capture_ratio_period",
            "payoff_burden_period",
            "assignment_flag",
            "realized_moneyness",
            "actual_dte",
        ]
    ].copy()


def compute_premium_payoff_quality(period_detail: pd.DataFrame, daily_nav: pd.DataFrame) -> pd.DataFrame:
    """Aggregate premium capture, payoff burden, and option-leg stability."""

    if period_detail.empty:
        return pd.DataFrame()
    day_counts = daily_nav.groupby(["etf_code", "implementation_name"])["date"].nunique().to_dict()
    rows = []
    for keys, group in period_detail.groupby(["etf_code", "implementation_name"]):
        etf_code, implementation_name = keys
        selected = group[group["option_selected_flag"].astype(int).eq(1)]
        premium = pd.to_numeric(group["premium_return"], errors="coerce").fillna(0.0)
        payoff = pd.to_numeric(group["payoff_return"], errors="coerce").fillna(0.0)
        cost = pd.to_numeric(group["transaction_cost_return"], errors="coerce").fillna(0.0)
        net = pd.to_numeric(group["option_leg_return"], errors="coerce").fillna(0.0)
        n_days = max(int(day_counts.get((etf_code, implementation_name), 0)), 1)
        rows.append(
            {
                "etf_code": etf_code,
                "implementation_name": implementation_name,
                "premium_sum": float(premium.sum()),
                "payoff_sum": float(payoff.sum()),
                "transaction_cost_sum": float(cost.sum()),
                "net_option_leg_sum": float(net.sum()),
                "option_leg_annualized_pnl_contribution": float(net.sum() * TRADING_DAYS / n_days),
                "premium_capture_ratio_agg": _safe_div(float(net.sum()), float(premium.sum())),
                "payoff_burden_agg": _safe_div(float(payoff.sum()), float(premium.sum())),
                "positive_option_leg_period_rate": float((net > 0).mean()) if len(net) else np.nan,
                "assignment_rate": float(selected["assignment_flag"].astype(bool).mean()) if not selected.empty else np.nan,
                "avg_active_coverage": float(pd.to_numeric(group["coverage"], errors="coerce").mean()),
                "avg_actual_dte": float(pd.to_numeric(selected["actual_dte"], errors="coerce").mean()) if not selected.empty else np.nan,
                "avg_realized_moneyness": float(pd.to_numeric(selected["realized_moneyness"], errors="coerce").mean()) if not selected.empty else np.nan,
                "avg_actual_entry_delta": float(pd.to_numeric(selected["actual_entry_delta"], errors="coerce").mean()) if not selected.empty else np.nan,
                "selected_periods": int(selected["option_selected_flag"].sum()) if "option_selected_flag" in selected else 0,
                "total_periods": int(len(group)),
            }
        )
    return pd.DataFrame(rows)


def compute_mtm_stress(daily_mtm: pd.DataFrame) -> pd.DataFrame:
    """Aggregate daily short-call MTM stress from frozen-engine daily marks."""

    if daily_mtm.empty:
        return pd.DataFrame()
    rows = []
    for keys, group in daily_mtm.groupby(["etf_code", "implementation_name"]):
        etf_code, implementation_name = keys
        stress = pd.to_numeric(group.get("short_call_mtm_loss_return", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
        rows.append(
            {
                "etf_code": etf_code,
                "implementation_name": implementation_name,
                "p95_short_call_mtm_loss": float(stress.quantile(0.95)),
                "p99_short_call_mtm_loss": float(stress.quantile(0.99)),
                "max_short_call_mtm_loss": float(stress.max()),
                "mean_short_call_mtm_loss": float(stress.mean()),
                "stress_obs": int(len(stress)),
            }
        )
    return pd.DataFrame(rows)


def _safe_div(numerator: float, denominator: float) -> float:
    if abs(float(denominator)) < 1e-12:
        return np.nan
    return float(numerator) / float(denominator)


def _safe_div_series(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    den = pd.to_numeric(denominator, errors="coerce")
    num = pd.to_numeric(numerator, errors="coerce")
    return num.divide(den.where(den.abs() > 1e-12))
