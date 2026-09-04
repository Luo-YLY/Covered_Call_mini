from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

LOGGER = logging.getLogger(__name__)

VERSION = "ver2.0"
VERSION_NAME = "Static Moneyness Ladder Baseline"
VERSION_TITLE_CN = "ver2.0 静态 Moneyness 梯度基准实验"

MONEYNESS_ORDER = {
    "ITM5_100": -0.05,
    "ITM2_100": -0.02,
    "ATM_100": 0.00,
    "OTM2_100": 0.02,
    "OTM5_100": 0.05,
}

MONEYNESS_LABELS = {
    -0.05: "ITM5",
    -0.02: "ITM2",
    0.00: "ATM",
    0.02: "OTM2",
    0.05: "OTM5",
}

GRADIENT_COLUMNS = [
    "etf_code",
    "strategy_name",
    "target_moneyness",
    "realized_moneyness_mean",
    "realized_moneyness_std",
    "num_periods",
    "cumulative_return",
    "annualized_return",
    "annualized_volatility",
    "sharpe_ratio",
    "max_drawdown",
    "max_drawdown_improvement",
    "assignment_rate",
    "average_total_premium_yield",
    "annualized_extrinsic_premium_yield",
    "premium_capture_ratio",
    "downside_excess_mean",
    "downside_win_rate",
    "downside_cushion_ratio_mean",
    "average_downside_benefit",
    "upside_cost_mean",
    "protection_cost_ratio",
    "primary_score",
]

GRADIENT_METRICS = [
    "annualized_extrinsic_premium_yield",
    "average_total_premium_yield",
    "premium_capture_ratio",
    "assignment_rate",
    "downside_cushion_ratio_mean",
    "max_drawdown",
    "max_drawdown_improvement",
    "annualized_return",
    "annualized_volatility",
    "primary_score",
]

FIGURE_METRICS = [
    "annualized_extrinsic_premium_yield",
    "average_total_premium_yield",
    "premium_capture_ratio",
    "assignment_rate",
    "downside_cushion_ratio_mean",
    "max_drawdown",
    "max_drawdown_improvement",
    "annualized_return",
    "primary_score",
]

FIGURE_FILENAMES = {
    "annualized_extrinsic_premium_yield": "moneyness_vs_annualized_extrinsic_premium_yield.png",
    "average_total_premium_yield": "moneyness_vs_average_total_premium_yield.png",
    "premium_capture_ratio": "moneyness_vs_premium_capture_ratio.png",
    "assignment_rate": "moneyness_vs_assignment_rate.png",
    "downside_cushion_ratio_mean": "moneyness_vs_downside_cushion_ratio.png",
    "max_drawdown": "moneyness_vs_max_drawdown.png",
    "max_drawdown_improvement": "moneyness_vs_max_drawdown_improvement.png",
    "annualized_return": "moneyness_vs_annualized_return.png",
    "primary_score": "moneyness_vs_primary_score.png",
}

METRIC_LABELS_CN = {
    "annualized_extrinsic_premium_yield": "年化时间价值权利金收益",
    "average_total_premium_yield": "平均总权利金收益",
    "premium_capture_ratio": "权利金留存率",
    "assignment_rate": "被行权频率",
    "downside_cushion_ratio_mean": "下跌缓冲比例均值",
    "max_drawdown": "最大回撤",
    "max_drawdown_improvement": "最大回撤改善",
    "annualized_return": "年化收益",
    "annualized_volatility": "年化波动率",
    "primary_score": "主评分",
}

PERCENT_METRICS = {
    "realized_moneyness_mean",
    "realized_moneyness_std",
    "cumulative_return",
    "annualized_return",
    "annualized_volatility",
    "max_drawdown",
    "max_drawdown_improvement",
    "assignment_rate",
    "average_total_premium_yield",
    "annualized_extrinsic_premium_yield",
    "premium_capture_ratio",
    "downside_excess_mean",
    "downside_win_rate",
    "downside_cushion_ratio_mean",
    "average_downside_benefit",
    "upside_cost_mean",
}

REQUIRED_INPUTS = {
    "summary": "summary_tables/ver2_summary.csv",
    "premium_summary": "premium_income/ver2_premium_income_summary.csv",
    "defensive_ranking": "premium_income/ver2_defensive_strategy_ranking.csv",
    "premium_decomposition": "premium_income/ver2_premium_decomposition_by_period.csv",
}


@dataclass(frozen=True)
class MoneynessGradientOutputs:
    summary: Path
    long: Path
    correlation: Path
    baseline_record: Path
    manifest: Path
    figures: dict[str, Path]


def _read_required_csv(output_dir: Path, relative_path: str) -> pd.DataFrame:
    path = output_dir / relative_path
    if not path.exists():
        raise FileNotFoundError(f"Missing required ver2 output: {path}")
    return pd.read_csv(path)


def load_existing_ver2_tables(output_dir: Path) -> dict[str, pd.DataFrame]:
    """Load existing ver2 outputs for moneyness-gradient diagnostics."""

    return {
        name: _read_required_csv(output_dir, relative_path)
        for name, relative_path in REQUIRED_INPUTS.items()
    }


def validate_moneyness_ladder(summary: pd.DataFrame) -> None:
    """Sanity-check the static moneyness ladder definition."""

    actual = sorted(
        summary.loc[summary["strategy_name"].isin(MONEYNESS_ORDER), "strategy_name"]
        .map(MONEYNESS_ORDER)
        .dropna()
        .unique()
    )
    expected = [-0.05, -0.02, 0.00, 0.02, 0.05]
    if actual != expected:
        raise AssertionError(f"target_moneyness order mismatch: {actual} != {expected}")
    if not all(MONEYNESS_ORDER[strategy] < 0 for strategy in ["ITM5_100", "ITM2_100"]):
        raise AssertionError("ITM strategies must have negative target_moneyness.")
    if not all(MONEYNESS_ORDER[strategy] > 0 for strategy in ["OTM2_100", "OTM5_100"]):
        raise AssertionError("OTM strategies must have positive target_moneyness.")


def _field_warnings(df: pd.DataFrame, required: list[str], table_name: str) -> list[str]:
    missing = [col for col in required if col not in df.columns]
    return [f"{table_name} 缺少字段：{', '.join(missing)}"] if missing else []


def build_moneyness_gradient_summary(tables: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, list[str]]:
    """Build the wide moneyness-gradient summary table from existing outputs."""

    warnings: list[str] = []
    summary = tables["summary"].copy()
    premium = tables["premium_summary"].copy()
    ranking = tables["defensive_ranking"].copy()
    decomp = tables["premium_decomposition"].copy()

    warnings.extend(_field_warnings(summary, ["etf_code", "strategy_name", "max_drawdown"], "ver2_summary"))
    warnings.extend(
        _field_warnings(
            premium,
            [
                "etf_code",
                "strategy_name",
                "average_total_premium_yield",
                "annualized_extrinsic_premium_yield",
                "premium_capture_ratio",
            ],
            "ver2_premium_income_summary",
        )
    )
    warnings.extend(
        _field_warnings(ranking, ["etf_code", "strategy_name", "primary_score"], "ver2_defensive_strategy_ranking")
    )
    warnings.extend(
        _field_warnings(
            decomp,
            ["etf_code", "strategy_name", "strike", "underlying_price_at_entry"],
            "ver2_premium_decomposition_by_period",
        )
    )

    validate_moneyness_ladder(summary)
    summary = summary[summary["strategy_name"].isin(MONEYNESS_ORDER)].copy()
    summary["target_moneyness"] = summary["strategy_name"].map(MONEYNESS_ORDER)

    decomp = decomp[decomp["strategy_name"].isin(MONEYNESS_ORDER)].copy()
    decomp["realized_moneyness"] = decomp["strike"] / decomp["underlying_price_at_entry"] - 1.0
    realized = (
        decomp.dropna(subset=["realized_moneyness"])
        .groupby(["etf_code", "strategy_name"], as_index=False)
        .agg(
            realized_moneyness_mean=("realized_moneyness", "mean"),
            realized_moneyness_std=("realized_moneyness", "std"),
        )
    )

    premium_cols = [
        "etf_code",
        "strategy_name",
        "average_total_premium_yield",
        "annualized_extrinsic_premium_yield",
        "premium_capture_ratio",
    ]
    ranking_cols = ["etf_code", "strategy_name", "primary_score"]
    merged = summary.merge(realized, on=["etf_code", "strategy_name"], how="left")
    merged = merged.merge(premium[[col for col in premium_cols if col in premium.columns]], on=["etf_code", "strategy_name"], how="left")
    merged = merged.merge(ranking[[col for col in ranking_cols if col in ranking.columns]], on=["etf_code", "strategy_name"], how="left")

    for col in GRADIENT_COLUMNS:
        if col not in merged.columns:
            merged[col] = np.nan
            warnings.append(f"moneyness summary 无法生成字段：{col}")

    out = merged[GRADIENT_COLUMNS].copy()
    out = out.sort_values(["etf_code", "target_moneyness"]).reset_index(drop=True)
    return out, warnings


def build_moneyness_gradient_long(gradient: pd.DataFrame) -> pd.DataFrame:
    """Build long-form metric table for moneyness-gradient diagnostics."""

    rows: list[dict[str, Any]] = []
    for _, row in gradient.iterrows():
        for metric in GRADIENT_METRICS:
            rows.append(
                {
                    "etf_code": row["etf_code"],
                    "target_moneyness": row["target_moneyness"],
                    "strategy_name": row["strategy_name"],
                    "metric_name": metric,
                    "metric_value": row.get(metric, np.nan),
                }
            )
    return pd.DataFrame(rows).sort_values(["etf_code", "metric_name", "target_moneyness"]).reset_index(drop=True)


def monotonic_direction(values: pd.Series, tolerance: float = 1e-10) -> str:
    """Classify a five-point ladder as increasing, decreasing, or non-monotonic."""

    clean = pd.to_numeric(values, errors="coerce").dropna().to_numpy(dtype=float)
    if len(clean) < 2:
        return "non_monotonic"
    diffs = np.diff(clean)
    if np.all(diffs >= -tolerance) and np.any(diffs > tolerance):
        return "increasing"
    if np.all(diffs <= tolerance) and np.any(diffs < -tolerance):
        return "decreasing"
    return "non_monotonic"


def _corr(x: pd.Series, y: pd.Series, method: str) -> float:
    data = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(data) < 3 or data["y"].nunique() <= 1:
        return np.nan
    if method == "spearman":
        x_values = data["x"].rank(method="average").to_numpy(dtype=float)
        y_values = data["y"].rank(method="average").to_numpy(dtype=float)
    else:
        x_values = data["x"].to_numpy(dtype=float)
        y_values = data["y"].to_numpy(dtype=float)
    if np.isclose(np.std(x_values), 0.0) or np.isclose(np.std(y_values), 0.0):
        return np.nan
    return float(np.corrcoef(x_values, y_values)[0, 1])


def _is_hump_shaped(values: pd.Series) -> bool:
    ordered = pd.to_numeric(values, errors="coerce").reset_index(drop=True)
    if ordered.isna().any() or len(ordered) != 5:
        return False
    peak_idx = int(ordered.idxmax())
    return peak_idx in {1, 2, 3} and ordered.iloc[peak_idx] > ordered.iloc[0] and ordered.iloc[peak_idx] > ordered.iloc[-1]


def _interpret_metric(metric: str, direction: str, values: pd.Series) -> str:
    label = METRIC_LABELS_CN.get(metric, metric)
    if metric == "annualized_extrinsic_premium_yield" and _is_hump_shaped(values):
        return "ATM 附近年化时间价值权利金收益较高，呈非单调的 hump-shaped pattern。"
    if metric == "assignment_rate":
        return "越 OTM，被行权频率明显下降。" if direction == "decreasing" else f"{label} 沿 moneyness 梯度呈非单调关系。"
    if metric == "premium_capture_ratio":
        return "越 OTM，权利金留存率上升。" if direction == "increasing" else f"{label} 沿 moneyness 梯度呈非单调关系。"
    if metric in {"max_drawdown", "max_drawdown_improvement", "downside_cushion_ratio_mean"}:
        if direction == "decreasing":
            return f"越 OTM，{label} 下降；更 ITM 的仓位防御性更强。"
        if direction == "increasing":
            return f"越 OTM，{label} 上升；该指标需结合收益和留存率解释。"
    if direction == "increasing":
        return f"越 OTM，{label} 整体上升。"
    if direction == "decreasing":
        return f"越 OTM，{label} 整体下降。"
    return f"{label} 沿 moneyness 梯度呈非单调关系。"


def build_moneyness_correlation(gradient: pd.DataFrame) -> pd.DataFrame:
    """Build descriptive correlations against target_moneyness."""

    rows: list[dict[str, Any]] = []
    for etf_code, g in gradient.groupby("etf_code"):
        g = g.sort_values("target_moneyness")
        x = g["target_moneyness"].astype(float)
        for metric in GRADIENT_METRICS:
            y = pd.to_numeric(g[metric], errors="coerce")
            direction = monotonic_direction(y)
            rows.append(
                {
                    "etf_code": etf_code,
                    "metric_name": metric,
                    "pearson_corr_with_target_moneyness": _corr(x, y, "pearson"),
                    "spearman_corr_with_target_moneyness": _corr(x, y, "spearman"),
                    "monotonic_direction": direction,
                    "interpretation": _interpret_metric(metric, direction, y),
                }
            )
    return pd.DataFrame(rows).sort_values(["etf_code", "metric_name"]).reset_index(drop=True)


def run_moneyness_sanity_checks(gradient: pd.DataFrame, tables: dict[str, pd.DataFrame]) -> None:
    """Run lightweight consistency checks for the ver2.0 moneyness checkpoint."""

    expected = [-0.05, -0.02, 0.00, 0.02, 0.05]
    for etf_code, g in gradient.groupby("etf_code"):
        actual = [round(float(value), 2) for value in g.sort_values("target_moneyness")["target_moneyness"]]
        if actual != expected:
            raise AssertionError(f"{etf_code} target_moneyness order mismatch: {actual} != {expected}")

    target_map = gradient.set_index("strategy_name")["target_moneyness"].to_dict()
    if not all(target_map.get(strategy, 0.0) < 0 for strategy in ["ITM5_100", "ITM2_100"]):
        raise AssertionError("ITM5_100 and ITM2_100 must have negative target_moneyness.")
    if not all(target_map.get(strategy, 0.0) > 0 for strategy in ["OTM2_100", "OTM5_100"]):
        raise AssertionError("OTM2_100 and OTM5_100 must have positive target_moneyness.")
    if "BuyHold" in set(gradient["strategy_name"]):
        raise AssertionError("BuyHold must not enter the moneyness gradient table.")

    premium = tables["premium_summary"].set_index(["etf_code", "strategy_name"])
    for _, row in gradient.iterrows():
        key = (row["etf_code"], row["strategy_name"])
        if key in premium.index:
            source_extrinsic = premium.loc[key, "annualized_extrinsic_premium_yield"]
            source_capture = premium.loc[key, "premium_capture_ratio"]
            if not np.isclose(row["annualized_extrinsic_premium_yield"], source_extrinsic, equal_nan=True):
                raise AssertionError("annualized_extrinsic_premium_yield must come from premium summary.")
            if not np.isclose(row["premium_capture_ratio"], source_capture, equal_nan=True):
                raise AssertionError("premium_capture_ratio must come from premium received and payoff paid summary.")

    summary = tables["summary"].copy()
    buyhold_mdd = summary[summary["strategy_name"] == "BuyHold"].set_index("etf_code")["max_drawdown"].to_dict()
    for _, row in gradient.iterrows():
        expected_improvement = buyhold_mdd[row["etf_code"]] - row["max_drawdown"]
        if not np.isclose(row["max_drawdown_improvement"], expected_improvement, atol=1e-10):
            raise AssertionError("max_drawdown_improvement must equal BuyHold MDD - Strategy MDD.")


def _format_value(value: Any, column: str) -> str:
    if pd.isna(value):
        return ""
    if column in PERCENT_METRICS:
        return f"{float(value):.2%}"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def _markdown_table(df: pd.DataFrame, columns: list[str] | None = None, max_rows: int | None = None) -> str:
    if df.empty:
        return "_No rows._"
    table = df[columns].copy() if columns is not None else df.copy()
    if max_rows is not None:
        table = table.head(max_rows)
    header = "| " + " | ".join(table.columns) + " |"
    divider = "| " + " | ".join(["---"] * len(table.columns)) + " |"
    rows = [
        "| " + " | ".join(_format_value(value, col) for col, value in row.items()) + " |"
        for _, row in table.iterrows()
    ]
    return "\n".join([header, divider, *rows])


def _metric_table_for_record(gradient: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "etf_code",
        "strategy_name",
        "target_moneyness",
        "annualized_return",
        "annualized_volatility",
        "max_drawdown",
        "assignment_rate",
        "annualized_extrinsic_premium_yield",
        "premium_capture_ratio",
        "downside_cushion_ratio_mean",
        "primary_score",
    ]
    return gradient[cols].copy()


def write_moneyness_figures(gradient: pd.DataFrame, output_dir: Path) -> dict[str, Path]:
    """Write faceted figures for key moneyness-gradient metrics."""

    figure_dir = output_dir / "moneyness_gradient" / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    saved: dict[str, Path] = {}
    x_ticks = [-0.05, -0.02, 0.0, 0.02, 0.05]
    x_labels = [MONEYNESS_LABELS[value] for value in x_ticks]

    for metric in FIGURE_METRICS:
        fig, axes = plt.subplots(1, len(sorted(gradient["etf_code"].unique())), figsize=(11.0, 4.6), sharey=False)
        if not isinstance(axes, np.ndarray):
            axes = np.array([axes])
        for ax, (etf_code, g) in zip(axes, gradient.groupby("etf_code")):
            g = g.sort_values("target_moneyness")
            ax.plot(g["target_moneyness"], g[metric], marker="o", linewidth=1.8, color="#1f77b4")
            ax.axvline(0.0, color="#555555", linestyle=":", linewidth=0.9)
            ax.set_xticks(x_ticks)
            ax.set_xticklabels(x_labels)
            ax.set_title(f"{etf_code} - {metric}", loc="left", fontsize=10)
            ax.set_xlabel("Target moneyness")
            ax.set_ylabel(metric)
            ax.grid(True, linestyle=":", alpha=0.45)
        fig.suptitle(f"ver2.0 moneyness gradient - {metric}", x=0.02, y=0.98, ha="left", fontsize=12)
        fig.text(
            0.02,
            0.01,
            "Note: negative moneyness means ITM call, positive moneyness means OTM call.",
            fontsize=9,
            color="#555555",
        )
        path = figure_dir / FIGURE_FILENAMES[metric]
        fig.tight_layout(rect=(0, 0.05, 1, 0.92))
        fig.savefig(path, dpi=170)
        plt.close(fig)
        saved[metric] = path
    return saved


def _git_info(repo_root: Path) -> dict[str, Any]:
    def run_git(args: list[str]) -> str | None:
        try:
            return subprocess.check_output(["git", *args], cwd=repo_root, text=True, stderr=subprocess.DEVNULL).strip()
        except Exception:
            return None

    status = run_git(["status", "--short"])
    return {
        "git_commit_hash": run_git(["rev-parse", "HEAD"]),
        "git_branch": run_git(["branch", "--show-current"]),
        "dirty_working_tree": bool(status) if status is not None else None,
    }


def write_manifest(
    *,
    repo_root: Path,
    output_dir: Path,
    created_outputs: list[Path],
) -> Path:
    manifest = {
        "version": VERSION,
        "name": VERSION_NAME,
        "research_theme": "Downside protection covered call",
        "etfs": ["510300", "510050"],
        "strategies": ["BuyHold", "ITM5_100", "ITM2_100", "ATM_100", "OTM2_100", "OTM5_100"],
        "rolling_mode": "continuous_30d",
        "dte_target": 30,
        "dte_window": [20, 45],
        "coverage_ratio": 1.0,
        "is_final_strategy": False,
        "purpose": "baseline checkpoint for future optimization",
        "created_outputs": [str(path.relative_to(repo_root)) if path.is_absolute() else str(path) for path in created_outputs],
    }
    manifest.update(_git_info(repo_root))
    path = output_dir / "reports" / "ver2_0_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _best_by_etf(ranking: pd.DataFrame) -> pd.DataFrame:
    return ranking.sort_values(["etf_code", "primary_score"], ascending=[True, False]).groupby("etf_code").head(2)


def write_baseline_record(
    *,
    output_dir: Path,
    gradient: pd.DataFrame,
    long_table: pd.DataFrame,
    correlation: pd.DataFrame,
    tables: dict[str, pd.DataFrame],
    warnings: list[str],
    created_outputs: list[Path],
) -> Path:
    """Write the ver2.0 baseline checkpoint markdown record."""

    summary = tables["summary"]
    premium = tables["premium_summary"]
    ranking = tables["defensive_ranking"]
    buyhold = summary[summary["strategy_name"] == "BuyHold"][
        ["etf_code", "strategy_name", "cumulative_return", "annualized_return", "max_drawdown"]
    ]
    data_limitations = "\n".join(f"- {item}" for item in warnings) if warnings else "- 未发现必需字段缺失。"

    text = f"""# {VERSION_TITLE_CN}

## 1. 版本定位

- 本版本是 ver2 downside protection research 的 baseline checkpoint。
- 本版本不构成最终策略方案。
- 本版本用于记录在统一 DTE30、continuous_30d、100% 覆盖率条件下，不同 moneyness 的基础表现。
- 后续所有动态优化都应以本版本作为对照基准。

## 2. 实验设置

- ETF: 510300, 510050
- Benchmark: BuyHold
- Strategies: ITM5_100, ITM2_100, ATM_100, OTM2_100, OTM5_100
- Target moneyness: -5%, -2%, 0%, 2%, 5%
- Moneyness definition: `K / S - 1`
- DTE target: 30
- DTE window: 20-45
- Rolling mode: continuous_30d
- Coverage ratio: 100%
- Option type: short call
- Payoff: hold to expiry
- ETF price field: `adj_close`
- Option premium pricing field: close, or bid/ask mid when available
- Transaction cost / slippage assumption: 5 bps option premium slippage plus assumed 5% bid/ask spread when market bid/ask is missing
- No future leakage: option selection uses only rebalance-date option chain; payoff is evaluated at expiry or settlement date

## 3. 核心结果总表

### BuyHold benchmark

{_markdown_table(buyhold)}

### Core performance summary

{_markdown_table(summary[["etf_code", "strategy_name", "cumulative_return", "annualized_return", "annualized_volatility", "max_drawdown", "assignment_rate", "downside_cushion_ratio_mean", "max_drawdown_improvement"]])}

### Premium-income summary

{_markdown_table(premium[["etf_code", "strategy_name", "average_total_premium_yield", "annualized_extrinsic_premium_yield", "premium_capture_ratio", "assignment_rate", "max_drawdown_improvement"]])}

### Defensive ranking

{_markdown_table(ranking[["etf_code", "strategy_name", "primary_score", "annualized_extrinsic_premium_yield", "downside_cushion_ratio_mean", "max_drawdown_improvement", "premium_capture_ratio"]])}

### Moneyness gradient summary

{_markdown_table(_metric_table_for_record(gradient))}

## 4. 初步机制结论

A. ATM_100 是当前静态 defensive-income scoring 下的综合基准。

- ATM 通常具有较厚的时间价值。
- 在当前结果中，ATM_100 在 510050 和 510300 的 defensive ranking 中均排在第一或最前列。
- 这不意味着 ATM 是最终方案，只说明它适合作为后续优化的核心对照基准。

B. ITM 策略提供更强防御，但收入质量不一定更高。

- ITM5 / ITM2 的 max drawdown 更低，max drawdown improvement 更强。
- 但 ITM 策略 assignment_rate 高，premium_capture_ratio 低。
- ITM 的总权利金中包含较多 intrinsic value，因此不能把总权利金全部解释为期权时间价值收入。

C. OTM 策略 premium capture 更高，但下跌保护偏弱。

- OTM2 / OTM5 的 premium_capture_ratio 较高。
- 但 downside cushion 和 max drawdown improvement 更弱。
- OTM5 更适合作为保留上涨空间或温和增强的对照组，而不是强防御主策略。

D. 510050 与 510300 存在差异。

- 510050 中 ATM_100 的综合优势更清晰。
- 510300 中 OTM2_100 的累计收益较高，说明该标的在样本期内对上涨空间保留更敏感。
- 后续需要结合 9.30 政策跳涨事件、趋势状态和 rolling mode 做进一步归因。

## 5. 当前版本局限

1. 当前只有两个 ETF，不能推广为全市场 ETF 结论。
2. 当前全部是 100% 覆盖率，没有比较 25%、50%、75%。
3. 当前没有引入 IV/RV 条件。
4. 当前没有引入趋势过滤。
5. 当前没有比较 DTE30 与 DTE60。
6. 当前仍依赖 option premium pricing 和交易成本假设。
7. 当前 moneyness 相关性只有 5 个点，属于描述性诊断，不能视为强统计结论。
8. 当前没有完成 9.30 政策跳涨事件归因。
9. 当前没有扩展到 collar / protective put 等真正尾部保护结构。

Data limitation notes:

{data_limitations}

## 6. 后续版本计划

- ver2.1: moneyness x IV/RV x trend diagnostic
- ver2.2: 9.30 policy jump event attribution and rolling mode comparison
- ver2.3: coverage ratio comparison, including 25%, 50%, 75%, 100%
- ver2.4: DTE comparison, such as DTE30 vs DTE60
- ver2.5: dynamic rules based on IV percentile and trend filter
- ver3.0: explicit downside protection structures, such as collar and protective put

## 7. 诊断文件

- Moneyness gradient summary: `outputs/ver2_downside_protection/moneyness_gradient/ver2_0_moneyness_gradient_summary.csv`
- Moneyness gradient long table: `outputs/ver2_downside_protection/moneyness_gradient/ver2_0_moneyness_gradient_long.csv`
- Moneyness correlation: `outputs/ver2_downside_protection/moneyness_gradient/ver2_0_moneyness_correlation.csv`
- Manifest: `outputs/ver2_downside_protection/reports/ver2_0_manifest.json`
"""
    path = output_dir / "reports" / "ver2_0_baseline_record.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def generate_ver2_0_moneyness_outputs(repo_root: Path, output_dir: Path | None = None) -> MoneynessGradientOutputs:
    """Generate ver2.0 static moneyness ladder diagnostics from existing outputs."""

    output_dir = output_dir or repo_root / "outputs" / "ver2_downside_protection"
    tables = load_existing_ver2_tables(output_dir)
    gradient, warnings = build_moneyness_gradient_summary(tables)
    run_moneyness_sanity_checks(gradient, tables)
    long_table = build_moneyness_gradient_long(gradient)
    correlation = build_moneyness_correlation(gradient)

    mg_dir = output_dir / "moneyness_gradient"
    mg_dir.mkdir(parents=True, exist_ok=True)
    summary_path = mg_dir / "ver2_0_moneyness_gradient_summary.csv"
    long_path = mg_dir / "ver2_0_moneyness_gradient_long.csv"
    corr_path = mg_dir / "ver2_0_moneyness_correlation.csv"
    gradient.to_csv(summary_path, index=False, encoding="utf-8-sig")
    long_table.to_csv(long_path, index=False, encoding="utf-8-sig")
    correlation.to_csv(corr_path, index=False, encoding="utf-8-sig")

    figures = write_moneyness_figures(gradient, output_dir)
    created_outputs = [summary_path, long_path, corr_path, *figures.values()]
    baseline_path = write_baseline_record(
        output_dir=output_dir,
        gradient=gradient,
        long_table=long_table,
        correlation=correlation,
        tables=tables,
        warnings=warnings,
        created_outputs=created_outputs,
    )
    created_outputs.append(baseline_path)
    manifest_path = write_manifest(repo_root=repo_root, output_dir=output_dir, created_outputs=created_outputs)
    return MoneynessGradientOutputs(
        summary=summary_path,
        long=long_path,
        correlation=corr_path,
        baseline_record=baseline_path,
        manifest=manifest_path,
        figures=figures,
    )
