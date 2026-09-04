from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


EXPERIMENT_ID = "ver4_0_single_etf_cycle_cashflow"
TARGET_DTE = 30
MIN_DTE = 20
MAX_DTE = 45
DEFAULT_FIXED_NOTIONAL = 100.0
DEFAULT_RISK_FREE_RATE = 0.02


@dataclass(frozen=True)
class EtfSampleSpec:
    etf_code: str
    sample_start: str
    sample_end: str
    sample_scope: str


ETF_SAMPLE_SPECS: dict[str, EtfSampleSpec] = {
    "510300": EtfSampleSpec("510300", "2022-09-30", "2026-05-27", "main_common_sample"),
    "510050": EtfSampleSpec("510050", "2022-09-30", "2026-05-27", "main_common_sample"),
    "510500": EtfSampleSpec("510500", "2022-09-30", "2026-05-27", "main_common_sample"),
    "159915": EtfSampleSpec("159915", "2022-09-30", "2026-05-27", "main_common_sample"),
    "588000": EtfSampleSpec("588000", "2023-06-05", "2026-05-27", "short_sample_extension"),
}


@dataclass(frozen=True)
class CycleExperimentPaths:
    project_root: Path
    engine_config_path: Path
    etf_prices_path: Path
    option_chain_path: Path
    metadata_path: Path
    output_root: Path


@dataclass(frozen=True)
class CycleExperimentConfig:
    experiment_id: str
    etf: EtfSampleSpec
    paths: CycleExperimentPaths
    target_deltas: tuple[float, ...]
    include_atm: bool
    coverages: tuple[float, ...]
    target_dte: int
    min_dte: int
    max_dte: int
    fixed_notional: float
    risk_free_rate: float
    rolling_cashflow_cycles: int
    cash_yield_targets: tuple[float, ...]
    regime_breaks: tuple[float, ...]
    timing_enabled: bool


def build_cycle_experiment_config(
    project_root: str | Path,
    *,
    etf_code: str,
    fixed_notional: float = DEFAULT_FIXED_NOTIONAL,
    sample_start: str | None = None,
    sample_end: str | None = None,
) -> CycleExperimentConfig:
    """Build an isolated, single-ETF ver4.0 configuration."""

    root = Path(project_root).resolve()
    code = str(etf_code).zfill(6)
    if code not in ETF_SAMPLE_SPECS:
        supported = ", ".join(sorted(ETF_SAMPLE_SPECS))
        raise ValueError(f"Unsupported ETF '{code}'. Supported ETF codes: {supported}")
    if fixed_notional <= 0:
        raise ValueError("fixed_notional must be positive.")

    source = ETF_SAMPLE_SPECS[code]
    etf = EtfSampleSpec(
        etf_code=code,
        sample_start=sample_start or source.sample_start,
        sample_end=sample_end or source.sample_end,
        sample_scope=source.sample_scope,
    )
    output_root = root / "outputs" / EXPERIMENT_ID / code
    paths = CycleExperimentPaths(
        project_root=root,
        engine_config_path=root / "configs" / "ver2_downside_protection.yaml",
        etf_prices_path=root / "data" / "raw" / "etf_prices.csv",
        option_chain_path=root / "data" / "source" / "delta_enriched_options.csv",
        metadata_path=root / "data" / "raw" / "etf_metadata.csv",
        output_root=output_root,
    )
    return CycleExperimentConfig(
        experiment_id=EXPERIMENT_ID,
        etf=etf,
        paths=paths,
        target_deltas=(0.10, 0.20, 0.30, 0.40, 0.50),
        include_atm=True,
        coverages=(1.0,),
        target_dte=TARGET_DTE,
        min_dte=MIN_DTE,
        max_dte=MAX_DTE,
        fixed_notional=float(fixed_notional),
        risk_free_rate=DEFAULT_RISK_FREE_RATE,
        rolling_cashflow_cycles=12,
        cash_yield_targets=(0.02, 0.04, 0.06),
        regime_breaks=(-0.05, 0.05, 0.10),
        timing_enabled=False,
    )


def config_manifest(config: CycleExperimentConfig) -> dict[str, Any]:
    """Return a JSON-safe manifest of the frozen baseline assumptions."""

    raw = asdict(config)
    raw["paths"] = {key: str(value) for key, value in raw["paths"].items()}
    raw["accounting"] = {
        "mode": "fixed_notional_independent_option_cycles",
        "fixed_notional": config.fixed_notional,
        "prior_cycle_pnl_reinvested": False,
        "main_performance_unit": "per_cycle_cashflow_and_return",
        "daily_mtm_role": "within_cycle_risk_diagnostic_only",
        "cagr_role": "not_reported_as_a_primary_metric",
    }
    raw["scope"] = {
        "single_etf_only": True,
        "multi_asset_portfolio": False,
        "dynamic_weighting": False,
        "iv_timing": False,
        "product_selection": "not_run_in_static_baseline",
        "static_grid": "ATM and D10/D20/D30/D40/D50 at Q100 only",
    }
    return raw
