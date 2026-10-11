# 設計規格書：SuperTrend AI 訊號與最適參數 GitHub Pages 靜態儀表板

- **日期**：2026-10-11
- **狀態**：設計已獲審查通過 (Approved)
- **目標標的**：SuperTrend AI 監控之美股與台股/國內基金
- **發布平台**：GitHub Pages (via GitHub Actions 原生部署)

---

## 1. 背景與目標 (Background & Objectives)

本專案之 SuperTrend AI 策略已具備每日自動回測、訊號計算、最適參數網格尋優與 Telegram 即時推播功能。為提供更直觀、具備互動性的可視化監控介面，本規格書設計一套**輕量、自包含且零外部依賴的靜態網頁儀表板 (Static Dashboard)**，整合於 GitHub CI 流水線中並自動發布至 GitHub Pages。

### 核心目標：
1. **專注於 SuperTrend AI 策略**：僅展示 AI 策略之最新訊號與學習參數，維持介面清晰專注。
2. **多市場清晰分流**：同頁面內劃分「美股市場」與「台股與國內基金」兩大區塊，並支援 Tab 標籤切換。
3. **雙核心表格展示**：
   - **最新訊號與價格表**：呈現標的最新收盤價/淨值、目前倉位（🟢 Long / ⚪ Wait）、進出場參考價格、距標百分比與今日動作。
   - **最適參數與評分表**：呈現各標的最新 AI 參數（ATR、Factor 範圍、Alpha、Cluster），並明確揭示 **Score (自訂綜合評分)**、**Win Rate (勝率)**、**CAGR (年化報酬率)**、**Max Drawdown (最大回撤)** 與 **Sharpe Ratio**。
4. **現代科技深色主題與輕量互動**：採用深色科技風（Dark Theme），透過原生 Vanilla JS 提供即時表格標頭排序與關鍵字搜尋過濾，完美支援手機 RWD 瀏覽。
5. **CI/CD 原生零依賴發布**：純 Python 渲染 HTML，無需 Node.js / npm 建置步驟；使用 GitHub Actions 原生 `deploy-pages` 部署，不污染 Git 主分支歷史。
6. **Telegram 訊息聯動**：每日推播訊息末端附帶儀表板網址連結，方便使用者一鍵點擊檢視。

---

## 2. 系統架構與檔案劃分 (System Architecture)

```text
d:\MyProj\SuperTrend\
├── data\
│   ├── latest_signals_ai.json            # [NEW] 結構化儲存最新 AI 交易訊號與進出場價
│   └── optimized_params_ai.json          # [EXISTING] 最適參數與回測評分指標備份檔
├── src\
│   └── supertrend_ai\
│       ├── __init__.py
│       └── html_generator.py             # [NEW] 儀表板 HTML/CSS/JS 靜態生成核心
├── public\
│   └── index.html                        # [BUILD] 自動構建之自包含靜態儀表板（部署至 Pages）
├── tests\
│   └── test_html_generator.py            # [NEW] 網頁生成與資料完整性單元測試
├── run_batch_optimization_supertrend_ai.py # [MOD] 整合最新訊號匯出與網頁自動生成
└── .github\workflows\
    └── daily_supertrend_ai_signals.yml   # [MOD] 加入 GitHub Pages 部署步驟與權限
```

---

## 3. 詳細規格與資料結構 (Detailed Specifications)

### 3.1 訊號持久化格式：`data/latest_signals_ai.json`
格式為 JSON 陣列，儲存最新一筆標的計算狀態：
```json
[
  {
    "ticker": "0050.TW",
    "name": "元大台灣50",
    "market": "tw",
    "is_fund": false,
    "date": "2026-10-11",
    "close": 195.5,
    "currency": "NT$",
    "position": "long",
    "entry_ref": 188.2,
    "exit_ref": 190.0,
    "distance_pct": 2.89,
    "action": "HOLD_LONG",
    "updated_at": "2026-10-11 23:30:00"
  }
]
```

### 3.2 網頁生成引擎：`src/supertrend_ai/html_generator.py`
- **輸入**：
  - `signals`: 訊號字典清單（或自 `data/latest_signals_ai.json` 讀取）。
  - `params`: 最佳化參數清單（或自 `data/optimized_params_ai.json` 讀取）。
- **輸出**：`public/index.html`（自包含，所有 CSS 與 JS 內嵌，單檔即可運作）。
- **功能特性**：
  - **Tab 切換**：美股 (US) / 台股與基金 (TW)。
  - **表格 1 (Signals Table)**：代碼、名稱、資料日期、最新市價、目前部位、進場參考價、出場參考價、距標百分比。
  - **表格 2 (Optimized Params Table)**：代碼、名稱、ATR Length、Factor 範圍、Alpha、Cluster、Score、Win Rate、CAGR、Max Drawdown、Sharpe。
  - **客戶端互動**：
    - 點擊欄位標頭切換升序 / 降序。
    - 即時搜尋框（過濾 Ticker 或名稱）。
    - 狀態徽章顏色（Long 亮綠、Wait 沉灰、正報酬綠色、負報酬紅色）。
- **CLI 呼叫支援**：
  ```bash
  python -m src.supertrend_ai.html_generator --output public/index.html --open
  ```

### 3.3 CI/CD 工作流擴充：`.github/workflows/daily_supertrend_ai_signals.yml`
1. **GitHub Pages 權限設定**：
   ```yaml
   permissions:
     contents: write
     pages: write
     id-token: write
   ```
2. **部署步驟**：
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
3. **資料版控**：
   `git add data/optimized_params_ai.json data/latest_signals_ai.json`，一同自動 commit & push。

---

## 4. 邊界條件與驗證規劃 (Review Focus & Edge Cases)
1. **空資料防護**：若 `data/latest_signals_ai.json` 或 `data/optimized_params_ai.json` 為空或缺失，網頁能優雅顯示「暫無資料」提示，不發生 JavaScript 崩潰。
2. **基金淨值與小數位數對齊**：共同基金無標準 OHLC，且部分標的價格小數點位數較多，數值格式化需自適應（如貨幣符號 `$` vs `NT$`、百分比帶正負號）。
3. **XSS 安全防護**：標的名稱或字串渲染時一律經由安全轉義（HTML escaping），防止潛在腳本注入。
4. **手機瀏覽適配 (Responsive Table)**：在窄螢幕裝置上，表格自動啟用容器水平滑動並固定表頭視覺。
5. **部署重試與並發**：GitHub Pages 部署失敗不應阻斷整個批次腳本的成功退出狀態。
