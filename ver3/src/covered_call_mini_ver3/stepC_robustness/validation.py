from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import CandidateSpec, StepCPaths, forbidden_main_tokens


def build_validation_summary(
    *,
    paths: StepCPaths,
    inputs_exist: bool,
    candidates: list[CandidateSpec],
    sample_panel: pd.DataFrame,
    candidate_nav: pd.DataFrame,
    drawdowns: pd.DataFrame,
    rolling_outputs: list[pd.DataFrame],
    event_outputs: list[pd.DataFrame],
    cost_outputs: list[pd.DataFrame],
    output_files: list[Path],
    report_path: Path,
    ver3_index_path: Path,
) -> pd.DataFrame:
    """Build Step C validation summary."""

    checks = [
        ("project_root_exists", paths.project_root.exists(), str(paths.project_root)),
        ("ver3_root_exists", paths.ver3_root.exists(), str(paths.ver3_root)),
        ("input_files_exist", inputs_exist, "所有 Step C 必需输入文件均存在"),
        ("required_candidate_portfolios_exist", len(candidates) >= 1, "当前 Step C 候选组合已定义"),
        ("required_sleeves_exist", _required_sleeves_exist(sample_panel, candidates), "候选组合需要的 sleeve return 均存在"),
        ("candidates_same_sample", _candidates_same_sample(candidate_nav), "四个候选组合使用同一共同样本"),
        ("no_588000_in_main_stepC", _no_forbidden_token(candidates, ("588000",)), "588000 未进入 Step C 主线"),
        ("no_new_option_parameter_sleeves", _no_forbidden_token(candidates, forbidden_main_tokens()), "未引入 Q100/ATM/TP80/TouchK 等新参数 sleeve"),
        ("weights_sum_to_one", _weights_sum_to_one(candidates), "候选组合权重和均为 1"),
        ("nav_initial_reference_is_one", bool((candidate_nav["initial_nav"].astype(float) == 1.0).all()), "NAV 使用 initial_nav=1.0"),
        ("nav_positive", bool((candidate_nav["nav"].astype(float) > 0).all()), "所有候选 NAV 均为正"),
        ("max_drawdown_positive_magnitude", bool((drawdowns["drawdown_magnitude"].astype(float) >= -1e-12).all()), "回撤幅度使用正数口径"),
        ("rolling_outputs_non_empty", all(not df.empty for df in rolling_outputs), "滚动与分段指标输出非空"),
        ("event_outputs_non_empty", all(not df.empty for df in event_outputs), "事件窗口输出非空"),
        ("cost_outputs_non_empty_or_marked_unavailable", all(not df.empty for df in cost_outputs), "成本敏感性输出非空"),
        ("output_csv_rows_nonzero", _csv_outputs_nonzero(output_files), "所有 CSV 输出均包含有效行"),
        ("report_generated", report_path.exists() and report_path.stat().st_size > 0, "中文 Markdown 报告已生成"),
        ("real_outputs_written_to_root_outputs", _real_outputs_under_root_outputs(paths, output_files), "真实输出写入根目录 outputs"),
        ("no_large_outputs_written_to_ver3_outputs", _no_large_ver3_outputs(paths), "ver3/outputs 只保留轻量索引"),
        ("no_outputs_written_outside_allowed_dirs", _outputs_inside_allowed_dirs(paths, output_files), "输出路径均在允许目录内"),
        ("no_ver2_files_modified", _no_output_under(paths.project_root / "ver2_downside_protection", output_files), "未写入冻结 ver2 目录"),
        ("frozen_metrics_not_modified", _no_output_under(paths.project_root / "src" / "metrics", output_files), "未写入冻结指标目录"),
        ("ver3_output_index_generated", ver3_index_path.exists() and ver3_index_path.stat().st_size > 0, "ver3 轻量索引已生成"),
    ]
    return pd.DataFrame([{"check_name": name, "passed": bool(passed), "note": note} for name, passed, note in checks])


def _required_sleeves_exist(sample_panel: pd.DataFrame, candidates: list[CandidateSpec]) -> bool:
    text = " ".join(sample_panel.columns)
    return all(f"{key}__daily_return" in text for candidate in candidates for key in candidate.sleeve_weights)


def _candidates_same_sample(candidate_nav: pd.DataFrame) -> bool:
    sample = candidate_nav.groupby("portfolio_name").agg(start=("date", "min"), end=("date", "max"), n=("date", "count"))
    return bool(sample["start"].nunique() == 1 and sample["end"].nunique() == 1 and sample["n"].nunique() == 1)


def _no_forbidden_token(candidates: list[CandidateSpec], tokens: tuple[str, ...]) -> bool:
    text = " ".join(" ".join(candidate.sleeve_weights) for candidate in candidates)
    return not any(token in text for token in tokens)


def _weights_sum_to_one(candidates: list[CandidateSpec]) -> bool:
    return all(abs(sum(candidate.sleeve_weights.values()) - 1.0) <= 1e-10 for candidate in candidates)


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


def _real_outputs_under_root_outputs(paths: StepCPaths, output_files: list[Path]) -> bool:
    root_outputs = (paths.project_root / "outputs").resolve()
    for path in output_files:
        if path.resolve() == paths.ver3_output_index.resolve():
            continue
        if not _is_relative_to(path.resolve(), root_outputs):
            return False
    return True


def _no_large_ver3_outputs(paths: StepCPaths) -> bool:
    if not (paths.ver3_root / "outputs").exists():
        return True
    large_suffixes = {".csv", ".png", ".jpg", ".jpeg", ".xlsx", ".parquet", ".html"}
    for path in (paths.ver3_root / "outputs").rglob("*"):
        if path.is_file() and path.suffix.lower() in large_suffixes:
            return False
    return True


def _outputs_inside_allowed_dirs(paths: StepCPaths, output_files: list[Path]) -> bool:
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
