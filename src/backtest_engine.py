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
            risk_pct: float = 0.01,
            execution_mode: str = "current_close"
            ) -> Tuple[List[Trade], pd.Series, pd.Series]:
        """
        execution_mode:
          - "current_close": 舊版行為，訊號當日收盤成交
          - "next_open": 股票預設，訊號隔日開盤成交
          - "next_close": 基金預設，訊號隔日收盤(淨值)成交
        """
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

        def evaluate_signals(idx: int) -> Tuple[bool, bool, bool, bool]:
            if idx < 1:
                return False, False, False, False
            trend = self.df["Trend"].iloc[idx]
            prev_trend = self.df["Trend"].iloc[idx-1]
            ma_ok = self.df["MA_Filter"].iloc[idx] if "MA_Filter" in self.df.columns else True
            adx_ok = self.df["ADX_Filter"].iloc[idx] if "ADX_Filter" in self.df.columns else True
            rsi_ok = self.df["RSI_Filter"].iloc[idx] if "RSI_Filter" in self.df.columns else True

            ma_filter_active = ("MA_Filter" in self.df.columns and not self.df["MA_Filter"].all())

            if ma_filter_active:
                l_sig = (trend == 1) and ma_ok and adx_ok and rsi_ok
                s_sig = (trend == -1) and ma_ok and adx_ok and rsi_ok
            else:
                l_sig = (trend == 1) and (prev_trend == -1) and ma_ok and adx_ok and rsi_ok
                s_sig = (trend == -1) and (prev_trend == 1) and ma_ok and adx_ok and rsi_ok

            exit_l_sig = (trend == -1)
            exit_s_sig = (trend == 1)
            return l_sig, s_sig, exit_l_sig, exit_s_sig

        for i in range(1, len(self.df)):
            current_date = self.df.index[i]
            current_open = self.df["Open"].iloc[i]
            current_high = self.df["High"].iloc[i]
            current_low = self.df["Low"].iloc[i]
            current_close = self.df["Close"].iloc[i]

            # 決定訊號來源 index
            sig_i = i - 1 if execution_mode in ["next_open", "next_close"] else i
            long_sig, short_sig, exit_long_sig, exit_short_sig = evaluate_signals(sig_i)

            # 定義執行動作函式
            def execute_exits(exec_price: float):
                nonlocal cash, shares, position, active_trade
                if position == 1 and exit_long_sig:
                    actual_exit = exec_price * (1.0 - slip_factor)
                    cash += shares * actual_exit * (1.0 - comm_factor)
                    active_trade.exit_price, active_trade.exit_date = actual_exit, current_date
                    active_trade.exit_reason, active_trade.is_closed = "Signal", True
                    active_trade.pnl_pct = (actual_exit - active_trade.entry_price) / active_trade.entry_price
                    trades.append(active_trade)
                    shares, position, active_trade = 0.0, 0, None

                elif position == -1 and exit_short_sig and not long_only:
                    actual_exit = exec_price * (1.0 + slip_factor)
                    cash += shares * actual_exit * (1.0 + comm_factor)
                    active_trade.exit_price, active_trade.exit_date = actual_exit, current_date
                    active_trade.exit_reason, active_trade.is_closed = "Signal", True
                    active_trade.pnl_pct = (active_trade.entry_price - actual_exit) / active_trade.entry_price
                    trades.append(active_trade)
                    shares, position, active_trade = 0.0, 0, None

            def execute_entries(exec_price: float):
                nonlocal cash, shares, position, active_trade
                if position == 0:
                    if long_sig:
                        position = 1
                        if position_sizing_mode == "fixed_risk" and stop_loss_pct > 0.0:
                            risk_amount = cash * risk_pct
                            loss_per_share = exec_price * stop_loss_pct
                            shares_to_buy = risk_amount / (loss_per_share + 1e-10)
                            max_shares = cash / (exec_price * (1.0 + slip_factor) * (1.0 + comm_factor))
                            shares = min(shares_to_buy, max_shares)
                        else:
                            shares = cash / (exec_price * (1.0 + slip_factor) * (1.0 + comm_factor))
                        actual_entry = exec_price * (1.0 + slip_factor)
                        cash -= shares * actual_entry * (1.0 + comm_factor)
                        active_trade = Trade(entry_date=current_date, entry_price=actual_entry, direction="Long")

                    elif short_sig and not long_only:
                        position = -1
                        if position_sizing_mode == "fixed_risk" and stop_loss_pct > 0.0:
                            risk_amount = cash * risk_pct
                            loss_per_share = exec_price * stop_loss_pct
                            shares_to_short = risk_amount / (loss_per_share + 1e-10)
                            max_shares = cash / (exec_price * (1.0 - slip_factor) * (1.0 - comm_factor))
                            shares_abs = min(shares_to_short, max_shares)
                        else:
                            shares_abs = cash / (exec_price * (1.0 - slip_factor) * (1.0 - comm_factor))
                        shares = -shares_abs
                        actual_entry = exec_price * (1.0 - slip_factor)
                        cash -= shares * actual_entry * (1.0 - comm_factor)
                        active_trade = Trade(entry_date=current_date, entry_price=actual_entry, direction="Short")

            # ======= Phase 1: OPEN =======
            if execution_mode == "next_open":
                execute_exits(current_open)
                execute_entries(current_open)

            # ======= Phase 2: INTRADAY (SL/TP) =======
            if position != 0 and active_trade:
                sl_triggered = False
                tp_triggered = False
                exit_p = 0.0
                reason = ""
                if position == 1:
                    sl_price = active_trade.entry_price * (1.0 - stop_loss_pct)
                    tp_price = active_trade.entry_price * (1.0 + take_profit_pct)
                    if stop_loss_pct > 0.0 and current_low <= sl_price:
                        if current_open <= sl_price:
                            exit_p = current_open * (1.0 - slip_factor)
                        else:
                            exit_p = sl_price * (1.0 - slip_factor)
                        sl_triggered = True
                        reason = "StopLoss"
                    elif take_profit_pct > 0.0 and current_high >= tp_price:
                        if current_open >= tp_price:
                            exit_p = current_open * (1.0 - slip_factor)
                        else:
                            exit_p = tp_price * (1.0 - slip_factor)
                        tp_triggered = True
                        reason = "TakeProfit"
                
                elif position == -1:
                    sl_price = active_trade.entry_price * (1.0 + stop_loss_pct)
                    tp_price = active_trade.entry_price * (1.0 - take_profit_pct)
                    if stop_loss_pct > 0.0 and current_high >= sl_price:
                        if current_open >= sl_price:
                            exit_p = current_open * (1.0 + slip_factor)
                        else:
                            exit_p = sl_price * (1.0 + slip_factor)
                        sl_triggered = True
                        reason = "StopLoss"
                    elif take_profit_pct > 0.0 and current_low <= tp_price:
                        if current_open <= tp_price:
                            exit_p = current_open * (1.0 + slip_factor)
                        else:
                            exit_p = tp_price * (1.0 + slip_factor)
                        tp_triggered = True
                        reason = "TakeProfit"

                if sl_triggered or tp_triggered:
                    if position == 1:
                        cash += shares * exit_p * (1.0 - comm_factor)
                        active_trade.pnl_pct = (exit_p - active_trade.entry_price) / active_trade.entry_price
                    else:
                        cash += shares * exit_p * (1.0 + comm_factor)
                        active_trade.pnl_pct = (active_trade.entry_price - exit_p) / active_trade.entry_price

                    active_trade.exit_price = exit_p
                    active_trade.exit_date = current_date
                    active_trade.exit_reason = reason
                    active_trade.is_closed = True
                    trades.append(active_trade)
                    shares, position, active_trade = 0.0, 0, None

            # ======= Phase 3: CLOSE =======
            if execution_mode in ["next_close", "current_close"]:
                execute_exits(current_close)
                execute_entries(current_close)

            # Mark-to-market
            equity.iloc[i] = cash + (shares * current_close)

        # 4. 回測期末強制平倉處理
        if position != 0 and active_trade:
            last_date = self.df.index[-1]
            last_close = self.df["Close"].iloc[-1]
            if position == 1:
                actual_exit = last_close * (1.0 - slip_factor)
                cash += shares * actual_exit * (1.0 - comm_factor)
                active_trade.pnl_pct = (actual_exit - active_trade.entry_price) / active_trade.entry_price
            else:
                actual_exit = last_close * (1.0 + slip_factor)
                cash += shares * actual_exit * (1.0 + comm_factor)
                active_trade.pnl_pct = (active_trade.entry_price - actual_exit) / active_trade.entry_price

            active_trade.exit_price = actual_exit
            active_trade.exit_date = last_date
            active_trade.exit_reason = "End"
            active_trade.is_closed = True
            trades.append(active_trade)
            shares = 0.0
            position = 0
            active_trade = None
            equity.iloc[-1] = cash

        return trades, equity, benchmark_equity
