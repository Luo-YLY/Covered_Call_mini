from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


EXPERIMENT_ID = "ver3_0_stepB_plus_mdd_constrained_sharpe_frontier"
TARGET_SAMPLE_START = "2022-09-30"
TARGET_SAMPLE_END = "2026-05-27"
INITIAL_NAV = 1.0
D_STAR_LIST = (0.18, 0.20, 0.22, 0.25, 0.30)


@dataclass(frozen=True)
class UniverseSpec:
    """Selected sleeve set for one long-sample universe."""

    universe_short: str
    universe_name: str
    description: str
    sleeves_by_etf: dict[str, str]

    @property
    def etf_codes(self) -> tuple[str, ...]:
        return tuple(self.sleeves_by_etf)


@dataclass(frozen=True)
class ConstraintSpec:
    """Static long-only weight bounds for one robustness set."""

    name: str
    lower_bound: float
    upper_bound: float
    is_primary: bool


@dataclass(frozen=True)
class StepBPlusPaths:
    """Input and output paths for Step B+."""

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
    stepB_selected_vs_pure: Path
    stepB_universe_comparison: Path
    stepB_weight_map: Path

    @property
    def config_dir(self) -> Path:
        return self.output_root / "config"

    @property
    def grid_dir(self) -> Path:
        return self.output_root / "grid"

    @property
    def daily_dir(self) -> Path:
        return self.output_root / "daily"

    @property
    def summary_dir(self) -> Path:
        return self.output_root / "summary"

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
        return self.ver3_root / "outputs" / "ver3_0_stepB_plus_output_index.md"

    def ensure_output_dirs(self) -> None:
        for path in [
            self.output_root,
            self.config_dir,
            self.grid_dir,
            self.daily_dir,
            self.summary_dir,
            self.attribution_dir,
            self.figure_dir,
            self.report_dir,
            self.ver3_output_index.parent,
        ]:
            path.mkdir(parents=True, exist_ok=True)


def default_paths(
    project_root: Path,
    ver3_root: Path | None = None,
    output_dir: Path | None = None,
) -> StepBPlusPaths:
    """Build the default Step B+ path contract."""

    ver3 = ver3_root or project_root / "ver3"
    output_root = output_dir or project_root / "outputs" / EXPERIMENT_ID
    main = project_root / "outputs" / "ver3_0_stepA_single_etf_sleeves"
    ext_510050 = project_root / "outputs" / "ver3_0_stepA_extension_510050_sleeve_clarification"
    step_b = project_root / "outputs" / "ver3_0_stepB_fixed_weight_universe_comparison"
    return StepBPlusPaths(
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
        stepB_selected_vs_pure=step_b / "summary" / "ver3_0_stepB_selected_vs_pure_baseline.csv",
        stepB_universe_comparison=step_b / "summary" / "ver3_0_stepB_universeA_vs_universeB_comparison.csv",
        stepB_weight_map=step_b / "config" / "ver3_0_stepB_portfolio_weight_map.csv",
    )


def universe_specs() -> dict[str, UniverseSpec]:
    """Return long-sample selected sleeve universes."""

    return {
        "A": UniverseSpec(
            universe_short="A",
            universe_name="Main Growth-Diversified Universe",
            description="510300 positive-carry core, 510500 pure ETF growth diversifier, 159915 defensive growth overlay.",
            sleeves_by_etf={
                "510300": "510300_DTE30_D40_Q70_Hold",
                "510500": "510500_ETF_BuyHold",
                "159915": "159915_DTE30_OTM5up_Q50_Hold",
            },
        ),
        "B": UniverseSpec(
            universe_short="B",
            universe_name="Alternative Defensive-Income Universe",
            description="510300 and 510050 dual large-cap covered-call cores plus 159915 defensive growth overlay.",
            sleeves_by_etf={
                "510300": "510300_DTE30_D40_Q70_Hold",
                "510050": "510050_DTE30_D40_Q70_Hold",
                "159915": "159915_DTE30_OTM5up_Q50_Hold",
            },
        ),
    }


def constraint_specs(selected: str = "both") -> list[ConstraintSpec]:
    """Return requested constraint sets."""

    specs = [
        ConstraintSpec("default", 0.05, 0.70, True),
        ConstraintSpec("relaxed", 0.00, 0.80, False),
    ]
    if selected == "both":
        return specs
    names = {item.strip() for item in selected.split(",")}
    out = [spec for spec in specs if spec.name in names]
    if not out:
        raise ValueError(f"No supported constraint set selected: {selected}")
    return out


def sleeve_key(etf_code: str, sleeve_name: str) -> str:
    """Return the standardized sleeve key without metric suffix."""

    return f"{etf_code}__{sleeve_name}"


def sleeve_return_column(etf_code: str, sleeve_name: str) -> str:
    """Return the standardized daily-return column."""

    return f"{sleeve_key(etf_code, sleeve_name)}__daily_return"


def forbidden_main_tokens() -> tuple[str, ...]:
    """Tokens forbidden in the Step B+ main frontier."""

    return ("588000", "Q100", "ATM_Q100", "TP80", "TouchK")
