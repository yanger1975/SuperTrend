# Batch Optimization Runner — 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 `run_batch_optimization.py`，自動收集交易標的（Most Active + Must Have），對每個標的並行跑參數優化與回測，輸出 Markdown 報告。

**Architecture:** 單一腳本 `run_batch_optimization.py`，引用 `spec/trending_scraper.py` 的 `TrendingScraper` 與 `src/` 的現有模組，使用 `concurrent.futures.ThreadPoolExecutor` 並行處理多個 ticker，每個 ticker 產出 `data/{yyyyMMdd}/{ticker}.md`。

**Tech Stack:** Python 3.8+, pandas, numpy, concurrent.futures, argparse, json

## Global Constraints

- 不修改現有 `src/` 模組與 `run_optimization.py`
- 不修改 `spec/trending_scraper.py`
- 不產生合併後的 ticker JSON 檔案
- 所有 ticker 共用同一組 `--start`、`--end`、`--interval`
- 優化參數 grid 沿用 `run_optimization.py` 的設定
- 輸出目錄: `data/{yyyyMMdd}/`
- 輸出格式: Markdown，對應 `run_optimization.py` 的全部 console 輸出

---

### Task 1: 建立腳本骨架與 CLI 參數解析

**Files:**
- Create: `run_batch_optimization.py`

**Interfaces:**
- Produces: `main()` function, CLI arg parsing with argparse

- [ ] **Step 1: 建立檔案並寫入骨架**

```python
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
"""

import argparse
import sys
import os
from datetime import datetime


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

    # TODO: 後續步驟將在此加入


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 驗證骨架可執行**

```bash
python run_batch_optimization.py --help
```

Expected: 顯示 argparse help 訊息，包含所有參數。

- [ ] **Step 3: 測試預設值行為**

```bash
python run_batch_optimization.py
```

Expected: 顯示 runner 資訊，日期為今天，無錯誤。

- [ ] **Step 4: Commit**

```bash
git add run_batch_optimization.py
git commit -m "feat: add batch optimization script skeleton with CLI parsing"
```

---

### Task 2: 實作 Ticker 收集邏輯

**Files:**
- Modify: `run_batch_optimization.py`

**Interfaces:**
- Consumes: CLI args from Task 1
- Produces: `collect_tickers() -> List[str]` — 合併去重後的 ticker 清單

- [ ] **Step 1: 加入 ticker 收集函數**

在 `run_batch_optimization.py` 的 `main()` 函數之前加入：

```python
import json
import logging

# 將 spec/ 加入 sys.path 以便 import TrendingScraper
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "spec"))
from trending_scraper import TrendingScraper


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
```

- [ ] **Step 2: 在 main() 中呼叫 collect_tickers()**

將 `main()` 中的 `# TODO: 後續步驟將在此加入` 替換為：

```python
    # Step 1: 收集 ticker 清單
    tickers = collect_tickers()
    if not tickers:
        print("錯誤: 沒有可處理的標的")
        sys.exit(1)
```

- [ ] **Step 3: 驗證 ticker 收集**

```bash
python run_batch_optimization.py
```

Expected: 顯示爬取結果、must_have 內容、合併清單。若網路不通則使用 fallback。

- [ ] **Step 4: Commit**

```bash
git add run_batch_optimization.py
git commit -m "feat: add ticker collection with TrendingScraper + must_have merge"
```

---

### Task 3: 實作單一 Ticker 優化與 Markdown 輸出

**Files:**
- Modify: `run_batch_optimization.py`

**Interfaces:**
- Consumes: `List[str]` tickers from Task 2
- Produces: `process_ticker(ticker, args) -> Dict[str, Any]` — 回傳處理結果 (success/failure + path)

- [ ] **Step 1: 加入優化參數常數與 Markdown 輔助函數**

在 `run_batch_optimization.py` 的 `collect_tickers()` 之後加入：

```python
import time
import pandas as pd
import numpy as np

from src.data_loader import DataLoader
from src.indicators import compute_supertrend, compute_hma, compute_adx, compute_rsi
from src.backtest_engine import BacktestEngine
from src.risk_manager import RiskManager
from src.optimizer import ParameterOptimizer

# 優化參數 grid (沿用 run_optimization.py)
ST_PERIODS = [5, 10, 15, 20, 25, 30]
ST_MULTIPLIERS = [2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
MA_PERIODS = [0, 25, 50, 75, 100, 125]
TRAIN_RATIO = 0.70
TARGET_METRIC = "Custom Score"

DISPLAY_COLS = [
    "ST_Period", "ST_Multiplier", "MA_Period", "Use_HMA_Filter",
    "Custom Score", "CAGR", "Max Drawdown", "Sharpe Ratio",
    "Calmar Ratio", "Win Rate", "Profit Factor"
]


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
    lines.append(f"- **HMA Filter**: {'啟用 (週期=' + str(best_ma) + ')' if best_use_hma else '未啟用 (模式 1: 需 Crossover)'}")
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
```

- [ ] **Step 2: 加入單一 ticker 處理函數**

在 `generate_markdown_report()` 之後加入：

```python
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
        trades, strat_equity, _ = engine.run(long_only=True)

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
```

- [ ] **Step 3: 驗證 import 與語法正確**

```bash
python -m py_compile run_batch_optimization.py
```

Expected: 無輸出（無錯誤）。

- [ ] **Step 4: Commit**

```bash
git add run_batch_optimization.py
git commit -m "feat: add single-ticker optimizer with markdown report generation"
```

---

### Task 4: 實作並行執行與摘要輸出

**Files:**
- Modify: `run_batch_optimization.py`

**Interfaces:**
- Consumes: `collect_tickers()`, `process_ticker()` from Tasks 2-3
- Produces: 完整 `main()` — 並行處理 + 摘要輸出

- [ ] **Step 1: 在 main() 中替換 TODO 為完整流程**

將 `main()` 函數中的這兩行：

```python
    # TODO: 後續步驟將在此加入
```

及其後續內容替換為：

```python
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
```

- [ ] **Step 2: 完整語法驗證**

```bash
python -m py_compile run_batch_optimization.py
```

Expected: 無輸出（無錯誤）。

- [ ] **Step 3: 用單一 ticker 快速測試**

```bash
python run_batch_optimization.py --start 2025-01-01 --workers 1
```

Expected:
- 爬取 Most Active（或 fallback）
- 合併 must_have.json
- 對每個 ticker 顯示進度
- 產出 `data/20260720/{ticker}.md` 檔案
- 輸出成功/失敗摘要

- [ ] **Step 4: 檢查 Markdown 輸出**

```bash
ls data/20260720/
head -50 data/20260720/SPY.md
```

Expected: 檔案存在，內容包含報告標題、表格、最佳參數等。

- [ ] **Step 5: Commit**

```bash
git add run_batch_optimization.py
git commit -m "feat: add parallel execution with ThreadPoolExecutor and summary output"
```
