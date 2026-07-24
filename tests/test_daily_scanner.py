import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np
from datetime import datetime

from run_daily_scanner import (
    get_target_tickers,
    get_best_param_for_ticker,
    process_ticker_signal,
    build_telegram_report
)
from src.storage import SQLiteStorage


@pytest.fixture
def mock_storage(tmp_path):
    db_path = str(tmp_path / "test_market.db")
    storage = SQLiteStorage(db_path)
    return storage


@pytest.fixture
def sample_price_df():
    dates = pd.date_range("2024-01-01", periods=100, freq="B")
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(100) * 2)
    high = close + np.random.rand(100) * 2
    low = close - np.random.rand(100) * 2
    open_p = low + (high - low) / 2

    df = pd.DataFrame({
        "Open": open_p,
        "High": high,
        "Low": low,
        "Close": close,
        "Volume": 100000
    }, index=dates)
    return df


def test_get_target_tickers():
    tickers = get_target_tickers(["AAPL", "TSLA"])
    assert "SPY" in tickers
    assert "QQQM" in tickers
    assert "AAPL" in tickers
    assert "TSLA" in tickers


def test_get_best_param_new_ticker(mock_storage, sample_price_df):
    param = get_best_param_for_ticker(
        storage=mock_storage,
        ticker="TEST_NEW",
        target_date_str="2024-05-24",
        raw_df=sample_price_df,
        force_reoptimize=False
    )
    assert "ST_Period" in param
    assert "ST_Multiplier" in param

    # 驗證資料庫是否有寫入 supertrend_params
    saved = mock_storage.query_supertrend_params("TEST_NEW")
    assert not saved.empty


def test_get_best_param_existing_ticker_nearest_date(mock_storage, sample_price_df):
    # 先儲存兩組不同 end_date 的參數
    mock_storage.save_supertrend_params(
        ticker="TEST_EXIST",
        start_date="2020-01-01",
        end_date="2024-01-01",
        st_period=10,
        st_multiplier=3.0,
        ma_period=0,
        use_hma_filter=False
    )
    mock_storage.save_supertrend_params(
        ticker="TEST_EXIST",
        start_date="2020-01-01",
        end_date="2024-05-01",
        st_period=20,
        st_multiplier=4.0,
        ma_period=50,
        use_hma_filter=True
    )

    # 查詢與 2024-05-20 最接近的參數（應該選到 2024-05-01 的那組，ST_Period=20）
    param = get_best_param_for_ticker(
        storage=mock_storage,
        ticker="TEST_EXIST",
        target_date_str="2024-05-20",  # 週一 (2024-05-20 不是週六)
        raw_df=sample_price_df,
        force_reoptimize=False
    )

    assert param["ST_Period"] == 20
    assert param["ST_Multiplier"] == 4.0
    assert param["Use_HMA_Filter"] is True


def test_process_ticker_signal(sample_price_df):
    param = {
        "ST_Period": 10,
        "ST_Multiplier": 3.0,
        "MA_Period": 0,
        "Use_HMA_Filter": False
    }

    sig = process_ticker_signal("TEST_SIG", sample_price_df, param)
    assert sig["ticker"] == "TEST_SIG"
    assert sig["signal_state"] in ["NEW_BUY", "NEW_SELL", "HOLD_LONG", "WAIT_CASH"]
    assert "close" in sig
    assert "supertrend" in sig


def test_build_telegram_report():
    signals = [
        {
            "ticker": "TSLA",
            "close": 250.0,
            "supertrend": 240.0,
            "signal_state": "NEW_BUY",
            "entry_ref": 240.0,
            "exit_ref": None,
            "param": {"ST_Period": 10, "ST_Multiplier": 3.0, "MA_Period": 0, "Use_HMA_Filter": False}
        },
        {
            "ticker": "NVDA",
            "close": 120.0,
            "supertrend": 125.0,
            "signal_state": "NEW_SELL",
            "entry_ref": None,
            "exit_ref": 125.0,
            "param": {"ST_Period": 20, "ST_Multiplier": 4.0, "MA_Period": 50, "Use_HMA_Filter": True}
        },
        {
            "ticker": "SPY",
            "close": 550.0,
            "supertrend": 540.0,
            "signal_state": "HOLD_LONG",
            "entry_ref": None,
            "exit_ref": 540.0,
            "param": {"ST_Period": 15, "ST_Multiplier": 2.5, "MA_Period": 50, "Use_HMA_Filter": False}
        },
        {
            "ticker": "AAPL",
            "close": 220.0,
            "supertrend": 230.0,
            "signal_state": "WAIT_CASH",
            "entry_ref": 230.0,
            "exit_ref": None
        }
    ]

    report = build_telegram_report("2024-05-24", signals)
    assert "SuperTrend 每日策略診斷報告" in report
    assert "TSLA (10, 3.0, 0)" in report
    assert "NVDA (20, 4.0, 50)" in report
    assert "SPY (15, 2.5, 0)" in report  # Use_HMA_Filter is False so ma_period displays 0
    assert "AAPL" in report
    assert "[買入]" in report
    assert "[平倉]" in report


@patch("sys.argv", ["run_daily_scanner.py", "--dry-run", "--tickers", "SPY"])
def test_daily_scanner_main_dry_run(mock_storage, sample_price_df):
    with patch("run_daily_scanner.DataLoader.fetch_data", return_value=sample_price_df):
        with patch("run_daily_scanner.SQLiteStorage", return_value=mock_storage):
            from run_daily_scanner import main
            main()

