from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
VER3_SRC = ROOT / "ver3" / "src"
for path in (ROOT, VER3_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from covered_call_mini_ver3.stepB.attribution import (  # noqa: E402
    compute_annualized_covariance_matrix,
    compute_option_leg_contribution,
    compute_risk_contribution,
    compute_sleeve_correlation_matrix,
    compute_universe_comparison,
    compute_vs_baseline_comparison,
)
from covered_call_mini_ver3.stepB.config import (  # noqa: E402
    REQUIRED_SAMPLE_END,
    REQUIRED_SAMPLE_START,
    StepBPaths,
    default_paths,
    portfolio_definitions,
    universe_definitions,
    weight_schemes,
)
from covered_call_mini_ver3.stepB.io import (  # noqa: E402
    common_sample_panel,
    load_stepB_inputs,
    validate_required_sleeves,
    write_input_manifest,
)
from covered_call_mini_ver3.stepB.metrics import compute_performance_metrics  # noqa: E402
from covered_call_mini_ver3.stepB.plotting import write_figures  # noqa: E402
from covered_call_mini_ver3.stepB.portfolio import (  # noqa: E402
    build_nav_from_returns,
    build_portfolio_returns,
    compute_drawdown_series,
    portfolio_weight_map,
)
from covered_call_mini_ver3.stepB.reporting import write_markdown_report  # noqa: E402
from covered_call_mini_ver3.stepB.validation import build_validation_summary  # noqa: E402


LOGGER = logging.getLogger("ver3_stepB")


def main() -> None:
    parser = argparse.ArgumentParser(description="ver3.0 Step B fixed-weight universe comparison.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Override Step B output directory.")
    parser.add_argument("--strict", action="store_true", help="Raise if any validation check fails.")
    parser.add_argument("--skip-plots", action="store_true", help="Skip PNG figure generation.")
    parser.add_argument("--write-report", action=argparse.BooleanOptionalAction, default=True, help="Write markdown report.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    paths = default_paths(ROOT, args.output_dir)
    result = run_stepB(paths=paths, strict=args.strict, skip_plots=args.skip_plots, write_report=args.write_report)
    _print_terminal_summary(result)


def run_stepB(*, paths: StepBPaths, strict: bool, skip_plots: bool, write_report: bool) -> dict[str, Any]:
    """Run the Step B fixed-weight comparison."""

    paths.ensure_output_dirs()
    portfolios = portfolio_definitions()
    LOGGER.info("Step B output directory: %s", paths.output_root)
    LOGGER.info("Loading Step A and 510050 extension inputs.")
    inputs = load_stepB_inputs(paths)
    write_input_manifest(paths, inputs)

    validate_required_sleeves(inputs.return_panel, portfolios)
    sample_panel = common_sample_panel(inputs.return_panel, portfolios)
    LOGGER.info(
        "Common sample: %s to %s (%d rows).",
        sample_panel["date"].min().date().isoformat(),
        sample_panel["date"].max().date().isoformat(),
        len(sample_panel),
    )

    LOGGER.info("Constructing %d fixed-weight portfolios.", len(portfolios))
    portfolio_returns = build_portfolio_returns(sample_panel, inputs.option_leg_panel, portfolios)
    portfolio_nav = build_nav_from_returns(portfolio_returns)
    drawdown = compute_drawdown_series(portfolio_nav)
    summary = compute_performance_metrics(portfolio_returns, portfolio_nav)
    selected_vs_pure = compute_vs_baseline_comparison(summary)
    universe_comparison = compute_universe_comparison(summary)
    option_contribution = compute_option_leg_contribution(inputs.option_leg_panel[inputs.option_leg_panel["date"].isin(sample_panel["date"])], portfolios)
    correlation = compute_sleeve_correlation_matrix(sample_panel, portfolios)
    covariance = compute_annualized_covariance_matrix(sample_panel, portfolios)
    risk_contribution = compute_risk_contribution(sample_panel, portfolios)
    sample_window = build_sample_window_summary(inputs, sample_panel, summary)

    output_files = write_outputs(
        paths=paths,
        portfolios=portfolios,
        portfolio_returns=portfolio_returns,
        portfolio_nav=portfolio_nav,
        drawdown=drawdown,
        summary=summary,
        selected_vs_pure=selected_vs_pure,
        universe_comparison=universe_comparison,
        option_contribution=option_contribution,
        correlation=correlation,
        covariance=covariance,
        risk_contribution=risk_contribution,
        sample_window=sample_window,
    )
    if not skip_plots:
        LOGGER.info("Writing figures.")
        output_files.extend(write_figures(paths.figure_dir, portfolio_nav, drawdown, summary, correlation, risk_contribution))

    report_path = paths.report_dir / "ver3_0_stepB_fixed_weight_universe_comparison_report.md"
    validation = build_validation_summary(
        portfolios=portfolios,
        portfolio_returns=portfolio_returns,
        portfolio_nav=portfolio_nav,
        summary=summary,
        selected_vs_pure=selected_vs_pure,
        sample_window=sample_window,
        output_files=[p for p in output_files if p.suffix.lower() == ".csv"],
        report_path=report_path,
    )
    if write_report:
        LOGGER.info("Writing markdown report.")
        write_markdown_report(
            report_path,
            summary,
            selected_vs_pure,
            universe_comparison,
            option_contribution,
            risk_contribution,
            sample_window,
            validation,
            inputs.extension_588000_available,
        )
        validation = build_validation_summary(
            portfolios=portfolios,
            portfolio_returns=portfolio_returns,
            portfolio_nav=portfolio_nav,
            summary=summary,
            selected_vs_pure=selected_vs_pure,
            sample_window=sample_window,
            output_files=[p for p in output_files if p.suffix.lower() == ".csv"],
            report_path=report_path,
        )
        write_markdown_report(
            report_path,
            summary,
            selected_vs_pure,
            universe_comparison,
            option_contribution,
            risk_contribution,
            sample_window,
            validation,
            inputs.extension_588000_available,
        )
        output_files.append(report_path)
    validation_path = paths.audit_dir / "ver3_0_stepB_sanity_checks.csv"
    validation.to_csv(validation_path, index=False, encoding="utf-8-sig")
    output_files.append(validation_path)
    write_manifest(paths, output_files, summary, validation, inputs.extension_588000_available)
    if strict and not validation["passed"].astype(bool).all():
        failed = validation.loc[~validation["passed"].astype(bool), "check_name"].tolist()
        raise SystemExit("Step B validation failed:\n" + "\n".join(failed))
    return {
        "paths": paths,
        "summary": summary,
        "selected_vs_pure": selected_vs_pure,
        "universe_comparison": universe_comparison,
        "sample_window": sample_window,
        "validation": validation,
        "output_files": output_files,
    }


def build_sample_window_summary(inputs: Any, sample_panel: pd.DataFrame, summary: pd.DataFrame) -> pd.DataFrame:
    """Build sample window summary."""

    rows = [
        {
            "window_name": "stepB_common_long_sample",
            "sample_start": sample_panel["date"].min().date().isoformat(),
            "sample_end": sample_panel["date"].max().date().isoformat(),
            "n_obs": int(len(sample_panel)),
            "note": "Universe A/B 必需 sleeves 对齐后的共同非缺失样本。",
        },
        {
            "window_name": "requested_main_stepB_sample",
            "sample_start": REQUIRED_SAMPLE_START,
            "sample_end": REQUIRED_SAMPLE_END,
            "n_obs": np.nan,
            "note": "任务指定的长样本窗口；实际样本由可用面板对齐后确认。",
        },
        {
            "window_name": "588000_extension_status",
            "sample_start": "",
            "sample_end": "",
            "n_obs": np.nan,
            "note": "588000 仅作为短样本 extension，可用但不进入 Step B 主线。",
        },
    ]
    actual_start = summary["sample_start"].dropna().unique()
    actual_end = summary["sample_end"].dropna().unique()
    actual_n = summary["n_trading_days"].dropna().unique()
    if len(actual_start) == 1 and len(actual_end) == 1 and len(actual_n) == 1:
        rows.append(
            {
                "window_name": "portfolio_metric_sample",
                "sample_start": str(actual_start[0]),
                "sample_end": str(actual_end[0]),
                "n_obs": int(actual_n[0]),
                "note": "组合 NAV 构建后的指标样本。",
            }
        )
    return pd.DataFrame(rows)


def write_outputs(
    *,
    paths: StepBPaths,
    portfolios: list[Any],
    portfolio_returns: pd.DataFrame,
    portfolio_nav: pd.DataFrame,
    drawdown: pd.DataFrame,
    summary: pd.DataFrame,
    selected_vs_pure: pd.DataFrame,
    universe_comparison: pd.DataFrame,
    option_contribution: pd.DataFrame,
    correlation: pd.DataFrame,
    covariance: pd.DataFrame,
    risk_contribution: pd.DataFrame,
    sample_window: pd.DataFrame,
) -> list[Path]:
    """Write CSV and JSON outputs."""

    files: list[Path] = []
    config_json = paths.config_dir / "ver3_0_stepB_universe_config.json"
    config_json.write_text(json.dumps(stepB_config_payload(), indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    files.append(config_json)

    weight_map = portfolio_weight_map(portfolios)
    files.append(_write_csv(weight_map, paths.config_dir / "ver3_0_stepB_portfolio_weight_map.csv"))
    files.append(_write_csv(portfolio_returns, paths.daily_dir / "ver3_0_stepB_portfolio_daily_returns.csv"))
    files.append(_write_csv(portfolio_nav, paths.daily_dir / "ver3_0_stepB_portfolio_daily_nav.csv"))
    files.append(_write_csv(drawdown, paths.daily_dir / "ver3_0_stepB_portfolio_drawdowns.csv"))
    files.append(_write_csv(summary, paths.summary_dir / "ver3_0_stepB_portfolio_summary.csv"))
    files.append(_write_csv(selected_vs_pure, paths.summary_dir / "ver3_0_stepB_selected_vs_pure_baseline.csv"))
    files.append(_write_csv(universe_comparison, paths.summary_dir / "ver3_0_stepB_universeA_vs_universeB_comparison.csv"))
    files.append(_write_csv(sample_window, paths.summary_dir / "ver3_0_stepB_sample_window_summary.csv"))
    files.append(_write_csv(option_contribution, paths.attribution_dir / "ver3_0_stepB_option_leg_contribution.csv"))
    files.append(_write_csv(correlation, paths.attribution_dir / "ver3_0_stepB_sleeve_correlation_matrix.csv"))
    files.append(_write_csv(covariance, paths.attribution_dir / "ver3_0_stepB_annualized_covariance_matrix.csv"))
    files.append(_write_csv(risk_contribution, paths.attribution_dir / "ver3_0_stepB_risk_contribution.csv"))
    return files


def stepB_config_payload() -> dict[str, Any]:
    """Return JSON-serializable Step B config."""

    universes = universe_definitions()
    schemes = weight_schemes()
    return {
        "experiment_id": "ver3_0_stepB_fixed_weight_universe_comparison",
        "report_language": "zh-CN",
        "sample_policy": {
            "requested_start": REQUIRED_SAMPLE_START,
            "requested_end": REQUIRED_SAMPLE_END,
            "common_sample": "drop rows with missing required sleeve returns after date alignment",
            "exclude_588000_from_main_stepB": True,
        },
        "universes": {
            key: {
                "universe_name": value.universe_name,
                "description": value.description,
                "pure_etf": value.pure_etf.sleeves_by_etf,
                "selected": value.selected.sleeves_by_etf,
            }
            for key, value in universes.items()
        },
        "weight_schemes": {
            universe_key: {
                scheme_name: {
                    "weights_by_etf": scheme.weights_by_etf,
                    "note": scheme.note,
                }
                for scheme_name, scheme in scheme_map.items()
            }
            for universe_key, scheme_map in schemes.items()
        },
        "forbidden_main_stepB_features": [
            "dynamic weights",
            "volatility timing",
            "inverse volatility",
            "minimum variance",
            "risk parity",
            "mean-variance optimization",
            "MDD-constrained Sharpe frontier",
            "Q100 default sleeves",
            "ATM Q100 default sleeves",
            "TP80 default sleeves",
            "Touch-K default sleeves",
        ],
    }


def write_manifest(paths: StepBPaths, output_files: list[Path], summary: pd.DataFrame, validation: pd.DataFrame, extension_588000_available: bool) -> Path:
    """Write manifest JSON."""

    payload = {
        "experiment_id": "ver3_0_stepB_fixed_weight_universe_comparison",
        "status": "complete",
        "runner": "ver3/scripts/python/ver3_0_stepB_fixed_weight_universe_comparison.py",
        "output_root": str(paths.output_root.relative_to(paths.root)),
        "output_files": [str(path.relative_to(paths.root)) for path in output_files if path.exists()],
        "sample_start": str(summary["sample_start"].iloc[0]),
        "sample_end": str(summary["sample_end"].iloc[0]),
        "n_portfolios": int(len(summary)),
        "validation": {
            "passed": int(validation["passed"].sum()),
            "total": int(len(validation)),
        },
        "extension_588000_available_but_excluded": bool(extension_588000_available),
    }
    path = paths.output_root / "manifest.json"
    path.write_text(json.dumps(_clean_json(payload), indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    return path


def _write_csv(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    LOGGER.info("Wrote %s (%d rows).", path.relative_to(ROOT), len(df))
    return path


def _print_terminal_summary(result: dict[str, Any]) -> None:
    summary = result["summary"]
    selected_vs_pure = result["selected_vs_pure"]
    universe = result["universe_comparison"]
    sample = result["sample_window"].iloc[0]
    best_sharpe = summary.sort_values("sharpe_daily_mean", ascending=False).iloc[0]
    lowest_mdd = summary.sort_values("max_drawdown", ascending=True).iloc[0]
    best_improvement = selected_vs_pure.sort_values("delta_sharpe_vs_baseline", ascending=False).iloc[0]
    selected_ab = universe[universe["portfolio_type"].eq("Selected")].copy()
    judgement = selected_ab.sort_values(["delta_sharpe", "delta_mdd"], ascending=[False, True]).iloc[0]
    validation = result["validation"]
    print(f"Step B output directory: {result['paths'].output_root}")
    print(f"Sample: {sample['sample_start']} to {sample['sample_end']} (n_obs={int(sample['n_obs'])})")
    print(f"Constructed portfolios: {len(summary)}")
    print(f"Best Sharpe portfolio: {best_sharpe['portfolio_name']} ({best_sharpe['sharpe_daily_mean']:.3f})")
    print(f"Lowest MDD portfolio: {lowest_mdd['portfolio_name']} ({lowest_mdd['max_drawdown']:.2%})")
    print(f"Best selected-vs-pure Sharpe improvement: {best_improvement['selected_portfolio']} ({best_improvement['delta_sharpe_vs_baseline']:.3f})")
    print(f"Universe A vs B initial judgment: {judgement['left_portfolio']} vs {judgement['right_portfolio']} -> {judgement['interpretation_hint']}")
    print("Recommend Step B+: yes, compare Universe A and B separately under MDD-constrained Sharpe frontier.")
    print(f"Validation: {int(validation['passed'].sum())}/{len(validation)} passed")


def _clean_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _clean_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean_json(v) for v in value]
    if isinstance(value, tuple):
        return [_clean_json(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if pd.isna(value) else float(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


if __name__ == "__main__":
    main()
