from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def make_phase_plots(
    figure_dir: Path,
    *,
    sleeve_metrics: pd.DataFrame,
    portfolio_metrics: pd.DataFrame,
    portfolio_ensemble_daily: pd.DataFrame,
    cycle_concentration: pd.DataFrame,
) -> list[Path]:
    """Write appendix-oriented phase diagnostic figures."""

    figure_dir.mkdir(parents=True, exist_ok=True)
    files = [
        _boxplot(figure_dir / "ver3_0_phase_sharpe_distribution.png", sleeve_metrics, portfolio_metrics, "sharpe_daily_mean", "Sharpe"),
        _boxplot(figure_dir / "ver3_0_phase_mdd_distribution.png", sleeve_metrics, portfolio_metrics, "max_drawdown", "MDD"),
        _boxplot(
            figure_dir / "ver3_0_phase_option_leg_distribution.png",
            sleeve_metrics,
            portfolio_metrics,
            "option_leg_annualized_pnl_contribution",
            "Option-leg contribution",
        ),
        _portfolio_heatmap(figure_dir / "ver3_0_phase_heatmap_candidate_metrics.png", portfolio_metrics),
        _ensemble_nav(figure_dir / "ver3_0_phase_ensemble_vs_single_nav.png", portfolio_ensemble_daily),
    ]
    if not cycle_concentration.empty and bool(cycle_concentration.get("cycle_attribution_available", pd.Series([False])).iloc[0]):
        files.append(_cycle_concentration(figure_dir / "ver3_0_phase_cycle_concentration.png", cycle_concentration))
    return files


def _boxplot(path: Path, sleeve_metrics: pd.DataFrame, portfolio_metrics: pd.DataFrame, metric: str, title: str) -> Path:
    data = pd.concat(
        [
            sleeve_metrics[sleeve_metrics["window_mode"].eq("common")][["sleeve_name", metric]].rename(columns={"sleeve_name": "name"}),
            portfolio_metrics[
                portfolio_metrics["window_mode"].eq("common") & portfolio_metrics["portfolio_role"].eq("target_candidate")
            ][["portfolio_name", metric]].rename(columns={"portfolio_name": "name"}),
        ],
        ignore_index=True,
    ).dropna()
    fig, ax = plt.subplots(figsize=(12, 5.8))
    names = list(data["name"].drop_duplicates())
    values = [data[data["name"].eq(name)][metric].astype(float).values for name in names]
    ax.boxplot(values, labels=[_short(name) for name in names], showfliers=False)
    ax.set_title(f"Phase distribution: {title}")
    ax.grid(axis="y", alpha=0.25)
    ax.tick_params(axis="x", labelrotation=35, labelsize=8)
    if metric != "sharpe_daily_mean":
        ax.yaxis.set_major_formatter(lambda y, _pos: f"{y:.0%}")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _portfolio_heatmap(path: Path, portfolio_metrics: pd.DataFrame) -> Path:
    d = portfolio_metrics[
        portfolio_metrics["window_mode"].eq("common") & portfolio_metrics["portfolio_role"].eq("target_candidate")
    ].copy()
    pivot = d.pivot_table(index="portfolio_name", columns="phase_shift", values="sharpe_daily_mean", aggfunc="last")
    fig, ax = plt.subplots(figsize=(11, 4.8))
    im = ax.imshow(pivot.values, aspect="auto", cmap="RdYlGn")
    ax.set_yticks(np.arange(len(pivot.index)))
    ax.set_yticklabels([_short(x) for x in pivot.index], fontsize=8)
    ax.set_xticks(np.arange(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns, fontsize=7)
    ax.set_xlabel("Phase shift (trading days)")
    ax.set_title("Candidate portfolio Sharpe by phase")
    fig.colorbar(im, ax=ax, label="Sharpe")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _ensemble_nav(path: Path, ensemble_daily: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(10.5, 5.8))
    if not ensemble_daily.empty:
        for name, group in ensemble_daily.groupby("portfolio_name", sort=True):
            ax.plot(group["date"], group["nav"], linewidth=1.6, label=_short(name))
    ax.set_title("All-phase equal-weight portfolio ensemble NAV")
    ax.set_ylabel("NAV")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _cycle_concentration(path: Path, cycle: pd.DataFrame) -> Path:
    d = cycle.groupby("sleeve_name", as_index=False)["top_3_abs_cycle_pnl_share"].mean()
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    ax.bar(d["sleeve_name"].map(_short), d["top_3_abs_cycle_pnl_share"], color="#4C78A8")
    ax.yaxis.set_major_formatter(lambda y, _pos: f"{y:.0%}")
    ax.set_title("Average top-3 option-cycle absolute P&L share")
    ax.grid(axis="y", alpha=0.24)
    ax.tick_params(axis="x", labelrotation=25, labelsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _short(name: object) -> str:
    return str(name).replace("_DTE30_", "_").replace("_Hold", "").replace("_default_", "_")
