from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .config import DiagnosticConfig, ImplementationSpec
from .engine_adapter import run_sleeve_engine


@dataclass(frozen=True)
class SleeveRunOutputs:
    run_status: pd.DataFrame
    option_selection_detail: pd.DataFrame
    daily_returns: pd.DataFrame
    daily_nav: pd.DataFrame
    daily_drawdowns: pd.DataFrame
    raw_daily_mtm: pd.DataFrame
    raw_periods: pd.DataFrame


def run_all_implementations(config: DiagnosticConfig) -> SleeveRunOutputs:
    """Run the pre-registered implementation set once on the main sample."""

    result = run_sleeve_engine(config)
    return build_sleeve_outputs(config, result.periods, result.daily_mtm, phase_shift=0, phase_start=config.sample_start)


def build_sleeve_outputs(
    config: DiagnosticConfig,
    periods: pd.DataFrame,
    daily_mtm: pd.DataFrame,
    *,
    phase_shift: int,
    phase_start: str,
) -> SleeveRunOutputs:
    period_detail = build_option_selection_detail(config, periods, phase_shift=phase_shift, phase_start=phase_start)
    daily = build_daily_paths(config, daily_mtm, phase_shift=phase_shift, phase_start=phase_start)
    run_status = build_run_status(config, period_detail, daily)
    return SleeveRunOutputs(
        run_status=run_status,
        option_selection_detail=period_detail,
        daily_returns=daily[
            [
                "date",
                "etf_code",
                "implementation_name",
                "phase_shift",
                "phase_start",
                "daily_return",
            ]
        ].copy(),
        daily_nav=daily[
            [
                "date",
                "etf_code",
                "implementation_name",
                "phase_shift",
                "phase_start",
                "nav",
            ]
        ].copy(),
        daily_drawdowns=daily[
            [
                "date",
                "etf_code",
                "implementation_name",
                "phase_shift",
                "phase_start",
                "drawdown",
                "max_drawdown_to_date",
            ]
        ].copy(),
        raw_daily_mtm=daily,
        raw_periods=periods.copy(),
    )


def build_option_selection_detail(
    config: DiagnosticConfig,
    periods: pd.DataFrame,
    *,
    phase_shift: int,
    phase_start: str,
) -> pd.DataFrame:
    meta = implementation_lookup(config)
    p = periods[periods["strategy_name"].isin(meta)].copy()
    if p.empty:
        return pd.DataFrame()
    p["etf_code"] = p["etf_code"].astype(str).str.zfill(6)
    p["implementation_name"] = p["strategy_name"].astype(str)
    p["phase_shift"] = int(phase_shift)
    p["phase_start"] = phase_start
    for col in ["rebalance_date", "expiry_date", "period_end_date"]:
        p[col] = pd.to_datetime(p[col], errors="coerce")
    p["target_effective_delta"] = config.target_effective_delta
    p["target_call_delta"] = p["implementation_name"].map(lambda name: meta[name].target_call_delta)
    p["coverage"] = p["implementation_name"].map(lambda name: meta[name].coverage)
    p["expected_overlay_delta"] = p["implementation_name"].map(lambda name: meta[name].expected_overlay_delta)
    p["expected_effective_delta"] = p["implementation_name"].map(lambda name: meta[name].expected_effective_delta)
    p["actual_entry_delta"] = pd.to_numeric(p["selected_delta"], errors="coerce").abs()
    p["actual_effective_delta"] = 1.0 - p["coverage"].astype(float) * p["actual_entry_delta"].astype(float)
    p["option_leg_return"] = pd.to_numeric(p["net_option_contribution"], errors="coerce")
    p["payoff_return"] = pd.to_numeric(p["upside_payoff_return"], errors="coerce")
    p["premium_return"] = pd.to_numeric(p["premium_return"], errors="coerce")
    p["selected_period_flag"] = p["option_selected_flag"].astype(int)
    keep = [
        "etf_code",
        "implementation_name",
        "phase_shift",
        "phase_start",
        "target_effective_delta",
        "target_call_delta",
        "coverage",
        "expected_overlay_delta",
        "expected_effective_delta",
        "actual_entry_delta",
        "actual_effective_delta",
        "period_index",
        "rebalance_date",
        "expiry_date",
        "period_end_date",
        "option_code",
        "option_selected_flag",
        "selection_reason",
        "actual_dte",
        "strike",
        "underlying_price_at_entry",
        "underlying_price_at_expiry",
        "realized_moneyness",
        "selected_iv",
        "premium_return",
        "payoff_return",
        "transaction_cost_return",
        "option_leg_return",
        "etf_period_return",
        "strategy_period_return",
        "assignment_flag",
        "price_source",
        "selection_fallback_flag",
    ]
    return p[keep].sort_values(["etf_code", "implementation_name", "rebalance_date"]).reset_index(drop=True)


def build_daily_paths(
    config: DiagnosticConfig,
    daily_mtm: pd.DataFrame,
    *,
    phase_shift: int,
    phase_start: str,
) -> pd.DataFrame:
    meta = implementation_lookup(config)
    d = daily_mtm[daily_mtm["strategy_name"].isin(meta)].copy()
    if d.empty:
        return pd.DataFrame()
    d["etf_code"] = d["etf_code"].astype(str).str.zfill(6)
    d["implementation_name"] = d["strategy_name"].astype(str)
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d["phase_shift"] = int(phase_shift)
    d["phase_start"] = phase_start
    d["_event_order"] = d["event"].map({"expire_settle": 0, "open_call": 1, "mark_to_market": 2}).fillna(1)
    d = (
        d.sort_values(["etf_code", "implementation_name", "date", "period_index", "_event_order"])
        .drop_duplicates(["etf_code", "implementation_name", "date"], keep="last")
        .copy()
    )
    d["nav"] = pd.to_numeric(d["daily_mtm_nav"], errors="coerce")
    d = d.dropna(subset=["date", "nav"]).copy()
    d["daily_return"] = d.groupby(["etf_code", "implementation_name"])["nav"].pct_change().fillna(0.0)
    d["rolling_peak_nav"] = d.groupby(["etf_code", "implementation_name"])["nav"].cummax()
    d["drawdown"] = d["nav"] / d["rolling_peak_nav"] - 1.0
    d["max_drawdown_to_date"] = d.groupby(["etf_code", "implementation_name"])["drawdown"].cummin().abs()
    return d.sort_values(["etf_code", "implementation_name", "date"]).reset_index(drop=True)


def build_run_status(config: DiagnosticConfig, period_detail: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for etf_code in config.active_etfs:
        for impl in config.implementations:
            p = period_detail[
                period_detail["etf_code"].eq(etf_code) & period_detail["implementation_name"].eq(impl.name)
            ]
            d = daily[daily["etf_code"].eq(etf_code) & daily["implementation_name"].eq(impl.name)]
            selected_periods = int(p["option_selected_flag"].astype(int).sum()) if not p.empty else 0
            rows.append(
                {
                    "etf_code": etf_code,
                    "implementation_name": impl.name,
                    "phase_shift": 0,
                    "run_success": bool(not d.empty and selected_periods > 0),
                    "selected_periods": selected_periods,
                    "skipped_periods": int((p["option_selected_flag"].astype(int) == 0).sum()) if not p.empty else 0,
                    "actual_sample_start": _date_or_blank(d["date"].min()) if not d.empty else "",
                    "actual_sample_end": _date_or_blank(d["date"].max()) if not d.empty else "",
                    "n_daily_rows": int(len(d)),
                    "note": "main sample run",
                }
            )
    return pd.DataFrame(rows)


def implementation_lookup(config: DiagnosticConfig) -> dict[str, ImplementationSpec]:
    return {item.name: item for item in config.implementations}


def _date_or_blank(value: Any) -> str:
    if pd.isna(value):
        return ""
    return pd.Timestamp(value).date().isoformat()
