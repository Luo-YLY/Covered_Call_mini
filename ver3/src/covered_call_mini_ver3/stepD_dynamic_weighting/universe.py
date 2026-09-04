from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .config import TARGET_SAMPLE_END, TARGET_SAMPLE_START, UniverseSpec


@dataclass(frozen=True)
class UniverseData:
    """Aligned daily total and option-leg return panels for one Step D universe."""

    universe: UniverseSpec
    returns: pd.DataFrame
    option_returns: pd.DataFrame


def build_universe_data(return_panel: pd.DataFrame, option_leg_panel: pd.DataFrame, universe: UniverseSpec) -> UniverseData:
    """Build one aligned universe panel with ETF-code columns."""

    required = [asset.return_column for asset in universe.assets]
    missing = [col for col in required if col not in return_panel.columns]
    if missing:
        raise ValueError("Step D missing required sleeve return column(s):\n" + "\n".join(missing))

    base = return_panel[["date", *required]].copy()
    base["date"] = pd.to_datetime(base["date"])
    base = base[(base["date"] >= pd.Timestamp(TARGET_SAMPLE_START)) & (base["date"] <= pd.Timestamp(TARGET_SAMPLE_END))]
    base = base.dropna(subset=required).sort_values("date").reset_index(drop=True)
    if base.empty:
        raise ValueError(f"Step D universe {universe.universe_short} has no aligned return sample.")

    rename = {asset.return_column: asset.etf_code for asset in universe.assets}
    returns = base.rename(columns=rename)

    option = pd.DataFrame({"date": returns["date"]})
    if option_leg_panel is not None and not option_leg_panel.empty:
        opt = option_leg_panel.copy()
        opt["date"] = pd.to_datetime(opt["date"])
        opt = opt.set_index("date").reindex(returns["date"]).reset_index()
        for asset in universe.assets:
            if asset.return_column in opt.columns:
                option[asset.etf_code] = opt[asset.return_column].astype(float).fillna(0.0).values
            else:
                option[asset.etf_code] = 0.0
    else:
        for asset in universe.assets:
            option[asset.etf_code] = 0.0

    return UniverseData(universe=universe, returns=returns[["date", *universe.etf_codes]], option_returns=option[["date", *universe.etf_codes]])


def universe_config_table(universes: list[UniverseSpec]) -> pd.DataFrame:
    """Return a long table describing Step D universe assets and anchor weights."""

    rows: list[dict[str, object]] = []
    for universe in universes:
        for asset in universe.assets:
            rows.append(
                {
                    "universe_short": universe.universe_short,
                    "universe_name": universe.universe_name,
                    "anchor_portfolio_name": universe.anchor_portfolio_name,
                    "etf_code": asset.etf_code,
                    "sleeve_name": asset.sleeve_name,
                    "sleeve_key": asset.sleeve_key,
                    "asset_role": asset.role,
                    "anchor_weight": universe.anchor_weights[asset.etf_code],
                    "description": universe.description,
                }
            )
    return pd.DataFrame(rows)


def sample_summary_table(datas: list[UniverseData]) -> pd.DataFrame:
    """Summarize aligned sample windows."""

    rows = []
    for data in datas:
        rows.append(
            {
                "universe_short": data.universe.universe_short,
                "sample_start": data.returns["date"].min().date().isoformat(),
                "sample_end": data.returns["date"].max().date().isoformat(),
                "n_trading_days_before_lookback": int(len(data.returns)),
                "required_sleeve_count": int(len(data.universe.assets)),
                "required_sleeves": ";".join(asset.sleeve_key for asset in data.universe.assets),
            }
        )
    return pd.DataFrame(rows)
