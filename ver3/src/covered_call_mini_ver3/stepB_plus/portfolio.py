from __future__ import annotations

import numpy as np
import pandas as pd

from .config import INITIAL_NAV, UniverseSpec, sleeve_return_column


def compute_portfolio_returns(
    sample_panel: pd.DataFrame,
    universe: UniverseSpec,
    weights: dict[str, float],
    option_leg_panel: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Compute daily weighted portfolio returns and option-leg returns."""

    returns = sample_panel.set_index("date")
    option = (
        option_leg_panel.set_index("date").reindex(returns.index)
        if option_leg_panel is not None and not option_leg_panel.empty
        else pd.DataFrame(index=returns.index)
    )
    total = pd.Series(0.0, index=returns.index)
    option_leg = pd.Series(0.0, index=returns.index)
    for etf, sleeve in universe.sleeves_by_etf.items():
        col = sleeve_return_column(etf, sleeve)
        weight = float(weights[etf])
        total = total.add(returns[col].astype(float) * weight, fill_value=0.0)
        if col in option.columns:
            option_leg = option_leg.add(option[col].astype(float) * weight, fill_value=0.0)
    return pd.DataFrame(
        {
            "date": returns.index,
            "portfolio_daily_return": total.values,
            "portfolio_option_leg_return": option_leg.values,
        }
    )


def build_nav_series(portfolio_returns: pd.DataFrame) -> pd.DataFrame:
    """Build NAV from daily returns using an initial reference NAV of 1.0."""

    out = portfolio_returns[["date", "portfolio_daily_return"]].copy()
    out["nav"] = (1.0 + out["portfolio_daily_return"].astype(float)).cumprod() * INITIAL_NAV
    out["initial_nav"] = INITIAL_NAV
    return out[["date", "nav", "initial_nav"]]


def compute_drawdown_series(portfolio_nav: pd.DataFrame) -> pd.DataFrame:
    """Return signed drawdown and positive drawdown magnitude."""

    out = portfolio_nav[["date", "nav"]].copy()
    out["rolling_peak_nav"] = out["nav"].astype(float).cummax()
    out["drawdown"] = out["nav"].astype(float) / out["rolling_peak_nav"] - 1.0
    out["drawdown_magnitude"] = -out["drawdown"]
    return out[["date", "drawdown", "drawdown_magnitude", "rolling_peak_nav"]]


def weights_to_name(universe_short: str, constraint_set: str, d_star: float | None, weights: dict[str, float]) -> str:
    """Build a stable portfolio name for grid-selected portfolios."""

    suffix = "all_grid" if d_star is None else f"D{int(round(d_star * 100)):02d}"
    weight_text = "_".join(f"{etf}{int(round(weight * 100)):02d}" for etf, weight in weights.items())
    return f"{universe_short}_{constraint_set}_{suffix}_{weight_text}"


def max_drawdown_from_returns(daily_returns: np.ndarray) -> float:
    """Compute positive MDD magnitude directly from daily returns."""

    nav = np.cumprod(1.0 + daily_returns)
    if nav.size == 0:
        return np.nan
    peak = np.maximum.accumulate(nav)
    return float(np.max(1.0 - nav / peak))
