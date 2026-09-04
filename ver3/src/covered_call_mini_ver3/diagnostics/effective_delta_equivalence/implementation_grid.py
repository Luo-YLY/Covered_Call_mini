from __future__ import annotations

import pandas as pd

from .config import DiagnosticConfig


PREREGISTERED_NAMES = ("D28_Q100", "D35_Q80", "D40_Q70", "D50_Q56")


def build_effective_delta_implementation_grid(config: DiagnosticConfig) -> pd.DataFrame:
    """Build the pre-registered same-effective-delta implementation table."""

    rows = []
    for item in config.implementations:
        rows.append(
            {
                "implementation_name": item.name,
                "target_effective_delta": config.target_effective_delta,
                "target_call_delta": item.target_call_delta,
                "coverage": item.coverage,
                "coverage_label": item.coverage_label,
                "expected_overlay_delta": item.expected_overlay_delta,
                "expected_effective_delta": item.expected_effective_delta,
                "effective_delta_error_vs_target": item.expected_effective_delta - config.target_effective_delta,
                "role": item.role,
                "interpretation": item.interpretation,
                "is_current_mainline": item.name == "D40_Q70",
                "is_q100_equivalence_context": item.name == "D28_Q100",
            }
        )
    return pd.DataFrame(rows)


def build_target_etf_table(config: DiagnosticConfig) -> pd.DataFrame:
    rows = []
    for etf in config.active_etfs:
        rows.append(
            {
                "etf_code": etf,
                "diagnostic_role": "main_core" if etf in {"510300", "510050"} else "growth_appendix",
                "included_by_default": etf in {"510300", "510050"},
                "sample_start_requested": config.sample_start,
                "sample_end_requested": config.sample_end,
            }
        )
    return pd.DataFrame(rows)


def validate_preregistered_grid(grid: pd.DataFrame, target_effective_delta: float) -> None:
    names = tuple(grid["implementation_name"].astype(str))
    if names != PREREGISTERED_NAMES:
        raise ValueError(f"Implementation grid must equal {PREREGISTERED_NAMES}; got {names}")
    overlay = pd.to_numeric(grid["expected_overlay_delta"], errors="coerce")
    expected = pd.to_numeric(grid["expected_effective_delta"], errors="coerce")
    if not overlay.sub(1.0 - target_effective_delta).abs().le(1e-10).all():
        raise ValueError("Expected overlay delta is not equal to the pre-registered 0.28 target.")
    if not expected.sub(target_effective_delta).abs().le(1e-10).all():
        raise ValueError("Expected effective delta is not equal to the target.")
    if not pd.to_numeric(grid["coverage"], errors="coerce").between(0.0, 1.0).all():
        raise ValueError("Coverage must stay between 0 and 1.")
