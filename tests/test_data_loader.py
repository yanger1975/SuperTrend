import os
import pandas as pd
import pytest
from src.data_loader import DataLoader

def test_data_loader_caching_and_cleaning():
    db_path = "test_loader_market_data.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    try:
        loader = DataLoader(db_path=db_path)

        # 1. 測試資料清洗與校驗 (特別是 High 比 Close 還小的異常資料)
        idx = pd.to_datetime(["2023-01-01", "2023-01-02"])
        bad_df = pd.DataFrame({
            "Open": [100.0, 101.0],
            "High": [95.0, 103.0], # 第一筆的 High 95 異常小於 Close 101
            "Low": [99.0, 105.0],  # 第二筆的 Low 105 異常大於 Close 102
            "Close": [101.0, 102.0],
            "Volume": [1000.0, 1100.0]
        }, index=idx)

        cleaned = loader.validate_and_clean_data(bad_df)
        assert cleaned["High"].iloc[0] == 101.0 # 應自動修正為 Close 的 101.0
        assert cleaned["Low"].iloc[1] == 101.0  # 應自動修正為 Open 的 101.0

        # 2. 測試完整 fetch_data (會向 yfinance 下載並存入 SQLite)
        df = loader.fetch_data("SPY", start_date="2023-01-01", end_date="2023-01-08", interval="1d")
        assert not df.empty
        assert "Close" in df.columns

        # 3. 測試從快取直接讀取 (不透過網路)
        df_cached = loader.fetch_data("SPY", start_date="2023-01-01", end_date="2023-01-08", interval="1d", refresh=False)
        assert len(df_cached) == len(df)

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)

def test_hourly_data_limit_730_days():
    db_path = "test_loader_hourly_limit.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    try:
        loader = DataLoader(db_path=db_path)
        # 傳入超過 730 天的起始日期 (如 2018-01-01 至 2024-06-01)
        # loader 應自動將起始日期限制在 730 天內，並正常調用不報錯
        start_too_old = "2018-01-01"
        end_date = "2024-06-01"

        # 計算預期限制後的起始日期 (2024-06-01 - 730 days = 2022-06-02)
        end_dt = pd.to_datetime(end_date)
        capped_start = (end_dt - pd.Timedelta(days=730)).strftime("%Y-%m-%d")

        # 手動寫入涵蓋 capped_start 至 end_date 的資料至 DB 快取
        idx = pd.to_datetime(["2022-06-02 09:30:00", "2024-06-01 09:30:00"])
        mock_df = pd.DataFrame({
            "Open": [100.0, 101.0],
            "High": [102.0, 103.0],
            "Low": [99.0, 100.0],
            "Close": [101.0, 102.0],
            "Volume": [1000.0, 1100.0]
        }, index=idx)
        loader.storage.upsert_prices(mock_df, "SPY", "1h")

        # query fetch_data without refresh
        res = loader.fetch_data("SPY", start_date=start_too_old, end_date=end_date, interval="1h", refresh=False)
        assert not res.empty
        assert res.index[0] >= pd.to_datetime(capped_start)
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)

def test_get_latest_dividend_date():
    loader = DataLoader(db_path="test_div_loader.db")
    try:
        # 測試 0050.TW 回傳有效日期
        div_dt = loader.get_latest_dividend_date("0050.TW")
        assert div_dt is not None
        assert isinstance(div_dt, pd.Timestamp)
        assert div_dt >= pd.Timestamp("2024-01-01")

        # 測試異常代碼回傳 None 且不崩潰
        none_dt = loader.get_latest_dividend_date("NON_EXISTENT_TICKER_12345")
        assert none_dt is None
    finally:
        if os.path.exists("test_div_loader.db"):
            os.remove("test_div_loader.db")

def test_patch_twse_data_if_needed(monkeypatch):
    loader = DataLoader(db_path="test_patch_loader.db")
    try:
        # 建立模擬 yfinance 落後至 2026-10-14 的 DataFrame
        dates = pd.to_datetime(["2026-10-12", "2026-10-13", "2026-10-14"])
        mock_df = pd.DataFrame({
            "Open": [114.2, 112.55, 113.0],
            "High": [114.95, 113.2, 113.75],
            "Low": [113.4, 111.9, 112.75],
            "Close": [114.8, 112.4, 113.0],
            "Volume": [106348658.0, 242070746.0, 64109641.0]
        }, index=dates)

        # Mock TwseScraper 快照包含 2026-10-15 最新數據
        from src.scrapers.twse_scraper import TwseScraper
        def mock_fetch_daily_snapshot(self, force_refresh=False):
            return {
                "0050": {
                    "Code": "0050",
                    "Name": "元大台灣50",
                    "Open": 110.15,
                    "High": 110.15,
                    "Low": 108.55,
                    "Close": 108.9,
                    "Volume": 453386198.0,
                    "Date": "2026-10-15"
                }
            }
        monkeypatch.setattr(TwseScraper, "fetch_daily_snapshot", mock_fetch_daily_snapshot)

        # Mock 配息日在 2026-07-21 (早於 2026-10-14，安全無除息問題)
        monkeypatch.setattr(loader, "get_latest_dividend_date", lambda t: pd.Timestamp("2026-07-21"))

        # 執行補丁
        patched_df = loader.patch_twse_data_if_needed("0050.TW", mock_df, pd.to_datetime("2026-10-15"))
        assert len(patched_df) == 4
        assert str(patched_df.index[-1].date()) == "2026-10-15"
        assert patched_df.iloc[-1]["Close"] == 108.9

        # 測試：若 yfinance 已是最新日 (2026-10-15)，應保持不變
        no_patch_needed = loader.patch_twse_data_if_needed("0050.TW", patched_df, pd.to_datetime("2026-10-15"))
        assert len(no_patch_needed) == 4

        # 測試：若除息日落在補丁期間 (例如 2026-10-15 除息)，為防折價誤差應跳過補丁
        monkeypatch.setattr(loader, "get_latest_dividend_date", lambda t: pd.Timestamp("2026-10-15"))
        skip_due_to_div = loader.patch_twse_data_if_needed("0050.TW", mock_df, pd.to_datetime("2026-10-15"))
        assert len(skip_due_to_div) == 3

        # 測試：非台股標的 (例如 SPY) 應直接返回
        spy_df = loader.patch_twse_data_if_needed("SPY", mock_df, pd.to_datetime("2026-10-15"))
        assert len(spy_df) == 3

    finally:
        if os.path.exists("test_patch_loader.db"):
            os.remove("test_patch_loader.db")

def test_fetch_data_with_twse_patch(monkeypatch, tmp_path):
    db_file = str(tmp_path / "test_fetch_twse_patch.db")
    loader = DataLoader(db_path=db_file)

    dates = pd.to_datetime(["2026-10-12", "2026-10-13", "2026-10-14"])
    mock_yf_df = pd.DataFrame({
        "Open": [114.2, 112.55, 113.0],
        "High": [114.95, 113.2, 113.75],
        "Low": [113.4, 111.9, 112.75],
        "Close": [114.8, 112.4, 113.0],
        "Volume": [1000.0, 2000.0, 3000.0]
    }, index=dates)

    import yfinance as yf
    monkeypatch.setattr(yf, "download", lambda *args, **kwargs: mock_yf_df)

    from src.scrapers.twse_scraper import TwseScraper
    monkeypatch.setattr(TwseScraper, "fetch_daily_snapshot", lambda self, force_refresh=False: {
        "0050": {
            "Code": "0050",
            "Name": "元大台灣50",
            "Open": 110.15,
            "High": 110.15,
            "Low": 108.55,
            "Close": 108.9,
            "Volume": 453386198.0,
            "Date": "2026-10-15"
        }
    })
    monkeypatch.setattr(loader, "get_latest_dividend_date", lambda t: pd.Timestamp("2026-07-21"))

    df = loader.fetch_data("0050.TW", start_date="2026-10-12", end_date="2026-10-15", refresh=True)
    assert not df.empty
    assert len(df) == 4
    assert str(df.index[-1].date()) == "2026-10-15"
    assert df.iloc[-1]["Close"] == 108.9

    # 驗證 SQLite 資料庫中亦持久化了 2026-10-15
    stored = loader.storage.query_prices("0050.TW", "1d", "2026-10-12", "2026-10-15")
    assert len(stored) == 4
    assert stored.iloc[-1]["Close"] == 108.9




