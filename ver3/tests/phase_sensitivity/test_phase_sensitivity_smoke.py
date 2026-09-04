from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
VER3_SRC = ROOT / "ver3" / "src"
for candidate in (ROOT, VER3_SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from covered_call_mini_ver3.diagnostics.phase_sensitivity.config import (  # noqa: E402
    candidate_portfolios,
    target_sleeves,
)
from covered_call_mini_ver3.diagnostics.phase_sensitivity.phase_grid import (  # noqa: E402
    generate_phase_shift_grid,
    map_phase_to_inception_dates,
)


def test_phase_grid_generation() -> None:
    grid = generate_phase_shift_grid(4, 2)
    assert grid["phase_shift"].tolist() == [0, 2, 4]
    assert grid["phase_id"].tolist() == ["h00", "h02", "h04"]


def test_phase_inception_dates_are_monotonic() -> None:
    dates = pd.date_range("2022-09-19", periods=5, freq="B")
    prices = pd.DataFrame(
        {
            "date": list(dates) * 2,
            "etf_code": ["510300"] * 5 + ["510050"] * 5,
            "adj_close": [1.0] * 10,
        }
    )
    phase = map_phase_to_inception_dates(
        prices,
        generate_phase_shift_grid(4, 1),
        sample_start="2022-09-19",
        etf_codes=["510300", "510050"],
    )
    assert pd.to_datetime(phase["inception_date"]).is_monotonic_increasing


def test_target_constraints() -> None:
    sleeves = target_sleeves()
    names = [s.sleeve_name for s in sleeves]
    assert all("588000" not in name for name in names)
    assert all("TP80" not in name and "TouchK" not in name and "ATM_Q100" not in name for name in names)
    assert any(not s.is_buyhold for s in sleeves)


def test_candidate_weights_sum_to_one() -> None:
    for portfolio in candidate_portfolios():
        assert abs(sum(portfolio.sleeve_weights.values()) - 1.0) < 1e-8
