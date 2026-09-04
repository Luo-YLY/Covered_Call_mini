from __future__ import annotations

import numpy as np
import pandas as pd

from src.features.etf_features import max_drawdown


def _annual_factor(periods: pd.DataFrame) -> float:
    days = (pd.to_datetime(periods["end_date"]) - pd.to_datetime(periods["roll_date"])).dt.days.mean()
    return 365 / days if days and not np.isnan(days) else 12


def _annualized_return_from_periods(returns: pd.Series, factor: float) -> float:
    if returns.empty:
        return np.nan
    cumulative = (1 + returns).prod() - 1
    return (1 + cumulative) ** (factor / len(returns)) - 1 if cumulative > -1 else np.nan


def summarize_performance(periods: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    rows = []
    for (etf_code, strategy), g in periods.groupby(["etf_code", "strategy"]):
        g = g.sort_values("roll_date")
        returns = g["R_cc"]
        factor = _annual_factor(g)
        nav = (1 + returns).cumprod()
        bh = periods[(periods["etf_code"] == etf_code) & (periods["strategy"] == "S0_BuyHold")].sort_values("roll_date")
        bh_returns = pd.Series(bh["R_cc"].values[: len(returns)], index=g.index) if len(bh) >= len(returns) else pd.Series(np.nan, index=g.index)
        cumulative = nav.iloc[-1] - 1 if len(nav) else np.nan
        ann_return = _annualized_return_from_periods(returns, factor)
        ann_vol = returns.std() * np.sqrt(factor)
        has_buyhold = len(bh) >= len(returns)
        excess = returns - bh_returns if has_buyhold else g["excess_return"]
        bh_basis_returns = bh_returns.dropna() if has_buyhold else g["R_etf"]
        bh_ann_return = _annualized_return_from_periods(bh_basis_returns, factor)
        ann_excess_return = ann_return - bh_ann_return if pd.notna(ann_return) and pd.notna(bh_ann_return) else np.nan
        mdd = max_drawdown(nav)
        rows.append(
            {
                "etf_code": etf_code,
                "strategy": strategy,
                "style_bucket": g["style_bucket"].dropna().iloc[0] if g["style_bucket"].notna().any() else np.nan,
                "cumulative_return": cumulative,
                "annualized_return": ann_return,
                "annualized_volatility": ann_vol,
                "sharpe_ratio": ann_return / ann_vol if ann_vol and ann_vol > 0 else np.nan,
                "sortino_ratio": ann_return / (returns[returns < 0].std() * np.sqrt(factor))
                if returns[returns < 0].std() and returns[returns < 0].std() > 0
                else np.nan,
                "max_drawdown": mdd,
                "calmar_ratio": ann_return / abs(mdd) if mdd < 0 else np.nan,
                "excess_return_total": (1 + returns).prod() - (1 + bh["R_cc"].values[: len(returns)]).prod()
                if len(bh) >= len(returns)
                else g["excess_return"].sum(),
                "excess_return_annualized": ann_excess_return,
                "information_ratio": excess.mean() / excess.std() * np.sqrt(factor) if excess.std() and excess.std() > 0 else np.nan,
                "upside_capture_ratio": returns[bh_returns > 0].mean() / bh_returns[bh_returns > 0].mean()
                if (bh_returns > 0).any()
                else np.nan,
                "downside_capture_ratio": returns[bh_returns < 0].mean() / bh_returns[bh_returns < 0].mean()
                if (bh_returns < 0).any()
                else np.nan,
                "average_premium_yield": g["premium_yield"].mean(),
                "total_premium_contribution": g["premium_contribution"].sum(),
                "total_upside_truncation_cost": g["upside_cost"].sum(),
                "total_transaction_cost_drag": g["cost"].sum(),
                "net_option_contribution": g["net_option_contribution"].sum(),
                "assignment_frequency": g["assignment_flag"].mean(),
                "average_coverage_ratio": g["coverage_ratio"].mean(),
                "average_selected_delta": g["selected_delta"].mean(),
                "average_moneyness": g["moneyness"].mean(),
                "option_sale_success_rate": g["option_selected_flag"].mean(),
            }
        )
    summary = pd.DataFrame(rows)
    matrices = {
        "annualized_return": summary.pivot(index="etf_code", columns="strategy", values="annualized_return"),
        "sharpe": summary.pivot(index="etf_code", columns="strategy", values="sharpe_ratio"),
        "max_drawdown": summary.pivot(index="etf_code", columns="strategy", values="max_drawdown"),
        "excess_return": summary.pivot(index="etf_code", columns="strategy", values="excess_return_annualized"),
        "assignment_frequency": summary.pivot(index="etf_code", columns="strategy", values="assignment_frequency"),
        "total_premium_contribution": summary.pivot(index="etf_code", columns="strategy", values="total_premium_contribution"),
        "total_upside_truncation_cost": summary.pivot(index="etf_code", columns="strategy", values="total_upside_truncation_cost"),
        "net_option_contribution": summary.pivot(index="etf_code", columns="strategy", values="net_option_contribution"),
    }
    return summary, matrices
