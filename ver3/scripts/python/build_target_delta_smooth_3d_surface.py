from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from matplotlib.ticker import PercentFormatter
import numpy as np
import pandas as pd
from scipy.interpolate import RectBivariateSpline


ROOT = Path(__file__).resolve().parents[3]
GRID_PATH = (
    ROOT
    / "outputs"
    / "ver3_1_effective_zone_target_delta"
    / "summary"
    / "ver3_1_target_delta_surface_grid.csv"
)
OUT_ROOT = (
    ROOT
    / "outputs"
    / "ver3_1_effective_zone_target_delta"
    / "analysis"
    / "target_delta_smooth_3d"
)
FIGURE_DIR = OUT_ROOT / "figures"
SUMMARY_DIR = OUT_ROOT / "summary"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a presentation-ready smooth target-delta x coverage Sharpe surface."
    )
    parser.add_argument("--etf", default="510300", help="Six-digit ETF code.")
    parser.add_argument("--dpi", type=int, default=200, help="PNG resolution.")
    return parser.parse_args()


def load_surface(etf_code: str) -> pd.DataFrame:
    if not GRID_PATH.exists():
        raise FileNotFoundError(f"Missing target-delta grid: {GRID_PATH}")

    grid = pd.read_csv(GRID_PATH, dtype={"etf_code": str})
    grid["etf_code"] = grid["etf_code"].str.zfill(6)
    surface = grid[
        grid["etf_code"].eq(etf_code)
        & grid["parameter_grid_role"].astype(str).eq("target_delta_surface")
    ].copy()
    for column in ("target_delta", "coverage", "sharpe_daily_mean"):
        surface[column] = pd.to_numeric(surface[column], errors="coerce")
    surface = surface.dropna(subset=["target_delta", "coverage", "sharpe_daily_mean"])
    surface = surface.sort_values(["target_delta", "coverage"]).reset_index(drop=True)
    if surface.empty:
        raise ValueError(f"No target-delta surface rows found for {etf_code}.")

    delta_count = surface["target_delta"].nunique()
    coverage_count = surface["coverage"].nunique()
    expected_rows = delta_count * coverage_count
    if len(surface) != expected_rows:
        raise ValueError(
            f"Surface grid is incomplete for {etf_code}: {len(surface)} rows, expected {expected_rows}."
        )
    return surface


def build_smooth_surface(surface: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    pivot = (
        surface.pivot(index="target_delta", columns="coverage", values="sharpe_daily_mean")
        .sort_index()
        .sort_index(axis=1)
    )
    deltas = pivot.index.to_numpy(dtype=float)
    coverages = pivot.columns.to_numpy(dtype=float)
    values = pivot.to_numpy(dtype=float)

    spline = RectBivariateSpline(
        deltas,
        coverages,
        values,
        kx=min(3, len(deltas) - 1),
        ky=min(3, len(coverages) - 1),
        s=0,
    )
    delta_fine = np.linspace(float(deltas.min()), float(deltas.max()), 81)
    coverage_fine = np.linspace(float(coverages.min()), float(coverages.max()), 121)
    z_fine = spline(delta_fine, coverage_fine)

    # Prevent cubic interpolation overshoot from inventing values outside the observed grid range.
    z_fine = np.clip(z_fine, float(np.nanmin(values)), float(np.nanmax(values)))
    x_grid, y_grid = np.meshgrid(delta_fine, coverage_fine, indexing="ij")
    return x_grid, y_grid, z_fine


def draw_surface(surface: pd.DataFrame, etf_code: str, output_path: Path, dpi: int) -> None:
    x_grid, y_grid, z_grid = build_smooth_surface(surface)
    x = surface["target_delta"].to_numpy(dtype=float)
    y = surface["coverage"].to_numpy(dtype=float)
    z = surface["sharpe_daily_mean"].to_numpy(dtype=float)
    z_min = float(np.nanmin(z))
    z_max = float(np.nanmax(z))
    best = surface.loc[surface["sharpe_daily_mean"].idxmax()]

    fig = plt.figure(figsize=(10.0, 7.5), facecolor="white")
    ax = fig.add_subplot(111, projection="3d")
    norm = Normalize(vmin=z_min, vmax=z_max)
    plotted_surface = ax.plot_surface(
        x_grid,
        y_grid,
        z_grid,
        cmap="RdYlGn",
        norm=norm,
        alpha=0.82,
        rstride=2,
        cstride=2,
        linewidth=0.12,
        edgecolor=(1.0, 1.0, 1.0, 0.38),
        antialiased=True,
    )
    ax.scatter(
        x,
        y,
        z,
        s=26,
        color="#17212f",
        alpha=0.9,
        edgecolor="white",
        linewidth=0.45,
        depthshade=False,
        label="backtest points",
    )
    best_marker_z = float(best["sharpe_daily_mean"]) + 0.015
    ax.scatter(
        [float(best["target_delta"])],
        [float(best["coverage"])],
        [best_marker_z],
        s=360,
        marker="*",
        color="#bd4b43",
        edgecolor="white",
        linewidth=0.9,
        depthshade=False,
        label="best grid point",
        zorder=20,
    )
    ax.text(
        float(best["target_delta"]),
        float(best["coverage"]) - 0.045,
        best_marker_z + 0.007,
        f"D{int(round(float(best['target_delta']) * 100))} Q{int(round(float(best['coverage']) * 100))}",
        fontsize=8,
        color="#2d3d4d",
        ha="center",
    )

    ax.set_title(
        f"{etf_code} Daily Sharpe: target delta x coverage x metric",
        pad=20,
        fontsize=13,
        fontweight="bold",
    )
    ax.set_xlabel("Target delta", labelpad=8)
    ax.set_ylabel("Coverage", labelpad=9)
    ax.set_zlabel("Daily Sharpe", labelpad=8)
    delta_ticks = sorted(surface["target_delta"].unique())
    coverage_ticks = sorted(surface["coverage"].unique())
    ax.set_xticks(delta_ticks)
    ax.set_xticklabels([f"D{int(round(value * 100))}" for value in delta_ticks])
    ax.set_yticks(coverage_ticks)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_zlim(z_min - 0.01, z_max + 0.025)
    ax.view_init(elev=25, azim=-55)
    ax.grid(True, alpha=0.24)
    ax.legend(loc="upper left", bbox_to_anchor=(0.02, 0.98), fontsize=8, frameon=True)

    colorbar = fig.colorbar(
        plotted_surface,
        ax=ax,
        shrink=0.60,
        pad=0.08,
        aspect=22,
        label="Daily Sharpe",
    )
    colorbar.set_ticks(np.linspace(z_min, z_max, 6))
    fig.text(
        0.5,
        0.025,
        "Surface is interpolated for visualization only; strategy interpretation still uses the 50 true daily-MTM grid points.",
        ha="center",
        fontsize=8.5,
        color="#4c5b6b",
    )
    fig.subplots_adjust(left=0.01, right=0.90, bottom=0.12, top=0.90)
    fig.savefig(output_path, dpi=dpi, facecolor="white")
    plt.close(fig)


def write_source_grid(surface: pd.DataFrame, output_path: Path) -> None:
    source = surface.copy()
    source["target_delta_label"] = source["target_delta"].map(
        lambda value: f"D{int(round(float(value) * 100))}"
    )
    source["coverage_label"] = source["coverage"].map(
        lambda value: f"Q{int(round(float(value) * 100))}"
    )
    columns = [
        "etf_code",
        "sleeve_name",
        "sample_start",
        "sample_end",
        "target_delta_label",
        "target_delta",
        "coverage_label",
        "coverage",
        "sharpe_daily_mean",
    ]
    source[columns].to_csv(output_path, index=False, encoding="utf-8-sig")


def main() -> None:
    args = parse_args()
    etf_code = str(args.etf).zfill(6)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)

    surface = load_surface(etf_code)
    figure_path = FIGURE_DIR / f"{etf_code}_target_delta_coverage_sharpe_3d_surface.png"
    source_path = SUMMARY_DIR / f"{etf_code}_target_delta_coverage_sharpe_grid.csv"
    draw_surface(surface, etf_code, figure_path, args.dpi)
    write_source_grid(surface, source_path)

    best = surface.loc[surface["sharpe_daily_mean"].idxmax()]
    print(f"Wrote {figure_path.relative_to(ROOT)}")
    print(f"Wrote {source_path.relative_to(ROOT)}")
    print(
        "Best true grid point: "
        f"D{int(round(float(best['target_delta']) * 100))} "
        f"Q{int(round(float(best['coverage']) * 100))} "
        f"Sharpe={float(best['sharpe_daily_mean']):.6f}"
    )


if __name__ == "__main__":
    main()
