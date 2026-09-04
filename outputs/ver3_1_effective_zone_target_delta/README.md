# ver3.1 target-delta x coverage experiment

This sidecar experiment keeps ver3.0 outputs intact.
The output directory name is retained for compatibility; the active selection logic no longer uses the earlier fixed-moneyness delta mapping.

Main flow:

1. Run target-delta daily-MTM grids for D10/D20/D30/D40/D50 x Q10..Q100.
2. Select core ETF sleeves directly from the full target-delta x coverage grid after economic filters.
3. Keep non-core sleeves in their explicit fixed-moneyness or BuyHold roles.
4. Rebuild fixed-weight, MDD-constrained Sharpe frontier, and dynamic-weight comparisons.

Report: `outputs/ver3_1_effective_zone_target_delta/reports/ver3_1_effective_zone_target_delta_report.md`