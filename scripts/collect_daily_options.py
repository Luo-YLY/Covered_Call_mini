from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.tushare_source import TushareCollector, normalize_tushare_options


def _date_arg(value: str | None) -> pd.Timestamp | None:
    if not value:
        return None
    return pd.Timestamp(value)


def _trade_dates_from_prices(price_path: Path, start_date: str | None, end_date: str | None) -> list[str]:
    prices = pd.read_csv(price_path, parse_dates=["date"])
    dates = pd.Series(prices["date"].dropna().unique()).sort_values()
    start = _date_arg(start_date)
    end = _date_arg(end_date)
    if start is not None:
        dates = dates[dates >= start]
    if end is not None:
        dates = dates[dates <= end]
    return pd.to_datetime(dates).dt.strftime("%Y%m%d").tolist()


def _load_existing(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect daily ETF option chains from Tushare opt_daily.")
    parser.add_argument("--start-date", default=None, help="Inclusive start date, e.g. 2021-01-01.")
    parser.add_argument("--end-date", default=None, help="Inclusive end date, e.g. 2026-06-03.")
    parser.add_argument("--exchange", default=None, help="Optional single Tushare option exchange filter.")
    parser.add_argument("--exchanges", default="SSE,SZSE", help="Comma-separated option exchanges for ETF options.")
    parser.add_argument("--sleep-seconds", type=float, default=0.25)
    parser.add_argument("--token", default=None)
    parser.add_argument("--http-url", default=None)
    parser.add_argument("--token-file", default=str(ROOT / "config" / "tushare_token.txt"))
    parser.add_argument("--http-url-file", default=str(ROOT / "config" / "tushare_http_url.txt"))
    parser.add_argument("--resume", action="store_true", help="Skip trade dates already present in the raw output.")
    parser.add_argument("--raw-dir", default=str(ROOT / "data" / "raw"))
    args = parser.parse_args()

    raw_dir = Path(args.raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    daily_raw_path = raw_dir / "tushare_opt_daily_full_raw.csv"
    options_daily_path = raw_dir / "options_daily.csv"
    status_path = raw_dir / "_option_daily_collection_status.csv"

    trade_dates = _trade_dates_from_prices(raw_dir / "etf_prices.csv", args.start_date, args.end_date)
    existing_raw = _load_existing(daily_raw_path) if args.resume else pd.DataFrame()
    if args.resume and not existing_raw.empty and "trade_date" in existing_raw.columns:
        done = set(existing_raw["trade_date"].astype(str))
        trade_dates = [date for date in trade_dates if date not in done]

    collector = TushareCollector(
        token=args.token,
        token_file=args.token_file,
        http_url=args.http_url,
        http_url_file=args.http_url_file,
        sleep_seconds=args.sleep_seconds,
    )
    exchanges = [args.exchange] if args.exchange else [item.strip() for item in args.exchanges.split(",") if item.strip()]
    parts = []
    statuses = []
    for exchange in exchanges:
        opt_daily_part = collector.fetch_opt_daily_by_trade_dates(trade_dates, exchange=exchange)
        if not opt_daily_part.empty:
            parts.append(opt_daily_part)
        if hasattr(collector, "opt_daily_status"):
            status = collector.opt_daily_status.copy()
            status["exchange"] = exchange
            statuses.append(status)
    opt_daily_new = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    opt_basic = pd.read_csv(raw_dir / "tushare_opt_basic_raw.csv")

    raw_parts = [df for df in [existing_raw, opt_daily_new] if not df.empty]
    opt_daily_full = pd.concat(raw_parts, ignore_index=True) if raw_parts else pd.DataFrame()
    if not opt_daily_full.empty:
        opt_daily_full = opt_daily_full.drop_duplicates(["ts_code", "trade_date"], keep="last")
        opt_daily_full.to_csv(daily_raw_path, index=False, encoding="utf-8-sig")
        options_daily = normalize_tushare_options(opt_daily_full, opt_basic)
        options_daily.to_csv(options_daily_path, index=False, encoding="utf-8-sig")

    if statuses:
        status = pd.concat(statuses, ignore_index=True)
        if args.resume and status_path.exists():
            old_status = pd.read_csv(status_path)
            status = pd.concat([old_status, status], ignore_index=True)
        status.to_csv(status_path, index=False, encoding="utf-8-sig")

    print(f"requested_trade_dates={len(trade_dates)}")
    print(f"raw_rows={len(opt_daily_full)}")
    print(f"standardized_rows={len(pd.read_csv(options_daily_path)) if options_daily_path.exists() else 0}")
    print(f"wrote={options_daily_path}")


if __name__ == "__main__":
    main()
