from __future__ import annotations

import numpy as np
import pandas as pd

from src.metrics.ver2_metric_standard import compute_portfolio_option_contribution, summarize_daily_nav


def build_phase_ensemble_sleeves(sleeve_returns: pd.DataFrame, *, common_start: str, rf: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build all-phase equal-weight ensemble sleeves."""

    return _build_ensemble(
        sleeve_returns,
        entity_col="sleeve_name",
        key_col="sleeve_key",
        return_col="daily_return_total",
        option_col="daily_return_option_leg_component",
        common_start=common_start,
        rf=rf,
    )


def build_phase_ensemble_portfolios(portfolio_returns: pd.DataFrame, *, common_start: str, rf: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build all-phase equal-weight ensemble portfolios for target candidates."""

    target = portfolio_returns[portfolio_returns["portfolio_role"].eq("target_candidate")].copy()
    return _build_ensemble(
        target,
        entity_col="portfolio_name",
        key_col="portfolio_name",
        return_col="portfolio_return",
        option_col="portfolio_option_leg_return",
        common_start=common_start,
        rf=rf,
    )


def compare_ensemble_vs_single_phase(ensemble_summary: pd.DataFrame, phase_metrics: pd.DataFrame, *, entity_col: str) -> pd.DataFrame:
    """Compare ensemble metrics with phase0, median, worst, and best phases."""

    rows: list[dict[str, object]] = []
    common = phase_metrics[phase_metrics["window_mode"].eq("common")].copy()
    for _, ens in ensemble_summary.iterrows():
        name = ens[entity_col]
        g = common[common[entity_col].eq(name)].copy()
        if g.empty:
            continue
        phase0 = g.sort_values("phase_shift").iloc[0]
        median_sharpe = float(g["sharpe_daily_mean"].median())
        worst = g.loc[g["sharpe_daily_mean"].idxmin()]
        best = g.loc[g["sharpe_daily_mean"].idxmax()]
        rows.append(
            {
                entity_col: name,
                "ensemble_sharpe": ens["sharpe_daily_mean"],
                "phase0_sharpe": phase0["sharpe_daily_mean"],
                "phase_median_sharpe": median_sharpe,
                "worst_phase_sharpe": worst["sharpe_daily_mean"],
                "best_phase_sharpe": best["sharpe_daily_mean"],
                "ensemble_mdd": ens["max_drawdown"],
                "phase0_mdd": phase0["max_drawdown"],
                "worst_phase_mdd": float(g["max_drawdown"].max()),
                "best_phase_mdd": float(g["max_drawdown"].min()),
                "delta_sharpe_vs_phase0": ens["sharpe_daily_mean"] - phase0["sharpe_daily_mean"],
                "delta_mdd_vs_phase0": ens["max_drawdown"] - phase0["max_drawdown"],
                "ensemble_improves_sharpe_dispersion_proxy": bool(
                    ens["sharpe_daily_mean"] >= median_sharpe and ens["max_drawdown"] <= float(g["max_drawdown"].quantile(0.75))
                ),
            }
        )
    return pd.DataFrame(rows)


def _build_ensemble(
    returns: pd.DataFrame,
    *,
    entity_col: str,
    key_col: str,
    return_col: str,
    option_col: str,
    common_start: str,
    rf: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    daily_rows: list[pd.DataFrame] = []
    summary_rows: list[dict[str, object]] = []
    source = returns[pd.to_datetime(returns["date"]) >= pd.Timestamp(common_start)].copy()
    for name, group in source.groupby(entity_col, sort=True):
        piv = group.pivot_table(index="date", columns="phase_id", values=return_col, aggfunc="last").dropna()
        opt = group.pivot_table(index="date", columns="phase_id", values=option_col, aggfunc="last").reindex(piv.index).dropna()
        if piv.empty:
            continue
        ens_ret = piv.mean(axis=1)
        ens_opt = opt.mean(axis=1)
        nav = (1.0 + ens_ret.fillna(0.0)).cumprod()
        daily = pd.DataFrame(
            {
                "date": pd.to_datetime(piv.index),
                entity_col: name,
                "ensemble_name": f"{name}_all_phase_equal_weight_ensemble",
                "ensemble_type": "all_phase_equal_weight",
                "phase_count": int(piv.shape[1]),
                "daily_return": ens_ret.values,
                "daily_option_leg_return": ens_opt.values,
                "nav": nav.values,
            }
        )
        metrics = summarize_daily_nav(daily[["date", "nav"]], date_col="date", nav_col="nav", rf=rf)
        summary_rows.append(
            {
                entity_col: name,
                "ensemble_name": f"{name}_all_phase_equal_weight_ensemble",
                "ensemble_type": "all_phase_equal_weight",
                "phase_count": int(piv.shape[1]),
                **metrics,
                "option_leg_annualized_pnl_contribution": compute_portfolio_option_contribution(
                    ens_opt, n_days=len(ens_opt)
                ),
                "final_nav": float(nav.iloc[-1]),
            }
        )
        daily_rows.append(daily)
    return pd.concat(daily_rows, ignore_index=True), pd.DataFrame(summary_rows)
