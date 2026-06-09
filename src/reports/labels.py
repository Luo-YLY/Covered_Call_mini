from __future__ import annotations

STRATEGY_LABELS = {
    "S0_BuyHold": "买入持有 (BuyHold)",
    "S1_ATM_100_Monthly": "ATM全覆盖月度备兑 (ATM 100%)",
    "S2_Delta30_100_Monthly": "30Delta全覆盖月度备兑 (30Delta 100%)",
    "S3_Delta30_50_Monthly": "30Delta半覆盖月度备兑 (30Delta 50%)",
    "S4_OTM5_100_Monthly": "虚值5%全覆盖月度备兑 (OTM5 100%)",
    "S5_IVTiming_ATM_Monthly": "IV择时ATM月度备兑 (IV Timing ATM)",
    "S6_IVTiming_OTM5_Monthly": "IV择时OTM5月度备兑 (IV Timing OTM5)",
    "S7_IVStyleRule_v1": "IV风格规则v1 (IV Style Rule v1)",
    "S8_IVStyleRule_Close_v1": "IV风格规则+提前平仓v1 (IV Style Close v1)",
}

VALUE_LABELS = {
    "buy_hold": "买入持有 (BuyHold)",
    "selected": "已选中期权 (Selected)",
    "no_chain_on_trade_date": "交易日无期权链 (No Chain on Trade Date)",
    "no_contract_in_dte_window": "到期窗口内无合约 (No Contract in DTE Window)",
    "no_contract_after_liquidity_filters": "流动性过滤后无合约 (No Contract after Liquidity Filters)",
    "delta_unavailable_for_delta30": "缺少Delta，30Delta不可用 (Delta Unavailable)",
    "delta_missing": "缺少Delta (Delta Missing)",
    "high_iv_sell": "高IV卖出 (High IV Sell)",
    "high_iv_skip": "高IV跳过 (High IV Skip)",
    "normal_iv_sell": "正常IV卖出 (Normal IV Sell)",
    "normal_iv_skip": "正常IV跳过 (Normal IV Skip)",
    "low_iv_sell": "低IV卖出 (Low IV Sell)",
    "low_iv_skip": "低IV跳过 (Low IV Skip)",
    "ultra_low_iv_skip": "极低IV跳过 (Ultra Low IV Skip)",
    "invalid_iv_signal_sell": "IV信号无效卖出 (Invalid IV Signal Sell)",
    "invalid_iv_signal_skip": "IV信号无效跳过 (Invalid IV Signal Skip)",
    "warmup_invalid_sell": "IV预热期卖出 (Warm-up Invalid Sell)",
    "warmup_invalid_skip": "IV预热期跳过 (Warm-up Invalid Skip)",
    "data_invalid_sell": "IV数据无效卖出 (Data Invalid Sell)",
    "data_invalid_skip": "IV数据无效跳过 (Data Invalid Skip)",
    "not_used": "未使用 (Not Used)",
    "close": "收盘价 (Close)",
    "mid": "买卖中间价 (Mid)",
    "none": "无 (None)",
}


def label_strategy(strategy: object) -> str:
    return STRATEGY_LABELS.get(str(strategy), str(strategy))


def label_value(value: object) -> object:
    if value is None:
        return value
    return VALUE_LABELS.get(str(value), STRATEGY_LABELS.get(str(value), value))
