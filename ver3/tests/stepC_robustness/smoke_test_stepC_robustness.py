from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
VER3_SRC = ROOT / "ver3" / "src"
for item in (ROOT, VER3_SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from covered_call_mini_ver3.stepC_robustness.config import candidate_specs, default_paths  # noqa: E402
from covered_call_mini_ver3.stepC_robustness.cost_sensitivity import evaluate_cost_sensitivity  # noqa: E402
from covered_call_mini_ver3.stepC_robustness.event_windows import detect_extreme_event_windows, evaluate_event_exclusion  # noqa: E402
from covered_call_mini_ver3.stepC_robustness.io import load_stepC_inputs  # noqa: E402
from covered_call_mini_ver3.stepC_robustness.portfolio import align_candidate_sample, build_nav_and_drawdown, compute_candidate_daily_returns  # noqa: E402
from covered_call_mini_ver3.stepC_robustness.rolling import compute_rolling_metrics  # noqa: E402


def main() -> None:
    paths = default_paths(ROOT, ROOT / "ver3")
    candidates = candidate_specs()

    assert all(abs(sum(item.sleeve_weights.values()) - 1.0) < 1e-10 for item in candidates)
    assert "588000" not in " ".join(" ".join(item.sleeve_weights) for item in candidates)
    assert paths.output_root == ROOT / "outputs" / "ver3_0_stepC_robustness_stability_diagnostics"
    assert paths.ver3_output_index == ROOT / "ver3" / "outputs" / "ver3_0_stepC_output_index.md"

    inputs = load_stepC_inputs(paths)
    sample = align_candidate_sample(inputs.return_panel, candidates)
    assert sample["date"].min() == pd.Timestamp("2022-09-19")
    assert sample["date"].max() == pd.Timestamp("2026-05-27")

    returns = compute_candidate_daily_returns(sample, inputs.option_leg_panel, candidates)
    nav, drawdown = build_nav_and_drawdown(returns)
    assert nav.groupby("portfolio_name")["date"].count().nunique() == 1
    assert (drawdown["drawdown_magnitude"].astype(float) >= -1e-12).all()

    events = detect_extreme_event_windows(returns, top_n=2, radius_days=3)
    event_summary = evaluate_event_exclusion(returns, events)
    assert not events.empty
    assert not event_summary.empty

    rolling = compute_rolling_metrics(returns, 252)
    assert not rolling.empty

    from covered_call_mini_ver3.stepC_robustness.config import cost_scenarios

    cost_summary, robustness = evaluate_cost_sensitivity(returns, cost_scenarios([0, 5]))
    assert not cost_summary.empty
    assert not robustness.empty
    assert cost_summary["approximation_note"].astype(str).str.contains("未伪造").any()

    print("Step C smoke test passed.")


if __name__ == "__main__":
    main()
