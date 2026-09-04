from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class PathsConfig:
    etf_prices: Path
    options: Path
    metadata: Path | None
    output_dir: Path


@dataclass(frozen=True)
class BacktestConfig:
    start_date: str | None
    end_date: str | None
    initial_nav: float
    execution_mode: str
    roll_frequency: str
    target_dte: int
    min_days_to_expiry: int
    max_days_to_expiry: int
    min_periods: int
    require_expiry_within_period: bool
    dte_fallback_mode: str = "strict_window"


@dataclass(frozen=True)
class StrategyConfig:
    name: str
    kind: str
    coverage_ratio: float
    target_moneyness: float = 0.0
    enabled: bool = True


@dataclass(frozen=True)
class ExperimentConfig:
    experiment_name: str
    etf_codes: tuple[str, ...]
    paths: PathsConfig
    backtest: BacktestConfig
    strategies: tuple[StrategyConfig, ...]
    liquidity_filters: dict[str, Any]
    transaction_costs: dict[str, Any]
    assumptions: dict[str, Any]

    @property
    def enabled_strategies(self) -> tuple[StrategyConfig, ...]:
        return tuple(strategy for strategy in self.strategies if strategy.enabled)


def _resolve_path(root: Path, value: str | None) -> Path | None:
    if value in (None, ""):
        return None
    path = Path(str(value))
    return path if path.is_absolute() else root / path


def _strategy_from_raw(raw: dict[str, Any]) -> StrategyConfig:
    return StrategyConfig(
        name=str(raw["name"]),
        kind=str(raw["kind"]),
        coverage_ratio=float(raw.get("coverage_ratio", 0.0)),
        target_moneyness=float(raw.get("target_moneyness", 0.0)),
        enabled=bool(raw.get("enabled", True)),
    )


def load_config(path: str | Path, root: str | Path | None = None) -> ExperimentConfig:
    """Load the ver2 YAML config and normalize paths relative to the repo root."""

    config_path = Path(path)
    repo_root = Path(root) if root is not None else config_path.resolve().parents[1]
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    paths = raw.get("paths", {})
    backtest = raw.get("backtest", {})
    return ExperimentConfig(
        experiment_name=str(raw.get("experiment_name", "ver2_downside_protection")),
        etf_codes=tuple(str(code).zfill(6) for code in raw.get("etf_codes", [])),
        paths=PathsConfig(
            etf_prices=_resolve_path(repo_root, paths.get("etf_prices")) or repo_root / "data/raw/etf_prices.csv",
            options=_resolve_path(repo_root, paths.get("options")) or repo_root / "data/raw/options.csv",
            metadata=_resolve_path(repo_root, paths.get("metadata")),
            output_dir=_resolve_path(repo_root, paths.get("output_dir"))
            or repo_root / "outputs/ver2_downside_protection",
        ),
        backtest=BacktestConfig(
            start_date=backtest.get("start_date"),
            end_date=backtest.get("end_date"),
            initial_nav=float(backtest.get("initial_nav", 1.0)),
            execution_mode=str(backtest.get("execution_mode", "continuous_30d")),
            roll_frequency=str(backtest.get("roll_frequency", "monthly")),
            target_dte=int(backtest.get("target_dte", 30)),
            min_days_to_expiry=int(backtest.get("min_days_to_expiry", 20)),
            max_days_to_expiry=int(backtest.get("max_days_to_expiry", 45)),
            min_periods=int(backtest.get("min_periods", 6)),
            require_expiry_within_period=bool(backtest.get("require_expiry_within_period", True)),
            dte_fallback_mode=str(backtest.get("dte_fallback_mode", "strict_window")),
        ),
        strategies=tuple(_strategy_from_raw(item) for item in raw.get("strategies", [])),
        liquidity_filters=dict(raw.get("liquidity_filters", {})),
        transaction_costs=dict(raw.get("transaction_costs", {})),
        assumptions=dict(raw.get("assumptions", {})),
    )


def with_transaction_cost_overrides(config: ExperimentConfig, **overrides: Any) -> ExperimentConfig:
    """Return a copy of config with transaction-cost overrides.

    Dashboard or API callers can use this helper to rerun the same experiment
    under a user-selected cost model without mutating the loaded YAML config.
    """

    transaction_costs = dict(config.transaction_costs)
    transaction_costs.update({key: value for key, value in overrides.items() if value is not None})
    return replace(config, transaction_costs=transaction_costs)
