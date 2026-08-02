import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional

@dataclass
class Trade:
    entry_date: pd.Timestamp
    entry_price: float
    exit_date: pd.Timestamp = None
    exit_price: float = None
    direction: str = "Long"
    pnl_pct: float = 0.0
    exit_reason: str = "Signal"
    is_closed: bool = False

class BacktestEngine:
    def __init__(self, df: pd.DataFrame):
        self.df = df

    def run(self,
            long_only: bool = True,
            stop_loss_pct: float = 0.0,
            take_profit_pct: float = 0.0,
            commission_bps: float = 0.0,
            slippage_bps: float = 0.0,
            position_sizing_mode: str = "fixed_fraction",
            risk_pct: float = 0.01
            ) -> Tuple[List[Trade], pd.Series, pd.Series]:

        trades: List[Trade] = []
        equity = pd.Series(0.0, index=self.df.index)
        equity.iloc[0] = 100000.0

        initial_close = self.df["Close"].iloc[0]
        benchmark_shares = 100000.0 / initial_close
        benchmark_equity = self.df["Close"] * benchmark_shares

        cash = 100000.0
        shares = 0.0
        position = 0
        active_trade: Optional[Trade] = None

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

            # 1. 停損停利檢測
            if position != 0 and active_trade:
                if position == 1:
                    sl_price = active_trade.entry_price * (1.0 - stop_loss_pct)
                    tp_price = active_trade.entry_price * (1.0 + take_profit_pct)
                    
                    if stop_loss_pct > 0.0 and current_open <= sl_price:
                        actual_exit_price = current_open * (1.0 - slip_factor)
                        cash += shares * actual_exit_price * (1.0 - comm_factor)
                        active_trade.exit_price, active_trade.exit_date, active_trade.exit_reason, active_trade.is_closed = actual_exit_price, current_date, "StopLoss", True
                        active_trade.pnl_pct = (actual_exit_price - active_trade.entry_price) / active_trade.entry_price
                        trades.append(active_trade)
                        shares, position, active_trade = 0.0, 0, None
                        equity.iloc[i] = cash
                        continue

                    if take_profit_pct > 0.0 and current_open >= tp_price:
                        actual_exit_price = current_open * (1.0 - slip_factor)
                        cash += shares * actual_exit_price * (1.0 - comm_factor)
                        active_trade.exit_price, active_trade.exit_date, active_trade.exit_reason, active_trade.is_closed = actual_exit_price, current_date, "TakeProfit", True
                        active_trade.pnl_pct = (actual_exit_price - active_trade.entry_price) / active_trade.entry_price
                        trades.append(active_trade)
                        shares, position, active_trade = 0.0, 0, None
                        equity.iloc[i] = cash
                        continue

                    if stop_loss_pct > 0.0 and current_low <= sl_price and take_profit_pct > 0.0 and current_high >= tp_price:
                        actual_exit_price = sl_price * (1.0 - slip_factor)
                        cash += shares * actual_exit_price * (1.0 - comm_factor)
                        active_trade.exit_price, active_trade.exit_date, active_trade.exit_reason, active_trade.is_closed = actual_exit_price, current_date, "StopLoss", True
                        active_trade.pnl_pct = (actual_exit_price - active_trade.entry_price) / active_trade.entry_price
                        trades.append(active_trade)
                        shares, position, active_trade = 0.0, 0, None
                        equity.iloc[i] = cash
                        continue

                    if stop_loss_pct > 0.0 and current_low <= sl_price:
                        actual_exit_price = sl_price * (1.0 - slip_factor)
                        cash += shares * actual_exit_price * (1.0 - comm_factor)
                        active_trade.exit_price, active_trade.exit_date, active_trade.exit_reason, active_trade.is_closed = actual_exit_price, current_date, "StopLoss", True
                        active_trade.pnl_pct = (actual_exit_price - active_trade.entry_price) / active_trade.entry_price
                        trades.append(active_trade)
                        shares, position, active_trade = 0.0, 0, None
                        equity.iloc[i] = cash
                        continue

                    if take_profit_pct > 0.0 and current_high >= tp_price:
                        actual_exit_price = tp_price * (1.0 - slip_factor)
                        cash += shares * actual_exit_price * (1.0 - comm_factor)
                        active_trade.exit_price, active_trade.exit_date, active_trade.exit_reason, active_trade.is_closed = actual_exit_price, current_date, "TakeProfit", True
                        active_trade.pnl_pct = (actual_exit_price - active_trade.entry_price) / active_trade.entry_price
                        trades.append(active_trade)
                        shares, position, active_trade = 0.0, 0, None
                        equity.iloc[i] = cash
                        continue

                elif position == -1:
                    sl_price = active_trade.entry_price * (1.0 + stop_loss_pct)
                    tp_price = active_trade.entry_price * (1.0 - take_profit_pct)
                    
                    if stop_loss_pct > 0.0 and current_open >= sl_price:
                        actual_exit_price = current_open * (1.0 + slip_factor)
                        cash += shares * actual_exit_price * (1.0 + comm_factor)
                        active_trade.exit_price, active_trade.exit_date, active_trade.exit_reason, active_trade.is_closed = actual_exit_price, current_date, "StopLoss", True
                        active_trade.pnl_pct = (active_trade.entry_price - actual_exit_price) / active_trade.entry_price
                        trades.append(active_trade)
                        shares, position, active_trade = 0.0, 0, None
                        equity.iloc[i] = cash
                        continue

                    if take_profit_pct > 0.0 and current_open <= tp_price:
                        actual_exit_price = current_open * (1.0 + slip_factor)
                        cash += shares * actual_exit_price * (1.0 + comm_factor)
                        active_trade.exit_price, active_trade.exit_date, active_trade.exit_reason, active_trade.is_closed = actual_exit_price, current_date, "TakeProfit", True
                        active_trade.pnl_pct = (active_trade.entry_price - actual_exit_price) / active_trade.entry_price
                        trades.append(active_trade)
                        shares, position, active_trade = 0.0, 0, None
                        equity.iloc[i] = cash
                        continue

                    if stop_loss_pct > 0.0 and current_high >= sl_price and take_profit_pct > 0.0 and current_low <= tp_price:
                        actual_exit_price = sl_price * (1.0 + slip_factor)
                        cash += shares * actual_exit_price * (1.0 + comm_factor)
                        active_trade.exit_price, active_trade.exit_date, active_trade.exit_reason, active_trade.is_closed = actual_exit_price, current_date, "StopLoss", True
                        active_trade.pnl_pct = (active_trade.entry_price - actual_exit_price) / active_trade.entry_price
                        trades.append(active_trade)
                        shares, position, active_trade = 0.0, 0, None
                        equity.iloc[i] = cash
                        continue

                    if stop_loss_pct > 0.0 and current_high >= sl_price:
                        actual_exit_price = sl_price * (1.0 + slip_factor)
                        cash += shares * actual_exit_price * (1.0 + comm_factor)
                        active_trade.exit_price, active_trade.exit_date, active_trade.exit_reason, active_trade.is_closed = actual_exit_price, current_date, "StopLoss", True
                        active_trade.pnl_pct = (active_trade.entry_price - actual_exit_price) / active_trade.entry_price
                        trades.append(active_trade)
                        shares, position, active_trade = 0.0, 0, None
                        equity.iloc[i] = cash
                        continue

                    if take_profit_pct > 0.0 and current_low <= tp_price:
                        actual_exit_price = tp_price * (1.0 + slip_factor)
                        cash += shares * actual_exit_price * (1.0 + comm_factor)
                        active_trade.exit_price, active_trade.exit_date, active_trade.exit_reason, active_trade.is_closed = actual_exit_price, current_date, "TakeProfit", True
                        active_trade.pnl_pct = (active_trade.entry_price - actual_exit_price) / active_trade.entry_price
                        trades.append(active_trade)
                        shares, position, active_trade = 0.0, 0, None
                        equity.iloc[i] = cash
                        continue

            # 2. 出場與反手進場信號處理
            ma_ok = self.df["MA_Filter"].iloc[i] if "MA_Filter" in self.df.columns else True
            adx_ok = self.df["ADX_Filter"].iloc[i] if "ADX_Filter" in self.df.columns else True
            rsi_ok = self.df["RSI_Filter"].iloc[i] if "RSI_Filter" in self.df.columns else True

            ma_filter_active = ("MA_Filter" in self.df.columns and not self.df["MA_Filter"].all())

            # 判斷信號
            if ma_filter_active:
                long_signal = trend == 1 and ma_ok and adx_ok and rsi_ok
                short_signal = trend == -1 and ma_ok and adx_ok and rsi_ok
            else:
                long_signal = trend == 1 and prev_trend == -1 and ma_ok and adx_ok and rsi_ok
                short_signal = trend == -1 and prev_trend == 1 and ma_ok and adx_ok and rsi_ok

            if not long_only:
                # 短單出場
                if position == -1 and trend == 1:
                    actual_exit_price = current_close * (1.0 + slip_factor)
                    cash += shares * actual_exit_price * (1.0 + comm_factor)
                    active_trade.exit_price, active_trade.exit_date, active_trade.exit_reason, active_trade.is_closed = actual_exit_price, current_date, "Signal", True
                    active_trade.pnl_pct = (active_trade.entry_price - actual_exit_price) / active_trade.entry_price
                    trades.append(active_trade)
                    shares, position, active_trade = 0.0, 0, None

            # 長單出場
            if position == 1 and trend == -1:
                actual_exit_price = current_close * (1.0 - slip_factor)
                cash += shares * actual_exit_price * (1.0 - comm_factor)
                active_trade.exit_price, active_trade.exit_date, active_trade.exit_reason, active_trade.is_closed = actual_exit_price, current_date, "Signal", True
                active_trade.pnl_pct = (actual_exit_price - active_trade.entry_price) / active_trade.entry_price
                trades.append(active_trade)
                shares, position, active_trade = 0.0, 0, None

            # 檢查進場
            if position == 0:
                if long_signal:
                    position = 1
                    if position_sizing_mode == "fixed_risk" and stop_loss_pct > 0.0:
                        risk_amount = cash * risk_pct
                        loss_per_share = current_close * stop_loss_pct
                        shares_to_buy = risk_amount / (loss_per_share + 1e-10)
                        max_shares = cash / (current_close * (1.0 + slip_factor) * (1.0 + comm_factor))
                        shares = min(shares_to_buy, max_shares)
                    else:
                        shares = cash / (current_close * (1.0 + slip_factor) * (1.0 + comm_factor))
                    
                    actual_entry_price = current_close * (1.0 + slip_factor)
                    cash -= shares * actual_entry_price * (1.0 + comm_factor)
                    active_trade = Trade(entry_date=current_date, entry_price=actual_entry_price, direction="Long")
                
                elif short_signal and not long_only:
                    position = -1
                    if position_sizing_mode == "fixed_risk" and stop_loss_pct > 0.0:
                        risk_amount = cash * risk_pct
                        loss_per_share = current_close * stop_loss_pct
                        shares_to_short = risk_amount / (loss_per_share + 1e-10)
                        max_shares = cash / (current_close * (1.0 - slip_factor) * (1.0 - comm_factor))
                        shares_abs = min(shares_to_short, max_shares)
                    else:
                        shares_abs = cash / (current_close * (1.0 - slip_factor) * (1.0 - comm_factor))
                    
                    shares = -shares_abs
                    actual_entry_price = current_close * (1.0 - slip_factor)
                    cash -= shares * actual_entry_price * (1.0 - comm_factor)
                    active_trade = Trade(entry_date=current_date, entry_price=actual_entry_price, direction="Short")

            # 3. 盯市權益更新 (Mark-to-market)
            equity.iloc[i] = cash + (shares * current_close)

        # 4. 回測期末強制平倉處理
        if position != 0 and active_trade:
            last_date = self.df.index[-1]
            last_close = self.df["Close"].iloc[-1]
            if position == 1:
                actual_exit_price = last_close * (1.0 - slip_factor)
                cash += shares * actual_exit_price * (1.0 - comm_factor)
                active_trade.pnl_pct = (actual_exit_price - active_trade.entry_price) / active_trade.entry_price
            else:
                actual_exit_price = last_close * (1.0 + slip_factor)
                cash += shares * actual_exit_price * (1.0 + comm_factor)
                active_trade.pnl_pct = (active_trade.entry_price - actual_exit_price) / active_trade.entry_price

            active_trade.exit_price = actual_exit_price
            active_trade.exit_date = last_date
            active_trade.exit_reason = "End"
            active_trade.is_closed = True

            trades.append(active_trade)
            shares = 0.0
            position = 0
            active_trade = None
            equity.iloc[-1] = cash

        return trades, equity, benchmark_equity
