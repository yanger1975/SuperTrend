import pytest
import pandas as pd
import numpy as np
import os
from src.supertrend_ai.indicator import calculate_atr, supertrend_ai
from src.supertrend_ai.backtest import run_supertrend_ai_backtest
from src.supertrend_ai.db_setup import get_connection, init_supertrend_ai_db, query_supertrend_ai_params

@pytest.fixture
def mock_df():
    np.random.seed(42)
    dates = pd.date_range("2023-01-01", periods=100, freq='D')
    close = np.linspace(100, 150, 100) + np.random.randn(100) * 2
    open_price = close - np.random.randn(100)
    high = close + np.random.rand(100) * 2
    low = close - np.random.rand(100) * 2
    df = pd.DataFrame({"Open": open_price, "High": high, "Low": low, "Close": close}, index=dates)
    return df

def test_indicator_shape(mock_df):
    df_ind = supertrend_ai(mock_df, length=5, min_mult=1.0, max_mult=3.0, step=1.0)
    assert 'SuperTrend_AI' in df_ind.columns
    assert 'SuperTrend_AI_Direction' in df_ind.columns
    assert 'Target_Factor' in df_ind.columns
    assert len(df_ind) == 100

def test_backtest_engine_integration(mock_df):
    trades, equity, benchmark, df_ind, metrics = run_supertrend_ai_backtest(
        mock_df, length=5, min_mult=1.0, max_mult=3.0, step=1.0
    )
    assert len(equity) == 100
    assert "CAGR" in metrics
    assert "Max Drawdown" in metrics

def test_db_setup_and_write():
    # Write a test record
    from src.supertrend_ai.db_setup import save_supertrend_ai_params, get_connection
    init_supertrend_ai_db()
    try:
        save_supertrend_ai_params(
            ticker="TEST",
            start_date="2023-01-01",
            end_date="2023-12-31",
            atr_length=10,
            factor_min=1.0,
            factor_max=2.0,
            factor_step=0.5,
            perf_alpha=10.0,
            from_cluster="Best",
            custom_score=1.23,
            cagr=0.15,
            export_json=False
        )
        df_db = query_supertrend_ai_params("TEST")
        assert not df_db.empty
        assert df_db.iloc[0]['cagr'] == 0.15
    finally:
        with get_connection() as conn:
            conn.cursor().execute("DELETE FROM strategy_params_supertrend_ai WHERE ticker = 'TEST'")
            conn.commit()


def test_collect_tickers_and_market_split():
    from run_batch_optimization_supertrend_ai import collect_tickers, build_telegram_ai_report
    import argparse

    us_tickers, tw_tickers = collect_tickers()
    assert "SPY" in us_tickers
    assert "0050.TW" in tw_tickers
    assert "33YTW.EZ" in tw_tickers

    args = argparse.Namespace(date="2026-10-11")
    fake_results_us = [{
        "ticker": "SPY",
        "success": True,
        "latest_signal": {"date": "2026-10-09", "close": "778.57", "position": "long", "exit_ref": "745.00"}
    }]
    fake_results_tw = [{
        "ticker": "0050.TW",
        "success": True,
        "latest_signal": {"date": "2026-10-08", "close": "114.95", "position": "long", "exit_ref": "111.00"}
    }]

    us_blocks = build_telegram_ai_report(fake_results_us, args, is_saturday=False, market_type="us")
    tw_blocks = build_telegram_ai_report(fake_results_tw, args, is_saturday=False, market_type="tw")

    us_text = "\n".join(us_blocks)
    tw_text = "\n".join(tw_blocks)

    assert "美股市場" in us_text
    assert "台股與基金" in tw_text
    assert "SPY" in us_text
    assert "0050.TW" in tw_text

