# 共同基金淨值數據擷取與 SQLite 整合系統設計規格書 (EZMoney Scraper Design Spec)

## 1. 系統概述與目標 (Overview & Goal)

本模組旨在擴充專案的資料擷取能力，新增 **台灣公募共同基金（EZMoney 統一投信）** 的歷史淨值自動下載與快取機制。
下載後的基金淨值將寫入本地 SQLite 資料庫 (`data/market_data.db`)，並整合至 `DataLoader`，使左側交易回測引擎 (`DCAAddOnBacktester`)、CLI 腳本與 Jupyter Notebook 能無縫進行共同基金的定期定額與低檔加碼回測。

---

## 2. 核心設計與變更決策 (Design Decisions)

1. **專屬 Scraper 模組位置 (`src/scrapers/ezmoney_scraper.py`)**：
   - 新增 `src/scrapers/` 目錄，專門放置第三方數據源擷取器。
   - `EzMoneyScraper` 負責管理 HTTP Session、擷取 ASP.NET `__RequestVerificationToken` 防偽權杖、轉換民國年與西元年、解析 HTML 淨值表格，並妥善處理基金成立日較晚的邊界例外。

2. **Ticker 命名規範**：
   - SQLite 資料庫中使用 `{代號}.EZ` 作為 Ticker 主鍵（例如 `33YTW.EZ`、`06YTW.EZ`）。
   - 區分股票/ETF（如 `SPY`, `0050.TW`）與共同基金，防止撞名。

3. **新增 SQLite 元數據資料表 (`ticker_info`)**：
   - 在 `src/storage.py` 的 `SQLiteStorage` 中新增 `ticker_info` 表格，紀錄 Ticker 對應之中文全名、資產類別與資料來源。

4. **價格欄位補零規則 (Open/High/Low)**：
   - 共同基金每日僅有收盤淨值 (Close / NAV)。
   - 寫入 `price_history` 資料表時，`close` 欄位填入 NAV，`open`、`high`、`low`、`volume` 均補 `0.0`，`source` 標註為 `'ezmoney'`。
   - 相容性調整：更新 `DataLoader.validate_and_clean_data`，確保當 `open` 或 `high` 為 0 時，不強制用 Close 覆蓋修正。

5. **DataLoader 自動路由與 `data/ezmoney.json` 整合**：
   - 讀取 `data/ezmoney.json` 設定檔（包含基金中文名稱與 API 代號對照表）。
   - 當呼叫 `DataLoader.fetch_data(ticker)` 且 Ticker 以 `.EZ` 結尾或屬於 ezmoney 基金時，自動調用 `EzMoneyScraper` 進行線上下載與快取更新。

---

## 3. 詳細模組與資料庫 Schema 規格 (Specifications)

### 3.1 `src/storage.py` Schema 擴充

#### 新增 `ticker_info` 資料表：
```sql
CREATE TABLE IF NOT EXISTS ticker_info (
    ticker TEXT NOT NULL PRIMARY KEY,
    name TEXT NOT NULL,
    asset_type TEXT NOT NULL,  -- 'fund', 'etf', 'stock'
    source TEXT NOT NULL,      -- 'ezmoney', 'yfinance'
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

#### `SQLiteStorage` 新增方法：
- `upsert_ticker_info(ticker: str, name: str, asset_type: str, source: str)`
- `get_ticker_info(ticker: str) -> Optional[Dict[str, Any]]`

### 3.2 `src/scrapers/ezmoney_scraper.py` 模組規格

```python
class EzMoneyScraper:
    def __init__(self, db_path: str = "data/market_data.db", json_path: str = "data/ezmoney.json"):
        ...

    def fetch_fund_nav(self, symbol_or_code: str, start_date: str = "2020-01-01", end_date: str = None) -> pd.DataFrame:
        """
        1. 自動解析代碼 (如 33YTW.EZ -> 33YTW) 並取得基金中文名稱。
        2. 將西元日期 (YYYY-MM-DD) 轉換為民國年格式 (YYY/MM/DD)。
        3. 發送 GET 請求獲取 Session Cookie 與 __RequestVerificationToken。
        4. 發送 POST 請求獲取 HTML 淨值表格。
        5. 解析 HTML 表格，將民國年轉回西元年格式，欄位設為 ['Date', 'Open', 'High', 'Low', 'Close', 'Volume'] (Open/High/Low/Volume補0)。
        6. 例外處理：若基金成立日晚於 start_date，自動回傳實際可取得之歷史淨值序列，不拋出錯誤。
        7. 自動更新 SQLite price_history 與 ticker_info 資料表。
        """
```

### 3.3 `src/data_loader.py` 整合與路由

```python
# DataLoader.fetch_data() 中的路由邏輯：
if ticker.endswith(".EZ") or ticker in ezmoney_mapping:
    scraper = EzMoneyScraper(self.storage.db_path)
    return scraper.fetch_fund_nav(ticker, start_date, end_date)
```

---

## 4. 驗證與測試計畫 (Verification & Testing Plan)

1. **單元測試 (`tests/test_ezmoney_scraper.py`)**：
   - 測試民國年與西元年雙向轉換邏輯 (`2025-01-02` <-> `114/01/02`)。
   - 測試代碼解析 (`33YTW.EZ` -> `33YTW` 與中文名稱 `統一全球新科技基金`)。
   - 測試 Mock POST 回應解析與欄位補零 (`Open=0, High=0, Low=0`)。
   - 測試 `ticker_info` 與 `price_history` 資料庫寫入與讀取。
2. **實體整合測試 (`tests/test_fund_integration.py`)**：
   - 實體對 `33YTW.EZ` (統一全球新科技基金) 執行線上抓取測試，驗證取得筆數大於 0 且日期遞增無誤。
   - 使用 `run_dca_backtest.py --symbol 33YTW.EZ` 執行左側加碼策略回測，驗證是否能正常產出 HTML 報告。

---

## 5. 設計自檢 (Spec Self-Check)

- **占位符檢查**：無 TODO、無待定字樣，所有結構與類別皆已明確定義。
- **內部一致性**：`33YTW.EZ` 後綴、`ticker_info` 資料表與 `source='ezmoney'` 在各模組間保持 100% 一致。
- **邊界保護**：處理基金成立日晚於 2020 年之資料截斷例外，並調整 Data Cleaning 邏輯避免 0 價覆蓋。
