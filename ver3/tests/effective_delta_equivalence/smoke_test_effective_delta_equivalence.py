from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd


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


def main() -> None:
    config = load_effective_delta_config(project_root=ROOT, ver3_root=ROOT / "ver3", skip_phase_lite=True, skip_plots=True)
    grid = build_effective_delta_implementation_grid(config)
    target = build_target_etf_table(config)
    assert tuple(grid["implementation_name"]) == PREREGISTERED_NAMES
    assert grid["expected_overlay_delta"].sub(0.28).abs().le(1e-10).all()
    assert grid["expected_effective_delta"].sub(0.72).abs().le(1e-10).all()
    assert "588000" not in set(target["etf_code"])

    output_root = config.paths.output_root
    option_detail = output_root / "runs" / "ver3_0_effective_delta_option_selection_detail.csv"
    if option_detail.exists():
        df = pd.read_csv(option_detail)
        assert not df.empty
        assert df["actual_effective_delta"].notna().any()

    print("Effective-delta equivalence smoke test passed.")


if __name__ == "__main__":
    main()
