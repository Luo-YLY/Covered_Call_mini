from __future__ import annotations

import json
import math
import secrets
import shutil
import time
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.backtest.custom import CustomBacktestRequest, run_custom_covered_call_backtest
from src.backtest.metrics import summarize_performance
from src.data.etf_submission import MIN_COMPLETE_MONTHLY_PERIODS, summarize_backtest_date_availability
from src.data.validators import validate_etf_prices, validate_options


class DashboardRuntimeError(ValueError):
    """Raised when a local dashboard request is invalid or cannot be completed."""


def _now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _relative(root: Path, path: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, pd.Timestamp):
        if value.hour == value.minute == value.second == value.microsecond == 0:
            return value.date().isoformat()
        return value.isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def _promote_temp_directory(temp_dir: Path, final_dir: Path) -> None:
    """Retry the atomic directory promotion when Windows briefly holds a new file."""

    for attempt in range(5):
        try:
            temp_dir.rename(final_dir)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.08 * (attempt + 1))


def _strategy_identity(
    selection_mode: str,
    target_delta: float,
    otm_pct: float,
    coverage_ratio: float,
) -> tuple[str, str, str]:
    coverage_label = int(round(coverage_ratio * 100))
    if selection_mode == "target_delta":
        depth_code = f"D{int(round(target_delta * 100)):02d}"
        depth_label = f"目标Delta {target_delta:.2f}"
        role = "dynamic_target_delta_coverage"
    elif selection_mode == "atm":
        depth_code = "ATM"
        depth_label = "ATM"
        role = "dynamic_atm_coverage"
    elif selection_mode == "otm_pct":
        depth_code = f"OTM{int(round(otm_pct * 100)):02d}"
        depth_label = f"OTM {otm_pct:.0%}"
        role = "dynamic_otm_coverage"
    else:
        raise DashboardRuntimeError("虚值规则必须是目标Delta、ATM或OTM")
    return (
        f"{depth_code}_Q{coverage_label:03d}",
        f"{depth_label} / 覆盖 {coverage_ratio:.0%}",
        role,
    )


def _build_drawdown(nav: pd.DataFrame) -> pd.DataFrame:
    if nav.empty:
        return pd.DataFrame(columns=["date", "etf_code", "strategy", "nav", "drawdown"])
    out = nav.copy().sort_values(["strategy", "date"])
    out["nav"] = pd.to_numeric(out["nav"], errors="coerce")
    out["drawdown"] = out.groupby("strategy")["nav"].transform(
        lambda values: values / values.cummax() - 1.0
    )
    return out[["date", "etf_code", "strategy", "nav", "drawdown"]]


def _build_cycle_ledger(
    periods: pd.DataFrame,
    prices: pd.DataFrame,
    options: pd.DataFrame,
    *,
    etf_code: str,
    selection_mode: str,
    target_delta: float,
    otm_pct: float,
    coverage_ratio: float,
    fixed_notional: float,
) -> pd.DataFrame:
    """Map the dynamic engine result to the single-ETF evidence ledger."""

    if periods.empty:
        return pd.DataFrame()
    p = periods.copy().sort_values(["strategy", "roll_date"])
    dynamic_name, dynamic_label, dynamic_role = _strategy_identity(
        selection_mode, target_delta, otm_pct, coverage_ratio
    )
    p["strategy_name"] = np.where(p["strategy"].eq("S0_BuyHold"), "BuyHold", dynamic_name)
    p["strategy_label"] = np.where(
        p["strategy"].eq("S0_BuyHold"),
        "ETF BuyHold",
        dynamic_label,
    )
    p["parameter_role"] = np.where(
        p["strategy"].eq("S0_BuyHold"), "buyhold", dynamic_role
    )
    p["rebalance_date"] = pd.to_datetime(p["roll_date"], errors="coerce")
    p["period_end_date"] = pd.to_datetime(p["end_date"], errors="coerce")
    p["expiry_date"] = pd.to_datetime(p.get("option_settlement_date"), errors="coerce")
    p["cycle_sequence"] = p.groupby("strategy_name").cumcount() + 1
    p["period_index"] = p["cycle_sequence"]
    p["cycle_id"] = (
        etf_code + "__" + p["strategy_name"].astype(str) + "__" + p["cycle_sequence"].astype(str)
    )
    p["fixed_notional"] = float(fixed_notional)
    p["target_delta"] = np.where(
        p["parameter_role"].eq(dynamic_role) & (selection_mode == "target_delta"),
        target_delta,
        np.nan,
    )
    p["otm_pct"] = np.where(
        p["parameter_role"].eq(dynamic_role) & (selection_mode == "otm_pct"),
        otm_pct,
        np.nan,
    )
    p["coverage"] = np.where(p["parameter_role"].eq("buyhold"), 0.0, coverage_ratio)
    p["selected_option_flag"] = pd.to_numeric(
        p.get("option_selected_flag", 0), errors="coerce"
    ).fillna(0).astype(int)
    p["gross_premium_yield"] = pd.to_numeric(p.get("premium_contribution"), errors="coerce").fillna(0.0)
    p["exercise_or_close_cost_yield"] = pd.to_numeric(p.get("upside_cost"), errors="coerce").fillna(0.0)
    p["transaction_cost_yield"] = pd.to_numeric(p.get("cost"), errors="coerce").fillna(0.0)
    p["net_option_yield"] = pd.to_numeric(p.get("net_option_contribution"), errors="coerce").fillna(0.0)
    p["covered_call_period_return"] = pd.to_numeric(p.get("R_cc"), errors="coerce").fillna(0.0)
    p["strategy_net_return"] = p["covered_call_period_return"]
    p["etf_period_return"] = pd.to_numeric(p.get("R_etf"), errors="coerce").fillna(0.0)
    p["relative_to_buyhold_return"] = pd.to_numeric(p.get("excess_return"), errors="coerce").fillna(0.0)
    p["upside_cap_return"] = p["exercise_or_close_cost_yield"]
    p["net_option_yield_ex_upside_cap"] = p["net_option_yield"] + p["upside_cap_return"]
    p["etf_pnl_cash"] = fixed_notional * p["etf_period_return"]
    p["gross_premium_cash"] = fixed_notional * p["gross_premium_yield"]
    p["exercise_or_close_cost_cash"] = -fixed_notional * p["exercise_or_close_cost_yield"]
    p["transaction_cost_cash"] = -fixed_notional * p["transaction_cost_yield"]
    p["net_option_pnl_cash"] = fixed_notional * p["net_option_yield"]
    p["covered_call_pnl_cash"] = fixed_notional * p["covered_call_period_return"]
    p["strategy_net_pnl_cash"] = p["covered_call_pnl_cash"]
    p["buyhold_pnl_cash"] = p["etf_pnl_cash"]
    p["relative_to_buyhold_pnl_cash"] = fixed_notional * p["relative_to_buyhold_return"]
    p["upside_cap_pnl_cash"] = fixed_notional * p["upside_cap_return"]
    p["net_option_pnl_cash_ex_upside_cap"] = fixed_notional * p["net_option_yield_ex_upside_cap"]
    p["period_days"] = (p["period_end_date"] - p["rebalance_date"]).dt.days.astype("Int64")
    p["actual_dte"] = pd.to_numeric(p.get("days_to_expiry"), errors="coerce")
    p["strike"] = pd.to_numeric(p.get("K"), errors="coerce")
    p["underlying_price_at_entry"] = pd.to_numeric(p.get("S0"), errors="coerce")
    p["underlying_price_at_period_end"] = pd.to_numeric(p.get("ST"), errors="coerce")
    p["underlying_price_at_expiry"] = p["underlying_price_at_period_end"]
    p["entry_iv"] = pd.to_numeric(p.get("selected_iv"), errors="coerce")

    price_g = prices.copy()
    price_g["date"] = pd.to_datetime(price_g["date"], errors="coerce")
    price_g = price_g[price_g["etf_code"].astype(str).str.zfill(6).eq(etf_code)].copy()
    price_g = price_g.sort_values("date").drop_duplicates("date", keep="last")
    price_g["price"] = pd.to_numeric(
        price_g["adj_close"] if "adj_close" in price_g else price_g["close"], errors="coerce"
    )
    price_g["log_return"] = np.log(price_g["price"]).diff()
    price_g["entry_rv20"] = price_g["log_return"].rolling(20, min_periods=20).std(ddof=1).shift(1) * np.sqrt(252)
    rv_by_date = price_g.set_index("date")["entry_rv20"] if not price_g.empty else pd.Series(dtype=float)

    option_g = options.copy()
    option_g["trade_date"] = pd.to_datetime(option_g["trade_date"], errors="coerce")
    option_g["option_code"] = option_g["option_code"].astype(str)
    option_g["model_iv"] = pd.to_numeric(option_g.get("model_iv"), errors="coerce")

    def context(row: pd.Series) -> pd.Series:
        entry = row["rebalance_date"]
        end = row["period_end_date"]
        path = price_g[price_g["date"].gt(entry) & price_g["date"].le(end)]
        realized = float(path["log_return"].dropna().std(ddof=1) * np.sqrt(252)) if path["log_return"].notna().sum() >= 2 else np.nan
        entry_price = float(row["underlying_price_at_entry"]) if pd.notna(row["underlying_price_at_entry"]) else np.nan
        if np.isfinite(entry_price) and entry_price > 0 and {"high", "low"}.issubset(path.columns) and not path.empty:
            high = pd.to_numeric(path["high"], errors="coerce").max()
            low = pd.to_numeric(path["low"], errors="coerce").min()
            maximum_upside = float(high / entry_price - 1.0) if pd.notna(high) else np.nan
            maximum_drawdown = float(low / entry_price - 1.0) if pd.notna(low) else np.nan
            holding_range = float((high - low) / entry_price) if pd.notna(high) and pd.notna(low) else np.nan
        else:
            maximum_upside = maximum_drawdown = holding_range = np.nan

        code = row.get("option_code")
        observations = option_g[
            option_g["option_code"].eq(str(code))
            & option_g["trade_date"].ge(entry)
            & option_g["trade_date"].le(end)
            & option_g["model_iv"].notna()
        ] if pd.notna(code) else option_g.iloc[0:0]
        if observations.empty:
            pre_iv, pre_iv_date = np.nan, pd.NaT
        else:
            last = observations.sort_values("trade_date").iloc[-1]
            pre_iv, pre_iv_date = float(last["model_iv"]), last["trade_date"]
        return pd.Series(
            [rv_by_date.get(entry, np.nan), realized, maximum_upside, maximum_drawdown, holding_range, pre_iv, pre_iv_date]
        )

    p[[
        "entry_rv20", "holding_realized_vol", "holding_max_upside_return",
        "holding_max_drawdown_return", "holding_range_return", "pre_settlement_iv",
        "pre_settlement_iv_date",
    ]] = p.apply(context, axis=1)
    p["entry_iv_rv20_spread"] = p["entry_iv"] - p["entry_rv20"]
    p["ex_post_variance_risk_premium"] = p["entry_iv"].pow(2) - p["holding_realized_vol"].pow(2)
    p["accounting_mode"] = "fixed_notional_independent_option_cycles"
    p["etf_code"] = etf_code

    keep = [
        "cycle_id", "cycle_sequence", "accounting_mode", "etf_code", "strategy_name",
        "strategy_label", "parameter_role", "target_delta", "otm_pct", "coverage", "fixed_notional",
        "period_index", "rebalance_date", "expiry_date", "period_end_date", "period_days",
        "option_code", "option_selected_flag", "selected_option_flag", "selection_reason",
        "actual_dte", "strike", "underlying_price_at_entry", "underlying_price_at_period_end",
        "underlying_price_at_expiry", "selected_delta", "selected_iv", "assignment_flag",
        "etf_period_return", "gross_premium_yield", "exercise_or_close_cost_yield",
        "transaction_cost_yield", "net_option_yield", "covered_call_period_return",
        "relative_to_buyhold_return", "upside_cap_return", "net_option_yield_ex_upside_cap",
        "etf_pnl_cash", "gross_premium_cash", "exercise_or_close_cost_cash",
        "transaction_cost_cash", "net_option_pnl_cash", "covered_call_pnl_cash",
        "buyhold_pnl_cash", "relative_to_buyhold_pnl_cash", "upside_cap_pnl_cash",
        "net_option_pnl_cash_ex_upside_cap", "strategy_net_return", "strategy_net_pnl_cash",
        "entry_iv", "entry_rv20", "entry_iv_rv20_spread", "pre_settlement_iv",
        "pre_settlement_iv_date", "holding_realized_vol", "ex_post_variance_risk_premium",
        "holding_max_upside_return", "holding_max_drawdown_return", "holding_range_return",
    ]
    for column in keep:
        if column not in p:
            p[column] = np.nan
    return p[keep].sort_values(["strategy_name", "rebalance_date"]).reset_index(drop=True)


def _build_rolling_cashflow(ledger: pd.DataFrame, window: int = 12) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for strategy_name, group in ledger.groupby("strategy_name"):
        group = group.sort_values("rebalance_date").reset_index(drop=True)
        for end_index in range(window - 1, len(group)):
            sample = group.iloc[end_index - window + 1 : end_index + 1]
            first = sample.iloc[0]
            last = sample.iloc[-1]
            net = float(sample["net_option_yield"].sum())
            rows.append(
                {
                    "etf_code": first["etf_code"], "strategy_name": strategy_name,
                    "strategy_label": first["strategy_label"], "parameter_role": first["parameter_role"],
                    "target_delta": first["target_delta"], "coverage": first["coverage"],
                    "window_cycles": window, "window_start": first["rebalance_date"],
                    "window_end": last["period_end_date"], "net_option_yield_non_compound": net,
                    "gross_premium_yield_non_compound": float(sample["gross_premium_yield"].sum()),
                    "covered_call_return_non_compound": float(sample["covered_call_period_return"].sum()),
                    "relative_to_buyhold_return_non_compound": float(sample["relative_to_buyhold_return"].sum()),
                    "net_option_pnl_cash": float(sample["net_option_pnl_cash"].sum()),
                    "upside_cap_pnl_cash": float(sample["upside_cap_pnl_cash"].sum()),
                    "cash_target_02_met": net >= 0.02, "cash_target_04_met": net >= 0.04,
                    "cash_target_06_met": net >= 0.06,
                }
            )
    return pd.DataFrame(rows)


def _build_cycle_summary(
    ledger: pd.DataFrame, rolling: pd.DataFrame, *, sample_start: str, sample_end: str
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    sample_days = max((pd.Timestamp(sample_end) - pd.Timestamp(sample_start)).days, 1)
    for strategy_name, group in ledger.groupby("strategy_name"):
        group = group.sort_values("rebalance_date")
        first = group.iloc[0]
        selected = group[group["selected_option_flag"].eq(1)]
        current_rolling = rolling[rolling["strategy_name"].eq(strategy_name)] if not rolling.empty else rolling
        total_return = float(group["covered_call_period_return"].sum())
        def quantile(column: str, value: float) -> float:
            return float(group[column].quantile(value)) if len(group) else np.nan
        def rolling_quantile(value: float) -> float:
            return float(current_rolling["net_option_yield_non_compound"].quantile(value)) if len(current_rolling) else np.nan
        rows.append(
            {
                "etf_code": first["etf_code"], "strategy_name": strategy_name,
                "strategy_label": first["strategy_label"], "parameter_role": first["parameter_role"],
                "target_delta": first["target_delta"], "coverage": first["coverage"],
                "sample_start": sample_start, "sample_end": sample_end, "sample_days": sample_days,
                "cycle_count": int(len(group)), "selected_option_cycle_count": int(len(selected)),
                "assignment_rate": float(selected["assignment_flag"].mean()) if len(selected) else np.nan,
                "fixed_notional": float(first["fixed_notional"]),
                "gross_premium_cash_total": float(group["gross_premium_cash"].sum()),
                "net_option_pnl_cash_total": float(group["net_option_pnl_cash"].sum()),
                "covered_call_pnl_cash_total": float(group["covered_call_pnl_cash"].sum()),
                "buyhold_pnl_cash_total": float(group["buyhold_pnl_cash"].sum()),
                "relative_to_buyhold_pnl_cash_total": float(group["relative_to_buyhold_pnl_cash"].sum()),
                "non_compound_total_return": total_return,
                "non_compound_annualized_return": total_return * 365.0 / sample_days,
                "non_compound_annualized_net_option_yield": float(group["net_option_yield"].sum()) * 365.0 / sample_days,
                "net_option_yield_mean": float(group["net_option_yield"].mean()),
                "net_option_yield_median": float(group["net_option_yield"].median()),
                "net_option_yield_p10": quantile("net_option_yield", 0.10),
                "net_option_yield_p90": quantile("net_option_yield", 0.90),
                "positive_net_option_cycle_rate": float(group["net_option_yield"].gt(0).mean()),
                "gross_premium_yield_median": float(group["gross_premium_yield"].median()),
                "covered_call_cycle_return_median": float(group["covered_call_period_return"].median()),
                "covered_call_positive_cycle_rate": float(group["covered_call_period_return"].gt(0).mean()),
                "relative_to_buyhold_return_mean": float(group["relative_to_buyhold_return"].mean()),
                "upside_cap_return_mean": float(group["upside_cap_return"].mean()),
                "upside_cap_return_p90": quantile("upside_cap_return", 0.90),
                "upside_cap_cycle_rate": float(group["upside_cap_return"].gt(0).mean()),
                "rolling_window_count": int(len(current_rolling)),
                "rolling_net_option_yield_p10": rolling_quantile(0.10),
                "rolling_net_option_yield_median": rolling_quantile(0.50),
                "rolling_net_option_yield_p90": rolling_quantile(0.90),
                "rolling_cash_target_02_met_rate": float(current_rolling["cash_target_02_met"].mean()) if len(current_rolling) else np.nan,
                "rolling_cash_target_04_met_rate": float(current_rolling["cash_target_04_met"].mean()) if len(current_rolling) else np.nan,
                "rolling_cash_target_06_met_rate": float(current_rolling["cash_target_06_met"].mean()) if len(current_rolling) else np.nan,
            }
        )
    return pd.DataFrame(rows)


def _build_regime_attribution(ledger: pd.DataFrame) -> pd.DataFrame:
    out = ledger.copy()
    out["market_regime"] = pd.cut(
        out["etf_period_return"], [-np.inf, -0.05, 0.05, 0.10, np.inf],
        labels=["下跌周期", "震荡周期", "上涨周期", "强上涨周期"], include_lowest=True,
    )
    rows: list[dict[str, Any]] = []
    for (strategy_name, regime), group in out.groupby(["strategy_name", "market_regime"], observed=True):
        first = group.iloc[0]
        rows.append(
            {
                "etf_code": first["etf_code"], "strategy_name": strategy_name,
                "strategy_label": first["strategy_label"], "parameter_role": first["parameter_role"],
                "target_delta": first["target_delta"], "coverage": first["coverage"],
                "market_regime": str(regime),
                "regime_definition": "ex_post_etf_period_return: <=-5%, -5%~5%, 5%~10%, >=10%",
                "cycle_count": int(len(group)), "etf_period_return_mean": float(group["etf_period_return"].mean()),
                "gross_premium_yield_mean": float(group["gross_premium_yield"].mean()),
                "net_option_yield_mean": float(group["net_option_yield"].mean()),
                "net_option_yield_median": float(group["net_option_yield"].median()),
                "positive_net_option_cycle_rate": float(group["net_option_yield"].gt(0).mean()),
                "relative_to_buyhold_return_mean": float(group["relative_to_buyhold_return"].mean()),
                "underperform_buyhold_cycle_rate": float(group["relative_to_buyhold_return"].lt(0).mean()),
                "upside_cap_return_mean": float(group["upside_cap_return"].mean()),
                "assignment_rate": float(group["assignment_flag"].astype(bool).mean()),
            }
        )
    return pd.DataFrame(rows)


def _early_close_cost(liability_yield: float) -> float:
    return max(float(liability_yield), 0.0) * (0.0005 + 0.5 * 0.05)


def _early_close_trigger(
    source: pd.Series,
    observations: pd.DataFrame,
    *,
    rule: str,
    parameter: float,
) -> pd.Series | None:
    entry = pd.Timestamp(source["rebalance_date"])
    end = pd.Timestamp(source["period_end_date"])
    entry_spot = float(source["underlying_price_at_entry"])
    coverage = float(source["coverage"])
    cycle = observations.loc[
        observations["option_code"].astype(str).eq(str(source.get("option_code") or ""))
        & observations["trade_date"].gt(entry)
        & observations["trade_date"].le(end)
        & observations["days_to_expiry"].ge(5)
        & observations["close"].gt(0)
    ].copy()
    if rule == "delta":
        cycle = cycle.loc[cycle["model_abs_delta"].ge(parameter)]
    else:
        entry_option_price = float(source["gross_premium_yield"]) * entry_spot / coverage if coverage > 0 else np.nan
        cycle = cycle.loc[cycle["close"].le((1.0 - parameter) * entry_option_price)]
    return None if cycle.empty else cycle.sort_values("trade_date").iloc[0]


def _build_early_close_overlay(
    ledger: pd.DataFrame,
    options: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    rule: str,
    parameters: tuple[float, ...],
) -> dict[str, Any]:
    """Build the same close-proxy early-buyback evidence for a dynamic sleeve."""

    base = ledger.loc[ledger["parameter_role"].ne("buyhold")].copy()
    observations = options.copy()
    observations["trade_date"] = pd.to_datetime(observations["trade_date"], errors="coerce")
    observations["days_to_expiry"] = pd.to_numeric(
        observations.get("days_to_expiry", (observations["expiry"] - observations["trade_date"]).dt.days),
        errors="coerce",
    )
    observations["model_abs_delta"] = pd.to_numeric(
        observations.get("model_abs_delta", observations.get("model_delta")), errors="coerce"
    ).abs()
    observations["close"] = pd.to_numeric(observations["close"], errors="coerce")
    price_frame = prices.copy()
    price_frame["date"] = pd.to_datetime(price_frame["date"], errors="coerce")
    price_frame["underlying_price"] = pd.to_numeric(
        price_frame["adj_close"] if "adj_close" in price_frame else price_frame["close"], errors="coerce"
    )

    overlay_rows: list[dict[str, Any]] = []
    daily_rows: list[dict[str, Any]] = []
    for parameter in parameters:
        for _, source in base.iterrows():
            row = source.to_dict()
            row.update(
                {
                    "delta_buyback_threshold": parameter,
                    "delta_buyback_label": f"Delta >= {parameter:.2f}" if rule == "delta" else "TP80 (remaining premium <= 20%)",
                    "early_close_rule": rule,
                    "early_close_parameter": parameter,
                    "early_close_label": f"Delta >= {parameter:.2f}" if rule == "delta" else "TP80 (remaining premium <= 20%)",
                    "early_close_trigger_metric": "absolute_delta" if rule == "delta" else "premium_capture",
                    "buyback_triggered": False,
                    "buyback_date": None,
                    "buyback_delta": np.nan,
                    "buyback_abs_delta": np.nan,
                    "buyback_option_price": np.nan,
                    "buyback_remaining_dte": np.nan,
                    "buyback_held_days": np.nan,
                    "buyback_liability_yield": 0.0,
                    "buyback_transaction_cost_yield": 0.0,
                    "buyback_premium_capture": np.nan,
                    "buyback_execution": "not_triggered",
                    "baseline_net_option_yield": float(source["net_option_yield"]),
                    "baseline_covered_call_period_return": float(source["covered_call_period_return"]),
                    "baseline_assignment_flag": bool(source["assignment_flag"]),
                    "baseline_exercise_or_close_cost_yield": float(source["exercise_or_close_cost_yield"]),
                }
            )
            hit = None
            if int(source["selected_option_flag"]) == 1:
                hit = _early_close_trigger(source, observations, rule=rule, parameter=parameter)
            if hit is not None:
                entry_spot = float(source["underlying_price_at_entry"])
                coverage = float(source["coverage"])
                liability = coverage * float(hit["close"]) / entry_spot
                buyback_cost = _early_close_cost(liability)
                entry_option_price = float(source["gross_premium_yield"]) * entry_spot / coverage if coverage > 0 else np.nan
                row.update(
                    {
                        "buyback_triggered": True,
                        "buyback_date": pd.Timestamp(hit["trade_date"]),
                        "buyback_delta": float(hit.get("model_delta", np.nan)),
                        "buyback_abs_delta": float(hit.get("model_abs_delta", np.nan)),
                        "buyback_option_price": float(hit["close"]),
                        "buyback_remaining_dte": int(hit["days_to_expiry"]),
                        "buyback_held_days": int((pd.Timestamp(hit["trade_date"]) - pd.Timestamp(source["rebalance_date"])).days),
                        "buyback_liability_yield": liability,
                        "buyback_transaction_cost_yield": buyback_cost,
                        "buyback_premium_capture": 1.0 - float(hit["close"]) / entry_option_price if entry_option_price > 0 else np.nan,
                        "buyback_execution": "trigger_day_close_proxy",
                        "exercise_or_close_cost_yield": liability,
                        "transaction_cost_yield": float(source["transaction_cost_yield"]) + buyback_cost,
                        "assignment_flag": False,
                    }
                )
                row["net_option_yield"] = row["gross_premium_yield"] - row["exercise_or_close_cost_yield"] - row["transaction_cost_yield"]
                row["covered_call_period_return"] = row["etf_period_return"] + row["net_option_yield"]
                row["strategy_net_return"] = row["covered_call_period_return"]
                row["relative_to_buyhold_return"] = row["net_option_yield"]
                row["upside_cap_return"] = max(-row["relative_to_buyhold_return"], 0.0)
            notional = float(source["fixed_notional"])
            row["exercise_or_close_cost_cash"] = -notional * float(row["exercise_or_close_cost_yield"])
            row["transaction_cost_cash"] = -notional * float(row["transaction_cost_yield"])
            row["net_option_pnl_cash"] = notional * float(row["net_option_yield"])
            row["covered_call_pnl_cash"] = notional * float(row["covered_call_period_return"])
            row["strategy_net_pnl_cash"] = row["covered_call_pnl_cash"]
            row["relative_to_buyhold_pnl_cash"] = notional * float(row["relative_to_buyhold_return"])
            row["delta_buyback_net_option_change"] = float(row["net_option_yield"]) - float(source["net_option_yield"])
            row["delta_buyback_strategy_change"] = float(row["covered_call_period_return"]) - float(source["covered_call_period_return"])
            overlay_rows.append(row)

            entry = pd.Timestamp(source["rebalance_date"])
            end = pd.Timestamp(source["period_end_date"])
            path = price_frame.loc[price_frame["date"].between(entry, end), ["date", "underlying_price"]].copy()
            option_path = observations.loc[
                observations["option_code"].astype(str).eq(str(source.get("option_code") or ""))
                & observations["trade_date"].between(entry, end),
                ["trade_date", "close"],
            ].drop_duplicates("trade_date", keep="last").set_index("trade_date")["close"]
            if path.empty:
                continue
            path["option_mark_price"] = path["date"].map(option_path).ffill()
            entry_spot = float(source["underlying_price_at_entry"])
            coverage = float(source["coverage"])
            gross = float(source["gross_premium_yield"])
            entry_cost = float(source["transaction_cost_yield"])
            path["underlying_return_since_entry"] = path["underlying_price"] / entry_spot - 1.0
            path["option_liability_return"] = coverage * path["option_mark_price"].fillna(0.0) / entry_spot
            path["premium_return"] = gross
            path["transaction_cost_return"] = entry_cost
            path["baseline_option_mtm_yield"] = gross - path["option_liability_return"] - entry_cost
            path["baseline_period_mtm_return"] = path["underlying_return_since_entry"] + path["baseline_option_mtm_yield"]
            path["early_close_option_mtm_yield"] = path["baseline_option_mtm_yield"]
            trigger_date = pd.to_datetime(row["buyback_date"], errors="coerce")
            path["buyback_trigger_day"] = False
            if pd.notna(trigger_date):
                locked = gross - float(row["buyback_liability_yield"]) - float(row["transaction_cost_yield"])
                path.loc[path["date"].ge(trigger_date), "early_close_option_mtm_yield"] = locked
                path.loc[path["date"].eq(trigger_date), "buyback_trigger_day"] = True
            path["early_close_period_mtm_return"] = path["underlying_return_since_entry"] + path["early_close_option_mtm_yield"]
            path["event"] = np.where(path["date"].eq(entry), "entry", np.where(path["date"].eq(end), "period_end", "mark"))
            for index, daily in path.reset_index(drop=True).iterrows():
                daily_rows.append(
                    {
                        "etf_code": source["etf_code"], "strategy_name": source["strategy_name"],
                        "cycle_id": source["cycle_id"], "rebalance_date": entry, "period_end_date": end,
                        "date": daily["date"], "cycle_day_index": index, "event": daily["event"],
                        "underlying_price": daily["underlying_price"], "underlying_return_since_entry": daily["underlying_return_since_entry"],
                        "option_mark_price": daily["option_mark_price"], "option_liability_return": daily["option_liability_return"],
                        "premium_return": gross, "transaction_cost_return": entry_cost,
                        "baseline_period_mtm_return": daily["baseline_period_mtm_return"],
                        "early_close_period_mtm_return": daily["early_close_period_mtm_return"],
                        "baseline_option_mtm_yield": daily["baseline_option_mtm_yield"],
                        "early_close_option_mtm_yield": daily["early_close_option_mtm_yield"],
                        "buyback_triggered": row["buyback_triggered"], "buyback_trigger_day": daily["buyback_trigger_day"],
                        "buyback_date": row["buyback_date"], "buyback_abs_delta": row["buyback_abs_delta"],
                        "buyback_premium_capture": row["buyback_premium_capture"], "buyback_remaining_dte": row["buyback_remaining_dte"],
                        "early_close_rule": rule, "early_close_parameter": parameter, "early_close_label": row["early_close_label"],
                    }
                )

    overlay = pd.DataFrame(overlay_rows)
    summaries: list[dict[str, Any]] = []
    for (_, strategy_name, parameter), group in overlay.groupby(["etf_code", "strategy_name", "early_close_parameter"]):
        selected = group.loc[group["selected_option_flag"].astype(int).eq(1)]
        triggered = selected.loc[selected["buyback_triggered"].astype(bool)]
        summaries.append(
            {
                "etf_code": str(group["etf_code"].iloc[0]).zfill(6), "strategy_name": strategy_name,
                "strategy_label": group["strategy_label"].iloc[0], "delta_buyback_threshold": parameter,
                "delta_buyback_label": group["delta_buyback_label"].iloc[0], "early_close_rule": rule,
                "early_close_parameter": parameter, "early_close_label": group["early_close_label"].iloc[0],
                "cycle_count": len(group), "selected_cycle_count": len(selected), "buyback_count": len(triggered),
                "buyback_rate": len(triggered) / len(selected) if len(selected) else np.nan,
                "baseline_assignment_count": int(selected["baseline_assignment_flag"].sum()),
                "residual_assignment_count": int(selected["assignment_flag"].sum()),
                "baseline_net_option_yield_sum": float(group["baseline_net_option_yield"].sum()),
                "delta_buyback_net_option_yield_sum": float(group["net_option_yield"].sum()),
                "net_option_yield_change_sum": float(group["delta_buyback_net_option_change"].sum()),
                "baseline_strategy_return_sum": float(group["baseline_covered_call_period_return"].sum()),
                "delta_buyback_strategy_return_sum": float(group["covered_call_period_return"].sum()),
                "strategy_return_change_sum": float(group["delta_buyback_strategy_change"].sum()),
                "baseline_upside_cost_sum": float(group["baseline_exercise_or_close_cost_yield"].sum()),
                "delta_buyback_close_cost_sum": float(group["exercise_or_close_cost_yield"].sum()),
                "added_buyback_cost_sum": float(group["buyback_transaction_cost_yield"].sum()),
            }
        )
    return {
        "manifest": {"rule": rule, "parameters": list(parameters), "execution": "trigger_day_close_proxy", "after_buyback": "no_reopen"},
        "ledger": overlay.to_dict(orient="records"),
        "summary": summaries,
        "daily": daily_rows,
    }


def _resolve_relative_file(root: Path, relative_path: object, allowed_root: Path, filename: str) -> Path:
    text = str(relative_path or "").strip()
    if not text:
        raise DashboardRuntimeError("缺少结果文件路径")
    relative = Path(text.replace("/", "\\"))
    if relative.is_absolute():
        raise DashboardRuntimeError("只允许使用项目内相对路径")
    target = (root / relative).resolve()
    try:
        target.relative_to(allowed_root.resolve())
    except ValueError as exc:
        raise DashboardRuntimeError("文件路径超出允许范围") from exc
    if target.name != filename or not target.is_file():
        raise DashboardRuntimeError(f"找不到有效的 {filename}")
    return target


def load_submission_manifest(project_root: str | Path, manifest_path: object) -> tuple[Path, dict[str, Any]]:
    root = Path(project_root).resolve()
    path = _resolve_relative_file(
        root,
        manifest_path,
        root / "data" / "user_submissions",
        "manifest.json",
    )
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DashboardRuntimeError("ETF数据清单无法读取") from exc
    if not isinstance(manifest, dict) or not manifest.get("etf_code"):
        raise DashboardRuntimeError("ETF数据清单内容不完整")
    return path, manifest


@lru_cache(maxsize=4)
def _builtin_packages_cached(root_text: str, price_stamp: int, option_stamp: int) -> tuple[dict[str, Any], ...]:
    del price_stamp, option_stamp  # cache-key-only values
    root = Path(root_text)
    price_path = root / "data" / "raw" / "etf_prices.csv"
    option_path = root / "data" / "source" / "delta_enriched_options.csv"
    prices = pd.read_csv(price_path, usecols=["date", "etf_code"], dtype={"etf_code": str})
    options = pd.read_csv(option_path, dtype={"underlying_etf": str})
    prices["etf_code"] = prices["etf_code"].astype(str).str.zfill(6)
    options["underlying_etf"] = options["underlying_etf"].astype(str).str.zfill(6)
    prices["date"] = pd.to_datetime(prices["date"], errors="coerce")
    options["trade_date"] = pd.to_datetime(options["trade_date"], errors="coerce")
    codes = sorted(set(prices["etf_code"]).intersection(set(options["underlying_etf"])))
    packages = []
    for code in codes:
        code_prices = prices.loc[prices["etf_code"].eq(code)].copy()
        code_options = options.loc[options["underlying_etf"].eq(code)].copy()
        date_availability = summarize_backtest_date_availability(code_prices, code_options)
        ready = (
            int(date_availability.get("available_monthly_periods", 0)) >= MIN_COMPLETE_MONTHLY_PERIODS
            and int(date_availability.get("selectable_monthly_periods", 0)) >= MIN_COMPLETE_MONTHLY_PERIODS
        )
        if not date_availability["backtest_trade_dates"]:
            continue
        packages.append(
            {
                "etf_code": code,
                "submission_id": f"project-data-{code}",
                "manifest_path": f"builtin:{code}",
                "created_at": datetime.fromtimestamp(max(price_path.stat().st_mtime, option_path.stat().st_mtime)).astimezone().isoformat(timespec="seconds"),
                "ready_for_backtest": ready,
                "sample_start": date_availability["backtest_start"],
                "sample_end": date_availability["backtest_end"],
                "common_trade_dates": date_availability["backtest_trade_dates"],
                "date_availability": date_availability,
                "warnings": [] if ready else [f"完整研究至少需要 {MIN_COMPLETE_MONTHLY_PERIODS} 个可选月度周期"],
            }
        )
    return tuple(packages)


def _builtin_packages(root: Path) -> list[dict[str, Any]]:
    price_path = root / "data" / "raw" / "etf_prices.csv"
    option_path = root / "data" / "source" / "delta_enriched_options.csv"
    if not price_path.is_file() or not option_path.is_file():
        return []
    return [
        dict(item)
        for item in _builtin_packages_cached(
            str(root),
            price_path.stat().st_mtime_ns,
            option_path.stat().st_mtime_ns,
        )
    ]


def list_submission_packages(project_root: str | Path) -> list[dict[str, Any]]:
    root = Path(project_root).resolve()
    submission_root = root / "data" / "user_submissions"
    packages: list[dict[str, Any]] = []
    paths = submission_root.glob("[0-9][0-9][0-9][0-9][0-9][0-9]/*/manifest.json") if submission_root.is_dir() else []
    for path in paths:
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
            readiness = manifest.get("readiness", {})
            date_availability = readiness.get("date_availability")
            if not isinstance(date_availability, dict):
                outputs = manifest.get("outputs", {})
                price_path = _manifest_input(path.parent, outputs.get("etf_prices"))
                option_path = _manifest_input(path.parent, outputs.get("delta_enriched_options"))
                date_availability = summarize_backtest_date_availability(
                    pd.read_csv(price_path, dtype={"etf_code": str}),
                    pd.read_csv(option_path, dtype={"underlying_etf": str}),
                )
            has_full_periods = (
                int(date_availability.get("available_monthly_periods", 0)) >= MIN_COMPLETE_MONTHLY_PERIODS
                and int(date_availability.get("selectable_monthly_periods", 0)) >= MIN_COMPLETE_MONTHLY_PERIODS
            )
            packages.append(
                {
                    "etf_code": str(manifest["etf_code"]).zfill(6),
                    "submission_id": str(manifest.get("submission_id", path.parent.name)),
                    "manifest_path": _relative(root, path),
                    "created_at": manifest.get("created_at"),
                    "ready_for_backtest": bool(readiness.get("ready_for_backtest")) and has_full_periods,
                    "sample_start": date_availability.get("backtest_start") or readiness.get("sample_start"),
                    "sample_end": date_availability.get("backtest_end") or readiness.get("sample_end"),
                    "common_trade_dates": int(
                        date_availability.get("backtest_trade_dates")
                        or readiness.get("common_trade_dates", 0)
                    ),
                    "date_availability": date_availability,
                    "warnings": list(readiness.get("warnings", [])),
                }
            )
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
    user_packages = sorted(packages, key=lambda item: str(item.get("created_at") or item["submission_id"]), reverse=True)
    return user_packages + _builtin_packages(root)


def _manifest_input(package_dir: Path, relative_path: object) -> Path:
    text = str(relative_path or "").strip()
    if not text:
        raise DashboardRuntimeError("ETF数据清单缺少标准化文件路径")
    target = (package_dir / Path(text.replace("/", "\\"))).resolve()
    try:
        target.relative_to(package_dir.resolve())
    except ValueError as exc:
        raise DashboardRuntimeError("ETF数据清单中的文件路径越界") from exc
    if not target.is_file():
        raise DashboardRuntimeError(f"找不到回测输入：{text}")
    return target


def _date_window(manifest: dict[str, Any], payload: dict[str, Any]) -> tuple[str, str]:
    readiness = manifest.get("readiness", {})
    availability = readiness.get("date_availability", {})
    sample_start = pd.Timestamp(availability.get("backtest_start") or readiness.get("sample_start"))
    sample_end = pd.Timestamp(availability.get("backtest_end") or readiness.get("sample_end"))
    try:
        start = pd.Timestamp(payload.get("start_date") or sample_start)
        end = pd.Timestamp(payload.get("end_date") or sample_end)
    except (TypeError, ValueError) as exc:
        raise DashboardRuntimeError("回测日期格式不正确") from exc
    if pd.isna(start) or pd.isna(end):
        raise DashboardRuntimeError("ETF数据清单没有有效的共同样本区间")
    if start < sample_start or end > sample_end:
        raise DashboardRuntimeError(
            f"回测区间必须位于可用期权样本 {sample_start.date().isoformat()} 至 {sample_end.date().isoformat()} 内"
        )
    if start >= end:
        raise DashboardRuntimeError("回测开始日期必须早于结束日期")
    return start.date().isoformat(), end.date().isoformat()


def _float_input(payload: dict[str, Any], name: str, default: float, low: float, high: float) -> float:
    try:
        value = float(payload.get(name, default))
    except (TypeError, ValueError) as exc:
        raise DashboardRuntimeError(f"{name} 不是有效数字") from exc
    if not low <= value <= high:
        raise DashboardRuntimeError(f"{name} 必须位于 {low} 至 {high} 之间")
    return value


def run_submission_backtest(
    project_root: str | Path,
    manifest_path: object,
    payload: dict[str, Any],
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    manifest_ref = str(manifest_path or "").strip()
    manifest_file: Path | None = None
    if manifest_ref.startswith("builtin:"):
        etf_code = manifest_ref.removeprefix("builtin:")
        builtins = {item["etf_code"]: item for item in _builtin_packages(root)}
        package = builtins.get(etf_code)
        if package is None:
            raise DashboardRuntimeError("找不到该ETF的内置数据")
        manifest = {
            "etf_code": etf_code,
            "readiness": package,
        }
        price_path = root / "data" / "raw" / "etf_prices.csv"
        option_path = root / "data" / "source" / "delta_enriched_options.csv"
    else:
        manifest_file, manifest = load_submission_manifest(root, manifest_ref)
        package_dir = manifest_file.parent
        outputs = manifest.get("outputs", {})
        price_path = _manifest_input(package_dir, outputs.get("etf_prices"))
        option_path = _manifest_input(package_dir, outputs.get("delta_enriched_options"))
    readiness = manifest.get("readiness", {})

    selection_mode = str(payload.get("selection_mode", "target_delta")).strip().lower()
    if selection_mode not in {"target_delta", "atm", "otm_pct"}:
        raise DashboardRuntimeError("selection_mode 必须是 target_delta、atm 或 otm_pct")
    target_delta = _float_input(payload, "target_delta", 0.30, 0.01, 0.95)
    otm_pct = _float_input(payload, "otm_pct", 0.05, 0.0, 0.50)
    coverage_ratio = _float_input(payload, "coverage_ratio", 1.0, 0.0, 1.0)
    etf_code = str(manifest["etf_code"]).zfill(6)
    raw_prices = pd.read_csv(price_path, dtype={"etf_code": str})
    raw_options = pd.read_csv(option_path, dtype={"underlying_etf": str})
    raw_prices = raw_prices[raw_prices["etf_code"].astype(str).str.zfill(6).eq(etf_code)].copy()
    raw_options = raw_options[
        raw_options["underlying_etf"].astype(str).str.zfill(6).eq(etf_code)
    ].copy()
    date_availability = summarize_backtest_date_availability(raw_prices, raw_options)
    readiness = {**readiness, "date_availability": date_availability}
    manifest = {**manifest, "readiness": readiness}
    if not readiness.get("ready_for_backtest"):
        raise DashboardRuntimeError("该ETF数据包尚未通过回测可用性检查")
    if (
        int(date_availability.get("available_monthly_periods", 0)) < MIN_COMPLETE_MONTHLY_PERIODS
        or int(date_availability.get("selectable_monthly_periods", 0)) < MIN_COMPLETE_MONTHLY_PERIODS
    ):
        raise DashboardRuntimeError(
            f"完整单ETF研究至少需要 {MIN_COMPLETE_MONTHLY_PERIODS} 个可闭合且可选出期权的月度周期"
        )
    start_date, end_date = _date_window(manifest, payload)
    prices = validate_etf_prices(raw_prices)
    options = validate_options(raw_options, keep_calls_only=True)
    request = CustomBacktestRequest(
        etf_code=etf_code,
        target_delta=target_delta,
        coverage_ratio=coverage_ratio,
        start_date=start_date,
        end_date=end_date,
        roll_frequency="monthly",
        target_dte=30,
        min_days_to_expiry=20,
        max_days_to_expiry=45,
        selection_mode=selection_mode,
        otm_pct=otm_pct,
        min_periods=MIN_COMPLETE_MONTHLY_PERIODS,
    )
    try:
        result = run_custom_covered_call_backtest(prices, options, request)
    except ValueError as exc:
        raise DashboardRuntimeError(str(exc)) from exc

    summary = result["summary"].copy()
    periods = result["periods"].copy()
    nav = result["nav"].copy()
    diagnostics = dict(result["diagnostics"])
    custom_rows = summary[summary["strategy"].ne("S0_BuyHold")]
    if custom_rows.empty:
        raise DashboardRuntimeError("回测没有生成备兑策略结果")

    fixed_notional = 100.0
    drawdown = _build_drawdown(nav)
    cycle_ledger = _build_cycle_ledger(
        periods,
        prices,
        options,
        etf_code=etf_code,
        selection_mode=selection_mode,
        target_delta=target_delta,
        otm_pct=otm_pct,
        coverage_ratio=coverage_ratio,
        fixed_notional=fixed_notional,
    )
    rolling_cashflow = _build_rolling_cashflow(cycle_ledger)
    cycle_summary = _build_cycle_summary(
        cycle_ledger, rolling_cashflow, sample_start=start_date, sample_end=end_date
    )
    regime = _build_regime_attribution(cycle_ledger)
    strategy_name, _, _ = _strategy_identity(
        selection_mode, target_delta, otm_pct, coverage_ratio
    )
    strategy_cycles = cycle_ledger[cycle_ledger["strategy_name"].eq(strategy_name)].copy()
    accounting_error = (
        strategy_cycles["covered_call_period_return"]
        - strategy_cycles["etf_period_return"]
        - strategy_cycles["net_option_yield"]
    ).abs()
    daily_mtm, daily_mtm_quality = _build_submission_daily_mtm(
        periods,
        prices,
        options,
        etf_code=etf_code,
        strategy_name=str(diagnostics.get("strategy_name", "")),
    )
    audit = {
        "status": "passed",
        "minimum_monthly_periods_required": MIN_COMPLETE_MONTHLY_PERIODS,
        "cycle_count": int(len(strategy_cycles)),
        "selected_option_cycles": int(strategy_cycles["selected_option_flag"].sum()),
        "unselected_option_cycles": int((strategy_cycles["selected_option_flag"] == 0).sum()),
        "assignment_cycles": int(strategy_cycles["assignment_flag"].astype(bool).sum()),
        "etf_price_rows": int(len(raw_prices)),
        "option_rows": int(len(raw_options)),
        "date_availability": date_availability,
        "daily_mtm_quality": daily_mtm_quality,
        "max_accounting_identity_error": float(accounting_error.max()) if len(accounting_error) else None,
        "checks": [
            {"check_name": "minimum_monthly_periods", "passed": len(strategy_cycles) >= MIN_COMPLETE_MONTHLY_PERIODS, "detail": f"cycles={len(strategy_cycles)}"},
            {"check_name": "option_selection_nonempty", "passed": bool(strategy_cycles["selected_option_flag"].sum()), "detail": f"selected={int(strategy_cycles['selected_option_flag'].sum())}"},
            {"check_name": "accounting_identity", "passed": bool(len(accounting_error)) and float(accounting_error.max()) <= 1e-10, "detail": f"max_error={float(accounting_error.max()) if len(accounting_error) else float('nan'):.3e}"},
            {"check_name": "daily_mtm_reconciles_to_settlement", "passed": daily_mtm_quality["max_period_end_reconciliation_error"] <= 1e-10, "detail": f"max_error={daily_mtm_quality['max_period_end_reconciliation_error']:.3e}"},
        ],
    }
    if not all(item["passed"] for item in audit["checks"]):
        raise DashboardRuntimeError("完整研究审计未通过，请检查期权覆盖和逐期收益恒等式")

    include_early_close = payload.get("include_early_close", True) not in {False, 0, "0", "false"}
    delta_buyback = (
        _build_early_close_overlay(cycle_ledger, options, prices, rule="delta", parameters=(0.70, 0.80, 0.90))
        if include_early_close else {"manifest": {}, "ledger": [], "summary": [], "daily": []}
    )
    tp80_buyback = (
        _build_early_close_overlay(cycle_ledger, options, prices, rule="tp80", parameters=(0.80,))
        if include_early_close else {"manifest": {}, "ledger": [], "summary": [], "daily": []}
    )
    capabilities = ["cash", "cycles", "postdiag", "tradeoff", "path", "regime", "timing"]
    if include_early_close:
        capabilities.append("earlyclose")
    runtime_warnings = list(result.get("warnings", []))
    if daily_mtm_quality["exact_option_quote_ratio"] < 0.80:
        runtime_warnings.append(
            "日频MTM的期权当日收盘覆盖不足80%，缺失日期沿用最近可得期权收盘价；请结合审计覆盖率解读。"
        )

    cycle_validation = {
        "etf_code": etf_code,
        "generated_at": _now_text(),
        "capabilities": capabilities,
        "manifest": {
            "experiment_id": "dynamic_single_etf_cycle_research",
            "fixed_notional": fixed_notional,
            "etf": {
                "etf_code": etf_code,
                "sample_start": start_date,
                "sample_end": end_date,
                "sample_scope": "user_selected_window",
            },
            "parameters": {
                "selection_mode": selection_mode,
                "target_delta": target_delta,
                "otm_pct": otm_pct,
                "coverage_ratio": coverage_ratio,
                "target_dte": 30,
                "dte_window": [20, 45],
            },
        },
        "summary": cycle_summary.to_dict(orient="records"),
        "ledger": cycle_ledger.to_dict(orient="records"),
        "rolling_cashflow": rolling_cashflow.to_dict(orient="records"),
        "regime": regime.to_dict(orient="records"),
        "validation": audit["checks"],
        "delta_buyback": delta_buyback,
        "tp80_buyback": tp80_buyback,
    }

    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    run_id = f"{stamp}_{secrets.token_hex(4)}"
    run_parent = root / "outputs" / "user_backtests" / etf_code
    final_dir = run_parent / run_id
    temp_dir = run_parent / f".{run_id}.tmp"
    temp_dir.mkdir(parents=True, exist_ok=False)
    try:
        summary.to_csv(temp_dir / "summary.csv", index=False, encoding="utf-8-sig")
        periods.to_csv(temp_dir / "periods.csv", index=False, encoding="utf-8-sig")
        nav.to_csv(temp_dir / "nav.csv", index=False, encoding="utf-8-sig")
        drawdown.to_csv(temp_dir / "drawdown.csv", index=False, encoding="utf-8-sig")
        cycle_ledger.to_csv(temp_dir / "cycle_ledger.csv", index=False, encoding="utf-8-sig")
        daily_mtm.to_csv(temp_dir / "daily_mtm.csv", index=False, encoding="utf-8-sig")
        rolling_cashflow.to_csv(temp_dir / "rolling_12_cycle_cashflow.csv", index=False, encoding="utf-8-sig")
        cycle_summary.to_csv(temp_dir / "cycle_cashflow_summary.csv", index=False, encoding="utf-8-sig")
        regime.to_csv(temp_dir / "cycle_regime_attribution.csv", index=False, encoding="utf-8-sig")
        pd.DataFrame(delta_buyback["ledger"]).to_csv(temp_dir / "delta_buyback_ledger.csv", index=False, encoding="utf-8-sig")
        pd.DataFrame(delta_buyback["summary"]).to_csv(temp_dir / "delta_buyback_summary.csv", index=False, encoding="utf-8-sig")
        pd.DataFrame(delta_buyback["daily"]).to_csv(temp_dir / "delta_buyback_daily.csv", index=False, encoding="utf-8-sig")
        pd.DataFrame(tp80_buyback["ledger"]).to_csv(temp_dir / "tp80_buyback_ledger.csv", index=False, encoding="utf-8-sig")
        pd.DataFrame(tp80_buyback["summary"]).to_csv(temp_dir / "tp80_buyback_summary.csv", index=False, encoding="utf-8-sig")
        pd.DataFrame(tp80_buyback["daily"]).to_csv(temp_dir / "tp80_buyback_daily.csv", index=False, encoding="utf-8-sig")
        _write_json(temp_dir / "research_audit.json", audit)
        preview = {
            "etf_code": etf_code,
            "run_id": run_id,
            "created_at": _now_text(),
            "publication_status": "preview",
            "source_submission": _relative(root, manifest_file) if manifest_file is not None else manifest_ref,
            "sample": {"start": start_date, "end": end_date},
            "parameters": {
                "selection_mode": selection_mode,
                "target_delta": target_delta,
                "otm_pct": otm_pct,
                "coverage_ratio": coverage_ratio,
                "roll_frequency": "monthly",
                "target_dte": 30,
                "dte_window": [20, 45],
                "fixed_notional": fixed_notional,
            },
            "summary": summary.to_dict(orient="records"),
            "nav": nav.to_dict(orient="records"),
            "drawdown": drawdown.to_dict(orient="records"),
            "daily_mtm": daily_mtm.to_dict(orient="records"),
            "cycles": strategy_cycles.to_dict(orient="records"),
            "audit": audit,
            "cycle_validation": cycle_validation,
            "diagnostics": diagnostics,
            "warnings": runtime_warnings,
        }
        run_manifest = {
            "schema_version": "1.0",
            **preview,
            "files": {
                "summary": "summary.csv", "periods": "periods.csv", "nav": "nav.csv",
                "drawdown": "drawdown.csv", "cycle_ledger": "cycle_ledger.csv",
                "daily_mtm": "daily_mtm.csv",
                "rolling_cashflow": "rolling_12_cycle_cashflow.csv",
                "cycle_cashflow_summary": "cycle_cashflow_summary.csv",
                "regime": "cycle_regime_attribution.csv", "audit": "research_audit.json",
                "delta_buyback_ledger": "delta_buyback_ledger.csv",
                "delta_buyback_summary": "delta_buyback_summary.csv",
                "delta_buyback_daily": "delta_buyback_daily.csv",
                "tp80_buyback_ledger": "tp80_buyback_ledger.csv",
                "tp80_buyback_summary": "tp80_buyback_summary.csv",
                "tp80_buyback_daily": "tp80_buyback_daily.csv",
            },
        }
        _write_json(temp_dir / "preview.json", preview)
        _write_json(temp_dir / "run_manifest.json", run_manifest)
        final_dir.parent.mkdir(parents=True, exist_ok=True)
        _promote_temp_directory(temp_dir, final_dir)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    preview["run_manifest_path"] = _relative(root, final_dir / "run_manifest.json")
    preview["preview_path"] = _relative(root, final_dir / "preview.json")
    return _json_safe(preview)


def _build_submission_daily_mtm(
    periods: pd.DataFrame,
    prices: pd.DataFrame,
    options: pd.DataFrame,
    *,
    etf_code: str,
    strategy_name: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build a continuous daily MTM path that reconciles to cycle settlement returns.

    ETF positions use daily adjusted closes. The short call uses its observed daily
    close when available, otherwise the latest prior close. At settlement the mark
    is locked to realized intrinsic value so each cycle ends at the audited return.
    """

    strategy_periods = periods[periods["strategy"].eq(strategy_name)].copy()
    strategy_periods["roll_date"] = pd.to_datetime(strategy_periods["roll_date"], errors="coerce")
    strategy_periods["end_date"] = pd.to_datetime(strategy_periods["end_date"], errors="coerce")
    strategy_periods["option_settlement_date"] = pd.to_datetime(
        strategy_periods["option_settlement_date"], errors="coerce"
    )
    strategy_periods = strategy_periods.sort_values("roll_date").reset_index(drop=True)

    price_rows = prices[prices["etf_code"].astype(str).str.zfill(6).eq(str(etf_code).zfill(6))].copy()
    price_rows["date"] = pd.to_datetime(price_rows["date"], errors="coerce")
    price_rows["adj_close"] = pd.to_numeric(price_rows["adj_close"], errors="coerce")
    price_rows = price_rows.dropna(subset=["date", "adj_close"]).sort_values("date")

    quote_rows = options[["trade_date", "option_code", "close"]].copy()
    quote_rows["trade_date"] = pd.to_datetime(quote_rows["trade_date"], errors="coerce")
    quote_rows["option_code"] = quote_rows["option_code"].astype(str)
    quote_rows["close"] = pd.to_numeric(quote_rows["close"], errors="coerce")
    quote_rows = quote_rows.dropna(subset=["trade_date", "option_code", "close"])
    quote_lookup: dict[str, pd.Series] = {}
    for option_code, group in quote_rows.groupby("option_code"):
        quote_lookup[str(option_code)] = (
            group.sort_values("trade_date")
            .drop_duplicates("trade_date", keep="last")
            .set_index("trade_date")["close"]
        )

    rows: list[dict[str, Any]] = []
    strategy_nav_start = 1.0
    buyhold_nav_start = 1.0
    active_mark_days = 0
    exact_mark_days = 0
    stale_mark_days = 0
    maximum_reconciliation_error = 0.0

    for period_index, period in strategy_periods.iterrows():
        start = pd.Timestamp(period["roll_date"])
        end = pd.Timestamp(period["end_date"])
        period_prices = price_rows[price_rows["date"].between(start, end)].copy()
        if period_prices.empty:
            continue

        entry_spot = float(period["S0"])
        coverage = float(period.get("coverage_ratio", 0.0) or 0.0)
        premium = float(period.get("C0", 0.0) or 0.0)
        premium_yield = float(period.get("premium_yield", 0.0) or 0.0)
        transaction_cost = float(period.get("cost", 0.0) or 0.0)
        realized_liability = float(period.get("upside_cost", 0.0) or 0.0)
        selected = bool(int(period.get("option_selected_flag", 0) or 0))
        option_code = str(period.get("option_code", "")) if selected else ""
        settlement = period.get("option_settlement_date")
        settlement = pd.Timestamp(settlement) if selected and pd.notna(settlement) else end
        quotes = quote_lookup.get(option_code, pd.Series(dtype=float))
        period_key = end.to_period("M").strftime("%Y-%m")
        final_period_return = np.nan

        for price_row in period_prices.itertuples(index=False):
            date = pd.Timestamp(price_row.date)
            spot = float(price_row.adj_close)
            etf_return = spot / entry_spot - 1.0 if entry_spot else np.nan
            exact_quote = False

            if not selected:
                option_mark = 0.0
                option_mark_source = "none"
                option_liability_return = 0.0
                position_state = "no_option"
            elif date >= settlement:
                option_liability_return = realized_liability
                option_mark = realized_liability * entry_spot / coverage if coverage > 0 else 0.0
                option_mark_source = "settlement_intrinsic" if date == settlement else "settled_intrinsic"
                position_state = "settled"
            elif date == start:
                option_mark = premium
                option_mark_source = "entry_close"
                option_liability_return = coverage * option_mark / entry_spot if entry_spot else 0.0
                position_state = "short_call"
            else:
                active_mark_days += 1
                if date in quotes.index:
                    option_mark = float(quotes.loc[date])
                    option_mark_source = "observed_close"
                    exact_quote = True
                    exact_mark_days += 1
                else:
                    previous = quotes.loc[quotes.index < date]
                    if not previous.empty:
                        option_mark = float(previous.iloc[-1])
                        option_mark_source = "previous_close"
                    else:
                        option_mark = premium
                        option_mark_source = "entry_close_fallback"
                    stale_mark_days += 1
                option_liability_return = coverage * option_mark / entry_spot if entry_spot else 0.0
                position_state = "short_call"

            period_mtm_return = (
                etf_return + premium_yield - option_liability_return - transaction_cost
            )
            buyhold_period_return = etf_return
            final_period_return = period_mtm_return
            rows.append(
                {
                    "date": date,
                    "period_key": period_key,
                    "period_index": period_index + 1,
                    "period_start_date": start,
                    "period_end_date": end,
                    "etf_code": str(etf_code).zfill(6),
                    "strategy_name": strategy_name,
                    "underlying_price": spot,
                    "underlying_return_since_entry": etf_return,
                    "option_code": option_code or None,
                    "position_state": position_state,
                    "option_mark_price": option_mark,
                    "option_mark_source": option_mark_source,
                    "exact_option_quote": exact_quote,
                    "option_liability_return": option_liability_return,
                    "premium_yield": premium_yield,
                    "transaction_cost_return": transaction_cost,
                    "period_mtm_return": period_mtm_return,
                    "buyhold_period_return": buyhold_period_return,
                    "daily_mtm_nav": strategy_nav_start * (1.0 + period_mtm_return),
                    "buyhold_daily_nav": buyhold_nav_start * (1.0 + buyhold_period_return),
                }
            )

        target_return = float(period["R_cc"])
        if np.isfinite(final_period_return):
            maximum_reconciliation_error = max(
                maximum_reconciliation_error, abs(float(final_period_return) - target_return)
            )
        strategy_nav_start *= 1.0 + target_return
        buyhold_nav_start *= 1.0 + float(period["R_etf"])

    daily = pd.DataFrame(rows)
    if not daily.empty:
        daily = daily.sort_values(["date", "period_index"]).reset_index(drop=True)
    exact_ratio = exact_mark_days / active_mark_days if active_mark_days else 1.0
    quality = {
        "active_option_mark_days": int(active_mark_days),
        "exact_option_quote_days": int(exact_mark_days),
        "stale_option_quote_days": int(stale_mark_days),
        "exact_option_quote_ratio": float(exact_ratio),
        "max_period_end_reconciliation_error": float(maximum_reconciliation_error),
        "fallback_policy": "latest_prior_option_close_then_entry_close",
    }
    return daily, quality


def _portfolio_performance(returns: pd.Series) -> dict[str, Any]:
    values = pd.to_numeric(returns, errors="coerce").dropna()
    if values.empty:
        return {}
    cumulative = float((1.0 + values).prod() - 1.0)
    annualized = float((1.0 + cumulative) ** (12.0 / len(values)) - 1.0) if cumulative > -1 else np.nan
    volatility = float(values.std(ddof=1) * np.sqrt(12.0)) if len(values) > 1 else np.nan
    nav = (1.0 + values).cumprod()
    drawdown = nav / nav.cummax() - 1.0
    maximum_drawdown = float(drawdown.min())
    return {
        "periods": int(len(values)),
        "cumulative_return": cumulative,
        "annualized_return": annualized,
        "annualized_volatility": volatility,
        "sharpe_ratio": annualized / volatility if np.isfinite(volatility) and volatility > 0 else np.nan,
        "max_drawdown": maximum_drawdown,
        "calmar_ratio": annualized / abs(maximum_drawdown) if maximum_drawdown < 0 else np.nan,
    }


def _daily_portfolio_performance(returns: pd.Series, *, periods: int) -> dict[str, Any]:
    values = pd.to_numeric(returns, errors="coerce").dropna()
    if values.empty:
        return {}
    cumulative = float((1.0 + values).prod() - 1.0)
    annualized = float((1.0 + cumulative) ** (252.0 / len(values)) - 1.0) if cumulative > -1 else np.nan
    volatility = float(values.std(ddof=1) * np.sqrt(252.0)) if len(values) > 1 else np.nan
    sharpe = (
        float(values.mean() / values.std(ddof=1) * np.sqrt(252.0))
        if len(values) > 1 and values.std(ddof=1) > 0
        else np.nan
    )
    nav = (1.0 + values).cumprod()
    drawdown = nav / nav.cummax() - 1.0
    maximum_drawdown = float(drawdown.min())
    return {
        "periods": int(periods),
        "daily_observations": int(len(values)),
        "cumulative_return": cumulative,
        "annualized_return": annualized,
        "annualized_volatility": volatility,
        "sharpe_ratio": sharpe,
        "max_drawdown": maximum_drawdown,
        "calmar_ratio": annualized / abs(maximum_drawdown) if maximum_drawdown < 0 else np.nan,
    }


def run_portfolio_backtest(project_root: str | Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Run monthly-rebalanced ETF sleeves with a reconciled daily MTM portfolio path."""

    root = Path(project_root).resolve()
    raw_legs = payload.get("legs")
    if not isinstance(raw_legs, list) or not 2 <= len(raw_legs) <= 8:
        raise DashboardRuntimeError("自选组合需要选择2至8只ETF")

    legs: list[dict[str, Any]] = []
    codes: set[str] = set()
    for raw in raw_legs:
        if not isinstance(raw, dict):
            raise DashboardRuntimeError("组合策略腿格式不正确")
        code = str(raw.get("etf_code", "")).strip().zfill(6)
        if code in codes:
            raise DashboardRuntimeError(f"组合中ETF {code} 重复")
        codes.add(code)
        weight = _float_input(raw, "weight", 0.0, 0.000001, 1.0)
        mode = str(raw.get("selection_mode", "target_delta")).strip().lower()
        if mode not in {"target_delta", "atm", "otm_pct"}:
            raise DashboardRuntimeError(f"ETF {code} 的虚值规则不正确")
        delta = _float_input(raw, "target_delta", 0.30, 0.01, 0.95)
        otm = _float_input(raw, "otm_pct", 0.05, 0.0, 0.50)
        coverage = _float_input(raw, "coverage_ratio", 1.0, 0.0, 1.0)
        manifest_path = str(raw.get("manifest_path", "")).strip()
        if not manifest_path:
            raise DashboardRuntimeError(f"ETF {code} 缺少数据包")
        strategy_name, strategy_label, _ = _strategy_identity(mode, delta, otm, coverage)
        legs.append(
            {
                "etf_code": code,
                "manifest_path": manifest_path,
                "weight": weight,
                "selection_mode": mode,
                "target_delta": delta,
                "otm_pct": otm,
                "coverage_ratio": coverage,
                "strategy_name": strategy_name,
                "strategy_label": strategy_label,
            }
        )

    weight_sum = sum(item["weight"] for item in legs)
    if not math.isclose(weight_sum, 1.0, abs_tol=1e-6):
        raise DashboardRuntimeError(f"组合权重之和必须为100%，当前为 {weight_sum:.2%}")
    start_date = str(payload.get("start_date", "")).strip()
    end_date = str(payload.get("end_date", "")).strip()
    if not start_date or not end_date:
        raise DashboardRuntimeError("请选择组合回测开始和结束日期")

    sleeve_rows: list[pd.DataFrame] = []
    daily_rows: list[pd.DataFrame] = []
    leg_runs: list[dict[str, Any]] = []
    for leg in legs:
        leg_preview = run_submission_backtest(
            root,
            leg["manifest_path"],
            {
                "start_date": start_date,
                "end_date": end_date,
                "selection_mode": leg["selection_mode"],
                "target_delta": leg["target_delta"],
                "otm_pct": leg["otm_pct"],
                "coverage_ratio": leg["coverage_ratio"],
                "include_early_close": False,
            },
        )
        cycles = pd.DataFrame(leg_preview.get("cycles", []))
        if cycles.empty:
            raise DashboardRuntimeError(f"ETF {leg['etf_code']} 没有生成策略周期")
        cycles["period_end_date"] = pd.to_datetime(cycles["period_end_date"], errors="coerce")
        cycles["period_key"] = cycles["period_end_date"].dt.to_period("M").astype(str)
        cycles["etf_code"] = leg["etf_code"]
        cycles["weight"] = leg["weight"]
        cycles["weighted_strategy_return"] = leg["weight"] * pd.to_numeric(
            cycles["covered_call_period_return"], errors="coerce"
        )
        cycles["weighted_buyhold_return"] = leg["weight"] * pd.to_numeric(
            cycles["etf_period_return"], errors="coerce"
        )
        cycles["weighted_option_contribution"] = leg["weight"] * pd.to_numeric(
            cycles["net_option_yield"], errors="coerce"
        )
        daily_mtm = pd.DataFrame(leg_preview.get("daily_mtm", []))
        if daily_mtm.empty:
            raise DashboardRuntimeError(f"ETF {leg['etf_code']} 没有生成日频MTM路径")
        daily_mtm["date"] = pd.to_datetime(daily_mtm["date"], errors="coerce")
        daily_mtm["etf_code"] = leg["etf_code"]
        daily_mtm["weight"] = leg["weight"]
        daily_mtm["weighted_strategy_period_return"] = leg["weight"] * pd.to_numeric(
            daily_mtm["period_mtm_return"], errors="coerce"
        )
        daily_mtm["weighted_buyhold_period_return"] = leg["weight"] * pd.to_numeric(
            daily_mtm["buyhold_period_return"], errors="coerce"
        )
        daily_rows.append(daily_mtm)
        sleeve_rows.append(cycles)
        mtm_quality = dict(leg_preview.get("audit", {}).get("daily_mtm_quality", {}))
        leg_runs.append(
            {
                **leg,
                "run_manifest_path": leg_preview["run_manifest_path"],
                "cycle_count": int(leg_preview["audit"]["cycle_count"]),
                "selected_option_cycles": int(leg_preview["audit"]["selected_option_cycles"]),
                "daily_mtm_quality": mtm_quality,
            }
        )

    panel = pd.concat(sleeve_rows, ignore_index=True)
    common_keys = (
        panel.groupby("period_key")["etf_code"].nunique().loc[lambda values: values.eq(len(legs))].index
    )
    panel = panel[panel["period_key"].isin(common_keys)].copy()
    if len(common_keys) < MIN_COMPLETE_MONTHLY_PERIODS:
        raise DashboardRuntimeError(
            f"所选ETF与区间只有 {len(common_keys)} 个共同月度周期，至少需要 {MIN_COMPLETE_MONTHLY_PERIODS} 个"
        )

    monthly = (
        panel.groupby("period_key", as_index=False)
        .agg(
            date=("period_end_date", "max"),
            portfolio_return=("weighted_strategy_return", "sum"),
            buyhold_return=("weighted_buyhold_return", "sum"),
            option_contribution=("weighted_option_contribution", "sum"),
            leg_count=("etf_code", "nunique"),
        )
        .sort_values("period_key")
        .reset_index(drop=True)
    )
    monthly["nav"] = (1.0 + monthly["portfolio_return"]).cumprod()
    monthly["buyhold_nav"] = (1.0 + monthly["buyhold_return"]).cumprod()
    monthly["drawdown"] = monthly["nav"] / monthly["nav"].cummax() - 1.0
    monthly["buyhold_drawdown"] = monthly["buyhold_nav"] / monthly["buyhold_nav"].cummax() - 1.0

    daily_panel = pd.concat(daily_rows, ignore_index=True)
    daily_panel = daily_panel[daily_panel["period_key"].isin(common_keys)].copy()
    daily_common = (
        daily_panel.groupby(["period_key", "date"], as_index=False)
        .agg(
            portfolio_period_return=("weighted_strategy_period_return", "sum"),
            buyhold_period_return=("weighted_buyhold_period_return", "sum"),
            leg_count=("etf_code", "nunique"),
        )
        .loc[lambda frame: frame["leg_count"].eq(len(legs))]
        .sort_values(["period_key", "date"])
        .reset_index(drop=True)
    )
    daily_frames: list[pd.DataFrame] = []
    portfolio_nav_start = 1.0
    buyhold_nav_start = 1.0
    maximum_month_end_error = 0.0
    monthly_lookup = monthly.set_index("period_key")
    for period_key in monthly["period_key"]:
        group = daily_common[daily_common["period_key"].eq(period_key)].copy()
        if group.empty:
            raise DashboardRuntimeError(f"共同周期 {period_key} 没有可对齐的日频MTM数据")
        group["nav"] = portfolio_nav_start * (1.0 + group["portfolio_period_return"])
        group["buyhold_nav"] = buyhold_nav_start * (1.0 + group["buyhold_period_return"])
        monthly_row = monthly_lookup.loc[period_key]
        expected_nav = portfolio_nav_start * (1.0 + float(monthly_row["portfolio_return"]))
        expected_buyhold_nav = buyhold_nav_start * (1.0 + float(monthly_row["buyhold_return"]))
        maximum_month_end_error = max(
            maximum_month_end_error,
            abs(float(group.iloc[-1]["nav"]) - expected_nav),
            abs(float(group.iloc[-1]["buyhold_nav"]) - expected_buyhold_nav),
        )
        portfolio_nav_start = expected_nav
        buyhold_nav_start = expected_buyhold_nav
        daily_frames.append(group)

    daily = pd.concat(daily_frames, ignore_index=True).sort_values(["date", "period_key"])
    daily = daily.drop_duplicates("date", keep="last").reset_index(drop=True)
    daily["portfolio_daily_return"] = daily["nav"].pct_change()
    daily["buyhold_daily_return"] = daily["buyhold_nav"].pct_change()
    daily.loc[daily.index[0], "portfolio_daily_return"] = float(daily.loc[daily.index[0], "nav"]) - 1.0
    daily.loc[daily.index[0], "buyhold_daily_return"] = float(daily.loc[daily.index[0], "buyhold_nav"]) - 1.0
    daily["drawdown"] = daily["nav"] / daily["nav"].cummax() - 1.0
    daily["buyhold_drawdown"] = daily["buyhold_nav"] / daily["buyhold_nav"].cummax() - 1.0

    contribution_rows = []
    for leg in legs:
        group = panel[panel["etf_code"].eq(leg["etf_code"])]
        contribution_rows.append(
            {
                **leg,
                "common_periods": int(len(group)),
                "strategy_return_contribution_sum": float(group["weighted_strategy_return"].sum()),
                "buyhold_return_contribution_sum": float(group["weighted_buyhold_return"].sum()),
                "option_contribution_sum": float(group["weighted_option_contribution"].sum()),
            }
        )
    contributions = pd.DataFrame(contribution_rows)
    summary = _daily_portfolio_performance(
        daily["portfolio_daily_return"], periods=len(monthly)
    )
    buyhold_summary = _daily_portfolio_performance(
        daily["buyhold_daily_return"], periods=len(monthly)
    )
    quote_ratios = [
        float(item.get("daily_mtm_quality", {}).get("exact_option_quote_ratio", 0.0))
        for item in leg_runs
    ]
    audit = {
        "status": "passed",
        "accounting_mode": "fixed_weight_monthly_rebalanced_daily_mtm",
        "weight_sum": weight_sum,
        "selected_etf_count": len(legs),
        "common_periods": int(len(monthly)),
        "common_daily_observations": int(len(daily)),
        "minimum_exact_option_quote_ratio": min(quote_ratios) if quote_ratios else None,
        "max_month_end_reconciliation_error": float(maximum_month_end_error),
        "daily_mtm_quote_quality": [
            {
                "etf_code": item["etf_code"],
                **item.get("daily_mtm_quality", {}),
            }
            for item in leg_runs
        ],
        "sample_start": start_date,
        "sample_end": end_date,
        "checks": [
            {"check_name": "weights_sum_to_one", "passed": math.isclose(weight_sum, 1.0, abs_tol=1e-6), "detail": f"weight_sum={weight_sum:.8f}"},
            {"check_name": "minimum_common_periods", "passed": len(monthly) >= MIN_COMPLETE_MONTHLY_PERIODS, "detail": f"periods={len(monthly)}"},
            {"check_name": "all_legs_present", "passed": bool(monthly["leg_count"].eq(len(legs)).all()), "detail": f"legs={len(legs)}"},
            {"check_name": "daily_mtm_all_legs_present", "passed": bool(daily["leg_count"].eq(len(legs)).all()), "detail": f"daily_rows={len(daily)}"},
            {"check_name": "daily_mtm_reconciles_to_monthly_settlement", "passed": maximum_month_end_error <= 1e-10, "detail": f"max_error={maximum_month_end_error:.3e}"},
        ],
    }
    if not all(item["passed"] for item in audit["checks"]):
        raise DashboardRuntimeError("组合日频MTM审计未通过，请检查共同日期和月末结算对账")

    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    run_id = f"{stamp}_{secrets.token_hex(4)}"
    run_parent = root / "outputs" / "user_portfolios"
    final_dir = run_parent / run_id
    temp_dir = run_parent / f".{run_id}.tmp"
    temp_dir.mkdir(parents=True, exist_ok=False)
    try:
        monthly.to_csv(temp_dir / "monthly_returns.csv", index=False, encoding="utf-8-sig")
        daily.to_csv(temp_dir / "daily_mtm.csv", index=False, encoding="utf-8-sig")
        contributions.to_csv(temp_dir / "sleeve_contributions.csv", index=False, encoding="utf-8-sig")
        preview = {
            "portfolio_name": f"自选组合 {run_id[:15]}",
            "run_id": run_id,
            "created_at": _now_text(),
            "publication_status": "preview",
            "sample": {"start": start_date, "end": end_date},
            "accounting_mode": "fixed_weight_monthly_rebalanced_daily_mtm",
            "legs": leg_runs,
            "summary": summary,
            "buyhold_summary": buyhold_summary,
            "monthly": monthly.to_dict(orient="records"),
            "daily_mtm": daily.to_dict(orient="records"),
            "contributions": contributions.to_dict(orient="records"),
            "audit": audit,
        }
        run_manifest = {
            "schema_version": "1.0",
            **preview,
            "files": {
                "monthly_returns": "monthly_returns.csv",
                "daily_mtm": "daily_mtm.csv",
                "sleeve_contributions": "sleeve_contributions.csv",
            },
        }
        _write_json(temp_dir / "preview.json", preview)
        _write_json(temp_dir / "run_manifest.json", run_manifest)
        final_dir.parent.mkdir(parents=True, exist_ok=True)
        _promote_temp_directory(temp_dir, final_dir)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    preview["run_manifest_path"] = _relative(root, final_dir / "run_manifest.json")
    return _json_safe(preview)


def publish_portfolio_result(project_root: str | Path, run_manifest_path: object) -> dict[str, Any]:
    root = Path(project_root).resolve()
    path = _resolve_relative_file(
        root, run_manifest_path, root / "outputs" / "user_portfolios", "run_manifest.json"
    )
    try:
        run = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DashboardRuntimeError("组合回测结果清单无法读取") from exc
    if run.get("publication_status") not in {"preview", "published"}:
        raise DashboardRuntimeError("组合回测结果状态不允许保存")
    run["publication_status"] = "published"
    run["published_at"] = _now_text()
    run["run_manifest_path"] = _relative(root, path)
    _write_json(path, run)
    index_path = root / "outputs" / "user_portfolios" / "published.json"
    published = {
        "schema_version": "1.0",
        "updated_at": run["published_at"],
        "current": run,
    }
    index_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = index_path.with_suffix(".json.tmp")
    _write_json(temp_path, published)
    temp_path.replace(index_path)
    return _json_safe({"ok": True, "published": run, "published_index_path": _relative(root, index_path)})


def load_published_portfolio(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    path = root / "outputs" / "user_portfolios" / "published.json"
    if not path.is_file():
        return {"ok": True, "updated_at": None, "current": None}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DashboardRuntimeError("已保存组合结果无法读取") from exc
    payload["ok"] = True
    return payload


DEFAULT_SURFACE_TARGET_DELTAS = (0.10, 0.20, 0.30, 0.40, 0.50)
DEFAULT_SURFACE_COVERAGES = tuple(value / 10 for value in range(1, 11))
MAX_SURFACE_GRID_POINTS = 100


def _surface_grid_values(
    payload: dict[str, Any],
    name: str,
    default: tuple[float, ...],
    low: float,
    high: float,
) -> list[float]:
    raw = payload.get(name)
    values = list(default) if raw is None else raw
    if not isinstance(values, list):
        raise DashboardRuntimeError(f"{name} 必须是数字数组")
    parsed: list[float] = []
    for item in values:
        try:
            value = float(item)
        except (TypeError, ValueError) as exc:
            raise DashboardRuntimeError(f"{name} 包含无效数字") from exc
        if not low <= value <= high:
            raise DashboardRuntimeError(f"{name} 必须位于 {low} 至 {high} 之间")
        parsed.append(round(value, 6))
    unique = sorted(set(parsed))
    if not unique:
        raise DashboardRuntimeError(f"{name} 不能为空")
    return unique


def _surface_submission_inputs(
    root: Path,
    manifest_path: object,
) -> tuple[str, Path | None, dict[str, Any], str, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    manifest_ref = str(manifest_path or "").strip()
    manifest_file: Path | None = None
    if manifest_ref.startswith("builtin:"):
        etf_code = manifest_ref.removeprefix("builtin:")
        builtins = {item["etf_code"]: item for item in _builtin_packages(root)}
        package = builtins.get(etf_code)
        if package is None:
            raise DashboardRuntimeError("找不到该ETF的内置数据")
        manifest = {"etf_code": etf_code, "readiness": package}
        price_path = root / "data" / "raw" / "etf_prices.csv"
        option_path = root / "data" / "source" / "delta_enriched_options.csv"
    else:
        manifest_file, manifest = load_submission_manifest(root, manifest_ref)
        package_dir = manifest_file.parent
        outputs = manifest.get("outputs", {})
        price_path = _manifest_input(package_dir, outputs.get("etf_prices"))
        option_path = _manifest_input(package_dir, outputs.get("delta_enriched_options"))

    etf_code = str(manifest["etf_code"]).zfill(6)
    raw_prices = pd.read_csv(price_path, dtype={"etf_code": str})
    raw_options = pd.read_csv(option_path, dtype={"underlying_etf": str})
    raw_prices = raw_prices[raw_prices["etf_code"].astype(str).str.zfill(6).eq(etf_code)].copy()
    raw_options = raw_options[
        raw_options["underlying_etf"].astype(str).str.zfill(6).eq(etf_code)
    ].copy()
    date_availability = summarize_backtest_date_availability(raw_prices, raw_options)
    readiness = {**manifest.get("readiness", {}), "date_availability": date_availability}
    manifest = {**manifest, "readiness": readiness}
    if not readiness.get("ready_for_backtest"):
        raise DashboardRuntimeError("该ETF数据包尚未通过回测可用性检查")
    if (
        int(date_availability.get("available_monthly_periods", 0)) < MIN_COMPLETE_MONTHLY_PERIODS
        or int(date_availability.get("selectable_monthly_periods", 0)) < MIN_COMPLETE_MONTHLY_PERIODS
    ):
        raise DashboardRuntimeError(
            f"完整参数图谱至少需要 {MIN_COMPLETE_MONTHLY_PERIODS} 个可闭合且可选出期权的月度周期"
        )
    prices = validate_etf_prices(raw_prices)
    options = validate_options(raw_options, keep_calls_only=True)
    return manifest_ref, manifest_file, manifest, etf_code, prices, options, date_availability


def _surface_point_from_periods(
    periods: pd.DataFrame,
    *,
    etf_code: str,
    target_delta: float,
    coverage: float,
    sample_start: str,
    sample_end: str,
) -> dict[str, Any]:
    buyhold = periods[periods["strategy"].eq("S0_BuyHold")].copy()
    strategy = periods[periods["strategy"].ne("S0_BuyHold")].copy()
    if strategy.empty:
        raise DashboardRuntimeError(f"目标Delta {target_delta:.2f} 没有生成策略周期")
    scaled_columns = [
        "premium_contribution",
        "upside_cost",
        "cost",
        "net_option_contribution",
        "excess_return",
    ]
    for name in scaled_columns:
        strategy[name] = pd.to_numeric(strategy[name], errors="coerce").fillna(0.0) * coverage
    strategy["coverage_ratio"] = pd.to_numeric(
        strategy["coverage_ratio"], errors="coerce"
    ).fillna(0.0) * coverage
    strategy["base_coverage_ratio"] = coverage
    strategy["R_cc"] = pd.to_numeric(strategy["R_etf"], errors="coerce").fillna(0.0) + strategy[
        "net_option_contribution"
    ]
    strategy_name = f"Surface_D{int(round(target_delta * 100)):02d}_Q{int(round(coverage * 100)):03d}"
    strategy["strategy"] = strategy_name
    combined = pd.concat([buyhold, strategy], ignore_index=True, sort=False)
    summary, _ = summarize_performance(combined)
    row = summary[summary["strategy"].eq(strategy_name)]
    if row.empty:
        raise DashboardRuntimeError("参数格点没有生成绩效摘要")
    metric = row.iloc[0]
    period_days = (
        pd.to_datetime(strategy["end_date"], errors="coerce")
        - pd.to_datetime(strategy["roll_date"], errors="coerce")
    ).dt.days.mean()
    annual_factor = 365.0 / period_days if pd.notna(period_days) and period_days > 0 else 12.0
    selected_mask = pd.to_numeric(strategy["option_selected_flag"], errors="coerce").fillna(0).astype(bool)
    assignment = pd.to_numeric(strategy.get("assignment_flag", 0), errors="coerce").fillna(0).astype(bool)
    selected_periods = int(selected_mask.sum())
    assignment_count = int((assignment & selected_mask).sum())
    average_delta = pd.to_numeric(strategy.loc[selected_mask, "selected_delta"], errors="coerce").mean()
    average_moneyness = pd.to_numeric(strategy.loc[selected_mask, "moneyness"], errors="coerce").mean()
    return {
        "surface_point_id": f"dynamic_{etf_code}_D{int(round(target_delta * 100)):02d}_Q{int(round(coverage * 100)):03d}",
        "etf_code": etf_code,
        "sleeve_name": f"{etf_code}_DTE30_D{int(round(target_delta * 100)):02d}_Q{int(round(coverage * 100)):02d}_Hold",
        "parameter_grid_role": "target_delta_surface",
        "sample_scope": "user_selected_window",
        "sample_start": sample_start,
        "sample_end": sample_end,
        "n_trading_days": None,
        "backtest_period": f"{sample_start} to {sample_end}",
        "delta_label": f"D{int(round(target_delta * 100)):02d}",
        "moneyness_label": f"D{int(round(target_delta * 100)):02d}",
        "target_delta": target_delta,
        "target_moneyness": None,
        "moneyness_axis": target_delta,
        "moneyness_depth": target_delta,
        "coverage": coverage,
        "coverage_axis": coverage,
        "coverage_label": f"Q{int(round(coverage * 100)):02d}",
        "parameter_depth": target_delta * coverage,
        "annualized_return_cagr": metric["annualized_return"],
        "annualized_volatility": metric["annualized_volatility"],
        "sharpe_daily_mean": metric["sharpe_ratio"],
        "max_drawdown": abs(float(metric["max_drawdown"])),
        "option_leg_annualized_pnl_contribution": strategy["net_option_contribution"].mean() * annual_factor,
        "monthly_win_rate": float((strategy["R_cc"] > 0).mean()),
        "assignment_rate": assignment_count / selected_periods if selected_periods else None,
        "assignment_count": assignment_count,
        "selected_periods": selected_periods,
        "avg_active_coverage": float(strategy["coverage_ratio"].mean()),
        "avg_selected_delta": average_delta,
        "avg_realized_moneyness": average_moneyness,
        "surface_axis_type": "target_delta",
        "source_group": "动态参数图谱",
        "source_detail": "uploaded-data target-delta x coverage monthly backtest",
        "notes": "由当前数据包与自选区间动态生成",
    }


def run_parameter_surface(
    project_root: str | Path,
    manifest_path: object,
    payload: dict[str, Any],
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    (
        manifest_ref,
        manifest_file,
        manifest,
        etf_code,
        prices,
        options,
        date_availability,
    ) = _surface_submission_inputs(root, manifest_path)
    start_date, end_date = _date_window(manifest, payload)
    target_deltas = _surface_grid_values(
        payload, "target_deltas", DEFAULT_SURFACE_TARGET_DELTAS, 0.01, 0.95
    )
    coverages = _surface_grid_values(
        payload, "coverages", DEFAULT_SURFACE_COVERAGES, 0.01, 1.0
    )
    if len(target_deltas) * len(coverages) > MAX_SURFACE_GRID_POINTS:
        raise DashboardRuntimeError(f"参数图谱最多允许 {MAX_SURFACE_GRID_POINTS} 个格点")

    price_dates = pd.to_datetime(prices["date"], errors="coerce")
    n_trading_days = int(
        price_dates.between(pd.Timestamp(start_date), pd.Timestamp(end_date), inclusive="both").sum()
    )

    grid: list[dict[str, Any]] = []
    buyhold_row: dict[str, Any] | None = None
    selected_by_delta: dict[str, int] = {}
    for target_delta in target_deltas:
        request = CustomBacktestRequest(
            etf_code=etf_code,
            target_delta=target_delta,
            coverage_ratio=1.0,
            start_date=start_date,
            end_date=end_date,
            roll_frequency="monthly",
            target_dte=30,
            min_days_to_expiry=20,
            max_days_to_expiry=45,
            selection_mode="target_delta",
            min_periods=MIN_COMPLETE_MONTHLY_PERIODS,
        )
        try:
            result = run_custom_covered_call_backtest(prices, options, request)
        except ValueError as exc:
            raise DashboardRuntimeError(str(exc)) from exc
        periods = result["periods"].copy()
        selected_by_delta[f"D{int(round(target_delta * 100)):02d}"] = int(
            result["diagnostics"].get("selected_periods", 0)
        )
        if buyhold_row is None:
            summary = result["summary"]
            buyhold = summary[summary["strategy"].eq("S0_BuyHold")]
            if buyhold.empty:
                raise DashboardRuntimeError("参数图谱缺少ETF买入持有基准")
            metric = buyhold.iloc[0]
            buyhold_row = {
                "etf_code": etf_code,
                "sleeve_name": f"{etf_code}_ETF_BuyHold",
                "parameter_grid_role": "buyhold",
                "sample_scope": "user_selected_window",
                "sample_start": start_date,
                "sample_end": end_date,
                "n_trading_days": n_trading_days,
                "backtest_period": f"{start_date} to {end_date}",
                "annualized_return_cagr": metric["annualized_return"],
                "annualized_volatility": metric["annualized_volatility"],
                "sharpe_daily_mean": metric["sharpe_ratio"],
                "max_drawdown": abs(float(metric["max_drawdown"])),
                "option_leg_annualized_pnl_contribution": 0.0,
                "coverage": 0.0,
                "coverage_label": "0%",
                "moneyness_axis": 0.0,
                "moneyness_label": "BuyHold",
                "parameter_depth": 0.0,
                "assignment_count": 0,
                "selected_periods": int(len(periods[periods["strategy"].eq("S0_BuyHold")])),
                "surface_axis_type": "target_delta",
                "source_group": "动态参数图谱",
                "source_detail": "uploaded-data ETF BuyHold baseline",
            }
        for coverage in coverages:
            point = _surface_point_from_periods(
                periods,
                etf_code=etf_code,
                target_delta=target_delta,
                coverage=coverage,
                sample_start=start_date,
                sample_end=end_date,
            )
            point["n_trading_days"] = n_trading_days
            grid.append(point)

    metric_names = (
        "annualized_return_cagr",
        "sharpe_daily_mean",
        "annualized_volatility",
        "max_drawdown",
        "option_leg_annualized_pnl_contribution",
    )
    finite_metrics = all(
        all(value.get(name) is not None and math.isfinite(float(value[name])) for name in metric_names)
        for value in grid
    )
    audit = {
        "status": "passed" if finite_metrics else "failed",
        "grid_points": len(grid),
        "target_delta_count": len(target_deltas),
        "coverage_count": len(coverages),
        "engine_runs": len(target_deltas),
        "selected_option_periods_by_delta": selected_by_delta,
        "date_availability": date_availability,
        "checks": [
            {
                "check_name": "complete_grid",
                "passed": len(grid) == len(target_deltas) * len(coverages),
                "detail": f"grid_points={len(grid)}",
            },
            {
                "check_name": "finite_surface_metrics",
                "passed": finite_metrics,
                "detail": "all five displayed metrics are finite",
            },
            {
                "check_name": "option_selection_nonempty",
                "passed": all(value >= MIN_COMPLETE_MONTHLY_PERIODS for value in selected_by_delta.values()),
                "detail": json.dumps(selected_by_delta, ensure_ascii=False),
            },
        ],
    }
    if not all(item["passed"] for item in audit["checks"]):
        raise DashboardRuntimeError("参数图谱审计未通过，请检查期权覆盖与所选回测区间")

    metadata = {
        "etf_code": etf_code,
        "sample_scope": "user_selected_window",
        "sample_start": start_date,
        "sample_end": end_date,
        "n_trading_days": n_trading_days,
        "backtest_period": f"{start_date} to {end_date}",
        "grid_points": len(grid),
        "available_delta_rules": " / ".join(f"D{int(round(value * 100)):02d}" for value in target_deltas),
        "available_coverages": " / ".join(f"{value:.0%}" for value in coverages),
        "surface_axis_type": "target_delta",
        "backtest_note": "由当前ETF数据包在自选区间内动态生成；曲面和热力图均使用真实回测格点。",
    }
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    run_id = f"{stamp}_{secrets.token_hex(4)}"
    run_parent = root / "outputs" / "user_surfaces" / etf_code
    final_dir = run_parent / run_id
    temp_dir = run_parent / f".{run_id}.tmp"
    temp_dir.mkdir(parents=True, exist_ok=False)
    try:
        pd.DataFrame(grid).to_csv(temp_dir / "surface_grid.csv", index=False, encoding="utf-8-sig")
        pd.DataFrame([buyhold_row]).to_csv(temp_dir / "buyhold.csv", index=False, encoding="utf-8-sig")
        preview = {
            "schema_version": "1.0",
            "etf_code": etf_code,
            "run_id": run_id,
            "created_at": _now_text(),
            "publication_status": "preview",
            "source_submission": _relative(root, manifest_file) if manifest_file is not None else manifest_ref,
            "sample": {"start": start_date, "end": end_date},
            "target_deltas": target_deltas,
            "coverages": coverages,
            "surface_grid": grid,
            "buyhold": buyhold_row,
            "metadata": metadata,
            "audit": audit,
        }
        manifest_payload = {
            **preview,
            "files": {"surface_grid": "surface_grid.csv", "buyhold": "buyhold.csv"},
        }
        _write_json(temp_dir / "surface_manifest.json", manifest_payload)
        _promote_temp_directory(temp_dir, final_dir)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    preview["surface_manifest_path"] = _relative(root, final_dir / "surface_manifest.json")
    return _json_safe(preview)


def publish_parameter_surface(project_root: str | Path, surface_manifest_path: object) -> dict[str, Any]:
    root = Path(project_root).resolve()
    path = _resolve_relative_file(
        root,
        surface_manifest_path,
        root / "outputs" / "user_surfaces",
        "surface_manifest.json",
    )
    try:
        surface = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DashboardRuntimeError("参数图谱结果清单无法读取") from exc
    if surface.get("publication_status") not in {"preview", "published"}:
        raise DashboardRuntimeError("参数图谱结果状态不允许发布")
    published_at = _now_text()
    surface["publication_status"] = "published"
    surface["published_at"] = published_at
    surface["surface_manifest_path"] = _relative(root, path)
    _write_json(path, surface)

    index_path = root / "outputs" / "user_surfaces" / "published.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.is_file() else {}
    except (OSError, json.JSONDecodeError):
        index = {}
    latest_by_etf = index.get("latest_by_etf", {})
    if not isinstance(latest_by_etf, dict):
        latest_by_etf = {}
    etf_code = str(surface.get("etf_code", "")).zfill(6)
    latest_by_etf[etf_code] = surface
    published = {
        "schema_version": "1.0",
        "updated_at": published_at,
        "current_etf": etf_code,
        "current": surface,
        "latest_by_etf": latest_by_etf,
    }
    index_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = index_path.with_suffix(".json.tmp")
    _write_json(temp_path, published)
    temp_path.replace(index_path)
    return _json_safe(
        {"ok": True, "published": surface, "published_index_path": _relative(root, index_path)}
    )


def load_published_surfaces(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    path = root / "outputs" / "user_surfaces" / "published.json"
    if not path.is_file():
        return {"ok": True, "updated_at": None, "current": None, "latest_by_etf": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DashboardRuntimeError("已发布参数图谱索引无法读取") from exc
    payload["ok"] = True
    return payload


def publish_backtest_result(project_root: str | Path, run_manifest_path: object) -> dict[str, Any]:
    root = Path(project_root).resolve()
    path = _resolve_relative_file(
        root,
        run_manifest_path,
        root / "outputs" / "user_backtests",
        "run_manifest.json",
    )
    try:
        run = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DashboardRuntimeError("回测结果清单无法读取") from exc
    if run.get("publication_status") not in {"preview", "published"}:
        raise DashboardRuntimeError("回测结果状态不允许发布")

    published_at = _now_text()
    run["publication_status"] = "published"
    run["published_at"] = published_at
    run["run_manifest_path"] = _relative(root, path)
    _write_json(path, run)

    index_path = root / "outputs" / "user_backtests" / "published.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.is_file() else {}
    except (OSError, json.JSONDecodeError):
        index = {}
    latest_by_etf = index.get("latest_by_etf", {})
    if not isinstance(latest_by_etf, dict):
        latest_by_etf = {}
    etf_code = str(run.get("etf_code", "")).zfill(6)
    latest_by_etf[etf_code] = run
    published = {
        "schema_version": "1.0",
        "updated_at": published_at,
        "current_etf": etf_code,
        "current": run,
        "latest_by_etf": latest_by_etf,
    }
    index_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = index_path.with_suffix(".json.tmp")
    _write_json(temp_path, published)
    temp_path.replace(index_path)
    return _json_safe({"ok": True, "published": run, "published_index_path": _relative(root, index_path)})


def load_published_results(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    path = root / "outputs" / "user_backtests" / "published.json"
    if not path.is_file():
        return {"ok": True, "updated_at": None, "current": None, "latest_by_etf": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DashboardRuntimeError("已发布回测索引无法读取") from exc
    payload["ok"] = True
    return payload
