from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

import matplotlib

matplotlib.use("Agg")

import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import TwoSlopeNorm


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXPERIMENT_ROOT = ROOT / "outputs" / "ver3_1_effective_zone_target_delta"
GRID_PATH = EXPERIMENT_ROOT / "summary" / "ver3_1_target_delta_surface_grid.csv"
OUT_ROOT = EXPERIMENT_ROOT / "analysis" / "target_delta_surface_contours"
FIGURE_DIR = OUT_ROOT / "figures"
SUMMARY_DIR = OUT_ROOT / "summary"

EFFECTIVE_DELTA_LEVELS = (0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45)


@dataclass(frozen=True)
class MetricSpec:
    column: str
    title: str
    cmap: str
    percent: bool = False
    center_zero: bool = False


SHARPE_METRIC = MetricSpec("sharpe_daily_mean", "Sharpe", "viridis")
CAGR_METRIC = MetricSpec("annualized_return_cagr", "CAGR", "viridis", percent=True)
MDD_METRIC = MetricSpec("max_drawdown", "Max drawdown", "magma_r", percent=True)
VOLATILITY_METRIC = MetricSpec("annualized_volatility", "Annualized volatility", "magma_r", percent=True)
OPTION_LEG_METRIC = MetricSpec(
    "option_leg_annualized_pnl_contribution",
    "Option leg ann. contribution",
    "RdBu",
    percent=True,
    center_zero=True,
)

FULL_METRICS = (
    SHARPE_METRIC,
    CAGR_METRIC,
    MDD_METRIC,
    VOLATILITY_METRIC,
    OPTION_LEG_METRIC,
    MetricSpec("assignment_rate", "Assignment rate", "magma_r", percent=True),
)

STANDALONE_METRICS = (
    ("sharpe", "sharpe", SHARPE_METRIC),
    ("cagr", "cagr", CAGR_METRIC),
    ("annualized_volatility", "volatility", VOLATILITY_METRIC),
    ("max_drawdown", "mdd", MDD_METRIC),
    ("option_leg", "option_leg", OPTION_LEG_METRIC),
)


def main() -> None:
    ensure_dirs()
    grid = load_target_delta_grid()
    grid = add_exposure_columns(grid)

    write_surface_table(grid)
    figure_index = build_figures(grid)
    figure_index.to_csv(SUMMARY_DIR / "target_delta_surface_contour_figure_index.csv", index=False, encoding="utf-8-sig")
    write_sample_audit(grid)
    write_readme(figure_index)

    print(f"Wrote target-delta surface contours to {OUT_ROOT.relative_to(ROOT)}")
    print((SUMMARY_DIR / "target_delta_surface_contour_points.csv").resolve())
    print((SUMMARY_DIR / "target_delta_surface_contour_figure_index.csv").resolve())


def ensure_dirs() -> None:
    for path in (OUT_ROOT, FIGURE_DIR, SUMMARY_DIR):
        path.mkdir(parents=True, exist_ok=True)


def load_target_delta_grid() -> pd.DataFrame:
    if not GRID_PATH.exists():
        raise FileNotFoundError(f"Missing target-delta grid: {GRID_PATH}")

    grid = pd.read_csv(GRID_PATH)
    grid["etf_code"] = grid["etf_code"].astype(str).str.zfill(6)
    grid = grid[
        grid["parameter_grid_role"].astype(str).eq("target_delta_surface")
        & grid["target_delta"].notna()
        & grid["coverage"].notna()
    ].copy()
    if grid.empty:
        raise ValueError("Target-delta surface grid is empty after filtering.")

    numeric_cols = [
        "target_delta",
        "coverage",
        "annualized_return_cagr",
        "annualized_volatility",
        "sharpe_daily_mean",
        "max_drawdown",
        "option_leg_annualized_pnl_contribution",
        "assignment_rate",
        "avg_selected_delta",
        "avg_realized_moneyness",
    ]
    for col in numeric_cols:
        if col in grid.columns:
            grid[col] = pd.to_numeric(grid[col], errors="coerce")
    return grid


def add_exposure_columns(grid: pd.DataFrame) -> pd.DataFrame:
    out = grid.copy()
    out["short_call_effective_delta"] = out["target_delta"] * out["coverage"]
    out["net_delta_proxy"] = 1.0 - out["short_call_effective_delta"]
    out["target_delta_label"] = out["target_delta"].map(lambda x: f"D{int(round(float(x) * 100)):02d}")
    out["coverage_label"] = out["coverage"].map(lambda x: f"Q{int(round(float(x) * 100))}")
    return out


def write_surface_table(grid: pd.DataFrame) -> None:
    columns = [
        "etf_code",
        "sleeve_name",
        "sample_scope",
        "sample_start",
        "sample_end",
        "n_trading_days",
        "selected_periods",
        "target_delta_label",
        "target_delta",
        "coverage_label",
        "coverage",
        "short_call_effective_delta",
        "net_delta_proxy",
        "annualized_return_cagr",
        "annualized_volatility",
        "sharpe_daily_mean",
        "max_drawdown",
        "option_leg_annualized_pnl_contribution",
        "assignment_rate",
        "avg_selected_delta",
        "avg_realized_moneyness",
    ]
    available = [col for col in columns if col in grid.columns]
    grid[available].sort_values(["etf_code", "target_delta", "coverage"]).to_csv(
        SUMMARY_DIR / "target_delta_surface_contour_points.csv",
        index=False,
        encoding="utf-8-sig",
    )


def write_sample_audit(grid: pd.DataFrame) -> None:
    rows = []
    for etf_code, group in grid.groupby("etf_code", sort=True):
        rows.append(
            {
                "etf_code": etf_code,
                "sample_scope": ";".join(sorted(group["sample_scope"].astype(str).unique())),
                "sample_start": ";".join(sorted(group["sample_start"].astype(str).unique())),
                "sample_end": ";".join(sorted(group["sample_end"].astype(str).unique())),
                "n_trading_days": ";".join(str(x) for x in sorted(group["n_trading_days"].dropna().unique())),
                "selected_periods": ";".join(str(x) for x in sorted(group["selected_periods"].dropna().unique())),
                "target_delta_grid": ";".join(f"{x:.2f}" for x in sorted(group["target_delta"].dropna().unique())),
                "coverage_grid": ";".join(f"{x:.1f}" for x in sorted(group["coverage"].dropna().unique())),
            }
        )
    pd.DataFrame(rows).to_csv(SUMMARY_DIR / "target_delta_surface_contour_sample_audit.csv", index=False, encoding="utf-8-sig")


def build_figures(grid: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    for etf_code, group in grid.groupby("etf_code", sort=True):
        full_path = FIGURE_DIR / f"{etf_code}_target_delta_coverage_full_metric_contours.png"
        for figure_type, file_metric, metric_spec in STANDALONE_METRICS:
            output_path = FIGURE_DIR / f"{etf_code}_target_delta_coverage_{file_metric}_contours.png"
            draw_metric_panel(group, etf_code, (metric_spec,), output_path, ncols=1, figsize=(7.5, 5.8))
            rows.append(
                {
                    "etf_code": etf_code,
                    "figure_type": figure_type,
                    "path": str(output_path.relative_to(ROOT)),
                    "sample_scope": str(group["sample_scope"].iloc[0]),
                    "sample_start": str(group["sample_start"].iloc[0]),
                    "sample_end": str(group["sample_end"].iloc[0]),
                }
            )

        draw_metric_panel(group, etf_code, FULL_METRICS, full_path, ncols=3, figsize=(13.5, 7.8))
        rows.append(
            {
                "etf_code": etf_code,
                "figure_type": "full_metrics",
                "path": str(full_path.relative_to(ROOT)),
                "sample_scope": str(group["sample_scope"].iloc[0]),
                "sample_start": str(group["sample_start"].iloc[0]),
                "sample_end": str(group["sample_end"].iloc[0]),
            }
        )
    return pd.DataFrame(rows)


def draw_metric_panel(
    group: pd.DataFrame,
    etf_code: str,
    metric_specs: tuple[MetricSpec, ...],
    output_path: Path,
    ncols: int,
    figsize: tuple[float, float],
) -> None:
    nrows = int(np.ceil(len(metric_specs) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=figsize, constrained_layout=True)
    axes_arr = np.array(axes).reshape(-1)
    for ax, spec in zip(axes_arr, metric_specs):
        draw_single_surface(ax, group, spec)
    for ax in axes_arr[len(metric_specs) :]:
        ax.axis("off")

    sample = group.iloc[0]
    title = (
        f"{etf_code} target-delta x coverage surface, "
        f"{sample['sample_start']} to {sample['sample_end']}"
    )
    fig.suptitle(title, fontsize=13)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def draw_single_surface(ax: plt.Axes, group: pd.DataFrame, spec: MetricSpec) -> None:
    pivot = (
        group.pivot_table(index="target_delta", columns="coverage", values=spec.column, aggfunc="first")
        .sort_index()
        .sort_index(axis=1)
    )
    x = pivot.columns.to_numpy(dtype=float)
    y = pivot.index.to_numpy(dtype=float)
    x_grid, y_grid = np.meshgrid(x, y)
    z = pivot.to_numpy(dtype=float)

    norm = None
    if spec.center_zero:
        max_abs = float(np.nanmax(np.abs(z))) if np.isfinite(z).any() else 1.0
        max_abs = max(max_abs, 1e-9)
        norm = TwoSlopeNorm(vmin=-max_abs, vcenter=0.0, vmax=max_abs)

    mesh = ax.pcolormesh(x_grid, y_grid, z, shading="auto", cmap=spec.cmap, norm=norm)
    add_effective_delta_contours(ax, x_grid, y_grid)
    add_cell_values(ax, pivot, spec)

    ax.set_title(spec.title, fontsize=10)
    ax.set_xlabel("Coverage")
    ax.set_ylabel("Target call delta")
    ax.set_xticks(x)
    ax.set_xticklabels([f"Q{int(round(v * 100))}" for v in x], rotation=45, ha="right")
    ax.set_yticks(y)
    ax.set_yticklabels([f"D{int(round(v * 100))}" for v in y])
    ax.set_xlim(float(x.min()) - 0.05, float(x.max()) + 0.05)
    ax.set_ylim(float(y.min()) - 0.025, float(y.max()) + 0.025)

    colorbar = plt.colorbar(mesh, ax=ax, shrink=0.82)
    if spec.percent:
        colorbar.ax.set_ylabel("value")
        colorbar.ax.yaxis.set_major_formatter(lambda value, _pos: f"{value * 100:.1f}%")


def add_effective_delta_contours(ax: plt.Axes, x_grid: np.ndarray, y_grid: np.ndarray) -> None:
    effective_delta = x_grid * y_grid
    min_level = float(np.nanmin(effective_delta))
    max_level = float(np.nanmax(effective_delta))
    levels = [level for level in EFFECTIVE_DELTA_LEVELS if min_level <= level <= max_level]
    if not levels:
        return

    contours = ax.contour(
        x_grid,
        y_grid,
        effective_delta,
        levels=levels,
        colors="#101010",
        linewidths=1.0,
        linestyles="dashed",
        alpha=0.92,
    )
    for collection in contours.collections:
        collection.set_path_effects([pe.Stroke(linewidth=2.6, foreground="white"), pe.Normal()])
    labels = ax.clabel(contours, inline=True, fontsize=7, fmt=lambda value: f"c*d={value:.2f}")
    for label in labels:
        label.set_path_effects([pe.Stroke(linewidth=2.2, foreground="white"), pe.Normal()])


def add_cell_values(ax: plt.Axes, pivot: pd.DataFrame, spec: MetricSpec) -> None:
    for target_delta, row in pivot.iterrows():
        for coverage, value in row.items():
            if pd.isna(value):
                continue
            text = f"{value * 100:.1f}" if spec.percent else f"{value:.2f}"
            ax.text(
                float(coverage),
                float(target_delta),
                text,
                ha="center",
                va="center",
                fontsize=7,
                color="#111111",
                path_effects=[pe.Stroke(linewidth=1.8, foreground="white"), pe.Normal()],
            )


def write_readme(figure_index: pd.DataFrame) -> None:
    lines = [
        "# Target Delta Surface Contours",
        "",
        "This output visualizes the target-delta x coverage parameter surface from `ver3_1_target_delta_surface_grid.csv`.",
        "Each heatmap overlays contour lines of `coverage * target_delta`, a proxy for short-call effective delta exposure.",
        "",
        "No candidate selection is performed in this layer.",
        "",
        "## Outputs",
        "",
        "- `summary/target_delta_surface_contour_points.csv`: long-form grid with effective-delta exposure columns.",
        "- `summary/target_delta_surface_contour_sample_audit.csv`: sample-period and grid audit by ETF.",
        "- `figures/*_target_delta_coverage_sharpe_contours.png`: standalone Sharpe heatmaps.",
        "- `figures/*_target_delta_coverage_cagr_contours.png`: standalone CAGR heatmaps.",
        "- `figures/*_target_delta_coverage_volatility_contours.png`: standalone annualized volatility heatmaps.",
        "- `figures/*_target_delta_coverage_mdd_contours.png`: standalone MDD heatmaps.",
        "- `figures/*_target_delta_coverage_option_leg_contours.png`: standalone option-leg contribution heatmaps.",
        "- `figures/*_target_delta_coverage_full_metric_contours.png`: six-metric diagnostic panels.",
        "",
        "## Figure Index",
        "",
    ]
    for _, row in figure_index.iterrows():
        lines.append(f"- {row['etf_code']} `{row['figure_type']}`: `{row['path']}`")
    (OUT_ROOT / "README.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
