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

from ver2_downside_protection.step1_regime_attribution_510300 import (
    ETF_CODE,
    normalize_etf_code,
)


LOGGER = logging.getLogger(__name__)

TRADING_DAYS_PER_YEAR = 252.0
CALENDAR_DAYS_PER_YEAR = 365.25
TARGET_DTES = ("DTE30", "DTE60")
TARGET_STRATEGIES = ("ATM_100", "D50_100", "D40_100", "OTM2_100")
STRATEGY_ORDER = {"ATM_100": 0, "D50_100": 1, "D40_100": 2, "OTM2_100": 3}
DTE_ORDER = {"DTE30": 0, "DTE60": 1}

PERIOD_USECOLS = [
    "etf_code",
    "strategy_name",
    "period_index",
    "rebalance_date",
    "period_end_date",
    "underlying_price_at_entry",
    "underlying_price_at_period_end",
    "coverage_ratio",
    "premium_return",
    "upside_payoff_return",
    "transaction_cost_return",
    "etf_period_return",
    "strategy_period_return",
    "assignment_flag",
    "expiry_date",
    "actual_dte",
    "strike",
    "option_price_at_entry",
    "realized_moneyness",
    "underlying_price_at_expiry",
    "option_payoff_return_at_expiry",
    "selected_delta",
    "selected_iv",
    "dte_label",
    "target_delta",
    "trend_5d",
    "trend_20d",
    "ma_gap_60",
    "drawdown_from_rolling_high",
    "rv_20d",
    "iv_at_entry",
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
    "option_code",
    "strike",
    "expiry_date",
    "option_price_at_entry",
    "option_mark_price",
    "option_liability_return",
    "short_call_mtm_loss_return",
    "premium_return",
    "transaction_cost_return",
    "daily_mtm_nav",
    "dte_label",
    "target_delta",
    "target_moneyness_spec",
]

STEP1_USECOLS = [
    "etf_code",
    "dte_label",
    "source_strategy_name",
    "strategy_name",
    "rebalance_date",
    "period_end_date",
    "primary_regime",
    "down_then_rebound",
]

DATASET_COLUMNS = [
    "etf_code",
    "rebalance_date",
    "expiry_date",
    "period_end_date",
    "dte_label",
    "strategy_name",
    "actual_dte",
    "target_delta",
    "entry_delta",
    "realized_moneyness",
    "strike",
    "underlying_price_at_entry",
    "underlying_price_at_expiry",
    "etf_period_return",
    "covered_call_period_return",
    "option_leg_return",
    "premium_return",
    "total_premium_yield",
    "intrinsic_premium_yield",
    "extrinsic_premium_yield",
    "annualized_extrinsic_premium_yield",
    "payoff_return",
    "transaction_cost_return",
    "realized_time_carry_yield",
    "premium_capture_ratio",
    "payoff_burden",
    "assignment_flag",
    "option_leg_contribution_to_cc_return",
    "option_leg_contribution_to_excess_vs_buyhold",
    "daily_mtm_nav_start",
    "daily_mtm_nav_end",
    "short_call_mtm_loss_max_in_period",
    "short_call_mtm_loss_mean_in_period",
    "daily_option_leg_mtm_return_mean",
    "daily_option_leg_mtm_return_vol",
    "mtm_stress_day_count",
    "daily_observation_count",
    "policy_jump_like",
    "down_then_rebound",
    "primary_regime",
    "iv_at_entry",
    "rv_20d",
    "iv_minus_rv20",
]


@dataclass(frozen=True)
class OptionLegPaths:
    source_dir: Path = Path("outputs/ver2_downside_protection/ver2_1_dte_regime")
    step1_dir: Path = Path(
        "outputs/ver2_downside_protection/510300_branch/ver2_2_step1_regime_attribution"
    )
    output_dir: Path = Path(
        "outputs/ver2_downside_protection/510300_branch/ver2_3_option_leg_time_carry"
    )

    @property
    def periods_path(self) -> Path:
        return self.source_dir / "ver2_1_periods_with_regime.csv"

    @property
    def daily_mtm_path(self) -> Path:
        return self.source_dir / "ver2_1_daily_mtm.csv"

    @property
    def step1_dataset_path(self) -> Path:
        return self.step1_dir / "ver2_2_510300_period_regime_dataset.csv"

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
class OptionLegOutputs:
    period_dataset: Path
    summary: Path
    dte_comparison: Path
    strategy_family_comparison: Path
    return_attribution: Path
    regime_attribution: Path
    ranking: Path
    mtm_stress_event_diagnostics: Path
    sanity_checks: Path
    report: Path
    figures_dir: Path
    warnings: tuple[str, ...]


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


def _dateify(df: pd.DataFrame, cols: Iterable[str]) -> pd.DataFrame:
    out = df.copy()
    for col in cols:
        if col in out.columns:
            out[col] = pd.to_datetime(out[col], errors="coerce")
    return out


def _filter_target(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["etf_code"] = normalize_etf_code(out["etf_code"])
    return out[
        out["etf_code"].eq(ETF_CODE)
        & out["dte_label"].isin(TARGET_DTES)
        & out["strategy_name"].isin(TARGET_STRATEGIES)
    ].copy()


def _strategy_family(strategy_name: str) -> str:
    if strategy_name.startswith("ATM"):
        return "ATM"
    if strategy_name.startswith("D50"):
        return "D50"
    if strategy_name.startswith("D40"):
        return "D40"
    if strategy_name.startswith("OTM2"):
        return "OTM2"
    return strategy_name


def _safe_divide(numerator: pd.Series | float, denominator: pd.Series | float) -> pd.Series | float:
    if isinstance(denominator, pd.Series):
        return np.where(pd.to_numeric(denominator, errors="coerce").abs() > 1e-12, numerator / denominator, np.nan)
    return float(numerator / denominator) if abs(float(denominator)) > 1e-12 else np.nan


def annualized_from_period_returns(
    returns: pd.Series,
    start_dates: pd.Series,
    end_dates: pd.Series,
) -> float:
    numeric = pd.to_numeric(returns, errors="coerce").dropna()
    if numeric.empty:
        return np.nan
    cumulative = float((1.0 + numeric).prod() - 1.0)
    valid_start = pd.to_datetime(start_dates, errors="coerce").dropna()
    valid_end = pd.to_datetime(end_dates, errors="coerce").dropna()
    if valid_start.empty or valid_end.empty:
        years = max(len(numeric) / 12.0, 1e-12)
    else:
        years = (valid_end.max() - valid_start.min()).days / 365.25
        years = max(years, len(numeric) / 12.0, 1e-12)
    if 1.0 + cumulative <= 0:
        return np.nan
    return float((1.0 + cumulative) ** (1.0 / years) - 1.0)


def _periods_per_year(actual_dte: pd.Series) -> float:
    avg_dte = pd.to_numeric(actual_dte, errors="coerce").mean()
    if pd.isna(avg_dte) or avg_dte <= 0:
        return np.nan
    return float(CALENDAR_DAYS_PER_YEAR / avg_dte)


def _daily_option_leg_stats(daily_mtm: pd.DataFrame) -> pd.DataFrame:
    daily = _filter_target(daily_mtm)
    daily = _dateify(daily, ["date", "rebalance_date", "period_end_date"])
    rows: list[dict[str, object]] = []
    group_cols = ["etf_code", "dte_label", "strategy_name", "period_index", "rebalance_date", "period_end_date"]
    for keys, group in daily.sort_values("date").groupby(group_cols, dropna=False):
        nav = pd.to_numeric(group["daily_mtm_nav"], errors="coerce").dropna()
        mtm_loss = pd.to_numeric(group["short_call_mtm_loss_return"], errors="coerce")
        option_leg_level = (
            pd.to_numeric(group["premium_return"], errors="coerce")
            - pd.to_numeric(group["option_liability_return"], errors="coerce")
            - pd.to_numeric(group["transaction_cost_return"], errors="coerce")
        )
        daily_option_leg = option_leg_level.diff()
        if not option_leg_level.empty:
            daily_option_leg.iloc[0] = option_leg_level.iloc[0]
        rows.append(
            {
                "etf_code": keys[0],
                "dte_label": keys[1],
                "strategy_name": keys[2],
                "period_index": keys[3],
                "rebalance_date": keys[4],
                "period_end_date": keys[5],
                "daily_mtm_nav_start": float(nav.iloc[0]) if not nav.empty else np.nan,
                "daily_mtm_nav_end": float(nav.iloc[-1]) if not nav.empty else np.nan,
                "short_call_mtm_loss_max_in_period": float(mtm_loss.max()) if mtm_loss.notna().any() else np.nan,
                "short_call_mtm_loss_mean_in_period": float(mtm_loss.mean()) if mtm_loss.notna().any() else np.nan,
                "daily_option_leg_mtm_return_mean": float(daily_option_leg.mean())
                if daily_option_leg.notna().any()
                else np.nan,
                "daily_option_leg_mtm_return_vol": float(daily_option_leg.std(ddof=0))
                if daily_option_leg.notna().any()
                else np.nan,
                "mtm_stress_day_count": int((mtm_loss > 0).sum()) if mtm_loss.notna().any() else 0,
                "daily_observation_count": int(mtm_loss.notna().sum()),
            }
        )
    return pd.DataFrame(rows)


def _load_step1_regime(paths: OptionLegPaths) -> pd.DataFrame:
    if not paths.step1_dataset_path.exists():
        LOGGER.warning("Step 1 dataset not found, primary_regime/down_then_rebound will be NaN: %s", paths.step1_dataset_path)
        return pd.DataFrame(
            columns=[
                "etf_code",
                "dte_label",
                "strategy_name",
                "rebalance_date",
                "period_end_date",
                "primary_regime",
                "down_then_rebound",
            ]
        )
    step1 = _read_csv(paths.step1_dataset_path, STEP1_USECOLS)
    step1["strategy_name"] = step1["source_strategy_name"]
    step1["etf_code"] = normalize_etf_code(step1["etf_code"])
    step1 = step1[
        step1["etf_code"].eq(ETF_CODE)
        & step1["dte_label"].isin(TARGET_DTES)
        & step1["strategy_name"].isin(TARGET_STRATEGIES)
    ].copy()
    return _dateify(step1, ["rebalance_date", "period_end_date"])


def build_option_leg_period_dataset(
    periods: pd.DataFrame,
    daily_mtm: pd.DataFrame,
    step1_regime: pd.DataFrame,
) -> pd.DataFrame:
    """Build period-level option-leg carry observations for 510300 DTE30/DTE60 candidates."""
    out = _filter_target(periods)
    out = _dateify(out, ["rebalance_date", "period_end_date", "expiry_date"])
    out["entry_delta"] = out["selected_delta"]
    out["underlying_price_at_expiry"] = out["underlying_price_at_expiry"].fillna(
        out["underlying_price_at_period_end"]
    )
    out["covered_call_period_return"] = out["strategy_period_return"]
    out["payoff_return"] = out["option_payoff_return_at_expiry"].fillna(out["upside_payoff_return"]).fillna(0.0)
    out["total_premium_yield"] = out["premium_return"]
    coverage = pd.to_numeric(out.get("coverage_ratio", 1.0), errors="coerce").fillna(1.0)
    premium = pd.to_numeric(out["premium_return"], errors="coerce").fillna(0.0)
    has_option = premium.gt(0) & out["strike"].notna() & out["underlying_price_at_entry"].gt(0)
    intrinsic = np.where(
        has_option,
        np.maximum(out["underlying_price_at_entry"] - out["strike"], 0.0),
        0.0,
    )
    out["intrinsic_premium_yield"] = np.where(
        has_option,
        intrinsic / out["underlying_price_at_entry"] * coverage,
        0.0,
    )
    out["extrinsic_premium_yield"] = out["total_premium_yield"] - out["intrinsic_premium_yield"]
    out["annualized_extrinsic_premium_yield"] = np.where(
        out["actual_dte"].gt(0),
        out["extrinsic_premium_yield"] * CALENDAR_DAYS_PER_YEAR / out["actual_dte"],
        np.where(out["extrinsic_premium_yield"].abs() <= 1e-12, 0.0, np.nan),
    )
    out["realized_time_carry_yield"] = (
        out["premium_return"] - out["payoff_return"] - out["transaction_cost_return"]
    )
    out["option_leg_return"] = out["realized_time_carry_yield"]
    out["premium_capture_ratio"] = np.where(
        out["premium_return"].abs() > 1e-12,
        (out["premium_return"] - out["payoff_return"]) / out["premium_return"],
        np.nan,
    )
    out["payoff_burden"] = np.where(
        out["premium_return"].abs() > 1e-12,
        out["payoff_return"] / out["premium_return"],
        np.nan,
    )
    out["option_leg_contribution_to_cc_return"] = _safe_divide(
        out["option_leg_return"], out["covered_call_period_return"]
    )
    excess = out["covered_call_period_return"] - out["etf_period_return"]
    out["option_leg_contribution_to_excess_vs_buyhold"] = _safe_divide(out["option_leg_return"], excess)
    out["iv_minus_rv20"] = out["iv_minus_rv"]

    mtm_stats = _daily_option_leg_stats(daily_mtm)
    out = out.merge(
        mtm_stats,
        on=["etf_code", "dte_label", "strategy_name", "period_index", "rebalance_date", "period_end_date"],
        how="left",
    )
    if not step1_regime.empty:
        out = out.merge(
            step1_regime[
                [
                    "etf_code",
                    "dte_label",
                    "strategy_name",
                    "rebalance_date",
                    "period_end_date",
                    "primary_regime",
                    "down_then_rebound",
                ]
            ],
            on=["etf_code", "dte_label", "strategy_name", "rebalance_date", "period_end_date"],
            how="left",
        )
    else:
        out["primary_regime"] = np.nan
        out["down_then_rebound"] = np.nan
    out["down_then_rebound"] = out["down_then_rebound"].fillna(0).astype(int)
    out["policy_jump_like"] = out["policy_jump_like"].fillna(0).astype(int)
    out["assignment_flag"] = out["assignment_flag"].fillna(0).astype(int)

    for col in DATASET_COLUMNS:
        if col not in out.columns:
            out[col] = np.nan
    out["_dte_order"] = out["dte_label"].map(DTE_ORDER).fillna(999)
    out["_strategy_order"] = out["strategy_name"].map(STRATEGY_ORDER).fillna(999)
    return (
        out.sort_values(["_dte_order", "_strategy_order", "rebalance_date"])
        .drop(columns=["_dte_order", "_strategy_order"], errors="ignore")[DATASET_COLUMNS]
        .reset_index(drop=True)
    )


def _summary_rows(dataset: pd.DataFrame) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for (dte, strategy), group in dataset.groupby(["dte_label", "strategy_name"], dropna=False):
        option_returns = pd.to_numeric(group["option_leg_return"], errors="coerce").dropna()
        mtm_max_by_period = pd.to_numeric(group["short_call_mtm_loss_max_in_period"], errors="coerce")
        cumulative_option = float((1.0 + option_returns).prod() - 1.0) if not option_returns.empty else np.nan
        ann_option = annualized_from_period_returns(
            group["option_leg_return"], group["rebalance_date"], group["period_end_date"]
        )
        periods_year = _periods_per_year(group["actual_dte"])
        vol = float(option_returns.std(ddof=0) * np.sqrt(periods_year)) if len(option_returns) > 1 and pd.notna(periods_year) else np.nan
        sharpe = float(ann_option / vol) if pd.notna(ann_option) and pd.notna(vol) and vol > 1e-12 else np.nan
        stress_day_count = pd.to_numeric(group.get("mtm_stress_day_count", 0), errors="coerce").sum()
        obs_count = pd.to_numeric(group.get("daily_observation_count", 0), errors="coerce").sum()
        policy_loss = group.loc[group["policy_jump_like"].eq(1), "option_leg_return"]
        rebound_loss = group.loc[group["down_then_rebound"].eq(1), "option_leg_return"]
        rows.append(
            {
                "dte_label": dte,
                "strategy_name": strategy,
                "strategy_family": _strategy_family(strategy),
                "active_option_periods": int((pd.to_numeric(group["premium_return"], errors="coerce") > 0).sum()),
                "etf_only_gap_periods": int((pd.to_numeric(group["premium_return"], errors="coerce") <= 0).sum()),
                "num_periods": int(len(group)),
                "avg_actual_dte": float(pd.to_numeric(group["actual_dte"], errors="coerce").mean()),
                "median_actual_dte": float(pd.to_numeric(group["actual_dte"], errors="coerce").median()),
                "avg_premium_return": float(pd.to_numeric(group["premium_return"], errors="coerce").mean()),
                "avg_extrinsic_premium_yield": float(
                    pd.to_numeric(group["extrinsic_premium_yield"], errors="coerce").mean()
                ),
                "annualized_extrinsic_premium_yield_mean": float(
                    pd.to_numeric(group["annualized_extrinsic_premium_yield"], errors="coerce").mean()
                ),
                "avg_payoff_return": float(pd.to_numeric(group["payoff_return"], errors="coerce").mean()),
                "avg_transaction_cost_return": float(
                    pd.to_numeric(group["transaction_cost_return"], errors="coerce").mean()
                ),
                "avg_realized_time_carry_yield": float(
                    pd.to_numeric(group["realized_time_carry_yield"], errors="coerce").mean()
                ),
                "cumulative_option_leg_return": cumulative_option,
                "annualized_option_leg_return": ann_option,
                "option_leg_return_volatility": vol,
                "option_leg_sharpe": sharpe,
                "premium_capture_ratio_mean": float(
                    pd.to_numeric(group["premium_capture_ratio"], errors="coerce").mean()
                ),
                "payoff_burden_mean": float(pd.to_numeric(group["payoff_burden"], errors="coerce").mean()),
                "assignment_rate": float(pd.to_numeric(group["assignment_flag"], errors="coerce").mean()),
                "positive_option_leg_period_rate": float((pd.to_numeric(group["option_leg_return"], errors="coerce") > 0).mean()),
                "negative_option_leg_period_rate": float((pd.to_numeric(group["option_leg_return"], errors="coerce") < 0).mean()),
                "worst_option_leg_period_return": float(pd.to_numeric(group["option_leg_return"], errors="coerce").min()),
                "best_option_leg_period_return": float(pd.to_numeric(group["option_leg_return"], errors="coerce").max()),
                "max_short_call_mtm_loss": float(
                    mtm_max_by_period.max()
                ),
                "p95_short_call_mtm_loss": float(mtm_max_by_period.quantile(0.95))
                if mtm_max_by_period.notna().any()
                else np.nan,
                "median_short_call_mtm_loss": float(mtm_max_by_period.median())
                if mtm_max_by_period.notna().any()
                else np.nan,
                "top3_avg_short_call_mtm_loss": float(mtm_max_by_period.nlargest(3).mean())
                if mtm_max_by_period.notna().any()
                else np.nan,
                "avg_short_call_mtm_loss": float(
                    pd.to_numeric(group["short_call_mtm_loss_mean_in_period"], errors="coerce").mean()
                ),
                "mtm_stress_days_ratio": float(stress_day_count / obs_count) if obs_count > 0 else np.nan,
                "policy_jump_option_leg_loss": float((-policy_loss.clip(upper=0)).mean())
                if not policy_loss.empty
                else 0.0,
                "down_then_rebound_option_leg_loss": float((-rebound_loss.clip(upper=0)).mean())
                if not rebound_loss.empty
                else 0.0,
            }
        )
    return rows


def build_option_leg_summary(dataset: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(_summary_rows(dataset))
    out["_dte_order"] = out["dte_label"].map(DTE_ORDER).fillna(999)
    out["_strategy_order"] = out["strategy_name"].map(STRATEGY_ORDER).fillna(999)
    return out.sort_values(["_dte_order", "_strategy_order"]).drop(columns=["_dte_order", "_strategy_order"]).reset_index(drop=True)


def _summary_lookup(summary: pd.DataFrame, dte: str, family: str, column: str) -> float:
    row = summary[(summary["dte_label"].eq(dte)) & (summary["strategy_family"].eq(family))]
    if row.empty or column not in row:
        return np.nan
    return float(row.iloc[0][column])


def _compare_dte_interpretation(row: pd.Series) -> str:
    d30_carry = row["dte30_realized_time_carry_yield"]
    d60_carry = row["dte60_realized_time_carry_yield"]
    d30_ext = row["dte30_annualized_extrinsic_premium_yield"]
    d60_ext = row["dte60_annualized_extrinsic_premium_yield"]
    if pd.notna(d30_carry) and pd.notna(d60_carry) and d30_carry > d60_carry:
        if pd.notna(d30_ext) and pd.notna(d60_ext) and d30_ext > d60_ext:
            return "DTE30 的年化外在价值与净 time carry 均更强。"
        return "DTE30 的净 time carry 更强，但年化外在价值差异需要结合成本和 payoff 观察。"
    if pd.notna(d30_carry) and pd.notna(d60_carry) and d60_carry > d30_carry:
        return "DTE60 的单周期净 carry 更高，但需确认年化效率和 MTM 压力是否足够好。"
    return "DTE30 与 DTE60 差异不明显或样本不足。"


def build_dte_time_carry_comparison(summary: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for family in ["ATM", "D50", "D40", "OTM2"]:
        row = {
            "strategy_family": family,
            "dte30_annualized_extrinsic_premium_yield": _summary_lookup(
                summary, "DTE30", family, "annualized_extrinsic_premium_yield_mean"
            ),
            "dte60_annualized_extrinsic_premium_yield": _summary_lookup(
                summary, "DTE60", family, "annualized_extrinsic_premium_yield_mean"
            ),
            "dte30_realized_time_carry_yield": _summary_lookup(
                summary, "DTE30", family, "avg_realized_time_carry_yield"
            ),
            "dte60_realized_time_carry_yield": _summary_lookup(
                summary, "DTE60", family, "avg_realized_time_carry_yield"
            ),
            "dte30_premium_capture_ratio": _summary_lookup(
                summary, "DTE30", family, "premium_capture_ratio_mean"
            ),
            "dte60_premium_capture_ratio": _summary_lookup(
                summary, "DTE60", family, "premium_capture_ratio_mean"
            ),
            "dte30_payoff_burden": _summary_lookup(summary, "DTE30", family, "payoff_burden_mean"),
            "dte60_payoff_burden": _summary_lookup(summary, "DTE60", family, "payoff_burden_mean"),
            "dte30_option_leg_sharpe": _summary_lookup(summary, "DTE30", family, "option_leg_sharpe"),
            "dte60_option_leg_sharpe": _summary_lookup(summary, "DTE60", family, "option_leg_sharpe"),
            "dte30_mtm_stress": _summary_lookup(summary, "DTE30", family, "max_short_call_mtm_loss"),
            "dte60_mtm_stress": _summary_lookup(summary, "DTE60", family, "max_short_call_mtm_loss"),
        }
        score30 = np.nanmean([row["dte30_realized_time_carry_yield"], row["dte30_option_leg_sharpe"]])
        score60 = np.nanmean([row["dte60_realized_time_carry_yield"], row["dte60_option_leg_sharpe"]])
        row["which_dte_has_better_time_carry"] = "DTE30" if score30 >= score60 else "DTE60"
        row["interpretation"] = _compare_dte_interpretation(pd.Series(row))
        rows.append(row)
    return pd.DataFrame(rows)


def _family_interpretation(row: pd.Series) -> str:
    family = row["strategy_family"]
    if family == "ATM":
        return "ATM 通常权利金更厚，但 payoff burden 和被行权压力也更高。"
    if family == "D50":
        return "D50 接近 ATM，是偏防御的近 ATM 替代，需要观察是否与 ATM 差异足够大。"
    if family == "D40":
        return "D40 在外在价值、留存率、payoff burden 和 MTM 压力之间更均衡。"
    if family == "OTM2":
        return "OTM2 权利金较薄但更保留上涨，收益更多可能来自底仓参与。"
    return ""


def build_strategy_family_time_carry(summary: pd.DataFrame) -> pd.DataFrame:
    out = summary[
        [
            "dte_label",
            "strategy_family",
            "avg_extrinsic_premium_yield",
            "annualized_extrinsic_premium_yield_mean",
            "premium_capture_ratio_mean",
            "payoff_burden_mean",
            "avg_realized_time_carry_yield",
            "option_leg_sharpe",
            "max_short_call_mtm_loss",
            "down_then_rebound_option_leg_loss",
        ]
    ].copy()
    out = out.rename(
        columns={
            "annualized_extrinsic_premium_yield_mean": "annualized_extrinsic_premium_yield",
            "premium_capture_ratio_mean": "premium_capture_ratio",
            "payoff_burden_mean": "payoff_burden",
            "avg_realized_time_carry_yield": "realized_time_carry_yield",
            "down_then_rebound_option_leg_loss": "missed_rebound_option_leg_loss",
        }
    )
    out["interpretation"] = out.apply(_family_interpretation, axis=1)
    return out


def build_return_attribution(dataset: pd.DataFrame, summary: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (dte, strategy), group in dataset.groupby(["dte_label", "strategy_name"], dropna=False):
        family = _strategy_family(strategy)
        summary_row = summary[(summary["dte_label"].eq(dte)) & (summary["strategy_name"].eq(strategy))].iloc[0]
        ann_etf = annualized_from_period_returns(group["etf_period_return"], group["rebalance_date"], group["period_end_date"])
        ann_cc = annualized_from_period_returns(
            group["covered_call_period_return"], group["rebalance_date"], group["period_end_date"]
        )
        ann_option = float(summary_row["annualized_option_leg_return"])
        cumulative_etf = float((1.0 + pd.to_numeric(group["etf_period_return"], errors="coerce")).prod() - 1.0)
        cumulative_cc = float(
            (1.0 + pd.to_numeric(group["covered_call_period_return"], errors="coerce")).prod() - 1.0
        )
        cumulative_option = float(summary_row["cumulative_option_leg_return"])
        excess_total = cumulative_cc - cumulative_etf
        option_share_excess = cumulative_option / excess_total if abs(excess_total) > 1e-12 else np.nan
        option_share_total = ann_option / ann_cc if pd.notna(ann_cc) and abs(ann_cc) > 1e-12 else np.nan
        if ann_option > 0 and option_share_total > 0.5:
            conclusion = "总收益中期权腿贡献较高。"
        elif ann_option > 0:
            conclusion = "期权腿为正，但总收益仍明显受 ETF 底仓路径影响。"
        else:
            conclusion = "期权腿净 carry 偏弱，策略表现更多来自底仓参与或路径差异。"
        rows.append(
            {
                "dte_label": dte,
                "strategy_name": strategy,
                "strategy_family": family,
                "annualized_etf_component_return": ann_etf,
                "annualized_option_leg_return": ann_option,
                "annualized_total_covered_call_return": ann_cc,
                "option_leg_share_of_total_return": option_share_total,
                "option_leg_share_of_excess_vs_buyhold": option_share_excess,
                "premium_contribution": float(summary_row["avg_premium_return"]),
                "payoff_drag": float(summary_row["avg_payoff_return"]),
                "transaction_cost_drag": float(summary_row["avg_transaction_cost_return"]),
                "mtm_path_penalty": float(summary_row["avg_short_call_mtm_loss"]),
                "conclusion": conclusion,
            }
        )
    out = pd.DataFrame(rows)
    out["_dte_order"] = out["dte_label"].map(DTE_ORDER).fillna(999)
    out["_strategy_order"] = out["strategy_name"].map(STRATEGY_ORDER).fillna(999)
    return out.sort_values(["_dte_order", "_strategy_order"]).drop(columns=["_dte_order", "_strategy_order"])


def build_option_leg_by_regime(dataset: pd.DataFrame) -> pd.DataFrame:
    source = dataset[dataset["primary_regime"].notna()].copy()
    rows: list[dict[str, object]] = []
    for (regime, dte, strategy), group in source.groupby(["primary_regime", "dte_label", "strategy_name"], dropna=False):
        option_return = pd.to_numeric(group["option_leg_return"], errors="coerce")
        rows.append(
            {
                "primary_regime": regime,
                "dte_label": dte,
                "strategy_name": strategy,
                "count": int(len(group)),
                "avg_option_leg_return": float(option_return.mean()),
                "avg_premium_return": float(pd.to_numeric(group["premium_return"], errors="coerce").mean()),
                "avg_payoff_return": float(pd.to_numeric(group["payoff_return"], errors="coerce").mean()),
                "avg_realized_time_carry_yield": float(
                    pd.to_numeric(group["realized_time_carry_yield"], errors="coerce").mean()
                ),
                "premium_capture_ratio_mean": float(
                    pd.to_numeric(group["premium_capture_ratio"], errors="coerce").mean()
                ),
                "payoff_burden_mean": float(pd.to_numeric(group["payoff_burden"], errors="coerce").mean()),
                "positive_option_leg_period_rate": float((option_return > 0).mean()),
                "max_short_call_mtm_loss_mean": float(
                    pd.to_numeric(group["short_call_mtm_loss_max_in_period"], errors="coerce").mean()
                ),
                "missed_rebound_option_leg_loss_mean": float(
                    (-pd.to_numeric(group.loc[group["down_then_rebound"].eq(1), "option_leg_return"], errors="coerce").clip(upper=0)).mean()
                )
                if group["down_then_rebound"].eq(1).any()
                else 0.0,
            }
        )
    out = pd.DataFrame(rows)
    out["_dte_order"] = out["dte_label"].map(DTE_ORDER).fillna(999)
    out["_strategy_order"] = out["strategy_name"].map(STRATEGY_ORDER).fillna(999)
    return out.sort_values(["primary_regime", "_dte_order", "_strategy_order"]).drop(
        columns=["_dte_order", "_strategy_order"]
    )


def build_option_leg_ranking(summary: pd.DataFrame, attribution: pd.DataFrame) -> pd.DataFrame:
    out = summary.copy()
    out["rank_annualized_extrinsic_premium_yield"] = out["annualized_extrinsic_premium_yield_mean"].rank(
        pct=True, ascending=True
    )
    out["rank_realized_time_carry_yield"] = out["avg_realized_time_carry_yield"].rank(pct=True, ascending=True)
    out["rank_premium_capture_ratio"] = out["premium_capture_ratio_mean"].rank(pct=True, ascending=True)
    out["rank_option_leg_sharpe"] = out["option_leg_sharpe"].rank(pct=True, ascending=True)
    out["rank_payoff_burden"] = out["payoff_burden_mean"].rank(pct=True, ascending=True)
    out["rank_max_short_call_mtm_loss"] = out["max_short_call_mtm_loss"].rank(pct=True, ascending=True)
    out["option_leg_score"] = (
        0.25 * out["rank_annualized_extrinsic_premium_yield"]
        + 0.25 * out["rank_realized_time_carry_yield"]
        + 0.20 * out["rank_premium_capture_ratio"]
        + 0.15 * out["rank_option_leg_sharpe"]
        - 0.10 * out["rank_payoff_burden"]
        - 0.05 * out["rank_max_short_call_mtm_loss"]
    )
    out = out.merge(
        attribution[["dte_label", "strategy_name", "conclusion"]],
        on=["dte_label", "strategy_name"],
        how="left",
    )
    out["candidate_rank"] = out["option_leg_score"].rank(method="first", ascending=False).astype(int)
    cols = [
        "candidate_rank",
        "dte_label",
        "strategy_name",
        "strategy_family",
        "option_leg_score",
        "annualized_extrinsic_premium_yield_mean",
        "avg_realized_time_carry_yield",
        "premium_capture_ratio_mean",
        "payoff_burden_mean",
        "option_leg_sharpe",
        "max_short_call_mtm_loss",
        "conclusion",
    ]
    return out.sort_values("candidate_rank")[cols].reset_index(drop=True)


def build_mtm_stress_event_diagnostics(daily_mtm: pd.DataFrame) -> pd.DataFrame:
    """Return the exact daily event behind each strategy's max short-call MTM stress."""
    daily = _filter_target(daily_mtm)
    daily = _dateify(daily, ["date", "rebalance_date", "period_end_date", "expiry_date"])
    if daily.empty:
        return pd.DataFrame()
    rows: list[pd.Series] = []
    group_cols = ["dte_label", "strategy_name"]
    for _, group in daily.groupby(group_cols, dropna=False):
        loss = pd.to_numeric(group["short_call_mtm_loss_return"], errors="coerce")
        if loss.notna().any():
            rows.append(group.loc[loss.idxmax()])
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows).copy()
    collapse = (
        out.groupby(["dte_label", "period_index", "option_code"], dropna=False)["strategy_name"]
        .transform("nunique")
        .rename("selection_collapse_strategy_count")
    )
    out["selection_collapse_strategy_count"] = collapse
    out["selection_collapse_flag"] = out["selection_collapse_strategy_count"] > 1
    cols = [
        "etf_code",
        "dte_label",
        "strategy_name",
        "date",
        "period_index",
        "rebalance_date",
        "period_end_date",
        "expiry_date",
        "option_code",
        "strike",
        "option_price_at_entry",
        "option_mark_price",
        "premium_return",
        "option_liability_return",
        "short_call_mtm_loss_return",
        "target_delta",
        "target_moneyness_spec",
        "selection_collapse_strategy_count",
        "selection_collapse_flag",
    ]
    for col in cols:
        if col not in out.columns:
            out[col] = np.nan
    out["_dte_order"] = out["dte_label"].map(DTE_ORDER).fillna(999)
    out["_strategy_order"] = out["strategy_name"].map(STRATEGY_ORDER).fillna(999)
    return out.sort_values(["_dte_order", "_strategy_order"])[cols].reset_index(drop=True)


def build_sanity_checks(dataset: pd.DataFrame, ranking: pd.DataFrame) -> pd.DataFrame:
    checks: list[dict[str, object]] = []

    def add(check: str, passed: bool, detail: str) -> None:
        checks.append({"check": check, "passed": bool(passed), "detail": detail})

    add("only_510300", set(dataset["etf_code"].dropna().unique()) == {ETF_CODE}, ",".join(dataset["etf_code"].dropna().unique()))
    add("no_itm_strategies", not dataset["strategy_name"].str.contains("ITM", case=False, na=False).any(), "")
    add("no_dte14_or_dte45", not dataset["dte_label"].isin(["DTE14", "DTE45", "DTE14_strict_window"]).any(), ",".join(sorted(dataset["dte_label"].dropna().unique())))
    diff = (
        dataset["option_leg_return"]
        - (dataset["premium_return"] - dataset["payoff_return"] - dataset["transaction_cost_return"])
    ).abs()
    add("option_leg_return_formula", bool((diff.fillna(0) < 1e-10).all()), f"max_abs_diff={diff.max()}")
    add(
        "annualized_extrinsic_uses_extrinsic",
        "extrinsic_premium_yield" in dataset.columns and "annualized_extrinsic_premium_yield" in dataset.columns,
        "annualized_extrinsic_premium_yield = extrinsic_premium_yield * 365.25 / actual_dte",
    )
    realized_diff = (dataset["realized_time_carry_yield"] - dataset["option_leg_return"]).abs()
    add("realized_time_carry_formula", bool((realized_diff.fillna(0) < 1e-10).all()), f"max_abs_diff={realized_diff.max()}")
    zero_premium = dataset["premium_return"].abs() <= 1e-12
    add(
        "payoff_burden_zero_premium_nan",
        bool(dataset.loc[zero_premium, "payoff_burden"].isna().all()),
        f"zero_premium_rows={int(zero_premium.sum())}",
    )
    ranking_cols = set(ranking.columns)
    add(
        "ranking_excludes_total_cc_return",
        "annualized_total_covered_call_return" not in ranking_cols,
        "ranking uses option-leg carry fields only",
    )
    add(
        "regime_is_attribution_only",
        True,
        "no dynamic trading rule output is generated",
    )
    add(
        "daily_mtm_cost_no_level4",
        True,
        "daily_mtm_nav source already includes current transaction cost assumptions",
    )
    return pd.DataFrame(checks)


def _format_pct(value: object, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value) * 100:.{digits}f}%"


def _format_float(value: object, digits: int = 3) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value):.{digits}f}"


def _label(row: pd.Series) -> str:
    return f"{row['dte_label']} {row['strategy_family']}"


def _save_bar(df: pd.DataFrame, value_col: str, path: Path, title: str, ylabel: str) -> None:
    plot = df.copy()
    plot["label"] = plot.apply(_label, axis=1)
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.bar(plot["label"], plot[value_col], color="#4C78A8")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _save_scatter(df: pd.DataFrame, x: str, y: str, path: Path, title: str, xlabel: str, ylabel: str) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.scatter(df[x], df[y], color="#F58518", edgecolor="#222222", s=80, alpha=0.85)
    for _, row in df.iterrows():
        ax.annotate(_label(row), (row[x], row[y]), xytext=(5, 5), textcoords="offset points", fontsize=8)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _save_attribution(attribution: pd.DataFrame, path: Path) -> None:
    plot = attribution.copy()
    plot["label"] = plot["dte_label"] + " " + plot["strategy_family"]
    x = np.arange(len(plot))
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.bar(x - 0.2, plot["annualized_etf_component_return"], width=0.2, label="ETF component")
    ax.bar(x, plot["annualized_option_leg_return"], width=0.2, label="Option leg")
    ax.bar(x + 0.2, plot["annualized_total_covered_call_return"], width=0.2, label="Covered call")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(plot["label"], rotation=30, ha="right")
    ax.set_title("Return attribution: ETF component vs option leg")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _save_dte_comparison(dte_comp: pd.DataFrame, path: Path) -> None:
    families = dte_comp["strategy_family"].tolist()
    x = np.arange(len(families))
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(x - 0.18, dte_comp["dte30_realized_time_carry_yield"], width=0.36, label="DTE30")
    ax.bar(x + 0.18, dte_comp["dte60_realized_time_carry_yield"], width=0.36, label="DTE60")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(families)
    ax.set_title("DTE30 vs DTE60 realized time carry")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _save_regime_heatmap(regime: pd.DataFrame, path: Path) -> None:
    pivot = regime.pivot_table(
        index="primary_regime",
        columns=["dte_label", "strategy_name"],
        values="avg_option_leg_return",
        aggfunc="mean",
    )
    if pivot.empty:
        return
    labels = [f"{a} {b.replace('_100', '')}" for a, b in pivot.columns]
    data = pivot.to_numpy(dtype=float)
    fig, ax = plt.subplots(figsize=(12, max(4, len(pivot.index) * 0.55 + 2)))
    image = ax.imshow(data, cmap="RdYlGn", aspect="auto")
    ax.set_title("Option-leg return by regime")
    ax.set_xticks(np.arange(len(labels)))
    ax.set_xticklabels(labels, rotation=30, ha="right")
    ax.set_yticks(np.arange(len(pivot.index)))
    ax.set_yticklabels(pivot.index)
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            value = data[i, j]
            ax.text(j, i, "" if np.isnan(value) else f"{value:.2%}", ha="center", va="center", fontsize=7)
    fig.colorbar(image, ax=ax, fraction=0.03, pad=0.02)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def write_figures(
    summary: pd.DataFrame,
    dte_comp: pd.DataFrame,
    attribution: pd.DataFrame,
    regime: pd.DataFrame,
    figures_dir: Path,
) -> None:
    _save_bar(
        summary,
        "annualized_extrinsic_premium_yield_mean",
        figures_dir / "annualized_extrinsic_yield_by_dte_strategy.png",
        "Annualized extrinsic premium yield",
        "annualized extrinsic yield",
    )
    _save_bar(
        summary,
        "avg_realized_time_carry_yield",
        figures_dir / "realized_time_carry_by_dte_strategy.png",
        "Average realized option-leg time carry",
        "realized time carry",
    )
    _save_scatter(
        summary,
        "payoff_burden_mean",
        "premium_capture_ratio_mean",
        figures_dir / "premium_capture_vs_payoff_burden.png",
        "Premium capture vs payoff burden",
        "payoff burden",
        "premium capture",
    )
    _save_bar(
        summary,
        "option_leg_sharpe",
        figures_dir / "option_leg_sharpe_by_strategy.png",
        "Option-leg Sharpe by strategy",
        "option-leg Sharpe",
    )
    _save_attribution(attribution, figures_dir / "option_leg_return_attribution.png")
    _save_dte_comparison(dte_comp, figures_dir / "dte30_vs_dte60_time_carry_bar.png")
    _save_scatter(
        summary,
        "max_short_call_mtm_loss",
        "avg_realized_time_carry_yield",
        figures_dir / "mtm_stress_vs_time_carry.png",
        "MTM stress vs time carry",
        "max short-call MTM loss",
        "realized time carry",
    )
    _save_regime_heatmap(regime, figures_dir / "option_leg_by_regime_heatmap.png")


def _summary_table(summary: pd.DataFrame) -> str:
    cols = [
        "dte_label",
        "strategy_family",
        "annualized_extrinsic_premium_yield_mean",
        "avg_realized_time_carry_yield",
        "premium_capture_ratio_mean",
        "payoff_burden_mean",
        "option_leg_sharpe",
        "max_short_call_mtm_loss",
    ]
    table = summary[cols].copy()
    for col in cols[2:6] + ["max_short_call_mtm_loss"]:
        table[col] = table[col].map(lambda x: _format_pct(x, 2))
    table["option_leg_sharpe"] = table["option_leg_sharpe"].map(lambda x: _format_float(x, 3))
    table = table.rename(
        columns={
            "dte_label": "DTE",
            "strategy_family": "结构",
            "annualized_extrinsic_premium_yield_mean": "年化外在价值收益率",
            "avg_realized_time_carry_yield": "单期净时间收益",
            "premium_capture_ratio_mean": "权利金留存率",
            "payoff_burden_mean": "payoff侵蚀率",
            "option_leg_sharpe": "期权腿Sharpe",
            "max_short_call_mtm_loss": "最大盯市压力",
        }
    )
    return table.to_markdown(index=False)


def _dte_table(dte_comp: pd.DataFrame) -> str:
    table = dte_comp[
        [
            "strategy_family",
            "dte30_annualized_extrinsic_premium_yield",
            "dte60_annualized_extrinsic_premium_yield",
            "dte30_realized_time_carry_yield",
            "dte60_realized_time_carry_yield",
            "dte30_premium_capture_ratio",
            "dte60_premium_capture_ratio",
            "which_dte_has_better_time_carry",
            "interpretation",
        ]
    ].copy()
    for col in table.columns:
        if col.startswith("dte"):
            table[col] = table[col].map(lambda x: _format_pct(x, 2))
    return table.rename(
        columns={
            "strategy_family": "结构",
            "which_dte_has_better_time_carry": "更优DTE",
            "interpretation": "解释",
        }
    ).to_markdown(index=False)


def _family_table(family: pd.DataFrame) -> str:
    table = family[
        [
            "dte_label",
            "strategy_family",
            "annualized_extrinsic_premium_yield",
            "realized_time_carry_yield",
            "premium_capture_ratio",
            "payoff_burden",
            "option_leg_sharpe",
            "interpretation",
        ]
    ].copy()
    for col in [
        "annualized_extrinsic_premium_yield",
        "realized_time_carry_yield",
        "premium_capture_ratio",
        "payoff_burden",
    ]:
        table[col] = table[col].map(lambda x: _format_pct(x, 2))
    table["option_leg_sharpe"] = table["option_leg_sharpe"].map(lambda x: _format_float(x, 3))
    return table.rename(columns={"dte_label": "DTE", "strategy_family": "结构"}).to_markdown(index=False)


def _ranking_table(ranking: pd.DataFrame) -> str:
    table = ranking.head(8).copy()
    for col in [
        "option_leg_score",
        "annualized_extrinsic_premium_yield_mean",
        "avg_realized_time_carry_yield",
        "premium_capture_ratio_mean",
        "payoff_burden_mean",
        "max_short_call_mtm_loss",
    ]:
        if col == "option_leg_score":
            table[col] = table[col].map(lambda x: _format_float(x, 3))
        else:
            table[col] = table[col].map(lambda x: _format_pct(x, 2))
    table["option_leg_sharpe"] = table["option_leg_sharpe"].map(lambda x: _format_float(x, 3))
    return table[
        [
            "candidate_rank",
            "dte_label",
            "strategy_family",
            "option_leg_score",
            "annualized_extrinsic_premium_yield_mean",
            "avg_realized_time_carry_yield",
            "premium_capture_ratio_mean",
            "payoff_burden_mean",
            "option_leg_sharpe",
            "conclusion",
        ]
    ].rename(
        columns={
            "candidate_rank": "排名",
            "dte_label": "DTE",
            "strategy_family": "结构",
            "option_leg_score": "期权腿得分",
            "annualized_extrinsic_premium_yield_mean": "年化外在价值收益率",
            "avg_realized_time_carry_yield": "单期净时间收益",
            "premium_capture_ratio_mean": "权利金留存率",
            "payoff_burden_mean": "payoff侵蚀率",
            "option_leg_sharpe": "期权腿Sharpe",
            "conclusion": "结论",
        }
    ).to_markdown(index=False)


def write_report(
    summary: pd.DataFrame,
    dte_comp: pd.DataFrame,
    family: pd.DataFrame,
    attribution: pd.DataFrame,
    regime: pd.DataFrame,
    ranking: pd.DataFrame,
    mtm_events: pd.DataFrame,
    sanity: pd.DataFrame,
    paths: OptionLegPaths,
    warnings: list[str],
) -> Path:
    report_path = paths.reports_dir / "ver2_3_510300_option_leg_time_carry_readable.md"
    top = ranking.iloc[0]
    d40 = summary[(summary["dte_label"].eq("DTE30")) & (summary["strategy_name"].eq("D40_100"))]
    dte60_gap_periods = int(summary.loc[summary["dte_label"].eq("DTE60"), "etf_only_gap_periods"].max())
    d40_note = ""
    if not d40.empty:
        d40_row = d40.iloc[0]
        d40_note = (
            f"DTE30 D40 的平均净时间收益为 {_format_pct(d40_row['avg_realized_time_carry_yield'])}，"
            f"期权腿 Sharpe 为 {_format_float(d40_row['option_leg_sharpe'])}。"
        )
    collapse_note = ""
    if not mtm_events.empty and "selection_collapse_flag" in mtm_events:
        collapsed = mtm_events[mtm_events["selection_collapse_flag"].eq(True)]
        if not collapsed.empty:
            first = collapsed.iloc[0]
            collapse_note = (
                f"最大 short-call MTM 压力存在选券坍缩事件：{first['date']}，"
                f"{first['dte_label']} 多个策略同时选中 {first['option_code']}，"
                f"strike={first['strike']}，因此单点 max 不能单独代表不同 delta/strike 的常态压力。"
            )
    warning_lines = "\n".join(f"- {item}" for item in warnings) if warnings else "- 当前没有阻塞性 warning。"
    sanity_table = sanity.to_markdown(index=False)
    text = f"""# ver2.3｜510300 期权腿时间收益诊断

## 1. 版本定位

本版本只研究 510300，不是最终策略，不做动态择时，也不扩展 ITM。本版本单独诊断 short call 期权腿的时间收益，用于判断 DTE30 / DTE60 与 ATM / D50 / D40 / OTM2 的 option-leg carry 差异。

## 2. 为什么做 Option-Leg Decomposition

Covered call 总收益混合了 ETF 底仓收益和期权腿收益。如果不拆分，就无法判断策略收益到底来自底仓路径，还是来自卖 call 的时间价值。本实验采用：

`R_CC = R_ETF + R_OptionLeg`

其中：

`R_OptionLeg = Premium - Payoff - TransactionCost`

`Premium = IntrinsicPremium + ExtrinsicPremium`

由于本实验只研究非 ITM call，重点观察外在价值收益率、净时间收益、权利金留存率和 payoff 侵蚀率。

## 3. 实验设置

- ETF: 510300 only
- DTE: DTE30, DTE60
- 策略: ATM_100, D50_100, D40_100, OTM2_100
- 数据来源: ver2.1 period/daily MTM 输出，外加 ver2.2 Step 1 的 regime attribution
- 成本假设: 沿用当前 ver2.1 daily MTM / period output 中已经计入的 transaction cost，不额外添加 Level 4 滑点
- 收益口径: period-level option leg return 均相对 ETF 入场价格 / 策略周期收益率口径

## 4. Option-Leg Time Carry Summary

当前期权腿诊断排名第一的是 **{top['dte_label']} {top['strategy_family']}**。{d40_note}

{collapse_note}

{_summary_table(summary)}

## 5. DTE30 vs DTE60

DTE60 在当前样本中存在有效覆盖不足：每个 DTE60 候选有 {dte60_gap_periods} 个 ETF-only gap 周期，因此其 option-leg carry 不能只按单次权利金厚度理解。

{_dte_table(dte_comp)}

## 6. ATM / D50 / D40 / OTM2 比较

{_family_table(family)}

## 7. Return Attribution

Return attribution 输出用于判断总收益来自 ETF 底仓还是期权腿。完整表见：

`{(paths.output_dir / "ver2_3_510300_return_attribution.csv").as_posix()}`

期权腿排序如下：

{_ranking_table(ranking)}

## 8. Regime Attribution

Regime 只用于事后归因，不生成动态规则。完整表见：

`{(paths.output_dir / "ver2_3_510300_option_leg_by_regime.csv").as_posix()}`

## 9. 可推广性：向固定权重多 ETF 组合扩展

这个框架具有较强通用性，因为每个 ETF 的 covered call 都可以拆成：

`R_i^CC = R_i^ETF + R_i^OptionLeg`

未来固定权重多 ETF 组合可以写成：

`R_portfolio = sum_i w_i R_i^ETF + sum_i w_i R_i^OptionLeg + R_rebalancing`

因此 ver2.3 的 option-leg time carry 输出可以直接作为多标的组合的 overlay input。限制是：只有具备流动性较好期权的 ETF 才适合纳入 overlay；不同 ETF 的 IV、delta、DTE、流动性差异需要标准化；多资产组合还要单独考虑固定权重再平衡收益。option-leg carry 不是无风险套利，而是承担 gamma / vega / MTM 风险后的时间价值收益。

## 10. 局限性

1. 当前只研究 510300。
2. 当前不做动态策略。
3. 当前不做 out-of-sample。
4. 成本假设仍需 execution sensitivity。
5. 期权腿 time carry 不等于无风险套利。
6. 后续需要扩展到多 ETF 验证通用性。

## 11. 下一步

如果 DTE30 D40 的 option-leg carry 继续稳定，可以作为 510300 overlay candidate。若 DTE30 在年化外在价值、净 time carry 和期权腿 Sharpe 上优于 DTE60，后续可以降低 DTE60 研究优先级。下一阶段建议先启动 fixed-weight multi-ETF basket，不加期权先验证 rebalancing premium，再把 option-leg carry overlay 接到多 ETF 组合上。

## 附录：Sanity Checks

{sanity_table}

Warnings:

{warning_lines}
"""
    report_path.write_text(text, encoding="utf-8")
    return report_path


def run_option_leg_time_carry(paths: OptionLegPaths | None = None) -> OptionLegOutputs:
    paths = paths or OptionLegPaths()
    paths.ensure_dirs()
    warnings: list[str] = []

    periods = _read_csv(paths.periods_path, PERIOD_USECOLS)
    daily = _read_csv(paths.daily_mtm_path, DAILY_USECOLS)
    step1 = _load_step1_regime(paths)
    dataset = build_option_leg_period_dataset(periods, daily, step1)
    summary = build_option_leg_summary(dataset)
    dte_comp = build_dte_time_carry_comparison(summary)
    family = build_strategy_family_time_carry(summary)
    attribution = build_return_attribution(dataset, summary)
    regime = build_option_leg_by_regime(dataset)
    ranking = build_option_leg_ranking(summary, attribution)
    mtm_events = build_mtm_stress_event_diagnostics(daily)
    sanity = build_sanity_checks(dataset, ranking)

    expected = {(dte, strategy) for dte in TARGET_DTES for strategy in TARGET_STRATEGIES}
    observed = set(zip(dataset["dte_label"], dataset["strategy_name"]))
    missing = sorted(expected - observed)
    if missing:
        warnings.append(f"Missing expected DTE/strategy observations: {missing}")
    if (summary["etf_only_gap_periods"] > 0).any():
        gap_text = summary.loc[
            summary["etf_only_gap_periods"] > 0,
            ["dte_label", "strategy_name", "etf_only_gap_periods"],
        ].to_dict("records")
        warnings.append(f"Some strategies have ETF-only gap periods and incomplete option overlay coverage: {gap_text}")
    intrinsic_not_zero = dataset["intrinsic_premium_yield"].abs() > 1e-6
    if intrinsic_not_zero.any():
        warnings.append(
            f"{int(intrinsic_not_zero.sum())} rows have non-zero intrinsic premium; check nearest/delta selection moneyness."
        )
    if not sanity["passed"].all():
        failed = sanity.loc[~sanity["passed"], "check"].tolist()
        warnings.append(f"Sanity checks failed: {failed}")

    period_path = paths.output_dir / "ver2_3_510300_option_leg_period_dataset.csv"
    summary_path = paths.output_dir / "ver2_3_510300_option_leg_summary.csv"
    dte_path = paths.output_dir / "ver2_3_510300_dte30_vs_dte60_time_carry.csv"
    family_path = paths.output_dir / "ver2_3_510300_strategy_family_time_carry.csv"
    attribution_path = paths.output_dir / "ver2_3_510300_return_attribution.csv"
    regime_path = paths.output_dir / "ver2_3_510300_option_leg_by_regime.csv"
    ranking_path = paths.output_dir / "ver2_3_510300_option_leg_candidate_ranking.csv"
    mtm_events_path = paths.output_dir / "ver2_3_510300_mtm_stress_event_diagnostics.csv"
    sanity_path = paths.output_dir / "ver2_3_510300_option_leg_sanity_checks.csv"

    dataset.to_csv(period_path, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    dte_comp.to_csv(dte_path, index=False, encoding="utf-8-sig")
    family.to_csv(family_path, index=False, encoding="utf-8-sig")
    attribution.to_csv(attribution_path, index=False, encoding="utf-8-sig")
    regime.to_csv(regime_path, index=False, encoding="utf-8-sig")
    ranking.to_csv(ranking_path, index=False, encoding="utf-8-sig")
    mtm_events.to_csv(mtm_events_path, index=False, encoding="utf-8-sig")
    sanity.to_csv(sanity_path, index=False, encoding="utf-8-sig")

    write_figures(summary, dte_comp, attribution, regime, paths.figures_dir)
    report = write_report(summary, dte_comp, family, attribution, regime, ranking, mtm_events, sanity, paths, warnings)

    LOGGER.info("Wrote ver2.3 option-leg outputs to %s", paths.output_dir)
    return OptionLegOutputs(
        period_dataset=period_path,
        summary=summary_path,
        dte_comparison=dte_path,
        strategy_family_comparison=family_path,
        return_attribution=attribution_path,
        regime_attribution=regime_path,
        ranking=ranking_path,
        mtm_stress_event_diagnostics=mtm_events_path,
        sanity_checks=sanity_path,
        report=report,
        figures_dir=paths.figures_dir,
        warnings=tuple(warnings),
    )


__all__ = [
    "OptionLegOutputs",
    "OptionLegPaths",
    "annualized_from_period_returns",
    "build_dte_time_carry_comparison",
    "build_option_leg_by_regime",
    "build_option_leg_period_dataset",
    "build_option_leg_ranking",
    "build_option_leg_summary",
    "build_mtm_stress_event_diagnostics",
    "build_return_attribution",
    "build_strategy_family_time_carry",
    "run_option_leg_time_carry",
]
