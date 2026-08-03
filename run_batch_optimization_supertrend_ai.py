#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SuperTrend AI Batch Optimization Runner
=======================================
批次對多檔標的（來自 data/must_have.json）執行 SuperTrend AI 策略參數優化與回測。
會將最新的一筆優化結果儲存到資料庫中，並輸出彙整的 All_AI.md 狀態報表。

Usage:
    python run_batch_optimization_supertrend_ai.py
    python run_batch_optimization_supertrend_ai.py --force
    python run_batch_optimization_supertrend_ai.py --workers 8 --date 20260803
"""

import sys
import os
import json
import argparse
import traceback
from datetime import datetime, timedelta
import pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed
from dateutil.relativedelta import relativedelta

# Ensure stdout supports UTF-8 (e.g. for printing emojis on Windows console)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.supertrend_ai.optimizer import optimize_supertrend_ai
from src.supertrend_ai.backtest import run_supertrend_ai_backtest
from src.supertrend_ai.reporter import generate_supertrend_ai_report
from src.supertrend_ai.db_setup import query_supertrend_ai_params, import_supertrend_ai_params_from_json
from src.data_loader import DataLoader
from src.telegram_notifier import TelegramNotifier
from src.scrapers.ezmoney_scraper import EzMoneyScraper

def validate_ticker(ticker: str) -> bool:
    if not ticker or not isinstance(ticker, str): return False
    ticker = ticker.strip()
    if not ticker or any(c in ticker for c in [" ", "\t", "\n"]) or len(ticker) > 20: return False
    return True

def collect_tickers() -> list:
    must_have_path = "data/supertrend_ai_tickers.json"
    if not os.path.exists(must_have_path):
        print(f"錯誤: 找不到 {must_have_path}")
        return []
        
    with open(must_have_path, "r", encoding="utf-8") as f:
        tickers = json.load(f)
        
    # 去除重複並保留順序，並進行基本驗證
    seen = set()
    unique_tickers = []
    for t in tickers:
        if t not in seen and validate_ticker(t):
            seen.add(t)
            unique_tickers.append(t)
            
    return unique_tickers

def generate_all_summary_report(results: list, args) -> str:
    """產生包含所有標的市場狀態與交易訊號的 All_AI.md 報告。"""
    valid_signals = []
    for r in results:
        if r.get("success") and r.get("latest_signal"):
            sig = r["latest_signal"]
            pos_order = 0 if sig["position"] == "long" else 1
            valid_signals.append({
                "ticker": r["ticker"],
                "date": sig["date"],
                "close": sig["close"],
                "position": sig["position_str"],
                "entry_ref": sig["entry_ref"],
                "exit_ref": sig["exit_ref"],
                "pos_order": pos_order
            })

    # 排序：Long 排在最前面，同部位群內按 Ticker 字母排序
    valid_signals.sort(key=lambda x: (x["pos_order"], x["ticker"]))

    if args.date is None:
        args.date = datetime.now().strftime("%Y-%m-%d")
        
    latest_date = valid_signals[0]["date"] if valid_signals else args.date

    lines = []
    lines.append("# SuperTrend AI 全標的市場狀態與交易訊號總覽")
    lines.append("")
    lines.append(f"**報表產生日期**: {latest_date}")
    lines.append("")
    lines.append("| Ticker | Close Price | Position | Entry Ref (Breakout) | Exit Ref (Stop Loss) |")
    lines.append("|--------|-------------|----------|----------------------|----------------------|")

    for item in valid_signals:
        lines.append(
            f"| {item['ticker']} | {item['close']} | {item['position']} | "
            f"{item['entry_ref']} | {item['exit_ref']} |"
        )
    lines.append("")
    return "\n".join(lines)


def process_ticker(ticker, args):
    """
    對單一 ticker 執行完整優化 + 回測流程，產出 Markdown 報告。
    """
    print(f"[{ticker}] 開始處理...")
    try:
        start_date = (datetime.now() - relativedelta(years=5)).strftime("%Y-%m-%d")
        end_date = datetime.now().strftime("%Y-%m-%d")
        
        loader = DataLoader()
        df = loader.fetch_data(ticker, start_date=start_date, end_date=end_date)
            
        if not df.empty:
            df.index = pd.to_datetime(df.index)
            df.dropna(inplace=True)
        
        if df.empty:
            raise ValueError("下載的資料為空")
            
        # 檢查資料庫是否有既有參數
        db_params = None
        if not args.force:
            existing_df = query_supertrend_ai_params(ticker)
            if not existing_df.empty:
                db_params = existing_df.iloc[0].to_dict()
                print(f"[{ticker}] 發現既有參數，跳過優化。")

        # 如果強制更新或沒有參數，執行優化
        if db_params is None:
            # 判斷是否為基金
            is_fund = ticker.endswith(".EZ") or ticker.endswith(".ez")
            asset_type = "fund" if is_fund else "stock"

            print(f"[{ticker}] 開始執行優化 (Asset Type: {asset_type})...")
            res_df, best_params = optimize_supertrend_ai(
                df=df,
                ticker=ticker,
                start_date=start_date,
                end_date=end_date,
                lengths=[10, 14, 20],
                min_mults=[1.0, 1.5, 2.0],
                max_mults=[3.0, 4.0, 5.0],
                steps=[0.5],
                perf_alphas=[5, 10.0, 20],
                clusters=['Best', 'Average'],
                update_freqs=[1],
                long_onlys=[True],
                asset_type=asset_type
            )
            # 因為 optimize_supertrend_ai 已經呼叫 save_supertrend_ai_params 儲存了，
            # 我們前面也已經在 db_setup 中加了 DELETE，所以這裡會確保只留一筆
            used_params = best_params
            opt_results = res_df
        else:
            used_params = db_params
            # 需要把名稱轉回適合 backtest 的變數
            if 'cagr' in used_params and 'CAGR' not in used_params:
                used_params['CAGR'] = used_params.pop('cagr')
                used_params['Max Drawdown'] = used_params.pop('max_drawdown')
                used_params['Sharpe Ratio'] = used_params.pop('sharpe_ratio')
                used_params['Calmar Ratio'] = used_params.pop('calmar_ratio')
                used_params['Win Rate'] = used_params.pop('win_rate')
                used_params['Profit Factor'] = used_params.pop('profit_factor')
                used_params['Custom Score'] = used_params.pop('custom_score')
            opt_results = pd.DataFrame([used_params]) # 為了報告顯示

        # 如果不是強制更新，我們前面沒有宣告 asset_type，所以在這裡補判斷
        if db_params is not None:
            is_fund = ticker.endswith(".EZ") or ticker.endswith(".ez")
            asset_type = "fund" if is_fund else "stock"

        # 回測與狀態擷取
        trades, equity, benchmark, df_ind, metrics = run_supertrend_ai_backtest(
            df=df,
            length=int(used_params['atr_length']),
            min_mult=float(used_params['factor_min']),
            max_mult=float(used_params['factor_max']),
            step=float(used_params['factor_step']),
            perf_alpha=float(used_params['perf_alpha']),
            from_cluster=used_params['from_cluster'],
            update_freq=int(used_params['update_freq']),
            long_only=bool(used_params.get('long_only', True)),
            show_progress=False,
            asset_type=asset_type
        )

        last_row = df_ind.iloc[-1]
        last_idx = df_ind.index[-1]
        latest_date_str = last_idx.strftime("%Y-%m-%d") if hasattr(last_idx, "strftime") else str(last_idx)[:10]

        current_price = float(last_row['Close'])
        trend_dir = last_row['Trend']
        st_line = float(last_row['SuperTrend_AI'])

        if trend_dir == 1:
            position = "long"
            position_str = "【多單持有中】"
            entry_ref = "-"
            exit_ref = f"{st_line:.2f}"
        else:
            position = "cash"
            position_str = "【空手觀望】"
            entry_ref = f"{st_line:.2f}"
            exit_ref = "-"

        latest_signal = {
            "date": latest_date_str,
            "close": f"{current_price:.2f}",
            "position": position,
            "position_str": position_str,
            "entry_ref": entry_ref,
            "exit_ref": exit_ref
        }

        # 輸出單一標的 Markdown
        out_dir = os.path.join("data", f"{args.date.replace('-', '')}_AI")
        md_report = generate_supertrend_ai_report(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            df_ind=df_ind,
            trades=trades,
            equity=equity,
            benchmark=benchmark,
            opt_results=opt_results,
            best_params=used_params,
            report_dir=out_dir
        )
        
        safe_ticker_name = "".join(c for c in ticker if c.isalnum() or c in ".-_")
        out_path = os.path.join(out_dir, f"{safe_ticker_name}_AI.md")

        used_params["start_date"] = start_date
        used_params["end_date"] = end_date
        # 統一處理 custom_score 的 key 大小寫
        if "Custom Score" in used_params and "custom_score" not in used_params:
            used_params["custom_score"] = used_params["Custom Score"]
            
        print(f"[{ticker}] 報告已輸出: {out_path} ({position_str})")
        return {"ticker": ticker, "success": True, "path": out_path, "error": None, "latest_signal": latest_signal, "opt_params": used_params}

    except Exception as e:
        err_msg = traceback.format_exc()
        print(f"[{ticker}] 處理失敗: {e}\n{err_msg}")
        return {"ticker": ticker, "success": False, "path": None, "error": str(e), "latest_signal": None, "opt_params": {}}


def main():
    parser = argparse.ArgumentParser(description="SuperTrend AI 批次自動優化與回測腳本")
    parser.add_argument("--force", action="store_true", help="強制重新進行網格優化（無視資料庫既有紀錄）")
    parser.add_argument("--workers", type=int, default=4, help="並行處理的 worker 數量 (預設: 4)")
    parser.add_argument("--date", type=str, default=None, help="輸出目錄的日期鍵 YYYY-MM-DD (預設: 今天)")
    parser.add_argument("--telegram", action="store_true", help="執行完畢後發送 Telegram 通知")
    parser.add_argument("--dry-run", action="store_true", help="僅印出 Telegram 報告內容，不實際發送")
    
    args = parser.parse_args()
    
    if args.date is None:
        args.date = datetime.now().strftime("%Y-%m-%d")
        
    print(f"SuperTrend AI Batch Optimization Runner")
    print(f"  強制優化: {'是' if args.force else '否 (從資料庫載入既有參數)'}")
    print(f"  輸出目錄: data/{args.date.replace('-', '')}_AI/")
    print(f"  並行數:   {args.workers}")
    print()
    
    if not args.force:
        print("嘗試從 JSON 匯入既有參數到本地資料庫 (若是全新的 CI 環境)...")
        import_supertrend_ai_params_from_json()
    
    tickers = collect_tickers()
    if not tickers:
        print("錯誤: 沒有可處理的標的。請檢查 data/supertrend_ai_tickers.json")
        sys.exit(1)
        
    print(f"開始並行處理 {len(tickers)} 個標的...")
    print("=" * 60)
    
    results = []
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(process_ticker, ticker, args): ticker
            for ticker in tickers
        }
        for future in as_completed(futures):
            results.append(future.result())
            
    print("\n" + "=" * 60)
    print("批次處理完成！")
    print("=" * 60)
    
    success = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]
    
    print(f"總計: {len(results)} 個標的")
    print(f"成功: {len(success)} 個")
    print(f"失敗: {len(failed)} 個")
    if failed:
        for r in failed:
            print(f"  FAIL {r['ticker']} -> {r['error']}")
            
    if success:
        all_md_content = generate_all_summary_report(results, args)
        all_md_path = os.path.join("data", f"{args.date.replace('-', '')}_AI", "All_AI.md")
        with open(all_md_path, "w", encoding="utf-8") as f:
            f.write(all_md_content)
        print(f"  OK  All Summary -> {all_md_path}")
        
        
    print(f"報告目錄: data/{args.date.replace('-', '')}_AI/")

    if args.telegram or args.dry_run:
        # 當傳入 --force 時，視為「週六強制優化」模式
        is_saturday = args.force
        blocks = build_telegram_ai_report(results, args, is_saturday)
        
        notifier = TelegramNotifier()
        chunks = notifier.split_blocks(blocks, max_length=3500)
        
        if args.dry_run:
            print("\n==================== Telegram Report (Dry Run) ====================")
            for i, chunk in enumerate(chunks, 1):
                print(f"--- Chunk {i}/{len(chunks)} ---")
                print(chunk)
            print("===================================================================")
        else:
            if notifier.is_configured():
                print("發送 Telegram 診斷報告中...")
                success_all = True
                for chunk in chunks:
                    if not notifier.send_message(chunk):
                        success_all = False
                if success_all:
                    print("Telegram 診斷報告成功發送！")
                else:
                    print("Telegram 診斷報告發送失敗（部分或全部）。")
            else:
                print("未偵測到 Telegram 憑證，無法發送。")

def build_telegram_ai_report(results: list, args, is_saturday: bool) -> list:
    """產出 Telegram 格式的報告區塊，回傳 List[str] 給 TelegramNotifier 切分。"""
    ez_scraper = EzMoneyScraper()
    
    blocks = []
    latest_date = args.date
    if results and results[0].get("latest_signal"):
        latest_date = results[0]["latest_signal"]["date"]

    if is_saturday:
        blocks.append(f"📅 計算日期：{latest_date} (優化報告)")
    else:
        blocks.append(f"📅 計算日期：{latest_date}")

    for r in results:
        if not r.get("success"):
            continue
            
        ticker = r["ticker"]
        is_fund = ticker.endswith(".EZ") or ticker.endswith(".ez")
        
        display_name = ticker
        if is_fund:
            _, fund_name, _ = ez_scraper.resolve_symbol(ticker)
            display_name = fund_name if fund_name != "未知基金" else ticker

        if is_saturday:
            # 週六 (強制優化) 報告格式
            opt_params = r.get("opt_params", {})
            start_d = opt_params.get("start_date", "")
            end_d = opt_params.get("end_date", "")
            atr = opt_params.get("atr_length", "")
            f_min = opt_params.get("factor_min", "")
            f_max = opt_params.get("factor_max", "")
            f_step = opt_params.get("factor_step", "")
            alpha = opt_params.get("perf_alpha", "")
            cluster = opt_params.get("from_cluster", "")
            score = opt_params.get("custom_score", 0.0)
            
            block = (
                f"【{display_name}】| {start_d} ~ {end_d}\n"
                f"ATR: {atr} | Factor: {f_min}~{f_max} ({f_step}) | Alpha: {alpha} | Cluster: {cluster} | Score: {score:.2f}"
            )
            blocks.append(block)
        else:
            # 平日 (一至五) 報告格式
            sig = r.get("latest_signal", {})
            pos_value = sig.get("position", "cash")
            pos = "做多 (Long)" if pos_value == "long" else "觀望 (Wait)"
            close_price = sig.get("close", "")
            entry_ref = sig.get("entry_ref", "-")
            exit_ref = sig.get("exit_ref", "-")
            
            if pos_value == "long":
                ref_str = f"出場建議價：{exit_ref}"
            else:
                ref_str = f"進場建議價：{entry_ref}"
                
            price_label = "最新淨值" if is_fund else "最新收盤"
            
            block = (
                f"【{display_name}】\n"
                f"倉位：{pos}\n"
                f"{price_label}：{close_price}\n"
                f"{ref_str}"
            )
            blocks.append(block)

    return blocks

if __name__ == "__main__":
    main()
