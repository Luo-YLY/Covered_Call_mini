from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .config import CycleExperimentConfig


def _number(frame: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column not in frame:
        return pd.Series(default, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce").fillna(default).astype(float)


def attach_cycle_market_context(
    ledger: pd.DataFrame,
    *,
    etf_prices: pd.DataFrame,
    option_chain: pd.DataFrame,
    rv_lookback: int = 20,
    trading_days: int = 252,
) -> pd.DataFrame:
    """Add pre-trade IV/RV signals and post-trade volatility attribution to a cycle ledger."""

    context_columns = [
        "entry_iv",
        "entry_rv20",
        "entry_iv_rv20_spread",
        "pre_settlement_iv",
        "pre_settlement_iv_date",
        "holding_realized_vol",
        "ex_post_variance_risk_premium",
        "holding_max_upside_return",
        "holding_max_drawdown_return",
        "holding_range_return",
    ]
    out = ledger.copy().drop(columns=context_columns, errors="ignore")
    if out.empty:
        for column in context_columns:
            out[column] = pd.Series(dtype="float64" if column != "pre_settlement_iv_date" else "datetime64[ns]")
        return out

    out["etf_code"] = out["etf_code"].astype(str).str.zfill(6)
    out["rebalance_date"] = pd.to_datetime(out["rebalance_date"], errors="coerce")
    out["period_end_date"] = pd.to_datetime(out["period_end_date"], errors="coerce")
    out["entry_iv"] = pd.to_numeric(out.get("selected_iv"), errors="coerce")
    net_option_yield = pd.to_numeric(out.get("net_option_yield"), errors="coerce")
    upside_cap_return = pd.to_numeric(out.get("upside_cap_return"), errors="coerce").fillna(0.0)
    net_option_pnl_cash = pd.to_numeric(out.get("net_option_pnl_cash"), errors="coerce")
    upside_cap_pnl_cash = pd.to_numeric(out.get("upside_cap_pnl_cash"), errors="coerce").fillna(0.0)
    out["net_option_yield_ex_upside_cap"] = net_option_yield + upside_cap_return
    out["net_option_pnl_cash_ex_upside_cap"] = net_option_pnl_cash + upside_cap_pnl_cash
    # A client-facing cycle result is the full covered-call outcome, not the option leg alone.
    out["strategy_net_return"] = _number(out, "covered_call_period_return")
    out["strategy_net_pnl_cash"] = _number(out, "covered_call_pnl_cash")

    prices = etf_prices.copy()
    price_column = "adj_close" if "adj_close" in prices.columns else "close"
    required_price_columns = {"date", "etf_code", price_column}
    if required_price_columns.issubset(prices.columns):
        path_columns = [column for column in ("high", "low") if column in prices.columns]
        prices = prices[["date", "etf_code", price_column, *path_columns]].copy()
        prices["date"] = pd.to_datetime(prices["date"], errors="coerce")
        prices["etf_code"] = prices["etf_code"].astype(str).str.zfill(6)
        prices["price"] = pd.to_numeric(prices[price_column], errors="coerce")
        for column in path_columns:
            prices[column] = pd.to_numeric(prices[column], errors="coerce")
        prices = prices.dropna(subset=["date", "price"]).sort_values(["etf_code", "date"])
        prices = prices.drop_duplicates(["etf_code", "date"], keep="last")
        prices["log_return"] = prices.groupby("etf_code")["price"].transform(lambda series: np.log(series).diff())
        prices["entry_rv20"] = prices.groupby("etf_code")["log_return"].transform(
            lambda series: series.rolling(rv_lookback, min_periods=rv_lookback).std(ddof=1).shift(1) * np.sqrt(trading_days)
        )
        out = out.merge(
            prices[["etf_code", "date", "entry_rv20"]],
            left_on=["etf_code", "rebalance_date"],
            right_on=["etf_code", "date"],
            how="left",
        ).drop(columns=["date"], errors="ignore")

        def holding_rv(row: pd.Series) -> float:
            cycle_returns = prices.loc[
                (prices["etf_code"] == row["etf_code"])
                & (prices["date"] > row["rebalance_date"])
                & (prices["date"] <= row["period_end_date"]),
                "log_return",
            ].dropna()
            return float(cycle_returns.std(ddof=1) * np.sqrt(trading_days)) if len(cycle_returns) >= 2 else np.nan

        out["holding_realized_vol"] = out.apply(holding_rv, axis=1)

        if {"high", "low"}.issubset(prices.columns):
            # The strategy is opened at the rebalance-date close.  Intraday highs and
            # lows on that date precede the trade, so the path starts on the next day.
            def holding_path(row: pd.Series) -> pd.Series:
                entry_price = pd.to_numeric(pd.Series([row.get("underlying_price_at_entry")]), errors="coerce").iloc[0]
                if not np.isfinite(entry_price) or entry_price <= 0:
                    return pd.Series([np.nan, np.nan, np.nan])
                cycle_prices = prices.loc[
                    (prices["etf_code"] == row["etf_code"])
                    & (prices["date"] > row["rebalance_date"])
                    & (prices["date"] <= row["period_end_date"]),
                    ["high", "low"],
                ].dropna()
                if cycle_prices.empty:
                    return pd.Series([np.nan, np.nan, np.nan])
                maximum_upside = float(cycle_prices["high"].max() / entry_price - 1.0)
                maximum_drawdown = float(cycle_prices["low"].min() / entry_price - 1.0)
                holding_range = float((cycle_prices["high"].max() - cycle_prices["low"].min()) / entry_price)
                return pd.Series([maximum_upside, maximum_drawdown, holding_range])

            out[["holding_max_upside_return", "holding_max_drawdown_return", "holding_range_return"]] = out.apply(
                holding_path,
                axis=1,
            )
        else:
            out["holding_max_upside_return"] = np.nan
            out["holding_max_drawdown_return"] = np.nan
            out["holding_range_return"] = np.nan
    else:
        out["entry_rv20"] = np.nan
        out["holding_realized_vol"] = np.nan
        out["holding_max_upside_return"] = np.nan
        out["holding_max_drawdown_return"] = np.nan
        out["holding_range_return"] = np.nan

    out["entry_iv_rv20_spread"] = out["entry_iv"] - out["entry_rv20"]
    # Diagnostic only: realized volatility is only known after the cycle closes.
    out["ex_post_variance_risk_premium"] = out["entry_iv"].pow(2) - out["holding_realized_vol"].pow(2)

    option_columns = {"trade_date", "option_code", "model_iv"}
    options = option_chain.copy()
    if option_columns.issubset(options.columns):
        keep = ["trade_date", "option_code", "model_iv"]
        if "days_to_expiry" in options.columns:
            keep.append("days_to_expiry")
        options = options[keep].copy()
        options["trade_date"] = pd.to_datetime(options["trade_date"], errors="coerce")
        options["option_code"] = options["option_code"].astype(str)
        options["model_iv"] = pd.to_numeric(options["model_iv"], errors="coerce")
        if "days_to_expiry" in options.columns:
            options["days_to_expiry"] = pd.to_numeric(options["days_to_expiry"], errors="coerce")
            options = options[options["days_to_expiry"] > 0]
        options = options.dropna(subset=["trade_date", "model_iv"]).sort_values("trade_date")

        def pre_settlement_iv(row: pd.Series) -> pd.Series:
            option_code = row.get("option_code")
            if pd.isna(option_code):
                return pd.Series([np.nan, pd.NaT])
            observations = options.loc[
                (options["option_code"] == str(option_code))
                & (options["trade_date"] >= row["rebalance_date"])
                & (options["trade_date"] <= row["period_end_date"])
            ]
            if observations.empty:
                return pd.Series([np.nan, pd.NaT])
            last = observations.iloc[-1]
            return pd.Series([float(last["model_iv"]), last["trade_date"]])

        out[["pre_settlement_iv", "pre_settlement_iv_date"]] = out.apply(pre_settlement_iv, axis=1)
    else:
        out["pre_settlement_iv"] = np.nan
        out["pre_settlement_iv_date"] = pd.NaT

    return out


def build_cycle_ledger(
    periods: pd.DataFrame,
    strategy_meta: dict[str, dict[str, float | str]],
    config: CycleExperimentConfig,
) -> pd.DataFrame:
    """Convert engine period returns into independently settled fixed-notional cycles."""

    if periods.empty:
        return pd.DataFrame()
    p = periods.copy()
    p["strategy_name"] = p["strategy_name"].astype(str)
    p = p[p["strategy_name"].isin(strategy_meta)].copy()
    p["rebalance_date"] = pd.to_datetime(p["rebalance_date"], errors="coerce")
    p["period_end_date"] = pd.to_datetime(p["period_end_date"], errors="coerce")
    p["expiry_date"] = pd.to_datetime(p.get("expiry_date"), errors="coerce")
    p["etf_code"] = p["etf_code"].astype(str).str.zfill(6)

    p["parameter_role"] = p["strategy_name"].map(lambda value: strategy_meta[value]["parameter_role"])
    p["strategy_label"] = p["strategy_name"].map(lambda value: strategy_meta[value]["strategy_label"])
    p["target_delta"] = p["strategy_name"].map(lambda value: strategy_meta[value]["target_delta"])
    p["coverage"] = p["strategy_name"].map(lambda value: strategy_meta[value]["coverage"])
    p["fixed_notional"] = float(config.fixed_notional)
    p["accounting_mode"] = "fixed_notional_independent_option_cycles"

    p["etf_period_return"] = _number(p, "etf_period_return")
    p["gross_premium_yield"] = _number(p, "premium_return")
    p["exercise_or_close_cost_yield"] = _number(p, "upside_payoff_return")
    p["transaction_cost_yield"] = _number(p, "transaction_cost_return")
    p["net_option_yield"] = (
        p["gross_premium_yield"] - p["exercise_or_close_cost_yield"] - p["transaction_cost_yield"]
    )
    p["covered_call_period_return"] = p["etf_period_return"] + p["net_option_yield"]
    p["strategy_net_return"] = p["covered_call_period_return"]
    p["relative_to_buyhold_return"] = p["covered_call_period_return"] - p["etf_period_return"]
    p["upside_cap_return"] = np.maximum(-p["relative_to_buyhold_return"], 0.0)
    p["net_option_yield_ex_upside_cap"] = p["net_option_yield"] + p["upside_cap_return"]

    p["etf_pnl_cash"] = p["fixed_notional"] * p["etf_period_return"]
    p["gross_premium_cash"] = p["fixed_notional"] * p["gross_premium_yield"]
    p["exercise_or_close_cost_cash"] = -p["fixed_notional"] * p["exercise_or_close_cost_yield"]
    p["transaction_cost_cash"] = -p["fixed_notional"] * p["transaction_cost_yield"]
    p["net_option_pnl_cash"] = p["fixed_notional"] * p["net_option_yield"]
    p["covered_call_pnl_cash"] = p["fixed_notional"] * p["covered_call_period_return"]
    p["strategy_net_pnl_cash"] = p["covered_call_pnl_cash"]
    p["buyhold_pnl_cash"] = p["fixed_notional"] * p["etf_period_return"]
    p["relative_to_buyhold_pnl_cash"] = p["covered_call_pnl_cash"] - p["buyhold_pnl_cash"]
    p["upside_cap_pnl_cash"] = p["fixed_notional"] * p["upside_cap_return"]
    p["net_option_pnl_cash_ex_upside_cap"] = p["net_option_pnl_cash"] + p["upside_cap_pnl_cash"]
    p["period_days"] = (p["period_end_date"] - p["rebalance_date"]).dt.days.astype("Int64")
    p["cycle_id"] = (
        p["etf_code"].astype(str)
        + "__"
        + p["strategy_name"].astype(str)
        + "__"
        + p["period_index"].astype("Int64").astype(str)
    )
    p["cycle_sequence"] = p.groupby(["etf_code", "strategy_name"]).cumcount() + 1
    p["selected_option_flag"] = _number(p, "option_selected_flag").astype(int)
    p["assignment_flag"] = p.get("assignment_flag", False).fillna(False).astype(bool)

    keep = [
        "cycle_id", "cycle_sequence", "accounting_mode", "etf_code", "strategy_name", "strategy_label",
        "parameter_role", "target_delta", "coverage", "fixed_notional", "period_index", "rebalance_date",
        "expiry_date", "period_end_date", "period_days", "option_code", "option_selected_flag",
        "selected_option_flag", "selection_reason", "actual_dte", "strike", "underlying_price_at_entry",
        "underlying_price_at_period_end", "underlying_price_at_expiry", "selected_delta", "selected_iv",
        "assignment_flag", "etf_period_return", "gross_premium_yield", "exercise_or_close_cost_yield",
        "transaction_cost_yield", "net_option_yield", "covered_call_period_return", "strategy_net_return",
        "relative_to_buyhold_return", "upside_cap_return", "net_option_yield_ex_upside_cap",
        "entry_iv", "entry_rv20", "entry_iv_rv20_spread", "pre_settlement_iv", "pre_settlement_iv_date",
        "holding_realized_vol", "ex_post_variance_risk_premium", "etf_pnl_cash", "gross_premium_cash",
        "exercise_or_close_cost_cash", "transaction_cost_cash", "net_option_pnl_cash", "strategy_net_pnl_cash",
        "net_option_pnl_cash_ex_upside_cap", "covered_call_pnl_cash", "buyhold_pnl_cash",
        "relative_to_buyhold_pnl_cash", "upside_cap_pnl_cash",
    ]
    for column in keep:
        if column not in p:
            p[column] = np.nan
    return p[keep].sort_values(["etf_code", "strategy_name", "rebalance_date"]).reset_index(drop=True)


def build_cycle_daily_mtm_ledger(
    daily_mtm: pd.DataFrame,
    strategy_meta: dict[str, dict[str, float | str]],
    config: CycleExperimentConfig,
) -> pd.DataFrame:
    """Rebase daily marks to each cycle's fixed notional, without a stitched NAV."""

    if daily_mtm.empty:
        return pd.DataFrame()
    d = daily_mtm.copy()
    d["strategy_name"] = d["strategy_name"].astype(str)
    d = d[d["strategy_name"].isin(strategy_meta)].copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d["rebalance_date"] = pd.to_datetime(d["rebalance_date"], errors="coerce")
    d["period_end_date"] = pd.to_datetime(d["period_end_date"], errors="coerce")
    d["etf_code"] = d["etf_code"].astype(str).str.zfill(6)
    d["parameter_role"] = d["strategy_name"].map(lambda value: strategy_meta[value]["parameter_role"])
    d["target_delta"] = d["strategy_name"].map(lambda value: strategy_meta[value]["target_delta"])
    d["coverage"] = d["strategy_name"].map(lambda value: strategy_meta[value]["coverage"])
    d["fixed_notional"] = float(config.fixed_notional)
    d["accounting_mode"] = "fixed_notional_within_cycle_mtm_only"
    d["period_mtm_return"] = _number(d, "period_mtm_return")
    d["cycle_mtm_pnl_cash"] = d["fixed_notional"] * d["period_mtm_return"]
    d["cycle_id"] = (
        d["etf_code"].astype(str)
        + "__"
        + d["strategy_name"].astype(str)
        + "__"
        + d["period_index"].astype("Int64").astype(str)
    )
    keep = [
        "cycle_id", "accounting_mode", "date", "etf_code", "strategy_name", "parameter_role",
        "target_delta", "coverage", "period_index", "rebalance_date", "period_end_date", "event",
        "position_state", "underlying_price", "underlying_price_at_entry", "underlying_return_since_entry",
        "option_code", "strike", "coverage_ratio", "option_mark_price", "option_liability_return",
        "short_call_unrealized_pnl_return", "short_call_mtm_loss_return", "premium_return",
        "transaction_cost_return", "period_mtm_return", "fixed_notional", "cycle_mtm_pnl_cash",
    ]
    for column in keep:
        if column not in d:
            d[column] = np.nan
    return d[keep].sort_values(["etf_code", "strategy_name", "period_index", "date"]).reset_index(drop=True)
