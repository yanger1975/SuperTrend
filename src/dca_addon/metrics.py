from typing import Dict, Any, Optional
import pandas as pd
import numpy as np
from src.dca_addon.config import StrategyConfig


def evaluate_performance(
    equity: pd.DataFrame,
    trades: pd.DataFrame,
    config: Optional[StrategyConfig] = None,
    risk_free_rate: float = 0.015
) -> Dict[str, Any]:
    """
    評估 DCA 加碼策略之績效指標。
    """
    required_cols = {"MarketValue", "TotalCost", "Return", "Close", "Date"}
    if equity.empty or not required_cols.issubset(equity.columns):
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
    cagr_ratio = (final_value / total_cost) if total_cost > 0 else 0.0
    cagr = (cagr_ratio ** (1.0 / years) - 1.0) if (years > 0 and cagr_ratio > 0) else 0.0
    result["cagr"] = round(cagr, 4)

    # 回撤計算 (Drawdown based on MarketValue Peak)
    peaks = equity["MarketValue"].cummax()
    drawdowns = np.where(peaks > 0, equity["MarketValue"] / peaks - 1.0, 0.0)
    max_dd = float(np.min(drawdowns)) if len(drawdowns) > 0 else 0.0
    result["max_drawdown"] = round(max_dd, 4)

    # Sharpe & Calmar Ratio
    daily_returns = equity["Close"].pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    std_dev = float(daily_returns.std() * np.sqrt(252)) if len(daily_returns) > 1 and daily_returns.std() > 0 else 0.0
    sharpe = (cagr - risk_free_rate) / std_dev if std_dev > 0 else 0.0
    calmar = cagr / abs(max_dd) if max_dd < 0 else 0.0
    result["sharpe_ratio"] = round(sharpe, 2)
    result["calmar_ratio"] = round(calmar, 2)

    # 交易統計
    addon_trades = trades[trades["Type"] == "addon"] if not trades.empty and "Type" in trades.columns else pd.DataFrame()
    regular_trades = trades[trades["Type"] == "regular"] if not trades.empty and "Type" in trades.columns else pd.DataFrame()

    result["regular_count"] = len(regular_trades)
    result["addon_count"] = len(addon_trades)
    total_addon_amount = float(addon_trades["Amount"].sum()) if not addon_trades.empty and "Amount" in addon_trades.columns else 0.0
    result["total_addon_amount"] = round(total_addon_amount, 2)

    # 左側專屬指標 (使用 getattr 安全讀取屬性)
    extra_budget = getattr(config, "total_extra_budget", 0) if config else 0
    if extra_budget and extra_budget > 0:
        utilization = total_addon_amount / extra_budget
        result["extra_budget_utilization_rate"] = round(utilization, 4)
    else:
        result["extra_budget_utilization_rate"] = 0.0

    # 計算純定期定額比較基準 (Pure DCA Benchmark)
    pure_dca_units = float(regular_trades["Units"].sum()) if not regular_trades.empty and "Units" in regular_trades.columns else 0.0
    pure_dca_cost = float(regular_trades["Amount"].sum()) if not regular_trades.empty and "Amount" in regular_trades.columns else 0.0
    last_price = float(equity["Close"].iloc[-1])
    pure_dca_value = pure_dca_units * last_price
    pure_dca_return = (pure_dca_value / pure_dca_cost - 1.0) if pure_dca_cost > 0 else 0.0

    result["pure_dca_return"] = round(pure_dca_return, 4)
    result["alpha_vs_pure_dca"] = round(total_return - pure_dca_return, 4)

    return result
