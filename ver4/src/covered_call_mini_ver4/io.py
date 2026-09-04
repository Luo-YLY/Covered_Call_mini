from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .config import CycleExperimentConfig, config_manifest


def ensure_output_dirs(config: CycleExperimentConfig) -> dict[str, Path]:
    root = config.paths.output_root
    paths = {
        "root": root,
        "config": root / "config",
        "period": root / "period",
        "daily_mtm": root / "daily_mtm",
        "summary": root / "summary",
        "regime": root / "regime",
        "audit": root / "audit",
        "reports": root / "reports",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def write_manifest(config: CycleExperimentConfig, path: Path) -> Path:
    path.write_text(json.dumps(config_manifest(config), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_csv(frame: pd.DataFrame, path: Path) -> Path:
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    return path
