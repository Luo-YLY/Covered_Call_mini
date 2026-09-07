from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


FROZEN_ETF_CODES = {"159915", "510050", "510300", "510500", "588000"}
CSV_SCOPES = {
    "data/raw/etf_metadata.csv": "etf_code",
    "data/raw/etf_prices.csv": "etf_code",
    "data/raw/options.csv": "underlying_etf",
    "data/raw/options_daily.csv": "underlying_etf",
    "data/source/delta_enriched_options.csv": "underlying_etf",
}
EXCLUDED_RUNTIME_PATHS = (
    "data/sample_uploads",
    "data/user_submissions",
    "outputs/final_acceptance",
    "outputs/user_backtests",
)


def _codes_in_csv(path: Path, column: str) -> tuple[set[str], int]:
    codes: set[str] = set()
    row_count = 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or column not in reader.fieldnames:
            raise ValueError(f"{path}: 缺少字段 {column}")
        for row in reader:
            code = str(row.get(column, "")).strip().split(".", 1)[0].zfill(6)
            if code:
                codes.add(code)
                row_count += 1
    return codes, row_count


def verify_release_scope(root: Path) -> dict[str, object]:
    root = root.resolve()
    summaries: dict[str, object] = {}
    for relative_path, column in CSV_SCOPES.items():
        path = root / relative_path
        if not path.is_file():
            raise FileNotFoundError(f"交付包缺少冻结数据文件：{relative_path}")
        codes, row_count = _codes_in_csv(path, column)
        if codes != FROZEN_ETF_CODES:
            raise ValueError(
                f"{relative_path}: ETF范围不符；实际={sorted(codes)}，"
                f"应为={sorted(FROZEN_ETF_CODES)}"
            )
        summaries[relative_path] = {
            "row_count": row_count,
            "etf_codes": sorted(codes),
        }

    for relative_path in EXCLUDED_RUNTIME_PATHS:
        if (root / relative_path).exists():
            raise ValueError(f"交付包包含本地测试或运行时数据：{relative_path}")

    cycle_root = root / "outputs" / "ver4_0_single_etf_cycle_cashflow"
    if not cycle_root.is_dir():
        raise FileNotFoundError("交付包缺少原始五ETF单券周期结果")
    result_codes = {
        path.name for path in cycle_root.iterdir() if path.is_dir() and path.name.isdigit()
    }
    if result_codes != FROZEN_ETF_CODES:
        raise ValueError(
            f"单券周期结果范围不符；实际={sorted(result_codes)}，"
            f"应为={sorted(FROZEN_ETF_CODES)}"
        )

    return {
        "status": "PASS",
        "frozen_etf_codes": sorted(FROZEN_ETF_CODES),
        "csv_files": summaries,
        "excluded_runtime_paths_absent": list(EXCLUDED_RUNTIME_PATHS),
        "single_etf_result_codes": sorted(result_codes),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="校验最终交付包的五ETF冻结数据边界")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()
    result = verify_release_scope(Path(args.root))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
