# SuperTrend 交易績效追蹤與回測系統

本專案是一個專為美股 ETF 與個股（以日線為主）設計的**模組化交易績效追蹤與回測研究框架**。本系統採用本地 SQLite 資料庫作為市場價格與最適參數的快取與持久化層，能自動下載並管理歷史價格資料。系統除了計算 SuperTrend、HMA 等技術指標之外，還整合了手續費、滑價、跳空交易成交規則、固定風險部位控制、Walk-Forward (樣本外) 參數尋優、交易級 Monte Carlo 模擬以及多標的批次自動化運行等功能，為您提供專業的策略穩健性分析。

---

## 1. 系統特點

* **SQLite 本地快取與持久化 (`src/storage.py`, `src/data_loader.py`):**
  * **價格歷史 (`price_history`)**：自動下載並儲存 `yfinance` 的除權息調整價格資料，具備資料一致性校驗規則，避免異常 K 線（例如 High 小於 Close）干擾回測。
  - **最適參數與 JSON 版控 (`supertrend_params` & `data/optimized_params.json`)**：將優化計算出的最佳 SuperTrend / HMA 參數組合及 CAGR、Max Drawdown 等指標儲存至 SQLite，並自動雙向同步至輕量化 `data/optimized_params.json`。在 GitHub Actions 等 CI/CD 無狀態環境中，系統會自動從 JSON 恢復優化參數，避免重複優化運算。
  - **市場狀態與訊號 (`stock_signals`)**：即時儲存標的最新交易日的持倉狀態 (`1=long`, `0=cash`)、進場參考點 (`Entry Ref`)、出場參考點 (`Exit Ref`)、收盤價與 HMA 數值。
* **多標的自動化批次處理 (`run_batch_optimization.py`):**
  * 自動收集熱門股票 (Most Active) 與必備清單 (Must Have, 如 SPY, QQQM, SMH, GLD, VNQ)。
  * 使用多執行緒 (ThreadPoolExecutor) 並行執行多標的參數優化與回測。
  * 自動生成各標的 Markdown 回測報告 (`data/{yyyyMMdd}/{ticker}.md`) 以及全標的總覽報告 [`data/{yyyyMMdd}/All.md`](file:///d:/MyProj/SuperTrend/data/20260722/All.md)。
* **交易摩擦與跳空模型 (`src/backtest_engine.py`):**
  * 支援設定單邊手續費與滑價基點。在日內觸發止損時，若開盤直接跳空突破止損價，系統將以 `Open` 價成交，貼近實盤。
* **盯市淨值計算 (Mark-to-Market):**
  * 持倉期間採用每日盯市計價，而非僅在平倉時更新淨值，確保每日報酬波動的真實性，從而精算 Sharpe 與 Sortino 等指標。
* **進階風險指標與 Monte Carlo (`src/risk_manager.py`):**
  * 支援計算 **Ulcer Index (潰瘍指數)**、**Expectancy (交易期望值)**、最大連續盈虧等指標。並可隨機抽樣進行 5,000 次模擬，輸出 50% 至 99% 的最壞最大回撤風險報告。
* **Walk-Forward 樣本外優化 (`src/optimizer.py`):**
  * 支援設定 Train/Test 比例進行樣本外驗證，並可自定義綜合得分公式，產出參數熱力圖，協助您鎖定穩健參數的「高原區 (Plateau)」。

---

## 2. 安裝與設定說明

### 依賴環境
本系統使用 Python 3.8+（推薦 Python 3.12）進行開發。請確保您的本機已安裝 Python 環境。

### 安裝步驟
1. 下載或複製本專案資料夾。
2. 開啟終端機並切換至專案根目錄，執行以下命令安裝依賴套件：
   ```bash
   pip install -r requirements.txt
   ```
   *註：主要相依套件包含 `pandas`, `numpy`, `yfinance`, `plotly`, `pytest`。*

### 執行單元測試
您可以使用 `pytest` 驗證所有核心運算與資料庫模組是否完全正確：
```bash
python -m pytest tests/ -v
```

---

## 3. 命令行腳本使用說明 (CLI Tools)

### A. 單標的優化腳本 (`run_optimization.py`)
用於對單一股票或 ETF 執行完整網格優化、回測與 console 績效展示，並將結果存入資料庫：

```bash
python run_optimization.py --ticker SPY --start 2020-01-01
```

#### 引數清單 (Full Arguments)
| 引數名稱 | 類型 | 預設值 | 說明 |
| :--- | :--- | :--- | :--- |
| `--ticker` | `str` | `"SPY"` | 交易標的代碼 (例如 SPY, NVDA, AAPL)。 |
| `--start` | `str` | `"2020-01-01"` | 歷史資料起始日期 `YYYY-MM-DD`。 |
| `--end` | `str` | `Today` | 歷史資料結束日期 `YYYY-MM-DD`。 |
| `--interval` | `str` | `"1d"` | K 線週期，可選擇 `"1d"` (日線), `"1h"` / `"60m"` (小時線)。 |
| `--stop-loss` | `float` | `0.0` | 固定止損百分比 (例如 `0.08` 代表 8% 止損)。 |
| `--take-profit` | `float` | `0.0` | 固定止利百分比 (例如 `0.20` 代表 20% 止利)。 |
| `--commission` | `float` | `10.0` | 單邊交易手續費基點 (bps)，`10.0` 代表 10 bps (0.10%)。 |
| `--slippage` | `float` | `5.0` | 單邊交易滑價基點 (bps)，`5.0` 代表 5 bps (0.05%)。 |

---

### B. 多標的批次優化腳本 (`run_batch_optimization.py`)
自動爬取最活躍股票並結合必備清單，並列執行優化、產出 Markdown 報告並寫入資料庫：

```bash
python run_batch_optimization.py --start 2020-01-01 --workers 4
```

#### 引數清單 (Full Arguments)
| 引數名稱 | 類型 | 預設值 | 說明 |
| :--- | :--- | :--- | :--- |
| `--date` | `str` | `Today (yyyyMMdd)` | 輸出報告目錄的日期標籤 (例如 `20260722`)。 |
| `--start` | `str` | `"2020-01-01"` | 歷史資料起始日期 `YYYY-MM-DD`。 |
| `--end` | `str` | `Today` | 歷史資料結束日期 `YYYY-MM-DD`。 |
| `--interval` | `str` | `"1d"` | K 線週期，可選擇 `"1d"`, `"1h"`, `"60m"`。 |
| `--workers` | `int` | `4` | 並行處理的 Worker 執行緒數量。 |

---

## 4. Jupyter Notebook 互動操作說明

本系統提供 `SuperTrend_Backtester.ipynb` 做為使用者互動入口。請啟動 Jupyter Notebook：
```bash
python -m notebook SuperTrend_Backtester.ipynb
```
在瀏覽器中開啟後，您可以依序執行各個 Cells：
* **Cell 1 & 2:** 自動設定搜尋路徑、載入模組並下載歷史資料（預設為 `SPY`）。下載後資料會快取於本地 `data/market_data.db`。即使直接執行 Cell 2 亦具備安全匯入防護。
* **Cell 3 & 4:** 計算技術指標並執行回測，繪製**互動式 Plotly K 線圖**，圖上標示買入與賣出標記。
* **Cell 5 & 6:** 繪製策略與「買入持有 (Buy & Hold)」基準的淨值曲線與回撤軌跡對比圖，並輸出多維績效統計表。
* **Cell 7:** 執行 5,000 次 Monte Carlo 風險模擬，輸出 50%/75%/90%/95%/99% 最大回撤風險分位數。
* **Cell 8:** 進行樣本外優化與繪製參數高原熱力圖，協助挑選最穩健參數。

---

### C. 每日交易訊號掃描與 Telegram 通知 (`run_daily_scanner.py`)
用於每日自動掃描熱門美股與必備標的，判斷新舊標的參數優化狀態，更新最新訊號並透過 Telegram 發送診斷報告：

```bash
# 設定 Telegram 憑證（支援環境變數或執行目錄下的 .env 檔案）
# 方式 A：設定系統環境變數
export TELEGRAM_BOT_TOKEN="your_bot_token"
export TELEGRAM_CHAT_ID="your_chat_id"

# 方式 B：在專案根目錄建立 .env 檔案
# TELEGRAM_BOT_TOKEN=your_bot_token
# TELEGRAM_CHAT_ID=your_chat_id

# 執行每日掃描並發送 Telegram 報告
python run_daily_scanner.py

# 模擬執行 (Dry Run) 不發送訊息
python run_daily_scanner.py --dry-run --tickers TSLA NVDA

# 強制重新進行網格參數優化
python run_daily_scanner.py --force-reoptimize
```

#### 引數清單 (Full Arguments)
| 引數名稱 | 類型 | 預設值 | 說明 |
| :--- | :--- | :--- | :--- |
| `--date` | `str` | 當前日期 (`YYYY-MM-DD`) | 掃描目標日期。 |
| `--start` | `str` | `"2020-01-01"` | 歷史資料下載與優化起始日。 |
| `--force-reoptimize` | `flag` | `False` | 是否強制所有標的重新執行參數網格優化（預設每週六自動執行）。 |
| `--tickers` | `list` | `None` | 附加或指定的股票標的清單（例如 `--tickers TSLA NVDA`）。 |
| `--dry-run` | `flag` | `False` | 僅在 Console 印出診斷報告內容，不實際呼叫 Telegram API。 |
| `--db-path` | `str` | `"data/market_data.db"` | SQLite 資料庫檔案路徑。 |

### D. GitHub Actions 自動化雲端部署 (`.github/workflows/daily_signals.yml`)
本專案已內建完整的 GitHub Actions 自動化工作流。每逢平日美股收盤自動計算訊號並推播至 Telegram；每逢週六自動觸發全標的參數網格重新優化，並將更新後的最適參數檔案 (`data/optimized_params.json`) 自動 Push 存回 Git 倉庫。

---

## 5. 預期輸出檔案與資料庫架構 (Expected Outputs)

### A. Markdown 報告檔案
- **個股報告 (`data/{yyyyMMdd}/{ticker}.md`)**：包含樣本內/外 Top 5 參數、最佳參數、最新市場狀態與交易訊號、完整交易紀錄與 Monte Carlo 評估。
- **全標的總覽報告 (`data/{yyyyMMdd}/All.md`)**：整合所有標的最新收盤價、HMA、SuperTrend、最適參數、當前持倉 (`long` / `cash`) 與進出場參考點 (`Entry Ref` / `Exit Ref`)，`long` 持倉自動排序於最上方。

### B. SQLite 資料庫與 JSON 版控
- `data/market_data.db` (本地快取資料庫):
  - `price_history`: 儲存歷史 OHLCV K 線價格資料 (主鍵: `ticker, interval, datetime`)。
  - `supertrend_params`: 儲存各標的最適參數與績效指標 (主鍵: `ticker, start_date, end_date`)。
  - `stock_signals`: 儲存最新交易日持倉狀態 (1=long, 0=cash)、進出場參考點與 HMA 數值 (主鍵: `ticker, start_date, end_date`)。
- `data/optimized_params.json`: 輕量化 JSON 格式之最適參數備份檔案，負責跨環境（如 GitHub Actions CI/CD）與 Git 版本控制之參數同步。

---

## 6. 回測引擎引數說明 (`BacktestEngine.run`)

| 引數名稱 | 類型 | 預設值 | 說明 |
| :--- | :--- | :--- | :--- |
| `long_only` | `bool` | `True` | 是否僅執行多頭交易（美股 ETF 一般設為 True）。 |
| `stop_loss_pct` | `float` | `0.0` | 止損百分比。例如 `0.08` 代表進場價跌落 8% 即出場。 |
| `take_profit_pct` | `float` | `0.0` | 止利百分比。例如 `0.20` 代表進場價上漲 20% 即出場。 |
| `commission_bps` | `float` | `0.0` | 單邊交易手續費（基點）。`10.0` 代表 10 bps (0.10%)。 |
| `slippage_bps` | `float` | `0.0` | 單邊交易滑價（基點）。`5.0` 代表 5 bps (0.05%)。 |
| `position_sizing_mode`| `str` | `"fixed_fraction"`| 部位配置模式。`"fixed_fraction"` 屬滿倉；`"fixed_risk"` 屬固定風險部位控制。 |
| `risk_pct` | `float` | `0.01` | 單筆交易承受風險比（當 sizing 模式為 `"fixed_risk"` 且設定止損時有效）。 |

---

## 7. 限制與假設說明

1. **資料範圍限制與自動截斷：**
   使用 `yfinance` 獲取美股歷史資料時，1 小時 (1-Hour / 60m) 頻率的歷史資料最長僅支援下載最近 730 日，而日線 (Daily) 資料則無限制。當請求 1 小時頻率且指定日期區間超過 730 日時，`DataLoader` 會自動將起始日期限制在 730 日內，無需拋出錯誤亦不需使用者手動調整。
2. **時區 naive 設定：**
   為避免 Pandas 對齊時出現時區錯誤，資料載入時統一將時區轉換為 naive (不含時區)，以 UTC 時間軸進行對齊與比對。
3. **無融資與融券利息計算：**
   回測引擎之空頭 (Short) 回測未扣除融券借券利息與借券成本，若執行空頭回測，其實盤效果可能會低於回測值。
