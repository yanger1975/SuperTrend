import pandas as pd
import numpy as np
from src.indicators import compute_hma, compute_rsi, compute_adx, compute_supertrend

def test_hma_calculation():
    # 建立遞增數值數列
    prices = pd.Series([10, 12, 14, 16, 18, 20, 22, 24, 26, 28])
    hma_val = compute_hma(prices, period=4)
    assert len(hma_val) == len(prices)
    # HMA 應在足夠長度後有非 nan 值
    assert not pd.isna(hma_val.iloc[-1])

def test_rsi_calculation():
    # 建立一段上漲後下跌的資料
    prices = pd.Series([10, 11, 12, 13, 14, 15, 14, 13, 12, 11, 10])
    rsi_val = compute_rsi(prices, period=5)
    assert len(rsi_val) == len(prices)
    # RSI 理論上應介於 0 至 100 之間
    assert rsi_val.dropna().min() >= 0
    assert rsi_val.dropna().max() <= 100

def test_supertrend_calculation():
    # 建立虛擬 OHLCV 資料
    df = pd.DataFrame({
        "Open": [10.0, 11.0, 12.0, 11.0, 10.0, 9.0, 10.0, 11.0, 12.0, 13.0],
        "High": [10.5, 11.5, 12.5, 11.5, 10.5, 9.5, 10.5, 11.5, 12.5, 13.5],
        "Low": [9.5, 10.5, 11.5, 10.5, 9.5, 8.5, 9.5, 10.5, 11.5, 12.5],
        "Close": [10.1, 11.2, 12.1, 10.9, 9.8, 8.9, 10.2, 11.1, 12.3, 13.1],
        "Volume": [1000] * 10
    })

    res_df, trend = compute_supertrend(df, period=3, multiplier=2.0)
    assert "SuperTrend" in res_df.columns
    assert "Trend" in res_df.columns
    assert len(trend) == 10
    # 趨勢只應為 1 或 -1
    assert set(trend.unique()).issubset({1, -1})
