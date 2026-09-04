from __future__ import annotations

import numpy as np
import pandas as pd

from ver2_downside_protection.metrics import add_period_diagnostics


BUCKET_ORDER = ["mild_down", "moderate_down", "severe_down"]


def downside_bucket_label(etf_return: float) -> str | None:
    if pd.isna(etf_return) or etf_return >= 0:
        return None
    if etf_return > -0.03:
        return "mild_down"
    if etf_return > -0.08:
        return "moderate_down"
    return "severe_down"


def build_downside_bucket_table(periods: pd.DataFrame) -> pd.DataFrame:
    """Bucket covered-call excess returns by the ETF's own period loss."""

    data = add_period_diagnostics(periods)
    data = data[data["strategy_name"] != "BuyHold"].copy()
    data["downside_bucket"] = data["etf_period_return"].map(downside_bucket_label)
    rows: list[dict[str, object]] = []

    group_keys = sorted(data[["etf_code", "strategy_name"]].drop_duplicates().itertuples(index=False, name=None))
    for etf_code, strategy_name in group_keys:
        g = data[(data["etf_code"] == etf_code) & (data["strategy_name"] == strategy_name)]
        for bucket in BUCKET_ORDER:
            b = g[g["downside_bucket"] == bucket]
            rows.append(
                {
                    "etf_code": etf_code,
                    "strategy_name": strategy_name,
                    "downside_bucket": bucket,
                    "count": int(len(b)),
                    "etf_return_mean": float(b["etf_period_return"].mean()) if not b.empty else np.nan,
                    "strategy_return_mean": float(b["strategy_period_return"].mean()) if not b.empty else np.nan,
                    "excess_return_mean": float(b["excess_return_vs_etf"].mean()) if not b.empty else np.nan,
                    "downside_cushion_ratio_mean": float(b["downside_cushion_ratio"].mean()) if not b.empty else np.nan,
                    "downside_win_rate": float((b["strategy_period_return"] > b["etf_period_return"]).mean())
                    if not b.empty
                    else np.nan,
                }
            )
    return pd.DataFrame(rows)
