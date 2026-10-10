import os
import re
import time
import json
import logging
import urllib.request
import urllib.error
from datetime import datetime
from typing import Tuple, Dict, Any, List, Optional
import pandas as pd
import numpy as np

from src.storage import SQLiteStorage


class TwseScraper:
    """
    臺灣證券交易所 (TWSE) 官方數據抓取與快取器
    ===========================================
    - 歷史回測與優化：透過 /exchangeReport/STOCK_DAY 按月抓取。
    - 當日盤後快照：透過 OpenAPI /v1/exchangeReport/STOCK_DAY_ALL。
    - 快取管理：提供 SQLite ↔ data/twse_prices.json 雙向同步機制。
    """
    def __init__(self, db_path: str = "data/market_data.db", json_path: str = "data/twse_prices.json"):
        self.db_path = db_path
        self.json_path = json_path
        self.storage = SQLiteStorage(db_path=self.db_path)
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def resolve_ticker(ticker: str) -> Tuple[str, str]:
        """
        解析股票代號。
        例如 '0050.TW' 或 '0050' -> ('0050', '0050.TW')
        """
        clean = ticker.strip().upper()
        if clean.endswith(".TW"):
            code = clean[:-3]
        else:
            code = clean
        symbol = f"{code}.TW"
        return code, symbol

    @staticmethod
    def to_ad_date(roc_date_str: str) -> str:
        """
        將民國年日期轉換為西元 YYYY-MM-DD 字串。
        支援 '113/10/30'、'113-10-30'、'1151008' 等格式。
        """
        s = roc_date_str.strip()
        if "/" in s or "-" in s:
            sep = "/" if "/" in s else "-"
            parts = s.split(sep)
            if len(parts) == 3:
                roc_year = int(parts[0])
                month = int(parts[1])
                day = int(parts[2])
                ad_year = roc_year + 1911
                return f"{ad_year:04d}-{month:02d}-{day:02d}"
        elif len(s) == 7: # e.g. 1151008
            roc_year = int(s[:3])
            month = int(s[3:5])
            day = int(s[5:7])
            ad_year = roc_year + 1911
            return f"{ad_year:04d}-{month:02d}-{day:02d}"
        elif len(s) == 6: # e.g. 991008
            roc_year = int(s[:2])
            month = int(s[2:4])
            day = int(s[4:6])
            ad_year = roc_year + 1911
            return f"{ad_year:04d}-{month:02d}-{day:02d}"

        dt = pd.to_datetime(s)
        return dt.strftime("%Y-%m-%d")

    def parse_stock_day_json(self, raw_json: Dict[str, Any]) -> pd.DataFrame:
        """
        將 TWSE /exchangeReport/STOCK_DAY 原始 JSON 解析為標準 OHLCV DataFrame。
        """
        stat = raw_json.get("stat", "")
        if stat != "OK":
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

        data = raw_json.get("data", [])
        if not data:
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

        rows = []
        for item in data:
            if len(item) < 7:
                continue
            date_str = self.to_ad_date(str(item[0]))

            def clean_float(val: Any) -> float:
                if val is None:
                    return np.nan
                s_val = str(val).replace(",", "").replace("+", "").replace("-", "").strip()
                s_val = re.sub(r"[^\d.]", "", s_val)
                try:
                    return float(s_val) if s_val else np.nan
                except ValueError:
                    return np.nan

            open_p = clean_float(item[3])
            high_p = clean_float(item[4])
            low_p = clean_float(item[5])
            close_p = clean_float(item[6])
            volume = clean_float(item[1])

            if pd.isna(close_p) or close_p <= 0:
                continue

            rows.append({
                "Date": pd.to_datetime(date_str),
                "Open": open_p if not pd.isna(open_p) else close_p,
                "High": high_p if not pd.isna(high_p) else close_p,
                "Low": low_p if not pd.isna(low_p) else close_p,
                "Close": close_p,
                "Volume": volume if not pd.isna(volume) else 0.0
            })

        if not rows:
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

        df = pd.DataFrame(rows)
        df.set_index("Date", inplace=True)
        df.sort_index(inplace=True)
        return df[["Open", "High", "Low", "Close", "Volume"]]

    def parse_daily_snapshot(self, raw_snapshot: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        解析 TWSE OpenAPI STOCK_DAY_ALL 原始快照清單。
        回傳字典格式：{ '0050': { 'Code': '0050', 'Name': '元大台灣50', 'Close': 192.0, ... } }
        """
        res = {}
        for item in raw_snapshot:
            code = str(item.get("Code", "")).strip()
            if not code:
                continue

            def clean_float(val: Any) -> float:
                if val is None:
                    return np.nan
                s = str(val).replace(",", "").strip()
                s = re.sub(r"[^\d.]", "", s)
                try:
                    return float(s) if s else np.nan
                except ValueError:
                    return np.nan

            close_p = clean_float(item.get("ClosingPrice"))
            open_p = clean_float(item.get("OpeningPrice"))
            high_p = clean_float(item.get("HighestPrice"))
            low_p = clean_float(item.get("LowestPrice"))
            vol = clean_float(item.get("TradeVolume"))

            res[code] = {
                "Code": code,
                "Name": str(item.get("Name", "")).strip(),
                "Open": open_p if not pd.isna(open_p) else close_p,
                "High": high_p if not pd.isna(high_p) else close_p,
                "Low": low_p if not pd.isna(low_p) else close_p,
                "Close": close_p,
                "Volume": vol if not pd.isna(vol) else 0.0,
                "Date": str(item.get("Date", "")).strip()
            }
        return res

    def fetch_daily_snapshot(self) -> Dict[str, Dict[str, Any]]:
        """
        向證券交易所 OpenAPI /v1/exchangeReport/STOCK_DAY_ALL 發送請求取得當日全市場快照。
        """
        url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return self.parse_daily_snapshot(data)
        except Exception as e:
            self.logger.warning(f"取得 TWSE OpenAPI 快照失敗: {e}")
            return {}

    def fetch_monthly_history(self, code: str, year: int, month: int, max_retries: int = 3) -> pd.DataFrame:
        """
        抓取指定股票特定月份的歷史日線資料，具備 3 秒延遲與重試機制。
        """
        date_str = f"{year:04d}{month:02d}01"
        url = f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={date_str}&stockNo={code}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        for attempt in range(max_retries):
            try:
                # 遵循證交所頻率保護，每次調用間隔 3 秒
                time.sleep(3.0)
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=20) as resp:
                    raw_text = resp.read().decode("utf-8")
                    data = json.loads(raw_text)
                    return self.parse_stock_day_json(data)
            except urllib.error.HTTPError as e:
                self.logger.warning(f"[{code}] 下載 {date_str} 遇到 HTTP {e.code}，第 {attempt + 1} 次重試...")
                if e.code in [403, 429]:
                    time.sleep(5.0 * (attempt + 1))
            except Exception as e:
                self.logger.warning(f"[{code}] 下載 {date_str} 異常: {e}，第 {attempt + 1} 次重試...")
                time.sleep(3.0)

        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

    def export_prices_to_json(self, json_path: Optional[str] = None) -> bool:
        """
        將 SQLite 資料庫中所有的台股 (.TW) 價格記錄與元數據導出為輕量化 JSON。
        """
        out_path = json_path or self.json_path
        out_dir = os.path.dirname(out_path)
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)

        conn = self.storage.get_connection()
        try:
            # 查詢所有台股標的
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT ticker FROM price_history WHERE ticker LIKE '%.TW'")
            tickers = [row[0] for row in cursor.fetchall()]

            data_export = {}
            for t in tickers:
                info = self.storage.get_ticker_info(t) or {
                    "name": t.replace(".TW", ""),
                    "asset_type": "etf" if t.replace(".TW", "").startswith("00") else "stock",
                    "source": "twse"
                }

                # 讀取完整歷史
                df = self.storage.query_prices(t, "1d", "2000-01-01", "2099-12-31")
                if df.empty:
                    continue

                prices_list = []
                for idx, row in df.iterrows():
                    d_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
                    prices_list.append({
                        "Date": d_str,
                        "Open": float(row["Open"]),
                        "High": float(row["High"]),
                        "Low": float(row["Low"]),
                        "Close": float(row["Close"]),
                        "Volume": float(row["Volume"])
                    })

                data_export[t] = {
                    "info": info,
                    "prices": prices_list
                }

            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data_export, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            self.logger.error(f"導出 TWSE 價格 JSON 失敗: {e}")
            return False
        finally:
            conn.close()

    def import_prices_from_json(self, json_path: Optional[str] = None) -> int:
        """
        從 JSON 快取匯入台股歷史記錄至本地 SQLite 資料庫。
        """
        in_path = json_path or self.json_path
        if not os.path.exists(in_path):
            return 0

        total_imported = 0
        try:
            with open(in_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for ticker, item in data.items():
                info = item.get("info", {})
                if info:
                    self.storage.upsert_ticker_info(
                        ticker=ticker,
                        name=info.get("name", ticker),
                        asset_type=info.get("asset_type", "etf"),
                        source=info.get("source", "twse")
                    )

                prices = item.get("prices", [])
                if prices:
                    df = pd.DataFrame(prices)
                    df["Date"] = pd.to_datetime(df["Date"])
                    df.set_index("Date", inplace=True)
                    df.sort_index(inplace=True)
                    self.storage.upsert_prices(df[["Open", "High", "Low", "Close", "Volume"]], ticker, "1d")
                    total_imported += len(df)

            return total_imported
        except Exception as e:
            self.logger.error(f"從 JSON 匯入 TWSE 價格失敗: {e}")
            return total_imported

    def fetch_stock_history(self, ticker: str, start_date: str, end_date: str, refresh: bool = False) -> pd.DataFrame:
        """
        獲取指定台股標的歷史數據。自動檢查已快取月份，下載缺失月份並同步更新 SQLite 與 JSON。
        """
        code, symbol = self.resolve_ticker(ticker)

        # 若本地 SQLite 無記錄，先嘗試自 JSON 恢復
        df_all = self.storage.query_prices(symbol, "1d", "2000-01-01", "2099-12-31")
        if df_all.empty:
            self.import_prices_from_json()
            df_all = self.storage.query_prices(symbol, "1d", "2000-01-01", "2099-12-31")

        latest_in_db = df_all.index[-1] if not df_all.empty else None


        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)

        # 判定是否需要下載（如果快取已有且無須 refresh，且最新日期涵蓋至最近營業日）
        need_fetch = refresh or (latest_in_db is None) or (pd.to_datetime(latest_in_db) < end_dt - pd.Timedelta(days=3))

        if need_fetch:
            # 建立需要抓取的年月清單
            # 起始月份：若資料庫已有資料且未指定 refresh，可從資料庫最新日期當月開始
            if latest_in_db and not refresh:
                fetch_start = pd.to_datetime(latest_in_db).replace(day=1)
            else:
                fetch_start = start_dt.replace(day=1)

            fetch_end = end_dt.replace(day=1)

            # 逐月抓取
            curr = fetch_start
            months_to_fetch = []
            while curr <= fetch_end:
                months_to_fetch.append((curr.year, curr.month))
                # 下一個月
                if curr.month == 12:
                    curr = curr.replace(year=curr.year + 1, month=1)
                else:
                    curr = curr.replace(month=curr.month + 1)

            self.logger.info(f"[{symbol}] 準備向 TWSE 抓取 {len(months_to_fetch)} 個月份之歷史數據...")
            all_dfs = []
            for y, m in months_to_fetch:
                m_df = self.fetch_monthly_history(code, y, m)
                if not m_df.empty:
                    all_dfs.append(m_df)

            if all_dfs:
                combined_df = pd.concat(all_dfs)
                combined_df = combined_df[~combined_df.index.duplicated(keep="last")]
                # 存入 SQLite
                self.storage.upsert_prices(combined_df, symbol, "1d")
                # 更新 ticker_info
                name_map = {"0050": "元大台灣50", "00935": "野村臺灣新科技50"}
                name = name_map.get(code, f"台股_{code}")
                self.storage.upsert_ticker_info(symbol, name=name, asset_type="etf", source="twse")
                # 同步導出 JSON 快取
                self.export_prices_to_json()

        # 從資料庫查詢所需區間
        df_out = self.storage.query_prices(symbol, "1d", start_date, end_date)
        return df_out
