from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CODES = ("510050", "510300", "159919", "159915", "159922")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _date_text(value: object) -> str:
    return pd.Timestamp(value).date().isoformat()


def _write_csv(frame: pd.DataFrame, path: Path) -> dict[str, object]:
    frame.to_csv(path, index=False, encoding="utf-8-sig", date_format="%Y-%m-%d")
    return {
        "path": path.name,
        "rows": int(len(frame)),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def build_samples(
    project_root: Path,
    output_root: Path,
    etf_codes: list[str],
) -> dict[str, object]:
    price_path = project_root / "data" / "raw" / "etf_prices.csv"
    option_path = project_root / "data" / "raw" / "options_daily.csv"
    if not price_path.is_file() or not option_path.is_file():
        raise FileNotFoundError("缺少 data/raw/etf_prices.csv 或 data/raw/options_daily.csv")
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"输出目录已存在且非空：{output_root}")
    output_root.mkdir(parents=True, exist_ok=True)

    prices = pd.read_csv(price_path, dtype={"etf_code": str}, low_memory=False)
    options = pd.read_csv(
        option_path,
        dtype={"option_code": str, "underlying_etf": str},
        low_memory=False,
    )
    prices["etf_code"] = prices["etf_code"].astype(str).str.zfill(6)
    options["underlying_etf"] = options["underlying_etf"].astype(str).str.zfill(6)
    prices["date"] = pd.to_datetime(prices["date"], errors="coerce")
    options["trade_date"] = pd.to_datetime(options["trade_date"], errors="coerce")
    options["expiry"] = pd.to_datetime(options["expiry"], errors="coerce")

    summaries: list[dict[str, object]] = []
    for code in etf_codes:
        code = str(code).zfill(6)
        option_rows = options.loc[options["underlying_etf"].eq(code)].copy()
        if option_rows.empty:
            raise ValueError(f"完整日频期权库中没有ETF {code}")
        option_rows = option_rows.dropna(
            subset=["trade_date", "option_code", "expiry", "strike", "close"]
        ).drop_duplicates(["option_code", "trade_date"], keep="last")
        option_start = option_rows["trade_date"].min()
        option_end = option_rows["trade_date"].max()
        price_rows = prices.loc[
            prices["etf_code"].eq(code)
            & prices["date"].between(option_start, option_end, inclusive="both")
        ].copy()
        if price_rows.empty:
            raise ValueError(f"ETF日行情中没有 {code} 的同期数据")

        price_dates = set(price_rows["date"].dropna().dt.normalize())
        option_dates = set(option_rows["trade_date"].dropna().dt.normalize())
        missing_option_dates = sorted(price_dates - option_dates)
        if missing_option_dates:
            preview = ", ".join(_date_text(value) for value in missing_option_dates[:5])
            raise ValueError(
                f"ETF {code} 有 {len(missing_option_dates)} 个交易日缺少期权行情：{preview}"
            )

        contracts = (
            option_rows[
                ["option_code", "underlying_etf", "option_type", "strike", "expiry"]
            ]
            .sort_values(["option_code", "expiry"])
            .drop_duplicates("option_code", keep="last")
        )
        daily_columns = [
            "option_code",
            "trade_date",
            "close",
            "volume",
            "amount",
            "open_interest",
        ]
        option_daily = option_rows[daily_columns].sort_values(
            ["trade_date", "option_code"]
        )
        etf_daily = price_rows.rename(columns={"date": "trade_date"}).sort_values(
            "trade_date"
        )

        package_dir = output_root / code
        package_dir.mkdir(parents=True)
        files = {
            "etf_daily": _write_csv(etf_daily, package_dir / "etf_daily.csv"),
            "option_contracts": _write_csv(
                contracts, package_dir / "option_contracts.csv"
            ),
            "option_daily": _write_csv(option_daily, package_dir / "option_daily.csv"),
        }
        summary = {
            "etf_code": code,
            "sample_start": _date_text(option_start),
            "sample_end": _date_text(option_end),
            "etf_trade_dates": len(price_dates),
            "option_trade_dates": len(option_dates),
            "daily_option_date_coverage": float(
                len(price_dates.intersection(option_dates)) / len(price_dates)
            ),
            "option_contracts": int(contracts["option_code"].nunique()),
            "option_daily_rows": int(len(option_daily)),
            "files": files,
        }
        (package_dir / "source_manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "source_layer": "project_standardized_daily_archive",
                    "source_files": [
                        "data/raw/etf_prices.csv",
                        "data/raw/options_daily.csv",
                    ],
                    "provenance_note": (
                        "由项目既有完整日频研究输入拆分；上游原始文件采用Tushare Pro字段体系，"
                        "本清单验证日期与文件完整性，不独立认证外部数据提供方。"
                    ),
                    **summary,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        summaries.append(summary)

    common_start = max(item["sample_start"] for item in summaries)
    common_end = min(item["sample_end"] for item in summaries)
    manifest = {
        "schema_version": "1.0",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "purpose": "统一看板五ETF完整日频上传与回测验收",
        "etf_codes": [item["etf_code"] for item in summaries],
        "common_window": {"start": common_start, "end": common_end},
        "all_daily_option_date_coverage_passed": all(
            item["daily_option_date_coverage"] == 1.0 for item in summaries
        ),
        "packages": summaries,
    }
    (output_root / "sample_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_root / "README.md").write_text(
        "# 五ETF完整日频上传样本\n\n"
        "每个ETF目录内的 `etf_daily.csv`、`option_contracts.csv` 和 "
        "`option_daily.csv` 可直接在统一看板的“数据与回测”页面选择并提交。\n\n"
        f"五ETF共同回测区间：`{common_start}` 至 `{common_end}`。\n\n"
        "`sample_manifest.json` 记录逐ETF日期覆盖、行数、文件大小和SHA-256。\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="生成五ETF完整日频看板上传样本")
    parser.add_argument(
        "--etf-codes",
        default=",".join(DEFAULT_CODES),
        help="逗号分隔的六位ETF代码",
    )
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "data" / "sample_uploads" / "five_etf_daily"),
    )
    args = parser.parse_args()
    codes = [item.strip().zfill(6) for item in args.etf_codes.split(",") if item.strip()]
    if len(codes) != 5 or len(set(codes)) != 5:
        raise ValueError("验收样本必须包含5只不重复ETF")
    result = build_samples(ROOT, Path(args.output_dir).resolve(), codes)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
