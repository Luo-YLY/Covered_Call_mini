from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
VER3_SRC = ROOT / "ver3" / "src"
for item in (ROOT, VER3_SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from covered_call_mini_ver3.diagnostics.effective_delta_equivalence.config import load_effective_delta_config  # noqa: E402
from covered_call_mini_ver3.diagnostics.effective_delta_equivalence.implementation_grid import (  # noqa: E402
    PREREGISTERED_NAMES,
    build_effective_delta_implementation_grid,
    build_target_etf_table,
)


def test_implementation_grid_is_preregistered() -> None:
    config = load_effective_delta_config(project_root=ROOT, ver3_root=ROOT / "ver3", skip_phase_lite=True, skip_plots=True)
    grid = build_effective_delta_implementation_grid(config)
    assert tuple(grid["implementation_name"]) == PREREGISTERED_NAMES
    assert grid["expected_overlay_delta"].sub(0.28).abs().le(1e-10).all()
    assert grid["expected_effective_delta"].sub(0.72).abs().le(1e-10).all()
    assert grid["coverage"].between(0, 1).all()


def test_target_etfs_exclude_588000_by_default() -> None:
    config = load_effective_delta_config(project_root=ROOT, ver3_root=ROOT / "ver3", skip_phase_lite=True, skip_plots=True)
    target = build_target_etf_table(config)
    assert set(target["etf_code"]) == {"510300", "510050"}
    assert "588000" not in set(target["etf_code"])


def test_output_root_stays_in_root_outputs() -> None:
    config = load_effective_delta_config(project_root=ROOT, ver3_root=ROOT / "ver3", skip_phase_lite=True, skip_plots=True)
    assert config.paths.output_root == ROOT / "outputs" / "ver3_0_independent_effective_delta_equivalence_diagnostic"
    assert config.paths.ver3_output_index == ROOT / "ver3" / "outputs" / "ver3_0_effective_delta_equivalence_output_index.md"
