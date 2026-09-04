from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .config import DiagnosticConfig
from .engine_adapter import validate_engine_support
from .implementation_grid import (
    build_effective_delta_implementation_grid,
    build_target_etf_table,
    validate_preregistered_grid,
)
from .io import ensure_output_dirs, write_config_artifacts, write_csv
from .metrics import (
    build_recommendation_diagnostic,
    compute_actual_effective_delta,
    compute_pairwise_implementation_comparison,
    compute_performance_metrics,
)
from .option_attribution import (
    compute_mtm_stress,
    compute_option_leg_attribution,
    compute_premium_payoff_quality,
)
from .phase_lite import run_phase_lite_diagnostic
from .plotting import make_effective_delta_plots
from .reporting import write_markdown_report, write_ver3_output_index
from .sleeve_runner import run_all_implementations
from .validation import build_validation_summary


@dataclass(frozen=True)
class DiagnosticResult:
    output_root: Path
    report_path: Path | None
    index_path: Path
    summary: pd.DataFrame
    recommendation: pd.DataFrame
    validation: pd.DataFrame


def run_effective_delta_equivalence_diagnostic(config: DiagnosticConfig) -> DiagnosticResult:
    """Run the full independent implementation-equivalence diagnostic."""

    ensure_output_dirs(config)
    validate_engine_support(config)

    implementation_grid = build_effective_delta_implementation_grid(config)
    validate_preregistered_grid(implementation_grid, config.target_effective_delta)
    target_etfs = build_target_etf_table(config)
    write_config_artifacts(config, implementation_grid, target_etfs)

    outputs = run_all_implementations(config)
    tracking = compute_actual_effective_delta(outputs.option_selection_detail, config)
    option_attribution = compute_option_leg_attribution(outputs.option_selection_detail)
    quality = compute_premium_payoff_quality(outputs.option_selection_detail, outputs.daily_nav)
    stress = compute_mtm_stress(outputs.raw_daily_mtm)
    summary = compute_performance_metrics(outputs.daily_nav, tracking, quality, stress, config)
    pairwise = compute_pairwise_implementation_comparison(summary)
    phase_metrics, phase_summary = run_phase_lite_diagnostic(config)
    recommendation = build_recommendation_diagnostic(summary, phase_summary)
    figure_paths = make_effective_delta_plots(
        config=config,
        daily_nav=outputs.daily_nav,
        daily_drawdowns=outputs.daily_drawdowns,
        summary=summary,
        quality=quality,
        stress=stress,
        phase_metrics=phase_metrics,
    )

    paths = _write_result_tables(
        config=config,
        outputs=outputs,
        summary=summary,
        tracking=tracking,
        pairwise=pairwise,
        recommendation=recommendation,
        option_attribution=option_attribution,
        quality=quality,
        stress=stress,
        phase_metrics=phase_metrics,
        phase_summary=phase_summary,
    )

    report_path: Path | None = None
    validation = pd.DataFrame()
    if config.write_report:
        report_path = write_markdown_report(
            config=config,
            implementation_grid=implementation_grid,
            summary=summary,
            tracking=tracking,
            quality=quality,
            stress=stress,
            pairwise=pairwise,
            phase_summary=phase_summary,
            recommendation=recommendation,
            validation=pd.DataFrame(),
            figure_paths=figure_paths,
        )

    validation = build_validation_summary(
        config=config,
        implementation_grid=implementation_grid,
        target_etfs=target_etfs,
        run_status=outputs.run_status,
        option_selection_detail=outputs.option_selection_detail,
        daily_returns=outputs.daily_returns,
        daily_nav=outputs.daily_nav,
        summary=summary,
        tracking=tracking,
        option_quality=quality,
        phase_metrics=phase_metrics,
        report_path=report_path,
    )
    validation_path = config.paths.output_root / "summary" / "ver3_0_effective_delta_validation_summary.csv"
    write_csv(validation, validation_path)

    if config.write_report and report_path is not None:
        report_path = write_markdown_report(
            config=config,
            implementation_grid=implementation_grid,
            summary=summary,
            tracking=tracking,
            quality=quality,
            stress=stress,
            pairwise=pairwise,
            phase_summary=phase_summary,
            recommendation=recommendation,
            validation=validation,
            figure_paths=figure_paths,
        )

    index_path = write_ver3_output_index(
        config=config,
        report_path=report_path or paths["summary"],
        summary_path=paths["summary"],
        validation=validation,
        recommendation=recommendation,
    )
    if not validation.empty:
        idx = validation["check_name"].eq("ver3_output_index_generated")
        validation.loc[idx, "passed"] = bool(index_path.exists())
        validation.loc[idx, "detail"] = str(index_path)
        write_csv(validation, validation_path)
        index_path = write_ver3_output_index(
            config=config,
            report_path=report_path or paths["summary"],
            summary_path=paths["summary"],
            validation=validation,
            recommendation=recommendation,
        )
    return DiagnosticResult(
        output_root=config.paths.output_root,
        report_path=report_path,
        index_path=index_path,
        summary=summary,
        recommendation=recommendation,
        validation=validation,
    )


def _write_result_tables(
    *,
    config: DiagnosticConfig,
    outputs,
    summary: pd.DataFrame,
    tracking: pd.DataFrame,
    pairwise: pd.DataFrame,
    recommendation: pd.DataFrame,
    option_attribution: pd.DataFrame,
    quality: pd.DataFrame,
    stress: pd.DataFrame,
    phase_metrics: pd.DataFrame,
    phase_summary: pd.DataFrame,
) -> dict[str, Path]:
    root = config.paths.output_root
    paths = {
        "run_status": write_csv(outputs.run_status, root / "runs" / "ver3_0_effective_delta_run_status.csv"),
        "option_selection": write_csv(outputs.option_selection_detail, root / "runs" / "ver3_0_effective_delta_option_selection_detail.csv"),
        "daily_returns": write_csv(outputs.daily_returns, root / "daily" / "ver3_0_effective_delta_sleeve_daily_returns.csv"),
        "daily_nav": write_csv(outputs.daily_nav, root / "daily" / "ver3_0_effective_delta_sleeve_daily_nav.csv"),
        "daily_drawdowns": write_csv(outputs.daily_drawdowns, root / "daily" / "ver3_0_effective_delta_sleeve_drawdowns.csv"),
        "summary": write_csv(summary, root / "summary" / "ver3_0_effective_delta_implementation_summary.csv"),
        "tracking": write_csv(tracking, root / "summary" / "ver3_0_effective_delta_tracking_summary.csv"),
        "pairwise": write_csv(pairwise, root / "summary" / "ver3_0_effective_delta_pairwise_comparison.csv"),
        "recommendation": write_csv(recommendation, root / "summary" / "ver3_0_effective_delta_recommendation_diagnostic.csv"),
        "option_attribution": write_csv(option_attribution, root / "attribution" / "ver3_0_effective_delta_option_leg_attribution.csv"),
        "quality": write_csv(quality, root / "attribution" / "ver3_0_effective_delta_premium_payoff_quality.csv"),
        "stress": write_csv(stress, root / "attribution" / "ver3_0_effective_delta_mtm_stress.csv"),
        "phase_metrics": write_csv(phase_metrics, root / "phase_lite" / "ver3_0_effective_delta_phase_lite_metrics.csv"),
        "phase_summary": write_csv(phase_summary, root / "phase_lite" / "ver3_0_effective_delta_phase_lite_summary.csv"),
    }
    return paths
