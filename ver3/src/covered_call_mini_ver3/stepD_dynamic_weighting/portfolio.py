from __future__ import annotations

import pandas as pd

from .config import INITIAL_NAV
from .universe import UniverseData


def compute_dynamic_daily_returns(data: UniverseData, daily_weight_paths: pd.DataFrame) -> pd.DataFrame:
    """Compute daily portfolio and option-leg returns from dynamic weights."""

    returns = data.returns.set_index("date")[list(data.universe.etf_codes)].astype(float)
    option = data.option_returns.set_index("date")[list(data.universe.etf_codes)].astype(float).reindex(returns.index).fillna(0.0)
    frames = []
    for (strategy, method, lookback), group in daily_weight_paths.groupby(["strategy_name", "method", "lookback"], sort=False):
        weights = (
            group.pivot_table(index="date", columns="etf_code", values="target_weight", aggfunc="last")
            .sort_index()
            .reindex(columns=list(data.universe.etf_codes))
        )
        aligned_returns = returns.reindex(weights.index)
        aligned_option = option.reindex(weights.index).fillna(0.0)
        portfolio_return = (weights * aligned_returns).sum(axis=1)
        option_return = (weights * aligned_option).sum(axis=1)
        frames.append(
            pd.DataFrame(
                {
                    "date": weights.index,
                    "strategy_name": strategy,
                    "portfolio_name": strategy,
                    "universe_short": data.universe.universe_short,
                    "method": method,
                    "lookback": int(lookback),
                    "rebalance_frequency": "monthly",
                    "portfolio_daily_return": portfolio_return.values,
                    "portfolio_option_leg_return": option_return.values,
                    "initial_nav": INITIAL_NAV,
                }
            )
        )
    return pd.concat(frames, ignore_index=True, sort=False).sort_values(["strategy_name", "date"]).reset_index(drop=True)


def build_nav_and_drawdown(daily_returns: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build NAV and drawdown paths from daily returns."""

    nav_frames = []
    dd_frames = []
    for strategy, group in daily_returns.groupby("strategy_name", sort=False):
        g = group.sort_values("date").copy()
        nav = (1.0 + g["portfolio_daily_return"].astype(float)).cumprod() * INITIAL_NAV
        nav_frame = g[["date", "strategy_name", "portfolio_name", "universe_short", "method", "lookback", "rebalance_frequency", "initial_nav"]].copy()
        nav_frame["nav"] = nav.values
        nav_frame["final_nav_to_date"] = nav_frame["nav"]
        peak = nav_frame["nav"].astype(float).cummax()
        dd_frame = nav_frame[["date", "strategy_name", "portfolio_name", "universe_short", "method", "lookback", "rebalance_frequency"]].copy()
        dd_frame["rolling_peak_nav"] = peak.values
        dd_frame["drawdown"] = nav_frame["nav"].astype(float).values / peak.values - 1.0
        dd_frame["drawdown_magnitude"] = -dd_frame["drawdown"]
        nav_frames.append(nav_frame)
        dd_frames.append(dd_frame)
    return (
        pd.concat(nav_frames, ignore_index=True, sort=False),
        pd.concat(dd_frames, ignore_index=True, sort=False),
    )
