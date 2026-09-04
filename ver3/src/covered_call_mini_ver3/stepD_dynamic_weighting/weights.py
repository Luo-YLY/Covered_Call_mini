from __future__ import annotations

import numpy as np
import pandas as pd

from .config import MethodSpec, WEIGHT_LOWER_BOUND, WEIGHT_UPPER_BOUND, strategy_name
from .universe import UniverseData


def compute_rebalance_weights(
    data: UniverseData,
    schedule: pd.DataFrame,
    method: MethodSpec,
    *,
    lower_bound: float = WEIGHT_LOWER_BOUND,
    upper_bound: float = WEIGHT_UPPER_BOUND,
    min_variance_grid_step: float = 0.01,
) -> pd.DataFrame:
    """Compute target weights on scheduled signal dates."""

    returns = data.returns.set_index("date")[list(data.universe.etf_codes)].astype(float)
    rows: list[dict[str, object]] = []
    for _, schedule_row in schedule.iterrows():
        lookback = int(schedule_row["lookback"])
        signal_date = pd.Timestamp(schedule_row["signal_date"])
        effective_date = pd.Timestamp(schedule_row["effective_date"])
        window = returns.loc[:signal_date].tail(lookback)
        sigma = window.std(ddof=1).replace(0.0, np.nan)
        if sigma.isna().any():
            raise ValueError(f"Zero or missing volatility in Step D signal window: {data.universe.universe_short} {signal_date}")

        raw = _raw_weights(data, window, method, sigma, min_variance_grid_step, lower_bound, upper_bound)
        bounded = normalize_with_bounds(raw, lower_bound=lower_bound, upper_bound=upper_bound)
        strat = strategy_name(data.universe.universe_short, method.method_name, lookback)
        for asset in data.universe.assets:
            raw_weight = float(raw[asset.etf_code])
            target_weight = float(bounded[asset.etf_code])
            rows.append(
                {
                    "strategy_name": strat,
                    "universe_short": data.universe.universe_short,
                    "method": method.method_name,
                    "method_label": method.method_label,
                    "lookback": lookback,
                    "rebalance_frequency": "monthly",
                    "signal_date": signal_date,
                    "effective_date": effective_date,
                    "etf_code": asset.etf_code,
                    "sleeve_key": asset.sleeve_key,
                    "raw_weight_unbounded": raw_weight,
                    "target_weight": target_weight,
                    "lower_bound": lower_bound,
                    "upper_bound": upper_bound,
                    "lower_bound_hit": target_weight <= lower_bound + 1e-10,
                    "upper_bound_hit": target_weight >= upper_bound - 1e-10,
                    "rolling_vol_daily": float(sigma.loc[asset.etf_code]),
                    "rolling_vol_annualized": float(sigma.loc[asset.etf_code] * np.sqrt(252.0)),
                    "signal_lag_rule": "uses t-1/signal_date information; applied on next trading day",
                }
            )
    return pd.DataFrame(rows)


def normalize_with_bounds(raw_weights: pd.Series, *, lower_bound: float, upper_bound: float) -> pd.Series:
    """Normalize positive raw weights into long-only box bounds."""

    raw = raw_weights.astype(float).replace([np.inf, -np.inf], np.nan)
    if raw.isna().any() or (raw <= 0).any():
        raise ValueError("Raw weights must be finite and positive.")
    values = raw / raw.sum()
    assets = list(values.index)
    fixed: dict[str, float] = {}
    for _ in range(20):
        below = [asset for asset in assets if asset not in fixed and values.loc[asset] < lower_bound]
        above = [asset for asset in assets if asset not in fixed and values.loc[asset] > upper_bound]
        if not below and not above:
            break
        for asset in below:
            fixed[asset] = lower_bound
        for asset in above:
            fixed[asset] = upper_bound
        free = [asset for asset in assets if asset not in fixed]
        if not free:
            break
        residual = 1.0 - sum(fixed.values())
        if residual < -1e-12:
            raise ValueError("Weight bounds are infeasible for the supplied raw weights.")
        free_raw = raw.loc[free]
        values = pd.Series(0.0, index=assets, dtype=float)
        for asset, value in fixed.items():
            values.loc[asset] = value
        values.loc[free] = free_raw / free_raw.sum() * residual

    values = values.clip(lower_bound, upper_bound)
    drift = 1.0 - float(values.sum())
    if abs(drift) > 1e-12:
        adjustable = [asset for asset in assets if lower_bound + 1e-10 < values.loc[asset] < upper_bound - 1e-10]
        if adjustable:
            values.loc[adjustable] = values.loc[adjustable] + drift / len(adjustable)
        else:
            values.loc[assets[-1]] = values.loc[assets[-1]] + drift
    if not np.isclose(values.sum(), 1.0, atol=1e-8):
        raise ValueError(f"Bounded weights do not sum to one: {values.sum()}")
    if (values < lower_bound - 1e-8).any() or (values > upper_bound + 1e-8).any():
        raise ValueError(f"Bounded weights outside constraints: {values.to_dict()}")
    return values


def weight_bound_hits(rebalance_weights: pd.DataFrame) -> pd.DataFrame:
    """Summarize weight bound hits by strategy and asset."""

    grouped = rebalance_weights.groupby(["strategy_name", "universe_short", "method", "lookback", "etf_code"], as_index=False).agg(
        rebalance_count=("effective_date", "count"),
        lower_bound_hit_count=("lower_bound_hit", "sum"),
        upper_bound_hit_count=("upper_bound_hit", "sum"),
        min_target_weight=("target_weight", "min"),
        max_target_weight=("target_weight", "max"),
        avg_target_weight=("target_weight", "mean"),
    )
    grouped["any_bound_hit"] = (grouped["lower_bound_hit_count"].astype(int) + grouped["upper_bound_hit_count"].astype(int)) > 0
    return grouped


def _raw_weights(
    data: UniverseData,
    window: pd.DataFrame,
    method: MethodSpec,
    sigma: pd.Series,
    min_variance_grid_step: float,
    lower_bound: float,
    upper_bound: float,
) -> pd.Series:
    if method.method_name == "anchored_inverse_vol":
        anchor = pd.Series(data.universe.anchor_weights, dtype=float).reindex(data.universe.etf_codes)
        raw = anchor / sigma.reindex(data.universe.etf_codes)
        return raw / raw.sum()
    if method.method_name == "pure_inverse_vol":
        raw = 1.0 / sigma.reindex(data.universe.etf_codes)
        return raw / raw.sum()
    if method.method_name == "rolling_min_variance":
        cov = window.cov().reindex(index=data.universe.etf_codes, columns=data.universe.etf_codes)
        return _grid_min_variance(cov, lower_bound=lower_bound, upper_bound=upper_bound, step=min_variance_grid_step)
    raise ValueError(f"Unsupported Step D method: {method.method_name}")


def _grid_min_variance(cov: pd.DataFrame, *, lower_bound: float, upper_bound: float, step: float) -> pd.Series:
    assets = list(cov.index)
    if len(assets) != 3:
        raise ValueError("Step D rolling minimum variance currently expects exactly three assets.")
    values = cov.to_numpy(dtype=float)
    best_w: np.ndarray | None = None
    best_var = np.inf
    grid = np.round(np.arange(lower_bound, upper_bound + step / 2.0, step), 10)
    for w0 in grid:
        for w1 in grid:
            w2 = 1.0 - w0 - w1
            if w2 < lower_bound - 1e-10 or w2 > upper_bound + 1e-10:
                continue
            w = np.array([w0, w1, w2], dtype=float)
            variance = float(w @ values @ w)
            if variance < best_var:
                best_var = variance
                best_w = w
    if best_w is None:
        raise ValueError("No feasible grid weight found for rolling minimum variance.")
    return pd.Series(best_w, index=assets, dtype=float)
