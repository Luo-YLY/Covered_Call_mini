from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .config import StepDPaths, sleeve_return_column


@dataclass(frozen=True)
class StepDInputs:
    """Loaded Step D source tables."""

    return_panel: pd.DataFrame
    option_leg_panel: pd.DataFrame
    stepB_summary: pd.DataFrame
    stepB_daily_returns: pd.DataFrame
    stepB_weight_map: pd.DataFrame
    stepC_summary: pd.DataFrame
    stepC_daily_returns: pd.DataFrame
    input_files: list[Path]
    option_leg_method: str


def required_input_files(paths: StepDPaths) -> list[Path]:
    """Return required Step D input files."""

    return [
        paths.main_panel_wide,
        paths.main_panel_long,
        paths.main_daily_nav,
        paths.ext_510050_panel_wide,
        paths.ext_510050_panel_long,
        paths.ext_510050_daily_nav,
        paths.stepB_summary,
        paths.stepB_daily_returns,
        paths.stepB_weight_map,
        paths.stepC_summary,
        paths.stepC_daily_returns,
    ]


def load_stepD_inputs(paths: StepDPaths) -> StepDInputs:
    """Load all Step D inputs and fail fast on missing files."""

    missing = [path for path in required_input_files(paths) if not path.exists()]
    if missing:
        available = sorted(p.name for p in (paths.project_root / "outputs").glob("ver3_0*") if p.is_dir())
        raise FileNotFoundError(
            "Missing Step D input file(s):\n"
            + "\n".join(f"- {path.relative_to(paths.project_root)}" for path in missing)
            + "\n\nAvailable ver3 output directories:\n"
            + "\n".join(f"- {name}" for name in available)
        )

    option_leg_panel, option_method = load_option_leg_panel(paths)
    return StepDInputs(
        return_panel=load_sleeve_return_panels(paths),
        option_leg_panel=option_leg_panel,
        stepB_summary=pd.read_csv(paths.stepB_summary),
        stepB_daily_returns=_read_date_csv(paths.stepB_daily_returns),
        stepB_weight_map=pd.read_csv(paths.stepB_weight_map, dtype={"etf_code": str}),
        stepC_summary=pd.read_csv(paths.stepC_summary),
        stepC_daily_returns=_read_date_csv(paths.stepC_daily_returns),
        input_files=required_input_files(paths),
        option_leg_method=option_method,
    )


def load_sleeve_return_panels(paths: StepDPaths) -> pd.DataFrame:
    """Load and merge Step A main plus 510050 extension return panels."""

    main = _read_date_csv(paths.main_panel_wide)
    ext = _read_date_csv(paths.ext_510050_panel_wide)
    overlap = sorted((set(main.columns) & set(ext.columns)) - {"date"})
    if overlap:
        raise ValueError(f"Step D return panel has overlapping columns: {overlap}")
    return main.merge(ext, on="date", how="outer").sort_values("date").reset_index(drop=True)


def load_option_leg_panel(paths: StepDPaths) -> tuple[pd.DataFrame, str]:
    """Load daily option-leg return columns from Step A daily NAV files."""

    frames = []
    for path in [paths.main_daily_nav, paths.ext_510050_daily_nav]:
        df = pd.read_csv(
            path,
            dtype={"etf_code": str},
            usecols=["date", "etf_code", "sleeve_name", "daily_return_option_leg_component"],
        )
        df["date"] = pd.to_datetime(df["date"])
        df["etf_code"] = df["etf_code"].astype(str).str.zfill(6)
        df["column"] = [sleeve_return_column(etf_code, sleeve_name) for etf_code, sleeve_name in zip(df["etf_code"], df["sleeve_name"])]
        frames.append(df[["date", "column", "daily_return_option_leg_component"]])

    long = pd.concat(frames, ignore_index=True, sort=False)
    wide = (
        long.pivot_table(index="date", columns="column", values="daily_return_option_leg_component", aggfunc="last")
        .sort_index()
        .reset_index()
    )
    wide.columns.name = None
    return wide, "daily_weighted_net_option_leg_return_from_stepA"


def load_static_baseline_daily(inputs: StepDInputs, baseline_names: list[str]) -> pd.DataFrame:
    """Load Step B and Step C static baseline daily returns."""

    step_b = inputs.stepB_daily_returns[inputs.stepB_daily_returns["portfolio_name"].isin(baseline_names)].copy()
    step_b["baseline_source"] = "stepB_fixed_weight"
    step_c = inputs.stepC_daily_returns[inputs.stepC_daily_returns["portfolio_name"].isin(baseline_names)].copy()
    step_c["baseline_source"] = "stepC_default_candidate"
    cols = ["date", "portfolio_name", "universe_short", "portfolio_daily_return", "portfolio_option_leg_return", "baseline_source"]
    out = pd.concat([step_b[cols], step_c[cols]], ignore_index=True, sort=False)
    if out.empty:
        raise ValueError("No static baseline daily returns loaded for Step D.")
    return out.sort_values(["portfolio_name", "date"]).reset_index(drop=True)


def write_csv(df: pd.DataFrame, path: Path) -> Path:
    """Write a non-empty CSV with a stable encoding."""

    if df.empty:
        raise ValueError(f"Refusing to write empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def _read_date_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    return df
