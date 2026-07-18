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
