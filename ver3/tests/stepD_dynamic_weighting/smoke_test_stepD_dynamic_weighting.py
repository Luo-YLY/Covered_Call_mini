from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
VER3_SRC = ROOT / "ver3" / "src"
for item in (ROOT, VER3_SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from covered_call_mini_ver3.stepD_dynamic_weighting.config import default_paths, method_specs, universe_specs  # noqa: E402
from covered_call_mini_ver3.stepD_dynamic_weighting.io import load_stepD_inputs  # noqa: E402
from covered_call_mini_ver3.stepD_dynamic_weighting.portfolio import build_nav_and_drawdown, compute_dynamic_daily_returns  # noqa: E402
from covered_call_mini_ver3.stepD_dynamic_weighting.rebalance import expand_rebalance_weights_to_daily  # noqa: E402
from covered_call_mini_ver3.stepD_dynamic_weighting.signals import build_monthly_rebalance_schedule, compute_rolling_signal_tables  # noqa: E402
from covered_call_mini_ver3.stepD_dynamic_weighting.universe import build_universe_data  # noqa: E402
from covered_call_mini_ver3.stepD_dynamic_weighting.weights import compute_rebalance_weights  # noqa: E402


def main() -> None:
    paths = default_paths(ROOT, ROOT / "ver3")
    assert paths.output_root == ROOT / "outputs" / "ver3_0_stepD_volatility_controlled_dynamic_weighting"
    assert paths.ver3_output_index == ROOT / "ver3" / "outputs" / "ver3_0_stepD_output_index.md"

    inputs = load_stepD_inputs(paths)
    universe = universe_specs()["B"]
    data = build_universe_data(inputs.return_panel, inputs.option_leg_panel, universe)
    assert data.returns["date"].min() == pd.Timestamp("2022-09-19")
    assert data.returns["date"].max() == pd.Timestamp("2026-05-27")
    assert "588000" not in " ".join(asset.sleeve_key for asset in universe.assets)

    schedule = build_monthly_rebalance_schedule(data.returns["date"], 126).head(3)
    assert (pd.to_datetime(schedule["effective_date"]) > pd.to_datetime(schedule["signal_date"])).all()

    vol, cov = compute_rolling_signal_tables(data, schedule)
    assert not vol.empty
    assert not cov.empty
    assert vol["n_window_obs"].eq(126).all()

    method = method_specs(["anchored_inverse_vol"])[0]
    rebalance_weights = compute_rebalance_weights(data, schedule, method)
    assert rebalance_weights.groupby(["strategy_name", "effective_date"])["target_weight"].sum().sub(1.0).abs().max() < 1e-8
    assert rebalance_weights["target_weight"].between(0.05 - 1e-10, 0.70 + 1e-10).all()

    daily_weights = expand_rebalance_weights_to_daily(data, rebalance_weights)
    returns = compute_dynamic_daily_returns(data, daily_weights)
    nav, drawdown = build_nav_and_drawdown(returns)
    assert not returns.empty
    assert (nav["nav"] > 0).all()
    assert (drawdown["drawdown_magnitude"] >= -1e-12).all()

    print("Step D smoke test passed.")


if __name__ == "__main__":
    main()
