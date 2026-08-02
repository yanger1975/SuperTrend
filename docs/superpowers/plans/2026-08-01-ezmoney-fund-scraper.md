# EZMoney 共同基金淨值擷取與 SQLite 整合 實現計畫

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推薦）或 superpowers:executing-plans 逐任務實現此計畫。步驟使用複選框（`- [ ]`）語法來跟踪進度。

**目標：** 構建獨立的 EZMoney 共同基金淨值爬蟲模組 (`src/scrapers/ezmoney_scraper.py`)，擴充 SQLite 資料庫以支援 `ticker_info` 元數據，並整合進 `DataLoader`，使共同基金淨值能無縫進行回測。

**架構：** 於 `src/scrapers/` 中建立專屬爬蟲，處理 ASP.NET CSRF 防偽權杖、民國/西元年轉換及 HTML 淨值解析。擴充 `src/storage.py` 的 `ticker_info` 資料表與 `SQLiteStorage` 方法，並於 `src/data_loader.py` 整合 `.EZ` 後綴之自動路由。

**技術棧：** Python 3.10+, requests, beautifulsoup4, pandas, numpy, sqlite3, pytest

---

## 預期建立與修改的檔案列表

- [NEW] `src/scrapers/__init__.py` - Scrapers 模組初始化
- [NEW] `src/scrapers/ezmoney_scraper.py` - EZMoney 共同基金淨值爬蟲類別
- [MODIFY] `src/storage.py` - 新增 `ticker_info` 表格與元數據讀寫方法
- [MODIFY] `src/data_loader.py` - 修正 0 價過濾邏輯並整合 `.EZ` 自動路由
- [NEW] `tests/test_ezmoney_scraper.py` - 淨值爬蟲與日期轉換單元測試
- [NEW] `tests/test_fund_integration.py` - 基金淨值載入與回測整合測試

---

### 任務 1：擴充 `src/storage.py` (新增 `ticker_info` 資料表與讀寫方法)

**檔案：**
- 修改：`src/storage.py`
- 測試：`tests/test_ezmoney_scraper.py`

- [ ] **步驟 1：編寫失敗的測試 (`tests/test_ezmoney_scraper.py`)**

```python
import os
import pytest
from src.storage import SQLiteStorage


def test_ticker_info_schema_and_upsert(tmp_path):
    db_file = str(tmp_path / "test_market_data.db")
    storage = SQLiteStorage(db_path=db_file)

    # 寫入 ticker_info
    storage.upsert_ticker_info(
        ticker="33YTW.EZ",
        name="統一全球新科技基金",
        asset_type="fund",
        source="ezmoney"
    )

    # 讀取 ticker_info
    info = storage.get_ticker_info("33YTW.EZ")
    assert info is not None
    assert info["ticker"] == "33YTW.EZ"
    assert info["name"] == "統一全球新科技基金"
    assert info["asset_type"] == "fund"
    assert info["source"] == "ezmoney"
```

- [ ] **步驟 2：運行測試驗證失敗**

運行：`pytest tests/test_ezmoney_scraper.py::test_ticker_info_schema_and_upsert -v`
預期：FAIL，報錯 "AttributeError: 'SQLiteStorage' object has no attribute 'upsert_ticker_info'"

- [ ] **步驟 3：編寫最少實現代碼 (`src/storage.py`)**

在 `SQLiteStorage._init_db()` 中加入 `ticker_info` 資料表建表語法：

```python
cursor.execute("""
    CREATE TABLE IF NOT EXISTS ticker_info (
        ticker TEXT NOT NULL PRIMARY KEY,
        name TEXT NOT NULL,
        asset_type TEXT NOT NULL,
        source TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
""")
```

在 `SQLiteStorage` 類別中新增 `upsert_ticker_info` 與 `get_ticker_info` 方法：

```python
    def upsert_ticker_info(self, ticker: str, name: str, asset_type: str, source: str):
        """
        寫入或更新標的元數據 (例如中文全名、資產類別、資料來源)。
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ticker_info (ticker, name, asset_type, source)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET
                    name=excluded.name,
                    asset_type=excluded.asset_type,
                    source=excluded.source,
                    updated_at=CURRENT_TIMESTAMP
            """, (ticker, name, asset_type, source))
            conn.commit()
        finally:
            conn.close()

    def get_ticker_info(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        查詢標的之元數據。
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT ticker, name, asset_type, source, created_at, updated_at
                FROM ticker_info
                WHERE ticker=?
            """, (ticker,))
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "ticker": row[0],
                "name": row[1],
                "asset_type": row[2],
                "source": row[3],
                "created_at": row[4],
                "updated_at": row[5]
            }
        finally:
            conn.close()
```

- [ ] **步驟 4：運行測試驗證通過**

運行：`pytest tests/test_ezmoney_scraper.py::test_ticker_info_schema_and_upsert -v`
預期：PASS

---

### 任務 2：建立 `src/scrapers/ezmoney_scraper.py` (日期轉換與 HTML 淨值解析)

**檔案：**
- 建立：`src/scrapers/__init__.py`
- 建立：`src/scrapers/ezmoney_scraper.py`
- 測試：`tests/test_ezmoney_scraper.py`

- [ ] **步驟 1：編寫失敗的測試 (`tests/test_ezmoney_scraper.py`)**

```python
from src.scrapers.ezmoney_scraper import EzMoneyScraper


def test_date_conversion_helpers():
    scraper = EzMoneyScraper()
    # 測試西元轉民國 (2025-01-02 -> 114/01/02)
    roc_date = scraper.to_roc_date("2025-01-02")
    assert roc_date == "114/01/02"

    # 測試民國轉西元 (114/01/02 -> 2025-01-02)
    ad_date = scraper.to_ad_date("114/01/02")
    assert ad_date == "2025-01-02"


def test_symbol_code_resolution():
    scraper = EzMoneyScraper()
    # 測試給予 33YTW.EZ 解析
    code, name, symbol = scraper.resolve_symbol("33YTW.EZ")
    assert code == "33YTW"
    assert name == "統一全球新科技基金"
    assert symbol == "33YTW.EZ"

    # 測試給予中文名稱解析
    code, name, symbol = scraper.resolve_symbol("統一全球新科技基金")
    assert code == "33YTW"
    assert name == "統一全球新科技基金"
    assert symbol == "33YTW.EZ"
```

- [ ] **步驟 2：運行測試驗證失敗**

運行：`pytest tests/test_ezmoney_scraper.py::test_date_conversion_helpers -v`
預期：FAIL，報錯 "ModuleNotFoundError: No module named 'src.scrapers'"

- [ ] **步驟 3：編寫最少實現代碼**

創建 `src/scrapers/__init__.py`：
```python
# src/scrapers/__init__.py
```

創建 `src/scrapers/ezmoney_scraper.py`：
```python
import os
import json
import logging
from datetime import datetime
from typing import Tuple, Optional, Dict, Any
import requests
from bs4 import BeautifulSoup
import pandas as pd
from src.storage import SQLiteStorage


class EzMoneyScraper:
    def __init__(self, db_path: str = "data/market_data.db", json_path: str = "data/ezmoney.json"):
        self.storage = SQLiteStorage(db_path)
        self.json_path = json_path
        self.logger = logging.getLogger(__name__)
        self.mapping = self._load_mapping()

    def _load_mapping(self) -> Dict[str, str]:
        if os.path.exists(self.json_path):
            with open(self.json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def to_roc_date(self, ad_date_str: str) -> str:
        dt = pd.to_datetime(ad_date_str)
        roc_year = dt.year - 1911
        return f"{roc_year}/{dt.month:02d}/{dt.day:02d}"

    def to_ad_date(self, roc_date_str: str) -> str:
        parts = roc_date_str.strip().split("/")
        if len(parts) != 3:
            return roc_date_str
        ad_year = int(parts[0]) + 1911
        month = int(parts[1])
        day = int(parts[2])
        return f"{ad_year:04d}-{month:02d}-{day:02d}"

    def resolve_symbol(self, symbol_or_name: str) -> Tuple[str, str, str]:
        # 清理輸入
        clean_input = symbol_or_name.strip()

        # 狀況 1: "33YTW.EZ" 或 "33YTW"
        code = clean_input.replace(".EZ", "").replace(".ez", "")
        # 尋找中文名稱
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

    def fetch_fund_nav(self, symbol_or_name: str, start_date: str = "2020-01-01", end_date: Optional[str] = None) -> pd.DataFrame:
        code, name, full_symbol = self.resolve_symbol(symbol_or_name)
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")

        # 優先查詢本地資料庫
        local_df = self.storage.query_prices(full_symbol, "1d", start_date, end_date)
        if not local_df.empty:
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
                return pd.DataFrame()

            table = tables[1]
            rows = table.find_all("tr")
            parsed_data = []

            for tr in rows[1:]:
                cols = [td.text.strip().replace("\r", "").replace("\n", "").replace(" ", "") for td in tr.find_all("td")]
                if len(cols) == 4:
                    roc_d = cols[0].replace("日期", "")
                    ad_d = self.to_ad_date(roc_d)
                    nav = float(cols[1].replace("基金淨值", ""))
                    parsed_data.append({
                        "Date": pd.to_datetime(ad_d),
                        "Open": 0.0,
                        "High": 0.0,
                        "Low": 0.0,
                        "Close": nav,
                        "Volume": 0.0
                    })

            if not parsed_data:
                return pd.DataFrame()

            df = pd.DataFrame(parsed_data)
            df = df.sort_values("Date").reset_index(drop=True)
            df.set_index("Date", inplace=True)

            # 寫入 SQLite 元數據與價格歷史
            self.storage.upsert_ticker_info(full_symbol, name, "fund", "ezmoney")
            self.storage.upsert_prices(df, full_symbol, "1d")

            return self.storage.query_prices(full_symbol, "1d", start_date, end_date)
        except Exception as e:
            self.logger.error(f"Error fetching fund nav for {full_symbol}: {e}")
            return pd.DataFrame()
```

- [ ] **步驟 4：運行測試驗證通過**

運行：`pytest tests/test_ezmoney_scraper.py::test_date_conversion_helpers tests/test_ezmoney_scraper.py::test_symbol_code_resolution -v`
預期：PASS

---

### 任務 3：修改 `src/data_loader.py` (更新清洗邏輯與 `.EZ` 自動路由)

**檔案：**
- 修改：`src/data_loader.py`
- 測試：`tests/test_ezmoney_scraper.py`

- [ ] **步驟 1：編寫失敗的測試 (`tests/test_ezmoney_scraper.py`)**

```python
def test_data_loader_preserves_zero_open_high_low():
    from src.data_loader import DataLoader
    loader = DataLoader()
    raw_df = pd.DataFrame({
        "Open": [0.0, 0.0],
        "High": [0.0, 0.0],
        "Low": [0.0, 0.0],
        "Close": [117.15, 117.60],
        "Volume": [0.0, 0.0]
    }, index=pd.to_datetime(["2026-07-22", "2026-07-23"]))

    cleaned = loader.validate_and_clean_data(raw_df)
    assert not cleaned.empty
    # 對於基金，Open/High/Low 為 0 不應被覆蓋強制校正
    assert (cleaned["Close"] > 0).all()
```

- [ ] **步驟 2：運行測試驗證失敗**

運行：`pytest tests/test_ezmoney_scraper.py::test_data_loader_preserves_zero_open_high_low -v`
預期：FAIL

- [ ] **步驟 3：修改 `src/data_loader.py` 程式碼**

更新 `DataLoader.validate_and_clean_data` 避開 0 價覆蓋校正：

```python
        # 4. 價格區間合法性檢查 (僅針對正常股票/ETF，若 High/Low/Open 均為 0 則視為基金淨值保持原狀)
        is_fund = (df["Open"] == 0) & (df["High"] == 0) & (df["Low"] == 0)
        stock_mask = ~is_fund
        if stock_mask.any():
            max_limit = df.loc[stock_mask, ["Open", "Close"]].max(axis=1)
            min_limit = df.loc[stock_mask, ["Open", "Close"]].min(axis=1)
            df.loc[stock_mask, "High"] = np.maximum(df.loc[stock_mask, "High"], max_limit)
            df.loc[stock_mask, "Low"] = np.minimum(df.loc[stock_mask, "Low"], min_limit)

        return df
```

在 `DataLoader.fetch_data` 頂部加入 `.EZ` 自動路由：

```python
        # 檢查是否為 EZMoney 基金標的 (.EZ 結尾或存在於 ezmoney.json 中)
        from src.scrapers.ezmoney_scraper import EzMoneyScraper
        ez_scraper = EzMoneyScraper(self.storage.db_path)
        if ticker.endswith(".EZ") or ticker in ez_scraper.mapping:
            return ez_scraper.fetch_fund_nav(ticker, start_date, end_date)
```

- [ ] **步驟 4：運行測試驗證通過**

運行：`pytest tests/test_ezmoney_scraper.py::test_data_loader_preserves_zero_open_high_low -v`
預期：PASS

---

### 任務 4：建立基金實體整合測試 (`tests/test_fund_integration.py`)

**檔案：**
- 建立：`tests/test_fund_integration.py`

- [ ] **步驟 1：編寫實體抓取與回測測試 (`tests/test_fund_integration.py`)**

```python
import pytest
import pandas as pd
from src.data_loader import DataLoader
from src.dca_addon.config import StrategyConfig, AddOnRule
from src.dca_addon.engine import DCAAddOnBacktester
from src.dca_addon.metrics import evaluate_performance


@pytest.mark.integration
def test_ezmoney_fund_fetch_and_backtest():
    loader = DataLoader()
    # 抓取 統一全球新科技基金 (33YTW.EZ)
    df = loader.fetch_data("33YTW.EZ", start_date="2024-01-01", end_date="2026-07-24")

    assert not df.empty
    assert "Close" in df.columns
    assert len(df) > 100

    # 執行左側加碼策略回測
    config = StrategyConfig(
        base_invest_amount=10000,
        rules=[
            AddOnRule(lookback_days=20, drawdown_threshold=0.05, multiplier=2.0)
        ],
        total_extra_budget=500000
    )

    bt = DCAAddOnBacktester(df, config)
    equity, trades = bt.run()
    perf = evaluate_performance(equity, trades, config)

    assert not equity.empty
    assert "total_return" in perf
    assert perf["total_cost"] > 0
```

- [ ] **步驟 2：運行測試驗證通過**

運行：`pytest tests/test_fund_integration.py -v`
預期：PASS

---

## 執行交接

計畫已完成並保存到 [docs/superpowers/plans/2026-08-01-ezmoney-fund-scraper.md](file:///d:/MyProj/SuperTrend/docs/superpowers/plans/2026-08-01-ezmoney-fund-scraper.md)。兩種執行方式：

**1. 子代理驅動（推薦）** - 必需子技能：使用 `superpowers:subagent-driven-development`，每個任務調度一個新的子代理，任務間進行審查，快速疊代。

**2. 內聯執行** - 必需子技能：使用 `superpowers:executing-plans`，在當前會話中批量執行並設有檢查點供審查。

**請告訴我您想選擇哪一種執行方式？**
