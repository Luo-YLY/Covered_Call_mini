from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
VER4_SRC = ROOT / "ver4" / "src"
for path in (ROOT, VER4_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from build_ver4_dashboard_data import main as build_dashboard_data  # noqa: E402
from covered_call_mini_ver4.io import write_csv  # noqa: E402
from covered_call_mini_ver4.ledger import attach_cycle_market_context  # noqa: E402


EXPERIMENT_ROOT = ROOT / "outputs" / "ver4_0_single_etf_cycle_cashflow"


def main() -> None:
    prices = pd.read_csv(ROOT / "data" / "raw" / "etf_prices.csv")
    options = pd.read_csv(
        ROOT / "data" / "source" / "delta_enriched_options.csv",
        usecols=lambda column: column in {"trade_date", "option_code", "model_iv", "days_to_expiry"},
    )
    updated = 0
    for etf_dir in sorted(path for path in EXPERIMENT_ROOT.iterdir() if path.is_dir() and path.name != "dashboard"):
        ledger_path = etf_dir / "period" / "ver4_0_cycle_ledger.csv"
        if not ledger_path.exists():
            continue
        ledger = pd.read_csv(ledger_path)
        enriched = attach_cycle_market_context(ledger, etf_prices=prices, option_chain=options)
        write_csv(enriched, ledger_path)
        updated += 1
        print(f"updated: {ledger_path}")
    build_dashboard_data()
    print(f"market-context ledgers updated: {updated}")


if __name__ == "__main__":
    main()
