# 臺灣證券交易所 (TWSE) 台股 SuperTrend 策略擴充實施計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 為 SuperTrend 交易系統擴充臺灣證券交易所 (TWSE) 官方數據爬蟲與快取機制，支援 `0050.TW` 與 `00935.TW` 等台股標的進行 2 年歷史日 K 線抓取、參數網格尋優與每日交易訊號生成。

**Architecture:** 
1. 建立 `data/must_have_tw.json` 設定檔，管理關注之台股與 ETF 清單。
2. 建立 `src/scrapers/twse_scraper.py`，實作雙端點架構：`/exchangeReport/STOCK_DAY` 歷史按月抓取（含 3 秒防限速延遲）與 OpenAPI `/v1/exchangeReport/STOCK_DAY_ALL` 每日盤後快照；提供 SQLite ↔ `data/twse_prices.json` 雙向同步機制。
3. 於 `src/data_loader.py` 整合 `.TW` 路由分流，優先讀取 SQLite 快取或從 JSON 恢復，缺失時呼叫 `TwseScraper` 下載並持久化。
4. 整合 `run_daily_scanner.py` 與 `run_optimization.py`，支援台股標的參數最佳化與 Telegram 訊號推播。

**Tech Stack:** Python 3.12, Pandas, Numpy, Requests, SQLite, Pytest.

**Spec:** `docs/superpowers/specs/2026-10-11-twse-taiwan-stock-supertrend-design.md`

## Global Constraints
- 所有文字檔案必須使用 Windows CRLF 換行與 UTF-8 (no BOM) 編碼，去除行尾空白。
- 所有文檔與註釋一律使用正體中文（繁體中文），嚴禁簡體中文。
- 臨時或非持久化檔案統一置於 `temp/` 目錄。
- 嚴格遵守 Git 規範：未經使用者明確授權前，絕不執行任何 `git commit`。

## Review Focus
- 民國年轉換邊界：確保民國年（如 `113/10/30`、`1151008`）正確轉換為標準西元年（`2024-10-30`、`2026-10-08`）。
- 數值清洗健全性：去除千分位逗號（`,`）、除權息標記（`X`）與正負價差符號，防範 NaN / ValueError。
- 限速防護與重試：證交所 HTTP 請求維持 3.0 秒安全間隔，遇到 429/403 能指數退避重試。
- 雙向快取一致性：無狀態環境下能自 `data/twse_prices.json` 完美復原歷史，本地新數據亦能自動更新至 JSON。
- 指標運算相容性：輸出的 DataFrame 包含標準 `Open, High, Low, Close, Volume` 與 `DatetimeIndex`，直接相容 `compute_supertrend` 與 `ParameterOptimizer`。

---

### Task 1: 建立台股配置清單 (`data/must_have_tw.json`)

**Files:**
- Create: `data/must_have_tw.json`
- Test: `tests/test_twse_scraper.py`

**Interfaces:**
- Consumes: 無
- Produces: `data/must_have_tw.json` 供 `DataLoader` 與 `run_daily_scanner.py` 讀取

- [x] **Step 1: 編寫失敗的測試 (`tests/test_twse_scraper.py`)**
  測試 `data/must_have_tw.json` 存在且包含 `0050.TW` 與 `00935.TW`。
  ```python
  import json
  import os

  def test_must_have_tw_config():
      path = "data/must_have_tw.json"
      assert os.path.exists(path)
      with open(path, "r", encoding="utf-8") as f:
          tickers = json.load(f)
      assert isinstance(tickers, list)
      assert "0050.TW" in tickers
      assert "00935.TW" in tickers
  ```

- [x] **Step 2: 執行測試驗證失敗**
  執行: `pytest tests/test_twse_scraper.py::test_must_have_tw_config -v`
  預期: FAIL（檔案不存在）

- [x] **Step 3: 建立 `data/must_have_tw.json`**
  寫入 `["0050.TW", "00935.TW"]`。

- [x] **Step 4: 執行測試驗證通過**
  執行: `pytest tests/test_twse_scraper.py::test_must_have_tw_config -v`
  預期: PASS

---

### Task 2: 建立證交所爬蟲核心與資料清洗工具 (`src/scrapers/twse_scraper.py`)

**Files:**
- Create: `src/scrapers/twse_scraper.py`
- Test: `tests/test_twse_scraper.py`

**Interfaces:**
- Consumes: 證交所 API 原始 JSON 格式字串/字典
- Produces: `TwseScraper.resolve_ticker`, `TwseScraper.to_ad_date`, `TwseScraper.parse_stock_day_json`

- [x] **Step 1: 編寫失敗的測試 (`tests/test_twse_scraper.py`)**
  測試代碼解析、民國年轉西元年及原始資料清洗為標準 DataFrame。
  ```python
  import pandas as pd
  from src.scrapers.twse_scraper import TwseScraper

  def test_resolve_ticker_and_date():
      scraper = TwseScraper()
      code, symbol = scraper.resolve_ticker("0050.TW")
      assert code == "0050"
      assert symbol == "0050.TW"
      assert scraper.to_ad_date("113/10/30") == "2024-10-30"
      assert scraper.to_ad_date("1151008") == "2026-10-08"

  def test_parse_stock_day_json():
      scraper = TwseScraper()
      raw_json = {
          "stat": "OK",
          "data": [
              ["113/10/29", "10,000,000", "1,900,000,000", "190.00", "192.00", "189.50", "191.00", "+1.00", "5,000"],
              ["113/10/30", "14,531,256", "2,800,185,309", "192.95", "194.05", "191.50", "191.80", "+0.80", "15,214"]
          ]
      }
      df = scraper.parse_stock_day_json(raw_json)
      assert len(df) == 2
      assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
      assert df.iloc[1]["Close"] == 191.80
      assert df.iloc[1]["Volume"] == 14531256.0
      assert str(df.index[1].date()) == "2024-10-30"
  ```

- [x] **Step 2: 執行測試驗證失敗**
  執行: `pytest tests/test_twse_scraper.py::test_resolve_ticker_and_date tests/test_twse_scraper.py::test_parse_stock_day_json -v`
  預期: FAIL（模組不存在或函式未實作）

- [x] **Step 3: 實作 `src/scrapers/twse_scraper.py` 中的解析與清洗邏輯**
  實作 `TwseScraper` 類別、`resolve_ticker`、`to_ad_date`、`parse_stock_day_json`。

- [x] **Step 4: 執行測試驗證通過**
  執行: `pytest tests/test_twse_scraper.py::test_resolve_ticker_and_date tests/test_twse_scraper.py::test_parse_stock_day_json -v`
  預期: PASS

---

### Task 3: 實作歷史按月抓取、快照與 JSON 雙向快取同步

**Files:**
- Modify: `src/scrapers/twse_scraper.py`
- Test: `tests/test_twse_scraper.py`

**Interfaces:**
- Consumes: `SQLiteStorage`, TWSE REST/OpenAPI
- Produces: `TwseScraper.export_prices_to_json`, `TwseScraper.import_prices_from_json`, `TwseScraper.fetch_stock_history`, `TwseScraper.fetch_daily_snapshot`

- [x] **Step 1: 編寫失敗的測試 (`tests/test_twse_scraper.py`)**
  測試 SQLite 寫入、JSON 導出、從空白 DB 自 JSON 復原、以及 Mock 歷史抓取流程。
  ```python
  def test_twse_prices_json_roundtrip(tmp_path):
      db_file = str(tmp_path / "test_market_data.db")
      json_file = str(tmp_path / "test_twse_prices.json")
      scraper = TwseScraper(db_path=db_file, json_path=json_file)

      # 建立假數據並寫入 SQLite
      dates = pd.date_range("2024-10-01", periods=5, freq="D")
      df = pd.DataFrame({
          "Open": [100.0, 101.0, 102.0, 103.0, 104.0],
          "High": [102.0, 103.0, 104.0, 105.0, 106.0],
          "Low": [99.0, 100.0, 101.0, 102.0, 103.0],
          "Close": [101.0, 102.0, 103.0, 104.0, 105.0],
          "Volume": [1000.0, 2000.0, 1500.0, 3000.0, 2500.0]
      }, index=dates)

      scraper.storage.save_price_history(df, ticker="0050.TW", interval="1d")
      scraper.storage.upsert_ticker_info("0050.TW", "元大台灣50", "etf", "twse")

      # 導出 JSON
      scraper.export_prices_to_json(json_path=json_file)
      assert os.path.exists(json_file)

      # 建立全新空白資料庫並自 JSON 匯入
      empty_db = str(tmp_path / "empty_market_data.db")
      new_scraper = TwseScraper(db_path=empty_db, json_path=json_file)
      imported_count = new_scraper.import_prices_from_json(json_path=json_file)
      assert imported_count > 0

      # 驗證新資料庫能正確讀出
      restored_df = new_scraper.storage.load_price_history("0050.TW", "1d", "2024-10-01", "2024-10-05")
      assert len(restored_df) == 5
      assert restored_df.iloc[0]["Close"] == 101.0
  ```

- [x] **Step 2: 執行測試驗證失敗**
  執行: `pytest tests/test_twse_scraper.py::test_twse_prices_json_roundtrip -v`
  預期: FAIL

- [x] **Step 3: 實作歷史抓取、OpenAPI 快照與 JSON 雙向同步邏輯**
  在 `TwseScraper` 實作：
  - `fetch_monthly_history(code, year, month)` (HTTP 請求 + 3 秒延遲 + 403 重試)
  - `fetch_daily_snapshot()` (OpenAPI 抓取全市場最新單日快照)
  - `export_prices_to_json()` 與 `import_prices_from_json()`
  - `fetch_stock_history(ticker, start_date, end_date, refresh)` (比對 DB 日期，補齊月份並持久化)

- [x] **Step 4: 執行測試驗證通過**
  執行: `pytest tests/test_twse_scraper.py::test_twse_prices_json_roundtrip -v`
  預期: PASS

---

### Task 4: 整合 `DataLoader` 路由與台股快取分流 (`src/data_loader.py`)

**Files:**
- Modify: `src/data_loader.py`
- Test: `tests/test_twse_scraper.py`

**Interfaces:**
- Consumes: `DataLoader.fetch_data("0050.TW", ...)`
- Produces: 標準化 OHLCV DataFrame 供指標與回測引擎使用

- [x] **Step 1: 編寫失敗的測試 (`tests/test_twse_scraper.py`)**
  測試 `DataLoader.fetch_data("0050.TW", ...)` 能自動透過 `TwseScraper` 分流與取得數據。
  ```python
  from src.data_loader import DataLoader

  def test_data_loader_twse_routing(tmp_path, monkeypatch):
      db_file = str(tmp_path / "test_market_data.db")
      json_file = str(tmp_path / "twse_prices.json")
      loader = DataLoader(db_path=db_file)

      # 建立假數據預先存入
      dates = pd.date_range("2024-10-01", periods=10, freq="D")
      sample_df = pd.DataFrame({
          "Open": [100.0] * 10,
          "High": [105.0] * 10,
          "Low": [95.0] * 10,
          "Close": [102.0] * 10,
          "Volume": [50000.0] * 10
      }, index=dates)
      loader.storage.save_price_history(sample_df, ticker="0050.TW", interval="1d")

      df = loader.fetch_data("0050.TW", start_date="2024-10-01", end_date="2024-10-10")
      assert not df.empty
      assert len(df) == 10
      assert "Close" in df.columns
  ```

- [x] **Step 2: 執行測試驗證失敗**
  執行: `pytest tests/test_twse_scraper.py::test_data_loader_twse_routing -v`
  預期: FAIL (DataLoader 尚無 .TW 分流，會嘗試向 yfinance 請求)

- [x] **Step 3: 修改 `src/data_loader.py` 加入台股分流**
  在 `fetch_data()` 中加入判斷：
  ```python
  if ticker.endswith(".TW") or ticker.endswith(".tw") or ticker in twse_must_have:
      # 自動調度 TwseScraper 處理快取、JSON 恢復與增量抓取
  ```

- [x] **Step 4: 執行測試驗證通過**
  執行: `pytest tests/test_twse_scraper.py::test_data_loader_twse_routing -v`
  預期: PASS

---

### Task 5: 每日掃描與參數最佳化整合實測 (`run_daily_scanner.py`, `run_optimization.py`)

**Files:**
- Modify: `run_daily_scanner.py`
- Test: `tests/test_daily_scanner.py`

**Interfaces:**
- Consumes: `data/must_have_tw.json`, `DataLoader`
- Produces: 包含美股與台股的 Telegram 訊號報告，以及台股參數優化結果

- [x] **Step 1: 編寫或更新 `tests/test_daily_scanner.py`**
  確保 `get_target_tickers()` 會合併載入 `must_have_tw.json` 的台股標的。

- [x] **Step 2: 修改 `run_daily_scanner.py` 載入 `must_have_tw.json`**
  更新 `get_target_tickers()` 讀取 `must_have_tw.json`，並在報告中正確標示中文名稱與最新台幣價格。

- [x] **Step 3: 執行 `test_daily_scanner.py` 測試**
  執行: `pytest tests/test_daily_scanner.py -v`
  預期: PASS

- [x] **Step 4: 執行本地 2 年歷史資料抓取與參數最佳化驗證**
  在本地抓取 2 年數據並驗證：
  ```bash
  python run_optimization.py --ticker 0050.TW --start 2024-10-11
  ```
  驗證：成功產出 0050.TW 最佳參數並寫入資料庫與 `data/optimized_params.json`。

- [x] **Step 5: 執行每日掃描 Dry Run 驗證**
  執行: `python run_daily_scanner.py --dry-run --tickers 0050.TW 00935.TW`
  驗證：產出完整訊號診斷報告。

---

### Task 6: 文檔同步與成果報告

**Files:**
- Modify: `README.md`
- Modify: `TechStack.html`
- Modify: `.agents/memory.md`

- [x] **Step 1: 更新 `README.md`**
  新增臺灣證券交易所台股支援說明、`must_have_tw.json` 配置與 CLI 範例。

- [x] **Step 2: 更新 `TechStack.html`**
  記錄 `TwseScraper` 雙端點架構、REST/OpenAPI 端點規範、JSON 雙向快取機制。

- [x] **Step 3: 更新 `.agents/memory.md`**
  記錄台股 TWSE 擴充完工狀態。

- [x] **Step 4: 執行專案全套單元測試驗證**
  執行: `python -m pytest -v`
  預期: 所有測試（原 31 項 + 新增測試）100% PASS。

- [x] **Step 5: 向使用者報告驗證成果（等待 Git Commit 授權）**
