from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .config import CycleExperimentConfig
from .engine_adapter import run_static_cycle_grid, strategy_metadata
from .io import ensure_output_dirs, write_csv, write_manifest
from .ledger import attach_cycle_market_context, build_cycle_daily_mtm_ledger, build_cycle_ledger
from .metrics import attach_rolling_cashflow_summary, build_cycle_cashflow_summary, build_rolling_cycle_cashflow
from .regime import build_cycle_regime_attribution
from .reporting import write_markdown_report
from .validation import build_validation_summary


@dataclass(frozen=True)
class CycleExperimentResult:
    output_root: Path
    cycle_ledger: pd.DataFrame
    cycle_daily_mtm: pd.DataFrame
    summary: pd.DataFrame
    rolling_cashflow: pd.DataFrame
    regime_attribution: pd.DataFrame
    validation: pd.DataFrame
    report_path: Path


def run_cycle_cashflow_experiment(config: CycleExperimentConfig) -> CycleExperimentResult:
    """Run the static single-ETF grid and write the ver4.0 accounting artifacts."""

    dirs = ensure_output_dirs(config)
    write_manifest(config, dirs["config"] / "ver4_0_experiment_manifest.json")
    result = run_static_cycle_grid(config)
    meta = strategy_metadata(config)
    ledger = build_cycle_ledger(result.periods, meta, config)
    ledger = attach_cycle_market_context(
        ledger,
        etf_prices=pd.read_csv(config.paths.etf_prices_path),
        option_chain=pd.read_csv(
            config.paths.option_chain_path,
            usecols=lambda column: column in {"trade_date", "option_code", "model_iv", "days_to_expiry"},
        ),
    )
    daily_mtm = build_cycle_daily_mtm_ledger(result.daily_mtm, meta, config)
    rolling = build_rolling_cycle_cashflow(ledger, config)
    summary = attach_rolling_cashflow_summary(build_cycle_cashflow_summary(ledger, config), rolling, config)
    regime = build_cycle_regime_attribution(ledger, config)
    validation = build_validation_summary(ledger, daily_mtm, summary, rolling, regime, config)

    write_csv(ledger, dirs["period"] / "ver4_0_cycle_ledger.csv")
    write_csv(daily_mtm, dirs["daily_mtm"] / "ver4_0_cycle_daily_mtm.csv")
    write_csv(summary, dirs["summary"] / "ver4_0_cycle_cashflow_summary.csv")
    write_csv(rolling, dirs["summary"] / "ver4_0_rolling_12_cycle_cashflow.csv")
    write_csv(regime, dirs["regime"] / "ver4_0_cycle_regime_attribution.csv")
    write_csv(validation, dirs["audit"] / "ver4_0_validation_summary.csv")
    report_path = write_markdown_report(config, summary=summary, validation=validation, output_root=dirs["root"])
    return CycleExperimentResult(
        output_root=dirs["root"],
        cycle_ledger=ledger,
        cycle_daily_mtm=daily_mtm,
        summary=summary,
        rolling_cashflow=rolling,
        regime_attribution=regime,
        validation=validation,
        report_path=report_path,
    )
