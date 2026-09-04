from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import StepBPlusPaths, UniverseSpec, forbidden_main_tokens, sleeve_return_column


def build_validation_summary(
    *,
    paths: StepBPlusPaths,
    inputs_exist: bool,
    sample_panel: pd.DataFrame,
    universes: dict[str, UniverseSpec],
    grid_results: pd.DataFrame,
    best_rows: pd.DataFrame,
    best_daily_nav: pd.DataFrame,
    best_drawdowns: pd.DataFrame,
    output_files: list[Path],
    report_path: Path,
    ver3_index_path: Path,
) -> pd.DataFrame:
    """Build the Step B+ required validation table."""

    checks = [
        ("project_root_exists", paths.project_root.exists(), str(paths.project_root)),
        ("ver3_root_exists", paths.ver3_root.exists(), str(paths.ver3_root)),
        ("input_files_exist", inputs_exist, "所有必需的 Step A/Step B 输入文件均存在"),
        ("required_sleeves_exist", _required_sleeves_exist(sample_panel, universes), "所有指定 selected sleeves 均存在"),
        ("universe_a_b_same_sample", _universe_a_b_same_sample(sample_panel), "A/B 前沿使用同一个对齐后的样本面板"),
        ("no_588000_in_main_frontier", _no_forbidden_sleeves(universes, ("588000",)), "588000 已排除在主前沿之外"),
        ("weights_sum_to_one", _weights_sum_to_one(grid_results, best_rows), "所有网格和最优权重行的权重和为 1"),
        ("weight_bounds_respected", _weight_bounds_respected(grid_results, best_rows), "网格与最优权重均满足当前边界"),
        ("grid_results_non_empty", not grid_results.empty, "网格结果存在有效行"),
        ("feasible_solution_exists_or_marked_infeasible", _feasible_or_marked(best_rows), "每个 D-star 均有可行解或明确标记为不可行"),
        ("nav_initial_reference_is_one", _initial_nav_is_one(best_daily_nav), "最优组合 NAV 使用 initial_nav=1.0 参考"),
        ("nav_positive", _nav_positive(best_daily_nav), "所有最优组合 NAV 均为正"),
        ("max_drawdown_positive_magnitude", _mdd_positive(best_rows, best_drawdowns), "MDD 使用正数幅度口径"),
        ("output_csv_rows_nonzero", _csv_outputs_nonzero(output_files), "CSV 输出存在且包含有效行"),
        ("report_generated", report_path.exists() and report_path.stat().st_size > 0, str(report_path)),
        ("real_outputs_written_to_root_outputs", _real_outputs_under_root_outputs(paths, output_files), "真实输出保留在仓库根目录 outputs 下"),
        ("no_large_outputs_written_to_ver3_outputs", _no_large_ver3_outputs(paths), "ver3/outputs 仅保留轻量 Markdown 索引"),
        ("no_outputs_written_outside_allowed_dirs", _outputs_inside_allowed_dirs(paths, output_files), "输出只写入允许的 Step B+ 输出根目录或 ver3 轻量索引"),
        ("no_ver2_files_modified", _no_output_under(paths.project_root / "ver2_downside_protection", output_files), "Step B+ 未写入冻结 ver2 证据目录"),
        ("frozen_metrics_not_modified", _no_output_under(paths.project_root / "src" / "metrics", output_files), "Step B+ 未写入冻结指标依赖目录"),
        ("ver3_output_index_generated", ver3_index_path.exists() and ver3_index_path.stat().st_size > 0, str(ver3_index_path)),
    ]
    return pd.DataFrame([{"check_name": name, "passed": bool(passed), "note": note} for name, passed, note in checks])


def _required_sleeves_exist(sample_panel: pd.DataFrame, universes: dict[str, UniverseSpec]) -> bool:
    cols = set(sample_panel.columns)
    return all(sleeve_return_column(etf, sleeve) in cols for universe in universes.values() for etf, sleeve in universe.sleeves_by_etf.items())


def _universe_a_b_same_sample(sample_panel: pd.DataFrame) -> bool:
    return not sample_panel.empty and sample_panel["date"].notna().all()


def _no_forbidden_sleeves(universes: dict[str, UniverseSpec], tokens: tuple[str, ...] | None = None) -> bool:
    text = " ".join(f"{etf} {sleeve}" for universe in universes.values() for etf, sleeve in universe.sleeves_by_etf.items())
    return not any(token in text for token in (tokens or forbidden_main_tokens()))


def _weights_sum_to_one(grid_results: pd.DataFrame, best_rows: pd.DataFrame) -> bool:
    frames = [grid_results, best_rows[best_rows.get("feasible", False).astype(bool)] if "feasible" in best_rows else best_rows]
    for frame in frames:
        if frame.empty:
            continue
        weight_cols = [c for c in frame.columns if c.startswith("weight_") and c != "weight_sum" and c != "weight_vector_key"]
        if not weight_cols:
            continue
        sums = frame[weight_cols].astype(float).sum(axis=1)
        if not bool((sums.sub(1.0).abs() <= 1e-8).all()):
            return False
    return True


def _weight_bounds_respected(grid_results: pd.DataFrame, best_rows: pd.DataFrame) -> bool:
    for frame in [grid_results, best_rows[best_rows.get("feasible", False).astype(bool)] if "feasible" in best_rows else best_rows]:
        if frame.empty:
            continue
        weight_cols = [c for c in frame.columns if c.startswith("weight_") and c != "weight_sum" and c != "weight_vector_key"]
        for _, row in frame.iterrows():
            lower = float(row["lower_bound"])
            upper = float(row["upper_bound"])
            values = row[weight_cols].dropna().astype(float)
            if values.empty:
                continue
            if not bool(((values >= lower - 1e-10) & (values <= upper + 1e-10)).all()):
                return False
    return True


def _feasible_or_marked(best_rows: pd.DataFrame) -> bool:
    if best_rows.empty:
        return False
    return bool(best_rows["frontier_status"].isin(["feasible", "infeasible"]).all())


def _initial_nav_is_one(best_daily_nav: pd.DataFrame) -> bool:
    return not best_daily_nav.empty and bool((best_daily_nav["initial_nav"].astype(float) == 1.0).all())


def _nav_positive(best_daily_nav: pd.DataFrame) -> bool:
    return not best_daily_nav.empty and bool((best_daily_nav["nav"].astype(float) > 0).all())


def _mdd_positive(best_rows: pd.DataFrame, best_drawdowns: pd.DataFrame) -> bool:
    feasible = best_rows[best_rows["feasible"].astype(bool)] if "feasible" in best_rows else best_rows
    if feasible.empty or best_drawdowns.empty:
        return False
    return bool((feasible["max_drawdown"].astype(float) >= 0).all() and (best_drawdowns["drawdown_magnitude"].astype(float) >= -1e-12).all())


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


def _real_outputs_under_root_outputs(paths: StepBPlusPaths, output_files: list[Path]) -> bool:
    root_outputs = (paths.project_root / "outputs").resolve()
    for path in output_files:
        if path.resolve() == paths.ver3_output_index.resolve():
            continue
        if not _is_relative_to(path.resolve(), root_outputs):
            return False
    return True


def _no_large_ver3_outputs(paths: StepBPlusPaths) -> bool:
    ver3_outputs = paths.ver3_root / "outputs"
    if not ver3_outputs.exists():
        return True
    large_suffixes = {".csv", ".png", ".jpg", ".jpeg", ".xlsx", ".parquet", ".html"}
    for path in ver3_outputs.rglob("*"):
        if path.is_file() and path.suffix.lower() in large_suffixes:
            return False
    return True


def _outputs_inside_allowed_dirs(paths: StepBPlusPaths, output_files: list[Path]) -> bool:
    allowed = [paths.output_root.resolve(), paths.ver3_output_index.resolve()]
    for path in output_files:
        resolved = path.resolve()
        if resolved == allowed[1]:
            continue
        if not _is_relative_to(resolved, allowed[0]):
            return False
    return True


def _no_output_under(forbidden_root: Path, output_files: list[Path]) -> bool:
    root = forbidden_root.resolve()
    return all(not _is_relative_to(path.resolve(), root) for path in output_files)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
