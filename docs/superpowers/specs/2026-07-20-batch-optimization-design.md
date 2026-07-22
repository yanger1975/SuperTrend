# Batch Optimization Runner — 設計規格

**日期**: 2026-07-20
**狀態**: 待審查
**關聯檔案**: `spec/20260720.txt`

---

## 1. 概述

建立一個批次優化腳本 `run_batch_optimization.py`，自動收集交易標的清單（Most Active + Must Have），對每個標的跑參數優化與回測，並將完整結果輸出為 Markdown 報告。

---

## 2. 架構

```
run_batch_optimization.py  (新建)
  ├── TrendingScraper (from spec/trending_scraper.py)
  ├── DataLoader       (from src/data_loader.py)
  ├── compute_supertrend, compute_hma (from src/indicators.py)
  ├── BacktestEngine   (from src/backtest_engine.py)
  ├── RiskManager      (from src/risk_manager.py)
  └── ParameterOptimizer (from src/optimizer.py)
```

不修改現有 `src/` 模組與 `run_optimization.py`。

### 2.1 並行處理

Step 3 使用 `concurrent.futures.ThreadPoolExecutor` 對多個 ticker 並行優化。每個 ticker 的優化/回測是 CPU-bound 且彼此獨立，ThreadPool 適合 I/O（yfinance 下載）與 CPU（pandas/numpy 計算）混合場景。並行數可透過 `--workers` 參數控制（預設 4）。

---

## 3. 執行流程

```
Step 1: 爬取 Most Active → 存成 data/most-active.json (含 fallback 機制)
Step 2: 讀取 most-active.json + must_have.json → 去重合併 → 最終 ticker 清單
Step 3: 取得完整 ticker 清單後，使用 asyncio (或 concurrent.futures) 並行處理每個 ticker：
  3a. 下載/載入歷史價格資料
  3b. 跑參數優化搜尋（含進度顯示）
  3c. 用最佳參數跑完整回測
  3d. 產出 data/{yyyyMMdd}/{ticker}.md
Step 4: 輸出摘要（共處理幾個 ticker、成功/失敗數量）
```

---

## 4. CLI 介面

```
python run_batch_optimization.py [--date 20260720] [--start 2020-01-01] [--end 2026-07-20] [--interval 1d] [--workers 4]
```

| 參數 | 預設值 | 說明 |
|------|--------|------|
| `--date` | 今天日期 | 輸出目錄的日期鍵 (`data/{date}/`) |
| `--start` | 2020-01-01 | 歷史資料起始日 |
| `--end` | 今天日期 | 歷史資料結束日 |
| `--interval` | 1d | K 線週期 (1d / 1h) |
| `--workers` | 4 | 並行處理的 worker 數量 |

所有 ticker 共用同一組 `--start`、`--end`、`--interval`。優化參數 grid 沿用 `run_optimization.py` 的設定：
- `ST_PERIODS = [5, 10, 15, 20, 25, 30]`
- `ST_MULTIPLIERS = [2.5, 3.0, 3.5, 4.0, 4.5, 5.0]`
- `MA_PERIODS = [0, 25, 50, 75, 100, 125]`
- `TRAIN_RATIO = 0.70`

---

## 5. Ticker 收集邏輯

- 使用 `TrendingScraper.fetch_top_tickers(limit=10)` 爬取 Most Active
- 成功時自動寫入 `data/most-active.json`（作為下次爬取失敗的備援）
- 爬取失敗時讀取 `data/most-active.json` 作為 fallback
- 在記憶體中與 `data/must_have.json` 合併、去重，不產生合併檔案
- Must-have ticker 永遠在清單中（即使爬蟲沒抓到）

---

## 6. Markdown 輸出格式

每個 ticker 產出 `data/{yyyyMMdd}/{ticker}.md`，內容對應 `run_optimization.py` 的全部 console 輸出：

### 6.1 報告結構

```markdown
# {TICKER} 優化回測報告

**執行日期**: 2026-07-20
**資料區間**: 2020-01-01 ~ 2026-07-20
**Train/Test 分割**: 70%

## 參數優化結果 - 樣本內 Top 5
| ST_Period | ST_Multiplier | MA_Period | Use_HMA | Custom Score | CAGR | Max Drawdown | Sharpe | Calmar | Win Rate | Profit Factor |
|-----------|---------------|-----------|---------|-------------|------|-------------|--------|--------|---------|---------------|

## 參數優化結果 - 樣本外 Top 5
（同上表格）

## 最佳參數
- SuperTrend: (period, multiplier)
- HMA Filter: 啟用(週期=N) / 未啟用

## 完整交易紀錄
| 序號 | 方向 | 進場日期 | 進場價 | 出場日期 | 出場價 | 損益(%) | 離場原因 |
|------|------|---------|--------|---------|--------|--------|---------|

## 績效與風險指標
| 指標 | 數值 |
|------|------|
| CAGR | xx% |
| Max Drawdown | xx% |
| Sharpe Ratio | x.xx |
| ... | ... |

## Monte Carlo 模擬 (5000次)
| 分位數 | 最大回撤 |
|--------|---------|
| ... | ... |
```

### 6.2 欄位說明

與 `run_optimization.py` 的 `DISPLAY_COLS` 一致：
- ST_Period, ST_Multiplier, MA_Period, Use_HMA_Filter
- Custom Score, CAGR, Max Drawdown, Sharpe Ratio, Calmar Ratio, Win Rate, Profit Factor

---

## 7. 錯誤處理

- 單一 ticker 下載失敗或優化失敗 → 記錄錯誤訊息，繼續處理下一個 ticker
- 所有 ticker 處理完後，在 console 輸出摘要（成功 N 個 / 失敗 M 個 / 總共 T 個）
- 爬蟲完全失敗 → 使用 `most-active.json` fallback，若該檔案也不存在則使用 `TrendingScraper` 的內建預設清單

---

## 8. 不納入範圍

- 不修改現有 `run_optimization.py`
- 不修改 `src/` 下的任何模組
- 不產生合併後的 ticker JSON 檔案
- 不支援多 instrument 同時回測（維持單一 ticker 回測）
