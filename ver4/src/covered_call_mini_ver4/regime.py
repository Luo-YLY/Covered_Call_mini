from __future__ import annotations

import numpy as np
import pandas as pd

from .config import CycleExperimentConfig


def label_market_regime(return_value: float, breaks: tuple[float, ...]) -> str:
    down, neutral, strong = breaks
    if return_value <= down:
        return "下跌周期"
    if return_value < neutral:
        return "震荡周期"
    if return_value < strong:
        return "上涨周期"
    return "强上涨周期"


def build_cycle_regime_attribution(ledger: pd.DataFrame, config: CycleExperimentConfig) -> pd.DataFrame:
    """Describe realised market states; these labels are never used for opening a trade."""

    if ledger.empty:
        return pd.DataFrame()
    d = ledger.copy()
    d["market_regime"] = d["etf_period_return"].astype(float).map(
        lambda value: label_market_regime(value, config.regime_breaks)
    )
    d["regime_definition"] = "ex_post_etf_period_return: <=-5%, -5%~5%, 5%~10%, >=10%"
    rows: list[dict[str, float | int | str]] = []
    group_cols = ["etf_code", "strategy_name", "strategy_label", "parameter_role", "target_delta", "coverage", "market_regime"]
    for keys, group in d.groupby(group_cols, dropna=False):
        net = group["net_option_yield"].astype(float)
        relative = group["relative_to_buyhold_return"].astype(float)
        rows.append(
            {
                "etf_code": keys[0],
                "strategy_name": keys[1],
                "strategy_label": keys[2],
                "parameter_role": keys[3],
                "target_delta": keys[4],
                "coverage": keys[5],
                "market_regime": keys[6],
                "regime_definition": group["regime_definition"].iloc[0],
                "cycle_count": int(len(group)),
                "etf_period_return_mean": float(group["etf_period_return"].mean()),
                "gross_premium_yield_mean": float(group["gross_premium_yield"].mean()),
                "net_option_yield_mean": float(net.mean()),
                "net_option_yield_median": float(net.median()),
                "positive_net_option_cycle_rate": float((net > 0).mean()),
                "relative_to_buyhold_return_mean": float(relative.mean()),
                "underperform_buyhold_cycle_rate": float((relative < 0).mean()),
                "upside_cap_return_mean": float(group["upside_cap_return"].mean()),
                "assignment_rate": float(group.loc[group["selected_option_flag"].eq(1), "assignment_flag"].mean())
                if int(group["selected_option_flag"].sum()) else np.nan,
            }
        )
    return pd.DataFrame(rows)
