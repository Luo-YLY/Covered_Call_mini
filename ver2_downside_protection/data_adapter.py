from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.data.loaders import load_metadata
from src.data.validators import validate_etf_prices, validate_options
from src.utils.dates import month_end_roll_dates

from ver2_downside_protection.config import ExperimentConfig


@dataclass(frozen=True)
class Ver2DataBundle:
    prices: pd.DataFrame
    options: pd.DataFrame
    metadata: pd.DataFrame


def _read_csv(path: Path, dtype: dict[str, str] | None = None) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Required input file does not exist: {path}")
    return pd.read_csv(path, dtype=dtype)


def load_ver2_data(config: ExperimentConfig) -> Ver2DataBundle:
    """Load and validate ver1-compatible source tables for the ver2 experiment.

    Field mapping follows the existing repo schema: ETF prices use date/etf_code/adj_close,
    options use trade_date/underlying_etf/expiry/strike/close, and option_mid_price()
    falls back to close when bid/ask are absent.
    """

    prices = validate_etf_prices(_read_csv(config.paths.etf_prices, dtype={"etf_code": str}))
    options = validate_options(_read_csv(config.paths.options, dtype={"underlying_etf": str}), keep_calls_only=True)

    prices["etf_code"] = prices["etf_code"].astype(str).str.zfill(6)
    options["underlying_etf"] = options["underlying_etf"].astype(str).str.zfill(6)
    options["trade_date"] = pd.to_datetime(options["trade_date"])
    options["expiry"] = pd.to_datetime(options["expiry"])

    etf_codes = set(config.etf_codes)
    prices = prices[prices["etf_code"].isin(etf_codes)].copy()
    options = options[options["underlying_etf"].isin(etf_codes)].copy()

    if config.paths.metadata and config.paths.metadata.exists():
        metadata = load_metadata(config.paths.metadata, prices)
        metadata["etf_code"] = metadata["etf_code"].astype(str).str.zfill(6)
        metadata = metadata[metadata["etf_code"].isin(etf_codes)].copy()
    else:
        metadata = pd.DataFrame({"etf_code": sorted(etf_codes)})

    if prices.empty:
        raise ValueError(f"No ETF price rows found for configured ETFs: {sorted(etf_codes)}")
    if options.empty:
        raise ValueError(f"No option rows found for configured ETFs: {sorted(etf_codes)}")

    return Ver2DataBundle(prices=prices, options=options, metadata=metadata)


def price_on(price_g: pd.DataFrame, date: pd.Timestamp, price_col: str = "adj_close") -> float:
    row = price_g[price_g["date"] == pd.Timestamp(date)]
    if row.empty:
        raise ValueError(f"No ETF price for {date}")
    return float(row.iloc[0][price_col])


def roll_dates_for_prices(price_dates: pd.Series, frequency: str) -> pd.DatetimeIndex:
    dates = pd.DatetimeIndex(pd.to_datetime(price_dates).sort_values().unique())
    if len(dates) == 0:
        return pd.DatetimeIndex([])
    if frequency == "monthly":
        return month_end_roll_dates(pd.Series(dates))
    if frequency == "weekly":
        grouped = pd.Series(dates, index=dates).groupby(dates.to_period("W-FRI")).last()
        return pd.DatetimeIndex(grouped.values)
    raise ValueError(f"Unsupported roll frequency: {frequency}")
