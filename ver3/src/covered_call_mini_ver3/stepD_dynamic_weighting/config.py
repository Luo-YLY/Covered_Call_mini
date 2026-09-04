from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


EXPERIMENT_ID = "ver3_0_stepD_volatility_controlled_dynamic_weighting"
TARGET_SAMPLE_START = "2022-09-30"
TARGET_SAMPLE_END = "2026-05-27"
INITIAL_NAV = 1.0

SUPPORTED_LOOKBACKS = (126, 252)
SUPPORTED_METHODS = ("anchored_inverse_vol", "pure_inverse_vol", "rolling_min_variance")
REBALANCE_FREQUENCY = "monthly"
WEIGHT_LOWER_BOUND = 0.05
WEIGHT_UPPER_BOUND = 0.70
TURNOVER_METHOD = "target_weight_change_approximation"
DEFAULT_COST_BPS = (0.0, 5.0, 10.0, 20.0)


@dataclass(frozen=True)
class AssetSpec:
    """One fixed sleeve inside a Step D universe."""

    etf_code: str
    sleeve_name: str
    role: str

    @property
    def sleeve_key(self) -> str:
        return sleeve_key(self.etf_code, self.sleeve_name)

    @property
    def return_column(self) -> str:
        return sleeve_return_column(self.etf_code, self.sleeve_name)


@dataclass(frozen=True)
class UniverseSpec:
    """Portfolio-level dynamic weighting universe."""

    universe_short: str
    universe_name: str
    description: str
    anchor_portfolio_name: str
    anchor_weights: dict[str, float]
    assets: tuple[AssetSpec, ...]

    @property
    def etf_codes(self) -> tuple[str, ...]:
        return tuple(asset.etf_code for asset in self.assets)

    @property
    def sleeves_by_etf(self) -> dict[str, str]:
        return {asset.etf_code: asset.sleeve_name for asset in self.assets}


@dataclass(frozen=True)
class MethodSpec:
    """One dynamic weighting method."""

    method_name: str
    method_label: str
    description: str


@dataclass(frozen=True)
class StaticBaselineSpec:
    """One static baseline used in Step D comparisons."""

    portfolio_name: str
    universe_short: str
    baseline_source: str
    role: str


@dataclass(frozen=True)
class StepDPaths:
    """Path contract for Step D."""

    project_root: Path
    ver3_root: Path
    output_root: Path
    main_panel_wide: Path
    main_panel_long: Path
    main_daily_nav: Path
    ext_510050_panel_wide: Path
    ext_510050_panel_long: Path
    ext_510050_daily_nav: Path
    stepB_summary: Path
    stepB_daily_returns: Path
    stepB_weight_map: Path
    stepC_summary: Path
    stepC_daily_returns: Path

    @property
    def config_dir(self) -> Path:
        return self.output_root / "config"

    @property
    def signals_dir(self) -> Path:
        return self.output_root / "signals"

    @property
    def weights_dir(self) -> Path:
        return self.output_root / "weights"

    @property
    def daily_dir(self) -> Path:
        return self.output_root / "daily"

    @property
    def summary_dir(self) -> Path:
        return self.output_root / "summary"

    @property
    def turnover_dir(self) -> Path:
        return self.output_root / "turnover"

    @property
    def cost_dir(self) -> Path:
        return self.output_root / "cost"

    @property
    def attribution_dir(self) -> Path:
        return self.output_root / "attribution"

    @property
    def figure_dir(self) -> Path:
        return self.output_root / "figures"

    @property
    def report_dir(self) -> Path:
        return self.output_root / "reports"

    @property
    def ver3_output_index(self) -> Path:
        return self.ver3_root / "outputs" / "ver3_0_stepD_output_index.md"

    def ensure_output_dirs(self) -> None:
        for path in [
            self.output_root,
            self.config_dir,
            self.signals_dir,
            self.weights_dir,
            self.daily_dir,
            self.summary_dir,
            self.turnover_dir,
            self.cost_dir,
            self.attribution_dir,
            self.figure_dir,
            self.report_dir,
            self.ver3_output_index.parent,
        ]:
            path.mkdir(parents=True, exist_ok=True)


def default_paths(project_root: Path, ver3_root: Path | None = None, output_dir: Path | None = None) -> StepDPaths:
    """Build the default Step D path contract."""

    ver3 = ver3_root or project_root / "ver3"
    output_root = output_dir or project_root / "outputs" / EXPERIMENT_ID
    main = project_root / "outputs" / "ver3_0_stepA_single_etf_sleeves"
    ext_510050 = project_root / "outputs" / "ver3_0_stepA_extension_510050_sleeve_clarification"
    step_b = project_root / "outputs" / "ver3_0_stepB_fixed_weight_universe_comparison"
    step_c = project_root / "outputs" / "ver3_0_stepC_robustness_stability_diagnostics"
    return StepDPaths(
        project_root=project_root,
        ver3_root=ver3,
        output_root=output_root,
        main_panel_wide=main / "panel" / "ver3_0_stepA_sleeve_return_panel_wide.csv",
        main_panel_long=main / "panel" / "ver3_0_stepA_sleeve_return_panel_long.csv",
        main_daily_nav=main / "daily" / "ver3_0_stepA_single_etf_sleeve_daily_nav.csv",
        ext_510050_panel_wide=ext_510050 / "panel" / "ver3_0_stepA_extension_510050_sleeve_return_panel_wide.csv",
        ext_510050_panel_long=ext_510050 / "panel" / "ver3_0_stepA_extension_510050_sleeve_return_panel_long.csv",
        ext_510050_daily_nav=ext_510050 / "daily" / "ver3_0_stepA_extension_510050_sleeve_daily_nav.csv",
        stepB_summary=step_b / "summary" / "ver3_0_stepB_portfolio_summary.csv",
        stepB_daily_returns=step_b / "daily" / "ver3_0_stepB_portfolio_daily_returns.csv",
        stepB_weight_map=step_b / "config" / "ver3_0_stepB_portfolio_weight_map.csv",
        stepC_summary=step_c / "summary" / "ver3_0_stepC_candidate_full_sample_summary.csv",
        stepC_daily_returns=step_c / "daily" / "ver3_0_stepC_candidate_daily_returns.csv",
    )


def universe_specs() -> dict[str, UniverseSpec]:
    """Return the fixed sleeve universes requested for Step D."""

    return {
        "A": UniverseSpec(
            universe_short="A",
            universe_name="Main Growth-Diversified Universe",
            description="510300 covered-call core, 510500 pure ETF diversifier, 159915 covered-call growth sleeve.",
            anchor_portfolio_name="A_Selected_50_30_20",
            anchor_weights={"510300": 0.50, "510500": 0.30, "159915": 0.20},
            assets=(
                AssetSpec("510300", "510300_DTE30_D40_Q70_Hold", "large_cap_covered_call_core"),
                AssetSpec("510500", "510500_ETF_BuyHold", "mid_cap_pure_etf_diversifier"),
                AssetSpec("159915", "159915_DTE30_OTM5up_Q50_Hold", "growth_covered_call_overlay"),
            ),
        ),
        "B": UniverseSpec(
            universe_short="B",
            universe_name="Alternative Defensive-Income Universe",
            description="510300 and 510050 large-cap covered-call cores plus 159915 covered-call growth sleeve.",
            anchor_portfolio_name="B_default_D20",
            anchor_weights={"510300": 0.70, "510050": 0.12, "159915": 0.18},
            assets=(
                AssetSpec("510300", "510300_DTE30_D40_Q70_Hold", "large_cap_covered_call_core"),
                AssetSpec("510050", "510050_DTE30_D40_Q70_Hold", "large_cap_covered_call_core_extension"),
                AssetSpec("159915", "159915_DTE30_OTM5up_Q50_Hold", "growth_covered_call_overlay"),
            ),
        ),
    }


def method_specs(selected: list[str] | None = None) -> list[MethodSpec]:
    """Return dynamic weighting methods in requested order."""

    specs = {
        "anchored_inverse_vol": MethodSpec(
            "anchored_inverse_vol",
            "Anchored inverse volatility",
            "Scale each universe anchor weight by inverse trailing volatility, then normalize inside bounds.",
        ),
        "pure_inverse_vol": MethodSpec(
            "pure_inverse_vol",
            "Pure inverse volatility",
            "Ignore anchor weights and allocate by inverse trailing volatility only, inside bounds.",
        ),
        "rolling_min_variance": MethodSpec(
            "rolling_min_variance",
            "Rolling minimum variance",
            "Long-only rolling minimum-variance allocation using covariance only, no expected returns.",
        ),
    }
    names = selected or list(SUPPORTED_METHODS)
    unsupported = [name for name in names if name not in specs]
    if unsupported:
        raise ValueError(f"Unsupported Step D method(s): {unsupported}")
    return [specs[name] for name in names]


def static_baseline_specs() -> list[StaticBaselineSpec]:
    """Return Step D static baselines."""

    return [
        StaticBaselineSpec("B_default_D20", "B", "stepC_default_candidate", "B main defensive-income anchor"),
        StaticBaselineSpec("B_default_D18", "B", "stepC_default_candidate", "B stricter defensive default"),
        StaticBaselineSpec("B_default_D22", "B", "stepC_default_candidate", "B balanced defensive-growth default"),
        StaticBaselineSpec("B_Selected_50_30_20", "B", "stepB_fixed_weight", "B fixed selected 50/30/20"),
        StaticBaselineSpec("B_Selected_70_20_10", "B", "stepB_fixed_weight", "B fixed selected 70/20/10"),
        StaticBaselineSpec("A_Selected_50_30_20", "A", "stepB_fixed_weight", "A fixed selected 50/30/20 anchor"),
        StaticBaselineSpec("A_default_D25", "A", "stepC_default_candidate", "A growth comparison default"),
        StaticBaselineSpec("A_Selected_70_20_10", "A", "stepB_fixed_weight", "A fixed selected 70/20/10"),
    ]


def parse_lookbacks(text: str | None) -> list[int]:
    """Parse and validate lookback values."""

    values = list(SUPPORTED_LOOKBACKS) if not text else [int(item.strip()) for item in text.split(",") if item.strip()]
    unsupported = [value for value in values if value not in SUPPORTED_LOOKBACKS]
    if unsupported:
        raise ValueError(f"Unsupported lookback(s): {unsupported}; supported values are {SUPPORTED_LOOKBACKS}")
    return values


def parse_methods(text: str | None) -> list[str]:
    """Parse and validate method names."""

    values = list(SUPPORTED_METHODS) if not text else [item.strip() for item in text.split(",") if item.strip()]
    unsupported = [value for value in values if value not in SUPPORTED_METHODS]
    if unsupported:
        raise ValueError(f"Unsupported method(s): {unsupported}; supported values are {SUPPORTED_METHODS}")
    return values


def parse_cost_bps(text: str | None) -> list[float]:
    """Parse rebalance cost bps values."""

    return list(DEFAULT_COST_BPS) if not text else [float(item.strip()) for item in text.split(",") if item.strip()]


def sleeve_key(etf_code: str, sleeve_name: str) -> str:
    """Return the standardized sleeve key."""

    return f"{etf_code}__{sleeve_name}"


def sleeve_return_column(etf_code: str, sleeve_name: str) -> str:
    """Return the standardized daily-return column."""

    return f"{sleeve_key(etf_code, sleeve_name)}__daily_return"


def strategy_name(universe_short: str, method_name: str, lookback: int) -> str:
    """Return a stable dynamic strategy name."""

    return f"{universe_short}_{method_name}_L{int(lookback)}"


def forbidden_main_tokens() -> tuple[str, ...]:
    """Tokens that must not enter the Step D main line."""

    return ("588000", "Q100", "ATM_Q100", "TP80", "TouchK")
