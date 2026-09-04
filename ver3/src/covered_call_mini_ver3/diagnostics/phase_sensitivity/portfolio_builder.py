from __future__ import annotations

import pandas as pd

from .config import CandidatePortfolio, buyhold_key_for_etf


def build_phase_candidate_portfolios(
    sleeve_daily_returns: pd.DataFrame,
    portfolios: list[CandidatePortfolio],
    *,
    build_buyhold_benchmarks: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build phase-specific candidate portfolio daily returns and NAV."""

    all_specs: list[tuple[CandidatePortfolio, str, dict[str, float]]] = []
    for portfolio in portfolios:
        all_specs.append((portfolio, "target_candidate", portfolio.sleeve_weights))
        if build_buyhold_benchmarks:
            benchmark_weights = {
                buyhold_key_for_etf(str(key).split("__", 1)[0]): weight for key, weight in portfolio.sleeve_weights.items()
            }
            all_specs.append((portfolio, "buyhold_benchmark", benchmark_weights))

    rows: list[pd.DataFrame] = []
    nav_rows: list[pd.DataFrame] = []
    for portfolio, role, weights in all_specs:
        _validate_weights(weights, portfolio.portfolio_name)
        for phase_id, phase_group in sleeve_daily_returns.groupby("phase_id", sort=True):
            phase_shift = int(phase_group["phase_shift"].iloc[0])
            inception_date = str(phase_group["inception_date"].iloc[0])
            merged = None
            option_merged = None
            for sleeve_key, weight in weights.items():
                s = phase_group[phase_group["sleeve_key"].eq(sleeve_key)][
                    ["date", "daily_return_total", "daily_return_option_leg_component"]
                ].copy()
                if s.empty:
                    raise ValueError(f"Missing sleeve {sleeve_key} for {portfolio.portfolio_name} phase {phase_id}.")
                s = s.rename(
                    columns={
                        "daily_return_total": f"{sleeve_key}__ret",
                        "daily_return_option_leg_component": f"{sleeve_key}__option",
                    }
                )
                merged = s[["date", f"{sleeve_key}__ret"]] if merged is None else merged.merge(
                    s[["date", f"{sleeve_key}__ret"]], on="date", how="inner"
                )
                option_merged = s[["date", f"{sleeve_key}__option"]] if option_merged is None else option_merged.merge(
                    s[["date", f"{sleeve_key}__option"]], on="date", how="inner"
                )
            if merged is None or merged.empty:
                continue
            merged = merged.sort_values("date").reset_index(drop=True)
            option_merged = option_merged.sort_values("date").reset_index(drop=True)
            total = pd.Series(0.0, index=merged.index)
            option = pd.Series(0.0, index=merged.index)
            for sleeve_key, weight in weights.items():
                total += float(weight) * merged[f"{sleeve_key}__ret"].astype(float)
                option += float(weight) * option_merged[f"{sleeve_key}__option"].astype(float)
            out_name = portfolio.portfolio_name if role == "target_candidate" else f"{portfolio.portfolio_name}_BuyHoldBenchmark"
            frame = pd.DataFrame(
                {
                    "date": merged["date"],
                    "phase_id": phase_id,
                    "phase_shift": phase_shift,
                    "inception_date": inception_date,
                    "portfolio_name": out_name,
                    "base_portfolio_name": portfolio.portfolio_name,
                    "portfolio_role": role,
                    "portfolio_return": total.values,
                    "portfolio_option_leg_return": option.values,
                }
            )
            frame.loc[frame.index[0], "portfolio_return"] = 0.0
            frame.loc[frame.index[0], "portfolio_option_leg_return"] = 0.0
            nav = frame.copy()
            nav["nav"] = (1.0 + nav["portfolio_return"].astype(float)).cumprod()
            nav["initial_nav"] = 1.0
            rows.append(frame)
            nav_rows.append(nav[["date", "phase_id", "phase_shift", "inception_date", "portfolio_name", "base_portfolio_name", "portfolio_role", "nav", "initial_nav"]])
    return (
        pd.concat(rows, ignore_index=True).sort_values(["portfolio_role", "portfolio_name", "phase_shift", "date"]),
        pd.concat(nav_rows, ignore_index=True).sort_values(["portfolio_role", "portfolio_name", "phase_shift", "date"]),
    )


def _validate_weights(weights: dict[str, float], portfolio_name: str) -> None:
    total = sum(float(v) for v in weights.values())
    if abs(total - 1.0) > 1e-8:
        raise ValueError(f"Portfolio weights do not sum to 1 for {portfolio_name}: {total}")
