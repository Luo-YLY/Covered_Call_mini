from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def write_figures(
    figure_dir: Path,
    daily_nav: pd.DataFrame,
    drawdown: pd.DataFrame,
    summary: pd.DataFrame,
    correlation: pd.DataFrame,
    risk_contribution: pd.DataFrame,
) -> list[Path]:
    """Write Step B diagnostic figures."""

    figure_dir.mkdir(parents=True, exist_ok=True)
    paths = [
        make_nav_plot(figure_dir / "ver3_0_stepB_nav_curves_selected.png", daily_nav, selected_only=True),
        make_nav_plot(figure_dir / "ver3_0_stepB_nav_curves_pure_vs_selected.png", daily_nav, selected_only=False),
        make_drawdown_plot(figure_dir / "ver3_0_stepB_drawdown_curves_selected.png", daily_nav, drawdown),
        make_metric_bar(figure_dir / "ver3_0_stepB_metric_comparison_bar.png", summary),
        make_correlation_heatmap(figure_dir / "ver3_0_stepB_correlation_heatmap.png", correlation),
        make_risk_contribution_bar(figure_dir / "ver3_0_stepB_risk_contribution_bar.png", risk_contribution),
    ]
    return paths


def make_nav_plot(path: Path, daily_nav: pd.DataFrame, selected_only: bool) -> Path:
    data = daily_nav.copy()
    if selected_only:
        data = data[data["portfolio_type"].eq("Selected")]
    fig, ax = plt.subplots(figsize=(11, 5.8))
    for name, g in data.groupby("portfolio_name"):
        ax.plot(g["date"], g["nav"], label=name, linewidth=2.0 if "Selected" in name else 1.0, alpha=0.9 if "Selected" in name else 0.55)
    ax.set_title("Step B fixed-weight portfolio NAV")
    ax.set_ylabel("NAV")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def make_drawdown_plot(path: Path, daily_nav: pd.DataFrame, drawdown: pd.DataFrame) -> Path:
    meta = daily_nav[["portfolio_name", "portfolio_type"]].drop_duplicates()
    data = drawdown.merge(meta, on="portfolio_name", how="left")
    data = data[data["portfolio_type"].eq("Selected")]
    fig, ax = plt.subplots(figsize=(11, 5.8))
    for name, g in data.groupby("portfolio_name"):
        ax.plot(g["date"], g["drawdown"], label=name, linewidth=1.8, alpha=0.85)
    ax.set_title("Step B selected portfolio drawdowns")
    ax.set_ylabel("Drawdown")
    ax.yaxis.set_major_formatter(lambda y, _pos: f"{y:.0%}")
    ax.grid(alpha=0.25)
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def make_metric_bar(path: Path, summary: pd.DataFrame) -> Path:
    data = summary[summary["portfolio_type"].eq("Selected")].copy()
    metrics = [
        ("annualized_return_cagr", "CAGR"),
        ("sharpe_daily_mean", "Sharpe"),
        ("max_drawdown", "MDD"),
        ("option_leg_annualized_pnl_contribution", "Option leg"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(12, 7.2))
    for ax, (col, title) in zip(axes.flatten(), metrics):
        ax.bar(data["portfolio_name"], data[col], color=np.where(data["universe_short"].eq("A"), "#4C78A8", "#F58518"))
        ax.set_title(title)
        ax.tick_params(axis="x", rotation=35, labelsize=7)
        if col != "sharpe_daily_mean":
            ax.yaxis.set_major_formatter(lambda y, _pos: f"{y:.0%}")
        ax.axhline(0, color="black", linewidth=0.7)
        ax.grid(axis="y", alpha=0.22)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def make_correlation_heatmap(path: Path, correlation: pd.DataFrame) -> Path:
    data = correlation.set_index("sleeve")
    values = data.to_numpy(dtype=float)
    fig, ax = plt.subplots(figsize=(9, 7.5))
    im = ax.imshow(values, vmin=-1, vmax=1, cmap="coolwarm")
    ax.set_xticks(np.arange(len(data.columns)))
    ax.set_xticklabels([_short_label(c) for c in data.columns], rotation=60, ha="right", fontsize=7)
    ax.set_yticks(np.arange(len(data.index)))
    ax.set_yticklabels([_short_label(c) for c in data.index], fontsize=7)
    for i in range(values.shape[0]):
        for j in range(values.shape[1]):
            ax.text(j, i, f"{values[i, j]:.2f}", ha="center", va="center", fontsize=6)
    ax.set_title("Sleeve daily return correlation")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def make_risk_contribution_bar(path: Path, risk_contribution: pd.DataFrame) -> Path:
    data = risk_contribution[risk_contribution["portfolio_type"].eq("Selected")].copy()
    fig, ax = plt.subplots(figsize=(12, 6))
    labels = []
    bottoms: dict[str, float] = {}
    for portfolio_name, g in data.groupby("portfolio_name"):
        labels.append(portfolio_name)
        bottoms[portfolio_name] = 0.0
    x = np.arange(len(labels))
    for sleeve in sorted(data["etf_code"].unique()):
        vals = []
        for portfolio_name in labels:
            row = data[(data["portfolio_name"].eq(portfolio_name)) & (data["etf_code"].eq(sleeve))]
            vals.append(float(row["risk_contribution_pct"].sum()) if not row.empty else 0.0)
        ax.bar(x, vals, bottom=[bottoms[p] for p in labels], label=sleeve)
        for p, v in zip(labels, vals):
            bottoms[p] += v
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=8)
    ax.yaxis.set_major_formatter(lambda y, _pos: f"{y:.0%}")
    ax.set_title("Selected portfolio volatility risk contribution")
    ax.grid(axis="y", alpha=0.22)
    ax.legend(title="ETF", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _short_label(value: object) -> str:
    text = str(value).replace("__daily_return", "")
    text = text.replace("_DTE30_", "_").replace("_Hold", "")
    return text
