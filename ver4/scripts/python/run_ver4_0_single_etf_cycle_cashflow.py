from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
VER4_SRC = ROOT / "ver4" / "src"
for path in (ROOT, VER4_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from covered_call_mini_ver4.config import build_cycle_experiment_config, config_manifest  # noqa: E402
from covered_call_mini_ver4.pipeline import run_cycle_cashflow_experiment  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run ver4.0 single-ETF, fixed-notional covered-call cycle cashflow diagnostic."
    )
    parser.add_argument("--etf", required=True, help="One ETF code, for example 510300.")
    parser.add_argument("--fixed-notional", type=float, default=100.0, help="Same notional reset at each option cycle.")
    parser.add_argument("--sample-start", default=None, help="Optional YYYY-MM-DD override.")
    parser.add_argument("--sample-end", default=None, help="Optional YYYY-MM-DD override.")
    parser.add_argument("--dry-run", action="store_true", help="Print frozen configuration and exit without running the grid.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = build_cycle_experiment_config(
        ROOT,
        etf_code=args.etf,
        fixed_notional=args.fixed_notional,
        sample_start=args.sample_start,
        sample_end=args.sample_end,
    )
    if args.dry_run:
        print(json.dumps(config_manifest(config), ensure_ascii=False, indent=2))
        return
    result = run_cycle_cashflow_experiment(config)
    passed = int(result.validation["passed"].sum()) if not result.validation.empty else 0
    print(f"output_root: {result.output_root}")
    print(f"cycle_ledger_rows: {len(result.cycle_ledger)}")
    print(f"validation: {passed}/{len(result.validation)} passed")
    print(f"report: {result.report_path}")


if __name__ == "__main__":
    main()
