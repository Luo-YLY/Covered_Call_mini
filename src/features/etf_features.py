from __future__ import annotations

import numpy as np
import pandas as pd


def max_drawdown(nav: pd.Series) -> float:
    nav = nav.dropna()
    if nav.empty:
        return np.nan
    running_max = nav.cummax()
    dd = nav / running_max - 1
    return float(dd.min())


def realized_volatility(prices: pd.Series, window: int) -> pd.Series:
    returns = prices.pct_change()
    return returns.rolling(window).std() * np.sqrt(252)


def compute_etf_tradability_metrics(etf_prices: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for etf_code, g in etf_prices.groupby("etf_code"):
        g = g.sort_values("date").copy()
        returns = g["adj_close"].pct_change()
        price_series = g.set_index("date")["adj_close"]
        try:
            monthly = price_series.resample("ME").last().pct_change().dropna()
        except ValueError:
            monthly = price_series.resample("M").last().pct_change().dropna()
        full_calendar = pd.bdate_range(g["date"].min(), g["date"].max())
        completeness = len(g) / len(full_calendar) if len(full_calendar) else np.nan
        rows.append(
            {
                "etf_code": etf_code,
                "start_date": g["date"].min(),
                "end_date": g["date"].max(),
                "number_of_trading_days": len(g),
                "data_completeness_ratio": completeness,
                "avg_daily_amount_60d": g["amount"].tail(60).mean(),
                "avg_daily_amount_252d": g["amount"].tail(252).mean(),
                "median_daily_amount_252d": g["amount"].tail(252).median(),
                "avg_daily_volume_252d": g["volume"].tail(252).mean(),
                "annualized_return_252d": (1 + returns.tail(252).mean()) ** 252 - 1,
                "annualized_vol_252d": returns.tail(252).std() * np.sqrt(252),
                "max_drawdown_full_sample": max_drawdown(g["adj_close"] / g["adj_close"].iloc[0]),
                "monthly_return_volatility": monthly.std(),
                "strong_up_month_frequency": (monthly > 0.05).mean() if len(monthly) else np.nan,
                "strong_down_month_frequency": (monthly < -0.05).mean() if len(monthly) else np.nan,
                "median_monthly_return": monthly.median() if len(monthly) else np.nan,
                "realized_vol_20d_median": realized_volatility(g["adj_close"], 20).median(),
                "realized_vol_60d_median": realized_volatility(g["adj_close"], 60).median(),
            }
        )
    return pd.DataFrame(rows)
