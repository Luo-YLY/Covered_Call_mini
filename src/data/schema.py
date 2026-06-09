from __future__ import annotations

ETF_REQUIRED_COLUMNS = {
    "date",
    "etf_code",
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
    "amount",
}

OPTION_REQUIRED_COLUMNS = {
    "trade_date",
    "option_code",
    "underlying_etf",
    "option_type",
    "expiry",
    "strike",
    "close",
}

OPTION_OPTIONAL_COLUMNS = {
    "bid",
    "ask",
    "volume",
    "open_interest",
    "amount",
    "implied_vol",
    "delta",
    "gamma",
    "theta",
    "vega",
}

METADATA_COLUMNS = {
    "etf_code",
    "etf_name",
    "index_name",
    "fund_company",
    "style_bucket",
    "expense_ratio",
    "inception_date",
}
