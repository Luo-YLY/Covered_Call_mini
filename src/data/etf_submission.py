from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.features.delta_surface import build_delta_enriched_options


DATASET_FILENAMES = {
    "etf_daily": "etf_daily.csv",
    "option_contracts": "option_contracts.csv",
    "option_daily": "option_daily.csv",
}

DATASET_LABELS = {
    "etf_daily": "ETF日行情",
    "option_contracts": "期权合约",
    "option_daily": "期权日行情",
}

# The first name in each tuple is the provider-neutral project field. Later names
# keep existing exports and common vendor conventions upload-compatible.
COLUMN_ALIASES = {
    "etf_daily": {
        "etf_code": ("etf_code", "ts_code", "symbol", "ticker", "code"),
        "trade_date": ("trade_date", "date"),
        "open": ("open",),
        "high": ("high",),
        "low": ("low",),
        "close": ("close",),
        "volume": ("volume", "vol"),
        "amount": ("amount", "turnover"),
    },
    "option_contracts": {
        "option_code": ("option_code", "contract_code", "ts_code"),
        "underlying_etf": ("underlying_etf", "underlying_code", "underlying", "opt_code"),
        "option_type": ("option_type", "call_put", "cp_flag", "opt_type"),
        "strike": ("strike", "strike_price", "exercise_price"),
        "expiry": ("expiry", "maturity_date", "expire_date", "exercise_date", "last_ddate"),
    },
    "option_daily": {
        "option_code": ("option_code", "contract_code", "ts_code"),
        "trade_date": ("trade_date", "date"),
        "close": ("close", "settle"),
        "volume": ("volume", "vol"),
        "amount": ("amount", "turnover"),
        "open_interest": ("open_interest", "oi"),
    },
}

ETF_CODE_PATTERN = re.compile(r"^\d{6}$")
MIN_COMPLETE_MONTHLY_PERIODS = 12


class SubmissionValidationError(ValueError):
    pass


def normalize_etf_code(value: object) -> str:
    code = str(value or "").strip().split(".")[0]
    if not ETF_CODE_PATTERN.fullmatch(code):
        raise SubmissionValidationError("ETF代码必须是6位数字")
    return code


def _read_input_csv(path: Path, dataset: str) -> pd.DataFrame:
    if not path.is_file():
        raise SubmissionValidationError(f"缺少 {DATASET_FILENAMES[dataset]}")
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            frame = pd.read_csv(path, encoding=encoding, low_memory=False)
            break
        except UnicodeDecodeError as exc:
            last_error = exc
    else:
        raise SubmissionValidationError(f"{path.name} 不是可识别的CSV编码") from last_error

    frame.columns = [str(column).strip().lower() for column in frame.columns]
    rename: dict[str, str] = {}
    missing: list[str] = []
    for target, aliases in COLUMN_ALIASES[dataset].items():
        source = next((alias for alias in aliases if alias in frame.columns), None)
        if source is None:
            missing.append(target)
        elif source != target:
            rename[source] = target
    if missing:
        raise SubmissionValidationError(
            f"{path.name} 不符合项目{DATASET_LABELS[dataset]}格式，缺少字段：{', '.join(sorted(missing))}"
        )
    if frame.empty:
        raise SubmissionValidationError(f"{path.name} 没有数据行")
    return frame.rename(columns=rename)


def _parse_date(series: pd.Series) -> pd.Series:
    text = series.astype("string").str.strip()
    compact = pd.to_datetime(text, format="%Y%m%d", errors="coerce")
    return compact.fillna(pd.to_datetime(text, errors="coerce"))


def _strip_market_suffix(value: object) -> str:
    return str(value).strip().split(".")[0]


def _normalize_option_type(value: object) -> str:
    text = str(value).strip().upper()
    if text in {"C", "CALL", "认购"}:
        return "C"
    if text in {"P", "PUT", "认沽"}:
        return "P"
    return text


def _normalize_etf_daily(frame: pd.DataFrame) -> pd.DataFrame:
    result = pd.DataFrame(
        {
            "date": _parse_date(frame["trade_date"]),
            "etf_code": frame["etf_code"].map(_strip_market_suffix),
            "open": pd.to_numeric(frame["open"], errors="coerce"),
            "high": pd.to_numeric(frame["high"], errors="coerce"),
            "low": pd.to_numeric(frame["low"], errors="coerce"),
            "close": pd.to_numeric(frame["close"], errors="coerce"),
            "adj_close": pd.to_numeric(frame.get("adj_close", frame["close"]), errors="coerce"),
            "volume": pd.to_numeric(frame["volume"], errors="coerce"),
            "amount": pd.to_numeric(frame["amount"], errors="coerce"),
        }
    )
    return result.dropna(subset=["date", "etf_code", "close"])


def _normalize_options(daily: pd.DataFrame, contracts: pd.DataFrame) -> pd.DataFrame:
    merged = daily.merge(contracts, on="option_code", how="left", suffixes=("", "_contract"))
    result = pd.DataFrame(
        {
            "trade_date": _parse_date(merged["trade_date"]),
            "option_code": merged["option_code"].astype(str),
            "underlying_etf": merged["underlying_etf"].map(_strip_market_suffix),
            "option_type": merged["option_type"].map(_normalize_option_type),
            "expiry": _parse_date(merged["expiry"]),
            "strike": pd.to_numeric(merged["strike"], errors="coerce"),
            "close": pd.to_numeric(merged["close"], errors="coerce"),
            "volume": pd.to_numeric(merged["volume"], errors="coerce"),
            "open_interest": pd.to_numeric(merged["open_interest"], errors="coerce"),
            "amount": pd.to_numeric(merged["amount"], errors="coerce"),
        }
    )
    for optional in ["bid", "ask", "implied_vol", "delta", "gamma", "theta", "vega"]:
        if optional in merged.columns:
            result[optional] = pd.to_numeric(merged[optional], errors="coerce")
    return result.dropna(
        subset=["trade_date", "option_code", "underlying_etf", "expiry", "strike", "close"]
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _date_text(value: object) -> str | None:
    if pd.isna(value):
        return None
    return pd.Timestamp(value).date().isoformat()


def _unique_dates(values: pd.Series) -> list[object]:
    parsed = pd.to_datetime(values, errors="coerce")
    return sorted(set(parsed.dropna().dt.date))


def summarize_backtest_date_availability(
    prices: pd.DataFrame,
    options: pd.DataFrame,
    *,
    min_days_to_expiry: int = 20,
    max_days_to_expiry: int = 45,
) -> dict[str, Any]:
    """Return the actual ETF/option date windows available to the dashboard.

    The backtest window is intentionally based on call rows that can enter the
    current target-Delta strategy, rather than every raw option quote.
    """

    price_column = "date" if "date" in prices.columns else "trade_date"
    price_dates = _unique_dates(prices[price_column]) if price_column in prices.columns else []
    option_dates = _unique_dates(options["trade_date"]) if "trade_date" in options.columns else []

    if "option_type" in options.columns:
        call_mask = options["option_type"].map(_normalize_option_type).eq("C")
    else:
        call_mask = pd.Series(False, index=options.index)

    if "days_to_expiry" in options.columns:
        days_to_expiry = pd.to_numeric(options["days_to_expiry"], errors="coerce")
    elif {"trade_date", "expiry"}.issubset(options.columns):
        days_to_expiry = (
            pd.to_datetime(options["expiry"], errors="coerce")
            - pd.to_datetime(options["trade_date"], errors="coerce")
        ).dt.days
    else:
        days_to_expiry = pd.Series(float("nan"), index=options.index)

    positive_strike = pd.to_numeric(options.get("strike"), errors="coerce").gt(0)
    positive_close = pd.to_numeric(options.get("close"), errors="coerce").gt(0)
    if "delta_valid" in options.columns:
        valid_delta = pd.to_numeric(options["delta_valid"], errors="coerce").eq(1)
    else:
        delta_column = next((name for name in ("model_delta", "delta") if name in options.columns), None)
        if delta_column:
            delta_values = pd.to_numeric(options[delta_column], errors="coerce")
            valid_delta = delta_values.notna() & delta_values.abs().between(0.01, 0.99, inclusive="both")
        else:
            valid_delta = pd.Series(False, index=options.index)

    eligible_mask = (
        call_mask
        & days_to_expiry.between(min_days_to_expiry, max_days_to_expiry, inclusive="both")
        & positive_strike
        & positive_close
        & valid_delta
    )
    eligible_options = options.loc[eligible_mask].copy()
    eligible_option_dates = _unique_dates(eligible_options["trade_date"])
    backtest_dates = sorted(set(price_dates).intersection(eligible_option_dates))

    eligible_option_months = len({(value.year, value.month) for value in eligible_option_dates})
    monthly_roll_dates: list[pd.Timestamp] = []
    selectable_monthly_periods = 0
    if backtest_dates:
        window_start = pd.Timestamp(backtest_dates[0])
        window_end = pd.Timestamp(backtest_dates[-1])
        price_frame = pd.DataFrame({"date": pd.to_datetime(price_dates)})
        price_frame = price_frame[
            price_frame["date"].between(window_start, window_end, inclusive="both")
        ]
        if not price_frame.empty:
            monthly_roll_dates = (
                price_frame.groupby(price_frame["date"].dt.to_period("M"))["date"]
                .max()
                .sort_values()
                .tolist()
            )

        if monthly_roll_dates and not eligible_options.empty:
            eligible_options["trade_date"] = pd.to_datetime(
                eligible_options["trade_date"], errors="coerce"
            )
            eligible_options["expiry"] = pd.to_datetime(
                eligible_options.get("expiry"), errors="coerce"
            )
            for roll_date, next_roll_date in zip(monthly_roll_dates[:-1], monthly_roll_dates[1:]):
                candidates = eligible_options[
                    eligible_options["trade_date"].eq(roll_date)
                    & eligible_options["expiry"].le(next_roll_date)
                ]
                selectable_monthly_periods += int(not candidates.empty)

    available_monthly_periods = max(len(monthly_roll_dates) - 1, 0)

    def bounds(values: list[object]) -> tuple[str | None, str | None]:
        if not values:
            return None, None
        return values[0].isoformat(), values[-1].isoformat()

    price_start, price_end = bounds(price_dates)
    option_start, option_end = bounds(option_dates)
    eligible_start, eligible_end = bounds(eligible_option_dates)
    backtest_start, backtest_end = bounds(backtest_dates)
    return {
        "etf_price_start": price_start,
        "etf_price_end": price_end,
        "etf_trade_dates": len(price_dates),
        "option_start": option_start,
        "option_end": option_end,
        "option_trade_dates": len(option_dates),
        "eligible_option_start": eligible_start,
        "eligible_option_end": eligible_end,
        "eligible_option_trade_dates": len(eligible_option_dates),
        "eligible_option_months": eligible_option_months,
        "backtest_start": backtest_start,
        "backtest_end": backtest_end,
        "backtest_trade_dates": len(backtest_dates),
        "available_monthly_periods": available_monthly_periods,
        "selectable_monthly_periods": selectable_monthly_periods,
        "minimum_monthly_periods_required": MIN_COMPLETE_MONTHLY_PERIODS,
    }


def _prepare_frames(staging_dir: Path, etf_code: str, risk_free_rate: float) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    raw = {
        dataset: _read_input_csv(staging_dir / filename, dataset)
        for dataset, filename in DATASET_FILENAMES.items()
    }

    prices = _normalize_etf_daily(raw["etf_daily"])
    prices["etf_code"] = prices["etf_code"].astype(str).str.zfill(6)
    prices = prices[prices["etf_code"].eq(etf_code)].copy()
    prices = prices.drop_duplicates(["date", "etf_code"], keep="last")
    if prices.empty:
        raise SubmissionValidationError(f"ETF日行情中没有ETF {etf_code} 的记录")

    basic = raw["option_contracts"].copy()
    basic["_underlying_etf"] = basic["underlying_etf"].map(_strip_market_suffix)
    relevant_basic = basic[basic["_underlying_etf"].eq(etf_code)].drop(columns=["_underlying_etf"])
    if relevant_basic.empty:
        raise SubmissionValidationError(f"期权合约中没有标的为 {etf_code} 的记录")

    contract_codes = set(relevant_basic["option_code"].astype(str))
    daily = raw["option_daily"].copy()
    relevant_daily = daily[daily["option_code"].astype(str).isin(contract_codes)].copy()
    if relevant_daily.empty:
        raise SubmissionValidationError(f"期权日行情中没有 {etf_code} 相关合约的记录")

    options = _normalize_options(relevant_daily, relevant_basic)
    options["underlying_etf"] = options["underlying_etf"].astype(str).str.zfill(6)
    options = options[options["underlying_etf"].eq(etf_code)].copy()
    options = options.drop_duplicates(["trade_date", "option_code"], keep="last")
    if options.empty:
        raise SubmissionValidationError("期权合约表与期权日行情无法合并出有效记录")

    delta_options = build_delta_enriched_options(
        prices,
        options,
        {"delta_standardization": {"risk_free_rate": float(risk_free_rate)}},
    )

    calls = delta_options[delta_options["option_type"].astype(str).str.upper().eq("C")].copy()
    eligible = calls[
        calls["days_to_expiry"].between(20, 45, inclusive="both")
        & calls["strike"].gt(0)
        & calls["close"].gt(0)
    ]
    valid_delta = eligible[eligible["delta_valid"].eq(1)]
    date_availability = summarize_backtest_date_availability(prices, delta_options)
    backtest_trade_dates = int(date_availability["backtest_trade_dates"])
    available_monthly_periods = int(date_availability["available_monthly_periods"])
    selectable_monthly_periods = int(date_availability["selectable_monthly_periods"])

    warnings: list[str] = []
    if backtest_trade_dates < 126:
        warnings.append("ETF行情与可用认购期权的共同交易日少于126天，适合试跑但不适合稳健性结论")
    if available_monthly_periods < MIN_COMPLETE_MONTHLY_PERIODS:
        warnings.append(
            f"共同样本只能闭合 {available_monthly_periods} 个完整月度周期，完整研究至少需要 "
            f"{MIN_COMPLETE_MONTHLY_PERIODS} 个"
        )
    if selectable_monthly_periods < MIN_COMPLETE_MONTHLY_PERIODS:
        warnings.append(
            f"月末可实际选出并在下一周期内结算的认购期权只有 {selectable_monthly_periods} 期，"
            f"至少需要 {MIN_COMPLETE_MONTHLY_PERIODS} 期"
        )
    if "bid" not in options.columns or "ask" not in options.columns:
        warnings.append("期权原始表没有买一卖一价，回测将沿用收盘价并使用假设价差成本")

    checks = {
        "has_price_rows": bool(len(prices)),
        "has_option_contracts": bool(len(relevant_basic)),
        "has_option_daily_rows": bool(len(options)),
        "has_common_trade_dates": bool(backtest_trade_dates),
        "has_eligible_calls_dte20_45": bool(len(eligible)),
        "has_valid_target_delta_rows": bool(len(valid_delta)),
        "has_minimum_monthly_periods": available_monthly_periods >= MIN_COMPLETE_MONTHLY_PERIODS,
        "has_minimum_selectable_periods": selectable_monthly_periods >= MIN_COMPLETE_MONTHLY_PERIODS,
    }
    readiness = {
        "ready_for_backtest": all(checks.values()),
        "checks": checks,
        "warnings": warnings,
        "price_rows": int(len(prices)),
        "option_contracts": int(relevant_basic["option_code"].nunique()),
        "option_daily_rows": int(len(options)),
        "call_rows": int(len(calls)),
        "eligible_call_rows": int(len(eligible)),
        "valid_delta_call_rows": int(len(valid_delta)),
        "delta_valid_rate": float(len(valid_delta) / len(eligible)) if len(eligible) else 0.0,
        "common_trade_dates": backtest_trade_dates,
        "sample_start": date_availability["backtest_start"],
        "sample_end": date_availability["backtest_end"],
        "date_availability": date_availability,
    }
    frames = {
        "etf_prices": prices.sort_values("date").reset_index(drop=True),
        "options_daily": options.sort_values(["trade_date", "expiry", "strike", "option_type"]).reset_index(drop=True),
        "delta_enriched_options": delta_options.reset_index(drop=True),
    }
    return frames, readiness


def prepare_etf_submission(
    project_root: str | Path,
    staging_dir: str | Path,
    etf_code: str,
    session_id: str,
    *,
    risk_free_rate: float = 0.02,
) -> dict[str, Any]:
    """Validate provider-neutral ETF inputs and create an isolated research-input package."""

    root = Path(project_root).resolve()
    stage = Path(staging_dir).resolve()
    code = normalize_etf_code(etf_code)
    frames, readiness = _prepare_frames(stage, code, risk_free_rate)

    submission_parent = root / "data" / "user_submissions" / code
    submission_parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    package_name = f"{stamp}_{session_id[:8]}"
    final_dir = submission_parent / package_name
    suffix = 1
    while final_dir.exists():
        final_dir = submission_parent / f"{package_name}_{suffix}"
        suffix += 1
    temp_dir = submission_parent / f".{final_dir.name}.tmp"

    try:
        raw_dir = temp_dir / "raw"
        normalized_dir = temp_dir / "normalized"
        derived_dir = temp_dir / "derived"
        raw_dir.mkdir(parents=True)
        normalized_dir.mkdir(parents=True)
        derived_dir.mkdir(parents=True)

        raw_files: dict[str, dict[str, Any]] = {}
        for dataset, filename in DATASET_FILENAMES.items():
            source = stage / filename
            destination = raw_dir / filename
            shutil.copy2(source, destination)
            raw_files[dataset] = {
                "path": str(destination.relative_to(temp_dir)).replace("\\", "/"),
                "bytes": destination.stat().st_size,
                "sha256": _sha256(destination),
                "dataset_type": dataset,
            }

        frames["etf_prices"].to_csv(normalized_dir / "etf_prices.csv", index=False, encoding="utf-8-sig")
        frames["options_daily"].to_csv(normalized_dir / "options_daily.csv", index=False, encoding="utf-8-sig")
        frames["delta_enriched_options"].to_csv(
            derived_dir / "delta_enriched_options.csv",
            index=False,
            encoding="utf-8-sig",
        )

        manifest = {
            "schema_version": "1.0",
            "submission_id": final_dir.name,
            "etf_code": code,
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "source_contract": {
                "provider": "user_supplied",
                "input_schema": "project_etf_input_v1",
                "datasets": ["etf_daily", "option_contracts", "option_daily"],
                "verification": "仅校验项目字段、数据类型、关联关系和共同样本；不认证外部数据来源",
                "metadata_required": False,
            },
            "model_assumptions": {
                "risk_free_rate": float(risk_free_rate),
                "delta_model": "Black-Scholes",
                "target_dte_window": [20, 45],
            },
            "raw_files": raw_files,
            "outputs": {
                "etf_prices": "normalized/etf_prices.csv",
                "options_daily": "normalized/options_daily.csv",
                "delta_enriched_options": "derived/delta_enriched_options.csv",
            },
            "readiness": readiness,
        }
        (temp_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_dir.rename(final_dir)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)

    relative_dir = str(final_dir.relative_to(root)).replace("\\", "/")
    return {
        "ok": True,
        "etf_code": code,
        "submission_id": final_dir.name,
        "package_path": relative_dir,
        "manifest_path": f"{relative_dir}/manifest.json",
        "readiness": readiness,
    }
