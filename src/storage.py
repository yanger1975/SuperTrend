import sqlite3
import pandas as pd
import os
from typing import Optional

class SQLiteStorage:
    """
    SQLite 本地歷史價格儲存層
    負責資料庫 schema 初始化，並提供 upsert 增量寫入與區間查詢功能。
    """
    def __init__(self, db_path: str = "data/market_data.db"):
        self.db_path = db_path
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
        self._init_db()

    def _init_db(self):
        """
        初始化資料庫，建立 price_history 表格
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS price_history (
                    ticker TEXT NOT NULL,
                    interval TEXT NOT NULL,
                    datetime TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL,
                    source TEXT DEFAULT 'yfinance',
                    adjusted INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (ticker, interval, datetime)
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def upsert_prices(self, df: pd.DataFrame, ticker: str, interval: str):
        """
        將 DataFrame 價格資料以 upsert 方式寫入/更新至資料庫。
        """
        if df.empty:
            return

        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            for dt, row in df.iterrows():
                if hasattr(dt, "tzinfo") and dt.tzinfo is not None:
                    dt = dt.tz_localize(None)
                dt_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                
                volume_val = float(row["Volume"]) if not pd.isna(row["Volume"]) else None
                
                cursor.execute("""
                    INSERT INTO price_history (ticker, interval, datetime, open, high, low, close, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(ticker, interval, datetime) DO UPDATE SET
                        open=excluded.open,
                        high=excluded.high,
                        low=excluded.low,
                        close=excluded.close,
                        volume=excluded.volume,
                        updated_at=CURRENT_TIMESTAMP
                """, (
                    ticker, 
                    interval, 
                    dt_str, 
                    float(row["Open"]), 
                    float(row["High"]), 
                    float(row["Low"]), 
                    float(row["Close"]), 
                    volume_val
                ))
            conn.commit()
        finally:
            conn.close()

    def query_prices(self, ticker: str, interval: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        從資料庫查詢指定標的、週期與時間範圍內的價格資料。
        """
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        
        # 若為日期字串且無指定時間，將結束時間設為當天最後一秒 (23:59:59)，確保包含日內交易
        if len(str(end_date)) <= 10:
            end_dt = end_dt.replace(hour=23, minute=59, second=59)
            
        start_ts = start_dt.strftime("%Y-%m-%d %H:%M:%S")
        end_ts = end_dt.strftime("%Y-%m-%d %H:%M:%S")
        
        conn = sqlite3.connect(self.db_path)
        try:
            query = """
                SELECT datetime, open, high, low, close, volume
                FROM price_history
                WHERE ticker=? AND interval=? AND datetime BETWEEN ? AND ?
                ORDER BY datetime ASC
            """
            df = pd.read_sql_query(query, conn, params=(ticker, interval, start_ts, end_ts))
            
            if df.empty:
                return pd.DataFrame()
            
            df["datetime"] = pd.to_datetime(df["datetime"])
            df.set_index("datetime", inplace=True)
            df.columns = ["Open", "High", "Low", "Close", "Volume"]
            return df
        finally:
            conn.close()
