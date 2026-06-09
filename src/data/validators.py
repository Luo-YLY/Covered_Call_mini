from __future__ import annotations

import warnings

import pandas as pd

from src.data.schema import ETF_REQUIRED_COLUMNS, OPTION_OPTIONAL_COLUMNS, OPTION_REQUIRED_COLUMNS


def _require_columns(df: pd.DataFrame, required: set[str], name: str) -> None:
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{name} data missing required columns: {missing}")


def _parse_datetime(series: pd.Series, column: str, name: str) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce")
    if parsed.isna().any():
        raise ValueError(f"{name}.{column} contains invalid dates")
    return parsed


def validate_etf_prices(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    _require_columns(df, ETF_REQUIRED_COLUMNS, "ETF price")
    df["date"] = _parse_datetime(df["date"], "date", "ETF price")
    df["etf_code"] = df["etf_code"].astype(str)
    for col in ["open", "high", "low", "close", "adj_close", "volume", "amount"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        if df[col].isna().any():
            raise ValueError(f"ETF price.{col} contains non-numeric values")
    dupes = df.duplicated(["date", "etf_code"])
    if dupes.any():
        warnings.warn("ETF price data contains duplicate date-etf_code rows", RuntimeWarning)
    return df.sort_values(["etf_code", "date"]).reset_index(drop=True)


def validate_options(df: pd.DataFrame, keep_calls_only: bool = True) -> pd.DataFrame:
    df = df.copy()
    _require_columns(df, OPTION_REQUIRED_COLUMNS, "Option")
    df["trade_date"] = _parse_datetime(df["trade_date"], "trade_date", "Option")
    df["expiry"] = _parse_datetime(df["expiry"], "expiry", "Option")
    df["option_code"] = df["option_code"].astype(str)
    df["underlying_etf"] = df["underlying_etf"].astype(str)
    df["option_type"] = df["option_type"].astype(str).str.upper()
    invalid_types = sorted(set(df["option_type"]) - {"C", "P"})
    if invalid_types:
        raise ValueError(f"Option.option_type must be C or P, got {invalid_types}")
    for col in ["strike", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        if df[col].isna().any():
            raise ValueError(f"Option.{col} contains non-numeric values")
    for col in OPTION_OPTIONAL_COLUMNS & set(df.columns):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    dupes = df.duplicated(["trade_date", "option_code"])
    if dupes.any():
        warnings.warn("Option data contains duplicate trade_date-option_code rows", RuntimeWarning)
    if keep_calls_only:
        df = df[df["option_type"] == "C"].copy()
    return df.sort_values(["underlying_etf", "trade_date", "expiry", "strike"]).reset_index(drop=True)


def data_quality_report(etf_prices: pd.DataFrame, options: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for dataset_name, df in [("etf_prices", etf_prices), ("options_calls_only", options)]:
        for col in df.columns:
            rows.append(
                {
                    "dataset": dataset_name,
                    "column": col,
                    "rows": len(df),
                    "missing_count": int(df[col].isna().sum()),
                    "missing_ratio": float(df[col].isna().mean()) if len(df) else 0.0,
                    "synthetic_demo": bool(df.attrs.get("synthetic_demo", False)),
                }
            )
    return pd.DataFrame(rows)
