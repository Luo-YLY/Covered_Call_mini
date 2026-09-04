from __future__ import annotations

import numpy as np
import pandas as pd

from .config import EventWindowSpec
from .metrics import compute_metrics_from_returns


def manual_event_window_table(windows: list[EventWindowSpec]) -> pd.DataFrame:
    """Convert manual event windows to a table."""

    return pd.DataFrame(
        [
            {
                "event_id": f"manual_{i+1:02d}_{item.event_name}",
                "event_name": item.event_name,
                "event_type": item.event_type,
                "source_portfolio": "MANUAL",
                "source_date": "",
                "start_date": item.start_date,
                "end_date": item.end_date,
                "window_radius_days": "",
                "rank": "",
                "description": item.description,
            }
            for i, item in enumerate(windows)
        ]
    )


def detect_extreme_event_windows(
    candidate_returns: pd.DataFrame,
    *,
    top_n: int = 10,
    radius_days: int = 5,
    rolling_window_days: int = 20,
) -> pd.DataFrame:
    """Detect extreme event windows from candidate daily returns."""

    rows: list[dict[str, object]] = []
    for portfolio_name, group in candidate_returns.groupby("portfolio_name", sort=True):
        g = group.sort_values("date").reset_index(drop=True)
        dates = pd.to_datetime(g["date"]).reset_index(drop=True)
        returns = g["portfolio_daily_return"].astype(float).reset_index(drop=True)

        for event_type, selected in [
            ("auto_downside_return", returns.nsmallest(top_n)),
            ("auto_upside_return", returns.nlargest(top_n)),
        ]:
            for rank, idx in enumerate(selected.index, start=1):
                rows.append(_event_row(event_type, portfolio_name, dates, int(idx), radius_days, rank, "基于单日组合收益自动识别。"))

        rolling_return = returns.rolling(rolling_window_days).sum()
        rolling_mdd = _rolling_mdd(returns, rolling_window_days)
        for event_type, selected, desc in [
            ("auto_rolling_drawdown", rolling_mdd.nlargest(top_n), "基于 rolling 20d 最大回撤自动识别。"),
            ("auto_rolling_return", rolling_return.nlargest(top_n), "基于 rolling 20d 最高累计收益自动识别。"),
        ]:
            for rank, idx in enumerate(selected.dropna().index, start=1):
                rows.append(_event_row(event_type, portfolio_name, dates, int(idx), radius_days, rank, desc))

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out.drop_duplicates(["event_type", "source_portfolio", "start_date", "end_date"]).reset_index(drop=True)
    out["event_id"] = [f"auto_{i+1:04d}" for i in range(len(out))]
    return out[
        [
            "event_id",
            "event_name",
            "event_type",
            "source_portfolio",
            "source_date",
            "start_date",
            "end_date",
            "window_radius_days",
            "rank",
            "description",
        ]
    ]


def evaluate_event_exclusion(candidate_returns: pd.DataFrame, event_windows: pd.DataFrame) -> pd.DataFrame:
    """Evaluate full-sample and event-exclusion metrics."""

    rows = []
    full = compute_metrics_from_returns(candidate_returns, group_cols=["portfolio_name"])
    full_lookup = full.set_index("portfolio_name")
    cases = [
        ("full_sample_metrics", set()),
        ("exclude_downside_event_metrics", _event_dates(event_windows, {"auto_downside_return", "auto_rolling_drawdown", "manual_downside_market"})),
        ("exclude_upside_event_metrics", _event_dates(event_windows, {"auto_upside_return", "auto_rolling_return", "manual_upside_policy"})),
        ("exclude_all_extreme_event_metrics", _event_dates(event_windows, set(event_windows["event_type"].astype(str).unique()))),
    ]
    for portfolio_name, group in candidate_returns.groupby("portfolio_name", sort=True):
        for case_name, dates_to_remove in cases:
            if dates_to_remove:
                data = group[~pd.to_datetime(group["date"]).dt.date.astype(str).isin(dates_to_remove)].copy()
            else:
                data = group.copy()
            if len(data) < 3:
                continue
            metrics = compute_metrics_from_returns(data, group_cols=["portfolio_name"]).iloc[0].to_dict()
            base = full_lookup.loc[portfolio_name]
            rows.append(
                {
                    "portfolio_name": portfolio_name,
                    "diagnostic_case": case_name,
                    "removed_trading_days": int(len(group) - len(data)),
                    **metrics,
                    "delta_sharpe_vs_full_sample": float(metrics["sharpe_daily_mean"]) - float(base["sharpe_daily_mean"]),
                    "delta_mdd_vs_full_sample": float(metrics["max_drawdown"]) - float(base["max_drawdown"]),
                    "delta_cagr_vs_full_sample": float(metrics["annualized_return_cagr"]) - float(base["annualized_return_cagr"]),
                }
            )
    return pd.DataFrame(rows)


def evaluate_event_window_performance(candidate_returns: pd.DataFrame, event_windows: pd.DataFrame) -> pd.DataFrame:
    """Compute candidate metrics inside each event window."""

    rows: list[pd.DataFrame] = []
    for _, event in event_windows.iterrows():
        start = pd.Timestamp(event["start_date"])
        end = pd.Timestamp(event["end_date"])
        mask = (pd.to_datetime(candidate_returns["date"]) >= start) & (pd.to_datetime(candidate_returns["date"]) <= end)
        data = candidate_returns.loc[mask].copy()
        if data.empty:
            continue
        metrics = compute_metrics_from_returns(data, group_cols=["portfolio_name"])
        for col in ["event_id", "event_name", "event_type", "start_date", "end_date", "description"]:
            metrics[col] = event[col]
        rows.append(metrics)
    return pd.concat(rows, ignore_index=True, sort=False) if rows else pd.DataFrame()


def _event_row(
    event_type: str,
    portfolio_name: str,
    dates: pd.Series,
    idx: int,
    radius_days: int,
    rank: int,
    description: str,
) -> dict[str, object]:
    start_idx = max(0, idx - radius_days)
    end_idx = min(len(dates) - 1, idx + radius_days)
    source_date = dates.iloc[idx].date().isoformat()
    return {
        "event_name": f"{portfolio_name}_{event_type}_{source_date}",
        "event_type": event_type,
        "source_portfolio": portfolio_name,
        "source_date": source_date,
        "start_date": dates.iloc[start_idx].date().isoformat(),
        "end_date": dates.iloc[end_idx].date().isoformat(),
        "window_radius_days": radius_days,
        "rank": rank,
        "description": description,
    }


def _rolling_mdd(returns: pd.Series, window: int) -> pd.Series:
    values = []
    for idx in range(len(returns)):
        if idx + 1 < window:
            values.append(np.nan)
            continue
        window_returns = returns.iloc[idx - window + 1 : idx + 1]
        nav = (1.0 + window_returns.astype(float)).cumprod()
        dd = 1.0 - nav / nav.cummax()
        values.append(float(dd.max()))
    return pd.Series(values, index=returns.index, dtype="float64")


def _event_dates(event_windows: pd.DataFrame, event_types: set[str]) -> set[str]:
    dates: set[str] = set()
    for _, event in event_windows[event_windows["event_type"].astype(str).isin(event_types)].iterrows():
        rng = pd.date_range(event["start_date"], event["end_date"], freq="D")
        dates.update(item.date().isoformat() for item in rng)
    return dates
