from __future__ import annotations

"""Run TP80 buyback on the frozen ver4.0 independent-cycle ledger.

TP80 means the first post-entry daily close at or below 20% of the option's
opening price.  It shares the Delta overlay's close proxy, cost model,
minimum remaining DTE, and no-reopen policy so the two rules are comparable.
"""

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_ver4_delta_buyback import (  # noqa: E402
    MIN_REMAINING_DTE,
    ROOT,
    _num,
    _option_cost_yield,
    build_overlay_daily_mtm,
    build_summary,
    load_base_daily_mtm,
    load_base_ledgers,
    load_option_observations,
)
from covered_call_mini_ver4.io import write_csv  # noqa: E402


OUTPUT_ROOT = ROOT / "outputs" / "ver4_2_tp80_buyback"
TP80_REMAINING_PREMIUM = 0.20
TP80_CAPTURE_TARGET = 0.80


def trigger_for_cycle(row: pd.Series, options_by_code: dict[str, pd.DataFrame]) -> dict[str, object] | None:
    option_code = str(row.get("option_code") or "")
    entry = pd.to_datetime(row.get("rebalance_date"), errors="coerce")
    end = pd.to_datetime(row.get("period_end_date"), errors="coerce")
    entry_spot = _num(row, "underlying_price_at_entry", np.nan)
    coverage = _num(row, "coverage", 1.0)
    entry_premium_yield = _num(row, "gross_premium_yield")
    entry_option_price = entry_premium_yield * entry_spot / coverage if coverage > 0 else np.nan
    if not option_code or pd.isna(entry) or pd.isna(end) or not np.isfinite(entry_option_price) or entry_option_price <= 0:
        return None
    observations = options_by_code.get(option_code)
    if observations is None:
        return None
    cycle = observations.loc[
        (observations["trade_date"] > entry)
        & (observations["trade_date"] <= end)
        & (observations["days_to_expiry"] >= MIN_REMAINING_DTE)
        & (observations["close"] > 0)
        & (observations["close"] <= TP80_REMAINING_PREMIUM * entry_option_price)
    ]
    if cycle.empty:
        return None
    hit = cycle.iloc[0]
    liability_yield = coverage * float(hit["close"]) / entry_spot
    return {
        "buyback_triggered": True,
        "buyback_date": pd.Timestamp(hit["trade_date"]).date().isoformat(),
        "buyback_delta": float(hit["model_delta"]) if pd.notna(hit["model_delta"]) else np.nan,
        "buyback_abs_delta": float(hit["model_abs_delta"]) if pd.notna(hit["model_abs_delta"]) else np.nan,
        "buyback_option_price": float(hit["close"]),
        "buyback_remaining_dte": int(hit["days_to_expiry"]),
        "buyback_held_days": int((pd.Timestamp(hit["trade_date"]) - entry).days),
        "buyback_liability_yield": liability_yield,
        "buyback_transaction_cost_yield": _option_cost_yield(liability_yield),
        "buyback_premium_capture": 1.0 - float(hit["close"]) / entry_option_price,
        "buyback_execution": "trigger_day_close_proxy",
    }


def apply_tp80_buyback(ledger: pd.DataFrame, options_by_code: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for _, source in ledger.iterrows():
        row = source.to_dict()
        row["delta_buyback_threshold"] = TP80_CAPTURE_TARGET  # Backward-compatible summary schema.
        row["delta_buyback_label"] = "TP80 (remaining premium <= 20%)"
        row["early_close_rule"] = "tp80"
        row["early_close_parameter"] = TP80_CAPTURE_TARGET
        row["early_close_label"] = "TP80 (remaining premium <= 20%)"
        row["early_close_trigger_metric"] = "premium_capture"
        row["buyback_triggered"] = False
        row["buyback_date"] = None
        row["buyback_delta"] = np.nan
        row["buyback_abs_delta"] = np.nan
        row["buyback_option_price"] = np.nan
        row["buyback_remaining_dte"] = np.nan
        row["buyback_held_days"] = np.nan
        row["buyback_liability_yield"] = 0.0
        row["buyback_transaction_cost_yield"] = 0.0
        row["buyback_premium_capture"] = np.nan
        row["buyback_execution"] = "not_triggered"
        row["baseline_net_option_yield"] = _num(source, "net_option_yield")
        row["baseline_covered_call_period_return"] = _num(source, "covered_call_period_return")
        row["baseline_assignment_flag"] = bool(source.get("assignment_flag", False))
        row["baseline_exercise_or_close_cost_yield"] = _num(source, "exercise_or_close_cost_yield")

        selected = int(_num(source, "selected_option_flag")) == 1
        hit = trigger_for_cycle(source, options_by_code) if selected else None
        if hit:
            row.update(hit)
            gross_premium = _num(source, "gross_premium_yield")
            entry_cost = _num(source, "transaction_cost_yield")
            liability = float(hit["buyback_liability_yield"])
            row["exercise_or_close_cost_yield"] = liability
            row["transaction_cost_yield"] = entry_cost + float(hit["buyback_transaction_cost_yield"])
            row["net_option_yield"] = gross_premium - liability - row["transaction_cost_yield"]
            row["covered_call_period_return"] = _num(source, "etf_period_return") + row["net_option_yield"]
            row["strategy_net_return"] = row["covered_call_period_return"]
            row["relative_to_buyhold_return"] = row["net_option_yield"]
            row["upside_cap_return"] = max(-row["relative_to_buyhold_return"], 0.0)
            row["net_option_yield_ex_upside_cap"] = row["net_option_yield"] + row["upside_cap_return"]
            row["assignment_flag"] = False

        notional = _num(source, "fixed_notional", 100.0)
        row["exercise_or_close_cost_cash"] = -notional * _num(pd.Series(row), "exercise_or_close_cost_yield")
        row["transaction_cost_cash"] = -notional * _num(pd.Series(row), "transaction_cost_yield")
        row["net_option_pnl_cash"] = notional * _num(pd.Series(row), "net_option_yield")
        row["covered_call_pnl_cash"] = notional * _num(pd.Series(row), "covered_call_period_return")
        row["strategy_net_pnl_cash"] = row["covered_call_pnl_cash"]
        row["relative_to_buyhold_pnl_cash"] = notional * _num(pd.Series(row), "relative_to_buyhold_return")
        row["upside_cap_pnl_cash"] = notional * _num(pd.Series(row), "upside_cap_return")
        row["net_option_pnl_cash_ex_upside_cap"] = row["net_option_pnl_cash"] + row["upside_cap_pnl_cash"]
        row["delta_buyback_net_option_change"] = _num(pd.Series(row), "net_option_yield") - _num(source, "net_option_yield")
        row["delta_buyback_strategy_change"] = _num(pd.Series(row), "covered_call_period_return") - _num(source, "covered_call_period_return")
        rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    ledger = apply_tp80_buyback(load_base_ledgers(), load_option_observations())
    summary = build_summary(ledger)
    daily = build_overlay_daily_mtm(ledger, load_base_daily_mtm())
    write_csv(ledger, OUTPUT_ROOT / "ver4_2_tp80_buyback_cycle_ledger.csv")
    write_csv(summary, OUTPUT_ROOT / "ver4_2_tp80_buyback_summary.csv")
    write_csv(daily, OUTPUT_ROOT / "ver4_2_tp80_buyback_cycle_daily_mtm.csv")
    manifest = {
        "experiment_id": "ver4_2_tp80_buyback",
        "baseline_experiment_id": "ver4_0_single_etf_cycle_cashflow",
        "rule": "TP80",
        "trigger": "First post-entry daily close at or below 20% of the entry option price, with remaining DTE >= 5.",
        "execution": "Trigger-day option close used as an end-of-day execution proxy; no intraday or bid/ask data is available.",
        "after_buyback": "The call is not reopened. The ETF remains held until the original cycle end date.",
        "costs": "Entry costs retain the ver4.0 result. Buyback adds 5 bps option slippage plus half of an assumed 5% bid/ask spread, applied to buyback premium yield.",
        "accounting": "Fixed notional independent cycles; prior-cycle P&L is not reinvested.",
    }
    (OUTPUT_ROOT / "ver4_2_tp80_buyback_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote: {OUTPUT_ROOT / 'ver4_2_tp80_buyback_cycle_ledger.csv'}")
    print(f"wrote: {OUTPUT_ROOT / 'ver4_2_tp80_buyback_summary.csv'}")
    print(f"wrote: {OUTPUT_ROOT / 'ver4_2_tp80_buyback_cycle_daily_mtm.csv'}")
    print(f"rows: {len(ledger)}; triggers: {int(ledger['buyback_triggered'].sum())}")


if __name__ == "__main__":
    main()
