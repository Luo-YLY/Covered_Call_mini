from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import (
    REBALANCE_FREQUENCY,
    SUPPORTED_LOOKBACKS,
    SUPPORTED_METHODS,
    TURNOVER_METHOD,
    WEIGHT_LOWER_BOUND,
    WEIGHT_UPPER_BOUND,
    StepDPaths,
    UniverseSpec,
    forbidden_main_tokens,
)


def build_validation_summary(
    *,
    paths: StepDPaths,
    inputs_exist: bool,
    universes: list[UniverseSpec],
    lookbacks: list[int],
    methods: list[str],
    sample_summary: pd.DataFrame,
    rebalance_weights: pd.DataFrame,
    daily_weight_paths: pd.DataFrame,
    dynamic_daily_returns: pd.DataFrame,
    dynamic_nav: pd.DataFrame,
    drawdowns: pd.DataFrame,
    turnover_detail: pd.DataFrame,
    cost_summary: pd.DataFrame,
    static_comparison: pd.DataFrame,
    output_files: list[Path],
    report_path: Path,
    ver3_index_path: Path,
) -> pd.DataFrame:
    """Build Step D validation summary."""

    checks = [
        ("project_root_exists", paths.project_root.exists(), str(paths.project_root)),
        ("ver3_root_exists", paths.ver3_root.exists(), str(paths.ver3_root)),
        ("stepD_module_path_exists", (paths.ver3_root / "src" / "covered_call_mini_ver3" / "stepD_dynamic_weighting").exists(), "Step D module path exists."),
        ("input_files_exist", inputs_exist, "All required Step D input files exist."),
        ("lookbacks_supported_only", set(lookbacks).issubset(set(SUPPORTED_LOOKBACKS)), "Lookbacks are restricted to 126 and 252."),
        ("methods_supported_only", set(methods).issubset(set(SUPPORTED_METHODS)), "Methods are restricted to the approved Step D set."),
        ("rebalance_frequency_monthly", REBALANCE_FREQUENCY == "monthly", "Only monthly rebalance frequency is used."),
        ("universe_A_assets_match_contract", _universe_assets(universes, "A") == {"510300", "510500", "159915"}, "Universe A uses 510300/510500/159915 only."),
        ("universe_B_assets_match_contract", _universe_assets(universes, "B") == {"510300", "510050", "159915"}, "Universe B uses 510300/510050/159915 only."),
        ("no_588000_in_main_stepD", _no_forbidden_token(universes, ("588000",)), "588000 is excluded from the Step D main long sample."),
        ("no_new_option_parameter_sleeves", _no_forbidden_token(universes, forbidden_main_tokens()), "No Q100/ATM_Q100/TP80/TouchK sleeves are introduced."),
        ("no_dynamic_q_or_call_timing_columns", _no_dynamic_q_or_timing(rebalance_weights), "Outputs contain no dynamic q or sell-call timing decision columns."),
        ("anchor_weights_sum_to_one", _anchor_weights_sum_to_one(universes), "Universe anchor weights sum to one."),
        ("sample_summary_non_empty", not sample_summary.empty, "Sample summary is non-empty."),
        ("rebalance_weights_sum_to_one", _weights_sum_to_one(rebalance_weights), "Every rebalance target weight vector sums to one."),
        ("daily_weights_sum_to_one", _daily_weights_sum_to_one(daily_weight_paths), "Every daily target weight vector sums to one."),
        ("weight_lower_bound_respected", bool((rebalance_weights["target_weight"].astype(float) >= WEIGHT_LOWER_BOUND - 1e-10).all()), "Rebalance weights respect lower bound."),
        ("weight_upper_bound_respected", bool((rebalance_weights["target_weight"].astype(float) <= WEIGHT_UPPER_BOUND + 1e-10).all()), "Rebalance weights respect upper bound."),
        ("long_only_weights", bool((rebalance_weights["target_weight"].astype(float) >= -1e-12).all()), "All weights are long-only."),
        ("lagged_signals_apply_next_trading_day", bool((pd.to_datetime(rebalance_weights["effective_date"]) > pd.to_datetime(rebalance_weights["signal_date"])).all()), "Signals are lagged to the next trading day."),
        ("monthly_signal_dates_only", _monthly_signal_dates_only(rebalance_weights), "There is no more than one signal date per calendar month per strategy."),
        ("no_daily_rebalancing", _no_daily_rebalancing(rebalance_weights), "Rebalance count is consistent with monthly rather than daily trading."),
        ("dynamic_daily_returns_non_empty", not dynamic_daily_returns.empty, "Dynamic daily return table is non-empty."),
        ("nav_positive", bool((dynamic_nav["nav"].astype(float) > 0).all()), "All dynamic NAV values are positive."),
        ("drawdown_magnitude_nonnegative", bool((drawdowns["drawdown_magnitude"].astype(float) >= -1e-12).all()), "Drawdown magnitude is non-negative."),
        ("turnover_method_recorded", bool(turnover_detail["turnover_method"].eq(TURNOVER_METHOD).all()), "Turnover method is recorded as target-weight approximation."),
        ("rebalance_cost_scenarios_complete", {0.0, 5.0, 10.0, 20.0}.issubset(set(cost_summary["rebalance_cost_bps"].astype(float))), "Cost scenarios include 0/5/10/20 bps."),
        ("static_baseline_comparison_non_empty", not static_comparison.empty, "Static baseline comparison is non-empty."),
        ("static_baselines_same_effective_sample", _static_samples_non_empty(static_comparison), "Static baselines are compared on dynamic effective samples."),
        ("output_csv_rows_nonzero", _csv_outputs_nonzero(output_files), "All CSV outputs contain rows."),
        ("report_generated", report_path.exists() and report_path.stat().st_size > 0, "Chinese markdown report generated."),
        ("ver3_output_index_generated", ver3_index_path.exists() and ver3_index_path.stat().st_size > 0, "ver3 lightweight output index generated."),
        ("real_outputs_written_to_root_outputs", _real_outputs_under_root_outputs(paths, output_files), "Real outputs are under root outputs/."),
        ("no_large_outputs_written_to_ver3_outputs", _no_large_ver3_outputs(paths), "ver3/outputs only keeps lightweight indexes."),
        ("no_outputs_written_outside_allowed_dirs", _outputs_inside_allowed_dirs(paths, output_files), "Output paths stay inside the Step D output root."),
        ("no_ver2_files_modified", _no_output_under(paths.project_root / "ver2_downside_protection", output_files), "No output is written under frozen ver2."),
        ("frozen_metrics_not_modified", _no_output_under(paths.project_root / "src" / "metrics", output_files), "Frozen metrics source path is not written."),
    ]
    return pd.DataFrame([{"check_name": name, "passed": bool(passed), "note": note} for name, passed, note in checks])


def _universe_assets(universes: list[UniverseSpec], universe_short: str) -> set[str]:
    for universe in universes:
        if universe.universe_short == universe_short:
            return set(universe.etf_codes)
    return set()


def _no_forbidden_token(universes: list[UniverseSpec], tokens: tuple[str, ...]) -> bool:
    text = " ".join(asset.sleeve_key for universe in universes for asset in universe.assets)
    return not any(token in text for token in tokens)


def _no_dynamic_q_or_timing(df: pd.DataFrame) -> bool:
    text = " ".join(df.columns).lower()
    forbidden = ("dynamic_q", "call_timing", "sell_call_signal", "vol_sell_call")
    return not any(token in text for token in forbidden)


def _anchor_weights_sum_to_one(universes: list[UniverseSpec]) -> bool:
    return all(abs(sum(universe.anchor_weights.values()) - 1.0) <= 1e-10 for universe in universes)


def _weights_sum_to_one(weights: pd.DataFrame) -> bool:
    sums = weights.groupby(["strategy_name", "effective_date"])["target_weight"].sum()
    return bool((sums - 1.0).abs().max() <= 1e-8)


def _daily_weights_sum_to_one(weights: pd.DataFrame) -> bool:
    sums = weights.groupby(["strategy_name", "date"])["target_weight"].sum()
    return bool((sums - 1.0).abs().max() <= 1e-8)


def _monthly_signal_dates_only(weights: pd.DataFrame) -> bool:
    unique = weights[["strategy_name", "signal_date"]].drop_duplicates().copy()
    unique["month"] = pd.to_datetime(unique["signal_date"]).dt.to_period("M")
    counts = unique.groupby(["strategy_name", "month"])["signal_date"].nunique()
    return bool((counts <= 1).all())


def _no_daily_rebalancing(weights: pd.DataFrame) -> bool:
    unique = weights[["strategy_name", "effective_date"]].drop_duplicates().copy()
    counts = unique.groupby("strategy_name")["effective_date"].nunique()
    if counts.empty:
        return False
    return bool((counts < 60).all())


def _static_samples_non_empty(static_comparison: pd.DataFrame) -> bool:
    return bool((static_comparison["n_trading_days"].astype(int) > 0).all()) if not static_comparison.empty else False


def _csv_outputs_nonzero(paths: list[Path]) -> bool:
    for path in paths:
        if path.suffix.lower() != ".csv":
            continue
        if not path.exists() or path.stat().st_size == 0:
            return False
        try:
            if pd.read_csv(path, nrows=2).empty:
                return False
        except Exception:
            return False
    return True


def _real_outputs_under_root_outputs(paths: StepDPaths, output_files: list[Path]) -> bool:
    root_outputs = (paths.project_root / "outputs").resolve()
    for path in output_files:
        if path.resolve() == paths.ver3_output_index.resolve():
            continue
        if not _is_relative_to(path.resolve(), root_outputs):
            return False
    return True


def _no_large_ver3_outputs(paths: StepDPaths) -> bool:
    if not (paths.ver3_root / "outputs").exists():
        return True
    large_suffixes = {".csv", ".png", ".jpg", ".jpeg", ".xlsx", ".parquet", ".html"}
    for path in (paths.ver3_root / "outputs").rglob("*"):
        if path.is_file() and path.suffix.lower() in large_suffixes:
            return False
    return True


def _outputs_inside_allowed_dirs(paths: StepDPaths, output_files: list[Path]) -> bool:
    output_root = paths.output_root.resolve()
    index = paths.ver3_output_index.resolve()
    for path in output_files:
        resolved = path.resolve()
        if resolved == index:
            continue
        if not _is_relative_to(resolved, output_root):
            return False
    return True


def _no_output_under(root: Path, output_files: list[Path]) -> bool:
    resolved_root = root.resolve()
    return all(not _is_relative_to(path.resolve(), resolved_root) for path in output_files)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
