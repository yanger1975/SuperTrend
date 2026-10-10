# 設計規格書：將 DCA 左側交易系統拆分至獨立專案 (ETF_DCA)

- **日期**：2026-10-10
- **狀態**：設計已獲審查通過 (Approved)
- **目標專案**：`d:\MyProj\ETF_DCA`
- **原專案**：`d:\MyProj\SuperTrend`

---

## 1. 背景與動機 (Background & Motivation)

`SuperTrend` 專案原先包含兩套交易系統：
1. **右側順勢突破系統**：SuperTrend 與 SuperTrend AI（動態波動率自適應、滿倉/固定風險切換、K-Means 動態尋優、Telegram 每日盤後推播）。
2. **左側資產累積系統**：DCA AddOn（ETF/基金定期定額扣款、跌幅階梯式低檔加碼、平均持倉成本平滑、加碼預算管控、專屬 HTML 績效圖表）。

兩套系統在交易哲學、資金管理邏輯、回測目標與指標評估上完全不同。為了降低架構耦合、簡化維護成本，並讓左側策略能獨立演化，決定將左側交易系統完整搬移至獨立專案 `d:\MyProj\ETF_DCA`，並將 `SuperTrend` 原專案進行解耦與精簡。

---

## 2. 目標專案架構：`d:\MyProj\ETF_DCA`

新專案將專注於「ETF / 共同基金 定期定額與低檔加碼策略」的量化回測與參數優化研究。

### 2.1 目錄結構

```text
d:\MyProj\ETF_DCA\
├── .agents\
│   └── AGENTS.md                  # 工作規範（正體中文、Windows CRLF、temp/ 暫存等）
├── data\
│   └── ezmoney.json               # 統一投信基金代碼對照表
├── docs\
│   ├── python_回測框架_ETF加碼策略.md
│   └── 該如何呈現回測報告的績效指標與圖表.md
├── notebooks\
│   └── DCA_Strategy_Research.ipynb# 互動研究與參數熱力圖 Notebook
├── src\
│   ├── dca\                       # 核心回測引擎（自 dca_addon 移入並精簡命名為 dca）
│   │   ├── __init__.py
│   │   ├── config.py              # 加碼規則與策略配置 dataclass
│   │   ├── engine.py              # 回測引擎核心 (DCAAddOnBacktester)
│   │   ├── metrics.py             # 績效評估、預算使用率與自訂指標
│   │   ├── optimizer.py           # 網格搜尋最佳化 (grid_search)
│   │   └── visualizer.py          # Plotly 三連動圖表與獨立 HTML 報告生成
│   ├── scrapers\
│   │   └── ezmoney_scraper.py     # EZMoney 基金淨值爬蟲
│   ├── data_loader.py             # 歷史行情整合載入器 (yfinance + ezmoney)
│   └── storage.py                 # SQLite 本地快取與資料庫管理
├── tests\
│   ├── test_dca.py                # DCA 策略核心測試（原 test_dca_addon.py）
│   ├── test_data_loader.py        # 資料載入與快取測試
│   └── test_ezmoney_scraper.py    # 基金淨值抓取測試
├── temp\                          # 暫存目錄
├── dca_backtest_report.html       # 歷史產出報告範本
├── dca_report.html                # 歷史產出報告範本
├── fund_33YTW_report.html         # 歷史產出報告範本
├── run_dca_backtest.py            # 單次回測 CLI 工具
├── run_dca_optimizer.py           # 網格優化 CLI 工具
├── .gitignore
├── .env.example
├── pytest.ini
├── requirements.txt
├── README.md                      # 左側系統專屬繁體中文說明文件
└── TechStack.html                 # 左側系統技術架構文檔
```

### 2.2 模組命名與引用規格
在新專案中，核心模組路徑由 `src/dca_addon/` 重構為 **`src/dca/`**：
* 內部所有引用統一為：
  ```python
  from src.dca.config import StrategyConfig, AddOnRule
  from src.dca.engine import DCAAddOnBacktester
  from src.dca.metrics import evaluate_performance
  from src.dca.optimizer import grid_search
  from src.dca.visualizer import generate_html_report, plot_dca_summary
  from src.data_loader import DataLoader
  from src.storage import SQLiteStorage
  ```
* 測試檔相應更名為 `tests/test_dca.py`，內部引用全部同步調整為 `src.dca`。

---

## 3. 原專案解耦與清理：`d:\MyProj\SuperTrend`

在新專案 `d:\MyProj\ETF_DCA` 建立並通過全數測試驗證後，原專案執行以下清理工作：

### 3.1 移除左側專屬檔案
- 刪除 `src/dca_addon/` 全目錄。
- 刪除根目錄 CLI 腳本：`run_dca_backtest.py`、`run_dca_optimizer.py`。
- 刪除 `notebooks/DCA_AddOn_Strategy_Research.ipynb`。
- 刪除 `tests/test_dca_addon.py`。
- 刪除移轉後的過渡報告檔案：`dca_backtest_report.html`、`dca_report.html`、`fund_33YTW_report.html`。

### 3.2 測試依賴重構
- 修改 `tests/test_fund_integration.py`：
  - 移除 `from src.dca_addon.config import ...` 與 `from src.dca_addon.engine import ...`。
  - 將測試重點調整為驗證基金價格數據抓取完整性、`ticker_info` 元數據寫入，以及基金數據傳入既有技術指標模組（如 HMA / SuperTrend）的運算相容性，確保原專案單元測試無外部殘留依賴且全數通過。

### 3.3 文檔同步維護
- 更新 `README.md`：移除「D. ETF 定期定額 + 低檔加碼策略回測」與「E. ETF 低檔加碼網格最佳化」說明區塊。
- 更新 `TechStack.html`：移除左側 DCA 模組結構與 CLI 說明。
- 更新 `.agents/memory.md`：記錄左側系統已成功移轉至 `d:\MyProj\ETF_DCA`。

---

## 4. 驗證標準與成功條件 (Verification & Acceptance Criteria)

1. **`d:\MyProj\ETF_DCA` 驗證**：
   - 執行 `python -m pytest`，測試全部通過 (100% Passed)。
   - 執行 `python run_dca_backtest.py --symbol 0050.TW --amount 10000 --budget 500000 --output dca_backtest_report.html`，成功輸出 HTML 報告與 Console 摘要。
   - 執行 `python run_dca_optimizer.py --symbol 0050.TW`，成功完成參數網格掃描。
2. **`d:\MyProj\SuperTrend` 驗證**：
   - 執行 `python -m pytest`，所有測試全數通過（無任何 dca_addon 殘留引發之 ImportError）。
   - `README.md` 與 `TechStack.html` 精準反映純右側趨勢交易系統。
3. **流程規範恪守**：
   - 未獲使用者明確指令前，嚴禁執行 `git commit`。
