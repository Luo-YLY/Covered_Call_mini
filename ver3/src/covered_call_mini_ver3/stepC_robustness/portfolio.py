from __future__ import annotations

import pandas as pd

from .config import CandidateSpec, INITIAL_NAV, TARGET_SAMPLE_END, TARGET_SAMPLE_START, sleeve_return_column


def align_candidate_sample(return_panel: pd.DataFrame, candidates: list[CandidateSpec]) -> pd.DataFrame:
    """Align candidate sleeve returns on the common non-missing Step C sample."""

    required = sorted({sleeve_return_column(key) for candidate in candidates for key in candidate.sleeve_weights})
    missing = [col for col in required if col not in return_panel.columns]
    if missing:
        raise ValueError("Step C 缺少候选 sleeve return 列：\n" + "\n".join(missing))
    out = return_panel[["date", *required]].copy()
    out["date"] = pd.to_datetime(out["date"])
    out = out[(out["date"] >= pd.Timestamp(TARGET_SAMPLE_START)) & (out["date"] <= pd.Timestamp(TARGET_SAMPLE_END))]
    out = out.dropna(subset=required).sort_values("date").reset_index(drop=True)
    if out.empty:
        raise ValueError("Step C 候选组合样本对齐后为空。")
    return out


def compute_candidate_daily_returns(
    sample_panel: pd.DataFrame,
    option_leg_panel: pd.DataFrame,
    candidates: list[CandidateSpec],
) -> pd.DataFrame:
    """Compute candidate daily total and option-leg returns."""

    returns = sample_panel.set_index("date")
    option = (
        option_leg_panel.assign(date=lambda x: pd.to_datetime(x["date"])).set_index("date").reindex(returns.index)
        if option_leg_panel is not None and not option_leg_panel.empty
        else pd.DataFrame(index=returns.index)
    )
    frames = []
    for candidate in candidates:
        total = pd.Series(0.0, index=returns.index)
        option_leg = pd.Series(0.0, index=returns.index)
        for sleeve_key, weight in candidate.sleeve_weights.items():
            col = sleeve_return_column(sleeve_key)
            total = total.add(returns[col].astype(float) * float(weight), fill_value=0.0)
            if col in option.columns:
                option_leg = option_leg.add(option[col].astype(float).fillna(0.0) * float(weight), fill_value=0.0)
        frame = pd.DataFrame(
            {
                "date": returns.index,
                "portfolio_name": candidate.portfolio_name,
                "source_portfolio_name": candidate.source_portfolio_name,
                "universe_short": candidate.universe_short,
                "role": candidate.role,
                "portfolio_daily_return": total.values,
                "portfolio_option_leg_return": option_leg.values,
                "initial_nav": INITIAL_NAV,
            }
        )
        frames.append(frame)
    return pd.concat(frames, ignore_index=True, sort=False)


def build_nav_and_drawdown(candidate_returns: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build NAV and drawdown paths from candidate returns."""

    nav_frames = []
    dd_frames = []
    for _name, group in candidate_returns.groupby("portfolio_name", sort=False):
        g = group.sort_values("date").copy()
        nav = (1.0 + g["portfolio_daily_return"].astype(float)).cumprod() * INITIAL_NAV
        nav_frame = g[["date", "portfolio_name", "source_portfolio_name", "universe_short", "role", "initial_nav"]].copy()
        nav_frame["nav"] = nav.values
        nav_frame["final_nav_to_date"] = nav_frame["nav"]
        peak = nav_frame["nav"].astype(float).cummax()
        dd_frame = nav_frame[["date", "portfolio_name", "source_portfolio_name", "universe_short", "role"]].copy()
        dd_frame["rolling_peak_nav"] = peak.values
        dd_frame["drawdown"] = nav_frame["nav"].astype(float).values / peak.values - 1.0
        dd_frame["drawdown_magnitude"] = -dd_frame["drawdown"]
        nav_frames.append(nav_frame)
        dd_frames.append(dd_frame)
    return (
        pd.concat(nav_frames, ignore_index=True, sort=False),
        pd.concat(dd_frames, ignore_index=True, sort=False),
    )
