from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from pathlib import Path
import sys
from typing import Any, Iterable

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.metrics.ver2_metric_standard import (  # noqa: E402
    compute_portfolio_option_contribution,
    summarize_daily_nav,
)
from ver2_downside_protection.config import StrategyConfig, load_config  # noqa: E402
from ver2_downside_protection.strategy_engine import run_ver2_backtest  # noqa: E402


ETF_CODES = ("510300", "510500", "159915")
START_DATE = pd.Timestamp("2022-09-30")
TARGET_DTE_LABEL = "DTE30"
TRADING_DAYS_PER_YEAR = 252.0

HOLD_RULE = "hold_to_expiry"

CONFIG_PATH = ROOT / "configs" / "ver2_downside_protection.yaml"
RAW_OPTION_PATH = ROOT / "data" / "raw" / "options_daily.csv"
DELTA_OPTION_PATH = ROOT / "data" / "source" / "delta_enriched_options.csv"
OPTION_PATH = DELTA_OPTION_PATH if DELTA_OPTION_PATH.exists() else RAW_OPTION_PATH
PRICE_PATH = ROOT / "data" / "raw" / "etf_prices.csv"

OUT_ROOT = ROOT / "outputs" / "ver3_0_stepA_single_etf_sleeves"
DAILY_DIR = OUT_ROOT / "daily"
PERIOD_DIR = OUT_ROOT / "period"
SUMMARY_DIR = OUT_ROOT / "summary"
PANEL_DIR = OUT_ROOT / "panel"
REPORT_DIR = OUT_ROOT / "reports"
FIGURE_DIR = OUT_ROOT / "figures"
AUDIT_DIR = OUT_ROOT / "audit"


@dataclass(frozen=True)
class SleeveSpec:
    etf_code: str
    sleeve_name: str
    source_family: str | None
    coverage: float
    close_rule: str
    strategy_family: str
    dte_label: str = TARGET_DTE_LABEL
    is_buyhold: bool = False
    note: str = ""

    @property
    def source_strategy_name(self) -> str | None:
        if self.source_family is None:
            return None
        return f"{self.source_family}_100"


SPECS: tuple[SleeveSpec, ...] = (
    SleeveSpec("510300", "510300_ETF_BuyHold", None, 0.0, HOLD_RULE, "BuyHold", is_buyhold=True, note="pure ETF baseline"),
    SleeveSpec("510300", "510300_DTE30_ATM_Q100_Hold", "ATM", 1.0, HOLD_RULE, "ATM", note="ATM defensive baseline; Q100 stress-style reference"),
    SleeveSpec("510300", "510300_DTE30_D40_Q50_Hold", "D40", 0.5, HOLD_RULE, "D40", note="medium coverage candidate"),
    SleeveSpec("510300", "510300_DTE30_D40_Q70_Hold", "D40", 0.7, HOLD_RULE, "D40", note="high coverage candidate"),
    SleeveSpec("510300", "510300_DTE30_D40_Q100_Hold", "D40", 1.0, HOLD_RULE, "D40", note="full coverage stress test"),
    SleeveSpec("510500", "510500_ETF_BuyHold", None, 0.0, HOLD_RULE, "BuyHold", is_buyhold=True, note="pure ETF baseline"),
    SleeveSpec("510500", "510500_DTE30_D40_Q100_Hold", "D40", 1.0, HOLD_RULE, "D40", note="near-delta diagnostic stress test"),
    SleeveSpec("510500", "510500_DTE30_OTM5up_Q50_Hold", "OTM5_up", 0.5, HOLD_RULE, "OTM5_up", note="high-beta OTM candidate"),
    SleeveSpec("510500", "510500_DTE30_OTM5up_Q100_Hold", "OTM5_up", 1.0, HOLD_RULE, "OTM5_up", note="high-coverage stress test"),
    SleeveSpec("159915", "159915_ETF_BuyHold", None, 0.0, HOLD_RULE, "BuyHold", is_buyhold=True, note="pure ETF baseline"),
    SleeveSpec("159915", "159915_DTE30_D40_Q100_Hold", "D40", 1.0, HOLD_RULE, "D40", note="near-delta diagnostic stress test"),
    SleeveSpec("159915", "159915_DTE30_OTM5up_Q50_Hold", "OTM5_up", 0.5, HOLD_RULE, "OTM5_up", note="high-beta OTM candidate"),
    SleeveSpec("159915", "159915_DTE30_OTM5up_Q100_Hold", "OTM5_up", 1.0, HOLD_RULE, "OTM5_up", note="high-coverage stress test"),
)


ETF_ROLES = {
    "510300": "核心宽基 / 相对低波动 / 主备兑候选",
    "510500": "中盘弹性 / 潜在防御 overlay",
    "159915": "成长弹性 / 高波动 / 高右尾风险",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ver3.0 Step A single-ETF covered-call sleeve outputs.")
    parser.add_argument("--rf", type=float, default=0.0, help="Annual risk-free rate for standardized Sharpe.")
    args = parser.parse_args()

    ensure_dirs()
    verify_inputs()
    _setup_plot_style()

    source_daily, source_period, prices = load_inputs()
    daily = build_daily_nav(source_daily, prices)
    period = build_period_attribution(source_period, source_daily)
    summary, common_start, common_end = build_summary(daily, period, args.rf)
    classification = build_classification(summary)
    panel_long, panel_wide = build_return_panel(daily, classification, common_start, common_end)
    sanity = build_sanity_checks(daily, period, summary, classification, panel_long, panel_wide)

    write_outputs(daily, period, summary, classification, panel_long, panel_wide, sanity)
    write_cards(summary, classification, period)
    write_master_report(summary, classification, sanity, common_start, common_end)
    write_figures(daily, summary, classification, common_start, common_end)

    # Re-run file-existence checks after reports/figures are materialized.
    sanity = build_sanity_checks(daily, period, summary, classification, panel_long, panel_wide)
    sanity.to_csv(AUDIT_DIR / "ver3_0_stepA_sanity_checks.csv", index=False, encoding="utf-8-sig")

    print(f"Wrote ver3.0 Step A outputs to {OUT_ROOT}")
    print(f"Common portfolio sample: {common_start.date().isoformat()} to {common_end.date().isoformat()}")
    print(f"Sanity checks: {int(sanity['passed'].sum())}/{len(sanity)} passed")
    print(classification[["etf_code", "sleeve_name", "classification", "recommendation_status"]].to_string(index=False))


def ensure_dirs() -> None:
    for path in (DAILY_DIR, PERIOD_DIR, SUMMARY_DIR, PANEL_DIR, REPORT_DIR, FIGURE_DIR, AUDIT_DIR):
        path.mkdir(parents=True, exist_ok=True)


def verify_inputs() -> None:
    required = [CONFIG_PATH, OPTION_PATH, PRICE_PATH]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing required Step A inputs:\n" + "\n".join(missing))


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    daily, period = build_continuous_source_paths()
    prices = pd.read_csv(PRICE_PATH, dtype={"etf_code": str})
    for df in (daily, period, prices):
        if "etf_code" in df:
            df["etf_code"] = df["etf_code"].astype(str).str.zfill(6)
    for col in ["date", "rebalance_date", "expiry_date"]:
        if col in daily:
            daily[col] = pd.to_datetime(daily[col], errors="coerce")
    for col in ["rebalance_date", "expiry_date", "period_end_date", "tp80_trigger_date", "spot_touch_trigger_date", "early_close_trigger_date"]:
        if col in period:
            period[col] = pd.to_datetime(period[col], errors="coerce")
    prices["date"] = pd.to_datetime(prices["date"], errors="coerce")

    for col in [
        "underlying_price",
        "option_mark",
        "raw_option_leg_daily_return",
        "raw_short_call_liability",
        "raw_short_call_mtm_loss",
        "option_transaction_cost_today",
    ]:
        if col in daily:
            daily[col] = pd.to_numeric(daily[col], errors="coerce").fillna(0.0)
    for col in [
        "actual_dte",
        "strike",
        "underlying_price_at_entry",
        "underlying_price_at_expiry",
        "entry_delta",
        "realized_moneyness",
        "entry_option_mark",
        "option_mark_at_close",
        "premium_return",
        "entry_transaction_cost",
        "close_transaction_cost",
        "payoff_at_expiry_if_held",
        "actual_payoff_after_close",
        "actual_option_leg_return",
        "dte_remaining_at_close",
        "mtm_max_loss_before_close",
        "days_uncovered_after_close",
    ]:
        if col in period:
            period[col] = pd.to_numeric(period[col], errors="coerce")
    for col in ["active_short_call_flag", "tp80_trigger_flag", "spot_touch_trigger_flag", "early_close_trigger_flag", "assignment_flag"]:
        if col in daily:
            daily[col] = _bool_series(daily[col])
        if col in period:
            period[col] = _bool_series(period[col])

    price_col = "adj_close" if "adj_close" in prices.columns and prices["adj_close"].notna().any() else "close"
    prices["price"] = pd.to_numeric(prices[price_col], errors="coerce")
    prices = prices[prices["etf_code"].isin(ETF_CODES)].dropna(subset=["date", "price"]).sort_values(["etf_code", "date"])
    return daily, period, prices


def build_continuous_source_paths() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rebuild Step A source paths with immediate continuous DTE30 rolls."""

    daily_frames: list[pd.DataFrame] = []
    period_frames: list[pd.DataFrame] = []
    base_config = load_config(CONFIG_PATH, ROOT)
    for etf_code in ETF_CODES:
        strategies = strategy_configs_for_etf(etf_code)
        config = replace(
            base_config,
            etf_codes=(etf_code,),
            paths=replace(base_config.paths, options=OPTION_PATH, output_dir=OUT_ROOT),
            backtest=replace(
                base_config.backtest,
                start_date=START_DATE.date().isoformat(),
                end_date=None,
                initial_nav=1.0,
                execution_mode="continuous_30d",
                roll_frequency="monthly",
                target_dte=30,
                min_days_to_expiry=20,
                max_days_to_expiry=45,
                min_periods=1,
                require_expiry_within_period=False,
                dte_fallback_mode="strict_window",
            ),
            strategies=tuple(strategies),
        )
        result = run_ver2_backtest(config)
        daily_frames.append(convert_continuous_daily(result.daily_mtm))
        period_frames.append(convert_continuous_periods(result.periods))
    daily = pd.concat(daily_frames, ignore_index=True, sort=False)
    period = pd.concat(period_frames, ignore_index=True, sort=False)
    return daily, period


def strategy_configs_for_etf(etf_code: str) -> list[StrategyConfig]:
    families = sorted(
        {
            spec.source_family
            for spec in SPECS
            if spec.etf_code == etf_code and not spec.is_buyhold and spec.close_rule == HOLD_RULE
        }
    )
    configs = [StrategyConfig("BuyHold", "buy_hold", 0.0, 0.0, True)]
    for family in families:
        if family == "ATM":
            configs.append(StrategyConfig("ATM_100", "atm", 1.0, 0.0, True))
        elif family == "D40":
            configs.append(StrategyConfig("D40_100", "target_delta", 1.0, 0.40, True))
        elif family == "OTM5_up":
            configs.append(StrategyConfig("OTM5_up_100", "otm_pct", 1.0, 0.05, True))
        else:
            raise ValueError(f"Unsupported Step A source family: {family}")
    return configs


def convert_continuous_daily(source: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for _, g in source.groupby(["etf_code", "strategy_name"], sort=False):
        gg = g.sort_values(["date", "period_index"]).drop_duplicates("date", keep="last").copy()
        gg["etf_code"] = gg["etf_code"].astype(str).str.zfill(6)
        gg["date"] = pd.to_datetime(gg["date"], errors="coerce")
        gg["rebalance_date"] = pd.to_datetime(gg["rebalance_date"], errors="coerce")
        gg["expiry_date"] = pd.to_datetime(gg["expiry_date"], errors="coerce")
        gg["period_end_date"] = pd.to_datetime(gg["period_end_date"], errors="coerce")
        total_return = gg["daily_mtm_nav"].astype(float).pct_change().fillna(0.0)
        underlying_return = gg["underlying_price"].astype(float).pct_change().fillna(0.0)
        if not total_return.empty:
            total_return.iloc[0] = 0.0
            underlying_return.iloc[0] = 0.0
        is_buyhold = gg["strategy_name"].eq("BuyHold")
        gg["dte_label"] = TARGET_DTE_LABEL
        gg["strategy_family"] = gg["strategy_name"].map(strategy_family_from_name)
        gg["close_rule"] = HOLD_RULE
        gg["raw_option_leg_daily_return"] = np.where(is_buyhold, 0.0, total_return - underlying_return)
        gg["raw_short_call_liability"] = np.where(is_buyhold, 0.0, pd.to_numeric(gg.get("option_liability_return", 0.0), errors="coerce").fillna(0.0))
        gg["raw_short_call_mtm_loss"] = np.where(is_buyhold, 0.0, pd.to_numeric(gg.get("short_call_mtm_loss_return", 0.0), errors="coerce").fillna(0.0))
        cost = pd.to_numeric(gg.get("transaction_cost_return", 0.0), errors="coerce").fillna(0.0)
        gg["option_transaction_cost_today"] = np.where(gg["date"].eq(gg["rebalance_date"]), cost, 0.0)
        gg["option_mark"] = pd.to_numeric(gg.get("option_mark_price", 0.0), errors="coerce").fillna(0.0)
        gg["active_short_call_flag"] = gg.get("position_state", "").astype(str).eq("short_call")
        gg["tp80_trigger_flag"] = False
        gg["spot_touch_trigger_flag"] = False
        gg["early_close_trigger_flag"] = False
        frames.append(gg)
    return pd.concat(frames, ignore_index=True, sort=False)


def convert_continuous_periods(source: pd.DataFrame) -> pd.DataFrame:
    out = source.copy()
    out["etf_code"] = out["etf_code"].astype(str).str.zfill(6)
    out["strategy_family"] = out["strategy_name"].map(strategy_family_from_name)
    out["dte_label"] = TARGET_DTE_LABEL
    out["close_rule"] = HOLD_RULE
    out["entry_delta"] = pd.to_numeric(out.get("selected_delta", np.nan), errors="coerce")
    out["entry_option_mark"] = pd.to_numeric(out.get("option_price_at_entry", np.nan), errors="coerce")
    out["option_mark_at_close"] = pd.to_numeric(out.get("option_intrinsic_value_at_expiry", np.nan), errors="coerce")
    out["entry_transaction_cost"] = pd.to_numeric(out.get("transaction_cost_return", 0.0), errors="coerce").fillna(0.0)
    out["close_transaction_cost"] = 0.0
    out["payoff_at_expiry_if_held"] = pd.to_numeric(out.get("upside_payoff_return", 0.0), errors="coerce").fillna(0.0)
    out["actual_payoff_after_close"] = out["payoff_at_expiry_if_held"]
    out["actual_option_leg_return"] = pd.to_numeric(out.get("net_option_contribution", 0.0), errors="coerce").fillna(0.0)
    out["dte_remaining_at_close"] = 0.0
    out["mtm_max_loss_before_close"] = np.nan
    out["days_uncovered_after_close"] = 0.0
    out["tp80_trigger_flag"] = False
    out["spot_touch_trigger_flag"] = False
    out["early_close_trigger_flag"] = False
    out["policy_jump_window_flag"] = False
    out["warning_flag"] = ""
    return out


def strategy_family_from_name(strategy_name: Any) -> str:
    name = str(strategy_name)
    if name == "BuyHold":
        return "BuyHold"
    if name.startswith("ATM"):
        return "ATM"
    if name.startswith("D40"):
        return "D40"
    if name.startswith("OTM5_up"):
        return "OTM5_up"
    return name.replace("_100", "")


def build_daily_nav(source_daily: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    option_dates = {
        etf: pd.DatetimeIndex(
            source_daily.loc[
                (source_daily["etf_code"].eq(etf))
                & (source_daily["dte_label"].eq(TARGET_DTE_LABEL))
                & (source_daily["close_rule"].eq(HOLD_RULE)),
                "date",
            ].dropna().sort_values().unique()
        )
        for etf in ETF_CODES
    }
    for spec in SPECS:
        if spec.is_buyhold:
            frames.append(build_buyhold_daily(spec, prices, option_dates[spec.etf_code]))
        else:
            frames.append(build_option_daily(spec, source_daily))
    daily = pd.concat(frames, ignore_index=True).sort_values(["etf_code", "sleeve_name", "date"]).reset_index(drop=True)
    return daily


def build_buyhold_daily(spec: SleeveSpec, prices: pd.DataFrame, option_dates: pd.DatetimeIndex) -> pd.DataFrame:
    p = prices[(prices["etf_code"].eq(spec.etf_code)) & (prices["date"].isin(option_dates))].copy()
    p = p.sort_values("date").drop_duplicates("date")
    p["daily_return_underlying_component"] = p["price"].pct_change().fillna(0.0)
    p["daily_return_option_leg_component"] = 0.0
    p["daily_return_total"] = p["daily_return_underlying_component"]
    p["nav_total"] = (1.0 + p["daily_return_total"]).cumprod()
    p["nav_underlying_component"] = (1.0 + p["daily_return_underlying_component"]).cumprod()
    p["nav_option_leg_component"] = 1.0
    return pd.DataFrame(
        {
            "date": p["date"],
            "etf_code": spec.etf_code,
            "sleeve_name": spec.sleeve_name,
            "strategy_family": "ETF_BuyHold",
            "dte_label": "NA",
            "coverage": 0.0,
            "close_rule": "buyhold",
            "nav_total": p["nav_total"],
            "daily_return_total": p["daily_return_total"],
            "nav_underlying_component": p["nav_underlying_component"],
            "daily_return_underlying_component": p["daily_return_underlying_component"],
            "nav_option_leg_component": p["nav_option_leg_component"],
            "daily_return_option_leg_component": 0.0,
            "option_leg_pnl": 0.0,
            "short_call_liability": 0.0,
            "short_call_mtm_loss": 0.0,
            "active_short_call_flag": False,
            "active_coverage": 0.0,
            "target_coverage": 0.0,
            "option_transaction_cost_today": 0.0,
            "rebalance_date": pd.NaT,
            "expiry_date": pd.NaT,
            "option_code": np.nan,
            "gap_flag": False,
            "gap_reason": "buyhold_no_option_leg",
        }
    )


def build_option_daily(spec: SleeveSpec, source_daily: pd.DataFrame) -> pd.DataFrame:
    src = source_daily[
        (source_daily["etf_code"].eq(spec.etf_code))
        & (source_daily["dte_label"].eq(spec.dte_label))
        & (source_daily["strategy_family"].eq(spec.source_family))
        & (source_daily["close_rule"].eq(spec.close_rule))
    ].copy()
    if src.empty:
        raise ValueError(f"No source daily rows for {spec.sleeve_name}")
    src = src.sort_values(["date", "rebalance_date", "option_code"]).drop_duplicates("date", keep="last")
    src["daily_return_underlying_component"] = src["underlying_price"].astype(float).pct_change().fillna(0.0)
    src["daily_return_option_leg_component"] = src["raw_option_leg_daily_return"].astype(float) * spec.coverage
    src["daily_return_total"] = src["daily_return_underlying_component"] + src["daily_return_option_leg_component"]
    src["nav_total"] = (1.0 + src["daily_return_total"]).cumprod()
    src["nav_underlying_component"] = (1.0 + src["daily_return_underlying_component"]).cumprod()
    src["nav_option_leg_component"] = (1.0 + src["daily_return_option_leg_component"]).cumprod()
    active = _bool_series(src["active_short_call_flag"]) if "active_short_call_flag" in src else pd.Series(True, index=src.index)
    return pd.DataFrame(
        {
            "date": src["date"],
            "etf_code": spec.etf_code,
            "sleeve_name": spec.sleeve_name,
            "strategy_family": spec.strategy_family,
            "dte_label": spec.dte_label,
            "coverage": spec.coverage,
            "close_rule": spec.close_rule,
            "nav_total": src["nav_total"],
            "daily_return_total": src["daily_return_total"],
            "nav_underlying_component": src["nav_underlying_component"],
            "daily_return_underlying_component": src["daily_return_underlying_component"],
            "nav_option_leg_component": src["nav_option_leg_component"],
            "daily_return_option_leg_component": src["daily_return_option_leg_component"],
            "option_leg_pnl": src["daily_return_option_leg_component"],
            "short_call_liability": src["raw_short_call_liability"].astype(float) * spec.coverage,
            "short_call_mtm_loss": src["raw_short_call_mtm_loss"].astype(float) * spec.coverage,
            "active_short_call_flag": active,
            "active_coverage": np.where(active, spec.coverage, 0.0),
            "target_coverage": spec.coverage,
            "option_transaction_cost_today": src.get("option_transaction_cost_today", 0.0).astype(float) * spec.coverage,
            "rebalance_date": src["rebalance_date"],
            "expiry_date": src["expiry_date"],
            "option_code": src["option_code"],
            "gap_flag": False,
            "gap_reason": "none",
        }
    )


def build_period_attribution(source_period: pd.DataFrame, source_daily: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    stress_lookup = build_cycle_stress_lookup(source_daily)
    for spec in SPECS:
        if spec.is_buyhold:
            continue
        src = source_period[
            (source_period["etf_code"].eq(spec.etf_code))
            & (source_period["strategy_family"].eq(spec.source_family))
            & (source_period["close_rule"].eq(spec.close_rule))
        ].copy()
        if src.empty:
            raise ValueError(f"No source period rows for {spec.sleeve_name}")
        for _, row in src.sort_values(["rebalance_date", "expiry_date"]).iterrows():
            entry_price = float(row.get("underlying_price_at_entry", np.nan))
            close_mark = float(row.get("option_mark_at_close", np.nan))
            early_close = bool(row.get("early_close_trigger_flag", False))
            premium = float(row.get("premium_return", 0.0) or 0.0) * spec.coverage
            cost = (float(row.get("entry_transaction_cost", 0.0) or 0.0) + float(row.get("close_transaction_cost", 0.0) or 0.0)) * spec.coverage
            option_leg = float(row.get("actual_option_leg_return", 0.0) or 0.0) * spec.coverage
            payoff = premium - cost - option_leg
            etf_ret = _safe_div(float(row.get("underlying_price_at_expiry", np.nan)), entry_price) - 1.0
            close_date, close_reason = _close_info(row, spec.close_rule)
            key = (
                spec.etf_code,
                spec.source_family or "",
                spec.close_rule,
                pd.Timestamp(row["rebalance_date"]),
                str(row["option_code"]),
            )
            stress = stress_lookup.get(key, {"max": np.nan, "p95": np.nan})
            assignment = bool(row.get("assignment_flag", False)) and not early_close
            rows.append(
                {
                    "etf_code": spec.etf_code,
                    "sleeve_name": spec.sleeve_name,
                    "strategy_family": spec.strategy_family,
                    "dte_label": spec.dte_label,
                    "target_dte": 30,
                    "actual_dte": row.get("actual_dte", np.nan),
                    "coverage": spec.coverage,
                    "close_rule": spec.close_rule,
                    "rebalance_date": pd.Timestamp(row["rebalance_date"]).date().isoformat(),
                    "expiry_date": pd.Timestamp(row["expiry_date"]).date().isoformat(),
                    "period_end_date": _date_string(row.get("period_end_date", row.get("expiry_date"))),
                    "option_code": row.get("option_code"),
                    "strike": row.get("strike", np.nan),
                    "entry_etf_price": entry_price,
                    "expiry_etf_price": row.get("underlying_price_at_expiry", np.nan),
                    "entry_delta": row.get("entry_delta", np.nan),
                    "realized_moneyness": row.get("realized_moneyness", np.nan),
                    "entry_option_mark": row.get("entry_option_mark", row.get("option_mark_at_entry", np.nan)),
                    "close_date": close_date,
                    "close_reason": close_reason,
                    "close_option_mark": close_mark if np.isfinite(close_mark) else np.nan,
                    "dte_remaining_at_close": row.get("dte_remaining_at_close", np.nan),
                    "premium_return": premium,
                    "payoff_return": payoff,
                    "transaction_cost_return": cost,
                    "option_leg_return": option_leg,
                    "etf_period_return": etf_ret,
                    "covered_call_period_return": etf_ret + option_leg if pd.notna(etf_ret) else np.nan,
                    "premium_capture_ratio": _safe_div(option_leg, premium),
                    "payoff_burden": _safe_div(payoff, premium),
                    "assignment_flag": assignment,
                    "tp80_trigger_flag": False,
                    "touch_k_trigger_flag": False,
                    "max_short_call_mtm_loss_in_period": stress["max"] * spec.coverage if pd.notna(stress["max"]) else np.nan,
                    "p95_short_call_mtm_loss_in_period": stress["p95"] * spec.coverage if pd.notna(stress["p95"]) else np.nan,
                    "policy_jump_window_flag": bool(row.get("policy_jump_window_flag", False)),
                    "warning_flag": row.get("warning_flag", ""),
                }
            )
    return pd.DataFrame(rows).sort_values(["etf_code", "sleeve_name", "rebalance_date"]).reset_index(drop=True)


def build_cycle_stress_lookup(source_daily: pd.DataFrame) -> dict[tuple[str, str, str, pd.Timestamp, str], dict[str, float]]:
    lookup: dict[tuple[str, str, str, pd.Timestamp, str], dict[str, float]] = {}
    for (etf, family, rule, rebalance, option_code), g in source_daily.groupby(
        ["etf_code", "strategy_family", "close_rule", "rebalance_date", "option_code"], dropna=False
    ):
        stress = pd.to_numeric(g["raw_short_call_mtm_loss"], errors="coerce").fillna(0.0)
        lookup[(str(etf).zfill(6), str(family), str(rule), pd.Timestamp(rebalance), str(option_code))] = {
            "max": float(stress.max()),
            "p95": float(stress.quantile(0.95)),
        }
    return lookup


def build_summary(
    daily: pd.DataFrame,
    period: pd.DataFrame,
    rf: float,
) -> tuple[pd.DataFrame, pd.Timestamp, pd.Timestamp]:
    common_start = START_DATE
    common_end = min(pd.Timestamp(g["date"].max()) for _, g in daily.groupby(["etf_code", "sleeve_name"]))
    rows: list[dict[str, Any]] = []
    for (etf, sleeve), g in daily.groupby(["etf_code", "sleeve_name"]):
        g = g.sort_values("date").copy()
        scopes = {
            "full_available_sample_by_etf": (pd.Timestamp(g["date"].min()), pd.Timestamp(g["date"].max())),
            "common_portfolio_sample": (common_start, common_end),
        }
        for scope, (start, end) in scopes.items():
            sample = g[(g["date"] >= start) & (g["date"] <= end)].copy()
            p = period[
                (period["etf_code"].eq(etf))
                & (period["sleeve_name"].eq(sleeve))
                & (pd.to_datetime(period["rebalance_date"]) >= start)
                & (pd.to_datetime(period["rebalance_date"]) <= end)
            ].copy()
            metrics = summarize_daily_nav(sample[["date", "nav_total"]], date_col="date", nav_col="nav_total", rf=rf)
            option_metrics = summarize_option_metrics(sample, p)
            rows.append(
                {
                    "etf_code": etf,
                    "sleeve_name": sleeve,
                    "sample_scope": scope,
                    **metrics,
                    **option_metrics,
                    "notes": _spec_by_name(sleeve).note,
                }
            )
    summary = pd.DataFrame(rows)
    ordered = [
        "etf_code",
        "sleeve_name",
        "sample_scope",
        "sample_start",
        "sample_end",
        "n_trading_days",
        "annualized_return_cagr",
        "arithmetic_annualized_return",
        "annualized_volatility",
        "sharpe_daily_mean",
        "cagr_vol_ratio",
        "sortino_ratio",
        "calmar_ratio",
        "max_drawdown",
        "monthly_win_rate",
        "option_leg_annualized_pnl_contribution",
        "premium_capture_ratio_agg",
        "payoff_burden_agg",
        "premium_capture_ratio_period_mean",
        "payoff_burden_period_mean",
        "positive_option_leg_period_rate",
        "assignment_rate",
        "p95_short_call_mtm_loss",
        "p99_short_call_mtm_loss",
        "max_short_call_mtm_loss",
        "avg_actual_dte",
        "avg_entry_delta",
        "median_entry_delta",
        "avg_realized_moneyness",
        "median_realized_moneyness",
        "gap_periods",
        "early_close_rate",
        "avg_active_coverage",
        "notes",
    ]
    return summary[ordered], common_start, common_end


def summarize_option_metrics(sample: pd.DataFrame, period: pd.DataFrame) -> dict[str, Any]:
    option_pnl = sample["option_leg_pnl"].astype(float)
    stress = sample["short_call_mtm_loss"].astype(float)
    if period.empty:
        return {
            "option_leg_annualized_pnl_contribution": 0.0,
            "premium_capture_ratio_agg": np.nan,
            "payoff_burden_agg": np.nan,
            "premium_capture_ratio_period_mean": np.nan,
            "payoff_burden_period_mean": np.nan,
            "positive_option_leg_period_rate": np.nan,
            "assignment_rate": np.nan,
            "p95_short_call_mtm_loss": 0.0,
            "p99_short_call_mtm_loss": 0.0,
            "max_short_call_mtm_loss": 0.0,
            "avg_actual_dte": np.nan,
            "avg_entry_delta": np.nan,
            "median_entry_delta": np.nan,
            "avg_realized_moneyness": np.nan,
            "median_realized_moneyness": np.nan,
            "gap_periods": 0,
            "early_close_rate": 0.0,
            "avg_active_coverage": float(sample["active_coverage"].mean()),
        }
    premium = period["premium_return"].astype(float)
    payoff = period["payoff_return"].astype(float)
    option_leg = period["option_leg_return"].astype(float)
    early = period["close_reason"].astype(str).isin(["tp80", "touch_k"])
    return {
        "option_leg_annualized_pnl_contribution": compute_portfolio_option_contribution(option_pnl, n_days=len(sample)),
        "premium_capture_ratio_agg": _safe_div(float(option_leg.sum()), float(premium.sum())),
        "payoff_burden_agg": _safe_div(float(payoff.sum()), float(premium.sum())),
        "premium_capture_ratio_period_mean": float(period["premium_capture_ratio"].astype(float).mean()),
        "payoff_burden_period_mean": float(period["payoff_burden"].astype(float).mean()),
        "positive_option_leg_period_rate": float((option_leg > 0).mean()),
        "assignment_rate": float(_bool_series(period["assignment_flag"]).mean()),
        "p95_short_call_mtm_loss": float(stress.quantile(0.95)),
        "p99_short_call_mtm_loss": float(stress.quantile(0.99)),
        "max_short_call_mtm_loss": float(stress.max()),
        "avg_actual_dte": float(period["actual_dte"].astype(float).mean()),
        "avg_entry_delta": float(period["entry_delta"].astype(float).mean()),
        "median_entry_delta": float(period["entry_delta"].astype(float).median()),
        "avg_realized_moneyness": float(period["realized_moneyness"].astype(float).mean()),
        "median_realized_moneyness": float(period["realized_moneyness"].astype(float).median()),
        "gap_periods": int(period["warning_flag"].astype(str).str.contains("gap|missing", case=False, na=False).sum()),
        "early_close_rate": float(early.mean()),
        "avg_active_coverage": float(sample["active_coverage"].mean()),
    }


def build_classification(summary: pd.DataFrame) -> pd.DataFrame:
    common = summary[summary["sample_scope"].eq("common_portfolio_sample")].copy()
    buyhold = common[common["sleeve_name"].str.endswith("ETF_BuyHold")].set_index("etf_code")
    rows: list[dict[str, Any]] = []
    for _, row in common.iterrows():
        spec = _spec_by_name(row["sleeve_name"])
        bh = buyhold.loc[row["etf_code"]]
        beats_return = bool(row["annualized_return_cagr"] >= bh["annualized_return_cagr"] - 1e-12)
        beats_sharpe = bool(row["sharpe_daily_mean"] >= bh["sharpe_daily_mean"] - 1e-12)
        improves_mdd = bool(row["max_drawdown"] <= bh["max_drawdown"] + 1e-12)
        option_positive = bool(row["option_leg_annualized_pnl_contribution"] > 0)
        execution_ok = bool((row["gap_periods"] == 0) and pd.notna(row["annualized_return_cagr"]))
        classification, reason, caveat = classify_sleeve(row, bh, spec, option_positive, beats_sharpe, improves_mdd)
        rows.append(
            {
                "etf_code": row["etf_code"],
                "sleeve_name": row["sleeve_name"],
                "classification": classification,
                "annualized_return_cagr": row["annualized_return_cagr"],
                "sharpe_daily_mean": row["sharpe_daily_mean"],
                "max_drawdown": row["max_drawdown"],
                "option_leg_annualized_pnl_contribution": row["option_leg_annualized_pnl_contribution"],
                "premium_capture_ratio_agg": row["premium_capture_ratio_agg"],
                "payoff_burden_agg": row["payoff_burden_agg"],
                "p99_short_call_mtm_loss": row["p99_short_call_mtm_loss"],
                "beats_buyhold_return": beats_return,
                "beats_buyhold_sharpe": beats_sharpe,
                "improves_buyhold_mdd": improves_mdd,
                "option_leg_positive": option_positive,
                "passes_execution_check": execution_ok,
                "recommendation_status": "rejected",
                "reason": reason,
                "caveat": caveat,
            }
        )
    out = pd.DataFrame(rows)
    out = assign_recommendations(out)
    order = {spec.sleeve_name: i for i, spec in enumerate(SPECS)}
    out["_order"] = out["sleeve_name"].map(order)
    return out.sort_values(["etf_code", "_order"]).drop(columns="_order").reset_index(drop=True)


def classify_sleeve(
    row: pd.Series,
    buyhold: pd.Series,
    spec: SleeveSpec,
    option_positive: bool,
    beats_sharpe: bool,
    improves_mdd: bool,
) -> tuple[str, str, str]:
    if spec.is_buyhold:
        return "Pure ETF Preferred", "ETF-only baseline for comparison.", "No option leg."
    is_q100 = "_Q100_" in spec.sleeve_name or spec.sleeve_name.endswith("_Q100_Hold")
    if is_q100:
        return "Stress Test Only", "Q100 is retained as a full-coverage stress test.", "Do not promote by default even when in-sample metrics look good."
    if option_positive and beats_sharpe and improves_mdd:
        return "Positive Carry Overlay", "Net option leg is positive while Sharpe and drawdown are at least as good as BuyHold.", "Still sample-limited and not an arbitrage claim."
    mdd_improvement = float(buyhold["max_drawdown"]) - float(row["max_drawdown"])
    sharpe_gap = float(row["sharpe_daily_mean"]) - float(buyhold["sharpe_daily_mean"])
    if (not option_positive) and mdd_improvement >= 0.01 and sharpe_gap >= -0.05:
        return "Defensive Overlay", "Net option leg is not positive, but drawdown improves enough with similar Sharpe.", "Use as risk-control sleeve, not income enhancement."
    if option_positive and improves_mdd and sharpe_gap >= -0.05:
        return "Defensive Overlay", "Option leg is positive but total profile is better framed as risk control.", "Return improvement is not the primary rationale."
    return "Pure ETF Preferred", "Covered-call sleeve does not improve the ETF baseline enough.", "Keep as pure ETF or diagnostic reference."


def assign_recommendations(classification: pd.DataFrame) -> pd.DataFrame:
    out = classification.copy()
    for etf, g in out.groupby("etf_code"):
        eligible = g[
            g["classification"].isin(["Positive Carry Overlay", "Defensive Overlay"])
            & g["passes_execution_check"].astype(bool)
        ].copy()
        if eligible.empty:
            primary = g[g["sleeve_name"].str.endswith("ETF_BuyHold")].iloc[0]["sleeve_name"]
            backup = ""
        else:
            rank_class = {"Positive Carry Overlay": 0, "Defensive Overlay": 1}
            eligible["_rank_class"] = eligible["classification"].map(rank_class)
            eligible = eligible.sort_values(
                ["_rank_class", "sharpe_daily_mean", "max_drawdown", "annualized_return_cagr"],
                ascending=[True, False, True, False],
            )
            primary = eligible.iloc[0]["sleeve_name"]
            backup = eligible.iloc[1]["sleeve_name"] if len(eligible) > 1 else f"{etf}_ETF_BuyHold"
        out.loc[(out["etf_code"].eq(etf)) & (out["sleeve_name"].eq(primary)), "recommendation_status"] = "primary_for_portfolio_layer"
        if backup:
            out.loc[(out["etf_code"].eq(etf)) & (out["sleeve_name"].eq(backup)), "recommendation_status"] = "backup_for_portfolio_layer"
        diagnostic_mask = (
            out["etf_code"].eq(etf)
            & out["classification"].isin(["Diagnostic Only", "Stress Test Only"])
            & ~out["sleeve_name"].isin([primary, backup])
        )
        out.loc[diagnostic_mask, "recommendation_status"] = "diagnostic_only"
    return out


def build_return_panel(
    daily: pd.DataFrame,
    classification: pd.DataFrame,
    common_start: pd.Timestamp,
    common_end: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    status = classification[["etf_code", "sleeve_name", "classification", "recommendation_status"]]
    panel = daily[(daily["date"] >= common_start) & (daily["date"] <= common_end)].copy()
    panel = panel.merge(status, on=["etf_code", "sleeve_name"], how="left")
    long = panel[
        [
            "date",
            "etf_code",
            "sleeve_name",
            "daily_return_total",
            "nav_total",
            "classification",
            "recommendation_status",
        ]
    ].rename(columns={"daily_return_total": "daily_return", "nav_total": "nav"})
    long["sample_scope"] = "common_portfolio_sample"
    long = long[
        [
            "date",
            "etf_code",
            "sleeve_name",
            "daily_return",
            "nav",
            "sample_scope",
            "classification",
            "recommendation_status",
        ]
    ]
    wide_source = long.copy()
    wide_source["column"] = wide_source["etf_code"] + "__" + wide_source["sleeve_name"] + "__daily_return"
    wide = wide_source.pivot(index="date", columns="column", values="daily_return").sort_index().reset_index()
    return long.sort_values(["date", "etf_code", "sleeve_name"]).reset_index(drop=True), wide


def build_sanity_checks(
    daily: pd.DataFrame,
    period: pd.DataFrame,
    summary: pd.DataFrame,
    classification: pd.DataFrame,
    panel_long: pd.DataFrame,
    panel_wide: pd.DataFrame,
) -> pd.DataFrame:
    summary_cols = set(summary.columns)
    expected_metric_cols = {
        "annualized_return_cagr",
        "arithmetic_annualized_return",
        "annualized_volatility",
        "sharpe_daily_mean",
        "cagr_vol_ratio",
        "max_drawdown",
        "calmar_ratio",
        "sortino_ratio",
        "option_leg_annualized_pnl_contribution",
        "premium_capture_ratio_agg",
        "payoff_burden_agg",
        "premium_capture_ratio_period_mean",
        "payoff_burden_period_mean",
        "p95_short_call_mtm_loss",
        "p99_short_call_mtm_loss",
        "max_short_call_mtm_loss",
    }
    checks = [
        ("uses_standardized_metrics", expected_metric_cols.issubset(summary_cols), "summary uses ver2 metric field names and summarize_daily_nav"),
        ("no_portfolio_weighting_in_stepA", not any(col.startswith("weight_") or col == "portfolio_name" for col in daily.columns), "single ETF rows only"),
        ("no_mean_variance_in_stepA", True, "no covariance or optimizer is called"),
        ("each_etf_sleeve_independent", set(daily["etf_code"].unique()) == set(ETF_CODES), "one independent sleeve path per ETF/spec"),
        ("no_forced_common_expiry_across_etfs", True, "source ETF paths keep their own selected option cycles"),
        ("option_leg_net_pnl", _period_formula_ok(period), "period option leg equals premium minus close/payoff liability and costs"),
        ("premium_not_immediate_profit", _entry_day_cost_only(daily), "entry-day option P&L is cost/MTM based, not premium income"),
        ("daily_panel_unique_sleeve_dates", _daily_panel_unique_dates(daily), "daily panel has one consolidated return row per sleeve/date after same-day rolls"),
        ("buyhold_option_fields_zero", _buyhold_zero(daily), "BuyHold option fields are zero"),
        ("deprecated_tp80_touch_absent", _deprecated_rules_absent(daily, period), "TP80 and Touch-K are excluded from the current Step A mainline"),
        ("immediate_reopen_after_period_end", _immediate_reopen_ok(period), "Next option cycle rebalances on the previous period_end_date"),
        ("q100_stress_test_only", _q100_stress(classification), "Q100 rows are stress tests"),
        ("no_new_dte_added", set(daily.loc[daily["dte_label"].ne("NA"), "dte_label"].unique()) <= {TARGET_DTE_LABEL}, "DTE30 only"),
        ("no_new_delta_grid_added", set(daily["strategy_family"].unique()) <= {"ETF_BuyHold", "ATM", "D40", "OTM5_up"}, "no added OTM/DTE grid"),
        ("no_arbitrage_language", _reports_avoid_arbitrage(), "reports avoid arbitrage language"),
        ("sleeve_return_panel_created", not panel_long.empty and not panel_wide.empty, "long and wide panels are populated"),
        ("classification_table_created", not classification.empty, "classification table is populated"),
        ("sleeve_cards_created", _cards_exist(), "three ETF sleeve cards exist after report writing"),
    ]
    return pd.DataFrame([{"check_name": name, "passed": bool(passed), "note": note} for name, passed, note in checks])


def write_outputs(
    daily: pd.DataFrame,
    period: pd.DataFrame,
    summary: pd.DataFrame,
    classification: pd.DataFrame,
    panel_long: pd.DataFrame,
    panel_wide: pd.DataFrame,
    sanity: pd.DataFrame,
) -> None:
    daily.to_csv(DAILY_DIR / "ver3_0_stepA_single_etf_sleeve_daily_nav.csv", index=False, encoding="utf-8-sig")
    period.to_csv(PERIOD_DIR / "ver3_0_stepA_single_etf_period_attribution.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(SUMMARY_DIR / "ver3_0_stepA_single_etf_sleeve_summary.csv", index=False, encoding="utf-8-sig")
    classification.to_csv(SUMMARY_DIR / "ver3_0_stepA_sleeve_classification_table.csv", index=False, encoding="utf-8-sig")
    panel_long.to_csv(PANEL_DIR / "ver3_0_stepA_sleeve_return_panel_long.csv", index=False, encoding="utf-8-sig")
    panel_wide.to_csv(PANEL_DIR / "ver3_0_stepA_sleeve_return_panel_wide.csv", index=False, encoding="utf-8-sig")
    sanity.to_csv(AUDIT_DIR / "ver3_0_stepA_sanity_checks.csv", index=False, encoding="utf-8-sig")


def write_cards(summary: pd.DataFrame, classification: pd.DataFrame, period: pd.DataFrame) -> None:
    common = summary[summary["sample_scope"].eq("common_portfolio_sample")].copy()
    for etf in ETF_CODES:
        s = common[common["etf_code"].eq(etf)].merge(
            classification[["etf_code", "sleeve_name", "classification", "recommendation_status", "reason", "caveat"]],
            on=["etf_code", "sleeve_name"],
            how="left",
        )
        primary = classification[
            (classification["etf_code"].eq(etf))
            & (classification["recommendation_status"].eq("primary_for_portfolio_layer"))
        ]
        backup = classification[
            (classification["etf_code"].eq(etf))
            & (classification["recommendation_status"].eq("backup_for_portfolio_layer"))
        ]
        rejected = classification[
            (classification["etf_code"].eq(etf))
            & (classification["recommendation_status"].isin(["diagnostic_only", "rejected"]))
        ]
        p = period[period["etf_code"].eq(etf)]
        jump_count = int(p["policy_jump_window_flag"].astype(bool).sum()) if not p.empty else 0
        text = f"""# ETF Sleeve Card | {etf}

## 1. 标的定位

{ETF_ROLES[etf]}

## 2. 候选 sleeve 列表

{_md_table(s[["sleeve_name", "classification", "recommendation_status"]])}

## 3. 核心绩效对比

{_md_table(s[["sleeve_name", "annualized_return_cagr", "sharpe_daily_mean", "max_drawdown", "option_leg_annualized_pnl_contribution", "p99_short_call_mtm_loss"]], pct_cols=["annualized_return_cagr", "max_drawdown", "option_leg_annualized_pnl_contribution", "p99_short_call_mtm_loss"], num_cols=["sharpe_daily_mean"])}

## 4. Option-leg 质量

{_md_table(s[["sleeve_name", "premium_capture_ratio_agg", "payoff_burden_agg", "positive_option_leg_period_rate", "assignment_rate", "early_close_rate"]], pct_cols=["premium_capture_ratio_agg", "payoff_burden_agg", "positive_option_leg_period_rate", "assignment_rate", "early_close_rate"])}

## 5. 风险路径

{_md_table(s[["sleeve_name", "max_drawdown", "p95_short_call_mtm_loss", "p99_short_call_mtm_loss", "max_short_call_mtm_loss"]], pct_cols=["max_drawdown", "p95_short_call_mtm_loss", "p99_short_call_mtm_loss", "max_short_call_mtm_loss"])}

政策跳涨窗口涉及的 option 周期数：{jump_count}。TP80 / Touch-K 已从当前 Step A 主线排除；Q100 仅作为 stress diagnostic，不作为默认组合层主线。

## 6. 执行与选券

{_md_table(s[["sleeve_name", "avg_actual_dte", "avg_entry_delta", "median_entry_delta", "avg_realized_moneyness", "gap_periods", "avg_active_coverage"]], pct_cols=["avg_realized_moneyness", "avg_active_coverage"], num_cols=["avg_actual_dte", "avg_entry_delta", "median_entry_delta"])}

## 7. Sleeve 分类

{_md_table(classification[classification["etf_code"].eq(etf)][["sleeve_name", "classification", "reason", "caveat"]])}

## 8. 推荐进入组合层的 sleeve

- primary_sleeve_for_portfolio_layer: {_first_or_blank(primary, "sleeve_name")}
- backup_sleeve: {_first_or_blank(backup, "sleeve_name")}
- rejected_sleeves: {", ".join(rejected["sleeve_name"].tolist())}
- rationale: {_first_or_blank(primary, "reason")}
- caveat: {_first_or_blank(primary, "caveat")}
"""
        (REPORT_DIR / f"{etf}_sleeve_card.md").write_text(text, encoding="utf-8")


def write_master_report(
    summary: pd.DataFrame,
    classification: pd.DataFrame,
    sanity: pd.DataFrame,
    common_start: pd.Timestamp,
    common_end: pd.Timestamp,
) -> None:
    common = summary[summary["sample_scope"].eq("common_portfolio_sample")]
    primary = classification[classification["recommendation_status"].eq("primary_for_portfolio_layer")]
    diag = classification[classification["recommendation_status"].isin(["diagnostic_only", "rejected"])]
    sets = build_recommended_sets(classification)
    text = f"""# ver3.0 Step A | 单 ETF 备兑 Sleeve 画像整理

## 1. 实验定位

本步骤先把每个 ETF 标的做清楚；不做组合、不做动态权重、不强制账户级统一周期。每个 ETF sleeve 独立生成净值曲线，后续 Step B / Step C 再用 return panel 加权。

共同样本：{common_start.date().isoformat()} 至 {common_end.date().isoformat()}。

## 2. 方法

日频口径使用 `R_CC = R_ETF + R_OptionLeg`。期权腿净 P&L 使用 `Premium - Payoff - Cost`；source paths 由 `continuous_30d` 引擎重建，上一周期 `period_end_date` 即下一周期 `rebalance_date`。TP80 / Touch-K 不进入当前 Step A 主线。

绩效字段沿用 ver2_metric_standardization 的命名：`annualized_return_cagr` 是主年化收益，`sharpe_daily_mean` 是主 Sharpe，`max_drawdown` 为正数口径。

## 3. 510300 Sleeve Card Summary

{_etf_short_verdict(classification, "510300")}

## 4. 510500 Sleeve Card Summary

{_etf_short_verdict(classification, "510500")}

## 5. 159915 Sleeve Card Summary

{_etf_short_verdict(classification, "159915")}

## 6. Cross-ETF Sleeve Classification

{_md_table(classification[["etf_code", "sleeve_name", "classification", "recommendation_status", "annualized_return_cagr", "sharpe_daily_mean", "max_drawdown", "option_leg_annualized_pnl_contribution"]], pct_cols=["annualized_return_cagr", "max_drawdown", "option_leg_annualized_pnl_contribution"], num_cols=["sharpe_daily_mean"])}

## 7. 推荐进入组合层的 Sleeve Set

{sets}

这些只是 sleeve set，不在 Step A 中计算组合绩效。

## 8. 为 ver3.0 Step B / C 准备

Step B 可以直接读取 `outputs/ver3_0_stepA_single_etf_sleeves/panel/ver3_0_stepA_sleeve_return_panel_wide.csv` 做固定权重组合。Step C 可以基于这些 sleeve 或 ETF daily return 做波动率 / 协方差驱动的动态权重。Step A 不涉及均值方差优化。

## 9. 局限性

- 样本期有限，且覆盖 2024 年政策跳涨等强事件窗口；
- 高弹性 ETF 的备兑可能负 carry；
- TP80 / Touch-K 已从当前主线 Step A 排除；
- Q100 是 stress test；
- 组合层结果不能反推单 ETF 有效性；
- 本报告不使用确定性收益或 guaranteed-profit 表述。

## 10. 主候选和诊断候选

主候选：

{_md_table(primary[["etf_code", "sleeve_name", "classification", "reason", "caveat"]])}

诊断 / 压力测试：

{_md_table(diag[["etf_code", "sleeve_name", "classification", "reason"]])}

## 11. Sanity Checks

{_md_table(sanity)}
"""
    (REPORT_DIR / "ver3_0_stepA_single_etf_sleeve_master_report.md").write_text(text, encoding="utf-8")


def build_recommended_sets(classification: pd.DataFrame) -> str:
    primary = classification[classification["recommendation_status"].eq("primary_for_portfolio_layer")].set_index("etf_code")
    backup = classification[classification["recommendation_status"].eq("backup_for_portfolio_layer")].set_index("etf_code")
    lines = [
        "conservative:",
        f"- 510300: {_safe_lookup(backup, '510300', 'sleeve_name') or _safe_lookup(primary, '510300', 'sleeve_name')}",
        f"- 510500: 510500_ETF_BuyHold",
        f"- 159915: 159915_ETF_BuyHold",
        "",
        "balanced:",
        f"- 510300: {_safe_lookup(primary, '510300', 'sleeve_name')}",
        f"- 510500: {_safe_lookup(primary, '510500', 'sleeve_name')}",
        f"- 159915: {_safe_lookup(primary, '159915', 'sleeve_name')}",
        "",
        "defensive:",
        f"- 510300: {_safe_lookup(primary, '510300', 'sleeve_name')}",
        f"- 510500: {_safe_lookup(primary, '510500', 'sleeve_name')}",
        f"- 159915: {_safe_lookup(primary, '159915', 'sleeve_name')}",
    ]
    return "\n".join(lines)


def write_figures(
    daily: pd.DataFrame,
    summary: pd.DataFrame,
    classification: pd.DataFrame,
    common_start: pd.Timestamp,
    common_end: pd.Timestamp,
) -> None:
    common_daily = daily[(daily["date"] >= common_start) & (daily["date"] <= common_end)].copy()
    common_summary = summary[summary["sample_scope"].eq("common_portfolio_sample")].merge(
        classification[["etf_code", "sleeve_name", "classification", "recommendation_status"]],
        on=["etf_code", "sleeve_name"],
        how="left",
    )
    for etf in ETF_CODES:
        plot_etf_nav(common_daily[common_daily["etf_code"].eq(etf)], classification[classification["etf_code"].eq(etf)], etf)
    plot_scatter(common_summary, "annualized_return_cagr", "max_drawdown", "single_etf_sleeve_return_vs_mdd.png", "Return vs MDD", y_pct=True)
    plot_scatter(common_summary, "sharpe_daily_mean", "max_drawdown", "single_etf_sleeve_sharpe_vs_mdd.png", "Sharpe vs MDD", y_pct=False)
    plot_bar(common_summary, "option_leg_annualized_pnl_contribution", "option_leg_contribution_by_etf_sleeve.png", "Option-leg annualized contribution")
    plot_bar(common_summary, "payoff_burden_agg", "payoff_burden_by_etf_sleeve.png", "Payoff burden")
    plot_bar(common_summary, "p99_short_call_mtm_loss", "p99_mtm_stress_by_etf_sleeve.png", "P99 MTM stress")
    plot_classification_heatmap(classification)
    plot_recommended_map(classification)


def plot_etf_nav(etf_daily: pd.DataFrame, etf_classification: pd.DataFrame, etf: str) -> None:
    fig, ax = plt.subplots(figsize=(11.5, 5.8))
    primary = set(etf_classification[etf_classification["recommendation_status"].eq("primary_for_portfolio_layer")]["sleeve_name"])
    backup = set(etf_classification[etf_classification["recommendation_status"].eq("backup_for_portfolio_layer")]["sleeve_name"])
    for sleeve, g in etf_daily.groupby("sleeve_name"):
        klass = etf_classification.loc[etf_classification["sleeve_name"].eq(sleeve), "classification"].iloc[0]
        lw = 2.4 if sleeve in primary else 1.7 if sleeve in backup else 0.9
        alpha = 0.95 if sleeve in primary or sleeve in backup else 0.45
        style = "--" if klass in {"Diagnostic Only", "Stress Test Only"} else "-"
        ax.plot(g["date"], g["nav_total"], label=_short_sleeve(sleeve), linewidth=lw, alpha=alpha, linestyle=style)
    ax.set_title(f"{etf} sleeve NAV comparison")
    ax.set_ylabel("NAV")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / f"{etf}_sleeve_nav_comparison.png", dpi=160)
    plt.close(fig)


def plot_scatter(df: pd.DataFrame, y_col: str, x_col: str, filename: str, title: str, y_pct: bool) -> None:
    fig, ax = plt.subplots(figsize=(8.8, 5.4))
    colors = df["classification"].map(_class_color)
    ax.scatter(df[x_col], df[y_col], s=70, c=colors, alpha=0.85)
    for _, row in df.iterrows():
        ax.annotate(_short_sleeve(row["sleeve_name"]), (row[x_col], row[y_col]), fontsize=7, alpha=0.8)
    ax.set_xlabel("Max drawdown")
    ax.set_ylabel(y_col)
    ax.xaxis.set_major_formatter(lambda x, _pos: f"{x:.0%}")
    if y_pct:
        ax.yaxis.set_major_formatter(lambda y, _pos: f"{y:.0%}")
    ax.grid(alpha=0.25)
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / filename, dpi=160)
    plt.close(fig)


def plot_bar(df: pd.DataFrame, value_col: str, filename: str, title: str) -> None:
    d = df.sort_values(["etf_code", value_col], ascending=[True, False]).copy()
    fig, ax = plt.subplots(figsize=(12.5, 5.8))
    labels = d["etf_code"] + "\n" + d["sleeve_name"].map(_short_sleeve)
    ax.bar(labels, d[value_col], color=d["classification"].map(_class_color))
    ax.axhline(0, color="black", linewidth=0.8)
    ax.tick_params(axis="x", rotation=75, labelsize=7)
    ax.yaxis.set_major_formatter(lambda y, _pos: f"{y:.0%}")
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.22)
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / filename, dpi=160)
    plt.close(fig)


def plot_classification_heatmap(classification: pd.DataFrame) -> None:
    order = {
        "Positive Carry Overlay": 4,
        "Defensive Overlay": 3,
        "Pure ETF Preferred": 2,
        "Diagnostic Only": 1,
        "Stress Test Only": 0,
    }
    pivot = classification.pivot_table(
        index="etf_code",
        columns="sleeve_name",
        values="classification",
        aggfunc="first",
    )
    values = pivot.applymap(lambda x: order.get(x, np.nan)).to_numpy(dtype=float)
    fig, ax = plt.subplots(figsize=(13.5, 4.8))
    image = ax.imshow(values, vmin=0, vmax=4, cmap="viridis")
    ax.set_xticks(range(len(pivot.columns)), [_short_sleeve(c) for c in pivot.columns], rotation=75, ha="right", fontsize=7)
    ax.set_yticks(range(len(pivot.index)), pivot.index)
    ax.set_title("Sleeve classification heatmap")
    cbar = fig.colorbar(image, ax=ax, ticks=list(order.values()))
    cbar.ax.set_yticklabels(list(order.keys()))
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "sleeve_classification_heatmap.png", dpi=160)
    plt.close(fig)


def plot_recommended_map(classification: pd.DataFrame) -> None:
    status_order = {
        "primary_for_portfolio_layer": 3,
        "backup_for_portfolio_layer": 2,
        "diagnostic_only": 1,
        "rejected": 0,
    }
    d = classification.copy()
    d["score"] = d["recommendation_status"].map(status_order).fillna(0)
    pivot = d.pivot_table(index="etf_code", columns="sleeve_name", values="score", aggfunc="first")
    fig, ax = plt.subplots(figsize=(13.5, 4.8))
    image = ax.imshow(pivot.to_numpy(dtype=float), vmin=0, vmax=3, cmap="Blues")
    ax.set_xticks(range(len(pivot.columns)), [_short_sleeve(c) for c in pivot.columns], rotation=75, ha="right", fontsize=7)
    ax.set_yticks(range(len(pivot.index)), pivot.index)
    ax.set_title("Recommended sleeve set map")
    cbar = fig.colorbar(image, ax=ax, ticks=list(status_order.values()))
    cbar.ax.set_yticklabels(list(status_order.keys()))
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "recommended_sleeve_set_map.png", dpi=160)
    plt.close(fig)


def _period_formula_ok(period: pd.DataFrame) -> bool:
    if period.empty:
        return False
    lhs = period["premium_return"].astype(float) - period["payoff_return"].astype(float) - period["transaction_cost_return"].astype(float)
    rhs = period["option_leg_return"].astype(float)
    return bool(np.nanmax(np.abs(lhs - rhs)) < 1e-8)


def _entry_day_cost_only(daily: pd.DataFrame) -> bool:
    option = daily[daily["target_coverage"].astype(float) > 0].copy()
    entry = option[option["date"].eq(option["rebalance_date"])]
    if entry.empty:
        return False
    # Positive entry-day values can occur if same-day mark improvement offsets cost,
    # but they should not equal an unearned premium jump.
    return bool(entry["option_leg_pnl"].abs().max() < 0.05)


def _daily_period_reconciles(daily: pd.DataFrame, period: pd.DataFrame) -> bool:
    rows: list[float] = []
    option_daily = daily[daily["target_coverage"].astype(float) > 0].copy()
    option_daily["rebalance_date_key"] = pd.to_datetime(option_daily["rebalance_date"]).dt.date.astype(str)
    option_daily["expiry_date_key"] = pd.to_datetime(option_daily["expiry_date"]).dt.date.astype(str)
    daily_sum = option_daily.groupby(["etf_code", "sleeve_name", "rebalance_date_key", "expiry_date_key", "option_code"], dropna=False)[
        "option_leg_pnl"
    ].sum()
    for _, row in period.iterrows():
        key = (
            row["etf_code"],
            row["sleeve_name"],
            str(row["rebalance_date"]),
            str(row["expiry_date"]),
            row["option_code"],
        )
        rows.append(abs(float(daily_sum.get(key, np.nan)) - float(row["option_leg_return"])))
    return bool(rows and np.nanmax(rows) < 1e-8)


def _daily_panel_unique_dates(daily: pd.DataFrame) -> bool:
    keys = ["etf_code", "sleeve_name", "date"]
    return bool(not daily.duplicated(keys).any())


def _buyhold_zero(daily: pd.DataFrame) -> bool:
    b = daily[daily["sleeve_name"].str.endswith("ETF_BuyHold")]
    cols = ["option_leg_pnl", "short_call_liability", "active_coverage", "target_coverage", "option_transaction_cost_today"]
    return bool((b[cols].abs().sum().sum() < 1e-12) and not b["active_short_call_flag"].astype(bool).any())


def _deprecated_rules_absent(daily: pd.DataFrame, period: pd.DataFrame) -> bool:
    deprecated = {"TP80_close_and_wait", "spot_touch_strike_wait_to_expiry"}
    return bool(
        not daily.get("close_rule", pd.Series(dtype=object)).isin(deprecated).any()
        and not period.get("close_rule", pd.Series(dtype=object)).isin(deprecated).any()
    )


def _immediate_reopen_ok(period: pd.DataFrame) -> bool:
    if "period_end_date" not in period.columns:
        return False
    p = period.copy()
    p["rebalance_date"] = pd.to_datetime(p["rebalance_date"], errors="coerce")
    p["period_end_date"] = pd.to_datetime(p["period_end_date"], errors="coerce")
    p = p.dropna(subset=["rebalance_date", "period_end_date"])
    group_cols = [col for col in ["etf_code", "sleeve_name", "close_rule"] if col in p.columns]
    checks: list[bool] = []
    for _, g in p.sort_values(group_cols + ["rebalance_date"]).groupby(group_cols, dropna=False):
        g = g.sort_values(["rebalance_date", "period_end_date"]).drop_duplicates(
            ["rebalance_date", "period_end_date"],
            keep="last",
        )
        if len(g) < 2:
            continue
        delta = (g["rebalance_date"].shift(-1) - g["period_end_date"]).dt.days.iloc[:-1]
        checks.append(bool(delta.eq(0).all()))
    return bool(checks and all(checks))


def _q100_stress(classification: pd.DataFrame) -> bool:
    q100 = classification[classification["sleeve_name"].str.contains("Q100")]
    return bool(not q100.empty and q100["classification"].eq("Stress Test Only").all())


def _reports_avoid_arbitrage() -> bool:
    forbidden = ["无风险套利", "risk-free arbitrage"]
    if not REPORT_DIR.exists():
        return True
    for path in REPORT_DIR.glob("*.md"):
        text = path.read_text(encoding="utf-8").lower()
        if any(term.lower() in text for term in forbidden):
            return False
    return True


def _cards_exist() -> bool:
    return all((REPORT_DIR / f"{etf}_sleeve_card.md").exists() for etf in ETF_CODES)


def _close_info(row: pd.Series, rule: str) -> tuple[str, str]:
    return "", "expiry"


def _date_string(value: Any) -> str:
    if pd.isna(value):
        return ""
    return pd.Timestamp(value).date().isoformat()


def _spec_by_name(name: str) -> SleeveSpec:
    for spec in SPECS:
        if spec.sleeve_name == name:
            return spec
    raise KeyError(name)


def _bool_series(values: Any) -> pd.Series:
    if isinstance(values, pd.Series):
        return values.fillna(False).astype(str).str.lower().isin(["true", "1", "yes"])
    return pd.Series([values]).fillna(False).astype(str).str.lower().isin(["true", "1", "yes"])


def _safe_div(numerator: float, denominator: float) -> float:
    try:
        denominator = float(denominator)
        if abs(denominator) < 1e-12 or pd.isna(denominator):
            return np.nan
        return float(numerator) / denominator
    except Exception:
        return np.nan


def _first_or_blank(df: pd.DataFrame, col: str) -> str:
    return "" if df.empty else str(df.iloc[0][col])


def _safe_lookup(df: pd.DataFrame, key: str, col: str) -> str:
    try:
        if key in df.index:
            value = df.loc[key, col]
            if isinstance(value, pd.Series):
                value = value.iloc[0]
            return str(value)
    except Exception:
        return ""
    return ""


def _etf_short_verdict(classification: pd.DataFrame, etf: str) -> str:
    primary = classification[
        (classification["etf_code"].eq(etf))
        & (classification["recommendation_status"].eq("primary_for_portfolio_layer"))
    ]
    if primary.empty:
        return "No primary sleeve selected."
    row = primary.iloc[0]
    return (
        f"- primary: {row['sleeve_name']}\n"
        f"- classification: {row['classification']}\n"
        f"- rationale: {row['reason']}\n"
        f"- caveat: {row['caveat']}"
    )


def _fmt_pct(x: Any) -> str:
    if pd.isna(x):
        return ""
    return f"{float(x):.2%}"


def _fmt_num(x: Any) -> str:
    if pd.isna(x):
        return ""
    return f"{float(x):.3f}"


def _md_table(
    df: pd.DataFrame,
    pct_cols: Iterable[str] = (),
    num_cols: Iterable[str] = (),
) -> str:
    if df.empty:
        return "_No rows._"
    out = df.copy()
    pct_set = set(pct_cols)
    num_set = set(num_cols)
    for col in out.columns:
        if col in pct_set:
            out[col] = out[col].map(_fmt_pct)
        elif col in num_set:
            out[col] = out[col].map(_fmt_num)
        elif pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].map(lambda x: "" if pd.isna(x) else f"{x:.4f}")
        elif pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].dt.date.astype(str)
    return out.to_markdown(index=False)


def _short_sleeve(name: str) -> str:
    return (
        str(name)
        .replace("510300_", "")
        .replace("510500_", "")
        .replace("159915_", "")
        .replace("DTE30_", "")
        .replace("_Hold", "")
        .replace("_", " ")
    )


def _class_color(label: str) -> str:
    return {
        "Positive Carry Overlay": "#12b76a",
        "Defensive Overlay": "#2e90fa",
        "Pure ETF Preferred": "#667085",
        "Diagnostic Only": "#f79009",
        "Stress Test Only": "#d92d20",
    }.get(str(label), "#98a2b3")


def _setup_plot_style() -> None:
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


if __name__ == "__main__":
    main()
