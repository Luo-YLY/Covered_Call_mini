from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd


def make_stepD_plots(
    figure_dir: Path,
    *,
    dynamic_nav: pd.DataFrame,
    dynamic_drawdowns: pd.DataFrame,
    static_nav: pd.DataFrame,
    static_drawdowns: pd.DataFrame,
    daily_weight_paths: pd.DataFrame,
    turnover_summary: pd.DataFrame,
    cost_summary: pd.DataFrame,
    dynamic_summary: pd.DataFrame,
) -> list[Path]:
    """Generate Step D diagnostic figures."""

    figure_dir.mkdir(parents=True, exist_ok=True)
    return [
        _nav_plot(figure_dir / "ver3_0_stepD_nav_vs_static_baselines.png", dynamic_nav, static_nav),
        _drawdown_plot(figure_dir / "ver3_0_stepD_drawdown_vs_static_baselines.png", dynamic_drawdowns, static_drawdowns),
        _weight_path_plot(figure_dir / "ver3_0_stepD_dynamic_weight_paths_universeA.png", daily_weight_paths, "A"),
        _weight_path_plot(figure_dir / "ver3_0_stepD_dynamic_weight_paths_universeB.png", daily_weight_paths, "B"),
        _turnover_plot(figure_dir / "ver3_0_stepD_turnover_comparison.png", turnover_summary),
        _cost_plot(figure_dir / "ver3_0_stepD_cost_sensitivity.png", cost_summary),
        _metric_plot(figure_dir / "ver3_0_stepD_method_metric_comparison.png", dynamic_summary),
    ]


def build_static_nav_and_drawdown(static_daily: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build NAV and drawdown for static baselines."""

    nav_frames = []
    dd_frames = []
    for name, group in static_daily.groupby("portfolio_name", sort=True):
        g = group.sort_values("date").copy()
        nav = (1.0 + g["portfolio_daily_return"].astype(float)).cumprod()
        nav_frame = g[["date", "portfolio_name", "universe_short", "baseline_source"]].copy()
        nav_frame["nav"] = nav.values
        peak = nav_frame["nav"].astype(float).cummax()
        dd_frame = nav_frame[["date", "portfolio_name", "universe_short", "baseline_source"]].copy()
        dd_frame["drawdown"] = nav_frame["nav"].astype(float).values / peak.values - 1.0
        nav_frames.append(nav_frame)
        dd_frames.append(dd_frame)
    return pd.concat(nav_frames, ignore_index=True, sort=False), pd.concat(dd_frames, ignore_index=True, sort=False)


def _nav_plot(path: Path, dynamic_nav: pd.DataFrame, static_nav: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(11.4, 6.0))
    for name, group in dynamic_nav.groupby("strategy_name", sort=True):
        ax.plot(pd.to_datetime(group["date"]), group["nav"], label=name, linewidth=1.45)
    for name, group in static_nav.groupby("portfolio_name", sort=True):
        ax.plot(pd.to_datetime(group["date"]), group["nav"], label=name, linewidth=1.0, linestyle="--", alpha=0.55)
    ax.set_title("Step D NAV vs Static Baselines")
    ax.set_ylabel("NAV")
    ax.grid(alpha=0.24)
    ax.legend(fontsize=6.6, ncol=2)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _drawdown_plot(path: Path, dynamic_drawdowns: pd.DataFrame, static_drawdowns: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(11.4, 6.0))
    for name, group in dynamic_drawdowns.groupby("strategy_name", sort=True):
        ax.plot(pd.to_datetime(group["date"]), group["drawdown"], label=name, linewidth=1.45)
    for name, group in static_drawdowns.groupby("portfolio_name", sort=True):
        ax.plot(pd.to_datetime(group["date"]), group["drawdown"], label=name, linewidth=1.0, linestyle="--", alpha=0.55)
    ax.set_title("Step D Drawdown vs Static Baselines")
    ax.set_ylabel("Drawdown")
    ax.yaxis.set_major_formatter(lambda y, _pos: f"{y:.0%}")
    ax.grid(alpha=0.24)
    ax.legend(fontsize=6.6, ncol=2)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _weight_path_plot(path: Path, weights: pd.DataFrame, universe_short: str) -> Path:
    data = weights[weights["universe_short"].eq(universe_short)].copy()
    fig, axes = plt.subplots(3, 2, figsize=(11.4, 7.2), sharex=True, sharey=True)
    axes_flat = axes.flatten()
    for ax, (strategy, group) in zip(axes_flat, data.groupby("strategy_name", sort=True)):
        for etf, eg in group.groupby("etf_code", sort=True):
            ax.plot(pd.to_datetime(eg["date"]), eg["target_weight"], label=etf, linewidth=1.35)
        ax.set_title(strategy, fontsize=9)
        ax.yaxis.set_major_formatter(lambda y, _pos: f"{y:.0%}")
        ax.grid(alpha=0.22)
    for ax in axes_flat:
        if not ax.lines:
            ax.axis("off")
    handles, labels = axes_flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, fontsize=8)
    fig.suptitle(f"Step D Dynamic Weight Paths - Universe {universe_short}", y=0.99)
    fig.tight_layout(rect=(0, 0.05, 1, 0.96))
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _turnover_plot(path: Path, turnover_summary: pd.DataFrame) -> Path:
    data = turnover_summary.sort_values(["universe_short", "method", "lookback"]).copy()
    fig, ax = plt.subplots(figsize=(11.2, 5.6))
    ax.bar(data["strategy_name"], data["annualized_turnover_approx"].astype(float))
    ax.set_title("Step D Annualized Turnover Approximation")
    ax.set_ylabel("Annualized turnover")
    ax.yaxis.set_major_formatter(lambda y, _pos: f"{y:.0%}")
    ax.tick_params(axis="x", labelrotation=28, labelsize=7)
    ax.grid(axis="y", alpha=0.24)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _cost_plot(path: Path, cost_summary: pd.DataFrame) -> Path:
    data = cost_summary.copy()
    fig, ax = plt.subplots(figsize=(10.6, 5.6))
    for name, group in data.groupby("strategy_name", sort=True):
        ax.plot(group["rebalance_cost_bps"], group["sharpe_daily_mean"], marker="o", label=name)
    ax.set_title("Step D Rebalance Cost Sensitivity")
    ax.set_xlabel("Rebalance cost bps")
    ax.set_ylabel("Sharpe")
    ax.grid(alpha=0.24)
    ax.legend(fontsize=6.4, ncol=2)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _metric_plot(path: Path, summary: pd.DataFrame) -> Path:
    data = summary.sort_values(["universe_short", "method", "lookback"]).copy()
    labels = data["strategy_name"]
    fig, axes = plt.subplots(3, 1, figsize=(11.4, 9.0), sharex=True)
    axes[0].bar(labels, data["sharpe_daily_mean"].astype(float))
    axes[0].set_ylabel("Sharpe")
    axes[1].bar(labels, data["annualized_return_cagr"].astype(float))
    axes[1].set_ylabel("CAGR")
    axes[1].yaxis.set_major_formatter(lambda y, _pos: f"{y:.0%}")
    axes[2].bar(labels, data["max_drawdown"].astype(float))
    axes[2].set_ylabel("MDD")
    axes[2].yaxis.set_major_formatter(lambda y, _pos: f"{y:.0%}")
    for ax in axes:
        ax.grid(axis="y", alpha=0.22)
    axes[0].set_title("Step D Method Metric Comparison")
    axes[2].tick_params(axis="x", labelrotation=28, labelsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path
