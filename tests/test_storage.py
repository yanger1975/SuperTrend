import os
import pandas as pd
import pytest
from src.storage import SQLiteStorage

def test_sqlite_storage_flow():
    db_path = "test_market_data.db"
    # 清理舊的測試資料庫
    if os.path.exists(db_path):
        os.remove(db_path)

    try:
        storage = SQLiteStorage(db_path)

        # 1. 構建測試資料
        idx = pd.to_datetime(["2023-01-01 09:30:00", "2023-01-02 09:30:00"])
        df = pd.DataFrame({
            "Open": [100.0, 101.0],
            "High": [102.0, 103.0],
            "Low": [99.0, 100.0],
            "Close": [101.0, 102.0],
            "Volume": [1000.0, 1100.0]
        }, index=idx)

        # 2. 寫入資料庫
        storage.upsert_prices(df, "SPY", "1d")

        # 3. 查詢並比對
        df_queried = storage.query_prices("SPY", "1d", "2023-01-01", "2023-01-02")
        assert not df_queried.empty
        assert len(df_queried) == 2
        assert df_queried["Close"].iloc[0] == 101.0
        assert df_queried["Open"].iloc[1] == 101.0

        # 4. 測試重複寫入的 Upsert 覆蓋邏輯 (Close 欄位從 101 變更為 105)
        df_update = pd.DataFrame({
            "Open": [100.0, 101.0],
            "High": [102.0, 103.0],
            "Low": [99.0, 100.0],
            "Close": [105.0, 102.0],
            "Volume": [1000.0, 1100.0]
        }, index=idx)
        storage.upsert_prices(df_update, "SPY", "1d")

        df_queried_2 = storage.query_prices("SPY", "1d", "2023-01-01", "2023-01-02")
        assert len(df_queried_2) == 2
        assert df_queried_2["Close"].iloc[0] == 105.0 # 第一筆已被成功更新為 105

    finally:
        # 清理測試產生的資料庫檔案
        if os.path.exists(db_path):
            os.remove(db_path)
