from __future__ import annotations

import numpy as np
import pandas as pd


STRATEGY_ORDER = {
    "BuyHold": 0,
    "ITM5_100": 1,
    "ITM2_100": 2,
    "ATM_100": 3,
    "OTM2_100": 4,
    "OTM5_100": 5,
    "OTM5_50": 6,
}


def annual_factor(periods: pd.DataFrame) -> float:
    days = (pd.to_datetime(periods["period_end_date"]) - pd.to_datetime(periods["rebalance_date"])).dt.days.mean()
    return 365.0 / days if days and not np.isnan(days) else 12.0


def annualized_return(returns: pd.Series, factor: float) -> float:
    returns = returns.dropna()
    if returns.empty:
        return np.nan
    cumulative = (1.0 + returns).prod() - 1.0
    if cumulative <= -1:
        return np.nan
    return float((1.0 + cumulative) ** (factor / len(returns)) - 1.0)


def max_drawdown_magnitude(nav: pd.Series) -> float:
    """Return max drawdown as a positive magnitude."""

    nav = nav.dropna()
    if nav.empty:
        return np.nan
    drawdown = nav / nav.cummax() - 1.0
    return float(abs(drawdown.min()))


def drawdown_curve(nav: pd.Series) -> pd.Series:
    nav = nav.astype(float)
    return nav / nav.cummax() - 1.0


def protection_cost_ratio(upside_cost_mean: float, average_downside_benefit: float) -> float:
    if pd.isna(average_downside_benefit) or average_downside_benefit == 0:
        return np.nan
    return float(upside_cost_mean / average_downside_benefit)


def max_drawdown_improvement(buyhold_mdd: float, strategy_mdd: float) -> float:
    if pd.isna(buyhold_mdd) or pd.isna(strategy_mdd):
        return np.nan
    return float(buyhold_mdd - strategy_mdd)


def add_period_diagnostics(periods: pd.DataFrame) -> pd.DataFrame:
    """Add ver2 relative-return, downside-cushion, and upside-cost columns."""

    out = periods.copy()
    out["excess_return_vs_etf"] = out["strategy_period_return"] - out["etf_period_return"]
    down_mask = out["etf_period_return"] < 0
    up_mask = out["etf_period_return"] > 0
    out["downside_cushion_ratio"] = np.where(
        down_mask,
        out["excess_return_vs_etf"] / out["etf_period_return"].abs(),
        np.nan,
    )
    out["downside_benefit"] = np.where(
        down_mask,
        np.maximum(out["excess_return_vs_etf"], 0.0),
        np.nan,
    )
    out["upside_cost"] = np.where(
        up_mask,
        np.maximum(out["etf_period_return"] - out["strategy_period_return"], 0.0),
        np.nan,
    )
    return out


def summarize_ver2_performance(periods: pd.DataFrame, nav: pd.DataFrame) -> pd.DataFrame:
    """Compute the ver2 performance and downside-protection summary table."""

    periods = add_period_diagnostics(periods)
    rows: list[dict[str, float | str | int | pd.Timestamp]] = []
    nav_lookup = {
        (str(etf), str(strategy)): g.sort_values("date")
        for (etf, strategy), g in nav.groupby(["etf_code", "strategy_name"])
    }

    for (etf_code, strategy_name), g in periods.groupby(["etf_code", "strategy_name"]):
        g = g.sort_values("rebalance_date")
        returns = g["strategy_period_return"].astype(float)
        excess = g["excess_return_vs_etf"].astype(float)
        factor = annual_factor(g)
        nav_g = nav_lookup.get((str(etf_code), str(strategy_name)))
        nav_series = nav_g["nav"].astype(float) if nav_g is not None else (1.0 + returns).cumprod()

        ann_return = annualized_return(returns, factor)
        ann_vol = float(returns.std(ddof=1) * np.sqrt(factor)) if len(returns.dropna()) > 1 else np.nan
        mdd = max_drawdown_magnitude(nav_series)
        down = g[g["etf_period_return"] < 0]
        up = g[g["etf_period_return"] > 0]
        selected = g[g.get("option_selected_flag", 0) == 1]
        downside_cushion = down["downside_cushion_ratio"].dropna()
        avg_downside_benefit = float(down["downside_benefit"].mean()) if not down.empty else np.nan
        upside_cost_mean = float(up["upside_cost"].mean()) if not up.empty else np.nan
        assignment_rate = (
            float(selected["assignment_flag"].fillna(0).astype(int).mean())
            if strategy_name != "BuyHold" and not selected.empty
            else np.nan
        )

        rows.append(
            {
                "etf_code": etf_code,
                "strategy_name": strategy_name,
                "start_date": g["rebalance_date"].min(),
                "end_date": g["period_end_date"].max(),
                "num_periods": int(len(g)),
                "cumulative_return": float((1.0 + returns).prod() - 1.0) if len(returns) else np.nan,
                "annualized_return": ann_return,
                "annualized_volatility": ann_vol,
                "sharpe_ratio": float(ann_return / ann_vol) if ann_vol and ann_vol > 0 else np.nan,
                "max_drawdown": mdd,
                "calmar_ratio": float(ann_return / mdd) if mdd and mdd > 0 else np.nan,
                "assignment_rate": assignment_rate,
                "period_win_rate": float((returns > 0).mean()) if len(returns) else np.nan,
                "average_excess_return": float(excess.mean()) if len(excess) else np.nan,
                "excess_return_mean": float(excess.mean()) if len(excess) else np.nan,
                "excess_return_volatility": float(excess.std(ddof=1)) if len(excess.dropna()) > 1 else np.nan,
                "excess_win_rate": float((excess > 0).mean()) if len(excess) else np.nan,
                "tracking_error_vs_etf": float(excess.std(ddof=1) * np.sqrt(factor))
                if len(excess.dropna()) > 1
                else np.nan,
                "downside_excess_mean": float(down["excess_return_vs_etf"].mean()) if not down.empty else np.nan,
                "downside_win_rate": float((down["strategy_period_return"] > down["etf_period_return"]).mean())
                if not down.empty
                else np.nan,
                "downside_cushion_ratio_mean": float(downside_cushion.mean()) if not downside_cushion.empty else np.nan,
                "downside_cushion_ratio_median": float(downside_cushion.median())
                if not downside_cushion.empty
                else np.nan,
                "downside_cushion_ratio_min": float(downside_cushion.min()) if not downside_cushion.empty else np.nan,
                "downside_cushion_ratio_max": float(downside_cushion.max()) if not downside_cushion.empty else np.nan,
                "average_downside_benefit": avg_downside_benefit,
                "upside_cost_mean": upside_cost_mean,
                "upside_underperformance_rate": float((up["strategy_period_return"] < up["etf_period_return"]).mean())
                if not up.empty
                else np.nan,
                "protection_cost_ratio": protection_cost_ratio(upside_cost_mean, avg_downside_benefit),
            }
        )

    summary = pd.DataFrame(rows)
    if summary.empty:
        return summary

    buyhold_mdd = (
        summary[summary["strategy_name"] == "BuyHold"]
        .set_index("etf_code")["max_drawdown"]
        .to_dict()
    )
    summary["max_drawdown_improvement"] = summary.apply(
        lambda row: max_drawdown_improvement(buyhold_mdd.get(row["etf_code"], np.nan), row["max_drawdown"]),
        axis=1,
    )
    summary["_strategy_order"] = summary["strategy_name"].map(STRATEGY_ORDER).fillna(999)
    return (
        summary.sort_values(["etf_code", "_strategy_order", "strategy_name"])
        .drop(columns=["_strategy_order"])
        .reset_index(drop=True)
    )
