from __future__ import annotations

import argparse
import json
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CODES = ("510050", "510300", "159919", "159915", "159922")
DATASETS = {
    "etf_daily": "etf_daily.csv",
    "option_contracts": "option_contracts.csv",
    "option_daily": "option_daily.csv",
}


def _request_json(
    base_url: str,
    endpoint: str,
    *,
    action: str,
    payload: dict[str, Any] | None = None,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 900,
) -> dict[str, Any]:
    request_headers = {"X-Dashboard-Action": action, **(headers or {})}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    else:
        request_headers["Content-Type"] = "application/octet-stream"
    request = Request(
        f"{base_url.rstrip('/')}{endpoint}",
        data=body,
        headers=request_headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{endpoint} 返回 HTTP {exc.code}: {detail}") from exc
    if not isinstance(result, dict) or result.get("ok") is False:
        raise RuntimeError(f"{endpoint} 未通过：{result}")
    return result


def _upload_package(base_url: str, package_dir: Path, etf_code: str) -> dict[str, Any]:
    session_id = f"final{datetime.now():%Y%m%d%H%M%S}{etf_code}{secrets.token_hex(3)}"
    uploads = {}
    for dataset, filename in DATASETS.items():
        path = package_dir / filename
        if not path.is_file():
            raise FileNotFoundError(path)
        uploads[dataset] = _request_json(
            base_url,
            "/__dashboard/submit-etf/upload",
            action="upload-etf-data",
            body=path.read_bytes(),
            headers={
                "X-ETF-Code": etf_code,
                "X-Upload-Session": session_id,
                "X-Dataset-Type": dataset,
            },
        )
    prepared = _request_json(
        base_url,
        "/__dashboard/submit-etf/prepare",
        action="prepare-etf-data",
        payload={"etf_code": etf_code, "session_id": session_id},
    )
    if not prepared.get("readiness", {}).get("ready_for_backtest"):
        raise RuntimeError(f"ETF {etf_code} 未达到完整回测条件：{prepared}")
    prepared["uploads"] = uploads
    return prepared


def _quote_ratio(result: dict[str, Any]) -> float:
    quality = result.get("audit", {}).get("daily_mtm_quality", {})
    return float(quality.get("exact_option_quote_ratio", 0.0))


def run_acceptance(base_url: str, sample_root: Path, etf_codes: list[str]) -> dict[str, Any]:
    uploaded: dict[str, dict[str, Any]] = {}
    single_results: list[dict[str, Any]] = []
    surface_results: list[dict[str, Any]] = []

    for code in etf_codes:
        print(f"[acceptance] 上传并处理 {code}", flush=True)
        prepared = _upload_package(base_url, sample_root / code, code)
        uploaded[code] = prepared
        readiness = prepared["readiness"]
        sample_start = readiness["sample_start"]
        sample_end = readiness["sample_end"]
        manifest_path = prepared["manifest_path"]

        print(f"[acceptance] 单券回测 {code}: {sample_start} -> {sample_end}", flush=True)
        backtest = _request_json(
            base_url,
            "/__dashboard/backtest/run",
            action="run-backtest",
            payload={
                "manifest_path": manifest_path,
                "start_date": sample_start,
                "end_date": sample_end,
                "selection_mode": "target_delta",
                "target_delta": 0.30,
                "coverage_ratio": 1.0,
            },
        )
        if backtest.get("audit", {}).get("status") != "passed":
            raise RuntimeError(f"ETF {code} 单券审计未通过")
        quote_ratio = _quote_ratio(backtest)
        if quote_ratio < 0.99:
            raise RuntimeError(f"ETF {code} 精确期权日行情覆盖率不足：{quote_ratio:.2%}")
        _request_json(
            base_url,
            "/__dashboard/backtest/publish",
            action="publish-backtest",
            payload={"run_manifest_path": backtest["run_manifest_path"]},
        )
        single_results.append(
            {
                "etf_code": code,
                "sample": backtest["sample"],
                "cycles": backtest["audit"]["cycle_count"],
                "selected_option_cycles": backtest["audit"]["selected_option_cycles"],
                "daily_mtm_rows": len(backtest.get("daily_mtm", [])),
                "exact_option_quote_ratio": quote_ratio,
                "max_reconciliation_error": backtest["audit"]
                .get("daily_mtm_quality", {})
                .get("max_period_end_reconciliation_error"),
                "run_manifest_path": backtest["run_manifest_path"],
            }
        )

        print(f"[acceptance] 生成50点参数图谱 {code}", flush=True)
        surface = _request_json(
            base_url,
            "/__dashboard/surface/run",
            action="run-surface",
            payload={
                "manifest_path": manifest_path,
                "start_date": sample_start,
                "end_date": sample_end,
                "target_deltas": [0.10, 0.20, 0.30, 0.40, 0.50],
                "coverages": [value / 10 for value in range(1, 11)],
            },
        )
        if surface.get("audit", {}).get("status") != "passed":
            raise RuntimeError(f"ETF {code} 参数图谱审计未通过")
        if len(surface.get("surface_grid", [])) != 50:
            raise RuntimeError(f"ETF {code} 参数图谱不是50个格点")
        _request_json(
            base_url,
            "/__dashboard/surface/publish",
            action="publish-surface",
            payload={"surface_manifest_path": surface["surface_manifest_path"]},
        )
        surface_results.append(
            {
                "etf_code": code,
                "sample": surface["sample"],
                "grid_points": len(surface["surface_grid"]),
                "engine_runs": surface["audit"]["engine_runs"],
                "surface_manifest_path": surface["surface_manifest_path"],
            }
        )

    common_start = max(item["readiness"]["sample_start"] for item in uploaded.values())
    common_end = min(item["readiness"]["sample_end"] for item in uploaded.values())
    print(f"[acceptance] 五券日频组合: {common_start} -> {common_end}", flush=True)
    portfolio = _request_json(
        base_url,
        "/__dashboard/portfolio/run",
        action="run-portfolio",
        payload={
            "start_date": common_start,
            "end_date": common_end,
            "legs": [
                {
                    "etf_code": code,
                    "manifest_path": uploaded[code]["manifest_path"],
                    "weight": 0.20,
                    "selection_mode": "target_delta",
                    "target_delta": 0.30,
                    "coverage_ratio": 1.0,
                }
                for code in etf_codes
            ],
        },
    )
    audit = portfolio.get("audit", {})
    if audit.get("status") != "passed":
        raise RuntimeError("五券组合审计未通过")
    if float(audit.get("minimum_exact_option_quote_ratio", 0.0)) < 0.99:
        raise RuntimeError("五券组合精确期权日行情覆盖率不足99%")
    if float(audit.get("max_month_end_reconciliation_error", 1.0)) > 1e-10:
        raise RuntimeError("五券组合月末对账误差超限")
    _request_json(
        base_url,
        "/__dashboard/portfolio/publish",
        action="publish-portfolio",
        payload={"run_manifest_path": portfolio["run_manifest_path"]},
    )

    result = {
        "status": "passed",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "dashboard_url": base_url,
        "etf_codes": etf_codes,
        "common_window": {"start": common_start, "end": common_end},
        "single_etf_backtests": single_results,
        "parameter_surfaces": surface_results,
        "portfolio": {
            "accounting_mode": portfolio["accounting_mode"],
            "common_periods": audit["common_periods"],
            "common_daily_observations": audit["common_daily_observations"],
            "minimum_exact_option_quote_ratio": audit[
                "minimum_exact_option_quote_ratio"
            ],
            "max_month_end_reconciliation_error": audit[
                "max_month_end_reconciliation_error"
            ],
            "annualized_return": portfolio["summary"]["annualized_return"],
            "sharpe_ratio": portfolio["summary"]["sharpe_ratio"],
            "max_drawdown": portfolio["summary"]["max_drawdown"],
            "run_manifest_path": portfolio["run_manifest_path"],
        },
    }
    output_dir = ROOT / "outputs" / "final_acceptance"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "five_etf_acceptance.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="运行统一看板五ETF完整日频验收")
    parser.add_argument("--base-url", default="http://127.0.0.1:8766")
    parser.add_argument(
        "--sample-dir",
        default=str(ROOT / "data" / "sample_uploads" / "five_etf_daily"),
    )
    parser.add_argument("--etf-codes", default=",".join(DEFAULT_CODES))
    args = parser.parse_args()
    codes = [item.strip().zfill(6) for item in args.etf_codes.split(",") if item.strip()]
    if len(codes) != 5 or len(set(codes)) != 5:
        raise ValueError("验收必须包含5只不重复ETF")
    result = run_acceptance(args.base_url, Path(args.sample_dir).resolve(), codes)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
