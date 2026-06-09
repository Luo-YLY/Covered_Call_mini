from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.data.validators import data_quality_report, validate_etf_prices, validate_options


def _read_existing(preferred_path: str | Path) -> pd.DataFrame | None:
    path = Path(preferred_path)
    candidates = [path]
    if path.suffix == ".parquet":
        candidates.append(path.with_suffix(".csv"))
    elif path.suffix == ".csv":
        candidates.append(path.with_suffix(".parquet"))
    for candidate in candidates:
        if candidate.exists():
            if candidate.suffix == ".parquet":
                return pd.read_parquet(candidate)
            return pd.read_csv(candidate)
    return None


def generate_synthetic_demo_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(7)
    dates = pd.bdate_range("2021-01-04", "2023-12-29")
    etfs = [
        ("ETF_A", "Broad Equity", "Equity"),
        ("ETF_B", "Growth Tilt", "Growth"),
        ("ETF_C", "Low Volatility", "Defensive"),
    ]
    price_rows = []
    for i, (code, _, _) in enumerate(etfs):
        rets = rng.normal(0.00025 + i * 0.00005, 0.010 + i * 0.002, len(dates))
        prices = 100 * np.cumprod(1 + rets)
        volume = rng.integers(700_000, 2_500_000, len(dates)) * (1 + i)
        for d, px, vol in zip(dates, prices, volume):
            price_rows.append(
                {
                    "date": d,
                    "etf_code": code,
                    "open": px * (1 + rng.normal(0, 0.001)),
                    "high": px * (1 + abs(rng.normal(0, 0.003))),
                    "low": px * (1 - abs(rng.normal(0, 0.003))),
                    "close": px,
                    "adj_close": px,
                    "volume": vol,
                    "amount": vol * px,
                }
            )
    prices = pd.DataFrame(price_rows)

    option_rows = []
    for code, _, _ in etfs:
        p = prices[prices["etf_code"] == code].set_index("date")
        roll_dates = pd.Series(p.index, index=p.index).groupby(p.index.to_period("M")).last().values
        for trade_date in pd.to_datetime(roll_dates[:-1]):
            s0 = float(p.loc[trade_date, "adj_close"])
            expiry = trade_date + pd.Timedelta(days=30)
            for m in [0.95, 1.0, 1.03, 1.05, 1.08, 1.12]:
                strike = round(s0 * m, 2)
                dte = 30 / 365
                iv = 0.18 + 0.04 * rng.random()
                intrinsic = max(s0 - strike, 0)
                extrinsic = s0 * iv * np.sqrt(dte) * max(0.15, 1 - abs(m - 1) * 4)
                close = max(0.05, intrinsic + extrinsic)
                spread = close * (0.02 + 0.04 * rng.random())
                delta = max(0.05, min(0.95, 0.5 - (m - 1) * 5 + rng.normal(0, 0.03)))
                option_rows.append(
                    {
                        "trade_date": trade_date,
                        "option_code": f"{code}_{trade_date:%Y%m}_{strike:.2f}C",
                        "underlying_etf": code,
                        "option_type": "C",
                        "expiry": expiry,
                        "strike": strike,
                        "close": close,
                        "bid": max(0.01, close - spread / 2),
                        "ask": close + spread / 2,
                        "volume": int(rng.integers(50, 1500)),
                        "open_interest": int(rng.integers(100, 5000)),
                        "amount": close * int(rng.integers(50, 1500)) * 10000,
                        "implied_vol": iv,
                        "delta": delta,
                    }
                )
    options = pd.DataFrame(option_rows)
    metadata = pd.DataFrame(
        [
            {"etf_code": code, "etf_name": name, "style_bucket": style, "index_name": name}
            for code, name, style in etfs
        ]
    )
    for df in [prices, options, metadata]:
        df.attrs["synthetic_demo"] = True
    return prices, options, metadata


def load_metadata(path: str | Path, etf_prices: pd.DataFrame) -> pd.DataFrame:
    path = Path(path)
    if path.exists():
        metadata = pd.read_csv(path)
        metadata["etf_code"] = metadata["etf_code"].astype(str)
        return metadata
    return pd.DataFrame({"etf_code": sorted(etf_prices["etf_code"].astype(str).unique())})


def load_research_data(config: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, bool]:
    prices_raw = _read_existing(config["paths"]["etf_prices"])
    options_raw = _read_existing(config["paths"]["options"])
    synthetic = prices_raw is None or options_raw is None
    if synthetic:
        prices_raw, options_raw, metadata = generate_synthetic_demo_data()
    else:
        metadata = load_metadata(config["paths"]["metadata"], prices_raw)

    prices = validate_etf_prices(prices_raw)
    options = validate_options(options_raw, keep_calls_only=True)
    prices.attrs["synthetic_demo"] = synthetic
    options.attrs["synthetic_demo"] = synthetic
    metadata.attrs["synthetic_demo"] = synthetic
    quality = data_quality_report(prices, options)
    return prices, options, metadata, quality, synthetic
