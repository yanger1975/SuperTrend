# 設計規格書：臺灣證券交易所 (TWSE) 台股 SuperTrend 策略擴充

- **日期**：2026-10-11
- **狀態**：設計已獲審查通過 (Approved)
- **目標標的**：`0050.TW`, `00935.TW` 等臺灣上市股票與 ETF
- **數據來源**：臺灣證券交易所 (TWSE) 官方 OpenAPI 與市場歷史報表

---

## 1. 背景與目標 (Background & Objectives)

本專案原先以美股 ETF 與個股為主要標的（經由 yfinance 抓取）。為將 SuperTrend / HMA 順勢交易系統擴展至台股市場（例如 `0050.TW`、`00935.TW`），本規格書設計一套專為**臺灣證券交易所 (TWSE) 官方數據**打造的爬蟲與快取模組，滿足以下核心目標：

1. **官方直接數據來源**：直接對接 TWSE 官方開放端點，獲取具備權威性之每日價量數據（Open, High, Low, Close, Volume）。
2. **雙端點架構 (Two-Endpoint Architecture)**：
   - 歷史回測與優化：透過 `/exchangeReport/STOCK_DAY` 按月抓取 2 年歷史 K 線，並具備頻率控制與防限速重試機制。
   - 當日快速訊號掃描：透過 OpenAPI `/v1/exchangeReport/STOCK_DAY_ALL` 一次取得全市場最新單日盤後收盤價量。
3. **無狀態 CI 與本地 DB 雙向同步機制**：
   - 本地端：快取於 SQLite `data/market_data.db`，並自動同步備份為輕量化 `data/twse_prices.json`（納入 Git 版控）。
   - 雲端 CI (GitHub Actions)：於無狀態環境中從 `data/twse_prices.json` 毫秒級恢復 2 年歷史，每日僅增量抓取最新數據，避免被證交所限速。
   - 本地復原：使用者在本地 `git pull` 後，系統自動將雲端新增之日期同步寫入本地 SQLite DB。
4. **SuperTrend 核心無縫對接**：
   - 標準化數據輸出，直接支援既有的 `compute_supertrend`、`compute_hma`、`ParameterOptimizer` 網格搜尋與 `run_daily_scanner.py`。

---

## 2. 系統架構與檔案劃分 (System Architecture)

### 2.1 新增與修改檔案清單

```text
d:\MyProj\SuperTrend\
├── data\
│   ├── must_have_tw.json          # [NEW] 台股必備標的清單（初始包含 0050.TW, 00935.TW）
│   └── twse_prices.json           # [NEW] 台股歷史日 K 線輕量化 JSON 快取備份
├── src\
│   ├── scrapers\
│   │   ├── __init__.py
│   │   └── twse_scraper.py        # [NEW] TWSE 官方資料抓取器核心
│   └── data_loader.py             # [MOD] 擴充 .TW / 台股分流路由
├── tests\
│   └── test_twse_scraper.py       # [NEW] 證交所爬蟲與資料清洗單元測試
└── run_daily_scanner.py           # [MOD] 引入 must_have_tw.json 支援台股每日掃描
```

---

## 3. 模組詳細設計 (Detailed Module Design)

### 3.1 專屬台股清單：`data/must_have_tw.json`
格式為標準 JSON 陣列：
```json
[
  "0050.TW",
  "00935.TW"
]
```

### 3.2 證交所爬蟲模組：`src/scrapers/twse_scraper.py`

#### 類別介面：`TwseScraper`
```python
class TwseScraper:
    def __init__(self, db_path: str = "data/market_data.db", json_path: str = "data/twse_prices.json"):
        ...
```

#### 核心方法職責：
1. **`resolve_ticker(ticker: str) -> Tuple[str, str]`**：
   - 輸入 `0050.TW` 或 `0050`，輸出純代碼 `0050` 與標準代碼 `0050.TW`。
2. **`to_ad_date(roc_date_str: str) -> str`**：
   - 將民國年字串（如 `113/10/30` 或 `1131030`）轉換為標準西元年字串 `2024-10-30`。
3. **`fetch_monthly_history(code: str, year: int, month: int) -> pd.DataFrame`**：
   - 請求 URL：`https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={YYYYMM01}&stockNo={code}`
   - 欄位清洗：
     - 去除金額、股數與價格字串中的逗號 `,`、正負號與除權息代號。
     - 轉型為 float。
     - 映射為標準欄位：`Open`, `High`, `Low`, `Close`, `Volume`。
   - 頻率保護：每次請求後強制暫停 3.0 秒；若遇 HTTP 429 / 403 則啟用指數退避重試（最長 15 秒）。
4. **`fetch_stock_history(ticker: str, start_date: str, end_date: str, refresh: bool = False) -> pd.DataFrame`**：
   - 查詢 SQLite 資料庫已有的最新日期。
   - 計算需回溯或增量更新的月份清單（例如 2 年前至當月）。
   - 呼叫 `fetch_monthly_history` 取得各月數據，合併後寫入 SQLite `price_history` 與 `ticker_info`。
   - 自動調用 `export_prices_to_json()` 保持 JSON 快取最新。
5. **`fetch_daily_snapshot() -> Dict[str, Dict[str, float]]`**：
   - 請求 URL：`https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL`
   - 單次請求即可獲得當日全市場股票與 ETF 最新收盤價、開高低與成交量。
   - 解析出以代碼為鍵（例如 `0050`）的最新價格字典。
6. **雙向同步機制**：
   - `export_prices_to_json(json_path: str)`：自 SQLite 讀取所有 `.TW` 標的的價格記錄，格式化輸出為輕量化 JSON。
   - `import_prices_from_json(json_path: str)`：於無資料庫或空白資料庫環境下，將 `data/twse_prices.json` 中的歷史記錄批次 Upsert 寫入本地 SQLite。

### 3.3 `DataLoader` 整合 (`src/data_loader.py`)

在 `DataLoader.fetch_data(ticker, start_date, end_date, interval="1d", refresh=False)` 中：
1. **分流判定**：若 `ticker.endswith(".TW")` 或 `ticker.endswith(".tw")` 或代號存在於 `data/must_have_tw.json`：
2. **冷啟動同步**：若本地 SQLite 查無該標的歷史，優先調用 `TwseScraper.import_prices_from_json()` 嘗試自 JSON 恢復歷史。
3. **區間檢驗與增量抓取**：
   - 查詢 SQLite 快取是否已完整覆蓋 `[start_date, end_date]`。
   - 若有日期缺漏或指定 `refresh=True`，呼叫 `TwseScraper.fetch_stock_history()` 下載缺失月份並更新資料庫。
4. **回傳資料**：經由 `validate_and_clean_data(df)` 清洗後回傳標準 OHLCV DataFrame。

### 3.4 每日掃描整合 (`run_daily_scanner.py`)
- 在收集待掃描標的清單時，除了美股 `data/must_have.json` 與熱門股之外，同時讀取 `data/must_have_tw.json`。
- 在推播報告中，台股標的能正確呈現代號、中文名稱（取自 `ticker_info`，如 `元大台灣50`）、最新台幣收盤價、持倉狀態與停損建議價。

---

## 4. 驗證與成功標準 (Verification & Success Criteria)

1. **單元測試驗證 (`tests/test_twse_scraper.py`)**：
   - 民國年日期解析正確，跨世紀與跨年計算無誤。
   - 證交所 API 原始 JSON 資料清洗（含字串逗號、符號過濾）為符合規格之浮點數 DataFrame。
   - SQLite ↔ `twse_prices.json` 雙向同步機制正確無損。
   - `DataLoader.fetch_data("0050.TW", ...)` 成功回傳有效之 OHLCV DataFrame。
2. **回測與參數優化實測**：
   - 成功執行：
     ```bash
     python run_optimization.py --ticker 0050.TW --start 2024-10-11
     ```
     能順利下載 2 年歷史資料，執行 36 組參數網格搜尋，並將最適參數存入資料庫與 `data/optimized_params.json`。
3. **每日掃描實測**：
   - 執行 `python run_daily_scanner.py --dry-run --tickers 0050.TW 00935.TW`，能在終端產出包含台股最新持倉與進出場價的 Telegram 診斷報表。
4. **代碼與規範遵從**：
   - Windows CRLF 換行、UTF-8 no BOM、正體中文。
   - 未獲使用者明確授權前，嚴禁執行 `git commit`。
