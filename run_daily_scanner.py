#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Daily SuperTrend Signal Scanner & Telegram Notifier
===================================================
1. 收集熱門美股 (TrendingScraper) + 必備標的 (Must Have)。
2. 判斷新標的 (進行參數優化) 與既有標的 (查詢最新 end_date 最適參數，固定週六重新優化)。
3. 下載更新最新 K 線數據並計算 SuperTrend / HMA 訊號。
4. 判斷訊號變動 (NEW_BUY, NEW_SELL, HOLD_LONG, WAIT_CASH) 並更新 SQLite 資料庫。
5. 產出 HTML 格式診斷報告並經由 Telegram Bot 發送。

Usage:
    python run_daily_scanner.py
    python run_daily_scanner.py --date 2026-07-24 --dry-run
    python run_daily_scanner.py --force-reoptimize
    python run_daily_scanner.py --tickers TSLA NVDA AAPL
"""

import argparse
import sys
import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple
import pandas as pd
import numpy as np

# 將 src/ 加入 sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from src.storage import SQLiteStorage
from src.data_loader import DataLoader
from src.indicators import compute_supertrend, compute_hma
from src.optimizer import ParameterOptimizer
from src.trending_scraper import TrendingScraper
from src.telegram_notifier import TelegramNotifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

MUST_HAVE_TICKERS = ["SPY", "QQQM", "SMH", "GLD", "VNQ"]

ST_PERIODS = [5, 10, 15, 20, 25, 30]
ST_MULTIPLIERS = [2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
MA_PERIODS = [0, 25, 50, 75, 100, 125]
TRAIN_RATIO = 0.70


def get_target_tickers(extra_tickers: List[str] = None) -> List[str]:
    """收集掃描標的（Trending + Must Have + Extra）。"""
    tickers = list(MUST_HAVE_TICKERS)
    try:
        scraper = TrendingScraper()
        trending = scraper.fetch_top_tickers(limit=10)
        for t in trending:
            if t not in tickers:
                tickers.append(t)
    except Exception as e:
        logger.warning(f"TrendingScraper 擷取熱門股票失敗: {e}")

    if extra_tickers:
        for t in extra_tickers:
            t_upper = t.strip().upper()
            if t_upper and t_upper not in tickers:
                tickers.append(t_upper)

    return tickers


def get_best_param_for_ticker(
    storage: SQLiteStorage,
    ticker: str,
    target_date_str: str,
    raw_df: pd.DataFrame,
    force_reoptimize: bool = False
) -> Dict[str, Any]:
    """
    獲取標的最適參數。
    - 若不在資料庫內 -> 立即優化
    - 若在資料庫內且 force_reoptimize=True 或 當天為週六 -> 重新優化
    - 若在資料庫內且不用優化 -> 找出 end_date 最接近 target_date_str 的參數
    """
    df_params = storage.query_supertrend_params(ticker)
    target_date = datetime.strptime(target_date_str, "%Y-%m-%d")
    is_saturday = target_date.weekday() == 5

    needs_optimization = force_reoptimize or is_saturday or df_params.empty

    if needs_optimization:
        logger.info(f"對 [{ticker}] 執行參數網格優化 (Force/Sat/New)...")
        optimizer = ParameterOptimizer(raw_df)
        train_res, test_res = optimizer.optimize(
            st_periods=ST_PERIODS,
            st_multipliers=ST_MULTIPLIERS,
            ma_periods=MA_PERIODS,
            train_ratio=TRAIN_RATIO
        )
        if train_res.empty:
            raise ValueError(f"標的 [{ticker}] 參數優化未產出有效結果")

        best_row = train_res.sort_values(by="Custom Score", ascending=False).iloc[0]

        # 儲存最佳參數至 SQLite
        storage.save_supertrend_params(
            ticker=ticker,
            start_date=raw_df.index[0].strftime("%Y-%m-%d"),
            end_date=target_date_str,
            st_period=int(best_row["ST_Period"]),
            st_multiplier=float(best_row["ST_Multiplier"]),
            ma_period=int(best_row["MA_Period"]),
            use_hma_filter=bool(best_row["Use_HMA_Filter"]),
            custom_score=float(best_row.get("Custom Score", 0.0)),
            cagr=float(best_row.get("CAGR", 0.0)),
            max_drawdown=float(best_row.get("Max Drawdown", 0.0)),
            sharpe_ratio=float(best_row.get("Sharpe Ratio", 0.0)),
            calmar_ratio=float(best_row.get("Calmar Ratio", 0.0)),
            win_rate=float(best_row.get("Win Rate", 0.0)),
            profit_factor=float(best_row.get("Profit Factor", 0.0))
        )

        return {
            "ST_Period": int(best_row["ST_Period"]),
            "ST_Multiplier": float(best_row["ST_Multiplier"]),
            "MA_Period": int(best_row["MA_Period"]),
            "Use_HMA_Filter": bool(best_row["Use_HMA_Filter"])
        }
    else:
        # 從既有紀錄中選擇 end_date 最接近 target_date 的參數
        df_params["end_date_dt"] = pd.to_datetime(df_params["end_date"])
        df_params["days_diff"] = (df_params["end_date_dt"] - target_date).abs()
        best_param_row = df_params.sort_values(by="days_diff").iloc[0]

        return {
            "ST_Period": int(best_param_row["st_period"]),
            "ST_Multiplier": float(best_param_row["st_multiplier"]),
            "MA_Period": int(best_param_row["ma_period"]),
            "Use_HMA_Filter": bool(best_param_row["use_hma_filter"])
        }


def process_ticker_signal(
    ticker: str,
    raw_df: pd.DataFrame,
    param: Dict[str, Any]
) -> Dict[str, Any]:
    """
    使用最適參數計算當前技術指標與交易訊號。
    """
    st_period = param["ST_Period"]
    st_mult = param["ST_Multiplier"]
    ma_period = param["MA_Period"]
    use_hma = param["Use_HMA_Filter"]

    # 1. 計算 SuperTrend
    df_st, _ = compute_supertrend(raw_df, period=st_period, multiplier=st_mult)

    # 2. 計算 HMA 軌道
    if use_hma and ma_period > 0:
        df_st["HMA"] = compute_hma(df_st["Close"], period=ma_period)
        df_st["MA_Filter"] = df_st["Close"] > df_st["HMA"]
    else:
        df_st["HMA"] = 0.0
        df_st["MA_Filter"] = True

    # 3. 判斷持倉狀態 (Position: 1=Long, 0=Cash)
    # 當使用 HMA Filter 時：進場需 Close > SuperTrend 且 MA_Filter=True；出場依據 SuperTrend 翻紅 (Close < SuperTrend)
    df_st["Position"] = 0
    pos = 0
    positions = []

    for i in range(len(df_st)):
        close = df_st["Close"].iloc[i]
        st_val = df_st["SuperTrend"].iloc[i]
        ma_flt = df_st["MA_Filter"].iloc[i]

        if pos == 0:
            if close > st_val and ma_flt:
                pos = 1
        elif pos == 1:
            if close < st_val:
                pos = 0
        positions.append(pos)

    df_st["Position"] = positions

    if len(df_st) < 2:
        prev_pos = df_st["Position"].iloc[-1]
    else:
        prev_pos = df_st["Position"].iloc[-2]

    curr_pos = df_st["Position"].iloc[-1]

    # 判斷狀態變動
    if prev_pos == 0 and curr_pos == 1:
        signal_state = "NEW_BUY"
    elif prev_pos == 1 and curr_pos == 0:
        signal_state = "NEW_SELL"
    elif prev_pos == 1 and curr_pos == 1:
        signal_state = "HOLD_LONG"
    else:
        signal_state = "WAIT_CASH"

    latest_bar = df_st.iloc[-1]
    close_p = float(latest_bar["Close"])
    st_p = float(latest_bar["SuperTrend"])
    hma_p = float(latest_bar["HMA"])

    # 參考價計算
    entry_ref = st_p if curr_pos == 0 else None
    exit_ref = st_p if curr_pos == 1 else None

    return {
        "ticker": ticker,
        "date": df_st.index[-1].strftime("%Y-%m-%d"),
        "close": close_p,
        "supertrend": st_p,
        "hma": hma_p,
        "position": curr_pos,
        "prev_position": prev_pos,
        "signal_state": signal_state,
        "entry_ref": entry_ref,
        "exit_ref": exit_ref,
        "param": param
    }


def build_telegram_report(date_str: str, signals: List[Dict[str, Any]]) -> str:
    """組裝 Telegram HTML 診斷報告。"""
    new_buy = [s for s in signals if s["signal_state"] == "NEW_BUY"]
    new_sell = [s for s in signals if s["signal_state"] == "NEW_SELL"]
    hold_long = [s for s in signals if s["signal_state"] == "HOLD_LONG"]
    wait_cash = [s for s in signals if s["signal_state"] == "WAIT_CASH"]

    def fmt_ticker_params(s: Dict[str, Any]) -> str:
        param = s.get("param") or {}
        st_period = param.get("ST_Period")
        st_mult = param.get("ST_Multiplier")
        use_hma = param.get("Use_HMA_Filter", False)
        ma_period = param.get("MA_Period", 0)

        if st_period is not None and st_mult is not None:
            ma_display = ma_period if (use_hma and ma_period > 0) else 0
            return f"{s['ticker']} ({st_period}, {st_mult}, {ma_display})"
        return s['ticker']

    lines = []
    lines.append(f"📊 <b>【SuperTrend 每日策略診斷報告】</b>")
    lines.append(f"📅 <b>日期:</b> {date_str} | 掃描標的: {len(signals)} 支\n")

    # Section 1: 新訊號觸發
    lines.append("🚨 <b>【本日新觸發動態】</b>")
    if not new_buy and not new_sell:
        lines.append("<i>今日無新買入或新賣出訊號。</i>\n")
    else:
        for s in new_buy:
            lines.append(
                f"🟢 <b>[買入] {fmt_ticker_params(s)}</b> | 收盤: <code>${s['close']:.2f}</code> | "
                f"止損點: <code>${s['supertrend']:.2f}</code>"
            )
        for s in new_sell:
            lines.append(
                f"🔴 <b>[平倉] {fmt_ticker_params(s)}</b> | 收盤: <code>${s['close']:.2f}</code> | "
                f"觸發出場觀望"
            )
        lines.append("")

    # Section 2: 持倉中標的
    lines.append(f"🟢 <b>【當前持倉標的】({len(hold_long)} 支)</b>")
    if not hold_long:
        lines.append("<i>目前無持倉部位。</i>\n")
    else:
        for s in hold_long:
            lines.append(
                f"• <b>{fmt_ticker_params(s)}</b> | 收盤: <code>${s['close']:.2f}</code> | "
                f"出場參考價: <code>${s['exit_ref']:.2f}</code>"
            )
        lines.append("")

    # Section 3: 觀望標的
    lines.append(f"⚪ <b>【觀望中標的】({len(wait_cash)} 支)</b>")
    if wait_cash:
        cash_tickers = [f"<b>{fmt_ticker_params(s)}</b>" for s in wait_cash]
        lines.append(", ".join(cash_tickers))

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="SuperTrend Daily Signal Scanner & Telegram Notifier")
    parser.add_argument("--date", type=str, default=datetime.now().strftime("%Y-%m-%d"), help="掃描日期 (YYYY-MM-DD)")
    parser.add_argument("--start", type=str, default="2020-01-01", help="歷史資料下載起始日 (YYYY-MM-DD)")
    parser.add_argument("--force-reoptimize", action="store_true", help="強制所有標的重新進行網格優化")
    parser.add_argument("--tickers", nargs="+", help="附加或指定的股票標的清單 (例如 TSLA NVDA AAPL)")
    parser.add_argument("--dry-run", action="store_true", help="僅印出報告內容，不發送 Telegram 訊息")
    parser.add_argument("--db-path", type=str, default="data/market_data.db", help="SQLite 資料庫路徑")

    args = parser.parse_args()

    storage = SQLiteStorage(args.db_path)
    data_loader = DataLoader(db_path=args.db_path)
    notifier = TelegramNotifier()

    target_tickers = get_target_tickers(args.tickers)
    logger.info(f"開始執行每日掃描，目標標的共 {len(target_tickers)} 支: {target_tickers}")

    all_signal_results = []

    for ticker in target_tickers:
        try:
            logger.info(f"刻正下載/更新 [{ticker}] 歷史數據...")
            raw_df = data_loader.fetch_data(ticker, start_date=args.start, end_date=args.date)
            if raw_df.empty or len(raw_df) < 30:
                logger.warning(f"標的 [{ticker}] 數據不足，跳過計算。")
                continue

            param = get_best_param_for_ticker(
                storage=storage,
                ticker=ticker,
                target_date_str=args.date,
                raw_df=raw_df,
                force_reoptimize=args.force_reoptimize
            )

            sig = process_ticker_signal(ticker, raw_df, param)
            all_signal_results.append(sig)

            # 儲存最新訊號至 SQLite stock_signals 表格
            storage.save_stock_signals(
                ticker=ticker,
                start_date=args.start,
                end_date=args.date,
                close_price=sig["close"],
                supertrend=sig["supertrend"],
                position=sig["position"],
                entry_ref=sig["entry_ref"],
                exit_ref=sig["exit_ref"],
                hma=sig["hma"]
            )

        except Exception as e:
            logger.error(f"處理標的 [{ticker}] 發生錯誤: {e}", exc_info=True)

    if not all_signal_results:
        logger.error("所有標的處理皆失敗或無有效數據。")
        return

    # 組裝報告
    report_msg = build_telegram_report(args.date, all_signal_results)

    if args.dry_run:
        print("\n==================== Telegram Report (Dry Run) ====================")
        print(report_msg)
        print("====================================================================\n")
    else:
        if notifier.is_configured():
            logger.info("發送 Telegram 診斷報告中...")
            success = notifier.send_message(report_msg)
            if success:
                logger.info("Telegram 診斷報告成功發送！")
            else:
                logger.error("Telegram 診斷報告發送失敗。")
        else:
            logger.warning("未偵測到 Telegram 憑證，改為顯示報告內容 (Dry Run Mode)：")
            print(report_msg)


if __name__ == "__main__":
    main()
