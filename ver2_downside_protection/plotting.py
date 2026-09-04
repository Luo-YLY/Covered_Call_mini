from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ver2_downside_protection.downside_analysis import BUCKET_ORDER
from ver2_downside_protection.metrics import drawdown_curve

plt.rcParams["axes.unicode_minus"] = False

PLOT_STRATEGIES = ["BuyHold", "ITM5_100", "ITM2_100", "ATM_100", "OTM2_100", "OTM5_100"]
STRATEGY_COLORS = {
    "BuyHold": "#222222",
    "ITM5_100": "#9467bd",
    "ITM2_100": "#8c564b",
    "ATM_100": "#1f77b4",
    "OTM2_100": "#17becf",
    "OTM5_100": "#2ca02c",
    "OTM5_50": "#ff7f0e",
}


def _save(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(path, dpi=170)
    plt.close()
    return path


def plot_nav_comparison(nav: pd.DataFrame, output_dir: Path) -> dict[str, Path]:
    saved: dict[str, Path] = {}
    data = nav.copy()
    data["date"] = pd.to_datetime(data["date"])
    for etf_code, g in data.groupby("etf_code"):
        fig, ax = plt.subplots(figsize=(10.5, 5.4))
        for strategy in PLOT_STRATEGIES:
            sg = g[g["strategy_name"] == strategy]
            if sg.empty:
                continue
            ax.plot(
                sg["date"],
                sg["nav"],
                label=strategy,
                linewidth=2.2 if strategy == "BuyHold" else 1.8,
                color=STRATEGY_COLORS.get(strategy),
                linestyle="--" if strategy == "BuyHold" else "-",
            )
        ax.set_title(f"ver2 NAV comparison - {etf_code}", loc="left")
        ax.set_xlabel("Date")
        ax.set_ylabel("NAV")
        ax.grid(True, linestyle=":", alpha=0.45)
        ax.legend()
        saved[str(etf_code)] = _save(output_dir / "figures" / "nav" / f"ver2_nav_{etf_code}.png")
    return saved


def plot_drawdown_comparison(nav: pd.DataFrame, output_dir: Path) -> dict[str, Path]:
    saved: dict[str, Path] = {}
    data = nav.copy()
    data["date"] = pd.to_datetime(data["date"])
    for etf_code, g in data.groupby("etf_code"):
        fig, ax = plt.subplots(figsize=(10.5, 5.4))
        for strategy in PLOT_STRATEGIES:
            sg = g[g["strategy_name"] == strategy].sort_values("date")
            if sg.empty:
                continue
            ax.plot(
                sg["date"],
                drawdown_curve(sg["nav"]) * 100.0,
                label=strategy,
                linewidth=2.2 if strategy == "BuyHold" else 1.8,
                color=STRATEGY_COLORS.get(strategy),
                linestyle="--" if strategy == "BuyHold" else "-",
            )
        ax.set_title(f"ver2 drawdown comparison - {etf_code}", loc="left")
        ax.set_xlabel("Date")
        ax.set_ylabel("Drawdown (%)")
        ax.grid(True, linestyle=":", alpha=0.45)
        ax.legend()
        saved[str(etf_code)] = _save(output_dir / "figures" / "drawdown" / f"ver2_drawdown_{etf_code}.png")
    return saved


def plot_downside_bucket_excess(bucket_table: pd.DataFrame, output_dir: Path) -> dict[str, Path]:
    saved: dict[str, Path] = {}
    if bucket_table.empty:
        return saved
    for etf_code, g in bucket_table.groupby("etf_code"):
        strategies = [
            s
            for s in ["ITM5_100", "ITM2_100", "ATM_100", "OTM2_100", "OTM5_100", "OTM5_50"]
            if s in set(g["strategy_name"])
        ]
        x = np.arange(len(BUCKET_ORDER))
        width = 0.75 / max(len(strategies), 1)
        fig, ax = plt.subplots(figsize=(9.5, 5.2))
        for i, strategy in enumerate(strategies):
            sg = g[g["strategy_name"] == strategy].set_index("downside_bucket").reindex(BUCKET_ORDER)
            values = sg["excess_return_mean"].astype(float).values * 100.0
            offset = (i - (len(strategies) - 1) / 2) * width
            ax.bar(x + offset, values, width=width, label=strategy, color=STRATEGY_COLORS.get(strategy))
        ax.axhline(0, color="#444444", linewidth=0.9)
        ax.set_title(f"ver2 downside bucket excess return - {etf_code}", loc="left")
        ax.set_xticks(x)
        ax.set_xticklabels(BUCKET_ORDER)
        ax.set_ylabel("Average excess return (pct points)")
        ax.grid(True, axis="y", linestyle=":", alpha=0.45)
        ax.legend()
        saved[str(etf_code)] = _save(
            output_dir / "figures" / "downside_bucket" / f"ver2_downside_bucket_excess_{etf_code}.png"
        )
    return saved


def plot_excess_scatter(periods: pd.DataFrame, output_dir: Path) -> dict[str, Path]:
    saved: dict[str, Path] = {}
    data = periods[periods["strategy_name"] != "BuyHold"].copy()
    if data.empty:
        return saved
    for (etf_code, strategy), g in data.groupby(["etf_code", "strategy_name"]):
        fig, ax = plt.subplots(figsize=(7.4, 5.4))
        colors = np.where(g["etf_period_return"] < 0, "#d62728", "#2ca02c")
        ax.scatter(g["etf_period_return"] * 100.0, g["excess_return_vs_etf"] * 100.0, c=colors, alpha=0.75)
        ax.axhline(0, color="#444444", linewidth=0.9)
        ax.axvline(0, color="#444444", linewidth=0.9)
        ax.set_title(f"ver2 excess scatter - {etf_code} {strategy}", loc="left")
        ax.set_xlabel("ETF period return (%)")
        ax.set_ylabel("Covered call excess return (pct points)")
        ax.grid(True, linestyle=":", alpha=0.45)
        saved[f"{etf_code}_{strategy}"] = _save(
            output_dir / "figures" / "scatter" / f"ver2_scatter_{etf_code}_{strategy}.png"
        )
    return saved


def plot_daily_mtm_nav(daily_mtm: pd.DataFrame, output_dir: Path) -> dict[str, Path]:
    saved: dict[str, Path] = {}
    if daily_mtm.empty:
        return saved
    data = daily_mtm.copy()
    data["date"] = pd.to_datetime(data["date"])
    data = data.sort_values(["date", "period_index"]).drop_duplicates(
        ["date", "etf_code", "strategy_name"],
        keep="last",
    )
    for etf_code, g in data.groupby("etf_code"):
        fig, ax = plt.subplots(figsize=(10.5, 5.4))
        for strategy in PLOT_STRATEGIES:
            sg = g[g["strategy_name"] == strategy].sort_values("date")
            if sg.empty:
                continue
            ax.plot(
                sg["date"],
                sg["daily_mtm_nav"],
                label=strategy,
                linewidth=2.1 if strategy == "BuyHold" else 1.5,
                color=STRATEGY_COLORS.get(strategy),
                linestyle="--" if strategy == "BuyHold" else "-",
            )
        ax.set_title(f"ver2 daily MTM NAV - {etf_code}", loc="left")
        ax.set_xlabel("Date")
        ax.set_ylabel("Daily MTM NAV")
        ax.grid(True, linestyle=":", alpha=0.45)
        ax.legend()
        saved[str(etf_code)] = _save(output_dir / "figures" / "daily_mtm_nav" / f"ver2_daily_mtm_nav_{etf_code}.png")
    return saved


def plot_option_mtm_loss(daily_mtm: pd.DataFrame, output_dir: Path) -> dict[str, Path]:
    saved: dict[str, Path] = {}
    if daily_mtm.empty:
        return saved
    data = daily_mtm[daily_mtm["strategy_name"] != "BuyHold"].copy()
    if data.empty:
        return saved
    data["date"] = pd.to_datetime(data["date"])
    for (etf_code, strategy), g in data.groupby(["etf_code", "strategy_name"]):
        g = g.sort_values(["date", "period_index"]).drop_duplicates(["date"], keep="last")
        fig, ax = plt.subplots(figsize=(10.0, 4.8))
        ax.plot(
            g["date"],
            g["short_call_mtm_loss_return"] * 100.0,
            color=STRATEGY_COLORS.get(strategy, "#1f77b4"),
            linewidth=1.4,
        )
        ax.fill_between(
            g["date"],
            0.0,
            g["short_call_mtm_loss_return"] * 100.0,
            color=STRATEGY_COLORS.get(strategy, "#1f77b4"),
            alpha=0.18,
        )
        ax.set_title(f"ver2 short call MTM loss - {etf_code} {strategy}", loc="left")
        ax.set_xlabel("Date")
        ax.set_ylabel("Loss vs entry premium (% of entry ETF)")
        ax.grid(True, linestyle=":", alpha=0.45)
        saved[f"{etf_code}_{strategy}"] = _save(
            output_dir / "figures" / "option_mtm_loss" / f"ver2_option_mtm_loss_{etf_code}_{strategy}.png"
        )
    return saved


def write_figures(
    periods: pd.DataFrame,
    nav: pd.DataFrame,
    bucket_table: pd.DataFrame,
    output_dir: Path,
    daily_mtm: pd.DataFrame | None = None,
) -> dict[str, dict[str, Path]]:
    daily = daily_mtm if daily_mtm is not None else pd.DataFrame()
    return {
        "nav": plot_nav_comparison(nav, output_dir),
        "drawdown": plot_drawdown_comparison(nav, output_dir),
        "downside_bucket": plot_downside_bucket_excess(bucket_table, output_dir),
        "scatter": plot_excess_scatter(periods, output_dir),
        "daily_mtm_nav": plot_daily_mtm_nav(daily, output_dir),
        "option_mtm_loss": plot_option_mtm_loss(daily, output_dir),
    }
