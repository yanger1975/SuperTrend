import pandas as pd
import numpy as np
from src.data_loader import DataLoader
from src.indicators import compute_supertrend, compute_hma
from src.backtest_engine import Trade
from src.risk_manager import RiskManager

tickers = ["QQQ", "TLT", "VNQ", "GLD"]
loader = DataLoader()
data = {}
for t in tickers:
    df = loader.fetch_data(t, "2010-01-01", "2024-12-31", "1d", refresh=False)
    data[t] = df

common_index = None
for t, df in data.items():
    if common_index is None:
        common_index = df.index
    else:
        common_index = common_index.intersection(df.index)
common_index = common_index.sort_values()

for t in tickers:
    data[t] = data[t].reindex(common_index).ffill()

years = (common_index[-1] - common_index[0]).days / 365.25

# Benchmark
bench_equity = pd.Series(0.0, index=common_index)
bench_equity.iloc[0] = 100000.0
bench_shares = {t: 25000.0 / data[t].loc[common_index[0], "Close"] for t in tickers}
for i in range(1, len(common_index)):
    date = common_index[i]
    prev_date = common_index[i-1]
    val = sum(bench_shares[t] * data[t].loc[date, "Close"] for t in tickers)
    bench_equity.iloc[i] = val
    if date.month != prev_date.month:
        for t in tickers:
            bench_shares[t] = (val * 0.25) / data[t].loc[date, "Close"]

bh_cagr = (bench_equity.iloc[-1] / bench_equity.iloc[0]) ** (1.0 / years) - 1.0
bench_dd = (bench_equity - bench_equity.cummax()) / bench_equity.cummax()

print(f"Benchmark: CAGR={bh_cagr*100:.2f}%, MaxDD={bench_dd.min()*100:.2f}%")
print()

comm = 10.0 / 10000.0
slip = 5.0 / 10000.0

# Test different SuperTrend periods on QQQ only
for period in [10, 14, 20, 30]:
    for mult in [2.5, 3.0, 3.5]:
        df_qqq, _ = compute_supertrend(data["QQQ"], period=period, multiplier=mult)

        cash = 100000.0
        qqq_pos = 0.0
        qqq_entry_price = 0.0
        qqq_entry_date = None
        all_trades = []
        equity_curve = pd.Series(0.0, index=common_index)
        equity_curve.iloc[0] = 100000.0

        tlt_shares = 25000.0 / data["TLT"].loc[common_index[0], "Close"]
        vnq_shares = 25000.0 / data["VNQ"].loc[common_index[0], "Close"]
        gld_shares = 25000.0 / data["GLD"].loc[common_index[0], "Close"]

        for i in range(1, len(common_index)):
            date = common_index[i]
            portfolio_value = cash
            portfolio_value += qqq_pos * df_qqq.loc[date, "Close"]
            portfolio_value += tlt_shares * data["TLT"].loc[date, "Close"]
            portfolio_value += vnq_shares * data["VNQ"].loc[date, "Close"]
            portfolio_value += gld_shares * data["GLD"].loc[date, "Close"]
            equity_curve.iloc[i] = portfolio_value

            target_qqq = portfolio_value * 0.25

            close = df_qqq.loc[date, "Close"]
            trend = df_qqq.loc[date, "Trend"]
            prev_trend = df_qqq.loc[common_index[i-1], "Trend"]

            if qqq_pos > 0 and trend == -1:
                exit_price = close * (1 - slip)
                cash += qqq_pos * exit_price * (1 - comm)
                if qqq_entry_price > 0:
                    pnl = (exit_price - qqq_entry_price) / qqq_entry_price
                    all_trades.append({"pnl": pnl})
                qqq_pos = 0.0; qqq_entry_price = 0.0; qqq_entry_date = None
            elif qqq_pos == 0 and trend == 1 and prev_trend == -1:
                entry_price = close * (1 + slip)
                max_shares = target_qqq / (entry_price * (1 + comm))
                cash -= max_shares * entry_price * (1 + comm)
                qqq_pos = max_shares
                qqq_entry_price = entry_price; qqq_entry_date = date

        if qqq_pos > 0:
            close = df_qqq.loc[common_index[-1], "Close"]
            exit_price = close * (1 - slip)
            cash += qqq_pos * exit_price * (1 - comm)
            if qqq_entry_price > 0:
                pnl = (exit_price - qqq_entry_price) / qqq_entry_price
                all_trades.append({"pnl": pnl})
            qqq_pos = 0.0

        final_val = cash + tlt_shares * data["TLT"].loc[common_index[-1], "Close"] + \
                       vnq_shares * data["VNQ"].loc[common_index[-1], "Close"] + \
                       gld_shares * data["GLD"].loc[common_index[-1], "Close"]
        equity_curve.iloc[-1] = final_val

        strat_cagr = (final_val / 100000.0) ** (1.0 / years) - 1.0

        trade_objects = [Trade(entry_date=pd.Timestamp.now(), entry_price=1, exit_date=pd.Timestamp.now(), exit_price=1, direction="Long", pnl_pct=t["pnl"], exit_reason="S", is_closed=True) for t in all_trades]
        rm = RiskManager(trade_objects, equity_curve)
        metrics = rm.calculate_metrics()

        dd = (equity_curve - equity_curve.cummax()) / equity_curve.cummax()

        print(f"ST({period},{mult}): CAGR={strat_cagr*100:.2f}% (diff={(strat_cagr-bh_cagr)*100:+.2f}%), "
              f"DD={metrics['Max Drawdown']*100:.1f}%, Sharpe={metrics['Sharpe Ratio']:.2f}, "
              f"Trades={len(all_trades)}, Win%={metrics['Win Rate']*100:.1f}%")