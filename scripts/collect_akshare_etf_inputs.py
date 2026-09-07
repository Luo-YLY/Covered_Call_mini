#!/usr/bin/env python3
"""Collect provider-neutral ETF and SSE option CSV inputs through AkShare."""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path

import pandas as pd


CONTRACT_PATTERN = re.compile(
    r"^(?P<underlying>\d{6})(?P<option_type>[CP])(?P<yymm>\d{4})M(?P<strike>\d+)$"
)


def _retry(callable_, *, attempts: int = 3, delay: float = 1.0):
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return callable_()
        except Exception as exc:  # pragma: no cover - network-dependent
            last_error = exc
            if attempt < attempts:
                time.sleep(delay * attempt)
    raise RuntimeError(str(last_error)) from last_error


def _fourth_wednesday(yymm: str) -> pd.Timestamp:
    year = 2000 + int(yymm[:2])
    month = int(yymm[2:])
    first = pd.Timestamp(year=year, month=month, day=1)
    first_wednesday = first + pd.Timedelta(days=(2 - first.weekday()) % 7)
    return first_wednesday + pd.Timedelta(days=21)


def _normalize_etf_history(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if frame.empty or frame.shape[1] < 7:
        raise RuntimeError(f"AkShare未返回ETF {symbol} 的有效日行情")
    out = pd.DataFrame(
        {
            "etf_code": symbol,
            "trade_date": pd.to_datetime(frame.iloc[:, 0], errors="coerce"),
            "open": pd.to_numeric(frame.iloc[:, 1], errors="coerce"),
            "close": pd.to_numeric(frame.iloc[:, 2], errors="coerce"),
            "high": pd.to_numeric(frame.iloc[:, 3], errors="coerce"),
            "low": pd.to_numeric(frame.iloc[:, 4], errors="coerce"),
            "volume": pd.to_numeric(frame.iloc[:, 5], errors="coerce"),
            "amount": pd.to_numeric(frame.iloc[:, 6], errors="coerce"),
        }
    )
    return out.dropna(subset=["trade_date", "close"]).sort_values("trade_date").reset_index(drop=True)


def _normalize_option_history(frame: pd.DataFrame, option_code: str) -> pd.DataFrame:
    if frame.empty or frame.shape[1] < 6:
        return pd.DataFrame()
    out = pd.DataFrame(
        {
            "option_code": option_code,
            "trade_date": pd.to_datetime(frame.iloc[:, 0], errors="coerce"),
            "open": pd.to_numeric(frame.iloc[:, 1], errors="coerce"),
            "high": pd.to_numeric(frame.iloc[:, 2], errors="coerce"),
            "low": pd.to_numeric(frame.iloc[:, 3], errors="coerce"),
            "close": pd.to_numeric(frame.iloc[:, 4], errors="coerce"),
            "volume": pd.to_numeric(frame.iloc[:, 5], errors="coerce"),
        }
    )
    out["amount"] = pd.NA
    out["open_interest"] = pd.NA
    out["implied_vol"] = pd.NA
    out["delta"] = pd.NA
    return out.dropna(subset=["trade_date", "close"]).sort_values("trade_date").reset_index(drop=True)


def _month_end_dates(etf_daily: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> list[pd.Timestamp]:
    dates = etf_daily.loc[
        etf_daily["trade_date"].between(start, end, inclusive="both"), "trade_date"
    ]
    return (
        dates.groupby(dates.dt.to_period("M"), sort=True)
        .max()
        .tolist()
    )


def collect_inputs(
    symbol: str,
    start_date: str,
    end_date: str,
    output_dir: Path,
    target_delta: float,
    candidates_per_month: int,
) -> dict[str, object]:
    import akshare as ak

    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[1/3] ETF日行情 {symbol} {start.date()} 至 {end.date()}", flush=True)
    etf_raw = _retry(
        lambda: ak.fund_etf_hist_em(
            symbol=symbol,
            period="daily",
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
            adjust="",
        )
    )
    etf_daily = _normalize_etf_history(etf_raw, symbol)
    roll_dates = _month_end_dates(etf_daily, start, end)
    if len(roll_dates) < 6:
        raise RuntimeError("ETF共同样本少于六个月，无法完成动态回测验收")

    print(f"[2/3] 筛选 {len(roll_dates)} 个月末的真实认购期权", flush=True)
    selections: list[pd.DataFrame] = []
    for index, roll_date in enumerate(roll_dates, start=1):
        date_text = roll_date.strftime("%Y%m%d")
        risk = _retry(lambda value=date_text: ak.option_risk_indicator_sse(date=value))
        if risk.empty:
            print(f"  {index}/{len(roll_dates)} {date_text}: 无风险指标数据", flush=True)
            continue
        relevant = risk[risk["CONTRACT_ID"].astype(str).str.startswith(symbol)].copy()
        parsed = relevant["CONTRACT_ID"].astype(str).str.extract(CONTRACT_PATTERN)
        relevant = pd.concat([relevant.reset_index(drop=True), parsed.reset_index(drop=True)], axis=1)
        relevant["expiry"] = relevant["yymm"].map(_fourth_wednesday)
        relevant["days_to_expiry"] = (relevant["expiry"] - roll_date).dt.days
        relevant["delta_numeric"] = pd.to_numeric(relevant["DELTA_VALUE"], errors="coerce")
        relevant = relevant[
            relevant["option_type"].eq("C")
            & relevant["days_to_expiry"].between(20, 45, inclusive="both")
            & relevant["delta_numeric"].between(0.01, 0.99, inclusive="both")
        ].copy()
        relevant["delta_distance"] = (relevant["delta_numeric"] - target_delta).abs()
        chosen = relevant.nsmallest(candidates_per_month, "delta_distance").copy()
        if chosen.empty:
            print(f"  {index}/{len(roll_dates)} {date_text}: 无DTE20-45有效认购", flush=True)
            continue
        chosen["roll_date"] = roll_date
        selections.append(chosen)
        codes = ",".join(chosen["SECURITY_ID"].astype(str).tolist())
        print(f"  {index}/{len(roll_dates)} {date_text}: {codes}", flush=True)

    if not selections:
        raise RuntimeError(f"AkShare风险指标中没有找到 {symbol} 的有效认购期权")
    audit = pd.concat(selections, ignore_index=True)
    audit["option_code"] = audit["SECURITY_ID"].astype(str)
    audit["strike"] = pd.to_numeric(audit["strike"], errors="coerce") / 1000.0
    audit = audit.drop_duplicates(["roll_date", "option_code"], keep="last")

    contract_rows = audit.sort_values("roll_date").drop_duplicates("option_code", keep="last")
    contracts = pd.DataFrame(
        {
            "option_code": contract_rows["option_code"],
            "underlying_etf": symbol,
            "option_type": contract_rows["option_type"],
            "strike": contract_rows["strike"],
            "expiry": contract_rows["expiry"],
        }
    ).reset_index(drop=True)

    print(f"[3/3] 下载 {len(contracts)} 张期权合约的日行情", flush=True)
    option_parts: list[pd.DataFrame] = []
    for index, option_code in enumerate(contracts["option_code"], start=1):
        try:
            history_raw = _retry(lambda code=option_code: ak.option_sse_daily_sina(symbol=code))
        except RuntimeError as exc:
            print(f"  {index}/{len(contracts)} {option_code}: 跳过 ({exc})", flush=True)
            continue
        history = _normalize_option_history(history_raw, option_code)
        history = history[history["trade_date"].between(start, end, inclusive="both")].copy()
        risk_rows = audit[audit["option_code"].eq(option_code)][
            ["roll_date", "delta_numeric", "IMPLC_VOLATLTY"]
        ].drop_duplicates("roll_date", keep="last")
        for row in risk_rows.itertuples(index=False):
            match = history["trade_date"].eq(row.roll_date)
            history.loc[match, "delta"] = row.delta_numeric
            history.loc[match, "implied_vol"] = row.IMPLC_VOLATLTY
        if not history.empty:
            option_parts.append(history)
        if index % 10 == 0 or index == len(contracts):
            print(f"  已完成 {index}/{len(contracts)}", flush=True)

    if not option_parts:
        raise RuntimeError("AkShare未返回所选合约的历史日行情")
    option_daily = pd.concat(option_parts, ignore_index=True)
    available_codes = set(option_daily["option_code"].astype(str))
    contracts = contracts[contracts["option_code"].astype(str).isin(available_codes)].copy()
    option_daily = option_daily[option_daily["option_code"].astype(str).isin(available_codes)].copy()

    etf_path = output_dir / "etf_daily.csv"
    contract_path = output_dir / "option_contracts.csv"
    option_path = output_dir / "option_daily.csv"
    etf_daily.to_csv(etf_path, index=False, encoding="utf-8-sig", date_format="%Y-%m-%d")
    contracts.to_csv(contract_path, index=False, encoding="utf-8-sig", date_format="%Y-%m-%d")
    option_daily.to_csv(option_path, index=False, encoding="utf-8-sig", date_format="%Y-%m-%d")
    audit.to_csv(output_dir / "akshare_selection_audit.csv", index=False, encoding="utf-8-sig")

    manifest = {
        "schema_version": "1.0",
        "provider": "AkShare",
        "akshare_version": getattr(ak, "__version__", "unknown"),
        "retrieved_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "symbol": symbol,
        "sample_start": etf_daily["trade_date"].min().date().isoformat(),
        "sample_end": etf_daily["trade_date"].max().date().isoformat(),
        "interfaces": [
            "fund_etf_hist_em",
            "option_risk_indicator_sse",
            "option_sse_daily_sina",
        ],
        "selection": {
            "target_delta": target_delta,
            "dte_window": [20, 45],
            "candidates_per_month": candidates_per_month,
        },
        "rows": {
            "etf_daily": int(len(etf_daily)),
            "option_contracts": int(len(contracts)),
            "option_daily": int(len(option_daily)),
            "selection_audit": int(len(audit)),
        },
        "limitations": [
            "AkShare的上交所期权历史日行情接口不提供成交额和持仓量，这两列保留为空值。",
            "合约筛选使用AkShare返回的上交所历史风险指标，上传后由项目统一重新计算Delta。",
        ],
    }
    (output_dir / "source_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect ETF covered-call inputs through AkShare")
    parser.add_argument("--symbol", default="588080")
    parser.add_argument("--start-date", default="2024-05-01")
    parser.add_argument("--end-date", default="2025-06-30")
    parser.add_argument("--target-delta", type=float, default=0.30)
    parser.add_argument("--candidates-per-month", type=int, default=4)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    collect_inputs(
        symbol=args.symbol,
        start_date=args.start_date,
        end_date=args.end_date,
        output_dir=Path(args.output_dir).resolve(),
        target_delta=args.target_delta,
        candidates_per_month=args.candidates_per_month,
    )


if __name__ == "__main__":
    main()
