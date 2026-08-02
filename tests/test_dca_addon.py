import pytest
import os
import pandas as pd
import numpy as np
from src.dca_addon.config import AddOnRule, StrategyConfig
from src.dca_addon.engine import DCAAddOnBacktester
from src.dca_addon.metrics import evaluate_performance
from src.dca_addon.visualizer import generate_html_report
from src.dca_addon.optimizer import grid_search


def test_addon_rule_creation():
    rule = AddOnRule(
        lookback_days=20,
        drawdown_threshold=0.06,
        multiplier=2.0,
        reference_type="shift"
    )
    assert rule.lookback_days == 20
    assert rule.drawdown_threshold == pytest.approx(0.06)
    assert rule.multiplier == pytest.approx(2.0)
    assert rule.reference_type == "shift"


def test_strategy_config_defaults():
    rule = AddOnRule(lookback_days=20, drawdown_threshold=0.06, multiplier=2.0)
    config = StrategyConfig(
        base_invest_amount=10000,
        rules=[rule]
    )
    assert config.base_invest_amount == 10000
    assert len(config.rules) == 1
    assert config.invest_frequency == "M"
    assert config.cooldown_days == 0
    assert config.max_addons_per_month is None
    assert config.total_extra_budget is None
    assert config.max_total_invest is None
    assert config.cash_risk_free_rate == 0.0


def create_sample_price_df():
    dates = pd.date_range("2020-01-01", periods=60, freq="B")
    prices = [100.0] * 25 + [90.0] * 35
    return pd.DataFrame({"Date": dates, "Close": prices})


def test_regular_dca_only():
    df = create_sample_price_df()
    config = StrategyConfig(base_invest_amount=10000, rules=[])
    bt = DCAAddOnBacktester(df, config)
    equity, trades = bt.run()

    assert not equity.empty
    assert len(trades) > 0
    assert (trades["Type"] == "regular").all()


def test_addon_trigger_and_cooldown():
    df = create_sample_price_df()
    rule = AddOnRule(lookback_days=10, drawdown_threshold=0.08, multiplier=2.0)
    config = StrategyConfig(
        base_invest_amount=10000,
        rules=[rule],
        cooldown_days=5,
        max_addons_per_month=1
    )
    bt = DCAAddOnBacktester(df, config)
    equity, trades = bt.run()

    addon_trades = trades[trades["Type"] == "addon"]
    assert len(addon_trades) >= 1
    assert addon_trades["Amount"].iloc[0] == pytest.approx(20000.0)


def test_evaluate_performance_metrics():
    df = create_sample_price_df()
    rule = AddOnRule(lookback_days=10, drawdown_threshold=0.08, multiplier=2.0)
    config = StrategyConfig(
        base_invest_amount=10000,
        rules=[rule],
        total_extra_budget=100000
    )
    bt = DCAAddOnBacktester(df, config)
    equity, trades = bt.run()

    perf = evaluate_performance(equity, trades, config)
    assert "total_return" in perf
    assert "max_drawdown" in perf
    assert "extra_budget_utilization_rate" in perf
    assert "alpha_vs_pure_dca" in perf
    assert perf["addon_count"] >= 1


def test_evaluate_performance_empty_df():
    empty_equity = pd.DataFrame()
    empty_trades = pd.DataFrame()
    perf = evaluate_performance(empty_equity, empty_trades)
    assert perf == {}


def test_grid_search_execution():
    df = create_sample_price_df()
    param_grid = {
        "lookbacks": [5, 10],
        "first_thresholds": [0.05],
        "second_thresholds": [0.10],
        "first_multipliers": [1.5],
        "second_multipliers": [2.0],
        "cooldowns": [0],
        "monthly_limits": [1]
    }
    results_df = grid_search(df, param_grid, base_amount=10000)
    assert not results_df.empty
    assert "cagr" in results_df.columns
    assert "max_drawdown" in results_df.columns


def test_generate_html_report_output(tmp_path):
    df = create_sample_price_df()
    config = StrategyConfig(base_invest_amount=10000, rules=[])
    bt = DCAAddOnBacktester(df, config)
    equity, trades = bt.run()
    perf = evaluate_performance(equity, trades, config)

    output_path = tmp_path / "report.html"
    generate_html_report(df, equity, trades, perf, str(output_path))
    assert os.path.exists(output_path)
    assert os.path.getsize(output_path) > 0


def test_cli_runners_execution():
    import subprocess
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    res = subprocess.run(["python", "run_dca_backtest.py", "--help"], capture_output=True, text=True, encoding="utf-8", env=env)
    assert res.returncode == 0
    assert "ETF" in res.stdout
