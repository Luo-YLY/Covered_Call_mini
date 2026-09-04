"""Export clean standalone figures from Ver4 dashboard data.

The figures deliberately contain no dashboard chrome.  They are intended for
review in chat or direct placement into a research deck, not for the DOCX
report.
"""

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "outputs" / "ver4_0_single_etf_cycle_cashflow"
DELTA = ROOT / "outputs" / "ver4_1_delta_buyback" / "ver4_1_delta_buyback_cycle_ledger.csv"
TP80 = ROOT / "outputs" / "ver4_2_tp80_buyback" / "ver4_2_tp80_buyback_cycle_ledger.csv"
OUT = ROOT / "outputs" / "ver4_chart_selections_510300_D40"

ETF = 510300
ATM = "ATM_Q100"
D40 = "D40_Q100"
PRIMARY = D40
PRIMARY_LABEL = "D40 / Q100"

NAVY = "#183A5A"
BLUE = "#0B57D0"
TEAL = "#167A59"
RED = "#BE4A4A"
GOLD = "#B78642"
SLATE = "#758797"
GRID = "#D8E1E8"
MUTED = "#647688"
INK = "#263445"
PALE_BLUE = "#EAF2FB"
PALE_GREEN = "#EAF6EF"
PALE_RED = "#FBECEE"


def font_setup():
    mpl.rcParams.update({
        "font.sans-serif": ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "axes.titleweight": "bold",
        "axes.titlecolor": NAVY,
        "axes.labelcolor": "#40505F",
        "xtick.color": "#5D6C79",
        "ytick.color": "#5D6C79",
        "font.size": 10,
        "figure.dpi": 180,
        "savefig.dpi": 220,
        "savefig.facecolor": "white",
    })


def style_axis(ax):
    ax.set_facecolor("white")
    ax.grid(axis="y", color=GRID, linewidth=0.75, alpha=0.9)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.spines["bottom"].set_color("#AAB7C1")
    ax.tick_params(axis="y", length=0)
    ax.tick_params(axis="x", length=0)


def subtitle(ax, text):
    # Keep figures presentation-clean; the explanatory subtitle is carried by
    # the chat caption rather than competing with the chart title.
    ax.title.set_y(1.05)


def percent(value, digits=1):
    return f"{value * 100:.{digits}f}%"


def percent_ticks(ax):
    ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda y, _: f"{y:.0f}%"))


def save(fig, filename):
    fig.tight_layout(pad=1.2, rect=(0, 0, 1, 0.96))
    fig.savefig(OUT / filename, bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)


def ledger(etf=ETF, strategy=PRIMARY):
    path = BASE / str(etf) / "period" / "ver4_0_cycle_ledger.csv"
    out = pd.read_csv(path)
    out = out[out["strategy_name"].eq(strategy)].copy()
    out["rebalance_date"] = pd.to_datetime(out["rebalance_date"])
    out["period_end_date"] = pd.to_datetime(out["period_end_date"])
    return out.sort_values("rebalance_date").reset_index(drop=True)


def mark_924(df):
    return df["rebalance_date"].eq(pd.Timestamp("2024-09-25"))


def chart_cashflow_bars(df):
    fig, ax = plt.subplots(figsize=(11.4, 4.7))
    x = np.arange(len(df))
    premium = df["gross_premium_yield"].to_numpy() * 100
    net = df["net_option_yield"].to_numpy() * 100
    ax.bar(x - 0.19, premium, width=0.36, color=BLUE, label="总权利金（含开仓内在价值）")
    ax.bar(x + 0.19, net, width=0.36, color=np.where(net >= 0, TEAL, RED), label="最终净期权收益")
    ax.axhline(0, color="#8A98A5", linewidth=0.9)
    style_axis(ax)
    ax.set_title(f"现金收入 | 510300 ETF，{PRIMARY_LABEL}", loc="left", fontsize=15)
    subtitle(ax, "")
    ax.set_ylabel("收益率")
    percent_ticks(ax)
    ticks = np.arange(0, len(df), 5)
    ax.set_xticks(ticks, [d.strftime("%Y-%m") for d in df.loc[ticks, "rebalance_date"]])
    ax.legend(loc="upper left", frameon=False, ncol=2, bbox_to_anchor=(0, -0.18))
    bad = np.argmin(net)
    ax.annotate("2024-09 强上涨\n上涨让渡最显著", xy=(bad + 0.19, net[bad]), xytext=(bad - 7, net[bad] - 4.2),
                arrowprops=dict(arrowstyle="-", color=GOLD, lw=1.2), color=GOLD, fontsize=9, ha="right")
    save(fig, "01_现金收入_逐期权利金与净期权收益_510300_D40.png")


def chart_cashflow_scatter(df):
    fig, ax = plt.subplots(figsize=(8.6, 5.3))
    assigned = df["assignment_flag"].astype(bool)
    ax.scatter(df.loc[~assigned, "gross_premium_yield"] * 100, df.loc[~assigned, "net_option_yield"] * 100,
               s=48, c=TEAL, alpha=0.86, label="未行权")
    ax.scatter(df.loc[assigned, "gross_premium_yield"] * 100, df.loc[assigned, "net_option_yield"] * 100,
               s=55, marker="s", c=RED, alpha=0.86, label="发生行权")
    ax.axhline(0, color="#8A98A5", linewidth=0.9)
    style_axis(ax)
    ax.set_title("现金收入的误读校正 | 总权利金不等于最终净收益", loc="left", fontsize=14)
    subtitle(ax, "")
    ax.set_xlabel("开仓收到的总权利金")
    ax.set_ylabel("最终净期权收益")
    percent_ticks(ax)
    ax.xaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda x, _: f"{x:.0f}%"))
    row = df.loc[mark_924(df)].iloc[0]
    ax.annotate("2024-09 强上涨", xy=(row.gross_premium_yield * 100, row.net_option_yield * 100),
                xytext=(row.gross_premium_yield * 100 + 0.5, row.net_option_yield * 100 - 2.5),
                arrowprops=dict(arrowstyle="-", color=GOLD, lw=1.2), color=GOLD, fontsize=9)
    ax.legend(frameon=False, loc="upper left")
    save(fig, "02_现金收入_总权利金与最终净期权收益_510300_D40.png")


def chart_extreme_cycle_waterfall(df):
    row = df.loc[mark_924(df)].iloc[0]
    components = [
        ("ETF\n当期收益", row.etf_period_return * 100, SLATE),
        ("总权利金", row.gross_premium_yield * 100, BLUE),
        ("行权截断", -row.exercise_or_close_cost_yield * 100, RED),
        ("交易摩擦", -row.transaction_cost_yield * 100, RED),
    ]
    values = [x[1] for x in components]
    starts = np.cumsum([0] + values[:-1]).tolist()
    fig, ax = plt.subplots(figsize=(8.8, 5.1))
    for i, ((label, value, color), start) in enumerate(zip(components, starts)):
        lower = min(start, start + value)
        ax.bar(i, abs(value), bottom=lower, color=color, width=0.58)
        ax.text(i, lower + abs(value) / 2, f"{value:+.2f}%", ha="center", va="center", color="white", fontsize=10, fontweight="bold")
        if i < len(components) - 1:
            ax.plot([i + 0.3, i + 0.7], [start + value, start + value], color="#9AA9B4", lw=1, ls="--")
    total = row.covered_call_period_return * 100
    ax.bar(4, total, color=NAVY, width=0.58)
    ax.text(4, total / 2, f"{total:+.2f}%", ha="center", va="center", color="white", fontsize=10, fontweight="bold")
    ax.axhline(0, color="#8A98A5", linewidth=0.9)
    style_axis(ax)
    ax.set_xticks(range(5), [x[0] for x in components] + ["完整策略\n当期收益"])
    ax.set_ylabel("收益率")
    percent_ticks(ax)
    ax.set_title("逐期账本 | 2024-09-25 至 2024-10-23 的收益拆解", loc="left", fontsize=14)
    subtitle(ax, "")
    save(fig, "03_逐期账本_924强上涨周期收益拆解_510300_D40.png")


def chart_selected_cycle_waterfall(df, date, filename, title):
    row = df.loc[df["rebalance_date"].eq(pd.Timestamp(date))].iloc[0]
    components = [
        ("ETF\n当期收益", row.etf_period_return * 100, SLATE),
        ("总权利金", row.gross_premium_yield * 100, BLUE),
        ("行权截断", -row.exercise_or_close_cost_yield * 100, RED),
        ("交易摩擦", -row.transaction_cost_yield * 100, RED),
    ]
    values = [item[1] for item in components]
    starts = np.cumsum([0] + values[:-1]).tolist()
    total = row.covered_call_period_return * 100
    candidates = [0, total] + starts + [start + value for start, value in zip(starts, values)]
    ymin = min(candidates) - 1.0
    ymax = max(candidates) + 1.0

    fig, ax = plt.subplots(figsize=(9.0, 5.15))
    for i, ((label, value, color), start) in enumerate(zip(components, starts)):
        lower = min(start, start + value)
        ax.bar(i, abs(value), bottom=lower, color=color, width=0.58)
        text_color = "white" if abs(value) > 0.7 else INK
        ax.text(i, lower + abs(value) / 2, f"{value:+.2f}%", ha="center", va="center", color=text_color, fontsize=10, fontweight="bold")
        if i < len(components) - 1:
            ax.plot([i + 0.3, i + 0.7], [start + value, start + value], color="#9AA9B4", lw=1, ls="--")
    ax.bar(4, total, color=NAVY, width=0.58)
    ax.text(4, total / 2, f"{total:+.2f}%", ha="center", va="center", color="white", fontsize=10, fontweight="bold")
    ax.axhline(0, color="#8A98A5", linewidth=0.9)
    style_axis(ax)
    ax.set_ylim(ymin, ymax)
    ax.set_xticks(range(5), [x[0] for x in components] + ["完整策略\n当期收益"])
    ax.set_ylabel("收益率")
    percent_ticks(ax)
    ax.set_title(title, loc="left", fontsize=14)
    subtitle(ax, "")
    save(fig, filename)


def chart_postdiag_vrp(df):
    fig, ax = plt.subplots(figsize=(8.6, 5.3))
    x = df["ex_post_variance_risk_premium"] * 10000
    y = df["net_option_yield"] * 100
    finite = np.isfinite(x) & np.isfinite(y)
    event = mark_924(df) & finite
    normal = (~mark_924(df)) & finite
    ax.scatter(x[normal], y[normal], s=45, c=SLATE, alpha=0.75)
    ax.scatter(x[event], y[event], s=72, c=GOLD, edgecolor="white", linewidth=1.2, zorder=3)
    ax.axvline(0, color="#8A98A5", lw=0.9)
    ax.axhline(0, color="#8A98A5", lw=0.9)
    style_axis(ax)
    ax.set_title("事后诊断 | VRP 与最终净期权收益", loc="left", fontsize=14)
    subtitle(ax, "")
    ax.set_xlabel("事后 VRP（IV² - 持有期实现方差，方差点）")
    ax.set_ylabel("最终净期权收益")
    percent_ticks(ax)
    r = np.corrcoef(x[normal], y[normal])[0, 1]
    ax.text(0.02, 0.04, f"剔除 2024-09 极端上涨后的 Pearson r = {r:.2f}", transform=ax.transAxes, color=MUTED, fontsize=9)
    ax.annotate("2024-09 强上涨", xy=(x[event].iloc[0], y[event].iloc[0]), xytext=(-1050, -9),
                arrowprops=dict(arrowstyle="-", color=GOLD), color=GOLD, fontsize=9)
    save(fig, "04_事后诊断_VRP与最终净期权收益_510300_D40.png")


def chart_upside_tradeoff(df):
    fig, ax = plt.subplots(figsize=(8.7, 5.35))
    x = df["etf_period_return"] * 100
    y = df["relative_to_buyhold_return"] * 100
    assigned = df["assignment_flag"].astype(bool)
    ax.axvspan(0, 3, color=PALE_BLUE, alpha=0.75)
    ax.axvspan(3, max(x.max() + 1, 6), color=PALE_RED, alpha=0.7)
    ax.scatter(x[~assigned], y[~assigned], s=48, c=TEAL, alpha=0.85, label="未行权")
    ax.scatter(x[assigned], y[assigned], s=54, marker="s", c=RED, alpha=0.9, label="发生行权")
    ax.axhline(0, color="#8A98A5", linewidth=0.9)
    ax.axvline(0, color="#8A98A5", linewidth=0.9)
    style_axis(ax)
    ax.set_title("上涨让渡 | ETF当期涨跌与备兑相对裸持贡献", loc="left", fontsize=14)
    subtitle(ax, "")
    ax.set_xlabel("ETF 当期收益")
    ax.set_ylabel("备兑相对裸持贡献（= 最终净期权收益）")
    percent_ticks(ax)
    ax.xaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax.text(1.5, ax.get_ylim()[1] * 0.88, "温和上涨", ha="center", color=BLUE, fontsize=9)
    ax.text((max(x.max(), 4) + 3) / 2, ax.get_ylim()[1] * 0.88, "强上涨", ha="center", color=RED, fontsize=9)
    ax.legend(frameon=False, loc="lower left")
    save(fig, "05_上涨让渡_ETF收益与相对裸持贡献_510300_D40.png")


def chart_path_upside(df):
    fig, ax = plt.subplots(figsize=(8.6, 5.3))
    x = df["holding_max_upside_return"] * 100
    y = df["net_option_yield"] * 100
    assigned = df["assignment_flag"].astype(bool)
    ax.scatter(x[~assigned], y[~assigned], s=48, c=TEAL, alpha=0.85, label="未行权")
    ax.scatter(x[assigned], y[assigned], s=54, marker="s", c=RED, alpha=0.9, label="发生行权")
    ax.axhline(0, color="#8A98A5", lw=0.9)
    style_axis(ax)
    ax.set_title("持有期路径 | 最大上涨与最终净期权收益", loc="left", fontsize=14)
    subtitle(ax, "")
    ax.set_xlabel("持有期最大上涨")
    ax.set_ylabel("最终净期权收益")
    percent_ticks(ax)
    ax.xaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    rho = pd.Series(x).corr(pd.Series(y), method="spearman")
    ax.text(0.02, 0.04, f"Spearman 相关系数：{rho:.2f}", transform=ax.transAxes, color=MUTED, fontsize=9)
    ax.legend(frameon=False, loc="lower left")
    save(fig, "06_持有期路径_最大上涨与净期权收益_510300_D40.png")


def chart_regime_bars():
    path = BASE / str(ETF) / "regime" / "ver4_0_cycle_regime_attribution.csv"
    df = pd.read_csv(path)
    df = df[df["strategy_name"].eq(PRIMARY)].copy()
    order = ["下跌周期", "震荡周期", "上涨周期", "强上涨周期"]
    df["market_regime"] = pd.Categorical(df["market_regime"], categories=order, ordered=True)
    df = df.sort_values("market_regime")
    values = df["net_option_yield_mean"] * 100
    colors = [TEAL if value >= 0 else RED for value in values]
    fig, ax = plt.subplots(figsize=(8.6, 4.9))
    bars = ax.bar(df["market_regime"].str.replace("周期", ""), values, color=colors, width=0.58)
    ax.axhline(0, color="#8A98A5", lw=0.9)
    style_axis(ax)
    ax.set_title("市场情景 | 不同ETF环境下的期权腿结果", loc="left", fontsize=14)
    subtitle(ax, "")
    ax.set_ylabel("平均最终净期权收益")
    percent_ticks(ax)
    for bar, value, count in zip(bars, values, df["cycle_count"]):
        va = "bottom" if value >= 0 else "top"
        y = value + (0.25 if value >= 0 else -0.25)
        ax.text(bar.get_x() + bar.get_width() / 2, y, f"{value:.2f}%\nn={int(count)}", ha="center", va=va, fontsize=9, color=INK)
    save(fig, "07_市场情景_平均净期权收益_510300_D40.png")


def chart_timing_signal(df):
    fig, ax = plt.subplots(figsize=(8.7, 5.35))
    x = df["entry_iv_rv20_spread"] * 100
    y = df["net_option_yield"] * 100
    assigned = df["assignment_flag"].astype(bool)
    ax.scatter(x[~assigned], y[~assigned], s=48, c=TEAL, alpha=0.85, label="未行权")
    ax.scatter(x[assigned], y[assigned], s=54, marker="s", c=RED, alpha=0.9, label="发生行权")
    ax.axvline(0, color="#8A98A5", lw=0.9)
    ax.axhline(0, color="#8A98A5", lw=0.9)
    style_axis(ax)
    ax.set_title("择时分析 | 开仓 IV-RV 与最终净期权收益", loc="left", fontsize=14)
    subtitle(ax, "")
    ax.set_xlabel("开仓 IV - 开仓前20日 RV")
    ax.set_ylabel("最终净期权收益")
    percent_ticks(ax)
    ax.xaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    rho = pd.Series(x).corr(pd.Series(y), method="spearman")
    ax.text(0.02, 0.04, f"Spearman 相关系数：{rho:.2f}", transform=ax.transAxes, color=MUTED, fontsize=9)
    ax.legend(frameon=False, loc="lower left")
    save(fig, "08_择时分析_开仓IVRV与净期权收益_510300_D40.png")


def earlyclose_rows(path, rule, parameter, etf=ETF, strategy=PRIMARY):
    df = pd.read_csv(path)
    df = df[(df["etf_code"].eq(etf)) & (df["strategy_name"].eq(strategy)) &
            (df["early_close_rule"].eq(rule)) & (np.isclose(df["early_close_parameter"], parameter))].copy()
    df["rebalance_date"] = pd.to_datetime(df["rebalance_date"])
    return df.sort_values("rebalance_date").reset_index(drop=True)


def chart_earlyclose_periods():
    df = earlyclose_rows(DELTA, "delta", 0.80)
    x = np.arange(len(df))
    baseline = df["baseline_net_option_yield"] * 100
    overlay = df["net_option_yield"] * 100
    fig, ax = plt.subplots(figsize=(11.4, 4.8))
    for i, triggered in enumerate(df["buyback_triggered"]):
        if triggered:
            improved = df.loc[i, "delta_buyback_strategy_change"] >= 0
            ax.axvspan(i - 0.49, i + 0.49, color=PALE_GREEN if improved else PALE_RED, alpha=0.75, zorder=0)
    ax.bar(x - 0.18, baseline, width=0.34, color=SLATE, label="原始备兑")
    ax.bar(x + 0.18, overlay, width=0.34, color=NAVY, label="Delta ≥ 0.80 买回")
    ax.axhline(0, color="#8A98A5", lw=0.9)
    style_axis(ax)
    ax.set_title("提前平仓 | 原始备兑 vs. Delta 买回的逐期净期权收益", loc="left", fontsize=14)
    subtitle(ax, "")
    ax.set_ylabel("最终净期权收益")
    percent_ticks(ax)
    ticks = np.arange(0, len(df), 5)
    ax.set_xticks(ticks, [d.strftime("%Y-%m") for d in df.loc[ticks, "rebalance_date"]])
    ax.legend(frameon=False, ncol=2, loc="upper left", bbox_to_anchor=(0, -0.18))
    save(fig, "09_提前平仓_Delta080逐期净期权收益对比_510300_D40.png")


def chart_earlyclose_cross_etf():
    delta = pd.read_csv(DELTA)
    tp80 = pd.read_csv(TP80)
    etfs = [159915, 510050, 510300, 510500, 588000]
    def aggregate(data, rule):
        out = data[(data["strategy_name"].eq(PRIMARY)) & data["early_close_rule"].eq(rule) & np.isclose(data["early_close_parameter"], 0.8)].copy()
        return out.groupby("etf_code", as_index=True)["delta_buyback_strategy_change"].sum().reindex(etfs) * 100
    delta_y = aggregate(delta, "delta")
    tp_y = aggregate(tp80, "tp80")
    labels = ["159915", "510050", "510300", "510500", "588000"]
    x = np.arange(len(etfs))
    fig, ax = plt.subplots(figsize=(9.3, 5.1))
    ax.bar(x - 0.19, delta_y.values, width=0.36, color=NAVY, label="Delta ≥ 0.80 买回")
    ax.bar(x + 0.19, tp_y.values, width=0.36, color=GOLD, label="TP80 买回")
    ax.axhline(0, color="#8A98A5", lw=0.9)
    style_axis(ax)
    ax.set_title("提前平仓 | 各ETF D40 / Q100 的完整策略变化", loc="left", fontsize=14)
    subtitle(ax, "")
    ax.set_ylabel("完整策略变化（百分点）")
    ax.set_xticks(x, labels)
    ax.legend(frameon=False, ncol=2, loc="upper left")
    for xs, values in [(x - 0.19, delta_y.values), (x + 0.19, tp_y.values)]:
        for xx, value in zip(xs, values):
            ax.text(xx, value + (1.4 if value >= 0 else -1.4), f"{value:+.1f}", ha="center", va="bottom" if value >= 0 else "top", fontsize=8.5, color=INK)
    save(fig, "10_提前平仓_Delta与TP80跨ETF比较_D40Q100.png")


def contact_sheet():
    files = sorted(path for path in OUT.glob("*.png") if path.name[:2].isdigit() and path.name[:2] != "00")
    images = [Image.open(path).convert("RGB") for path in files]
    thumb_w = 640
    thumbs = []
    for image, path in zip(images, files):
        ratio = thumb_w / image.width
        thumb = image.resize((thumb_w, int(image.height * ratio)))
        thumbs.append((thumb, path.stem))
    rows, cols, gap, title_h = 5, 2, 24, 40
    row_heights = [max(thumbs[r * cols + c][0].height for c in range(cols)) for r in range(rows)]
    canvas = Image.new("RGB", (cols * thumb_w + (cols + 1) * gap, sum(row_heights) + (rows + 1) * gap + rows * title_h), "#F5F8FB")
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 19)
    except OSError:
        font = ImageFont.load_default()
    y = gap
    for r in range(rows):
        x = gap
        for c in range(cols):
            thumb, name = thumbs[r * cols + c]
            canvas.paste(thumb, (x, y))
            draw.text((x, y + thumb.height + 8), name, fill="#183A5A", font=font)
            x += thumb_w + gap
        y += row_heights[r] + title_h + gap
    canvas.save(OUT / "00_图表总览.png")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    font_setup()
    primary = ledger(strategy=PRIMARY)
    chart_cashflow_bars(primary)
    chart_cashflow_scatter(primary)
    chart_extreme_cycle_waterfall(primary)
    chart_selected_cycle_waterfall(
        primary,
        "2023-09-27",
        "11_逐期账本_下跌缓冲周期_20230927_510300_D40.png",
        "逐期账本 | 下跌缓冲：ETF -5.53%，完整策略 -3.87%",
    )
    chart_selected_cycle_waterfall(
        primary,
        "2022-12-28",
        "12_逐期账本_上涨让渡周期_20221228_510300_D40.png",
        "逐期账本 | 上涨让渡：ETF +6.89%，完整策略 +1.37%",
    )
    chart_postdiag_vrp(primary)
    chart_upside_tradeoff(primary)
    chart_path_upside(primary)
    chart_regime_bars()
    chart_timing_signal(primary)
    chart_earlyclose_periods()
    chart_earlyclose_cross_etf()
    contact_sheet()
    print(OUT)


if __name__ == "__main__":
    main()
