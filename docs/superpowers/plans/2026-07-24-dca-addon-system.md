# ETF 定期定額 + 低檔加碼策略（左側交易）系統 實現計畫

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推薦）或 superpowers:executing-plans 逐任務實現此計畫。步驟使用複選框（`- [ ]`）語法來跟踪進度。

**目標：** 構建獨立的 ETF 定期定額與低檔條件加碼（左側交易）回測引擎、參數最佳化器、Plotly 互動視覺化報告生成器與 Jupyter Notebook 研究環境。

**架構：** 於 `src/dca_addon/` 中建立模組化核心元件（`config`, `engine`, `metrics`, `optimizer`, `visualizer`），共享既有的 `src/storage.py` SQLite 數據載入器，並提供獨立 CLI 腳本與互動式 Notebook。

**技術棧：** Python 3.10+, pandas, numpy, plotly, pytest, multiprocessing, jupyter

---

## 預期建立與修改的檔案列表

- [NEW] `src/dca_addon/__init__.py` - 模組初始化匯出
- [NEW] `src/dca_addon/config.py` - 加碼規則與策略配置 dataclass
- [NEW] `src/dca_addon/engine.py` - 回測引擎核心 (DCAAddOnBacktester)
- [NEW] `src/dca_addon/metrics.py` - 績效指標、風險指標與自訂左側加碼指標
- [NEW] `src/dca_addon/optimizer.py` - 多線程網格搜尋與 Walk-Forward Analysis
- [NEW] `src/dca_addon/visualizer.py` - Plotly 三連動互動圖表與 HTML 報告產出
- [NEW] `run_dca_backtest.py` - CLI 單次回測執行腳本
- [NEW] `run_dca_optimizer.py` - CLI 網格最佳化執行腳本
- [NEW] `notebooks/DCA_AddOn_Strategy_Research.ipynb` - 互動式研究與圖表繪製 Notebook
- [NEW] `tests/test_dca_addon.py` - 單元測試套件

---

### 任務 1：建立 `src/dca_addon/config.py` (策略規則與配置結構)

**檔案：**
- 建立：`src/dca_addon/config.py`
- 建立：`src/dca_addon/__init__.py`
- 測試：`tests/test_dca_addon.py`

- [ ] **步驟 1：編寫失敗的測試 (`tests/test_dca_addon.py`)**

```python
import pytest
from src.dca_addon.config import AddOnRule, StrategyConfig


def test_addon_rule_creation():
    rule = AddOnRule(
        lookback_days=20,
        drawdown_threshold=0.06,
        multiplier=2.0,
        reference_type="shift"
    )
    assert rule.lookback_days == 20
    assert rule.drawdown_threshold == 0.06
    assert rule.multiplier == 2.0
    assert rule.reference_type == "shift"


def test_strategy_config_defaults():
    rule = AddOnRule(lookback_days=20, drawdown_threshold=0.06, multiplier=2.0)
    config = StrategyConfig(
        base_invest_amount=10000,
        rules=[rule]
    )
    assert config.base_invest_amount == 10000
    assert len(config.rules) == 1
    assert config.invest_frequency == "M"
    assert config.cooldown_days == 0
    assert config.max_addons_per_month is None
    assert config.total_extra_budget is None
    assert config.max_total_invest is None
    assert config.cash_risk_free_rate == 0.0
```

- [ ] **步驟 2：運行測試驗證失敗**

運行：`pytest tests/test_dca_addon.py::test_addon_rule_creation -v`
預期：FAIL，報錯 "ModuleNotFoundError: No module named 'src.dca_addon'"

- [ ] **步驟 3：編寫最少實現代碼**

創建 `src/dca_addon/__init__.py`：
```python
# src/dca_addon/__init__.py
```

創建 `src/dca_addon/config.py`：
```python
from dataclasses import dataclass, field
from typing import List, Optional, Literal


@dataclass
class AddOnRule:
    lookback_days: int
    drawdown_threshold: float  # 例如 0.06 代表跌 6%
    multiplier: float          # 例如 2.0 代表為原定期定額金額的 2 倍
    reference_type: Literal["shift", "high"] = "shift"  # 'shift': N日前收盤價, 'high': N日最高價


@dataclass
class StrategyConfig:
    base_invest_amount: float
    rules: List[AddOnRule] = field(default_factory=list)
    invest_frequency: str = "M"                   # 'M' 代表每月
    cooldown_days: int = 0                       # 觸發後冷卻天數
    max_addons_per_month: Optional[int] = None    # 每月加碼次數上限
    total_extra_budget: Optional[float] = None     # 額外加碼總預算上限
    max_total_invest: Optional[float] = None      # 總投入金額上限
    cash_risk_free_rate: float = 0.0             # 未投入現金無風險年利率
```

- [ ] **步驟 4：運行測試驗證通過**

運行：`pytest tests/test_dca_addon.py::test_addon_rule_creation tests/test_dca_addon.py::test_strategy_config_defaults -v`
預期：PASS

- [ ] **步驟 5：Commit**

> （由使用者手動 commit 或後續執行）

---

### 任務 2：建立 `src/dca_addon/engine.py` (左側加碼回測引擎)

**檔案：**
- 建立：`src/dca_addon/engine.py`
- 修改：`src/dca_addon/__init__.py`
- 測試：`tests/test_dca_addon.py`

- [ ] **步驟 1：編寫失敗的測試 (`tests/test_dca_addon.py`)**

```python
import pandas as pd
import numpy as np
from src.dca_addon.config import AddOnRule, StrategyConfig
from src.dca_addon.engine import DCAAddOnBacktester


def create_sample_price_df():
    dates = pd.date_range("2020-01-01", periods=60, freq="B")
    # 建立先漲後跌的價格序列：前20天 100, 之後掉到 90 (跌 10%)
    prices = [100.0] * 25 + [90.0] * 35
    return pd.DataFrame({"Date": dates, "Close": prices})


def test_regular_dca_only():
    df = create_sample_price_df()
    config = StrategyConfig(base_invest_amount=10000, rules=[])
    bt = DCAAddOnBacktester(df, config)
    equity, trades = bt.run()

    assert not equity.empty
    assert len(trades) > 0
    # 驗證所有交易均為 regular
    assert (trades["Type"] == "regular").all()


def test_addon_trigger_and_cooldown():
    df = create_sample_price_df()
    rule = AddOnRule(lookback_days=10, drawdown_threshold=0.08, multiplier=2.0)
    config = StrategyConfig(
        base_invest_amount=10000,
        rules=[rule],
        cooldown_days=5,
        max_addons_per_month=1
    )
    bt = DCAAddOnBacktester(df, config)
    equity, trades = bt.run()

    addon_trades = trades[trades["Type"] == "addon"]
    assert len(addon_trades) >= 1
    # 加碼金額應為 20000
    assert addon_trades["Amount"].iloc[0] == 20000.0
```

- [ ] **步驟 2：運行測試驗證失敗**

運行：`pytest tests/test_dca_addon.py::test_regular_dca_only -v`
預期：FAIL，報錯 "ImportError: cannot import name 'DCAAddOnBacktester'"

- [ ] **步驟 3：編寫最少實現代碼 (`src/dca_addon/engine.py`)**

```python
from typing import List, Tuple, Dict, Any, Optional
import pandas as pd
import numpy as np
from src.dca_addon.config import StrategyConfig, AddOnRule


class DCAAddOnBacktester:
    def __init__(self, df: pd.DataFrame, config: StrategyConfig):
        self.df = df.copy().sort_values("Date").reset_index(drop=True)
        self.config = config
        self.trades: List[Dict[str, Any]] = []

    def prepare_data(self) -> None:
        self.df["Date"] = pd.to_datetime(self.df["Date"])
        self.df["year_month"] = self.df["Date"].dt.to_period("M")

        for i, rule in enumerate(self.config.rules):
            col_name = f"ret_rule_{i}"
            if rule.reference_type == "high":
                rolling_high = self.df["Close"].rolling(window=rule.lookback_days, min_periods=1).max()
                self.df[col_name] = self.df["Close"] / rolling_high - 1.0
            else:
                self.df[col_name] = self.df["Close"] / self.df["Close"].shift(rule.lookback_days) - 1.0

    def is_regular_invest_day(self, idx: int) -> bool:
        if idx == 0:
            return True
        curr_month = self.df.loc[idx, "year_month"]
        prev_month = self.df.loc[idx - 1, "year_month"]
        return curr_month != prev_month

    def run(self) -> Tuple[pd.DataFrame, pd.DataFrame]:
        self.prepare_data()

        total_units = 0.0
        total_cost = 0.0
        extra_budget_used = 0.0
        last_addon_idx = -999999
        monthly_addon_count: Dict[Any, int] = {}
        portfolio_values = []

        for idx, row in self.df.iterrows():
            date = row["Date"]
            price = float(row["Close"])
            ym = row["year_month"]

            # 1. 定期定額扣款
            if self.is_regular_invest_day(idx):
                amount = self.config.base_invest_amount
                # 總投入限制檢查
                if self.config.max_total_invest is not None:
                    remaining = self.config.max_total_invest - total_cost
                    amount = min(amount, max(0.0, remaining))

                if amount > 0:
                    units = amount / price
                    total_units += units
                    total_cost += amount
                    self.trades.append({
                        "Date": date,
                        "Type": "regular",
                        "Price": price,
                        "Amount": amount,
                        "Units": units
                    })

            # 2. 低檔加碼觸發
            eligible_rules = []
            for i, rule in enumerate(self.config.rules):
                ret_col = f"ret_rule_{i}"
                ret = row[ret_col]
                if pd.notna(ret) and ret <= -rule.drawdown_threshold:
                    eligible_rules.append(rule)

            if eligible_rules:
                # 取跌幅門檻最深者
                selected_rule = max(eligible_rules, key=lambda r: r.drawdown_threshold)

                # 冷卻天數檢查
                if idx - last_addon_idx <= self.config.cooldown_days:
                    selected_rule = None

                # 每月次數上限檢查
                curr_count = monthly_addon_count.get(ym, 0)
                if (
                    selected_rule is not None
                    and self.config.max_addons_per_month is not None
                    and curr_count >= self.config.max_addons_per_month
                ):
                    selected_rule = None

                if selected_rule is not None:
                    addon_amount = self.config.base_invest_amount * selected_rule.multiplier

                    # 額外加碼預算檢查
                    if self.config.total_extra_budget is not None:
                        if extra_budget_used + addon_amount > self.config.total_extra_budget:
                            addon_amount = max(0.0, self.config.total_extra_budget - extra_budget_used)

                    # 總投入資金上限檢查
                    if self.config.max_total_invest is not None:
                        remaining = self.config.max_total_invest - total_cost
                        addon_amount = min(addon_amount, max(0.0, remaining))

                    if addon_amount > 0:
                        units = addon_amount / price
                        total_units += units
                        total_cost += amount if 'amount' in locals() else addon_amount
                        total_cost += addon_amount
                        extra_budget_used += addon_amount
                        last_addon_idx = idx
                        monthly_addon_count[ym] = curr_count + 1
                        self.trades.append({
                            "Date": date,
                            "Type": "addon",
                            "Price": price,
                            "Amount": addon_amount,
                            "Units": units,
                            "RuleLookback": selected_rule.lookback_days,
                            "RuleThreshold": selected_rule.drawdown_threshold,
                            "RuleMultiplier": selected_rule.multiplier,
                        })

            market_value = total_units * price
            avg_cost = total_cost / total_units if total_units > 0 else 0.0
            unrealized_pnl = market_value - total_cost
            ret = market_value / total_cost - 1.0 if total_cost > 0 else 0.0

            portfolio_values.append({
                "Date": date,
                "Close": price,
                "TotalUnits": total_units,
                "TotalCost": total_cost,
                "MarketValue": market_value,
                "AvgCost": avg_cost,
                "UnrealizedPnL": unrealized_pnl,
                "Return": ret
            })

        equity = pd.DataFrame(portfolio_values)
        trades = pd.DataFrame(self.trades) if self.trades else pd.DataFrame(
            columns=["Date", "Type", "Price", "Amount", "Units"]
        )
        return equity, trades
```

- [ ] **步驟 4：運行測試驗證通過**

運行：`pytest tests/test_dca_addon.py::test_regular_dca_only tests/test_dca_addon.py::test_addon_trigger_and_cooldown -v`
預期：PASS

---

### 任務 3：建立 `src/dca_addon/metrics.py` (績效與自訂指標計算)

**檔案：**
- 建立：`src/dca_addon/metrics.py`
- 測試：`tests/test_dca_addon.py`

- [ ] **步驟 1：編寫失敗的測試 (`tests/test_dca_addon.py`)**

```python
from src.dca_addon.metrics import evaluate_performance


def test_evaluate_performance_metrics():
    df = create_sample_price_df()
    rule = AddOnRule(lookback_days=10, drawdown_threshold=0.08, multiplier=2.0)
    config = StrategyConfig(
        base_invest_amount=10000,
        rules=[rule],
        total_extra_budget=100000
    )
    bt = DCAAddOnBacktester(df, config)
    equity, trades = bt.run()

    perf = evaluate_performance(equity, trades, config)
    assert "total_return" in perf
    assert "max_drawdown" in perf
    assert "extra_budget_utilization_rate" in perf
    assert "alpha_vs_pure_dca" in perf
    assert perf["addon_count"] >= 1
```

- [ ] **步驟 2：運行測試驗證失敗**

運行：`pytest tests/test_dca_addon.py::test_evaluate_performance_metrics -v`
預期：FAIL，報錯 "ModuleNotFoundError: No module named 'src.dca_addon.metrics'"

- [ ] **步驟 3：編寫最少實現代碼 (`src/dca_addon/metrics.py`)**

```python
from typing import Dict, Any, Optional
import pandas as pd
import numpy as np
from src.dca_addon.config import StrategyConfig


def evaluate_performance(
    equity: pd.DataFrame,
    trades: pd.DataFrame,
    config: Optional[StrategyConfig] = None
) -> Dict[str, Any]:
    if equity.empty:
        return {}

    result: Dict[str, Any] = {}

    final_value = equity["MarketValue"].iloc[-1]
    total_cost = equity["TotalCost"].iloc[-1]
    total_return = equity["Return"].iloc[-1]

    result["final_market_value"] = round(final_value, 2)
    result["total_cost"] = round(total_cost, 2)
    result["total_return"] = round(total_return, 4)

    # 計算 CAGR
    days = (equity["Date"].iloc[-1] - equity["Date"].iloc[0]).days
    years = days / 365.25 if days > 0 else 0.0
    cagr = (final_value / total_cost) ** (1.0 / years) - 1.0 if years > 0 and total_cost > 0 else 0.0
    result["cagr"] = round(cagr, 4)

    # 回撤計算 (Drawdown based on MarketValue Peak)
    equity_copy = equity.copy()
    equity_copy["Peak"] = equity_copy["MarketValue"].cummax()
    equity_copy["Drawdown"] = np.where(
        equity_copy["Peak"] > 0,
        equity_copy["MarketValue"] / equity_copy["Peak"] - 1.0,
        0.0
    )
    max_dd = equity_copy["Drawdown"].min()
    result["max_drawdown"] = round(max_dd, 4)

    # Sharpe & Calmar Ratio
    daily_returns = equity_copy["Return"].pct_change().dropna()
    std_dev = daily_returns.std() * np.sqrt(252) if len(daily_returns) > 1 else 0.0
    sharpe = (cagr - 0.015) / std_dev if std_dev > 0 else 0.0
    calmar = cagr / abs(max_dd) if max_dd < 0 else 0.0
    result["sharpe_ratio"] = round(sharpe, 2)
    result["calmar_ratio"] = round(calmar, 2)

    # 交易統計
    addon_trades = trades[trades["Type"] == "addon"] if not trades.empty else pd.DataFrame()
    regular_trades = trades[trades["Type"] == "regular"] if not trades.empty else pd.DataFrame()

    result["regular_count"] = len(regular_trades)
    result["addon_count"] = len(addon_trades)
    total_addon_amount = addon_trades["Amount"].sum() if not addon_trades.empty else 0.0
    result["total_addon_amount"] = round(total_addon_amount, 2)

    # 左側專屬指標
    if config and config.total_extra_budget and config.total_extra_budget > 0:
        utilization = total_addon_amount / config.total_extra_budget
        result["extra_budget_utilization_rate"] = round(utilization, 4)
    else:
        result["extra_budget_utilization_rate"] = 0.0

    # 計算純定期定額比較基準 (Pure DCA Benchmark)
    pure_dca_units = regular_trades["Units"].sum() if not regular_trades.empty else 0.0
    pure_dca_cost = regular_trades["Amount"].sum() if not regular_trades.empty else 0.0
    last_price = equity["Close"].iloc[-1]
    pure_dca_value = pure_dca_units * last_price
    pure_dca_return = (pure_dca_value / pure_dca_cost - 1.0) if pure_dca_cost > 0 else 0.0

    result["pure_dca_return"] = round(pure_dca_return, 4)
    result["alpha_vs_pure_dca"] = round(total_return - pure_dca_return, 4)

    return result
```

- [ ] **步驟 4：運行測試驗證通過**

運行：`pytest tests/test_dca_addon.py::test_evaluate_performance_metrics -v`
預期：PASS

---

### 任務 4：建立 `src/dca_addon/optimizer.py` (網格搜尋與 Walk-Forward 最佳化)

**檔案：**
- 建立：`src/dca_addon/optimizer.py`
- 測試：`tests/test_dca_addon.py`

- [ ] **步驟 1：編寫失敗的測試 (`tests/test_dca_addon.py`)**

```python
from src.dca_addon.optimizer import grid_search


def test_grid_search_execution():
    df = create_sample_price_df()
    param_grid = {
        "lookbacks": [5, 10],
        "first_thresholds": [0.05],
        "second_thresholds": [0.10],
        "first_multipliers": [1.5],
        "second_multipliers": [2.0],
        "cooldowns": [0],
        "monthly_limits": [1]
    }
    results_df = grid_search(df, param_grid, base_amount=10000)
    assert not results_df.empty
    assert "cagr" in results_df.columns
    assert "max_drawdown" in results_df.columns
```

- [ ] **步驟 2：運行測試驗證失敗**

運行：`pytest tests/test_dca_addon.py::test_grid_search_execution -v`
預期：FAIL，報錯 "ModuleNotFoundError: No module named 'src.dca_addon.optimizer'"

- [ ] **步驟 3：編寫最少實現代碼 (`src/dca_addon/optimizer.py`)**

```python
from itertools import product
from typing import Dict, Any, List
import pandas as pd
from src.dca_addon.config import AddOnRule, StrategyConfig
from src.dca_addon.engine import DCAAddOnBacktester
from src.dca_addon.metrics import evaluate_performance


def grid_search(
    df: pd.DataFrame,
    param_grid: Dict[str, List[Any]],
    base_amount: float = 10000.0,
    total_extra_budget: float = 500000.0
) -> pd.DataFrame:
    records = []

    lookbacks = param_grid.get("lookbacks", [10, 20])
    t1_list = param_grid.get("first_thresholds", [0.05, 0.08])
    t2_list = param_grid.get("second_thresholds", [0.10, 0.12])
    m1_list = param_grid.get("first_multipliers", [1.5, 2.0])
    m2_list = param_grid.get("second_multipliers", [2.0, 3.0])
    cooldowns = param_grid.get("cooldowns", [0, 3])
    monthly_limits = param_grid.get("monthly_limits", [1, 2])

    for lb, t1, t2, m1, m2, cd, ml in product(
        lookbacks, t1_list, t2_list, m1_list, m2_list, cooldowns, monthly_limits
    ):
        if t2 <= t1 or m2 < m1:
            continue

        config = StrategyConfig(
            base_invest_amount=base_amount,
            rules=[
                AddOnRule(lookback_days=lb, drawdown_threshold=t1, multiplier=m1),
                AddOnRule(lookback_days=lb, drawdown_threshold=t2, multiplier=m2),
            ],
            cooldown_days=cd,
            max_addons_per_month=ml,
            total_extra_budget=total_extra_budget
        )

        bt = DCAAddOnBacktester(df, config)
        equity, trades = bt.run()
        perf = evaluate_performance(equity, trades, config)

        records.append({
            "lookback": lb,
            "t1": t1,
            "t2": t2,
            "m1": m1,
            "m2": m2,
            "cooldown": cd,
            "monthly_limit": ml,
            **perf
        })

    return pd.DataFrame(records)
```

- [ ] **步驟 4：運行測試驗證通過**

運行：`pytest tests/test_dca_addon.py::test_grid_search_execution -v`
預期：PASS

---

### 任務 5：建立 `src/dca_addon/visualizer.py` (Plotly 視覺化與 HTML 報告)

**檔案：**
- 建立：`src/dca_addon/visualizer.py`
- 測試：`tests/test_dca_addon.py`

- [ ] **步驟 1：編寫失敗的測試 (`tests/test_dca_addon.py`)**

```python
import os
from src.dca_addon.visualizer import generate_html_report


def test_generate_html_report_output(tmp_path):
    df = create_sample_price_df()
    config = StrategyConfig(base_invest_amount=10000, rules=[])
    bt = DCAAddOnBacktester(df, config)
    equity, trades = bt.run()
    perf = evaluate_performance(equity, trades, config)

    output_path = tmp_path / "report.html"
    generate_html_report(df, equity, trades, perf, str(output_path))
    assert os.path.exists(output_path)
    assert os.path.getsize(output_path) > 0
```

- [ ] **步驟 2：運行測試驗證失敗**

運行：`pytest tests/test_dca_addon.py::test_generate_html_report_output -v`
預期：FAIL，報錯 "ModuleNotFoundError: No module named 'src.dca_addon.visualizer'"

- [ ] **步驟 3：編寫最少實現代碼 (`src/dca_addon/visualizer.py`)**

```python
from typing import Dict, Any
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def plot_dca_summary(
    df: pd.DataFrame,
    equity: pd.DataFrame,
    trades: pd.DataFrame
) -> go.Figure:
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        subplot_titles=(
            "標的價格與加碼點位散點圖",
            "累計投入資金 vs 市場總市值",
            "平均持倉成本 vs 市場價格 (Underwater)"
        )
    )

    # Subplot 1: Price & Addon triggers
    fig.add_trace(
        go.Scatter(x=equity["Date"], y=equity["Close"], name="Close Price", line=dict(color="blue")),
        row=1, col=1
    )

    if not trades.empty:
        addon_trades = trades[trades["Type"] == "addon"]
        if not addon_trades.empty:
            fig.add_trace(
                go.Scatter(
                    x=addon_trades["Date"],
                    y=addon_trades["Price"],
                    mode="markers",
                    name="AddOn Trigger",
                    marker=dict(symbol="triangle-up", size=12, color="red")
                ),
                row=1, col=1
            )

    # Subplot 2: Total Cost vs Market Value
    fig.add_trace(
        go.Scatter(x=equity["Date"], y=equity["TotalCost"], name="Total Cost", line=dict(color="gray", dash="dash")),
        row=2, col=1
    )
    fig.add_trace(
        go.Scatter(x=equity["Date"], y=equity["MarketValue"], name="Market Value", line=dict(color="green")),
        row=2, col=1
    )

    # Subplot 3: Avg Cost vs Close Price
    fig.add_trace(
        go.Scatter(x=equity["Date"], y=equity["AvgCost"], name="Avg Cost", line=dict(color="orange")),
        row=3, col=1
    )
    fig.add_trace(
        go.Scatter(x=equity["Date"], y=equity["Close"], name="Close", line=dict(color="blue", opacity=0.4)),
        row=3, col=1
    )

    fig.update_layout(height=800, title_text="DCA + 低檔加碼策略回測綜合報告", showlegend=True)
    return fig


def generate_html_report(
    df: pd.DataFrame,
    equity: pd.DataFrame,
    trades: pd.DataFrame,
    metrics: Dict[str, Any],
    output_filename: str
) -> None:
    fig = plot_dca_summary(df, equity, trades)
    chart_html = fig.to_html(full_html=False, include_plotlyjs="cdn")

    kpi_cards = f"""
    <div style="display: flex; gap: 15px; flex-wrap: wrap; margin-bottom: 20px;">
        <div style="border: 1px solid #ccc; padding: 15px; border-radius: 8px; flex: 1;">
            <h4>總回報率</h4><p style="font-size: 20px; font-weight: bold;">{metrics.get('total_return', 0):.2%}</p>
        </div>
        <div style="border: 1px solid #ccc; padding: 15px; border-radius: 8px; flex: 1;">
            <h4>CAGR</h4><p style="font-size: 20px; font-weight: bold;">{metrics.get('cagr', 0):.2%}</p>
        </div>
        <div style="border: 1px solid #ccc; padding: 15px; border-radius: 8px; flex: 1;">
            <h4>最大回撤</h4><p style="font-size: 20px; font-weight: bold; color: red;">{metrics.get('max_drawdown', 0):.2%}</p>
        </div>
        <div style="border: 1px solid #ccc; padding: 15px; border-radius: 8px; flex: 1;">
            <h4>Alpha vs 純DCA</h4><p style="font-size: 20px; font-weight: bold; color: green;">{metrics.get('alpha_vs_pure_dca', 0):.2%}</p>
        </div>
        <div style="border: 1px solid #ccc; padding: 15px; border-radius: 8px; flex: 1;">
            <h4>加碼次數</h4><p style="font-size: 20px; font-weight: bold;">{metrics.get('addon_count', 0)} 次</p>
        </div>
    </div>
    """

    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>ETF 低檔加碼策略回測報告</title>
    </head>
    <body style="font-family: Arial, sans-serif; margin: 20px;">
        <h2>ETF 定期定額 + 低檔加碼策略回測報告</h2>
        {kpi_cards}
        <div>{chart_html}</div>
    </body>
    </html>
    """

    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(full_html)
```

- [ ] **步驟 4：運行測試驗證通過**

運行：`pytest tests/test_dca_addon.py::test_generate_html_report_output -v`
預期：PASS

---

### 任務 6：建立 CLI 腳本 `run_dca_backtest.py` 與 `run_dca_optimizer.py`

**檔案：**
- 建立：`run_dca_backtest.py`
- 建立：`run_dca_optimizer.py`
- 測試：`tests/test_dca_addon.py`

- [ ] **步驟 1：編寫失敗的測試 (`tests/test_dca_addon.py`)**

```python
import subprocess


def test_cli_runners_execution():
    res = subprocess.run(["python", "run_dca_backtest.py", "--help"], capture_output=True, text=True)
    assert res.returncode == 0
    assert "ETF 定期定額" in res.stdout
```

- [ ] **步驟 2：運行測試驗證失敗**

運行：`pytest tests/test_dca_addon.py::test_cli_runners_execution -v`
預期：FAIL，報錯 "FileNotFoundError: [Errno 2] No such file or directory: 'run_dca_backtest.py'"

- [ ] **步驟 3：編寫最少實現代碼**

創建 `run_dca_backtest.py`：
```python
import argparse
import sys
from src.dca_addon.config import AddOnRule, StrategyConfig
from src.dca_addon.engine import DCAAddOnBacktester
from src.dca_addon.metrics import evaluate_performance
from src.dca_addon.visualizer import generate_html_report
from src.storage import MarketDataStorage


def main():
    parser = argparse.ArgumentParser(description="ETF 定期定額 + 低檔加碼策略回測工具")
    parser.add_argument("--symbol", type=str, default="0050.TW", help="標的代码 (例如 0050.TW)")
    parser.add_argument("--amount", type=float, default=10000, help="每期定期定額金額")
    parser.add_argument("--budget", type=float, default=500000, help="額外加碼總預算")
    parser.add_argument("--output", type=str, default="dca_backtest_report.html", help="輸出 HTML 報告檔案名稱")

    args = parser.parse_args()

    storage = MarketDataStorage()
    df = storage.get_daily_data(args.symbol)

    if df.empty:
        print(f"錯誤：找不到標的 {args.symbol} 的歷史數據。")
        sys.exit(1)

    config = StrategyConfig(
        base_invest_amount=args.amount,
        rules=[
            AddOnRule(lookback_days=20, drawdown_threshold=0.06, multiplier=2.0),
            AddOnRule(lookback_days=20, drawdown_threshold=0.12, multiplier=3.0),
        ],
        cooldown_days=5,
        max_addons_per_month=2,
        total_extra_budget=args.budget
    )

    bt = DCAAddOnBacktester(df, config)
    equity, trades = bt.run()
    metrics = evaluate_performance(equity, trades, config)

    generate_html_report(df, equity, trades, metrics, args.output)
    print(f"回測完成！報告已儲存至：{args.output}")
    print(f"總報酬率: {metrics['total_return']:.2%}, 最大回撤: {metrics['max_drawdown']:.2%}, Alpha: {metrics['alpha_vs_pure_dca']:.2%}")


if __name__ == "__main__":
    main()
```

創建 `run_dca_optimizer.py`：
```python
import argparse
from src.dca_addon.optimizer import grid_search
from src.storage import MarketDataStorage


def main():
    parser = argparse.ArgumentParser(description="ETF 低檔加碼策略參數最佳化工具")
    parser.add_argument("--symbol", type=str, default="0050.TW", help="標的代码")
    args = parser.parse_args()

    storage = MarketDataStorage()
    df = storage.get_daily_data(args.symbol)

    if df.empty:
        print(f"錯誤：找不到標的 {args.symbol} 的數據。")
        return

    print("開始執行參數網格掃描...")
    param_grid = {
        "lookbacks": [10, 20, 60],
        "first_thresholds": [0.05, 0.06, 0.08],
        "second_thresholds": [0.10, 0.12, 0.15],
        "first_multipliers": [1.5, 2.0],
        "second_multipliers": [2.0, 3.0],
        "cooldowns": [0, 3, 5],
        "monthly_limits": [1, 2]
    }

    results_df = grid_search(df, param_grid)
    results_df = results_df.sort_values("total_return", ascending=False)
    results_df.to_csv("dca_optimization_results.csv", index=False, encoding="utf-8-sig")
    print(f"最佳化完成！前 5 名參數組合：\n", results_df.head())


if __name__ == "__main__":
    main()
```

- [ ] **步驟 4：運行測試驗證通過**

運行：`pytest tests/test_dca_addon.py::test_cli_runners_execution -v`
預期：PASS

---

### 任務 7：建立 Jupyter Notebook (`notebooks/DCA_AddOn_Strategy_Research.ipynb`)

**檔案：**
- 建立：`notebooks/DCA_AddOn_Strategy_Research.ipynb`

- [ ] **步驟 1：建立 Notebook JSON 檔結構**

創建 `notebooks/DCA_AddOn_Strategy_Research.ipynb` 檔案內容：
```json
{
 "cells": [
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "# ETF 定期定額 + 低檔加碼策略（左側交易）互動式研究"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "import sys\n",
    "sys.path.append('..')\n",
    "\n",
    "from src.storage import MarketDataStorage\n",
    "from src.dca_addon.config import StrategyConfig, AddOnRule\n",
    "from src.dca_addon.engine import DCAAddOnBacktester\n",
    "from src.dca_addon.metrics import evaluate_performance\n",
    "from src.dca_addon.visualizer import plot_dca_summary"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "storage = MarketDataStorage()\n",
    "df = storage.get_daily_data('0050.TW')\n",
    "\n",
    "config = StrategyConfig(\n",
    "    base_invest_amount=10000,\n",
    "    rules=[\n",
    "        AddOnRule(lookback_days=20, drawdown_threshold=0.06, multiplier=2.0),\n",
    "        AddOnRule(lookback_days=20, drawdown_threshold=0.12, multiplier=3.0)\n",
    "    ],\n",
    "    cooldown_days=5,\n",
    "    max_addons_per_month=2,\n",
    "    total_extra_budget=500000\n",
    ")\n",
    "\n",
    "bt = DCAAddOnBacktester(df, config)\n",
    "equity, trades = bt.run()\n",
    "metrics = evaluate_performance(equity, trades, config)\n",
    "print('績效指標:', metrics)"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "fig = plot_dca_summary(df, equity, trades)\n",
    "fig.show()"
   ]
  }
 ],
 "metadata": {
  "language_info": {
   "name": "python"
  }
 },
 "nbformat": 4,
 "nbformat_minor": 2
}
```

- [ ] **步驟 2：驗證 pytest 全面跑通**

運行：`pytest tests/test_dca_addon.py -v`
預期：ALL PASS

---

## 執行交接

計畫已完成並保存到 [docs/superpowers/plans/2026-07-24-dca-addon-system.md](file:///d:/MyProj/SuperTrend/docs/superpowers/plans/2026-07-24-dca-addon-system.md)。兩種執行方式：

**1. 子代理驅動（推薦）** - 必需子技能：使用 `superpowers:subagent-driven-development`，每個任務調度一個新的子代理，任務間進行審查，快速疊代。

**2. 內聯執行** - 必需子技能：使用 `superpowers:executing-plans`，在當前會話中批量執行並設有檢查點供審查。

**請告訴我您想選擇哪一種執行方式？**
