from __future__ import annotations

"""Run an isolated Delta-triggered buyback overlay on the frozen ver4.0 ledger.

The base experiment opens one covered call per independent fixed-notional cycle.
This extension does not re-select or reopen options: it only buys back the
already selected call after Delta crosses a threshold, then leaves the ETF
uncovered through that cycle's original end date.
"""

import json
import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
VER4_SRC = ROOT / "ver4" / "src"
for path in (ROOT, VER4_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from covered_call_mini_ver4.io import write_csv  # noqa: E402


BASE_ROOT = ROOT / "outputs" / "ver4_0_single_etf_cycle_cashflow"
OUTPUT_ROOT = ROOT / "outputs" / "ver4_1_delta_buyback"
THRESHOLDS = (0.70, 0.80, 0.90)
MIN_REMAINING_DTE = 5
OPTION_SLIPPAGE_BPS = 5
ASSUMED_BID_ASK_SPREAD_PCT = 0.05


def clean_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    if frame.empty:
        return []
    safe = frame.replace([float("inf"), float("-inf")], pd.NA).where(lambda value: pd.notna(value), None)
    records = safe.to_dict(orient="records")
    for record in records:
        for key, value in list(record.items()):
            if isinstance(value, float) and not math.isfinite(value):
                record[key] = None
    return records


def _num(row: pd.Series, field: str, default: float = 0.0) -> float:
    value = pd.to_numeric(pd.Series([row.get(field)]), errors="coerce").iloc[0]
    return float(value) if pd.notna(value) and np.isfinite(value) else float(default)


def _option_cost_yield(liability_yield: float) -> float:
    """Mirror baseline option slippage plus assumed half-spread on a close proxy."""

    multiplier = OPTION_SLIPPAGE_BPS / 10_000 + 0.5 * ASSUMED_BID_ASK_SPREAD_PCT
    return float(max(liability_yield, 0.0) * multiplier)


def load_option_observations() -> dict[str, pd.DataFrame]:
    columns = [
        "trade_date",
        "option_code",
        "close",
        "model_delta",
        "model_abs_delta",
        "days_to_expiry",
    ]
    options = pd.read_csv(ROOT / "data" / "source" / "delta_enriched_options.csv", usecols=columns)
    options["trade_date"] = pd.to_datetime(options["trade_date"], errors="coerce")
    options["option_code"] = options["option_code"].astype(str)
    for column in columns[2:]:
        options[column] = pd.to_numeric(options[column], errors="coerce")
    options = options.dropna(subset=["trade_date", "option_code"]).sort_values(["option_code", "trade_date"])
    return {str(code): group.reset_index(drop=True) for code, group in options.groupby("option_code", sort=False)}


def trigger_for_cycle(row: pd.Series, options_by_code: dict[str, pd.DataFrame], threshold: float) -> dict[str, object] | None:
    """Return the first observable Delta trigger, using that close as an execution proxy."""

    option_code = str(row.get("option_code") or "")
    entry = pd.to_datetime(row.get("rebalance_date"), errors="coerce")
    end = pd.to_datetime(row.get("period_end_date"), errors="coerce")
    entry_spot = _num(row, "underlying_price_at_entry", np.nan)
    coverage = _num(row, "coverage", 1.0)
    if not option_code or pd.isna(entry) or pd.isna(end) or not np.isfinite(entry_spot) or entry_spot <= 0 or coverage <= 0:
        return None

    observations = options_by_code.get(option_code)
    if observations is None:
        return None
    cycle = observations.loc[
        (observations["trade_date"] > entry)
        & (observations["trade_date"] <= end)
        & (observations["days_to_expiry"] >= MIN_REMAINING_DTE)
        & (observations["close"] > 0)
        & (observations["model_abs_delta"].notna())
        & (observations["model_abs_delta"] >= threshold)
    ]
    if cycle.empty:
        return None
    hit = cycle.iloc[0]
    buyback_liability_yield = coverage * float(hit["close"]) / entry_spot
    return {
        "buyback_triggered": True,
        "buyback_date": pd.Timestamp(hit["trade_date"]).date().isoformat(),
        "buyback_delta": float(hit["model_delta"]),
        "buyback_abs_delta": float(hit["model_abs_delta"]),
        "buyback_option_price": float(hit["close"]),
        "buyback_remaining_dte": int(hit["days_to_expiry"]),
        "buyback_held_days": int((pd.Timestamp(hit["trade_date"]) - entry).days),
        "buyback_liability_yield": buyback_liability_yield,
        "buyback_transaction_cost_yield": _option_cost_yield(buyback_liability_yield),
        "buyback_execution": "trigger_day_close_proxy",
    }


def apply_delta_buyback(ledger: pd.DataFrame, options_by_code: dict[str, pd.DataFrame], threshold: float) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for _, source in ledger.iterrows():
        row = source.to_dict()
        row["delta_buyback_threshold"] = float(threshold)
        row["delta_buyback_label"] = f"Delta >= {threshold:.2f}"
        row["early_close_rule"] = "delta"
        row["early_close_parameter"] = float(threshold)
        row["early_close_label"] = f"Delta >= {threshold:.2f}"
        row["early_close_trigger_metric"] = "absolute_delta"
        row["buyback_triggered"] = False
        row["buyback_date"] = None
        row["buyback_delta"] = np.nan
        row["buyback_abs_delta"] = np.nan
        row["buyback_option_price"] = np.nan
        row["buyback_remaining_dte"] = np.nan
        row["buyback_held_days"] = np.nan
        row["buyback_liability_yield"] = 0.0
        row["buyback_transaction_cost_yield"] = 0.0
        row["buyback_execution"] = "not_triggered"
        row["buyback_premium_capture"] = np.nan
        row["baseline_net_option_yield"] = _num(source, "net_option_yield")
        row["baseline_covered_call_period_return"] = _num(source, "covered_call_period_return")
        row["baseline_assignment_flag"] = bool(source.get("assignment_flag", False))
        row["baseline_exercise_or_close_cost_yield"] = _num(source, "exercise_or_close_cost_yield")

        selected = int(_num(source, "selected_option_flag")) == 1
        hit = trigger_for_cycle(source, options_by_code, threshold) if selected else None
        if hit:
            row.update(hit)
            entry_option_price = _num(source, "gross_premium_yield") * _num(source, "underlying_price_at_entry") / _num(source, "coverage", 1.0)
            row["buyback_premium_capture"] = 1.0 - float(hit["buyback_option_price"]) / entry_option_price if entry_option_price > 0 else np.nan
            gross_premium = _num(source, "gross_premium_yield")
            entry_cost = _num(source, "transaction_cost_yield")
            buyback_cost = float(hit["buyback_transaction_cost_yield"])
            liability = float(hit["buyback_liability_yield"])
            row["exercise_or_close_cost_yield"] = liability
            row["transaction_cost_yield"] = entry_cost + buyback_cost
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


def build_summary(overlay: pd.DataFrame) -> pd.DataFrame:
    if overlay.empty:
        return pd.DataFrame()
    result: list[dict[str, object]] = []
    for (etf_code, strategy_name, threshold), group in overlay.groupby(["etf_code", "strategy_name", "delta_buyback_threshold"], dropna=False):
        selected = group.loc[group["selected_option_flag"].astype(float).eq(1)]
        triggered = selected.loc[selected["buyback_triggered"].astype(bool)]
        result.append(
            {
                "etf_code": str(etf_code).zfill(6),
                "strategy_name": strategy_name,
                "strategy_label": group["strategy_label"].iloc[0],
                "delta_buyback_threshold": float(threshold),
                "delta_buyback_label": group["delta_buyback_label"].iloc[0],
                "early_close_rule": group["early_close_rule"].iloc[0],
                "early_close_parameter": float(group["early_close_parameter"].iloc[0]),
                "early_close_label": group["early_close_label"].iloc[0],
                "cycle_count": int(len(group)),
                "selected_cycle_count": int(len(selected)),
                "buyback_count": int(len(triggered)),
                "buyback_rate": float(len(triggered) / len(selected)) if len(selected) else np.nan,
                "baseline_assignment_count": int(selected["baseline_assignment_flag"].astype(bool).sum()),
                "residual_assignment_count": int(selected["assignment_flag"].astype(bool).sum()),
                "baseline_net_option_yield_sum": float(group["baseline_net_option_yield"].sum()),
                "delta_buyback_net_option_yield_sum": float(group["net_option_yield"].sum()),
                "net_option_yield_change_sum": float(group["delta_buyback_net_option_change"].sum()),
                "baseline_strategy_return_sum": float(group["baseline_covered_call_period_return"].sum()),
                "delta_buyback_strategy_return_sum": float(group["covered_call_period_return"].sum()),
                "strategy_return_change_sum": float(group["delta_buyback_strategy_change"].sum()),
                "baseline_upside_cost_sum": float(group["baseline_exercise_or_close_cost_yield"].sum()),
                "delta_buyback_close_cost_sum": float(group["exercise_or_close_cost_yield"].sum()),
                "added_buyback_cost_sum": float(group["buyback_transaction_cost_yield"].sum()),
                "triggered_cycle_strategy_change_median": float(triggered["delta_buyback_strategy_change"].median()) if len(triggered) else np.nan,
            }
        )
    return pd.DataFrame(result).sort_values(["etf_code", "strategy_name", "delta_buyback_threshold"]).reset_index(drop=True)


def load_base_ledgers() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for etf_dir in sorted(path for path in BASE_ROOT.iterdir() if path.is_dir() and path.name != "dashboard"):
        path = etf_dir / "period" / "ver4_0_cycle_ledger.csv"
        if path.exists():
            frames.append(pd.read_csv(path))
    if not frames:
        raise FileNotFoundError("No ver4.0 cycle ledger was found. Run the baseline experiment first.")
    return pd.concat(frames, ignore_index=True)


def load_base_daily_mtm() -> pd.DataFrame:
    """Load the frozen ver4.0 per-cycle daily marks for all ETFs."""

    frames: list[pd.DataFrame] = []
    for etf_dir in sorted(path for path in BASE_ROOT.iterdir() if path.is_dir() and path.name != "dashboard"):
        path = etf_dir / "daily_mtm" / "ver4_0_cycle_daily_mtm.csv"
        if path.exists():
            frames.append(pd.read_csv(path))
    if not frames:
        raise FileNotFoundError("No ver4.0 daily MTM ledger was found. Run the baseline experiment first.")
    daily = pd.concat(frames, ignore_index=True)
    daily["date"] = pd.to_datetime(daily["date"], errors="coerce")
    return daily


def build_overlay_daily_mtm(overlay_ledger: pd.DataFrame, base_daily: pd.DataFrame) -> pd.DataFrame:
    """Create re-based daily MTM paths for an early-close overlay.

    Before a trigger, the overlay is identical to the original short call. On
    the trigger-day close, the option leg is locked at the buyback result; the
    remaining path is ETF-only plus that locked option P&L.
    """

    if overlay_ledger.empty or base_daily.empty:
        return pd.DataFrame()
    daily_by_cycle = {
        str(cycle_id): group.sort_values("date").copy()
        for cycle_id, group in base_daily.groupby("cycle_id", sort=False)
    }
    fields = [
        "etf_code", "strategy_name", "cycle_id", "rebalance_date", "period_end_date", "date", "cycle_day_index",
        "event", "underlying_price", "underlying_return_since_entry", "option_mark_price", "option_liability_return",
        "premium_return", "transaction_cost_return", "baseline_period_mtm_return", "early_close_period_mtm_return",
        "baseline_option_mtm_yield", "early_close_option_mtm_yield", "buyback_triggered", "buyback_trigger_day",
        "buyback_date", "buyback_abs_delta", "buyback_premium_capture", "buyback_remaining_dte",
        "early_close_rule", "early_close_parameter", "early_close_label",
    ]
    out: list[pd.DataFrame] = []
    for _, row in overlay_ledger.iterrows():
        cycle = daily_by_cycle.get(str(row.get("cycle_id")))
        if cycle is None or cycle.empty:
            continue
        frame = cycle.copy()
        for column in [
            "underlying_return_since_entry", "option_liability_return", "premium_return", "transaction_cost_return", "period_mtm_return"
        ]:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
        frame["baseline_period_mtm_return"] = frame["period_mtm_return"]
        frame["baseline_option_mtm_yield"] = (
            frame["premium_return"] - frame["option_liability_return"] - frame["transaction_cost_return"]
        )
        frame["early_close_option_mtm_yield"] = frame["baseline_option_mtm_yield"]
        frame["buyback_triggered"] = bool(row.get("buyback_triggered", False))
        trigger_date = pd.to_datetime(row.get("buyback_date"), errors="coerce")
        frame["buyback_trigger_day"] = bool(False)

        if bool(row.get("buyback_triggered", False)) and pd.notna(trigger_date):
            locked_option_yield = (
                _num(row, "gross_premium_yield")
                - _num(row, "buyback_liability_yield")
                - _num(row, "transaction_cost_yield")
            )
            after_close = frame["date"] >= trigger_date
            frame.loc[after_close, "early_close_option_mtm_yield"] = locked_option_yield
            frame.loc[frame["date"] == trigger_date, "buyback_trigger_day"] = True

        frame["early_close_period_mtm_return"] = (
            frame["underlying_return_since_entry"] + frame["early_close_option_mtm_yield"]
        )
        frame["cycle_day_index"] = range(len(frame))
        for column in ["early_close_rule", "early_close_parameter", "early_close_label", "buyback_date", "buyback_abs_delta", "buyback_premium_capture", "buyback_remaining_dte"]:
            frame[column] = row.get(column, np.nan)
        for column in fields:
            if column not in frame:
                frame[column] = np.nan
        out.append(frame[fields])
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=fields)


def main() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    options = load_option_observations()
    base = load_base_ledgers()
    overlays = [apply_delta_buyback(base, options, threshold) for threshold in THRESHOLDS]
    ledger = pd.concat(overlays, ignore_index=True)
    summary = build_summary(ledger)
    daily = build_overlay_daily_mtm(ledger, load_base_daily_mtm())
    write_csv(ledger, OUTPUT_ROOT / "ver4_1_delta_buyback_cycle_ledger.csv")
    write_csv(summary, OUTPUT_ROOT / "ver4_1_delta_buyback_summary.csv")
    write_csv(daily, OUTPUT_ROOT / "ver4_1_delta_buyback_cycle_daily_mtm.csv")
    manifest = {
        "experiment_id": "ver4_1_delta_buyback",
        "baseline_experiment_id": "ver4_0_single_etf_cycle_cashflow",
        "thresholds": list(THRESHOLDS),
        "trigger": "First post-entry daily observation with model_abs_delta >= threshold and remaining DTE >= 5.",
        "execution": "Trigger-day option close used as an end-of-day execution proxy; no intraday or bid/ask data is available.",
        "after_buyback": "The call is not reopened. The ETF remains held until the original cycle end date.",
        "costs": "Entry costs retain the ver4.0 result. Buyback adds 5 bps option slippage plus half of an assumed 5% bid/ask spread, applied to buyback premium yield.",
        "accounting": "Fixed notional independent cycles; prior-cycle P&L is not reinvested.",
    }
    (OUTPUT_ROOT / "ver4_1_delta_buyback_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote: {OUTPUT_ROOT / 'ver4_1_delta_buyback_cycle_ledger.csv'}")
    print(f"wrote: {OUTPUT_ROOT / 'ver4_1_delta_buyback_summary.csv'}")
    print(f"wrote: {OUTPUT_ROOT / 'ver4_1_delta_buyback_cycle_daily_mtm.csv'}")
    print(f"rows: {len(ledger)}; triggers: {int(ledger['buyback_triggered'].sum())}")


if __name__ == "__main__":
    main()
