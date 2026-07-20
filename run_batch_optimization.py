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
import logging
import sys
import os
from datetime import datetime

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


if __name__ == "__main__":
    main()