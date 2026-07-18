import numpy as np
import pandas as pd
import pytest
from src.backtest_engine import Trade
from src.risk_manager import RiskManager

def test_risk_metrics_calculation():
    # 建立測試交易
    trades = [
        Trade(entry_date=pd.Timestamp("2023-01-01"), entry_price=10.0, exit_date=pd.Timestamp("2023-01-05"), exit_price=11.0, pnl_pct=0.10, is_closed=True),
        Trade(entry_date=pd.Timestamp("2023-01-06"), entry_price=10.0, exit_date=pd.Timestamp("2023-01-10"), exit_price=9.5, pnl_pct=-0.05, is_closed=True),
        Trade(entry_date=pd.Timestamp("2023-01-11"), entry_price=10.0, exit_date=pd.Timestamp("2023-01-15"), exit_price=10.5, pnl_pct=0.05, is_closed=True)
    ]
    # 建立每日淨值曲線 (15天)
    dates = pd.date_range(start="2023-01-01", periods=15, freq="D")
    equity_vals = [100000.0, 102000.0, 104000.0, 106000.0, 110000.0, 109000.0, 107000.0, 106000.0, 105000.0, 104500.0, 106000.0, 107000.0, 108000.0, 109000.0, 109725.0]
    equity = pd.Series(equity_vals, index=dates)
    
    rm = RiskManager(trades, equity)
    metrics = rm.calculate_metrics()
    
    # 驗證必要欄位存在與計算範圍
    assert "CAGR" in metrics
    assert "Ulcer Index" in metrics
    assert "Expectancy" in metrics
    assert "Sharpe Ratio" in metrics
    assert metrics["Win Rate"] == pytest.approx(2/3)
    
    # 驗證 Monte Carlo
    mc_res = rm.run_monte_carlo(runs=100, seed=42)
    assert "drawdowns" in mc_res
    assert "percentiles" in mc_res
    assert len(mc_res["drawdowns"]) == 100
    
    # 測試種子碼的可重現性
    mc_res_2 = rm.run_monte_carlo(runs=100, seed=42)
    assert np.allclose(mc_res["drawdowns"], mc_res_2["drawdowns"])
