from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_final_dashboard_uses_raw_data_entry_instead_of_independent_open() -> None:
    page = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")

    assert "查看原始数据" in page
    assert 'href="./raw-data/"' in page
    assert "独立打开" not in page
    assert 'target="_blank"' not in page
    assert "添加ETF" in page
    assert 'data-src="./add-etf/"' in page


def test_raw_data_catalog_uses_relative_local_links() -> None:
    page = (ROOT / "dashboard" / "raw-data" / "index.html").read_text(encoding="utf-8")

    assert 'const ROOT = "../../";' in page
    assert "http://" not in page
    assert "https://" not in page
    assert "data/raw/etf_prices.csv" in page
    assert "outputs/ver4_0_single_etf_cycle_cashflow" in page
    assert 'href="../"' in page
    assert "download" not in page
    assert "在文件资源管理器中查看" in page
    assert 'fetch("/__dashboard/open-in-explorer"' in page


def test_add_etf_page_requires_three_tushare_raw_tables_without_metadata() -> None:
    page = (ROOT / "dashboard" / "add-etf" / "index.html").read_text(encoding="utf-8")

    assert "Tushare fund_daily" in page
    assert "Tushare opt_basic" in page
    assert "Tushare opt_daily" in page
    assert "ETF元数据不是必填项" in page
    assert 'fetch("/__dashboard/submit-etf/upload"' in page
    assert 'fetch("/__dashboard/submit-etf/prepare"' in page
