from __future__ import annotations

from dataclasses import replace
from typing import Any

import numpy as np
import pandas as pd

from ver2_downside_protection.config import ExperimentConfig, StrategyConfig
from ver2_downside_protection.data_adapter import Ver2DataBundle, price_on
from ver2_downside_protection.strategy_engine import _build_daily_mtm, _continuous_covered_call_rows

from .config import INITIAL_NAV, SAMPLE_END, TargetSleeve


def validate_phase_engine_support() -> dict[str, object]:
    """Return support flags for real covered-call phase rebuilding."""

    return {
        "phase_engine_support": True,
        "covered_call_paths_rebuilt_not_sliced": True,
        "engine_adapter": "ver2_downside_protection.strategy_engine._continuous_covered_call_rows",
        "note": "The wrapper passes shifted inception date as first_rebalance_date, then rebuilds option cycles.",
    }


def run_buyhold_for_phase(
    data: Ver2DataBundle,
    sleeve: TargetSleeve,
    *,
    phase_id: str,
    phase_shift: int,
    inception_date: str,
    end_date: str = SAMPLE_END,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build a pure ETF buy-hold sleeve from the shifted inception date."""

    price_g = data.prices[
        (data.prices["etf_code"].eq(sleeve.etf_code))
        & (data.prices["date"] >= pd.Timestamp(inception_date))
        & (data.prices["date"] <= pd.Timestamp(end_date))
    ].sort_values("date")
    if price_g.empty:
        raise ValueError(f"No ETF price rows for {sleeve.sleeve_name} from {inception_date}.")
    nav = price_g["adj_close"].astype(float) / float(price_g["adj_close"].iloc[0])
    returns = nav.pct_change().fillna(0.0)
    daily = pd.DataFrame(
        {
            "date": price_g["date"].values,
            "phase_id": phase_id,
            "phase_shift": phase_shift,
            "inception_date": inception_date,
            "etf_code": sleeve.etf_code,
            "sleeve_name": sleeve.sleeve_name,
            "sleeve_key": sleeve.sleeve_key,
            "is_buyhold": True,
            "strategy_family": "ETF_BuyHold",
            "coverage": 0.0,
            "nav_total": nav.values,
            "daily_return_total": returns.values,
            "daily_return_underlying_component": returns.values,
            "daily_return_option_leg_component": 0.0,
            "option_leg_pnl": 0.0,
            "short_call_liability": 0.0,
            "short_call_mtm_loss": 0.0,
            "active_short_call_flag": False,
            "active_coverage": 0.0,
            "rebalance_date": pd.NaT,
            "period_end_date": pd.NaT,
            "expiry_date": pd.NaT,
            "period_index": np.nan,
            "option_code": np.nan,
            "strike": np.nan,
            "option_price_source": "none",
            "phase_rebuild_method": "buyhold_shifted_window",
        }
    )
    return daily, pd.DataFrame()


def run_covered_call_for_phase(
    data: Ver2DataBundle,
    base_config: ExperimentConfig,
    sleeve: TargetSleeve,
    *,
    phase_id: str,
    phase_shift: int,
    inception_date: str,
    end_date: str = SAMPLE_END,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rebuild one covered-call sleeve by changing the first rebalance date."""

    config = replace(
        base_config,
        etf_codes=(sleeve.etf_code,),
        backtest=replace(
            base_config.backtest,
            start_date=inception_date,
            end_date=end_date,
            initial_nav=INITIAL_NAV,
            execution_mode="continuous_30d",
            roll_frequency="monthly",
            target_dte=30,
            min_days_to_expiry=20,
            max_days_to_expiry=45,
            min_periods=1,
            require_expiry_within_period=False,
            dte_fallback_mode="strict_window",
        ),
        strategies=(
            StrategyConfig(
                name=sleeve.strategy_name,
                kind=sleeve.strategy_kind,
                coverage_ratio=sleeve.coverage,
                target_moneyness=sleeve.target_moneyness,
                enabled=True,
            ),
        ),
    )
    price_g = data.prices[
        (data.prices["etf_code"].eq(sleeve.etf_code))
        & (data.prices["date"] >= pd.Timestamp(inception_date))
        & (data.prices["date"] <= pd.Timestamp(end_date))
    ].sort_values("date")
    if price_g.empty:
        raise ValueError(f"No ETF price rows for {sleeve.sleeve_name} from {inception_date}.")
    if not (price_g["date"] == pd.Timestamp(inception_date)).any():
        raise ValueError(f"Inception date is not an ETF trading date: {inception_date}.")

    strategy = config.enabled_strategies[0]
    periods = pd.DataFrame(
        _continuous_covered_call_rows(
            data=data,
            config=config,
            etf_code=sleeve.etf_code,
            style_bucket=np.nan,
            strategy=strategy,
            price_g=price_g,
            first_rebalance_date=pd.Timestamp(inception_date),
            last_date=pd.Timestamp(price_g["date"].max()),
        )
    )
    if periods.empty:
        raise ValueError(f"No rebuilt option cycles for {sleeve.sleeve_name} phase {phase_id}.")
    daily_mtm = _build_daily_mtm(periods, data.prices, data.options, INITIAL_NAV)
    source = _canonical_daily(daily_mtm, strategy.name)
    daily = _convert_daily(source, sleeve, phase_id, phase_shift, inception_date)
    period = _convert_periods(periods, sleeve, phase_id, phase_shift, inception_date)
    return daily, period


def _canonical_daily(daily_mtm: pd.DataFrame, strategy_name: str) -> pd.DataFrame:
    d = daily_mtm[daily_mtm["strategy_name"].eq(strategy_name)].copy()
    if d.empty:
        raise ValueError(f"No daily MTM rows for rebuilt strategy {strategy_name}.")
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    return d.sort_values(["date", "period_index"]).drop_duplicates("date", keep="last").reset_index(drop=True)


def _convert_daily(
    source: pd.DataFrame,
    sleeve: TargetSleeve,
    phase_id: str,
    phase_shift: int,
    inception_date: str,
) -> pd.DataFrame:
    nav = source["daily_mtm_nav"].astype(float)
    total_return = nav.pct_change().fillna(0.0)
    underlying_nav = source["underlying_price"].astype(float) / float(source["underlying_price"].iloc[0])
    underlying_return = underlying_nav.pct_change().fillna(0.0)
    option_return = total_return - underlying_return
    active = source["position_state"].astype(str).eq("short_call")
    return pd.DataFrame(
        {
            "date": source["date"].values,
            "phase_id": phase_id,
            "phase_shift": phase_shift,
            "inception_date": inception_date,
            "etf_code": sleeve.etf_code,
            "sleeve_name": sleeve.sleeve_name,
            "sleeve_key": sleeve.sleeve_key,
            "is_buyhold": False,
            "strategy_family": sleeve.strategy_family,
            "coverage": sleeve.coverage,
            "nav_total": nav.values,
            "daily_return_total": total_return.values,
            "daily_return_underlying_component": underlying_return.values,
            "daily_return_option_leg_component": option_return.values,
            "option_leg_pnl": option_return.values,
            "short_call_liability": source.get("option_liability_return", 0.0).astype(float).values,
            "short_call_mtm_loss": source.get("short_call_mtm_loss_return", 0.0).astype(float).values,
            "active_short_call_flag": active.values,
            "active_coverage": np.where(active.values, sleeve.coverage, 0.0),
            "rebalance_date": source.get("rebalance_date", pd.NaT).values,
            "period_end_date": source.get("period_end_date", pd.NaT).values,
            "expiry_date": source.get("expiry_date", pd.NaT).values,
            "period_index": source.get("period_index", np.nan).values,
            "option_code": source.get("option_code", np.nan).values,
            "strike": source.get("strike", np.nan).values,
            "option_price_source": source.get("option_price_source", "none").values,
            "phase_rebuild_method": "rebuilt_option_cycles_from_shifted_inception",
        }
    )


def _convert_periods(
    periods: pd.DataFrame,
    sleeve: TargetSleeve,
    phase_id: str,
    phase_shift: int,
    inception_date: str,
) -> pd.DataFrame:
    p = periods.copy()
    p["phase_id"] = phase_id
    p["phase_shift"] = phase_shift
    p["inception_date"] = inception_date
    p["etf_code"] = sleeve.etf_code
    p["sleeve_name"] = sleeve.sleeve_name
    p["sleeve_key"] = sleeve.sleeve_key
    p["strategy_family"] = sleeve.strategy_family
    p["coverage"] = sleeve.coverage
    p["phase_rebuild_method"] = "rebuilt_option_cycles_from_shifted_inception"
    return p
