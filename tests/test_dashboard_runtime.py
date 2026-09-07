import json
from pathlib import Path

import pandas as pd
import pytest

from src.dashboard_runtime import (
    DashboardRuntimeError,
    list_submission_packages,
    load_published_portfolio,
    load_published_results,
    load_published_surfaces,
    load_submission_manifest,
    publish_backtest_result,
    publish_parameter_surface,
    publish_portfolio_result,
    run_parameter_surface,
    run_portfolio_backtest,
    run_submission_backtest,
)


def _build_ready_submission(root: Path, etf_code: str = "510300", submission_id: str = "submission_001") -> str:
    package = root / "data" / "user_submissions" / etf_code / submission_id
    normalized = package / "normalized"
    derived = package / "derived"
    normalized.mkdir(parents=True)
    derived.mkdir(parents=True)

    dates = pd.bdate_range("2024-01-02", "2025-06-30")
    prices = pd.DataFrame(
        {
            "date": dates,
            "etf_code": etf_code,
            "open": 3.0,
            "high": 3.1,
            "low": 2.9,
            "close": [3.0 + index * 0.001 for index in range(len(dates))],
            "adj_close": [3.0 + index * 0.001 for index in range(len(dates))],
            "volume": 100000.0,
            "amount": 300000.0,
        }
    )
    prices.to_csv(normalized / "etf_prices.csv", index=False)

    roll_dates = pd.Series(dates, index=dates).groupby(dates.to_period("M")).last().tolist()
    option_rows = []
    for index, roll_date in enumerate(roll_dates[:-1]):
        expiry = pd.Timestamp(roll_date) + pd.Timedelta(days=21)
        spot = float(prices.loc[prices["date"].eq(roll_date), "adj_close"].iloc[0])
        option_rows.append(
            {
                "trade_date": roll_date,
                "option_code": f"OPT{index:03d}",
                "underlying_etf": etf_code,
                "option_type": "C",
                "expiry": expiry,
                "strike": spot * 1.03,
                "close": 0.05,
                "volume": 1000,
                "open_interest": 5000,
                "model_delta": 0.30,
                "model_iv": 0.20,
            }
        )
    pd.DataFrame(option_rows).to_csv(derived / "delta_enriched_options.csv", index=False)

    manifest = {
        "schema_version": "1.0",
        "submission_id": package.name,
        "etf_code": etf_code,
        "created_at": "2024-11-01T10:00:00+08:00",
        "outputs": {
            "etf_prices": "normalized/etf_prices.csv",
            "delta_enriched_options": "derived/delta_enriched_options.csv",
        },
        "readiness": {
            "ready_for_backtest": True,
            "sample_start": "2024-01-02",
            "sample_end": "2024-10-31",
            "common_trade_dates": len(dates),
            "warnings": [],
        },
    }
    (package / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return f"data/user_submissions/{etf_code}/{submission_id}/manifest.json"


def test_dynamic_backtest_preview_and_publish(tmp_path: Path) -> None:
    manifest_path = _build_ready_submission(tmp_path)

    submissions = list_submission_packages(tmp_path)
    assert len(submissions) == 1
    assert submissions[0]["ready_for_backtest"] is True
    assert submissions[0]["date_availability"]["eligible_option_trade_dates"] == 17
    assert submissions[0]["sample_start"] == "2024-01-31"
    assert submissions[0]["sample_end"] == "2025-05-30"
    assert submissions[0]["date_availability"]["available_monthly_periods"] == 16
    assert submissions[0]["date_availability"]["selectable_monthly_periods"] == 16

    preview = run_submission_backtest(
        tmp_path,
        manifest_path,
        {
            "start_date": submissions[0]["sample_start"],
            "end_date": submissions[0]["sample_end"],
            "target_delta": 0.30,
            "coverage_ratio": 0.70,
        },
    )

    assert preview["publication_status"] == "preview"
    assert preview["parameters"]["coverage_ratio"] == 0.70
    assert preview["diagnostics"]["selected_periods"] >= 12
    assert preview["audit"]["status"] == "passed"
    assert preview["audit"]["cycle_count"] >= 12
    assert preview["cycles"]
    assert preview["drawdown"]
    assert preview["daily_mtm"]
    assert preview["audit"]["daily_mtm_quality"]["max_period_end_reconciliation_error"] <= 1e-10
    assert preview["cycle_validation"]["ledger"]
    assert "earlyclose" in preview["cycle_validation"]["capabilities"]
    assert preview["cycle_validation"]["delta_buyback"]["summary"]
    assert preview["cycle_validation"]["delta_buyback"]["daily"]
    assert preview["cycle_validation"]["tp80_buyback"]["summary"]
    run_manifest = tmp_path / preview["run_manifest_path"]
    assert run_manifest.is_file()
    assert (run_manifest.parent / "summary.csv").is_file()
    assert (run_manifest.parent / "periods.csv").is_file()
    assert (run_manifest.parent / "nav.csv").is_file()
    assert (run_manifest.parent / "drawdown.csv").is_file()
    assert (run_manifest.parent / "daily_mtm.csv").is_file()
    assert (run_manifest.parent / "cycle_ledger.csv").is_file()
    assert (run_manifest.parent / "cycle_cashflow_summary.csv").is_file()
    assert (run_manifest.parent / "rolling_12_cycle_cashflow.csv").is_file()
    assert (run_manifest.parent / "cycle_regime_attribution.csv").is_file()
    assert (run_manifest.parent / "delta_buyback_ledger.csv").is_file()
    assert (run_manifest.parent / "delta_buyback_daily.csv").is_file()
    assert (run_manifest.parent / "tp80_buyback_daily.csv").is_file()
    assert (run_manifest.parent / "research_audit.json").is_file()

    published = publish_backtest_result(tmp_path, preview["run_manifest_path"])
    assert published["ok"] is True
    assert published["published"]["publication_status"] == "published"
    current = load_published_results(tmp_path)
    assert current["current"]["etf_code"] == "510300"
    assert current["latest_by_etf"]["510300"]["run_id"] == preview["run_id"]


def test_dynamic_backtest_rejects_dates_outside_eligible_option_window(tmp_path: Path) -> None:
    manifest_path = _build_ready_submission(tmp_path)

    with pytest.raises(DashboardRuntimeError, match="可用期权样本"):
        run_submission_backtest(
            tmp_path,
            manifest_path,
            {
                "start_date": "2024-01-02",
                "end_date": "2025-06-30",
                "target_delta": 0.30,
                "coverage_ratio": 1.0,
            },
        )


def test_dynamic_backtest_rejects_manifest_path_outside_submission_root(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text("{}", encoding="utf-8")

    with pytest.raises(DashboardRuntimeError, match="超出允许范围"):
        load_submission_manifest(tmp_path, "manifest.json")


def test_builtin_etf_uses_same_engine_with_user_selected_window(tmp_path: Path) -> None:
    manifest_path = _build_ready_submission(tmp_path)
    manifest = json.loads((tmp_path / manifest_path).read_text(encoding="utf-8"))
    package = (tmp_path / manifest_path).parent
    raw_dir = tmp_path / "data" / "raw"
    source_dir = tmp_path / "data" / "source"
    raw_dir.mkdir(parents=True, exist_ok=True)
    source_dir.mkdir(parents=True, exist_ok=True)
    pd.read_csv(package / manifest["outputs"]["etf_prices"]).to_csv(raw_dir / "etf_prices.csv", index=False)
    pd.read_csv(package / manifest["outputs"]["delta_enriched_options"]).to_csv(
        source_dir / "delta_enriched_options.csv", index=False
    )

    builtin = next(item for item in list_submission_packages(tmp_path) if item["manifest_path"] == "builtin:510300")
    assert builtin["ready_for_backtest"] is True
    preview = run_submission_backtest(
        tmp_path,
        "builtin:510300",
        {
            "start_date": "2024-04-30",
            "end_date": "2025-05-30",
            "target_delta": 0.30,
            "coverage_ratio": 0.70,
            "include_early_close": False,
        },
    )

    assert preview["sample"] == {"start": "2024-04-30", "end": "2025-05-30"}
    assert preview["source_submission"] == "builtin:510300"
    assert preview["audit"]["cycle_count"] >= 12


def test_dynamic_backtest_supports_otm_selection(tmp_path: Path) -> None:
    manifest_path = _build_ready_submission(tmp_path)
    package = list_submission_packages(tmp_path)[0]
    preview = run_submission_backtest(
        tmp_path,
        manifest_path,
        {
            "start_date": package["sample_start"],
            "end_date": package["sample_end"],
            "selection_mode": "otm_pct",
            "otm_pct": 0.03,
            "coverage_ratio": 0.80,
            "include_early_close": False,
        },
    )

    assert preview["parameters"]["selection_mode"] == "otm_pct"
    assert preview["parameters"]["otm_pct"] == 0.03
    assert any(row["strategy_name"] == "OTM03_Q080" for row in preview["cycle_validation"]["summary"])


def test_dynamic_parameter_surface_builds_real_grid_and_can_be_published(tmp_path: Path) -> None:
    manifest_path = _build_ready_submission(tmp_path)
    package = list_submission_packages(tmp_path)[0]
    preview = run_parameter_surface(
        tmp_path,
        manifest_path,
        {
            "start_date": package["sample_start"],
            "end_date": package["sample_end"],
            "target_deltas": [0.20, 0.30],
            "coverages": [0.50, 1.00],
        },
    )

    assert preview["publication_status"] == "preview"
    assert preview["sample"] == {"start": package["sample_start"], "end": package["sample_end"]}
    assert len(preview["surface_grid"]) == 4
    assert preview["audit"]["engine_runs"] == 2
    assert preview["audit"]["status"] == "passed"
    assert preview["buyhold"]["parameter_grid_role"] == "buyhold"
    assert {row["target_delta"] for row in preview["surface_grid"]} == {0.20, 0.30}
    assert {row["coverage"] for row in preview["surface_grid"]} == {0.50, 1.00}
    assert all(row["surface_axis_type"] == "target_delta" for row in preview["surface_grid"])
    surface_manifest = tmp_path / preview["surface_manifest_path"]
    assert surface_manifest.is_file()
    assert (surface_manifest.parent / "surface_grid.csv").is_file()
    assert (surface_manifest.parent / "buyhold.csv").is_file()

    published = publish_parameter_surface(tmp_path, preview["surface_manifest_path"])
    assert published["published"]["publication_status"] == "published"
    current = load_published_surfaces(tmp_path)
    assert current["latest_by_etf"]["510300"]["run_id"] == preview["run_id"]


def test_dynamic_parameter_surface_rejects_excessive_grid(tmp_path: Path) -> None:
    manifest_path = _build_ready_submission(tmp_path)
    package = list_submission_packages(tmp_path)[0]
    with pytest.raises(DashboardRuntimeError, match="最多允许"):
        run_parameter_surface(
            tmp_path,
            manifest_path,
            {
                "start_date": package["sample_start"],
                "end_date": package["sample_end"],
                "target_deltas": [value / 100 for value in range(10, 21)],
                "coverages": [value / 100 for value in range(10, 101, 10)],
            },
        )


def test_custom_portfolio_runs_on_common_periods_and_can_be_saved(tmp_path: Path) -> None:
    manifest_a = _build_ready_submission(tmp_path, "510300", "submission_a")
    manifest_b = _build_ready_submission(tmp_path, "510050", "submission_b")
    packages = {item["etf_code"]: item for item in list_submission_packages(tmp_path)}
    preview = run_portfolio_backtest(
        tmp_path,
        {
            "start_date": packages["510300"]["sample_start"],
            "end_date": packages["510300"]["sample_end"],
            "legs": [
                {
                    "etf_code": "510300", "manifest_path": manifest_a, "weight": 0.60,
                    "selection_mode": "target_delta", "target_delta": 0.30,
                    "coverage_ratio": 0.70,
                },
                {
                    "etf_code": "510050", "manifest_path": manifest_b, "weight": 0.40,
                    "selection_mode": "atm", "coverage_ratio": 0.50,
                },
            ],
        },
    )

    assert preview["publication_status"] == "preview"
    assert preview["accounting_mode"] == "fixed_weight_monthly_rebalanced_daily_mtm"
    assert preview["audit"]["status"] == "passed"
    assert preview["audit"]["common_periods"] >= 12
    assert preview["audit"]["common_daily_observations"] > preview["audit"]["common_periods"]
    assert preview["audit"]["max_month_end_reconciliation_error"] <= 1e-10
    assert preview["daily_mtm"]
    assert preview["summary"]["daily_observations"] == len(preview["daily_mtm"])
    assert len(preview["contributions"]) == 2
    run_manifest = tmp_path / preview["run_manifest_path"]
    assert run_manifest.is_file()
    assert (run_manifest.parent / "monthly_returns.csv").is_file()
    assert (run_manifest.parent / "daily_mtm.csv").is_file()
    assert (run_manifest.parent / "sleeve_contributions.csv").is_file()

    published = publish_portfolio_result(tmp_path, preview["run_manifest_path"])
    assert published["published"]["publication_status"] == "published"
    current = load_published_portfolio(tmp_path)
    assert current["current"]["run_id"] == preview["run_id"]


def test_custom_portfolio_rejects_invalid_weight_sum(tmp_path: Path) -> None:
    manifest_a = _build_ready_submission(tmp_path, "510300", "submission_a")
    manifest_b = _build_ready_submission(tmp_path, "510050", "submission_b")
    packages = {item["etf_code"]: item for item in list_submission_packages(tmp_path)}
    with pytest.raises(DashboardRuntimeError, match="100%"):
        run_portfolio_backtest(
            tmp_path,
            {
                "start_date": packages["510300"]["sample_start"],
                "end_date": packages["510300"]["sample_end"],
                "legs": [
                    {"etf_code": "510300", "manifest_path": manifest_a, "weight": 0.60},
                    {"etf_code": "510050", "manifest_path": manifest_b, "weight": 0.30},
                ],
            },
        )
