from __future__ import annotations

import pandas as pd

from .config import CandidateSpec, FixedBaselineSpec, forbidden_main_tokens


def candidate_weight_table(candidates: list[CandidateSpec]) -> pd.DataFrame:
    """Return one row per candidate sleeve weight."""

    rows = []
    for candidate in candidates:
        for sleeve_key, weight in candidate.sleeve_weights.items():
            etf_code, sleeve_name = sleeve_key.split("__", 1)
            rows.append(
                {
                    "portfolio_name": candidate.portfolio_name,
                    "source_portfolio_name": candidate.source_portfolio_name,
                    "universe_short": candidate.universe_short,
                    "role": candidate.role,
                    "etf_code": etf_code,
                    "sleeve_key": sleeve_key,
                    "sleeve_name": sleeve_name,
                    "weight": float(weight),
                }
            )
    return pd.DataFrame(rows)


def fixed_baseline_table(baselines: list[FixedBaselineSpec]) -> pd.DataFrame:
    """Return fixed baseline metadata."""

    return pd.DataFrame([baseline.__dict__ for baseline in baselines])


def validate_candidate_sources(candidates: list[CandidateSpec], frontier_default: pd.DataFrame) -> None:
    """Ensure all candidate source portfolios exist in Step B+ default frontier."""

    available = set(frontier_default["portfolio_name"].astype(str))
    missing = [item.source_portfolio_name for item in candidates if item.source_portfolio_name not in available]
    missing = [name for name in missing if "_v31_" not in name]
    if missing:
        raise ValueError("Step B+ default frontier 缺少候选来源组合：\n" + "\n".join(missing))


def validate_candidate_weights(candidates: list[CandidateSpec]) -> None:
    """Validate weight sums and forbidden sleeves."""

    tokens = forbidden_main_tokens()
    for candidate in candidates:
        total = sum(float(v) for v in candidate.sleeve_weights.values())
        if abs(total - 1.0) > 1e-10:
            raise ValueError(f"{candidate.portfolio_name} 权重和不是 1：{total}")
        text = " ".join(candidate.sleeve_weights)
        if any(token in text for token in tokens):
            raise ValueError(f"{candidate.portfolio_name} 含有主线禁用 sleeve token：{tokens}")
