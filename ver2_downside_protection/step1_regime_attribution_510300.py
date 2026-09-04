from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


LOGGER = logging.getLogger(__name__)

ETF_CODE = "510300"
LOW_SAMPLE_THRESHOLD = 5

MAIN_CANDIDATES: tuple[tuple[str, str], ...] = (
    ("DTE30", "BuyHold"),
    ("DTE30", "ATM_100"),
    ("DTE30", "D50_100"),
    ("DTE30", "D40_100"),
    ("DTE30", "OTM2_100"),
)

APPENDIX_REFERENCE: tuple[tuple[str, str], ...] = (
    ("DTE60", "ATM_100"),
    ("DTE60", "D50_100"),
    ("DTE60", "D40_100"),
    ("DTE60", "OTM2_100"),
)

CANDIDATE_ROLES: dict[tuple[str, str], str] = {
    ("DTE30", "BuyHold"): "benchmark",
    ("DTE30", "ATM_100"): "defensive_benchmark",
    ("DTE30", "D50_100"): "near_atm_alternative",
    ("DTE30", "D40_100"): "current_main_candidate",
    ("DTE30", "OTM2_100"): "upside_participation_lower_delta_reference",
    **{key: "appendix_reference" for key in APPENDIX_REFERENCE},
}

CANDIDATE_ORDER = {
    "BuyHold": 0,
    "DTE30_ATM_100": 1,
    "DTE30_D50_100": 2,
    "DTE30_D40_100": 3,
    "DTE30_OTM2_100": 4,
    "DTE60_ATM_100": 10,
    "DTE60_D50_100": 11,
    "DTE60_D40_100": 12,
    "DTE60_OTM2_100": 13,
}

REGIME_ORDER = {
    "strong_uptrend": 0,
    "mild_uptrend": 1,
    "neutral": 2,
    "weak_downtrend": 3,
    "post_drawdown_rebound_risk": 4,
    "other": 5,
}

PERIOD_USECOLS = [
    "etf_code",
    "strategy_name",
    "period_index",
    "rebalance_date",
    "period_end_date",
    "underlying_price_at_entry",
    "underlying_price_at_period_end",
    "premium_return",
    "upside_payoff_return",
    "transaction_cost_return",
    "etf_period_return",
    "strategy_period_return",
    "excess_return_vs_etf",
    "assignment_flag",
    "expiry_date",
    "actual_dte",
    "option_code",
    "option_type",
    "strike",
    "target_moneyness",
    "realized_moneyness",
    "underlying_price_at_expiry",
    "option_payoff_return_at_expiry",
    "selected_delta",
    "selected_iv",
    "downside_cushion_ratio",
    "downside_benefit",
    "upside_cost",
    "dte_label",
    "target_delta",
    "trend_5d",
    "trend_20d",
    "trend_60d",
    "ma_gap_20",
    "ma_gap_60",
    "drawdown_from_rolling_high",
    "rv_20d",
    "rv_60d",
    "post_drawdown_rebound_risk",
    "iv_at_entry",
    "iv_percentile",
    "iv_minus_rv",
    "policy_jump_like",
]

DAILY_USECOLS = [
    "date",
    "etf_code",
    "strategy_name",
    "period_index",
    "rebalance_date",
    "period_end_date",
    "short_call_mtm_loss_return",
    "daily_mtm_nav",
    "dte_label",
]

EVENT_USECOLS = [
    "etf_code",
    "dte_label",
    "strategy_name",
    "event_date",
    "period_end_date",
    "recovery_capture",
    "missed_rebound_return",
    "policy_jump_like",
]

STANDARD_USECOLS = [
    "etf_code",
    "dte_label",
    "strategy_name",
    "annualized_return_daily_nav",
    "annualized_volatility_daily_nav",
    "sharpe_ratio_daily_nav",
    "sortino_ratio_daily_nav",
    "calmar_ratio_daily_nav",
    "max_drawdown",
]

SUMMARY_USECOLS = [
    "etf_code",
    "dte_label",
    "strategy_name",
    "annualized_extrinsic_premium_yield",
    "premium_capture_ratio",
    "downside_cushion_ratio_mean",
    "downside_excess_mean",
    "max_drawdown_improvement",
    "missed_rebound_return",
    "recovery_capture",
    "max_short_call_mtm_loss",
]

PERIOD_DATASET_COLUMNS = [
    "etf_code",
    "rebalance_date",
    "expiry_date",
    "period_end_date",
    "strategy_name",
    "source_strategy_name",
    "candidate_role",
    "dte_label",
    "actual_dte",
    "target_delta",
    "entry_delta",
    "realized_moneyness",
    "strike",
    "underlying_price_at_entry",
    "underlying_price_at_expiry",
    "trend_5d",
    "trend_20d",
    "trend_60d",
    "ma_gap_20",
    "ma_gap_60",
    "drawdown_from_rolling_high_252",
    "rv_20d",
    "rv_60d",
    "iv_at_entry",
    "iv_percentile_252",
    "iv_minus_rv20",
    "primary_regime",
    "high_rv20",
    "low_rv20",
    "iv_rich",
    "iv_low",
    "policy_jump_like",
    "down_then_rebound",
    "etf_period_return",
    "strategy_period_return",
    "excess_return_vs_buyhold",
    "premium_return",
    "payoff_return",
    "premium_capture_ratio_period",
    "assignment_flag",
    "downside_excess",
    "downside_cushion_ratio",
    "upside_cost",
    "missed_rebound_return",
    "recovery_capture",
    "daily_mtm_nav_start",
    "daily_mtm_nav_end",
    "max_short_call_mtm_loss_in_period",
    "daily_mtm_drawdown_in_period",
]


@dataclass(frozen=True)
class Step1Paths:
    source_dir: Path = Path("outputs/ver2_downside_protection/ver2_1_dte_regime")
    base_output_dir: Path = Path("outputs/ver2_downside_protection")
    output_dir: Path = Path(
        "outputs/ver2_downside_protection/510300_branch/ver2_2_step1_regime_attribution"
    )

    @property
    def periods_path(self) -> Path:
        return self.source_dir / "ver2_1_periods_with_regime.csv"

    @property
    def daily_mtm_path(self) -> Path:
        return self.source_dir / "ver2_1_daily_mtm.csv"

    @property
    def events_path(self) -> Path:
        return self.source_dir / "ver2_1_down_then_rebound_events.csv"

    @property
    def dte_summary_path(self) -> Path:
        return self.source_dir / "ver2_1_dte_moneyness_summary.csv"

    @property
    def standard_performance_path(self) -> Path:
        return self.base_output_dir / "ver2_1_standard_performance_summary.csv"

    @property
    def sharpe_bridge_summary_path(self) -> Path:
        return (
            self.base_output_dir
            / "510300_branch"
            / "sharpe_bridge"
            / "ver2_2_510300_sharpe_bridge_summary.csv"
        )

    @property
    def figures_dir(self) -> Path:
        return self.output_dir / "figures"

    @property
    def reports_dir(self) -> Path:
        return self.output_dir / "reports"

    def ensure_dirs(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.figures_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class Step1Outputs:
    period_dataset: Path
    regime_performance: Path
    candidate_comparison: Path
    state_action_hypothesis: Path
    sanity_checks: Path
    report: Path
    figures_dir: Path
    warnings: tuple[str, ...]


def normalize_etf_code(series: pd.Series) -> pd.Series:
    return series.astype(str).str.replace(".0", "", regex=False).str.zfill(6)


def candidate_strategy_name(dte_label: str, strategy_name: str) -> str:
    if strategy_name == "BuyHold":
        return "BuyHold"
    return f"{dte_label}_{strategy_name}"


def assign_primary_regime(row: pd.Series) -> str:
    """Assign the ex-ante regime using only entry-date trend, MA gap, and drawdown fields."""
    trend_5d = row.get("trend_5d")
    trend_20d = row.get("trend_20d")
    ma_gap_60 = row.get("ma_gap_60")
    drawdown = row.get("drawdown_from_rolling_high_252")

    if pd.notna(drawdown) and pd.notna(trend_5d) and drawdown < -0.08 and trend_5d > 0:
        return "post_drawdown_rebound_risk"
    if pd.notna(trend_20d) and pd.notna(ma_gap_60) and trend_20d > 0.03 and ma_gap_60 > 0:
        return "strong_uptrend"
    if pd.notna(trend_20d) and pd.notna(ma_gap_60) and trend_20d < 0 and ma_gap_60 < 0:
        return "weak_downtrend"
    if pd.notna(trend_20d) and pd.notna(ma_gap_60) and 0 < trend_20d <= 0.03 and ma_gap_60 >= 0:
        return "mild_uptrend"
    if pd.notna(trend_20d) and abs(trend_20d) <= 0.02:
        return "neutral"
    return "other"


def _read_csv(path: Path, usecols: Iterable[str] | None = None) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Required input file does not exist: {path}")
    if usecols is None:
        return pd.read_csv(path, dtype={"etf_code": str})
    header = pd.read_csv(path, nrows=0)
    missing = sorted(set(usecols) - set(header.columns))
    if missing:
        raise KeyError(f"{path} is missing required columns: {missing}")
    return pd.read_csv(path, usecols=list(usecols), dtype={"etf_code": str})


def _dateify(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        if col in out.columns:
            out[col] = pd.to_datetime(out[col], errors="coerce")
    return out


def _filter_candidate_rows(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["etf_code"] = normalize_etf_code(out["etf_code"])
    out = out[out["etf_code"].eq(ETF_CODE)].copy()
    out["_role_key"] = list(zip(out["dte_label"], out["strategy_name"]))
    out["candidate_role"] = out["_role_key"].map(CANDIDATE_ROLES)
    out = out[out["candidate_role"].notna()].copy()
    out["source_strategy_name"] = out["strategy_name"]
    out["strategy_name"] = [
        candidate_strategy_name(dte, strategy)
        for dte, strategy in zip(out["dte_label"], out["source_strategy_name"])
    ]
    return out.drop(columns=["_role_key"], errors="ignore")


def _period_sort(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    out = df.copy()
    out["_candidate_order"] = out["strategy_name"].map(CANDIDATE_ORDER).fillna(999)
    out["_regime_order"] = out.get("primary_regime", pd.Series(index=out.index, dtype=object)).map(REGIME_ORDER).fillna(999)
    return (
        out.sort_values(["_candidate_order", "rebalance_date", "period_end_date", "_regime_order"])
        .drop(columns=["_candidate_order", "_regime_order"], errors="ignore")
        .reset_index(drop=True)
    )


def _expanding_percentile_by_date(df: pd.DataFrame, date_col: str, value_col: str) -> pd.Series:
    unique = (
        df[[date_col, value_col]]
        .drop_duplicates(subset=[date_col])
        .sort_values(date_col)
        .reset_index(drop=True)
    )
    percentiles: list[float] = []
    history: list[float] = []
    for value in unique[value_col]:
        if pd.isna(value):
            percentiles.append(np.nan)
            continue
        history.append(float(value))
        rank = pd.Series(history).rank(pct=True).iloc[-1]
        percentiles.append(float(rank))
    mapping = dict(zip(unique[date_col], percentiles))
    return df[date_col].map(mapping)


def _add_secondary_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["rv20_expanding_percentile"] = _expanding_percentile_by_date(out, "rebalance_date", "rv_20d")
    out["high_rv20"] = np.where(out["rv20_expanding_percentile"].notna(), out["rv20_expanding_percentile"] >= 0.70, np.nan)
    out["low_rv20"] = np.where(out["rv20_expanding_percentile"].notna(), out["rv20_expanding_percentile"] <= 0.30, np.nan)
    iv_available = out["iv_at_entry"].notna() & out["iv_percentile_252"].notna()
    out["iv_rich"] = np.where(
        iv_available,
        (out["iv_minus_rv20"] > 0) & (out["iv_percentile_252"] >= 0.60),
        np.nan,
    )
    out["iv_low"] = np.where(iv_available, out["iv_percentile_252"] <= 0.30, np.nan)
    return out.drop(columns=["rv20_expanding_percentile"])


def _daily_mtm_period_stats(daily_mtm: pd.DataFrame) -> pd.DataFrame:
    daily = _filter_candidate_rows(daily_mtm)
    daily = _dateify(daily, ["date", "rebalance_date", "period_end_date"])
    group_cols = ["etf_code", "dte_label", "source_strategy_name", "strategy_name", "period_index"]
    rows: list[dict[str, object]] = []
    for keys, group in daily.sort_values("date").groupby(group_cols, dropna=False):
        nav = pd.to_numeric(group["daily_mtm_nav"], errors="coerce").dropna()
        if nav.empty:
            nav_start = np.nan
            nav_end = np.nan
            drawdown = np.nan
        else:
            nav_start = float(nav.iloc[0])
            nav_end = float(nav.iloc[-1])
            running_max = nav.cummax()
            drawdown = float(max(0.0, -((nav / running_max) - 1.0).min()))
        loss = pd.to_numeric(group["short_call_mtm_loss_return"], errors="coerce")
        rows.append(
            {
                "etf_code": keys[0],
                "dte_label": keys[1],
                "source_strategy_name": keys[2],
                "strategy_name": keys[3],
                "period_index": keys[4],
                "daily_mtm_nav_start": nav_start,
                "daily_mtm_nav_end": nav_end,
                "max_short_call_mtm_loss_in_period": float(loss.max()) if loss.notna().any() else np.nan,
                "daily_mtm_drawdown_in_period": drawdown,
            }
        )
    return pd.DataFrame(rows)


def _build_event_flags(events: pd.DataFrame) -> pd.DataFrame:
    out = _filter_candidate_rows(events)
    out = _dateify(out, ["event_date", "period_end_date"])
    out["down_then_rebound"] = 1
    return out.rename(columns={"event_date": "rebalance_date"})[
        [
            "etf_code",
            "dte_label",
            "source_strategy_name",
            "strategy_name",
            "rebalance_date",
            "period_end_date",
            "down_then_rebound",
            "missed_rebound_return",
            "recovery_capture",
        ]
    ].drop_duplicates()


def build_period_regime_dataset(
    periods: pd.DataFrame,
    daily_mtm: pd.DataFrame,
    events: pd.DataFrame,
) -> pd.DataFrame:
    """Build the 510300 period-level attribution dataset from existing ver2.1 outputs."""
    out = _filter_candidate_rows(periods)
    out = _dateify(out, ["rebalance_date", "period_end_date", "expiry_date"])

    out["entry_delta"] = out["selected_delta"]
    out["drawdown_from_rolling_high_252"] = out["drawdown_from_rolling_high"]
    out["iv_percentile_252"] = out["iv_percentile"]
    out["iv_minus_rv20"] = out["iv_minus_rv"]
    out["underlying_price_at_expiry"] = out["underlying_price_at_expiry"].fillna(
        out["underlying_price_at_period_end"]
    )
    has_strike = out["strike"].notna() & out["underlying_price_at_entry"].gt(0)
    out["realized_moneyness"] = np.where(
        has_strike,
        out["strike"] / out["underlying_price_at_entry"] - 1.0,
        out["realized_moneyness"],
    )

    out["payoff_return"] = out["option_payoff_return_at_expiry"].fillna(out["upside_payoff_return"]).fillna(0.0)
    out["premium_capture_ratio_period"] = np.where(
        out["premium_return"].gt(0),
        (out["premium_return"] - out["payoff_return"]) / out["premium_return"],
        np.nan,
    )
    out["excess_return_vs_buyhold"] = out["excess_return_vs_etf"].fillna(
        out["strategy_period_return"] - out["etf_period_return"]
    )
    out["downside_excess"] = np.where(out["etf_period_return"] < 0, out["excess_return_vs_buyhold"], np.nan)
    out["downside_cushion_ratio"] = np.where(
        out["etf_period_return"] < 0,
        out["downside_cushion_ratio"],
        np.nan,
    )
    out["primary_regime"] = out.apply(assign_primary_regime, axis=1)
    out = _add_secondary_flags(out)

    mtm_stats = _daily_mtm_period_stats(daily_mtm)
    out = out.merge(
        mtm_stats,
        on=["etf_code", "dte_label", "source_strategy_name", "strategy_name", "period_index"],
        how="left",
    )

    event_flags = _build_event_flags(events)
    out = out.merge(
        event_flags,
        on=[
            "etf_code",
            "dte_label",
            "source_strategy_name",
            "strategy_name",
            "rebalance_date",
            "period_end_date",
        ],
        how="left",
        suffixes=("", "_event"),
    )
    out["down_then_rebound"] = out["down_then_rebound"].fillna(0).astype(int)
    out["missed_rebound_return"] = out["missed_rebound_return"].fillna(0.0)
    out["recovery_capture"] = out["recovery_capture"]
    out["policy_jump_like"] = out["policy_jump_like"].fillna(0).astype(int)
    out["assignment_flag"] = out["assignment_flag"].fillna(0).astype(int)

    for col in PERIOD_DATASET_COLUMNS:
        if col not in out.columns:
            out[col] = np.nan
    return _period_sort(out[PERIOD_DATASET_COLUMNS])


def _group_mean(series: pd.Series) -> float:
    numeric = pd.to_numeric(series, errors="coerce")
    return float(numeric.mean()) if numeric.notna().any() else np.nan


def build_regime_performance(period_dataset: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (regime, strategy), group in period_dataset.groupby(["primary_regime", "strategy_name"], dropna=False):
        excess = pd.to_numeric(group["excess_return_vs_buyhold"], errors="coerce")
        row = {
            "primary_regime": regime,
            "strategy_name": strategy,
            "candidate_role": group["candidate_role"].iloc[0],
            "count": int(len(group)),
            "avg_etf_period_return": _group_mean(group["etf_period_return"]),
            "avg_strategy_period_return": _group_mean(group["strategy_period_return"]),
            "avg_excess_return_vs_buyhold": _group_mean(group["excess_return_vs_buyhold"]),
            "win_rate_vs_buyhold": float((excess > 0).mean()) if excess.notna().any() else np.nan,
            "annualized_return_daily_nav": np.nan,
            "annualized_volatility_daily_nav": np.nan,
            "sharpe_ratio_daily_nav": np.nan,
            "sortino_ratio_daily_nav": np.nan,
            "calmar_ratio_daily_nav": np.nan,
            "max_drawdown_daily_nav": np.nan,
            "daily_nav_metric_note": "not_computed_for_non_contiguous_regime_subsamples",
            "average_premium_return": _group_mean(group["premium_return"]),
            "average_payoff_return": _group_mean(group["payoff_return"]),
            "premium_capture_ratio_mean": _group_mean(group["premium_capture_ratio_period"]),
            "assignment_rate": float(pd.to_numeric(group["assignment_flag"], errors="coerce").fillna(0).mean()),
            "downside_excess_mean": _group_mean(group["downside_excess"]),
            "downside_cushion_ratio_mean": _group_mean(group["downside_cushion_ratio"]),
            "upside_cost_mean": _group_mean(group["upside_cost"]),
            "missed_rebound_return_mean": _group_mean(group["missed_rebound_return"]),
            "recovery_capture_mean": _group_mean(group["recovery_capture"]),
            "max_short_call_mtm_loss_mean": _group_mean(group["max_short_call_mtm_loss_in_period"]),
            "max_short_call_mtm_loss_max": float(
                pd.to_numeric(group["max_short_call_mtm_loss_in_period"], errors="coerce").max()
            ),
            "daily_mtm_drawdown_mean": _group_mean(group["daily_mtm_drawdown_in_period"]),
            "daily_mtm_drawdown_max": float(
                pd.to_numeric(group["daily_mtm_drawdown_in_period"], errors="coerce").max()
            ),
            "low_sample_warning": bool(len(group) < LOW_SAMPLE_THRESHOLD),
        }
        rows.append(row)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["_regime_order"] = out["primary_regime"].map(REGIME_ORDER).fillna(999)
    out["_candidate_order"] = out["strategy_name"].map(CANDIDATE_ORDER).fillna(999)
    return (
        out.sort_values(["_regime_order", "_candidate_order"])
        .drop(columns=["_regime_order", "_candidate_order"])
        .reset_index(drop=True)
    )


def _main_summary_name(row: pd.Series) -> str:
    return candidate_strategy_name(row["dte_label"], row["strategy_name"])


def _interpretation(strategy_name: str) -> str:
    mapping = {
        "BuyHold": "基准：不卖出期权，用于衡量备兑覆盖带来的收益、回撤和路径差异。",
        "DTE30_ATM_100": "防御强、权利金厚，但日频 Sharpe 不一定最优，且反弹截断更明显。",
        "DTE30_D50_100": "近 ATM 替代，缓冲接近 ATM，同时略微降低被上行打穿的压力。",
        "DTE30_D40_100": "当前 510300 daily MTM Sharpe 表现最优的主候选，防御和路径体验更均衡。",
        "DTE30_OTM2_100": "更保留上涨参与，但下跌保护和权利金厚度弱于 ATM / D50 / D40。",
    }
    return mapping.get(strategy_name, "")


def build_candidate_comparison(standard: pd.DataFrame, dte_summary: pd.DataFrame) -> pd.DataFrame:
    standard = standard.copy()
    dte_summary = dte_summary.copy()
    for df in (standard, dte_summary):
        df["etf_code"] = normalize_etf_code(df["etf_code"])
        df["_role_key"] = list(zip(df["dte_label"], df["strategy_name"]))
        df["candidate_role"] = df["_role_key"].map(CANDIDATE_ROLES)
        df["strategy_name_out"] = df.apply(_main_summary_name, axis=1)

    main_keys = set(MAIN_CANDIDATES)
    standard = standard[
        standard["etf_code"].eq(ETF_CODE) & standard["_role_key"].isin(main_keys)
    ].copy()
    dte_summary = dte_summary[
        dte_summary["etf_code"].eq(ETF_CODE) & dte_summary["_role_key"].isin(main_keys)
    ].copy()

    perf_cols = [
        "strategy_name_out",
        "candidate_role",
        "annualized_return_daily_nav",
        "annualized_volatility_daily_nav",
        "sharpe_ratio_daily_nav",
        "sortino_ratio_daily_nav",
        "calmar_ratio_daily_nav",
        "max_drawdown",
    ]
    summary_cols = [
        "strategy_name_out",
        "annualized_extrinsic_premium_yield",
        "premium_capture_ratio",
        "downside_cushion_ratio_mean",
        "downside_excess_mean",
        "max_drawdown_improvement",
        "missed_rebound_return",
        "recovery_capture",
        "max_short_call_mtm_loss",
    ]
    out = standard[perf_cols].merge(dte_summary[summary_cols], on="strategy_name_out", how="left")
    out = out.rename(columns={"strategy_name_out": "strategy_name", "max_drawdown": "max_drawdown_daily_nav"})
    out["interpretation"] = out["strategy_name"].map(_interpretation)
    out["_candidate_order"] = out["strategy_name"].map(CANDIDATE_ORDER).fillna(999)
    cols = [
        "strategy_name",
        "candidate_role",
        "annualized_return_daily_nav",
        "annualized_volatility_daily_nav",
        "sharpe_ratio_daily_nav",
        "sortino_ratio_daily_nav",
        "calmar_ratio_daily_nav",
        "max_drawdown_daily_nav",
        "annualized_extrinsic_premium_yield",
        "premium_capture_ratio",
        "downside_cushion_ratio_mean",
        "downside_excess_mean",
        "max_drawdown_improvement",
        "missed_rebound_return",
        "recovery_capture",
        "max_short_call_mtm_loss",
        "interpretation",
    ]
    return out.sort_values("_candidate_order").drop(columns="_candidate_order")[cols].reset_index(drop=True)


def build_state_action_hypothesis() -> pd.DataFrame:
    rows = [
        {
            "primary_regime": "strong_uptrend",
            "preferred_action_1": "OTM2_100",
            "preferred_action_2": "D40_100",
            "rationale": "降低 short call delta，减少上涨和反弹截断。",
            "risk_note": "下跌缓冲弱于 ATM，若上涨突然转为下跌，保护不足。",
            "evidence_source": "ver2.1 DTE30 main candidates + ver2.2 Sharpe Bridge; hypothesis only",
        },
        {
            "primary_regime": "mild_uptrend",
            "preferred_action_1": "D40_100",
            "preferred_action_2": "OTM2_100",
            "rationale": "在保留一定权利金的同时降低被上行打穿风险。",
            "risk_note": "若趋势转弱，OTM2 的缓冲可能偏薄。",
            "evidence_source": "ver2.1 DTE30 main candidates + regime attribution; hypothesis only",
        },
        {
            "primary_regime": "neutral",
            "preferred_action_1": "D40_100",
            "preferred_action_2": "D50_100",
            "rationale": "510300 中 D40 当前 daily MTM Sharpe 较好，D50 保留更强缓冲。",
            "risk_note": "D40 权利金和下跌缓冲弱于 ATM/D50。",
            "evidence_source": "ver2.2 Sharpe Bridge + candidate comparison; hypothesis only",
        },
        {
            "primary_regime": "weak_downtrend",
            "preferred_action_1": "D50_100",
            "preferred_action_2": "ATM_100",
            "rationale": "提高权利金和下跌缓冲。",
            "risk_note": "若随后反弹，ATM 可能截断修复。",
            "evidence_source": "ver2.1 downside protection metrics + regime attribution; hypothesis only",
        },
        {
            "primary_regime": "post_drawdown_rebound_risk",
            "preferred_action_1": "D40_100",
            "preferred_action_2": "OTM2_100",
            "rationale": "避免低位卖 ATM 后截断反弹。",
            "risk_note": "若反弹失败继续下跌，保护弱于 ATM/D50。",
            "evidence_source": "ver2.1 down-then-rebound events + regime attribution; hypothesis only",
        },
    ]
    return pd.DataFrame(rows)


def _format_pct(value: object, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value) * 100:.{digits}f}%"


def _format_float(value: object, digits: int = 3) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value):.{digits}f}"


def _main_only(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["candidate_role"].ne("appendix_reference")].copy()


def _save_bar(df: pd.DataFrame, x: str, y: str, path: Path, title: str, ylabel: str) -> None:
    plot_df = df.copy()
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(plot_df[x], plot_df[y], color="#4C78A8")
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.tick_params(axis="x", rotation=25)
    ax.axhline(0, color="black", linewidth=0.8)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _save_scatter(
    df: pd.DataFrame,
    x: str,
    y: str,
    path: Path,
    title: str,
    xlabel: str,
    ylabel: str,
    size_col: str | None = None,
) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    sizes = None
    if size_col and size_col in df:
        sizes = 80 + 1500 * pd.to_numeric(df[size_col], errors="coerce").abs().fillna(0)
    ax.scatter(df[x], df[y], s=sizes, color="#F58518", edgecolor="#222222", alpha=0.85)
    for _, row in df.iterrows():
        ax.annotate(row["strategy_name"].replace("DTE30_", ""), (row[x], row[y]), xytext=(5, 5), textcoords="offset points")
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _save_heatmap(
    regime_perf: pd.DataFrame,
    value_col: str,
    path: Path,
    title: str,
    fmt: str = ".2%",
) -> None:
    main = _main_only(regime_perf)
    pivot = main.pivot_table(index="primary_regime", columns="strategy_name", values=value_col, aggfunc="mean")
    if pivot.empty:
        return
    pivot = pivot.reindex(sorted(pivot.index, key=lambda x: REGIME_ORDER.get(str(x), 999)))
    pivot = pivot[[col for col in sorted(pivot.columns, key=lambda x: CANDIDATE_ORDER.get(str(x), 999))]]
    data = pivot.to_numpy(dtype=float)
    fig, ax = plt.subplots(figsize=(10, max(4, 0.6 * len(pivot.index) + 2)))
    image = ax.imshow(data, cmap="RdYlGn", aspect="auto")
    ax.set_title(title)
    ax.set_xticks(np.arange(len(pivot.columns)))
    ax.set_xticklabels([c.replace("DTE30_", "") for c in pivot.columns], rotation=25, ha="right")
    ax.set_yticks(np.arange(len(pivot.index)))
    ax.set_yticklabels(pivot.index)
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            value = data[i, j]
            label = "" if np.isnan(value) else format(value, fmt)
            ax.text(j, i, label, ha="center", va="center", fontsize=8)
    fig.colorbar(image, ax=ax, fraction=0.03, pad=0.02)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _save_state_action_map(state_action: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 4.5))
    ax.axis("off")
    table_df = state_action[["primary_regime", "preferred_action_1", "preferred_action_2"]]
    table = ax.table(
        cellText=table_df.values,
        colLabels=["regime", "action 1", "action 2"],
        cellLoc="center",
        loc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 1.6)
    ax.set_title("State-action hypothesis map (not a backtest)", pad=16)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def write_figures(
    candidate_comparison: pd.DataFrame,
    regime_performance: pd.DataFrame,
    state_action: pd.DataFrame,
    figures_dir: Path,
) -> None:
    main_candidates = candidate_comparison.copy()
    _save_bar(
        main_candidates,
        "strategy_name",
        "sharpe_ratio_daily_nav",
        figures_dir / "candidate_daily_sharpe_bar.png",
        "510300 DTE30 main candidates: daily MTM NAV Sharpe-like ratio",
        "daily NAV Sharpe-like ratio",
    )
    _save_scatter(
        main_candidates,
        "annualized_volatility_daily_nav",
        "annualized_return_daily_nav",
        figures_dir / "candidate_return_vol_scatter.png",
        "510300 candidate return vs volatility",
        "annualized volatility",
        "annualized return",
    )
    _save_scatter(
        main_candidates,
        "downside_cushion_ratio_mean",
        "sharpe_ratio_daily_nav",
        figures_dir / "candidate_downside_cushion_vs_sharpe.png",
        "Downside cushion vs daily NAV Sharpe-like ratio",
        "downside cushion ratio mean",
        "daily NAV Sharpe-like ratio",
    )
    _save_scatter(
        main_candidates,
        "max_short_call_mtm_loss",
        "sharpe_ratio_daily_nav",
        figures_dir / "candidate_mtm_loss_vs_sharpe.png",
        "Short-call MTM pressure vs daily NAV Sharpe-like ratio",
        "max short-call MTM loss",
        "daily NAV Sharpe-like ratio",
        size_col="max_short_call_mtm_loss",
    )
    _save_heatmap(
        regime_performance,
        "avg_excess_return_vs_buyhold",
        figures_dir / "regime_excess_return_heatmap.png",
        "Average excess return vs BuyHold by regime",
    )
    _save_heatmap(
        regime_performance,
        "premium_capture_ratio_mean",
        figures_dir / "regime_premium_capture_heatmap.png",
        "Premium capture ratio by regime",
    )
    _save_heatmap(
        regime_performance,
        "missed_rebound_return_mean",
        figures_dir / "regime_missed_rebound_heatmap.png",
        "Missed rebound return by regime",
    )
    _save_state_action_map(state_action, figures_dir / "state_action_map.png")


def _candidate_report_table(candidate_comparison: pd.DataFrame) -> str:
    cols = [
        "strategy_name",
        "annualized_return_daily_nav",
        "sharpe_ratio_daily_nav",
        "max_drawdown_daily_nav",
        "annualized_extrinsic_premium_yield",
        "premium_capture_ratio",
        "downside_cushion_ratio_mean",
        "missed_rebound_return",
        "max_short_call_mtm_loss",
    ]
    table = candidate_comparison[cols].copy()
    rename = {
        "strategy_name": "策略",
        "annualized_return_daily_nav": "日频NAV年化收益",
        "sharpe_ratio_daily_nav": "日频NAV Sharpe-like",
        "max_drawdown_daily_nav": "最大回撤",
        "annualized_extrinsic_premium_yield": "年化外在权利金",
        "premium_capture_ratio": "权利金留存率",
        "downside_cushion_ratio_mean": "下跌缓冲比例",
        "missed_rebound_return": "反弹截断损失",
        "max_short_call_mtm_loss": "最大short call盯市压力",
    }
    for col in table.columns:
        if col == "strategy_name":
            continue
        if col == "sharpe_ratio_daily_nav" or col == "downside_cushion_ratio_mean":
            table[col] = table[col].map(lambda x: _format_float(x, 3))
        else:
            table[col] = table[col].map(lambda x: _format_pct(x, 2))
    table = table.rename(columns=rename)
    return table.to_markdown(index=False)


def _regime_report_table(regime_performance: pd.DataFrame) -> str:
    main = _main_only(regime_performance)
    cols = [
        "primary_regime",
        "strategy_name",
        "count",
        "avg_excess_return_vs_buyhold",
        "win_rate_vs_buyhold",
        "premium_capture_ratio_mean",
        "downside_cushion_ratio_mean",
        "missed_rebound_return_mean",
        "low_sample_warning",
    ]
    table = main[cols].copy()
    for col in ["avg_excess_return_vs_buyhold", "win_rate_vs_buyhold", "premium_capture_ratio_mean", "missed_rebound_return_mean"]:
        table[col] = table[col].map(lambda x: _format_pct(x, 2))
    table["downside_cushion_ratio_mean"] = table["downside_cushion_ratio_mean"].map(lambda x: _format_float(x, 3))
    table["strategy_name"] = table["strategy_name"].str.replace("DTE30_", "", regex=False)
    table = table.rename(
        columns={
            "primary_regime": "状态",
            "strategy_name": "策略",
            "count": "周期数",
            "avg_excess_return_vs_buyhold": "平均超额",
            "win_rate_vs_buyhold": "跑赢频率",
            "premium_capture_ratio_mean": "权利金留存率",
            "downside_cushion_ratio_mean": "下跌缓冲比例",
            "missed_rebound_return_mean": "反弹截断损失",
            "low_sample_warning": "样本过少提示",
        }
    )
    return table.to_markdown(index=False)


def _state_action_report_table(state_action: pd.DataFrame) -> str:
    table = state_action[["primary_regime", "preferred_action_1", "preferred_action_2", "rationale", "risk_note"]].copy()
    table = table.rename(
        columns={
            "primary_regime": "状态",
            "preferred_action_1": "候选动作1",
            "preferred_action_2": "候选动作2",
            "rationale": "理由",
            "risk_note": "风险",
        }
    )
    return table.to_markdown(index=False)


def _safe_best_candidate(candidate_comparison: pd.DataFrame) -> str:
    candidates = candidate_comparison[candidate_comparison["strategy_name"].ne("BuyHold")].copy()
    if candidates.empty:
        return ""
    idx = pd.to_numeric(candidates["sharpe_ratio_daily_nav"], errors="coerce").idxmax()
    return str(candidates.loc[idx, "strategy_name"])


def write_report(
    period_dataset: pd.DataFrame,
    regime_performance: pd.DataFrame,
    candidate_comparison: pd.DataFrame,
    state_action: pd.DataFrame,
    sanity_checks: pd.DataFrame,
    paths: Step1Paths,
    warnings: list[str],
) -> Path:
    report_path = paths.reports_dir / "ver2_2_step1_510300_regime_attribution_readable.md"
    best_candidate = _safe_best_candidate(candidate_comparison)
    low_sample_count = int(regime_performance["low_sample_warning"].sum()) if "low_sample_warning" in regime_performance else 0
    dataset_path = paths.output_dir / "ver2_2_510300_period_regime_dataset.csv"
    regime_path = paths.output_dir / "ver2_2_510300_regime_performance_by_strategy.csv"
    candidate_path = paths.output_dir / "ver2_2_510300_candidate_comparison.csv"
    state_action_path = paths.output_dir / "ver2_2_510300_state_action_hypothesis.csv"

    warning_lines = "\n".join(f"- {item}" for item in warnings) if warnings else "- 当前没有阻塞性 warning。"
    sanity_table = sanity_checks.to_markdown(index=False)

    text = f"""# ver2.2 Step 1｜510300 候选池收敛与状态归因

## 1. 版本定位

本版本只研究 510300。它不是最终动态策略，也不执行状态依赖交易规则回测；当前目标是把 ver2.1 的非 ITM 机制诊断推进到 510300-only 的候选池收敛、状态归因母表和规则假设准备。

本步骤输出的是诊断数据集和 hypothesis table。后续只有在这些条件表现足够清楚时，才进入 `ver2.2 Step 2｜510300 Regime-Dependent Rule Backtest Prototype`。

## 2. 候选池

主候选池只包含：

- BuyHold
- DTE30 ATM_100
- DTE30 D50_100
- DTE30 D40_100
- DTE30 OTM2_100

DTE60 只保留为 `appendix_reference`，不进入主候选池和主图。ITM、DTE14、DTE45 不进入本版本主候选。

## 3. Sharpe 口径说明

本阶段候选比较使用 ver2.1 的 `daily_mtm_nav` 口径。它不同于 period settlement Sharpe：period settlement 只在期权周期结算点确认收益，而 daily MTM NAV 会每日反映 ETF 路径和 short call 负债变化。

同时要注意，当前 `sharpe_ratio_daily_nav` 是项目内既有的 daily NAV Sharpe-like ratio，核心是日频 NAV CAGR 除以年化日频波动；严格日收益 Sharpe 已在 510300 Sharpe Bridge 中另列。两者不能与 period settlement Sharpe 混用。

Sharpe Bridge 对 510300 的解释是：口径差异主要来自日频 ETF 路径波动；在当前样本中，DTE30 short call MTM 并没有系统性拖累 Sharpe，反而提供了一定路径缓冲。ATM 防御强，但 D40 当前 daily MTM Sharpe-like 表现更优。

## 4. 候选表现摘要

当前 daily MTM NAV 口径下，主候选中 Sharpe-like 最高的是：**{best_candidate}**。

{_candidate_report_table(candidate_comparison)}

完整候选比较表：`{candidate_path.as_posix()}`

## 5. Regime Conditional Performance

下面是按 `primary_regime` 分组后的周期条件表现。由于 regime 子样本不是连续可投资 NAV，报告不伪造 regime-level daily NAV Sharpe；CSV 中相关 daily NAV 年化列保留为空，并通过 `daily_nav_metric_note` 标注。

{_regime_report_table(regime_performance)}

样本过少提示：共有 {low_sample_count} 个 regime-strategy 组合触发 `low_sample_warning`，需要克制解释。

完整条件表现表：`{regime_path.as_posix()}`

## 6. 状态到动作的候选映射

下表只是规则设计假设，不是动态策略回测结果。

{_state_action_report_table(state_action)}

假设表 CSV：`{state_action_path.as_posix()}`

## 7. 局限性

1. 当前只覆盖 510300，不能直接外推到 510050 或其他 ETF。
2. 状态阈值是经验设定，尚未经过 out-of-sample 校验。
3. `down_then_rebound` 和 `policy_jump_like` 只用于事后归因，不进入 `primary_regime`。
4. 当前尚未做动态策略回测。
5. 当前尚未做覆盖率优化。
6. 当前尚未做 execution sensitivity。
7. 当前尚未做 out-of-sample validation。
8. regime 子样本不是连续 NAV，因此不计算 regime-level daily NAV Sharpe。

## 8. 下一步

建议下一步进入 `ver2.2 Step 2｜510300 Regime-Dependent Rule Backtest Prototype`，但前提是先确认本报告中的状态到动作映射只作为可检验假设，而非最终策略结论。

## 附录：输出与检查

母表：`{dataset_path.as_posix()}`

Sanity checks：

{sanity_table}

Warnings：

{warning_lines}
"""
    report_path.write_text(text, encoding="utf-8")
    return report_path


def run_sanity_checks(
    period_dataset: pd.DataFrame,
    candidate_comparison: pd.DataFrame,
    regime_performance: pd.DataFrame,
) -> pd.DataFrame:
    checks: list[dict[str, object]] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    add(
        "only_510300",
        set(period_dataset["etf_code"].dropna().unique()) == {ETF_CODE},
        ",".join(map(str, sorted(period_dataset["etf_code"].dropna().unique()))),
    )
    main = period_dataset[period_dataset["candidate_role"].ne("appendix_reference")]
    add("main_pool_excludes_itm", not main["strategy_name"].str.contains("ITM", case=False, na=False).any(), "")
    add(
        "main_pool_excludes_dte14_dte45",
        not main["dte_label"].isin(["DTE14_strict_window", "DTE14_nearest_continuous", "DTE45"]).any(),
        ",".join(sorted(main["dte_label"].dropna().unique())),
    )
    dte60_rows = period_dataset[period_dataset["dte_label"].eq("DTE60")]
    add(
        "dte60_appendix_only",
        dte60_rows.empty or dte60_rows["candidate_role"].eq("appendix_reference").all(),
        ",".join(sorted(dte60_rows["candidate_role"].dropna().unique())),
    )
    add(
        "regime_features_are_entry_date_only",
        True,
        "primary_regime uses trend_5d/trend_20d/ma_gap_60/drawdown_from_rolling_high_252 only",
    )
    add(
        "ex_post_labels_not_used_for_primary_regime",
        True,
        "policy_jump_like and down_then_rebound are merged after primary_regime assignment",
    )
    add(
        "daily_nav_sharpe_not_mixed_with_settlement",
        "sharpe_ratio_period_settlement" not in candidate_comparison.columns,
        "candidate comparison uses standard_performance daily_mtm_nav fields",
    )
    add(
        "low_sample_warning_available",
        "low_sample_warning" in regime_performance.columns,
        f"flagged={int(regime_performance.get('low_sample_warning', pd.Series(dtype=bool)).sum())}",
    )
    return pd.DataFrame(checks)


def _load_inputs(paths: Step1Paths) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    periods = _read_csv(paths.periods_path, PERIOD_USECOLS)
    daily_mtm = _read_csv(paths.daily_mtm_path, DAILY_USECOLS)
    events = _read_csv(paths.events_path, EVENT_USECOLS)
    standard = _read_csv(paths.standard_performance_path, STANDARD_USECOLS)
    dte_summary = _read_csv(paths.dte_summary_path, SUMMARY_USECOLS)
    return periods, daily_mtm, events, standard, dte_summary


def run_step1_regime_attribution(paths: Step1Paths | None = None) -> Step1Outputs:
    paths = paths or Step1Paths()
    paths.ensure_dirs()
    warnings: list[str] = []

    periods, daily_mtm, events, standard, dte_summary = _load_inputs(paths)
    period_dataset = build_period_regime_dataset(periods, daily_mtm, events)
    regime_performance = build_regime_performance(period_dataset)
    candidate_comparison = build_candidate_comparison(standard, dte_summary)
    state_action = build_state_action_hypothesis()
    sanity_checks = run_sanity_checks(period_dataset, candidate_comparison, regime_performance)

    if period_dataset["iv_at_entry"].notna().mean() < 0.50:
        warnings.append("IV-based fields have limited coverage; iv_rich/iv_low should be treated as diagnostics only.")
    if regime_performance.get("low_sample_warning", pd.Series(dtype=bool)).any():
        warnings.append("Some regime-strategy cells have fewer than five periods; avoid over-interpreting them.")
    if not sanity_checks["passed"].all():
        failed = sanity_checks.loc[~sanity_checks["passed"], "check"].tolist()
        warnings.append(f"Sanity checks failed: {failed}")

    period_path = paths.output_dir / "ver2_2_510300_period_regime_dataset.csv"
    regime_path = paths.output_dir / "ver2_2_510300_regime_performance_by_strategy.csv"
    candidate_path = paths.output_dir / "ver2_2_510300_candidate_comparison.csv"
    state_path = paths.output_dir / "ver2_2_510300_state_action_hypothesis.csv"
    sanity_path = paths.output_dir / "ver2_2_510300_sanity_checks.csv"

    period_dataset.to_csv(period_path, index=False, encoding="utf-8-sig")
    regime_performance.to_csv(regime_path, index=False, encoding="utf-8-sig")
    candidate_comparison.to_csv(candidate_path, index=False, encoding="utf-8-sig")
    state_action.to_csv(state_path, index=False, encoding="utf-8-sig")
    sanity_checks.to_csv(sanity_path, index=False, encoding="utf-8-sig")

    write_figures(candidate_comparison, regime_performance, state_action, paths.figures_dir)
    report_path = write_report(
        period_dataset,
        regime_performance,
        candidate_comparison,
        state_action,
        sanity_checks,
        paths,
        warnings,
    )

    LOGGER.info("Wrote ver2.2 Step 1 outputs to %s", paths.output_dir)
    return Step1Outputs(
        period_dataset=period_path,
        regime_performance=regime_path,
        candidate_comparison=candidate_path,
        state_action_hypothesis=state_path,
        sanity_checks=sanity_path,
        report=report_path,
        figures_dir=paths.figures_dir,
        warnings=tuple(warnings),
    )


__all__ = [
    "APPENDIX_REFERENCE",
    "CANDIDATE_ROLES",
    "MAIN_CANDIDATES",
    "Step1Outputs",
    "Step1Paths",
    "assign_primary_regime",
    "build_candidate_comparison",
    "build_period_regime_dataset",
    "build_regime_performance",
    "build_state_action_hypothesis",
    "candidate_strategy_name",
    "run_sanity_checks",
    "run_step1_regime_attribution",
]
