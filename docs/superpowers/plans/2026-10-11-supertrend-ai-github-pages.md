# SuperTrend AI 訊號與最適參數 GitHub Pages 靜態儀表板實施計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 為 SuperTrend AI 策略建立純 Python 渲染的自包含靜態網頁儀表板，整合至 GitHub Actions CI/CD 自動發布至 GitHub Pages，在同一頁面以美股與台股/基金分區表格呈現最新交易訊號、進出場價格、最適參數、Score 與 Win Rate，並於 Telegram 推播中附加儀表板連結。

**Architecture:**
1. 於 `run_batch_optimization_supertrend_ai.py` 增設結構化資料輸出，將最新運算訊號保存為 `data/latest_signals_ai.json`。
2. 建立 `src/supertrend_ai/html_generator.py`，作為純 Python、零外部依賴的靜態渲染器，讀取訊號與參數 JSON，生成內嵌深色科技風格 CSS 與 Vanilla JS 互動功能（Tab 切換、標頭排序、即時搜尋）的自包含單頁 `public/index.html`。
3. 批次腳本執行完畢後自動觸發網頁生成，並在 Telegram 推播訊息尾部附加 GitHub Pages 儀表板連結。
4. 擴充 `.github/workflows/daily_supertrend_ai_signals.yml` 工作流，配置 Pages 發布權限，透過 `actions/upload-pages-artifact` 與 `actions/deploy-pages` 實現自動無縫發布，並同步版控 JSON 數據。

**Tech Stack:** Python 3.12, HTML5/CSS3 (Vanilla CSS, Modern Dark Theme), Vanilla JavaScript (零外部依賴), GitHub Actions (Pages 原生部署), Pytest.

**Spec:** [`docs/superpowers/specs/2026-10-11-supertrend-ai-github-pages-design.md`](file:///d:/MyProj/SuperTrend/docs/superpowers/specs/2026-10-11-supertrend-ai-github-pages-design.md)

## Global Constraints
- 所有文字檔案必須使用 Windows CRLF 換行與 UTF-8 (no BOM) 編碼，去除行尾空白。
- 所有文檔與註釋一律使用正體中文（繁體中文），絕不得使用簡體中文。
- 臨時或非持久化檔案統一置於 `temp/` 目錄。
- 嚴格遵守 Git 規範：未經使用者明確授權前，絕不執行任何 `git commit`。

## Review Focus
- **空資料與異常欄位防護**：當 JSON 為空陣列或標的缺少部分指標時，網頁與生成器能優雅呈現「-」或「暫無資料」，不崩潰。
- **XSS 安全防護**：標的代碼與名稱在渲染進 HTML 時，必須經過標準 HTML 跳脫處理 (`html.escape`)。
- **數值格式化相容性**：貨幣單位（`$` vs `NT$`）、百分比符號（帶正負號）、小數位數需自適應股票與基金淨值特性。
- **手機 RWD 排版**：表格容器在行動裝置上自動啟用水平平滑滾動，避免表格破版或壓縮不可讀。
- **CI 部署健全性**：GitHub Pages 部署失敗不應阻斷整個批次腳本的成功退出狀態；本地支援 `--dry-run` 與獨立 CLI 預覽。

---

### Task 1: 最新訊號結構化資料導出 (`data/latest_signals_ai.json`)

**Files:**
- Modify: `run_batch_optimization_supertrend_ai.py`
- Test: `tests/test_latest_signals_export.py`

**Interfaces:**
- Consumes: `processed_results` 運算字典清單（來自 `run_batch_optimization_supertrend_ai.py`）
- Produces: 
  - `export_latest_signals_to_json(results: list, output_path: str = "data/latest_signals_ai.json") -> str`
  - `load_latest_signals_from_json(input_path: str = "data/latest_signals_ai.json") -> list`

- [ ] **Step 1: 編寫失敗的測試 (`tests/test_latest_signals_export.py`)**
  測試匯出函式將包含各項指標的計算結果序列化為合規的 JSON 檔案，並能正確反序列化驗證欄位。
  ```python
  import os
  import json
  import pytest
  from run_batch_optimization_supertrend_ai import export_latest_signals_to_json, load_latest_signals_from_json

  def test_export_and_load_latest_signals(tmp_path):
      test_file = str(tmp_path / "latest_signals_ai.json")
      mock_results = [
          {
              "ticker": "0050.TW",
              "display_name": "元大台灣50",
              "is_fund": False,
              "pos_value": "long",
              "distance_pct": 2.5,
              "raw": {
                  "latest_signal": {
                      "date": "2026-10-11",
                      "close": 195.5,
                      "entry_ref": 188.0,
                      "exit_ref": 190.0,
                      "action": "HOLD_LONG"
                  }
              }
          }
      ]
      out_path = export_latest_signals_to_json(mock_results, output_path=test_file)
      assert os.path.exists(out_path)
      loaded = load_latest_signals_from_json(test_file)
      assert len(loaded) == 1
      assert loaded[0]["ticker"] == "0050.TW"
      assert loaded[0]["position"] == "long"
      assert loaded[0]["currency"] == "NT$"
  ```

- [ ] **Step 2: 執行測試驗證失敗**
  執行: `pytest tests/test_latest_signals_export.py -v`
  預期: FAIL（`ImportError` 或函式未定義）

- [ ] **Step 3: 實作 `export_latest_signals_to_json` 與 `load_latest_signals_from_json`**
  於 `run_batch_optimization_supertrend_ai.py` 實作資料抽取、幣別判斷（`.TW` / `.EZ` 為 `NT$`，美股為 `$`）、安全防護與 JSON 寫入。

- [ ] **Step 4: 執行測試驗證通過**
  執行: `pytest tests/test_latest_signals_export.py -v`
  預期: PASS

- [ ] **Step 5: 驗證狀態**
  確認測試全數通過，暫存變更待整體驗證（依規定未經指示不執行 commit）。

---

### Task 2: 現代深色科技風格 HTML 儀表板生成引擎 (`src/supertrend_ai/html_generator.py`)

**Files:**
- Create: `src/supertrend_ai/html_generator.py`
- Test: `tests/test_html_generator.py`

**Interfaces:**
- Consumes: 
  - `signals`: 訊號字典清單（包含 ticker, name, market, date, close, position, entry_ref, exit_ref, distance_pct 等）
  - `params`: 最佳化參數清單（包含 ticker, atr_length, factor_min/max/step, custom_score, win_rate, cagr, max_drawdown, sharpe_ratio 等）
- Produces: 
  - `generate_dashboard_html(signals: list, params: list, output_path: str = "public/index.html") -> str`
  - CLI 工具：`python -m src.supertrend_ai.html_generator`

- [ ] **Step 1: 編寫失敗的測試 (`tests/test_html_generator.py`)**
  驗證生成之 HTML 包含深色主題樣式、美股與台股/基金 Tab、最新訊號表格、包含 Score 與 Win Rate 的參數表格、以及 XSS 跳脫防護。
  ```python
  import os
  import pytest
  from src.supertrend_ai.html_generator import generate_dashboard_html

  def test_generate_dashboard_html(tmp_path):
      out_html = str(tmp_path / "index.html")
      signals = [
          {"ticker": "SPY", "name": "SPDR S&P 500", "market": "us", "is_fund": False, "date": "2026-10-10", "close": 580.0, "currency": "$", "position": "long", "entry_ref": 570.0, "exit_ref": 575.0, "distance_pct": 0.87, "action": "HOLD_LONG"},
          {"ticker": "0050.TW", "name": "元大台灣50", "market": "tw", "is_fund": False, "date": "2026-10-11", "close": 195.5, "currency": "NT$", "position": "long", "entry_ref": 188.0, "exit_ref": 190.0, "distance_pct": 2.89, "action": "HOLD_LONG"}
      ]
      params = [
          {"ticker": "SPY", "atr_length": 10, "factor_min": 2.0, "factor_max": 5.0, "factor_step": 0.5, "perf_alpha": 10.0, "from_cluster": "Top", "custom_score": 12.5, "win_rate": 0.85, "cagr": 0.185, "max_drawdown": -0.095, "sharpe_ratio": 1.75},
          {"ticker": "0050.TW", "atr_length": 10, "factor_min": 2.0, "factor_max": 5.0, "factor_step": 0.5, "perf_alpha": 20.0, "from_cluster": "Average", "custom_score": 4.81, "win_rate": 0.875, "cagr": 0.265, "max_drawdown": -0.151, "sharpe_ratio": 1.43}
      ]
      result_path = generate_dashboard_html(signals, params, output_path=out_html)
      assert os.path.exists(result_path)
      with open(result_path, "r", encoding="utf-8") as f:
          content = f.read()
      assert "SuperTrend AI" in content
      assert "Score" in content
      assert "Win Rate" in content
      assert "0050.TW" in content
      assert "SPY" in content
      assert "tab-btn" in content
  ```

- [ ] **Step 2: 執行測試驗證失敗**
  執行: `pytest tests/test_html_generator.py -v`
  預期: FAIL（模組不存在）

- [ ] **Step 3: 實作 `src/supertrend_ai/html_generator.py`**
  實作現代科技深色主題 HTML 模板，包含：
  - CSS：CSS 變數、卡片容器、現代無襯線字體、美觀標籤徽章、RWD 響應式表格樣式。
  - Tab 切換按鈕：美股 (US) / 台股與基金 (TW)。
  - 兩組獨立表格：最新訊號表格與最佳化參數表格。
  - JavaScript：標頭點擊升降冪排序、即時搜尋過濾、Tab 標籤切換。
  - 安全保護：`html.escape` 防止 XSS。
  - CLI 入口：支援 `--output`、`--open` 與讀取現有 JSON 檔案。

- [ ] **Step 4: 執行測試驗證通過**
  執行: `pytest tests/test_html_generator.py -v`
  預期: PASS

- [ ] **Step 5: 驗證狀態**
  執行單元測試確保渲染完整，保持工作區乾淨。

---

### Task 3: 批次腳本主流程與 Telegram 連結整合

**Files:**
- Modify: `run_batch_optimization_supertrend_ai.py`
- Test: `tests/test_batch_ai_integration.py`

**Interfaces:**
- Consumes: `src/supertrend_ai/html_generator.py`, `export_latest_signals_to_json`
- Produces: 
  - 批次運行結束時自動產生 `data/latest_signals_ai.json` 與 `public/index.html`
  - Telegram 訊息底部包含 Pages 儀表板連結

- [ ] **Step 1: 編寫失敗的測試 (`tests/test_batch_ai_integration.py`)**
  測試批次主函式在執行報告生成時，Telegram 區塊包含儀表板連結，且 `public/index.html` 被自動生成。
  ```python
  from run_batch_optimization_supertrend_ai import build_telegram_blocks_ai

  def test_telegram_blocks_contain_dashboard_link():
      mock_results = [{
          "ticker": "SPY",
          "display_name": "SPY",
          "is_fund": False,
          "pos_value": "long",
          "distance_pct": 1.0,
          "raw": {"latest_signal": {"date": "2026-10-10", "close": "580", "entry_ref": "570", "exit_ref": "575"}}
      }]
      blocks = build_telegram_blocks_ai(mock_results, is_saturday=False, market_type="us", dashboard_url="https://user.github.io/SuperTrend/")
      joined = "\n".join(blocks)
      assert "https://user.github.io/SuperTrend/" in joined
  ```

- [ ] **Step 2: 執行測試驗證失敗**
  執行: `pytest tests/test_batch_ai_integration.py -v`
  預期: FAIL（`dashboard_url` 參數或連結不存在）

- [ ] **Step 3: 修改 `run_batch_optimization_supertrend_ai.py`**
  1. 於 `build_telegram_blocks_ai` 中增加可選 `dashboard_url` 參數，若有設定或讀取到環境變數 `GITHUB_PAGES_URL`，於報告結尾附加連結。
  2. 於 `main()` 中：運算完成後調用 `export_latest_signals_to_json()` 產生 `data/latest_signals_ai.json`。
  3. 調用 `generate_dashboard_html()` 產生 `public/index.html`。

- [ ] **Step 4: 執行測試驗證通過**
  執行: `pytest tests/test_batch_ai_integration.py -v`
  預期: PASS

- [ ] **Step 5: 驗證狀態**
  確認整合測試通過。

---

### Task 4: GitHub Actions CI/CD 工作流擴充與權限配置

**Files:**
- Modify: `.github/workflows/daily_supertrend_ai_signals.yml`

**Interfaces:**
- Consumes: `public/index.html` 打包目錄與 `data/latest_signals_ai.json`
- Produces: GitHub Pages 原生自動發布與 Git JSON 資料同步

- [ ] **Step 1: 檢視現有工作流並配置 Pages 權限**
  於 `.github/workflows/daily_supertrend_ai_signals.yml` 的 `jobs.scan-and-notify.permissions` 中增加：
  ```yaml
  permissions:
    contents: write
    pages: write
    id-token: write
  ```

- [ ] **Step 2: 增加 GitHub Pages 發布步驟**
  於 `Commit and Push Updated Parameters` 之前/之後增加：
  ```yaml
  - name: Setup Pages
    uses: actions/configure-pages@v5

  - name: Upload Pages Artifact
    uses: actions/upload-pages-artifact@v3
    with:
      path: 'public/'

  - name: Deploy to GitHub Pages
    id: deployment
    uses: actions/deploy-pages@v4
  ```

- [ ] **Step 3: 擴充 Git Commit 包含 `data/latest_signals_ai.json`**
  修改 git commit 步驟：
  ```bash
  git add data/optimized_params_ai.json data/latest_signals_ai.json
  ```
  確保最新訊號數據每日自動同步回 Git 儲存庫。

- [ ] **Step 4: 驗證 YAML 語法**
  檢查 YAML 縮排與語法正確無誤。

---

### Task 5: 系統文檔與技術架構同步更新 (`README.md` & `TechStack.html`)

**Files:**
- Modify: `README.md`
- Modify: `TechStack.html`

**Interfaces:**
- Consumes: 本計畫實作之 GitHub Pages 架構、`html_generator.py`、`data/latest_signals_ai.json`
- Produces: 完整正體中文系統文檔

- [ ] **Step 1: 更新 `README.md`**
  1. 於「系統特點」新增 GitHub Pages 靜態儀表板與即時網頁監控介紹。
  2. 於「預期輸出檔案與資料庫架構」新增 `data/latest_signals_ai.json` 與 `public/index.html` 說明。
  3. 補充本地網頁產生指令（`python -m src.supertrend_ai.html_generator --open`）。
  4. 補充 GitHub 倉庫前置設定說明（Settings -> Pages 來源改選為 GitHub Actions）。

- [ ] **Step 2: 更新 `TechStack.html`**
  1. 於資料流架構圖與模組清單中新增 `src/supertrend_ai/html_generator.py` 與 `public/index.html`。
  2. 補充前端輕量化渲染技術決策（Vanilla JS、CSS 變數、零 Node.js 依賴）。

- [ ] **Step 3: 執行全專案自動化測試驗證**
  執行: `python -m pytest tests/ -v`
  預期: 全部測試 PASS。

---

## Plan Self-Review Checklist
- [x] **Spec coverage**: 所有設計規格書需求均對應至具體 Task（Task 1 資料、Task 2 網頁、Task 3 批次整合、Task 4 CI 發布、Task 5 文檔）。
- [x] **Step scan**: 每一步均定義 Checkable 結果（測試代碼、測試命令、預期結果）。
- [x] **Type consistency**: 函式名稱、簽名與檔案路徑在跨 Task 間維持完全一致。
- [x] **Review focus**: Review Focus 涵蓋空資料防護、XSS 跳脫、RWD 行動端適配與 CI 容錯。
- [x] **Constraints adherence**: 嚴格遵守 CRLF、UTF-8 no BOM、正體中文與未獲許可不 commit 原則。
