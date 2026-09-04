from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def write_figures(
    figure_dir: Path,
    grid_results: pd.DataFrame,
    best_weights: pd.DataFrame,
    best_daily_nav: pd.DataFrame,
    best_drawdowns: pd.DataFrame,
    risk_contribution: pd.DataFrame,
) -> list[Path]:
    """Write Step B+ frontier and diagnostic figures."""

    figure_dir.mkdir(parents=True, exist_ok=True)
    files = [
        _make_frontier_plot(figure_dir / "ver3_0_stepB_plus_sharpe_mdd_frontier.png", grid_results, "sharpe_daily_mean", "Sharpe"),
        _make_frontier_plot(figure_dir / "ver3_0_stepB_plus_cagr_mdd_frontier.png", grid_results, "annualized_return_cagr", "CAGR"),
        _make_nav_plot(figure_dir / "ver3_0_stepB_plus_best_nav_curves_default.png", best_daily_nav),
        _make_drawdown_plot(figure_dir / "ver3_0_stepB_plus_best_drawdown_curves_default.png", best_drawdowns),
        _make_weight_stack(figure_dir / "ver3_0_stepB_plus_weight_stack_by_drawdown_target.png", best_weights),
        _make_risk_bar(figure_dir / "ver3_0_stepB_plus_risk_contribution_bar.png", risk_contribution),
    ]
    return files


def _make_frontier_plot(path: Path, grid_results: pd.DataFrame, y_col: str, y_label: str) -> Path:
    fig, ax = plt.subplots(figsize=(9.6, 5.8))
    colors = {"A": "#4C78A8", "B": "#F58518"}
    for (universe, constraint), group in grid_results.groupby(["universe_short", "constraint_set"], sort=True):
        marker = "o" if constraint == "default" else "^"
        ax.scatter(
            group["max_drawdown"],
            group[y_col],
            s=9,
            alpha=0.32 if constraint == "default" else 0.18,
            marker=marker,
            color=colors.get(str(universe), "#777777"),
            label=f"{universe} {constraint}",
        )
    ax.set_xlabel("MDD")
    ax.set_ylabel(y_label)
    ax.xaxis.set_major_formatter(lambda x, _pos: f"{x:.0%}")
    if y_col != "sharpe_daily_mean":
        ax.yaxis.set_major_formatter(lambda y, _pos: f"{y:.0%}")
    ax.set_title(f"Step B+ {y_label} vs MDD frontier")
    ax.grid(alpha=0.24)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _make_nav_plot(path: Path, best_daily_nav: pd.DataFrame) -> Path:
    data = best_daily_nav[best_daily_nav["constraint_set"].eq("default")].copy()
    fig, ax = plt.subplots(figsize=(10.8, 5.8))
    for name, group in data.groupby("portfolio_name", sort=True):
        ax.plot(group["date"], group["nav"], label=_short_name(name), linewidth=1.7, alpha=0.85)
    ax.set_ylabel("NAV")
    ax.set_title("Step B+ feasible best NAV curves, default bounds")
    ax.grid(alpha=0.24)
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _make_drawdown_plot(path: Path, best_drawdowns: pd.DataFrame) -> Path:
    data = best_drawdowns[best_drawdowns["constraint_set"].eq("default")].copy()
    fig, ax = plt.subplots(figsize=(10.8, 5.8))
    for name, group in data.groupby("portfolio_name", sort=True):
        ax.plot(group["date"], group["drawdown"], label=_short_name(name), linewidth=1.7, alpha=0.85)
    ax.set_ylabel("Drawdown")
    ax.yaxis.set_major_formatter(lambda y, _pos: f"{y:.0%}")
    ax.set_title("Step B+ feasible best drawdowns, default bounds")
    ax.grid(alpha=0.24)
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _make_weight_stack(path: Path, best_weights: pd.DataFrame) -> Path:
    data = best_weights[best_weights["constraint_set"].eq("default")].copy()
    labels = [f"{row.universe_short} D{int(round(float(row.D_star) * 100)):02d}" for row in data[["universe_short", "D_star"]].drop_duplicates().itertuples()]
    keys = data[["universe_short", "D_star"]].drop_duplicates().to_dict("records")
    fig, ax = plt.subplots(figsize=(10.5, 5.7))
    x = np.arange(len(labels))
    bottom = np.zeros(len(labels))
    for etf in sorted(data["etf_code"].unique()):
        vals = []
        for key in keys:
            row = data[
                data["universe_short"].eq(key["universe_short"])
                & data["D_star"].eq(key["D_star"])
                & data["etf_code"].eq(etf)
            ]
            vals.append(float(row["weight"].sum()) if not row.empty else 0.0)
        ax.bar(x, vals, bottom=bottom, label=etf)
        bottom += np.array(vals)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=25, ha="right")
    ax.yaxis.set_major_formatter(lambda y, _pos: f"{y:.0%}")
    ax.set_title("Step B+ best weights by MDD target, default bounds")
    ax.grid(axis="y", alpha=0.22)
    ax.legend(title="ETF", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _make_risk_bar(path: Path, risk_contribution: pd.DataFrame) -> Path:
    data = risk_contribution[risk_contribution["constraint_set"].eq("default")].copy()
    labels = sorted(data["portfolio_name"].unique())
    fig, ax = plt.subplots(figsize=(11.2, 5.9))
    x = np.arange(len(labels))
    bottom = np.zeros(len(labels))
    for etf in sorted(data["etf_code"].unique()):
        vals = []
        for name in labels:
            row = data[data["portfolio_name"].eq(name) & data["etf_code"].eq(etf)]
            vals.append(float(row["risk_contribution_pct"].sum()) if not row.empty else 0.0)
        ax.bar(x, vals, bottom=bottom, label=etf)
        bottom += np.array(vals)
    ax.set_xticks(x)
    ax.set_xticklabels([_short_name(name) for name in labels], rotation=25, ha="right", fontsize=8)
    ax.yaxis.set_major_formatter(lambda y, _pos: f"{y:.0%}")
    ax.set_title("Step B+ volatility risk contribution, default bounds")
    ax.grid(axis="y", alpha=0.22)
    ax.legend(title="ETF", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _short_name(name: object) -> str:
    return str(name).replace("_default_", "_").replace("_relaxed_", "_")
