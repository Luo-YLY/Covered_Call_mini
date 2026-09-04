# Phase Sensitivity Diagnostic Config

This independent diagnostic tests inception-date and roll-calendar phase sensitivity for selected ver3 covered-call sleeves and candidate portfolios.

- Sample: 2022-09-19 to 2026-05-27
- Phase shifts: 0 to 20 trading days by default
- Output root: `outputs/ver3_0_independent_phase_sensitivity_diagnostics/`
- ver3 lightweight index: `ver3/outputs/ver3_0_phase_sensitivity_output_index.md`
- Excluded: 588000, rejected sleeves, Q100/ATM_Q100, TP80, Touch-K, new DTE/delta/moneyness grids

Covered-call sleeves are rebuilt from shifted inception dates. The diagnostic does not slice the h=0 covered-call return panel.
