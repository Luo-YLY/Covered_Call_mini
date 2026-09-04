from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .config import DiagnosticConfig, config_manifest


OUTPUT_SUBDIRS = (
    "config",
    "runs",
    "daily",
    "summary",
    "attribution",
    "phase_lite",
    "figures",
    "reports",
)


def ensure_output_dirs(config: DiagnosticConfig) -> None:
    for name in OUTPUT_SUBDIRS:
        (config.paths.output_root / name).mkdir(parents=True, exist_ok=True)
    config.paths.ver3_output_index.parent.mkdir(parents=True, exist_ok=True)


def write_csv(df: pd.DataFrame, path: Path) -> Path:
    if df.empty:
        raise ValueError(f"Refusing to write empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def write_json(payload: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_config_artifacts(config: DiagnosticConfig, implementation_grid: pd.DataFrame, target_etfs: pd.DataFrame) -> dict[str, Path]:
    root = config.paths.output_root / "config"
    return {
        "run_config": write_json(config_manifest(config), root / "ver3_0_effective_delta_equivalence_config.json"),
        "implementation_grid": write_csv(
            implementation_grid,
            root / "ver3_0_effective_delta_implementation_grid.csv",
        ),
        "target_etfs": write_csv(target_etfs, root / "ver3_0_effective_delta_target_etfs.csv"),
    }


def rel_path(config: DiagnosticConfig, path: Path | str) -> str:
    p = Path(path)
    try:
        return str(p.resolve().relative_to(config.paths.project_root)).replace("\\", "/")
    except ValueError:
        return str(p)
