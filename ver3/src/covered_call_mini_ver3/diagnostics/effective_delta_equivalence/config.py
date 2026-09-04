from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path
from typing import Any


EXPERIMENT_ID = "ver3_0_independent_effective_delta_equivalence_diagnostic"
DEFAULT_SAMPLE_START = "2022-09-19"
DEFAULT_SAMPLE_END = "2026-05-27"
DEFAULT_TARGET_EFFECTIVE_DELTA = 0.72
DEFAULT_TARGET_ETFS = ("510300", "510050")
DEFAULT_GROWTH_ETF = "159915"
DEFAULT_PHASE_SHIFTS = (0, 5, 10, 15, 20)


@dataclass(frozen=True)
class ImplementationSpec:
    """One pre-registered covered-call implementation for the same entry delta."""

    name: str
    target_call_delta: float
    coverage: float
    role: str
    interpretation: str

    @property
    def expected_overlay_delta(self) -> float:
        return float(self.target_call_delta * self.coverage)

    @property
    def expected_effective_delta(self) -> float:
        return float(1.0 - self.expected_overlay_delta)

    @property
    def coverage_label(self) -> str:
        return f"Q{int(round(self.coverage * 100))}"


@dataclass(frozen=True)
class DiagnosticPaths:
    """Centralized path contract for this sidecar diagnostic."""

    project_root: Path
    ver3_root: Path
    output_root: Path
    ver3_output_index: Path
    static_config_path: Path
    engine_config_path: Path
    etf_prices_path: Path
    options_path: Path
    metadata_path: Path


@dataclass(frozen=True)
class DiagnosticConfig:
    """Runtime configuration for the effective-delta equivalence diagnostic."""

    paths: DiagnosticPaths
    sample_start: str
    sample_end: str
    target_effective_delta: float
    target_etfs: tuple[str, ...]
    include_growth_diagnostic: bool
    implementations: tuple[ImplementationSpec, ...]
    phase_shifts: tuple[int, ...]
    skip_phase_lite: bool
    skip_plots: bool
    write_report: bool
    strict: bool
    rf: float = 0.0

    @property
    def active_etfs(self) -> tuple[str, ...]:
        if self.include_growth_diagnostic and DEFAULT_GROWTH_ETF not in self.target_etfs:
            return tuple(self.target_etfs) + (DEFAULT_GROWTH_ETF,)
        return self.target_etfs


def default_project_root() -> Path:
    return Path(__file__).resolve().parents[6]


def default_ver3_root(project_root: Path) -> Path:
    return project_root / "ver3"


def default_paths(project_root: Path | None = None, ver3_root: Path | None = None, output_dir: Path | None = None) -> DiagnosticPaths:
    root = (project_root or default_project_root()).resolve()
    v3 = (ver3_root or default_ver3_root(root)).resolve()
    out = (output_dir or root / "outputs" / EXPERIMENT_ID).resolve()
    return DiagnosticPaths(
        project_root=root,
        ver3_root=v3,
        output_root=out,
        ver3_output_index=v3 / "outputs" / "ver3_0_effective_delta_equivalence_output_index.md",
        static_config_path=v3 / "configs" / "effective_delta_equivalence" / "ver3_0_effective_delta_equivalence_config.json",
        engine_config_path=root / "configs" / "ver2_downside_protection.yaml",
        etf_prices_path=root / "data" / "raw" / "etf_prices.csv",
        options_path=root / "data" / "source" / "delta_enriched_options.csv",
        metadata_path=root / "data" / "raw" / "etf_metadata.csv",
    )


def default_implementations() -> tuple[ImplementationSpec, ...]:
    return (
        ImplementationSpec("D28_Q100", 0.28, 1.00, "main", "farther OTM full overwrite"),
        ImplementationSpec("D35_Q80", 0.35, 0.80, "main", "middle implementation"),
        ImplementationSpec("D40_Q70", 0.40, 0.70, "current_mainline", "current mainline implementation"),
        ImplementationSpec("D50_Q56", 0.50, 0.56, "diagnostic_only", "closer-delta low-coverage implementation"),
    )


def load_effective_delta_config(
    *,
    project_root: Path | None = None,
    ver3_root: Path | None = None,
    output_dir: Path | None = None,
    target_effective_delta: float | None = None,
    include_growth_diagnostic: bool = False,
    skip_phase_lite: bool = False,
    skip_plots: bool = False,
    write_report: bool = True,
    strict: bool = False,
    rf: float = 0.0,
) -> DiagnosticConfig:
    """Load the static config when present, then apply CLI overrides."""

    paths = default_paths(project_root=project_root, ver3_root=ver3_root, output_dir=output_dir)
    raw: dict[str, Any] = {}
    if paths.static_config_path.exists():
        raw = json.loads(paths.static_config_path.read_text(encoding="utf-8"))

    implementations = tuple(
        ImplementationSpec(
            name=str(item["name"]),
            target_call_delta=float(item["target_call_delta"]),
            coverage=float(item["coverage"]),
            role=str(item.get("role", "main")),
            interpretation=str(item.get("interpretation", "")),
        )
        for item in raw.get("implementations", [])
    ) or default_implementations()

    cfg = DiagnosticConfig(
        paths=paths,
        sample_start=str(raw.get("sample_start", DEFAULT_SAMPLE_START)),
        sample_end=str(raw.get("sample_end", DEFAULT_SAMPLE_END)),
        target_effective_delta=float(raw.get("target_effective_delta", DEFAULT_TARGET_EFFECTIVE_DELTA)),
        target_etfs=tuple(str(code).zfill(6) for code in raw.get("target_etfs", DEFAULT_TARGET_ETFS)),
        include_growth_diagnostic=bool(raw.get("include_growth_diagnostic", include_growth_diagnostic)),
        implementations=implementations,
        phase_shifts=tuple(int(x) for x in raw.get("phase_shifts", DEFAULT_PHASE_SHIFTS)),
        skip_phase_lite=skip_phase_lite,
        skip_plots=skip_plots,
        write_report=write_report,
        strict=strict,
        rf=rf,
    )
    if target_effective_delta is not None:
        cfg = replace(cfg, target_effective_delta=float(target_effective_delta))
    if include_growth_diagnostic:
        cfg = replace(cfg, include_growth_diagnostic=True)
    return cfg


def config_manifest(config: DiagnosticConfig) -> dict[str, Any]:
    """Serialize the run config for reproducibility."""

    return {
        "experiment_id": EXPERIMENT_ID,
        "sample_start": config.sample_start,
        "sample_end": config.sample_end,
        "target_effective_delta": config.target_effective_delta,
        "target_overlay_delta": 1.0 - config.target_effective_delta,
        "target_etfs": list(config.active_etfs),
        "include_growth_diagnostic": config.include_growth_diagnostic,
        "phase_shifts": list(config.phase_shifts),
        "skip_phase_lite": config.skip_phase_lite,
        "skip_plots": config.skip_plots,
        "implementations": [
            {
                "name": item.name,
                "target_call_delta": item.target_call_delta,
                "coverage": item.coverage,
                "expected_overlay_delta": item.expected_overlay_delta,
                "expected_effective_delta": item.expected_effective_delta,
                "role": item.role,
                "interpretation": item.interpretation,
            }
            for item in config.implementations
        ],
        "paths": {
            "project_root": str(config.paths.project_root),
            "ver3_root": str(config.paths.ver3_root),
            "output_root": str(config.paths.output_root),
            "engine_config_path": str(config.paths.engine_config_path),
            "etf_prices_path": str(config.paths.etf_prices_path),
            "options_path": str(config.paths.options_path),
        },
    }
