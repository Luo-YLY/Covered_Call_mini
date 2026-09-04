from __future__ import annotations

import math

import numpy as np
import pandas as pd

from src.metrics.ver2_metric_standard import TRADING_DAYS_PER_YEAR

from .config import ConstraintSpec, D_STAR_LIST, UniverseSpec, sleeve_return_column


def generate_weight_grid(etf_codes: tuple[str, ...], grid_step: float, lower_bound: float, upper_bound: float) -> pd.DataFrame:
    """Generate a long-only grid whose weights sum to one."""

    if grid_step <= 0 or grid_step > 1:
        raise ValueError(f"grid_step must be in (0, 1], got {grid_step}")
    scale = int(round(1.0 / grid_step))
    if not math.isclose(scale * grid_step, 1.0, rel_tol=0.0, abs_tol=1e-10):
        raise ValueError("grid_step must divide 1.0 exactly enough for an integer grid.")

    lower = int(math.ceil(lower_bound * scale - 1e-10))
    upper = int(math.floor(upper_bound * scale + 1e-10))
    n_assets = len(etf_codes)
    rows: list[dict[str, float]] = []

    def recurse(prefix: list[int], remaining: int) -> None:
        idx = len(prefix)
        slots_left = n_assets - idx
        if slots_left == 1:
            value = remaining
            if lower <= value <= upper:
                units = [*prefix, value]
                rows.append({f"weight_{etf}": unit / scale for etf, unit in zip(etf_codes, units)})
            return

        min_value = max(lower, remaining - upper * (slots_left - 1))
        max_value = min(upper, remaining - lower * (slots_left - 1))
        for value in range(min_value, max_value + 1):
            recurse([*prefix, value], remaining - value)

    recurse([], scale)
    if not rows:
        return pd.DataFrame(columns=[f"weight_{etf}" for etf in etf_codes])
    out = pd.DataFrame(rows)
    out["weight_sum"] = out[[f"weight_{etf}" for etf in etf_codes]].sum(axis=1)
    out["weight_vector_key"] = out.apply(
        lambda row: "_".join(f"{etf}{int(round(float(row[f'weight_{etf}']) * 100)):02d}" for etf in etf_codes),
        axis=1,
    )
    return out


def evaluate_universe_grid(
    sample_panel: pd.DataFrame,
    option_leg_panel: pd.DataFrame,
    universe: UniverseSpec,
    constraint: ConstraintSpec,
    *,
    grid_step: float,
) -> pd.DataFrame:
    """Evaluate every static weight vector for one universe and constraint set."""

    grid = generate_weight_grid(universe.etf_codes, grid_step, constraint.lower_bound, constraint.upper_bound)
    if grid.empty:
        return _empty_grid_result(universe, constraint, grid_step)

    sleeve_cols = [sleeve_return_column(etf, universe.sleeves_by_etf[etf]) for etf in universe.etf_codes]
    returns = sample_panel[sleeve_cols].astype(float).to_numpy()
    option = _option_matrix(option_leg_panel, sample_panel["date"], sleeve_cols)
    weights = grid[[f"weight_{etf}" for etf in universe.etf_codes]].astype(float).to_numpy()

    portfolio_returns = returns @ weights.T
    option_returns = option @ weights.T
    metrics = _fast_metric_frame(portfolio_returns, option_returns)

    out = pd.concat([grid.reset_index(drop=True), metrics], axis=1)
    out.insert(0, "experiment_version", "ver3.0_stepB_plus")
    out.insert(1, "universe_short", universe.universe_short)
    out.insert(2, "universe_name", universe.universe_name)
    out.insert(3, "constraint_set", constraint.name)
    out.insert(4, "grid_step", float(grid_step))
    out.insert(5, "lower_bound", float(constraint.lower_bound))
    out.insert(6, "upper_bound", float(constraint.upper_bound))
    out["portfolio_type"] = "Selected_Grid"
    out["sample_start"] = pd.to_datetime(sample_panel["date"]).min().date().isoformat()
    out["sample_end"] = pd.to_datetime(sample_panel["date"]).max().date().isoformat()
    out["n_trading_days"] = int(len(sample_panel))
    out["sleeve_set"] = " | ".join(f"{etf}:{sleeve}" for etf, sleeve in universe.sleeves_by_etf.items())
    return out


def select_best_by_drawdown_target(
    grid_results: pd.DataFrame,
    *,
    d_star_list: tuple[float, ...] = D_STAR_LIST,
) -> pd.DataFrame:
    """Select max Sharpe rows under each MDD target, marking infeasible targets."""

    rows: list[dict[str, object]] = []
    group_cols = ["universe_short", "universe_name", "constraint_set", "grid_step", "lower_bound", "upper_bound"]
    for keys, group in grid_results.groupby(group_cols, dropna=False, sort=True):
        base = dict(zip(group_cols, keys))
        for d_star in d_star_list:
            feasible = group[group["max_drawdown"].astype(float) <= float(d_star)].copy()
            if feasible.empty:
                rows.append(
                    {
                        **base,
                        "D_star": float(d_star),
                        "frontier_status": "infeasible",
                        "feasible": False,
                        "feasible_candidate_count": 0,
                        "portfolio_name": _portfolio_name(base["universe_short"], base["constraint_set"], d_star, "NA"),
                        "note": "没有网格权重向量满足该 MDD 目标。",
                    }
                )
                continue
            best = feasible.sort_values(
                ["sharpe_daily_mean", "max_drawdown", "annualized_return_cagr"],
                ascending=[False, True, False],
            ).iloc[0]
            row = best.to_dict()
            row.update(
                {
                    "D_star": float(d_star),
                    "frontier_status": "feasible",
                    "feasible": True,
                    "feasible_candidate_count": int(len(feasible)),
                    "portfolio_name": _portfolio_name(
                        str(best["universe_short"]),
                        str(best["constraint_set"]),
                        float(d_star),
                        str(best["weight_vector_key"]),
                    ),
                    "note": "在满足 MDD 目标的网格行中选择 sharpe_daily_mean 最高者。",
                }
            )
            rows.append(row)
    out = pd.DataFrame(rows)
    return out.sort_values(["constraint_set", "universe_short", "D_star"]).reset_index(drop=True)


def best_weight_long(best_rows: pd.DataFrame) -> pd.DataFrame:
    """Convert feasible best rows to one row per ETF weight."""

    rows: list[dict[str, object]] = []
    for _, row in best_rows[best_rows["feasible"].astype(bool)].iterrows():
        for col in [c for c in best_rows.columns if c.startswith("weight_") and c not in {"weight_sum", "weight_vector_key"}]:
            etf = col.removeprefix("weight_")
            value = row.get(col)
            if pd.isna(value):
                continue
            rows.append(
                {
                    "portfolio_name": row["portfolio_name"],
                    "universe_short": row["universe_short"],
                    "constraint_set": row["constraint_set"],
                    "D_star": row["D_star"],
                    "etf_code": etf,
                    "weight": float(value),
                }
            )
    return pd.DataFrame(rows)


def _fast_metric_frame(portfolio_returns: np.ndarray, option_returns: np.ndarray) -> pd.DataFrame:
    nav = np.cumprod(1.0 + portfolio_returns, axis=0)
    metric_returns = portfolio_returns[1:, :] if portfolio_returns.shape[0] > 1 else portfolio_returns
    n_metric = max(metric_returns.shape[0], 1)

    mean = np.nanmean(metric_returns, axis=0)
    std = np.nanstd(metric_returns, axis=0, ddof=1) if metric_returns.shape[0] > 1 else np.full(portfolio_returns.shape[1], np.nan)
    annualized_vol = std * np.sqrt(TRADING_DAYS_PER_YEAR)
    sharpe = np.divide(
        mean,
        std,
        out=np.full_like(mean, np.nan, dtype=float),
        where=np.isfinite(std) & (std > 0),
    ) * np.sqrt(TRADING_DAYS_PER_YEAR)
    arithmetic = mean * TRADING_DAYS_PER_YEAR

    downside = np.minimum(metric_returns, 0.0)
    downside_std = np.nanstd(downside, axis=0, ddof=1) if metric_returns.shape[0] > 1 else np.full(portfolio_returns.shape[1], np.nan)
    downside_dev = downside_std * np.sqrt(TRADING_DAYS_PER_YEAR)
    sortino = np.divide(
        arithmetic,
        downside_dev,
        out=np.full_like(arithmetic, np.nan, dtype=float),
        where=np.isfinite(downside_dev) & (downside_dev > 0),
    )

    first_nav = nav[0, :]
    final_nav = nav[-1, :]
    cumulative = np.divide(
        final_nav,
        first_nav,
        out=np.full_like(final_nav, np.nan, dtype=float),
        where=np.isfinite(first_nav) & (first_nav > 0),
    ) - 1.0
    cagr = np.power(1.0 + cumulative, TRADING_DAYS_PER_YEAR / n_metric) - 1.0
    cagr[~np.isfinite(cagr)] = np.nan

    peaks = np.maximum.accumulate(nav, axis=0)
    drawdown_mag = 1.0 - np.divide(nav, peaks, out=np.ones_like(nav), where=peaks > 0)
    max_drawdown = np.nanmax(drawdown_mag, axis=0)
    calmar = np.divide(
        cagr,
        max_drawdown,
        out=np.full_like(cagr, np.nan, dtype=float),
        where=np.isfinite(max_drawdown) & (max_drawdown > 0),
    )
    option_contrib = np.nansum(option_returns, axis=0) * TRADING_DAYS_PER_YEAR / max(portfolio_returns.shape[0], 1)

    return pd.DataFrame(
        {
            "annualized_return_cagr": cagr,
            "arithmetic_annualized_return": arithmetic,
            "annualized_volatility": annualized_vol,
            "sharpe_daily_mean": sharpe,
            "sortino_ratio": sortino,
            "calmar_ratio": calmar,
            "max_drawdown": max_drawdown,
            "final_nav": final_nav,
            "initial_nav": 1.0,
            "cumulative_return": cumulative,
            "cagr_vol_ratio": np.divide(
                cagr,
                annualized_vol,
                out=np.full_like(cagr, np.nan, dtype=float),
                where=np.isfinite(annualized_vol) & (annualized_vol > 0),
            ),
            "option_leg_annualized_pnl_contribution": option_contrib,
        }
    )


def _option_matrix(option_leg_panel: pd.DataFrame, dates: pd.Series, sleeve_cols: list[str]) -> np.ndarray:
    if option_leg_panel.empty:
        return np.zeros((len(dates), len(sleeve_cols)))
    option = option_leg_panel.copy()
    option["date"] = pd.to_datetime(option["date"])
    option = option.set_index("date").reindex(pd.to_datetime(dates))
    cols = []
    for col in sleeve_cols:
        if col in option.columns:
            cols.append(option[col].astype(float).fillna(0.0).to_numpy())
        else:
            cols.append(np.zeros(len(dates)))
    return np.column_stack(cols)


def _empty_grid_result(universe: UniverseSpec, constraint: ConstraintSpec, grid_step: float) -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "experiment_version",
            "universe_short",
            "universe_name",
            "constraint_set",
            "grid_step",
            "lower_bound",
            "upper_bound",
            "portfolio_type",
            "sample_start",
            "sample_end",
            "n_trading_days",
            "sleeve_set",
        ]
    )


def _portfolio_name(universe_short: str, constraint_set: str, d_star: float, weight_key: str) -> str:
    return f"{universe_short}_{constraint_set}_D{int(round(float(d_star) * 100)):02d}_{weight_key}"
