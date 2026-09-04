from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import PortfolioDefinition, forbidden_main_sleeve_tokens


def build_validation_summary(
    *,
    portfolios: list[PortfolioDefinition],
    portfolio_returns: pd.DataFrame,
    portfolio_nav: pd.DataFrame,
    summary: pd.DataFrame,
    selected_vs_pure: pd.DataFrame,
    sample_window: pd.DataFrame,
    output_files: list[Path],
    report_path: Path,
) -> pd.DataFrame:
    """Build Step B sanity checks."""

    checks = [
        ("required_sleeves_exist", True, "组合构建前已验证必需 sleeves 存在"),
        ("weights_sum_to_one", _weights_sum_to_one(portfolios), "所有组合权重和为 1"),
        ("portfolio_returns_non_empty", not portfolio_returns.empty and portfolio_returns["portfolio_daily_return"].notna().any(), "组合日收益存在有效行"),
        ("initial_nav_reference_is_one", bool((portfolio_nav["initial_nav"].astype(float) == 1.0).all()), "NAV 路径使用 initial_nav=1.0 作为参考"),
        ("nav_positive", bool((portfolio_nav["nav"].astype(float) > 0).all()), "所有 NAV 值均为正"),
        ("max_drawdown_positive_magnitude", bool((summary["max_drawdown"].astype(float) >= 0).all()), "max_drawdown 使用正数幅度口径"),
        ("selected_has_matched_pure_baseline", _selected_has_baseline(summary, selected_vs_pure), "每个 selected 组合均有匹配 pure ETF 基准"),
        ("universe_a_b_same_sample", _same_sample_by_universe(summary), "Universe A 与 B 使用同一共同样本"),
        ("no_588000_in_main_portfolios", _no_forbidden_token(portfolios, ("588000",)), "588000 已排除在长样本 Step B 主线之外"),
        ("no_q100_atm_tp80_touchk_main_selected", _no_forbidden_token(portfolios, forbidden_main_sleeve_tokens()), "默认 selected 组合排除诊断型 sleeves"),
        ("output_csv_rows_nonzero", _csv_outputs_nonzero(output_files), "CSV 输出存在非空行"),
        ("report_generated", report_path.exists() and report_path.stat().st_size > 0, "Markdown 报告已生成"),
    ]
    return pd.DataFrame([{"check_name": name, "passed": bool(passed), "note": note} for name, passed, note in checks])


def _weights_sum_to_one(portfolios: list[PortfolioDefinition]) -> bool:
    return all(abs(sum(p.sleeve_weights.values()) - 1.0) < 1e-10 for p in portfolios)


def _selected_has_baseline(summary: pd.DataFrame, selected_vs_pure: pd.DataFrame) -> bool:
    selected_count = int(summary["portfolio_type"].eq("Selected").sum())
    return len(selected_vs_pure) == selected_count


def _same_sample_by_universe(summary: pd.DataFrame) -> bool:
    grouped = summary.groupby("universe_short")[["sample_start", "sample_end", "n_trading_days"]].nunique()
    return bool((grouped <= 1).all().all() and summary["sample_start"].nunique() == 1 and summary["sample_end"].nunique() == 1)


def _no_forbidden_token(portfolios: list[PortfolioDefinition], tokens: tuple[str, ...]) -> bool:
    selected = [p for p in portfolios if p.portfolio_type == "Selected"]
    for portfolio in selected:
        text = " ".join(portfolio.sleeve_weights)
        if any(token in text for token in tokens):
            return False
    return True


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
