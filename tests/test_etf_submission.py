import json
from pathlib import Path

import pandas as pd
import pytest

from src.data.etf_submission import SubmissionValidationError, prepare_etf_submission


def _write_input_fixture(
    stage: Path,
    *,
    include_fund_amount: bool = True,
    generic_columns: bool = False,
) -> None:
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
    if generic_columns:
        fund = fund.rename(columns={"ts_code": "etf_code", "vol": "volume"})
        fund["trade_date"] = ["2024-01-02", "2024-01-03"]
    fund.to_csv(stage / "etf_daily.csv", index=False)

    contracts = pd.DataFrame(
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
    )
    if generic_columns:
        contracts = contracts.drop(columns="opt_type").rename(
            columns={
                "ts_code": "option_code",
                "opt_code": "underlying_etf",
                "call_put": "option_type",
                "exercise_price": "strike",
                "maturity_date": "expiry",
            }
        )
        contracts["expiry"] = "2024-02-02"
    contracts.to_csv(stage / "option_contracts.csv", index=False)

    option_daily = pd.DataFrame(
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
    )
    if generic_columns:
        option_daily = option_daily.rename(
            columns={"ts_code": "option_code", "vol": "volume", "oi": "open_interest"}
        )
        option_daily["trade_date"] = ["2024-01-02", "2024-01-03"]
    option_daily.to_csv(stage / "option_daily.csv", index=False)


def _write_long_provider_neutral_fixture(stage: Path) -> None:
    stage.mkdir(parents=True)
    dates = pd.bdate_range("2024-01-02", "2025-06-30")
    closes = pd.Series([3.0 + index * 0.0005 for index in range(len(dates))], index=dates)
    pd.DataFrame(
        {
            "etf_code": "510300",
            "trade_date": dates.strftime("%Y-%m-%d"),
            "open": closes.values,
            "high": closes.values + 0.02,
            "low": closes.values - 0.02,
            "close": closes.values,
            "volume": 100000,
            "amount": 300000,
        }
    ).to_csv(stage / "etf_daily.csv", index=False)

    roll_dates = pd.Series(dates, index=dates).groupby(dates.to_period("M")).last().tolist()
    contracts = []
    daily = []
    for index, roll_date in enumerate(roll_dates[:-1]):
        option_code = f"OPT{index:03d}"
        expiry = pd.Timestamp(roll_date) + pd.Timedelta(days=21)
        contracts.append(
            {
                "option_code": option_code,
                "underlying_etf": "510300",
                "option_type": "C",
                "strike": float(closes.loc[roll_date] * 1.03),
                "expiry": expiry.date().isoformat(),
            }
        )
        daily.append(
            {
                "option_code": option_code,
                "trade_date": pd.Timestamp(roll_date).date().isoformat(),
                "close": 0.05,
                "volume": 1000,
                "amount": 50000,
                "open_interest": 5000,
            }
        )
    pd.DataFrame(contracts).to_csv(stage / "option_contracts.csv", index=False)
    pd.DataFrame(daily).to_csv(stage / "option_daily.csv", index=False)


def test_prepare_submission_without_metadata_accepts_existing_column_aliases(tmp_path: Path) -> None:
    project = tmp_path / "project"
    stage = tmp_path / "stage"
    _write_input_fixture(stage)

    result = prepare_etf_submission(project, stage, "510300", "session_12345678")

    assert result["ok"] is True
    assert result["readiness"]["ready_for_backtest"] is False
    assert result["readiness"]["price_rows"] == 2
    assert result["readiness"]["option_daily_rows"] == 2
    availability = result["readiness"]["date_availability"]
    assert availability["etf_price_start"] == "2024-01-02"
    assert availability["option_start"] == "2024-01-02"
    assert availability["eligible_option_start"] == "2024-01-02"
    assert availability["backtest_start"] == "2024-01-02"
    assert availability["backtest_end"] == "2024-01-03"
    assert availability["backtest_trade_dates"] == 2
    assert availability["available_monthly_periods"] == 0
    assert availability["selectable_monthly_periods"] == 0
    assert result["readiness"]["checks"]["has_minimum_monthly_periods"] is False
    package = project / result["package_path"]
    assert (package / "raw" / "etf_daily.csv").is_file()
    assert (package / "normalized" / "etf_prices.csv").is_file()
    assert (package / "derived" / "delta_enriched_options.csv").is_file()
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_contract"]["provider"] == "user_supplied"
    assert manifest["source_contract"]["input_schema"] == "project_etf_input_v1"
    assert manifest["source_contract"]["metadata_required"] is False
    assert manifest["source_contract"]["datasets"] == ["etf_daily", "option_contracts", "option_daily"]
    assert not stage.exists()


def test_prepare_accepts_provider_neutral_columns_and_iso_dates(tmp_path: Path) -> None:
    project = tmp_path / "project"
    stage = tmp_path / "stage"
    _write_long_provider_neutral_fixture(stage)

    result = prepare_etf_submission(project, stage, "510300", "session_12345678")

    assert result["ok"] is True
    assert result["readiness"]["ready_for_backtest"] is True
    assert result["readiness"]["date_availability"]["eligible_option_trade_dates"] == 17
    assert result["readiness"]["date_availability"]["available_monthly_periods"] == 16
    assert result["readiness"]["date_availability"]["selectable_monthly_periods"] == 16


def test_prepare_rejects_missing_project_field(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    _write_input_fixture(stage, include_fund_amount=False)

    with pytest.raises(SubmissionValidationError, match="项目ETF日行情格式"):
        prepare_etf_submission(tmp_path / "project", stage, "510300", "session_12345678")
