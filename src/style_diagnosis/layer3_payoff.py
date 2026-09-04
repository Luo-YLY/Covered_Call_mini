from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


FOCUS_ETFS = ["510300", "510050", "510500", "159915", "588000"]
EPSILON = 1e-6


COLUMN_LABELS_ZH = {
    "date": "开仓日",
    "close_date": "平仓/到期日",
    "etf_code": "ETF代码",
    "strategy_name": "策略名称",
    "strategy_family": "策略族",
    "option_rule": "期权规则",
    "moneyness_rule": "虚值规则",
    "delta_rule": "Delta规则",
    "tenor_rule": "期限规则",
    "coverage_rule": "覆盖率规则",
    "timing_rule": "择时规则",
    "is_diagnostic_rule": "是否诊断规则",
    "is_dynamic_rule": "是否动态规则",
    "underlying_price_open": "ETF开仓价格",
    "underlying_price_close": "ETF平仓价格",
    "strike": "行权价",
    "moneyness": "虚值程度",
    "days_to_expiry": "开仓剩余到期天数",
    "option_premium": "期权权利金",
    "premium_ratio_unit": "单位权利金比例",
    "coverage_ratio": "覆盖率",
    "underlying_return": "ETF本期收益率",
    "breach_flag": "是否突破行权价",
    "realized_upside_truncation_unit": "单位上行截断损失",
    "realized_cc_excess_unit": "单位备兑超额收益",
    "realized_premium_port": "组合权利金贡献",
    "realized_upside_truncation_port": "组合上行截断损失",
    "realized_cc_excess_port": "组合备兑超额收益",
    "transaction_cost": "交易成本",
    "actual_strategy_return": "实际策略收益",
    "actual_underlying_return": "实际ETF收益",
    "actual_strategy_excess": "实际策略超额收益",
    "theory_actual_gap": "理论与实际超额差异",
    "utr_hat_roll12": "12期滚动上行截断风险估计",
    "utr_hat_roll24": "24期滚动上行截断风险估计",
    "breach_prob_hat_roll24": "24期滚动突破概率估计",
    "breach_severity_hat_roll24": "24期滚动突破严重度估计",
    "pa_diff_roll24": "24期滚动权利金充足性差值",
    "pa_ratio_roll24": "24期滚动权利金充足性比例",
    "pa_z_roll24": "24期滚动权利金充足性Z值",
    "data_quality_flag": "数据质量标记",
    "observations": "样本数",
    "mean_premium_ratio_unit": "平均单位权利金比例",
    "median_premium_ratio_unit": "中位数单位权利金比例",
    "mean_realized_upside_truncation_unit": "平均单位上行截断损失",
    "median_realized_upside_truncation_unit": "中位数单位上行截断损失",
    "mean_realized_cc_excess_unit": "平均单位备兑超额收益",
    "median_realized_cc_excess_unit": "中位数单位备兑超额收益",
    "mean_realized_cc_excess_port": "平均组合备兑超额收益",
    "median_realized_cc_excess_port": "中位数组合备兑超额收益",
    "breach_rate": "突破率",
    "win_rate_unit": "单位收益胜率",
    "win_rate_port": "组合收益胜率",
    "mean_utr_hat_roll24": "平均24期滚动上行截断风险估计",
    "mean_pa_diff_roll24": "平均24期滚动权利金充足性差值",
    "median_pa_diff_roll24": "中位数24期滚动权利金充足性差值",
    "mean_pa_ratio_roll24": "平均24期滚动权利金充足性比例",
    "median_pa_ratio_roll24": "中位数24期滚动权利金充足性比例",
    "share_pa_diff_positive": "PA差值为正占比",
    "data_quality_summary": "数据质量汇总",
    "mean_breach_severity": "平均突破严重度",
    "pa_diff_bucket": "PA差值分组",
    "pa_ratio_bucket": "PA比例分组",
    "utr_bucket": "UTR分组",
    "scope": "范围",
    "x": "横轴变量",
    "y": "纵轴变量",
    "pearson": "Pearson相关系数",
    "spearman": "Spearman相关系数",
    "demeaned_corr": "去固定效应后相关系数",
    "note": "备注",
}


VALUE_LABELS_ZH = {
    "DTE30_ATM_unit": "DTE30平值单位覆盖",
    "DTE30_OTM5_unit": "DTE30虚值5%单位覆盖",
    "DTE30_Delta30_unit": "DTE30 Delta30单位覆盖",
    "DTE30_Delta20_unit": "DTE30 Delta20单位覆盖",
    "S1_ATM_100_Monthly": "平值100%月度备兑",
    "S2_Delta30_100_Monthly": "Delta30 100%月度备兑",
    "S3_Delta30_50_Monthly": "Delta30 50%月度备兑",
    "S4_OTM5_100_Monthly": "虚值5% 100%月度备兑",
    "S5_IVTiming_ATM_Monthly": "IV择时平值月度备兑",
    "S6_IVTiming_OTM5_Monthly": "IV择时虚值5%月度备兑",
    "covered_call": "备兑策略",
    "ATM": "平值",
    "OTM5": "虚值5%",
    "Delta30": "Delta30",
    "Delta20": "Delta20",
    "delta_target": "目标Delta",
    "DTE30": "约30天到期",
    "100%": "100%",
    "50%": "50%",
    "dynamic": "动态",
    "static": "静态",
    "iv_timing": "IV择时",
    "unknown": "未知",
    "none": "无",
    "ok": "正常",
    "low": "低",
    "medium": "中",
    "high": "高",
    "insufficient_data": "样本不足",
    "all": "全样本",
}


@dataclass(frozen=True)
class Layer3Paths:
    project_root: Path
    input_path: Path
    output_dir: Path
    plot_dir: Path


REQUIRED_SOURCE_COLUMNS = {
    "etf_code",
    "strategy",
    "roll_date",
    "end_date",
    "S0",
    "ST",
    "K",
    "C0",
    "coverage_ratio",
}


def _warn(message: str) -> None:
    warnings.warn(message, RuntimeWarning, stacklevel=2)


def _safe_numeric(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def _quality_append(flags: pd.Series, condition: pd.Series, label: str) -> pd.Series:
    out = flags.copy()
    mask = condition.fillna(False)
    out.loc[mask] = out.loc[mask].apply(lambda x: f"{x};{label}" if x else label)
    return out


def _zh_label(value: object) -> str:
    text = str(value)
    return VALUE_LABELS_ZH.get(text, COLUMN_LABELS_ZH.get(text, text))


def _localize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if out[col].dtype == "object":
            out[col] = out[col].map(lambda x: _zh_label(x) if pd.notna(x) else x)
    return out.rename(columns=COLUMN_LABELS_ZH)


def _to_csv_zh(df: pd.DataFrame, path: Path) -> None:
    _localize_dataframe(df).to_csv(path, index=False, encoding="utf-8-sig")


def load_source_periods(input_path: Path) -> pd.DataFrame:
    if not input_path.exists():
        raise FileNotFoundError(f"Missing source file: {input_path}")
    data = pd.read_csv(input_path, dtype={"etf_code": str})
    missing = sorted(REQUIRED_SOURCE_COLUMNS - set(data.columns))
    if missing:
        raise ValueError(f"{input_path} is missing required columns: {missing}")
    return data


def build_payoff_monthly(source: pd.DataFrame, focus_etfs: list[str] | None = None) -> tuple[pd.DataFrame, dict]:
    focus_etfs = focus_etfs or FOCUS_ETFS
    data = source.copy()
    data["etf_code"] = data["etf_code"].astype(str).str.zfill(6)
    data = data[data["etf_code"].isin(focus_etfs)].copy()
    data = data[data["strategy"].astype(str) != "S0_BuyHold"].copy()
    if "option_selected_flag" in data.columns:
        data = data[data["option_selected_flag"].fillna(0).astype(float) > 0].copy()

    rename = {
        "roll_date": "date",
        "end_date": "close_date",
        "strategy": "strategy_name",
        "S0": "underlying_price_open",
        "ST": "underlying_price_close",
        "K": "strike",
        "C0": "option_premium",
        "cost": "transaction_cost",
        "R_cc": "actual_strategy_return",
        "R_etf": "actual_underlying_return",
        "excess_return": "actual_strategy_excess",
    }
    out = data.rename(columns=rename)
    for col in ["date", "close_date"]:
        out[col] = pd.to_datetime(out[col], errors="coerce")

    numeric_cols = [
        "underlying_price_open",
        "underlying_price_close",
        "strike",
        "option_premium",
        "coverage_ratio",
        "transaction_cost",
        "actual_strategy_return",
        "actual_underlying_return",
        "actual_strategy_excess",
        "days_to_expiry",
    ]
    out = _safe_numeric(out, numeric_cols)

    out["data_quality_flag"] = ""
    for col in ["date", "close_date", "underlying_price_open", "underlying_price_close", "strike", "option_premium"]:
        if col not in out.columns:
            _warn(f"Missing {col}; related rows will be flagged.")
            out[col] = np.nan
        out["data_quality_flag"] = _quality_append(out["data_quality_flag"], out[col].isna(), f"missing_{col}")

    if "transaction_cost" not in out.columns:
        out["transaction_cost"] = 0.0
        out["data_quality_flag"] = _quality_append(out["data_quality_flag"], pd.Series(True, index=out.index), "transaction_cost_assumed_zero")
        _warn("transaction_cost missing; set to 0 and flagged.")
    else:
        out["transaction_cost"] = out["transaction_cost"].fillna(0.0)

    if "synthetic_demo" in out.columns and out["synthetic_demo"].fillna(False).astype(bool).any():
        out["data_quality_flag"] = _quality_append(
            out["data_quality_flag"], out["synthetic_demo"].fillna(False).astype(bool), "synthetic_demo"
        )

    out["moneyness"] = (out["strike"] - out["underlying_price_open"]) / out["underlying_price_open"]
    out["premium_ratio_unit"] = out["option_premium"] / out["underlying_price_open"]
    out["underlying_return"] = out["underlying_price_close"] / out["underlying_price_open"] - 1
    out["breach_flag"] = (out["underlying_return"] > out["moneyness"]).astype(int)
    out["realized_upside_truncation_unit"] = (out["underlying_return"] - out["moneyness"]).clip(lower=0)
    out["realized_cc_excess_unit"] = out["premium_ratio_unit"] - out["realized_upside_truncation_unit"]
    out["realized_premium_port"] = out["coverage_ratio"] * out["premium_ratio_unit"]
    out["realized_upside_truncation_port"] = out["coverage_ratio"] * out["realized_upside_truncation_unit"]
    out["realized_cc_excess_port"] = out["coverage_ratio"] * out["realized_cc_excess_unit"] - out["transaction_cost"]
    out["theory_actual_gap"] = np.nan
    if "actual_strategy_excess" in out.columns:
        out["theory_actual_gap"] = out["actual_strategy_excess"] - out["realized_cc_excess_port"]

    out["data_quality_flag"] = _quality_append(out["data_quality_flag"], out["premium_ratio_unit"] < 0, "negative_premium_ratio")
    out["data_quality_flag"] = _quality_append(
        out["data_quality_flag"], ~out["coverage_ratio"].between(0, 1.5), "coverage_ratio_out_of_expected_range"
    )
    out["data_quality_flag"] = _quality_append(out["data_quality_flag"], out["moneyness"].abs() > 0.5, "moneyness_outlier")

    out = out.sort_values(["etf_code", "strategy_name", "date"]).reset_index(drop=True)
    out = add_rolling_metrics(out)

    columns = [
        "date",
        "close_date",
        "etf_code",
        "strategy_name",
        "underlying_price_open",
        "underlying_price_close",
        "strike",
        "moneyness",
        "days_to_expiry",
        "option_premium",
        "premium_ratio_unit",
        "coverage_ratio",
        "underlying_return",
        "breach_flag",
        "realized_upside_truncation_unit",
        "realized_cc_excess_unit",
        "realized_premium_port",
        "realized_upside_truncation_port",
        "realized_cc_excess_port",
        "transaction_cost",
        "actual_strategy_return",
        "actual_underlying_return",
        "actual_strategy_excess",
        "theory_actual_gap",
        "utr_hat_roll12",
        "utr_hat_roll24",
        "breach_prob_hat_roll24",
        "breach_severity_hat_roll24",
        "pa_diff_roll24",
        "pa_ratio_roll24",
        "pa_z_roll24",
        "data_quality_flag",
    ]
    for col in columns:
        if col not in out.columns:
            out[col] = np.nan

    diagnostics = {
        "source_rows": len(source),
        "payoff_rows": len(out),
        "covered_etfs": sorted(out["etf_code"].dropna().unique().tolist()),
        "covered_strategies": sorted(out["strategy_name"].dropna().unique().tolist()),
        "date_min": out["date"].min(),
        "date_max": out["date"].max(),
        "quality_counts": quality_counts(out),
    }
    return out[columns], diagnostics


def add_rolling_metrics(df: pd.DataFrame, group_cols: list[str] | None = None) -> pd.DataFrame:
    out = df.copy()
    group_cols = group_cols or ["etf_code", "strategy_name"]
    groups = out.groupby(group_cols, group_keys=False)

    def add_group(g: pd.DataFrame) -> pd.DataFrame:
        g = g.sort_values("date").copy()
        trunc_shift = g["realized_upside_truncation_unit"].shift(1)
        breach_shift = g["breach_flag"].shift(1)
        premium_shift = g["premium_ratio_unit"].shift(1)

        g["utr_hat_roll12"] = trunc_shift.rolling(12, min_periods=6).mean()
        g["utr_hat_roll24"] = trunc_shift.rolling(24, min_periods=6).mean()
        g["breach_prob_hat_roll24"] = breach_shift.rolling(24, min_periods=6).mean()
        trunc_sum = trunc_shift.rolling(24, min_periods=6).sum()
        breach_sum = breach_shift.rolling(24, min_periods=6).sum()
        g["breach_severity_hat_roll24"] = trunc_sum / breach_sum.replace(0, np.nan)
        g["pa_diff_roll24"] = g["premium_ratio_unit"] - g["utr_hat_roll24"]
        g["pa_ratio_roll24"] = np.where(
            g["utr_hat_roll24"].notna(),
            g["premium_ratio_unit"] / (g["utr_hat_roll24"] + EPSILON),
            np.nan,
        )

        premium_mean = premium_shift.rolling(24, min_periods=6).mean()
        premium_std = premium_shift.rolling(24, min_periods=6).std()
        utr_mean = g["utr_hat_roll24"].shift(1).rolling(24, min_periods=6).mean()
        utr_std = g["utr_hat_roll24"].shift(1).rolling(24, min_periods=6).std()
        premium_z = (g["premium_ratio_unit"] - premium_mean) / premium_std.replace(0, np.nan)
        utr_z = (g["utr_hat_roll24"] - utr_mean) / utr_std.replace(0, np.nan)
        g["pa_z_roll24"] = premium_z - utr_z
        return g

    return groups.apply(add_group).reset_index(drop=True)


def parse_strategy_name(strategy_name: str) -> dict[str, object]:
    name = str(strategy_name)
    labels = {
        "strategy_family": "covered_call",
        "option_rule": "unknown",
        "moneyness_rule": "unknown",
        "delta_rule": "none",
        "tenor_rule": "DTE30",
        "coverage_rule": "unknown",
        "timing_rule": "static",
        "is_diagnostic_rule": False,
        "is_dynamic_rule": False,
    }
    if "IVTiming" in name:
        labels["timing_rule"] = "iv_timing"
        labels["is_dynamic_rule"] = True
    if "ATM" in name:
        labels["option_rule"] = "DTE30_ATM_unit"
        labels["moneyness_rule"] = "ATM"
    elif "OTM5" in name:
        labels["option_rule"] = "DTE30_OTM5_unit"
        labels["moneyness_rule"] = "OTM5"
    elif "Delta30" in name:
        labels["option_rule"] = "DTE30_Delta30_unit"
        labels["delta_rule"] = "Delta30"
        labels["moneyness_rule"] = "delta_target"
    elif "Delta20" in name:
        labels["option_rule"] = "DTE30_Delta20_unit"
        labels["delta_rule"] = "Delta20"
        labels["moneyness_rule"] = "delta_target"

    if "100" in name:
        labels["coverage_rule"] = "100%"
    elif "50" in name:
        labels["coverage_rule"] = "50%"
    elif labels["is_dynamic_rule"]:
        labels["coverage_rule"] = "dynamic"

    labels["is_diagnostic_rule"] = (
        labels["option_rule"] in {
            "DTE30_ATM_unit",
            "DTE30_OTM5_unit",
            "DTE30_Delta30_unit",
            "DTE30_Delta20_unit",
        }
        and not labels["is_dynamic_rule"]
    )
    return labels


def add_strategy_labels(payoff: pd.DataFrame) -> pd.DataFrame:
    out = payoff.copy()
    parsed = pd.DataFrame([parse_strategy_name(s) for s in out["strategy_name"]], index=out.index)
    for col in parsed.columns:
        out[col] = parsed[col]
    return out


def build_diagnostic_sample(payoff: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    labeled = add_strategy_labels(payoff)
    diagnostic = labeled[labeled["is_diagnostic_rule"]].copy()
    if diagnostic.empty:
        return diagnostic, labeled

    diagnostic["_coverage_distance"] = (diagnostic["coverage_ratio"] - 1.0).abs()
    diagnostic = diagnostic.sort_values(
        [
            "etf_code",
            "date",
            "option_rule",
            "_coverage_distance",
            "coverage_ratio",
            "strategy_name",
        ],
        ascending=[True, True, True, True, False, True],
    )
    diagnostic = diagnostic.drop_duplicates(["etf_code", "date", "option_rule"], keep="first")
    diagnostic = diagnostic.drop(columns=["_coverage_distance"])
    diagnostic = diagnostic.sort_values(["etf_code", "option_rule", "date"]).reset_index(drop=True)
    diagnostic = add_rolling_metrics(diagnostic, group_cols=["etf_code", "option_rule"])
    return diagnostic, labeled


def summarize_diagnostic_by_etf_option_rule(diagnostic: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (etf, option_rule), g in diagnostic.groupby(["etf_code", "option_rule"]):
        rows.append(
            {
                "etf_code": etf,
                "option_rule": option_rule,
                "observations": len(g),
                "mean_premium_ratio_unit": g["premium_ratio_unit"].mean(),
                "mean_realized_upside_truncation_unit": g["realized_upside_truncation_unit"].mean(),
                "mean_realized_cc_excess_unit": g["realized_cc_excess_unit"].mean(),
                "breach_rate": g["breach_flag"].mean(),
                "mean_breach_severity": g.loc[g["breach_flag"] == 1, "realized_upside_truncation_unit"].mean(),
                "mean_utr_hat_roll24": g["utr_hat_roll24"].mean(),
                "mean_pa_diff_roll24": g["pa_diff_roll24"].mean(),
                "median_pa_diff_roll24": g["pa_diff_roll24"].median(),
                "mean_pa_ratio_roll24": g["pa_ratio_roll24"].replace([np.inf, -np.inf], np.nan).mean(),
                "win_rate_unit": (g["realized_cc_excess_unit"] > 0).mean(),
            }
        )
    return pd.DataFrame(rows).sort_values(["option_rule", "etf_code"]).reset_index(drop=True)


def etf_comparison_fixed_option_rule(summary_diag: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "option_rule",
        "etf_code",
        "observations",
        "mean_premium_ratio_unit",
        "mean_realized_upside_truncation_unit",
        "mean_realized_cc_excess_unit",
        "breach_rate",
        "mean_pa_diff_roll24",
        "win_rate_unit",
    ]
    return summary_diag[cols].sort_values(["option_rule", "mean_realized_cc_excess_unit"], ascending=[True, False])


def option_rule_comparison_within_etf(summary_diag: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "etf_code",
        "option_rule",
        "observations",
        "mean_premium_ratio_unit",
        "mean_realized_upside_truncation_unit",
        "mean_realized_cc_excess_unit",
        "breach_rate",
        "mean_pa_diff_roll24",
        "win_rate_unit",
    ]
    return summary_diag[cols].sort_values(["etf_code", "mean_realized_cc_excess_unit"], ascending=[True, False])


def fixed_effect_test(diagnostic: pd.DataFrame, output_dir: Path) -> dict[str, Path | None]:
    reg_path = output_dir / "pa_diff_fixed_effect_regression.txt"
    corr_path = output_dir / "pa_diff_demeaned_correlation.csv"
    data = diagnostic[["realized_cc_excess_unit", "pa_diff_roll24", "etf_code", "option_rule"]].dropna().copy()
    if len(data) < 10:
        _to_csv_zh(
            pd.DataFrame([{"observations": len(data), "demeaned_corr": np.nan, "note": "insufficient_data"}]),
            corr_path,
        )
        return {"regression": None, "demeaned_correlation": corr_path}

    try:
        import statsmodels.formula.api as smf

        model = smf.ols(
            "realized_cc_excess_unit ~ pa_diff_roll24 + C(etf_code) + C(option_rule)",
            data=data,
        ).fit(cov_type="HC3")
        reg_path.write_text(str(model.summary()), encoding="utf-8")
        return {"regression": reg_path, "demeaned_correlation": None}
    except Exception as exc:
        demeaned = data.copy()
        for col in ["realized_cc_excess_unit", "pa_diff_roll24"]:
            demeaned[col] = demeaned[col] - demeaned.groupby("etf_code")[col].transform("mean")
            demeaned[col] = demeaned[col] - demeaned.groupby("option_rule")[col].transform("mean")
            demeaned[col] = demeaned[col] + data[col].mean()
        corr = demeaned["pa_diff_roll24"].corr(demeaned["realized_cc_excess_unit"])
        _to_csv_zh(
            pd.DataFrame(
                [{"observations": len(demeaned), "demeaned_corr": corr, "note": f"statsmodels_unavailable_or_failed: {exc}"}]
            ),
            corr_path,
        )
        return {"regression": None, "demeaned_correlation": corr_path}


def quality_counts(df: pd.DataFrame) -> dict[str, int]:
    counts: dict[str, int] = {}
    if "data_quality_flag" not in df.columns:
        return counts
    for value in df["data_quality_flag"].fillna(""):
        if not value:
            counts["ok"] = counts.get("ok", 0) + 1
            continue
        for part in str(value).split(";"):
            if part:
                counts[part] = counts.get(part, 0) + 1
    return counts


def summarize_by_etf_strategy(payoff: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (etf, strategy), g in payoff.groupby(["etf_code", "strategy_name"]):
        rows.append(
            {
                "etf_code": etf,
                "strategy_name": strategy,
                "observations": len(g),
                "mean_premium_ratio_unit": g["premium_ratio_unit"].mean(),
                "median_premium_ratio_unit": g["premium_ratio_unit"].median(),
                "mean_realized_upside_truncation_unit": g["realized_upside_truncation_unit"].mean(),
                "median_realized_upside_truncation_unit": g["realized_upside_truncation_unit"].median(),
                "mean_realized_cc_excess_unit": g["realized_cc_excess_unit"].mean(),
                "median_realized_cc_excess_unit": g["realized_cc_excess_unit"].median(),
                "mean_realized_cc_excess_port": g["realized_cc_excess_port"].mean(),
                "median_realized_cc_excess_port": g["realized_cc_excess_port"].median(),
                "breach_rate": g["breach_flag"].mean(),
                "win_rate_unit": (g["realized_cc_excess_unit"] > 0).mean(),
                "win_rate_port": (g["realized_cc_excess_port"] > 0).mean(),
                "mean_utr_hat_roll24": g["utr_hat_roll24"].mean(),
                "mean_pa_diff_roll24": g["pa_diff_roll24"].mean(),
                "median_pa_diff_roll24": g["pa_diff_roll24"].median(),
                "mean_pa_ratio_roll24": g["pa_ratio_roll24"].replace([np.inf, -np.inf], np.nan).mean(),
                "median_pa_ratio_roll24": g["pa_ratio_roll24"].replace([np.inf, -np.inf], np.nan).median(),
                "share_pa_diff_positive": (g["pa_diff_roll24"] > 0).mean(),
                "data_quality_summary": "; ".join(f"{k}:{v}" for k, v in quality_counts(g).items()),
            }
        )
    return pd.DataFrame(rows).sort_values(["etf_code", "strategy_name"]).reset_index(drop=True)


def _bucket_labels(series: pd.Series) -> pd.Series:
    valid = series.dropna()
    labels = pd.Series(index=series.index, dtype="object")
    if len(valid) < 6 or valid.nunique() < 3:
        labels.loc[series.notna()] = "insufficient_data"
        return labels
    try:
        labels.loc[valid.index] = pd.qcut(valid, q=3, labels=["low", "medium", "high"], duplicates="drop")
    except ValueError:
        labels.loc[valid.index] = "insufficient_data"
    return labels


def run_bucket_test(payoff: pd.DataFrame, metric: str, bucket_col_name: str) -> pd.DataFrame:
    data = payoff.copy()
    data[bucket_col_name] = pd.Series(index=data.index, dtype="object")
    for etf, g in data.groupby("etf_code"):
        if len(g[metric].dropna()) >= 18:
            data.loc[g.index, bucket_col_name] = _bucket_labels(g[metric])
    missing = data[bucket_col_name].isna()
    if missing.any():
        data.loc[missing, bucket_col_name] = _bucket_labels(data.loc[missing, metric])

    rows = []
    for bucket, g in data.dropna(subset=[bucket_col_name]).groupby(bucket_col_name):
        rows.append(
            {
                bucket_col_name: bucket,
                "observations": len(g),
                "mean_realized_cc_excess_unit": g["realized_cc_excess_unit"].mean(),
                "median_realized_cc_excess_unit": g["realized_cc_excess_unit"].median(),
                "mean_realized_cc_excess_port": g["realized_cc_excess_port"].mean(),
                "breach_rate": g["breach_flag"].mean(),
                "mean_realized_upside_truncation_unit": g["realized_upside_truncation_unit"].mean(),
            }
        )
    return pd.DataFrame(rows)


def _markdown_table(df: pd.DataFrame, max_rows: int | None = None) -> str:
    if df.empty:
        return "No rows."
    data = _localize_dataframe(df)
    if max_rows is not None:
        data = data.head(max_rows)
    data = data.replace([np.inf, -np.inf], np.nan)
    headers = list(data.columns)
    rows = []
    for _, row in data.iterrows():
        values = []
        for col in headers:
            value = row[col]
            if pd.isna(value):
                values.append("")
            elif isinstance(value, float):
                values.append(f"{value:.6g}")
            else:
                values.append(str(value))
        rows.append(values)
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    lines.extend("| " + " | ".join(values) + " |" for values in rows)
    return "\n".join(lines)


def correlation_summary(payoff: pd.DataFrame) -> pd.DataFrame:
    pairs = [
        ("pa_diff_roll24", "realized_cc_excess_unit"),
        ("pa_ratio_roll24", "realized_cc_excess_unit"),
        ("utr_hat_roll24", "realized_upside_truncation_unit"),
        ("breach_prob_hat_roll24", "breach_flag"),
        ("breach_severity_hat_roll24", "realized_upside_truncation_unit"),
    ]
    rows = []
    scopes = [("all", payoff)]
    scopes.extend((etf, g) for etf, g in payoff.groupby("etf_code"))
    for scope, data in scopes:
        for x, y in pairs:
            valid = data[[x, y]].replace([np.inf, -np.inf], np.nan).dropna()
            rows.append(
                {
                    "scope": scope,
                    "x": x,
                    "y": y,
                    "observations": len(valid),
                    "pearson": valid[x].corr(valid[y], method="pearson") if len(valid) >= 3 else np.nan,
                    "spearman": valid[x].corr(valid[y], method="spearman") if len(valid) >= 3 else np.nan,
                }
            )
    return pd.DataFrame(rows)


def save_plots(payoff: pd.DataFrame, summary: pd.DataFrame, plot_dir: Path, focus_etfs: list[str] | None = None) -> list[Path]:
    focus_etfs = focus_etfs or FOCUS_ETFS
    plot_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    for etf in focus_etfs:
        g = payoff[payoff["etf_code"] == etf]
        if g.empty:
            _warn(f"No payoff rows for ETF {etf}; skip ETF plots.")
            continue
        paths.append(_scatter_plot(g, "pa_diff_roll24", "realized_cc_excess_unit", plot_dir / f"pa_diff_vs_excess_{etf}.png", f"{etf}：PA差值与单位备兑超额收益"))
        paths.append(_scatter_plot(g, "pa_ratio_roll24", "realized_cc_excess_unit", plot_dir / f"pa_ratio_vs_excess_{etf}.png", f"{etf}：PA比例与单位备兑超额收益"))
        paths.append(_time_series_plot(g, ["pa_diff_roll24"], plot_dir / f"pa_diff_time_series_{etf}.png", f"{etf}：24期滚动PA差值时间序列"))
        paths.append(
            _time_series_plot(
                g,
                ["premium_ratio_unit", "utr_hat_roll24", "realized_cc_excess_unit"],
                plot_dir / f"payoff_components_time_series_{etf}.png",
                f"{etf}：权利金、UTR与单位备兑超额收益",
            )
        )

    if not summary.empty:
        paths.append(
            _bar_compare(
                summary,
                ["mean_premium_ratio_unit", "mean_realized_upside_truncation_unit"],
                plot_dir / "premium_vs_truncation_by_etf_strategy.png",
                "平均单位权利金比例与平均单位上行截断损失",
            )
        )
        paths.append(
            _bar_compare(
                summary,
                ["mean_realized_cc_excess_unit"],
                plot_dir / "mean_excess_by_etf_strategy.png",
                "各ETF与期权规则的平均单位备兑超额收益",
            )
        )
        paths.append(
            _bar_compare(
                summary,
                ["breach_rate"],
                plot_dir / "breach_rate_by_etf_strategy.png",
                "各ETF与期权规则的突破率",
            )
        )
    return paths


def _scatter_plot(df: pd.DataFrame, x: str, y: str, path: Path, title: str) -> Path:
    fig, ax = plt.subplots(figsize=(8, 5), dpi=150)
    for strategy, g in df.groupby("strategy_name"):
        valid = g[[x, y]].replace([np.inf, -np.inf], np.nan).dropna()
        if valid.empty:
            continue
        ax.scatter(valid[x], valid[y], s=18, alpha=0.65, label=_zh_label(strategy))
    ax.axhline(0, color="#666666", linewidth=0.8, alpha=0.7)
    ax.axvline(0, color="#666666", linewidth=0.8, alpha=0.7)
    ax.set_title(title)
    ax.set_xlabel(_zh_label(x))
    ax.set_ylabel(_zh_label(y))
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=7, frameon=False)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _time_series_plot(df: pd.DataFrame, cols: list[str], path: Path, title: str) -> Path:
    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
    for strategy, g in df.groupby("strategy_name"):
        g = g.sort_values("date")
        for col in cols:
            if col in g.columns and g[col].notna().sum() > 0:
                ax.plot(g["date"], g[col], label=f"{_zh_label(strategy)} | {_zh_label(col)}", linewidth=1.1, alpha=0.85)
    ax.axhline(0, color="#666666", linewidth=0.8, alpha=0.7)
    ax.set_title(title)
    ax.set_xlabel("日期")
    ax.set_ylabel("数值")
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=6, frameon=False, ncol=2)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _bar_compare(summary: pd.DataFrame, cols: list[str], path: Path, title: str) -> Path:
    data = summary.copy()
    data["label"] = data["etf_code"] + " | " + data["strategy_name"].map(_zh_label)
    data = data.sort_values(["etf_code", "strategy_name"])
    x = np.arange(len(data))
    width = 0.8 / max(len(cols), 1)
    fig, ax = plt.subplots(figsize=(max(10, len(data) * 0.28), 5.8), dpi=150)
    for i, col in enumerate(cols):
        ax.bar(x + (i - (len(cols) - 1) / 2) * width, data[col], width=width, label=_zh_label(col))
    ax.axhline(0, color="#666666", linewidth=0.8)
    ax.set_title(title)
    ax.set_xticks(x)
    ax.set_xticklabels(data["label"], rotation=75, ha="right", fontsize=7)
    ax.grid(axis="y", alpha=0.25)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def write_markdown_report(
    path: Path,
    diagnostics: dict,
    summary: pd.DataFrame,
    diagnostic: pd.DataFrame,
    summary_diag: pd.DataFrame,
    etf_compare: pd.DataFrame,
    option_compare: pd.DataFrame,
    bucket_pa_diff: pd.DataFrame,
    bucket_pa_ratio: pd.DataFrame,
    bucket_utr: pd.DataFrame,
    corr: pd.DataFrame,
    fe_paths: dict[str, Path | None] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    top_premium = summary.sort_values("mean_premium_ratio_unit", ascending=False).head(8)
    top_trunc = summary.sort_values("mean_realized_upside_truncation_unit", ascending=False).head(8)
    top_excess = summary.sort_values("mean_realized_cc_excess_unit", ascending=False).head(8)

    lines = [
        "# 第三层：期权收益分解与权利金充足性诊断报告",
        "",
        "## 1. 数据覆盖范围",
        f"- 原始周期拆解行数：{diagnostics.get('source_rows')}",
        f"- Full strategy sample 行数：{diagnostics.get('payoff_rows')}",
        f"- Main sample 行数：{len(diagnostic)}",
        f"- 日期范围：{diagnostics.get('date_min')} 至 {diagnostics.get('date_max')}",
        f"- 覆盖 ETF：{', '.join(diagnostics.get('covered_etfs', []))}",
        f"- 覆盖策略：{', '.join(diagnostics.get('covered_strategies', []))}",
        f"- 数据质量标记统计：{diagnostics.get('quality_counts')}",
        "",
        "## 2. 指标定义",
        "- `premium_ratio_unit = option_premium / underlying_price_open`，表示单位底仓收到的 call 权利金比例。",
        "- `realized_upside_truncation_unit = max(underlying_return - moneyness, 0)`，表示单位覆盖下事后实现的上行截断损失。",
        "- `realized_cc_excess_unit = premium_ratio_unit - realized_upside_truncation_unit`，表示单位覆盖下备兑相对 ETF 底仓的超额收益。",
        "- `realized_cc_excess_port = coverage_ratio * realized_cc_excess_unit - transaction_cost`，表示组合层面的备兑超额收益。",
        "- `utr_hat_roll12` 与 `utr_hat_roll24` 是基于历史已完成交易的上行截断风险滚动估计，计算时使用 `shift(1)`，避免未来函数。",
        "- `pa_diff_roll24 = premium_ratio_unit - utr_hat_roll24`，表示差值形式的权利金充足性，是本轮更稳健的主指标。",
        "- `pa_ratio_roll24 = premium_ratio_unit / (utr_hat_roll24 + epsilon)`，表示比例形式的权利金充足性；当 UTR 接近 0 时可能不稳定，不能单独作为策略信号。",
        "- `pa_z_roll24` 是权利金与 UTR 估计值的历史 z-score 差异，使用历史滚动输入计算。",
        "- `breach_prob_hat_roll24` 是历史 breach 概率的滚动估计。",
        "- `breach_severity_hat_roll24` 是历史 breach 后截断严重程度的滚动估计。",
        "",
        "## 3. 主分析样本说明",
        "Layer 3 的主目标是诊断 DTE30 option payoff quality，而不是评价完整策略绩效。本报告中的 DTE30 表示开仓时距离期权到期日约 30 天；当前结论只能解释 DTE30 covered call suitability，不能声称覆盖完整期权市场所有期限。",
        "",
        "主分析只保留标准化 DTE30 diagnostic option rules：",
        "",
        "- `DTE30_ATM_unit`",
        "- `DTE30_OTM5_unit`",
        "- `DTE30_Delta30_unit`",
        "- `DTE30_Delta20_unit`，如果数据允许",
        "",
        "动态择时规则、覆盖率变化和完整组合调参属于 Layer 4，不作为 Layer 3 主结论依据。同一个 ETF、同一个日期、同一个 option rule 下，如果存在不同 coverage ratio，本报告优先保留覆盖率最接近 100% 的记录，以避免单位覆盖 payoff 被重复计数。",
        "",
        "### 3.1 Main sample：DTE30 diagnostic option rules 汇总",
        _markdown_table(summary_diag),
        "",
        "### 3.2 同一 option rule 下的 ETF 对比",
        _markdown_table(etf_compare),
        "",
        "### 3.3 同一 ETF 下的 option rule 对比",
        _markdown_table(option_compare),
        "",
        "## 4. Full strategy sample 探索性附录",
        "以下结果包含此前实验过的完整策略样本，仅作为探索性附录。它混合了 moneyness、coverage、timing rule 和完整策略规则，不能直接作为 Layer 3 主结论。",
        "",
        "### 4.1 平均权利金比例较高的 ETF/策略",
        _markdown_table(top_premium),
        "",
        "### 4.2 事后上行截断损失较高的 ETF/策略",
        _markdown_table(top_trunc),
        "",
        "### 4.3 事后单位备兑超额收益较高的 ETF/策略",
        _markdown_table(top_excess),
        "",
        "## 5. DTE30 diagnostic sample 分组检验结果",
        "### 5.1 PA diff 分组",
        _markdown_table(bucket_pa_diff) if not bucket_pa_diff.empty else "No valid PA diff bucket rows.",
        "",
        "理论预期是：`pa_diff_roll24` 较高的组，后续 `realized_cc_excess_unit` 应更好。当前结果应结合样本量和极端行情谨慎解读。",
        "",
        "### 5.2 PA ratio 分组",
        _markdown_table(bucket_pa_ratio) if not bucket_pa_ratio.empty else "No valid PA ratio bucket rows.",
        "",
        "`pa_ratio_roll24` 在 UTR 估计值接近 0 时会非常不稳定，因此只能作为辅助观察，不能单独作为策略信号。",
        "",
        "### 5.3 UTR 分组",
        _markdown_table(bucket_utr) if not bucket_utr.empty else "No valid UTR bucket rows.",
        "",
        "理论预期是：`utr_hat_roll24` 较高的组，上行截断风险更高；如果权利金没有同步补偿，则备兑相对 ETF 底仓的超额收益可能更弱。",
        "",
        "## 6. 简单相关性与固定效应检验",
        _markdown_table(corr) if not corr.empty else "No valid correlation rows.",
        "",
        "相关性检验只用于研究诊断，不应被解释为稳定预测能力。当前样本仍然有限，并且包含若干特殊市场阶段。",
        "",
        f"- 固定效应回归输出：{fe_paths.get('regression') if fe_paths else None}",
        f"- 去均值相关性输出：{fe_paths.get('demeaned_correlation') if fe_paths else None}",
        "",
        "## 7. 数据质量与局限",
        "- 本模块复用已有周期级回测拆解结果，不重新进行选券或回测。",
        "- `strike`、`option_premium`、`coverage_ratio`、`underlying_return` 和 `transaction_cost` 均优先来自已有周期记录。",
        "- 关键字段缺失时会写入 `data_quality_flag`，不会静默失败。",
        "- rolling PA/UTR 指标需要历史已完成样本，因此早期样本出现 NaN 是正常现象。",
        "- 本报告定位为 payoff quality 研究诊断，不是独立交易信号，也不声称预测能力。",
        "",
        "## 8. 对 Layer 4 策略映射的启示",
        "- `pa_diff_roll24` 较高时，可以提高 covered call suitability，但它只能作为输入之一。",
        "- `utr_hat_roll24` 较高表示历史上行截断风险较高；即使 IV 较高，也不应机械提高覆盖率。",
        "- 如果 breach probability 与 breach severity 同时较高，应考虑降低覆盖率、卖更远 OTM，或缩短/调整期限。",
        "- 下一步可以将 `pa_diff_roll24`、`utr_hat_roll24`、`breach_prob_hat_roll24` 和 `breach_severity_hat_roll24` 接入透明的动态覆盖率映射规则。",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def run_layer3_pipeline(project_root: Path, focus_etfs: list[str] | None = None) -> dict[str, object]:
    project_root = project_root.resolve()
    output_dir = project_root / "outputs" / "layer3_payoff"
    plot_dir = output_dir / "plots"
    paths = Layer3Paths(
        project_root=project_root,
        input_path=project_root / "data" / "source" / "pnl_decomposition_by_roll.csv",
        output_dir=output_dir,
        plot_dir=plot_dir,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    plot_dir.mkdir(parents=True, exist_ok=True)

    print(f"loading existing backtest/trade data: {paths.input_path}")
    source = load_source_periods(paths.input_path)
    print(f"identifying available columns: {len(source.columns)} columns")
    print("building payoff decomposition")
    payoff, diagnostics = build_payoff_monthly(source, focus_etfs=focus_etfs)
    diagnostic, labeled_payoff = build_diagnostic_sample(payoff)
    print("computing realized upside truncation")
    print("computing rolling UTR estimates")
    print("computing premium adequacy metrics")

    summary = summarize_by_etf_strategy(labeled_payoff)
    summary_diag = summarize_diagnostic_by_etf_option_rule(diagnostic)
    etf_compare = etf_comparison_fixed_option_rule(summary_diag)
    option_compare = option_rule_comparison_within_etf(summary_diag)
    print("running bucket tests")
    bucket_pa_diff = run_bucket_test(diagnostic.dropna(subset=["pa_diff_roll24"]), "pa_diff_roll24", "pa_diff_bucket")
    bucket_pa_ratio = run_bucket_test(diagnostic.dropna(subset=["pa_ratio_roll24"]), "pa_ratio_roll24", "pa_ratio_bucket")
    bucket_utr = run_bucket_test(diagnostic.dropna(subset=["utr_hat_roll24"]), "utr_hat_roll24", "utr_bucket")
    corr = correlation_summary(diagnostic)
    fe_paths = fixed_effect_test(diagnostic, output_dir)

    csv_paths = {
        "monthly": output_dir / "layer3_payoff_monthly.csv",
        "dte30_diagnostic": output_dir / "layer3_dte30_diagnostic.csv",
        "summary": output_dir / "summary_by_etf_strategy.csv",
        "summary_dte30": output_dir / "summary_dte30_by_etf_option_rule.csv",
        "dte30_etf_comparison": output_dir / "dte30_etf_comparison_fixed_rule.csv",
        "dte30_option_rule_comparison": output_dir / "dte30_option_rule_comparison_within_etf.csv",
        "bucket_pa_diff": output_dir / "bucket_test_pa_diff.csv",
        "bucket_pa_ratio": output_dir / "bucket_test_pa_ratio.csv",
        "bucket_utr": output_dir / "bucket_test_utr.csv",
        "correlation": output_dir / "layer3_correlation_summary.csv",
    }
    print("saving csv files")
    _to_csv_zh(labeled_payoff, csv_paths["monthly"])
    diagnostic_cols = [
        "date",
        "close_date",
        "etf_code",
        "strategy_name",
        "option_rule",
        "strategy_family",
        "moneyness",
        "days_to_expiry",
        "premium_ratio_unit",
        "realized_upside_truncation_unit",
        "realized_cc_excess_unit",
        "utr_hat_roll24",
        "pa_diff_roll24",
        "pa_ratio_roll24",
        "breach_flag",
        "breach_prob_hat_roll24",
        "breach_severity_hat_roll24",
        "data_quality_flag",
    ]
    _to_csv_zh(diagnostic[diagnostic_cols], csv_paths["dte30_diagnostic"])
    _to_csv_zh(summary, csv_paths["summary"])
    _to_csv_zh(summary_diag, csv_paths["summary_dte30"])
    _to_csv_zh(etf_compare, csv_paths["dte30_etf_comparison"])
    _to_csv_zh(option_compare, csv_paths["dte30_option_rule_comparison"])
    _to_csv_zh(bucket_pa_diff, csv_paths["bucket_pa_diff"])
    _to_csv_zh(bucket_pa_ratio, csv_paths["bucket_pa_ratio"])
    _to_csv_zh(bucket_utr, csv_paths["bucket_utr"])
    _to_csv_zh(corr, csv_paths["correlation"])

    print("saving plots")
    plot_paths = save_plots(diagnostic, summary_diag.rename(columns={"option_rule": "strategy_name"}), plot_dir, focus_etfs=focus_etfs)
    report_path = output_dir / "layer3_payoff_report.md"
    print("writing markdown report")
    write_markdown_report(
        report_path,
        diagnostics,
        summary,
        diagnostic,
        summary_diag,
        etf_compare,
        option_compare,
        bucket_pa_diff,
        bucket_pa_ratio,
        bucket_utr,
        corr,
        fe_paths,
    )

    return {
        "paths": paths,
        "diagnostics": diagnostics,
        "csv_paths": csv_paths,
        "plot_paths": plot_paths,
        "report_path": report_path,
        "payoff": labeled_payoff,
        "diagnostic": diagnostic,
        "summary": summary,
        "summary_diagnostic": summary_diag,
        "etf_compare": etf_compare,
        "option_compare": option_compare,
        "bucket_pa_diff": bucket_pa_diff,
        "bucket_pa_ratio": bucket_pa_ratio,
        "bucket_utr": bucket_utr,
        "corr": corr,
        "fe_paths": fe_paths,
    }
