from __future__ import annotations

import numpy as np
import pandas as pd

from src.metrics.ver2_metric_standard import compute_portfolio_option_contribution, summarize_daily_nav

from .config import CandidatePortfolio, TargetSleeve, buyhold_key_for_etf


def common_window_start(daily: pd.DataFrame, group_col: str) -> str:
    """Return the latest first date across phase paths."""

    starts = pd.to_datetime(daily.groupby([group_col, "phase_id"])["date"].min())
    return pd.Timestamp(starts.max()).date().isoformat()


def compute_phase_metrics(
    daily_nav: pd.DataFrame,
    period_map: pd.DataFrame,
    *,
    rf: float,
    common_start: str,
    window_mode: str,
) -> pd.DataFrame:
    """Compute sleeve metrics by phase for natural or common windows."""

    rows: list[dict[str, object]] = []
    period_lookup = _period_lookup(period_map)
    for (sleeve_key, phase_id), group in daily_nav.groupby(["sleeve_key", "phase_id"], sort=True):
        g = _window(group, common_start, window_mode)
        if len(g) < 2:
            continue
        metrics = summarize_daily_nav(g[["date", "nav_total"]], date_col="date", nav_col="nav_total", rf=rf)
        key = (sleeve_key, phase_id)
        option_metrics = _option_metrics(g, period_lookup.get(key, pd.DataFrame()))
        first = g.iloc[0]
        rows.append(
            {
                "window_mode": window_mode,
                "phase_id": phase_id,
                "phase_shift": int(first["phase_shift"]),
                "inception_date": first["inception_date"],
                "etf_code": first["etf_code"],
                "sleeve_name": first["sleeve_name"],
                "sleeve_key": sleeve_key,
                "is_buyhold": bool(first["is_buyhold"]),
                "strategy_family": first["strategy_family"],
                "coverage": float(first["coverage"]),
                **metrics,
                "final_nav": float(g["nav_total"].iloc[-1]),
                **option_metrics,
            }
        )
    return pd.DataFrame(rows)


def compute_portfolio_phase_metrics(
    portfolio_returns: pd.DataFrame,
    portfolio_nav: pd.DataFrame,
    *,
    rf: float,
    common_start: str,
    window_mode: str,
) -> pd.DataFrame:
    """Compute portfolio metrics by phase."""

    rows: list[dict[str, object]] = []
    returns_lookup = {k: g for k, g in portfolio_returns.groupby(["portfolio_name", "phase_id"], sort=False)}
    for (portfolio_name, phase_id), nav_g in portfolio_nav.groupby(["portfolio_name", "phase_id"], sort=True):
        g = _window(nav_g, common_start, window_mode, nav_col="nav")
        if len(g) < 2:
            continue
        ret_g = returns_lookup[(portfolio_name, phase_id)]
        ret_g = ret_g[(pd.to_datetime(ret_g["date"]) >= pd.Timestamp(g["date"].min())) & (pd.to_datetime(ret_g["date"]) <= pd.Timestamp(g["date"].max()))]
        metrics = summarize_daily_nav(g[["date", "nav"]], date_col="date", nav_col="nav", rf=rf)
        first = g.iloc[0]
        rows.append(
            {
                "window_mode": window_mode,
                "phase_id": phase_id,
                "phase_shift": int(first["phase_shift"]),
                "inception_date": first["inception_date"],
                "portfolio_name": portfolio_name,
                "base_portfolio_name": first["base_portfolio_name"],
                "portfolio_role": first["portfolio_role"],
                **metrics,
                "option_leg_annualized_pnl_contribution": compute_portfolio_option_contribution(
                    ret_g["portfolio_option_leg_return"], n_days=len(ret_g)
                ),
                "final_nav": float(g["nav"].iloc[-1]),
            }
        )
    return pd.DataFrame(rows)


def compute_phase_robustness_summary(
    phase_metrics: pd.DataFrame,
    *,
    entity_col: str,
    target_mdd: dict[str, float] | None = None,
    buyhold_comparison: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Summarize phase metric distributions and assign robustness labels."""

    target_mdd = target_mdd or {}
    rows: list[dict[str, object]] = []
    for name, group in phase_metrics.groupby(entity_col, sort=True):
        g = group[group["window_mode"].eq("common")].copy()
        if g.empty:
            continue
        sharpe = g["sharpe_daily_mean"].astype(float)
        cagr = g["annualized_return_cagr"].astype(float)
        mdd = g["max_drawdown"].astype(float)
        option = g["option_leg_annualized_pnl_contribution"].astype(float)
        hit = _hit_rates(name, g, entity_col, buyhold_comparison)
        t_mdd = float(target_mdd.get(str(name), 0.20))
        sharpe_mean = float(sharpe.mean())
        sharpe_std = float(sharpe.std(ddof=1)) if len(sharpe) > 1 else 0.0
        mdd_p75 = _q(mdd, 0.75)
        robust_score = float(np.nanmedian(sharpe) - 0.5 * sharpe_std - max(0.0, mdd_p75 - t_mdd))
        fragility_score = float(sharpe_std / (abs(sharpe_mean) + 1e-6))
        rows.append(
            {
                entity_col: name,
                "phase_count": int(len(g)),
                "phase_success_count": int(g[["annualized_return_cagr", "sharpe_daily_mean", "max_drawdown"]].notna().all(axis=1).sum()),
                "phase_failure_count": int(group["phase_id"].nunique() - len(g)),
                "sharpe_mean": sharpe_mean,
                "sharpe_median": float(sharpe.median()),
                "sharpe_std": sharpe_std,
                "sharpe_min": float(sharpe.min()),
                "sharpe_p10": _q(sharpe, 0.10),
                "sharpe_p25": _q(sharpe, 0.25),
                "sharpe_p75": _q(sharpe, 0.75),
                "sharpe_max": float(sharpe.max()),
                "cagr_mean": float(cagr.mean()),
                "cagr_median": float(cagr.median()),
                "cagr_std": float(cagr.std(ddof=1)) if len(cagr) > 1 else 0.0,
                "mdd_mean": float(mdd.mean()),
                "mdd_median": float(mdd.median()),
                "mdd_p75": mdd_p75,
                "mdd_p90": _q(mdd, 0.90),
                "mdd_max": float(mdd.max()),
                "option_leg_mean": float(option.mean()),
                "option_leg_median": float(option.median()),
                "option_leg_std": float(option.std(ddof=1)) if len(option) > 1 else 0.0,
                "positive_option_leg_phase_rate": float((option > 0).mean()),
                "phase_hit_rate_vs_buyhold": hit["phase_hit_rate_vs_buyhold"],
                "phase_hit_rate_mdd_below_buyhold": hit["phase_hit_rate_mdd_below_buyhold"],
                "phase_hit_rate_sharpe_positive": float((sharpe > 0).mean()),
                "phase_fragility_score": fragility_score,
                "phase_robust_score": robust_score,
                "phase_robustness_label": _label(fragility_score, robust_score, sharpe, mdd, t_mdd),
            }
        )
    return pd.DataFrame(rows).sort_values("phase_robust_score", ascending=False).reset_index(drop=True)


def sleeve_buyhold_comparison(sleeve_metrics: pd.DataFrame, sleeves: list[TargetSleeve]) -> pd.DataFrame:
    """Build same-ETF buyhold comparison rows for sleeve hit rates."""

    common = sleeve_metrics[sleeve_metrics["window_mode"].eq("common")].copy()
    rows = []
    for sleeve in sleeves:
        if sleeve.is_buyhold:
            continue
        bench_key = buyhold_key_for_etf(sleeve.etf_code)
        left = common[common["sleeve_key"].eq(sleeve.sleeve_key)]
        right = common[common["sleeve_key"].eq(bench_key)][["phase_id", "sharpe_daily_mean", "max_drawdown", "annualized_return_cagr"]]
        merged = left.merge(right, on="phase_id", suffixes=("", "_buyhold"))
        rows.append(merged)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def portfolio_buyhold_comparison(portfolio_metrics: pd.DataFrame) -> pd.DataFrame:
    """Build buyhold-benchmark comparisons for candidate portfolio hit rates."""

    common = portfolio_metrics[portfolio_metrics["window_mode"].eq("common")].copy()
    target = common[common["portfolio_role"].eq("target_candidate")]
    bench = common[common["portfolio_role"].eq("buyhold_benchmark")][
        ["base_portfolio_name", "phase_id", "sharpe_daily_mean", "max_drawdown", "annualized_return_cagr"]
    ]
    return target.merge(bench, on=["base_portfolio_name", "phase_id"], suffixes=("", "_buyhold"))


def _window(group: pd.DataFrame, common_start: str, window_mode: str, nav_col: str = "nav_total") -> pd.DataFrame:
    g = group.sort_values("date").copy()
    g["date"] = pd.to_datetime(g["date"], errors="coerce")
    if window_mode == "common":
        g = g[g["date"] >= pd.Timestamp(common_start)].copy()
        if not g.empty:
            first_nav = float(g[nav_col].iloc[0])
            if first_nav > 0:
                g[nav_col] = g[nav_col].astype(float) / first_nav
    elif window_mode != "natural":
        raise ValueError(f"Unknown window_mode: {window_mode}")
    return g


def _period_lookup(period_map: pd.DataFrame) -> dict[tuple[str, str], pd.DataFrame]:
    if period_map.empty:
        return {}
    return {k: g.copy() for k, g in period_map.groupby(["sleeve_key", "phase_id"], sort=False)}


def _option_metrics(sample: pd.DataFrame, period: pd.DataFrame) -> dict[str, object]:
    option_pnl = sample["option_leg_pnl"].astype(float)
    stress = sample["short_call_mtm_loss"].astype(float)
    if period.empty:
        return {
            "option_leg_annualized_pnl_contribution": 0.0,
            "premium_capture_ratio_agg": np.nan,
            "payoff_burden_agg": np.nan,
            "positive_option_leg_period_rate": np.nan,
            "assignment_rate": np.nan,
            "p95_short_call_mtm_loss": 0.0,
            "p99_short_call_mtm_loss": 0.0,
            "max_short_call_mtm_loss": 0.0,
            "selected_periods": 0,
            "skipped_periods": 0,
        }
    premium = period["premium_return"].astype(float)
    payoff = period["upside_payoff_return"].astype(float)
    option_leg = period["net_option_contribution"].astype(float)
    return {
        "option_leg_annualized_pnl_contribution": compute_portfolio_option_contribution(option_pnl, n_days=len(sample)),
        "premium_capture_ratio_agg": _safe_div(float(option_leg.sum()), float(premium.sum())),
        "payoff_burden_agg": _safe_div(float(payoff.sum()), float(premium.sum())),
        "positive_option_leg_period_rate": float((option_leg > 0).mean()),
        "assignment_rate": float(period["assignment_flag"].astype(bool).mean()) if "assignment_flag" in period else np.nan,
        "p95_short_call_mtm_loss": float(stress.quantile(0.95)),
        "p99_short_call_mtm_loss": float(stress.quantile(0.99)),
        "max_short_call_mtm_loss": float(stress.max()),
        "selected_periods": int(period["option_selected_flag"].astype(int).sum()),
        "skipped_periods": int((period["option_selected_flag"].astype(int) == 0).sum()),
    }


def _hit_rates(name: str, group: pd.DataFrame, entity_col: str, comparison: pd.DataFrame | None) -> dict[str, float]:
    if comparison is None or comparison.empty:
        return {"phase_hit_rate_vs_buyhold": np.nan, "phase_hit_rate_mdd_below_buyhold": np.nan}
    if entity_col == "sleeve_name":
        c = comparison[comparison["sleeve_name"].eq(name)]
    else:
        c = comparison[comparison["base_portfolio_name"].eq(name)]
    if c.empty:
        return {"phase_hit_rate_vs_buyhold": np.nan, "phase_hit_rate_mdd_below_buyhold": np.nan}
    return {
        "phase_hit_rate_vs_buyhold": float((c["sharpe_daily_mean"] > c["sharpe_daily_mean_buyhold"]).mean()),
        "phase_hit_rate_mdd_below_buyhold": float((c["max_drawdown"] < c["max_drawdown_buyhold"]).mean()),
    }


def _safe_div(numerator: float, denominator: float) -> float:
    return float(numerator) / float(denominator) if abs(float(denominator)) > 1e-12 else np.nan


def _q(series: pd.Series, q: float) -> float:
    return float(series.dropna().quantile(q)) if not series.dropna().empty else np.nan


def _label(fragility: float, robust_score: float, sharpe: pd.Series, mdd: pd.Series, target_mdd: float) -> str:
    sharpe_p25 = _q(sharpe, 0.25)
    mdd_p75 = _q(mdd, 0.75)
    if len(sharpe.dropna()) < 3:
        return "Diagnostic Only"
    if fragility < 0.35 and sharpe_p25 > 0 and mdd_p75 <= target_mdd:
        return "High Phase Robustness"
    if fragility < 0.75 and float(sharpe.median()) > 0 and mdd_p75 <= target_mdd + 0.02:
        return "Medium Phase Robustness"
    if float(sharpe.min()) < 0 or fragility > 1.25 or robust_score < 0:
        return "Phase Fragile"
    return "Low Phase Robustness"
