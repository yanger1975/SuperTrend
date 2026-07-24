import json
import logging
import os
import re
from typing import List
import requests
from bs4 import BeautifulSoup

class TrendingScraper:
    """
    StockMarketWatch Most Active Stocks 爬蟲
    從 https://stockmarketwatch.com/screen/most-active 獲取最高成交量股票清單。
    具備網路異常時的自動備援 (Fallback) 處理。
    成功爬取時會自動更新備援清單。
    """
    def __init__(self, fallback_file: str = "data/most-active.json"):
        self.fallback_file = fallback_file
        self.url = "https://stockmarketwatch.com/screen/most-active"
        self.logger = logging.getLogger(__name__)

    def load_fallback_tickers(self) -> List[str]:
        if os.path.exists(self.fallback_file):
            with open(self.fallback_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return ["NVDA", "TSLA", "AAPL", "AMD", "PLTR", "MSFT", "AMZN", "GOOGL", "SPY", "QQQ"]

    def save_fallback_tickers(self, tickers: List[str]):
        """將成功爬取的股票清單保存到備援 JSON 檔案"""
        try:
            unique_tickers = list(dict.fromkeys(tickers))[:30]
            with open(self.fallback_file, "w", encoding="utf-8") as f:
                json.dump(unique_tickers, f, ensure_ascii=False, indent=2)
            self.logger.info(f"Updated fallback tickers file with {len(unique_tickers)} symbols")
        except Exception as e:
            self.logger.warning(f"Failed to save fallback tickers: {e}")

    def fetch_top_tickers(self, limit: int = 10) -> List[str]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        }
        try:
            resp = requests.get(self.url, headers=headers, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")

                # 方法 1: 從 JSON-LD 結構化資料提取 (最可靠)
                # 尋找 type="application/ld+json" 且包含 ItemList 的 script 標籤
                for script in soup.find_all("script", type="application/ld+json"):
                    try:
                        data = json.loads(script.string)
                        if isinstance(data, dict) and data.get("@type") == "ItemList":
                            items = data.get("itemListElement", [])
                            tickers = []
                            for item in items:
                                identifier = item.get("identifier")
                                if identifier:
                                    tickers.append(identifier)
                            if len(tickers) >= 3:
                                self.save_fallback_tickers(tickers)
                                return tickers[:limit]
                    except Exception:
                        continue

                # 方法 2: 從表格提取 (備用)
                # 尋找包含股票代碼的表格
                for table in soup.find_all("table"):
                    rows = table.find_all("tr")
                    if len(rows) > 5:  # 至少有標題行 + 幾行資料
                        tickers = []
                        for row in rows[1:]:  # 跳過標題行
                            cells = row.find_all(["td", "th"])
                            if len(cells) >= 2:
                                # 通常第 2 欄是 Symbol
                                symbol_link = cells[1].find("a")
                                if symbol_link:
                                    symbol = symbol_link.get_text(strip=True).upper()
                                    if symbol and symbol.isalpha() and len(symbol) <= 5:
                                        tickers.append(symbol)
                        if len(tickers) >= 3:
                            self.save_fallback_tickers(tickers)
                            return tickers[:limit]

        except Exception as e:
            self.logger.warning(f"Failed to scrape StockMarketWatch most active ({e}). Switching to fallback list.")

        # Fallback to saved list
        fallback = self.load_fallback_tickers()
        return fallback[:limit]
