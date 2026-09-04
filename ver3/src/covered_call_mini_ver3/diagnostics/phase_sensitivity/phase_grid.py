from __future__ import annotations

import pandas as pd


def generate_phase_shift_grid(max_phase_shift: int, phase_step: int) -> pd.DataFrame:
    """Generate integer trading-day phase shifts."""

    if max_phase_shift < 0:
        raise ValueError("max_phase_shift must be non-negative.")
    if phase_step <= 0:
        raise ValueError("phase_step must be positive.")
    shifts = list(range(0, int(max_phase_shift) + 1, int(phase_step)))
    return pd.DataFrame({"phase_id": [f"h{h:02d}" for h in shifts], "phase_shift": shifts})


def map_phase_to_inception_dates(
    prices: pd.DataFrame,
    phase_grid: pd.DataFrame,
    *,
    sample_start: str,
    etf_codes: list[str],
) -> pd.DataFrame:
    """Map phase shifts to the common ETF trading calendar."""

    p = prices[prices["etf_code"].astype(str).str.zfill(6).isin(etf_codes)].copy()
    p["date"] = pd.to_datetime(p["date"], errors="coerce")
    calendars = []
    for etf_code, group in p.groupby("etf_code"):
        dates = pd.DatetimeIndex(group["date"].dropna().sort_values().unique())
        dates = dates[dates >= pd.Timestamp(sample_start)]
        calendars.append(dates)
    if not calendars:
        raise ValueError("No ETF calendars are available for phase-grid construction.")
    common = calendars[0]
    for cal in calendars[1:]:
        common = common.intersection(cal)
    common = common.sort_values()
    rows: list[dict[str, object]] = []
    for row in phase_grid.itertuples(index=False):
        shift = int(row.phase_shift)
        if shift >= len(common):
            raise ValueError(f"Phase shift {shift} is outside the common trading calendar.")
        rows.append(
            {
                "phase_id": row.phase_id,
                "phase_shift": shift,
                "inception_date": pd.Timestamp(common[shift]).date().isoformat(),
            }
        )
    return pd.DataFrame(rows)
