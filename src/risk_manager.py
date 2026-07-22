import pandas as pd
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
from src.backtest_engine import Trade

class RiskManager:
    """
    績效指標計算與風險模擬器
    負責評估回測交易明細與每日盯市權益曲線，支援交易級 Monte Carlo 模擬。
    """
    def __init__(self, trades: List[Trade], equity: pd.Series):
        self.trades = trades
        self.equity = equity

    def calculate_metrics(self) -> Dict[str, Any]:
        """
        計算系統性的策略績效與統計指標。
        """
        if self.equity.empty or len(self.equity) < 2:
            return {}

        # 1. 計算時間長度 (年)
        years = (self.equity.index[-1] - self.equity.index[0]).days / 365.25
        years = max(years, 0.001)

        # 2. CAGR (年化複合報酬率)
        initial_val = self.equity.iloc[0]
        final_val = self.equity.iloc[-1]
        cagr = (final_val / initial_val) ** (1.0 / years) - 1.0

        # 3. Max Drawdown (最大回撤)與 Ulcer Index (潰瘍指數)
        roll_max = self.equity.cummax()
        # 避免除以 0
        drawdowns = (self.equity - roll_max) / (roll_max + 1e-10)
        max_dd = drawdowns.min()

        # 潰瘍指數 UI = sqrt(mean(drawdown_t ^ 2))
        squared_drawdowns = drawdowns ** 2
        ulcer_index = np.sqrt(squared_drawdowns.mean())

        # 4. 夏普比率 (Sharpe) 與 索提諾比率 (Sortino) (基於日收益率)
        daily_returns = self.equity.pct_change().dropna()
        sharpe = 0.0
        sortino = 0.0

        # 假定無風險年化利率為 2%
        rf_daily = 0.02 / 252.0
        if not daily_returns.empty and daily_returns.std() > 0:
            excess_returns = daily_returns - rf_daily
            sharpe = (excess_returns.mean() / daily_returns.std()) * np.sqrt(252.0)

            downside_returns = daily_returns[daily_returns < 0]
            # 避免除以 0
            downside_std = downside_returns.std() if len(downside_returns) > 1 else 0.0
            if downside_std > 0:
                sortino = (excess_returns.mean() / downside_std) * np.sqrt(252.0)

        # 5. 交易明細指標
        closed_trades = [t for t in self.trades if t.is_closed]
        wins = [t for t in closed_trades if t.pnl_pct > 0]
        losses = [t for t in closed_trades if t.pnl_pct <= 0]

        win_rate = len(wins) / len(closed_trades) if closed_trades else 0.0

        avg_win = np.mean([t.pnl_pct for t in wins]) if wins else 0.0
        avg_loss = np.mean([t.pnl_pct for t in losses]) if losses else 0.0

        # Expectancy 交易期望值
        expectancy = win_rate * avg_win - (1 - win_rate) * abs(avg_loss)

        total_gain = sum(t.pnl_pct for t in wins)
        total_loss = sum(abs(t.pnl_pct) for t in losses)
        # 避免除以 0
        profit_factor = total_gain / total_loss if total_loss > 0.0 else (total_gain if total_gain > 0.0 else 1.0)

        calmar = cagr / abs(max_dd) if max_dd != 0.0 else 0.0

        # 持倉天數與年化交易次數
        holding_days = [(t.exit_date - t.entry_date).days for t in closed_trades if t.exit_date]
        avg_holding_days = float(np.mean(holding_days)) if holding_days else 0.0
        annual_trades = len(closed_trades) / years

        # 最大連續盈虧次數
        max_consec_wins = 0
        max_consec_losses = 0
        curr_wins = 0
        curr_losses = 0
        for t in closed_trades:
            if t.pnl_pct > 0:
                curr_wins += 1
                curr_losses = 0
                max_consec_wins = max(max_consec_wins, curr_wins)
            else:
                curr_losses += 1
                curr_wins = 0
                max_consec_losses = max(max_consec_losses, curr_losses)

        return {
            "CAGR": float(cagr),
            "Max Drawdown": float(max_dd),
            "Ulcer Index": float(ulcer_index),
            "Sharpe Ratio": float(sharpe),
            "Sortino Ratio": float(sortino),
            "Win Rate": float(win_rate),
            "Profit Factor": float(profit_factor),
            "Calmar Ratio": float(calmar),
            "Expectancy": float(expectancy),
            "Avg Holding Days": avg_holding_days,
            "Annual Trades": float(annual_trades),
            "Max Consecutive Wins": int(max_consec_wins),
            "Max Consecutive Losses": int(max_consec_losses)
        }

    def run_monte_carlo(self, runs: int = 5000, num_trades: int = 50, seed: Optional[int] = None) -> Dict[str, Any]:
        """
        執行交易級 Monte Carlo 模擬。
        對平倉交易百分比收益率序列進行帶放回抽樣 (Bootstrapping)。
        """
        if seed is not None:
            np.random.seed(seed)

        returns = np.array([t.pnl_pct for t in self.trades if t.is_closed])
        if len(returns) == 0:
            return {
                "drawdowns": np.zeros(runs),
                "terminal_values": np.ones(runs) * 100000.0,
                "percentiles": {k: 0.0 for k in ["50% (Median)", "75%", "90%", "95%", "99%"]}
            }

        simulated_max_dds = []
        simulated_terminals = []

        for _ in range(runs):
            # 隨機抽樣
            sampled_returns = np.random.choice(returns, size=num_trades, replace=True)
            # 計算淨值增長路徑 (起始資金 10 萬)
            equity_curve = 100000.0 * np.cumprod(1.0 + sampled_returns)

            # 計算該路徑的最大回撤
            peaks = np.maximum.accumulate(equity_curve)
            drawdowns = (equity_curve - peaks) / (peaks + 1e-10)

            simulated_max_dds.append(drawdowns.min())
            simulated_terminals.append(equity_curve[-1])

        simulated_max_dds = np.array(simulated_max_dds)
        simulated_terminals = np.array(simulated_terminals)

        # 由於回撤為負值，百分位數越小表示回撤越深 (越差)
        # 例如 95% worst-case 等於從低到高排列的第 5 個百分位數
        percentiles_dd = {
            "50% (Median)": float(np.percentile(simulated_max_dds, 50)),
            "75%": float(np.percentile(simulated_max_dds, 25)),
            "90%": float(np.percentile(simulated_max_dds, 10)),
            "95%": float(np.percentile(simulated_max_dds, 5)),
            "99%": float(np.percentile(simulated_max_dds, 1))
        }

        return {
            "drawdowns": simulated_max_dds,
            "terminal_values": simulated_terminals,
            "percentiles": percentiles_dd
        }
