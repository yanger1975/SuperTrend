import pandas as pd
import numpy as np
import pytest
from src.backtest_engine import BacktestEngine

def test_backtester_execution_flow():
    # 1. 檢驗正常的進場與趨勢反轉出場流程
    idx = pd.to_datetime(["2023-01-01", "2023-01-02", "2023-01-03", "2023-01-04"])
    df = pd.DataFrame({
        "Open": [100.0, 101.0, 102.0, 103.0],
        "High": [102.0, 103.0, 104.0, 105.0],
        "Low": [98.0, 99.0, 100.0, 101.0],
        "Close": [99.0, 102.0, 100.0, 104.0],
        "SuperTrend": [98.0, 98.0, 103.0, 103.0],
        "Trend": [-1, 1, -1, -1]  # 第一天為 -1，第二天翻多 (進場)，第三天翻空 (出場)
    }, index=idx)
    
    engine = BacktestEngine(df)
    trades, strat_eq, bench_eq = engine.run(long_only=True, commission_bps=10, slippage_bps=5)
    
    assert len(trades) == 1
    assert trades[0].exit_reason == "Signal"
    assert trades[0].exit_date == pd.Timestamp("2023-01-03")
    assert len(strat_eq) == 4

def test_backtester_gap_stop_loss():
    # 2. 測試跳空低開直接穿越 Stop-Loss 的情形
    idx = pd.to_datetime(["2023-01-01", "2023-01-02", "2023-01-03"])
    df = pd.DataFrame({
        "Open": [100.0, 102.0, 80.0],  # 第三天跳空暴跌至 80.0
        "High": [105.0, 104.0, 85.0],
        "Low": [95.0, 99.0, 75.0],
        "Close": [99.0, 102.0, 81.0],
        "SuperTrend": [98.0, 98.0, 98.0],
        "Trend": [-1, 1, 1]  # 第二天翻多進場 (Close = 102.0)
    }, index=idx)
    
    # 停損設為 10% (即當進場價 102 時，止損價為 91.8)
    # 第三天開盤為 80.0，低於止損價 91.8，應以開盤價 80.0 成交
    engine = BacktestEngine(df)
    trades, strat_eq, bench_eq = engine.run(long_only=True, stop_loss_pct=0.10)
    
    assert len(trades) == 1
    assert trades[0].exit_reason == "StopLoss"
    # 考量無滑價時，成交價應剛好為開盤價 80.0
    assert trades[0].exit_price == 80.0

def test_backtester_same_bar_priority():
    # 3. 測試同一天既觸發止損 (Low) 又觸發止利 (High) 時，日線模式下保守假設止損 SL 優先
    idx = pd.to_datetime(["2023-01-01", "2023-01-02", "2023-01-03"])
    df = pd.DataFrame({
        "Open": [100.0, 100.0, 100.0],
        "High": [102.0, 102.0, 120.0],  # 第三天大漲大跌，High 120.0, Low 80.0
        "Low": [98.0, 98.0, 80.0],
        "Close": [99.0, 101.0, 101.0],
        "SuperTrend": [98.0, 98.0, 98.0],
        "Trend": [-1, 1, 1]  # 第二天進場 (Close = 101.0)
    }, index=idx)
    
    # 第三天設 5% 止損與 5% 止利
    # 止損點為 95.95，止利點為 106.05。第三天 High 120, Low 80 兩者皆滿足。
    # 系統應判定止損優先觸發
    engine = BacktestEngine(df)
    trades, strat_eq, bench_eq = engine.run(long_only=True, stop_loss_pct=0.05, take_profit_pct=0.05)
    
    assert len(trades) == 1
    assert trades[0].exit_reason == "StopLoss"
    assert trades[0].exit_price == 101.0 * 0.95
