import json
from pathlib import Path

import pandas as pd
import pytest

from src.data.etf_submission import SubmissionValidationError, prepare_tushare_submission


def _write_tushare_fixture(stage: Path, *, include_fund_amount: bool = True) -> None:
    stage.mkdir(parents=True)
    fund = pd.DataFrame(
        [
            {
                "ts_code": "510300.SH",
                "trade_date": 20240102,
                "pre_close": 2.99,
                "open": 3.00,
                "high": 3.03,
                "low": 2.98,
                "close": 3.00,
                "change": 0.01,
                "pct_chg": 0.33,
                "vol": 100000,
                "amount": 300000,
            },
            {
                "ts_code": "510300.SH",
                "trade_date": 20240103,
                "pre_close": 3.00,
                "open": 3.01,
                "high": 3.05,
                "low": 3.00,
                "close": 3.02,
                "change": 0.02,
                "pct_chg": 0.67,
                "vol": 110000,
                "amount": 330000,
            },
        ]
    )
    if not include_fund_amount:
        fund = fund.drop(columns="amount")
    fund.to_csv(stage / "tushare_fund_daily_raw.csv", index=False)

    pd.DataFrame(
        [
            {
                "ts_code": "10000001.SH",
                "exchange": "SSE",
                "name": "300ETF购2月3100",
                "per_unit": 10000,
                "opt_code": "510300.SH",
                "opt_type": "ETF期权",
                "call_put": "C",
                "exercise_type": "欧式",
                "exercise_price": 3.10,
                "s_month": "202402",
                "maturity_date": 20240202,
                "list_price": 0.08,
                "list_date": 20231201,
                "delist_date": 20240202,
                "last_edate": 20240202,
                "last_ddate": 20240202,
                "quote_unit": 0.0001,
                "min_price_chg": 0.0001,
            }
        ]
    ).to_csv(stage / "tushare_opt_basic_raw.csv", index=False)

    pd.DataFrame(
        [
            {
                "ts_code": "10000001.SH",
                "trade_date": 20240102,
                "exchange": "SSE",
                "pre_settle": 0.08,
                "pre_close": 0.08,
                "open": 0.08,
                "high": 0.09,
                "low": 0.07,
                "close": 0.08,
                "settle": 0.08,
                "vol": 1000,
                "amount": 80000,
                "oi": 5000,
            },
            {
                "ts_code": "10000001.SH",
                "trade_date": 20240103,
                "exchange": "SSE",
                "pre_settle": 0.08,
                "pre_close": 0.08,
                "open": 0.09,
                "high": 0.10,
                "low": 0.08,
                "close": 0.09,
                "settle": 0.09,
                "vol": 1200,
                "amount": 108000,
                "oi": 5200,
            },
        ]
    ).to_csv(stage / "tushare_opt_daily_raw.csv", index=False)


def test_prepare_tushare_submission_without_metadata(tmp_path: Path) -> None:
    project = tmp_path / "project"
    stage = tmp_path / "stage"
    _write_tushare_fixture(stage)

    result = prepare_tushare_submission(project, stage, "510300", "session_12345678")

    assert result["ok"] is True
    assert result["readiness"]["ready_for_backtest"] is True
    assert result["readiness"]["price_rows"] == 2
    assert result["readiness"]["option_daily_rows"] == 2
    package = project / result["package_path"]
    assert (package / "raw" / "tushare_fund_daily_raw.csv").is_file()
    assert (package / "normalized" / "etf_prices.csv").is_file()
    assert (package / "derived" / "delta_enriched_options.csv").is_file()
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_contract"]["provider"] == "Tushare"
    assert manifest["source_contract"]["metadata_required"] is False
    assert manifest["source_contract"]["datasets"] == ["fund_daily", "opt_basic", "opt_daily"]
    assert not stage.exists()


def test_prepare_rejects_non_tushare_raw_schema(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    _write_tushare_fixture(stage, include_fund_amount=False)

    with pytest.raises(SubmissionValidationError, match="Tushare fund_daily"):
        prepare_tushare_submission(tmp_path / "project", stage, "510300", "session_12345678")
