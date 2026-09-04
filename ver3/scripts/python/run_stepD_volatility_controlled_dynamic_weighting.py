from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime
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

from covered_call_mini_ver3.stepD_dynamic_weighting.attribution import (  # noqa: E402
    compute_option_leg_attribution,
    compute_risk_contribution,
)
from covered_call_mini_ver3.stepD_dynamic_weighting.config import (  # noqa: E402
    EXPERIMENT_ID,
    REBALANCE_FREQUENCY,
    TURNOVER_METHOD,
    WEIGHT_LOWER_BOUND,
    WEIGHT_UPPER_BOUND,
    StepDPaths,
    default_paths,
    method_specs,
    parse_cost_bps,
    parse_lookbacks,
    parse_methods,
    static_baseline_specs,
    universe_specs,
)
from covered_call_mini_ver3.stepD_dynamic_weighting.io import (  # noqa: E402
    load_static_baseline_daily,
    load_stepD_inputs,
    required_input_files,
    write_csv,
)
from covered_call_mini_ver3.stepD_dynamic_weighting.metrics import (  # noqa: E402
    build_static_baseline_config_table,
    compare_dynamic_to_static_baselines,
    compare_universe_A_vs_B,
    compute_dynamic_summary,
)
from covered_call_mini_ver3.stepD_dynamic_weighting.plotting import (  # noqa: E402
    build_static_nav_and_drawdown,
    make_stepD_plots,
)
from covered_call_mini_ver3.stepD_dynamic_weighting.portfolio import (  # noqa: E402
    build_nav_and_drawdown,
    compute_dynamic_daily_returns,
)
from covered_call_mini_ver3.stepD_dynamic_weighting.rebalance import expand_rebalance_weights_to_daily  # noqa: E402
from covered_call_mini_ver3.stepD_dynamic_weighting.reporting import (  # noqa: E402
    write_markdown_report,
    write_ver3_output_index,
)
from covered_call_mini_ver3.stepD_dynamic_weighting.signals import (  # noqa: E402
    build_monthly_rebalance_schedule,
    compute_rolling_signal_tables,
)
from covered_call_mini_ver3.stepD_dynamic_weighting.turnover import (  # noqa: E402
    compute_rebalance_turnover,
    evaluate_rebalance_cost_sensitivity,
)
from covered_call_mini_ver3.stepD_dynamic_weighting.universe import (  # noqa: E402
    build_universe_data,
    sample_summary_table,
    universe_config_table,
)
from covered_call_mini_ver3.stepD_dynamic_weighting.validation import build_validation_summary  # noqa: E402
from covered_call_mini_ver3.stepD_dynamic_weighting.weights import (  # noqa: E402
    compute_rebalance_weights,
    weight_bound_hits,
)


LOGGER = logging.getLogger("ver3_stepD")


def main() -> None:
    parser = argparse.ArgumentParser(description="ver3.0 Step D volatility-controlled dynamic sleeve weighting.")
    parser.add_argument("--project-root", type=Path, default=ROOT, help="Project root. Default: current checkout root.")
    parser.add_argument("--ver3-root", type=Path, default=None, help="ver3 root. Default: <project-root>/ver3.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Override Step D output directory.")
    parser.add_argument("--lookbacks", default="126,252", help="Comma-separated lookbacks. Supported: 126,252.")
    parser.add_argument(
        "--rebalance-frequency",
        choices=["monthly"],
        default=REBALANCE_FREQUENCY,
        help="Rebalance frequency. Step D only supports monthly.",
    )
    parser.add_argument(
        "--methods",
        default="anchored_inverse_vol,pure_inverse_vol,rolling_min_variance",
        help="Comma-separated methods.",
    )
    parser.add_argument("--cost-bps-list", default="0,5,10,20", help="Comma-separated rebalance cost bps values.")
    parser.add_argument("--skip-plots", action="store_true", help="Skip PNG figure generation.")
    parser.add_argument("--write-report", action=argparse.BooleanOptionalAction, default=True, help="Write markdown report.")
    parser.add_argument("--strict", action="store_true", help="Raise if validation checks fail.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    project_root = args.project_root.resolve()
    ver3_root = (args.ver3_root or project_root / "ver3").resolve()
    paths = default_paths(project_root, ver3_root, args.output_dir)
    result = run_stepD(
        paths=paths,
        lookbacks=parse_lookbacks(args.lookbacks),
        method_names=parse_methods(args.methods),
        rebalance_frequency=args.rebalance_frequency,
        cost_bps_values=parse_cost_bps(args.cost_bps_list),
        skip_plots=args.skip_plots,
        write_report=args.write_report,
        strict=args.strict,
    )
    _print_terminal_summary(result)


def run_stepD(
    *,
    paths: StepDPaths,
    lookbacks: list[int],
    method_names: list[str],
    rebalance_frequency: str,
    cost_bps_values: list[float],
    skip_plots: bool,
    write_report: bool,
    strict: bool,
) -> dict[str, Any]:
    """Run Step D dynamic weighting end to end."""

    if rebalance_frequency != "monthly":
        raise ValueError("Step D only supports monthly rebalance frequency.")

    run_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    paths.ensure_output_dirs()
    universe_map = universe_specs()
    universes = [universe_map["A"], universe_map["B"]]
    methods = method_specs(method_names)
    baselines = static_baseline_specs()
    baseline_config = build_static_baseline_config_table(baselines)

    LOGGER.info("Project root: %s", paths.project_root)
    LOGGER.info("ver3 root: %s", paths.ver3_root)
    LOGGER.info("Step D output directory: %s", paths.output_root)

    inputs = load_stepD_inputs(paths)
    datas = [build_universe_data(inputs.return_panel, inputs.option_leg_panel, universe) for universe in universes]
    sample_summary = sample_summary_table(datas)
    universe_config = universe_config_table(universes)
    method_config = _method_config_table(methods, lookbacks, cost_bps_values)

    signal_frames: list[pd.DataFrame] = []
    cov_frames: list[pd.DataFrame] = []
    rebalance_frames: list[pd.DataFrame] = []
    weight_path_frames: list[pd.DataFrame] = []
    daily_return_frames: list[pd.DataFrame] = []

    for data in datas:
        LOGGER.info("Building dynamic weights for Universe %s.", data.universe.universe_short)
        for lookback in lookbacks:
            schedule = build_monthly_rebalance_schedule(data.returns["date"], lookback)
            vol_signals, cov_summary = compute_rolling_signal_tables(data, schedule)
            signal_frames.append(vol_signals)
            cov_frames.append(cov_summary)
            for method in methods:
                rebalance_weights = compute_rebalance_weights(data, schedule, method)
                daily_weights = expand_rebalance_weights_to_daily(data, rebalance_weights)
                daily_returns = compute_dynamic_daily_returns(data, daily_weights)
                rebalance_frames.append(rebalance_weights)
                weight_path_frames.append(daily_weights)
                daily_return_frames.append(daily_returns)

    rolling_volatility_signals = pd.concat(signal_frames, ignore_index=True, sort=False)
    rolling_covariance_summary = pd.concat(cov_frames, ignore_index=True, sort=False)
    rebalance_weights = pd.concat(rebalance_frames, ignore_index=True, sort=False)
    daily_weight_paths = pd.concat(weight_path_frames, ignore_index=True, sort=False)
    dynamic_daily_returns = pd.concat(daily_return_frames, ignore_index=True, sort=False)
    dynamic_nav, dynamic_drawdowns = build_nav_and_drawdown(dynamic_daily_returns)
    dynamic_summary = compute_dynamic_summary(dynamic_daily_returns)

    static_daily = load_static_baseline_daily(inputs, baseline_config["portfolio_name"].tolist())
    static_nav, static_drawdowns = build_static_nav_and_drawdown(static_daily)
    static_comparison = compare_dynamic_to_static_baselines(dynamic_daily_returns, dynamic_summary, static_daily, baseline_config)
    universe_comparison = compare_universe_A_vs_B(dynamic_summary)

    turnover_detail, turnover_summary = compute_rebalance_turnover(rebalance_weights, universe_map)
    _cost_daily, cost_summary = evaluate_rebalance_cost_sensitivity(dynamic_daily_returns, turnover_detail, cost_bps_values)
    option_attribution = compute_option_leg_attribution(dynamic_daily_returns)
    risk_contribution = compute_risk_contribution(datas, daily_weight_paths)
    bound_hits = weight_bound_hits(rebalance_weights)
    recommendation = _build_recommendation_table(dynamic_summary, turnover_summary, static_comparison)

    output_files: list[Path] = []
    output_files.extend(
        _write_config_outputs(
            paths,
            lookbacks=lookbacks,
            method_names=method_names,
            cost_bps_values=cost_bps_values,
            inputs=inputs,
            universe_config=universe_config,
            method_config=method_config,
            baseline_config=baseline_config,
        )
    )
    output_files.extend(
        [
            write_csv(rolling_volatility_signals, paths.signals_dir / "ver3_0_stepD_rolling_volatility_signals.csv"),
            write_csv(rolling_covariance_summary, paths.signals_dir / "ver3_0_stepD_rolling_covariance_summary.csv"),
            write_csv(daily_weight_paths, paths.weights_dir / "ver3_0_stepD_dynamic_weight_paths.csv"),
            write_csv(rebalance_weights, paths.weights_dir / "ver3_0_stepD_rebalance_weights.csv"),
            write_csv(bound_hits, paths.weights_dir / "ver3_0_stepD_weight_bound_hits.csv"),
            write_csv(dynamic_daily_returns, paths.daily_dir / "ver3_0_stepD_dynamic_strategy_daily_returns.csv"),
            write_csv(dynamic_nav, paths.daily_dir / "ver3_0_stepD_dynamic_strategy_daily_nav.csv"),
            write_csv(dynamic_drawdowns, paths.daily_dir / "ver3_0_stepD_dynamic_strategy_drawdowns.csv"),
            write_csv(dynamic_summary, paths.summary_dir / "ver3_0_stepD_dynamic_strategy_summary.csv"),
            write_csv(static_comparison, paths.summary_dir / "ver3_0_stepD_comparison_vs_static_baselines.csv"),
            write_csv(universe_comparison, paths.summary_dir / "ver3_0_stepD_universeA_vs_universeB_dynamic_comparison.csv"),
            write_csv(recommendation, paths.summary_dir / "ver3_0_stepD_recommendation_table.csv"),
            write_csv(turnover_summary, paths.turnover_dir / "ver3_0_stepD_turnover_summary.csv"),
            write_csv(turnover_detail, paths.turnover_dir / "ver3_0_stepD_rebalance_turnover_detail.csv"),
            write_csv(cost_summary, paths.cost_dir / "ver3_0_stepD_rebalance_cost_sensitivity.csv"),
            write_csv(option_attribution, paths.attribution_dir / "ver3_0_stepD_option_leg_contribution.csv"),
            write_csv(risk_contribution, paths.attribution_dir / "ver3_0_stepD_risk_contribution.csv"),
        ]
    )

    if not skip_plots:
        LOGGER.info("Writing Step D figures.")
        output_files.extend(
            make_stepD_plots(
                paths.figure_dir,
                dynamic_nav=dynamic_nav,
                dynamic_drawdowns=dynamic_drawdowns,
                static_nav=static_nav,
                static_drawdowns=static_drawdowns,
                daily_weight_paths=daily_weight_paths,
                turnover_summary=turnover_summary,
                cost_summary=cost_summary,
                dynamic_summary=dynamic_summary,
            )
        )

    report_path = paths.report_dir / "ver3_0_stepD_volatility_controlled_dynamic_weighting_report.md"
    placeholder_validation = pd.DataFrame([{"check_name": "validation_pending", "passed": True, "note": "Final validation is written after report and index generation."}])
    if write_report:
        write_markdown_report(
            report_path,
            sample_summary=sample_summary,
            universe_config=universe_config,
            method_config=method_config,
            dynamic_summary=dynamic_summary,
            static_comparison=static_comparison,
            universe_comparison=universe_comparison,
            turnover_summary=turnover_summary,
            cost_summary=cost_summary,
            recommendation=recommendation,
            option_attribution=option_attribution,
            risk_contribution=risk_contribution,
            validation=placeholder_validation,
        )
        output_files.append(report_path)
    write_ver3_output_index(
        paths.ver3_output_index,
        output_root=paths.output_root,
        report_path=report_path,
        run_timestamp=run_timestamp,
        recommendation=recommendation,
        validation=placeholder_validation,
        key_paths=_key_paths(paths),
    )
    output_files.append(paths.ver3_output_index)

    validation = build_validation_summary(
        paths=paths,
        inputs_exist=all(path.exists() for path in required_input_files(paths)),
        universes=universes,
        lookbacks=lookbacks,
        methods=method_names,
        sample_summary=sample_summary,
        rebalance_weights=rebalance_weights,
        daily_weight_paths=daily_weight_paths,
        dynamic_daily_returns=dynamic_daily_returns,
        dynamic_nav=dynamic_nav,
        drawdowns=dynamic_drawdowns,
        turnover_detail=turnover_detail,
        cost_summary=cost_summary,
        static_comparison=static_comparison,
        output_files=output_files,
        report_path=report_path,
        ver3_index_path=paths.ver3_output_index,
    )
    validation_path = paths.summary_dir / "ver3_0_stepD_validation_summary.csv"
    output_files.append(write_csv(validation, validation_path))
    validation = build_validation_summary(
        paths=paths,
        inputs_exist=all(path.exists() for path in required_input_files(paths)),
        universes=universes,
        lookbacks=lookbacks,
        methods=method_names,
        sample_summary=sample_summary,
        rebalance_weights=rebalance_weights,
        daily_weight_paths=daily_weight_paths,
        dynamic_daily_returns=dynamic_daily_returns,
        dynamic_nav=dynamic_nav,
        drawdowns=dynamic_drawdowns,
        turnover_detail=turnover_detail,
        cost_summary=cost_summary,
        static_comparison=static_comparison,
        output_files=output_files,
        report_path=report_path,
        ver3_index_path=paths.ver3_output_index,
    )
    write_csv(validation, validation_path)

    if write_report:
        write_markdown_report(
            report_path,
            sample_summary=sample_summary,
            universe_config=universe_config,
            method_config=method_config,
            dynamic_summary=dynamic_summary,
            static_comparison=static_comparison,
            universe_comparison=universe_comparison,
            turnover_summary=turnover_summary,
            cost_summary=cost_summary,
            recommendation=recommendation,
            option_attribution=option_attribution,
            risk_contribution=risk_contribution,
            validation=validation,
        )
    write_ver3_output_index(
        paths.ver3_output_index,
        output_root=paths.output_root,
        report_path=report_path,
        run_timestamp=run_timestamp,
        recommendation=recommendation,
        validation=validation,
        key_paths=_key_paths(paths),
    )
    manifest_path = _write_manifest(paths, run_timestamp, output_files, validation, recommendation, sample_summary)
    output_files.append(manifest_path)

    if strict and not validation["passed"].astype(bool).all():
        failed = validation.loc[~validation["passed"].astype(bool), "check_name"].tolist()
        raise SystemExit("Step D validation failed:\n" + "\n".join(failed))

    return {
        "paths": paths,
        "sample_summary": sample_summary,
        "dynamic_daily_returns": dynamic_daily_returns,
        "dynamic_summary": dynamic_summary,
        "static_comparison": static_comparison,
        "turnover_summary": turnover_summary,
        "cost_summary": cost_summary,
        "recommendation": recommendation,
        "validation": validation,
        "output_files": output_files,
        "run_timestamp": run_timestamp,
    }


def _write_config_outputs(
    paths: StepDPaths,
    *,
    lookbacks: list[int],
    method_names: list[str],
    cost_bps_values: list[float],
    inputs: Any,
    universe_config: pd.DataFrame,
    method_config: pd.DataFrame,
    baseline_config: pd.DataFrame,
) -> list[Path]:
    payload = {
        "experiment_id": EXPERIMENT_ID,
        "report_language": "zh-CN",
        "sample_start": "2022-09-30",
        "sample_end": "2026-05-27",
        "effective_sample_note": "Each dynamic strategy starts after its lookback and first monthly effective rebalance date.",
        "lookbacks": lookbacks,
        "rebalance_frequency": "monthly",
        "methods": method_names,
        "weight_bounds": {"lower": WEIGHT_LOWER_BOUND, "upper": WEIGHT_UPPER_BOUND},
        "turnover_method": TURNOVER_METHOD,
        "rebalance_cost_bps_values": cost_bps_values,
        "option_leg_method": inputs.option_leg_method,
        "input_files": [str(path.relative_to(paths.project_root)) for path in inputs.input_files if path.exists()],
        "forbidden_actions": [
            "do not change option DTE/delta/moneyness/TP/Touch-K parameters",
            "do not dynamically change q or call coverage",
            "do not use volatility to decide whether to sell calls",
            "do not use expected-return forecasts",
            "do not include 588000 in the main long sample",
        ],
    }
    config_path = paths.config_dir / "ver3_0_stepD_config.json"
    config_path.write_text(json.dumps(_clean_json(payload), indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    return [
        config_path,
        write_csv(universe_config, paths.config_dir / "ver3_0_stepD_universe_config.csv"),
        write_csv(method_config, paths.config_dir / "ver3_0_stepD_method_config.csv"),
        write_csv(baseline_config, paths.config_dir / "ver3_0_stepD_static_baseline_config.csv"),
    ]


def _method_config_table(methods: list[Any], lookbacks: list[int], cost_bps_values: list[float]) -> pd.DataFrame:
    rows = []
    for method in methods:
        rows.append(
            {
                "method": method.method_name,
                "method_label": method.method_label,
                "description": method.description,
                "lookbacks": ",".join(str(item) for item in lookbacks),
                "rebalance_frequency": "monthly",
                "lower_bound": WEIGHT_LOWER_BOUND,
                "upper_bound": WEIGHT_UPPER_BOUND,
                "cost_bps_values": ",".join(str(int(item)) if float(item).is_integer() else str(item) for item in cost_bps_values),
                "uses_expected_returns": False,
                "changes_option_parameters": False,
            }
        )
    return pd.DataFrame(rows)


def _build_recommendation_table(
    dynamic_summary: pd.DataFrame,
    turnover_summary: pd.DataFrame,
    static_comparison: pd.DataFrame,
) -> pd.DataFrame:
    matched = {"A": "A_Selected_50_30_20", "B": "B_default_D20"}
    rows = []
    turnover = turnover_summary[["strategy_name", "avg_rebalance_turnover", "annualized_turnover_approx"]]
    for _, row in dynamic_summary.merge(turnover, on="strategy_name", how="left").iterrows():
        baseline_name = matched[str(row["universe_short"])]
        comp = static_comparison[
            static_comparison["strategy_name"].eq(row["strategy_name"])
            & static_comparison["baseline_portfolio_name"].eq(baseline_name)
        ]
        if comp.empty:
            delta_sharpe = np.nan
            delta_cagr = np.nan
            delta_mdd = np.nan
        else:
            first = comp.iloc[0]
            delta_sharpe = float(first["delta_sharpe_vs_baseline"])
            delta_cagr = float(first["delta_cagr_vs_baseline"])
            delta_mdd = float(first["delta_mdd_vs_baseline"])
        avg_turnover = float(row["avg_rebalance_turnover"]) if not pd.isna(row["avg_rebalance_turnover"]) else 0.0
        score = float(row["sharpe_daily_mean"]) + (0.5 * delta_sharpe if not pd.isna(delta_sharpe) else 0.0) - 0.75 * float(row["max_drawdown"]) - 0.15 * avg_turnover
        rows.append(
            {
                "strategy_name": row["strategy_name"],
                "universe_short": row["universe_short"],
                "method": row["method"],
                "lookback": int(row["lookback"]),
                "matched_static_baseline": baseline_name,
                "annualized_return_cagr": row["annualized_return_cagr"],
                "sharpe_daily_mean": row["sharpe_daily_mean"],
                "max_drawdown": row["max_drawdown"],
                "final_nav": row["final_nav"],
                "avg_rebalance_turnover": avg_turnover,
                "annualized_turnover_approx": row["annualized_turnover_approx"],
                "delta_sharpe_vs_matched_baseline": delta_sharpe,
                "delta_cagr_vs_matched_baseline": delta_cagr,
                "delta_mdd_vs_matched_baseline": delta_mdd,
                "recommendation_score": score,
                "research_note": _recommendation_note(row["method"], delta_sharpe, delta_mdd, avg_turnover),
            }
        )
    return pd.DataFrame(rows).sort_values("recommendation_score", ascending=False).reset_index(drop=True)


def _recommendation_note(method: str, delta_sharpe: float, delta_mdd: float, avg_turnover: float) -> str:
    if method == "anchored_inverse_vol" and delta_sharpe > 0 and delta_mdd <= 0:
        return "closest_to_current_static_research_line"
    if avg_turnover > 0.15:
        return "higher_turnover_requires_cost_and_execution_review"
    if delta_sharpe > 0:
        return "dynamic_weighting_has_sample_improvement_but_needs_robustness_review"
    return "keep_static_baseline_as_primary_interpretation"


def _key_paths(paths: StepDPaths) -> dict[str, Path]:
    return {
        "动态策略汇总": paths.summary_dir / "ver3_0_stepD_dynamic_strategy_summary.csv",
        "静态基准比较": paths.summary_dir / "ver3_0_stepD_comparison_vs_static_baselines.csv",
        "推荐观察表": paths.summary_dir / "ver3_0_stepD_recommendation_table.csv",
        "权重路径": paths.weights_dir / "ver3_0_stepD_dynamic_weight_paths.csv",
        "换手汇总": paths.turnover_dir / "ver3_0_stepD_turnover_summary.csv",
        "成本敏感性": paths.cost_dir / "ver3_0_stepD_rebalance_cost_sensitivity.csv",
    }


def _write_manifest(
    paths: StepDPaths,
    run_timestamp: str,
    output_files: list[Path],
    validation: pd.DataFrame,
    recommendation: pd.DataFrame,
    sample_summary: pd.DataFrame,
) -> Path:
    payload = {
        "experiment_id": EXPERIMENT_ID,
        "report_language": "zh-CN",
        "run_timestamp": run_timestamp,
        "output_root": str(paths.output_root.relative_to(paths.project_root)),
        "sample_summary": sample_summary.to_dict(orient="records"),
        "top_research_candidate": recommendation.iloc[0]["strategy_name"] if not recommendation.empty else "",
        "output_files": [
            str(path.relative_to(paths.project_root))
            for path in output_files
            if path.exists() and _is_relative_to(path.resolve(), paths.project_root.resolve())
        ],
        "validation": {"passed": int(validation["passed"].sum()), "total": int(len(validation))},
    }
    path = paths.output_root / "manifest.json"
    path.write_text(json.dumps(_clean_json(payload), indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    return path


def _print_terminal_summary(result: dict[str, Any]) -> None:
    paths: StepDPaths = result["paths"]
    summary = result["dynamic_summary"].sort_values("sharpe_daily_mean", ascending=False)
    recommendation = result["recommendation"]
    validation = result["validation"]
    print(f"project root: {paths.project_root}")
    print(f"ver3 root: {paths.ver3_root}")
    print(f"Step D real output dir: {paths.output_root}")
    print(f"ver3 lightweight index: {paths.ver3_output_index}")
    print("top dynamic strategies by Sharpe:")
    for _, row in summary.head(5).iterrows():
        print(
            f"  {row['strategy_name']}: Sharpe={float(row['sharpe_daily_mean']):.3f}, "
            f"MDD={float(row['max_drawdown']):.2%}, CAGR={float(row['annualized_return_cagr']):.2%}, "
            f"sample={row['sample_start']} to {row['sample_end']}"
        )
    if not recommendation.empty:
        top = recommendation.iloc[0]
        print(
            "research ranking top: "
            f"{top['strategy_name']} vs {top['matched_static_baseline']} "
            f"(delta Sharpe={float(top['delta_sharpe_vs_matched_baseline']):.3f}, "
            f"delta MDD={float(top['delta_mdd_vs_matched_baseline']):.2%})"
        )
    print(f"validation: {int(validation['passed'].sum())}/{len(validation)} passed")


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
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    main()
