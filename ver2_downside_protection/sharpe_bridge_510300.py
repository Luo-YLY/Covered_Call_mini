from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ver2_downside_protection.metrics import max_drawdown_magnitude


LOGGER = logging.getLogger(__name__)

TRADING_DAYS_PER_YEAR = 252.0
DEFAULT_ANNUAL_RISK_FREE_RATE = 0.02

BRIDGE_LEVELS: tuple[tuple[int, str], ...] = (
    (0, "period_settlement"),
    (1, "daily_step_settlement"),
    (2, "daily_etf_only_marking"),
    (3, "daily_mtm_nav"),
)

DEFAULT_CANDIDATES: tuple[tuple[str, str], ...] = (
    ("DTE30", "ATM_100"),
    ("DTE30", "D50_100"),
    ("DTE30", "D40_100"),
    ("DTE30", "OTM2_100"),
    ("DTE60", "ATM_100"),
    ("DTE60", "D50_100"),
    ("DTE60", "D40_100"),
    ("DTE60", "OTM2_100"),
)

PERIOD_USECOLS = [
    "etf_code",
    "dte_label",
    "strategy_name",
    "period_index",
    "rebalance_date",
    "period_end_date",
    "underlying_price_at_entry",
    "underlying_price_at_period_end",
    "coverage_ratio",
    "option_selected_flag",
    "premium_return",
    "upside_payoff_return",
    "transaction_cost_return",
    "etf_period_return",
    "strategy_period_return",
    "assignment_flag",
    "option_code",
    "strike",
    "actual_dte",
    "selected_delta",
]

DAILY_USECOLS = [
    "date",
    "etf_code",
    "dte_label",
    "strategy_name",
    "period_index",
    "rebalance_date",
    "period_end_date",
    "underlying_return_since_entry",
    "option_liability_return",
    "premium_return",
    "transaction_cost_return",
    "period_mtm_return",
    "daily_mtm_nav",
]


@dataclass(frozen=True)
class SharpeBridgePaths:
    source_dir: Path = Path("outputs/ver2_downside_protection/ver2_1_dte_regime")
    output_dir: Path = Path("outputs/ver2_downside_protection/510300_branch/sharpe_bridge")

    @property
    def periods_path(self) -> Path:
        return self.source_dir / "ver2_1_periods_with_regime.csv"

    @property
    def daily_mtm_path(self) -> Path:
        return self.source_dir / "ver2_1_daily_mtm.csv"


def _normalize_etf_code(series: pd.Series) -> pd.Series:
    return series.astype(str).str.replace(".0", "", regex=False).str.zfill(6)


def _candidate_label(dte_label: str, strategy_name: str) -> str:
    return f"{dte_label} {strategy_name}"


def _annualized_return_from_nav(nav: pd.Series) -> float:
    nav = nav.dropna().astype(float)
    if len(nav) < 2 or nav.iloc[0] <= 0 or nav.iloc[-1] <= 0:
        return np.nan
    years = (pd.Timestamp(nav.index[-1]) - pd.Timestamp(nav.index[0])).days / 365.25
    if years <= 0:
        years = max((len(nav) - 1) / TRADING_DAYS_PER_YEAR, 1e-12)
    return float((nav.iloc[-1] / nav.iloc[0]) ** (1.0 / years) - 1.0)


def _monthly_returns_from_returns(returns: pd.Series) -> pd.Series:
    if returns.empty:
        return pd.Series(dtype=float)
    return returns.groupby(returns.index.to_period("M")).apply(lambda s: float((1.0 + s).prod() - 1.0))


def _strict_sharpe(
    returns: pd.Series,
    annual_factor: float,
    *,
    annual_risk_free_rate: float = DEFAULT_ANNUAL_RISK_FREE_RATE,
) -> tuple[float, float]:
    """Return strict Sharpe ratios without rf and with annual rf converted to the return frequency."""

    returns = returns.dropna().astype(float)
    if len(returns) <= 1:
        return np.nan, np.nan
    volatility = returns.std(ddof=1)
    if pd.isna(volatility) or volatility <= 0 or pd.isna(annual_factor) or annual_factor <= 0:
        return np.nan, np.nan
    no_rf = float(returns.mean() / volatility * np.sqrt(annual_factor))
    rf_per_period = (1.0 + annual_risk_free_rate) ** (1.0 / annual_factor) - 1.0
    with_rf = float((returns - rf_per_period).mean() / volatility * np.sqrt(annual_factor))
    return no_rf, with_rf


def _metric_row_from_returns(
    *,
    returns: pd.Series,
    nav: pd.Series,
    annual_factor: float,
    level_order: int,
    level: str,
    etf_code: str,
    dte_label: str,
    strategy_name: str,
    return_frequency: str,
    is_execution_adjusted: bool,
) -> dict[str, object]:
    returns = returns.dropna().astype(float)
    nav = nav.dropna().astype(float)
    annualized_return = _annualized_return_from_nav(nav)
    annualized_volatility = (
        float(returns.std(ddof=1) * np.sqrt(annual_factor)) if len(returns.dropna()) > 1 else np.nan
    )
    downside = returns[returns < 0]
    downside_volatility = (
        float(downside.std(ddof=1) * np.sqrt(annual_factor)) if len(downside.dropna()) > 1 else np.nan
    )
    strict_sharpe_no_rf, strict_sharpe_rf_2pct = _strict_sharpe(returns, annual_factor)
    mdd = max_drawdown_magnitude(nav)
    monthly_returns = _monthly_returns_from_returns(returns)
    return {
        "etf_code": etf_code,
        "dte_label": dte_label,
        "strategy_name": strategy_name,
        "candidate_label": _candidate_label(dte_label, strategy_name),
        "level_order": level_order,
        "bridge_level": level,
        "return_frequency": return_frequency,
        "is_execution_adjusted": is_execution_adjusted,
        "start_date": nav.index.min() if not nav.empty else pd.NaT,
        "end_date": nav.index.max() if not nav.empty else pd.NaT,
        "observations": int(len(returns)),
        "cumulative_return": float(nav.iloc[-1] / nav.iloc[0] - 1.0)
        if len(nav) >= 2 and nav.iloc[0] != 0
        else np.nan,
        "annualized_return": annualized_return,
        "annualized_volatility": annualized_volatility,
        "sharpe_ratio": float(annualized_return / annualized_volatility)
        if pd.notna(annualized_return) and annualized_volatility and annualized_volatility > 0
        else np.nan,
        "strict_sharpe_no_rf": strict_sharpe_no_rf,
        "strict_sharpe_rf_2pct": strict_sharpe_rf_2pct,
        "annual_risk_free_rate": DEFAULT_ANNUAL_RISK_FREE_RATE,
        "sortino_ratio": float(annualized_return / downside_volatility)
        if pd.notna(annualized_return) and downside_volatility and downside_volatility > 0
        else np.nan,
        "max_drawdown": mdd,
        "calmar_ratio": float(annualized_return / mdd) if pd.notna(annualized_return) and mdd and mdd > 0 else np.nan,
        "monthly_win_rate": float((monthly_returns > 0).mean()) if not monthly_returns.empty else np.nan,
        "worst_month_return": float(monthly_returns.min()) if not monthly_returns.empty else np.nan,
    }


def _metric_row_from_daily_nav(
    *,
    nav: pd.Series,
    level_order: int,
    level: str,
    etf_code: str,
    dte_label: str,
    strategy_name: str,
    is_execution_adjusted: bool,
) -> dict[str, object]:
    nav = nav.dropna().astype(float)
    returns = nav.pct_change().dropna()
    return _metric_row_from_returns(
        returns=returns,
        nav=nav,
        annual_factor=TRADING_DAYS_PER_YEAR,
        level_order=level_order,
        level=level,
        etf_code=etf_code,
        dte_label=dte_label,
        strategy_name=strategy_name,
        return_frequency="daily",
        is_execution_adjusted=is_execution_adjusted,
    )


def _gross_period_return(period: pd.Series) -> float:
    return float(period.get("etf_period_return", 0.0) or 0.0) + float(
        period.get("premium_return", 0.0) or 0.0
    ) - float(period.get("upside_payoff_return", 0.0) or 0.0)


def _period_annual_factor(periods: pd.DataFrame) -> float:
    days = (
        pd.to_datetime(periods["period_end_date"]) - pd.to_datetime(periods["rebalance_date"])
    ).dt.days.astype(float)
    mean_days = days.replace(0, np.nan).mean()
    return float(365.0 / mean_days) if pd.notna(mean_days) and mean_days > 0 else 12.0


def _period_settlement_nav(periods: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    periods = periods.sort_values(["rebalance_date", "period_index"]).copy()
    returns = periods.apply(_gross_period_return, axis=1)
    returns.index = pd.DatetimeIndex(pd.to_datetime(periods["period_end_date"]))
    nav_dates = [pd.Timestamp(periods.iloc[0]["rebalance_date"])]
    nav_values = [1.0]
    nav = 1.0
    for _, period in periods.iterrows():
        nav *= 1.0 + _gross_period_return(period)
        nav_dates.append(pd.Timestamp(period["period_end_date"]))
        nav_values.append(nav)
    nav_series = pd.Series(nav_values, index=pd.DatetimeIndex(nav_dates))
    nav_series = nav_series[~nav_series.index.duplicated(keep="last")].sort_index()
    return returns.sort_index(), nav_series


def _deduplicate_daily_nav(rows: list[dict[str, object]]) -> pd.Series:
    if not rows:
        return pd.Series(dtype=float)
    data = pd.DataFrame(rows)
    data["date"] = pd.to_datetime(data["date"])
    data = data.sort_values(["date", "period_index", "_row_order"])
    data = data.groupby("date", as_index=False).tail(1).sort_values("date")
    return pd.Series(data["nav"].astype(float).to_numpy(), index=pd.DatetimeIndex(data["date"]))


def _daily_period_rows(daily_group: pd.DataFrame, period_index: int) -> pd.DataFrame:
    rows = daily_group[daily_group["period_index"].astype(int) == int(period_index)].copy()
    rows["date"] = pd.to_datetime(rows["date"])
    return rows.sort_values("date")


def _daily_step_settlement_nav(periods: pd.DataFrame, daily_group: pd.DataFrame) -> pd.Series:
    rows: list[dict[str, object]] = []
    nav_start = 1.0
    row_order = 0
    for _, period in periods.sort_values(["rebalance_date", "period_index"]).iterrows():
        period_index = int(period["period_index"])
        period_rows = _daily_period_rows(daily_group, period_index)
        if period_rows.empty:
            continue
        nav_end = nav_start * (1.0 + _gross_period_return(period))
        end = pd.Timestamp(period["period_end_date"])
        for _, daily in period_rows.iterrows():
            row_order += 1
            date = pd.Timestamp(daily["date"])
            rows.append(
                {
                    "date": date,
                    "period_index": period_index,
                    "_row_order": row_order,
                    "nav": nav_end if date >= end else nav_start,
                }
            )
        nav_start = nav_end
    return _deduplicate_daily_nav(rows)


def _daily_etf_only_marking_nav(periods: pd.DataFrame, daily_group: pd.DataFrame) -> pd.Series:
    rows: list[dict[str, object]] = []
    nav_start = 1.0
    row_order = 0
    for _, period in periods.sort_values(["rebalance_date", "period_index"]).iterrows():
        period_index = int(period["period_index"])
        period_rows = _daily_period_rows(daily_group, period_index)
        if period_rows.empty:
            continue
        end = pd.Timestamp(period["period_end_date"])
        premium = float(period.get("premium_return", 0.0) or 0.0)
        payoff = float(period.get("upside_payoff_return", 0.0) or 0.0)
        for _, daily in period_rows.iterrows():
            row_order += 1
            date = pd.Timestamp(daily["date"])
            period_return = float(daily.get("underlying_return_since_entry", 0.0) or 0.0) + premium
            if date >= end:
                period_return -= payoff
            rows.append(
                {
                    "date": date,
                    "period_index": period_index,
                    "_row_order": row_order,
                    "nav": nav_start * (1.0 + period_return),
                }
            )
        nav_start *= 1.0 + _gross_period_return(period)
    return _deduplicate_daily_nav(rows)


def _daily_mtm_nav_gross(periods: pd.DataFrame, daily_group: pd.DataFrame) -> pd.Series:
    rows: list[dict[str, object]] = []
    nav_start = 1.0
    row_order = 0
    for _, period in periods.sort_values(["rebalance_date", "period_index"]).iterrows():
        period_index = int(period["period_index"])
        period_rows = _daily_period_rows(daily_group, period_index)
        if period_rows.empty:
            continue
        for _, daily in period_rows.iterrows():
            row_order += 1
            period_return = (
                float(daily.get("underlying_return_since_entry", 0.0) or 0.0)
                + float(daily.get("premium_return", 0.0) or 0.0)
                - float(daily.get("option_liability_return", 0.0) or 0.0)
            )
            rows.append(
                {
                    "date": pd.Timestamp(daily["date"]),
                    "period_index": period_index,
                    "_row_order": row_order,
                    "nav": nav_start * (1.0 + period_return),
                }
            )
        nav_start *= 1.0 + _gross_period_return(period)
    return _deduplicate_daily_nav(rows)


def _current_daily_mtm_nav(daily_group: pd.DataFrame) -> pd.Series:
    work = daily_group.copy()
    work["date"] = pd.to_datetime(work["date"])
    work["_row_order"] = np.arange(len(work))
    work = work.sort_values(["date", "period_index", "_row_order"])
    work = work.groupby("date", as_index=False).tail(1).sort_values("date")
    return pd.Series(work["daily_mtm_nav"].astype(float).to_numpy(), index=pd.DatetimeIndex(work["date"]))


def build_sharpe_bridge_tables(
    periods: pd.DataFrame,
    daily_mtm: pd.DataFrame,
    *,
    etf_code: str = "510300",
    candidates: Iterable[tuple[str, str]] = DEFAULT_CANDIDATES,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build long and summary Sharpe bridge tables for one ETF branch.

    Level 3 uses the stored ver2.1 daily_mtm_nav directly. That NAV already
    includes transaction costs, bid/ask spread assumptions, and slippage, so the
    bridge intentionally does not create a separate execution-adjusted Level 4.
    """

    periods = periods.copy()
    daily_mtm = daily_mtm.copy()
    periods["etf_code"] = _normalize_etf_code(periods["etf_code"])
    daily_mtm["etf_code"] = _normalize_etf_code(daily_mtm["etf_code"])
    periods["rebalance_date"] = pd.to_datetime(periods["rebalance_date"])
    periods["period_end_date"] = pd.to_datetime(periods["period_end_date"])
    daily_mtm["date"] = pd.to_datetime(daily_mtm["date"])
    daily_mtm["period_index"] = daily_mtm["period_index"].astype(int)

    rows: list[dict[str, object]] = []
    candidate_set = set(candidates)
    for dte_label, strategy_name in candidates:
        period_g = periods[
            (periods["etf_code"] == etf_code)
            & (periods["dte_label"] == dte_label)
            & (periods["strategy_name"] == strategy_name)
        ].copy()
        daily_g = daily_mtm[
            (daily_mtm["etf_code"] == etf_code)
            & (daily_mtm["dte_label"] == dte_label)
            & (daily_mtm["strategy_name"] == strategy_name)
        ].copy()
        if period_g.empty or daily_g.empty:
            LOGGER.warning("Skipping missing Sharpe bridge candidate: %s %s %s", etf_code, dte_label, strategy_name)
            continue

        observed_pair = (str(dte_label), str(strategy_name))
        if observed_pair not in candidate_set:
            continue

        period_returns, period_nav = _period_settlement_nav(period_g)
        rows.append(
            _metric_row_from_returns(
                returns=period_returns,
                nav=period_nav,
                annual_factor=_period_annual_factor(period_g),
                level_order=0,
                level="period_settlement",
                etf_code=etf_code,
                dte_label=dte_label,
                strategy_name=strategy_name,
                return_frequency="period",
                is_execution_adjusted=False,
            )
        )
        daily_levels = [
            (1, "daily_step_settlement", _daily_step_settlement_nav(period_g, daily_g), False),
            (2, "daily_etf_only_marking", _daily_etf_only_marking_nav(period_g, daily_g), False),
            (3, "daily_mtm_nav", _current_daily_mtm_nav(daily_g), True),
        ]
        for level_order, level, nav, is_execution_adjusted in daily_levels:
            rows.append(
                _metric_row_from_daily_nav(
                    nav=nav,
                    level_order=level_order,
                    level=level,
                    etf_code=etf_code,
                    dte_label=dte_label,
                    strategy_name=strategy_name,
                    is_execution_adjusted=is_execution_adjusted,
                )
            )

    long = pd.DataFrame(rows)
    if long.empty:
        return long, pd.DataFrame()
    long = long.sort_values(["etf_code", "dte_label", "strategy_name", "level_order"]).reset_index(drop=True)
    summary = build_sharpe_bridge_summary(long)
    return long, summary


def _level_metric(metrics: pd.DataFrame, level: str, metric: str) -> float:
    selected = metrics[metrics["bridge_level"] == level]
    if selected.empty or metric not in selected.columns:
        return np.nan
    return float(selected.iloc[0][metric])


def build_sharpe_bridge_summary(long: pd.DataFrame) -> pd.DataFrame:
    """Build a one-row-per-strategy bridge summary with adjacent-level effects."""

    rows: list[dict[str, object]] = []
    metric_cols = [
        "annualized_return",
        "annualized_volatility",
        "sharpe_ratio",
        "strict_sharpe_no_rf",
        "strict_sharpe_rf_2pct",
        "sortino_ratio",
        "max_drawdown",
        "calmar_ratio",
        "monthly_win_rate",
        "worst_month_return",
    ]
    for (etf_code, dte_label, strategy_name), g in long.groupby(["etf_code", "dte_label", "strategy_name"]):
        row: dict[str, object] = {
            "etf_code": etf_code,
            "dte_label": dte_label,
            "strategy_name": strategy_name,
            "candidate_label": _candidate_label(str(dte_label), str(strategy_name)),
        }
        for level in [name for _, name in BRIDGE_LEVELS]:
            for metric in metric_cols:
                row[f"{metric}_{level}"] = _level_metric(g, level, metric)

        s0 = row["sharpe_ratio_period_settlement"]
        s1 = row["sharpe_ratio_daily_step_settlement"]
        s2 = row["sharpe_ratio_daily_etf_only_marking"]
        s3 = row["sharpe_ratio_daily_mtm_nav"]
        row["settlement_to_daily_mtm_sharpe_gap"] = s0 - s3
        row["etf_daily_volatility_effect"] = s1 - s2
        row["option_mtm_sharpe_drag"] = s2 - s3
        row["settlement_to_daily_mtm_strict_sharpe_no_rf_gap"] = (
            row["strict_sharpe_no_rf_period_settlement"] - row["strict_sharpe_no_rf_daily_mtm_nav"]
        )
        row["settlement_to_daily_mtm_strict_sharpe_rf_2pct_gap"] = (
            row["strict_sharpe_rf_2pct_period_settlement"] - row["strict_sharpe_rf_2pct_daily_mtm_nav"]
        )

        row["return_bridge_contribution"] = (
            row["annualized_return_daily_mtm_nav"] - row["annualized_return_period_settlement"]
        )
        row["volatility_bridge_contribution"] = (
            row["annualized_volatility_daily_mtm_nav"] - row["annualized_volatility_period_settlement"]
        )
        row["return_daily_step_effect"] = (
            row["annualized_return_daily_step_settlement"] - row["annualized_return_period_settlement"]
        )
        row["return_etf_daily_marking_effect"] = (
            row["annualized_return_daily_etf_only_marking"] - row["annualized_return_daily_step_settlement"]
        )
        row["return_option_mtm_effect"] = (
            row["annualized_return_daily_mtm_nav"] - row["annualized_return_daily_etf_only_marking"]
        )
        row["volatility_daily_step_effect"] = (
            row["annualized_volatility_daily_step_settlement"] - row["annualized_volatility_period_settlement"]
        )
        row["volatility_etf_daily_marking_effect"] = (
            row["annualized_volatility_daily_etf_only_marking"]
            - row["annualized_volatility_daily_step_settlement"]
        )
        row["volatility_option_mtm_effect"] = (
            row["annualized_volatility_daily_mtm_nav"] - row["annualized_volatility_daily_etf_only_marking"]
        )
        rows.append(row)

    summary = pd.DataFrame(rows)
    if summary.empty:
        return summary
    summary["_dte_order"] = summary["dte_label"].map({"DTE30": 0, "DTE60": 1}).fillna(99)
    summary["_strategy_order"] = summary["strategy_name"].map(
        {"ATM_100": 0, "D50_100": 1, "D40_100": 2, "OTM2_100": 3}
    ).fillna(99)
    return summary.sort_values(["_dte_order", "_strategy_order", "strategy_name"]).drop(
        columns=["_dte_order", "_strategy_order"]
    ).reset_index(drop=True)


def _write_csv(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def _plot_metric_by_level(long: pd.DataFrame, metric: str, title: str, ylabel: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(12, 7))
    levels = [name for _, name in BRIDGE_LEVELS]
    labels = {
        "period_settlement": "L0\nperiod",
        "daily_step_settlement": "L1\nstep",
        "daily_etf_only_marking": "L2\nETF daily",
        "daily_mtm_nav": "L3\nMTM net",
    }
    for candidate, g in long.groupby("candidate_label"):
        g = g.set_index("bridge_level").reindex(levels)
        ax.plot([labels[level] for level in levels], g[metric], marker="o", linewidth=1.8, label=candidate)
    ax.axhline(0.0, color="#777777", linewidth=0.8)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", alpha=0.25)
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _plot_option_drag(summary: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = summary.sort_values(["dte_label", "strategy_name"])
    fig, ax = plt.subplots(figsize=(11, 6))
    colors = np.where(data["option_mtm_sharpe_drag"] >= 0, "#e45756", "#54a24b")
    ax.bar(data["candidate_label"], data["option_mtm_sharpe_drag"], color=colors)
    ax.axhline(0.0, color="#777777", linewidth=0.8)
    ax.set_title("Option MTM Sharpe-like Effect: L2 ETF daily marking - L3 current daily MTM")
    ax.set_ylabel("Positive = ratio drag; negative = ratio improvement")
    ax.tick_params(axis="x", rotation=35)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _plot_settlement_scatter(summary: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    x = summary["sharpe_ratio_period_settlement"]
    y = summary["sharpe_ratio_daily_mtm_nav"]
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.scatter(x, y, s=70, color="#f58518")
    for _, row in summary.iterrows():
        ax.annotate(
            row["candidate_label"],
            (row["sharpe_ratio_period_settlement"], row["sharpe_ratio_daily_mtm_nav"]),
            fontsize=8,
            xytext=(5, 4),
            textcoords="offset points",
        )
    finite = pd.concat([x, y]).replace([np.inf, -np.inf], np.nan).dropna()
    if not finite.empty:
        low = float(finite.min())
        high = float(finite.max())
        pad = max((high - low) * 0.1, 0.02)
        ax.plot([low - pad, high + pad], [low - pad, high + pad], color="#777777", linestyle="--", linewidth=1.0)
        ax.set_xlim(low - pad, high + pad)
        ax.set_ylim(low - pad, high + pad)
    ax.axhline(0.0, color="#cccccc", linewidth=0.8)
    ax.axvline(0.0, color="#cccccc", linewidth=0.8)
    ax.set_title("Settlement Ratio vs Current Daily MTM NAV Sharpe-like Ratio")
    ax.set_xlabel("L0 period settlement Sharpe-like ratio")
    ax.set_ylabel("L3 current daily MTM NAV Sharpe-like ratio")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def write_sharpe_bridge_figures(long: pd.DataFrame, summary: pd.DataFrame, output_dir: Path) -> dict[str, Path]:
    figures_dir = output_dir / "figures"
    return {
        "sharpe_bridge_by_strategy": _plot_metric_by_level(
            long,
            "sharpe_ratio",
            "510300 Sharpe-like Bridge by Strategy",
            "Sharpe-like ratio",
            figures_dir / "sharpe_bridge_by_strategy.png",
        ),
        "strict_sharpe_rf_2pct_bridge_by_strategy": _plot_metric_by_level(
            long,
            "strict_sharpe_rf_2pct",
            "510300 Strict Sharpe Bridge by Strategy (rf=2%)",
            "Strict Sharpe (rf=2%)",
            figures_dir / "strict_sharpe_rf_2pct_bridge_by_strategy.png",
        ),
        "return_bridge_by_strategy": _plot_metric_by_level(
            long,
            "annualized_return",
            "510300 Annualized Return Bridge by Strategy",
            "Annualized return",
            figures_dir / "return_bridge_by_strategy.png",
        ),
        "volatility_bridge_by_strategy": _plot_metric_by_level(
            long,
            "annualized_volatility",
            "510300 Annualized Volatility Bridge by Strategy",
            "Annualized volatility",
            figures_dir / "volatility_bridge_by_strategy.png",
        ),
        "option_mtm_sharpe_drag": _plot_option_drag(summary, figures_dir / "option_mtm_sharpe_drag.png"),
        "settlement_vs_daily_mtm_scatter": _plot_settlement_scatter(
            summary,
            figures_dir / "settlement_vs_daily_mtm_scatter.png",
        ),
    }


def _fmt_float(value: object, digits: int = 3) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value):.{digits}f}"


def _fmt_pct(value: object, digits: int = 2) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value) * 100:.{digits}f}%"


def _markdown_table(df: pd.DataFrame, *, percent_cols: Iterable[str] = (), float_cols: Iterable[str] = ()) -> str:
    if df.empty:
        return "_No rows._"
    out = df.copy()
    for col in percent_cols:
        if col in out.columns:
            out[col] = out[col].map(_fmt_pct)
    for col in float_cols:
        if col in out.columns:
            out[col] = out[col].map(_fmt_float)
    return out.to_markdown(index=False)


def write_sharpe_bridge_report(
    summary: pd.DataFrame,
    long: pd.DataFrame,
    figures: dict[str, Path],
    output_dir: Path,
) -> Path:
    report_path = output_dir / "ver2_2_510300_sharpe_bridge_report.md"
    compact_cols = [
        "candidate_label",
        "sharpe_ratio_period_settlement",
        "sharpe_ratio_daily_step_settlement",
        "sharpe_ratio_daily_etf_only_marking",
        "sharpe_ratio_daily_mtm_nav",
        "settlement_to_daily_mtm_sharpe_gap",
        "option_mtm_sharpe_drag",
    ]
    strict_cols = [
        "candidate_label",
        "strict_sharpe_rf_2pct_period_settlement",
        "strict_sharpe_rf_2pct_daily_step_settlement",
        "strict_sharpe_rf_2pct_daily_etf_only_marking",
        "strict_sharpe_rf_2pct_daily_mtm_nav",
        "settlement_to_daily_mtm_strict_sharpe_rf_2pct_gap",
    ]
    return_cols = [
        "candidate_label",
        "annualized_return_period_settlement",
        "annualized_return_daily_mtm_nav",
        "annualized_volatility_period_settlement",
        "annualized_volatility_daily_mtm_nav",
    ]
    mtm_effect = summary.sort_values("option_mtm_sharpe_drag", ascending=True)
    best_daily = summary.sort_values("sharpe_ratio_daily_mtm_nav", ascending=False).head(3)

    text = f"""# ver2.2 510300 Sharpe-like Bridge 中文报告

## 实验目标

本模块用于解释 510300 备兑分支中，为什么周期结算口径的收益/波动比与当前日频 MTM NAV 的 Sharpe-like ratio 会出现差异。它不是换算表，也不是要把两个口径强行转换成同一个数，而是把口径差异拆成几个可观察层级：从期权周期收益，到日频阶梯净值，到 ETF 日频盯市，再到当前已经包含交易摩擦的日频 MTM 净值。

## 实验范围

- ETF: 510300
- 来源实验：ver2.1 Non-ITM Covered Call DTE x Regime Diagnostic
- 候选策略：DTE30 ATM_100, DTE30 D50_100, DTE30 D40_100, DTE30 OTM2_100, DTE60 ATM_100, DTE60 D50_100；如果 DTE60 D40_100 / OTM2_100 已有结果，也一并纳入。
- Level 3 直接使用当前 ver2.1 的 `daily_mtm_nav`。该 NAV 已经包含 transaction cost、bid/ask spread 假设和 slippage，因此本报告不再创建单独 Level 4，避免暗示或重复加入第二层交易摩擦。
- 表格列名暂时保留英文代码字段，例如 `sharpe_ratio_period_settlement`，便于和 CSV 一一对应；但这些字段在本文中统一解释为 Sharpe-like ratio，而不是严格经典 Sharpe。

## 桥接层级

| Level | Name | 含义 |
|---:|---|---|
| 0 | period_settlement | 使用期权周期收益。权利金和到期 payoff 都在期权周期层面结算。 |
| 1 | daily_step_settlement | 将 Level 0 的周期净值映射为日频阶梯净值。周期中不做 ETF 或期权盯市，只在结算日跳变。 |
| 2 | daily_etf_only_marking | 每日反映 ETF 价格变化，并在开仓日确认权利金现金；short call 负债不做日频盯市，到期日确认 payoff。 |
| 3 | daily_mtm_nav | 当前 ver2.1 日频 MTM NAV。每日标记 short call 负债，并且已包含配置中的交易摩擦。 |

## Sharpe-like 桥接表

{_markdown_table(summary[compact_cols], float_cols=[c for c in compact_cols if c != "candidate_label"])}

## 严格 Sharpe 桥接表（rf=2%）

本表使用严格日频/周期 Sharpe 口径：`mean(return - rf_per_period) / std(return) * sqrt(annual_factor)`。年化无风险利率暂设为 2%，并按对应频率折算为单期无风险收益。该表和上方 Sharpe-like 表应并列阅读。

{_markdown_table(summary[strict_cols], float_cols=[c for c in strict_cols if c != "candidate_label"])}

## 收益与波动桥接表

{_markdown_table(summary[return_cols], percent_cols=[c for c in return_cols if c != "candidate_label"])}

## 期权日频盯市 Sharpe-like 影响

`option_mtm_sharpe_drag = SharpeLike_L2 - SharpeLike_L3`。该指标是有方向的：正数表示 short call 日频负债盯市降低了 Sharpe-like ratio；负数表示当前 MTM 路径的 Sharpe-like ratio 高于只做 ETF 日频盯市的路径。

{_markdown_table(mtm_effect[["candidate_label", "option_mtm_sharpe_drag", "sharpe_ratio_daily_etf_only_marking", "sharpe_ratio_daily_mtm_nav"]], float_cols=["option_mtm_sharpe_drag", "sharpe_ratio_daily_etf_only_marking", "sharpe_ratio_daily_mtm_nav"])}

## 当前日频 MTM Sharpe-like ratio 较高的候选

{_markdown_table(best_daily[["candidate_label", "sharpe_ratio_daily_mtm_nav", "annualized_return_daily_mtm_nav", "annualized_volatility_daily_mtm_nav", "max_drawdown_daily_mtm_nav"]], percent_cols=["annualized_return_daily_mtm_nav", "annualized_volatility_daily_mtm_nav", "max_drawdown_daily_mtm_nav"], float_cols=["sharpe_ratio_daily_mtm_nav"])}

## 510300 结果解读

- 周期结算层级和日频 MTM NAV 层级是两种不同的会计视角。前者关注权利金减去到期 payoff 后，是否改善了每个期权周期的收益/波动比；后者关注产品净值路径在每日标记 short call 负债后是否仍然平滑。
- 日频 MTM Sharpe-like ratio 不是对周期结算结果的推翻，而是从产品净值路径角度给出的更严格评价，尤其适合观察反弹行情或政策跳涨窗口中的路径压力。
- 对 510300 来说，当前 settlement-to-daily 的 ratio 差异主要来自日频 ETF 路径波动，以及当前 daily MTM NAV 中已经包含的交易摩擦。
- ATM 通常有更强的下跌缓冲和更厚的权利金，但在 ETF 反弹时也更容易承受 short call 盯市压力。
- D50 接近 ATM，可视为近 ATM 替代结构；其日频净值体验取决于实际选到的 delta 是否真的低于 ATM 足够多。
- D40 可能牺牲部分下跌保护和权利金厚度，但在当前 510300 样本里，它提供了更好的日频净值体验。

## 输出文件

- 长表：`{(output_dir / "ver2_2_510300_sharpe_bridge_long.csv").as_posix()}`
- 汇总表：`{(output_dir / "ver2_2_510300_sharpe_bridge_summary.csv").as_posix()}`
- 图表：
{chr(10).join(f"- `{path.as_posix()}`" for path in figures.values())}

## 口径说明

- Level 3 是当前 ver2.1 的日频 MTM NAV，已经包含配置中的交易成本模型，因此本报告没有单独 Level 4。
- Level 2 在开仓日确认权利金现金、到期日确认 payoff，但不每日标记 short call 负债。`option_mtm_sharpe_drag` 是有符号指标：正数表示 Level 3 的 short-call MTM 降低 Sharpe-like ratio；负数表示 Level 3 的 ratio 高于 Level 2。
- 本报告中的 `sharpe_ratio_*` 字段统一按收益/波动比理解。日频层级使用 `daily NAV CAGR / annualized daily return volatility`，即 `CAGR / 年化日频波动率`；这不是严格经典的 `mean(daily excess return) / std(daily return) * sqrt(252)`。
- CSV 同时输出 `strict_sharpe_no_rf_*` 和 `strict_sharpe_rf_2pct_*`。其中 `strict_sharpe_rf_2pct_*` 使用年化 2% 无风险利率，并折算到对应 return frequency。
- 为避免误解，正文统一称为 Sharpe-like ratio。字段名暂不修改，是为了保持 CSV 与已有 ver2.1 输出兼容。
"""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(text, encoding="utf-8")
    return report_path


def load_sharpe_bridge_inputs(paths: SharpeBridgePaths) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not paths.periods_path.exists():
        raise FileNotFoundError(f"Missing ver2.1 periods file: {paths.periods_path}")
    if not paths.daily_mtm_path.exists():
        raise FileNotFoundError(f"Missing ver2.1 daily MTM file: {paths.daily_mtm_path}")
    periods = pd.read_csv(paths.periods_path, usecols=lambda c: c in PERIOD_USECOLS)
    daily_mtm = pd.read_csv(paths.daily_mtm_path, usecols=lambda c: c in DAILY_USECOLS)
    return periods, daily_mtm


def run_510300_sharpe_bridge(paths: SharpeBridgePaths | None = None, *, etf_code: str = "510300") -> dict[str, Path]:
    paths = paths or SharpeBridgePaths()
    periods, daily_mtm = load_sharpe_bridge_inputs(paths)
    long, summary = build_sharpe_bridge_tables(periods, daily_mtm, etf_code=etf_code)
    if long.empty or summary.empty:
        raise ValueError(f"No Sharpe bridge rows were built for ETF {etf_code}.")

    output_dir = paths.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    figures = write_sharpe_bridge_figures(long, summary, output_dir)
    report = write_sharpe_bridge_report(summary, long, figures, output_dir)
    return {
        "summary": _write_csv(summary, output_dir / "ver2_2_510300_sharpe_bridge_summary.csv"),
        "long": _write_csv(long, output_dir / "ver2_2_510300_sharpe_bridge_long.csv"),
        "report": report,
        **figures,
    }
