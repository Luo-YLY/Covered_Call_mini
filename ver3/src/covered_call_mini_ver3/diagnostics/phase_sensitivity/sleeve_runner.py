from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from ver2_downside_protection.config import ExperimentConfig
from ver2_downside_protection.data_adapter import Ver2DataBundle

from .config import TargetSleeve
from .engine_adapter import run_buyhold_for_phase, run_covered_call_for_phase


@dataclass(frozen=True)
class SleeveRunArtifacts:
    """Collected outputs from all sleeve phase runs."""

    daily_nav: pd.DataFrame
    daily_returns: pd.DataFrame
    period_map: pd.DataFrame
    run_status: pd.DataFrame


def run_sleeve_for_phase(
    data: Ver2DataBundle,
    base_config: ExperimentConfig,
    sleeve: TargetSleeve,
    phase_row: pd.Series,
    *,
    end_date: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run one sleeve under one shifted inception phase."""

    kwargs = {
        "phase_id": str(phase_row["phase_id"]),
        "phase_shift": int(phase_row["phase_shift"]),
        "inception_date": str(phase_row["inception_date"]),
        "end_date": end_date,
    }
    if sleeve.is_buyhold:
        return run_buyhold_for_phase(data, sleeve, **kwargs)
    return run_covered_call_for_phase(data, base_config, sleeve, **kwargs)


def run_all_phase_sleeves(
    data: Ver2DataBundle,
    base_config: ExperimentConfig,
    target_sleeves: list[TargetSleeve],
    phase_inception: pd.DataFrame,
    *,
    end_date: str,
    strict: bool,
) -> SleeveRunArtifacts:
    """Run every target sleeve across all phase shifts."""

    daily_frames: list[pd.DataFrame] = []
    period_frames: list[pd.DataFrame] = []
    status_rows: list[dict[str, object]] = []
    for phase in phase_inception.itertuples(index=False):
        phase_row = pd.Series(phase._asdict())
        for sleeve in target_sleeves:
            try:
                daily, period = run_sleeve_for_phase(data, base_config, sleeve, phase_row, end_date=end_date)
                daily_frames.append(daily)
                if not period.empty:
                    period_frames.append(period)
                status_rows.append(
                    {
                        "phase_id": phase.phase_id,
                        "phase_shift": int(phase.phase_shift),
                        "inception_date": phase.inception_date,
                        "etf_code": sleeve.etf_code,
                        "sleeve_name": sleeve.sleeve_name,
                        "sleeve_key": sleeve.sleeve_key,
                        "is_buyhold": sleeve.is_buyhold,
                        "status": "success",
                        "phase_engine_support": True,
                        "covered_call_paths_rebuilt_not_sliced": not sleeve.is_buyhold,
                        "daily_rows": len(daily),
                        "period_rows": len(period),
                        "error": "",
                    }
                )
            except Exception as exc:  # noqa: BLE001 - surfaced in run-status artifact
                status_rows.append(
                    {
                        "phase_id": phase.phase_id,
                        "phase_shift": int(phase.phase_shift),
                        "inception_date": phase.inception_date,
                        "etf_code": sleeve.etf_code,
                        "sleeve_name": sleeve.sleeve_name,
                        "sleeve_key": sleeve.sleeve_key,
                        "is_buyhold": sleeve.is_buyhold,
                        "status": "failed",
                        "phase_engine_support": False if not sleeve.is_buyhold else True,
                        "covered_call_paths_rebuilt_not_sliced": False if not sleeve.is_buyhold else True,
                        "daily_rows": 0,
                        "period_rows": 0,
                        "error": str(exc),
                    }
                )
                if strict:
                    raise
    if not daily_frames:
        raise ValueError("No successful sleeve phase runs were produced.")
    daily_nav = pd.concat(daily_frames, ignore_index=True).sort_values(
        ["phase_shift", "etf_code", "sleeve_name", "date"]
    )
    daily_returns = daily_nav[
        [
            "date",
            "phase_id",
            "phase_shift",
            "inception_date",
            "etf_code",
            "sleeve_name",
            "sleeve_key",
            "daily_return_total",
            "daily_return_underlying_component",
            "daily_return_option_leg_component",
            "option_leg_pnl",
        ]
    ].copy()
    period_map = (
        pd.concat(period_frames, ignore_index=True).sort_values(["phase_shift", "sleeve_key", "rebalance_date"])
        if period_frames
        else pd.DataFrame()
    )
    return SleeveRunArtifacts(
        daily_nav=daily_nav.reset_index(drop=True),
        daily_returns=daily_returns.reset_index(drop=True),
        period_map=period_map.reset_index(drop=True),
        run_status=pd.DataFrame(status_rows),
    )
