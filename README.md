# SuperTrend 交易績效追蹤與回測系統

本專案是一個專為美股 ETF（以日線為主）設計的**模組化交易績效追蹤與回測研究框架**。本系統採用本地 SQLite 資料庫作為市場價格快取層，能自動下載並管理價格資料。系統除了計算 SuperTrend、HMA 等技術指標之外，還整合了手續費、滑價、跳空交易成交規則、固定風險部位控制、Walk-Forward (樣本外) 參數尋優與交易級 Monte Carlo 模擬等功能，為您提供專業的策略穩健性分析。

---

## 1. 系統特點

* **SQLite 本地快取與清洗 (`src/storage.py`, `src/data_loader.py`):**
  自動下載並儲存 `yfinance` 的除權息調整價格資料。具備資料一致性校驗規則，避免異常 K 線（例如 High 小於 Close）干擾回測。
* **交易摩擦與跳空模型 (`src/backtest_engine.py`):**
  支援設定單邊手續費與滑價基點。在日內觸發止損時，若開盤直接跳空突破止損價，系統將以 `Open` 價成交，貼近實盤。
* **盯市淨值計算 (Mark-to-Market):**
  持倉期間採用每日盯市計價，而非僅在平倉時更新淨值，確保每日報酬波動的真實性，從而精算 Sharpe 與 Sortino 等指標。
* **進階風險指標與 Monte Carlo (`src/risk_manager.py`):**
  支援計算 **Ulcer Index (潰瘍指數)**、**Expectancy (交易期望值)**、最大連續盈虧等指標。並可隨機抽樣進行 5,000 次模擬，輸出 50% 至 99% 的最壞最大回撤風險報告。
* **Walk-Forward 樣本外優化 (`src/optimizer.py`):**
  支援設定 Train/Test 比例進行樣本外驗證，並可自定義綜合得分公式，產出參數熱力圖，協助您鎖定穩健參數的「高原區 (Plateau)」。

---

## 2. 安裝與設定說明

### 依賴環境
本系統使用 Python 3.8+ 進行開發。請確保您的本機已安裝 Python 環境。

### 安裝步驟
1. 下載或複製本專案資料夾。
2. 開啟終端機並切換至專案根目錄，執行以下命令安裝依賴套件：
   ```bash
   pip install -r requirements.txt
   ```
   *註：主要相依套件包含 `pandas`, `numpy`, `yfinance`, `plotly`, `pytest`。*

### 執行單元測試
您可以使用 `pytest` 驗證所有核心運算模組是否完全正確：
```bash
python -m pytest tests/ -v
```

---

## 3. Jupyter Notebook 互動操作說明

本系統提供 `SuperTrend_Backtester.ipynb` 做為使用者互動入口。請啟動 Jupyter Notebook：
```bash
python -m notebook SuperTrend_Backtester.ipynb
```
在瀏覽器中開啟後，您可以依序執行各個 Cells：
* **Cell 1 & 2:** 載入模組並下載美股 ETF 資料（預設為 `SPY`）。下載後資料會快取於本地的 `data/market_data.db`。
* **Cell 3 & 4:** 計算技術指標（SuperTrend, 200 日 HMA, ADX, RSI）並執行回測，最後繪製**互動式 Plotly K 線圖**，圖上精確標示買入（進場）與賣出（出場）標記。
* **Cell 5 & 6:** 繪製策略與「買入持有 (Buy & Hold)」基準的淨值曲線與回撤軌跡對比圖，並輸出多維績效統計表（含年化交易次數、平均持倉天數、潰瘍指數等）。
* **Cell 7:** 執行 5,000 次 Monte Carlo 風險模擬，輸出 50%/75%/90%/95%/99% 最大回撤風險分位數，並繪製回撤發生機率分佈圖。
* **Cell 8:** 進行樣本外優化與繪製參數高原熱力圖，幫助您挑選最穩健的引數。

---

## 4. 回測引擎引數說明

在執行 `BacktestEngine.run()` 時，可設定以下引數：

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

## 5. 限制與假設說明

1. **資料範圍限制與自動截斷：**
   使用 `yfinance` 獲取美股歷史資料時，1 小時 (1-Hour / 60m) 頻率的歷史資料最長僅支援下載最近 730 日，而日線 (Daily) 資料則無限制。當請求 1 小時頻率且指定日期區間超過 730 日時，`DataLoader` 會自動將起始日期限制在 730 日內，無需拋出錯誤亦不需使用者手動調整。

2. **時區 naive 設定：**
   為避免 Pandas 對齊時出現時區錯誤，資料載入時統一將時區轉換為 naive (不含時區)，以 UTC 時間軸進行對齊與比對。
3. **無融資與融券利息計算：**
   回測引擎之空頭 (Short) 回測未扣除融券借券利息與借券成本，若執行空頭回測，其實盤效果可能會低於回測值。
