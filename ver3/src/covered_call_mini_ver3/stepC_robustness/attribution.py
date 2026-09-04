from __future__ import annotations

import numpy as np
import pandas as pd

from src.metrics.ver2_metric_standard import TRADING_DAYS_PER_YEAR, compute_portfolio_option_contribution

from .config import CandidateSpec, sleeve_return_column


def compute_option_leg_attribution(
    option_leg_panel: pd.DataFrame,
    sample_dates: pd.Series,
    candidates: list[CandidateSpec],
    *,
    attribution_method: str,
) -> pd.DataFrame:
    """Compute sleeve and portfolio-level option-leg contribution."""

    if option_leg_panel.empty:
        return pd.DataFrame()
    option = option_leg_panel.copy()
    option["date"] = pd.to_datetime(option["date"])
    option = option.set_index("date").reindex(pd.to_datetime(sample_dates)).fillna(0.0)
    rows: list[dict[str, object]] = []
    for candidate in candidates:
        total = pd.Series(0.0, index=option.index)
        for sleeve_key, weight in candidate.sleeve_weights.items():
            col = sleeve_return_column(sleeve_key)
            daily = option[col].astype(float) * float(weight) if col in option.columns else pd.Series(0.0, index=option.index)
            total = total.add(daily, fill_value=0.0)
            etf_code, sleeve_name = sleeve_key.split("__", 1)
            rows.append(
                {
                    "portfolio_name": candidate.portfolio_name,
                    "source_portfolio_name": candidate.source_portfolio_name,
                    "universe_short": candidate.universe_short,
                    "role": candidate.role,
                    "etf_code": etf_code,
                    "sleeve_key": sleeve_key,
                    "sleeve_name": sleeve_name,
                    "weight": float(weight),
                    "option_leg_annualized_pnl_contribution": compute_portfolio_option_contribution(daily, n_days=len(option)),
                    "attribution_method": attribution_method,
                }
            )
        rows.append(
            {
                "portfolio_name": candidate.portfolio_name,
                "source_portfolio_name": candidate.source_portfolio_name,
                "universe_short": candidate.universe_short,
                "role": candidate.role,
                "etf_code": "PORTFOLIO",
                "sleeve_key": "PORTFOLIO_TOTAL",
                "sleeve_name": "PORTFOLIO_TOTAL",
                "weight": 1.0,
                "option_leg_annualized_pnl_contribution": compute_portfolio_option_contribution(total, n_days=len(option)),
                "attribution_method": attribution_method,
            }
        )
    return pd.DataFrame(rows)


def compute_risk_contribution(sample_panel: pd.DataFrame, candidates: list[CandidateSpec]) -> pd.DataFrame:
    """Compute static volatility risk contribution for candidates."""

    data = sample_panel.set_index("date")
    rows: list[dict[str, object]] = []
    for candidate in candidates:
        sleeve_keys = list(candidate.sleeve_weights)
        cols = [sleeve_return_column(key) for key in sleeve_keys]
        weights = np.array([candidate.sleeve_weights[key] for key in sleeve_keys], dtype=float)
        cov = data[cols].astype(float).cov().to_numpy() * TRADING_DAYS_PER_YEAR
        variance = float(weights @ cov @ weights)
        portfolio_vol = float(np.sqrt(max(variance, 0.0)))
        marginal = cov @ weights
        component_var = weights * marginal
        for sleeve_key, col, weight, component in zip(sleeve_keys, cols, weights, component_var):
            etf_code, sleeve_name = sleeve_key.split("__", 1)
            rows.append(
                {
                    "portfolio_name": candidate.portfolio_name,
                    "source_portfolio_name": candidate.source_portfolio_name,
                    "universe_short": candidate.universe_short,
                    "role": candidate.role,
                    "etf_code": etf_code,
                    "sleeve_key": sleeve_key,
                    "sleeve_name": sleeve_name,
                    "sleeve_return_column": col,
                    "weight": float(weight),
                    "portfolio_volatility": portfolio_vol,
                    "risk_contribution_to_variance": float(component),
                    "risk_contribution_pct": float(component / variance) if variance > 0 else np.nan,
                }
            )
    return pd.DataFrame(rows)
