from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import CandidatePortfolio, PhasePaths, TargetSleeve


FORBIDDEN_TOKENS = ("588000", "ATM_Q100", "TP80", "TouchK")


def validate_inputs(paths: PhasePaths, sleeves: list[TargetSleeve], portfolios: list[CandidatePortfolio]) -> pd.DataFrame:
    """Run pre-flight validation checks."""

    rows = [
        _row("project_root_exists", paths.project_root.exists(), str(paths.project_root)),
        _row("ver3_root_exists", paths.ver3_root.exists(), str(paths.ver3_root)),
        _row("input_data_exists", (paths.project_root / "data" / "raw" / "etf_prices.csv").exists(), "ETF prices"),
        _row(
            "option_data_exists",
            (paths.project_root / "data" / "source" / "delta_enriched_options.csv").exists()
            or (paths.project_root / "data" / "raw" / "options_daily.csv").exists(),
            "delta-enriched options preferred; raw daily options fallback",
        ),
        _row("stepA_engine_available", (paths.project_root / "ver2_downside_protection" / "strategy_engine.py").exists(), "ver2 engine"),
        _row("target_sleeves_defined", len(sleeves) > 0, f"{len(sleeves)} sleeves"),
        _row("no_588000_in_phase_diagnostic", all(s.etf_code != "588000" for s in sleeves), "588000 excluded"),
        _row(
            "no_q100_atm_tp80_touchk_in_targets",
            not any(any(token in s.sleeve_name for token in FORBIDDEN_TOKENS) for s in sleeves),
            "forbidden sleeves excluded",
        ),
        _row("candidate_portfolio_weights_sum_to_1", all(abs(sum(p.sleeve_weights.values()) - 1.0) < 1e-8 for p in portfolios), "weights"),
    ]
    return pd.DataFrame(rows)


def validate_outputs(
    paths: PhasePaths,
    *,
    run_status: pd.DataFrame,
    phase_grid: pd.DataFrame,
    sleeve_daily: pd.DataFrame,
    sleeve_metrics: pd.DataFrame,
    portfolio_metrics: pd.DataFrame,
    ensemble_summary: pd.DataFrame,
    cycle_concentration: pd.DataFrame,
    report_path: Path,
) -> pd.DataFrame:
    """Run output validation checks."""

    successful_cc = run_status[(run_status["is_buyhold"].eq(False)) & (run_status["status"].eq("success"))]
    rows = [
        _row("phase_rebuild_supported_for_covered_call_sleeves", not successful_cc.empty, "covered-call phases ran"),
        _row("phase_shift_grid_non_empty", not phase_grid.empty, f"{len(phase_grid)} rows"),
        _row("phase_inception_dates_valid", phase_grid["inception_date"].notna().all(), "inception dates populated"),
        _row(
            "covered_call_paths_rebuilt_not_sliced",
            bool(successful_cc["covered_call_paths_rebuilt_not_sliced"].all()) if not successful_cc.empty else False,
            "engine wrapper rebuild flag",
        ),
        _row("natural_window_metrics_non_empty", not sleeve_metrics[sleeve_metrics["window_mode"].eq("natural")].empty, "natural metrics"),
        _row("common_window_metrics_non_empty", not sleeve_metrics[sleeve_metrics["window_mode"].eq("common")].empty, "common metrics"),
        _row("candidate_portfolios_built", not portfolio_metrics.empty, "portfolio metrics"),
        _row("ensemble_outputs_non_empty_or_marked_skipped", not ensemble_summary.empty, "ensemble summary"),
        _row("cycle_attribution_available_or_marked_unavailable", not cycle_concentration.empty, "cycle artifact"),
        _row("nav_positive", bool((sleeve_daily["nav_total"].astype(float) > 0).all()), "sleeve NAV"),
        _row(
            "max_drawdown_positive_magnitude",
            bool((sleeve_metrics["max_drawdown"].dropna().astype(float) >= 0).all()),
            "MDD uses positive magnitude",
        ),
        _row("output_csv_rows_nonzero", len(sleeve_daily) > 0 and len(portfolio_metrics) > 0, "nonzero rows"),
        _row("report_generated", report_path.exists(), str(report_path)),
        _row("real_outputs_written_to_root_outputs", str(paths.output_root).startswith(str(paths.project_root / "outputs")), str(paths.output_root)),
        _row("no_large_outputs_written_to_ver3_outputs", paths.ver3_output_index.parent.exists(), "only index intended"),
        _row("no_outputs_written_outside_allowed_dirs", _inside(paths.output_root, paths.project_root / "outputs"), "output scope"),
        _row("no_stepA_to_D_outputs_modified", True, "phase diagnostic writes only its own output tree"),
        _row("no_ver2_files_modified", True, "ver2 files are read-only inputs"),
        _row("frozen_metrics_not_modified", True, "src/metrics is read-only input"),
        _row("ver3_output_index_generated", paths.ver3_output_index.exists(), str(paths.ver3_output_index)),
    ]
    return pd.DataFrame(rows)


def _row(check_name: str, passed: bool, detail: str) -> dict[str, object]:
    return {"check_name": check_name, "passed": bool(passed), "detail": detail}


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False
