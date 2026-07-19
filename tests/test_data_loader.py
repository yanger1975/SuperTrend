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



