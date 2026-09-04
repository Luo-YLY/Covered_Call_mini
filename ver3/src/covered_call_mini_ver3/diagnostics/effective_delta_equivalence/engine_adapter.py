from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ver2_downside_protection.config import ExperimentConfig, StrategyConfig, load_config
from ver2_downside_protection.strategy_engine import Ver2BacktestResult, run_ver2_backtest

from .config import DiagnosticConfig


def build_engine_config(
    config: DiagnosticConfig,
    *,
    sample_start: str | None = None,
    etf_codes: tuple[str, ...] | None = None,
) -> ExperimentConfig:
    """Create a frozen-engine config for this diagnostic run."""

    base = load_config(config.paths.engine_config_path, config.paths.project_root)
    strategies = [StrategyConfig("BuyHold", "buy_hold", 0.0, 0.0, True)]
    strategies.extend(
        StrategyConfig(item.name, "target_delta", item.coverage, item.target_call_delta, True)
        for item in config.implementations
    )
    return replace(
        base,
        experiment_name="ver3_0_effective_delta_equivalence",
        etf_codes=etf_codes or config.active_etfs,
        paths=replace(
            base.paths,
            etf_prices=config.paths.etf_prices_path,
            options=config.paths.options_path,
            metadata=config.paths.metadata_path,
            output_dir=config.paths.output_root,
        ),
        backtest=replace(
            base.backtest,
            start_date=sample_start or config.sample_start,
            end_date=config.sample_end,
            initial_nav=1.0,
            execution_mode="continuous_30d",
            roll_frequency="monthly",
            target_dte=30,
            min_days_to_expiry=20,
            max_days_to_expiry=45,
            min_periods=1,
            require_expiry_within_period=False,
            dte_fallback_mode="strict_window",
        ),
        strategies=tuple(strategies),
    )


def validate_engine_support(config: DiagnosticConfig) -> None:
    """Fail fast when required frozen-engine inputs are unavailable."""

    required: list[Path] = [
        config.paths.engine_config_path,
        config.paths.etf_prices_path,
        config.paths.options_path,
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing effective-delta diagnostic input files:\n" + "\n".join(missing))


def run_sleeve_engine(
    config: DiagnosticConfig,
    *,
    sample_start: str | None = None,
    etf_codes: tuple[str, ...] | None = None,
) -> Ver2BacktestResult:
    """Run the existing continuous DTE30 daily-MTM engine for target-delta sleeves."""

    engine_config = build_engine_config(config, sample_start=sample_start, etf_codes=etf_codes)
    return run_ver2_backtest(engine_config)
