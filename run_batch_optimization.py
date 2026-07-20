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