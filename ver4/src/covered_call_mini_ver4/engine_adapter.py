from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ver2_downside_protection.config import ExperimentConfig, StrategyConfig, load_config
from ver2_downside_protection.strategy_engine import Ver2BacktestResult, run_ver2_backtest

from .config import CycleExperimentConfig


def strategy_name(target_delta: float, coverage: float) -> str:
    return f"D{int(round(target_delta * 100)):02d}_Q{int(round(coverage * 100)):03d}"


def atm_strategy_name(coverage: float) -> str:
    return f"ATM_Q{int(round(coverage * 100)):03d}"


def static_strategy_count(config: CycleExperimentConfig) -> int:
    return 1 + len(config.target_deltas) * len(config.coverages) + int(config.include_atm) * len(config.coverages)


def strategy_metadata(config: CycleExperimentConfig) -> dict[str, dict[str, float | str]]:
    rows: dict[str, dict[str, float | str]] = {
        "BuyHold": {
            "parameter_role": "buyhold",
            "target_delta": float("nan"),
            "coverage": 0.0,
            "strategy_label": "ETF BuyHold",
        }
    }
    for target_delta in config.target_deltas:
        for coverage in config.coverages:
            name = strategy_name(target_delta, coverage)
            rows[name] = {
                "parameter_role": "static_target_delta_coverage",
                "target_delta": float(target_delta),
                "coverage": float(coverage),
                "strategy_label": f"D{int(round(target_delta * 100)):02d} / Q{int(round(coverage * 100)):03d}",
            }
    if config.include_atm:
        for coverage in config.coverages:
            name = atm_strategy_name(coverage)
            rows[name] = {
                "parameter_role": "static_atm_coverage",
                "target_delta": float("nan"),
                "coverage": float(coverage),
                "strategy_label": f"ATM / Q{int(round(coverage * 100)):03d}",
            }
    return rows


def build_engine_config(config: CycleExperimentConfig) -> ExperimentConfig:
    """Build the frozen execution configuration for one ETF static grid."""

    base = load_config(config.paths.engine_config_path, config.paths.project_root)
    strategies = [StrategyConfig("BuyHold", "buy_hold", 0.0, 0.0, True)]
    strategies.extend(
        StrategyConfig(strategy_name(delta, coverage), "target_delta", coverage, delta, True)
        for delta in config.target_deltas
        for coverage in config.coverages
    )
    if config.include_atm:
        strategies.extend(
            StrategyConfig(atm_strategy_name(coverage), "atm", coverage, 0.0, True)
            for coverage in config.coverages
        )
    return replace(
        base,
        experiment_name=config.experiment_id,
        etf_codes=(config.etf.etf_code,),
        paths=replace(
            base.paths,
            etf_prices=config.paths.etf_prices_path,
            options=config.paths.option_chain_path,
            metadata=config.paths.metadata_path,
            output_dir=config.paths.output_root,
        ),
        backtest=replace(
            base.backtest,
            start_date=config.etf.sample_start,
            end_date=config.etf.sample_end,
            initial_nav=1.0,
            execution_mode="continuous_30d",
            roll_frequency="monthly",
            target_dte=config.target_dte,
            min_days_to_expiry=config.min_dte,
            max_days_to_expiry=config.max_dte,
            min_periods=1,
            require_expiry_within_period=False,
            dte_fallback_mode="strict_window",
        ),
        strategies=tuple(strategies),
    )


def validate_engine_inputs(config: CycleExperimentConfig) -> None:
    required: tuple[Path, ...] = (
        config.paths.engine_config_path,
        config.paths.etf_prices_path,
        config.paths.option_chain_path,
    )
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing ver4.0 input files:\n" + "\n".join(missing))


def run_static_cycle_grid(config: CycleExperimentConfig) -> Ver2BacktestResult:
    """Run the execution engine once; accounting is transformed downstream."""

    validate_engine_inputs(config)
    return run_ver2_backtest(build_engine_config(config))
