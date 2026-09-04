from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


EXPERIMENT_ID = "ver3_0_independent_phase_sensitivity_diagnostics"
SAMPLE_START = "2022-09-30"
SAMPLE_END = "2026-05-27"
INITIAL_NAV = 1.0
TRADING_DAYS_PER_YEAR = 252.0


@dataclass(frozen=True)
class PhasePaths:
    """Path contract for the independent phase diagnostic."""

    project_root: Path
    ver3_root: Path
    output_root: Path

    @property
    def config_dir(self) -> Path:
        return self.output_root / "config"

    @property
    def phase_runs_dir(self) -> Path:
        return self.output_root / "phase_runs"

    @property
    def daily_dir(self) -> Path:
        return self.output_root / "daily"

    @property
    def summary_dir(self) -> Path:
        return self.output_root / "summary"

    @property
    def cycle_dir(self) -> Path:
        return self.output_root / "cycle"

    @property
    def ensemble_dir(self) -> Path:
        return self.output_root / "ensemble"

    @property
    def figure_dir(self) -> Path:
        return self.output_root / "figures"

    @property
    def report_dir(self) -> Path:
        return self.output_root / "reports"

    @property
    def ver3_output_index(self) -> Path:
        return self.ver3_root / "outputs" / "ver3_0_phase_sensitivity_output_index.md"

    def ensure_output_dirs(self) -> None:
        for path in [
            self.config_dir,
            self.phase_runs_dir,
            self.daily_dir,
            self.summary_dir,
            self.cycle_dir,
            self.ensemble_dir,
            self.figure_dir,
            self.report_dir,
            self.ver3_output_index.parent,
        ]:
            path.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class TargetSleeve:
    """One sleeve included in the phase diagnostic."""

    etf_code: str
    sleeve_name: str
    role: str
    is_buyhold: bool
    strategy_name: str = "BuyHold"
    strategy_kind: str = "buy_hold"
    coverage: float = 0.0
    target_moneyness: float = 0.0
    strategy_family: str = "ETF_BuyHold"

    @property
    def sleeve_key(self) -> str:
        return f"{self.etf_code}__{self.sleeve_name}"


@dataclass(frozen=True)
class CandidatePortfolio:
    """One fixed-weight candidate portfolio tested across phases."""

    portfolio_name: str
    role: str
    sleeve_weights: dict[str, float]
    target_mdd: float


@dataclass(frozen=True)
class PhaseRunConfig:
    """Runtime choices for one phase-sensitivity diagnostic run."""

    max_phase_shift: int = 20
    phase_step: int = 1
    sample_start: str = SAMPLE_START
    sample_end: str = SAMPLE_END
    rf: float = 0.0
    skip_cycle_attribution: bool = False
    skip_ensemble: bool = False
    skip_plots: bool = False
    write_report: bool = True
    strict: bool = False


def default_paths(project_root: Path, ver3_root: Path | None = None, output_dir: Path | None = None) -> PhasePaths:
    """Return the default path contract."""

    ver3 = ver3_root or project_root / "ver3"
    out = output_dir or project_root / "outputs" / EXPERIMENT_ID
    return PhasePaths(project_root=project_root, ver3_root=ver3, output_root=out)


def target_sleeves() -> list[TargetSleeve]:
    """Return the fixed target sleeve list for this independent diagnostic."""

    return [
        TargetSleeve(
            "510300",
            "510300_DTE30_D40_Q70_Hold",
            "Main large-cap positive-carry covered-call core.",
            False,
            "D40_Q70",
            "target_delta",
            0.70,
            0.40,
            "D40",
        ),
        TargetSleeve(
            "510050",
            "510050_DTE30_D40_Q70_Hold",
            "Second large-cap positive-carry covered-call core.",
            False,
            "D40_Q70",
            "target_delta",
            0.70,
            0.40,
            "D40",
        ),
        TargetSleeve(
            "159915",
            "159915_DTE30_OTM5up_Q50_Hold",
            "Defensive growth overlay.",
            False,
            "OTM5_Q50",
            "otm_pct",
            0.50,
            0.05,
            "OTM5_up",
        ),
        TargetSleeve("510500", "510500_ETF_BuyHold", "Mid-cap pure ETF growth-diversification baseline.", True),
        TargetSleeve("510300", "510300_ETF_BuyHold", "Large-cap pure ETF baseline.", True),
        TargetSleeve("510050", "510050_ETF_BuyHold", "Second large-cap pure ETF baseline.", True),
        TargetSleeve("159915", "159915_ETF_BuyHold", "Growth pure ETF baseline.", True),
    ]


def candidate_portfolios() -> list[CandidatePortfolio]:
    """Return the fixed target candidate portfolios."""

    return [
        CandidatePortfolio(
            "B_default_D20",
            "Current main defensive-income candidate.",
            {
                "510300__510300_DTE30_D40_Q70_Hold": 0.70,
                "510050__510050_DTE30_D40_Q70_Hold": 0.15,
                "159915__159915_DTE30_OTM5up_Q50_Hold": 0.15,
            },
            0.20,
        ),
        CandidatePortfolio(
            "B_default_D18",
            "Strict defensive candidate.",
            {
                "510300__510300_DTE30_D40_Q70_Hold": 0.70,
                "510050__510050_DTE30_D40_Q70_Hold": 0.22,
                "159915__159915_DTE30_OTM5up_Q50_Hold": 0.08,
            },
            0.18,
        ),
        CandidatePortfolio(
            "B_default_D22",
            "Balanced defensive-growth candidate.",
            {
                "510300__510300_DTE30_D40_Q70_Hold": 0.68,
                "510050__510050_DTE30_D40_Q70_Hold": 0.09,
                "159915__159915_DTE30_OTM5up_Q50_Hold": 0.23,
            },
            0.22,
        ),
        CandidatePortfolio(
            "A_default_D25",
            "Growth comparison candidate.",
            {
                "510300__510300_DTE30_D40_Q70_Hold": 0.63,
                "510500__510500_ETF_BuyHold": 0.05,
                "159915__159915_DTE30_OTM5up_Q50_Hold": 0.32,
            },
            0.25,
        ),
        CandidatePortfolio(
            "A_Selected_50_30_20",
            "Growth-diversified fixed baseline.",
            {
                "510300__510300_DTE30_D40_Q70_Hold": 0.50,
                "510500__510500_ETF_BuyHold": 0.30,
                "159915__159915_DTE30_OTM5up_Q50_Hold": 0.20,
            },
            0.25,
        ),
    ]


def buyhold_key_for_etf(etf_code: str) -> str:
    """Return the pure ETF sleeve key for an ETF."""

    return f"{etf_code}__{etf_code}_ETF_BuyHold"
