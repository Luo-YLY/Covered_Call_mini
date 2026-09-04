from __future__ import annotations

import numpy as np
import pandas as pd

from src.metrics.ver2_metric_standard import compute_portfolio_option_contribution

from .universe import UniverseData


def compute_option_leg_attribution(daily_returns: pd.DataFrame) -> pd.DataFrame:
    """Summarize dynamic portfolio option-leg contribution."""

    rows = []
    for strategy, group in daily_returns.groupby("strategy_name", sort=False):
        g = group.sort_values("date")
        option = g["portfolio_option_leg_return"].astype(float)
        total = g["portfolio_daily_return"].astype(float)
        rows.append(
            {
                "strategy_name": strategy,
                "universe_short": g["universe_short"].iloc[0],
                "method": g["method"].iloc[0],
                "lookback": int(g["lookback"].iloc[0]),
                "sample_start": pd.to_datetime(g["date"]).min().date().isoformat(),
                "sample_end": pd.to_datetime(g["date"]).max().date().isoformat(),
                "n_trading_days": int(len(g)),
                "option_leg_cumulative_simple_return": float(option.sum()),
                "portfolio_cumulative_simple_return": float(total.sum()),
                "option_leg_annualized_pnl_contribution": compute_portfolio_option_contribution(option, n_days=len(g)),
                "avg_daily_option_leg_return": float(option.mean()),
                "option_leg_positive_day_rate": float((option > 0).mean()),
                "attribution_method": "weighted Step A daily_return_option_leg_component",
            }
        )
    return pd.DataFrame(rows)


def compute_risk_contribution(datas: list[UniverseData], daily_weight_paths: pd.DataFrame) -> pd.DataFrame:
    """Approximate ex-post variance contribution using average dynamic weights."""

    data_by_universe = {data.universe.universe_short: data for data in datas}
    rows = []
    for strategy, group in daily_weight_paths.groupby("strategy_name", sort=False):
        meta = group.iloc[0]
        data = data_by_universe[str(meta["universe_short"])]
        weights = (
            group.pivot_table(index="date", columns="etf_code", values="target_weight", aggfunc="last")
            .sort_index()
            .reindex(columns=list(data.universe.etf_codes))
        )
        returns = data.returns.set_index("date")[list(data.universe.etf_codes)].astype(float).reindex(weights.index)
        avg_w = weights.mean()
        cov = returns.cov()
        portfolio_var = float(avg_w.to_numpy(dtype=float) @ cov.to_numpy(dtype=float) @ avg_w.to_numpy(dtype=float))
        marginal = cov @ avg_w
        for asset in data.universe.assets:
            contribution = float(avg_w.loc[asset.etf_code] * marginal.loc[asset.etf_code])
            rows.append(
                {
                    "strategy_name": strategy,
                    "universe_short": data.universe.universe_short,
                    "method": meta["method"],
                    "lookback": int(meta["lookback"]),
                    "etf_code": asset.etf_code,
                    "sleeve_key": asset.sleeve_key,
                    "avg_target_weight": float(avg_w.loc[asset.etf_code]),
                    "asset_vol_annualized": float(returns[asset.etf_code].std(ddof=1) * np.sqrt(252.0)),
                    "covariance_contribution": contribution,
                    "risk_contribution_to_variance": contribution / portfolio_var if portfolio_var > 0 else np.nan,
                    "risk_contribution_method": "ex_post_average_weight_covariance",
                }
            )
    return pd.DataFrame(rows)
