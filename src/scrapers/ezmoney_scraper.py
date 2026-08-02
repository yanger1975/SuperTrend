import os
import json
import logging
from datetime import datetime
from typing import Tuple, Optional, Dict, Any
import requests
from bs4 import BeautifulSoup
import pandas as pd
import sqlite3
from src.storage import SQLiteStorage


class EzMoneyScraper:
    def __init__(self, db_path: str = "data/market_data.db", json_path: str = "data/ezmoney.json"):
        self.storage = SQLiteStorage(db_path)
        self.json_path = json_path
        self.logger = logging.getLogger(__name__)
        self.mapping = self._load_mapping()

    def _load_mapping(self) -> Dict[str, str]:
        if os.path.exists(self.json_path):
            try:
                with open(self.json_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                self.logger.warning("載入 ezmoney.json 失敗: %s", e)
        return {}

    def to_roc_date(self, ad_date_str: str) -> str:
        try:
            dt = pd.to_datetime(ad_date_str)
            roc_year = dt.year - 1911
            return f"{roc_year}/{dt.month:02d}/{dt.day:02d}"
        except Exception:
            return ad_date_str

    def to_ad_date(self, roc_date_str: str) -> str:
        try:
            parts = roc_date_str.strip().split("/")
            if len(parts) != 3:
                return roc_date_str
            ad_year = int(parts[0]) + 1911
            month = int(parts[1])
            day = int(parts[2])
            return f"{ad_year:04d}-{month:02d}-{day:02d}"
        except Exception:
            return roc_date_str

    def resolve_symbol(self, symbol_or_name: str) -> Tuple[str, str, str]:
        clean_input = symbol_or_name.strip()

        # 狀況 1: "33YTW.EZ" 或 "33YTW"
        code = clean_input.replace(".EZ", "").replace(".ez", "")
        name = "未知基金"
        for fund_name, fund_code in self.mapping.items():
            if fund_code == code:
                name = fund_name
                break
            if fund_name == clean_input:
                code = fund_code
                name = fund_name
                break

        full_symbol = f"{code}.EZ"
        return code, name, full_symbol

    def fetch_fund_nav(self, symbol_or_name: str, start_date: Optional[str] = None, end_date: Optional[str] = None, refresh: bool = False) -> pd.DataFrame:
        code, name, full_symbol = self.resolve_symbol(symbol_or_name)

        today = datetime.now()
        today_str = today.strftime("%Y-%m-%d")
        min_supported_start = "2022-01-01"

        if not end_date:
            end_date = today_str

        # EZMoney 伺服器限制最早查詢起算日期為 2022-01-01 (民國 111 年)；若未指定或早於此日期，自動校正為 2022-01-01
        if not start_date or start_date < min_supported_start:
            start_date = min_supported_start

        # 優先查詢本地資料庫
        local_df = self.storage.query_prices(full_symbol, "1d", start_date, end_date)

        need_fetch = False
        if refresh or local_df.empty:
            need_fetch = True
        else:
            latest_local_date = local_df.index.max().strftime("%Y-%m-%d")
            # 若本地最新日期早於目標 end_date 且早於今日，說明需要向上抓取最新淨值
            if latest_local_date < end_date and latest_local_date < today_str:
                need_fetch = True

        if not need_fetch:
            return local_df

        roc_start = self.to_roc_date(start_date)
        roc_end = self.to_roc_date(end_date)

        url = "https://www.ezmoney.com.tw/funds/nav"
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

        try:
            r_get = session.get(url, timeout=10)
            soup_get = BeautifulSoup(r_get.text, "html.parser")
            token_tag = soup_get.find("input", {"name": "__RequestVerificationToken"})
            token = token_tag.get("value") if token_tag else ""

            payload = {
                "__RequestVerificationToken": token,
                "start": roc_start,
                "end": roc_end,
                "Fund": code
            }

            r_post = session.post(url, data=payload, timeout=15)
            r_post.encoding = "utf-8"
            soup_post = BeautifulSoup(r_post.text, "html.parser")
            tables = soup_post.find_all("table")

            if len(tables) < 2:
                return local_df if not local_df.empty else pd.DataFrame()

            table = tables[1]
            rows = table.find_all("tr")
            parsed_data = []

            for tr in rows[1:]:
                cols = [td.text.strip().replace("\r", "").replace("\n", "").replace(" ", "") for td in tr.find_all("td")]
                if len(cols) >= 2:
                    roc_d = cols[0].replace("日期", "")
                    ad_d = self.to_ad_date(roc_d)
                    try:
                        nav_str = cols[1].replace("基金淨值", "").replace(",", "")
                        nav = float(nav_str)
                    except ValueError:
                        continue

                    parsed_data.append({
                        "Date": pd.to_datetime(ad_d),
                        "Open": 0.0,
                        "High": 0.0,
                        "Low": 0.0,
                        "Close": nav,
                        "Volume": 0.0
                    })

            if not parsed_data:
                return local_df if not local_df.empty else pd.DataFrame()

            df = pd.DataFrame(parsed_data)
            df = df.sort_values("Date").reset_index(drop=True)
            df.set_index("Date", inplace=True)

            # 寫入 SQLite 元數據與價格歷史 (指定 source="ezmoney")
            self.storage.upsert_ticker_info(full_symbol, name, "fund", "ezmoney")
            self.storage.upsert_prices(df, full_symbol, "1d", source="ezmoney")

            return self.storage.query_prices(full_symbol, "1d", start_date, end_date)
        except (requests.RequestException, ValueError, KeyError, IndexError, sqlite3.Error) as e:
            self.logger.error("Error fetching fund nav for %s: %s", full_symbol, e)
            return local_df if not local_df.empty else pd.DataFrame()
        finally:
            session.close()
