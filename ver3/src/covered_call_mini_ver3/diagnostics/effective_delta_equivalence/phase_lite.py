from __future__ import annotations

import pandas as pd

from .config import DiagnosticConfig
from .engine_adapter import run_sleeve_engine
from .metrics import compute_actual_effective_delta, compute_performance_metrics
from .option_attribution import compute_mtm_stress, compute_premium_payoff_quality
from .sleeve_runner import build_sleeve_outputs


def run_phase_lite_diagnostic(config: DiagnosticConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rebuild option cycles under a small set of shifted inception dates."""

    if config.skip_phase_lite:
        return _skipped_phase_metrics(config), _skipped_phase_summary(config)

    starts = phase_start_dates(config)
    metric_frames: list[pd.DataFrame] = []
    for _, row in starts.iterrows():
        shift = int(row["phase_shift"])
        start = str(row["phase_start"])
        result = run_sleeve_engine(config, sample_start=start)
        outputs = build_sleeve_outputs(config, result.periods, result.daily_mtm, phase_shift=shift, phase_start=start)
        tracking = compute_actual_effective_delta(outputs.option_selection_detail, config)
        quality = compute_premium_payoff_quality(outputs.option_selection_detail, outputs.daily_nav)
        stress = compute_mtm_stress(outputs.raw_daily_mtm)
        summary = compute_performance_metrics(outputs.daily_nav, tracking, quality, stress, config)
        summary["phase_shift"] = shift
        summary["phase_start"] = start
        metric_frames.append(summary)

    metrics = pd.concat(metric_frames, ignore_index=True) if metric_frames else pd.DataFrame()
    if metrics.empty:
        return metrics, _skipped_phase_summary(config)
    summary_rows = []
    for keys, group in metrics.groupby(["etf_code", "implementation_name"]):
        etf_code, implementation_name = keys
        summary_rows.append(
            {
                "etf_code": etf_code,
                "implementation_name": implementation_name,
                "phase_lite_status": "completed",
                "phase_count": int(group["phase_shift"].nunique()),
                "phase_lite_sharpe_median": float(group["sharpe_daily_mean"].median()),
                "phase_lite_sharpe_std": float(group["sharpe_daily_mean"].std(ddof=1)),
                "phase_lite_mdd_p75": float(group["max_drawdown"].quantile(0.75)),
                "phase_lite_option_leg_median": float(group["option_leg_annualized_pnl_contribution"].median()),
                "phase_lite_tracking_error_abs_median": float(group["effective_delta_tracking_error"].abs().median()),
            }
        )
    return metrics, pd.DataFrame(summary_rows)


def phase_start_dates(config: DiagnosticConfig) -> pd.DataFrame:
    prices = pd.read_csv(config.paths.etf_prices_path, dtype={"etf_code": str}, usecols=["date", "etf_code"])
    prices["etf_code"] = prices["etf_code"].astype(str).str.zfill(6)
    prices["date"] = pd.to_datetime(prices["date"], errors="coerce")
    first_etf = config.active_etfs[0]
    dates = (
        prices[prices["etf_code"].eq(first_etf)]["date"]
        .dropna()
        .sort_values()
        .drop_duplicates()
        .reset_index(drop=True)
    )
    dates = dates[dates.ge(pd.Timestamp(config.sample_start)) & dates.le(pd.Timestamp(config.sample_end))].reset_index(drop=True)
    rows = []
    for shift in config.phase_shifts:
        if shift >= len(dates):
            continue
        rows.append({"phase_shift": int(shift), "phase_start": dates.iloc[int(shift)].date().isoformat()})
    return pd.DataFrame(rows)


def _skipped_phase_metrics(config: DiagnosticConfig) -> pd.DataFrame:
    rows = []
    for etf in config.active_etfs:
        for impl in config.implementations:
            rows.append(
                {
                    "etf_code": etf,
                    "implementation_name": impl.name,
                    "phase_shift": -1,
                    "phase_start": "",
                    "phase_lite_status": "skipped",
                    "note": "phase-lite skipped by CLI flag",
                }
            )
    return pd.DataFrame(rows)


def _skipped_phase_summary(config: DiagnosticConfig) -> pd.DataFrame:
    rows = []
    for etf in config.active_etfs:
        for impl in config.implementations:
            rows.append(
                {
                    "etf_code": etf,
                    "implementation_name": impl.name,
                    "phase_lite_status": "skipped",
                    "phase_count": 0,
                    "phase_lite_sharpe_median": pd.NA,
                    "phase_lite_sharpe_std": pd.NA,
                    "phase_lite_mdd_p75": pd.NA,
                    "phase_lite_option_leg_median": pd.NA,
                    "phase_lite_tracking_error_abs_median": pd.NA,
                }
            )
    return pd.DataFrame(rows)
