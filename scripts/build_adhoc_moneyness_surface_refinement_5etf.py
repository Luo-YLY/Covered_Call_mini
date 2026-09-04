from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import json
import sys
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import PercentFormatter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.backtest.custom import CustomBacktestRequest, run_custom_covered_call_backtest  # noqa: E402


OUTPUT_PROFILES = {
    "adhoc": {
        "experiment_id": "_adhoc_moneyness_surface_refinement_5etf",
        "out_dir": "_adhoc_moneyness_surface_refinement_5etf",
        "file_prefix": "adhoc_moneyness_refined",
        "figure_prefix": "adhoc_moneyness_surface",
        "report_name": "adhoc_moneyness_surface_refinement_5etf_report.md",
        "report_title": "Ad hoc：5 ETF moneyness 细网格参数曲面诊断",
        "boundary_manifest": "Independent ad hoc diagnostic. Does not modify current ver3 reports, dashboard data, or main strategy conclusions.",
        "boundary_report": "本报告是独立 ad hoc 诊断，不修改当前 ver3 总报告、dashboard 主数据或主线策略结论。",
        "source_note": "Ad hoc monthly DTE30 moneyness-target backtest from raw option chain; independent from current ver3 report.",
    },
    "official": {
        "experiment_id": "ver3_0_stepA_moneyness_refined_surface",
        "out_dir": "ver3_0_stepA_moneyness_refined_surface",
        "file_prefix": "ver3_0_stepA_moneyness_refined",
        "figure_prefix": "ver3_0_stepA_moneyness_refined_surface",
        "report_name": "ver3_0_stepA_moneyness_refined_surface_report.md",
        "report_title": "ver3.0 Step A：5 ETF moneyness 细网格参数曲面诊断",
        "boundary_manifest": "Formal single-ETF diagnostic enhancement. It refines the moneyness axis only and does not modify Step B/C/D main strategy conclusions. Monthly segmented NAV only; not comparable to daily MTM sleeve results and not eligible for direct strategy recommendation.",
        "boundary_report": "本报告是 ver3.0 Step A 单 ETF 诊断增强层。它只细化单 ETF 的虚值程度 × 覆盖率参数曲面，不修改当前 Step B/C/D 组合主线结论。",
        "source_note": "ver3.0 Step A refined monthly DTE30 moneyness-target backtest from raw option chain; diagnostic layer only.",
    },
}

PROFILE_NAME = "adhoc"
PROFILE = OUTPUT_PROFILES[PROFILE_NAME]
OUT_ROOT = ROOT / "outputs" / PROFILE["out_dir"]
SUMMARY_DIR = OUT_ROOT / "summary"
FIGURE_DIR = OUT_ROOT / "figures"
REPORT_DIR = OUT_ROOT / "reports"
FILE_PREFIX = PROFILE["file_prefix"]
FIGURE_PREFIX = PROFILE["figure_prefix"]
REPORT_NAME = PROFILE["report_name"]
REPORT_TITLE = PROFILE["report_title"]
BOUNDARY_MANIFEST = PROFILE["boundary_manifest"]
BOUNDARY_REPORT = PROFILE["boundary_report"]
SOURCE_NOTE = PROFILE["source_note"]

PRICE_PATH = ROOT / "data" / "raw" / "etf_prices.csv"
OPTION_PATH = ROOT / "data" / "raw" / "options.csv"
METADATA_PATH = ROOT / "data" / "raw" / "etf_metadata.csv"

MAIN_START = "2022-09-19"
SHORT_START = "2023-06-30"
END_DATE = "2026-05-27"

ETF_ORDER = ["510300", "510050", "510500", "159915", "588000"]
MONEYNESS_GRID = [
    ("ATM", 0.00),
    ("OTM1", 0.01),
    ("OTM2", 0.02),
    ("OTM3", 0.03),
    ("OTM4", 0.04),
    ("OTM5", 0.05),
    ("OTM7", 0.07),
]
COVERAGE_GRID = [round(x / 10, 1) for x in range(1, 11)]


@dataclass(frozen=True)
class EtfSpec:
    etf_code: str
    sample_start: str
    sample_end: str
    role_note: str


ETF_SPECS = {
    "510300": EtfSpec("510300", MAIN_START, END_DATE, "主线大盘核心资产；本轮观察更细 moneyness 是否改变 ATM/D40/OTM5 的粗网格直觉。"),
    "510050": EtfSpec("510050", MAIN_START, END_DATE, "大盘偏蓝筹/偏防御补充；已有网格相对更细，本轮提供 moneyness 口径的同一标尺。"),
    "510500": EtfSpec("510500", MAIN_START, END_DATE, "中盘分散化资产；重点观察轻度 OTM 是否优于直接裸持。"),
    "159915": EtfSpec("159915", MAIN_START, END_DATE, "成长弹性资产；重点观察低覆盖、轻虚值是否能保留上行并降低回撤。"),
    "588000": EtfSpec("588000", SHORT_START, END_DATE, "科创成长扩展样本；样本短于主线，只作为 extension 诊断。"),
}


def main(profile_name: str | None = None) -> None:
    if profile_name is None:
        profile_name = parse_args().profile
    configure_output_profile(profile_name)
    ensure_dirs()
    prices = pd.read_csv(PRICE_PATH, dtype={"etf_code": str}, parse_dates=["date"])
    options = pd.read_csv(OPTION_PATH, dtype={"underlying_etf": str}, parse_dates=["trade_date", "expiry"])
    metadata = pd.read_csv(METADATA_PATH, dtype={"etf_code": str}) if METADATA_PATH.exists() else pd.DataFrame()

    all_surface: list[pd.DataFrame] = []
    all_periods: list[pd.DataFrame] = []
    all_nav: list[pd.DataFrame] = []
    all_buyhold: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []

    for etf_code in ETF_ORDER:
        spec = ETF_SPECS[etf_code]
        print(f"running moneyness refinement: {etf_code}")
        etf_prices = prices[prices["etf_code"].astype(str).str.zfill(6).eq(etf_code)].copy()
        etf_options = options[options["underlying_etf"].astype(str).str.zfill(6).eq(etf_code)].copy()
        surface, periods, nav, buyhold, diag = run_etf_grid(etf_prices, etf_options, metadata, spec)
        all_surface.append(surface)
        all_periods.append(periods)
        all_nav.append(nav)
        if buyhold:
            all_buyhold.append(buyhold)
        diagnostics.extend(diag)

    surface_df = pd.concat(all_surface, ignore_index=True, sort=False)
    period_df = pd.concat(all_periods, ignore_index=True, sort=False)
    nav_df = pd.concat(all_nav, ignore_index=True, sort=False)
    buyhold_df = pd.DataFrame(all_buyhold)
    diagnostics_df = pd.DataFrame(diagnostics)

    surface_df.insert(0, "surface_point_id", [f"mny_{i + 1:04d}" for i in range(len(surface_df))])
    surface_df.to_csv(SUMMARY_DIR / f"{FILE_PREFIX}_surface_grid.csv", index=False, encoding="utf-8-sig")
    buyhold_df.to_csv(SUMMARY_DIR / f"{FILE_PREFIX}_buyhold_baseline.csv", index=False, encoding="utf-8-sig")
    diagnostics_df.to_csv(SUMMARY_DIR / f"{FILE_PREFIX}_run_diagnostics.csv", index=False, encoding="utf-8-sig")
    period_df.to_csv(SUMMARY_DIR / f"{FILE_PREFIX}_period_paths.csv", index=False, encoding="utf-8-sig")
    nav_df.to_csv(SUMMARY_DIR / f"{FILE_PREFIX}_nav_paths.csv", index=False, encoding="utf-8-sig")

    figure_rows = write_figures(surface_df)
    figure_df = pd.DataFrame(figure_rows)
    figure_df.to_csv(SUMMARY_DIR / f"{FILE_PREFIX}_figures.csv", index=False, encoding="utf-8-sig")

    report = build_report(surface_df, buyhold_df, diagnostics_df, figure_df)
    report_path = REPORT_DIR / REPORT_NAME
    report_path.write_text(report, encoding="utf-8")

    manifest = {
        "experiment_id": PROFILE["experiment_id"],
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "complete",
        "boundary": BOUNDARY_MANIFEST,
        "sample_end": END_DATE,
        "moneyness_grid": [label for label, _ in MONEYNESS_GRID],
        "coverage_grid": [f"Q{int(v * 100)}" for v in COVERAGE_GRID],
        "output_files": {
            "report": rel_output_path(report_path),
            "surface_grid": f"summary/{FILE_PREFIX}_surface_grid.csv",
            "buyhold_baseline": f"summary/{FILE_PREFIX}_buyhold_baseline.csv",
            "period_paths": f"summary/{FILE_PREFIX}_period_paths.csv",
            "nav_paths": f"summary/{FILE_PREFIX}_nav_paths.csv",
            "figures": "figures/",
        },
        "row_counts": {
            "surface_grid": int(len(surface_df)),
            "period_paths": int(len(period_df)),
            "nav_paths": int(len(nav_df)),
        },
    }
    (OUT_ROOT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"wrote report: {report_path}")
    print(f"wrote grid: {SUMMARY_DIR / f'{FILE_PREFIX}_surface_grid.csv'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build 5 ETF moneyness x coverage refined surface diagnostics.")
    parser.add_argument(
        "--profile",
        choices=sorted(OUTPUT_PROFILES),
        default="adhoc",
        help="Output profile. Use official for ver3 Step A diagnostic outputs.",
    )
    return parser.parse_args()


def configure_output_profile(profile_name: str) -> None:
    if profile_name not in OUTPUT_PROFILES:
        raise ValueError(f"Unsupported output profile: {profile_name}")
    global PROFILE_NAME, PROFILE, OUT_ROOT, SUMMARY_DIR, FIGURE_DIR, REPORT_DIR
    global FILE_PREFIX, FIGURE_PREFIX, REPORT_NAME, REPORT_TITLE
    global BOUNDARY_MANIFEST, BOUNDARY_REPORT, SOURCE_NOTE
    PROFILE_NAME = profile_name
    PROFILE = OUTPUT_PROFILES[profile_name]
    OUT_ROOT = ROOT / "outputs" / PROFILE["out_dir"]
    SUMMARY_DIR = OUT_ROOT / "summary"
    FIGURE_DIR = OUT_ROOT / "figures"
    REPORT_DIR = OUT_ROOT / "reports"
    FILE_PREFIX = PROFILE["file_prefix"]
    FIGURE_PREFIX = PROFILE["figure_prefix"]
    REPORT_NAME = PROFILE["report_name"]
    REPORT_TITLE = PROFILE["report_title"]
    BOUNDARY_MANIFEST = PROFILE["boundary_manifest"]
    BOUNDARY_REPORT = PROFILE["boundary_report"]
    SOURCE_NOTE = PROFILE["source_note"]


def ensure_dirs() -> None:
    for path in [OUT_ROOT, SUMMARY_DIR, FIGURE_DIR, REPORT_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def run_etf_grid(
    prices: pd.DataFrame,
    options: pd.DataFrame,
    metadata: pd.DataFrame,
    spec: EtfSpec,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any], list[dict[str, Any]]]:
    surface_rows: list[dict[str, Any]] = []
    period_frames: list[pd.DataFrame] = []
    nav_frames: list[pd.DataFrame] = []
    diagnostics: list[dict[str, Any]] = []
    buyhold_row: dict[str, Any] = {}

    for moneyness_label, target_moneyness in MONEYNESS_GRID:
        for coverage in COVERAGE_GRID:
            request = CustomBacktestRequest(
                etf_code=spec.etf_code,
                coverage_ratio=coverage,
                start_date=spec.sample_start,
                end_date=spec.sample_end,
                roll_frequency="monthly",
                target_dte=30,
                min_days_to_expiry=20,
                max_days_to_expiry=45,
                selection_mode="atm" if target_moneyness == 0 else "otm_pct",
                otm_pct=target_moneyness,
                min_periods=6,
            )
            result = run_custom_covered_call_backtest(
                prices,
                options,
                request,
                metadata=metadata,
                liquidity_filters={"min_option_volume": 0, "min_open_interest": 0, "max_bid_ask_spread_pct": 1.0},
                transaction_costs={
                    "option_slippage_bps": 5,
                    "etf_slippage_bps": 2,
                    "option_commission_per_contract": 0,
                    "use_bid_ask_spread_cost": True,
                },
            )
            summary = result["summary"].copy()
            periods = result["periods"].copy()
            nav = result["nav"].copy()
            diag = dict(result["diagnostics"])

            strategy_name = strategy_label(spec.etf_code, moneyness_label, coverage)
            raw_strategy = str(diag["strategy_name"])
            periods["strategy"] = periods["strategy"].replace({raw_strategy: strategy_name, "S0_BuyHold": buyhold_label(spec.etf_code)})
            nav["strategy"] = nav["strategy"].replace({raw_strategy: strategy_name, "S0_BuyHold": buyhold_label(spec.etf_code)})
            period_frames.append(add_grid_fields(periods, moneyness_label, target_moneyness, coverage))
            nav_frames.append(add_grid_fields(nav, moneyness_label, target_moneyness, coverage))

            if not buyhold_row:
                buyhold_summary = summary[summary["strategy"].eq("S0_BuyHold")]
                if not buyhold_summary.empty:
                    buyhold_row = summarize_buyhold(buyhold_summary.iloc[0], spec)

            cc_summary = summary[~summary["strategy"].eq("S0_BuyHold")]
            if cc_summary.empty:
                continue
            cc = cc_summary.iloc[0]
            cc_periods = periods[periods["strategy"].eq(strategy_name)].copy()
            surface_rows.append(summarize_surface_row(cc, cc_periods, spec, moneyness_label, target_moneyness, coverage, strategy_name))
            diagnostics.append({
                "etf_code": spec.etf_code,
                "moneyness_label": moneyness_label,
                "target_moneyness": target_moneyness,
                "coverage": coverage,
                "strategy_name": strategy_name,
                "available_periods": diag.get("available_periods"),
                "selected_periods": diag.get("selected_periods"),
                "warnings": "; ".join(diag.get("warnings", [])),
            })

    return (
        pd.DataFrame(surface_rows),
        pd.concat(period_frames, ignore_index=True, sort=False),
        pd.concat(nav_frames, ignore_index=True, sort=False),
        buyhold_row,
        diagnostics,
    )


def strategy_label(etf_code: str, moneyness_label: str, coverage: float) -> str:
    return f"{etf_code}_DTE30_{moneyness_label}_Q{int(round(coverage * 100))}_MonthlyHold"


def buyhold_label(etf_code: str) -> str:
    return f"{etf_code}_ETF_BuyHold"


def add_grid_fields(df: pd.DataFrame, moneyness_label: str, target_moneyness: float, coverage: float) -> pd.DataFrame:
    out = df.copy()
    out["moneyness_label"] = moneyness_label
    out["target_moneyness"] = target_moneyness
    out["coverage"] = coverage
    out["coverage_label"] = f"Q{int(round(coverage * 100))}"
    return out


def summarize_buyhold(row: pd.Series, spec: EtfSpec) -> dict[str, Any]:
    return {
        "etf_code": spec.etf_code,
        "strategy_name": buyhold_label(spec.etf_code),
        "sample_start": spec.sample_start,
        "sample_end": spec.sample_end,
        "cumulative_return": row.get("cumulative_return"),
        "annualized_return_cagr": row.get("annualized_return"),
        "annualized_volatility": row.get("annualized_volatility"),
        "sharpe_daily_mean": row.get("sharpe_ratio"),
        "max_drawdown": abs_float(row.get("max_drawdown")),
        "option_leg_annualized_pnl_contribution": 0.0,
    }


def summarize_surface_row(
    row: pd.Series,
    periods: pd.DataFrame,
    spec: EtfSpec,
    moneyness_label: str,
    target_moneyness: float,
    coverage: float,
    strategy_name: str,
) -> dict[str, Any]:
    selected = periods[periods["option_selected_flag"].astype(int).eq(1)].copy()
    annual_factor = 12.0
    return {
        "etf_code": spec.etf_code,
        "strategy_name": strategy_name,
        "moneyness_label": moneyness_label,
        "target_moneyness": target_moneyness,
        "avg_realized_moneyness": numeric_mean(selected.get("moneyness")),
        "median_realized_moneyness": numeric_median(selected.get("moneyness")),
        "coverage": coverage,
        "coverage_label": f"Q{int(round(coverage * 100))}",
        "sample_start": spec.sample_start,
        "sample_end": spec.sample_end,
        "n_periods": int(len(periods[periods["strategy"].eq(strategy_name)])),
        "selected_periods": int(selected["option_selected_flag"].sum()) if not selected.empty else 0,
        "option_sale_success_rate": row.get("option_sale_success_rate"),
        "assignment_frequency": row.get("assignment_frequency"),
        "avg_selected_delta": row.get("average_selected_delta"),
        "cumulative_return": row.get("cumulative_return"),
        "annualized_return_cagr": row.get("annualized_return"),
        "annualized_volatility": row.get("annualized_volatility"),
        "sharpe_daily_mean": row.get("sharpe_ratio"),
        "max_drawdown": abs_float(row.get("max_drawdown")),
        "calmar_ratio": row.get("calmar_ratio"),
        "premium_contribution_annualized": numeric_mean(periods[periods["strategy"].eq(strategy_name)].get("premium_contribution")) * annual_factor,
        "upside_cost_annualized": numeric_mean(periods[periods["strategy"].eq(strategy_name)].get("upside_cost")) * annual_factor,
        "option_leg_annualized_pnl_contribution": numeric_mean(periods[periods["strategy"].eq(strategy_name)].get("net_option_contribution")) * annual_factor,
        "total_net_option_contribution": row.get("net_option_contribution"),
        "source_note": SOURCE_NOTE,
    }


def abs_float(value: Any) -> float:
    try:
        if pd.isna(value):
            return np.nan
        return abs(float(value))
    except (TypeError, ValueError):
        return np.nan


def numeric_mean(series: Any) -> float:
    if series is None:
        return np.nan
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.mean()) if len(values) else np.nan


def numeric_median(series: Any) -> float:
    if series is None:
        return np.nan
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.median()) if len(values) else np.nan


def write_figures(surface: pd.DataFrame) -> list[dict[str, str]]:
    setup_plot_style()
    rows: list[dict[str, str]] = []
    for etf_code in ETF_ORDER:
        sub = surface[surface["etf_code"].eq(etf_code)].copy()
        if sub.empty:
            continue
        for metric_name, metric_label in [
            ("sharpe_daily_mean", "Sharpe"),
            ("annualized_return_cagr", "CAGR"),
            ("max_drawdown", "MDD"),
            ("option_leg_annualized_pnl_contribution", "期权腿年化贡献"),
        ]:
            path = FIGURE_DIR / f"{FIGURE_PREFIX}_{etf_code}_{metric_name}.png"
            write_surface_figure(path, sub, metric_name, metric_label, etf_code)
            rows.append({
                "etf_code": etf_code,
                "metric_name": metric_name,
                "metric_label": metric_label,
                "figure_path": str(path.relative_to(OUT_ROOT)).replace("\\", "/"),
            })
    return rows


def write_surface_figure(path: Path, data: pd.DataFrame, metric_name: str, metric_label: str, etf_code: str) -> None:
    pivot = data.pivot_table(index="coverage", columns="target_moneyness", values=metric_name, aggfunc="first")
    x = pivot.columns.astype(float).to_numpy()
    y = pivot.index.astype(float).to_numpy()
    xx, yy = np.meshgrid(x, y)
    zz = pivot.to_numpy(dtype=float)

    fig = plt.figure(figsize=(8.8, 5.9))
    ax = fig.add_subplot(111, projection="3d")
    surface = ax.plot_surface(xx, yy, zz, cmap="viridis", linewidth=0.25, edgecolor="white", alpha=0.84)
    ax.scatter(xx.ravel(), yy.ravel(), zz.ravel(), color="#1c2d3d", s=14, alpha=0.78)
    best = data.sort_values(metric_name, ascending=(metric_name == "max_drawdown")).iloc[0]
    ax.scatter(
        [float(best["target_moneyness"])],
        [float(best["coverage"])],
        [float(best[metric_name])],
        color="#bd3d36",
        s=72,
        marker="*",
        label="最佳真实格点",
    )
    ax.set_title(f"{etf_code} moneyness refined surface - {metric_label}", fontsize=12, fontweight="bold", pad=14)
    ax.set_xlabel("目标虚值")
    ax.set_ylabel("覆盖率")
    ax.set_zlabel(metric_label)
    ax.xaxis.set_major_formatter(PercentFormatter(1.0))
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    if metric_name in {"annualized_return_cagr", "max_drawdown", "option_leg_annualized_pnl_contribution"}:
        ax.zaxis.set_major_formatter(PercentFormatter(1.0))
    ax.view_init(elev=26, azim=-55)
    ax.legend(loc="upper left", fontsize=8)
    fig.colorbar(surface, ax=ax, shrink=0.58, pad=0.08, label=metric_label)
    fig.tight_layout()
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def setup_plot_style() -> None:
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def build_report(surface: pd.DataFrame, buyhold: pd.DataFrame, diagnostics: pd.DataFrame, figures: pd.DataFrame) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sections = "\n\n".join(build_etf_section(etf, surface, buyhold, diagnostics, figures, idx) for idx, etf in enumerate(ETF_ORDER, 1))
    surface_path = rel_output_path(SUMMARY_DIR / f"{FILE_PREFIX}_surface_grid.csv")
    buyhold_path = rel_output_path(SUMMARY_DIR / f"{FILE_PREFIX}_buyhold_baseline.csv")
    period_path = rel_output_path(SUMMARY_DIR / f"{FILE_PREFIX}_period_paths.csv")
    return f"""# {REPORT_TITLE}

生成时间：{generated_at}

## 0. 边界说明

{BOUNDARY_REPORT}

它使用 raw option chain 重新按 moneyness 选券，目的是把虚值轴从原来的粗网格细化为：

```text
ATM / OTM1 / OTM2 / OTM3 / OTM4 / OTM5 / OTM7
```

覆盖率仍为 `Q10` 到 `Q100`。本轮采用 monthly DTE30 持有到期口径，指标与当前 ver3 主报告中的日频 MTM/冻结口径不应直接硬比；本报告只回答“更细 moneyness 网格下，单 ETF 参数曲面的形状如何”。

口径警告：

- 本报告的 NAV 是月度分段 NAV，不是日频 MTM NAV；MDD 和 Sharpe 不包含月内净值波动。
- 期权多在月末前到期，收益由“到期日赔付 + 月末 ETF 底仓收益”合成，和主线 sleeve 的日频持仓/估值口径不同。
- ATM/Q100 的 Sharpe 高点常来自波动和回撤被机械压低，并不代表期权腿盈利或组合层适合采用。
- 下表的 `Best` 只表示当前单指标曲面高点，不是策略推荐；组合主线仍以 Step A/B/C 的冻结口径和稳定性诊断为准。

完整真实格点数据保存在：

- `{surface_path}`
- `{buyhold_path}`
- `{period_path}`

## 1. 曲面高点观察（非策略推荐）

{summary_table(surface, buyhold)}

## 2. 分 ETF 诊断

{sections}
"""


def summary_table(surface: pd.DataFrame, buyhold: pd.DataFrame) -> str:
    rows = []
    for etf_code in ETF_ORDER:
        top = surface[surface["etf_code"].eq(etf_code)].sort_values("sharpe_daily_mean", ascending=False).head(1)
        bh = buyhold[buyhold["etf_code"].eq(etf_code)]
        if top.empty:
            continue
        row = top.iloc[0]
        bh_row = bh.iloc[0] if not bh.empty else pd.Series(dtype=float)
        rows.append({
            "ETF": etf_code,
            "BuyHold Sharpe": bh_row.get("sharpe_daily_mean", np.nan),
            "Best rule": row["moneyness_label"],
            "Best coverage": row["coverage_label"],
            "Best Sharpe": row["sharpe_daily_mean"],
            "Best CAGR": row["annualized_return_cagr"],
            "Best MDD": row["max_drawdown"],
            "Best option leg": row["option_leg_annualized_pnl_contribution"],
        })
    return md_table(pd.DataFrame(rows), pct_cols=["Best CAGR", "Best MDD", "Best option leg"], num_cols=["BuyHold Sharpe", "Best Sharpe"])


def build_etf_section(etf_code: str, surface: pd.DataFrame, buyhold: pd.DataFrame, diagnostics: pd.DataFrame, figures: pd.DataFrame, idx: int) -> str:
    sub = surface[surface["etf_code"].eq(etf_code)].copy()
    bh = buyhold[buyhold["etf_code"].eq(etf_code)].copy()
    diag = diagnostics[diagnostics["etf_code"].eq(etf_code)].copy()
    spec = ETF_SPECS[etf_code]
    if sub.empty:
        return f"### 2.{idx} {etf_code}\n\n暂无数据。"

    best_sharpe = sub.sort_values("sharpe_daily_mean", ascending=False).iloc[0]
    best_mdd = sub.sort_values("max_drawdown", ascending=True).iloc[0]
    bh_row = bh.iloc[0] if not bh.empty else pd.Series(dtype=float)
    selected_period_min = int(diag["selected_periods"].min()) if not diag.empty else 0
    selected_period_max = int(diag["selected_periods"].max()) if not diag.empty else 0
    fig = figure_md(figures, etf_code, "sharpe_daily_mean")
    top_rows = top_table(sub, bh_row)
    pivot = sharpe_pivot_table(sub)

    return f"""### 2.{idx} {etf_code}

定位：{spec.role_note}

样本：`{spec.sample_start}` 至 `{spec.sample_end}`。每个参数点可卖出期权周期数范围：`{selected_period_min}` 到 `{selected_period_max}`。

{fig}

核心观察：

- BuyHold Sharpe：`{fmt_num(bh_row.get("sharpe_daily_mean", np.nan))}`。
- Sharpe 最优真实格点：`{best_sharpe["moneyness_label"]} / {best_sharpe["coverage_label"]}`，Sharpe `{fmt_num(best_sharpe["sharpe_daily_mean"])}`，CAGR `{fmt_pct(best_sharpe["annualized_return_cagr"])}`，MDD `{fmt_pct(best_sharpe["max_drawdown"])}`。
- MDD 最低真实格点：`{best_mdd["moneyness_label"]} / {best_mdd["coverage_label"]}`，MDD `{fmt_pct(best_mdd["max_drawdown"])}`，Sharpe `{fmt_num(best_mdd["sharpe_daily_mean"])}`。
- 实际虚值会受行权价离散影响，报告中的图使用目标虚值作横轴，表格同时给出平均/中位实现虚值。
- 上述“最优”只是在本月度分段曲面内按单指标排序，不进入组合层推荐。

BuyHold 与 Sharpe 前八：

{top_rows}

Sharpe 网格透视表：

{pivot}
"""


def figure_md(figures: pd.DataFrame, etf_code: str, metric_name: str) -> str:
    row = figures[figures["etf_code"].eq(etf_code) & figures["metric_name"].eq(metric_name)]
    if row.empty:
        return "_未生成图表。_"
    path = "../" + str(row.iloc[0]["figure_path"]).replace("\\", "/")
    return f"![{etf_code} Sharpe moneyness surface]({path})"


def top_table(sub: pd.DataFrame, bh_row: pd.Series) -> str:
    rows = []
    if not bh_row.empty:
        rows.append({
            "类型": "BuyHold",
            "规则": "BuyHold",
            "覆盖率": "0%",
            "目标虚值": "",
            "平均实现虚值": "",
            "中位实现虚值": "",
            "CAGR": bh_row.get("annualized_return_cagr"),
            "Sharpe": bh_row.get("sharpe_daily_mean"),
            "MDD": bh_row.get("max_drawdown"),
            "期权腿年化": 0.0,
        })
    for _, row in sub.sort_values("sharpe_daily_mean", ascending=False).head(8).iterrows():
        rows.append({
            "类型": "Sharpe前八",
            "规则": row["moneyness_label"],
            "覆盖率": row["coverage_label"],
            "目标虚值": row["target_moneyness"],
            "平均实现虚值": row["avg_realized_moneyness"],
            "中位实现虚值": row["median_realized_moneyness"],
            "CAGR": row["annualized_return_cagr"],
            "Sharpe": row["sharpe_daily_mean"],
            "MDD": row["max_drawdown"],
            "期权腿年化": row["option_leg_annualized_pnl_contribution"],
        })
    return md_table(
        pd.DataFrame(rows),
        pct_cols=["目标虚值", "平均实现虚值", "中位实现虚值", "CAGR", "MDD", "期权腿年化"],
        num_cols=["Sharpe"],
    )


def sharpe_pivot_table(sub: pd.DataFrame) -> str:
    pivot = sub.pivot_table(index="moneyness_label", columns="coverage_label", values="sharpe_daily_mean", aggfunc="first")
    order = [label for label, _ in MONEYNESS_GRID]
    cols = [f"Q{int(v * 100)}" for v in COVERAGE_GRID]
    pivot = pivot.reindex(index=order, columns=cols)
    return md_table(pivot.reset_index().rename(columns={"moneyness_label": "规则"}), num_cols=cols)


def md_table(df: pd.DataFrame, pct_cols: list[str] | None = None, num_cols: list[str] | None = None) -> str:
    if df.empty:
        return "_empty_"
    out = df.copy()
    pct = set(pct_cols or [])
    num = set(num_cols or [])
    for col in out.columns:
        if col in pct:
            out[col] = out[col].map(fmt_pct)
        elif col in num:
            out[col] = out[col].map(fmt_num)
        else:
            out[col] = out[col].map(fmt_cell)
    return out.to_markdown(index=False)


def fmt_cell(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value)


def fmt_pct(value: Any) -> str:
    try:
        if pd.isna(value) or value == "":
            return ""
        return f"{float(value):.2%}"
    except (TypeError, ValueError):
        return ""


def fmt_num(value: Any) -> str:
    try:
        if pd.isna(value):
            return ""
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return ""


def rel_output_path(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


if __name__ == "__main__":
    main()
