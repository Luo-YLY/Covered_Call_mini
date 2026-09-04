from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT_ROOT = ROOT / "outputs" / "ver4_0_single_etf_cycle_cashflow"
DELTA_BUYBACK_ROOT = ROOT / "outputs" / "ver4_1_delta_buyback"
TP80_BUYBACK_ROOT = ROOT / "outputs" / "ver4_2_tp80_buyback"
DASHBOARD_DIR = EXPERIMENT_ROOT / "dashboard"
OUT_JS = DASHBOARD_DIR / "ver4_dashboard_data.js"
OUT_MANIFEST = DASHBOARD_DIR / "manifest.json"


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def clean_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    out = frame.replace([float("inf"), float("-inf")], pd.NA).where(lambda value: pd.notna(value), None)
    records = out.to_dict(orient="records")
    for record in records:
        for key, value in list(record.items()):
            if isinstance(value, float) and not math.isfinite(value):
                record[key] = None
    return records


def load_etf_payload(etf_dir: Path) -> dict[str, Any] | None:
    manifest_path = etf_dir / "config" / "ver4_0_experiment_manifest.json"
    if not manifest_path.exists():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "etf_code": str(manifest["etf"]["etf_code"]).zfill(6),
        "manifest": manifest,
        "summary": clean_records(read_csv(etf_dir / "summary" / "ver4_0_cycle_cashflow_summary.csv")),
        "ledger": clean_records(read_csv(etf_dir / "period" / "ver4_0_cycle_ledger.csv")),
        "rolling_cashflow": clean_records(read_csv(etf_dir / "summary" / "ver4_0_rolling_12_cycle_cashflow.csv")),
        "regime": clean_records(read_csv(etf_dir / "regime" / "ver4_0_cycle_regime_attribution.csv")),
        "validation": clean_records(read_csv(etf_dir / "audit" / "ver4_0_validation_summary.csv")),
    }


def build_payload() -> dict[str, Any]:
    etfs = [payload for path in sorted(EXPERIMENT_ROOT.iterdir()) if path.is_dir() and path.name != "dashboard" if (payload := load_etf_payload(path))]
    delta_ledger = read_csv(DELTA_BUYBACK_ROOT / "ver4_1_delta_buyback_cycle_ledger.csv")
    delta_summary = read_csv(DELTA_BUYBACK_ROOT / "ver4_1_delta_buyback_summary.csv")
    delta_manifest_path = DELTA_BUYBACK_ROOT / "ver4_1_delta_buyback_manifest.json"
    delta_manifest = json.loads(delta_manifest_path.read_text(encoding="utf-8")) if delta_manifest_path.exists() else {}
    tp80_ledger = read_csv(TP80_BUYBACK_ROOT / "ver4_2_tp80_buyback_cycle_ledger.csv")
    tp80_summary = read_csv(TP80_BUYBACK_ROOT / "ver4_2_tp80_buyback_summary.csv")
    tp80_manifest_path = TP80_BUYBACK_ROOT / "ver4_2_tp80_buyback_manifest.json"
    tp80_manifest = json.loads(tp80_manifest_path.read_text(encoding="utf-8")) if tp80_manifest_path.exists() else {}
    return {
        "experiment_id": "ver4_0_single_etf_cycle_cashflow",
        "generated_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
        "accounting_note": "Each option cycle resets to a fixed notional. Prior-cycle P&L is not reinvested; results are not a compounded NAV.",
        "etfs": etfs,
        "delta_buyback": {
            "manifest": delta_manifest,
            "ledger": clean_records(delta_ledger),
            "summary": clean_records(delta_summary),
        },
        "tp80_buyback": {
            "manifest": tp80_manifest,
            "ledger": clean_records(tp80_ledger),
            "summary": clean_records(tp80_summary),
        },
    }


def main() -> None:
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_payload()
    OUT_JS.write_text(
        "window.VER4_DASHBOARD_DATA = " + json.dumps(payload, ensure_ascii=False, allow_nan=False) + ";\n",
        encoding="utf-8",
    )
    OUT_MANIFEST.write_text(
        json.dumps(
            {
                "experiment_id": payload["experiment_id"],
                "generated_at": payload["generated_at"],
                "data_file": str(OUT_JS.relative_to(ROOT)),
                "etf_count": len(payload["etfs"]),
                "etf_codes": [row["etf_code"] for row in payload["etfs"]],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {OUT_JS}")
    print(f"Wrote {OUT_MANIFEST}")


if __name__ == "__main__":
    main()
