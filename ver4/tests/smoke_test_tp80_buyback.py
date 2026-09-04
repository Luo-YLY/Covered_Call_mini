from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
LEDGER_PATH = ROOT / "outputs" / "ver4_2_tp80_buyback" / "ver4_2_tp80_buyback_cycle_ledger.csv"
SUMMARY_PATH = ROOT / "outputs" / "ver4_2_tp80_buyback" / "ver4_2_tp80_buyback_summary.csv"


def main() -> None:
    ledger = pd.read_csv(LEDGER_PATH)
    summary = pd.read_csv(SUMMARY_PATH)
    assert not ledger.empty, "TP80 ledger is empty."
    assert not summary.empty, "TP80 summary is empty."
    assert set(ledger["early_close_rule"].dropna().unique()) == {"tp80"}

    option_identity = ledger["gross_premium_yield"] - ledger["exercise_or_close_cost_yield"] - ledger["transaction_cost_yield"]
    strategy_identity = ledger["etf_period_return"] + ledger["net_option_yield"]
    assert np.isclose(ledger["net_option_yield"], option_identity, atol=1e-12).all(), "Option-leg identity failed."
    assert np.isclose(ledger["covered_call_period_return"], strategy_identity, atol=1e-12).all(), "Strategy identity failed."
    assert np.isclose(ledger["delta_buyback_strategy_change"], ledger["delta_buyback_net_option_change"], atol=1e-12).all(), "ETF leg changed under TP80."

    triggered = ledger.loc[ledger["buyback_triggered"].astype(bool)]
    assert not triggered.empty, "No TP80 triggers were produced."
    assert (~triggered["assignment_flag"].astype(bool)).all(), "A triggered TP80 cycle remained assigned."
    assert (triggered["buyback_remaining_dte"].astype(float) >= 5).all(), "TP80 used a disallowed late-expiry observation."
    assert (triggered["buyback_premium_capture"].astype(float) >= 0.80 - 1e-12).all(), "TP80 did not capture 80% of entry premium."
    print(f"tp80 smoke test passed: rows={len(ledger)}, triggers={len(triggered)}, summaries={len(summary)}")


if __name__ == "__main__":
    main()
