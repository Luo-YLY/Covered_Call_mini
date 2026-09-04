from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .config import StepCPaths, sleeve_return_column


@dataclass(frozen=True)
class StepCInputs:
    """Loaded Step C source tables."""

    stepB_plus_frontier_default: pd.DataFrame
    stepB_plus_frontier_relaxed: pd.DataFrame
    stepB_plus_best_weights: pd.DataFrame
    stepB_plus_baseline_comparison: pd.DataFrame
    stepB_plus_universe_comparison: pd.DataFrame
    stepB_plus_daily_returns: pd.DataFrame
    stepB_plus_daily_nav: pd.DataFrame
    stepB_plus_drawdowns: pd.DataFrame
    stepB_plus_option_contribution: pd.DataFrame
    stepB_plus_risk_contribution: pd.DataFrame
    stepB_summary: pd.DataFrame
    stepB_selected_vs_pure: pd.DataFrame
    stepB_weight_map: pd.DataFrame
    stepB_daily_returns: pd.DataFrame
    return_panel: pd.DataFrame
    option_leg_panel: pd.DataFrame
    input_files: list[Path]
    option_leg_method: str


def required_input_files(paths: StepCPaths) -> list[Path]:
    """Return required Step C input files."""

    return [
        paths.stepB_plus_frontier_default,
        paths.stepB_plus_frontier_relaxed,
        paths.stepB_plus_best_weights,
        paths.stepB_plus_baseline_comparison,
        paths.stepB_plus_universe_comparison,
        paths.stepB_plus_daily_returns,
        paths.stepB_plus_daily_nav,
        paths.stepB_plus_drawdowns,
        paths.stepB_plus_option_contribution,
        paths.stepB_plus_risk_contribution,
        paths.stepB_summary,
        paths.stepB_selected_vs_pure,
        paths.stepB_weight_map,
        paths.stepB_daily_returns,
        paths.main_panel_wide,
        paths.main_panel_long,
        paths.ext_510050_panel_wide,
        paths.ext_510050_panel_long,
        paths.v31_selected_sleeve_daily_panel,
    ]


def load_stepC_inputs(paths: StepCPaths) -> StepCInputs:
    """Load all Step C inputs and fail fast on missing files."""

    missing = [path for path in required_input_files(paths) if not path.exists()]
    if missing:
        available = sorted(p.name for p in (paths.project_root / "outputs").glob("ver3_0*") if p.is_dir())
        raise FileNotFoundError(
            "缺少 Step C 输入文件：\n"
            + "\n".join(f"- {p.relative_to(paths.project_root)}" for p in missing)
            + "\n\n当前 outputs/ 下可用的 ver3_0 目录：\n"
            + "\n".join(f"- {name}" for name in available)
        )

    option_leg_panel, option_method = load_option_leg_panel(paths)
    files = required_input_files(paths) + [
        p for p in [paths.main_daily_nav, paths.ext_510050_daily_nav, paths.v31_selected_sleeve_daily_panel] if p.exists()
    ]
    return StepCInputs(
        stepB_plus_frontier_default=pd.read_csv(paths.stepB_plus_frontier_default),
        stepB_plus_frontier_relaxed=pd.read_csv(paths.stepB_plus_frontier_relaxed),
        stepB_plus_best_weights=pd.read_csv(paths.stepB_plus_best_weights, dtype={"etf_code": str}),
        stepB_plus_baseline_comparison=pd.read_csv(paths.stepB_plus_baseline_comparison),
        stepB_plus_universe_comparison=pd.read_csv(paths.stepB_plus_universe_comparison),
        stepB_plus_daily_returns=_read_date_csv(paths.stepB_plus_daily_returns),
        stepB_plus_daily_nav=_read_date_csv(paths.stepB_plus_daily_nav),
        stepB_plus_drawdowns=_read_date_csv(paths.stepB_plus_drawdowns),
        stepB_plus_option_contribution=pd.read_csv(paths.stepB_plus_option_contribution),
        stepB_plus_risk_contribution=pd.read_csv(paths.stepB_plus_risk_contribution),
        stepB_summary=pd.read_csv(paths.stepB_summary),
        stepB_selected_vs_pure=pd.read_csv(paths.stepB_selected_vs_pure),
        stepB_weight_map=pd.read_csv(paths.stepB_weight_map, dtype={"etf_code": str}),
        stepB_daily_returns=_read_date_csv(paths.stepB_daily_returns),
        return_panel=load_sleeve_return_panels(paths),
        option_leg_panel=option_leg_panel,
        input_files=files,
        option_leg_method=option_method,
    )


def load_sleeve_return_panels(paths: StepCPaths) -> pd.DataFrame:
    """Load return panels, with ver3.1 selected sleeves taking precedence."""

    main = _read_date_csv(paths.main_panel_wide)
    ext = _read_date_csv(paths.ext_510050_panel_wide)
    v31 = load_v31_selected_panel(paths.v31_selected_sleeve_daily_panel, "daily_return_total")
    return _merge_panel_prefer_later([main, ext, v31]).sort_values("date").reset_index(drop=True)


def load_option_leg_panel(paths: StepCPaths) -> tuple[pd.DataFrame, str]:
    """Load daily option-leg return columns when Step A daily files are available."""

    daily_files = [paths.main_daily_nav, paths.ext_510050_daily_nav]
    if not all(path.exists() for path in [*daily_files, paths.v31_selected_sleeve_daily_panel]):
        return pd.DataFrame(columns=["date"]), "unavailable"

    frames = []
    for path in daily_files:
        df = pd.read_csv(
            path,
            dtype={"etf_code": str},
            usecols=["date", "etf_code", "sleeve_name", "daily_return_option_leg_component"],
        )
        df["date"] = pd.to_datetime(df["date"])
        df["etf_code"] = df["etf_code"].astype(str).str.zfill(6)
        df["sleeve_key"] = df["etf_code"] + "__" + df["sleeve_name"].astype(str)
        df["column"] = df["sleeve_key"].map(sleeve_return_column)
        frames.append(df[["date", "column", "daily_return_option_leg_component"]])

    long = pd.concat(frames, ignore_index=True, sort=False)
    legacy_wide = (
        long.pivot_table(index="date", columns="column", values="daily_return_option_leg_component", aggfunc="last")
        .sort_index()
        .reset_index()
    )
    legacy_wide.columns.name = None
    v31_wide = load_v31_selected_panel(paths.v31_selected_sleeve_daily_panel, "daily_return_option_leg_component")
    wide = _merge_panel_prefer_later([legacy_wide, v31_wide])
    return wide, "daily_weighted_net_option_leg_return"


def load_v31_selected_panel(path: Path, value_col: str) -> pd.DataFrame:
    """Load the ver3.1 selected-sleeve daily panel as wide Step C columns."""

    df = pd.read_csv(path, dtype={"etf_code": str})
    df["date"] = pd.to_datetime(df["date"])
    df["etf_code"] = df["etf_code"].astype(str).str.zfill(6)
    df["sleeve_key"] = df["etf_code"] + "__" + df["sleeve_name"].astype(str)
    df["column"] = df["sleeve_key"].map(sleeve_return_column)
    wide = (
        df.pivot_table(index="date", columns="column", values=value_col, aggfunc="last")
        .sort_index()
        .reset_index()
    )
    wide.columns.name = None
    return wide


def _merge_panel_prefer_later(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Merge date panels and let later frames override duplicate columns."""

    prepared: list[pd.DataFrame] = []
    for frame in frames:
        if frame is None or frame.empty:
            continue
        out = frame.copy()
        out["date"] = pd.to_datetime(out["date"])
        prepared.append(out)
    if not prepared:
        return pd.DataFrame(columns=["date"])
    merged = prepared[0]
    for frame in prepared[1:]:
        overlap = sorted((set(merged.columns) & set(frame.columns)) - {"date"})
        if overlap:
            merged = merged.drop(columns=overlap)
        merged = merged.merge(frame, on="date", how="outer")
    return merged


def write_csv(df: pd.DataFrame, path: Path) -> Path:
    """Write a non-empty CSV."""

    if df.empty:
        raise ValueError(f"拒绝写出空 CSV：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def _read_date_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    return df
