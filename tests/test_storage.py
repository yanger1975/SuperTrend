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

        # 5. 測試 supertrend_params 寫入與查詢
        storage.save_supertrend_params(
            ticker="SPY",
            start_date="2020-01-01",
            end_date="2023-01-01",
            st_period=10,
            st_multiplier=3.0,
            ma_period=50,
            use_hma_filter=True,
            custom_score=5.25,
            cagr=0.15,
            max_drawdown=-0.08,
            sharpe_ratio=1.5,
            calmar_ratio=1.8,
            win_rate=0.6,
            profit_factor=2.1
        )

        res_df = storage.query_supertrend_params("SPY", "2020-01-01", "2023-01-01")
        assert not res_df.empty
        assert res_df["st_period"].iloc[0] == 10
        assert res_df["st_multiplier"].iloc[0] == 3.0
        assert res_df["cagr"].iloc[0] == 0.15

        # 測試 ON CONFLICT (Upsert) 覆蓋更新
        storage.save_supertrend_params(
            ticker="SPY",
            start_date="2020-01-01",
            end_date="2023-01-01",
            st_period=15,
            st_multiplier=2.5,
            ma_period=0,
            use_hma_filter=False,
            custom_score=6.0,
            cagr=0.18,
            max_drawdown=-0.06,
            sharpe_ratio=1.8,
            calmar_ratio=2.0,
            win_rate=0.65,
            profit_factor=2.5
        )

        res_df_updated = storage.query_supertrend_params("SPY", "2020-01-01", "2023-01-01")
        assert len(res_df_updated) == 1
        assert res_df_updated["st_period"].iloc[0] == 15
        assert res_df_updated["st_multiplier"].iloc[0] == 2.5
        assert res_df_updated["cagr"].iloc[0] == 0.18

        # 6. 測試 stock_signals 寫入與查詢
        storage.save_stock_signals(
            ticker="SPY",
            start_date="2020-01-01",
            end_date="2023-01-01",
            close_price=400.0,
            supertrend=390.0,
            position=1,
            entry_ref=None,
            exit_ref=390.0,
            hma=395.0
        )

        sig_df = storage.query_stock_signals("SPY", "2020-01-01", "2023-01-01")
        assert not sig_df.empty
        assert sig_df["position"].iloc[0] == 1
        assert sig_df["exit_ref"].iloc[0] == 390.0
        assert pd.isna(sig_df["entry_ref"].iloc[0])
        assert sig_df["hma"].iloc[0] == 395.0

        # 測試 stock_signals Upsert
        storage.save_stock_signals(
            ticker="SPY",
            start_date="2020-01-01",
            end_date="2023-01-01",
            close_price=380.0,
            supertrend=385.0,
            position=0,
            entry_ref=385.0,
            exit_ref=None,
            hma=0.0
        )

        sig_df_updated = storage.query_stock_signals("SPY", "2020-01-01", "2023-01-01")
        assert len(sig_df_updated) == 1
        assert sig_df_updated["position"].iloc[0] == 0
        assert sig_df_updated["entry_ref"].iloc[0] == 385.0
        assert pd.isna(sig_df_updated["exit_ref"].iloc[0])
        assert sig_df_updated["hma"].iloc[0] == 0.0

    finally:
        # 清理測試產生的資料庫檔案
        if os.path.exists(db_path):
            os.remove(db_path)
