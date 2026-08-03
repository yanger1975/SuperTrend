import sqlite3
import pandas as pd
import os
import json
from typing import Optional

DB_PATH = "data/market_data.db"

def get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
    except sqlite3.Error as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to set SQLite PRAGMAs: {e}")
    return conn

_initialized = False

def init_supertrend_ai_db():
    global _initialized
    if _initialized:
        return
        
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS strategy_params_supertrend_ai (
                ticker TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                atr_length INTEGER NOT NULL,
                factor_min REAL NOT NULL,
                factor_max REAL NOT NULL,
                factor_step REAL NOT NULL,
                perf_alpha REAL NOT NULL,
                from_cluster TEXT NOT NULL,
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
        
        # Check if update_freq column exists, add it if not
        cursor.execute("PRAGMA table_info(strategy_params_supertrend_ai)")
        columns = [row[1] for row in cursor.fetchall()]
        if "update_freq" not in columns:
            cursor.execute("ALTER TABLE strategy_params_supertrend_ai ADD COLUMN update_freq INTEGER DEFAULT 1")
            
        if "long_only" not in columns:
            cursor.execute("ALTER TABLE strategy_params_supertrend_ai ADD COLUMN long_only INTEGER DEFAULT 1")

        conn.commit()
    _initialized = True

def save_supertrend_ai_params(
    ticker: str,
    start_date: str,
    end_date: str,
    atr_length: int,
    factor_min: float,
    factor_max: float,
    factor_step: float,
    perf_alpha: float,
    from_cluster: str,
    update_freq: int = 1,
    long_only: bool = True,
    custom_score: float = None,
    cagr: float = None,
    max_drawdown: float = None,
    sharpe_ratio: float = None,
    calmar_ratio: float = None,
    win_rate: float = None,
    profit_factor: float = None
):
    init_supertrend_ai_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM strategy_params_supertrend_ai WHERE ticker = ?", (ticker,))
        cursor.execute("""
            INSERT INTO strategy_params_supertrend_ai (
                ticker, start_date, end_date, atr_length, factor_min,
                factor_max, factor_step, perf_alpha, from_cluster, update_freq, long_only,
                custom_score, cagr, max_drawdown, sharpe_ratio,
                calmar_ratio, win_rate, profit_factor
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, start_date, end_date) DO UPDATE SET
                atr_length=excluded.atr_length,
                factor_min=excluded.factor_min,
                factor_max=excluded.factor_max,
                factor_step=excluded.factor_step,
                perf_alpha=excluded.perf_alpha,
                from_cluster=excluded.from_cluster,
                update_freq=excluded.update_freq,
                long_only=excluded.long_only,
                custom_score=excluded.custom_score,
                cagr=excluded.cagr,
                max_drawdown=excluded.max_drawdown,
                sharpe_ratio=excluded.sharpe_ratio,
                calmar_ratio=excluded.calmar_ratio,
                win_rate=excluded.win_rate,
                profit_factor=excluded.profit_factor,
                updated_at=CURRENT_TIMESTAMP
        """, (
            ticker, start_date, end_date, atr_length, factor_min,
            factor_max, factor_step, perf_alpha, from_cluster, update_freq, int(long_only),
            float(custom_score) if custom_score is not None else None,
            float(cagr) if cagr is not None else None,
            float(max_drawdown) if max_drawdown is not None else None,
            float(sharpe_ratio) if sharpe_ratio is not None else None,
            float(calmar_ratio) if calmar_ratio is not None else None,
            float(win_rate) if win_rate is not None else None,
            float(profit_factor) if profit_factor is not None else None
        ))
        conn.commit()
    export_supertrend_ai_params_to_json()

def export_supertrend_ai_params_to_json(json_path: str = "data/optimized_params_ai.json"):
    """將 strategy_params_supertrend_ai 資料表中的所有優化參數匯出為 JSON 檔案"""
    with get_connection() as conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM strategy_params_supertrend_ai ORDER BY ticker, start_date, end_date")
            rows = cursor.fetchall()
            columns = [description[0] for description in cursor.description]
            
            params_list = []
            for row in rows:
                params_dict = dict(zip(columns, row))
                if 'long_only' in params_dict:
                    params_dict['long_only'] = bool(params_dict['long_only'])
                params_list.append(params_dict)
                
            os.makedirs(os.path.dirname(json_path), exist_ok=True)
            tmp_json = json_path + ".tmp"
            with open(tmp_json, "w", encoding="utf-8") as f:
                json.dump(params_list, f, indent=2, ensure_ascii=False)
            os.replace(tmp_json, json_path)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"匯出 AI 參數至 JSON 失敗: {e}")

def query_supertrend_ai_params(ticker: str) -> pd.DataFrame:
    init_supertrend_ai_db()
    with get_connection() as conn:
        query = "SELECT * FROM strategy_params_supertrend_ai WHERE ticker=? ORDER BY updated_at DESC"
        return pd.read_sql_query(query, conn, params=(ticker,))
