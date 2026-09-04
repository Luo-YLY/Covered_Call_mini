from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .config import PortfolioDefinition, StepBPaths, sleeve_column, sleeve_key


@dataclass(frozen=True)
class StepBInputs:
    """Loaded Step B inputs."""

    return_panel: pd.DataFrame
    option_leg_panel: pd.DataFrame
    sleeve_summary: pd.DataFrame
    period_attribution: pd.DataFrame
    input_files: list[str]
    extension_588000_available: bool


def load_stepB_inputs(paths: StepBPaths) -> StepBInputs:
    """Load all Step B source tables."""

    required = [
        paths.main_panel_wide,
        paths.main_panel_long,
        paths.main_summary,
        paths.main_period,
        paths.main_daily_nav,
        paths.ext_510050_panel_wide,
        paths.ext_510050_panel_long,
        paths.ext_510050_summary,
        paths.ext_510050_period,
        paths.ext_510050_daily_nav,
    ]
    missing = [str(p.relative_to(paths.root)) for p in required if not p.exists()]
    if missing:
        raise FileNotFoundError("Missing Step B inputs:\n" + "\n".join(f"- {p}" for p in missing))
    return StepBInputs(
        return_panel=load_return_panel(paths),
        option_leg_panel=load_option_leg_panel(paths),
        sleeve_summary=load_sleeve_summary(paths),
        period_attribution=load_period_attribution(paths),
        input_files=[str(p.relative_to(paths.root)) for p in required],
        extension_588000_available=paths.ext_588000_summary.exists() or paths.ext_588000_panel_wide.exists(),
    )


def load_return_panel(paths: StepBPaths) -> pd.DataFrame:
    """Load and merge main Step A plus 510050 extension wide return panels."""

    main = _read_date_csv(paths.main_panel_wide)
    ext = _read_date_csv(paths.ext_510050_panel_wide)
    overlap = sorted((set(main.columns) & set(ext.columns)) - {"date"})
    if overlap:
        raise ValueError(f"Overlapping return panel columns are not allowed: {overlap}")
    out = main.merge(ext, on="date", how="outer").sort_values("date").reset_index(drop=True)
    return out


def load_sleeve_summary(paths: StepBPaths) -> pd.DataFrame:
    """Load main and 510050 sleeve summaries."""

    frames = []
    for source, path in [
        ("ver3_0_stepA_single_etf_sleeves", paths.main_summary),
        ("ver3_0_stepA_extension_510050_sleeve_clarification", paths.ext_510050_summary),
    ]:
        df = pd.read_csv(path, dtype={"etf_code": str})
        df.insert(0, "source_experiment", source)
        frames.append(df)
    out = pd.concat(frames, ignore_index=True, sort=False)
    if "sample_scope" in out.columns:
        preferred = out[out["sample_scope"].astype(str).eq("common_portfolio_sample")].copy()
        if not preferred.empty:
            out = preferred
    out["etf_code"] = out["etf_code"].astype(str).str.zfill(6)
    return out.reset_index(drop=True)


def load_period_attribution(paths: StepBPaths) -> pd.DataFrame:
    """Load period attribution tables for traceability."""

    frames = []
    for source, path in [
        ("ver3_0_stepA_single_etf_sleeves", paths.main_period),
        ("ver3_0_stepA_extension_510050_sleeve_clarification", paths.ext_510050_period),
    ]:
        df = pd.read_csv(path, dtype={"etf_code": str})
        df.insert(0, "source_experiment", source)
        frames.append(df)
    out = pd.concat(frames, ignore_index=True, sort=False)
    out["etf_code"] = out["etf_code"].astype(str).str.zfill(6)
    return out


def load_option_leg_panel(paths: StepBPaths) -> pd.DataFrame:
    """Load daily option-leg return panels from Step A daily NAV outputs."""

    frames = []
    for path in [paths.main_daily_nav, paths.ext_510050_daily_nav]:
        df = pd.read_csv(
            path,
            dtype={"etf_code": str},
            usecols=["date", "etf_code", "sleeve_name", "daily_return_option_leg_component"],
        )
        df["date"] = pd.to_datetime(df["date"])
        df["etf_code"] = df["etf_code"].astype(str).str.zfill(6)
        df["column"] = df.apply(lambda r: sleeve_column(r["etf_code"], r["sleeve_name"]), axis=1)
        frames.append(df[["date", "column", "daily_return_option_leg_component"]])
    long = pd.concat(frames, ignore_index=True, sort=False)
    wide = (
        long.pivot_table(
            index="date",
            columns="column",
            values="daily_return_option_leg_component",
            aggfunc="last",
        )
        .sort_index()
        .reset_index()
    )
    wide.columns.name = None
    return wide


def validate_required_sleeves(panel: pd.DataFrame, portfolios: list[PortfolioDefinition]) -> None:
    """Fail fast when required sleeve columns are missing."""

    required = sorted({f"{key}__daily_return" for p in portfolios for key in p.sleeve_weights})
    missing = [col for col in required if col not in panel.columns]
    if missing:
        available = "\n".join(str(col) for col in panel.columns)
        raise ValueError("Missing required sleeve columns:\n" + "\n".join(missing) + "\n\nAvailable columns:\n" + available)


def common_sample_panel(panel: pd.DataFrame, portfolios: list[PortfolioDefinition]) -> pd.DataFrame:
    """Return the common non-missing date sample for all required sleeves."""

    required = sorted({f"{key}__daily_return" for p in portfolios for key in p.sleeve_weights})
    sample = panel[["date", *required]].copy()
    sample = sample.dropna(subset=required).sort_values("date").reset_index(drop=True)
    if sample.empty:
        raise ValueError("No common sample remains after aligning required sleeve return columns.")
    return sample


def write_input_manifest(paths: StepBPaths, inputs: StepBInputs) -> None:
    """Write the input manifest."""

    rows = [{"input_file": item} for item in inputs.input_files]
    pd.DataFrame(rows).to_csv(paths.config_dir / "ver3_0_stepB_input_manifest.csv", index=False, encoding="utf-8-sig")


def _read_date_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "date" not in df.columns:
        raise ValueError(f"{path} does not contain a date column.")
    df["date"] = pd.to_datetime(df["date"])
    return df
