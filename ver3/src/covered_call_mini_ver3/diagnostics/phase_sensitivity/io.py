from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from dataclasses import replace

from ver2_downside_protection.config import PathsConfig, load_config
from ver2_downside_protection.data_adapter import Ver2DataBundle, load_ver2_data

from .config import CandidatePortfolio, PhasePaths, PhaseRunConfig, TargetSleeve


def load_required_market_data(paths: PhasePaths, target_etfs: list[str]) -> tuple[Any, Ver2DataBundle]:
    """Load the frozen ver2 market-data bundle used by the phase wrapper."""

    base = load_config(paths.project_root / "configs" / "ver2_downside_protection.yaml", paths.project_root)
    delta_options = paths.project_root / "data" / "source" / "delta_enriched_options.csv"
    option_path = delta_options if delta_options.exists() else base.paths.options
    base = replace(
        base,
        etf_codes=tuple(sorted(set(target_etfs))),
        paths=PathsConfig(
            etf_prices=base.paths.etf_prices,
            options=option_path,
            metadata=base.paths.metadata,
            output_dir=paths.output_root,
        ),
    )
    return base, load_ver2_data(base)


def write_csv(df: pd.DataFrame, path: Path) -> None:
    """Write a non-empty CSV with a stable UTF-8 BOM for Excel inspection."""

    if df.empty:
        raise ValueError(f"Refusing to write empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def write_json(payload: dict[str, Any], path: Path) -> None:
    """Write a JSON payload."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_config_artifacts(
    paths: PhasePaths,
    run_config: PhaseRunConfig,
    target_sleeves: list[TargetSleeve],
    portfolios: list[CandidatePortfolio],
    phase_grid: pd.DataFrame,
) -> None:
    """Write static config artifacts for the diagnostic run."""

    write_json(
        {
            "experiment_id": paths.output_root.name,
            "run_config": asdict(run_config),
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "project_root": str(paths.project_root),
            "ver3_root": str(paths.ver3_root),
            "output_root": str(paths.output_root),
        },
        paths.config_dir / "ver3_0_phase_sensitivity_config.json",
    )
    write_csv(pd.DataFrame([asdict(s) for s in target_sleeves]), paths.config_dir / "ver3_0_phase_target_sleeves.csv")
    portfolio_rows = []
    for p in portfolios:
        for sleeve_key, weight in p.sleeve_weights.items():
            portfolio_rows.append(
                {
                    "portfolio_name": p.portfolio_name,
                    "role": p.role,
                    "target_mdd": p.target_mdd,
                    "sleeve_key": sleeve_key,
                    "weight": weight,
                }
            )
    write_csv(pd.DataFrame(portfolio_rows), paths.config_dir / "ver3_0_phase_candidate_portfolios.csv")
    write_csv(phase_grid, paths.config_dir / "ver3_0_phase_shift_grid.csv")


def write_ver3_index(
    path: Path,
    *,
    output_root: Path,
    report_path: Path,
    run_timestamp: str,
    target_sleeves: list[TargetSleeve],
    portfolios: list[CandidatePortfolio],
    highest_fragility_sleeve: str,
    highest_robust_candidate: str,
    ensemble_improved: str,
    appendix_recommendation: str,
) -> None:
    """Write the lightweight ver3 output index."""

    lines = [
        "# ver3.0 Phase Sensitivity Output Index",
        "",
        f"- Real output root: `{output_root}`",
        f"- Main report: `{report_path}`",
        f"- Run timestamp: {run_timestamp}",
        f"- Highest phase fragility sleeve: `{highest_fragility_sleeve}`",
        f"- Highest phase robustness candidate: `{highest_robust_candidate}`",
        f"- Ensemble improves phase risk: {ensemble_improved}",
        f"- Suggested final appendix inclusion: {appendix_recommendation}",
        "",
        "## Target Sleeves",
    ]
    for sleeve in target_sleeves:
        lines.append(f"- `{sleeve.sleeve_name}`: {sleeve.role}")
    lines += ["", "## Target Portfolios"]
    for portfolio in portfolios:
        lines.append(f"- `{portfolio.portfolio_name}`: {portfolio.role}")
    lines += [
        "",
        "## Core Summary Paths",
        f"- Sleeve metrics by phase: `{output_root / 'summary' / 'ver3_0_phase_sleeve_metrics_by_phase.csv'}`",
        f"- Portfolio metrics by phase: `{output_root / 'summary' / 'ver3_0_phase_portfolio_metrics_by_phase.csv'}`",
        f"- Sleeve robustness summary: `{output_root / 'summary' / 'ver3_0_phase_sleeve_robustness_summary.csv'}`",
        f"- Portfolio robustness summary: `{output_root / 'summary' / 'ver3_0_phase_portfolio_robustness_summary.csv'}`",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8-sig")
