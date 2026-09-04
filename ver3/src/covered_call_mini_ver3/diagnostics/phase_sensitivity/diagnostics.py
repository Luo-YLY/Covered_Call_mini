from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from .config import PhaseRunConfig, candidate_portfolios, default_paths, target_sleeves
from .cycle_attribution import (
    compute_leave_one_cycle_out,
    compute_option_cycle_concentration,
    summarize_leave_one_cycle_out,
)
from .ensemble import (
    build_phase_ensemble_portfolios,
    build_phase_ensemble_sleeves,
    compare_ensemble_vs_single_phase,
)
from .io import load_required_market_data, write_config_artifacts, write_csv, write_ver3_index
from .metrics import (
    common_window_start,
    compute_phase_metrics,
    compute_phase_robustness_summary,
    compute_portfolio_phase_metrics,
    portfolio_buyhold_comparison,
    sleeve_buyhold_comparison,
)
from .phase_grid import generate_phase_shift_grid, map_phase_to_inception_dates
from .plotting import make_phase_plots
from .portfolio_builder import build_phase_candidate_portfolios
from .reporting import write_markdown_report
from .sleeve_runner import run_all_phase_sleeves
from .validation import validate_inputs, validate_outputs


def run_phase_sensitivity_diagnostics(
    *,
    project_root: Path,
    ver3_root: Path | None = None,
    output_dir: Path | None = None,
    run_config: PhaseRunConfig | None = None,
) -> dict[str, object]:
    """Run the independent phase-sensitivity diagnostic end to end."""

    cfg = run_config or PhaseRunConfig()
    paths = default_paths(project_root, ver3_root, output_dir)
    paths.ensure_output_dirs()
    sleeves = target_sleeves()
    portfolios = candidate_portfolios()
    input_validation = validate_inputs(paths, sleeves, portfolios)
    write_csv(input_validation, paths.summary_dir / "ver3_0_phase_validation_preflight.csv")

    target_etfs = sorted({s.etf_code for s in sleeves})
    base_config, data = load_required_market_data(paths, target_etfs)
    shift_grid = generate_phase_shift_grid(cfg.max_phase_shift, cfg.phase_step)
    inception_grid = map_phase_to_inception_dates(
        data.prices,
        shift_grid,
        sample_start=cfg.sample_start,
        etf_codes=target_etfs,
    )
    phase_grid = shift_grid.merge(inception_grid, on=["phase_id", "phase_shift"], how="left")
    write_config_artifacts(paths, cfg, sleeves, portfolios, phase_grid)
    write_csv(inception_grid, paths.phase_runs_dir / "ver3_0_phase_inception_dates.csv")

    runs = run_all_phase_sleeves(
        data,
        base_config,
        sleeves,
        phase_grid,
        end_date=cfg.sample_end,
        strict=cfg.strict,
    )
    write_csv(runs.run_status, paths.phase_runs_dir / "ver3_0_phase_run_status.csv")
    write_csv(runs.daily_returns, paths.daily_dir / "ver3_0_phase_sleeve_daily_returns.csv")
    write_csv(runs.daily_nav, paths.daily_dir / "ver3_0_phase_sleeve_daily_nav.csv")
    if not runs.period_map.empty:
        write_csv(runs.period_map, paths.phase_runs_dir / "ver3_0_phase_option_cycle_map.csv")

    sleeve_common_start = common_window_start(runs.daily_nav, "sleeve_key")
    sleeve_metrics = pd.concat(
        [
            compute_phase_metrics(runs.daily_nav, runs.period_map, rf=cfg.rf, common_start=sleeve_common_start, window_mode="natural"),
            compute_phase_metrics(runs.daily_nav, runs.period_map, rf=cfg.rf, common_start=sleeve_common_start, window_mode="common"),
        ],
        ignore_index=True,
    )
    write_csv(sleeve_metrics, paths.summary_dir / "ver3_0_phase_sleeve_metrics_by_phase.csv")

    portfolio_returns, portfolio_nav = build_phase_candidate_portfolios(runs.daily_returns, portfolios)
    write_csv(
        portfolio_returns[portfolio_returns["portfolio_role"].eq("target_candidate")],
        paths.daily_dir / "ver3_0_phase_portfolio_daily_returns.csv",
    )
    write_csv(
        portfolio_nav[portfolio_nav["portfolio_role"].eq("target_candidate")],
        paths.daily_dir / "ver3_0_phase_portfolio_daily_nav.csv",
    )
    portfolio_common_start = common_window_start(portfolio_nav, "portfolio_name")
    portfolio_metrics = pd.concat(
        [
            compute_portfolio_phase_metrics(
                portfolio_returns, portfolio_nav, rf=cfg.rf, common_start=portfolio_common_start, window_mode="natural"
            ),
            compute_portfolio_phase_metrics(
                portfolio_returns, portfolio_nav, rf=cfg.rf, common_start=portfolio_common_start, window_mode="common"
            ),
        ],
        ignore_index=True,
    )
    write_csv(
        portfolio_metrics[portfolio_metrics["portfolio_role"].eq("target_candidate")],
        paths.summary_dir / "ver3_0_phase_portfolio_metrics_by_phase.csv",
    )

    sleeve_comp = sleeve_buyhold_comparison(sleeve_metrics, sleeves)
    sleeve_robust = compute_phase_robustness_summary(
        sleeve_metrics,
        entity_col="sleeve_name",
        buyhold_comparison=sleeve_comp,
    )
    portfolio_comp = portfolio_buyhold_comparison(portfolio_metrics)
    target_mdd = {p.portfolio_name: p.target_mdd for p in portfolios}
    portfolio_robust = compute_phase_robustness_summary(
        portfolio_metrics[portfolio_metrics["portfolio_role"].eq("target_candidate")],
        entity_col="portfolio_name",
        target_mdd=target_mdd,
        buyhold_comparison=portfolio_comp,
    )
    label_table = pd.concat(
        [
            sleeve_robust.rename(columns={"sleeve_name": "entity_name"}).assign(entity_type="sleeve"),
            portfolio_robust.rename(columns={"portfolio_name": "entity_name"}).assign(entity_type="portfolio"),
        ],
        ignore_index=True,
    )
    write_csv(sleeve_robust, paths.summary_dir / "ver3_0_phase_sleeve_robustness_summary.csv")
    write_csv(portfolio_robust, paths.summary_dir / "ver3_0_phase_portfolio_robustness_summary.csv")
    write_csv(label_table, paths.summary_dir / "ver3_0_phase_robustness_label_table.csv")

    if cfg.skip_cycle_attribution:
        cycle = pd.DataFrame([{"cycle_attribution_available": False, "reason": "Skipped by user flag."}])
        leave_one = pd.DataFrame([{"cycle_attribution_available": False, "reason": "Skipped by user flag."}])
        leave_one_summary = leave_one.copy()
    else:
        cycle = compute_option_cycle_concentration(runs.period_map)
        leave_one = compute_leave_one_cycle_out(runs.daily_nav, runs.period_map, rf=cfg.rf)
        leave_one_summary = summarize_leave_one_cycle_out(leave_one)
    write_csv(cycle, paths.cycle_dir / "ver3_0_phase_option_cycle_concentration.csv")
    write_csv(leave_one_summary, paths.cycle_dir / "ver3_0_phase_leave_one_cycle_out_summary.csv")

    if cfg.skip_ensemble:
        sleeve_ensemble_daily = pd.DataFrame()
        sleeve_ensemble = pd.DataFrame([{"ensemble_available": False, "reason": "Skipped by user flag."}])
        portfolio_ensemble_daily = pd.DataFrame()
        portfolio_ensemble = pd.DataFrame([{"ensemble_available": False, "reason": "Skipped by user flag."}])
        ensemble_compare = pd.DataFrame([{"ensemble_available": False, "reason": "Skipped by user flag."}])
    else:
        sleeve_ensemble_daily, sleeve_ensemble = build_phase_ensemble_sleeves(runs.daily_returns, common_start=sleeve_common_start, rf=cfg.rf)
        portfolio_ensemble_daily, portfolio_ensemble = build_phase_ensemble_portfolios(
            portfolio_returns, common_start=portfolio_common_start, rf=cfg.rf
        )
        sleeve_compare = compare_ensemble_vs_single_phase(sleeve_ensemble, sleeve_metrics, entity_col="sleeve_name")
        portfolio_compare = compare_ensemble_vs_single_phase(portfolio_ensemble, portfolio_metrics, entity_col="portfolio_name")
        ensemble_compare = pd.concat(
            [
                sleeve_compare.assign(entity_type="sleeve").rename(columns={"sleeve_name": "entity_name"}),
                portfolio_compare.assign(entity_type="portfolio").rename(columns={"portfolio_name": "entity_name"}),
            ],
            ignore_index=True,
        )
    if not sleeve_ensemble.empty:
        write_csv(sleeve_ensemble, paths.ensemble_dir / "ver3_0_phase_sleeve_ensemble_summary.csv")
    if not portfolio_ensemble.empty:
        write_csv(portfolio_ensemble, paths.ensemble_dir / "ver3_0_phase_portfolio_ensemble_summary.csv")
    if not sleeve_ensemble_daily.empty or not portfolio_ensemble_daily.empty:
        ensemble_daily = pd.concat(
            [
                sleeve_ensemble_daily.assign(entity_type="sleeve").rename(columns={"sleeve_name": "entity_name"}),
                portfolio_ensemble_daily.assign(entity_type="portfolio").rename(columns={"portfolio_name": "entity_name"}),
            ],
            ignore_index=True,
        )
        write_csv(ensemble_daily, paths.ensemble_dir / "ver3_0_phase_ensemble_daily_nav.csv")
    write_csv(ensemble_compare, paths.ensemble_dir / "ver3_0_phase_ensemble_vs_single_phase.csv")

    figure_paths: list[Path] = []
    if not cfg.skip_plots:
        figure_paths = make_phase_plots(
            paths.figure_dir,
            sleeve_metrics=sleeve_metrics,
            portfolio_metrics=portfolio_metrics,
            portfolio_ensemble_daily=portfolio_ensemble_daily,
            cycle_concentration=cycle,
        )

    report_path = paths.report_dir / "ver3_0_independent_phase_sensitivity_diagnostics_report.md"
    highest_fragility_sleeve = (
        str(sleeve_robust.sort_values("phase_fragility_score", ascending=False).iloc[0]["sleeve_name"])
        if not sleeve_robust.empty
        else ""
    )
    highest_robust_candidate = str(portfolio_robust.iloc[0]["portfolio_name"]) if not portfolio_robust.empty else ""
    b20 = portfolio_robust[portfolio_robust["portfolio_name"].eq("B_default_D20")]
    b20_label = str(b20.iloc[0]["phase_robustness_label"]) if not b20.empty else ""
    ensemble_improved = _ensemble_improved(ensemble_compare)
    run_timestamp = datetime.now().isoformat(timespec="seconds")
    write_ver3_index(
        paths.ver3_output_index,
        output_root=paths.output_root,
        report_path=report_path,
        run_timestamp=run_timestamp,
        target_sleeves=sleeves,
        portfolios=portfolios,
        highest_fragility_sleeve=highest_fragility_sleeve,
        highest_robust_candidate=highest_robust_candidate,
        ensemble_improved=ensemble_improved,
        appendix_recommendation="yes",
    )
    validation = validate_outputs(
        paths,
        run_status=runs.run_status,
        phase_grid=phase_grid,
        sleeve_daily=runs.daily_nav,
        sleeve_metrics=sleeve_metrics,
        portfolio_metrics=portfolio_metrics,
        ensemble_summary=portfolio_ensemble,
        cycle_concentration=cycle,
        report_path=report_path,
    )
    if cfg.write_report:
        write_markdown_report(
            report_path,
            sleeve_robustness=sleeve_robust,
            portfolio_robustness=portfolio_robust,
            sleeve_metrics=sleeve_metrics,
            portfolio_metrics=portfolio_metrics[portfolio_metrics["portfolio_role"].eq("target_candidate")],
            cycle_concentration=cycle,
            leave_one_summary=leave_one_summary,
            sleeve_ensemble=sleeve_ensemble,
            portfolio_ensemble=portfolio_ensemble,
            ensemble_compare=_portfolio_ensemble_compare_for_report(ensemble_compare),
            validation=validation,
            figure_paths=figure_paths,
        )
        validation = validate_outputs(
            paths,
            run_status=runs.run_status,
            phase_grid=phase_grid,
            sleeve_daily=runs.daily_nav,
            sleeve_metrics=sleeve_metrics,
            portfolio_metrics=portfolio_metrics,
            ensemble_summary=portfolio_ensemble,
            cycle_concentration=cycle,
            report_path=report_path,
        )
        write_markdown_report(
            report_path,
            sleeve_robustness=sleeve_robust,
            portfolio_robustness=portfolio_robust,
            sleeve_metrics=sleeve_metrics,
            portfolio_metrics=portfolio_metrics[portfolio_metrics["portfolio_role"].eq("target_candidate")],
            cycle_concentration=cycle,
            leave_one_summary=leave_one_summary,
            sleeve_ensemble=sleeve_ensemble,
            portfolio_ensemble=portfolio_ensemble,
            ensemble_compare=_portfolio_ensemble_compare_for_report(ensemble_compare),
            validation=validation,
            figure_paths=figure_paths,
        )
    write_csv(validation, paths.summary_dir / "ver3_0_phase_validation_summary.csv")
    return {
        "project_root": paths.project_root,
        "ver3_root": paths.ver3_root,
        "output_root": paths.output_root,
        "ver3_output_index": paths.ver3_output_index,
        "phase_shift_count": int(len(phase_grid)),
        "target_sleeve_count": int(len(sleeves)),
        "target_portfolio_count": int(len(portfolios)),
        "phase_run_success_rate": float(runs.run_status["status"].eq("success").mean()),
        "highest_phase_fragility_sleeve": highest_fragility_sleeve,
        "most_phase_robust_candidate": highest_robust_candidate,
        "b_default_d20_phase_robustness_label": b20_label,
        "ensemble_improves_phase_robustness": ensemble_improved,
        "appendix_recommendation": "yes",
        "report_path": report_path,
        "validation_passed": int(validation["passed"].sum()),
        "validation_total": int(len(validation)),
    }


def _ensemble_improved(compare: pd.DataFrame) -> str:
    if compare.empty or "ensemble_improves_sharpe_dispersion_proxy" not in compare:
        return "not_available"
    target = compare[compare.get("entity_type", "").eq("portfolio")] if "entity_type" in compare else compare
    if target.empty:
        return "not_available"
    return "yes" if bool(target["ensemble_improves_sharpe_dispersion_proxy"].mean() >= 0.5) else "mixed"


def _portfolio_ensemble_compare_for_report(compare: pd.DataFrame) -> pd.DataFrame:
    """Return only portfolio ensemble comparison rows for reporting."""

    if compare.empty or "entity_type" not in compare:
        return pd.DataFrame()
    return compare[compare["entity_type"].eq("portfolio")].rename(columns={"entity_name": "portfolio_name"})
