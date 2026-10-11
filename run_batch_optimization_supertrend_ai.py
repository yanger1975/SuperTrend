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
from typing import Any, Optional, List, Dict

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

def collect_tickers(extra_tickers: list = None) -> tuple:
    """
    從 data/must_have.json (美股) 與 data/must_have_tw.json (台股/國內基金) 收集標的。
    回傳 (us_tickers, tw_tickers)。
    """
    must_have_us_path = "data/must_have.json"
    must_have_tw_path = "data/must_have_tw.json"

    us_tickers = []
    if os.path.exists(must_have_us_path):
        try:
            with open(must_have_us_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    us_tickers = [t for t in data if validate_ticker(t)]
        except Exception as e:
            print(f"載入 must_have.json 失敗: {e}")
    if not us_tickers:
        us_tickers = ["SPY", "QQQM", "SMH", "GLD", "VNQ", "DIVB", "SPMO"]

    tw_tickers = []
    if os.path.exists(must_have_tw_path):
        try:
            with open(must_have_tw_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    tw_tickers = [t for t in data if validate_ticker(t)]
        except Exception as e:
            print(f"載入 must_have_tw.json 失敗: {e}")
    if not tw_tickers:
        tw_tickers = ["0050.TW", "00935.TW", "33YTW.EZ", "25YTW.EZ", "10YTW.EZ"]

    if extra_tickers:
        for t in extra_tickers:
            if not validate_ticker(t):
                continue
            if t.upper().endswith((".TW", ".EZ")) or t.lower().endswith((".tw", ".ez")):
                if t not in tw_tickers:
                    tw_tickers.append(t)
            else:
                if t not in us_tickers:
                    us_tickers.append(t)

    # 去除重複並保留順序
    def dedupe(lst):
        seen = set()
        out = []
        for item in lst:
            if item not in seen:
                seen.add(item)
                out.append(item)
        return out

    return dedupe(us_tickers), dedupe(tw_tickers)


def export_latest_signals_to_json(results: list, output_path: str = "data/latest_signals_ai.json") -> str:
    """
    將最新計算出的訊號結果匯出為結構化的 JSON 檔案供版控與網頁儀表板讀取。
    支援 results 包含 processed_results 字典清單或 raw 結果字典清單。
    """
    output_records = []
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for item in results:
        if "raw" in item:
            r = item.get("raw", {})
            ticker = item.get("ticker", r.get("ticker", ""))
            display_name = item.get("display_name", ticker)
            is_fund = item.get("is_fund", False)
            pos_value = item.get("pos_value", "cash")
            distance_pct = item.get("distance_pct", 0.0)
        else:
            r = item
            ticker = r.get("ticker", "")
            display_name = ticker
            is_fund = ticker.upper().endswith(".EZ")
            if is_fund:
                try:
                    ez_s = EzMoneyScraper()
                    _, f_name, _ = ez_s.resolve_symbol(ticker)
                    if f_name and f_name != "未知基金":
                        display_name = f_name
                except Exception:
                    pass
            elif ticker.upper().endswith(".TW"):
                try:
                    from src.storage import SQLiteStorage
                    info = SQLiteStorage().get_ticker_info(ticker)
                    if info and info.get("name"):
                        display_name = info["name"]
                except Exception:
                    pass

            sig = r.get("latest_signal", {})
            pos_value = sig.get("position", "cash")
            close_val = sig.get("close", 0.0)
            entry_ref_val = sig.get("entry_ref", "-")
            exit_ref_val = sig.get("exit_ref", "-")
            try:
                c_p = float(close_val)
                r_p = float(exit_ref_val) if pos_value == "long" else float(entry_ref_val)
                distance_pct = (c_p - r_p) / r_p * 100.0 if r_p > 0 else 0.0
            except (ValueError, TypeError):
                distance_pct = 0.0

        sig = r.get("latest_signal", {})
        ticker_upper = ticker.upper()
        if ticker_upper.endswith(".TW") or ticker_upper.endswith(".EZ"):
            market = "tw"
            currency = "NT$"
        else:
            market = "us"
            currency = "$"

        close_val = sig.get("close", 0.0)
        entry_ref_val = sig.get("entry_ref", "-")
        exit_ref_val = sig.get("exit_ref", "-")
        action_val = sig.get("action", "HOLD_LONG" if pos_value == "long" else "WAIT_CASH")
        date_val = sig.get("date", datetime.now().strftime("%Y-%m-%d"))

        output_records.append({
            "ticker": ticker,
            "name": display_name,
            "market": market,
            "is_fund": is_fund,
            "date": date_val,
            "close": close_val,
            "currency": currency,
            "position": pos_value,
            "entry_ref": entry_ref_val,
            "exit_ref": exit_ref_val,
            "distance_pct": round(distance_pct, 2) if isinstance(distance_pct, (int, float)) else 0.0,
            "action": action_val,
            "updated_at": now_str
        })

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_records, f, indent=2, ensure_ascii=False)

    return output_path


def load_latest_signals_from_json(input_path: str = "data/latest_signals_ai.json") -> list:
    """從 JSON 檔案載入最新訊號清單，若檔案不存在或解析失敗則回傳空清單。"""
    if not os.path.exists(input_path):
        return []
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as e:
        print(f"讀取 {input_path} 失敗: {e}")
        return []


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

    valid_stock_dates = [s["date"] for s in valid_signals if not (s["ticker"].endswith(".EZ") or s["ticker"].endswith(".ez"))]
    if valid_stock_dates:
        latest_date = max(valid_stock_dates)
    elif valid_signals:
        latest_date = max(s["date"] for s in valid_signals)
    else:
        latest_date = args.date

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
    parser.add_argument("--tickers", nargs="+", help="指定執行的標的清單 (例如 SPY 0050.TW 33YTW.EZ)")

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

    us_tickers, tw_tickers = collect_tickers(args.tickers)
    tickers = us_tickers + tw_tickers
    if not tickers:
        print("錯誤: 沒有可處理的標的。請檢查 data/must_have.json 與 data/must_have_tw.json")
        sys.exit(1)

    print(f"開始並行處理 {len(tickers)} 個標的 (美股: {len(us_tickers)}, 台股/基金: {len(tw_tickers)})...")
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

        # 匯出最新訊號 JSON
        signals_json_path = "data/latest_signals_ai.json"
        export_latest_signals_to_json(results, signals_json_path)
        print(f"  OK  Latest Signals JSON -> {signals_json_path}")

        # 生成 GitHub Pages 靜態儀表板
        try:
            from src.supertrend_ai.html_generator import generate_dashboard_html, load_json_data
            opt_params = load_json_data("data/optimized_params_ai.json")
            latest_sigs = load_json_data(signals_json_path)
            html_out = generate_dashboard_html(signals=latest_sigs, params=opt_params, output_path="public/index.html")
            print(f"  OK  GitHub Pages Dashboard -> {html_out}")
        except Exception as e:
            print(f"  WARN 生成網頁儀表板失敗: {e}")

    print(f"報告目錄: data/{args.date.replace('-', '')}_AI/")

    if args.telegram or args.dry_run:
        is_saturday = args.force
        notifier = TelegramNotifier()

        # 分流美股與台股/基金結果
        us_results = [r for r in results if r.get("ticker") in us_tickers]
        tw_results = [r for r in results if r.get("ticker") in tw_tickers]
        # 防呆：未明確歸類的標的歸入美股
        other_results = [r for r in results if r.get("ticker") not in us_tickers and r.get("ticker") not in tw_tickers]
        if other_results:
            us_results.extend(other_results)

        market_reports = []
        if us_results:
            market_reports.append(("美股市場", build_telegram_ai_report(us_results, args, is_saturday, market_type="us")))
        if tw_results:
            market_reports.append(("台股與基金", build_telegram_ai_report(tw_results, args, is_saturday, market_type="tw")))

        if args.dry_run:
            print("\n==================== Telegram Report (Dry Run) ====================")
            for market_name, blocks in market_reports:
                chunks = notifier.split_blocks(blocks, max_length=3500)
                print(f"\n--- 【{market_name}】共 {len(chunks)} 個訊息分段 ---")
                for i, chunk in enumerate(chunks, 1):
                    print(f"--- Chunk {i}/{len(chunks)} ---")
                    print(chunk)
            print("===================================================================")
        else:
            if notifier.is_configured():
                print("發送 Telegram 診斷報告中 (依市場獨立發送)...")
                success_all = True
                for market_name, blocks in market_reports:
                    chunks = notifier.split_blocks(blocks, max_length=3500)
                    print(f"發送【{market_name}】訊息中 ({len(chunks)} 段)...")
                    for chunk in chunks:
                        if not notifier.send_message(chunk):
                            success_all = False
                if success_all:
                    print("Telegram 診斷報告成功發送！")
                else:
                    print("Telegram 診斷報告發送失敗（部分或全部）。")
            else:
                print("未偵測到 Telegram 憑證，無法發送。")

def build_telegram_ai_report(
    results: list,
    args: Any = None,
    is_saturday: bool = False,
    market_type: str = "all",
    dashboard_url: Optional[str] = None
) -> list:
    """產出 Telegram 格式的報告區塊，回傳 List[str] 給 TelegramNotifier 切分。"""
    ez_scraper = EzMoneyScraper()
    from src.storage import SQLiteStorage
    storage = SQLiteStorage()

    # 1. 預處理 results 並加上自訂排序欄位
    processed_results = []
    for r in results:
        if "raw" in r and "distance_pct" in r:
            processed_results.append(r)
            continue

        if not r.get("success"):
            continue

        ticker = r["ticker"]
        is_fund = ticker.endswith(".EZ") or ticker.endswith(".ez")

        display_name = ticker
        if is_fund:
            _, fund_name, _ = ez_scraper.resolve_symbol(ticker)
            display_name = fund_name if fund_name != "未知基金" else ticker
        elif ticker.upper().endswith(".TW"):
            try:
                info = storage.get_ticker_info(ticker)
                tw_name = info.get("name") if info else None
                display_name = f"{tw_name} ({ticker})" if tw_name else ticker
            except Exception:
                display_name = ticker

        sig = r.get("latest_signal", {})
        pos_value = sig.get("position", "cash")
        close_price_str = sig.get("close", "0")
        entry_ref_str = sig.get("entry_ref", "0")
        exit_ref_str = sig.get("exit_ref", "0")

        try:
            close_price = float(close_price_str)
        except ValueError:
            close_price = 0.0

        if pos_value == "long":
            try:
                ref_price = float(exit_ref_str)
            except ValueError:
                ref_price = 1.0
        else:
            try:
                ref_price = float(entry_ref_str)
            except ValueError:
                ref_price = 1.0

        # 避免除以零
        if ref_price <= 0:
            ref_price = 1.0

        distance_pct = (close_price - ref_price) / ref_price * 100.0

        processed_results.append({
            "raw": r,
            "ticker": ticker,
            "display_name": display_name,
            "is_fund": is_fund,
            "pos_value": pos_value,
            "distance_pct": distance_pct
        })

    # 2. 依照距離百分比由大到小排序
    processed_results.sort(key=lambda x: x["distance_pct"], reverse=True)

    blocks = []
    if market_type == "us":
        blocks.append("📊 <b>Supertrend AI 指標計算結果 (美股市場)</b> 📊")
    elif market_type == "tw":
        blocks.append("📊 <b>Supertrend AI 指標計算結果 (台股與基金)</b> 📊")
    else:
        blocks.append("📊 <b>Supertrend AI 指標計算結果</b> 📊")

    stock_dates = [
        r["raw"]["latest_signal"]["date"]
        for r in processed_results
        if not r["is_fund"] and r["raw"].get("latest_signal", {}).get("date")
    ]
    all_dates = [
        r["raw"]["latest_signal"]["date"]
        for r in processed_results
        if r["raw"].get("latest_signal", {}).get("date")
    ]
    if stock_dates:
        latest_date = max(stock_dates)
    elif all_dates:
        latest_date = max(all_dates)
    elif args and hasattr(args, "date") and args.date:
        latest_date = args.date
    else:
        latest_date = datetime.now().strftime("%Y-%m-%d")

    if is_saturday:
        blocks.append(f"📅 <b>市場資料日</b>：{latest_date} (優化報告)")
    else:
        blocks.append(f"📅 <b>市場資料日</b>：{latest_date}")

    for item in processed_results:
        r = item["raw"]
        ticker = item["ticker"]
        display_name = item["display_name"]
        is_fund = item["is_fund"]
        pos_value = item["pos_value"]
        distance_pct = item["distance_pct"]

        # 多單與空手的圖示
        icon = "🟢" if pos_value == "long" else "⚪"
        curr = "NT$" if (is_fund or ticker.upper().endswith(".TW")) else "$"

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
                f"{icon} 【{display_name}】| {start_d} ~ {end_d}\n"
                f"ATR: {atr} | Factor: {f_min}~{f_max} ({f_step}) | Alpha: {alpha} | Cluster: {cluster} | Score: {score:.2f}\n"
                f"距標: {distance_pct:+.2f}%"
            )
            blocks.append(block)
        else:
            # 平日 (一至五) 報告格式
            sig = r.get("latest_signal", {})
            close_price = sig.get("close", "")
            entry_ref = sig.get("entry_ref", "-")
            exit_ref = sig.get("exit_ref", "-")
            sig_date = sig.get("date", "")
            date_note = f" ({sig_date})" if sig_date and sig_date != latest_date else ""

            close_display = f"{curr}{close_price}" if close_price and not str(close_price).startswith(("$", "NT$")) else close_price
            if exit_ref != "-" and not str(exit_ref).startswith(("$", "NT$")):
                exit_display = f"{curr}{exit_ref}"
            else:
                exit_display = exit_ref

            if entry_ref != "-" and not str(entry_ref).startswith(("$", "NT$")):
                entry_display = f"{curr}{entry_ref}"
            else:
                entry_display = entry_ref

            if pos_value == "long":
                pos = "做多 (Long)"
                ref_str = f"出場建議價：{exit_display}"
            else:
                pos = "觀望 (Wait)"
                ref_str = f"進場建議價：{entry_display}"

            price_label = "最新淨值" if is_fund else "最新收盤"

            block = (
                f"{icon} 【{display_name}】{date_note}\n"
                f"倉位：{pos} (距標 {distance_pct:+.2f}%)\n"
                f"{price_label}：{close_display}\n"
                f"{ref_str}"
            )
            blocks.append(block)

    # 若有設定 GitHub Pages 儀表板網址，附加於報告結尾
    url = dashboard_url or os.environ.get("GITHUB_PAGES_URL")
    if url:
        blocks.append(f'🔗 <a href="{url}">查看即時網頁儀表板 (Dashboard)</a>')

    return blocks


build_telegram_blocks_ai = build_telegram_ai_report

if __name__ == "__main__":
    main()
