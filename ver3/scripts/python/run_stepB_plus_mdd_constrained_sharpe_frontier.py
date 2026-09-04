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
VER3_ROOT = ROOT / "ver3"
VER3_SRC = VER3_ROOT / "src"
for item in (ROOT, VER3_SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from covered_call_mini_ver3.stepB_plus.attribution import (  # noqa: E402
    compute_annualized_covariance_matrix,
    compute_option_leg_attribution,
    compute_risk_contribution,
    compute_sleeve_correlation_matrix,
)
from covered_call_mini_ver3.stepB_plus.config import (  # noqa: E402
    D_STAR_LIST,
    EXPERIMENT_ID,
    TARGET_SAMPLE_END,
    TARGET_SAMPLE_START,
    ConstraintSpec,
    StepBPlusPaths,
    UniverseSpec,
    constraint_specs,
    default_paths,
    forbidden_main_tokens,
    sleeve_key,
    universe_specs,
)
from covered_call_mini_ver3.stepB_plus.io import (  # noqa: E402
    load_stepB_plus_inputs,
    merge_required_sleeve_returns,
    required_input_files,
)
from covered_call_mini_ver3.stepB_plus.optimizer import (  # noqa: E402
    best_weight_long,
    evaluate_universe_grid,
    select_best_by_drawdown_target,
)
from covered_call_mini_ver3.stepB_plus.plotting import write_figures  # noqa: E402
from covered_call_mini_ver3.stepB_plus.portfolio import (  # noqa: E402
    build_nav_series,
    compute_drawdown_series,
    compute_portfolio_returns,
)
from covered_call_mini_ver3.stepB_plus.reporting import write_markdown_report, write_ver3_output_index  # noqa: E402
from covered_call_mini_ver3.stepB_plus.validation import build_validation_summary  # noqa: E402


LOGGER = logging.getLogger("ver3_stepB_plus")


def main() -> None:
    parser = argparse.ArgumentParser(description="ver3.0 Step B+ MDD-constrained Sharpe frontier.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Override root outputs directory.")
    parser.add_argument("--grid-step", type=float, default=0.01, help="Static weight grid step. Default: 0.01.")
    parser.add_argument("--constraint-set", default="both", help="default, relaxed, or both.")
    parser.add_argument("--strict", action="store_true", help="Raise if any validation check fails.")
    parser.add_argument("--skip-plots", action="store_true", help="Skip PNG figure generation.")
    parser.add_argument("--write-report", action=argparse.BooleanOptionalAction, default=True, help="Write markdown report.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    paths = default_paths(ROOT, VER3_ROOT, args.output_dir)
    result = run_stepB_plus(
        paths=paths,
        grid_step=args.grid_step,
        constraint_set=args.constraint_set,
        strict=args.strict,
        skip_plots=args.skip_plots,
        write_report=args.write_report,
    )
    _print_terminal_summary(result)


def run_stepB_plus(
    *,
    paths: StepBPlusPaths,
    grid_step: float,
    constraint_set: str,
    strict: bool,
    skip_plots: bool,
    write_report: bool,
) -> dict[str, Any]:
    """Run Step B+ end to end."""

    paths.ensure_output_dirs()
    universes = universe_specs()
    constraints = constraint_specs(constraint_set)
    LOGGER.info("Project root: %s", paths.project_root)
    LOGGER.info("ver3 root: %s", paths.ver3_root)
    LOGGER.info("Step B+ output directory: %s", paths.output_root)

    inputs = load_stepB_plus_inputs(paths)
    sample_panel = merge_required_sleeve_returns(
        inputs.return_panel,
        universes,
        sample_start=TARGET_SAMPLE_START,
        sample_end=TARGET_SAMPLE_END,
    )
    LOGGER.info(
        "Common sample: %s to %s (%d rows).",
        sample_panel["date"].min().date().isoformat(),
        sample_panel["date"].max().date().isoformat(),
        len(sample_panel),
    )

    output_files: list[Path] = []
    output_files.extend(_write_config_outputs(paths, universes, constraints, grid_step, inputs.input_files))

    grid_frames = []
    for constraint in constraints:
        for universe in universes.values():
            LOGGER.info("Evaluating universe %s, constraint %s.", universe.universe_short, constraint.name)
            grid_frames.append(
                evaluate_universe_grid(
                    sample_panel,
                    inputs.option_leg_panel,
                    universe,
                    constraint,
                    grid_step=grid_step,
                )
            )
    grid_results = pd.concat(grid_frames, ignore_index=True, sort=False)
    best_rows = select_best_by_drawdown_target(grid_results, d_star_list=D_STAR_LIST)
    best_weights = best_weight_long(best_rows)
    daily_returns, daily_nav, drawdowns = _build_best_daily_paths(best_rows, universes, sample_panel, inputs.option_leg_panel)

    baseline_comparison = _compare_vs_fixed_weight_baselines(best_rows, inputs.baseline_summary)
    universe_comparison = _compare_universe_frontiers(best_rows)
    sample_window = _build_sample_window_summary(sample_panel, inputs.input_files, grid_results, best_rows)
    option_attribution = compute_option_leg_attribution(
        best_rows,
        universes,
        sample_panel,
        inputs.option_leg_panel,
        attribution_method=inputs.option_leg_method,
    )
    correlation = compute_sleeve_correlation_matrix(sample_panel, universes)
    covariance = compute_annualized_covariance_matrix(sample_panel, universes)
    risk_contribution = compute_risk_contribution(best_rows, universes, sample_panel)

    output_files.extend(_write_main_outputs(paths, grid_results, best_rows, best_weights, daily_returns, daily_nav, drawdowns))
    output_files.extend(
        _write_summary_outputs(paths, best_rows, baseline_comparison, universe_comparison, sample_window)
    )
    output_files.extend(_write_attribution_outputs(paths, option_attribution, correlation, covariance, risk_contribution))
    if not skip_plots:
        LOGGER.info("Writing figures.")
        output_files.extend(write_figures(paths.figure_dir, grid_results, best_weights, daily_nav, drawdowns, risk_contribution))

    report_path = paths.report_dir / "ver3_0_stepB_plus_mdd_constrained_sharpe_frontier_report.md"
    summary_paths = {
        "default 前沿汇总": paths.summary_dir / "ver3_0_stepB_plus_frontier_summary_default.csv",
        "relaxed 前沿汇总": paths.summary_dir / "ver3_0_stepB_plus_frontier_summary_relaxed.csv",
        "各 D-star 最优权重": paths.summary_dir / "ver3_0_stepB_plus_best_weights_by_drawdown_target.csv",
        "固定权重基准对比": paths.summary_dir / "ver3_0_stepB_plus_comparison_vs_fixed_weight_baselines.csv",
    }
    validation = build_validation_summary(
        paths=paths,
        inputs_exist=all(path.exists() for path in required_input_files(paths)),
        sample_panel=sample_panel,
        universes=universes,
        grid_results=grid_results,
        best_rows=best_rows,
        best_daily_nav=daily_nav,
        best_drawdowns=drawdowns,
        output_files=output_files,
        report_path=report_path,
        ver3_index_path=paths.ver3_output_index,
    )
    if write_report:
        write_markdown_report(
            report_path,
            config_summary=_config_summary_payload(grid_step, constraints),
            sample_window=sample_window,
            frontier_default=_frontier_for(best_rows, "default"),
            frontier_relaxed=_frontier_for(best_rows, "relaxed"),
            best_weights=best_weights,
            baseline_comparison=baseline_comparison,
            universe_comparison=universe_comparison,
            option_attribution=option_attribution,
            risk_contribution=risk_contribution,
            validation=validation,
        )
        output_files.append(report_path)

    conclusion = _frontier_conclusion(best_rows)
    write_ver3_output_index(
        paths.ver3_output_index,
        output_root=paths.output_root,
        report_path=report_path,
        summary_paths=summary_paths,
        sample_text=f"{sample_panel['date'].min().date().isoformat()} 至 {sample_panel['date'].max().date().isoformat()}（{len(sample_panel)} 行）",
        conclusion_text=conclusion,
    )
    output_files.append(paths.ver3_output_index)

    validation = build_validation_summary(
        paths=paths,
        inputs_exist=all(path.exists() for path in required_input_files(paths)),
        sample_panel=sample_panel,
        universes=universes,
        grid_results=grid_results,
        best_rows=best_rows,
        best_daily_nav=daily_nav,
        best_drawdowns=drawdowns,
        output_files=output_files,
        report_path=report_path,
        ver3_index_path=paths.ver3_output_index,
    )
    validation_path = paths.summary_dir / "ver3_0_stepB_plus_validation_summary.csv"
    output_files.append(_write_csv(validation, validation_path))
    if write_report:
        write_markdown_report(
            report_path,
            config_summary=_config_summary_payload(grid_step, constraints),
            sample_window=sample_window,
            frontier_default=_frontier_for(best_rows, "default"),
            frontier_relaxed=_frontier_for(best_rows, "relaxed"),
            best_weights=best_weights,
            baseline_comparison=baseline_comparison,
            universe_comparison=universe_comparison,
            option_attribution=option_attribution,
            risk_contribution=risk_contribution,
            validation=validation,
        )
    manifest_path = _write_manifest(paths, grid_step, constraints, sample_panel, best_rows, output_files, validation)
    output_files.append(manifest_path)

    if strict and not validation["passed"].astype(bool).all():
        failed = validation.loc[~validation["passed"].astype(bool), "check_name"].tolist()
        raise SystemExit("Step B+ validation failed:\n" + "\n".join(failed))
    return {
        "paths": paths,
        "universes": universes,
        "constraints": constraints,
        "sample_panel": sample_panel,
        "grid_results": grid_results,
        "best_rows": best_rows,
        "best_weights": best_weights,
        "baseline_comparison": baseline_comparison,
        "universe_comparison": universe_comparison,
        "sample_window": sample_window,
        "validation": validation,
        "output_files": output_files,
        "conclusion": conclusion,
        "grid_step": grid_step,
    }


def _write_config_outputs(
    paths: StepBPlusPaths,
    universes: dict[str, UniverseSpec],
    constraints: list[ConstraintSpec],
    grid_step: float,
    input_files: list[Path],
) -> list[Path]:
    payload = {
        **_config_summary_payload(grid_step, constraints),
        "sample_policy": {
            "target_start": TARGET_SAMPLE_START,
            "target_end": TARGET_SAMPLE_END,
            "common_sample": "drop rows with missing required sleeve returns after A/B alignment",
            "exclude_588000_from_main_frontier": True,
        },
        "universes": {
            key: {
                "universe_name": spec.universe_name,
                "description": spec.description,
                "sleeves_by_etf": spec.sleeves_by_etf,
            }
            for key, spec in universes.items()
        },
        "input_files": [str(path.relative_to(paths.project_root)) for path in input_files if path.exists()],
        "forbidden_main_tokens": list(forbidden_main_tokens()),
        "runner": "ver3/scripts/python/run_stepB_plus_mdd_constrained_sharpe_frontier.py",
    }
    files = []
    config_path = paths.config_dir / "ver3_0_stepB_plus_config.json"
    config_path.write_text(json.dumps(_clean_json(payload), indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    files.append(config_path)

    universe_rows = []
    for universe in universes.values():
        for etf, sleeve in universe.sleeves_by_etf.items():
            universe_rows.append(
                {
                    "universe_short": universe.universe_short,
                    "universe_name": universe.universe_name,
                    "etf_code": etf,
                    "sleeve_name": sleeve,
                    "sleeve_key": sleeve_key(etf, sleeve),
                    "description": universe.description,
                }
            )
    files.append(_write_csv(pd.DataFrame(universe_rows), paths.config_dir / "ver3_0_stepB_plus_universe_config.csv"))

    grid_rows = []
    for constraint in constraints:
        for d_star in D_STAR_LIST:
            grid_rows.append(
                {
                    "constraint_set": constraint.name,
                    "lower_bound": constraint.lower_bound,
                    "upper_bound": constraint.upper_bound,
                    "grid_step": grid_step,
                    "D_star": d_star,
                    "objective": "max sharpe_daily_mean subject to max_drawdown <= D_star",
                }
            )
    files.append(_write_csv(pd.DataFrame(grid_rows), paths.config_dir / "ver3_0_stepB_plus_grid_config.csv"))
    return files


def _write_main_outputs(
    paths: StepBPlusPaths,
    grid_results: pd.DataFrame,
    best_rows: pd.DataFrame,
    best_weights: pd.DataFrame,
    daily_returns: pd.DataFrame,
    daily_nav: pd.DataFrame,
    drawdowns: pd.DataFrame,
) -> list[Path]:
    return [
        _write_csv(_grid_for(grid_results, "default"), paths.grid_dir / "ver3_0_stepB_plus_all_grid_results_default.csv"),
        _write_csv(_grid_for(grid_results, "relaxed"), paths.grid_dir / "ver3_0_stepB_plus_all_grid_results_relaxed.csv"),
        _write_csv(daily_returns, paths.daily_dir / "ver3_0_stepB_plus_best_portfolio_daily_returns.csv"),
        _write_csv(daily_nav, paths.daily_dir / "ver3_0_stepB_plus_best_portfolio_daily_nav.csv"),
        _write_csv(drawdowns, paths.daily_dir / "ver3_0_stepB_plus_best_portfolio_drawdowns.csv"),
        _write_csv(best_weights, paths.summary_dir / "ver3_0_stepB_plus_best_weights_by_drawdown_target.csv"),
    ]


def _write_summary_outputs(
    paths: StepBPlusPaths,
    best_rows: pd.DataFrame,
    baseline_comparison: pd.DataFrame,
    universe_comparison: pd.DataFrame,
    sample_window: pd.DataFrame,
) -> list[Path]:
    return [
        _write_csv(_frontier_for(best_rows, "default"), paths.summary_dir / "ver3_0_stepB_plus_frontier_summary_default.csv"),
        _write_csv(_frontier_for(best_rows, "relaxed"), paths.summary_dir / "ver3_0_stepB_plus_frontier_summary_relaxed.csv"),
        _write_csv(baseline_comparison, paths.summary_dir / "ver3_0_stepB_plus_comparison_vs_fixed_weight_baselines.csv"),
        _write_csv(universe_comparison, paths.summary_dir / "ver3_0_stepB_plus_universeA_vs_universeB_frontier_comparison.csv"),
        _write_csv(sample_window, paths.summary_dir / "ver3_0_stepB_plus_sample_window_summary.csv"),
    ]


def _write_attribution_outputs(
    paths: StepBPlusPaths,
    option_attribution: pd.DataFrame,
    correlation: pd.DataFrame,
    covariance: pd.DataFrame,
    risk_contribution: pd.DataFrame,
) -> list[Path]:
    return [
        _write_csv(option_attribution, paths.attribution_dir / "ver3_0_stepB_plus_option_leg_contribution.csv"),
        _write_csv(correlation, paths.attribution_dir / "ver3_0_stepB_plus_sleeve_correlation_matrix.csv"),
        _write_csv(covariance, paths.attribution_dir / "ver3_0_stepB_plus_annualized_covariance_matrix.csv"),
        _write_csv(risk_contribution, paths.attribution_dir / "ver3_0_stepB_plus_risk_contribution.csv"),
    ]


def _build_best_daily_paths(
    best_rows: pd.DataFrame,
    universes: dict[str, UniverseSpec],
    sample_panel: pd.DataFrame,
    option_leg_panel: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return_frames = []
    nav_frames = []
    drawdown_frames = []
    feasible = best_rows[best_rows["feasible"].astype(bool)].copy()
    for _, row in feasible.iterrows():
        universe = universes[str(row["universe_short"])]
        weights = {etf: float(row[f"weight_{etf}"]) for etf in universe.etf_codes}
        returns = compute_portfolio_returns(sample_panel, universe, weights, option_leg_panel)
        nav = build_nav_series(returns)
        drawdown = compute_drawdown_series(nav)
        meta = {
            "portfolio_name": row["portfolio_name"],
            "universe_short": row["universe_short"],
            "universe_name": row["universe_name"],
            "constraint_set": row["constraint_set"],
            "D_star": row["D_star"],
            "frontier_status": row["frontier_status"],
        }
        for frame in [returns, nav, drawdown]:
            for key, value in meta.items():
                frame[key] = value
        return_frames.append(
            returns[
                [
                    "date",
                    "portfolio_name",
                    "universe_short",
                    "constraint_set",
                    "D_star",
                    "portfolio_daily_return",
                    "portfolio_option_leg_return",
                ]
            ]
        )
        nav_frames.append(
            nav[
                [
                    "date",
                    "portfolio_name",
                    "universe_short",
                    "constraint_set",
                    "D_star",
                    "nav",
                    "initial_nav",
                ]
            ]
        )
        drawdown_frames.append(
            drawdown[
                [
                    "date",
                    "portfolio_name",
                    "universe_short",
                    "constraint_set",
                    "D_star",
                    "drawdown",
                    "drawdown_magnitude",
                    "rolling_peak_nav",
                ]
            ]
        )
    return (
        pd.concat(return_frames, ignore_index=True, sort=False),
        pd.concat(nav_frames, ignore_index=True, sort=False),
        pd.concat(drawdown_frames, ignore_index=True, sort=False),
    )


def _compare_vs_fixed_weight_baselines(best_rows: pd.DataFrame, baseline_summary: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    selected = baseline_summary[baseline_summary["portfolio_type"].eq("Selected")].copy()
    for _, row in best_rows[best_rows["feasible"].astype(bool)].iterrows():
        matches = selected[selected["universe_short"].eq(row["universe_short"])].copy()
        if matches.empty:
            continue
        baseline = matches.sort_values(["sharpe_daily_mean", "max_drawdown"], ascending=[False, True]).iloc[0]
        rows.append(
            {
                "portfolio_name": row["portfolio_name"],
                "universe_short": row["universe_short"],
                "constraint_set": row["constraint_set"],
                "D_star": row["D_star"],
                "matched_fixed_weight_baseline": baseline["portfolio_name"],
                "matched_fixed_weight_scheme": baseline["weight_scheme"],
                "annualized_return_cagr": row["annualized_return_cagr"],
                "sharpe_daily_mean": row["sharpe_daily_mean"],
                "max_drawdown": row["max_drawdown"],
                "baseline_cagr": baseline["annualized_return_cagr"],
                "baseline_sharpe": baseline["sharpe_daily_mean"],
                "baseline_mdd": baseline["max_drawdown"],
                "delta_cagr_vs_fixed_baseline": float(row["annualized_return_cagr"]) - float(baseline["annualized_return_cagr"]),
                "delta_sharpe_vs_fixed_baseline": float(row["sharpe_daily_mean"]) - float(baseline["sharpe_daily_mean"]),
                "delta_mdd_vs_fixed_baseline": float(row["max_drawdown"]) - float(baseline["max_drawdown"]),
            }
        )
    return pd.DataFrame(rows)


def _compare_universe_frontiers(best_rows: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (constraint, d_star), group in best_rows.groupby(["constraint_set", "D_star"], sort=True):
        a = group[group["universe_short"].eq("A")]
        b = group[group["universe_short"].eq("B")]
        if a.empty or b.empty:
            continue
        arow = a.iloc[0]
        brow = b.iloc[0]
        row = {
            "constraint_set": constraint,
            "D_star": d_star,
            "universe_A_status": arow["frontier_status"],
            "universe_B_status": brow["frontier_status"],
            "universe_A_portfolio": arow["portfolio_name"],
            "universe_B_portfolio": brow["portfolio_name"],
        }
        if bool(arow["feasible"]) and bool(brow["feasible"]):
            delta_sharpe = float(brow["sharpe_daily_mean"]) - float(arow["sharpe_daily_mean"])
            delta_mdd = float(brow["max_drawdown"]) - float(arow["max_drawdown"])
            row.update(
                {
                    "A_sharpe": arow["sharpe_daily_mean"],
                    "B_sharpe": brow["sharpe_daily_mean"],
                    "delta_sharpe_B_minus_A": delta_sharpe,
                    "A_mdd": arow["max_drawdown"],
                    "B_mdd": brow["max_drawdown"],
                    "delta_mdd_B_minus_A": delta_mdd,
                    "A_cagr": arow["annualized_return_cagr"],
                    "B_cagr": brow["annualized_return_cagr"],
                    "delta_cagr_B_minus_A": float(brow["annualized_return_cagr"]) - float(arow["annualized_return_cagr"]),
                    "interpretation_hint": _ab_hint(delta_sharpe, delta_mdd),
                }
            )
        else:
            row.update(
                {
                    "A_sharpe": np.nan,
                    "B_sharpe": np.nan,
                    "delta_sharpe_B_minus_A": np.nan,
                    "A_mdd": np.nan,
                    "B_mdd": np.nan,
                    "delta_mdd_B_minus_A": np.nan,
                    "A_cagr": np.nan,
                    "B_cagr": np.nan,
                    "delta_cagr_B_minus_A": np.nan,
                    "interpretation_hint": "该 D-star 下至少一个 universe 不可行",
                }
            )
        rows.append(row)
    return pd.DataFrame(rows)


def _build_sample_window_summary(
    sample_panel: pd.DataFrame,
    input_files: list[Path],
    grid_results: pd.DataFrame,
    best_rows: pd.DataFrame,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "window_name": "stepB_plus_common_long_sample",
                "sample_start": sample_panel["date"].min().date().isoformat(),
                "sample_end": sample_panel["date"].max().date().isoformat(),
                "n_obs": int(len(sample_panel)),
                "note": "Universe A/B 所有必需 sleeves 对齐后的共同非缺失样本。",
            },
            {
                "window_name": "requested_main_stepB_plus_sample",
                "sample_start": TARGET_SAMPLE_START,
                "sample_end": TARGET_SAMPLE_END,
                "n_obs": np.nan,
                "note": "任务指定的长样本窗口；实际可用样本以上方对齐后的日期为准。",
            },
            {
                "window_name": "input_file_count",
                "sample_start": "",
                "sample_end": "",
                "n_obs": int(len(input_files)),
                "note": "使用 Step A、510050 extension 和 Step B 固定权重基准作为输入。",
            },
            {
                "window_name": "grid_and_frontier_count",
                "sample_start": "",
                "sample_end": "",
                "n_obs": int(len(grid_results)),
                "note": f"各 D-star 和约束组下共有 {int(best_rows['feasible'].sum())} 条可行前沿行。",
            },
        ]
    )


def _write_manifest(
    paths: StepBPlusPaths,
    grid_step: float,
    constraints: list[ConstraintSpec],
    sample_panel: pd.DataFrame,
    best_rows: pd.DataFrame,
    output_files: list[Path],
    validation: pd.DataFrame,
) -> Path:
    payload = {
        "experiment_id": EXPERIMENT_ID,
        "status": "complete",
        "runner": "ver3/scripts/python/run_stepB_plus_mdd_constrained_sharpe_frontier.py",
        "output_root": str(paths.output_root.relative_to(paths.project_root)),
        "grid_step": grid_step,
        "constraint_sets": [item.name for item in constraints],
        "sample_start": sample_panel["date"].min().date().isoformat(),
        "sample_end": sample_panel["date"].max().date().isoformat(),
        "n_grid_rows": int(len(best_rows)),
        "n_feasible_frontier_rows": int(best_rows["feasible"].sum()),
        "output_files": [str(path.relative_to(paths.project_root)) for path in output_files if path.exists() and path.is_relative_to(paths.project_root)],
        "validation": {"passed": int(validation["passed"].sum()), "total": int(len(validation))},
    }
    path = paths.output_root / "manifest.json"
    path.write_text(json.dumps(_clean_json(payload), indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    return path


def _config_summary_payload(grid_step: float, constraints: list[ConstraintSpec]) -> dict[str, object]:
    return {
        "experiment_id": EXPERIMENT_ID,
        "grid_step": float(grid_step),
        "report_language": "zh-CN",
        "d_star_list": list(D_STAR_LIST),
        "constraint_sets": [
            {
                "name": item.name,
                "lower_bound": item.lower_bound,
                "upper_bound": item.upper_bound,
                "is_primary": item.is_primary,
            }
            for item in constraints
        ],
        "objective": "在 max_drawdown <= D_star、权重和为 1、long-only 边界内最大化 sharpe_daily_mean",
    }


def _write_csv(df: pd.DataFrame, path: Path) -> Path:
    if df.empty:
        raise ValueError(f"Refusing to write empty Step B+ CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    LOGGER.info("Wrote %s (%d rows).", path.relative_to(ROOT), len(df))
    return path


def _grid_for(grid_results: pd.DataFrame, constraint_set: str) -> pd.DataFrame:
    out = grid_results[grid_results["constraint_set"].eq(constraint_set)].copy()
    if out.empty:
        return pd.DataFrame({"constraint_set": [constraint_set], "note": ["本次运行未选择该约束组"]})
    return out


def _frontier_for(best_rows: pd.DataFrame, constraint_set: str) -> pd.DataFrame:
    cols = [
        "portfolio_name",
        "universe_short",
        "constraint_set",
        "D_star",
        "frontier_status",
        "feasible",
        "feasible_candidate_count",
        "sharpe_daily_mean",
        "annualized_return_cagr",
        "annualized_volatility",
        "max_drawdown",
        "calmar_ratio",
        "sortino_ratio",
        "option_leg_annualized_pnl_contribution",
        "final_nav",
        "weight_510300",
        "weight_510500",
        "weight_510050",
        "weight_159915",
        "note",
    ]
    out = best_rows[best_rows["constraint_set"].eq(constraint_set)].copy()
    if out.empty:
        return pd.DataFrame({"constraint_set": [constraint_set], "frontier_status": ["not_selected"]})
    for col in cols:
        if col not in out.columns:
            out[col] = np.nan
    return out[cols]


def _ab_hint(delta_sharpe: float, delta_mdd: float) -> str:
    if delta_sharpe > 0 and delta_mdd <= 0:
        return "该样本内网格点中，Universe B 的 Sharpe 更高且 MDD 不高于 Universe A。"
    if delta_sharpe > 0:
        return "Universe B 的 Sharpe 更高，但需要接受更高 MDD。"
    if delta_mdd < 0:
        return "Universe B 降低 MDD，但牺牲 Sharpe。"
    return "该网格点上 Universe A 的 Sharpe 更强。"


def _frontier_conclusion(best_rows: pd.DataFrame) -> str:
    feasible = best_rows[best_rows["feasible"].astype(bool)].copy()
    if feasible.empty:
        return "在当前 D-star 目标下没有找到可行前沿点。"
    default = feasible[feasible["constraint_set"].eq("default")].copy()
    focus = default if not default.empty else feasible
    best = focus.sort_values(["sharpe_daily_mean", "max_drawdown"], ascending=[False, True]).iloc[0]
    return (
        f"{best['portfolio_name']} 是当前{'default' if not default.empty else '可用'}约束下 Sharpe 最高的网格点"
        f"（Sharpe {float(best['sharpe_daily_mean']):.3f}，MDD {float(best['max_drawdown']):.2%}）。"
    )


def _print_terminal_summary(result: dict[str, Any]) -> None:
    paths: StepBPlusPaths = result["paths"]
    best_rows: pd.DataFrame = result["best_rows"]
    universe_comparison: pd.DataFrame = result["universe_comparison"]
    validation: pd.DataFrame = result["validation"]
    sample_panel: pd.DataFrame = result["sample_panel"]

    print(f"Project root: {paths.project_root}")
    print(f"ver3 root: {paths.ver3_root}")
    print(f"Real output dir: {paths.output_root}")
    print(f"ver3 output index: {paths.ver3_output_index}")
    print(f"Sample: {sample_panel['date'].min().date().isoformat()} to {sample_panel['date'].max().date().isoformat()} (n={len(sample_panel)})")
    print(f"Grid step: {result['grid_step']}")
    print("Constraint sets: " + ", ".join(item.name for item in result["constraints"]))
    print("Best rows by D_star:")
    for _, row in best_rows.sort_values(["constraint_set", "D_star", "universe_short"]).iterrows():
        if bool(row["feasible"]):
            weights = _weight_text(row)
            print(
                f"  {row['constraint_set']} {row['universe_short']} D*={float(row['D_star']):.0%}: "
                f"Sharpe={float(row['sharpe_daily_mean']):.3f}, MDD={float(row['max_drawdown']):.2%}, {weights}"
            )
        else:
            print(f"  {row['constraint_set']} {row['universe_short']} D*={float(row['D_star']):.0%}: infeasible")
    infeasible = best_rows[~best_rows["feasible"].astype(bool)]
    print(f"Infeasible targets: {len(infeasible)}")
    if not universe_comparison.empty:
        default_comp = universe_comparison[universe_comparison["constraint_set"].eq("default")]
        if not default_comp.empty:
            row = default_comp.sort_values("D_star").iloc[0]
            print(f"A vs B first default judgment: {row['interpretation_hint']}")
    print(f"Step C recommendation: {result['conclusion']} Then run robustness checks before treating it as stable.")
    print(f"Validation: {int(validation['passed'].sum())}/{len(validation)} passed")


def _weight_text(row: pd.Series) -> str:
    parts = []
    for col in [
        c
        for c in row.index
        if str(c).startswith("weight_") and c not in {"weight_sum", "weight_vector_key"} and pd.notna(row[c])
    ]:
        parts.append(f"{col.removeprefix('weight_')}={float(row[col]):.0%}")
    return "weights " + ", ".join(parts)


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
