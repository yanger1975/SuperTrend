import pandas as pd
from typing import Tuple, List, Dict, Any
from src.backtest_engine import BacktestEngine, Trade
from src.risk_manager import RiskManager
from src.supertrend_ai.indicator import supertrend_ai

def run_supertrend_ai_backtest(df: pd.DataFrame, 
                              length: int = 10,
                              min_mult: float = 1.0,
                              max_mult: float = 5.0,
                              step: float = 0.5,
                              perf_alpha: float = 10.0,
                              from_cluster: str = 'Best',
                              update_freq: int = 1,
                              long_only: bool = True,
                              stop_loss_pct: float = 0.0,
                              take_profit_pct: float = 0.0,
                              commission_bps: float = 0.0,
                              slippage_bps: float = 0.0,
                              show_progress: bool = False,
                              asset_type: str = "stock") -> Tuple[List[Trade], pd.Series, pd.Series, pd.DataFrame, Dict[str, Any]]:
    """
    執行 SuperTrend AI 策略回測，返回交易紀錄、資金曲線、基準曲線、加上指標的 DataFrame 與績效指標。
    """
    if length <= 0:
        raise ValueError("length must be > 0")
    if min_mult >= max_mult:
        raise ValueError("min_mult must be < max_mult")
    if step <= 0:
        raise ValueError("step must be > 0")
    if perf_alpha <= 0:
        raise ValueError("perf_alpha must be > 0")
    if update_freq <= 0:
        raise ValueError("update_freq must be > 0")
    for pct in [stop_loss_pct, take_profit_pct, commission_bps, slippage_bps]:
        if pct < 0:
            raise ValueError("Percentage/bps parameters must be >= 0")

    if df.empty:
        raise ValueError("Input DataFrame is empty")

    # 1. 產生 SuperTrend AI 指標
    df_ind = supertrend_ai(df.copy(), length, min_mult, max_mult, step, perf_alpha, from_cluster, update_freq=update_freq, show_progress=show_progress)
    
    if df_ind.empty:
        raise ValueError("Indicator computation returned empty DataFrame")

    # 2. 轉換欄位供回測引擎使用 (Trend=1 為多頭, -1 為空頭)
    df_ind['Trend'] = df_ind['SuperTrend_AI_Direction'].replace({0: -1})
    
    # 強制設定 MA_Filter 為 True (本策略核心為動態聚類，預設不依賴外部 MA 過濾，若需擴充可在此加入)
    df_ind['MA_Filter'] = True
    df_ind['ADX_Filter'] = True
    df_ind['RSI_Filter'] = True
    
    # 3. 執行回測
    engine = BacktestEngine(df_ind)
    valid_asset_types = {"stock", "fund"}
    asset_type_normalized = asset_type.lower() if asset_type else "stock"
    if asset_type_normalized not in valid_asset_types:
        raise ValueError(f"Invalid asset_type: '{asset_type}'. Expected one of: {sorted(valid_asset_types)}")
    execution_mode = "next_close" if asset_type_normalized == "fund" else "next_open"
    trades, equity, benchmark = engine.run(
        long_only=long_only,
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
        commission_bps=commission_bps,
        slippage_bps=slippage_bps,
        execution_mode=execution_mode
    )
    
    # 4. 計算績效指標
    rm = RiskManager(trades, equity)
    metrics = rm.calculate_metrics()
    
    return trades, equity, benchmark, df_ind, metrics

def calculate_custom_score(metrics: Dict[str, Any]) -> float:
    """
    評估穩健性的綜合評分公式 (與原系統一致)：
    Score = 0.35 * Sharpe + 0.25 * Calmar + 0.20 * PF - 0.20 * |MaxDD|
    """
    if not metrics:
        return 0.0
    sharpe = metrics.get("Sharpe Ratio", 0.0)
    calmar = metrics.get("Calmar Ratio", 0.0)
    pf = metrics.get("Profit Factor", 0.0)
    max_dd = abs(metrics.get("Max Drawdown", 0.0))
    return 0.35 * sharpe + 0.25 * calmar + 0.20 * pf - 0.20 * max_dd
