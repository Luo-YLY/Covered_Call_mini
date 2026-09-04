from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def make_stepC_plots(
    figure_dir: Path,
    candidate_nav: pd.DataFrame,
    drawdowns: pd.DataFrame,
    rolling_252: pd.DataFrame,
    cost_summary: pd.DataFrame,
    scorecard: pd.DataFrame,
) -> list[Path]:
    """Generate Step C figures."""

    figure_dir.mkdir(parents=True, exist_ok=True)
    return [
        _nav_plot(figure_dir / "ver3_0_stepC_candidate_nav_curves.png", candidate_nav),
        _drawdown_plot(figure_dir / "ver3_0_stepC_candidate_drawdown_curves.png", drawdowns),
        _rolling_plot(figure_dir / "ver3_0_stepC_rolling_sharpe.png", rolling_252, "rolling_sharpe", "rolling 252d Sharpe"),
        _rolling_plot(figure_dir / "ver3_0_stepC_rolling_mdd.png", rolling_252, "rolling_mdd", "rolling 252d MDD"),
        _cost_plot(figure_dir / "ver3_0_stepC_cost_sensitivity.png", cost_summary),
        _scorecard_plot(figure_dir / "ver3_0_stepC_stability_scorecard.png", scorecard),
    ]


def _nav_plot(path: Path, candidate_nav: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(10.5, 5.8))
    for name, group in candidate_nav.groupby("portfolio_name", sort=True):
        ax.plot(pd.to_datetime(group["date"]), group["nav"], label=name, linewidth=1.8)
    ax.set_title("Step C Candidate NAV")
    ax.set_ylabel("NAV")
    ax.grid(alpha=0.24)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _drawdown_plot(path: Path, drawdowns: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(10.5, 5.8))
    for name, group in drawdowns.groupby("portfolio_name", sort=True):
        ax.plot(pd.to_datetime(group["date"]), group["drawdown"], label=name, linewidth=1.8)
    ax.set_title("Step C Candidate Drawdown")
    ax.set_ylabel("Drawdown")
    ax.yaxis.set_major_formatter(lambda y, _pos: f"{y:.0%}")
    ax.grid(alpha=0.24)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _rolling_plot(path: Path, rolling: pd.DataFrame, column: str, title: str) -> Path:
    fig, ax = plt.subplots(figsize=(10.5, 5.8))
    for name, group in rolling.groupby("portfolio_name", sort=True):
        ax.plot(pd.to_datetime(group["window_end"]), group[column], label=name, linewidth=1.5, alpha=0.9)
    ax.set_title(title)
    if column == "rolling_mdd":
        ax.yaxis.set_major_formatter(lambda y, _pos: f"{y:.0%}")
    ax.grid(alpha=0.24)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _cost_plot(path: Path, cost_summary: pd.DataFrame) -> Path:
    data = cost_summary.copy()
    data["extra_cost_bps"] = data["extra_cost_bps"].astype(float)
    fig, ax = plt.subplots(figsize=(10, 5.6))
    for name, group in data.groupby("portfolio_name", sort=True):
        ax.plot(group["extra_cost_bps"], group["sharpe_daily_mean"], marker="o", label=name)
    ax.set_xlabel("extra option cost bps")
    ax.set_ylabel("Sharpe")
    ax.set_title("Cost Sensitivity: Sharpe")
    ax.grid(alpha=0.24)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _scorecard_plot(path: Path, scorecard: pd.DataFrame) -> Path:
    metrics = [
        "event_exclusion_sharpe_stability",
        "rolling_sharpe_stability",
        "cost_sensitivity_score",
        "option_leg_robustness_score",
        "weight_interpretability_score",
    ]
    data = scorecard.set_index("portfolio_name")[metrics]
    fig, ax = plt.subplots(figsize=(10.8, 5.8))
    x = np.arange(len(data.index))
    bottom = np.zeros(len(data.index))
    for metric in metrics:
        values = data[metric].astype(float).to_numpy()
        ax.bar(x, values, bottom=bottom, label=metric)
        bottom += values
    ax.set_xticks(x)
    ax.set_xticklabels(data.index, rotation=20, ha="right")
    ax.set_ylabel("score components")
    ax.set_title("Stability Score Components")
    ax.grid(axis="y", alpha=0.22)
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path
