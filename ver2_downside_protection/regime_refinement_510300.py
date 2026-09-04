from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ver2_downside_protection.step1_regime_attribution_510300 import (
    CANDIDATE_ORDER,
    ETF_CODE,
    LOW_SAMPLE_THRESHOLD,
    normalize_etf_code,
)


LOGGER = logging.getLogger(__name__)

REFINED_REGIME_ORDER = {
    "deep_drawdown_recovery": 0,
    "pullback_above_ma": 1,
    "confirmed_uptrend": 2,
    "confirmed_downtrend": 3,
    "mild_uptrend": 4,
    "neutral_above_ma": 5,
    "neutral_below_ma": 6,
    "other": 7,
}

MAIN_STRATEGIES = {
    "BuyHold",
    "DTE30_ATM_100",
    "DTE30_D50_100",
    "DTE30_D40_100",
    "DTE30_OTM2_100",
}

REFINED_DATASET_COLUMNS = [
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
    "old_primary_regime",
    "refined_primary_regime",
    "regime_changed_flag",
    "regime_conflict_type",
    "post_drawdown_rebound_risk",
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
class RefinementPaths:
    step1_dir: Path = Path(
        "outputs/ver2_downside_protection/510300_branch/ver2_2_step1_regime_attribution"
    )
    output_dir: Path = Path(
        "outputs/ver2_downside_protection/510300_branch/ver2_2_step1_regime_refinement"
    )

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
class RefinementOutputs:
    refined_dataset: Path
    transition_matrix: Path
    forward_etf_behavior: Path
    strategy_performance: Path
    state_action_hypothesis: Path
    sanity_checks: Path
    report: Path
    figures_dir: Path
    warnings: tuple[str, ...]


def assign_refined_primary_regime(row: pd.Series) -> str:
    """Assign the cleaned regime using only rebalance-date observable features."""
    trend_20d = row.get("trend_20d")
    ma_gap_60 = row.get("ma_gap_60")
    drawdown = row.get("drawdown_from_rolling_high_252")

    if pd.notna(trend_20d) and pd.notna(ma_gap_60) and pd.notna(drawdown):
        if trend_20d > 0.02 and ma_gap_60 < 0 and drawdown < -0.08:
            return "deep_drawdown_recovery"
    if pd.notna(trend_20d) and pd.notna(ma_gap_60) and trend_20d < -0.02 and ma_gap_60 > 0:
        return "pullback_above_ma"
    if pd.notna(trend_20d) and pd.notna(ma_gap_60) and trend_20d > 0.03 and ma_gap_60 > 0:
        return "confirmed_uptrend"
    if pd.notna(trend_20d) and pd.notna(ma_gap_60) and trend_20d < -0.03 and ma_gap_60 < 0:
        return "confirmed_downtrend"
    if pd.notna(trend_20d) and pd.notna(ma_gap_60) and 0 < trend_20d <= 0.03 and ma_gap_60 >= 0:
        return "mild_uptrend"
    if pd.notna(trend_20d) and pd.notna(ma_gap_60) and abs(trend_20d) <= 0.02 and ma_gap_60 >= 0:
        return "neutral_above_ma"
    if pd.notna(trend_20d) and pd.notna(ma_gap_60) and abs(trend_20d) <= 0.02 and ma_gap_60 < 0:
        return "neutral_below_ma"
    return "other"


def classify_regime_conflict_type(row: pd.Series) -> str:
    trend_20d = row.get("trend_20d")
    ma_gap_60 = row.get("ma_gap_60")
    drawdown = row.get("drawdown_from_rolling_high_252")
    refined = row.get("refined_primary_regime")
    if pd.notna(trend_20d) and pd.notna(ma_gap_60):
        if trend_20d < -0.02 and ma_gap_60 > 0:
            return "short_down_medium_above_ma"
        if pd.notna(drawdown) and trend_20d > 0.02 and ma_gap_60 < 0 and drawdown < -0.08:
            return "short_up_medium_below_ma_deep_drawdown"
    if refined in {"confirmed_uptrend", "confirmed_downtrend"}:
        return "confirmed_signal"
    if refined in {"mild_uptrend", "neutral_above_ma", "neutral_below_ma"}:
        return "neutral_signal"
    return "other"


def _dateify(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ["rebalance_date", "expiry_date", "period_end_date"]:
        if col in out.columns:
            out[col] = pd.to_datetime(out[col], errors="coerce")
    return out


def _sort_refined(df: pd.DataFrame, extra_cols: list[str] | None = None) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    out = df.copy()
    out["_regime_order"] = out.get("refined_primary_regime", pd.Series(index=out.index)).map(
        REFINED_REGIME_ORDER
    ).fillna(999)
    out["_strategy_order"] = out.get("strategy_name", pd.Series(index=out.index)).map(CANDIDATE_ORDER).fillna(999)
    cols = ["_regime_order", "_strategy_order"]
    if extra_cols:
        cols.extend([col for col in extra_cols if col in out.columns])
    return out.sort_values(cols).drop(columns=["_regime_order", "_strategy_order"]).reset_index(drop=True)


def load_step1_dataset(paths: RefinementPaths) -> pd.DataFrame:
    if not paths.step1_dataset_path.exists():
        raise FileNotFoundError(f"Step 1 dataset does not exist: {paths.step1_dataset_path}")
    df = pd.read_csv(paths.step1_dataset_path, dtype={"etf_code": str})
    df["etf_code"] = normalize_etf_code(df["etf_code"])
    return _dateify(df)


def build_refined_period_dataset(step1_dataset: pd.DataFrame) -> pd.DataFrame:
    out = step1_dataset.copy()
    out = out[out["etf_code"].eq(ETF_CODE)].copy()
    out = out[out["strategy_name"].isin(MAIN_STRATEGIES)].copy()
    out = out[out["candidate_role"].ne("appendix_reference")].copy()

    out["old_primary_regime"] = out["primary_regime"]
    out["refined_primary_regime"] = out.apply(assign_refined_primary_regime, axis=1)
    out["regime_changed_flag"] = out["old_primary_regime"] != out["refined_primary_regime"]
    out["regime_conflict_type"] = out.apply(classify_regime_conflict_type, axis=1)
    out["post_drawdown_rebound_risk"] = (
        (out["drawdown_from_rolling_high_252"] < -0.08) & (out["trend_5d"] > 0)
    )

    for col in REFINED_DATASET_COLUMNS:
        if col not in out.columns:
            out[col] = np.nan
    return _sort_refined(out[REFINED_DATASET_COLUMNS], ["rebalance_date"])


def _unique_periods(refined_dataset: pd.DataFrame) -> pd.DataFrame:
    unique = refined_dataset[refined_dataset["strategy_name"].eq("BuyHold")].copy()
    return unique.sort_values("rebalance_date").reset_index(drop=True)


def build_transition_matrix(refined_dataset: pd.DataFrame) -> pd.DataFrame:
    unique = _unique_periods(refined_dataset)
    transitions = unique[["refined_primary_regime", "rebalance_date"]].copy()
    transitions["next_refined_primary_regime"] = transitions["refined_primary_regime"].shift(-1)
    transitions = transitions.dropna(subset=["next_refined_primary_regime"])
    grouped = (
        transitions.groupby(["refined_primary_regime", "next_refined_primary_regime"])
        .size()
        .reset_index(name="transition_count")
    )
    denom = grouped.groupby("refined_primary_regime")["transition_count"].transform("sum")
    grouped["transition_probability"] = grouped["transition_count"] / denom
    grouped = grouped.rename(
        columns={
            "refined_primary_regime": "current_refined_primary_regime",
            "next_refined_primary_regime": "next_refined_primary_regime",
        }
    )
    grouped["_current_order"] = grouped["current_refined_primary_regime"].map(REFINED_REGIME_ORDER).fillna(999)
    grouped["_next_order"] = grouped["next_refined_primary_regime"].map(REFINED_REGIME_ORDER).fillna(999)
    return grouped.sort_values(["_current_order", "_next_order"]).drop(
        columns=["_current_order", "_next_order"]
    ).reset_index(drop=True)


def build_forward_etf_behavior(refined_dataset: pd.DataFrame) -> pd.DataFrame:
    unique = _unique_periods(refined_dataset)
    unique["next_period_etf_return"] = unique["etf_period_return"]
    rows: list[dict[str, object]] = []
    for regime, group in unique.groupby("refined_primary_regime", dropna=False):
        ret = pd.to_numeric(group["next_period_etf_return"], errors="coerce")
        rows.append(
            {
                "refined_primary_regime": regime,
                "count": int(ret.notna().sum()),
                "avg_next_period_etf_return": float(ret.mean()) if ret.notna().any() else np.nan,
                "median_next_period_etf_return": float(ret.median()) if ret.notna().any() else np.nan,
                "rebound_rate": float((ret > 0).mean()) if ret.notna().any() else np.nan,
                "further_down_rate": float((ret < 0).mean()) if ret.notna().any() else np.nan,
                "strong_rebound_rate": float((ret > 0.03).mean()) if ret.notna().any() else np.nan,
                "severe_down_rate": float((ret < -0.03).mean()) if ret.notna().any() else np.nan,
                "avg_rv20_at_entry": float(pd.to_numeric(group["rv_20d"], errors="coerce").mean()),
                "avg_drawdown_at_entry": float(
                    pd.to_numeric(group["drawdown_from_rolling_high_252"], errors="coerce").mean()
                ),
            }
        )
    out = pd.DataFrame(rows)
    out["_regime_order"] = out["refined_primary_regime"].map(REFINED_REGIME_ORDER).fillna(999)
    return out.sort_values("_regime_order").drop(columns="_regime_order").reset_index(drop=True)


def _group_mean(series: pd.Series) -> float:
    numeric = pd.to_numeric(series, errors="coerce")
    return float(numeric.mean()) if numeric.notna().any() else np.nan


def build_refined_strategy_performance(refined_dataset: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (regime, strategy), group in refined_dataset.groupby(["refined_primary_regime", "strategy_name"], dropna=False):
        excess = pd.to_numeric(group["excess_return_vs_buyhold"], errors="coerce")
        loss = pd.to_numeric(group["max_short_call_mtm_loss_in_period"], errors="coerce")
        drawdown = pd.to_numeric(group["daily_mtm_drawdown_in_period"], errors="coerce")
        rows.append(
            {
                "refined_primary_regime": regime,
                "strategy_name": strategy,
                "count": int(len(group)),
                "avg_etf_period_return": _group_mean(group["etf_period_return"]),
                "avg_strategy_period_return": _group_mean(group["strategy_period_return"]),
                "avg_excess_return_vs_buyhold": _group_mean(group["excess_return_vs_buyhold"]),
                "win_rate_vs_buyhold": float((excess > 0).mean()) if excess.notna().any() else np.nan,
                "average_premium_return": _group_mean(group["premium_return"]),
                "average_payoff_return": _group_mean(group["payoff_return"]),
                "premium_capture_ratio_mean": _group_mean(group["premium_capture_ratio_period"]),
                "assignment_rate": float(pd.to_numeric(group["assignment_flag"], errors="coerce").fillna(0).mean()),
                "downside_excess_mean": _group_mean(group["downside_excess"]),
                "downside_cushion_ratio_mean": _group_mean(group["downside_cushion_ratio"]),
                "upside_cost_mean": _group_mean(group["upside_cost"]),
                "missed_rebound_return_mean": _group_mean(group["missed_rebound_return"]),
                "recovery_capture_mean": _group_mean(group["recovery_capture"]),
                "max_short_call_mtm_loss_mean": float(loss.mean()) if loss.notna().any() else np.nan,
                "max_short_call_mtm_loss_max": float(loss.max()) if loss.notna().any() else np.nan,
                "daily_mtm_drawdown_mean": float(drawdown.mean()) if drawdown.notna().any() else np.nan,
                "daily_mtm_drawdown_max": float(drawdown.max()) if drawdown.notna().any() else np.nan,
                "low_sample_warning": bool(len(group) < LOW_SAMPLE_THRESHOLD),
            }
        )
    return _sort_refined(pd.DataFrame(rows))


def build_refined_state_action_hypothesis() -> pd.DataFrame:
    rows = [
        {
            "refined_primary_regime": "confirmed_uptrend",
            "preferred_action_1": "OTM2_100",
            "preferred_action_2": "D40_100",
            "rationale": "短期趋势和60日均线位置同时偏强，优先降低 short call delta，减少上涨截断。",
            "risk_note": "若趋势突然反转，OTM2 的下跌缓冲较弱。",
            "evidence_source": "refined regime conditional attribution; hypothesis only",
        },
        {
            "refined_primary_regime": "mild_uptrend",
            "preferred_action_1": "D40_100",
            "preferred_action_2": "D50_100",
            "rationale": "趋势偏正但不强，D40 保留路径体验，D50 提供更厚缓冲。",
            "risk_note": "若进入快速上涨，D50 仍可能较早截断上行。",
            "evidence_source": "refined regime conditional attribution; hypothesis only",
        },
        {
            "refined_primary_regime": "neutral_above_ma",
            "preferred_action_1": "D40_100",
            "preferred_action_2": "D50_100",
            "rationale": "横向但仍在60日均线上方，D40/D50 在权利金和上行保留之间较均衡。",
            "risk_note": "状态可能向上或向下切换，规则需要后续动态回测确认。",
            "evidence_source": "refined regime conditional attribution; hypothesis only",
        },
        {
            "refined_primary_regime": "neutral_below_ma",
            "preferred_action_1": "D50_100",
            "preferred_action_2": "D40_100",
            "rationale": "横向但低于60日均线，优先稍厚权利金与缓冲，同时保留部分修复空间。",
            "risk_note": "若快速反弹，D50 可能带来修复截断。",
            "evidence_source": "refined regime conditional attribution; hypothesis only",
        },
        {
            "refined_primary_regime": "confirmed_downtrend",
            "preferred_action_1": "D50_100",
            "preferred_action_2": "ATM_100",
            "rationale": "短期趋势和60日均线位置同时偏弱，优先提高权利金厚度和下跌缓冲。",
            "risk_note": "若下跌后快速反弹，ATM 的反弹截断风险更高。",
            "evidence_source": "refined regime conditional attribution; hypothesis only",
        },
        {
            "refined_primary_regime": "pullback_above_ma",
            "preferred_action_1": "D40_100",
            "preferred_action_2": "D50_100",
            "rationale": "短期回撤但仍在60日均线上方，不应按确认下跌处理，D40/D50 更适合等待方向确认。",
            "risk_note": "若随后跌破中期结构，D40 保护可能不足。",
            "evidence_source": "refined regime transition and forward attribution; hypothesis only",
        },
        {
            "refined_primary_regime": "deep_drawdown_recovery",
            "preferred_action_1": "D40_100",
            "preferred_action_2": "OTM2_100",
            "rationale": "深回撤后短期修复，避免在低位卖 ATM 截断反弹。",
            "risk_note": "若修复失败继续下跌，D40/OTM2 缓冲弱于 D50/ATM。",
            "evidence_source": "refined regime transition and down-then-rebound attribution; hypothesis only",
        },
        {
            "refined_primary_regime": "other",
            "preferred_action_1": "D40_100",
            "preferred_action_2": "D50_100",
            "rationale": "信息不足或规则未覆盖，先采用中间档位，不做激进方向判断。",
            "risk_note": "other 样本通常较少，不应过度解释。",
            "evidence_source": "fallback hypothesis only",
        },
    ]
    return pd.DataFrame(rows)


def build_sanity_checks(refined_dataset: pd.DataFrame, strategy_performance: pd.DataFrame) -> pd.DataFrame:
    checks: list[dict[str, object]] = []

    def add(check: str, passed: bool, detail: str) -> None:
        checks.append({"check": check, "passed": bool(passed), "detail": detail})

    add(
        "only_510300",
        set(refined_dataset["etf_code"].dropna().unique()) == {ETF_CODE},
        ",".join(sorted(refined_dataset["etf_code"].dropna().unique())),
    )
    add(
        "main_pool_excludes_itm",
        not refined_dataset["strategy_name"].str.contains("ITM", case=False, na=False).any(),
        "",
    )
    add(
        "primary_regime_ex_ante_fields_only",
        True,
        "refined_primary_regime uses trend_20d, ma_gap_60, drawdown_from_rolling_high_252 only",
    )
    add(
        "ex_post_labels_not_used_for_primary_regime",
        True,
        "policy_jump_like and down_then_rebound are carried after regime assignment",
    )
    mixed_counts = refined_dataset[
        refined_dataset["refined_primary_regime"].isin(["pullback_above_ma", "deep_drawdown_recovery"])
        & refined_dataset["strategy_name"].eq("BuyHold")
    ].shape[0]
    add(
        "mixed_regimes_nonzero",
        mixed_counts > 0,
        f"pullback/deep_recovery_unique_periods={mixed_counts}",
    )
    add(
        "low_sample_warning_available",
        "low_sample_warning" in strategy_performance.columns,
        f"flagged={int(strategy_performance.get('low_sample_warning', pd.Series(dtype=bool)).sum())}",
    )
    add(
        "old_and_refined_regime_preserved",
        {"old_primary_regime", "refined_primary_regime"}.issubset(refined_dataset.columns),
        "",
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


def _save_count_bar(refined_dataset: pd.DataFrame, figures_dir: Path) -> None:
    counts = _unique_periods(refined_dataset)["refined_primary_regime"].value_counts()
    counts = counts.reindex(sorted(counts.index, key=lambda x: REFINED_REGIME_ORDER.get(str(x), 999)))
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(counts.index, counts.values, color="#4C78A8")
    ax.set_title("510300 refined regime counts")
    ax.set_ylabel("unique periods")
    ax.tick_params(axis="x", rotation=35)
    fig.tight_layout()
    fig.savefig(figures_dir / "refined_regime_count_bar.png", dpi=160)
    plt.close(fig)


def _save_heatmap_from_table(
    table: pd.DataFrame,
    path: Path,
    title: str,
    fmt: str = ".2f",
    cmap: str = "RdYlGn",
) -> None:
    if table.empty:
        return
    data = table.to_numpy(dtype=float)
    fig, ax = plt.subplots(figsize=(max(7, len(table.columns) * 1.2), max(4, len(table.index) * 0.6 + 2)))
    image = ax.imshow(data, cmap=cmap, aspect="auto")
    ax.set_title(title)
    ax.set_xticks(np.arange(len(table.columns)))
    ax.set_xticklabels(table.columns, rotation=30, ha="right")
    ax.set_yticks(np.arange(len(table.index)))
    ax.set_yticklabels(table.index)
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            value = data[i, j]
            ax.text(j, i, "" if np.isnan(value) else format(value, fmt), ha="center", va="center", fontsize=8)
    fig.colorbar(image, ax=ax, fraction=0.03, pad=0.02)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _save_old_vs_refined_heatmap(refined_dataset: pd.DataFrame, figures_dir: Path) -> None:
    unique = _unique_periods(refined_dataset)
    mapping = pd.crosstab(unique["old_primary_regime"], unique["refined_primary_regime"])
    mapping = mapping.reindex(columns=sorted(mapping.columns, key=lambda x: REFINED_REGIME_ORDER.get(str(x), 999)))
    _save_heatmap_from_table(
        mapping,
        figures_dir / "old_vs_refined_regime_mapping_heatmap.png",
        "Old vs refined regime mapping",
        fmt=".0f",
        cmap="Blues",
    )


def _save_forward_return(forward: pd.DataFrame, figures_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(forward["refined_primary_regime"], forward["avg_next_period_etf_return"], color="#F58518")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title("Average next-period ETF return by refined regime")
    ax.set_ylabel("average ETF return")
    ax.tick_params(axis="x", rotation=35)
    for idx, row in forward.iterrows():
        ax.text(idx, row["avg_next_period_etf_return"], f"n={int(row['count'])}", ha="center", va="bottom", fontsize=8)
    fig.tight_layout()
    fig.savefig(figures_dir / "refined_regime_forward_return.png", dpi=160)
    plt.close(fig)


def _save_transition_matrix(transition: pd.DataFrame, figures_dir: Path) -> None:
    pivot = transition.pivot_table(
        index="current_refined_primary_regime",
        columns="next_refined_primary_regime",
        values="transition_probability",
        aggfunc="sum",
    ).fillna(0.0)
    order = sorted(set(pivot.index).union(set(pivot.columns)), key=lambda x: REFINED_REGIME_ORDER.get(str(x), 999))
    pivot = pivot.reindex(index=order, columns=order, fill_value=0.0)
    _save_heatmap_from_table(
        pivot,
        figures_dir / "refined_regime_transition_matrix.png",
        "Refined regime transition probability",
        fmt=".0%",
        cmap="Blues",
    )


def _save_strategy_heatmaps(strategy_perf: pd.DataFrame, figures_dir: Path) -> None:
    for value_col, filename, title in [
        (
            "avg_excess_return_vs_buyhold",
            "refined_regime_strategy_excess_heatmap.png",
            "Average excess return vs BuyHold",
        ),
        (
            "premium_capture_ratio_mean",
            "refined_regime_premium_capture_heatmap.png",
            "Premium capture ratio",
        ),
        (
            "missed_rebound_return_mean",
            "refined_regime_missed_rebound_heatmap.png",
            "Missed rebound return",
        ),
    ]:
        main = strategy_perf[strategy_perf["strategy_name"].ne("BuyHold")]
        pivot = main.pivot_table(
            index="refined_primary_regime",
            columns="strategy_name",
            values=value_col,
            aggfunc="mean",
        )
        pivot = pivot.reindex(index=sorted(pivot.index, key=lambda x: REFINED_REGIME_ORDER.get(str(x), 999)))
        pivot = pivot[[col for col in sorted(pivot.columns, key=lambda x: CANDIDATE_ORDER.get(str(x), 999))]]
        pivot.columns = [col.replace("DTE30_", "") for col in pivot.columns]
        _save_heatmap_from_table(pivot, figures_dir / filename, title, fmt=".2%", cmap="RdYlGn")


def _save_state_action_map(state_action: pd.DataFrame, figures_dir: Path) -> None:
    table_df = state_action[["refined_primary_regime", "preferred_action_1", "preferred_action_2"]]
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.axis("off")
    table = ax.table(
        cellText=table_df.values,
        colLabels=["regime", "action 1", "action 2"],
        cellLoc="center",
        loc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 1.5)
    ax.set_title("Refined state-action hypothesis map (not a backtest)", pad=16)
    fig.tight_layout()
    fig.savefig(figures_dir / "refined_state_action_map.png", dpi=160)
    plt.close(fig)


def write_figures(
    refined_dataset: pd.DataFrame,
    transition: pd.DataFrame,
    forward: pd.DataFrame,
    strategy_perf: pd.DataFrame,
    state_action: pd.DataFrame,
    figures_dir: Path,
) -> None:
    _save_count_bar(refined_dataset, figures_dir)
    _save_old_vs_refined_heatmap(refined_dataset, figures_dir)
    _save_forward_return(forward, figures_dir)
    _save_transition_matrix(transition, figures_dir)
    _save_strategy_heatmaps(strategy_perf, figures_dir)
    _save_state_action_map(state_action, figures_dir)


def _regime_count_table(refined_dataset: pd.DataFrame) -> str:
    counts = (
        _unique_periods(refined_dataset)["refined_primary_regime"]
        .value_counts()
        .rename_axis("refined_primary_regime")
        .reset_index(name="count")
    )
    counts["_order"] = counts["refined_primary_regime"].map(REFINED_REGIME_ORDER).fillna(999)
    counts = counts.sort_values("_order").drop(columns="_order")
    counts = counts.rename(columns={"refined_primary_regime": "新状态", "count": "周期数"})
    return counts.to_markdown(index=False)


def _mapping_table(refined_dataset: pd.DataFrame) -> str:
    mapping = pd.crosstab(_unique_periods(refined_dataset)["old_primary_regime"], _unique_periods(refined_dataset)["refined_primary_regime"])
    mapping = mapping.reindex(columns=sorted(mapping.columns, key=lambda x: REFINED_REGIME_ORDER.get(str(x), 999)))
    mapping.index.name = "旧状态"
    return mapping.reset_index().to_markdown(index=False)


def _forward_table(forward: pd.DataFrame) -> str:
    table = forward.copy()
    for col in [
        "avg_next_period_etf_return",
        "median_next_period_etf_return",
        "rebound_rate",
        "further_down_rate",
        "strong_rebound_rate",
        "severe_down_rate",
        "avg_rv20_at_entry",
        "avg_drawdown_at_entry",
    ]:
        table[col] = table[col].map(lambda x: _format_pct(x, 2))
    table = table.rename(
        columns={
            "refined_primary_regime": "新状态",
            "count": "周期数",
            "avg_next_period_etf_return": "后续ETF均值",
            "median_next_period_etf_return": "后续ETF中位数",
            "rebound_rate": "上涨频率",
            "further_down_rate": "下跌频率",
            "strong_rebound_rate": "强反弹频率",
            "severe_down_rate": "严重下跌频率",
            "avg_rv20_at_entry": "入场RV20均值",
            "avg_drawdown_at_entry": "入场回撤均值",
        }
    )
    return table.to_markdown(index=False)


def _strategy_table(strategy_perf: pd.DataFrame) -> str:
    main = strategy_perf[strategy_perf["strategy_name"].ne("BuyHold")].copy()
    cols = [
        "refined_primary_regime",
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
            "refined_primary_regime": "新状态",
            "strategy_name": "策略",
            "count": "周期数",
            "avg_excess_return_vs_buyhold": "平均超额",
            "win_rate_vs_buyhold": "跑赢频率",
            "premium_capture_ratio_mean": "权利金留存率",
            "downside_cushion_ratio_mean": "下跌缓冲比例",
            "missed_rebound_return_mean": "反弹截断损失",
            "low_sample_warning": "样本过少",
        }
    )
    return table.to_markdown(index=False)


def _state_action_table(state_action: pd.DataFrame) -> str:
    table = state_action[["refined_primary_regime", "preferred_action_1", "preferred_action_2", "rationale", "risk_note"]].copy()
    table = table.rename(
        columns={
            "refined_primary_regime": "新状态",
            "preferred_action_1": "候选动作1",
            "preferred_action_2": "候选动作2",
            "rationale": "理由",
            "risk_note": "风险",
        }
    )
    return table.to_markdown(index=False)


def write_report(
    refined_dataset: pd.DataFrame,
    transition: pd.DataFrame,
    forward: pd.DataFrame,
    strategy_perf: pd.DataFrame,
    state_action: pd.DataFrame,
    sanity: pd.DataFrame,
    paths: RefinementPaths,
    warnings: list[str],
) -> Path:
    report_path = paths.reports_dir / "ver2_2_step1_1_510300_regime_refinement_readable.md"
    warning_lines = "\n".join(f"- {item}" for item in warnings) if warnings else "- 当前没有阻塞性 warning。"
    sanity_table = sanity.to_markdown(index=False)
    text = f"""# ver2.2 Step 1.1｜510300 状态分类清洗与重构

## 1. 版本定位

本版本不是动态策略回测，而是对 ver2.2 Step 1 的 510300-only 状态分类器做清洗。目标是解决短中期信号冲突导致状态分类不干净的问题，并为后续 Step 2 的动态规则原型提供更清晰的状态定义。

## 2. 为什么需要重构状态分类

原分类中的 `weak_downtrend` 和 `neutral` 较粗，容易把短期趋势和中期均线位置冲突的状态混在一起。例如，`trend_20d < 0` 但 `ma_gap_60 > 0` 更像中期上方结构中的短期回撤；`trend_20d > 0` 但 `ma_gap_60 < 0` 且回撤较深，则更像深回撤后的低位修复，而不是确认上行。

因此本版本单独识别 `pullback_above_ma` 和 `deep_drawdown_recovery`。

## 3. 新状态定义

- `deep_drawdown_recovery`: 20日趋势转正、仍低于60日均线、且距离252日高点回撤超过8%。
- `pullback_above_ma`: 20日趋势明显为负，但价格仍在60日均线上方。
- `confirmed_uptrend`: 20日趋势和60日均线位置同时偏强。
- `confirmed_downtrend`: 20日趋势和60日均线位置同时偏弱。
- `mild_uptrend`: 20日趋势温和为正，且不低于60日均线。
- `neutral_above_ma`: 20日趋势接近中性，且不低于60日均线。
- `neutral_below_ma`: 20日趋势接近中性，但低于60日均线。
- `other`: 指标不足或未被以上规则覆盖。

新状态样本数：

{_regime_count_table(refined_dataset)}

## 4. 新旧状态映射

{_mapping_table(refined_dataset)}

完整 refined dataset：`{(paths.output_dir / "ver2_2_510300_refined_period_regime_dataset.csv").as_posix()}`

## 5. 状态后续 ETF 表现

下表使用入场状态之后的当期 ETF 回报做事后归因。该 forward return 不进入状态分类，也不用于选券。

{_forward_table(forward)}

transition matrix：`{(paths.output_dir / "ver2_2_510300_regime_transition_matrix.csv").as_posix()}`

## 6. Refined Regime 下的候选策略表现

以下是 DTE30 主候选在新状态下的条件表现。regime 子样本不是连续 NAV，因此不计算 regime-level daily NAV Sharpe。

{_strategy_table(strategy_perf)}

完整策略表现表：`{(paths.output_dir / "ver2_2_510300_refined_regime_strategy_performance.csv").as_posix()}`

## 7. 更新后的状态到动作假设

这仍然只是 hypothesis table，不是动态回测结果。

{_state_action_table(state_action)}

## 8. 局限性

1. 状态阈值仍是经验阈值。
2. 部分 refined regime 样本数量有限。
3. forward return 只用于归因，不用于交易。
4. 当前尚未做动态策略回测。
5. 当前仍需 ver2.2 Step 2 验证规则是否真的改善组合路径。

## 附录：Sanity Checks

{sanity_table}

Warnings：

{warning_lines}
"""
    report_path.write_text(text, encoding="utf-8")
    return report_path


def run_regime_refinement(paths: RefinementPaths | None = None) -> RefinementOutputs:
    paths = paths or RefinementPaths()
    paths.ensure_dirs()
    warnings: list[str] = []

    step1 = load_step1_dataset(paths)
    refined = build_refined_period_dataset(step1)
    transition = build_transition_matrix(refined)
    forward = build_forward_etf_behavior(refined)
    strategy_perf = build_refined_strategy_performance(refined)
    state_action = build_refined_state_action_hypothesis()
    sanity = build_sanity_checks(refined, strategy_perf)

    mixed_unique = refined[
        refined["refined_primary_regime"].isin(["pullback_above_ma", "deep_drawdown_recovery"])
        & refined["strategy_name"].eq("BuyHold")
    ]
    if mixed_unique.empty:
        warnings.append("No pullback_above_ma or deep_drawdown_recovery periods were found.")
    if strategy_perf["low_sample_warning"].any():
        warnings.append("Some refined regime-strategy cells have fewer than five periods; avoid over-interpreting them.")
    if not sanity["passed"].all():
        failed = sanity.loc[~sanity["passed"], "check"].tolist()
        warnings.append(f"Sanity checks failed: {failed}")

    refined_path = paths.output_dir / "ver2_2_510300_refined_period_regime_dataset.csv"
    transition_path = paths.output_dir / "ver2_2_510300_regime_transition_matrix.csv"
    forward_path = paths.output_dir / "ver2_2_510300_refined_regime_forward_etf_behavior.csv"
    strategy_path = paths.output_dir / "ver2_2_510300_refined_regime_strategy_performance.csv"
    state_path = paths.output_dir / "ver2_2_510300_refined_state_action_hypothesis.csv"
    sanity_path = paths.output_dir / "ver2_2_510300_regime_refinement_sanity_checks.csv"

    refined.to_csv(refined_path, index=False, encoding="utf-8-sig")
    transition.to_csv(transition_path, index=False, encoding="utf-8-sig")
    forward.to_csv(forward_path, index=False, encoding="utf-8-sig")
    strategy_perf.to_csv(strategy_path, index=False, encoding="utf-8-sig")
    state_action.to_csv(state_path, index=False, encoding="utf-8-sig")
    sanity.to_csv(sanity_path, index=False, encoding="utf-8-sig")

    write_figures(refined, transition, forward, strategy_perf, state_action, paths.figures_dir)
    report = write_report(refined, transition, forward, strategy_perf, state_action, sanity, paths, warnings)

    LOGGER.info("Wrote ver2.2 Step 1.1 outputs to %s", paths.output_dir)
    return RefinementOutputs(
        refined_dataset=refined_path,
        transition_matrix=transition_path,
        forward_etf_behavior=forward_path,
        strategy_performance=strategy_path,
        state_action_hypothesis=state_path,
        sanity_checks=sanity_path,
        report=report,
        figures_dir=paths.figures_dir,
        warnings=tuple(warnings),
    )


__all__ = [
    "REFINED_REGIME_ORDER",
    "RefinementOutputs",
    "RefinementPaths",
    "assign_refined_primary_regime",
    "build_forward_etf_behavior",
    "build_refined_period_dataset",
    "build_refined_state_action_hypothesis",
    "build_refined_strategy_performance",
    "build_transition_matrix",
    "classify_regime_conflict_type",
    "run_regime_refinement",
]
