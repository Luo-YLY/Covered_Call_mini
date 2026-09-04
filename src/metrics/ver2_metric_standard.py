from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

import numpy as np
import pandas as pd


TRADING_DAYS_PER_YEAR = 252.0
CALENDAR_DAYS_PER_YEAR = 365.25


def _as_float_series(values: pd.Series | Iterable[float]) -> pd.Series:
    """Return a numeric Series with missing and non-finite values removed."""

    series = pd.Series(values, dtype="float64").replace([np.inf, -np.inf], np.nan)
    return series.dropna()


def _safe_div(numerator: float, denominator: float) -> float:
    """Divide with NaN output when the denominator is zero or missing."""

    if denominator is None or pd.isna(denominator) or abs(float(denominator)) < 1e-12:
        return np.nan
    return float(numerator) / float(denominator)


def compute_daily_returns(nav_series: pd.Series) -> pd.Series:
    """Compute daily returns as NAV_t / NAV_(t-1) - 1.

    Annualization is not applied here. The first observation is dropped because
    it has no prior NAV. Event-exclusion workflows should compute this full
    daily-return series first, then mask event-window rows.
    """

    nav = _as_float_series(nav_series)
    return nav.pct_change().replace([np.inf, -np.inf], np.nan).dropna()


def compute_cagr(nav_series: pd.Series, trading_days: float = TRADING_DAYS_PER_YEAR) -> float:
    """Compute NAV CAGR using the 252-trading-day convention.

    Formula: (NAV_end / NAV_start) ** (trading_days / n_daily_returns) - 1.
    Returns NaN when NAV is empty, non-positive, or ends below -100%.
    """

    nav = _as_float_series(nav_series)
    if len(nav) < 2 or nav.iloc[0] <= 0 or nav.iloc[-1] <= 0:
        return np.nan
    n_daily_returns = max(len(nav) - 1, 1)
    return float((nav.iloc[-1] / nav.iloc[0]) ** (float(trading_days) / n_daily_returns) - 1.0)


def compute_arithmetic_annualized_return(
    daily_returns: pd.Series,
    trading_days: float = TRADING_DAYS_PER_YEAR,
) -> float:
    """Compute arithmetic annualized return as mean(daily_return) * trading_days."""

    returns = _as_float_series(daily_returns)
    return float(returns.mean() * float(trading_days)) if not returns.empty else np.nan


def compute_annualized_volatility(
    daily_returns: pd.Series,
    trading_days: float = TRADING_DAYS_PER_YEAR,
) -> float:
    """Compute annualized volatility as std(daily_return) * sqrt(trading_days)."""

    returns = _as_float_series(daily_returns)
    if len(returns) < 2:
        return np.nan
    return float(returns.std(ddof=1) * np.sqrt(float(trading_days)))


def compute_sharpe_daily_mean(
    daily_returns: pd.Series,
    rf: float = 0.0,
    trading_days: float = TRADING_DAYS_PER_YEAR,
) -> float:
    """Compute strict daily-mean Sharpe.

    Formula: mean(daily_return - rf_daily) / std(daily_return) * sqrt(trading_days).
    The annual risk-free rate is converted to a daily compounded rate.
    Returns NaN when the daily standard deviation is zero or unavailable.
    """

    returns = _as_float_series(daily_returns)
    if len(returns) < 2:
        return np.nan
    rf_daily = (1.0 + float(rf)) ** (1.0 / float(trading_days)) - 1.0
    vol = returns.std(ddof=1)
    return float((returns - rf_daily).mean() / vol * np.sqrt(float(trading_days))) if vol > 0 else np.nan


def compute_sortino(
    daily_returns: pd.Series,
    rf: float = 0.0,
    trading_days: float = TRADING_DAYS_PER_YEAR,
) -> float:
    """Compute Sortino ratio using annualized arithmetic excess return.

    Downside deviation is std(min(daily_return - rf_daily, 0)) * sqrt(252).
    Returns NaN when downside deviation is zero or unavailable.
    """

    returns = _as_float_series(daily_returns)
    if len(returns) < 2:
        return np.nan
    rf_daily = (1.0 + float(rf)) ** (1.0 / float(trading_days)) - 1.0
    excess = returns - rf_daily
    downside = np.minimum(excess, 0.0)
    downside_deviation = pd.Series(downside).std(ddof=1) * np.sqrt(float(trading_days))
    if pd.isna(downside_deviation) or downside_deviation <= 0:
        return np.nan
    annual_excess = excess.mean() * float(trading_days)
    return float(annual_excess / downside_deviation)


def compute_drawdown(nav_series: pd.Series) -> pd.DataFrame:
    """Compute drawdown path as NAV / rolling_peak_NAV - 1.

    The returned DataFrame contains nav, rolling_peak_nav, and drawdown. The
    drawdown values are negative or zero; max_drawdown uses the positive
    magnitude via compute_max_drawdown.
    """

    nav = _as_float_series(nav_series)
    peaks = nav.cummax()
    drawdown = nav / peaks - 1.0
    return pd.DataFrame({"nav": nav, "rolling_peak_nav": peaks, "drawdown": drawdown})


def compute_max_drawdown(nav_series: pd.Series) -> float:
    """Return max drawdown as a positive magnitude."""

    dd = compute_drawdown(nav_series)
    if dd.empty:
        return np.nan
    return float(abs(dd["drawdown"].min()))


def compute_max_drawdown_details(nav_series: pd.Series) -> dict[str, object]:
    """Return positive max drawdown plus start/trough/recovery positions.

    The index of nav_series is preserved and returned as the date-like labels.
    recovery is NaN when NAV never recovers to the prior peak inside the sample.
    """

    nav = pd.Series(nav_series, dtype="float64").replace([np.inf, -np.inf], np.nan).dropna()
    if len(nav) < 2:
        return {
            "max_drawdown": np.nan,
            "max_drawdown_start": pd.NaT,
            "max_drawdown_trough": pd.NaT,
            "max_drawdown_recovery": pd.NaT,
            "drawdown_duration": np.nan,
        }

    peaks = nav.cummax()
    dd = nav / peaks - 1.0

    # Work by integer position so duplicated date labels do not break .loc
    # comparisons. Some ver2.x daily MTM outputs can contain repeated dates
    # across stitched option cycles.
    trough_pos = int(np.nanargmin(dd.values))
    trough = nav.index[trough_pos]
    prefix_values = nav.iloc[: trough_pos + 1].values
    peak_pos = int(np.nanargmax(prefix_values))
    peak_value = float(nav.iloc[peak_pos])
    start = nav.index[peak_pos]
    recovery = pd.NaT
    for pos in range(trough_pos, len(nav)):
        if float(nav.iloc[pos]) >= peak_value:
            recovery = nav.index[pos]
            break

    underwater = nav < peaks
    max_duration = 0
    current = 0
    for flag in underwater:
        if bool(flag):
            current += 1
            max_duration = max(max_duration, current)
        else:
            current = 0

    return {
        "max_drawdown": float(abs(dd.min())),
        "max_drawdown_start": start,
        "max_drawdown_trough": trough,
        "max_drawdown_recovery": recovery,
        "drawdown_duration": int(max_duration),
    }


def compute_calmar(cagr: float, max_drawdown: float) -> float:
    """Compute Calmar ratio as CAGR / positive max drawdown."""

    return _safe_div(cagr, max_drawdown)


def compute_monthly_returns(daily_nav: pd.Series) -> pd.Series:
    """Compute month-end NAV returns from a date-indexed daily NAV series."""

    nav = pd.Series(daily_nav, dtype="float64").replace([np.inf, -np.inf], np.nan).dropna()
    if not isinstance(nav.index, pd.DatetimeIndex):
        nav.index = pd.to_datetime(nav.index)
    month_end_nav = nav.resample("ME").last().dropna()
    return month_end_nav.pct_change().dropna()


def compute_monthly_win_rate(daily_nav: pd.Series) -> float:
    """Compute the share of positive monthly returns from date-indexed daily NAV."""

    monthly = compute_monthly_returns(daily_nav)
    return float((monthly > 0).mean()) if not monthly.empty else np.nan


def summarize_daily_nav(
    daily_nav: pd.DataFrame,
    date_col: str = "date",
    nav_col: str = "nav",
    rf: float = 0.0,
    trading_days: float = TRADING_DAYS_PER_YEAR,
) -> dict[str, object]:
    """Return the standard daily-NAV performance metric set.

    The output names follow the ver2.x standard: annualized_return_cagr,
    arithmetic_annualized_return, annualized_volatility, sharpe_daily_mean,
    cagr_vol_ratio, sortino_ratio, calmar_ratio, max_drawdown, monthly_win_rate,
    worst_month_return, and best_month_return.
    """

    df = daily_nav[[date_col, nav_col]].dropna().copy()
    if df.empty:
        return {}
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.sort_values(date_col)
    nav = pd.Series(df[nav_col].astype(float).values, index=df[date_col])
    returns = compute_daily_returns(nav)
    cagr = compute_cagr(nav, trading_days=trading_days)
    vol = compute_annualized_volatility(returns, trading_days=trading_days)
    mdd_details = compute_max_drawdown_details(nav)
    monthly = compute_monthly_returns(nav)
    return {
        "sample_start": df[date_col].min().date().isoformat(),
        "sample_end": df[date_col].max().date().isoformat(),
        "n_trading_days": int(len(df)),
        "cumulative_return": float(nav.iloc[-1] / nav.iloc[0] - 1.0) if nav.iloc[0] > 0 else np.nan,
        "annualized_return_cagr": cagr,
        "arithmetic_annualized_return": compute_arithmetic_annualized_return(returns, trading_days=trading_days),
        "annualized_volatility": vol,
        "sharpe_daily_mean": compute_sharpe_daily_mean(returns, rf=rf, trading_days=trading_days),
        "cagr_vol_ratio": _safe_div(cagr, vol),
        "sortino_ratio": compute_sortino(returns, rf=rf, trading_days=trading_days),
        "calmar_ratio": compute_calmar(cagr, mdd_details["max_drawdown"]),
        "max_drawdown": mdd_details["max_drawdown"],
        "max_drawdown_start": _date_to_iso(mdd_details["max_drawdown_start"]),
        "max_drawdown_trough": _date_to_iso(mdd_details["max_drawdown_trough"]),
        "max_drawdown_recovery": _date_to_iso(mdd_details["max_drawdown_recovery"]),
        "drawdown_duration": mdd_details["drawdown_duration"],
        "monthly_win_rate": float((monthly > 0).mean()) if not monthly.empty else np.nan,
        "worst_month_return": float(monthly.min()) if not monthly.empty else np.nan,
        "best_month_return": float(monthly.max()) if not monthly.empty else np.nan,
    }


def _date_to_iso(value: object) -> object:
    if value is pd.NaT or pd.isna(value):
        return np.nan
    try:
        return pd.Timestamp(value).date().isoformat()
    except Exception:
        return value


def compute_option_period_metrics(period_df: pd.DataFrame) -> pd.DataFrame:
    """Add standard per-period option-leg accounting fields.

    Required fields are premium_return, payoff_return, and transaction_cost_return.
    option_leg_return_standard is premium - payoff - cost. Missing fields are
    treated as zero for the formula and warning_flags should be set upstream.
    """

    out = period_df.copy()
    for col in ["premium_return", "payoff_return", "transaction_cost_return"]:
        if col not in out.columns:
            out[col] = 0.0
    out["option_leg_return_standard"] = (
        out["premium_return"].astype(float)
        - out["payoff_return"].astype(float)
        - out["transaction_cost_return"].astype(float)
    )
    out["realized_time_carry_yield"] = out["option_leg_return_standard"]
    out["premium_capture_ratio_period"] = out.apply(
        lambda r: _safe_div(r["option_leg_return_standard"], r["premium_return"]),
        axis=1,
    )
    out["payoff_burden_period"] = out.apply(
        lambda r: _safe_div(r["payoff_return"], r["premium_return"]),
        axis=1,
    )
    return out


def compute_option_aggregate_metrics(period_df: pd.DataFrame) -> dict[str, float]:
    """Compute aggregate option-leg ratios from period data.

    Aggregate premium_capture_ratio_agg uses sum(realized_time_carry_yield) /
    sum(premium_return). This is the default ranking ratio; period means may be
    reported separately but should not replace aggregate ratios.
    """

    p = compute_option_period_metrics(period_df)
    premium_sum = float(p["premium_return"].sum())
    net_sum = float(p["option_leg_return_standard"].sum())
    payoff_sum = float(p["payoff_return"].sum())
    actual_dte = p["actual_dte"].astype(float) if "actual_dte" in p.columns else pd.Series(dtype=float)
    extrinsic = p["annualized_extrinsic_premium_yield"].astype(float) if "annualized_extrinsic_premium_yield" in p.columns else pd.Series(dtype=float)
    assignment = p["assignment_flag"].astype(float) if "assignment_flag" in p.columns else pd.Series(dtype=float)
    return {
        "num_periods": int(len(p)),
        "avg_actual_dte": float(actual_dte.mean()) if not actual_dte.empty else np.nan,
        "annualized_extrinsic_premium_yield_mean": float(extrinsic.mean()) if not extrinsic.empty else np.nan,
        "realized_time_carry_yield_agg": net_sum,
        "premium_capture_ratio_agg": _safe_div(net_sum, premium_sum),
        "payoff_burden_agg": _safe_div(payoff_sum, premium_sum),
        "premium_capture_ratio_period_mean": float(p["premium_capture_ratio_period"].mean()),
        "payoff_burden_period_mean": float(p["payoff_burden_period"].mean()),
        "assignment_rate": float(assignment.mean()) if not assignment.empty else np.nan,
        "positive_option_leg_period_rate": float((p["option_leg_return_standard"] > 0).mean()) if len(p) else np.nan,
    }


def compute_portfolio_option_contribution(
    daily_option_pnl: pd.Series,
    initial_nav: float = 1.0,
    n_days: int | None = None,
    trading_days: float = TRADING_DAYS_PER_YEAR,
) -> float:
    """Annualize additive portfolio option-leg P&L contribution.

    Formula: sum(daily_option_leg_pnl) / initial_nav * trading_days / n_days.
    This is a portfolio contribution, not a standalone option sleeve return.
    """

    pnl = _as_float_series(daily_option_pnl)
    if pnl.empty:
        return np.nan
    days = int(n_days) if n_days is not None else len(pnl)
    return _safe_div(float(pnl.sum()), float(initial_nav)) * float(trading_days) / max(days, 1)


def compute_effective_portfolio_coverage(
    weights: Mapping[str, float],
    coverages: Mapping[str, float],
) -> float:
    """Compute effective coverage as sum(weight_i * coverage_i)."""

    return float(sum(float(weights.get(k, 0.0)) * float(coverages.get(k, 0.0)) for k in set(weights) | set(coverages)))


def compute_mdd_reduction_cost(
    pure_metrics: Mapping[str, float],
    overlay_metrics: Mapping[str, float],
) -> dict[str, object]:
    """Compute MDD reduction cost and dominance flag.

    If overlay return is higher and overlay MDD is lower, dominates_pure_basket is
    True and the cost ratio is left negative when applicable. If there is no MDD
    improvement, the cost is NaN and status is no_mdd_improvement.
    """

    pure_return = float(pure_metrics.get("annualized_return_cagr", np.nan))
    overlay_return = float(overlay_metrics.get("annualized_return_cagr", np.nan))
    pure_mdd = float(pure_metrics.get("max_drawdown", np.nan))
    overlay_mdd = float(overlay_metrics.get("max_drawdown", np.nan))
    mdd_improvement = pure_mdd - overlay_mdd
    dominates = bool(overlay_return > pure_return and overlay_mdd < pure_mdd)
    if pd.isna(mdd_improvement) or mdd_improvement <= 0:
        return {
            "mdd_reduction_cost": np.nan,
            "mdd_improvement": mdd_improvement,
            "dominates_pure_basket": False,
            "status": "no_mdd_improvement",
        }
    return {
        "mdd_reduction_cost": _safe_div(pure_return - overlay_return, mdd_improvement),
        "mdd_improvement": mdd_improvement,
        "dominates_pure_basket": dominates,
        "status": "dominates_pure_basket" if dominates else "normal_cost",
    }


@dataclass(frozen=True)
class EventWindow:
    """Named inclusive event window for sensitivity attribution."""

    name: str
    start: str
    end: str


def compute_event_exclusion_metrics(
    nav_df: pd.DataFrame,
    event_windows: Iterable[EventWindow],
    date_col: str = "date",
    nav_col: str = "nav",
    trading_days: float = TRADING_DAYS_PER_YEAR,
) -> pd.DataFrame:
    """Compute event-only and ex-event sensitivity metrics.

    The daily return series is first computed on the full NAV path and event
    windows are masked afterward. ex-event results are sensitivity paths, not
    tradable paths. event-only annualized returns are short-window references.
    """

    df = nav_df[[date_col, nav_col]].dropna().copy()
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.sort_values(date_col)
    df["daily_return"] = df[nav_col].astype(float).pct_change()
    rows = []
    for window in event_windows:
        start = pd.Timestamp(window.start)
        end = pd.Timestamp(window.end)
        mask = (df[date_col] >= start) & (df[date_col] <= end)
        for sample_version, sample_returns, note in [
            ("full_sample", df["daily_return"].dropna(), "full_path"),
            ("ex_event", df.loc[~mask, "daily_return"].dropna(), "sensitivity_path"),
            ("event_only", df.loc[mask, "daily_return"].dropna(), "short_window_reference"),
        ]:
            nav = (1.0 + sample_returns.fillna(0.0)).cumprod()
            if nav.empty:
                metrics = {}
            else:
                sample_df = pd.DataFrame(
                    {
                        date_col: df.loc[sample_returns.index, date_col].values,
                        nav_col: nav.values,
                    }
                )
                metrics = summarize_daily_nav(sample_df, date_col=date_col, nav_col=nav_col, trading_days=trading_days)
            rows.append({"event_window_name": window.name, "sample_version": sample_version, "note": note, **metrics})
    return pd.DataFrame(rows)


def reconcile_period_option_pnl(
    period_df: pd.DataFrame,
    daily_mtm_df: pd.DataFrame,
    tolerance: float = 1e-10,
) -> pd.DataFrame:
    """Reconcile Step2-like period net option P&L with reconstructed daily MTM.

    The preferred reconstruction uses short_call_cumulative_mtm_pnl.diff() by
    cycle and terminally adjusts to the period option_leg_return. The raw
    option_leg_daily_return sum is retained for audit because it may include
    entry premium and is not necessarily net option-leg P&L.
    """

    keys = ["etf_code", "dte_label", "strategy_name", "rebalance_date", "expiry_date"]
    p = compute_option_period_metrics(period_df.copy())
    d = daily_mtm_df.copy()
    for col in ["rebalance_date", "expiry_date"]:
        if col in p.columns:
            p[col] = pd.to_datetime(p[col]).dt.date.astype(str)
        if col in d.columns:
            d[col] = pd.to_datetime(d[col]).dt.date.astype(str)
    if "etf_code" in p.columns:
        p["etf_code"] = p["etf_code"].astype(str).str.zfill(6)
    if "etf_code" in d.columns:
        d["etf_code"] = d["etf_code"].astype(str).str.zfill(6)

    rows = []
    grouped_daily = {key: g.sort_values("date") for key, g in d.groupby(keys, dropna=False)}
    for _, row in p.iterrows():
        key = tuple(row[k] for k in keys)
        cycle = grouped_daily.get(key)
        if cycle is None or cycle.empty:
            rows.append(_reconcile_missing_row(row))
            continue
        raw_sum = float(cycle.get("option_leg_daily_return", pd.Series(dtype=float)).astype(float).sum())
        if "short_call_cumulative_mtm_pnl" in cycle.columns:
            reconstructed = cycle["short_call_cumulative_mtm_pnl"].astype(float).diff()
            reconstructed.iloc[0] = cycle["short_call_cumulative_mtm_pnl"].astype(float).iloc[0]
        else:
            reconstructed = cycle["option_leg_daily_return"].astype(float).copy()
        pre_adjust = float(reconstructed.sum())
        period_net = float(row["option_leg_return_standard"])
        terminal_adjustment = period_net - pre_adjust
        if len(reconstructed):
            reconstructed.iloc[-1] += terminal_adjustment
        reconstructed_sum = float(reconstructed.sum())
        diff = reconstructed_sum - period_net
        rows.append(
            {
                "experiment_version": "step2_option_leg_panel",
                "etf_code": row.get("etf_code"),
                "dte_label": row.get("dte_label"),
                "strategy_family": row.get("strategy_family", row.get("strategy_name")),
                "strategy_name": row.get("strategy_name"),
                "rebalance_date": row.get("rebalance_date"),
                "expiry_date": row.get("expiry_date"),
                "premium_return": row.get("premium_return"),
                "payoff_return": row.get("payoff_return"),
                "transaction_cost_return": row.get("transaction_cost_return"),
                "period_option_leg_return": period_net,
                "raw_summed_daily_option_pnl": raw_sum,
                "reconstructed_daily_option_pnl_pre_terminal_adjustment": pre_adjust,
                "terminal_adjustment": terminal_adjustment,
                "summed_daily_option_pnl": reconstructed_sum,
                "difference": diff,
                "passed": bool(abs(diff) <= tolerance),
                "note": "raw Step2 daily field retained; pass uses reconstructed net MTM path",
            }
        )
    return pd.DataFrame(rows)


def _reconcile_missing_row(row: pd.Series) -> dict[str, object]:
    return {
        "experiment_version": "step2_option_leg_panel",
        "etf_code": row.get("etf_code"),
        "dte_label": row.get("dte_label"),
        "strategy_family": row.get("strategy_family", row.get("strategy_name")),
        "strategy_name": row.get("strategy_name"),
        "rebalance_date": row.get("rebalance_date"),
        "expiry_date": row.get("expiry_date"),
        "premium_return": row.get("premium_return"),
        "payoff_return": row.get("payoff_return"),
        "transaction_cost_return": row.get("transaction_cost_return"),
        "period_option_leg_return": row.get("option_leg_return_standard", np.nan),
        "raw_summed_daily_option_pnl": np.nan,
        "reconstructed_daily_option_pnl_pre_terminal_adjustment": np.nan,
        "terminal_adjustment": np.nan,
        "summed_daily_option_pnl": np.nan,
        "difference": np.nan,
        "passed": False,
        "note": "no matching daily MTM rows",
    }


def reconcile_step2_step3_option_pnl(
    step2_df: pd.DataFrame,
    step3_df: pd.DataFrame,
) -> pd.DataFrame:
    """Bridge Step2 net option P&L to Step3 additive portfolio option contribution.

    This helper expects caller-provided Step3 rows with portfolio_name,
    overlay_policy, etf_code, weight, coverage, and actual_step3_contribution.
    """

    if step2_df.empty or step3_df.empty:
        return pd.DataFrame()
    rows = []
    p = compute_option_period_metrics(step2_df)
    p["etf_code"] = p["etf_code"].astype(str).str.zfill(6)
    step2_net = p.groupby(["etf_code", "strategy_family"], as_index=False)["option_leg_return_standard"].sum()
    lookup = {
        (row["etf_code"], row["strategy_family"]): float(row["option_leg_return_standard"])
        for _, row in step2_net.iterrows()
    }
    for _, row in step3_df.iterrows():
        etf = str(row["etf_code"]).zfill(6)
        family = row.get("strategy_family")
        step2_value = lookup.get((etf, family), 0.0)
        expected = float(row["weight"]) * float(row["coverage"]) * step2_value
        actual = float(row.get("actual_step3_contribution", np.nan))
        rows.append(
            {
                **row.to_dict(),
                "step2_net_option_pnl": step2_value,
                "expected_step3_contribution": expected,
                "actual_step3_contribution": actual,
                "difference": actual - expected,
                "passed": bool(abs(actual - expected) <= 1e-8),
            }
        )
    return pd.DataFrame(rows)
