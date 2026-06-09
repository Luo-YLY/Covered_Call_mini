from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.backtest.accounting import assert_accounting_identity, covered_call_period_return
from src.backtest.engine import run_fixed_covered_call_backtest
from src.backtest.metrics import summarize_performance
from src.backtest.transaction_costs import proportional_cost
from src.data.loaders import load_metadata
from src.data.validators import data_quality_report, validate_etf_prices, validate_options
from src.features.delta_surface import build_delta_enriched_options
from src.features.iv_timing import build_30d_atm_iv_signals
from src.features.suitability import build_suitability_screen
from src.options.selection import option_mid_price
from src.utils.dates import month_end_roll_dates


EXECUTABLE_STRATEGIES = [
    "S0_BuyHold",
    "S1_ATM_100_Monthly",
    "S4_OTM5_100_Monthly",
    "S5_IVTiming_ATM_Monthly",
    "S6_IVTiming_OTM5_Monthly",
]

CLOSE_RULE_V1 = {
    "rule_id": "CloseRule_v1",
    "profit_take_ratio": 0.50,
    "broad_base_ultra_low_percentile": 0.15,
    "growth_close_percentile": 0.70,
}

IV_RULE_PROFILES = [
    {
        "rule_id": "RuleA_Current",
        "rule_name": "当前保守版",
        "warmup_invalid_coverage_ratio": 0.00,
        "data_invalid_coverage_ratio": 0.00,
        "low_iv_coverage_ratio": 0.00,
        "normal_iv_coverage_ratio": 0.50,
        "high_iv_coverage_ratio": 1.00,
    },
    {
        "rule_id": "RuleB_BroadBaseEnhanced",
        "rule_name": "宽基增强版",
        "warmup_invalid_coverage_ratio": 1.00,
        "data_invalid_coverage_ratio": 0.00,
        "low_iv_coverage_ratio": 0.50,
        "normal_iv_coverage_ratio": 0.75,
        "high_iv_coverage_ratio": 1.00,
    },
    {
        "rule_id": "RuleC_GrowthDefensive",
        "rule_name": "成长防守版",
        "warmup_invalid_coverage_ratio": 0.00,
        "data_invalid_coverage_ratio": 0.00,
        "low_iv_coverage_ratio": 0.00,
        "normal_iv_coverage_ratio": 0.25,
        "high_iv_coverage_ratio": 0.75,
    },
    {
        "rule_id": "RuleD_HighIVOnly",
        "rule_name": "高IV-only版",
        "warmup_invalid_coverage_ratio": 0.00,
        "data_invalid_coverage_ratio": 0.00,
        "low_iv_coverage_ratio": 0.00,
        "normal_iv_coverage_ratio": 0.00,
        "high_iv_coverage_ratio": 1.00,
    },
]

IV_RULE_EXPERIMENT_SPECS = [
    ("core_atm", "ATM核心检验", "S5_IVTiming_ATM_Monthly"),
    ("otm5_check", "OTM5稳健性检查", "S6_IVTiming_OTM5_Monthly"),
]

STYLE_RULE_V1 = {
    "510300": {
        "style_group": "broad_base",
        "recommended_rule": "RuleB_BroadBaseEnhanced",
        "recommended_moneyness": "atm",
        "recommended_stage": "core_atm",
        "reason": "核心宽基，低IV也保留少量覆盖，增强长期权利金收取。",
    },
    "510050": {
        "style_group": "broad_base",
        "recommended_rule": "RuleB_BroadBaseEnhanced",
        "recommended_moneyness": "atm",
        "recommended_stage": "core_atm",
        "reason": "大盘蓝筹宽基，固定ATM备兑有效，低IV不完全跳过更符合收租属性。",
    },
    "588000": {
        "style_group": "growth_high_beta",
        "recommended_rule": "RuleD_HighIVOnly",
        "recommended_moneyness": "otm5",
        "recommended_stage": "otm5_check",
        "reason": "科创高弹性标的，上涨截断风险高，仅在高IV且更虚值时卖出。",
    },
    "159915": {
        "style_group": "growth_high_beta",
        "recommended_rule": "RuleD_HighIVOnly",
        "recommended_moneyness": "otm5",
        "recommended_stage": "otm5_check",
        "reason": "创业板高弹性标的，normal IV卖出容易损失反弹，优先高IV-only。",
    },
    "510500": {
        "style_group": "growth_high_beta",
        "recommended_rule": "RuleD_HighIVOnly",
        "recommended_moneyness": "otm5",
        "recommended_stage": "otm5_check",
        "reason": "中盘成长属性较强，采用高IV-only降低趋势行情中的截断成本。",
    },
}

CONFIG = {
    "backtest": {
        "start_date": None,
        "end_date": None,
        "initial_nav": 1.0,
        "roll_frequency": "monthly",
        "target_dte": 30,
        "min_days_to_expiry": 20,
        "max_days_to_expiry": 45,
        "assume_no_early_exercise": True,
    },
    "liquidity_filters": {
        "min_option_volume": 0,
        "min_open_interest": 0,
        "max_bid_ask_spread_pct": 0.20,
    },
    "transaction_costs": {
        "option_slippage_bps": 5,
        "etf_slippage_bps": 2,
        "option_commission_per_contract": 0,
        "use_bid_ask_spread_cost": True,
    },
    "suitability_weights": {
        "etf_liquidity_score": 0.20,
        "option_availability_score": 0.25,
        "option_liquidity_score": 0.25,
        "premium_adequacy_score": 0.15,
        "upside_truncation_risk_score": 0.10,
        "data_quality_score": 0.05,
    },
    "strategies": EXECUTABLE_STRATEGIES,
    "iv_timing": {
        "target_dte": 30,
        "min_days_to_expiry": 20,
        "max_days_to_expiry": 45,
        "risk_free_rate": 0.02,
        "percentile_window": 252,
        "min_percentile_observations": 252,
        "low_iv_percentile": 0.30,
        "high_iv_percentile": 0.70,
        "normal_iv_coverage_ratio": 0.50,
        "high_iv_coverage_ratio": 1.00,
    },
    "delta_standardization": {
        "risk_free_rate": 0.02,
    },
    "hard_gates": {
        "min_data_completeness_ratio": 0.80,
        "min_trading_days": 252,
        "require_options": True,
        "require_eligible_rolls": True,
    },
}


def _write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def _load_raw_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, str]:
    raw_dir = ROOT / "data" / "raw"
    prices = validate_etf_prices(pd.read_csv(raw_dir / "etf_prices.csv"))
    raw_options = pd.read_csv(raw_dir / "options.csv")
    options = validate_options(raw_options, keep_calls_only=True)
    iv_option_path = raw_dir / "options_daily.csv"
    iv_option_source = "options_daily.csv" if iv_option_path.exists() else "options.csv"
    iv_raw_options = pd.read_csv(raw_dir / iv_option_source)
    options_all = validate_options(iv_raw_options, keep_calls_only=False)
    metadata = load_metadata(raw_dir / "etf_metadata.csv", prices)
    metadata["etf_code"] = metadata["etf_code"].astype(str)
    return prices, options, options_all, metadata, iv_option_source


def _apply_hard_gate_scores(scores: pd.DataFrame, screen: pd.DataFrame) -> pd.DataFrame:
    gates = CONFIG["hard_gates"]
    out = scores.merge(
        screen[
            [
                "etf_code",
                "has_options",
                "eligible_roll_date_ratio",
                "data_completeness_ratio",
                "number_of_trading_days",
            ]
        ],
        on="etf_code",
        how="left",
    )
    out = out.rename(columns={"suitability_score": "soft_suitability_score"})
    out["hard_gate_has_options"] = out["has_options"].fillna(False).astype(int)
    out["hard_gate_eligible_rolls"] = (
        pd.to_numeric(out["eligible_roll_date_ratio"], errors="coerce").fillna(0) > 0
    ).astype(int)
    out["hard_gate_data_completeness"] = (
        pd.to_numeric(out["data_completeness_ratio"], errors="coerce").fillna(0)
        >= gates["min_data_completeness_ratio"]
    ).astype(int)
    out["hard_gate_trading_days"] = (
        pd.to_numeric(out["number_of_trading_days"], errors="coerce").fillna(0)
        >= gates["min_trading_days"]
    ).astype(int)

    gate_cols = ["hard_gate_data_completeness", "hard_gate_trading_days"]
    if gates["require_options"]:
        gate_cols.append("hard_gate_has_options")
    if gates["require_eligible_rolls"]:
        gate_cols.append("hard_gate_eligible_rolls")
    out["hard_gate_all"] = out[gate_cols].prod(axis=1)
    out["suitability_score"] = out["soft_suitability_score"] * out["hard_gate_all"]
    return out.sort_values(
        ["hard_gate_all", "suitability_score", "soft_suitability_score"],
        ascending=[False, False, False],
    ).reset_index(drop=True)


def _filter_to_top5(
    prices: pd.DataFrame,
    options: pd.DataFrame,
    metadata: pd.DataFrame,
    top5: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    top5_set = set(top5)
    return (
        prices[prices["etf_code"].isin(top5_set)].copy(),
        options[options["underlying_etf"].isin(top5_set)].copy(),
        metadata[metadata["etf_code"].isin(top5_set)].copy(),
    )


def _with_iv_rule_profile(config: dict, profile: dict, strategy: str) -> dict:
    out = {
        **config,
        "strategies": [strategy],
        "iv_timing": {
            **config["iv_timing"],
            "warmup_invalid_coverage_ratio": profile["warmup_invalid_coverage_ratio"],
            "data_invalid_coverage_ratio": profile["data_invalid_coverage_ratio"],
            "low_iv_coverage_ratio": profile["low_iv_coverage_ratio"],
            "normal_iv_coverage_ratio": profile["normal_iv_coverage_ratio"],
            "high_iv_coverage_ratio": profile["high_iv_coverage_ratio"],
        },
    }
    return out


def _build_iv_rule_experiments(
    prices: pd.DataFrame,
    options: pd.DataFrame,
    metadata: pd.DataFrame,
    iv_signals: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    period_parts = []
    summary_parts = []

    for stage_id, stage_name, strategy in IV_RULE_EXPERIMENT_SPECS:
        for profile in IV_RULE_PROFILES:
            cfg = _with_iv_rule_profile(CONFIG, profile, strategy)
            periods, _ = run_fixed_covered_call_backtest(prices, options, metadata, cfg, iv_signals)
            if periods.empty:
                continue
            periods = periods.copy()
            periods["experiment_stage"] = stage_id
            periods["experiment_stage_name"] = stage_name
            periods["rule_id"] = profile["rule_id"]
            periods["rule_name"] = profile["rule_name"]
            periods["rule_warmup_invalid_coverage"] = profile["warmup_invalid_coverage_ratio"]
            periods["rule_data_invalid_coverage"] = profile["data_invalid_coverage_ratio"]
            periods["rule_low_coverage"] = profile["low_iv_coverage_ratio"]
            periods["rule_normal_coverage"] = profile["normal_iv_coverage_ratio"]
            periods["rule_high_coverage"] = profile["high_iv_coverage_ratio"]
            periods["experiment_strategy"] = periods["rule_id"] + "_" + stage_id
            period_parts.append(periods)

            summary, _ = summarize_performance(periods)
            summary = summary.copy()
            summary["experiment_stage"] = stage_id
            summary["experiment_stage_name"] = stage_name
            summary["rule_id"] = profile["rule_id"]
            summary["rule_name"] = profile["rule_name"]
            summary["rule_warmup_invalid_coverage"] = profile["warmup_invalid_coverage_ratio"]
            summary["rule_data_invalid_coverage"] = profile["data_invalid_coverage_ratio"]
            summary["rule_low_coverage"] = profile["low_iv_coverage_ratio"]
            summary["rule_normal_coverage"] = profile["normal_iv_coverage_ratio"]
            summary["rule_high_coverage"] = profile["high_iv_coverage_ratio"]
            summary["base_strategy"] = strategy
            summary_parts.append(summary)

    periods_out = pd.concat(period_parts, ignore_index=True) if period_parts else pd.DataFrame()
    summary_out = pd.concat(summary_parts, ignore_index=True) if summary_parts else pd.DataFrame()
    return periods_out, summary_out


def _style_group(etf_code: object) -> str:
    return STYLE_RULE_V1.get(str(etf_code).zfill(6), {}).get("style_group", "other")


def _build_style_rule_diagnostics(
    iv_rule_periods: pd.DataFrame,
    iv_rule_summary: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    summary = iv_rule_summary.copy()
    periods = iv_rule_periods.copy()
    if summary.empty or periods.empty:
        empty = pd.DataFrame()
        return empty, empty, empty, empty, empty

    summary["etf_code"] = summary["etf_code"].astype(str).str.zfill(6)
    periods["etf_code"] = periods["etf_code"].astype(str).str.zfill(6)
    summary["style_group"] = summary["etf_code"].map(_style_group)
    periods["style_group"] = periods["etf_code"].map(_style_group)

    by_style = (
        summary.groupby(["style_group", "experiment_stage", "experiment_stage_name", "rule_id", "rule_name"])
        .agg(
            etf_count=("etf_code", "nunique"),
            avg_annualized_return=("annualized_return", "mean"),
            avg_excess_return_annualized=("excess_return_annualized", "mean"),
            avg_max_drawdown=("max_drawdown", "mean"),
            avg_net_option_contribution=("net_option_contribution", "mean"),
            avg_coverage_ratio=("average_coverage_ratio", "mean"),
            avg_assignment_frequency=("assignment_frequency", "mean"),
            avg_option_sale_success_rate=("option_sale_success_rate", "mean"),
        )
        .reset_index()
    )

    by_regime = (
        periods.groupby(
            [
                "etf_code",
                "style_group",
                "experiment_stage",
                "experiment_stage_name",
                "rule_id",
                "rule_name",
                "iv_regime",
            ]
        )
        .agg(
            periods=("R_cc", "size"),
            selected_periods=("option_selected_flag", "sum"),
            avg_etf_return=("R_etf", "mean"),
            avg_strategy_return=("R_cc", "mean"),
            premium_contribution=("premium_yield", "sum"),
            upside_cost=("upside_cost", "sum"),
            transaction_cost=("cost", "sum"),
            net_option_contribution=("net_option_contribution", "sum"),
            assignment_frequency=("assignment_flag", "mean"),
            avg_coverage_ratio=("coverage_ratio", "mean"),
        )
        .reset_index()
    )

    rec_rows = []
    for etf_code, rec in STYLE_RULE_V1.items():
        match = summary[
            (summary["etf_code"] == etf_code)
            & (summary["rule_id"] == rec["recommended_rule"])
            & (summary["experiment_stage"] == rec["recommended_stage"])
        ]
        row = {
            "etf_code": etf_code,
            **rec,
        }
        if not match.empty:
            metrics = match.iloc[0]
            row.update(
                {
                    "annualized_return": metrics["annualized_return"],
                    "excess_return_annualized": metrics["excess_return_annualized"],
                    "max_drawdown": metrics["max_drawdown"],
                    "net_option_contribution": metrics["net_option_contribution"],
                    "average_coverage_ratio": metrics["average_coverage_ratio"],
                    "option_sale_success_rate": metrics["option_sale_success_rate"],
                }
            )
        rec_rows.append(row)
    recommendations = pd.DataFrame(rec_rows)

    combo_periods = []
    for _, rec in recommendations.iterrows():
        selected = periods[
            (periods["etf_code"] == rec["etf_code"])
            & (periods["rule_id"] == rec["recommended_rule"])
            & (periods["experiment_stage"] == rec["recommended_stage"])
        ].copy()
        if selected.empty:
            continue
        selected["strategy"] = "S7_IVStyleRule_v1"
        selected["style_rule_group"] = rec["style_group"]
        selected["style_rule_reason"] = rec["reason"]
        combo_periods.append(selected)
    style_periods = pd.concat(combo_periods, ignore_index=True) if combo_periods else pd.DataFrame()
    style_summary = summarize_performance(style_periods)[0] if not style_periods.empty else pd.DataFrame()
    if not style_summary.empty:
        style_summary["strategy"] = "S7_IVStyleRule_v1"
    return by_style, by_regime, recommendations, style_periods, style_summary


def _price_on(price_g: pd.DataFrame, date: pd.Timestamp) -> float:
    row = price_g[price_g["date"] == pd.Timestamp(date)]
    if row.empty:
        raise ValueError(f"No ETF price for {date}")
    return float(row.iloc[0]["adj_close"])


def _next_roll_date(price_dates: pd.Series, roll_date: pd.Timestamp) -> pd.Timestamp:
    roll_dates = list(month_end_roll_dates(price_dates))
    idx = roll_dates.index(pd.Timestamp(roll_date))
    return pd.Timestamp(roll_dates[idx + 1])


def _option_price_on(options: pd.DataFrame, option_code: object, trade_date: pd.Timestamp) -> tuple[float, str, float] | None:
    if pd.isna(option_code):
        return None
    row = options[
        (options["option_code"].astype(str) == str(option_code))
        & (options["trade_date"] == pd.Timestamp(trade_date))
    ]
    if row.empty:
        return None
    return option_mid_price(row.iloc[0])


def _style_close_threshold(style_group: str) -> float:
    if style_group == "broad_base":
        return CLOSE_RULE_V1["broad_base_ultra_low_percentile"]
    if style_group == "growth_high_beta":
        return CLOSE_RULE_V1["growth_close_percentile"]
    return CLOSE_RULE_V1["growth_close_percentile"]


def _find_close_trigger(
    row: pd.Series,
    options: pd.DataFrame,
    iv_signals: pd.DataFrame,
    price_dates: pd.Series,
) -> dict[str, object] | None:
    option_code = row.get("option_code", np.nan)
    if pd.isna(option_code):
        return None
    open_premium = float(row["C0"])
    if open_premium <= 0:
        return None

    roll_date = pd.Timestamp(row["roll_date"])
    end_date = pd.Timestamp(row["end_date"])
    etf_code = str(row["etf_code"]).zfill(6)
    style_group = str(row.get("style_group", "other"))
    close_iv_threshold = _style_close_threshold(style_group)
    max_buyback = open_premium * CLOSE_RULE_V1["profit_take_ratio"]

    dates = price_dates[(price_dates > roll_date) & (price_dates <= end_date)]
    iv_g = iv_signals[iv_signals["etf_code"].astype(str).str.zfill(6) == etf_code].copy()
    iv_g["trade_date"] = pd.to_datetime(iv_g["trade_date"])

    for trade_date in dates:
        iv_row = iv_g[iv_g["trade_date"] == pd.Timestamp(trade_date)]
        if iv_row.empty:
            continue
        iv_percentile = iv_row.iloc[0].get("iv_percentile_252", np.nan)
        if pd.isna(iv_percentile) or float(iv_percentile) >= close_iv_threshold:
            continue
        price_info = _option_price_on(options, option_code, pd.Timestamp(trade_date))
        if price_info is None:
            continue
        buyback_price, price_source, spread_pct = price_info
        if buyback_price <= max_buyback:
            return {
                "close_date": pd.Timestamp(trade_date),
                "close_buyback_price": float(buyback_price),
                "close_price_source": price_source,
                "close_bid_ask_spread_pct": spread_pct,
                "close_iv_percentile": float(iv_percentile),
                "close_iv_threshold": close_iv_threshold,
            }
    return None


def _build_style_rule_close_v1(
    style_periods: pd.DataFrame,
    prices: pd.DataFrame,
    options_all: pd.DataFrame,
    iv_signals: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if style_periods.empty:
        return pd.DataFrame(), pd.DataFrame()

    parts = []
    prices = prices.copy()
    prices["etf_code"] = prices["etf_code"].astype(str).str.zfill(6)
    options_all = options_all.copy()
    options_all["trade_date"] = pd.to_datetime(options_all["trade_date"])
    iv_signals = iv_signals.copy()
    iv_signals["etf_code"] = iv_signals["etf_code"].astype(str).str.zfill(6)

    for etf_code, g in style_periods.groupby(style_periods["etf_code"].astype(str).str.zfill(6)):
        price_g = prices[prices["etf_code"] == etf_code].sort_values("date")
        price_dates = price_g["date"]
        option_g = options_all[options_all["underlying_etf"].astype(str).str.zfill(6) == etf_code]
        for _, row in g.sort_values("roll_date").iterrows():
            out = row.copy()
            out["strategy"] = "S8_IVStyleRule_Close_v1"
            out["close_rule"] = CLOSE_RULE_V1["rule_id"]
            out["close_triggered"] = 0
            out["close_date"] = pd.NaT
            out["close_buyback_price"] = np.nan
            out["close_buyback_yield"] = 0.0
            out["close_price_source"] = "none"
            out["close_iv_percentile"] = np.nan
            out["close_iv_threshold"] = _style_close_threshold(str(row.get("style_group", "other")))
            out["close_days_held"] = np.nan

            roll_date = pd.Timestamp(row["roll_date"])
            next_roll = _next_roll_date(price_dates, roll_date)
            spot_start = float(row["S0"])
            style_group = str(row.get("style_group", "other"))
            iv_pct = row.get("iv_percentile_252", np.nan)

            ultra_low_entry_skip = (
                style_group == "broad_base"
                and pd.notna(iv_pct)
                and float(iv_pct) < CLOSE_RULE_V1["broad_base_ultra_low_percentile"]
            )
            if ultra_low_entry_skip:
                spot_end = _price_on(price_g, next_roll)
                accounting = covered_call_period_return(spot_start, spot_end, None, 0.0, 0.0, 0.0)
                out["end_date"] = next_roll
                out["ST"] = spot_end
                out["K"] = np.nan
                out["C0"] = 0.0
                out["coverage_ratio"] = 0.0
                out["option_selected_flag"] = 0
                out["selection_reason"] = "ultra_low_iv_skip"
                out["iv_timing_action"] = "ultra_low_iv_skip"
                out["price_source"] = "none"
                out["option_code"] = np.nan
                out["moneyness"] = np.nan
                for key, value in accounting.items():
                    out[key] = value
                parts.append(out)
                continue

            if int(row.get("option_selected_flag", 0)) != 1 or float(row.get("coverage_ratio", 0.0)) <= 0:
                parts.append(out)
                continue

            trigger = _find_close_trigger(row, option_g, iv_signals, price_dates)
            if trigger is None:
                parts.append(out)
                continue

            spot_end = _price_on(price_g, next_roll)
            coverage = float(row["coverage_ratio"])
            premium = float(row["C0"])
            buyback = float(trigger["close_buyback_price"])
            open_cost = float(row.get("cost", 0.0))
            close_cost = proportional_cost(
                buyback,
                spot_start,
                coverage,
                CONFIG["transaction_costs"],
                trigger.get("close_bid_ask_spread_pct"),
            )
            r_etf = (spot_end - spot_start) / spot_start
            premium_yield = coverage * premium / spot_start
            buyback_yield = coverage * buyback / spot_start
            total_cost = open_cost + close_cost
            net_option = premium_yield - buyback_yield - total_cost
            r_cc = r_etf + net_option

            out["end_date"] = next_roll
            out["ST"] = spot_end
            out["close_triggered"] = 1
            out["close_date"] = trigger["close_date"]
            out["close_buyback_price"] = buyback
            out["close_buyback_yield"] = buyback_yield
            out["close_price_source"] = trigger["close_price_source"]
            out["close_iv_percentile"] = trigger["close_iv_percentile"]
            out["close_iv_threshold"] = trigger["close_iv_threshold"]
            out["close_days_held"] = (pd.Timestamp(trigger["close_date"]) - roll_date).days
            out["R_etf"] = float(r_etf)
            out["premium_yield"] = float(premium_yield)
            out["upside_cost"] = float(buyback_yield)
            out["cost"] = float(total_cost)
            out["R_cc"] = float(r_cc)
            out["excess_return"] = float(net_option)
            out["assignment_flag"] = 0
            out["premium_contribution"] = float(premium_yield)
            out["upside_cost_contribution"] = float(-buyback_yield)
            out["transaction_cost_contribution"] = float(-total_cost)
            out["net_option_contribution"] = float(net_option)
            assert_accounting_identity(out.to_dict())
            parts.append(out)

    periods = pd.DataFrame(parts)
    summary = summarize_performance(periods)[0] if not periods.empty else pd.DataFrame()
    if not summary.empty:
        summary["strategy"] = "S8_IVStyleRule_Close_v1"
        close_stats = (
            periods.groupby("etf_code")
            .agg(
                close_trigger_rate=("close_triggered", "mean"),
                avg_days_to_close=("close_days_held", "mean"),
                close_buyback_cost=("close_buyback_yield", "sum"),
            )
            .reset_index()
        )
        summary = summary.merge(close_stats, on="etf_code", how="left")
    return periods, summary


def _build_valid_iv_sample_summary(periods: pd.DataFrame, iv_signals: pd.DataFrame) -> pd.DataFrame:
    if periods.empty or iv_signals.empty:
        return pd.DataFrame()
    signals = iv_signals.copy()
    signals["etf_code"] = signals["etf_code"].astype(str).str.zfill(6)
    signals["trade_date"] = pd.to_datetime(signals["trade_date"])
    first_valid = (
        signals[signals["signal_valid"] == 1]
        .groupby("etf_code")["trade_date"]
        .min()
        .to_dict()
    )
    sample = periods.copy()
    sample["etf_code"] = sample["etf_code"].astype(str).str.zfill(6)
    sample["roll_date"] = pd.to_datetime(sample["roll_date"])
    sample["valid_iv_sample_start"] = sample["etf_code"].map(first_valid)
    sample = sample[
        sample["valid_iv_sample_start"].notna()
        & (sample["roll_date"] >= sample["valid_iv_sample_start"])
    ].copy()
    if sample.empty:
        return pd.DataFrame()
    summary = summarize_performance(sample)[0]
    summary["valid_iv_sample"] = True
    summary["valid_iv_sample_start"] = summary["etf_code"].map(first_valid)
    return summary


def build_source_from_raw() -> dict[str, object]:
    prices, options, options_all, metadata, iv_option_source = _load_raw_data()
    source_dir = ROOT / "data" / "source"

    quality = data_quality_report(prices, options)
    screen, base_scores = build_suitability_screen(prices, options, metadata, CONFIG)
    scores = _apply_hard_gate_scores(base_scores, screen)
    scores["synthetic_demo"] = False
    screen["synthetic_demo"] = False
    quality["synthetic_demo"] = False
    top5 = scores.head(5)["etf_code"].astype(str).tolist()

    top_prices, top_options, top_metadata = _filter_to_top5(prices, options, metadata, top5)
    top_options_all = options_all[options_all["underlying_etf"].isin(set(top5))].copy()
    delta_enriched_options = build_delta_enriched_options(top_prices, top_options_all, CONFIG)
    top_options = build_delta_enriched_options(top_prices, top_options, CONFIG)
    iv_signals = build_30d_atm_iv_signals(top_prices, top_options_all, CONFIG)
    periods, nav = run_fixed_covered_call_backtest(top_prices, top_options, top_metadata, CONFIG, iv_signals)
    iv_rule_periods, iv_rule_summary = _build_iv_rule_experiments(
        top_prices,
        top_options,
        top_metadata,
        iv_signals,
    )
    periods["synthetic_demo"] = False
    nav["synthetic_demo"] = False
    if not iv_rule_periods.empty:
        iv_rule_periods["synthetic_demo"] = False
    if not iv_rule_summary.empty:
        iv_rule_summary["synthetic_demo"] = False
    (
        iv_rule_by_style,
        iv_rule_by_regime,
        iv_rule_recommendation,
        style_rule_periods,
        style_rule_summary,
    ) = _build_style_rule_diagnostics(iv_rule_periods, iv_rule_summary)
    style_rule_close_periods, style_rule_close_summary = _build_style_rule_close_v1(
        style_rule_periods,
        top_prices,
        top_options_all,
        iv_signals,
    )
    if not style_rule_periods.empty:
        style_rule_periods["synthetic_demo"] = False
    if not style_rule_summary.empty:
        style_rule_summary["synthetic_demo"] = False
    if not style_rule_close_periods.empty:
        style_rule_close_periods["synthetic_demo"] = False
    if not style_rule_close_summary.empty:
        style_rule_close_summary["synthetic_demo"] = False
    valid_iv_sample_summary = _build_valid_iv_sample_summary(
        pd.concat(
            [df for df in [periods, style_rule_periods, style_rule_close_periods] if not df.empty],
            ignore_index=True,
            sort=False,
        ),
        iv_signals,
    )
    if not valid_iv_sample_summary.empty:
        valid_iv_sample_summary["synthetic_demo"] = False
    if not iv_signals.empty:
        iv_signals["synthetic_demo"] = False
        iv_signals["iv_option_source"] = iv_option_source
    perf, _ = summarize_performance(periods)

    strategy_rank = {strategy: i for i, strategy in enumerate(EXECUTABLE_STRATEGIES)}
    etf_rank = {etf: i for i, etf in enumerate(top5)}
    perf["etf_rank"] = perf["etf_code"].map(etf_rank)
    perf["strategy_rank"] = perf["strategy"].map(strategy_rank)
    perf = perf.sort_values(["etf_rank", "strategy_rank"]).drop(columns=["etf_rank", "strategy_rank"])
    periods["etf_rank"] = periods["etf_code"].map(etf_rank)
    periods["strategy_rank"] = periods["strategy"].map(strategy_rank)
    periods = periods.sort_values(["etf_rank", "strategy_rank", "roll_date"]).drop(
        columns=["etf_rank", "strategy_rank"]
    )

    _write_csv(quality, source_dir / "data_quality_report.csv")
    _write_csv(screen, source_dir / "etf_universe_screen.csv")
    _write_csv(scores, source_dir / "etf_suitability_scores.csv")
    _write_csv(pd.DataFrame({"rank": range(1, len(top5) + 1), "etf_code": top5}), source_dir / "selected_top5_etfs.csv")
    _write_csv(delta_enriched_options, source_dir / "delta_enriched_options.csv")
    _write_csv(iv_signals, source_dir / "iv_timing_signals.csv")
    _write_csv(iv_rule_periods, source_dir / "iv_rule_experiment_periods.csv")
    _write_csv(iv_rule_summary, source_dir / "iv_rule_experiment_summary.csv")
    _write_csv(iv_rule_by_style, source_dir / "iv_rule_experiment_by_style.csv")
    _write_csv(iv_rule_by_regime, source_dir / "iv_rule_regime_decomposition.csv")
    _write_csv(iv_rule_recommendation, source_dir / "iv_rule_recommendation.csv")
    _write_csv(style_rule_periods, source_dir / "iv_style_rule_v1_periods.csv")
    _write_csv(style_rule_summary, source_dir / "iv_style_rule_v1_summary.csv")
    _write_csv(style_rule_close_periods, source_dir / "iv_style_rule_close_v1_periods.csv")
    _write_csv(style_rule_close_summary, source_dir / "iv_style_rule_close_v1_summary.csv")
    _write_csv(valid_iv_sample_summary, source_dir / "iv_valid_sample_strategy_summary.csv")
    _write_csv(perf, source_dir / "fixed_cc_strategy_summary.csv")
    _write_csv(periods, source_dir / "pnl_decomposition_by_roll.csv")
    _write_csv(nav, source_dir / "nav_by_strategy.csv")

    return {
        "top5": top5,
        "scores": scores,
        "screen": screen,
        "periods": periods,
        "nav": nav,
        "perf": perf,
        "iv_signals": iv_signals,
        "delta_enriched_options": delta_enriched_options,
        "iv_rule_periods": iv_rule_periods,
        "iv_rule_summary": iv_rule_summary,
        "iv_rule_by_style": iv_rule_by_style,
        "iv_rule_by_regime": iv_rule_by_regime,
        "iv_rule_recommendation": iv_rule_recommendation,
        "style_rule_periods": style_rule_periods,
        "style_rule_summary": style_rule_summary,
        "style_rule_close_periods": style_rule_close_periods,
        "style_rule_close_summary": style_rule_close_summary,
        "valid_iv_sample_summary": valid_iv_sample_summary,
        "iv_option_source": iv_option_source,
    }


def main() -> None:
    result = build_source_from_raw()
    print("Raw-data mini source tables rebuilt.")
    print("Top 5 ETFs:", ", ".join(result["top5"]))
    print("IV option source:", result["iv_option_source"])


if __name__ == "__main__":
    main()
