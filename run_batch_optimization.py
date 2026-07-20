#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Batch Optimization Runner
==========================
自動收集交易標的（Most Active + Must Have），對每個標的並行跑參數優化與回測，
輸出 Markdown 報告到 data/{yyyyMMdd}/{ticker}.md。

Usage:
    python run_batch_optimization.py --start 2020-01-01
    python run_batch_optimization.py --date 20260720 --workers 8
    python run_batch_optimization.py --start 2018-01-01 --end 2026-06-30 --interval 1d
"""

import argparse
import json
import sys
import os
from datetime import datetime
from typing import List, Dict, Any
import pandas as pd
import numpy as np

# 將 spec/ 加入 sys.path 以便 import TrendingScraper
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "spec"))
from trending_scraper import TrendingScraper

# Import src modules
from src.data_loader import DataLoader
from src.indicators import compute_supertrend, compute_hma
from src.backtest_engine import BacktestEngine
from src.risk_manager import RiskManager
from src.optimizer import ParameterOptimizer

# ============================================================================
# Configuration: Optimization Parameter Grids (from run_optimization.py)
# ============================================================================
ST_PERIODS = [5, 10, 15, 20, 25, 30]
ST_MULTIPLIERS = [2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
MA_PERIODS = [0, 25, 50, 75, 100, 125]  # 0 = no HMA filter
TRAIN_RATIO = 0.70
TARGET_METRIC = "Custom Score"

DISPLAY_COLS = [
    "ST_Period", "ST_Multiplier", "MA_Period", "Use_HMA_Filter",
    "Custom Score", "CAGR", "Max Drawdown", "Sharpe Ratio",
    "Calmar Ratio", "Win Rate", "Profit Factor"
]


# ============================================================================
# Markdown Helper Functions
# ============================================================================
def dataframe_to_markdown_table(df, columns, fmt_map=None):
    """將 DataFrame 前 5 列轉成 Markdown 表格字串。"""
    if fmt_map is None:
        fmt_map = {}

    lines = []
    # Header
    lines.append("| " + " | ".join(columns) + " |")
    # Separator
    lines.append("|" + "|".join(["---"] * len(columns)) + "|")
    # Data rows (top 5)
    for _, row in df[columns].head(5).iterrows():
        vals = []
        for col in columns:
            val = row[col]
            if col in fmt_map:
                vals.append(fmt_map[col](val))
            else:
                vals.append(str(val))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def format_metric_md(value, pct_fmt=False):
    """Format metric for markdown display."""
    if pd.isna(value):
        return "N/A"
    if pct_fmt:
        return f"{value * 100:.2f}%"
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    if abs(value) >= 100:
        return f"{value:.1f}"
    if abs(value) >= 10:
        return f"{value:.2f}"
    return f"{value:.3f}"


def generate_markdown_report(ticker, args, train_df, test_df, best_row,
                              trades, metrics, mc_results):
    """產生完整的 Markdown 報告字串。"""
    lines = []
    lines.append(f"# {ticker} 優化回測報告")
    lines.append("")
    lines.append(f"**執行日期**: {args.date}")
    lines.append(f"**資料區間**: {args.start} ~ {args.end}")
    lines.append(f"**Train/Test 分割**: {TRAIN_RATIO:.0%}")
    lines.append("")

    # --- In-sample Top 5 ---
    lines.append("## 參數優化結果 - 樣本內 Top 5")
    lines.append("")
    if not train_df.empty:
        train_fmt = {
            "CAGR": lambda v: format_metric_md(v, True),
            "Max Drawdown": lambda v: format_metric_md(v, True),
            "Win Rate": lambda v: format_metric_md(v, True),
            "Custom Score": lambda v: format_metric_md(v),
            "Sharpe Ratio": lambda v: format_metric_md(v),
            "Calmar Ratio": lambda v: format_metric_md(v),
            "Profit Factor": lambda v: format_metric_md(v),
            "MA_Period": lambda v: f"HMA({int(v)})" if v > 0 else "None",
            "Use_HMA_Filter": lambda v: "Yes" if v else "No",
        }
        lines.append(dataframe_to_markdown_table(train_df, DISPLAY_COLS, fmt_map=train_fmt))
    else:
        lines.append("無結果")
    lines.append("")

    # --- Out-of-sample Top 5 ---
    lines.append("## 參數優化結果 - 樣本外 Top 5")
    lines.append("")
    if not test_df.empty:
        test_fmt = train_fmt
        lines.append(dataframe_to_markdown_table(test_df, DISPLAY_COLS, fmt_map=test_fmt))
    else:
        lines.append("無結果")
    lines.append("")

    # --- Best Parameters ---
    lines.append("## 最佳參數")
    lines.append("")
    best_period = int(best_row["ST_Period"])
    best_mult = float(best_row["ST_Multiplier"])
    best_ma = int(best_row["MA_Period"])
    best_use_hma = bool(best_row["Use_HMA_Filter"])
    lines.append(f"- **SuperTrend**: ({best_period}, {best_mult})")
    lines.append(f"- **HMA 過濾**: {'啟用 (週期=' + str(best_ma) + ')' if best_use_hma else '未啟用 (模式 1: 需 Crossover)'}")
    lines.append(f"- **目標指標 ({TARGET_METRIC})**: {best_row['Custom Score']:.4f}")
    lines.append("")

    # --- Transaction History ---
    lines.append("## 完整交易紀錄")
    lines.append("")
    if trades:
        lines.append("| 序號 | 方向 | 進場日期 | 進場價 | 出場日期 | 出場價 | 損益(%) | 離場原因 |")
        lines.append("|------|------|---------|--------|---------|--------|--------|---------|")
        for idx, t in enumerate(trades, 1):
            entry_d = t.entry_date.strftime("%Y-%m-%d")
            exit_d = t.exit_date.strftime("%Y-%m-%d") if t.exit_date else "未平倉"
            exit_p = f"{t.exit_price:.2f}" if t.exit_price else "未平倉"
            lines.append(
                f"| {idx} | {t.direction} | {entry_d} | {t.entry_price:.2f} | "
                f"{exit_d} | {exit_p} | {t.pnl_pct * 100:.2f}% | {t.exit_reason} |"
            )
    else:
        lines.append("無交易記錄")
    lines.append("")

    # --- Performance Metrics ---
    lines.append("## 績效與風險指標")
    lines.append("")
    if metrics:
        lines.append("| 指標 | 數值 |")
        lines.append("|------|------|")
        pct_keys = {"CAGR", "Max Drawdown", "Ulcer Index", "Win Rate", "Expectancy"}
        for key, val in metrics.items():
            if isinstance(val, float):
                if key in pct_keys:
                    lines.append(f"| {key} | {val * 100:.2f}% |")
                else:
                    lines.append(f"| {key} | {val:.2f} |")
            else:
                lines.append(f"| {key} | {val} |")
    lines.append("")

    # --- Monte Carlo ---
    lines.append("## Monte Carlo 模擬 (5000次)")
    lines.append("")
    if mc_results:
        lines.append("| 分位數 | 最大回撤 |")
        lines.append("|--------|---------|")
        for pct_label, val in mc_results["percentiles"].items():
            lines.append(f"| {pct_label} | {val * 100:.2f}% |")
    lines.append("")

    return "\n".join(lines)


def collect_tickers() -> list:
    """
    收集交易標的清單：
    1. 從 TrendingScraper 爬取 Most Active 股票 (含 fallback 機制)
    2. 與 must_have.json 合併去重
    3. 回傳最終 ticker 清單
    """
    # Step 1: 爬取 Most Active
    print("Step 1: 收集交易標的清單...")
    scraper = TrendingScraper(fallback_file="data/most-active.json")
    tickers = scraper.fetch_top_tickers(limit=10)
    print(f"  爬取 Most Active: {len(tickers)} 個標的")
    print(f"  Tickers: {', '.join(tickers)}")

    # Step 2: 讀取 must_have.json
    must_have_path = "data/must_have.json"
    must_have = []
    if os.path.exists(must_have_path):
        with open(must_have_path, "r", encoding="utf-8") as f:
            must_have = json.load(f)
        print(f"  Must Have: {len(must_have)} 個標的 ({', '.join(must_have)})")

    # Step 3: 合併去重 (保持順序：must_have 在前，most-active 在後)
    seen = set()
    merged = []
    for t in must_have + tickers:
        if t not in seen:
            seen.add(t)
            merged.append(t)

    print(f"  合併後總計: {len(merged)} 個標的")
    print(f"  最終清單: {', '.join(merged)}")
    print()
    return merged


def process_ticker(ticker, args):
    """
    對單一 ticker 執行完整優化 + 回測流程，產出 Markdown 報告。
    回傳 {"ticker": str, "success": bool, "path": str|None, "error": str|None}
    """
    print(f"[{ticker}] 開始處理...")
    try:
        # 3a. 下載/載入資料
        loader = DataLoader()
        df_raw = loader.fetch_data(
            ticker=ticker,
            start_date=args.start,
            end_date=args.end,
            interval=args.interval
        )
        print(f"[{ticker}] 資料載入完成: {len(df_raw)} 筆")

        # 3b. 參數優化
        optimizer = ParameterOptimizer(df_raw)
        train_df, test_df = optimizer.optimize(
            st_periods=ST_PERIODS,
            st_multipliers=ST_MULTIPLIERS,
            ma_periods=MA_PERIODS,
            target_metric=TARGET_METRIC,
            train_ratio=TRAIN_RATIO
        )

        if train_df.empty:
            raise ValueError("優化未產生任何結果")

        best = train_df.iloc[0]
        print(f"[{ticker}] 最佳參數: ST({int(best['ST_Period'])}, {float(best['ST_Multiplier'])}) "
              f"HMA={int(best['MA_Period']) if bool(best['Use_HMA_Filter']) else 'None'} "
              f"Score={best['Custom Score']:.4f}")

        # 3c. 完整回測
        best_period = int(best["ST_Period"])
        best_mult = float(best["ST_Multiplier"])
        best_ma = int(best["MA_Period"])
        best_use_hma = bool(best["Use_HMA_Filter"])

        df_indicators, _ = compute_supertrend(df_raw, period=best_period, multiplier=best_mult)

        if best_use_hma:
            df_indicators["HMA"] = compute_hma(df_indicators["Close"], period=best_ma)
            df_indicators["MA_Filter"] = df_indicators["Close"] > df_indicators["HMA"]
        else:
            df_indicators["MA_Filter"] = True

        engine = BacktestEngine(df_indicators)
        trades, strat_equity, _ = engine.run(
            long_only=True,
            stop_loss_pct=0.0,
            take_profit_pct=0.0,
            commission_bps=10.0,
            slippage_bps=5.0,
            position_sizing_mode="fixed_fraction"
        )

        rm = RiskManager(trades, strat_equity)
        metrics = rm.calculate_metrics()

        # Monte Carlo
        mc_results = None
        if len(trades) >= 10:
            mc_results = rm.run_monte_carlo(runs=5000, num_trades=min(50, len(trades)), seed=42)

        # 3d. 產出 Markdown
        out_dir = os.path.join("data", args.date)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{ticker}.md")

        report = generate_markdown_report(
            ticker, args, train_df, test_df, best,
            trades, metrics, mc_results
        )

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(report)

        print(f"[{ticker}] 報告已輸出: {out_path}")
        return {"ticker": ticker, "success": True, "path": out_path, "error": None}

    except Exception as e:
        print(f"[{ticker}] 處理失敗: {e}")
        return {"ticker": ticker, "success": False, "path": None, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(
        description="Batch Optimization Runner — 多標的自動優化與回測",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_batch_optimization.py --start 2020-01-01
  python run_batch_optimization.py --date 20260720 --workers 8
  python run_batch_optimization.py --start 2018-01-01 --end 2026-06-30 --interval 1d
        """
    )
    parser.add_argument("--date", type=str, default=None,
                        help="輸出目錄的日期鍵 yyyyMMdd (預設: 今天)")
    parser.add_argument("--start", type=str, default="2020-01-01",
                        help="歷史資料起始日 YYYY-MM-DD (預設: 2020-01-01)")
    parser.add_argument("--end", type=str, default=None,
                        help="歷史資料結束日 YYYY-MM-DD (預設: 今天)")
    parser.add_argument("--interval", type=str, default="1d",
                        choices=["1d", "1h", "60m"],
                        help="K 線週期 (預設: 1d)")
    parser.add_argument("--workers", type=int, default=4,
                        help="並行處理的 worker 數量 (預設: 4)")

    args = parser.parse_args()

    # 設定預設值
    if args.date is None:
        args.date = datetime.now().strftime("%Y%m%d")
    if args.end is None:
        args.end = datetime.now().strftime("%Y-%m-%d")

    print(f"Batch Optimization Runner")
    print(f"  輸出目錄: data/{args.date}/")
    print(f"  資料區間: {args.start} ~ {args.end}")
    print(f"  K 線週期: {args.interval}")
    print(f"  並行數:   {args.workers}")
    print()

    # Step 1: 收集 ticker 清單
    tickers = collect_tickers()
    if not tickers:
        print("錯誤: 沒有可處理的標的")
        sys.exit(1)

    # Step 2: 並行處理所有 ticker
    print(f"Step 2: 開始並行處理 {len(tickers)} 個標的 (workers={args.workers})...")
    print("=" * 60)

    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(process_ticker, ticker, args): ticker
            for ticker in tickers
        }
        for future in as_completed(futures):
            result = future.result()
            results.append(result)

    # Step 3: 輸出摘要
    print()
    print("=" * 60)
    print("批次處理完成！")
    print("=" * 60)

    success = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]

    print(f"總計: {len(results)} 個標的")
    print(f"成功: {len(success)} 個")
    if success:
        for r in success:
            print(f"  OK  {r['ticker']} -> {r['path']}")

    print(f"失敗: {len(failed)} 個")
    if failed:
        for r in failed:
            print(f"  FAIL {r['ticker']} -> {r['error']}")

    print(f"報告目錄: data/{args.date}/")


if __name__ == "__main__":
    main()