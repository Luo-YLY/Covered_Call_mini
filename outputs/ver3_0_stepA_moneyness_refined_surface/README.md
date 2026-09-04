# ver3.0 Step A moneyness refined daily-MTM surface

This output replaces the interrupted moneyness-surface task with the current ver3 daily-MTM semantics.

- Source engine: `ver2_downside_protection.strategy_engine.run_ver2_backtest`
- Execution mode: `continuous_30d_daily_mtm`
- Not used: `scripts/build_adhoc_moneyness_surface_refinement_5etf.py` monthly custom backtest
- Surface rows: 350
- Sanity checks: 7/7 passed

Main report:
- `reports/ver3_0_stepA_moneyness_refined_daily_mtm_surface_report.md`