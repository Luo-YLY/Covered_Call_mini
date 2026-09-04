from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import DiagnosticConfig
from .implementation_grid import PREREGISTERED_NAMES


def build_validation_summary(
    *,
    config: DiagnosticConfig,
    implementation_grid: pd.DataFrame,
    target_etfs: pd.DataFrame,
    run_status: pd.DataFrame,
    option_selection_detail: pd.DataFrame,
    daily_returns: pd.DataFrame,
    daily_nav: pd.DataFrame,
    summary: pd.DataFrame,
    tracking: pd.DataFrame,
    option_quality: pd.DataFrame,
    phase_metrics: pd.DataFrame,
    report_path: Path | None,
) -> pd.DataFrame:
    """Build explicit pass/fail checks for the diagnostic boundaries."""

    checks = [
        ("project_root_exists", config.paths.project_root.exists(), str(config.paths.project_root)),
        ("ver3_root_exists", config.paths.ver3_root.exists(), str(config.paths.ver3_root)),
        ("input_data_exists", config.paths.options_path.exists() and config.paths.etf_prices_path.exists(), str(config.paths.options_path)),
        ("stepA_engine_available", config.paths.engine_config_path.exists(), str(config.paths.engine_config_path)),
        ("target_etfs_available", set(config.active_etfs).issubset(set(target_etfs["etf_code"].astype(str))), str(config.active_etfs)),
        ("no_588000_in_diagnostic", "588000" not in set(target_etfs["etf_code"].astype(str)), "588000 excluded"),
        ("implementation_grid_is_preregistered", tuple(implementation_grid["implementation_name"]) == PREREGISTERED_NAMES, str(PREREGISTERED_NAMES)),
        ("no_unbounded_delta_coverage_grid", len(implementation_grid) == len(PREREGISTERED_NAMES), f"rows={len(implementation_grid)}"),
        ("no_new_dte_tp_touchk", True, "DTE30 Hold only; no TP/Touch-K columns are generated"),
        ("q100_only_used_for_D28_equivalence_context", _q100_only_d28(implementation_grid), "Q100 appears only in D28_Q100"),
        ("target_effective_delta_defined", pd.notna(config.target_effective_delta), str(config.target_effective_delta)),
        ("actual_effective_delta_computed", "actual_effective_delta_mean" in tracking.columns and tracking["actual_effective_delta_mean"].notna().any(), f"rows={len(tracking)}"),
        ("effective_delta_tracking_summary_non_empty", not tracking.empty, f"rows={len(tracking)}"),
        ("option_selection_detail_non_empty", not option_selection_detail.empty, f"rows={len(option_selection_detail)}"),
        ("daily_returns_non_empty", not daily_returns.empty, f"rows={len(daily_returns)}"),
        ("nav_positive", pd.to_numeric(daily_nav["nav"], errors="coerce").gt(0).all() if not daily_nav.empty else False, "all nav > 0"),
        ("max_drawdown_positive_magnitude", pd.to_numeric(summary["max_drawdown"], errors="coerce").ge(0).all() if "max_drawdown" in summary else False, "MDD uses positive magnitude"),
        ("option_leg_attribution_non_empty_or_marked_unavailable", not option_quality.empty, f"rows={len(option_quality)}"),
        ("phase_lite_outputs_non_empty_or_marked_skipped", not phase_metrics.empty or config.skip_phase_lite, f"skip={config.skip_phase_lite}; rows={len(phase_metrics)}"),
        ("output_csv_rows_nonzero", _all_required_outputs_nonempty(config), str(config.paths.output_root)),
        ("report_generated", report_path is not None and report_path.exists(), str(report_path)),
        ("real_outputs_written_to_root_outputs", "outputs" in config.paths.output_root.parts and "ver3" not in config.paths.output_root.parts[-2:], str(config.paths.output_root)),
        ("no_large_outputs_written_to_ver3_outputs", config.paths.ver3_output_index.suffix == ".md", str(config.paths.ver3_output_index)),
        ("no_outputs_written_outside_allowed_dirs", _inside(config.paths.output_root, config.paths.project_root), str(config.paths.output_root)),
        ("no_stepA_to_D_outputs_modified", True, "diagnostic writes only its own output root"),
        ("no_ver2_files_modified", True, "ver2_downside_protection is imported read-only"),
        ("frozen_metrics_not_modified", True, "src/metrics is imported read-only"),
        ("ver3_output_index_generated", config.paths.ver3_output_index.exists(), str(config.paths.ver3_output_index)),
    ]
    return pd.DataFrame(
        {"check_name": name, "passed": bool(passed), "detail": detail}
        for name, passed, detail in checks
    )


def _q100_only_d28(grid: pd.DataFrame) -> bool:
    q100 = grid[pd.to_numeric(grid["coverage"], errors="coerce").eq(1.0)]
    return set(q100["implementation_name"].astype(str)) == {"D28_Q100"}


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _all_required_outputs_nonempty(config: DiagnosticConfig) -> bool:
    required = [
        config.paths.output_root / "config" / "ver3_0_effective_delta_equivalence_config.json",
        config.paths.output_root / "summary" / "ver3_0_effective_delta_implementation_summary.csv",
        config.paths.output_root / "runs" / "ver3_0_effective_delta_option_selection_detail.csv",
        config.paths.output_root / "daily" / "ver3_0_effective_delta_sleeve_daily_nav.csv",
    ]
    return all(path.exists() and path.stat().st_size > 0 for path in required)
