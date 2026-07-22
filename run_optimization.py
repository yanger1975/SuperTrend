#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SuperTrend Optimization Console Script
========================================
Usage:
    python run_optimization.py --ticker SPY --start 2020-01-01

This script:
1. Downloads daily data for the given ticker (end date = today)
2. Runs parameter optimization with progress display
3. Shows top 5 parameter sets with key metrics
4. Runs backtest with best parameters and shows all transactions
5. Displays performance and risk metrics
"""

import argparse
import sys
import time
from datetime import datetime
from typing import List, Tuple

import pandas as pd
import numpy as np

from src.data_loader import DataLoader
from src.indicators import compute_supertrend, compute_hma, compute_adx, compute_rsi
from src.backtest_engine import BacktestEngine, Trade
from src.risk_manager import RiskManager
from src.optimizer import ParameterOptimizer


# ============================================================================
# Configuration: Optimization Parameter Grids
# ============================================================================
ST_PERIODS = [5, 10, 15, 20, 25, 30]
ST_MULTIPLIERS = [2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
MA_PERIODS = [0, 25, 50, 75, 100, 125]  # 0 = no HMA filter
TRAIN_RATIO = 0.70
TARGET_METRIC = "Custom Score"

# Display columns for top results
DISPLAY_COLS = [
    "ST_Period", "ST_Multiplier", "MA_Period", "Use_HMA_Filter",
    "Custom Score", "CAGR", "Max Drawdown", "Sharpe Ratio",
    "Calmar Ratio", "Win Rate", "Profit Factor"
]


# ============================================================================
# Console Progress Display
# ============================================================================
class ProgressTracker:
    """Simple console progress tracker with spinner and counters."""

    def __init__(self, total_combinations: int):
        self.total = total_combinations
        self.current = 0
        self.start_time = time.time()
        self.spinner_chars = ['|', '/', '-', '\\']
        self.spinner_idx = 0

    def update(self, current_params: str = ""):
        self.current += 1
        elapsed = time.time() - self.start_time
        pct = (self.current / self.total) * 100 if self.total > 0 else 0
        eta = (elapsed / self.current) * (self.total - self.current) if self.current > 0 else 0

        spinner = self.spinner_chars[self.spinner_idx % len(self.spinner_chars)]
        self.spinner_idx += 1

        bar_width = 30
        filled = int(bar_width * self.current / self.total) if self.total > 0 else 0
        bar = '#' * filled + '-' * (bar_width - filled)

        params_str = f" | {current_params}" if current_params else ""
        sys.stdout.write(
            f"\r{spinner} [{bar}] {self.current}/{self.total} ({pct:.1f}%) "
            f"Elapsed: {elapsed:.1f}s ETA: {eta:.1f}s{params_str}"
        )
        sys.stdout.flush()

    def finish(self):
        elapsed = time.time() - self.start_time
        sys.stdout.write(f"\r{'OK':>2} [{'#' * 30}] {self.total}/{self.total} (100.0%) "
                         f"Elapsed: {elapsed:.1f}s\n")
        sys.stdout.flush()


def format_metric(value: float, pct_format: bool = False) -> str:
    """Format metric value for display."""
    if pd.isna(value):
        return "N/A"
    if pct_format:
        return f"{value * 100:.2f}%"
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    if abs(value) >= 100:
        return f"{value:.1f}"
    if abs(value) >= 10:
        return f"{value:.2f}"
    return f"{value:.3f}"


def print_results_table(df: pd.DataFrame, title: str, top_n: int = 5):
    """Pretty print a results DataFrame with the specified columns."""
    print(f"\n{'=' * 80}")
    print(f"{title}")
    print(f"{'=' * 80}")

    if df.empty:
        print("No results found.")
        return

    display_df = df[DISPLAY_COLS].head(top_n).copy()

    # Format for display
    for col in ["CAGR", "Max Drawdown", "Win Rate"]:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(lambda x: format_metric(x, pct_format=True))

    for col in ["Custom Score", "Sharpe Ratio", "Calmar Ratio", "Profit Factor"]:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(format_metric)

    display_df["MA_Period"] = display_df["MA_Period"].apply(lambda x: f"HMA({int(x)})" if x > 0 else "None")
    display_df["Use_HMA_Filter"] = display_df["Use_HMA_Filter"].apply(lambda x: "Yes" if x else "No")

    # Print with pandas formatting
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 160)
    pd.set_option('display.colheader_justify', 'center')
    print(display_df.to_string(index=False))
    print()


def print_transactions(trades: List[Trade]):
    """Print all transactions in a formatted table."""
    print(f"\n{'=' * 80}")
    print(f"完整交易紀錄 (共 {len(trades)} 筆)")
    print(f"{'=' * 80}")

    if not trades:
        print("無交易記錄")
        return

    trade_data = []
    for idx, t in enumerate(trades, 1):
        trade_data.append({
            "序號": idx,
            "方向": t.direction,
            "進場日期": t.entry_date.strftime("%Y-%m-%d"),
            "進場價": f"{t.entry_price:.2f}",
            "出場日期": t.exit_date.strftime("%Y-%m-%d") if t.exit_date else "未平倉",
            "出場價": f"{t.exit_price:.2f}" if t.exit_price else "未平倉",
            "損益(%)": f"{t.pnl_pct * 100:.2f}%",
            "離場原因": t.exit_reason
        })

    df_trades = pd.DataFrame(trade_data)
    pd.set_option('display.max_rows', None)
    pd.set_option('display.width', 160)
    print(df_trades.to_string(index=False))
    print()


def print_performance_metrics(metrics: dict):
    """Print performance and risk metrics."""
    print(f"\n{'=' * 80}")
    print(f"績效與風險統計指標")
    print(f"{'=' * 80}")

    for key, val in metrics.items():
        if isinstance(val, float):
            if key in ["CAGR", "Max Drawdown", "Ulcer Index", "Win Rate", "Expectancy"]:
                print(f"  {key:25s}: {val * 100:>8.2f}%")
            else:
                print(f"  {key:25s}: {val:>8.2f}")
        else:
            print(f"  {key:25s}: {val}")
    print()


def run_optimization_with_progress(df_raw: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Run optimization with console progress display."""
    total_combos = len(ST_PERIODS) * len(ST_MULTIPLIERS) * len(MA_PERIODS)
    tracker = ProgressTracker(total_combos)

    # We'll monkey-patch the optimizer to show progress
    optimizer = ParameterOptimizer(df_raw)

    # Custom optimize with progress
    split_idx = int(len(df_raw) * TRAIN_RATIO)
    train_results = []
    test_results = []

    print(f"\n{'=' * 80}")
    print(f"參數優化進度 (Train Ratio: {TRAIN_RATIO:.0%}, Target: {TARGET_METRIC})")
    print(f"搜尋空間: ST_Period={ST_PERIODS}, ST_Multiplier={ST_MULTIPLIERS}, MA_Period={MA_PERIODS}")
    print(f"總組合數: {total_combos}")
    print(f"{'=' * 80}\n")

    for period in ST_PERIODS:
        for mult in ST_MULTIPLIERS:
            df_st_full, _ = compute_supertrend(df_raw, period=period, multiplier=mult)

            df_st_train = df_st_full.iloc[:split_idx].copy()
            df_st_test = df_st_full.iloc[split_idx:].copy() if TRAIN_RATIO < 1.0 else pd.DataFrame()

            for ma_p in MA_PERIODS:
                use_hma = ma_p is not None and ma_p > 0
                param_str = f"ST({period},{mult}) HMA={ma_p if use_hma else 'None'}"
                tracker.update(param_str)

                # Train
                df_temp_train = df_st_train.copy()
                if use_hma:
                    df_temp_train["HMA"] = compute_hma(df_temp_train["Close"], period=ma_p)
                    df_temp_train["MA_Filter"] = df_temp_train["Close"] > df_temp_train["HMA"]
                else:
                    df_temp_train["MA_Filter"] = True

                engine_train = BacktestEngine(df_temp_train)
                trades_train, eq_train, _ = engine_train.run(long_only=True)
                rm_train = RiskManager(trades_train, eq_train)
                metrics_train = rm_train.calculate_metrics()

                if metrics_train:
                    score_train = optimizer.calculate_custom_score(metrics_train)
                    train_results.append({
                        "ST_Period": period, "ST_Multiplier": mult,
                        "MA_Period": ma_p if use_hma else 0,
                        "Use_HMA_Filter": use_hma,
                        "Custom Score": score_train, **metrics_train
                    })

                # Test (OOS)
                if not df_st_test.empty:
                    df_temp_test = df_st_test.copy()
                    if use_hma:
                        df_temp_test["HMA"] = compute_hma(df_temp_test["Close"], period=ma_p)
                        df_temp_test["MA_Filter"] = df_temp_test["Close"] > df_temp_test["HMA"]
                    else:
                        df_temp_test["MA_Filter"] = True

                    engine_test = BacktestEngine(df_temp_test)
                    trades_test, eq_test, _ = engine_test.run(long_only=True)
                    rm_test = RiskManager(trades_test, eq_test)
                    metrics_test = rm_test.calculate_metrics()

                    if metrics_test:
                        score_test = optimizer.calculate_custom_score(metrics_test)
                        test_results.append({
                            "ST_Period": period, "ST_Multiplier": mult,
                            "MA_Period": ma_p if use_hma else 0,
                            "Use_HMA_Filter": use_hma,
                            "Custom Score": score_test, **metrics_test
                        })

    tracker.finish()

    train_df = pd.DataFrame(train_results)
    test_df = pd.DataFrame(test_results)

    if not train_df.empty:
        train_df = train_df.sort_values(by=TARGET_METRIC, ascending=False).reset_index(drop=True)
    if not test_df.empty:
        test_df = test_df.sort_values(by=TARGET_METRIC, ascending=False).reset_index(drop=True)

    return train_df, test_df


def main():
    parser = argparse.ArgumentParser(
        description="SuperTrend Parameter Optimization & Backtest Console Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_optimization.py --ticker SPY --start 2020-01-01
  python run_optimization.py --ticker TSM --start 2018-07-20 --interval 1d
  python run_optimization.py --ticker QQQ --start 2015-01-01 --commission 5 --slippage 2
        """
    )
    parser.add_argument("--ticker", type=str, default="SPY",
                        help="Stock/ETF ticker symbol (default: SPY)")
    parser.add_argument("--start", type=str, default="2020-01-01",
                        help="Start date in YYYY-MM-DD format (default: 2020-01-01)")
    parser.add_argument("--end", type=str, default=None,
                        help="End date in YYYY-MM-DD format (default: today)")
    parser.add_argument("--interval", type=str, default="1d",
                        choices=["1d", "1h", "60m"],
                        help="Data interval (default: 1d)")
    parser.add_argument("--commission", type=float, default=10.0,
                        help="Commission in basis points per side (default: 10)")
    parser.add_argument("--slippage", type=float, default=5.0,
                        help="Slippage in basis points per side (default: 5)")
    parser.add_argument("--train-ratio", type=float, default=0.70,
                        help="Train/test split ratio (default: 0.70, 1.0 = no split)")
    parser.add_argument("--refresh", action="store_true",
                        help="Force re-download from Yahoo Finance (ignore cache)")
    parser.add_argument("--stop-loss", type=float, default=0.0,
                        help="Stop loss percentage (e.g., 0.08 for 8%, default: 0 = disabled)")
    parser.add_argument("--take-profit", type=float, default=0.0,
                        help="Take profit percentage (e.g., 0.15 for 15%, default: 0 = disabled)")

    args = parser.parse_args()

    # Set end date to today if not provided
    if args.end is None:
        args.end = datetime.now().strftime("%Y-%m-%d")

    print(f"\n{'=' * 80}")
    print(f"SuperTrend 優化回測系統")
    print(f"{'=' * 80}")
    print(f"標的: {args.ticker}")
    print(f"區間: {args.start} 至 {args.end}")
    print(f"週期: {args.interval}")
    print(f"手續費: {args.commission} bps | 滑價: {args.slippage} bps")
    if args.stop_loss > 0:
        print(f"停損: {args.stop_loss * 100:.1f}%")
    if args.take_profit > 0:
        print(f"停利: {args.take_profit * 100:.1f}%")
    print(f"Train/Test 分割: {args.train_ratio:.0%}")
    print(f"{'=' * 80}\n")

    # -------------------------------------------------------------------------
    # Step 1: Download / Load Data
    # -------------------------------------------------------------------------
    print("步驟 1: 下載/載入歷史價格資料...")
    loader = DataLoader()
    df_raw = loader.fetch_data(
        ticker=args.ticker,
        start_date=args.start,
        end_date=args.end,
        interval=args.interval,
        refresh=args.refresh
    )
    print(f"  成功載入 {len(df_raw)} 筆 {args.ticker} K 線資料")
    print(f"  區間: {df_raw.index[0].date()} ~ {df_raw.index[-1].date()}")

    # -------------------------------------------------------------------------
    # Step 2: Parameter Optimization
    # -------------------------------------------------------------------------
    print("\n步驟 2: 參數優化搜尋...")
    global TRAIN_RATIO, TARGET_METRIC
    TRAIN_RATIO = args.train_ratio

    train_res, test_res = run_optimization_with_progress(df_raw)

    # Show top 5 train results
    print_results_table(train_res, "=== 樣本內優化結果 - 前 5 名最穩健參數組合 ===", top_n=5)

    # Show top 5 test results if available
    if not test_res.empty:
        print_results_table(test_res, "=== 樣本外驗證結果 - 前 5 名參數組合 ===", top_n=5)

    # Get best parameters
    best = train_res.iloc[0]
    best_period = int(best["ST_Period"])
    best_mult = float(best["ST_Multiplier"])
    best_ma = int(best["MA_Period"])
    best_use_hma = bool(best["Use_HMA_Filter"])

    print(f"\n>>> 最佳參數: ST({best_period}, {best_mult})")
    print(f">>> HMA 過濾: {'啟用 (週期=' + str(best_ma) + ')' if best_use_hma else '未啟用 (模式 1: 需 Crossover)'}")
    print(f">>> 目標指標 ({TARGET_METRIC}): {best['Custom Score']:.4f}")

    # -------------------------------------------------------------------------
    # Step 3: Backtest with Best Parameters
    # -------------------------------------------------------------------------
    print(f"\n步驟 3: 使用最佳參數執行完整回測...")

    df_indicators, _ = compute_supertrend(df_raw, period=best_period, multiplier=best_mult)

    if best_use_hma:
        df_indicators["HMA"] = compute_hma(df_indicators["Close"], period=best_ma)
        df_indicators["MA_Filter"] = df_indicators["Close"] > df_indicators["HMA"]
    else:
        df_indicators["MA_Filter"] = True

    df_indicators["ADX"] = compute_adx(df_indicators, period=14)
    df_indicators["ADX_Filter"] = df_indicators["ADX"] > 20  # Always available, but filter is off by default

    df_indicators["RSI"] = compute_rsi(df_indicators["Close"], period=14)
    df_indicators["RSI_Filter"] = (df_indicators["RSI"] > 30) & (df_indicators["RSI"] < 70)

    engine = BacktestEngine(df_indicators)
    trades, strat_equity, bench_equity = engine.run(
        long_only=True,
        stop_loss_pct=args.stop_loss,
        take_profit_pct=args.take_profit,
        commission_bps=args.commission,
        slippage_bps=args.slippage,
        position_sizing_mode="fixed_fraction"
    )

    print(f"  回測完成！已平倉交易筆數: {len(trades)}")

    # -------------------------------------------------------------------------
    # Step 4: Show All Transactions
    # -------------------------------------------------------------------------
    print_transactions(trades)

    # -------------------------------------------------------------------------
    # Step 5: Performance & Risk Metrics
    # -------------------------------------------------------------------------
    rm = RiskManager(trades, strat_equity)
    metrics = rm.calculate_metrics()
    print_performance_metrics(metrics)

    # Save optimal parameters and metrics to SQLite database
    loader.storage.save_supertrend_params(
        ticker=args.ticker,
        start_date=args.start,
        end_date=args.end,
        st_period=best_period,
        st_multiplier=best_mult,
        ma_period=best_ma,
        use_hma_filter=best_use_hma,
        custom_score=float(best["Custom Score"]) if "Custom Score" in best else None,
        cagr=metrics.get("CAGR"),
        max_drawdown=metrics.get("Max Drawdown"),
        sharpe_ratio=metrics.get("Sharpe Ratio"),
        calmar_ratio=metrics.get("Calmar Ratio"),
        win_rate=metrics.get("Win Rate"),
        profit_factor=metrics.get("Profit Factor")
    )

    # Save latest market state and trading signal to SQLite database
    last_row = df_indicators.iloc[-1]
    close_val = float(last_row["Close"])
    st_val = float(last_row["SuperTrend"])
    hma_val = float(last_row["HMA"]) if best_use_hma and "HMA" in df_indicators.columns and pd.notna(last_row["HMA"]) else 0.0

    is_long = close_val > st_val and (not best_use_hma or close_val > hma_val)
    db_pos = 1 if is_long else 0
    db_entry_ref = None if db_pos == 1 else st_val
    db_exit_ref = st_val if db_pos == 1 else None

    loader.storage.save_stock_signals(
        ticker=args.ticker,
        start_date=args.start,
        end_date=args.end,
        close_price=close_val,
        supertrend=st_val,
        position=db_pos,
        entry_ref=db_entry_ref,
        exit_ref=db_exit_ref,
        hma=hma_val
    )

    # Also show Monte Carlo if there are enough trades
    if len(trades) >= 10:
        print("步驟 6: Monte Carlo 風險模擬 (5000 次)...")
        mc_results = rm.run_monte_carlo(runs=5000, num_trades=min(50, len(trades)), seed=42)
        percentiles = mc_results["percentiles"]

        print(f"\n{'=' * 80}")
        print(f"Monte Carlo 5000 次模擬 - 最大回撤分位數")
        print(f"{'=' * 80}")
        for pct, val in percentiles.items():
            print(f"  {pct:20s}: {val * 100:.2f}%")
        print()

    print(f"\n{'=' * 80}")
    print(f"分析完成！")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
