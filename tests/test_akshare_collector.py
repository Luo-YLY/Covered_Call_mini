from pathlib import Path

import pandas as pd

from scripts.collect_akshare_etf_inputs import (
    CONTRACT_PATTERN,
    _fourth_wednesday,
    _normalize_etf_history,
)


def test_contract_pattern_and_fourth_wednesday() -> None:
    parsed = CONTRACT_PATTERN.fullmatch("588080C2407M00800")

    assert parsed is not None
    assert parsed.group("underlying") == "588080"
    assert parsed.group("option_type") == "C"
    assert float(parsed.group("strike")) / 1000 == 0.8
    assert _fourth_wednesday("2407") == pd.Timestamp("2024-07-24")


def test_normalize_etf_history_uses_provider_neutral_columns(tmp_path: Path) -> None:
    raw = pd.DataFrame(
        [["2024-05-06", 0.70, 0.72, 0.73, 0.69, 1000, 720000]]
    )

    result = _normalize_etf_history(raw, "588080")

    assert result.loc[0, "etf_code"] == "588080"
    assert result.loc[0, "trade_date"] == pd.Timestamp("2024-05-06")
    assert result.loc[0, "close"] == 0.72
    assert result.loc[0, "volume"] == 1000
