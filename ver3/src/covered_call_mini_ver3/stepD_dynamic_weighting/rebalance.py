from __future__ import annotations

import pandas as pd

from .universe import UniverseData


def expand_rebalance_weights_to_daily(data: UniverseData, rebalance_weights: pd.DataFrame) -> pd.DataFrame:
    """Forward-fill monthly target weights to daily portfolio weights."""

    frames = []
    for (strategy, method, lookback), group in rebalance_weights.groupby(["strategy_name", "method", "lookback"], sort=False):
        pivot = (
            group.pivot_table(index="effective_date", columns="etf_code", values="target_weight", aggfunc="last")
            .sort_index()
            .reindex(columns=list(data.universe.etf_codes))
        )
        dates = pd.to_datetime(data.returns["date"])
        daily_index = dates[dates >= pd.Timestamp(pivot.index.min())]
        daily = pivot.reindex(daily_index, method="ffill")
        daily.index.name = "date"
        long = daily.reset_index().melt(id_vars="date", var_name="etf_code", value_name="target_weight")
        long["strategy_name"] = strategy
        long["universe_short"] = data.universe.universe_short
        long["method"] = method
        long["lookback"] = int(lookback)
        long["rebalance_frequency"] = "monthly"
        sleeve_map = {asset.etf_code: asset.sleeve_key for asset in data.universe.assets}
        long["sleeve_key"] = long["etf_code"].map(sleeve_map)
        frames.append(long)
    out = pd.concat(frames, ignore_index=True, sort=False)
    return out[
        [
            "date",
            "strategy_name",
            "universe_short",
            "method",
            "lookback",
            "rebalance_frequency",
            "etf_code",
            "sleeve_key",
            "target_weight",
        ]
    ].sort_values(["strategy_name", "date", "etf_code"]).reset_index(drop=True)
