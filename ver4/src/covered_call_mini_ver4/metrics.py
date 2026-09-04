from __future__ import annotations

import numpy as np
import pandas as pd

from .config import CycleExperimentConfig


def _quantile(series: pd.Series, q: float) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.quantile(q)) if not values.empty else np.nan


def build_cycle_cashflow_summary(ledger: pd.DataFrame, config: CycleExperimentConfig) -> pd.DataFrame:
    """Summarize fixed-notional cashflow properties without CAGR or compounded NAV."""

    if ledger.empty:
        return pd.DataFrame()
    rows: list[dict[str, float | int | str]] = []
    group_cols = ["etf_code", "strategy_name", "strategy_label", "parameter_role", "target_delta", "coverage"]
    for keys, group in ledger.groupby(group_cols, dropna=False):
        g = group.sort_values("rebalance_date")
        start = pd.to_datetime(g["rebalance_date"].min())
        end = pd.to_datetime(g["period_end_date"].max())
        sample_days = max((end - start).days, 1)
        net_option = g["net_option_yield"].astype(float)
        covered = g["covered_call_period_return"].astype(float)
        premium = g["gross_premium_yield"].astype(float)
        rows.append(
            {
                "etf_code": keys[0],
                "strategy_name": keys[1],
                "strategy_label": keys[2],
                "parameter_role": keys[3],
                "target_delta": keys[4],
                "coverage": keys[5],
                "sample_start": start.date().isoformat(),
                "sample_end": end.date().isoformat(),
                "sample_days": int(sample_days),
                "cycle_count": int(len(g)),
                "selected_option_cycle_count": int(g["selected_option_flag"].sum()),
                "assignment_rate": float(g.loc[g["selected_option_flag"].eq(1), "assignment_flag"].mean())
                if int(g["selected_option_flag"].sum()) else np.nan,
                "fixed_notional": float(config.fixed_notional),
                "gross_premium_cash_total": float(g["gross_premium_cash"].sum()),
                "net_option_pnl_cash_total": float(g["net_option_pnl_cash"].sum()),
                "covered_call_pnl_cash_total": float(g["covered_call_pnl_cash"].sum()),
                "buyhold_pnl_cash_total": float(g["buyhold_pnl_cash"].sum()),
                "relative_to_buyhold_pnl_cash_total": float(g["relative_to_buyhold_pnl_cash"].sum()),
                "non_compound_total_return": float(covered.sum()),
                "non_compound_annualized_return": float(covered.sum() * 365.0 / sample_days),
                "non_compound_annualized_net_option_yield": float(net_option.sum() * 365.0 / sample_days),
                "net_option_yield_mean": float(net_option.mean()),
                "net_option_yield_median": float(net_option.median()),
                "net_option_yield_p10": _quantile(net_option, 0.10),
                "net_option_yield_p90": _quantile(net_option, 0.90),
                "positive_net_option_cycle_rate": float((net_option > 0).mean()),
                "gross_premium_yield_median": float(premium.median()),
                "covered_call_cycle_return_median": float(covered.median()),
                "covered_call_positive_cycle_rate": float((covered > 0).mean()),
                "relative_to_buyhold_return_mean": float(g["relative_to_buyhold_return"].mean()),
                "upside_cap_return_mean": float(g["upside_cap_return"].mean()),
                "upside_cap_return_p90": _quantile(g["upside_cap_return"], 0.90),
                "upside_cap_cycle_rate": float((g["upside_cap_return"] > 0).mean()),
            }
        )
    return pd.DataFrame(rows).sort_values(["etf_code", "parameter_role", "target_delta", "coverage"]).reset_index(drop=True)


def build_rolling_cycle_cashflow(ledger: pd.DataFrame, config: CycleExperimentConfig) -> pd.DataFrame:
    """Build rolling, non-compounded cash income over a fixed count of option cycles."""

    if ledger.empty:
        return pd.DataFrame()
    window = config.rolling_cashflow_cycles
    rows: list[dict[str, float | int | str]] = []
    for (etf_code, strategy_name), group in ledger.groupby(["etf_code", "strategy_name"], dropna=False):
        g = group.sort_values("rebalance_date").reset_index(drop=True)
        if len(g) < window:
            continue
        for end_idx in range(window - 1, len(g)):
            sample = g.iloc[end_idx - window + 1 : end_idx + 1]
            target_values = {
                f"cash_target_{int(round(target * 100)):02d}_met": bool(sample["net_option_yield"].sum() >= target)
                for target in config.cash_yield_targets
            }
            rows.append(
                {
                    "etf_code": etf_code,
                    "strategy_name": strategy_name,
                    "strategy_label": sample["strategy_label"].iloc[-1],
                    "parameter_role": sample["parameter_role"].iloc[-1],
                    "target_delta": sample["target_delta"].iloc[-1],
                    "coverage": sample["coverage"].iloc[-1],
                    "window_cycles": window,
                    "window_start": pd.to_datetime(sample["rebalance_date"].iloc[0]).date().isoformat(),
                    "window_end": pd.to_datetime(sample["period_end_date"].iloc[-1]).date().isoformat(),
                    "net_option_yield_non_compound": float(sample["net_option_yield"].sum()),
                    "gross_premium_yield_non_compound": float(sample["gross_premium_yield"].sum()),
                    "covered_call_return_non_compound": float(sample["covered_call_period_return"].sum()),
                    "relative_to_buyhold_return_non_compound": float(sample["relative_to_buyhold_return"].sum()),
                    "net_option_pnl_cash": float(sample["net_option_pnl_cash"].sum()),
                    "upside_cap_pnl_cash": float(sample["upside_cap_pnl_cash"].sum()),
                    **target_values,
                }
            )
    return pd.DataFrame(rows)


def attach_rolling_cashflow_summary(summary: pd.DataFrame, rolling: pd.DataFrame, config: CycleExperimentConfig) -> pd.DataFrame:
    if summary.empty:
        return summary.copy()
    out = summary.copy()
    if rolling.empty:
        out["rolling_window_count"] = 0
        return out
    group_cols = ["etf_code", "strategy_name"]
    grouped = rolling.groupby(group_cols, dropna=False)
    rows: list[dict[str, float | int | str]] = []
    for keys, group in grouped:
        row: dict[str, float | int | str] = {
            "etf_code": keys[0],
            "strategy_name": keys[1],
            "rolling_window_count": int(len(group)),
            "rolling_net_option_yield_p10": _quantile(group["net_option_yield_non_compound"], 0.10),
            "rolling_net_option_yield_median": _quantile(group["net_option_yield_non_compound"], 0.50),
            "rolling_net_option_yield_p90": _quantile(group["net_option_yield_non_compound"], 0.90),
        }
        for target in config.cash_yield_targets:
            column = f"cash_target_{int(round(target * 100)):02d}_met"
            row[f"rolling_{column}_rate"] = float(group[column].mean()) if column in group else np.nan
        rows.append(row)
    return out.merge(pd.DataFrame(rows), on=group_cols, how="left")
