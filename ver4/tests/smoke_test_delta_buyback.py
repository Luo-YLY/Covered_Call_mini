from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
LEDGER_PATH = ROOT / "outputs" / "ver4_1_delta_buyback" / "ver4_1_delta_buyback_cycle_ledger.csv"
SUMMARY_PATH = ROOT / "outputs" / "ver4_1_delta_buyback" / "ver4_1_delta_buyback_summary.csv"


def main() -> None:
    ledger = pd.read_csv(LEDGER_PATH)
    summary = pd.read_csv(SUMMARY_PATH)
    assert not ledger.empty, "Delta-buyback ledger is empty."
    assert not summary.empty, "Delta-buyback summary is empty."
    assert set(np.round(ledger["delta_buyback_threshold"].unique(), 2)) == {0.70, 0.80, 0.90}

    option_identity = (
        ledger["gross_premium_yield"]
        - ledger["exercise_or_close_cost_yield"]
        - ledger["transaction_cost_yield"]
    )
    strategy_identity = ledger["etf_period_return"] + ledger["net_option_yield"]
    assert np.isclose(ledger["net_option_yield"], option_identity, atol=1e-12).all(), "Option-leg identity failed."
    assert np.isclose(ledger["covered_call_period_return"], strategy_identity, atol=1e-12).all(), "Strategy identity failed."
    assert np.isclose(
        ledger["delta_buyback_strategy_change"], ledger["delta_buyback_net_option_change"], atol=1e-12
    ).all(), "ETF leg changed under the buyback overlay."

    triggered = ledger.loc[ledger["buyback_triggered"].astype(bool)]
    assert not triggered.empty, "No Delta triggers were produced."
    assert (~triggered["assignment_flag"].astype(bool)).all(), "A triggered cycle remained assigned."
    assert (triggered["buyback_remaining_dte"].astype(float) >= 5).all(), "Trigger used a disallowed late-expiry observation."
    assert (triggered["buyback_date"].notna()).all(), "Triggered cycle is missing a buyback date."
    print(f"delta-buyback smoke test passed: rows={len(ledger)}, triggers={len(triggered)}, summaries={len(summary)}")


if __name__ == "__main__":
    main()
