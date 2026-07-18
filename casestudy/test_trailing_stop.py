import pandas as pd
import numpy as np
from src.data_loader import DataLoader
from src.indicators import compute_supertrend, compute_hma
from src.backtest_engine import Trade
from src.risk_manager import RiskManager

# Load data
tickers = ["QQQ", "TLT", "VNQ", "GLD"]
loader = DataLoader()
data = {}
for t in tickers:
    df = loader.fetch_data(t, "2010-01-01", "2024-12-31", "1d", refresh=False)
    data[t] = df

# Common index
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

# Benchmark: Equal weight monthly rebalance
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
print(f"Benchmark (Monthly Rebal): CAGR = {bh_cagr*100:.2f}%")

# ============================================================
# STRATEGY: QQQ SuperTrend as Trailing Stop, others Buy & Hold
# ============================================================
print("\n" + "="*60)
print("STRATEGY: QQQ SuperTrend(10,3) Trailing Stop + TLT/VNQ/GLD B&H")
print("="*60)

df_qqq, _ = compute_supertrend(data["QQQ"], period=10, multiplier=3.0)

cash = 100000.0
qqq_pos = 0.0
qqq_entry_price = 0.0
qqq_entry_date = None
all_trades = []
equity_curve = pd.Series(0.0, index=common_index)
equity_curve.iloc[0] = 100000.0

# Fixed positions for TLT, VNQ, GLD (buy & hold)
tlt_shares = 25000.0 / data["TLT"].loc[common_index[0], "Close"]
vnq_shares = 25000.0 / data["VNQ"].loc[common_index[0], "Close"]
gld_shares = 25000.0 / data["GLD"].loc[common_index[0], "Close"]

comm = 10.0 / 10000.0
slip = 5.0 / 10000.0

for i in range(1, len(common_index)):
    date = common_index[i]

    # Mark to market
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

    # EXIT QQQ on trend flip to bearish
    if qqq_pos > 0 and trend == -1:
        exit_price = close * (1 - slip)
        cash += qqq_pos * exit_price * (1 - comm)
        if qqq_entry_price > 0:
            pnl = (exit_price - qqq_entry_price) / qqq_entry_price
            all_trades.append({"entry_date": qqq_entry_date, "exit_date": date,
                             "entry_price": qqq_entry_price, "exit_price": exit_price,
                             "pnl_pct": pnl, "reason": "Signal"})
        qqq_pos = 0.0; qqq_entry_price = 0.0; qqq_entry_date = None

    # ENTRY QQQ on trend flip to bullish
    elif qqq_pos == 0 and trend == 1 and prev_trend == -1:
        entry_price = close * (1 + slip)
        max_shares = target_qqq / (entry_price * (1 + comm))
        cash -= max_shares * entry_price * (1 + comm)
        qqq_pos = max_shares
        qqq_entry_price = entry_price; qqq_entry_date = date

# Final liquidation
if qqq_pos > 0:
    close = df_qqq.loc[common_index[-1], "Close"]
    exit_price = close * (1 - slip)
    cash += qqq_pos * exit_price * (1 - comm)
    if qqq_entry_price > 0:
        pnl = (exit_price - qqq_entry_price) / qqq_entry_price
        all_trades.append({"entry_date": qqq_entry_date, "exit_date": common_index[-1],
                         "entry_price": qqq_entry_price, "exit_price": exit_price,
                         "pnl_pct": pnl, "reason": "End"})
    qqq_pos = 0.0

# Add final value of buy & hold positions
final_val = cash
final_val += tlt_shares * data["TLT"].loc[common_index[-1], "Close"]
final_val += vnq_shares * data["VNQ"].loc[common_index[-1], "Close"]
final_val += gld_shares * data["GLD"].loc[common_index[-1], "Close"]
equity_curve.iloc[-1] = final_val

strat_cagr = (final_val / 100000.0) ** (1.0 / years) - 1.0

# Analyze
trade_objects = [Trade(entry_date=t["entry_date"], entry_price=t["entry_price"],
              exit_date=t["exit_date"], exit_price=t["exit_price"],
              direction="Long", pnl_pct=t["pnl_pct"], exit_reason=t["reason"], is_closed=True) for t in all_trades]
rm = RiskManager(trade_objects, equity_curve)
metrics = rm.calculate_metrics()

print(f"Strategy CAGR: {strat_cagr*100:.2f}% (vs BH {bh_cagr*100:.2f}%)")
print(f"Final Value: ${final_val:,.2f} (vs BH ${bench_equity.iloc[-1]:,.2f})")
print(f"Max Drawdown: {metrics['Max Drawdown']*100:.2f}%")
print(f"Sharpe: {metrics['Sharpe Ratio']:.2f}")
print(f"Sortino: {metrics['Sortino Ratio']:.2f}")
print(f"Calmar: {metrics['Calmar Ratio']:.2f}")
print(f"Win Rate: {metrics['Win Rate']*100:.1f}%")
print(f"Total Trades: {len(trade_objects)}")

for t in all_trades:
    print(f"  {t['entry_date'].date()} -> {t['exit_date'].date()}: {t['pnl_pct']*100:+.2f}% ({t['reason']})")

# Benchmark DD
bench_dd = (bench_equity - bench_equity.cummax()) / bench_equity.cummax()
print(f"\nBenchmark Max DD: {bench_dd.min()*100:.2f}%")
print(f"Strategy vs Benchmark CAGR diff: {(strat_cagr - bh_cagr)*100:+.2f}%")

# ============================================================
# STRATEGY 2: QQQ SuperTrend + HMA200 filter
# ============================================================
print("\n" + "="*60)
print("STRATEGY 2: QQQ SuperTrend(10,3) + HMA200 Filter + TLT/VNQ/GLD B&H")
print("="*60)

df_qqq2, _ = compute_supertrend(data["QQQ"], period=10, multiplier=3.0)
df_qqq2["HMA"] = compute_hma(df_qqq2["Close"], period=200)
df_qqq2["MA_Filter"] = df_qqq2["Close"] > df_qqq2["HMA"]

cash = 100000.0
qqq_pos = 0.0
qqq_entry_price = 0.0
qqq_entry_date = None
all_trades = []
equity_curve2 = pd.Series(0.0, index=common_index)
equity_curve2.iloc[0] = 100000.0

tlt_shares = 25000.0 / data["TLT"].loc[common_index[0], "Close"]
vnq_shares = 25000.0 / data["VNQ"].loc[common_index[0], "Close"]
gld_shares = 25000.0 / data["GLD"].loc[common_index[0], "Close"]

for i in range(1, len(common_index)):
    date = common_index[i]

    portfolio_value = cash
    portfolio_value += qqq_pos * df_qqq2.loc[date, "Close"]
    portfolio_value += tlt_shares * data["TLT"].loc[date, "Close"]
    portfolio_value += vnq_shares * data["VNQ"].loc[date, "Close"]
    portfolio_value += gld_shares * data["GLD"].loc[date, "Close"]
    equity_curve2.iloc[i] = portfolio_value

    target_qqq = portfolio_value * 0.25

    close = df_qqq2.loc[date, "Close"]
    trend = df_qqq2.loc[date, "Trend"]
    prev_trend = df_qqq2.loc[common_index[i-1], "Trend"]
    ma_ok = df_qqq2.loc[date, "MA_Filter"]

    if qqq_pos > 0 and trend == -1:
        exit_price = close * (1 - slip)
        cash += qqq_pos * exit_price * (1 - comm)
        if qqq_entry_price > 0:
            pnl = (exit_price - qqq_entry_price) / qqq_entry_price
            all_trades.append({"entry_date": qqq_entry_date, "exit_date": date,
                             "entry_price": qqq_entry_price, "exit_price": exit_price,
                             "pnl_pct": pnl, "reason": "Signal"})
        qqq_pos = 0.0; qqq_entry_price = 0.0; qqq_entry_date = None
    elif qqq_pos == 0 and trend == 1 and prev_trend == -1 and ma_ok:
        entry_price = close * (1 + slip)
        max_shares = target_qqq / (entry_price * (1 + comm))
        cash -= max_shares * entry_price * (1 + comm)
        qqq_pos = max_shares
        qqq_entry_price = entry_price; qqq_entry_date = date

if qqq_pos > 0:
    close = df_qqq2.loc[common_index[-1], "Close"]
    exit_price = close * (1 - slip)
    cash += qqq_pos * exit_price * (1 - comm)
    if qqq_entry_price > 0:
        pnl = (exit_price - qqq_entry_price) / qqq_entry_price
        all_trades.append({"entry_date": qqq_entry_date, "exit_date": common_index[-1],
                         "entry_price": qqq_entry_price, "exit_price": exit_price,
                         "pnl_pct": pnl, "reason": "End"})
    qqq_pos = 0.0

final_val2 = cash
final_val2 += tlt_shares * data["TLT"].loc[common_index[-1], "Close"]
final_val2 += vnq_shares * data["VNQ"].loc[common_index[-1], "Close"]
final_val2 += gld_shares * data["GLD"].loc[common_index[-1], "Close"]
equity_curve2.iloc[-1] = final_val2

strat_cagr2 = (final_val2 / 100000.0) ** (1.0 / years) - 1.0

trade_objects2 = [Trade(entry_date=t["entry_date"], entry_price=t["entry_price"],
               exit_date=t["exit_date"], exit_price=t["exit_price"],
               direction="Long", pnl_pct=t["pnl_pct"], exit_reason=t["reason"], is_closed=True) for t in all_trades]
rm2 = RiskManager(trade_objects2, equity_curve2)
metrics2 = rm2.calculate_metrics()

print(f"Strategy CAGR: {strat_cagr2*100:.2f}% (vs BH {bh_cagr*100:.2f}%)")
print(f"Final Value: ${final_val2:,.2f}")
print(f"Max Drawdown: {metrics2['Max Drawdown']*100:.2f}%")
print(f"Sharpe: {metrics2['Sharpe Ratio']:.2f}")
print(f"Total Trades: {len(trade_objects2)}")
print(f"Win Rate: {metrics2['Win Rate']*100:.1f}%")

for t in all_trades:
    print(f"  {t['entry_date'].date()} -> {t['exit_date'].date()}: {t['pnl_pct']*100:+.2f}% ({t['reason']})")

print(f"\nBenchmark Max DD: {bench_dd.min()*100:.2f}%")
print(f"Strategy vs Benchmark CAGR diff: {(strat_cagr2 - bh_cagr)*100:+.2f}%")