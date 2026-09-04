from __future__ import annotations

import numpy as np
import pandas as pd

from src.metrics.ver2_metric_standard import compute_portfolio_option_contribution, summarize_daily_nav


def compute_option_cycle_concentration(period_map: pd.DataFrame) -> pd.DataFrame:
    """Compute option-cycle concentration diagnostics for rebuilt sleeves."""

    if period_map.empty:
        return pd.DataFrame(
            [{"cycle_attribution_available": False, "reason": "No covered-call period map was produced."}]
        )
    rows: list[dict[str, object]] = []
    for (sleeve_key, phase_id), group in period_map.groupby(["sleeve_key", "phase_id"], sort=True):
        option_pnl = group["net_option_contribution"].astype(float)
        abs_pnl = option_pnl.abs()
        denom = float(abs_pnl.sum())
        weights = abs_pnl / denom if denom > 0 else pd.Series(0.0, index=option_pnl.index)
        first = group.iloc[0]
        rows.append(
            {
                "cycle_attribution_available": True,
                "phase_id": phase_id,
                "phase_shift": int(first["phase_shift"]),
                "inception_date": first["inception_date"],
                "etf_code": first["etf_code"],
                "sleeve_name": first["sleeve_name"],
                "sleeve_key": sleeve_key,
                "option_cycle_count": int(len(group)),
                "cycle_option_pnl_sum": float(option_pnl.sum()),
                "cycle_option_pnl_mean": float(option_pnl.mean()),
                "cycle_option_pnl_std": float(option_pnl.std(ddof=1)) if len(option_pnl) > 1 else 0.0,
                "top_1_abs_cycle_pnl_share": _top_share(abs_pnl, 1),
                "top_3_abs_cycle_pnl_share": _top_share(abs_pnl, 3),
                "top_5_abs_cycle_pnl_share": _top_share(abs_pnl, 5),
                "option_cycle_hhi": float((weights**2).sum()) if denom > 0 else np.nan,
                "worst_cycle_pnl": float(option_pnl.min()),
                "best_cycle_pnl": float(option_pnl.max()),
                "positive_cycle_rate": float((option_pnl > 0).mean()),
            }
        )
    return pd.DataFrame(rows)


def compute_leave_one_cycle_out(daily_nav: pd.DataFrame, period_map: pd.DataFrame, *, rf: float) -> pd.DataFrame:
    """Drop each option cycle's daily rows and recompute phase metrics."""

    if period_map.empty:
        return pd.DataFrame(
            [{"cycle_attribution_available": False, "reason": "No covered-call period map was produced."}]
        )
    daily_lookup = {k: g.sort_values("date") for k, g in daily_nav.groupby(["sleeve_key", "phase_id"], sort=False)}
    rows: list[dict[str, object]] = []
    for (sleeve_key, phase_id), periods in period_map.groupby(["sleeve_key", "phase_id"], sort=True):
        d = daily_lookup.get((sleeve_key, phase_id))
        if d is None or d.empty:
            continue
        full_metrics = _metrics_from_returns(d["date"], d["daily_return_total"], d["daily_return_option_leg_component"], rf)
        full_option_sign = np.sign(full_metrics["option_leg_annualized_pnl_contribution"])
        for _, period in periods.sort_values("period_index").iterrows():
            cycle_idx = int(period["period_index"])
            keep = d[d["period_index"].astype("Int64") != cycle_idx].copy()
            if len(keep) < 2:
                continue
            metrics = _metrics_from_returns(keep["date"], keep["daily_return_total"], keep["daily_return_option_leg_component"], rf)
            rows.append(
                {
                    "cycle_attribution_available": True,
                    "phase_id": phase_id,
                    "phase_shift": int(period["phase_shift"]),
                    "inception_date": period["inception_date"],
                    "etf_code": period["etf_code"],
                    "sleeve_name": period["sleeve_name"],
                    "sleeve_key": sleeve_key,
                    "removed_cycle_id": cycle_idx,
                    "removed_cycle_start": _date(period["rebalance_date"]),
                    "removed_cycle_end": _date(period["period_end_date"]),
                    "removed_cycle_option_code": period.get("option_code", ""),
                    "removed_cycle_option_pnl": float(period.get("net_option_contribution", np.nan)),
                    "annualized_return_cagr_after_removal": metrics["annualized_return_cagr"],
                    "sharpe_after_removal": metrics["sharpe_daily_mean"],
                    "max_drawdown_after_removal": metrics["max_drawdown"],
                    "option_leg_after_removal": metrics["option_leg_annualized_pnl_contribution"],
                    "delta_sharpe_vs_full_phase": metrics["sharpe_daily_mean"] - full_metrics["sharpe_daily_mean"],
                    "delta_cagr_vs_full_phase": metrics["annualized_return_cagr"] - full_metrics["annualized_return_cagr"],
                    "delta_mdd_vs_full_phase": metrics["max_drawdown"] - full_metrics["max_drawdown"],
                    "classification_flip_flag": bool(
                        np.sign(metrics["option_leg_annualized_pnl_contribution"]) != full_option_sign
                    ),
                }
            )
    return pd.DataFrame(rows)


def summarize_leave_one_cycle_out(leave_one: pd.DataFrame) -> pd.DataFrame:
    """Summarize leave-one-cycle-out rows at sleeve/phase level."""

    if leave_one.empty or "cycle_attribution_available" not in leave_one or not bool(leave_one["cycle_attribution_available"].iloc[0]):
        return leave_one
    rows: list[dict[str, object]] = []
    for (sleeve_key, phase_id), group in leave_one.groupby(["sleeve_key", "phase_id"], sort=True):
        first = group.iloc[0]
        rows.append(
            {
                "phase_id": phase_id,
                "phase_shift": int(first["phase_shift"]),
                "inception_date": first["inception_date"],
                "etf_code": first["etf_code"],
                "sleeve_name": first["sleeve_name"],
                "sleeve_key": sleeve_key,
                "leave_one_cycle_out_sharpe_min": float(group["sharpe_after_removal"].min()),
                "leave_one_cycle_out_sharpe_max": float(group["sharpe_after_removal"].max()),
                "leave_one_cycle_out_cagr_min": float(group["annualized_return_cagr_after_removal"].min()),
                "leave_one_cycle_out_cagr_max": float(group["annualized_return_cagr_after_removal"].max()),
                "leave_one_cycle_out_mdd_min": float(group["max_drawdown_after_removal"].min()),
                "leave_one_cycle_out_mdd_max": float(group["max_drawdown_after_removal"].max()),
                "leave_one_cycle_out_option_leg_sign_flip_flag": bool(group["classification_flip_flag"].any()),
                "largest_abs_delta_sharpe": float(group["delta_sharpe_vs_full_phase"].abs().max()),
            }
        )
    return pd.DataFrame(rows)


def _metrics_from_returns(dates: pd.Series, returns: pd.Series, option_returns: pd.Series, rf: float) -> dict[str, float]:
    r = pd.Series(returns, dtype="float64").fillna(0.0).reset_index(drop=True)
    nav = (1.0 + r).cumprod()
    df = pd.DataFrame({"date": pd.to_datetime(dates).reset_index(drop=True), "nav": nav})
    metrics = summarize_daily_nav(df, date_col="date", nav_col="nav", rf=rf)
    metrics["option_leg_annualized_pnl_contribution"] = compute_portfolio_option_contribution(option_returns, n_days=len(r))
    return metrics


def _top_share(values: pd.Series, n: int) -> float:
    denom = float(values.sum())
    return float(values.sort_values(ascending=False).head(n).sum() / denom) if denom > 0 else np.nan


def _date(value: object) -> str:
    return pd.Timestamp(value).date().isoformat() if pd.notna(value) else ""
