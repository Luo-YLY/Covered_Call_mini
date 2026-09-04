from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_final_dashboard_uses_raw_data_entry_instead_of_independent_open() -> None:
    page = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")

    assert "查看原始数据" in page
    assert 'href="./raw-data/"' in page
    assert "独立打开" not in page
    assert 'target="_blank"' not in page


def test_raw_data_catalog_uses_relative_local_links() -> None:
    page = (ROOT / "dashboard" / "raw-data" / "index.html").read_text(encoding="utf-8")

    assert 'const ROOT = "../../";' in page
    assert "http://" not in page
    assert "https://" not in page
    assert "data/raw/etf_prices.csv" in page
    assert "outputs/ver4_0_single_etf_cycle_cashflow" in page
    assert 'href="../"' in page
