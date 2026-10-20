import pandas as pd
import numpy as np
import yfinance as yf
from src.storage import SQLiteStorage
import os
import json
import logging
from typing import Optional
from datetime import datetime, timezone, timedelta, time as dt_time


class DataLoader:
    """
    資料加載與快取協調器
    協調 SQLite 本地儲存層與 yfinance API，並實作資料校驗清洗。
    """
    def __init__(self, db_path: str = "data/market_data.db"):
        self.storage = SQLiteStorage(db_path)
        self.logger = logging.getLogger(__name__)

    def validate_and_clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        執行資料清洗與校驗規則，避免回測中的髒資料。
        """
        if df.empty:
            return df

        # 1. 確保 Close 價格不為 Null 且大於 0
        df = df.dropna(subset=["Close"]).copy()
        df = df[df["Close"] > 0]
        if df.empty:
            return df

        # 2. 處理重疊日期戳記，僅保留第一筆
        df = df[~df.index.duplicated(keep="first")]

        # 3. 確保時間索引遞增排序
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()

        # 4. 價格區間合法性檢查
        is_fund = (df["Open"] == 0) & (df["High"] == 0) & (df["Low"] == 0)
        stock_mask = ~is_fund
        if stock_mask.any():
            max_limit = df.loc[stock_mask, ["Open", "Close"]].max(axis=1)
            min_limit = df.loc[stock_mask, ["Open", "Close"]].min(axis=1)
            df.loc[stock_mask, "High"] = np.maximum(df.loc[stock_mask, "High"], max_limit)
            df.loc[stock_mask, "Low"] = np.minimum(df.loc[stock_mask, "Low"], min_limit)

        if is_fund.any():
            df.loc[is_fund, "Open"] = df.loc[is_fund, "Close"]
            df.loc[is_fund, "High"] = df.loc[is_fund, "Close"]
            df.loc[is_fund, "Low"] = df.loc[is_fund, "Close"]

        return df

    def get_latest_dividend_date(self, ticker: str) -> Optional[pd.Timestamp]:
        """
        查詢標的最新除權息日（包含現金股利與股票分割）。
        若查無記錄或發生例外，回傳 None。
        """
        try:
            t = yf.Ticker(ticker)
            actions = getattr(t, "actions", None)
            dates = []
            if actions is not None and not actions.empty:
                if "Dividends" in actions.columns:
                    divs = actions[actions["Dividends"] > 0]
                    if not divs.empty:
                        dates.extend(divs.index.tolist())
                if "Stock Splits" in actions.columns:
                    splits = actions[actions["Stock Splits"] > 0]
                    if not splits.empty:
                        dates.extend(splits.index.tolist())

            if not dates:
                divs = getattr(t, "dividends", None)
                if divs is not None and not divs.empty:
                    divs = divs[divs > 0]
                    if not divs.empty:
                        dates.extend(divs.index.tolist())

            if dates:
                latest = max(dates)
                if hasattr(latest, "tzinfo") and latest.tzinfo is not None:
                    latest = latest.tz_convert(None)
                return pd.to_datetime(latest).normalize()
        except Exception as e:
            self.logger.warning(f"[{ticker}] 查詢配息記錄失敗: {e}")
        return None

    def patch_twse_data_if_needed(self, ticker: str, df: pd.DataFrame, end_dt: pd.Timestamp) -> pd.DataFrame:
        """
        若 yfinance 台股資料落後於 TWSE 最新交易日，且缺漏區間在最新除息日之後，
        自動以 TWSE 官方日線無縫補齊，消除 Yahoo Finance 的 1 日更新延遲。
        """
        if df.empty or not ticker.upper().endswith(".TW"):
            return df

        try:
            from src.scrapers.twse_scraper import TwseScraper
            tw_scraper = TwseScraper(self.storage.db_path)
            code, _ = tw_scraper.resolve_ticker(ticker)

            snap = tw_scraper.fetch_daily_snapshot()
            if not snap or code not in snap:
                return df

            item = snap[code]
            date_str = item.get("Date")
            if not date_str:
                return df

            twse_latest_dt = pd.to_datetime(date_str).normalize()
            yf_latest_dt = df.index[-1].normalize()

            # 若 yfinance 最新日期已達到或超過 TWSE 最新日期，無需補丁
            if yf_latest_dt >= twse_latest_dt:
                return df

            # 若使用者請求的 end_dt 早於 TWSE 最新日期，代表請求歷史資料，無需補上今日快照
            if end_dt < twse_latest_dt:
                return df

            # 檢查除權息日：缺漏期間必須在最新除權息日之後
            latest_div = self.get_latest_dividend_date(ticker)
            if latest_div is not None and yf_latest_dt < latest_div:
                self.logger.warning(
                    f"[{ticker}] yfinance 最新日期 ({yf_latest_dt.strftime('%Y-%m-%d')}) "
                    f"早於最新除息日 ({latest_div.strftime('%Y-%m-%d')})，為防除息折價誤差跳過 TWSE 補丁。"
                )
                return df

            # 補齊缺漏交易日
            missing_start = (yf_latest_dt + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            missing_end = twse_latest_dt.strftime("%Y-%m-%d")

            b_days = len(pd.bdate_range(missing_start, missing_end))
            if b_days <= 1:
                patch_df = tw_scraper.get_latest_snapshot_bar(ticker)
            else:
                patch_df = tw_scraper.fetch_recent_days(ticker, missing_start, missing_end)

            if patch_df is not None and not patch_df.empty:
                patch_df = patch_df[["Open", "High", "Low", "Close", "Volume"]]
                combined = pd.concat([df, patch_df])
                combined = combined[~combined.index.duplicated(keep="last")]
                combined.sort_index(inplace=True)
                self.logger.info(
                    f"[{ticker}] 成功透過 TWSE 補齊 {len(patch_df)} 筆最新交易日數據 "
                    f"({patch_df.index[0].strftime('%Y-%m-%d')} ~ {patch_df.index[-1].strftime('%Y-%m-%d')})"
                )
                return combined

        except Exception as e:
            self.logger.warning(f"[{ticker}] TWSE 補丁執行異常，維持 yfinance 原始數據: {e}")

        return df

    def fetch_data(self, ticker: str, start_date: str, end_date: str, interval: str = "1d", refresh: bool = False) -> pd.DataFrame:
        """
        獲取歷史 OHLCV 資料。優先查詢本地 SQLite 快取，缺失時向 yfinance 下載並更新快取。
        """
        # 檢查是否為 EZMoney 基金標的 (.EZ 結尾或存在於 ezmoney.json 中)
        from src.scrapers.ezmoney_scraper import EzMoneyScraper
        ez_scraper = EzMoneyScraper(self.storage.db_path)
        if ticker.endswith(".EZ") or ticker.endswith(".ez") or ticker in ez_scraper.mapping:
            fund_df = ez_scraper.fetch_fund_nav(ticker, start_date, end_date, refresh=refresh)
            return self.validate_and_clean_data(fund_df)

        # 若為純數字台股代碼，自動補上 .TW 後綴 (例如 0050 -> 0050.TW)
        if ticker.isdigit() and len(ticker) in [4, 5, 6]:
            ticker = f"{ticker}.TW"

        # 若為台股標的，預先記錄其標的元數據
        if ticker.upper().endswith(".TW"):
            tw_names = {"0050.TW": "元大台灣50", "00935.TW": "野村臺灣新科技50"}
            name = tw_names.get(ticker.upper(), f"台股_{ticker.upper().replace('.TW', '')}")
            self.storage.upsert_ticker_info(ticker.upper(), name=name, asset_type="etf", source="yfinance")

        # 統一處理為 UTC naive 時間以便於比對
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)

        # 針對台股/國內基金日線資料：若當前台北時間在 14:30 盤後正式結算前，
        # 當日 K 線仍處於未收盤或未結算狀態，嚴格限制結束日期為昨日，並剔除當日未結算之價格，
        # 防止早盤誤將即時行情寫入歷史日線快取。
        is_tw_asset = ticker.upper().endswith((".TW", ".EZ"))
        if is_tw_asset and interval.lower() in ["1d"]:
            utc_now = datetime.now(timezone.utc)
            tw_now = utc_now + timedelta(hours=8)
            today_tw = pd.to_datetime(tw_now.date())
            if tw_now.time() < dt_time(14, 30):
                if end_dt >= today_tw:
                    end_dt = today_tw - pd.Timedelta(days=1)
                    end_date = end_dt.strftime("%Y-%m-%d")

        # 對於 1 小時 (1h / 60m) 資料，yfinance 最長僅支援下載最近 730 日
        # 若指定時間區間超過 730 日，自動將起始日期限制為 730 日內，無需提示錯誤
        if interval.lower() in ["1h", "60m"]:
            max_days = 730
            orig_start = start_date
            # 1. 若指定時間區間超過 730 日，自動將起始日期限制為 end_dt - 730 日
            if (end_dt - start_dt).days > max_days:
                start_dt = end_dt - pd.Timedelta(days=max_days)

            # 2. 若 start_dt 早於當前時間前 730 日，且 end_dt 在當前時間 730 日內，限制為 earliest_allowed
            earliest_allowed = pd.Timestamp.now() - pd.Timedelta(days=max_days)
            if start_dt < earliest_allowed and earliest_allowed < end_dt:
                start_dt = earliest_allowed

            start_date = start_dt.strftime("%Y-%m-%d")
            if start_date != orig_start:
                self.logger.warning("1 小時頻率資料請求區間超過 yfinance 730 日限制，起始日期已自動調整: %s -> %s", orig_start, start_date)

        if not refresh:
            # 優先從 SQLite 查詢
            local_df = self.storage.query_prices(ticker, interval, start_date, end_date)

            # 若本地資料庫已有該區間內且資料天數大於預估期間天數的 50% 則視為命中快取
            # 這能處理一般的日線快取。如果想要完全覆蓋，則直接檢查起訖日期是否完整。
            if not local_df.empty:
                if is_tw_asset and interval.lower() in ["1d"] and tw_now.time() < dt_time(14, 30):
                    local_df = local_df[local_df.index < today_tw]

                # 檢查本地資料的頭尾日期是否已完全覆蓋請求區間
                local_start = local_df.index[0]
                local_end = local_df.index[-1]

                # 檢查起始日期是否滿足（考慮開頭歷史資料遇週末假期放寬 4 天）
                start_covered = local_start <= (start_dt + pd.Timedelta(days=4))

                # 結束日期：確保快取資料涵蓋至最新交易日（除了週末之外，不應遺漏任何營業日，防止週中快取假命中）
                if interval.lower() in ["1h", "60m"]:
                    end_covered = local_end >= end_dt
                else:
                    end_covered = local_end >= end_dt or len(pd.bdate_range(local_end + pd.Timedelta(days=1), end_dt)) == 0

                if start_covered and end_covered:
                    return self.validate_and_clean_data(local_df)

        # 下載資料 (注意: yfinance 的 end 參數為 exclusive，需 +1 天以涵蓋 end_date 當日)
        yf_end_date = (end_dt + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        data = yf.download(ticker, start=start_date, end=yf_end_date, interval=interval, auto_adjust=True)
        if data.empty:
            raise ValueError(f"Downloaded yfinance data is empty for ticker '{ticker}' in interval '{interval}'.")

        # 若 yfinance 下載包含多級 columns (例如 MultiIndex)，進行扁平化
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        # 清洗與校驗
        cleaned_df = self.validate_and_clean_data(data)
        if is_tw_asset and interval.lower() in ["1d"] and tw_now.time() < dt_time(14, 30):
            cleaned_df = cleaned_df[cleaned_df.index < today_tw]

        # 若為台股日線資料，自動檢查並以 TWSE 數據補齊延遲
        if ticker.upper().endswith(".TW") and interval.lower() in ["1d"]:
            cleaned_df = self.patch_twse_data_if_needed(ticker, cleaned_df, end_dt)
            cleaned_df = self.validate_and_clean_data(cleaned_df)
            if tw_now.time() < dt_time(14, 30):
                cleaned_df = cleaned_df[cleaned_df.index < today_tw]

        # 快取存入 SQLite
        self.storage.upsert_prices(cleaned_df, ticker, interval)

        # 存入後再次從資料庫查詢以確保時區和格式的完全對齊
        final_df = self.storage.query_prices(ticker, interval, start_date, end_date)
        if is_tw_asset and interval.lower() in ["1d"] and tw_now.time() < dt_time(14, 30):
            if not final_df.empty:
                final_df = final_df[final_df.index < today_tw]

        if not final_df.empty:
            return self.validate_and_clean_data(final_df)
        return cleaned_df
