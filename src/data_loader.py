import pandas as pd
import numpy as np
import yfinance as yf
from src.storage import SQLiteStorage
import logging

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

        # 4. 價格區間合法性檢查 (High >= max(Open, Close), Low <= min(Open, Close))
        max_limit = df[["Open", "Close"]].max(axis=1)
        min_limit = df[["Open", "Close"]].min(axis=1)

        # 若 High 比 Open/Close 還小，則自動校正為 Open/Close 之最大值
        df["High"] = np.maximum(df["High"], max_limit)
        # 若 Low 比 Open/Close 還大，則自動校正為 Open/Close 之最小值
        df["Low"] = np.minimum(df["Low"], min_limit)

        return df

    def fetch_data(self, ticker: str, start_date: str, end_date: str, interval: str = "1d", refresh: bool = False) -> pd.DataFrame:
        """
        獲取歷史 OHLCV 資料。優先查詢本地 SQLite 快取，缺失時向 yfinance 下載並更新快取。
        """
        # 統一處理為 UTC naive 時間以便於比對
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)

        # 對於 1 小時 (1h / 60m) 資料，yfinance 最長僅支援下載最近 730 日
        # 若指定時間區間超過 730 日，自動將起始日期限制為 730 日內，無需提示錯誤
        if interval.lower() in ["1h", "60m"]:
            max_days = 730
            # 1. 若指定時間區間超過 730 日，自動將起始日期限制為 end_dt - 730 日
            if (end_dt - start_dt).days > max_days:
                start_dt = end_dt - pd.Timedelta(days=max_days)

            # 2. 若 start_dt 早於當前時間前 730 日，且 end_dt 在當前時間 730 日內，限制為 earliest_allowed
            earliest_allowed = pd.Timestamp.now() - pd.Timedelta(days=max_days)
            if start_dt < earliest_allowed and earliest_allowed < end_dt:
                start_dt = earliest_allowed

            start_date = start_dt.strftime("%Y-%m-%d")

        if not refresh:
            # 優先從 SQLite 查詢
            local_df = self.storage.query_prices(ticker, interval, start_date, end_date)

            # 若本地資料庫已有該區間內且資料天數大於預估期間天數的 50% 則視為命中快取
            # 這能處理一般的日線快取。如果想要完全覆蓋，則直接檢查起訖日期是否完整。
            if not local_df.empty:
                # 檢查本地資料的頭尾日期是否已完全覆蓋請求區間
                local_start = local_df.index[0]
                local_end = local_df.index[-1]

                # 對於日線，如果本地最舊日期小於等於請求最舊，且最新日期大於等於請求最新（考慮到週末，放寬 3 天）
                day_slack = pd.Timedelta(days=3)
                if local_start <= (start_dt + day_slack) and local_end >= (end_dt - day_slack):
                    return local_df

        # 下載資料
        data = yf.download(ticker, start=start_date, end=end_date, interval=interval, auto_adjust=True)
        if data.empty:
            raise ValueError(f"Downloaded yfinance data is empty for ticker '{ticker}' in interval '{interval}'.")

        # 若 yfinance 下載包含多級 columns (例如 MultiIndex)，進行扁平化
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        # 清洗與校驗
        cleaned_df = self.validate_and_clean_data(data)

        # 快取存入 SQLite
        self.storage.upsert_prices(cleaned_df, ticker, interval)

        # 存入後再次從資料庫查詢以確保時區和格式的完全對齊
        return self.storage.query_prices(ticker, interval, start_date, end_date)
