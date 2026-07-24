import sqlite3
import pandas as pd
import os
import json
from typing import Optional

class SQLiteStorage:
    """
    SQLite 本地歷史價格儲存層
    負責資料庫 schema 初始化，並提供 upsert 增量寫入與區間查詢功能。
    """
    def __init__(self, db_path: str = "data/market_data.db", json_path: Optional[str] = None):
        self.db_path = db_path
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)

        if json_path is None:
            self.json_path = os.path.join(db_dir, "optimized_params.json") if db_dir else "optimized_params.json"
        else:
            self.json_path = json_path

        self._init_db()

    def _init_db(self):
        """
        初始化資料庫，建立 price_history 表格，並於必要時自動從 JSON 恢復優化參數。
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
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS supertrend_params (
                    ticker TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    st_period INTEGER NOT NULL,
                    st_multiplier REAL NOT NULL,
                    ma_period INTEGER NOT NULL,
                    use_hma_filter INTEGER NOT NULL,
                    custom_score REAL,
                    cagr REAL,
                    max_drawdown REAL,
                    sharpe_ratio REAL,
                    calmar_ratio REAL,
                    win_rate REAL,
                    profit_factor REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (ticker, start_date, end_date)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stock_signals (
                    ticker TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    close_price REAL NOT NULL,
                    supertrend REAL NOT NULL,
                    position INTEGER NOT NULL,
                    entry_ref REAL,
                    exit_ref REAL,
                    hma REAL NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (ticker, start_date, end_date)
                )
            """)
            conn.commit()

            # 若 supertrend_params 為空且 JSON 檔案存在，自動恢復參數
            cursor.execute("SELECT COUNT(*) FROM supertrend_params")
            count = cursor.fetchone()[0]
            if count == 0 and os.path.exists(self.json_path):
                self.import_params_from_json(self.json_path)
        finally:
            conn.close()

    def _safe_float(self, value, default=None):
        """
        Safely convert a value to float, handling None and NaN values.

        Args:
            value: The value to convert
            default: The default value to return if conversion fails (None by default)

        Returns:
            float: The converted value or default
        """
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

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

    def save_supertrend_params(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        st_period: int,
        st_multiplier: float,
        ma_period: int,
        use_hma_filter: bool,
        custom_score: float = None,
        cagr: float = None,
        max_drawdown: float = None,
        sharpe_ratio: float = None,
        calmar_ratio: float = None,
        win_rate: float = None,
        profit_factor: float = None
    ):
        """
        儲存或更新標的的最適 SuperTrend 參數與績效指標至 supertrend_params 資料表。
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO supertrend_params (
                    ticker, start_date, end_date, st_period, st_multiplier,
                    ma_period, use_hma_filter, custom_score, cagr, max_drawdown,
                    sharpe_ratio, calmar_ratio, win_rate, profit_factor
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker, start_date, end_date) DO UPDATE SET
                    st_period=excluded.st_period,
                    st_multiplier=excluded.st_multiplier,
                    ma_period=excluded.ma_period,
                    use_hma_filter=excluded.use_hma_filter,
                    custom_score=excluded.custom_score,
                    cagr=excluded.cagr,
                    max_drawdown=excluded.max_drawdown,
                    sharpe_ratio=excluded.sharpe_ratio,
                    calmar_ratio=excluded.calmar_ratio,
                    win_rate=excluded.win_rate,
                    profit_factor=excluded.profit_factor,
                    updated_at=CURRENT_TIMESTAMP
            """, (
                ticker, start_date, end_date, int(st_period), float(st_multiplier),
                int(ma_period), 1 if use_hma_filter else 0,
                self._safe_float(custom_score),
                self._safe_float(cagr),
                self._safe_float(max_drawdown),
                self._safe_float(sharpe_ratio),
                self._safe_float(calmar_ratio),
                self._safe_float(win_rate),
                self._safe_float(profit_factor)
            ))
            conn.commit()
            self.export_params_to_json(self.json_path)
        finally:
            conn.close()

    def export_params_to_json(self, json_path: Optional[str] = None) -> bool:
        """
        將 supertrend_params 資料表中的所有優化參數匯出為 JSON 檔案。
        """
        target_json = json_path or self.json_path
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM supertrend_params ORDER BY ticker, start_date, end_date")
            columns = [d[0] for d in cursor.description]
            rows = cursor.fetchall()
            params_list = []
            for r in rows:
                item = dict(zip(columns, r))
                item["use_hma_filter"] = bool(item.get("use_hma_filter"))
                params_list.append(item)

            json_dir = os.path.dirname(target_json)
            if json_dir and not os.path.exists(json_dir):
                os.makedirs(json_dir)

            with open(target_json, "w", encoding="utf-8") as f:
                json.dump(params_list, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"匯出參數至 JSON 失敗: {e}")
            return False
        finally:
            conn.close()

    def import_params_from_json(self, json_path: Optional[str] = None) -> bool:
        """
        從 JSON 檔案將優化參數匯入至 supertrend_params 資料表。
        """
        target_json = json_path or self.json_path
        if not os.path.exists(target_json):
            return False

        try:
            with open(target_json, "r", encoding="utf-8") as f:
                params_list = json.load(f)

            if not isinstance(params_list, list):
                return False

            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.cursor()
                for item in params_list:
                    cursor.execute("""
                        INSERT INTO supertrend_params (
                            ticker, start_date, end_date, st_period, st_multiplier,
                            ma_period, use_hma_filter, custom_score, cagr, max_drawdown,
                            sharpe_ratio, calmar_ratio, win_rate, profit_factor
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(ticker, start_date, end_date) DO UPDATE SET
                            st_period=excluded.st_period,
                            st_multiplier=excluded.st_multiplier,
                            ma_period=excluded.ma_period,
                            use_hma_filter=excluded.use_hma_filter,
                            custom_score=excluded.custom_score,
                            cagr=excluded.cagr,
                            max_drawdown=excluded.max_drawdown,
                            sharpe_ratio=excluded.sharpe_ratio,
                            calmar_ratio=excluded.calmar_ratio,
                            win_rate=excluded.win_rate,
                            profit_factor=excluded.profit_factor,
                            updated_at=CURRENT_TIMESTAMP
                    """, (
                        item["ticker"],
                        item["start_date"],
                        item["end_date"],
                        int(item["st_period"]),
                        float(item["st_multiplier"]),
                        int(item["ma_period"]),
                        1 if item.get("use_hma_filter") else 0,
                        self._safe_float(item.get("custom_score")),
                        self._safe_float(item.get("cagr")),
                        self._safe_float(item.get("max_drawdown")),
                        self._safe_float(item.get("sharpe_ratio")),
                        self._safe_float(item.get("calmar_ratio")),
                        self._safe_float(item.get("win_rate")),
                        self._safe_float(item.get("profit_factor"))
                    ))
                conn.commit()
            finally:
                conn.close()
            return True
        except Exception as e:
            print(f"從 JSON 匯入參數失敗: {e}")
            return False

    def query_supertrend_params(self, ticker: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """
        從資料庫查詢 supertrend_params 紀錄。
        """
        conn = sqlite3.connect(self.db_path)
        try:
            if start_date and end_date:
                query = "SELECT * FROM supertrend_params WHERE ticker=? AND start_date=? AND end_date=?"
                params = (ticker, start_date, end_date)
            else:
                query = "SELECT * FROM supertrend_params WHERE ticker=? ORDER BY updated_at DESC"
                params = (ticker,)
            return pd.read_sql_query(query, conn, params=params)
        finally:
            conn.close()

    def save_stock_signals(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        close_price: float,
        supertrend: float,
        position: int,
        entry_ref: Optional[float] = None,
        exit_ref: Optional[float] = None,
        hma: float = 0.0
    ):
        """
        儲存或更新標的的最新市場狀態與交易訊號至 stock_signals 資料表。
        position: 1 代表 long，0 代表 cash
        hma: 0.0 代表未啟用或無數值，其餘為實際計算出的 HMA 數值
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO stock_signals (
                    ticker, start_date, end_date, close_price, supertrend,
                    position, entry_ref, exit_ref, hma
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker, start_date, end_date) DO UPDATE SET
                    close_price=excluded.close_price,
                    supertrend=excluded.supertrend,
                    position=excluded.position,
                    entry_ref=excluded.entry_ref,
                    exit_ref=excluded.exit_ref,
                    hma=excluded.hma,
                    updated_at=CURRENT_TIMESTAMP
            """, (
                ticker, start_date, end_date,
                float(close_price), float(supertrend),
                int(position),
                self._safe_float(entry_ref),
                self._safe_float(exit_ref),
                self._safe_float(hma, 0.0)  # Default to 0.0 for hma if None/NaN
            ))
            conn.commit()
        finally:
            conn.close()

    def query_stock_signals(self, ticker: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """
        從資料庫查詢 stock_signals 紀錄。
        """
        conn = sqlite3.connect(self.db_path)
        try:
            if start_date and end_date:
                query = "SELECT * FROM stock_signals WHERE ticker=? AND start_date=? AND end_date=?"
                params = (ticker, start_date, end_date)
            else:
                query = "SELECT * FROM stock_signals WHERE ticker=? ORDER BY updated_at DESC"
                params = (ticker,)
            return pd.read_sql_query(query, conn, params=params)
        finally:
            conn.close()
