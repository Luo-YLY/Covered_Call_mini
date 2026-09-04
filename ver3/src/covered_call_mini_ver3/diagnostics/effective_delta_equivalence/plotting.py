from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from .config import DiagnosticConfig


def make_effective_delta_plots(
    *,
    config: DiagnosticConfig,
    daily_nav: pd.DataFrame,
    daily_drawdowns: pd.DataFrame,
    summary: pd.DataFrame,
    quality: pd.DataFrame,
    stress: pd.DataFrame,
    phase_metrics: pd.DataFrame,
) -> dict[str, Path]:
    """Generate compact appendix-ready diagnostic charts."""

    if config.skip_plots:
        return {}
    fig_dir = config.paths.output_root / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    saved: dict[str, Path] = {}
    for etf in config.active_etfs:
        nav_path = fig_dir / f"ver3_0_effective_delta_nav_comparison_{etf}.png"
        dd_path = fig_dir / f"ver3_0_effective_delta_drawdown_comparison_{etf}.png"
        bar_path = fig_dir / f"ver3_0_effective_delta_metric_bar_{etf}.png"
        _line_plot(
            daily_nav[daily_nav["etf_code"].eq(etf)],
            "date",
            "nav",
            nav_path,
            f"{etf} NAV by implementation",
            "NAV",
        )
        _line_plot(
            daily_drawdowns[daily_drawdowns["etf_code"].eq(etf)],
            "date",
            "drawdown",
            dd_path,
            f"{etf} drawdown by implementation",
            "Drawdown",
        )
        _metric_bar(summary[summary["etf_code"].eq(etf)], bar_path, f"{etf} core metrics")
        saved[f"nav_{etf}"] = nav_path
        saved[f"drawdown_{etf}"] = dd_path
        saved[f"metric_bar_{etf}"] = bar_path

    tracking_path = fig_dir / "ver3_0_effective_delta_tracking_error.png"
    _tracking_plot(summary, tracking_path)
    saved["tracking_error"] = tracking_path

    quality_path = fig_dir / "ver3_0_effective_delta_option_quality_comparison.png"
    _quality_plot(quality, stress, quality_path)
    saved["option_quality"] = quality_path

    phase_path = fig_dir / "ver3_0_effective_delta_phase_lite_distribution.png"
    if "sharpe_daily_mean" in phase_metrics.columns:
        _phase_plot(phase_metrics, phase_path)
        saved["phase_lite"] = phase_path
    return saved


def _line_plot(df: pd.DataFrame, x_col: str, y_col: str, path: Path, title: str, ylabel: str) -> None:
    fig, ax = plt.subplots(figsize=(9, 4.8))
    for name, group in df.groupby("implementation_name"):
        g = group.sort_values(x_col)
        ax.plot(pd.to_datetime(g[x_col]), g[y_col].astype(float), label=name, linewidth=1.4)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def _metric_bar(df: pd.DataFrame, path: Path, title: str) -> None:
    cols = [
        ("annualized_return_cagr", "CAGR"),
        ("sharpe_daily_mean", "Sharpe"),
        ("max_drawdown", "MDD"),
        ("option_leg_annualized_pnl_contribution", "Option leg"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(9, 6))
    for ax, (col, label) in zip(axes.ravel(), cols):
        ax.bar(df["implementation_name"], pd.to_numeric(df[col], errors="coerce"), color="#3b6ea8")
        ax.set_title(label)
        ax.tick_params(axis="x", labelrotation=30)
        ax.grid(axis="y", alpha=0.2)
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def _tracking_plot(summary: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 4.8))
    labels = summary["etf_code"].astype(str) + " " + summary["implementation_name"].astype(str)
    ax.bar(labels, summary["effective_delta_tracking_error"].astype(float), color="#6a8f4e")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title("Actual effective delta tracking error")
    ax.tick_params(axis="x", labelrotation=45)
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def _quality_plot(quality: pd.DataFrame, stress: pd.DataFrame, path: Path) -> None:
    df = quality.merge(stress, on=["etf_code", "implementation_name"], how="left")
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.scatter(df["payoff_burden_agg"], df["premium_capture_ratio_agg"], s=70, c=df["p99_short_call_mtm_loss"], cmap="viridis")
    for _, row in df.iterrows():
        ax.annotate(f"{row['etf_code']} {row['implementation_name']}", (row["payoff_burden_agg"], row["premium_capture_ratio_agg"]), fontsize=7)
    ax.set_xlabel("Payoff burden / premium")
    ax.set_ylabel("Net option leg / premium")
    ax.set_title("Premium capture vs payoff burden")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def _phase_plot(phase_metrics: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 4.8))
    labels = []
    data = []
    for keys, group in phase_metrics.groupby(["etf_code", "implementation_name"]):
        labels.append(f"{keys[0]} {keys[1]}")
        data.append(pd.to_numeric(group["sharpe_daily_mean"], errors="coerce").dropna())
    ax.boxplot(data, labels=labels, showmeans=True)
    ax.set_title("Phase-lite Sharpe distribution")
    ax.tick_params(axis="x", labelrotation=45)
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
