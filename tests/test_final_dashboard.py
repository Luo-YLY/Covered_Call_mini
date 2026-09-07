from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_final_dashboard_uses_raw_data_entry_instead_of_independent_open() -> None:
    page = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")

    assert "查看原始数据" in page
    assert 'href="./raw-data/"' in page
    assert "独立打开" not in page
    assert 'target="_blank"' not in page
    assert "数据与回测" in page
    assert 'data-src="./add-etf/?ui=option-date-range"' in page
    assert "一体化研究看板" in page
    assert "冻结主线" not in page
    assert "用户提交" not in page


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


def test_add_etf_page_requires_three_provider_neutral_tables_without_metadata() -> None:
    page = (ROOT / "dashboard" / "add-etf" / "index.html").read_text(encoding="utf-8")

    assert "数据来源不限" in page
    assert "ETF日行情" in page
    assert "期权合约" in page
    assert "期权日行情" in page
    assert "ETF元数据不是必填项" in page
    assert 'api("/__dashboard/submit-etf/upload"' in page
    assert 'api("/__dashboard/submit-etf/prepare"' in page
    assert 'api("/__dashboard/backtest/run"' in page
    assert 'api("/__dashboard/backtest/publish"' in page
    assert "开始日期" in page
    assert "结束日期" in page
    assert "有效认购期权" in page
    assert "可回测共同区间" in page
    assert "可闭合月度周期" in page
    assert "可实际选期权周期" in page
    assert "完整研究至少需要12个可闭合月度周期" in page
    assert "回撤曲线" in page
    assert "逐期账本与期权选择" in page
    assert "数据与计算审计" in page
    assert "date_availability" in page
    assert 'startDate.addEventListener("change", syncDateSelection)' in page
    assert "确认更新看板" in page
    assert "冻结主线" not in page
    assert "用户提交" not in page


def test_cycle_dashboard_loads_published_etfs_and_links_to_custom_window() -> None:
    page = (ROOT / "ver4" / "dashboard" / "index.html").read_text(encoding="utf-8")

    assert "自选单券回测" in page
    assert "运行并更新本页" in page
    assert "目标 Delta" in page
    assert "ATM" in page
    assert "OTM 比例" in page
    assert 'fetch("/__dashboard/submissions"' in page
    assert 'fetch("/__dashboard/backtest/published"' in page
    assert 'dashboardApi("/__dashboard/backtest/run"' in page
    assert "cycle_validation" in page
    assert "currentEtf()?.cycle_validation?.[key]" in page
    assert "!earlyCloseDailyCache.delta && !rows(earlyClosePayload().daily).length" in page
    assert "user_selected_window" in page
    assert "syncTabAvailability" in page
    assert 'new URLSearchParams(location.search).get("etf")' in page


def test_combination_dashboard_contains_dynamic_portfolio_research() -> None:
    dashboard = (ROOT / "ver3" / "dashboard" / "index.html").read_text(encoding="utf-8")
    portfolio = (ROOT / "dashboard" / "portfolio" / "index.html").read_text(encoding="utf-8")
    server = (ROOT / "scripts" / "serve_dashboard.py").read_text(encoding="utf-8")

    assert 'data-tab="custom"' in dashboard
    assert "../../dashboard/portfolio/" in dashboard
    assert "共同可用区间" in portfolio
    assert "权重合计必须为100%" in portfolio
    assert "日频MTM组合净值" in portfolio
    assert "data.daily_mtm" in portfolio
    assert "minimum_exact_option_quote_ratio" in portfolio
    assert 'api("/__dashboard/portfolio/run"' in portfolio
    assert 'api("/__dashboard/portfolio/publish"' in portfolio
    assert 'PORTFOLIO_BACKTEST_ENDPOINT = "/__dashboard/portfolio/run"' in server


def test_combination_single_sleeves_stay_compact_and_link_to_cycle_validation() -> None:
    dashboard = (ROOT / "ver3" / "dashboard" / "index.html").read_text(encoding="utf-8")
    shell = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")

    assert "renderCompactSleeves" in dashboard
    assert "完整验证独立" in dashboard
    assert "../../dashboard/?etf=" in dashboard
    assert "现金收入、逐期账本、行权明细及诊断" in dashboard
    assert "single-sleeve-frame" not in dashboard
    assert 'new URLSearchParams(location.search).get("etf")' in shell


def test_single_sleeve_parameter_atlas_supports_dynamic_surface_and_heatmap() -> None:
    dashboard = (ROOT / "ver3" / "dashboard" / "index.html").read_text(encoding="utf-8")
    shell = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    submission = (ROOT / "dashboard" / "add-etf" / "index.html").read_text(encoding="utf-8")
    server = (ROOT / "scripts" / "serve_dashboard.py").read_text(encoding="utf-8")

    assert 'dashboardJson("/__dashboard/surface/run"' in dashboard
    assert 'dashboardJson("/__dashboard/surface/publish"' in dashboard
    assert 'dashboardJson("/__dashboard/surface/published")' in dashboard
    assert "renderSurfaceHeatmap" in dashboard
    assert 'id="surfaceInteractiveChart"' in dashboard
    assert 'id="surfaceHeatmapChart"' in dashboard
    assert "5个Delta × 10档覆盖率" in dashboard
    assert "dashboard-data-prepared" in submission
    assert "dashboard-data-prepared" in shell
    assert "dashboard-data-prepared" in dashboard
    assert "dashboard-open-surface" in submission
    assert "dashboard-open-surface" in shell
    assert "dashboard-open-surface" in dashboard
    assert "上传新ETF数据" in dashboard
    assert "下一步：生成单券参数图谱" in submission
    assert 'id="surfaceEtfSelect"' in dashboard
    assert "已确认可用的ETF" in dashboard
    assert "renderSurfaceKpis" in dashboard
    assert "surfacePointLabel" in dashboard
    assert "最优参数" in dashboard
    assert "样本内${metricLabel}最优值" in dashboard
    assert "个有效周期" in dashboard
    assert "同期BuyHold" in dashboard
    assert "data-surface-etf" not in dashboard
    assert "data-etf=" not in dashboard
    assert 'SURFACE_BACKTEST_ENDPOINT = "/__dashboard/surface/run"' in server
    assert 'SURFACE_PUBLISH_ENDPOINT = "/__dashboard/surface/publish"' in server
    assert 'SURFACE_PUBLISHED_ENDPOINT = "/__dashboard/surface/published"' in server


def test_release_includes_target_delta_heatmap_assets_and_dynamic_server() -> None:
    script = (ROOT / "scripts" / "package_project_release.ps1").read_text(encoding="utf-8-sig")

    assert "target_delta_surface_contours\\figures" in script
    assert "159915_target_delta_coverage_sharpe_contours.png" in script
    assert "python scripts\\serve_dashboard.py --port 8765" in script
    assert "covered_call_research_handoff" not in script


def test_delivery_has_reproducible_environment_and_one_click_entrypoints() -> None:
    package_script = (ROOT / "scripts" / "package_project_release.ps1").read_text(encoding="utf-8-sig")
    start_script = (ROOT / "start_dashboard.ps1").read_text(encoding="utf-8-sig")
    verify_script = (ROOT / "scripts" / "verify_delivery.ps1").read_text(encoding="utf-8-sig")

    assert (ROOT / "requirements.txt").is_file()
    assert (ROOT / "requirements-collectors.txt").is_file()
    assert "scripts\\serve_dashboard.py" in start_script
    assert "python -m pytest" in verify_script
    assert '"requirements.txt"' in package_script
    assert '"start_dashboard.ps1"' in package_script


def test_dashboard_server_disables_stale_browser_cache() -> None:
    server = (ROOT / "scripts" / "serve_dashboard.py").read_text(encoding="utf-8")

    assert 'self.send_header("Cache-Control", "no-store")' in server
