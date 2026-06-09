from __future__ import annotations

from pathlib import Path
from typing import Any


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"null", "None", ""}:
        return None
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _minimal_yaml_load(text: str) -> dict[str, Any]:
    """Small fallback parser for the simple default.yaml shape."""
    root: dict[str, Any] = {}
    current_key: str | None = None
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if not raw_line.startswith(" "):
            key, _, value = raw_line.partition(":")
            key = key.strip()
            value = value.strip()
            if value:
                root[key] = _parse_scalar(value)
                current_key = None
            else:
                root[key] = {}
                current_key = key
            continue
        if current_key is None:
            continue
        stripped = raw_line.strip()
        if stripped.startswith("- "):
            if not isinstance(root[current_key], list):
                root[current_key] = []
            root[current_key].append(_parse_scalar(stripped[2:]))
        else:
            key, _, value = stripped.partition(":")
            root[current_key][key.strip()] = _parse_scalar(value)
    return root


def load_config(path: str | Path = "configs/default.yaml") -> dict[str, Any]:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    try:
        import yaml

        return yaml.safe_load(text)
    except Exception:
        return _minimal_yaml_load(text)


def ensure_output_dirs(config: dict[str, Any]) -> None:
    Path(config["paths"]["output_tables"]).mkdir(parents=True, exist_ok=True)
    Path(config["paths"]["output_figures"]).mkdir(parents=True, exist_ok=True)
