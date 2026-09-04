from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


EXPERIMENT_ID = "ver3_0_stepC_robustness_stability_diagnostics"
TARGET_SAMPLE_START = "2022-09-30"
TARGET_SAMPLE_END = "2026-05-27"
INITIAL_NAV = 1.0


@dataclass(frozen=True)
class CandidateSpec:
    """One Step C representative candidate portfolio."""

    portfolio_name: str
    source_portfolio_name: str
    universe_short: str
    role: str
    sleeve_weights: dict[str, float]


@dataclass(frozen=True)
class FixedBaselineSpec:
    """One fixed-weight Step B baseline used for interpretation."""

    portfolio_name: str
    universe_short: str
    role: str


@dataclass(frozen=True)
class EventWindowSpec:
    """Manual event window definition."""

    event_name: str
    start_date: str
    end_date: str
    event_type: str
    description: str


@dataclass(frozen=True)
class CostScenario:
    """Additional option-leg cost scenario in annualized bps."""

    cost_scenario: str
    extra_cost_bps: float


@dataclass(frozen=True)
class StepCPaths:
    """Path contract for Step C."""

    project_root: Path
    ver3_root: Path
    output_root: Path
    stepB_plus_frontier_default: Path
    stepB_plus_frontier_relaxed: Path
    stepB_plus_best_weights: Path
    stepB_plus_baseline_comparison: Path
    stepB_plus_universe_comparison: Path
    stepB_plus_daily_returns: Path
    stepB_plus_daily_nav: Path
    stepB_plus_drawdowns: Path
    stepB_plus_option_contribution: Path
    stepB_plus_risk_contribution: Path
    stepB_summary: Path
    stepB_selected_vs_pure: Path
    stepB_weight_map: Path
    stepB_daily_returns: Path
    main_panel_wide: Path
    main_panel_long: Path
    main_daily_nav: Path
    ext_510050_panel_wide: Path
    ext_510050_panel_long: Path
    ext_510050_daily_nav: Path
    v31_selected_sleeve_daily_panel: Path

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
    def events_dir(self) -> Path:
        return self.output_root / "events"

    @property
    def rolling_dir(self) -> Path:
        return self.output_root / "rolling"

    @property
    def cost_dir(self) -> Path:
        return self.output_root / "cost"

    @property
    def sensitivity_dir(self) -> Path:
        return self.output_root / "sensitivity"

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
        return self.ver3_root / "outputs" / "ver3_0_stepC_output_index.md"

    def ensure_output_dirs(self) -> None:
        for path in [
            self.output_root,
            self.config_dir,
            self.daily_dir,
            self.summary_dir,
            self.events_dir,
            self.rolling_dir,
            self.cost_dir,
            self.sensitivity_dir,
            self.attribution_dir,
            self.figure_dir,
            self.report_dir,
            self.ver3_output_index.parent,
        ]:
            path.mkdir(parents=True, exist_ok=True)


def default_paths(project_root: Path, ver3_root: Path | None = None, output_dir: Path | None = None) -> StepCPaths:
    """Build the default Step C path contract."""

    ver3 = ver3_root or project_root / "ver3"
    output_root = output_dir or project_root / "outputs" / EXPERIMENT_ID
    step_b_plus = project_root / "outputs" / "ver3_0_stepB_plus_mdd_constrained_sharpe_frontier"
    step_b = project_root / "outputs" / "ver3_0_stepB_fixed_weight_universe_comparison"
    main = project_root / "outputs" / "ver3_0_stepA_single_etf_sleeves"
    ext_510050 = project_root / "outputs" / "ver3_0_stepA_extension_510050_sleeve_clarification"
    v31_target_delta = project_root / "outputs" / "ver3_1_effective_zone_target_delta"
    return StepCPaths(
        project_root=project_root,
        ver3_root=ver3,
        output_root=output_root,
        stepB_plus_frontier_default=step_b_plus / "summary" / "ver3_0_stepB_plus_frontier_summary_default.csv",
        stepB_plus_frontier_relaxed=step_b_plus / "summary" / "ver3_0_stepB_plus_frontier_summary_relaxed.csv",
        stepB_plus_best_weights=step_b_plus / "summary" / "ver3_0_stepB_plus_best_weights_by_drawdown_target.csv",
        stepB_plus_baseline_comparison=step_b_plus / "summary" / "ver3_0_stepB_plus_comparison_vs_fixed_weight_baselines.csv",
        stepB_plus_universe_comparison=step_b_plus / "summary" / "ver3_0_stepB_plus_universeA_vs_universeB_frontier_comparison.csv",
        stepB_plus_daily_returns=step_b_plus / "daily" / "ver3_0_stepB_plus_best_portfolio_daily_returns.csv",
        stepB_plus_daily_nav=step_b_plus / "daily" / "ver3_0_stepB_plus_best_portfolio_daily_nav.csv",
        stepB_plus_drawdowns=step_b_plus / "daily" / "ver3_0_stepB_plus_best_portfolio_drawdowns.csv",
        stepB_plus_option_contribution=step_b_plus / "attribution" / "ver3_0_stepB_plus_option_leg_contribution.csv",
        stepB_plus_risk_contribution=step_b_plus / "attribution" / "ver3_0_stepB_plus_risk_contribution.csv",
        stepB_summary=step_b / "summary" / "ver3_0_stepB_portfolio_summary.csv",
        stepB_selected_vs_pure=step_b / "summary" / "ver3_0_stepB_selected_vs_pure_baseline.csv",
        stepB_weight_map=step_b / "config" / "ver3_0_stepB_portfolio_weight_map.csv",
        stepB_daily_returns=step_b / "daily" / "ver3_0_stepB_portfolio_daily_returns.csv",
        main_panel_wide=main / "panel" / "ver3_0_stepA_sleeve_return_panel_wide.csv",
        main_panel_long=main / "panel" / "ver3_0_stepA_sleeve_return_panel_long.csv",
        main_daily_nav=main / "daily" / "ver3_0_stepA_single_etf_sleeve_daily_nav.csv",
        ext_510050_panel_wide=ext_510050 / "panel" / "ver3_0_stepA_extension_510050_sleeve_return_panel_wide.csv",
        ext_510050_panel_long=ext_510050 / "panel" / "ver3_0_stepA_extension_510050_sleeve_return_panel_long.csv",
        ext_510050_daily_nav=ext_510050 / "daily" / "ver3_0_stepA_extension_510050_sleeve_daily_nav.csv",
        v31_selected_sleeve_daily_panel=v31_target_delta / "daily" / "ver3_1_selected_sleeve_daily_panel.csv",
    )


def candidate_specs() -> list[CandidateSpec]:
    """Return the current Step C representative candidate portfolio."""

    return [
        CandidateSpec(
            portfolio_name="B_v31_D20_51030070_51005014_15991516",
            source_portfolio_name="B_v31_D20_51030070_51005014_15991516",
            universe_short="B",
            role="3.1 主线组合（D20 回撤预算）",
            sleeve_weights={
                "510300__510300_DTE30_D40_Q70_Hold": 0.70,
                "510050__510050_DTE30_D40_Q70_Hold": 0.14,
                "159915__159915_DTE30_D20_Q10_Hold": 0.16,
            },
        ),
    ]


def fixed_baseline_specs() -> list[FixedBaselineSpec]:
    """Return Step B fixed-weight baselines for Step C interpretation."""

    return [
        FixedBaselineSpec("A_Selected_50_30_20", "A", "A 组固定权重主基准"),
        FixedBaselineSpec("A_Selected_70_20_10", "A", "A 组偏防御固定权重基准"),
        FixedBaselineSpec("B_Selected_50_30_20", "B", "B 组固定权重主基准"),
        FixedBaselineSpec("B_Selected_70_20_10", "B", "B 组偏防御固定权重基准"),
    ]


def manual_event_windows() -> list[EventWindowSpec]:
    """Return manually maintained event windows for diagnostics."""

    return [
        EventWindowSpec(
            event_name="2024_09_policy_rebound",
            start_date="2024-09-24",
            end_date="2024-10-08",
            event_type="manual_upside_policy",
            description="2024 年 9 月末至 10 月初政策强反弹窗口。",
        ),
        EventWindowSpec(
            event_name="2024_01_early_year_drawdown",
            start_date="2024-01-02",
            end_date="2024-02-05",
            event_type="manual_downside_market",
            description="2024 年初市场急跌与回撤压力窗口。",
        ),
    ]


def cost_scenarios(extra_bps: list[float] | None = None) -> list[CostScenario]:
    """Return option-leg cost stress scenarios."""

    values = extra_bps if extra_bps is not None else [0.0, 5.0, 10.0, 20.0, 30.0]
    rows = []
    for value in values:
        name = "base" if abs(value) < 1e-12 else f"option_cost_plus_{int(value)}bps"
        rows.append(CostScenario(name, float(value)))
    return rows


def sleeve_return_column(sleeve_key: str) -> str:
    """Return the standardized daily-return column for a sleeve key."""

    return f"{sleeve_key}__daily_return"


def forbidden_main_tokens() -> tuple[str, ...]:
    """Tokens that must not enter the Step C main line."""

    return ("588000", "Q100", "ATM_Q100", "TP80", "TouchK")
