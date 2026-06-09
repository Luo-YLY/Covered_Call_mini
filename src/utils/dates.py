from __future__ import annotations

import pandas as pd


def month_end_roll_dates(price_dates: pd.Series) -> pd.DatetimeIndex:
    dates = pd.DatetimeIndex(pd.to_datetime(price_dates).sort_values().unique())
    if len(dates) == 0:
        return pd.DatetimeIndex([])
    grouped = pd.Series(dates, index=dates).groupby(dates.to_period("M")).last()
    return pd.DatetimeIndex(grouped.values)


def nearest_trading_date_on_or_after(dates: pd.Series, target: pd.Timestamp) -> pd.Timestamp | None:
    idx = pd.DatetimeIndex(pd.to_datetime(dates).sort_values().unique())
    possible = idx[idx >= pd.Timestamp(target)]
    if len(possible) > 0:
        return possible[0]
    return idx[-1] if len(idx) else None
