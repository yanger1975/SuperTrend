# DCA 左側交易系統拆分至獨立專案 (ETF_DCA) 實施計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 將 DCA 左側交易系統（定期定額 + 低檔加碼）從 `SuperTrend` 專案拆分並建立獨立專案 `d:\MyProj\ETF_DCA`，並對 `SuperTrend` 進行依賴解耦與殘留清理。

**Architecture:** 
1. 在 `d:\MyProj\ETF_DCA` 建立完整專案結構，包含數據層 (`storage.py`, `data_loader.py`, `ezmoney_scraper.py`) 與核心策略層 (`src/dca/`)，更新模組路徑由 `src.dca_addon` 改為 `src.dca`。
2. 移轉 CLI 工具、研究 Notebook、歷史產出 HTML 報告與 SuperPowers 規格文檔至新專案，並產出新專案專屬之 `README.md` 與 `TechStack.html`。
3. 重構 `SuperTrend` 專案的 `test_fund_integration.py` 解除對 DCA 的依賴，刪除原專案的 DCA 程式碼、測試與報告，並同步更新 `SuperTrend` 的 `README.md`、`TechStack.html` 與記憶庫。

**Tech Stack:** Python 3.12, Pandas, Numpy, Plotly, Requests, BeautifulSoup4, SQLite, Pytest.

**Spec:** `docs/superpowers/specs/2026-10-10-extract-dca-to-separate-project-design.md`

## Global Constraints
- 所有文字檔案必須使用 Windows CRLF 換行與 UTF-8 (no BOM) 編碼。
- 所有文檔與註釋一律使用正體中文（繁體中文），嚴禁簡體中文。
- 臨時或非持久化檔案統一置於 `temp/` 目錄。
- 嚴格遵守 Git 規範：未經使用者明確授權前，絕不執行任何 `git commit`。

## Review Focus
- 模組引用路徑替換：確保新專案內部所有 `src.dca_addon` 完整更新為 `src.dca`，無殘留舊路徑。
- 測試環境獨立性：新專案透過 `PYTHONPATH` 與 `pytest` 能在完全獨立的環境下全部通過測試。
- 原專案解耦完整性：`SuperTrend` 移除 `dca_addon` 後，原有 11 個測試模組依然全數通過，無任何殘留 import。
- 歷史產出報告完整性：原專案暫存的 HTML 回測報告安全遷移至新專案根目錄，無數據遺失。
- 雙向文檔同步：兩專案之 `README.md` 與 `TechStack.html` 精準反映各自職責，無交叉混淆內容。

---

### Task 1: 建立 `d:\MyProj\ETF_DCA` 專案骨架與環境設定檔案

**Files:**
- Create: `d:\MyProj\ETF_DCA\.agents\AGENTS.md`
- Create: `d:\MyProj\ETF_DCA\requirements.txt`
- Create: `d:\MyProj\ETF_DCA\pytest.ini`
- Create: `d:\MyProj\ETF_DCA\.gitignore`
- Create: `d:\MyProj\ETF_DCA\.env.example`
- Create: `d:\MyProj\ETF_DCA\data\ezmoney.json`
- Create: `d:\MyProj\ETF_DCA\temp\` (目錄)

**Interfaces:**
- Consumes: `d:\MyProj\SuperTrend` 之現有環境設定與基金代碼表
- Produces: `d:\MyProj\ETF_DCA` 之標準量化專案基礎環境配置

- [ ] **Step 1: 建立目標目錄結構**
  建立 `d:\MyProj\ETF_DCA`、`src`、`data`、`tests`、`docs`、`notebooks`、`temp`、`.agents` 目錄。

- [ ] **Step 2: 建立 `.agents/AGENTS.md` 與專案工作規範**
  寫入正體中文規範、Windows CRLF、UTF-8 no BOM 與 temp/ 規範。

- [ ] **Step 3: 建立 `requirements.txt`、`pytest.ini`、`.gitignore`、`.env.example` 與 `data/ezmoney.json`**
  複製並精簡環境依賴（移除 scikit-learn 等 AI 專用套件），設定 pytest `pythonpath = .`。

- [ ] **Step 4: 驗證環境配置檔案存在**
  使用 powershell 檢查目錄與關鍵檔案是否全部建立就緒。

---

### Task 2: 移轉數據存儲與爬蟲基礎設施至 `d:\MyProj\ETF_DCA`

**Files:**
- Create: `d:\MyProj\ETF_DCA\src\storage.py`
- Create: `d:\MyProj\ETF_DCA\src\scrapers\__init__.py`
- Create: `d:\MyProj\ETF_DCA\src\scrapers\ezmoney_scraper.py`
- Create: `d:\MyProj\ETF_DCA\src\data_loader.py`
- Create: `d:\MyProj\ETF_DCA\tests\test_storage.py`
- Create: `d:\MyProj\ETF_DCA\tests\test_data_loader.py`
- Create: `d:\MyProj\ETF_DCA\tests\test_ezmoney_scraper.py`

**Interfaces:**
- Consumes: `d:\MyProj\SuperTrend\src\storage.py`, `src\data_loader.py`, `src\scrapers\ezmoney_scraper.py`
- Produces: `DataLoader.fetch_data()`, `SQLiteStorage`, `EzMoneyScraper` 提供給 DCA 引擎

- [ ] **Step 1: 移轉 `storage.py`、`data_loader.py` 與 `scrapers/ezmoney_scraper.py`**
  將數據載入器、SQLite 存儲層與 EZMoney 基金爬蟲寫入至新專案 `src/`。

- [ ] **Step 2: 複製並配置對應之單元測試檔**
  建立 `tests/test_storage.py`、`tests/test_data_loader.py`、`tests/test_ezmoney_scraper.py`。

- [ ] **Step 3: 執行新專案數據層單元測試驗證**
  在指令中以 `PYTHONPATH=d:\MyProj\ETF_DCA` 執行：
  ```bash
  python -m pytest d:\MyProj\ETF_DCA\tests\test_data_loader.py d:\MyProj\ETF_DCA\tests\test_ezmoney_scraper.py -v
  ```
  預期：全部 PASS。

---

### Task 3: 移轉並重構 DCA 核心模組至 `d:\MyProj\ETF_DCA\src\dca\`

**Files:**
- Create: `d:\MyProj\ETF_DCA\src\dca\__init__.py`
- Create: `d:\MyProj\ETF_DCA\src\dca\config.py`
- Create: `d:\MyProj\ETF_DCA\src\dca\engine.py`
- Create: `d:\MyProj\ETF_DCA\src\dca\metrics.py`
- Create: `d:\MyProj\ETF_DCA\src\dca\optimizer.py`
- Create: `d:\MyProj\ETF_DCA\src\dca\visualizer.py`
- Create: `d:\MyProj\ETF_DCA\tests\test_dca.py`

**Interfaces:**
- Consumes: `DataLoader` 輸出之 OHLCV / NAV 數據
- Produces: `DCAAddOnBacktester`, `StrategyConfig`, `AddOnRule`, `evaluate_performance`, `generate_html_report`

- [ ] **Step 1: 建立 `src/dca/` 各模組並更新引用**
  將 `dca_addon` 程式碼移入 `src/dca/`，並將所有模組內部的 `from src.dca_addon...` 改為 `from src.dca...`。

- [ ] **Step 2: 建立 `tests/test_dca.py`**
  將 `test_dca_addon.py` 內容複製至 `tests/test_dca.py`，並全面將引用路徑改為 `from src.dca...`。

- [ ] **Step 3: 執行 DCA 策略模組測試驗證**
  執行指令：
  ```bash
  python -m pytest d:\MyProj\ETF_DCA\tests\test_dca.py -v
  ```
  預期：測試全數 PASS。

---

### Task 4: 移轉 CLI 腳本、Notebook、歷史報告與文檔至 `d:\MyProj\ETF_DCA`

**Files:**
- Create: `d:\MyProj\ETF_DCA\run_dca_backtest.py`
- Create: `d:\MyProj\ETF_DCA\run_dca_optimizer.py`
- Create: `d:\MyProj\ETF_DCA\notebooks\DCA_Strategy_Research.ipynb`
- Create: `d:\MyProj\ETF_DCA\dca_backtest_report.html`
- Create: `d:\MyProj\ETF_DCA\dca_report.html`
- Create: `d:\MyProj\ETF_DCA\fund_33YTW_report.html`
- Create: `d:\MyProj\ETF_DCA\docs\superpowers\specs\`
- Create: `d:\MyProj\ETF_DCA\docs\superpowers\plans\`
- Create: `d:\MyProj\ETF_DCA\README.md`
- Create: `d:\MyProj\ETF_DCA\TechStack.html`

**Interfaces:**
- Consumes: `src.dca` 核心模組
- Produces: 獨立完整的左側量化交易系統使用介面與文檔

- [ ] **Step 1: 移轉並更新 CLI 工具與 Notebook**
  - 移轉 `run_dca_backtest.py` 與 `run_dca_optimizer.py`，更新 import 為 `src.dca`。
  - 複製 `notebooks/DCA_Strategy_Research.ipynb`，更新 cell 中的 import 為 `src.dca`。

- [ ] **Step 2: 移轉歷史報告與專屬文檔**
  - 將 `dca_backtest_report.html`、`dca_report.html`、`fund_33YTW_report.html` 複製至新專案根目錄。
  - 複製 `docs/python_回測框架_ETF加碼策略.md`、`docs/該如何呈現回測報告的績效指標與圖表.md`。
  - 將 DCA 規格書、計畫書與本次拆分設計書複製至 `docs/superpowers/specs/` 與 `plans/`。

- [ ] **Step 3: 編寫新專案之 `README.md` 與 `TechStack.html`**
  詳細記錄 ETF_DCA 的安裝方式、CLI 指令、參數說明、架構設計與 Plotly 報告格式。

- [ ] **Step 4: 驗證新專案全套測試與 CLI 回測**
  - 執行 `python -m pytest d:\MyProj\ETF_DCA\tests -v`，確認所有測試 PASS。
  - 執行回測測試：
    ```bash
    powershell -Command "$env:PYTHONPATH='d:\MyProj\ETF_DCA'; python d:\MyProj\ETF_DCA\run_dca_backtest.py --help"
    ```
    預期：輸出標準 CLI 說明無錯誤。

---

### Task 5: 解耦與清理原專案 `d:\MyProj\SuperTrend`

**Files:**
- Modify: `d:\MyProj\SuperTrend\tests\test_fund_integration.py`
- Modify: `d:\MyProj\SuperTrend\README.md`
- Modify: `d:\MyProj\SuperTrend\TechStack.html`
- Modify: `d:\MyProj\SuperTrend\.agents\memory.md`
- Delete: `d:\MyProj\SuperTrend\src\dca_addon/`
- Delete: `d:\MyProj\SuperTrend\run_dca_backtest.py`
- Delete: `d:\MyProj\SuperTrend\run_dca_optimizer.py`
- Delete: `d:\MyProj\SuperTrend\notebooks\DCA_AddOn_Strategy_Research.ipynb`
- Delete: `d:\MyProj\SuperTrend\tests\test_dca_addon.py`
- Delete: `d:\MyProj\SuperTrend\dca_backtest_report.html`
- Delete: `d:\MyProj\SuperTrend\dca_report.html`
- Delete: `d:\MyProj\SuperTrend\fund_33YTW_report.html`

**Interfaces:**
- Consumes: 獨立完成之 `d:\MyProj\ETF_DCA`
- Produces: 乾淨無 DCA 依賴的純粹右側順勢交易系統

- [ ] **Step 1: 重構 `tests/test_fund_integration.py`**
  移除對 `dca_addon` 的引用，改為驗證基金價格載入、元數據寫入及與指標模組之相容性。

- [ ] **Step 2: 刪除 `SuperTrend` 中之 DCA 檔案與暫存報告**
  刪除 `src/dca_addon/`、`run_dca_*.py`、`notebooks/DCA_AddOn_Strategy_Research.ipynb`、`tests/test_dca_addon.py` 與根目錄的 `*.html` 回測報告。

- [ ] **Step 3: 更新 `SuperTrend` 之 `README.md`、`TechStack.html` 與 `.agents/memory.md`**
  移除左側交易章節，記載拆分完成並專注於右側順勢交易架構。

- [ ] **Step 4: 執行 `SuperTrend` 全套單元測試驗證**
  執行 `python -m pytest`。
  預期：所有測試全數通過（無 ImportError、無殘留依賴）。

- [ ] **Step 5: 驗證狀態彙整與報告**
  向使用者報告兩專案的拆分成果與驗證狀態，等待使用者給予進一步指示（絕不擅自執行 git commit）。
