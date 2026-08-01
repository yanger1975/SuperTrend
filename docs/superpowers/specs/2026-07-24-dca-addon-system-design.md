# ETF 定期定額 + 低檔加碼策略（左側交易）系統設計規格書

## 1. 系統概述與目標 (Overview & Goal)

本系統旨在構建一套專為 **左側交易（定期定額 + 低檔條件加碼）** 設計的回測、參數最佳化與視覺化報告平台。
系統與現有的 `SuperTrend` 順勢交易系統相互獨立，但共享數據儲存層 (`src/storage.py`) 的 SQLite 歷史行情數據。

系統提供兩種使用模式：
1. **互動研究模式 (Notebook Workflow)**：透過 `notebooks/DCA_AddOn_Strategy_Research.ipynb` 進行快速實驗、繪製互動式 Plotly 圖表與參數敏銳度熱力圖。
2. **自動化 CLI 腳本模式**：透過 `run_dca_backtest.py` 與 `run_dca_optimizer.py` 進行單次回測或大批量參數掃描。

---

## 2. 系統架構與模組劃分 (System Architecture)

專案結構如下：

```
SuperTrend/
├── src/
│   ├── dca_addon/                 # [NEW] 左側加碼系統核心模組
│   │   ├── __init__.py
│   │   ├── config.py              # 策略配置與加碼規則 Dataclass
│   │   ├── engine.py              # 回測引擎核心 (DCAAddOnBacktester)
│   │   ├── metrics.py             # 績效、風險與自訂左側指標計算器
│   │   ├── optimizer.py           # 網格搜尋與 Walk-Forward Analysis 最佳化器
│   │   └── visualizer.py          # Plotly 互動圖表與 HTML 報告生成器
│   └── storage.py                 # [EXISTING] SQLite 數據庫載入器
├── notebooks/                     # [NEW] 研究與視覺化實驗區
│   └── DCA_AddOn_Strategy_Research.ipynb
├── run_dca_backtest.py            # [NEW] 單次回測 CLI 執行入口
├── run_dca_optimizer.py           # [NEW] 參數掃描 CLI 執行入口
├── tests/                         # [NEW/EXISTING] 單元測試
│   └── test_dca_addon.py          # 左側加碼系統單元測試
└── docs/superpowers/specs/
    └── 2026-07-24-dca-addon-system-design.md # 本設計規格書
```

---

## 3. 詳細模組設計 (Detailed Module Specifications)

### 3.1 `src/dca_addon/config.py`
定義策略規則與設定資料類別：

- `AddOnRule`
  - `lookback_days`: `int` (回測比較天數，如 10, 20, 60 日)
  - `drawdown_threshold`: `float` (跌幅門檻，如 0.05 代表跌 5%)
  - `multiplier`: `float` (加碼倍數，相較於基礎定期定額金額之倍數，如 2.0)
  - `reference_type`: `str` (跌幅基準，預設 `'shift'` 代表相較 N 日前收盤價；可選 `'high'` 代表過去 N 日最高價)

- `StrategyConfig`
  - `base_invest_amount`: `float` (每期基礎定期定額金額)
  - `invest_frequency`: `str` (預設 `'M'` 代表每月扣款)
  - `rules`: `List[AddOnRule]` (多階梯加碼規則列表)
  - `max_addons_per_month`: `Optional[int]` (每月加碼次數上限)
  - `cooldown_days`: `int` (觸發加碼後冷卻天數)
  - `total_extra_budget`: `Optional[float]` (總加碼額外預算上限)
  - `max_total_invest`: `Optional[float]` (總投入資金上限)
  - `cash_risk_free_rate`: `float` (閒置加碼預算無風險年利率，預設 0.0)

### 3.2 `src/dca_addon/engine.py`
實現核心回測引擎 `DCAAddOnBacktester`：

- **資料預處理 (`prepare_data`)**：
  - 自動計算各 `AddOnRule` 對應之跌幅指標序列。
  - 判定定期定額扣款日（每月第一個交易日或指定交易日）。
- **交易模擬迴圈 (`run`)**：
  - **定期定額觸發**：當符合扣款日，執行固定金額買入，紀錄交易細節。
  - **低檔加碼觸發與過濾**：
    1. 評估所有 `eligible_rules`，若同日有多個規則觸發，自動選擇跌幅門檻最深者（不重複加碼）。
    2. 檢查 `cooldown_days` 限制（距上次加碼交易日天數）。
    3. 檢查 `max_addons_per_month` 本月累計次數。
    4. 檢查 `total_extra_budget` 與 `max_total_invest` 資金剩餘額度。
    5. 若通過所有檢查，執行加碼交易並記錄。
  - **資產與成本追蹤**：每日紀錄持股總股數、累計總投入成本、每日市值、平均持股成本、未實現損益與每日報酬率。
- **輸出**：回傳 `equity` (DataFrame) 與 `trades` (DataFrame)。

### 3.3 `src/dca_addon/metrics.py`
計算常規與專屬左側績效指標：

- **通用指標**：
  - `final_market_value`, `total_cost`, `total_return`, `CAGR`
  - `max_drawdown` (最大回撤), `max_drawdown_duration` (最長回撤期)
  - `sharpe_ratio`, `calmar_ratio`
- **左側策略專屬指標**：
  - `extra_budget_utilization_rate`: 額外資金使用率 = (總加碼投入金額 / `total_extra_budget`)
  - `alpha_vs_pure_dca`: 超額報酬 = (本策略總報酬率 - 純定期定額總報酬率)
  - `avg_cost_reduction_ratio`: 每次加碼平均拉低成本效益百分比
  - `addon_trade_count`, `regular_trade_count`

### 3.4 `src/dca_addon/optimizer.py`
參數搜尋與穩健性檢測：

- `grid_search(df, param_grid)`：
  - 支援 Python `multiprocessing` 多核心平行計算。
  - 篩選合理條件（如 $t_2 > t_1$, $m_2 \ge m1$）。
- `walk_forward_analysis(df, config, train_window_years, test_window_years)`：
  - 進行 In-Sample (IS) 最佳化與 Out-of-Sample (OOS) 滾動驗證，計算績效衰退率 (Degradation Ratio)，防止過度擬合。

### 3.5 `src/dca_addon/visualizer.py`
互動式 Plotly 圖表與獨立 HTML 報告產出：

- `plot_equity_and_cost()`：雙 Y 軸/三連動圖，顯示價格+加碼點散點、累計投入資金 vs 市值、平均持倉成本 vs 市價。
- `plot_underwater()`：水下圖（Drawdown Chart）。
- `plot_param_heatmap()`：參數敏銳度熱力圖（如 跌幅門檻 vs Lookback 天數對應之 Sharpe 或 Alpha）。
- `generate_html_report(equity, trades, metrics, filename)`：輸出包含 KPI 卡片與互動圖表的單頁 HTML 報告。

---

## 4. 驗證與測試計畫 (Verification & Testing Plan)

### 4.1 自動化單元測試 (`tests/test_dca_addon.py`)
使用 `pytest` 針對邊界條件進行 100% 覆蓋測試：
1. **定期定額觸發測試**：驗證跨月交易日是否精確觸發 base invest。
2. **多階梯加碼取最深跌幅測試**：驗證同日滿足 5% 與 10% 跌幅時，僅觸發 10% 階梯且次數只計 1 次。
3. **Cool-down 冷卻天數測試**：驗證觸發加碼後，N 天內再次滿足跌幅條件時不重複加碼。
4. **每月加碼次數上限測試**：驗證達到 `max_addons_per_month` 後不再觸發。
5. **預算上限截斷測試**：驗證額外預算不足時，加碼金額自動截斷至剩餘額度。
6. **純定期定額對照組測試**：當 rules 為空時，回測結果應與標準定期定額 100% 一致。

### 4.2 實體資料整合驗證
執行 `run_dca_backtest.py` 載入 `market_data.db` 中的真實數據（例如 `0050.TW` 與 `006208.TW`），比對 2020~2026 歷史區間之回測成果，並生成 HTML 報告確認視覺化完全正常。

---

## 5. 設計自檢 (Spec Self-Check)

1. **占位符檢查**：無 TODO、無待定字樣，所有欄位與模組皆有明確定義。
2. **內部一致性**：`config.py` 中的 `AddOnRule` 屬性與 `engine.py` 及 `metrics.py` 完全匹配。
3. **範圍控制**：聚焦於左側 ETF 加碼系統與研究流程，與 SuperTrend 順勢模組完全解耦。
4. **歧義檢查**：明確定義跌幅基準比較方式 (`reference_type`) 與同日多階梯選取規則。
