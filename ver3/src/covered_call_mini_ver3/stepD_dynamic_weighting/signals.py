from __future__ import annotations

import numpy as np
import pandas as pd

from .universe import UniverseData


def build_monthly_rebalance_schedule(dates: pd.Series, lookback: int) -> pd.DataFrame:
    """Use month-end signal dates and apply weights from the next trading day."""

    date_index = pd.Series(pd.to_datetime(dates).sort_values().drop_duplicates().to_list(), name="date")
    if len(date_index) <= lookback:
        raise ValueError(f"Not enough dates for lookback={lookback}.")
    indexed = pd.DataFrame({"date": date_index, "row_number": np.arange(len(date_index))})
    indexed["month"] = indexed["date"].dt.to_period("M")
    month_end = indexed.groupby("month", as_index=False).tail(1)
    month_end = month_end[(month_end["row_number"] >= lookback - 1) & (month_end["row_number"] + 1 < len(date_index))]
    rows = []
    for _, row in month_end.iterrows():
        signal_index = int(row["row_number"])
        effective_index = signal_index + 1
        rows.append(
            {
                "lookback": int(lookback),
                "signal_date": date_index.iloc[signal_index],
                "effective_date": date_index.iloc[effective_index],
                "signal_row_number": signal_index,
                "effective_row_number": effective_index,
                "rebalance_frequency": "monthly",
                "signal_uses_data_through": date_index.iloc[signal_index],
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        raise ValueError(f"No monthly signal dates available for lookback={lookback}.")
    return out


def compute_rolling_signal_tables(data: UniverseData, schedule: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compute rolling volatility and covariance tables at monthly signal dates."""

    returns = data.returns.set_index("date")[list(data.universe.etf_codes)].astype(float)
    vol_rows: list[dict[str, object]] = []
    cov_rows: list[dict[str, object]] = []
    for _, row in schedule.iterrows():
        lookback = int(row["lookback"])
        signal_date = pd.Timestamp(row["signal_date"])
        window = returns.loc[:signal_date].tail(lookback)
        if len(window) != lookback:
            raise ValueError(f"Rolling window length mismatch for {data.universe.universe_short} {signal_date.date()}.")
        vol_daily = window.std(ddof=1).replace(0.0, np.nan)
        vol_annualized = vol_daily * np.sqrt(252.0)
        cov_daily = window.cov()
        cov_annualized = cov_daily * 252.0
        for asset in data.universe.assets:
            vol_rows.append(
                {
                    "universe_short": data.universe.universe_short,
                    "lookback": lookback,
                    "signal_date": signal_date,
                    "effective_date": pd.Timestamp(row["effective_date"]),
                    "etf_code": asset.etf_code,
                    "sleeve_key": asset.sleeve_key,
                    "rolling_vol_daily": float(vol_daily.loc[asset.etf_code]),
                    "rolling_vol_annualized": float(vol_annualized.loc[asset.etf_code]),
                    "window_start": window.index.min(),
                    "window_end": window.index.max(),
                    "n_window_obs": int(len(window)),
                    "lag_rule": "signal uses data through signal_date; weights apply on next trading day",
                }
            )
        for left in data.universe.etf_codes:
            for right in data.universe.etf_codes:
                cov_rows.append(
                    {
                        "universe_short": data.universe.universe_short,
                        "lookback": lookback,
                        "signal_date": signal_date,
                        "effective_date": pd.Timestamp(row["effective_date"]),
                        "asset_i": left,
                        "asset_j": right,
                        "covariance_daily": float(cov_daily.loc[left, right]),
                        "covariance_annualized": float(cov_annualized.loc[left, right]),
                        "window_start": window.index.min(),
                        "window_end": window.index.max(),
                        "n_window_obs": int(len(window)),
                    }
                )
    return pd.DataFrame(vol_rows), pd.DataFrame(cov_rows)
