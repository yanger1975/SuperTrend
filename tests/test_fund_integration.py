import pytest
import pandas as pd
from src.data_loader import DataLoader
from src.dca_addon.config import StrategyConfig, AddOnRule
from src.dca_addon.engine import DCAAddOnBacktester
from src.dca_addon.metrics import evaluate_performance


def test_ezmoney_fund_fetch_and_backtest():

    loader = DataLoader()
    # 抓取 統一全球新科技基金 (33YTW.EZ)
    df = loader.fetch_data("33YTW.EZ", start_date="2024-01-01", end_date="2026-07-24")

    assert not df.empty
    assert "Close" in df.columns
    assert len(df) > 50

    # 驗證元數據已建立
    info = loader.storage.get_ticker_info("33YTW.EZ")
    assert info is not None
    assert info["name"] == "統一全球新科技基金"
    assert info["asset_type"] == "fund"

    # 執行左側加碼策略回測
    config = StrategyConfig(
        base_invest_amount=10000,
        rules=[
            AddOnRule(lookback_days=20, drawdown_threshold=0.05, multiplier=2.0)
        ],
        total_extra_budget=500000
    )

    bt = DCAAddOnBacktester(df, config)
    equity, trades = bt.run()
    perf = evaluate_performance(equity, trades, config)

    assert not equity.empty
    assert "total_return" in perf
    assert perf["total_cost"] > 0
