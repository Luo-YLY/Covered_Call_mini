from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


REQUIRED_SAMPLE_START = "2022-09-30"
REQUIRED_SAMPLE_END = "2026-05-27"
TRADING_DAYS_PER_YEAR = 252.0
INITIAL_NAV = 1.0


@dataclass(frozen=True)
class SleeveSet:
    """Sleeves used by one universe under pure ETF or selected mode."""

    sleeves_by_etf: dict[str, str]


@dataclass(frozen=True)
class UniverseDefinition:
    """Universe-level sleeve map."""

    universe_name: str
    short_name: str
    description: str
    pure_etf: SleeveSet
    selected: SleeveSet


@dataclass(frozen=True)
class WeightScheme:
    """Static ETF weights for one universe."""

    name: str
    weights_by_etf: dict[str, float]
    note: str = ""


@dataclass(frozen=True)
class PortfolioDefinition:
    """Fully specified fixed-weight sleeve portfolio."""

    portfolio_name: str
    universe_name: str
    universe_short: str
    portfolio_type: str
    weight_scheme: str
    sleeve_weights: dict[str, float]
    sleeve_to_etf: dict[str, str]


@dataclass(frozen=True)
class StepBPaths:
    """Input and output paths for Step B."""

    root: Path
    output_root: Path
    main_panel_wide: Path
    main_panel_long: Path
    main_summary: Path
    main_period: Path
    main_daily_nav: Path
    ext_510050_panel_wide: Path
    ext_510050_panel_long: Path
    ext_510050_summary: Path
    ext_510050_period: Path
    ext_510050_daily_nav: Path
    ext_588000_summary: Path
    ext_588000_card: Path
    ext_588000_panel_wide: Path

    @property
    def config_dir(self) -> Path:
        return self.output_root / "config"

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
    def audit_dir(self) -> Path:
        return self.output_root / "audit"

    def ensure_output_dirs(self) -> None:
        for path in [
            self.output_root,
            self.config_dir,
            self.daily_dir,
            self.summary_dir,
            self.attribution_dir,
            self.figure_dir,
            self.report_dir,
            self.audit_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)


def default_paths(root: Path, output_dir: Path | None = None) -> StepBPaths:
    """Return the default Step B path contract."""

    out = output_dir or root / "outputs" / "ver3_0_stepB_fixed_weight_universe_comparison"
    main = root / "outputs" / "ver3_0_stepA_single_etf_sleeves"
    ext_510050 = root / "outputs" / "ver3_0_stepA_extension_510050_sleeve_clarification"
    ext_588000 = root / "outputs" / "ver3_0_stepA_extension_588000_sleeve_clarification"
    return StepBPaths(
        root=root,
        output_root=out,
        main_panel_wide=main / "panel" / "ver3_0_stepA_sleeve_return_panel_wide.csv",
        main_panel_long=main / "panel" / "ver3_0_stepA_sleeve_return_panel_long.csv",
        main_summary=main / "summary" / "ver3_0_stepA_single_etf_sleeve_summary.csv",
        main_period=main / "period" / "ver3_0_stepA_single_etf_period_attribution.csv",
        main_daily_nav=main / "daily" / "ver3_0_stepA_single_etf_sleeve_daily_nav.csv",
        ext_510050_panel_wide=ext_510050 / "panel" / "ver3_0_stepA_extension_510050_sleeve_return_panel_wide.csv",
        ext_510050_panel_long=ext_510050 / "panel" / "ver3_0_stepA_extension_510050_sleeve_return_panel_long.csv",
        ext_510050_summary=ext_510050 / "summary" / "ver3_0_stepA_extension_510050_sleeve_summary.csv",
        ext_510050_period=ext_510050 / "period" / "ver3_0_stepA_extension_510050_period_attribution.csv",
        ext_510050_daily_nav=ext_510050 / "daily" / "ver3_0_stepA_extension_510050_sleeve_daily_nav.csv",
        ext_588000_summary=ext_588000 / "summary" / "ver3_0_stepA_extension_588000_sleeve_summary.csv",
        ext_588000_card=ext_588000 / "cards" / "588000_sleeve_card.md",
        ext_588000_panel_wide=ext_588000 / "panel" / "ver3_0_stepA_extension_588000_sleeve_return_panel_wide.csv",
    )


def universe_definitions() -> dict[str, UniverseDefinition]:
    """Return the two long-sample universes used by Step B."""

    return {
        "A": UniverseDefinition(
            universe_name="Main Growth-Diversified Universe",
            short_name="A",
            description="510300 positive-carry core, 510500 pure ETF growth diversifier, 159915 defensive growth overlay.",
            pure_etf=SleeveSet(
                {
                    "510300": "510300_ETF_BuyHold",
                    "510500": "510500_ETF_BuyHold",
                    "159915": "159915_ETF_BuyHold",
                }
            ),
            selected=SleeveSet(
                {
                    "510300": "510300_DTE30_D40_Q70_Hold",
                    "510500": "510500_ETF_BuyHold",
                    "159915": "159915_DTE30_OTM5up_Q50_Hold",
                }
            ),
        ),
        "B": UniverseDefinition(
            universe_name="Alternative Defensive-Income Universe",
            short_name="B",
            description="510300 and 510050 dual large-cap covered-call cores plus 159915 defensive growth overlay.",
            pure_etf=SleeveSet(
                {
                    "510300": "510300_ETF_BuyHold",
                    "510050": "510050_ETF_BuyHold",
                    "159915": "159915_ETF_BuyHold",
                }
            ),
            selected=SleeveSet(
                {
                    "510300": "510300_DTE30_D40_Q70_Hold",
                    "510050": "510050_DTE30_D40_Q70_Hold",
                    "159915": "159915_DTE30_OTM5up_Q50_Hold",
                }
            ),
        ),
    }


def weight_schemes() -> dict[str, dict[str, WeightScheme]]:
    """Return fixed weights by universe."""

    return {
        "A": {
            "50_30_20": WeightScheme("50_30_20", {"510300": 0.50, "510500": 0.30, "159915": 0.20}),
            "70_20_10": WeightScheme("70_20_10", {"510300": 0.70, "510500": 0.20, "159915": 0.10}),
            "40_40_20": WeightScheme(
                "40_40_20",
                {"510300": 0.40, "510500": 0.40, "159915": 0.20},
                "A-side comparator; the dual-core economic interpretation mainly belongs to Universe B.",
            ),
        },
        "B": {
            "50_30_20": WeightScheme("50_30_20", {"510300": 0.50, "510050": 0.30, "159915": 0.20}),
            "70_20_10": WeightScheme("70_20_10", {"510300": 0.70, "510050": 0.20, "159915": 0.10}),
            "40_40_20": WeightScheme(
                "40_40_20",
                {"510300": 0.40, "510050": 0.40, "159915": 0.20},
                "Dual large-cap covered-call core.",
            ),
        },
    }


def sleeve_column(etf_code: str, sleeve_name: str) -> str:
    """Return the standardized wide-panel daily return column name."""

    return f"{etf_code}__{sleeve_name}__daily_return"


def sleeve_key(etf_code: str, sleeve_name: str) -> str:
    """Return the standardized sleeve key without metric suffix."""

    return f"{etf_code}__{sleeve_name}"


def portfolio_definitions() -> list[PortfolioDefinition]:
    """Build all fixed-weight portfolio definitions."""

    portfolios: list[PortfolioDefinition] = []
    universes = universe_definitions()
    weights = weight_schemes()
    for universe_key, universe in universes.items():
        for scheme_name, scheme in weights[universe_key].items():
            for portfolio_type, sleeve_set in [("Pure_ETF", universe.pure_etf), ("Selected", universe.selected)]:
                sleeve_weights: dict[str, float] = {}
                sleeve_to_etf: dict[str, str] = {}
                for etf_code, weight in scheme.weights_by_etf.items():
                    sleeve_name = sleeve_set.sleeves_by_etf[etf_code]
                    key = sleeve_key(etf_code, sleeve_name)
                    sleeve_weights[key] = float(weight)
                    sleeve_to_etf[key] = etf_code
                portfolios.append(
                    PortfolioDefinition(
                        portfolio_name=f"{universe_key}_{portfolio_type}_{scheme_name}",
                        universe_name=universe.universe_name,
                        universe_short=universe.short_name,
                        portfolio_type=portfolio_type,
                        weight_scheme=scheme_name,
                        sleeve_weights=sleeve_weights,
                        sleeve_to_etf=sleeve_to_etf,
                    )
                )
    return portfolios


def forbidden_main_sleeve_tokens() -> tuple[str, ...]:
    """Tokens that should not appear in selected main portfolios."""

    return ("Q100", "ATM_Q100", "TP80", "TouchK", "588000")
