from __future__ import annotations

from src.strategies.base import STRATEGY_SPECS, StrategySpec


def fixed_covered_call_strategies(names: list[str]) -> list[StrategySpec]:
    return [STRATEGY_SPECS[name] for name in names]
