from __future__ import annotations

import numpy as np
import pandas as pd

from src.metrics.ver2_metric_standard import TRADING_DAYS_PER_YEAR, compute_portfolio_option_contribution

from .config import PortfolioDefinition


def compute_option_leg_contribution(
    option_leg_panel: pd.DataFrame,
    portfolios: list[PortfolioDefinition],
) -> pd.DataFrame:
    """Compute portfolio and sleeve-level option-leg contribution from daily option-leg returns."""

    option = option_leg_panel.set_index("date")
    rows: list[dict[str, object]] = []
    for portfolio in portfolios:
        total = pd.Series(0.0, index=option.index)
        leg_series: dict[str, pd.Series] = {}
        for sleeve_key, weight in portfolio.sleeve_weights.items():
            col = f"{sleeve_key}__daily_return"
            leg = option[col].astype(float) * float(weight) if col in option else pd.Series(0.0, index=option.index)
            leg_series[sleeve_key] = leg
            total = total.add(leg, fill_value=0.0)
        portfolio_contribution = compute_portfolio_option_contribution(total, n_days=len(total))
        rows.append(
            {
                "portfolio_name": portfolio.portfolio_name,
                "universe_name": portfolio.universe_name,
                "portfolio_type": portfolio.portfolio_type,
                "weight_scheme": portfolio.weight_scheme,
                "etf_code": "PORTFOLIO",
                "sleeve_key": "PORTFOLIO_TOTAL",
                "weight": 1.0,
                "option_leg_annualized_pnl_contribution": portfolio_contribution,
                "contribution_share_of_portfolio_option_leg": 1.0 if abs(portfolio_contribution) > 1e-12 else np.nan,
                "attribution_method": "daily_weighted_option_leg_return",
            }
        )
        for sleeve_key, leg in leg_series.items():
            contribution = compute_portfolio_option_contribution(leg, n_days=len(leg))
            rows.append(
                {
                    "portfolio_name": portfolio.portfolio_name,
                    "universe_name": portfolio.universe_name,
                    "portfolio_type": portfolio.portfolio_type,
                    "weight_scheme": portfolio.weight_scheme,
                    "etf_code": portfolio.sleeve_to_etf[sleeve_key],
                    "sleeve_key": sleeve_key,
                    "weight": portfolio.sleeve_weights[sleeve_key],
                    "option_leg_annualized_pnl_contribution": contribution,
                    "contribution_share_of_portfolio_option_leg": _safe_div(contribution, portfolio_contribution),
                    "attribution_method": "daily_weighted_option_leg_return",
                }
            )
    return pd.DataFrame(rows)


def compute_vs_baseline_comparison(summary: pd.DataFrame) -> pd.DataFrame:
    """Compare selected portfolios to matched pure ETF baselines."""

    rows: list[dict[str, object]] = []
    idx = summary.set_index("portfolio_name")
    selected = summary[summary["portfolio_type"].eq("Selected")].copy()
    for _, row in selected.iterrows():
        baseline_name = row["portfolio_name"].replace("_Selected_", "_Pure_ETF_")
        if baseline_name not in idx.index:
            continue
        base = idx.loc[baseline_name]
        rows.append(
            {
                "selected_portfolio": row["portfolio_name"],
                "matched_baseline": baseline_name,
                "universe_name": row["universe_name"],
                "weight_scheme": row["weight_scheme"],
                "excess_cagr_vs_baseline": row["annualized_return_cagr"] - base["annualized_return_cagr"],
                "delta_sharpe_vs_baseline": row["sharpe_daily_mean"] - base["sharpe_daily_mean"],
                "delta_volatility_vs_baseline": row["annualized_volatility"] - base["annualized_volatility"],
                "delta_mdd_vs_baseline": row["max_drawdown"] - base["max_drawdown"],
                "delta_calmar_vs_baseline": row["calmar_ratio"] - base["calmar_ratio"],
                "delta_sortino_vs_baseline": row["sortino_ratio"] - base["sortino_ratio"],
                "delta_final_nav_vs_baseline": row["final_nav"] - base["final_nav"],
                "option_leg_annualized_pnl_contribution": row["option_leg_annualized_pnl_contribution"],
                "interpretation_hint": _baseline_hint(row, base),
            }
        )
    return pd.DataFrame(rows).sort_values(["selected_portfolio"]).reset_index(drop=True)


def compute_universe_comparison(summary: pd.DataFrame) -> pd.DataFrame:
    """Compare Universe B against Universe A under matched weight schemes."""

    rows: list[dict[str, object]] = []
    idx = summary.set_index("portfolio_name")
    for portfolio_type in ["Pure_ETF", "Selected"]:
        for scheme in sorted(summary["weight_scheme"].unique()):
            left = f"B_{portfolio_type}_{scheme}"
            right = f"A_{portfolio_type}_{scheme}"
            if left not in idx.index or right not in idx.index:
                continue
            lrow = idx.loc[left]
            rrow = idx.loc[right]
            rows.append(
                {
                    "left_portfolio": left,
                    "right_portfolio": right,
                    "portfolio_type": portfolio_type,
                    "weight_scheme": scheme,
                    "delta_cagr": lrow["annualized_return_cagr"] - rrow["annualized_return_cagr"],
                    "delta_sharpe": lrow["sharpe_daily_mean"] - rrow["sharpe_daily_mean"],
                    "delta_volatility": lrow["annualized_volatility"] - rrow["annualized_volatility"],
                    "delta_mdd": lrow["max_drawdown"] - rrow["max_drawdown"],
                    "delta_calmar": lrow["calmar_ratio"] - rrow["calmar_ratio"],
                    "delta_sortino": lrow["sortino_ratio"] - rrow["sortino_ratio"],
                    "interpretation_hint": _universe_hint(lrow, rrow),
                }
            )
    return pd.DataFrame(rows).sort_values(["portfolio_type", "weight_scheme"]).reset_index(drop=True)


def compute_sleeve_correlation_matrix(return_panel: pd.DataFrame, portfolios: list[PortfolioDefinition]) -> pd.DataFrame:
    """Compute the sleeve daily-return correlation matrix."""

    columns = sorted({f"{key}__daily_return" for p in portfolios for key in p.sleeve_weights})
    corr = return_panel.set_index("date")[columns].corr()
    corr.index.name = "sleeve"
    return corr.reset_index()


def compute_annualized_covariance_matrix(return_panel: pd.DataFrame, portfolios: list[PortfolioDefinition]) -> pd.DataFrame:
    """Compute annualized covariance matrix for used sleeve returns."""

    columns = sorted({f"{key}__daily_return" for p in portfolios for key in p.sleeve_weights})
    cov = return_panel.set_index("date")[columns].cov() * TRADING_DAYS_PER_YEAR
    cov.index.name = "sleeve"
    return cov.reset_index()


def compute_risk_contribution(return_panel: pd.DataFrame, portfolios: list[PortfolioDefinition]) -> pd.DataFrame:
    """Compute static volatility risk contribution for each portfolio sleeve."""

    data = return_panel.set_index("date")
    rows: list[dict[str, object]] = []
    for portfolio in portfolios:
        sleeve_keys = list(portfolio.sleeve_weights)
        cols = [f"{key}__daily_return" for key in sleeve_keys]
        weights = np.array([portfolio.sleeve_weights[key] for key in sleeve_keys], dtype=float)
        cov = data[cols].cov().to_numpy(dtype=float) * TRADING_DAYS_PER_YEAR
        variance = float(weights.T @ cov @ weights)
        portfolio_vol = float(np.sqrt(max(variance, 0.0)))
        marginal = cov @ weights / portfolio_vol if portfolio_vol > 0 else np.full_like(weights, np.nan)
        risk_contrib = weights * marginal
        for key, col, weight, mc, rc in zip(sleeve_keys, cols, weights, marginal, risk_contrib):
            rows.append(
                {
                    "portfolio_name": portfolio.portfolio_name,
                    "universe_name": portfolio.universe_name,
                    "portfolio_type": portfolio.portfolio_type,
                    "weight_scheme": portfolio.weight_scheme,
                    "etf_code": portfolio.sleeve_to_etf[key],
                    "sleeve_key": key,
                    "sleeve_return_column": col,
                    "weight": weight,
                    "portfolio_volatility": portfolio_vol,
                    "marginal_contribution": mc,
                    "risk_contribution": rc,
                    "risk_contribution_pct": _safe_div(rc, portfolio_vol),
                }
            )
    return pd.DataFrame(rows)


def _baseline_hint(row: pd.Series, base: pd.Series) -> str:
    sharpe_up = row["sharpe_daily_mean"] > base["sharpe_daily_mean"]
    mdd_down = row["max_drawdown"] < base["max_drawdown"]
    cagr_up = row["annualized_return_cagr"] > base["annualized_return_cagr"]
    if sharpe_up and mdd_down and cagr_up:
        return "selected 相对匹配 pure ETF 基准同时改善收益、Sharpe 和回撤"
    if sharpe_up and mdd_down:
        return "selected 改善风险调整路径，但收益取舍仍需复核"
    if mdd_down:
        return "selected 主要降低最大回撤"
    if cagr_up:
        return "selected 主要改善收益"
    return "selected 未明显优于匹配 pure ETF 基准"


def _universe_hint(left: pd.Series, right: pd.Series) -> str:
    sharpe_up = left["sharpe_daily_mean"] > right["sharpe_daily_mean"]
    mdd_down = left["max_drawdown"] < right["max_drawdown"]
    cagr_up = left["annualized_return_cagr"] > right["annualized_return_cagr"]
    if sharpe_up and mdd_down and cagr_up:
        return "Universe B 同时改善收益、Sharpe 和回撤"
    if sharpe_up and mdd_down:
        return "Universe B 改善风险控制，但可能牺牲成长暴露"
    if mdd_down:
        return "Universe B 降低回撤，但成长分散化收益较有限"
    if cagr_up:
        return "Universe B 改善收益，但需要复核风险影响"
    return "本组匹配比较中 Universe A 仍更强"


def _safe_div(numerator: float, denominator: float) -> float:
    if denominator is None or pd.isna(denominator) or abs(float(denominator)) < 1e-12:
        return np.nan
    return float(numerator) / float(denominator)
