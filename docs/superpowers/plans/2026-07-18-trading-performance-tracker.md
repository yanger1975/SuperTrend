# 交易績效追蹤系統 實現計劃

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推薦）或 superpowers:executing-plans 逐任務實現此計劃。步驟使用複選框（`- [ ]`）語法來跟蹤進度。

**目標：** 構建一個模組化的 Python 交易績效追蹤與回測系統，支援 SQLite 本地快取、Single/Multi-Timeframe 的 SuperTrend 策略回測、手續費與滑價計算、部位控管、樣本外優化、Monte Carlo 風險模擬，並在 Jupyter Notebook 中呈現互動圖表。

**架構：** 採用 Modular Package 結構，核心計算（儲存、載入、指標、回測、風險、優化）寫入 `src/`，各模組撰寫對應的 pytest 單元測試以確保正確性。前端使用 Jupyter Notebook 作為互動介面進行策略分析與圖表繪製。

**技術棧：** Python, pandas, numpy, yfinance, sqlite3, plotly, pytest

---

## 文件結構與職責鎖定
* `requirements.txt`: 外部套件依賴。
* `src/storage.py`: 本地 SQLite 資料庫價格歷史持久化儲存層。 [NEW]
* `src/data_loader.py`: 資料下載與快取協調器。優先檢索 SQLite 庫，缺失時進行下載與清洗驗證。
* `src/indicators.py`: 指標計算核心（SuperTrend, HMA, EMA, SMA, ADX, RSI）。
* `src/backtest_engine.py`: 逐根 K 線交易回測引擎（含滑價手續費、跳空開盤、部位控制）。
* `src/risk_manager.py`: 績效指標計算（CAGR, Max DD, UI, Sharpe, Sortino, PF, Calmar, Expectancy）與 Monte Carlo 模擬。
* `src/optimizer.py`: 網格搜尋與 Walk-Forward 參數優化器。
* `SuperTrend_Backtester.ipynb`: 互動式前端分析與 Plotly 互動式圖表展示。
* `README.md`: 使用說明（正體中文）。
* `TechStack.html`: 技術架構說明（正體中文，無簡體字）。

---

### 任務 1：環境設定與依賴安裝

**檔案：**
* 建立：`requirements.txt`

- [ ] **步驟 1：編寫 requirements.txt**
  在專案根目錄建立 `requirements.txt`，寫入以下依賴套件：
  ```text
  pandas>=2.0.0
  numpy>=1.24.0
  yfinance>=0.2.20
  plotly>=5.15.0
  pytest>=7.3.0
  ```
- [ ] **步驟 2：執行安裝指令**
  執行安裝：`pip install -r requirements.txt`
- [ ] **步驟 3：Commit**
  ```bash
  git add requirements.txt
  git commit -m "chore: add dependencies in requirements.txt"
  ```

---

### 任務 2：SQLite 本地儲存層模組

**檔案：**
* 建立：`src/storage.py`
* 建立：`tests/test_storage.py`

- [ ] **步驟 1：編寫測試 `tests/test_storage.py`**
  驗證資料庫表格初始化與 upsert（新增或覆蓋）邏輯。
  ```python
  import os
  import pandas as pd
  import pytest
  from src.storage import SQLiteStorage

  def test_sqlite_storage():
      db_path = "test_market_data.db"
      if os.path.exists(db_path):
          os.remove(db_path)
          
      storage = SQLiteStorage(db_path)
      # 構建模擬資料
      idx = pd.to_datetime(["2023-01-01 09:30:00", "2023-01-02 09:30:00"])
      df = pd.DataFrame({
          "Open": [100.0, 101.0],
          "High": [102.0, 103.0],
          "Low": [99.0, 100.0],
          "Close": [101.0, 102.0],
          "Volume": [1000, 1100]
      }, index=idx)
      
      # 寫入測試
      storage.upsert_prices(df, "SPY", "1d")
      
      # 查詢測試
      df_queried = storage.query_prices("SPY", "1d", "2023-01-01", "2023-01-02")
      assert not df_queried.empty
      assert len(df_queried) == 2
      assert df_queried["Close"].iloc[0] == 101.0
      
      # 重複寫入 (Upsert 衝突) 測試
      df_update = pd.DataFrame({
          "Open": [100.0, 101.0],
          "High": [102.0, 103.0],
          "Low": [99.0, 100.0],
          "Close": [105.0, 102.0], # 更新第一筆的 Close
          "Volume": [1000, 1100]
      }, index=idx)
      storage.upsert_prices(df_update, "SPY", "1d")
      df_queried_2 = storage.query_prices("SPY", "1d", "2023-01-01", "2023-01-02")
      assert df_queried_2["Close"].iloc[0] == 105.0
      
      if os.path.exists(db_path):
          os.remove(db_path)
  ```
- [ ] **步驟 2：運行測試驗證失敗**
  運行：`pytest tests/test_storage.py -v`
  預期：FAIL (ImportError)
- [ ] **步驟 3：編寫最少實現代碼 `src/storage.py`**
  ```python
  import sqlite3
  import pandas as pd
  import os

  class SQLiteStorage:
      def __init__(self, db_path: str = "data/market_data.db"):
          self.db_path = db_path
          db_dir = os.path.dirname(db_path)
          if db_dir and not os.path.exists(db_dir):
              os.makedirs(db_dir)
          self._init_db()

      def _init_db(self):
          with sqlite3.connect(self.db_path) as conn:
              cursor = conn.cursor()
              cursor.execute("""
                  CREATE TABLE IF NOT EXISTS price_history (
                      ticker TEXT NOT NULL,
                      interval TEXT NOT NULL,
                      datetime TEXT NOT NULL,
                      open REAL NOT NULL,
                      high REAL NOT NULL,
                      low REAL NOT NULL,
                      close REAL NOT NULL,
                      volume REAL,
                      source TEXT DEFAULT 'yfinance',
                      adjusted INTEGER DEFAULT 1,
                      created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                      updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                      PRIMARY KEY (ticker, interval, datetime)
                  )
              """)
              conn.commit()

      def upsert_prices(self, df: pd.DataFrame, ticker: str, interval: str):
          with sqlite3.connect(self.db_path) as conn:
              cursor = conn.cursor()
              for dt, row in df.iterrows():
                  dt_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                  cursor.execute("""
                      INSERT INTO price_history (ticker, interval, datetime, open, high, low, close, volume)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                      ON CONFLICT(ticker, interval, datetime) DO UPDATE SET
                          open=excluded.open,
                          high=excluded.high,
                          low=excluded.low,
                          close=excluded.close,
                          volume=excluded.volume,
                          updated_at=CURRENT_TIMESTAMP
                  """, (ticker, interval, dt_str, float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"]), float(row["Volume"])))
              conn.commit()

      def query_prices(self, ticker: str, interval: str, start_date: str, end_date: str) -> pd.DataFrame:
          # 將日期字串格式化為資料庫比對的格式
          start_ts = pd.to_datetime(start_date).strftime("%Y-%m-%d %H:%M:%S")
          end_ts = pd.to_datetime(end_date).strftime("%Y-%m-%d %H:%M:%S")
          
          with sqlite3.connect(self.db_path) as conn:
              query = """
                  SELECT datetime, open, high, low, close, volume
                  FROM price_history
                  WHERE ticker=? AND interval=? AND datetime BETWEEN ? AND ?
                  ORDER BY datetime ASC
              """
              df = pd.read_sql_query(query, conn, params=(ticker, interval, start_ts, end_ts))
              if df.empty:
                  return pd.DataFrame()
              
              df["datetime"] = pd.to_datetime(df["datetime"])
              df.set_index("datetime", inplace=True)
              # 將欄位名稱首字母大寫以對齊 yfinance 格式
              df.columns = ["Open", "High", "Low", "Close", "Volume"]
              return df
  ```
- [ ] **步驟 4：運行測試驗證通過**
  運行：`pytest tests/test_storage.py -v`
  預期：PASS
- [ ] **步驟 5：Commit**
  ```bash
  git add src/storage.py tests/test_storage.py
  git commit -m "feat: implement SQLiteStorage module with upsert capability"
  ```

---

### 任務 3：Data Loader 與資料清洗驗證

**檔案：**
* 建立：`src/data_loader.py`
* 建立：`tests/test_data_loader.py`

- [ ] **步驟 1：編寫測試 `tests/test_data_loader.py`**
  ```python
  import os
  import pandas as pd
  import pytest
  from src.data_loader import DataLoader

  def test_data_loader_flow():
      db_path = "test_loader_market_data.db"
      if os.path.exists(db_path):
          os.remove(db_path)
          
      loader = DataLoader(db_path=db_path)
      # 第一次獲取：應下載並快取
      df = loader.fetch_data("SPY", start_date="2023-01-01", end_date="2023-01-10", interval="1d")
      assert not df.empty
      assert "Close" in df.columns
      
      # 驗證資料品質清洗規則 (High >= max(Open, Close))
      assert (df["High"] >= df[["Open", "Close"]].max(axis=1)).all()
      assert (df["Low"] <= df[["Open", "Close"]].min(axis=1)).all()
      
      # 第二次獲取：應從本地 SQLite 查出
      df_cached = loader.fetch_data("SPY", start_date="2023-01-01", end_date="2023-01-10", interval="1d")
      assert len(df_cached) == len(df)
      
      if os.path.exists(db_path):
          os.remove(db_path)
  ```
- [ ] **步驟 2：運行測試驗證失敗**
  運行：`pytest tests/test_data_loader.py -v`
  預期：FAIL
- [ ] **步驟 3：編寫最少實現代碼 `src/data_loader.py`**
  ```python
  import pandas as pd
  import numpy as np
  import yfinance as yf
  from src.storage import SQLiteStorage

  class DataLoader:
      def __init__(self, db_path: str = "data/market_data.db"):
          self.storage = SQLiteStorage(db_path)

      def validate_and_clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
          # 1. 去除空價格
          df = df.dropna(subset=["Close"]).copy()
          if df.empty:
              return df
              
          # 2. 移除重複索引，保留第一筆
          df = df[~df.index.duplicated(keep="first")]
          
          # 3. 欄位類型轉換與排序
          df.index = pd.to_datetime(df.index)
          df = df.sort_index()
          
          # 4. 防錯價格校驗 (High >= max(Open, Close), Low <= min(Open, Close))
          max_op_cl = df[["Open", "Close"]].max(axis=1)
          min_op_cl = df[["Open", "Close"]].min(axis=1)
          
          df["High"] = np.maximum(df["High"], max_op_cl)
          df["Low"] = np.minimum(df["Low"], min_op_cl)
          return df

      def fetch_data(self, ticker: str, start_date: str, end_date: str, interval: str = "1d", refresh: bool = False) -> pd.DataFrame:
          if not refresh:
              # 優先查詢本地資料庫
              local_df = self.storage.query_prices(ticker, interval, start_date, end_date)
              # 計算預期天數差，判斷本地資料是否足夠完整 (簡單判定是否有資料)
              if not local_df.empty:
                  # 若本地已有資料則返回本地資料
                  return local_df
                  
          # 下載並自動除權息調整
          data = yf.download(ticker, start=start_date, end=end_date, interval=interval, auto_adjust=True)
          if data.empty:
              raise ValueError(f"No data downloaded from yfinance for {ticker}")
              
          if isinstance(data.columns, pd.MultiIndex):
              data.columns = data.columns.get_level_values(0)
              
          # 清洗與校驗
          cleaned_df = self.validate_and_clean_data(data)
          
          # 存入資料庫
          self.storage.upsert_prices(cleaned_df, ticker, interval)
          return cleaned_df
  ```
- [ ] **步驟 4：運行測試驗證通過**
  運行：`pytest tests/test_data_loader.py -v`
  預期：PASS
- [ ] **步驟 5：Commit**
  ```bash
  git add src/data_loader.py tests/test_data_loader.py
  git commit -m "feat: implement DataLoader with SQLite integration and cleaning rules"
  ```

---

### 任務 4：技術指標模組

**檔案：**
* 修改：`src/indicators.py`
* 修改：`tests/test_indicators.py`

- [ ] **步驟 1：編寫測試 `tests/test_indicators.py`**
  驗證 HMA、RSI 與 SuperTrend 計算正確性。
  ```python
  import pandas as pd
  import numpy as np
  from src.indicators import compute_hma, compute_rsi, compute_supertrend

  def test_indicators_math():
      prices = pd.Series([10, 11, 12, 11, 10, 9, 10, 11, 12, 13, 14])
      hma_val = compute_hma(prices, period=5)
      assert len(hma_val) == len(prices)
      
      df = pd.DataFrame({
          "High": [10, 11, 12, 11, 12],
          "Low": [9, 10, 11, 10, 11],
          "Close": [9.5, 10.5, 11.5, 10.5, 11.5]
      })
      st, trend = compute_supertrend(df, period=3, multiplier=2.0)
      assert "SuperTrend" in st.columns
      assert "Trend" in st.columns
  ```
- [ ] **步驟 2：執行 `pytest tests/test_indicators.py` 驗證計算邏輯**
- [ ] **步驟 3：編寫 `src/indicators.py` 計算代碼**
  實作 `compute_hma`, `compute_rsi`, `compute_adx`, `compute_supertrend` 指標計算。
- [ ] **步驟 4：確認測試全部通過**
- [ ] **步驟 5：Commit**
  ```bash
  git add src/indicators.py tests/test_indicators.py
  git commit -m "feat: verify all technical indicator calculations"
  ```

---

### 任務 5：回測引擎模組（含交易成本與跳空處理）

**檔案：**
* 修改：`src/backtest_engine.py`
* 修改：`tests/test_backtester.py`

- [ ] **步驟 1：編寫測試 `tests/test_backtester.py`**
  特別測試開盤 Gap 直接跌破止損時，是否以 `Open` 成交，以及 SL/TP 同時觸發時 Daily 週期下判定 SL 優先的邏輯。
  ```python
  import pandas as pd
  from src.backtest_engine import BacktestEngine

  def test_backtest_gap_and_priority():
      idx = pd.to_datetime(["2023-01-01", "2023-01-02", "2023-01-03"])
      df = pd.DataFrame({
          "Open": [100.0, 102.0, 80.0],  # 第三天跳空大跌
          "High": [105.0, 104.0, 85.0],
          "Low": [95.0, 99.0, 75.0],
          "Close": [101.0, 102.0, 81.0],
          "SuperTrend": [98.0, 98.0, 98.0],
          "Trend": [1, 1, 1],
          "MA_Filter": [True] * 3,
          "ADX_Filter": [True] * 3,
          "RSI_Filter": [True] * 3
      }, index=idx)
      
      # 測試 Gap 止損成交 (Stop Loss 10% 即 90.0, 第三天開盤為 80.0)
      engine = BacktestEngine(df)
      trades, strat_eq, bench_eq = engine.run(long_only=True, stop_loss_pct=0.10)
      assert len(trades) == 1
      # 應以第三天開盤價 80.0 成交，而非以 90.0 成交
      assert trades[0].exit_price == 80.0
      assert trades[0].exit_reason == "StopLoss"
  ```
- [ ] **步驟 2：執行並確認測試失敗**
- [ ] **步驟 3：實作 `src/backtest_engine.py` 的迭代回測迴圈**
  精確處理手續費扣除、日內 SL/TP 觸發、開盤 Gap 跳空交易與 fixed risk 的部位計算。
- [ ] **步驟 4：執行測試並驗證通過**
- [ ] **步驟 5：Commit**
  ```bash
  git add src/backtest_engine.py tests/test_backtester.py
  git commit -m "feat: complete backtest engine gap handling and costs"
  ```

---

### 任務 6：風險分析與進階統計指標

**檔案：**
* 修改：`src/risk_manager.py`
* 修改：`tests/test_risk.py`

- [ ] **步驟 1：修改測試 `tests/test_risk.py`**
  確保 Ulcer Index, Expectancy 以及設定 seed 時 Monte Carlo 的穩定產出。
- [ ] **步驟 2：實現 `src/risk_manager.py` 的指標算法**
  計算 CAGR, Max DD, Ulcer Index, Sharpe, Sortino, Expectancy 以及 Monte Carlo 的分位數百分比。
- [ ] **步驟 3：運行單元測試確認通過**
- [ ] **步驟 4：Commit**
  ```bash
  git add src/risk_manager.py tests/test_risk.py
  git commit -m "feat: add advanced risk metrics and reproducible Monte Carlo"
  ```

---

### 任務 7：優化器與 Walk-Forward 驗證

**檔案：**
* 修改：`src/optimizer.py`

- [ ] **步驟 1：實作網格搜尋與 Train/Test Split**
  讓使用者傳入 `train_ratio` (如 0.70)，輸出兩份排行 DataFrame（樣本內優化與樣本外適應）。
- [ ] **步驟 2：在 `tests/test_optimizer.py` 中進行驗證**
  確保優化器執行無誤。
- [ ] **步驟 3：Commit**
  ```bash
  git add src/optimizer.py
  git commit -m "feat: implement Walk-Forward train-test optimizer and scoring"
  ```

---

### 任務 8：Jupyter Notebook 整合與互動圖表

**檔案：**
* 建立：`SuperTrend_Backtester.ipynb`

- [ ] **步驟 1：在 Jupyter Notebook 中載入模組，繪製高質感 Plotly 圖表**
  包含 K 線交易標記、Bench Curve 對比、Drawdown Path、月度/年度 Heatmap、以及 Monte Carlo 分位數與熱力圖高原。
- [ ] **步驟 2：執行所有 Cells 確認流程運作正常，無任何 errors**
- [ ] **步驟 3：Commit**
  ```bash
  git add SuperTrend_Backtester.ipynb
  git commit -m "feat: create interactive jupyter notebook dashboard"
  ```

---

### 任務 9：說明文件編寫 (正體中文)

**檔案：**
* 建立：`README.md`
* 建立：`TechStack.html`

- [ ] **步驟 1：建立說明手冊 `README.md`**
  正體中文說明如何執行 Notebook、說明手續費參數、Monte Carlo 與 Walk-Forward OOS 解讀。
- [ ] **步驟 2：建立 `TechStack.html` 技術規格文件**
  以高質感的純 HTML/CSS 呈現架構圖、SQLite 持久化機制與多維風險指標定義，確保全文件皆為正體中文（無簡體字）。
- [ ] **步驟 3：Commit**
  ```bash
  git add README.md TechStack.html
  git commit -m "docs: write README and TechStack docs in Traditional Chinese"
  ```
