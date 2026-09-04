from __future__ import annotations

import numpy as np
import pandas as pd

from src.metrics.ver2_metric_standard import TRADING_DAYS_PER_YEAR, compute_portfolio_option_contribution

from .config import UniverseSpec, sleeve_return_column


def compute_option_leg_attribution(
    best_rows: pd.DataFrame,
    universes: dict[str, UniverseSpec],
    sample_panel: pd.DataFrame,
    option_leg_panel: pd.DataFrame,
    *,
    attribution_method: str,
) -> pd.DataFrame:
    """Compute sleeve and portfolio-level additive option-leg contribution."""

    if option_leg_panel.empty:
        return pd.DataFrame()
    option = option_leg_panel.copy()
    option["date"] = pd.to_datetime(option["date"])
    option = option.set_index("date").reindex(pd.to_datetime(sample_panel["date"])).fillna(0.0)
    rows: list[dict[str, object]] = []
    feasible = best_rows[best_rows["feasible"].astype(bool)].copy()
    for _, row in feasible.iterrows():
        universe = universes[str(row["universe_short"])]
        total = pd.Series(0.0, index=option.index)
        for etf, sleeve in universe.sleeves_by_etf.items():
            col = sleeve_return_column(etf, sleeve)
            weight = float(row[f"weight_{etf}"])
            daily = option[col].astype(float) * weight if col in option.columns else pd.Series(0.0, index=option.index)
            total = total.add(daily, fill_value=0.0)
            rows.append(
                {
                    "portfolio_name": row["portfolio_name"],
                    "universe_short": row["universe_short"],
                    "constraint_set": row["constraint_set"],
                    "D_star": row["D_star"],
                    "etf_code": etf,
                    "sleeve_name": sleeve,
                    "sleeve_key": f"{etf}__{sleeve}",
                    "weight": weight,
                    "option_leg_annualized_pnl_contribution": compute_portfolio_option_contribution(daily, n_days=len(sample_panel)),
                    "attribution_method": attribution_method,
                }
            )
        rows.append(
            {
                "portfolio_name": row["portfolio_name"],
                "universe_short": row["universe_short"],
                "constraint_set": row["constraint_set"],
                "D_star": row["D_star"],
                "etf_code": "PORTFOLIO",
                "sleeve_name": "PORTFOLIO_TOTAL",
                "sleeve_key": "PORTFOLIO_TOTAL",
                "weight": 1.0,
                "option_leg_annualized_pnl_contribution": compute_portfolio_option_contribution(total, n_days=len(sample_panel)),
                "attribution_method": attribution_method,
            }
        )
    return pd.DataFrame(rows)


def compute_sleeve_correlation_matrix(sample_panel: pd.DataFrame, universes: dict[str, UniverseSpec]) -> pd.DataFrame:
    """Return sleeve return correlations in long matrix form."""

    rows: list[dict[str, object]] = []
    for universe in universes.values():
        labels = [f"{etf}__{sleeve}" for etf, sleeve in universe.sleeves_by_etf.items()]
        cols = [sleeve_return_column(etf, sleeve) for etf, sleeve in universe.sleeves_by_etf.items()]
        corr = sample_panel[cols].astype(float).corr()
        for row_label, row_col in zip(labels, cols):
            for col_label, col_col in zip(labels, cols):
                rows.append(
                    {
                        "universe_short": universe.universe_short,
                        "row_sleeve": row_label,
                        "col_sleeve": col_label,
                        "correlation": float(corr.loc[row_col, col_col]),
                    }
                )
    return pd.DataFrame(rows)


def compute_annualized_covariance_matrix(sample_panel: pd.DataFrame, universes: dict[str, UniverseSpec]) -> pd.DataFrame:
    """Return annualized sleeve covariance in long matrix form."""

    rows: list[dict[str, object]] = []
    for universe in universes.values():
        labels = [f"{etf}__{sleeve}" for etf, sleeve in universe.sleeves_by_etf.items()]
        cols = [sleeve_return_column(etf, sleeve) for etf, sleeve in universe.sleeves_by_etf.items()]
        cov = sample_panel[cols].astype(float).cov() * TRADING_DAYS_PER_YEAR
        for row_label, row_col in zip(labels, cols):
            for col_label, col_col in zip(labels, cols):
                rows.append(
                    {
                        "universe_short": universe.universe_short,
                        "row_sleeve": row_label,
                        "col_sleeve": col_label,
                        "annualized_covariance": float(cov.loc[row_col, col_col]),
                    }
                )
    return pd.DataFrame(rows)


def compute_risk_contribution(
    best_rows: pd.DataFrame,
    universes: dict[str, UniverseSpec],
    sample_panel: pd.DataFrame,
) -> pd.DataFrame:
    """Compute volatility risk contribution for feasible best frontier points."""

    rows: list[dict[str, object]] = []
    feasible = best_rows[best_rows["feasible"].astype(bool)].copy()
    for _, row in feasible.iterrows():
        universe = universes[str(row["universe_short"])]
        etfs = list(universe.etf_codes)
        cols = [sleeve_return_column(etf, universe.sleeves_by_etf[etf]) for etf in etfs]
        cov = sample_panel[cols].astype(float).cov().to_numpy() * TRADING_DAYS_PER_YEAR
        weights = np.array([float(row[f"weight_{etf}"]) for etf in etfs])
        variance = float(weights @ cov @ weights)
        portfolio_vol = float(np.sqrt(max(variance, 0.0)))
        marginal = cov @ weights
        component_var = weights * marginal
        for etf, component, weight in zip(etfs, component_var, weights):
            rows.append(
                {
                    "portfolio_name": row["portfolio_name"],
                    "universe_short": row["universe_short"],
                    "constraint_set": row["constraint_set"],
                    "D_star": row["D_star"],
                    "etf_code": etf,
                    "sleeve_name": universe.sleeves_by_etf[etf],
                    "weight": float(weight),
                    "portfolio_volatility": portfolio_vol,
                    "risk_contribution_to_variance": float(component),
                    "risk_contribution_pct": float(component / variance) if variance > 0 else np.nan,
                }
            )
    return pd.DataFrame(rows)
