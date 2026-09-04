from __future__ import annotations

import numpy as np
import pandas as pd

from ver2_downside_protection.metrics import STRATEGY_ORDER, annual_factor


PREMIUM_DECOMPOSITION_COLUMNS = [
    "etf_code",
    "strategy_name",
    "period_index",
    "rebalance_date",
    "period_end_date",
    "expiry_date",
    "actual_dte",
    "option_code",
    "strike",
    "underlying_price_at_entry",
    "underlying_price_at_expiry",
    "coverage_ratio",
    "total_premium",
    "intrinsic_value_at_entry",
    "extrinsic_value_at_entry",
    "total_premium_yield",
    "intrinsic_premium_yield",
    "extrinsic_premium_yield",
    "option_payoff_return_at_expiry",
    "assignment_flag",
    "premium_capture_period",
    "etf_period_return",
    "strategy_period_return",
    "excess_return_vs_etf",
]


def _sort_by_strategy_order(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "strategy_name" not in df.columns:
        return df.copy()
    out = df.copy()
    out["_strategy_order"] = out["strategy_name"].map(STRATEGY_ORDER).fillna(999)
    sort_cols = [col for col in ["etf_code", "_strategy_order", "strategy_name", "rebalance_date"] if col in out.columns]
    return out.sort_values(sort_cols).drop(columns=["_strategy_order"]).reset_index(drop=True)


def add_premium_decomposition(periods: pd.DataFrame) -> pd.DataFrame:
    """Add entry premium decomposition fields to each ver2 period.

    The decomposition is per one ETF unit. Yields are adjusted by the actual
    coverage ratio and divided by the ETF entry price.
    """

    out = periods.copy()
    selected = out.get("option_selected_flag", 0).astype(bool)
    spot = out["underlying_price_at_entry"].astype(float)
    strike = out["strike"].astype(float)
    coverage = out["coverage_ratio"].fillna(0.0).astype(float)
    premium = out["option_price_at_entry"].fillna(0.0).astype(float)

    intrinsic = np.where(selected & strike.notna(), np.maximum(spot - strike, 0.0), 0.0)
    extrinsic = np.where(selected, premium - intrinsic, 0.0)
    valid_spot = spot.replace(0.0, np.nan)

    out["total_premium"] = np.where(selected, premium, 0.0)
    out["intrinsic_value_at_entry"] = intrinsic
    out["extrinsic_value_at_entry"] = extrinsic
    out["total_premium_yield"] = coverage * out["total_premium"] / valid_spot
    out["intrinsic_premium_yield"] = coverage * out["intrinsic_value_at_entry"] / valid_spot
    out["extrinsic_premium_yield"] = coverage * out["extrinsic_value_at_entry"] / valid_spot
    payoff = out["option_payoff_return_at_expiry"].fillna(0.0).astype(float)
    out["premium_capture_period"] = np.where(
        out["total_premium_yield"].abs() > 0,
        (out["total_premium_yield"] - payoff) / out["total_premium_yield"],
        np.nan,
    )
    return out


def _drawdown_duration_stats(nav_g: pd.DataFrame) -> dict[str, float]:
    """Return drawdown duration diagnostics in calendar days."""

    if nav_g.empty:
        return {"drawdown_duration": np.nan, "recovery_lag_after_drawdown": np.nan}

    g = nav_g.sort_values("date").copy()
    g["date"] = pd.to_datetime(g["date"])
    nav = g["nav"].astype(float).reset_index(drop=True)
    dates = pd.Series(g["date"].to_numpy())
    peak = nav.cummax()
    drawdown = nav / peak - 1.0
    underwater = drawdown < -1e-12

    max_duration = 0.0
    start_date = None
    for idx, is_underwater in enumerate(underwater):
        current_date = pd.Timestamp(dates.iloc[idx])
        if is_underwater and start_date is None:
            start_date = current_date
        elif not is_underwater and start_date is not None:
            max_duration = max(max_duration, float((current_date - start_date).days))
            start_date = None
    if start_date is not None:
        max_duration = max(max_duration, float((pd.Timestamp(dates.iloc[-1]) - start_date).days))

    if drawdown.empty:
        recovery_lag = np.nan
    else:
        trough_idx = int(drawdown.idxmin())
        prior_peak_nav = float(peak.iloc[trough_idx])
        recovery = nav.iloc[trough_idx:][nav.iloc[trough_idx:] >= prior_peak_nav - 1e-12]
        if recovery.empty:
            recovery_lag = np.nan
        else:
            recovery_idx = int(recovery.index[0])
            recovery_lag = float((pd.Timestamp(dates.iloc[recovery_idx]) - pd.Timestamp(dates.iloc[trough_idx])).days)

    return {
        "drawdown_duration": max_duration,
        "recovery_lag_after_drawdown": recovery_lag,
    }


def build_premium_decomposition_by_period(periods: pd.DataFrame) -> pd.DataFrame:
    """Return the covered-call period-level premium decomposition table."""

    decomposed = add_premium_decomposition(periods)
    covered = decomposed[decomposed["strategy_name"] != "BuyHold"].copy()
    cols = [col for col in PREMIUM_DECOMPOSITION_COLUMNS if col in covered.columns]
    return _sort_by_strategy_order(covered[cols])


def build_premium_income_summary(
    periods: pd.DataFrame,
    nav: pd.DataFrame,
    base_summary: pd.DataFrame,
) -> pd.DataFrame:
    """Compute premium-income and defensive diagnostics for covered-call strategies."""

    decomposed = add_premium_decomposition(periods)
    summary_lookup = base_summary.set_index(["etf_code", "strategy_name"]).to_dict(orient="index")
    nav_lookup = {
        (str(etf), str(strategy)): g.sort_values("date")
        for (etf, strategy), g in nav.groupby(["etf_code", "strategy_name"])
    }

    rows: list[dict[str, object]] = []
    for (etf_code, strategy_name), g in decomposed.groupby(["etf_code", "strategy_name"]):
        if strategy_name == "BuyHold":
            continue
        g = g.sort_values("rebalance_date")
        factor = annual_factor(g)
        selected = g[g["option_selected_flag"] == 1]
        premium_received = float(selected["total_premium_yield"].sum())
        payoff_paid = float(selected["option_payoff_return_at_expiry"].fillna(0.0).sum())
        assigned = selected[selected["assignment_flag"].fillna(0).astype(int) == 1]
        base = summary_lookup.get((etf_code, strategy_name), {})
        dd_stats = _drawdown_duration_stats(nav_lookup.get((str(etf_code), str(strategy_name)), pd.DataFrame()))

        rows.append(
            {
                "etf_code": etf_code,
                "strategy_name": strategy_name,
                "start_date": g["rebalance_date"].min(),
                "end_date": g["period_end_date"].max(),
                "num_periods": int(len(g)),
                "selected_periods": int(len(selected)),
                "average_total_premium_yield": float(selected["total_premium_yield"].mean())
                if not selected.empty
                else np.nan,
                "average_extrinsic_premium_yield": float(selected["extrinsic_premium_yield"].mean())
                if not selected.empty
                else np.nan,
                "annualized_total_premium_yield": float(selected["total_premium_yield"].mean() * factor)
                if not selected.empty
                else np.nan,
                "annualized_extrinsic_premium_yield": float(selected["extrinsic_premium_yield"].mean() * factor)
                if not selected.empty
                else np.nan,
                "premium_received": premium_received,
                "payoff_paid": payoff_paid,
                "premium_capture_ratio": (premium_received - payoff_paid) / premium_received
                if premium_received != 0
                else np.nan,
                "assignment_rate": float(selected["assignment_flag"].fillna(0).astype(int).mean())
                if not selected.empty
                else np.nan,
                "average_payoff_given_assignment": float(assigned["option_payoff_return_at_expiry"].mean())
                if not assigned.empty
                else np.nan,
                "downside_excess_mean": base.get("downside_excess_mean", np.nan),
                "downside_cushion_ratio_mean": base.get("downside_cushion_ratio_mean", np.nan),
                "downside_win_rate": base.get("downside_win_rate", np.nan),
                "max_drawdown": base.get("max_drawdown", np.nan),
                "max_drawdown_improvement": base.get("max_drawdown_improvement", np.nan),
                "drawdown_duration": dd_stats["drawdown_duration"],
                "recovery_lag_after_drawdown": dd_stats["recovery_lag_after_drawdown"],
                "upside_cost_mean": base.get("upside_cost_mean", np.nan),
                "upside_underperformance_rate": base.get("upside_underperformance_rate", np.nan),
                "protection_cost_ratio": base.get("protection_cost_ratio", np.nan),
            }
        )

    return _sort_by_strategy_order(pd.DataFrame(rows))


def build_defensive_strategy_ranking(premium_summary: pd.DataFrame) -> pd.DataFrame:
    """Rank covered-call strategies by premium-income defensive priorities."""

    if premium_summary.empty:
        return premium_summary.copy()

    ranked = premium_summary.copy()
    rank_specs = {
        "annualized_extrinsic_premium_yield": "annualized_extrinsic_premium_yield_rank",
        "downside_cushion_ratio_mean": "downside_cushion_ratio_rank",
        "max_drawdown_improvement": "max_drawdown_improvement_rank",
        "premium_capture_ratio": "premium_capture_ratio_rank",
    }
    for source_col, rank_col in rank_specs.items():
        ranked[rank_col] = ranked.groupby("etf_code")[source_col].transform(
            lambda s: s.rank(method="average", pct=True, ascending=True).fillna(0.0)
        )

    ranked["primary_score"] = (
        0.35 * ranked["annualized_extrinsic_premium_yield_rank"]
        + 0.25 * ranked["downside_cushion_ratio_rank"]
        + 0.25 * ranked["max_drawdown_improvement_rank"]
        + 0.15 * ranked["premium_capture_ratio_rank"]
    )
    return ranked.sort_values(["etf_code", "primary_score"], ascending=[True, False]).reset_index(drop=True)


def build_premium_income_outputs(
    periods: pd.DataFrame,
    nav: pd.DataFrame,
    base_summary: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Build all premium-income defensive output tables."""

    premium_summary = build_premium_income_summary(periods, nav, base_summary)
    return {
        "premium_summary": premium_summary,
        "premium_decomposition": build_premium_decomposition_by_period(periods),
        "defensive_ranking": build_defensive_strategy_ranking(premium_summary),
    }
