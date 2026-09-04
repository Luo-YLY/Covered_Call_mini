from __future__ import annotations

import pandas as pd

from .config import INITIAL_NAV, PortfolioDefinition


def build_portfolio_returns(
    return_panel: pd.DataFrame,
    option_leg_panel: pd.DataFrame,
    portfolios: list[PortfolioDefinition],
) -> pd.DataFrame:
    """Build fixed-weight portfolio daily total and option-leg returns."""

    option = option_leg_panel.set_index("date")
    returns = return_panel.set_index("date")
    rows: list[pd.DataFrame] = []
    for portfolio in portfolios:
        total = pd.Series(0.0, index=returns.index)
        option_leg = pd.Series(0.0, index=returns.index)
        for sleeve_key, weight in portfolio.sleeve_weights.items():
            col = f"{sleeve_key}__daily_return"
            total = total.add(returns[col].astype(float) * float(weight), fill_value=0.0)
            if col in option.columns:
                option_leg = option_leg.add(option[col].reindex(returns.index).astype(float) * float(weight), fill_value=0.0)
        frame = pd.DataFrame(
            {
                "date": returns.index,
                "portfolio_name": portfolio.portfolio_name,
                "universe_name": portfolio.universe_name,
                "universe_short": portfolio.universe_short,
                "portfolio_type": portfolio.portfolio_type,
                "weight_scheme": portfolio.weight_scheme,
                "portfolio_daily_return": total.values,
                "portfolio_option_leg_return": option_leg.values,
                "initial_nav": INITIAL_NAV,
            }
        )
        rows.append(frame)
    return pd.concat(rows, ignore_index=True, sort=False).sort_values(["portfolio_name", "date"]).reset_index(drop=True)


def build_nav_from_returns(portfolio_returns: pd.DataFrame) -> pd.DataFrame:
    """Build NAV paths from portfolio returns."""

    frames: list[pd.DataFrame] = []
    for portfolio_name, g in portfolio_returns.groupby("portfolio_name", sort=False):
        nav = (1.0 + g["portfolio_daily_return"].astype(float)).cumprod() * INITIAL_NAV
        out = g[
            [
                "date",
                "portfolio_name",
                "universe_name",
                "universe_short",
                "portfolio_type",
                "weight_scheme",
                "initial_nav",
            ]
        ].copy()
        out["nav"] = nav.values
        out["final_nav_to_date"] = out["nav"]
        frames.append(out)
    return pd.concat(frames, ignore_index=True, sort=False)


def compute_drawdown_series(portfolio_nav: pd.DataFrame) -> pd.DataFrame:
    """Compute positive-magnitude drawdown fields and signed drawdown path."""

    frames: list[pd.DataFrame] = []
    for _portfolio_name, g in portfolio_nav.groupby("portfolio_name", sort=False):
        out = g.copy()
        peak = out["nav"].astype(float).cummax()
        out["rolling_peak_nav"] = peak
        out["drawdown"] = out["nav"].astype(float) / peak - 1.0
        out["drawdown_magnitude"] = -out["drawdown"]
        frames.append(out[["date", "portfolio_name", "drawdown", "drawdown_magnitude", "rolling_peak_nav"]])
    return pd.concat(frames, ignore_index=True, sort=False)


def portfolio_weight_map(portfolios: list[PortfolioDefinition]) -> pd.DataFrame:
    """Return one row per portfolio sleeve weight."""

    rows = []
    for portfolio in portfolios:
        for sleeve_key, weight in portfolio.sleeve_weights.items():
            rows.append(
                {
                    "portfolio_name": portfolio.portfolio_name,
                    "universe_name": portfolio.universe_name,
                    "universe_short": portfolio.universe_short,
                    "portfolio_type": portfolio.portfolio_type,
                    "weight_scheme": portfolio.weight_scheme,
                    "etf_code": portfolio.sleeve_to_etf[sleeve_key],
                    "sleeve_key": sleeve_key,
                    "sleeve_name": sleeve_key.split("__", 1)[1],
                    "weight": weight,
                }
            )
    return pd.DataFrame(rows)
