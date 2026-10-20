#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SuperTrend AI 台股盤中即時訊號監控與 Telegram 推播器 (13:10)
============================================================
在台股交易時段 (盤中 13:10 前後) 抓取即時報價，
在記憶體中拼接當日日 K 線進行 SuperTrend AI 策略推論，
判斷是否有即時觸發的進出場訊號或接近停損/突破警示，
並及時發送 Telegram 通知，讓使用者在 13:25 試撮收盤前有充裕時間應對。

Usage:
    python run_intraday_tw_signals.py --dry-run
    python run_intraday_tw_signals.py --telegram
    python run_intraday_tw_signals.py --tickers 0050.TW 00935.TW --dry-run
"""

import sys
import os
import json
import argparse
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import pandas as pd
from dateutil.relativedelta import relativedelta

# Ensure stdout supports UTF-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.scrapers.twse_scraper import TwseScraper
from src.data_loader import DataLoader
from src.supertrend_ai.db_setup import query_supertrend_ai_params, import_supertrend_ai_params_from_json
from src.supertrend_ai.backtest import run_supertrend_ai_backtest
from src.telegram_notifier import TelegramNotifier
from src.storage import SQLiteStorage


def collect_tw_tickers(extra_tickers: Optional[List[str]] = None) -> List[str]:
    """從 data/must_have_tw.json 收集所有台股 (.TW) 標的，排除境內基金 (.EZ)。"""
    config_path = "data/must_have_tw.json"
    tickers = []
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    tickers = [t.strip().upper() for t in data if isinstance(t, str)]
        except Exception as e:
            print(f"讀取 {config_path} 失敗: {e}")

    if not tickers:
        tickers = ["0050.TW", "00935.TW"]

    if extra_tickers:
        for t in extra_tickers:
            clean = t.strip().upper()
            if clean and clean not in tickers:
                tickers.append(clean)

    # 僅篩選 .TW 標的（基金 .EZ 盤中無即時行情）
    tw_stock_tickers = [t for t in tickers if t.endswith(".TW")]
    # 保留順序去重
    seen = set()
    out = []
    for t in tw_stock_tickers:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def evaluate_intraday_ticker(
    ticker: str,
    realtime_quote: Dict[str, Any],
    loader: DataLoader,
    storage: SQLiteStorage
) -> Dict[str, Any]:
    """
    針對單一台股標的，以記憶體拼接即時 K 線進行 SuperTrend AI 推論。
    不污染本機 SQLite 已結算資料庫。
    """
    code, symbol = TwseScraper.resolve_ticker(ticker)
    info = storage.get_ticker_info(symbol)
    display_name = info.get("name") if info else realtime_quote.get("name", symbol)

    # 1. 取得截至昨日的歷史已結算資料
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    start_date_str = (datetime.now() - relativedelta(years=5)).strftime("%Y-%m-%d")
    df_hist = loader.fetch_data(symbol, start_date=start_date_str, end_date=yesterday_str)

    if df_hist.empty:
        raise ValueError(f"[{symbol}] 無法取得歷史日 K 資料")

    # 2. 在記憶體中虛擬拼接今日盤中即時 Bar
    today_dt = pd.to_datetime(realtime_quote["date"])
    intraday_bar = pd.DataFrame([{
        "Open": realtime_quote["open"],
        "High": realtime_quote["high"],
        "Low": realtime_quote["low"],
        "Close": realtime_quote["close"],
        "Volume": realtime_quote["volume"]
    }], index=[today_dt])
    intraday_bar.index.name = "Date"

    if today_dt in df_hist.index:
        df_combined = df_hist.copy()
        df_combined.loc[today_dt] = intraday_bar.loc[today_dt]
    else:
        df_combined = pd.concat([df_hist, intraday_bar])

    df_combined = df_combined[~df_combined.index.duplicated(keep="last")]
    df_combined.sort_index(inplace=True)

    # 3. 讀取現有最佳參數
    params_df = query_supertrend_ai_params(symbol)
    if not params_df.empty:
        params = params_df.iloc[0].to_dict()
    else:
        opt_json_path = "data/optimized_params_ai.json"
        if os.path.exists(opt_json_path):
            with open(opt_json_path, "r", encoding="utf-8") as f:
                all_p = json.load(f)
                params = next((p for p in all_p if p.get("ticker") == symbol), None)
        else:
            params = None

    if not params:
        raise ValueError(f"[{symbol}] 查無 SuperTrend AI 優化參數")

    # 4. 執行純推論 (Inference)
    trades, equity, benchmark, df_ind, metrics = run_supertrend_ai_backtest(
        df=df_combined,
        length=int(params['atr_length']),
        min_mult=float(params['factor_min']),
        max_mult=float(params['factor_max']),
        step=float(params['factor_step']),
        perf_alpha=float(params['perf_alpha']),
        from_cluster=params['from_cluster'],
        update_freq=int(params['update_freq']),
        long_only=bool(params.get('long_only', True)),
        show_progress=False,
        asset_type="stock"
    )

    last_row = df_ind.iloc[-1]
    prev_row = df_ind.iloc[-2] if len(df_ind) >= 2 else last_row

    curr_trend = int(last_row["Trend"])
    prev_trend = int(prev_row["Trend"])
    curr_close = float(last_row["Close"])
    curr_st_line = float(last_row["SuperTrend_AI"])

    curr_pos = "long" if curr_trend == 1 else "cash"
    prev_pos = "long" if prev_trend == 1 else "cash"

    entry_ref = f"{curr_st_line:.2f}" if curr_pos == "cash" else "-"
    exit_ref = f"{curr_st_line:.2f}" if curr_pos == "long" else "-"

    # 計算距標距離百分比
    ref_price = curr_st_line if curr_st_line > 0 else curr_close
    distance_pct = (curr_close - ref_price) / ref_price * 100.0 if ref_price > 0 else 0.0

    # 判斷信號事件狀態
    if prev_pos == "cash" and curr_pos == "long":
        signal_status = "NEW_BUY"
        status_label = "【🟢 盤中突破買進】"
    elif prev_pos == "long" and curr_pos == "cash":
        signal_status = "NEW_SELL"
        status_label = "【🔴 盤中跌破賣出】"
    elif curr_pos == "long" and 0 <= distance_pct <= 1.0:
        signal_status = "NEAR_STOP"
        status_label = "【⚠️ 接近停損警示】"
    elif curr_pos == "cash" and -1.0 <= distance_pct <= 0:
        signal_status = "NEAR_BREAKOUT"
        status_label = "【⚠️ 接近突破警示】"
    else:
        signal_status = "HOLD" if curr_pos == "long" else "WAIT"
        status_label = "【多單持有】" if curr_pos == "long" else "【空手觀望】"

    return {
        "ticker": symbol,
        "name": display_name,
        "date": realtime_quote["date"],
        "time": realtime_quote["time"],
        "close": curr_close,
        "open": realtime_quote["open"],
        "high": realtime_quote["high"],
        "low": realtime_quote["low"],
        "volume": realtime_quote["volume"],
        "best_bid": realtime_quote.get("best_bid"),
        "best_ask": realtime_quote.get("best_ask"),
        "yesterday_close": realtime_quote.get("yesterday_close"),
        "curr_pos": curr_pos,
        "prev_pos": prev_pos,
        "signal_status": signal_status,
        "status_label": status_label,
        "entry_ref": entry_ref,
        "exit_ref": exit_ref,
        "st_line": curr_st_line,
        "distance_pct": round(distance_pct, 2)
    }


def build_intraday_telegram_report(
    eval_results: List[Dict[str, Any]],
    dashboard_url: Optional[str] = None
) -> List[str]:
    """生成台股盤中專屬的 Telegram 格式推播訊息。"""
    if not eval_results:
        return ["📊 <b>SuperTrend AI 台股盤中快訊</b>：查無今日有效報價數據。"]

    latest_time = max(r.get("time", "13:10:00") for r in eval_results)
    latest_date = max(r.get("date", datetime.now().strftime("%Y-%m-%d")) for r in eval_results)

    urgent_items = [r for r in eval_results if r["signal_status"] in ["NEW_BUY", "NEW_SELL", "NEAR_STOP", "NEAR_BREAKOUT"]]
    normal_items = [r for r in eval_results if r["signal_status"] not in ["NEW_BUY", "NEW_SELL", "NEAR_STOP", "NEAR_BREAKOUT"]]

    blocks = []
    header = (
        f"⚡ <b>SuperTrend AI 台股盤中即時快訊 (13:10)</b> ⚡\n\n"
        f"📅 <b>報價時間</b>：{latest_date} {latest_time}\n"
        f"⏰ <b>提醒</b>：距離 13:25 收盤試撮尚餘約 15 分鐘！"
    )
    blocks.append(header)

    # 1. 重點行動指示區塊
    if urgent_items:
        urgent_text = "<b>【🎯 今日重點行動指示】</b>\n"
        for item in urgent_items:
            ticker = item["ticker"]
            name = item["name"]
            st = item["signal_status"]
            close_p = item["close"]
            dist = item["distance_pct"]

            if st == "NEW_BUY":
                urgent_text += (
                    f"🟢 <b>{name} ({ticker})</b>\n"
                    f"  現價：NT${close_p:.2f} | 昨倉：觀望 ➔ <b>【新進場訊號 (BUY)】</b>\n"
                    f"  進場參考價：NT${item['st_line']:.2f} (已突破 {dist:+.2f}%)\n\n"
                )
            elif st == "NEW_SELL":
                urgent_text += (
                    f"🔴 <b>{name} ({ticker})</b>\n"
                    f"  現價：NT${close_p:.2f} | 昨倉：多單 ➔ <b>【新出場訊號 (SELL)】</b>\n"
                    f"  出場參考價：NT${item['st_line']:.2f} (已跌破 {dist:+.2f}%)\n\n"
                )
            elif st == "NEAR_STOP":
                urgent_text += (
                    f"⚠️ <b>{name} ({ticker})</b>\n"
                    f"  現價：NT${close_p:.2f} | <b>接近停損線！</b> (距停損只差 {dist:+.2f}%)\n"
                    f"  停損警戒價：NT${item['st_line']:.2f}\n\n"
                )
            elif st == "NEAR_BREAKOUT":
                urgent_text += (
                    f"⚠️ <b>{name} ({ticker})</b>\n"
                    f"  現價：NT${close_p:.2f} | <b>接近突破點！</b> (距進場只差 {dist:+.2f}%)\n"
                    f"  突破警戒價：NT${item['st_line']:.2f}\n\n"
                )
        blocks.append(urgent_text.strip())
    else:
        blocks.append("✅ <b>今日盤中無重大轉折訊號</b>，現有持倉維持原策略。")

    # 2. 標的盤中即時狀態清單
    status_text = "<b>【📊 盤中持倉監控總覽】</b>\n"
    # 按照距離百分比由大到小排序
    eval_results_sorted = sorted(eval_results, key=lambda x: x["distance_pct"], reverse=True)
    for item in eval_results_sorted:
        ticker = item["ticker"]
        name = item["name"]
        pos = "做多 (Long)" if item["curr_pos"] == "long" else "觀望 (Wait)"
        icon = "🟢" if item["curr_pos"] == "long" else "⚪"
        close_p = item["close"]
        dist = item["distance_pct"]
        bid_str = f"{item['best_bid']:.2f}" if item.get("best_bid") else "-"
        ask_str = f"{item['best_ask']:.2f}" if item.get("best_ask") else "-"
        ref_label = "出場建議價" if item["curr_pos"] == "long" else "進場建議價"
        ref_val = item["exit_ref"] if item["curr_pos"] == "long" else item["entry_ref"]

        status_text += (
            f"{icon} <b>【{name}】</b> ({ticker})\n"
            f"倉位：{pos} (距標 {dist:+.2f}%)\n"
            f"盤中現價：NT${close_p:.2f} (買一: {bid_str} / 賣一: {ask_str})\n"
            f"{ref_label}：NT${ref_val}\n\n"
        )
    blocks.append(status_text.strip())

    url = dashboard_url or os.environ.get("GITHUB_PAGES_URL")
    if url:
        blocks.append(f'🔗 <a href="{url}">查看策略儀表板 (Dashboard)</a>')

    return blocks


def main():
    parser = argparse.ArgumentParser(description="SuperTrend AI 台股盤中即時訊號推播器 (13:10)")
    parser.add_argument("--telegram", action="store_true", help="執行完畢後發送 Telegram 通知")
    parser.add_argument("--dry-run", action="store_true", help="僅在終端印出訊息內容，不實際發送")
    parser.add_argument("--tickers", nargs="+", help="指定執行的台股標的清單 (例如 0050.TW 00935.TW)")
    args = parser.parse_args()

    print("=" * 60)
    print(f"啟動 SuperTrend AI 台股盤中即時監控 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
    print("=" * 60)

    # 確保資料庫有最新優化參數
    import_supertrend_ai_params_from_json()

    tickers = collect_tw_tickers(args.tickers)
    if not tickers:
        print("未找到任何有效台股標的 (.TW)，程序結束。")
        sys.exit(0)

    print(f"監控標的清單: {tickers}")

    # 1. 向 TWSE MIS 取得即時行情
    scraper = TwseScraper()
    realtime_quotes = scraper.fetch_realtime_quotes(tickers)
    if not realtime_quotes:
        print("警告: 無法取得台股即時行情（可能非開盤日或伺服器無回應）。")
        sys.exit(0)

    loader = DataLoader()
    storage = SQLiteStorage()

    eval_results = []
    for t in tickers:
        quote = realtime_quotes.get(t)
        if not quote:
            print(f"[{t}] 未取得即時報價，略過。")
            continue
        try:
            res = evaluate_intraday_ticker(t, quote, loader, storage)
            eval_results.append(res)
            print(f"[{t}] 評估完成: 現價 NT${res['close']:.2f} | 倉位: {res['curr_pos']} | 狀態: {res['status_label']}")
        except Exception as e:
            print(f"[{t}] 評估異常: {e}")

    if not eval_results:
        print("沒有成功評估的標的，程序結束。")
        sys.exit(0)

    # 2. 生成 Telegram 報告區塊
    report_blocks = build_intraday_telegram_report(eval_results)

    notifier = TelegramNotifier()
    chunks = notifier.split_blocks(report_blocks, max_length=3500)

    if args.dry_run or not args.telegram:
        print("\n" + "=" * 20 + " Telegram 盤中快訊預覽 (Dry Run) " + "=" * 20)
        for i, chunk in enumerate(chunks, 1):
            print(f"--- Chunk {i}/{len(chunks)} ---")
            print(chunk)
            print("-" * 50)
        print("=" * 60)
        if not args.telegram:
            print("若需實際發送至 Telegram，請帶入 --telegram 參數。")

    if args.telegram:
        if notifier.is_configured():
            print(f"正在發送 Telegram 盤中快訊 ({len(chunks)} 段)...")
            success_all = True
            for chunk in chunks:
                if not notifier.send_message(chunk):
                    success_all = False
            if success_all:
                print("Telegram 盤中快訊發送成功！")
            else:
                print("Telegram 盤中快訊發送失敗（部分或全部）。")
        else:
            print("未偵測到 Telegram 憑證 (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)，無法發送。")


if __name__ == "__main__":
    main()
