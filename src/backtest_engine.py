import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Tuple

@dataclass
class Trade:
    entry_date: pd.Timestamp
    entry_price: float  # 已包含進場滑價與手續費後的實際成本價
    exit_date: pd.Timestamp = None
    exit_price: float = None  # 已扣除出場滑價與手續費後的實際結算價
    direction: str = "Long"  # "Long" or "Short"
    pnl_pct: float = 0.0
    exit_reason: str = "Signal"  # "Signal", "StopLoss", "TakeProfit", "End"
    is_closed: bool = False

class BacktestEngine:
    """
    K 線逐根迭代回測引擎
    採用 mark-to-market (逐日按收盤價盯市) 的現金與股數模型，精準計算每日權益變化。
    """
    def __init__(self, df: pd.DataFrame):
        self.df = df

    def run(self,
            long_only: bool = True,
            stop_loss_pct: float = 0.0,
            take_profit_pct: float = 0.0,
            commission_bps: float = 0.0,  # 單邊交易手續費 (基點，例如 10 bps = 0.0010)
            slippage_bps: float = 0.0,    # 單邊交易滑價 (基點，例如 5 bps = 0.0005)
            position_sizing_mode: str = "fixed_fraction", # "fixed_fraction" 或 "fixed_risk"
            risk_pct: float = 0.01        # 單筆交易承受風險比 (用於 fixed_risk，預設 1% 資金)
            ) -> Tuple[List[Trade], pd.Series, pd.Series]:

        trades: List[Trade] = []

        # 初始化權益曲線與基準線
        equity = pd.Series(0.0, index=self.df.index)
        equity.iloc[0] = 100000.0

        # 基準線 (Buy & Hold)
        initial_close = self.df["Close"].iloc[0]
        benchmark_shares = 100000.0 / initial_close
        benchmark_equity = self.df["Close"] * benchmark_shares

        # 交易帳戶狀態
        cash = 100000.0
        shares = 0.0
        position = 0  # 0: 空倉, 1: 多頭, -1: 空頭 (本系統以 ETF 長期多頭回測為主)
        active_trade: Optional[Trade] = None

        # 費率因子
        comm_factor = commission_bps / 10000.0
        slip_factor = slippage_bps / 10000.0

        for i in range(1, len(self.df)):
            current_date = self.df.index[i]
            current_open = self.df["Open"].iloc[i]
            current_high = self.df["High"].iloc[i]
            current_low = self.df["Low"].iloc[i]
            current_close = self.df["Close"].iloc[i]

            trend = self.df["Trend"].iloc[i]
            prev_trend = self.df["Trend"].iloc[i-1]

            # 1. 持倉狀態下的 Stop-Loss / Take-Profit 檢測
            if position == 1 and active_trade:
                sl_price = active_trade.entry_price * (1.0 - stop_loss_pct)
                tp_price = active_trade.entry_price * (1.0 + take_profit_pct)

                # A. 檢查開盤跳空跌破或突破
                if stop_loss_pct > 0.0 and current_open <= sl_price:
                    # 跳空開低，直接以開盤價止損
                    actual_exit_price = current_open * (1.0 - slip_factor)
                    cash += shares * actual_exit_price * (1.0 - comm_factor)

                    active_trade.exit_price = actual_exit_price
                    active_trade.exit_date = current_date
                    active_trade.pnl_pct = (actual_exit_price - active_trade.entry_price) / active_trade.entry_price
                    active_trade.exit_reason = "StopLoss"
                    active_trade.is_closed = True

                    trades.append(active_trade)
                    shares = 0.0
                    position = 0
                    active_trade = None
                    equity.iloc[i] = cash
                    continue

                if take_profit_pct > 0.0 and current_open >= tp_price:
                    # 跳空開高，直接以開盤價止利
                    actual_exit_price = current_open * (1.0 - slip_factor)
                    cash += shares * actual_exit_price * (1.0 - comm_factor)

                    active_trade.exit_price = actual_exit_price
                    active_trade.exit_date = current_date
                    active_trade.pnl_pct = (actual_exit_price - active_trade.entry_price) / active_trade.entry_price
                    active_trade.exit_reason = "TakeProfit"
                    active_trade.is_closed = True

                    trades.append(active_trade)
                    shares = 0.0
                    position = 0
                    active_trade = None
                    equity.iloc[i] = cash
                    continue

                # B. 檢查日內同時觸發 (Daily 週期下保守假設止損 SL 優先發生)
                if stop_loss_pct > 0.0 and current_low <= sl_price and take_profit_pct > 0.0 and current_high >= tp_price:
                    actual_exit_price = sl_price * (1.0 - slip_factor)
                    cash += shares * actual_exit_price * (1.0 - comm_factor)

                    active_trade.exit_price = actual_exit_price
                    active_trade.exit_date = current_date
                    active_trade.pnl_pct = (actual_exit_price - active_trade.entry_price) / active_trade.entry_price
                    active_trade.exit_reason = "StopLoss"
                    active_trade.is_closed = True

                    trades.append(active_trade)
                    shares = 0.0
                    position = 0
                    active_trade = None
                    equity.iloc[i] = cash
                    continue

                # C. 獨立檢查止損或止利
                if stop_loss_pct > 0.0 and current_low <= sl_price:
                    actual_exit_price = sl_price * (1.0 - slip_factor)
                    cash += shares * actual_exit_price * (1.0 - comm_factor)

                    active_trade.exit_price = actual_exit_price
                    active_trade.exit_date = current_date
                    active_trade.pnl_pct = (actual_exit_price - active_trade.entry_price) / active_trade.entry_price
                    active_trade.exit_reason = "StopLoss"
                    active_trade.is_closed = True

                    trades.append(active_trade)
                    shares = 0.0
                    position = 0
                    active_trade = None
                    equity.iloc[i] = cash
                    continue

                if take_profit_pct > 0.0 and current_high >= tp_price:
                    actual_exit_price = tp_price * (1.0 - slip_factor)
                    cash += shares * actual_exit_price * (1.0 - comm_factor)

                    active_trade.exit_price = actual_exit_price
                    active_trade.exit_date = current_date
                    active_trade.pnl_pct = (actual_exit_price - active_trade.entry_price) / active_trade.entry_price
                    active_trade.exit_reason = "TakeProfit"
                    active_trade.is_closed = True

                    trades.append(active_trade)
                    shares = 0.0
                    position = 0
                    active_trade = None
                    equity.iloc[i] = cash
                    continue

            # 2. 進出場信號處理
            if position == 0:
                # 檢索過濾器狀態
                ma_ok = self.df["MA_Filter"].iloc[i] if "MA_Filter" in self.df.columns else True
                adx_ok = self.df["ADX_Filter"].iloc[i] if "ADX_Filter" in self.df.columns else True
                rsi_ok = self.df["RSI_Filter"].iloc[i] if "RSI_Filter" in self.df.columns else True

                trend = self.df["Trend"].iloc[i]
                prev_trend = self.df["Trend"].iloc[i-1]

                # --- 雙模式進場邏輯 ---
                # 判斷 MA_Filter 是否實際啟用 (非全 True)
                ma_filter_active = (
                    "MA_Filter" in self.df.columns
                    and not self.df["MA_Filter"].all()  # 有 False 值表示實際在過濾
                )

                if ma_filter_active:
                    # 模式 2：有 HMA 過濾 → 趨勢跟隨模式
                    # 只要目前多頭趨勢且所有過濾器通過即可進場，不需 Crossover
                    entry_signal = trend == 1 and ma_ok and adx_ok and rsi_ok
                else:
                    # 模式 1：無 HMA 過濾 → 反轉捕捉模式
                    # 嚴格要求 SuperTrend Crossover (由空轉多)
                    entry_signal = trend == 1 and prev_trend == -1 and ma_ok and adx_ok and rsi_ok

                if entry_signal:
                    # 買入進場
                    position = 1
                    current_equity = cash

                    # 計算部位 sizing
                    if position_sizing_mode == "fixed_risk" and stop_loss_pct > 0.0:
                        risk_amount = current_equity * risk_pct
                        loss_per_share = current_close * stop_loss_pct
                        shares_to_buy = risk_amount / (loss_per_share + 1e-10)

                        # 限制最多滿倉 (無槓桿)
                        max_shares = current_equity / (current_close * (1.0 + slip_factor) * (1.0 + comm_factor))
                        shares = min(shares_to_buy, max_shares)
                    else:
                        # 預設滿倉
                        shares = current_equity / (current_close * (1.0 + slip_factor) * (1.0 + comm_factor))

                    actual_entry_price = current_close * (1.0 + slip_factor)
                    # 扣除進場總金額 (含手續費)
                    cash -= shares * actual_entry_price * (1.0 + comm_factor)

                    active_trade = Trade(
                        entry_date=current_date,
                        entry_price=actual_entry_price,
                        direction="Long"
                    )
            else:
                # 訊號反轉出場
                if position == 1 and trend == -1:
                    actual_exit_price = current_close * (1.0 - slip_factor)
                    cash += shares * actual_exit_price * (1.0 - comm_factor)

                    active_trade.exit_price = actual_exit_price
                    active_trade.exit_date = current_date
                    active_trade.pnl_pct = (actual_exit_price - active_trade.entry_price) / active_trade.entry_price
                    active_trade.exit_reason = "Signal"
                    active_trade.is_closed = True

                    trades.append(active_trade)
                    shares = 0.0
                    position = 0
                    active_trade = None

            # 3. 盯市權益更新 (Mark-to-market)
            equity.iloc[i] = cash + (shares * current_close)

        # 4. 回測期末強制平倉處理
        if position != 0 and active_trade:
            last_date = self.df.index[-1]
            last_close = self.df["Close"].iloc[-1]
            actual_exit_price = last_close * (1.0 - slip_factor)

            cash += shares * actual_exit_price * (1.0 - comm_factor)
            active_trade.exit_price = actual_exit_price
            active_trade.exit_date = last_date
            active_trade.pnl_pct = (actual_exit_price - active_trade.entry_price) / active_trade.entry_price
            active_trade.exit_reason = "End"
            active_trade.is_closed = True

            trades.append(active_trade)
            shares = 0.0
            position = 0
            active_trade = None
            equity.iloc[-1] = cash

        return trades, equity, benchmark_equity
