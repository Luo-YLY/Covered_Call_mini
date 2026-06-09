from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StrategySpec:
    name: str
    kind: str
    coverage_ratio: float
    use_iv_timing: bool = False


STRATEGY_SPECS = {
    "S0_BuyHold": StrategySpec("S0_BuyHold", "buy_hold", 0.0),
    "S1_ATM_100_Monthly": StrategySpec("S1_ATM_100_Monthly", "atm", 1.0),
    "S2_Delta30_100_Monthly": StrategySpec("S2_Delta30_100_Monthly", "delta30", 1.0),
    "S3_Delta30_50_Monthly": StrategySpec("S3_Delta30_50_Monthly", "delta30", 0.5),
    "S4_OTM5_100_Monthly": StrategySpec("S4_OTM5_100_Monthly", "otm5", 1.0),
    "S5_IVTiming_ATM_Monthly": StrategySpec("S5_IVTiming_ATM_Monthly", "atm", 1.0, True),
    "S6_IVTiming_OTM5_Monthly": StrategySpec("S6_IVTiming_OTM5_Monthly", "otm5", 1.0, True),
}
