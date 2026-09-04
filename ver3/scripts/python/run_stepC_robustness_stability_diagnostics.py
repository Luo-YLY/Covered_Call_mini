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

from covered_call_mini_ver3.stepC_robustness.attribution import (  # noqa: E402
    compute_option_leg_attribution,
    compute_risk_contribution,
)
from covered_call_mini_ver3.stepC_robustness.candidate import (  # noqa: E402
    candidate_weight_table,
    fixed_baseline_table,
    validate_candidate_sources,
    validate_candidate_weights,
)
from covered_call_mini_ver3.stepC_robustness.config import (  # noqa: E402
    EXPERIMENT_ID,
    TARGET_SAMPLE_END,
    TARGET_SAMPLE_START,
    CostScenario,
    StepCPaths,
    candidate_specs,
    cost_scenarios,
    default_paths,
    fixed_baseline_specs,
    manual_event_windows,
)
from covered_call_mini_ver3.stepC_robustness.cost_sensitivity import evaluate_cost_sensitivity  # noqa: E402
from covered_call_mini_ver3.stepC_robustness.event_windows import (  # noqa: E402
    detect_extreme_event_windows,
    evaluate_event_exclusion,
    evaluate_event_window_performance,
    manual_event_window_table,
)
from covered_call_mini_ver3.stepC_robustness.io import load_stepC_inputs, required_input_files, write_csv  # noqa: E402
from covered_call_mini_ver3.stepC_robustness.metrics import (  # noqa: E402
    compare_candidates_to_baselines,
    compute_metrics_from_returns,
)
from covered_call_mini_ver3.stepC_robustness.plotting import make_stepC_plots  # noqa: E402
from covered_call_mini_ver3.stepC_robustness.portfolio import (  # noqa: E402
    align_candidate_sample,
    build_nav_and_drawdown,
    compute_candidate_daily_returns,
)
from covered_call_mini_ver3.stepC_robustness.reporting import write_markdown_report, write_ver3_output_index  # noqa: E402
from covered_call_mini_ver3.stepC_robustness.rolling import (  # noqa: E402
    compute_calendar_year_metrics,
    compute_half_year_metrics,
    compute_rolling_metrics,
    compute_rolling_stability_summary,
)
from covered_call_mini_ver3.stepC_robustness.stability import (  # noqa: E402
    build_recommended_candidate_table,
    build_stability_scorecard,
)
from covered_call_mini_ver3.stepC_robustness.validation import build_validation_summary  # noqa: E402
from covered_call_mini_ver3.stepC_robustness.weight_bound_sensitivity import evaluate_weight_bound_sensitivity  # noqa: E402


LOGGER = logging.getLogger("ver3_stepC")


def main() -> None:
    parser = argparse.ArgumentParser(description="ver3.0 Step C robustness and stability diagnostics.")
    parser.add_argument("--project-root", type=Path, default=ROOT, help="Project root. Default: current checkout root.")
    parser.add_argument("--ver3-root", type=Path, default=None, help="ver3 root. Default: <project-root>/ver3.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Override Step C output directory.")
    parser.add_argument("--skip-plots", action="store_true", help="Skip PNG figure generation.")
    parser.add_argument("--write-report", action=argparse.BooleanOptionalAction, default=True, help="Write markdown report.")
    parser.add_argument("--strict", action="store_true", help="Raise if validation checks fail.")
    parser.add_argument("--rolling-window-days", type=int, default=252, help="Primary rolling window. 252 and 504 are always written.")
    parser.add_argument("--cost-bps-list", default="0,5,10,20,30", help="Comma-separated extra annualized cost bps.")
    parser.add_argument("--event-mode", choices=["auto", "manual", "auto_and_manual"], default="auto", help="Event window source mode.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    project_root = args.project_root.resolve()
    ver3_root = (args.ver3_root or project_root / "ver3").resolve()
    paths = default_paths(project_root, ver3_root, args.output_dir)
    result = run_stepC(
        paths=paths,
        cost_bps_values=_parse_cost_bps(args.cost_bps_list),
        event_mode=args.event_mode,
        rolling_window_days=args.rolling_window_days,
        skip_plots=args.skip_plots,
        write_report=args.write_report,
        strict=args.strict,
    )
    _print_terminal_summary(result)


def run_stepC(
    *,
    paths: StepCPaths,
    cost_bps_values: list[float],
    event_mode: str,
    rolling_window_days: int,
    skip_plots: bool,
    write_report: bool,
    strict: bool,
) -> dict[str, Any]:
    """Run Step C diagnostics end to end."""

    run_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    paths.ensure_output_dirs()
    candidates = candidate_specs()
    baselines = fixed_baseline_specs()
    costs = cost_scenarios(cost_bps_values)

    LOGGER.info("Project root: %s", paths.project_root)
    LOGGER.info("ver3 root: %s", paths.ver3_root)
    LOGGER.info("Step C output directory: %s", paths.output_root)

    inputs = load_stepC_inputs(paths)
    validate_candidate_sources(candidates, inputs.stepB_plus_frontier_default)
    validate_candidate_weights(candidates)
    sample_panel = align_candidate_sample(inputs.return_panel, candidates)
    candidate_returns = compute_candidate_daily_returns(sample_panel, inputs.option_leg_panel, candidates)
    candidate_nav, candidate_drawdowns = build_nav_and_drawdown(candidate_returns)
    full_summary = compute_metrics_from_returns(candidate_returns, group_cols=["portfolio_name", "source_portfolio_name", "universe_short", "role"])
    baseline_comparison = compare_candidates_to_baselines(full_summary, inputs.stepB_summary)
    sample_summary = _sample_summary(sample_panel, candidate_nav, inputs.input_files)

    event_config = _build_event_config(candidate_returns, event_mode)
    event_exclusion = evaluate_event_exclusion(candidate_returns, event_config)
    event_performance = evaluate_event_window_performance(candidate_returns, event_config)

    calendar_year = compute_calendar_year_metrics(candidate_returns)
    half_year = compute_half_year_metrics(candidate_returns)
    rolling_252 = compute_rolling_metrics(candidate_returns, 252)
    rolling_504 = compute_rolling_metrics(candidate_returns, 504)
    rolling_stability = compute_rolling_stability_summary(rolling_252, rolling_504)

    cost_summary, option_cost_robustness = evaluate_cost_sensitivity(candidate_returns, costs)
    weight_bound, barbell = evaluate_weight_bound_sensitivity(inputs.stepB_plus_frontier_default, inputs.stepB_plus_frontier_relaxed)
    option_attribution = compute_option_leg_attribution(
        inputs.option_leg_panel,
        sample_panel["date"],
        candidates,
        attribution_method=inputs.option_leg_method,
    )
    risk_contribution = compute_risk_contribution(sample_panel, candidates)
    scorecard = build_stability_scorecard(full_summary, event_exclusion, rolling_stability, option_cost_robustness, weight_bound)
    recommended = build_recommended_candidate_table(scorecard, baseline_comparison)

    output_files: list[Path] = []
    output_files.extend(_write_config_outputs(paths, candidates, baselines, costs, event_config, inputs.input_files, event_mode, rolling_window_days))
    output_files.extend(_write_daily_outputs(paths, candidate_returns, candidate_nav, candidate_drawdowns))
    output_files.extend(_write_summary_outputs(paths, full_summary, baseline_comparison, scorecard, recommended))
    output_files.extend(_write_event_outputs(paths, event_config, event_exclusion, event_performance))
    output_files.extend(_write_rolling_outputs(paths, calendar_year, half_year, rolling_252, rolling_504, rolling_stability))
    output_files.extend(_write_cost_outputs(paths, cost_summary, option_cost_robustness))
    output_files.extend(_write_sensitivity_outputs(paths, weight_bound, barbell))
    output_files.extend(_write_attribution_outputs(paths, option_attribution, risk_contribution))

    if not skip_plots:
        LOGGER.info("Writing Step C figures.")
        output_files.extend(make_stepC_plots(paths.figure_dir, candidate_nav, candidate_drawdowns, rolling_252, cost_summary, scorecard))

    report_path = paths.report_dir / "ver3_0_stepC_robustness_stability_diagnostics_report.md"
    validation = build_validation_summary(
        paths=paths,
        inputs_exist=all(path.exists() for path in required_input_files(paths)),
        candidates=candidates,
        sample_panel=sample_panel,
        candidate_nav=candidate_nav,
        drawdowns=candidate_drawdowns,
        rolling_outputs=[calendar_year, half_year, rolling_252, rolling_504, rolling_stability],
        event_outputs=[event_config, event_exclusion, event_performance],
        cost_outputs=[cost_summary, option_cost_robustness],
        output_files=output_files,
        report_path=report_path,
        ver3_index_path=paths.ver3_output_index,
    )
    if write_report:
        write_markdown_report(
            report_path,
            sample_summary=sample_summary,
            candidate_weights=candidate_weight_table(candidates),
            full_summary=full_summary,
            baseline_comparison=baseline_comparison,
            event_exclusion=event_exclusion,
            rolling_stability=rolling_stability,
            cost_summary=cost_summary,
            weight_bound=weight_bound,
            barbell=barbell,
            scorecard=scorecard,
            recommended=recommended,
            validation=validation,
        )
        output_files.append(report_path)

    summary_paths = {
        "全样本汇总": paths.summary_dir / "ver3_0_stepC_candidate_full_sample_summary.csv",
        "稳定性评分": paths.summary_dir / "ver3_0_stepC_stability_scorecard.csv",
        "推荐候选表": paths.summary_dir / "ver3_0_stepC_recommended_candidate_table.csv",
        "成本敏感性": paths.cost_dir / "ver3_0_stepC_cost_sensitivity_summary.csv",
        "权重边界敏感性": paths.sensitivity_dir / "ver3_0_stepC_weight_bound_sensitivity.csv",
    }
    index_conclusion = _index_conclusion(recommended, scorecard)
    write_ver3_output_index(
        paths.ver3_output_index,
        output_root=paths.output_root,
        report_path=report_path,
        summary_paths=summary_paths,
        run_timestamp=run_timestamp,
        sample_text=f"{sample_panel['date'].min().date().isoformat()} 至 {sample_panel['date'].max().date().isoformat()}（{len(sample_panel)} 行）",
        recommended_candidate=str(recommended.iloc[0]["portfolio_name"]) if not recommended.empty else "",
        stability_conclusion=index_conclusion,
        next_stage=_next_stage_text(recommended),
    )
    output_files.append(paths.ver3_output_index)

    validation = build_validation_summary(
        paths=paths,
        inputs_exist=all(path.exists() for path in required_input_files(paths)),
        candidates=candidates,
        sample_panel=sample_panel,
        candidate_nav=candidate_nav,
        drawdowns=candidate_drawdowns,
        rolling_outputs=[calendar_year, half_year, rolling_252, rolling_504, rolling_stability],
        event_outputs=[event_config, event_exclusion, event_performance],
        cost_outputs=[cost_summary, option_cost_robustness],
        output_files=output_files,
        report_path=report_path,
        ver3_index_path=paths.ver3_output_index,
    )
    validation_path = paths.summary_dir / "ver3_0_stepC_validation_summary.csv"
    output_files.append(write_csv(validation, validation_path))
    if write_report:
        write_markdown_report(
            report_path,
            sample_summary=sample_summary,
            candidate_weights=candidate_weight_table(candidates),
            full_summary=full_summary,
            baseline_comparison=baseline_comparison,
            event_exclusion=event_exclusion,
            rolling_stability=rolling_stability,
            cost_summary=cost_summary,
            weight_bound=weight_bound,
            barbell=barbell,
            scorecard=scorecard,
            recommended=recommended,
            validation=validation,
        )
    manifest_path = _write_manifest(paths, run_timestamp, sample_panel, output_files, validation, recommended)
    output_files.append(manifest_path)

    if strict and not validation["passed"].astype(bool).all():
        failed = validation.loc[~validation["passed"].astype(bool), "check_name"].tolist()
        raise SystemExit("Step C validation failed:\n" + "\n".join(failed))

    return {
        "paths": paths,
        "sample_panel": sample_panel,
        "candidate_returns": candidate_returns,
        "candidate_nav": candidate_nav,
        "full_summary": full_summary,
        "rolling_stability": rolling_stability,
        "cost_summary": cost_summary,
        "weight_bound": weight_bound,
        "scorecard": scorecard,
        "recommended": recommended,
        "validation": validation,
        "output_files": output_files,
        "run_timestamp": run_timestamp,
    }


def _build_event_config(candidate_returns: pd.DataFrame, event_mode: str) -> pd.DataFrame:
    auto = detect_extreme_event_windows(candidate_returns, top_n=1)
    auto = auto[auto["event_type"].isin(["auto_downside_return", "auto_upside_return"])].copy()
    manual = manual_event_window_table(manual_event_windows())
    if event_mode == "auto":
        return auto
    if event_mode == "manual":
        return manual
    return pd.concat([manual, auto], ignore_index=True, sort=False)


def _sample_summary(sample_panel: pd.DataFrame, candidate_nav: pd.DataFrame, input_files: list[Path]) -> pd.DataFrame:
    actual_start = sample_panel["date"].min().date().isoformat()
    actual_end = sample_panel["date"].max().date().isoformat()
    return pd.DataFrame(
        [
            {
                "window_name": "stepC_common_long_sample",
                "sample_start": actual_start,
                "sample_end": actual_end,
                "n_obs": int(len(sample_panel)),
                "note": "四个候选组合对齐后的共同非缺失样本。",
            },
            {
                "window_name": "requested_stepC_sample",
                "sample_start": TARGET_SAMPLE_START,
                "sample_end": TARGET_SAMPLE_END,
                "n_obs": "",
                "note": "任务指定的长样本窗口；若与实际不同，报告应以实际共同样本解释。",
            },
            {
                "window_name": "candidate_nav_sample_check",
                "sample_start": pd.to_datetime(candidate_nav["date"]).min().date().isoformat(),
                "sample_end": pd.to_datetime(candidate_nav["date"]).max().date().isoformat(),
                "n_obs": int(candidate_nav.groupby("portfolio_name")["date"].count().min()),
                "note": "每个候选组合 NAV 的最小观察数。",
            },
            {
                "window_name": "input_file_count",
                "sample_start": "",
                "sample_end": "",
                "n_obs": int(len(input_files)),
                "note": "本次 Step C 读取的上游输入文件数量。",
            },
        ]
    )


def _write_config_outputs(
    paths: StepCPaths,
    candidates: list[Any],
    baselines: list[Any],
    costs: list[CostScenario],
    event_config: pd.DataFrame,
    input_files: list[Path],
    event_mode: str,
    rolling_window_days: int,
) -> list[Path]:
    payload = {
        "experiment_id": EXPERIMENT_ID,
        "report_language": "zh-CN",
        "sample_start": TARGET_SAMPLE_START,
        "sample_end": TARGET_SAMPLE_END,
        "event_mode": event_mode,
        "rolling_window_days_arg": rolling_window_days,
        "rolling_windows_written": [252, 504],
        "cost_scenarios": [item.__dict__ for item in costs],
        "candidates": [
            {
                "portfolio_name": item.portfolio_name,
                "source_portfolio_name": item.source_portfolio_name,
                "universe_short": item.universe_short,
                "role": item.role,
                "sleeve_weights": item.sleeve_weights,
            }
            for item in candidates
        ],
        "fixed_baselines": [item.__dict__ for item in baselines],
        "input_files": [str(path.relative_to(paths.project_root)) for path in input_files if path.exists()],
        "forbidden_actions": [
            "不重新运行 Step A",
            "不新增 DTE/delta/moneyness/TP/Touch-K 网格",
            "不引入 588000 主线长样本",
            "不做动态择时或滚动调仓",
        ],
    }
    config_path = paths.config_dir / "ver3_0_stepC_config.json"
    config_path.write_text(json.dumps(_clean_json(payload), indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    return [
        config_path,
        write_csv(candidate_weight_table(candidates), paths.config_dir / "ver3_0_stepC_candidate_weights.csv"),
        write_csv(event_config, paths.config_dir / "ver3_0_stepC_event_window_config.csv"),
        write_csv(pd.DataFrame([item.__dict__ for item in costs]), paths.config_dir / "ver3_0_stepC_cost_scenarios.csv"),
        write_csv(fixed_baseline_table(baselines), paths.config_dir / "ver3_0_stepC_fixed_baseline_config.csv"),
    ]


def _write_daily_outputs(paths: StepCPaths, candidate_returns: pd.DataFrame, candidate_nav: pd.DataFrame, drawdowns: pd.DataFrame) -> list[Path]:
    return [
        write_csv(candidate_returns, paths.daily_dir / "ver3_0_stepC_candidate_daily_returns.csv"),
        write_csv(candidate_nav, paths.daily_dir / "ver3_0_stepC_candidate_daily_nav.csv"),
        write_csv(drawdowns, paths.daily_dir / "ver3_0_stepC_candidate_drawdowns.csv"),
    ]


def _write_summary_outputs(
    paths: StepCPaths,
    full_summary: pd.DataFrame,
    baseline_comparison: pd.DataFrame,
    scorecard: pd.DataFrame,
    recommended: pd.DataFrame,
) -> list[Path]:
    return [
        write_csv(full_summary, paths.summary_dir / "ver3_0_stepC_candidate_full_sample_summary.csv"),
        write_csv(baseline_comparison, paths.summary_dir / "ver3_0_stepC_candidate_vs_fixed_baseline.csv"),
        write_csv(scorecard, paths.summary_dir / "ver3_0_stepC_stability_scorecard.csv"),
        write_csv(recommended, paths.summary_dir / "ver3_0_stepC_recommended_candidate_table.csv"),
    ]


def _write_event_outputs(paths: StepCPaths, event_config: pd.DataFrame, event_exclusion: pd.DataFrame, event_performance: pd.DataFrame) -> list[Path]:
    return [
        write_csv(event_config, paths.events_dir / "ver3_0_stepC_auto_detected_event_windows.csv"),
        write_csv(event_exclusion, paths.events_dir / "ver3_0_stepC_event_exclusion_summary.csv"),
        write_csv(event_performance, paths.events_dir / "ver3_0_stepC_event_window_performance.csv"),
    ]


def _write_rolling_outputs(
    paths: StepCPaths,
    calendar_year: pd.DataFrame,
    half_year: pd.DataFrame,
    rolling_252: pd.DataFrame,
    rolling_504: pd.DataFrame,
    rolling_stability: pd.DataFrame,
) -> list[Path]:
    return [
        write_csv(calendar_year, paths.rolling_dir / "ver3_0_stepC_calendar_year_metrics.csv"),
        write_csv(half_year, paths.rolling_dir / "ver3_0_stepC_half_year_metrics.csv"),
        write_csv(rolling_252, paths.rolling_dir / "ver3_0_stepC_rolling_252d_metrics.csv"),
        write_csv(rolling_504, paths.rolling_dir / "ver3_0_stepC_rolling_504d_metrics.csv"),
        write_csv(rolling_stability, paths.rolling_dir / "ver3_0_stepC_rolling_stability_summary.csv"),
    ]


def _write_cost_outputs(paths: StepCPaths, cost_summary: pd.DataFrame, option_cost_robustness: pd.DataFrame) -> list[Path]:
    return [
        write_csv(cost_summary, paths.cost_dir / "ver3_0_stepC_cost_sensitivity_summary.csv"),
        write_csv(option_cost_robustness, paths.cost_dir / "ver3_0_stepC_option_leg_cost_robustness.csv"),
    ]


def _write_sensitivity_outputs(paths: StepCPaths, weight_bound: pd.DataFrame, barbell: pd.DataFrame) -> list[Path]:
    return [
        write_csv(weight_bound, paths.sensitivity_dir / "ver3_0_stepC_weight_bound_sensitivity.csv"),
        write_csv(barbell, paths.sensitivity_dir / "ver3_0_stepC_barbell_diagnostic.csv"),
    ]


def _write_attribution_outputs(paths: StepCPaths, option_attribution: pd.DataFrame, risk_contribution: pd.DataFrame) -> list[Path]:
    return [
        write_csv(option_attribution, paths.attribution_dir / "ver3_0_stepC_option_leg_contribution.csv"),
        write_csv(risk_contribution, paths.attribution_dir / "ver3_0_stepC_risk_contribution.csv"),
    ]


def _write_manifest(
    paths: StepCPaths,
    run_timestamp: str,
    sample_panel: pd.DataFrame,
    output_files: list[Path],
    validation: pd.DataFrame,
    recommended: pd.DataFrame,
) -> Path:
    payload = {
        "experiment_id": EXPERIMENT_ID,
        "report_language": "zh-CN",
        "run_timestamp": run_timestamp,
        "output_root": str(paths.output_root.relative_to(paths.project_root)),
        "sample_start": sample_panel["date"].min().date().isoformat(),
        "sample_end": sample_panel["date"].max().date().isoformat(),
        "n_obs": int(len(sample_panel)),
        "recommended_candidate": recommended.iloc[0]["portfolio_name"] if not recommended.empty else "",
        "output_files": [str(path.relative_to(paths.project_root)) for path in output_files if path.exists() and _is_relative_to(path, paths.project_root)],
        "validation": {"passed": int(validation["passed"].sum()), "total": int(len(validation))},
    }
    path = paths.output_root / "manifest.json"
    path.write_text(json.dumps(_clean_json(payload), indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    return path


def _index_conclusion(recommended: pd.DataFrame, scorecard: pd.DataFrame) -> str:
    if recommended.empty:
        return "未形成推荐候选。"
    row = recommended.iloc[0]
    return f"{row['portfolio_name']} 为主候选，稳定性标签为 {row['overall_stability_label']}。"


def _next_stage_text(recommended: pd.DataFrame) -> str:
    if recommended.empty:
        return "否，需先补齐诊断。"
    label = str(recommended.iloc[0]["overall_stability_label"])
    if label in {"High Stability", "Medium Stability"}:
        return "可选进入 Step D，但应定位为动态权重研究层，不重新打开期权参数网格。"
    return "暂不建议进入 Step D，先完善风险解释。"


def _print_terminal_summary(result: dict[str, Any]) -> None:
    paths: StepCPaths = result["paths"]
    sample = result["sample_panel"]
    full = result["full_summary"]
    recommended = result["recommended"]
    scorecard = result["scorecard"]
    validation = result["validation"]
    print(f"project root: {paths.project_root}")
    print(f"ver3 root: {paths.ver3_root}")
    print(f"Step C real output dir: {paths.output_root}")
    print(f"ver3 lightweight index: {paths.ver3_output_index}")
    print(f"sample: {sample['date'].min().date().isoformat()} to {sample['date'].max().date().isoformat()} (n_obs={len(sample)})")
    print("candidate full-sample metrics:")
    for _, row in full.sort_values("portfolio_name").iterrows():
        print(
            f"  {row['portfolio_name']}: Sharpe={float(row['sharpe_daily_mean']):.3f}, "
            f"MDD={float(row['max_drawdown']):.2%}, CAGR={float(row['annualized_return_cagr']):.2%}"
        )
    best_roll = result["rolling_stability"][result["rolling_stability"]["window_days"].eq(252)].sort_values("ranking_stability_score", ascending=False).iloc[0]
    cost_best = result["cost_summary"].groupby("portfolio_name")["option_leg_still_positive"].mean().sort_values(ascending=False).index[0]
    print(f"rolling stability 初步结论: 252d ranking stability 较强的是 {best_roll['portfolio_name']} ({float(best_roll['ranking_stability_score']):.2%})")
    print(f"cost sensitivity 初步结论: option-leg positive rate 较好的候选包括 {cost_best}")
    print("weight-bound sensitivity 初步结论: relaxed D25/D30 会把中间资产压到 0，default 最小权重有解释约束价值。")
    print(f"推荐主候选: {recommended.iloc[0]['portfolio_name'] if not recommended.empty else ''}")
    print("推荐对照候选: B_default_D22, A_default_D25")
    print(f"是否建议进入下一阶段: {_next_stage_text(recommended)}")
    print(f"validation: {int(validation['passed'].sum())}/{len(validation)} passed")


def _parse_cost_bps(text: str) -> list[float]:
    return [float(item.strip()) for item in text.split(",") if item.strip()]


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


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    main()
