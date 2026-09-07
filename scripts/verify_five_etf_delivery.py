from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_CODES = {"510050", "510300", "159919", "159915", "159922"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    sample_root = ROOT / "data" / "sample_uploads" / "five_etf_daily"
    sample_manifest = json.loads(
        (sample_root / "sample_manifest.json").read_text(encoding="utf-8")
    )
    if set(sample_manifest.get("etf_codes", [])) != EXPECTED_CODES:
        raise RuntimeError("五ETF上传样本代码集合不正确")
    if sample_manifest.get("all_daily_option_date_coverage_passed") is not True:
        raise RuntimeError("五ETF上传样本未通过逐交易日期权覆盖检查")
    if sample_manifest.get("common_window") != {
        "start": "2022-09-19",
        "end": "2026-06-03",
    }:
        raise RuntimeError("五ETF共同样本区间与验收基准不一致")

    for package in sample_manifest.get("packages", []):
        code = str(package["etf_code"]).zfill(6)
        if float(package.get("daily_option_date_coverage", 0.0)) != 1.0:
            raise RuntimeError(f"ETF {code} 期权日期覆盖率不是100%")
        for item in package.get("files", {}).values():
            path = sample_root / code / item["path"]
            if not path.is_file():
                raise RuntimeError(f"五ETF上传样本缺少文件：{path}")
            if path.stat().st_size != int(item["bytes"]):
                raise RuntimeError(f"五ETF上传样本文件大小不匹配：{path}")
            if _sha256(path) != item["sha256"]:
                raise RuntimeError(f"五ETF上传样本SHA-256不匹配：{path}")

    acceptance = json.loads(
        (ROOT / "outputs" / "final_acceptance" / "five_etf_acceptance.json").read_text(
            encoding="utf-8"
        )
    )
    if acceptance.get("status") != "passed":
        raise RuntimeError("五ETF完整链路验收未通过")
    if set(acceptance.get("etf_codes", [])) != EXPECTED_CODES:
        raise RuntimeError("五ETF验收记录代码集合不正确")
    singles = acceptance.get("single_etf_backtests", [])
    if len(singles) != 5 or any(
        float(item.get("exact_option_quote_ratio", 0.0)) < 0.99 for item in singles
    ):
        raise RuntimeError("单券回测精确期权报价覆盖率不足99%")
    surfaces = acceptance.get("parameter_surfaces", [])
    if len(surfaces) != 5 or any(item.get("grid_points") != 50 for item in surfaces):
        raise RuntimeError("五ETF参数图谱不是每只50个格点")
    portfolio = acceptance.get("portfolio", {})
    if portfolio.get("accounting_mode") != "fixed_weight_monthly_rebalanced_daily_mtm":
        raise RuntimeError("五ETF组合不是日频MTM口径")
    if int(portfolio.get("common_daily_observations", 0)) <= int(
        portfolio.get("common_periods", 0)
    ):
        raise RuntimeError("五ETF组合没有形成真实日频路径")
    if float(portfolio.get("minimum_exact_option_quote_ratio", 0.0)) < 0.99:
        raise RuntimeError("五ETF组合精确期权报价覆盖率不足99%")
    if float(portfolio.get("max_month_end_reconciliation_error", 1.0)) > 1e-10:
        raise RuntimeError("五ETF组合月末对账误差超限")

    print(
        "PASS: 5 ETF upload samples, 5 single-leg backtests, "
        "5 parameter surfaces, and daily-MTM portfolio are verified."
    )


if __name__ == "__main__":
    main()
