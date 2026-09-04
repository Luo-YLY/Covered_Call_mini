from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
VER3_SRC = ROOT / "ver3" / "src"
for item in (ROOT, VER3_SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from covered_call_mini_ver3.stepB_plus.config import default_paths, universe_specs  # noqa: E402
from covered_call_mini_ver3.stepB_plus.io import load_stepB_plus_inputs, merge_required_sleeve_returns  # noqa: E402
from covered_call_mini_ver3.stepB_plus.optimizer import generate_weight_grid, select_best_by_drawdown_target  # noqa: E402


def main() -> None:
    paths = default_paths(ROOT, ROOT / "ver3")
    universes = universe_specs()

    grid = generate_weight_grid(("510300", "510500", "159915"), 0.1, 0.0, 0.8)
    weight_cols = [c for c in grid.columns if c.startswith("weight_") and c not in {"weight_sum", "weight_vector_key"}]
    assert not grid.empty
    assert (grid[weight_cols].sum(axis=1).sub(1.0).abs() < 1e-10).all()
    assert ((grid[weight_cols] >= -1e-10) & (grid[weight_cols] <= 0.8 + 1e-10)).all().all()

    impossible = pd.DataFrame(
        {
            "universe_short": ["A"],
            "universe_name": ["test"],
            "constraint_set": ["default"],
            "grid_step": [0.1],
            "lower_bound": [0.05],
            "upper_bound": [0.7],
            "max_drawdown": [0.5],
            "sharpe_daily_mean": [0.1],
            "annualized_return_cagr": [0.02],
            "annualized_volatility": [0.1],
            "calmar_ratio": [0.04],
            "sortino_ratio": [0.2],
            "final_nav": [1.0],
            "weight_510300": [0.5],
            "weight_510500": [0.3],
            "weight_159915": [0.2],
            "weight_vector_key": ["51030050_51050030_15991520"],
        }
    )
    best = select_best_by_drawdown_target(impossible, d_star_list=(0.18,))
    assert len(best) == 1
    assert not bool(best["feasible"].iloc[0])
    assert best["frontier_status"].iloc[0] == "infeasible"

    text = " ".join(f"{etf} {sleeve}" for universe in universes.values() for etf, sleeve in universe.sleeves_by_etf.items())
    assert "588000" not in text

    assert paths.output_root == ROOT / "outputs" / "ver3_0_stepB_plus_mdd_constrained_sharpe_frontier"
    assert paths.ver3_output_index == ROOT / "ver3" / "outputs" / "ver3_0_stepB_plus_output_index.md"

    inputs = load_stepB_plus_inputs(paths)
    sample = merge_required_sleeve_returns(inputs.return_panel, universes, sample_start="2022-09-19", sample_end="2026-05-27")
    assert not sample.empty
    assert sample["date"].min() == pd.Timestamp("2022-09-19")
    assert sample["date"].max() == pd.Timestamp("2026-05-27")

    print("Step B+ smoke test passed.")


if __name__ == "__main__":
    main()
