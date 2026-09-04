from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from pathlib import Path
import sys

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
VER3_SRC = ROOT / "ver3" / "src"
for candidate in (ROOT, VER3_SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from covered_call_mini_ver3.diagnostics.phase_sensitivity.config import (  # noqa: E402
    PhaseRunConfig,
    TargetSleeve,
    default_paths,
)
from covered_call_mini_ver3.diagnostics.phase_sensitivity.io import (  # noqa: E402
    load_required_market_data,
    write_csv,
    write_json,
)
from covered_call_mini_ver3.diagnostics.phase_sensitivity.metrics import (  # noqa: E402
    common_window_start,
    compute_phase_metrics,
)
from covered_call_mini_ver3.diagnostics.phase_sensitivity.phase_grid import (  # noqa: E402
    generate_phase_shift_grid,
    map_phase_to_inception_dates,
)
from covered_call_mini_ver3.diagnostics.phase_sensitivity.sleeve_runner import (  # noqa: E402
    run_all_phase_sleeves,
)


EXPERIMENT_ID = "ver3_0_delta_vs_moneyness_phase_sensitivity"
MONEYNESS_GRID: tuple[tuple[str, float], ...] = (
    ("ATM", 0.00),
    ("OTM1", 0.01),
    ("OTM2", 0.02),
    ("OTM3", 0.03),
    ("OTM4", 0.04),
    ("OTM5", 0.05),
    ("OTM7", 0.07),
)


@dataclass(frozen=True)
class SleeveSpec:
    etf_code: str
    sleeve_name: str
    selector_type: str
    rule_label: str
    coverage: float
    target_delta: float | None
    target_moneyness: float | None

    @property
    def sleeve_key(self) -> str:
        return f"{self.etf_code}__{self.sleeve_name}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a focused phase-sensitivity check comparing D40 target-delta selection with fixed-moneyness rules."
    )
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--ver3-root", type=Path, default=ROOT / "ver3")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs" / EXPERIMENT_ID)
    parser.add_argument("--etfs", type=str, default="510300,510050")
    parser.add_argument("--coverages", type=str, default="0.70")
    parser.add_argument("--max-phase-shift", type=int, default=20)
    parser.add_argument("--phase-step", type=int, default=1)
    parser.add_argument("--sample-start", type=str, default="2022-09-30")
    parser.add_argument("--sample-end", type=str, default="2026-05-27")
    parser.add_argument("--reuse-existing", action="store_true")
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = args.project_root.resolve()
    ver3_root = args.ver3_root.resolve()
    output_dir = args.output_dir.resolve()
    paths = default_paths(project_root, ver3_root, output_dir)
    paths.ensure_output_dirs()

    etfs = [item.strip().zfill(6) for item in args.etfs.split(",") if item.strip()]
    coverages = [float(item.strip()) for item in args.coverages.split(",") if item.strip()]
    if not etfs:
        raise ValueError("At least one ETF must be supplied.")
    if not coverages:
        raise ValueError("At least one coverage value must be supplied.")

    run_config = PhaseRunConfig(
        max_phase_shift=args.max_phase_shift,
        phase_step=args.phase_step,
        sample_start=args.sample_start,
        sample_end=args.sample_end,
        skip_cycle_attribution=True,
        skip_ensemble=True,
        skip_plots=True,
        write_report=True,
        strict=args.strict,
    )
    sleeves, specs = build_target_sleeves(etfs, coverages)
    base_config, data = load_required_market_data(paths, etfs)
    shift_grid = generate_phase_shift_grid(run_config.max_phase_shift, run_config.phase_step)
    inception_grid = map_phase_to_inception_dates(
        data.prices,
        shift_grid,
        sample_start=run_config.sample_start,
        etf_codes=etfs,
    )
    phase_grid = shift_grid.merge(inception_grid, on=["phase_id", "phase_shift"], how="left")

    write_json(
        {
            "experiment_id": EXPERIMENT_ID,
            "run_config": asdict(run_config),
            "etfs": etfs,
            "coverages": coverages,
            "comparison": "D40 target_delta versus fixed moneyness rules",
            "exclusions": ["TP80", "Touch-K"],
        },
        paths.config_dir / "ver3_0_delta_vs_moneyness_phase_config.json",
    )
    write_csv(pd.DataFrame([asdict(spec) for spec in specs]), paths.config_dir / "ver3_0_delta_vs_moneyness_target_sleeves.csv")
    write_csv(phase_grid, paths.phase_runs_dir / "ver3_0_delta_vs_moneyness_phase_grid.csv")

    run_status_path = paths.phase_runs_dir / "ver3_0_delta_vs_moneyness_run_status.csv"
    daily_nav_path = paths.daily_dir / "ver3_0_delta_vs_moneyness_daily_nav.csv"
    daily_returns_path = paths.daily_dir / "ver3_0_delta_vs_moneyness_daily_returns.csv"
    period_map_path = paths.phase_runs_dir / "ver3_0_delta_vs_moneyness_option_cycle_map.csv"
    if args.reuse_existing and run_status_path.exists() and daily_nav_path.exists() and daily_returns_path.exists():
        run_status = pd.read_csv(run_status_path)
        daily_nav = pd.read_csv(daily_nav_path)
        daily_returns = pd.read_csv(daily_returns_path)
        period_map = pd.read_csv(period_map_path) if period_map_path.exists() else pd.DataFrame()
    else:
        runs = run_all_phase_sleeves(
            data,
            base_config,
            sleeves,
            phase_grid,
            end_date=run_config.sample_end,
            strict=run_config.strict,
        )
        run_status = runs.run_status
        daily_nav = runs.daily_nav
        daily_returns = runs.daily_returns
        period_map = runs.period_map
        write_csv(run_status, run_status_path)
        write_csv(daily_nav, daily_nav_path)
        write_csv(daily_returns, daily_returns_path)
        if not period_map.empty:
            write_csv(period_map, period_map_path)

    common_start = common_window_start(daily_nav, "sleeve_key")
    sleeve_metrics = pd.concat(
        [
            compute_phase_metrics(
                daily_nav,
                period_map,
                rf=run_config.rf,
                common_start=common_start,
                window_mode="natural",
            ),
            compute_phase_metrics(
                daily_nav,
                period_map,
                rf=run_config.rf,
                common_start=common_start,
                window_mode="common",
            ),
        ],
        ignore_index=True,
    )
    sleeve_metrics = enrich_with_specs(sleeve_metrics, specs)
    write_csv(sleeve_metrics, paths.summary_dir / "ver3_0_delta_vs_moneyness_metrics_by_phase.csv")

    summary = summarize_phase_dispersion(sleeve_metrics, period_map, specs)
    pairwise = build_pairwise_comparison(summary)
    family = build_family_comparison(summary)
    write_csv(summary, paths.summary_dir / "ver3_0_delta_vs_moneyness_phase_dispersion_summary.csv")
    write_csv(pairwise, paths.summary_dir / "ver3_0_delta_vs_moneyness_pairwise_comparison.csv")
    write_csv(family, paths.summary_dir / "ver3_0_delta_vs_moneyness_family_comparison.csv")

    report_path = paths.report_dir / "ver3_0_delta_vs_moneyness_phase_sensitivity_report.md"
    write_report(report_path, run_config, common_start, summary, pairwise, family)
    print("Delta vs moneyness phase check complete.")
    print(f"output_root: {paths.output_root}")
    print(f"phase_count: {phase_grid['phase_id'].nunique()}")
    print(f"sleeve_count: {len(sleeves)}")
    print(f"success_rate: {run_status['status'].eq('success').mean():.4f}")
    print(f"common_start: {common_start}")
    print(f"report_path: {report_path}")


def build_target_sleeves(etfs: list[str], coverages: list[float]) -> tuple[list[TargetSleeve], list[SleeveSpec]]:
    sleeves: list[TargetSleeve] = []
    specs: list[SleeveSpec] = []
    for etf_code in etfs:
        for coverage in coverages:
            q = coverage_label(coverage)
            sleeve_name = f"{etf_code}_DTE30_D40_{q}_Hold"
            sleeves.append(
                TargetSleeve(
                    etf_code=etf_code,
                    sleeve_name=sleeve_name,
                    role="Target-delta D40 sleeve for paired phase sensitivity check.",
                    is_buyhold=False,
                    strategy_name=f"D40_{q}",
                    strategy_kind="target_delta",
                    coverage=coverage,
                    target_moneyness=0.40,
                    strategy_family="D40",
                )
            )
            specs.append(
                SleeveSpec(
                    etf_code=etf_code,
                    sleeve_name=sleeve_name,
                    selector_type="target_delta",
                    rule_label="D40",
                    coverage=coverage,
                    target_delta=0.40,
                    target_moneyness=None,
                )
            )
            for rule_label, target_moneyness in MONEYNESS_GRID:
                sleeve_name = f"{etf_code}_DTE30_{rule_label}_{q}_Hold"
                sleeves.append(
                    TargetSleeve(
                        etf_code=etf_code,
                        sleeve_name=sleeve_name,
                        role=f"Fixed-moneyness {rule_label} sleeve for paired phase sensitivity check.",
                        is_buyhold=False,
                        strategy_name=f"{rule_label}_{q}",
                        strategy_kind="atm" if target_moneyness == 0 else "otm_pct",
                        coverage=coverage,
                        target_moneyness=target_moneyness,
                        strategy_family=rule_label,
                    )
                )
                specs.append(
                    SleeveSpec(
                        etf_code=etf_code,
                        sleeve_name=sleeve_name,
                        selector_type="moneyness",
                        rule_label=rule_label,
                        coverage=coverage,
                        target_delta=None,
                        target_moneyness=target_moneyness,
                    )
                )
    return sleeves, specs


def enrich_with_specs(metrics: pd.DataFrame, specs: list[SleeveSpec]) -> pd.DataFrame:
    spec_rows = []
    for spec in specs:
        row = asdict(spec)
        row["sleeve_key"] = spec.sleeve_key
        spec_rows.append(row)
    spec_df = pd.DataFrame(spec_rows)
    return metrics.merge(
        spec_df[
            [
                "sleeve_key",
                "selector_type",
                "rule_label",
                "target_delta",
                "target_moneyness",
            ]
        ],
        on="sleeve_key",
        how="left",
    )


def summarize_phase_dispersion(
    metrics: pd.DataFrame,
    period_map: pd.DataFrame,
    specs: list[SleeveSpec],
) -> pd.DataFrame:
    common = metrics[metrics["window_mode"].eq("common")].copy()
    cycle_stats = cycle_selection_stats(period_map)
    rows: list[dict[str, object]] = []
    spec_lookup = {spec.sleeve_key: spec for spec in specs}
    for sleeve_key, group in common.groupby("sleeve_key", sort=True):
        spec = spec_lookup[sleeve_key]
        row: dict[str, object] = {
            "etf_code": spec.etf_code,
            "sleeve_name": spec.sleeve_name,
            "sleeve_key": sleeve_key,
            "selector_type": spec.selector_type,
            "rule_label": spec.rule_label,
            "coverage": spec.coverage,
            "coverage_label": coverage_label(spec.coverage),
            "target_delta": spec.target_delta,
            "target_moneyness": spec.target_moneyness,
            "phase_count": int(group["phase_id"].nunique()),
        }
        for metric in [
            "sharpe_daily_mean",
            "annualized_return_cagr",
            "max_drawdown",
            "option_leg_annualized_pnl_contribution",
            "final_nav",
            "selected_periods",
        ]:
            add_metric_dispersion(row, group[metric], metric)
        sharpe_mean = float(group["sharpe_daily_mean"].mean())
        row["phase_fragility_sharpe_cv"] = float(group["sharpe_daily_mean"].std(ddof=1) / (abs(sharpe_mean) + 1e-12))
        option = group["option_leg_annualized_pnl_contribution"].astype(float)
        row["positive_option_leg_phase_rate"] = float((option > 0).mean())
        if sleeve_key in cycle_stats.index:
            row.update(cycle_stats.loc[sleeve_key].to_dict())
        rows.append(row)
    out = pd.DataFrame(rows)
    return out.sort_values(["etf_code", "coverage", "selector_type", "target_moneyness", "rule_label"]).reset_index(drop=True)


def cycle_selection_stats(period_map: pd.DataFrame) -> pd.DataFrame:
    if period_map.empty:
        return pd.DataFrame()
    p = period_map.copy()
    if "option_selected_flag" in p:
        p = p[p["option_selected_flag"].astype(float).eq(1.0)].copy()
    if p.empty:
        return pd.DataFrame()
    rows: list[dict[str, object]] = []
    for sleeve_key, group in p.groupby("sleeve_key", sort=True):
        rows.append(
            {
                "sleeve_key": sleeve_key,
                "cycle_count": int(len(group)),
                "avg_realized_moneyness": safe_mean(group.get("realized_moneyness")),
                "median_realized_moneyness": safe_median(group.get("realized_moneyness")),
                "std_realized_moneyness": safe_std(group.get("realized_moneyness")),
                "avg_selected_delta": safe_mean(group.get("selected_delta")),
                "median_selected_delta": safe_median(group.get("selected_delta")),
                "std_selected_delta": safe_std(group.get("selected_delta")),
            }
        )
    return pd.DataFrame(rows).set_index("sleeve_key")


def add_metric_dispersion(row: dict[str, object], values: pd.Series, metric: str) -> None:
    v = pd.to_numeric(values, errors="coerce").dropna()
    if v.empty:
        row[f"{metric}_min"] = np.nan
        row[f"{metric}_median"] = np.nan
        row[f"{metric}_max"] = np.nan
        row[f"{metric}_range"] = np.nan
        row[f"{metric}_std"] = np.nan
        return
    row[f"{metric}_min"] = float(v.min())
    row[f"{metric}_median"] = float(v.median())
    row[f"{metric}_max"] = float(v.max())
    row[f"{metric}_range"] = float(v.max() - v.min())
    row[f"{metric}_std"] = float(v.std(ddof=1)) if len(v) > 1 else 0.0


def build_pairwise_comparison(summary: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (etf_code, coverage), group in summary.groupby(["etf_code", "coverage"], sort=True):
        delta = group[group["selector_type"].eq("target_delta")]
        moneyness = group[group["selector_type"].eq("moneyness")].copy()
        if delta.empty or moneyness.empty:
            continue
        d = delta.iloc[0]
        d_mny = float(d.get("avg_realized_moneyness", np.nan))
        if np.isfinite(d_mny):
            moneyness["_distance_to_d40_realized_moneyness"] = (
                pd.to_numeric(moneyness["avg_realized_moneyness"], errors="coerce") - d_mny
            ).abs()
            nearest = moneyness.sort_values("_distance_to_d40_realized_moneyness").iloc[0]
        else:
            nearest = moneyness.sort_values("sharpe_daily_mean_range").iloc[0]
        mny_median_sharpe_range = float(moneyness["sharpe_daily_mean_range"].median())
        mny_median_option_range = float(moneyness["option_leg_annualized_pnl_contribution_range"].median())
        row = {
            "etf_code": etf_code,
            "coverage": coverage,
            "coverage_label": coverage_label(float(coverage)),
            "delta_rule": str(d["rule_label"]),
            "nearest_moneyness_rule": str(nearest["rule_label"]),
            "delta_avg_realized_moneyness": d.get("avg_realized_moneyness", np.nan),
            "nearest_avg_realized_moneyness": nearest.get("avg_realized_moneyness", np.nan),
            "delta_sharpe_range": float(d["sharpe_daily_mean_range"]),
            "nearest_moneyness_sharpe_range": float(nearest["sharpe_daily_mean_range"]),
            "moneyness_median_sharpe_range": mny_median_sharpe_range,
            "delta_option_leg_range": float(d["option_leg_annualized_pnl_contribution_range"]),
            "nearest_moneyness_option_leg_range": float(nearest["option_leg_annualized_pnl_contribution_range"]),
            "moneyness_median_option_leg_range": mny_median_option_range,
            "delta_sharpe_range_minus_nearest": float(d["sharpe_daily_mean_range"] - nearest["sharpe_daily_mean_range"]),
            "delta_option_range_minus_nearest": float(
                d["option_leg_annualized_pnl_contribution_range"]
                - nearest["option_leg_annualized_pnl_contribution_range"]
            ),
            "delta_sharpe_range_minus_moneyness_median": float(d["sharpe_daily_mean_range"] - mny_median_sharpe_range),
            "delta_option_range_minus_moneyness_median": float(
                d["option_leg_annualized_pnl_contribution_range"] - mny_median_option_range
            ),
        }
        row["delta_less_phase_sensitive_than_nearest"] = bool(
            row["delta_sharpe_range_minus_nearest"] <= 0 and row["delta_option_range_minus_nearest"] <= 0
        )
        row["delta_less_phase_sensitive_than_moneyness_median"] = bool(
            row["delta_sharpe_range_minus_moneyness_median"] <= 0
            and row["delta_option_range_minus_moneyness_median"] <= 0
        )
        rows.append(row)
    return pd.DataFrame(rows)


def build_family_comparison(summary: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (etf_code, coverage, selector_type), group in summary.groupby(["etf_code", "coverage", "selector_type"], sort=True):
        rows.append(
            {
                "etf_code": etf_code,
                "coverage": coverage,
                "coverage_label": coverage_label(float(coverage)),
                "selector_type": selector_type,
                "rule_count": int(group["sleeve_name"].nunique()),
                "median_sharpe_range": float(group["sharpe_daily_mean_range"].median()),
                "min_sharpe_range": float(group["sharpe_daily_mean_range"].min()),
                "max_sharpe_range": float(group["sharpe_daily_mean_range"].max()),
                "median_option_leg_range": float(group["option_leg_annualized_pnl_contribution_range"].median()),
                "min_option_leg_range": float(group["option_leg_annualized_pnl_contribution_range"].min()),
                "max_option_leg_range": float(group["option_leg_annualized_pnl_contribution_range"].max()),
                "median_cagr_range": float(group["annualized_return_cagr_range"].median()),
                "median_mdd_range": float(group["max_drawdown_range"].median()),
            }
        )
    return pd.DataFrame(rows)


def write_report(
    path: Path,
    run_config: PhaseRunConfig,
    common_start: str,
    summary: pd.DataFrame,
    pairwise: pd.DataFrame,
    family: pd.DataFrame,
) -> None:
    lines = [
        "# Delta vs Moneyness Phase Sensitivity Check",
        "",
        "## Scope",
        "",
        f"- Phase grid: h00 to h{run_config.max_phase_shift:02d}, step {run_config.phase_step}.",
        f"- Sample end: {run_config.sample_end}; common metric window starts at {common_start}.",
        "- Tested selectors: D40 target_delta versus ATM/OTM1/OTM2/OTM3/OTM4/OTM5/OTM7 fixed moneyness.",
        "- Excluded path-management rules: TP80 and Touch-K.",
        "",
        "## Pairwise Result",
        "",
        markdown_table(pairwise),
        "",
        "## Family Dispersion",
        "",
        markdown_table(family),
        "",
        "## Sleeve Dispersion Detail",
        "",
        markdown_table(
            summary[
                [
                    "etf_code",
                    "coverage_label",
                    "selector_type",
                    "rule_label",
                    "sharpe_daily_mean_median",
                    "sharpe_daily_mean_range",
                    "annualized_return_cagr_median",
                    "annualized_return_cagr_range",
                    "option_leg_annualized_pnl_contribution_median",
                    "option_leg_annualized_pnl_contribution_range",
                    "avg_realized_moneyness",
                    "avg_selected_delta",
                ]
            ]
        ),
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8-sig")


def markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_No rows._"
    display = df.copy()
    for col in display.columns:
        if pd.api.types.is_float_dtype(display[col]):
            display[col] = display[col].map(lambda x: "" if pd.isna(x) else f"{x:.6f}")
    return display.to_markdown(index=False)


def coverage_label(coverage: float) -> str:
    return f"Q{int(round(float(coverage) * 100))}"


def safe_mean(values: pd.Series | None) -> float:
    if values is None:
        return np.nan
    v = pd.to_numeric(values, errors="coerce").dropna()
    return float(v.mean()) if not v.empty else np.nan


def safe_median(values: pd.Series | None) -> float:
    if values is None:
        return np.nan
    v = pd.to_numeric(values, errors="coerce").dropna()
    return float(v.median()) if not v.empty else np.nan


def safe_std(values: pd.Series | None) -> float:
    if values is None:
        return np.nan
    v = pd.to_numeric(values, errors="coerce").dropna()
    return float(v.std(ddof=1)) if len(v) > 1 else 0.0


if __name__ == "__main__":
    main()
