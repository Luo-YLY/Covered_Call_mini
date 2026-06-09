from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


def etf_ts_code(etf_code: str, exchange: str | None = None) -> str:
    code = str(etf_code).split(".")[0].zfill(6)
    if exchange:
        ex = str(exchange).upper()
        if ex in {"SH", "SSE", "SHSE"} or "\u4e0a" in str(exchange):
            return f"{code}.SH"
        if ex in {"SZ", "SZSE"} or "\u6df1" in str(exchange):
            return f"{code}.SZ"
    suffix = "SH" if code.startswith(("5", "6")) else "SZ"
    return f"{code}.{suffix}"


def strip_ts_suffix(value: str) -> str:
    code = str(value).split(".")[0]
    if code.upper().startswith("OP"):
        code = code[2:]
    return code.zfill(6)


def load_tushare_token(token: str | None = None, token_file: str | Path | None = None) -> str:
    if token:
        return token.strip()
    env_token = os.environ.get("TUSHARE_TOKEN")
    if env_token:
        return env_token.strip()
    file_path = Path(token_file or "configs/tushare_token.txt")
    if file_path.exists():
        file_token = file_path.read_text(encoding="utf-8").strip()
        if file_token and not file_token.startswith("#"):
            return file_token
    raise ValueError(
        "Tushare token is required. Pass --token, set TUSHARE_TOKEN, "
        "or create configs/tushare_token.txt from configs/tushare_token.example.txt."
    )


def load_tushare_http_url(http_url: str | None = None, http_url_file: str | Path | None = None) -> str | None:
    if http_url:
        return http_url.strip()
    env_url = os.environ.get("TUSHARE_HTTP_URL")
    if env_url:
        return env_url.strip()
    file_path = Path(http_url_file or "configs/tushare_http_url.txt")
    if file_path.exists():
        file_url = file_path.read_text(encoding="utf-8").strip()
        if file_url and not file_url.startswith("#"):
            return file_url
    return None


def normalize_tushare_fund_daily(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).lower() for c in out.columns]
    required = {"trade_date", "ts_code", "open", "high", "low", "close"}
    missing = required - set(out.columns)
    if missing:
        raise ValueError(f"Tushare fund_daily missing columns: {sorted(missing)}")
    result = pd.DataFrame(
        {
            "date": pd.to_datetime(out["trade_date"].astype(str), format="%Y%m%d", errors="coerce"),
            "etf_code": out["ts_code"].map(strip_ts_suffix),
            "open": pd.to_numeric(out["open"], errors="coerce"),
            "high": pd.to_numeric(out["high"], errors="coerce"),
            "low": pd.to_numeric(out["low"], errors="coerce"),
            "close": pd.to_numeric(out["close"], errors="coerce"),
            "adj_close": pd.to_numeric(out.get("adj_close", out["close"]), errors="coerce"),
            "volume": pd.to_numeric(out.get("vol", out.get("volume", 0)), errors="coerce"),
            "amount": pd.to_numeric(out.get("amount", 0), errors="coerce"),
        }
    )
    return result.dropna(subset=["date", "etf_code", "close"]).sort_values(["etf_code", "date"]).reset_index(drop=True)


def _first_existing(df: pd.DataFrame, candidates: Iterable[str]) -> str | None:
    lowered = {str(c).lower(): c for c in df.columns}
    for candidate in candidates:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    return None


def _option_type(value) -> str:
    text = str(value).upper()
    if text in {"C", "CALL"} or "\u8ba4\u8d2d" in str(value):
        return "C"
    if text in {"P", "PUT"} or "\u8ba4\u6cbd" in str(value):
        return "P"
    if "C" in text and "P" not in text:
        return "C"
    if "P" in text and "C" not in text:
        return "P"
    return text


def _parse_yyyymmdd(series: pd.Series) -> pd.Series:
    text = pd.to_numeric(series, errors="coerce").astype("Int64").astype(str)
    text = text.replace("<NA>", pd.NA)
    return pd.to_datetime(text, format="%Y%m%d", errors="coerce")


def normalize_tushare_options(opt_daily: pd.DataFrame, opt_basic: pd.DataFrame) -> pd.DataFrame:
    daily = opt_daily.copy()
    basic = opt_basic.copy()
    daily.columns = [str(c).lower() for c in daily.columns]
    basic.columns = [str(c).lower() for c in basic.columns]
    if "ts_code" not in daily.columns or "ts_code" not in basic.columns:
        raise ValueError("Tushare opt_daily and opt_basic must both include ts_code")
    merged = daily.merge(basic, on="ts_code", how="left", suffixes=("", "_basic"))

    trade_date_col = _first_existing(merged, ["trade_date"])
    expiry_col = _first_existing(merged, ["maturity_date", "expire_date", "exercise_date", "last_ddate"])
    strike_col = _first_existing(merged, ["exercise_price", "strike_price", "strike"])
    call_put_col = _first_existing(merged, ["call_put", "option_type", "opt_type"])
    underlying_col = _first_existing(merged, ["underlying", "underlying_code", "us_code", "s_code", "opt_code"])
    close_col = _first_existing(merged, ["close", "settle"])
    if not all([trade_date_col, expiry_col, strike_col, call_put_col, underlying_col, close_col]):
        missing = {
            "trade_date": trade_date_col,
            "expiry": expiry_col,
            "strike": strike_col,
            "call_put": call_put_col,
            "underlying": underlying_col,
            "close": close_col,
        }
        raise ValueError(f"Cannot map Tushare option columns: {missing}")

    result = pd.DataFrame(
        {
            "trade_date": _parse_yyyymmdd(merged[trade_date_col]),
            "option_code": merged["ts_code"].astype(str),
            "underlying_etf": merged[underlying_col].map(strip_ts_suffix),
            "option_type": merged[call_put_col].map(_option_type),
            "expiry": _parse_yyyymmdd(merged[expiry_col]),
            "strike": pd.to_numeric(merged[strike_col], errors="coerce"),
            "close": pd.to_numeric(merged[close_col], errors="coerce"),
            "volume": pd.to_numeric(merged.get("vol", merged.get("volume", pd.NA)), errors="coerce"),
            "open_interest": pd.to_numeric(merged.get("oi", merged.get("open_interest", pd.NA)), errors="coerce"),
            "amount": pd.to_numeric(merged.get("amount", pd.NA), errors="coerce"),
        }
    )
    for optional in ["bid", "ask", "implied_vol", "delta", "gamma", "theta", "vega"]:
        if optional in merged.columns:
            result[optional] = pd.to_numeric(merged[optional], errors="coerce")
    result = result.dropna(subset=["trade_date", "option_code", "underlying_etf", "expiry", "strike", "close"])
    return result.sort_values(["underlying_etf", "trade_date", "expiry", "strike"]).reset_index(drop=True)


@dataclass
class TushareCollector:
    token: str | None = None
    token_file: str | Path | None = None
    http_url: str | None = None
    http_url_file: str | Path | None = None
    sleep_seconds: float = 0.25

    def __post_init__(self) -> None:
        token = load_tushare_token(self.token, self.token_file)
        http_url = load_tushare_http_url(self.http_url, self.http_url_file)
        try:
            import tushare as ts
        except ImportError as exc:
            raise ImportError("Install tushare first: python -m pip install tushare") from exc
        self.pro = ts.pro_api(token)
        if http_url:
            self.pro._DataApi__http_url = http_url

    def fetch_fund_daily(self, etf_codes: list[str], start_date: str, end_date: str) -> pd.DataFrame:
        parts = []
        rows = []
        for code in etf_codes:
            ts_code = etf_ts_code(code)
            try:
                raw = self.pro.fund_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
                if raw is None or raw.empty:
                    rows.append({"dataset": "tushare_fund_daily", "symbol": ts_code, "status": "empty", "rows": 0, "message": ""})
                    continue
                parts.append(raw)
                rows.append({"dataset": "tushare_fund_daily", "symbol": ts_code, "status": "ok", "rows": len(raw), "message": ""})
            except Exception as exc:
                rows.append({"dataset": "tushare_fund_daily", "symbol": ts_code, "status": "error", "rows": 0, "message": str(exc)})
            time.sleep(self.sleep_seconds)
        self.fund_status = pd.DataFrame(rows)
        return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()

    def fetch_opt_basic(self, exchanges: list[str]) -> pd.DataFrame:
        parts = []
        rows = []
        for exchange in exchanges:
            try:
                raw = self.pro.opt_basic(exchange=exchange)
                if raw is None or raw.empty:
                    rows.append({"dataset": "tushare_opt_basic", "symbol": exchange, "status": "empty", "rows": 0, "message": ""})
                    continue
                parts.append(raw)
                rows.append({"dataset": "tushare_opt_basic", "symbol": exchange, "status": "ok", "rows": len(raw), "message": ""})
            except Exception as exc:
                rows.append({"dataset": "tushare_opt_basic", "symbol": exchange, "status": "error", "rows": 0, "message": str(exc)})
            time.sleep(self.sleep_seconds)
        self.opt_basic_status = pd.DataFrame(rows)
        return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()

    def fetch_opt_daily_by_trade_dates(self, trade_dates: list[str], exchange: str | None = None) -> pd.DataFrame:
        parts = []
        rows = []
        for trade_date in trade_dates:
            try:
                kwargs = {"trade_date": trade_date}
                if exchange:
                    kwargs["exchange"] = exchange
                raw = self.pro.opt_daily(**kwargs)
                if raw is None or raw.empty:
                    rows.append({"dataset": "tushare_opt_daily", "symbol": trade_date, "status": "empty", "rows": 0, "message": ""})
                    continue
                parts.append(raw)
                rows.append({"dataset": "tushare_opt_daily", "symbol": trade_date, "status": "ok", "rows": len(raw), "message": ""})
            except Exception as exc:
                rows.append({"dataset": "tushare_opt_daily", "symbol": trade_date, "status": "error", "rows": 0, "message": str(exc)})
            time.sleep(self.sleep_seconds)
        self.opt_daily_status = pd.DataFrame(rows)
        return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def write_standard_raw_outputs(
    etf_prices: pd.DataFrame,
    options: pd.DataFrame,
    output_dir: str | Path = "data/raw",
) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if not etf_prices.empty:
        etf_prices.to_csv(output / "etf_prices.csv", index=False, encoding="utf-8-sig")
    if not options.empty:
        options.to_csv(output / "options.csv", index=False, encoding="utf-8-sig")
