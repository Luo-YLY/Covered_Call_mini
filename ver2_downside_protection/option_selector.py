from __future__ import annotations

import pandas as pd

from src.options.selection import OptionSelectionResult, select_option

from ver2_downside_protection.config import BacktestConfig, StrategyConfig


_CHAIN_CACHE: dict[tuple[int, int, tuple[str, ...], pd.Timestamp, str], pd.DataFrame] = {}


def _chain_for_rebalance_date(options: pd.DataFrame, trade_date: pd.Timestamp, etf_code: str) -> pd.DataFrame:
    """Return the call chain visible on one rebalance date.

    The cache is keyed by the in-memory DataFrame id plus date/ETF. It does not
    change selection logic; it only avoids scanning the full option table once
    per strategy when several strategies rebalance on the same date.
    """

    normalized_trade_date = pd.Timestamp(trade_date)
    normalized_etf = str(etf_code).zfill(6)
    key = (id(options), len(options), tuple(map(str, options.columns)), normalized_trade_date, normalized_etf)
    if key not in _CHAIN_CACHE:
        _CHAIN_CACHE[key] = options[
            (options["trade_date"] == normalized_trade_date)
            & (options["underlying_etf"].astype(str) == normalized_etf)
            & (options["option_type"].astype(str).str.upper() == "C")
        ].copy()
    return _CHAIN_CACHE[key]


def select_ver2_option(
    options: pd.DataFrame,
    trade_date: pd.Timestamp,
    etf_code: str,
    spot: float,
    period_end: pd.Timestamp,
    strategy: StrategyConfig,
    backtest: BacktestConfig,
    liquidity_filters: dict,
) -> OptionSelectionResult:
    """Select a call option using only the rebalance-date chain.

    This is a thin wrapper over ver1's select_option(). It keeps ATM and OTM5
    behavior aligned with the existing implementation. In continuous_30d mode,
    period_end is the available backtest end date rather than the next month-end.
    """

    if strategy.kind == "buy_hold":
        return OptionSelectionResult(False, "buy_hold")
    if strategy.kind == "atm":
        strategy_kind = "atm"
    elif strategy.kind in {"otm_pct", "itm_pct"}:
        strategy_kind = "otm_pct"
    elif strategy.kind in {"target_delta", "delta"}:
        strategy_kind = "target_delta"
    else:
        raise ValueError(f"Unsupported ver2 strategy kind: {strategy.kind}")

    if backtest.execution_mode == "continuous_30d":
        max_expiry_date = period_end
    else:
        max_expiry_date = period_end if backtest.require_expiry_within_period else None
    chain = _chain_for_rebalance_date(options, trade_date, etf_code)
    return select_option(
        options=chain,
        trade_date=pd.Timestamp(trade_date),
        underlying_etf=str(etf_code).zfill(6),
        spot=spot,
        strategy_kind=strategy_kind,
        target_dte=backtest.target_dte,
        min_days_to_expiry=backtest.min_days_to_expiry,
        max_days_to_expiry=backtest.max_days_to_expiry,
        liquidity_filters=liquidity_filters,
        otm_pct=strategy.target_moneyness,
        target_delta=abs(strategy.target_moneyness),
        max_expiry_date=max_expiry_date,
        dte_fallback_mode=backtest.dte_fallback_mode,
    )
