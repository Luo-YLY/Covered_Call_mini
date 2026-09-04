from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .config import StepBPlusPaths, UniverseSpec, sleeve_return_column


@dataclass(frozen=True)
class StepBPlusInputs:
    """Loaded Step B+ input tables."""

    return_panel: pd.DataFrame
    option_leg_panel: pd.DataFrame
    baseline_summary: pd.DataFrame
    selected_vs_pure: pd.DataFrame
    universe_comparison: pd.DataFrame
    weight_map: pd.DataFrame
    input_files: list[Path]
    option_leg_method: str


def required_input_files(paths: StepBPlusPaths) -> list[Path]:
    """Return required input files that must exist."""

    return [
        paths.main_panel_wide,
        paths.main_panel_long,
        paths.ext_510050_panel_wide,
        paths.ext_510050_panel_long,
        paths.stepB_summary,
        paths.stepB_selected_vs_pure,
        paths.stepB_universe_comparison,
        paths.stepB_weight_map,
    ]


def load_stepB_plus_inputs(paths: StepBPlusPaths) -> StepBPlusInputs:
    """Load all Step B+ source tables from root outputs."""

    missing = [path for path in required_input_files(paths) if not path.exists()]
    if missing:
        available = sorted(p.name for p in (paths.project_root / "outputs").glob("ver3_0*") if p.is_dir())
        raise FileNotFoundError(
            "Missing Step B+ input files:\n"
            + "\n".join(f"- {p.relative_to(paths.project_root)}" for p in missing)
            + "\n\nAvailable root outputs/ver3_0* directories:\n"
            + "\n".join(f"- {item}" for item in available)
        )
    return_panel = load_sleeve_return_panels(paths)
    option_leg_panel, option_method = load_option_leg_panel(paths)
    return StepBPlusInputs(
        return_panel=return_panel,
        option_leg_panel=option_leg_panel,
        baseline_summary=pd.read_csv(paths.stepB_summary),
        selected_vs_pure=pd.read_csv(paths.stepB_selected_vs_pure),
        universe_comparison=pd.read_csv(paths.stepB_universe_comparison),
        weight_map=pd.read_csv(paths.stepB_weight_map, dtype={"etf_code": str}),
        input_files=required_input_files(paths)
        + [p for p in [paths.main_daily_nav, paths.ext_510050_daily_nav] if p.exists()],
        option_leg_method=option_method,
    )


def load_sleeve_return_panels(paths: StepBPlusPaths) -> pd.DataFrame:
    """Load and merge main Step A plus 510050 wide return panels."""

    main = _read_date_csv(paths.main_panel_wide)
    ext = _read_date_csv(paths.ext_510050_panel_wide)
    overlap = sorted((set(main.columns) & set(ext.columns)) - {"date"})
    if overlap:
        raise ValueError(f"Overlapping sleeve return columns are not allowed: {overlap}")
    return main.merge(ext, on="date", how="outer").sort_values("date").reset_index(drop=True)


def load_option_leg_panel(paths: StepBPlusPaths) -> tuple[pd.DataFrame, str]:
    """Load daily option-leg return columns when available."""

    daily_files = [paths.main_daily_nav, paths.ext_510050_daily_nav]
    if not all(path.exists() for path in daily_files):
        return pd.DataFrame(columns=["date"]), "summary_weighted_option_leg_approximation"
    frames = []
    for path in daily_files:
        df = pd.read_csv(
            path,
            dtype={"etf_code": str},
            usecols=["date", "etf_code", "sleeve_name", "daily_return_option_leg_component"],
        )
        df["date"] = pd.to_datetime(df["date"])
        df["etf_code"] = df["etf_code"].astype(str).str.zfill(6)
        df["column"] = df.apply(lambda r: sleeve_return_column(r["etf_code"], r["sleeve_name"]), axis=1)
        frames.append(df[["date", "column", "daily_return_option_leg_component"]])
    long = pd.concat(frames, ignore_index=True, sort=False)
    wide = (
        long.pivot_table(index="date", columns="column", values="daily_return_option_leg_component", aggfunc="last")
        .sort_index()
        .reset_index()
    )
    wide.columns.name = None
    return wide, "daily_weighted_option_leg_return"


def merge_required_sleeve_returns(
    return_panel: pd.DataFrame,
    universes: dict[str, UniverseSpec],
    *,
    sample_start: str,
    sample_end: str,
) -> pd.DataFrame:
    """Align all universe sleeve returns on the common non-missing sample."""

    required = sorted(
        {
            sleeve_return_column(etf, sleeve)
            for universe in universes.values()
            for etf, sleeve in universe.sleeves_by_etf.items()
        }
    )
    missing = [col for col in required if col not in return_panel.columns]
    if missing:
        raise ValueError("Missing required sleeve return columns:\n" + "\n".join(missing))
    out = return_panel[["date", *required]].copy()
    out["date"] = pd.to_datetime(out["date"])
    out = out[(out["date"] >= pd.Timestamp(sample_start)) & (out["date"] <= pd.Timestamp(sample_end))]
    out = out.dropna(subset=required).sort_values("date").reset_index(drop=True)
    if out.empty:
        raise ValueError("No common Step B+ sample remains after aligning required sleeves.")
    return out


def write_csv(df: pd.DataFrame, path: Path) -> Path:
    """Write non-empty CSV with UTF-8 BOM for Excel-friendly local review."""

    if df.empty:
        raise ValueError(f"Refusing to write empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def _read_date_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "date" not in df.columns:
        raise ValueError(f"{path} does not contain a date column.")
    df["date"] = pd.to_datetime(df["date"])
    return df
