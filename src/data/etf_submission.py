from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.data.tushare_source import normalize_tushare_fund_daily, normalize_tushare_options, strip_ts_suffix
from src.features.delta_surface import build_delta_enriched_options


DATASET_FILENAMES = {
    "fund_daily": "tushare_fund_daily_raw.csv",
    "opt_basic": "tushare_opt_basic_raw.csv",
    "opt_daily": "tushare_opt_daily_raw.csv",
}

TUSHARE_REQUIRED_COLUMNS = {
    "fund_daily": {"ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount"},
    "opt_basic": {
        "ts_code",
        "exchange",
        "opt_code",
        "call_put",
        "exercise_price",
        "maturity_date",
    },
    "opt_daily": {"ts_code", "trade_date", "exchange", "close", "vol", "amount", "oi"},
}

ETF_CODE_PATTERN = re.compile(r"^\d{6}$")


class SubmissionValidationError(ValueError):
    pass


def normalize_etf_code(value: object) -> str:
    code = str(value or "").strip().split(".")[0]
    if not ETF_CODE_PATTERN.fullmatch(code):
        raise SubmissionValidationError("ETF代码必须是6位数字")
    return code


def _read_tushare_csv(path: Path, dataset: str) -> pd.DataFrame:
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
    missing = sorted(TUSHARE_REQUIRED_COLUMNS[dataset] - set(frame.columns))
    if missing:
        raise SubmissionValidationError(
            f"{path.name} 不符合Tushare {dataset} 原始表结构，缺少字段：{', '.join(missing)}"
        )
    if frame.empty:
        raise SubmissionValidationError(f"{path.name} 没有数据行")
    return frame


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


def _prepare_frames(staging_dir: Path, etf_code: str, risk_free_rate: float) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    raw = {
        dataset: _read_tushare_csv(staging_dir / filename, dataset)
        for dataset, filename in DATASET_FILENAMES.items()
    }

    prices = normalize_tushare_fund_daily(raw["fund_daily"])
    prices["etf_code"] = prices["etf_code"].astype(str).str.zfill(6)
    prices = prices[prices["etf_code"].eq(etf_code)].copy()
    prices = prices.drop_duplicates(["date", "etf_code"], keep="last")
    if prices.empty:
        raise SubmissionValidationError(f"fund_daily 中没有ETF {etf_code} 的日行情")

    basic = raw["opt_basic"].copy()
    basic["_underlying_etf"] = basic["opt_code"].map(strip_ts_suffix)
    relevant_basic = basic[basic["_underlying_etf"].eq(etf_code)].drop(columns=["_underlying_etf"])
    if relevant_basic.empty:
        raise SubmissionValidationError(f"opt_basic 中没有标的为 {etf_code} 的期权合约")

    contract_codes = set(relevant_basic["ts_code"].astype(str))
    daily = raw["opt_daily"].copy()
    relevant_daily = daily[daily["ts_code"].astype(str).isin(contract_codes)].copy()
    if relevant_daily.empty:
        raise SubmissionValidationError(f"opt_daily 中没有 {etf_code} 相关合约的日行情")

    options = normalize_tushare_options(relevant_daily, relevant_basic)
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

    option_dates = pd.to_datetime(options["trade_date"])
    price_dates = pd.to_datetime(prices["date"])
    calls = delta_options[delta_options["option_type"].astype(str).str.upper().eq("C")].copy()
    eligible = calls[
        calls["days_to_expiry"].between(20, 45, inclusive="both")
        & calls["strike"].gt(0)
        & calls["close"].gt(0)
    ]
    valid_delta = eligible[eligible["delta_valid"].eq(1)]
    common_dates = set(price_dates.dt.date).intersection(set(option_dates.dt.date))

    warnings: list[str] = []
    if len(common_dates) < 126:
        warnings.append("ETF行情与期权行情的共同交易日少于126天，适合试跑但不适合稳健性结论")
    if "bid" not in options.columns or "ask" not in options.columns:
        warnings.append("期权原始表没有买一卖一价，回测将沿用收盘价并使用假设价差成本")

    checks = {
        "has_price_rows": bool(len(prices)),
        "has_option_contracts": bool(len(relevant_basic)),
        "has_option_daily_rows": bool(len(options)),
        "has_common_trade_dates": bool(common_dates),
        "has_eligible_calls_dte20_45": bool(len(eligible)),
        "has_valid_target_delta_rows": bool(len(valid_delta)),
    }
    readiness = {
        "ready_for_backtest": all(checks.values()),
        "checks": checks,
        "warnings": warnings,
        "price_rows": int(len(prices)),
        "option_contracts": int(relevant_basic["ts_code"].nunique()),
        "option_daily_rows": int(len(options)),
        "call_rows": int(len(calls)),
        "eligible_call_rows": int(len(eligible)),
        "valid_delta_call_rows": int(len(valid_delta)),
        "delta_valid_rate": float(len(valid_delta) / len(eligible)) if len(eligible) else 0.0,
        "common_trade_dates": int(len(common_dates)),
        "sample_start": _date_text(max(price_dates.min(), option_dates.min())),
        "sample_end": _date_text(min(price_dates.max(), option_dates.max())),
    }
    frames = {
        "etf_prices": prices.sort_values("date").reset_index(drop=True),
        "options_daily": options.sort_values(["trade_date", "expiry", "strike", "option_type"]).reset_index(drop=True),
        "delta_enriched_options": delta_options.reset_index(drop=True),
    }
    return frames, readiness


def prepare_tushare_submission(
    project_root: str | Path,
    staging_dir: str | Path,
    etf_code: str,
    session_id: str,
    *,
    risk_free_rate: float = 0.02,
) -> dict[str, Any]:
    """Validate three Tushare raw exports and create an isolated research-input package."""

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
                "tushare_endpoint": dataset,
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
                "provider": "Tushare",
                "datasets": ["fund_daily", "opt_basic", "opt_daily"],
                "verification": "Tushare原始字段结构校验；不等同于对文件来源做密码学认证",
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
