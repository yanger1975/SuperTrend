# SuperTrend 交易系統工作與記憶檔案 (Memory)

> **建立時間**：2026-07-25 (最後更新：2026-10-10)
> **專案位置**：`d:\MyProj\SuperTrend`  
> **當前狀態**：
> 1. 左側交易系統 (DCA) 拆分：已於 2026-10-10 成功將所有左側定期定額與低檔加碼模組、CLI 工具、Notebook、HTML 報告及測試完整拆分移轉至獨立專案 `d:\MyProj\ETF_DCA`。
> 2. SuperTrend 右側順勢系統：回測引擎、指標庫、資料快取、SuperTrend AI 批次最佳化 (`run_batch_optimization_supertrend_ai.py`)、Telegram 自動化推播、GitHub Actions CI 排程全數正常運作（31 項單元測試全數通過）。

---

## 1. 專案目標與定位 (Project Background & Goal)

本專案專注於**右側順勢突破交易系統（SuperTrend 與 SuperTrend AI）**。左側資產累積與低檔加碼策略已獨立維護於 `d:\MyProj\ETF_DCA`。


---

## 2. 已建立之架構與檔案清單 (Completed Architecture & Files)

### 核心模組 (`src/dca_addon/`)
1. [src/dca_addon/config.py](file:///d:/MyProj/SuperTrend/src/dca_addon/config.py)
   - `AddOnRule`: 加碼規則 dataclass（比較天數 `lookback_days`、跌幅門檻 `drawdown_threshold`、加碼倍數 `multiplier`、比較基準 `reference_type`）。
   - `StrategyConfig`: 策略配置（基礎定期定額金額、冷卻天數 `cooldown_days`、每月加碼次數上限 `max_addons_per_month`、額外加碼總預算 `total_extra_budget`、總投入資金上限）。
2. [src/dca_addon/engine.py](file:///d:/MyProj/SuperTrend/src/dca_addon/engine.py)
   - `DCAAddOnBacktester`: 回測引擎核心。
   - 自動判斷每月扣款日、處理多階梯加碼並自動選取當日最深跌幅階梯（不重複加碼）、驗證冷卻期與預算上限。
   - 兼容 DatetimeIndex 與各種名稱之日期欄位（如 `Date` 或 `datetime`）。
3. [src/dca_addon/metrics.py](file:///d:/MyProj/SuperTrend/src/dca_addon/metrics.py)
   - `evaluate_performance()`: 計算 CAGR、Max Drawdown、Sharpe Ratio、Calmar Ratio。
   - 算產左側專屬指標：**加碼預算使用率** (`extra_budget_utilization_rate`)、**Alpha vs 純定期定額** (`alpha_vs_pure_dca`)、**加碼次數**。
4. [src/dca_addon/optimizer.py](file:///d:/MyProj/SuperTrend/src/dca_addon/optimizer.py)
   - `grid_search()`: 多維度網格搜尋最佳化函式。
5. [src/dca_addon/visualizer.py](file:///d:/MyProj/SuperTrend/src/dca_addon/visualizer.py)
   - `plot_dca_summary()`: Plotly 三連動圖表（價格與加碼點散點、投入資金 vs 市值、平均持倉成本 vs 市價）。
   - `generate_html_report()`: 產出包含 **KPI 卡片**、**⚙️ 策略參數說明卡片**、** Plotly 互動圖表** 與 **📌 加碼交易明細紀錄表** 的獨立 HTML 報告。

### CLI 工具與研究 Notebook
- [run_dca_backtest.py](file:///d:/MyProj/SuperTrend/run_dca_backtest.py): 單次回測 CLI 腳本（支援 `--symbol`, `--start`, `--end`, `--amount`, `--budget`, `--output`）。
- [run_dca_optimizer.py](file:///d:/MyProj/SuperTrend/run_dca_optimizer.py): 網格搜尋 CLI 腳本，輸出 `dca_optimization_results.csv`。
- [notebooks/DCA_AddOn_Strategy_Research.ipynb](file:///d:/MyProj/SuperTrend/notebooks/DCA_AddOn_Strategy_Research.ipynb): 互動式研究專用 Notebook（包含單次回測、Plotly 圖表、Grid Search 排行榜與參數敏銳度熱力圖 `px.imshow`）。

### 設計規格書與計畫
- 規格書：[docs/superpowers/specs/2026-07-24-dca-addon-system-design.md](file:///d:/MyProj/SuperTrend/docs/superpowers/specs/2026-07-24-dca-addon-system-design.md)
- 計畫書：[docs/superpowers/plans/2026-07-24-dca-addon-system.md](file:///d:/MyProj/SuperTrend/docs/superpowers/plans/2026-07-24-dca-addon-system.md)

---

## 3. 已解決之關鍵 Bug 與優化紀錄 (Fixed Issues & Optimizations)

1. **`AttributeError: 'SQLiteStorage' object has no attribute 'load_daily_data'`**：
   - 原因：CLI 腳本誤呼叫 SQLiteStorage 不存在的 `load_daily_data`。
   - 修正：改用標準 `DataLoader().fetch_data(ticker, start_date, end_date, interval="1d")`。
2. **Plotly `opacity` 傳參錯誤**：
   - 原因：在 `go.Scatter` 中將 `opacity` 誤置於 `line=dict(...)` 內部。
   - 修正：將 `opacity=0.35` 移至 `go.Scatter` 層級。
3. **Windows Console 中文字元編碼問題**：
   - 修正：於 CLI 腳本加入 `sys.stdout.reconfigure(encoding="utf-8")`，並於測試中指定 `PYTHONIOENCODING=utf-8`。
4. **HTML 報告缺乏參數與交易細節**：
   - 修正：在 `visualizer.py` 中新增「策略參數設定面板」與「加碼交易明細表格 (包含日期、成交價、金額、股數、跌幅與倍數)」，並於散點圖標記加入 Hover Tooltip。
5. **`RuntimeWarning: invalid value encountered in subtract` (Pandas `nanops.py`)**：
   - 原因：原 Sharpe Ratio 計算使用 `equity["Return"].pct_change()`，因初期 Return 為 `0.0` 導致 `0/0` 產生 `NaN/inf`。
   - 修正：改為使用 `equity["Close"].pct_change().replace([np.inf, -np.inf], np.nan).dropna()`。目前測試集 warning 數為 `0`。

---

## 4. 驗證指令 (Verification Commands)

明天復工時，可直接執行以下指令進行快速健康檢查：

```bash
# 1. 執行單元測試套件 (應為 31 passed, 0 warnings)
python -m pytest

# 2. 測試左側加碼單次回測並產出 HTML 報告
python run_dca_backtest.py --symbol 0050.TW --amount 10000 --budget 500000 --output dca_backtest_report.html

# 3. 測試網格參數最佳化
python run_dca_optimizer.py --symbol 0050.TW
```

---

## 5. 基金淨值 Web API 擷取方法 (Fund NAV Scraping Method)

針對 **ezmoney 基金淨值查詢（如「統一全球新科技基金」代碼 `33YTW`）**，經實測驗證，因網站具備 ASP.NET CSRF 防護，需要先進行 GET 取得 Session Cookie 與 Token 後再發送 POST。

### API 技術規格
- **GET 頁面 URL**：`https://www.ezmoney.com.tw/funds/nav`
- **POST 請求 URL**：`https://www.ezmoney.com.tw/funds/nav`
- **關鍵 Header**：`User-Agent: Mozilla/5.0 ...`
- **POST Payload 參數**：
  - `__RequestVerificationToken`: （自 GET 回應 HTML 的 `<input name="__RequestVerificationToken" value="...">` 中提取）
  - `start`: `"114/01/01"` (民國年/月/日)
  - `end`: `"115/07/25"`
  - `Fund`: `"33YTW"` (統一全球新科技基金)

### 完整 Python 擷取腳本範例

```python
import requests
from bs4 import BeautifulSoup
import pandas as pd

url = "https://www.ezmoney.com.tw/funds/nav"
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
})

# 1. 發送 GET 取得 Token 與 Session Cookie
r_get = session.get(url)
soup_get = BeautifulSoup(r_get.text, "html.parser")
token_tag = soup_get.find("input", {"name": "__RequestVerificationToken"})
token = token_tag.get("value") if token_tag else ""

# 2. 帶入 Token 與查詢條件發送 POST
payload = {
    "__RequestVerificationToken": token,
    "start": "114/01/01",
    "end": "115/07/25",
    "Fund": "33YTW"
}

r_post = session.post(url, data=payload)
r_post.encoding = "utf-8"

# 3. 解析 HTML 表格數據
soup_post = BeautifulSoup(r_post.text, "html.parser")
tables = soup_post.find_all("table")

if len(tables) >= 2:
    table = tables[1]
    rows = table.find_all("tr")
    parsed_data = []

    for tr in rows[1:]:
        cols = [td.text.strip().replace("\r", "").replace("\n", "").replace(" ", "") for td in tr.find_all("td")]
        if len(cols) == 4:
            date_val = cols[0].replace("日期", "")
            nav_val = float(cols[1].replace("基金淨值", ""))
            change_val = float(cols[2].replace("基金漲跌", ""))
            pct_val = cols[3].replace("基金漲跌幅", "")
            parsed_data.append([date_val, nav_val, change_val, pct_val])

    df = pd.DataFrame(parsed_data, columns=["淨值日期", "淨值", "漲跌", "漲跌幅"])
    print("成功擷取基金淨值比數:", len(df))
```

---

## 6. 已完工項目：EZMoney 共同基金淨值爬蟲與 SQLite 整合 (Completed Fund Scraper)

- **模組位置**：[src/scrapers/ezmoney_scraper.py](file:///d:/MyProj/SuperTrend/src/scrapers/ezmoney_scraper.py)
- **資料庫擴充**：`SQLiteStorage` 新增 `ticker_info` 資料表，記錄中文全名 (如 `統一全球新科技基金`)、資產類別 (`fund`) 與資料來源 (`ezmoney`)。
- **價格格式**：`Open`, `High`, `Low`, `Volume` 補 `0.0`，`Close` 為每日淨值 (NAV)。
- **DataLoader 自動路由**：傳入 `.EZ` 後綴代碼（如 `33YTW.EZ`）或於 `data/ezmoney.json` 之基金時，自動經由 `EzMoneyScraper` 下載並寫入 SQLite。
- **回測驗證**：已驗證 `python run_dca_backtest.py --symbol 33YTW.EZ`，成功計算並輸出 `fund_33YTW_report.html` (總報酬率 126.70%, MDD -28.17%)。

---

## 7. 已完工項目：SuperTrend AI 批次最佳化與自動化推播 (Completed AI Batch & Automation)

1. **批次參數最佳化 (`run_batch_optimization_supertrend_ai.py`)**：
   - 讀取 `data/supertrend_ai_tickers.json` 標的清單（支援股票與 `.EZ` 基金）。
   - 導入 `ProcessPoolExecutor` 進行多核心平行運算，大幅加速回測。
   - 優化參數統一寫入 `data/market_data.db`，並自動匯出至 `data/optimized_params_ai.json`。針對 CI 空白環境支援「反向匯入」JSON 至資料庫，避免不必要的重新優化。
2. **Telegram 交易訊號防截斷推播**：
   - 強化 `src/telegram_notifier.py` 的 `split_blocks`，確保單一標的資訊完整不被 4096 字元限制切斷。
   - 平日模式（自動推播最新倉位與進出場建議價）、週六模式（強制重新優化並推播最佳化參數，如 ATR、Factor 等）。
   - 自動將基金代號轉換為中文全名（如 `33YTW.EZ` -> 統一全球新科技基金）。
3. **GitHub Actions 每日排程 CI**：
   - 建立 `.github/workflows/daily_supertrend_ai_signals.yml`。
   - 週一至週五：更新歷史數據，掃描最新收盤價，推播進出場訊號。
   - 週六：自動帶入 `--force` 觸發全標的重新網格參數優化，推播優化結果，並自動 Commit `optimized_params_ai.json` 回 GitHub Repo 保存最新參數。
   - 解決了 SQLite 多進程併發建立資料表時的 `duplicate column name` Race Condition 問題。

---

## 8. 下階段可擴充方向 (Future Work & Extensions)

### 左側交易系統 (DCA AddOn)
1. **Walk-Forward Analysis (樣本外驗證)**：
   - 在 `src/dca_addon/optimizer.py` 中補充 In-Sample (訓練期) 與 Out-of-Sample (測試期) 滾動分割，計算績效衰退率 (Degradation Ratio)。
2. **反彈條件過濾 (Rebound Filter)**：
   - 探索在跌幅滿足後，加入「站回 N 日均線」或「RSI 自超賣區回升」才正式觸發扣款的策略變體。

