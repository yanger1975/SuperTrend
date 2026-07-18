import pandas as pd
import numpy as np
from src.data_loader import DataLoader
from src.indicators import compute_supertrend, compute_hma, compute_adx, compute_rsi
from src.backtest_engine import BacktestEngine
from src.risk_manager import RiskManager

# ============================================================
# MULTI-ETF PORTFOLIO BACKTEST
# ============================================================

tickers = ["QQQ", "TLT", "VNQ", "GLD"]
weights = {"QQQ": 0.25, "TLT": 0.25, "VNQ": 0.25, "GLD": 0.25}
start_date = "2010-01-01"
end_date = "2024-12-31"
interval = "1d"

loader = DataLoader()

# 1. Load all data
print("Loading data...")
data = {}
for ticker in tickers:
    df = loader.fetch_data(ticker, start_date, end_date, interval, refresh=False)
    data[ticker] = df
    print(f"  {ticker}: {len(df)} bars")

# 2. Calculate indicators for each
print("\nCalculating indicators...")
indicators = {}
for ticker, df in data.items():
    df_st, _ = compute_supertrend(df, period=10, multiplier=3.0)
    df_st["HMA"] = compute_hma(df_st["Close"], period=200)
    df_st["MA_Filter"] = df_st["Close"] > df_st["HMA"]
    df_st["ADX"] = compute_adx(df_st, period=14)
    df_st["RSI"] = compute_rsi(df_st["Close"], period=14)
    df_st["ADX_Filter"] = df_st["ADX"] > 20
    df_st["RSI_Filter"] = df_st["RSI"] > 50
    indicators[ticker] = df_st

# 3. Align all to common date index
common_index = None
for ticker, df in indicators.items():
    if common_index is None:
        common_index = df.index
    else:
        common_index = common_index.intersection(df.index)
common_index = common_index.sort_values()

print(f"\nCommon date range: {common_index[0].date()} to {common_index[-1].date()} ({len(common_index)} days)")

# Reindex all to common index
for ticker in tickers:
    indicators[ticker] = indicators[ticker].reindex(common_index).ffill()

# 4. PORTFOLIO BACKTEST
print("\nRunning portfolio backtest...")

initial_cash = 100000.0
cash = initial_cash
positions = {t: 0.0 for t in tickers}  # shares held
entry_prices = {t: 0.0 for t in tickers}
entry_dates = {t: None for t in tickers}
active_trades = {t: None for t in tickers}

equity_curve = pd.Series(0.0, index=common_index)
equity_curve.iloc[0] = initial_cash

# Benchmark: Equal weight buy & hold (rebalanced monthly)
bench_shares = {}
for ticker in tickers:
    bench_shares[ticker] = (initial_cash * weights[ticker]) / data[ticker].reindex(common_index).ffill()["Close"].iloc[0]
bench_equity = pd.Series(0.0, index=common_index)
for ticker in tickers:
    bench_equity += data[ticker].reindex(common_index).ffill()["Close"] * bench_shares[ticker]

comm = 10.0 / 10000.0
slip = 5.0 / 10000.0

all_trades = []

for i in range(1, len(common_index)):
    date = common_index[i]

    # Current equity
    portfolio_value = cash
    for ticker in tickers:
        portfolio_value += positions[ticker] * indicators[ticker].loc[date, "Close"]
    equity_curve.iloc[i] = portfolio_value

    target_per_ticker = portfolio_value * 0.25  # 25% each when active

    for ticker in tickers:
        df = indicators[ticker]
        close = df.loc[date, "Close"]
        trend = df.loc[date, "Trend"]
        prev_trend = df.loc[common_index[i-1], "Trend"]
        ma_ok = df.loc[date, "MA_Filter"]
        adx_ok = df.loc[date, "ADX_Filter"]
        rsi_ok = df.loc[date, "RSI_Filter"]

        pos = positions[ticker]

        # EXIT: Trend flip to bearish
        if pos > 0 and trend == -1:
            exit_price = close * (1 - slip)
            cash += pos * exit_price * (1 - comm)

            # Record trade
            if entry_prices[ticker] > 0:
                pnl = (exit_price - entry_prices[ticker]) / entry_prices[ticker]
                all_trades.append({
                    "ticker": ticker, "entry_date": entry_dates[ticker],
                    "exit_date": date, "entry_price": entry_prices[ticker],
                    "exit_price": exit_price, "pnl_pct": pnl, "reason": "Signal"
                })

            positions[ticker] = 0.0
            entry_prices[ticker] = 0.0
            entry_dates[ticker] = None

        # ENTRY: Trend flip to bullish + filters pass
        elif pos == 0 and trend == 1 and prev_trend == -1 and ma_ok and adx_ok and rsi_ok:
            entry_price = close * (1 + slip)
            max_shares = target_per_ticker / (entry_price * (1 + comm))
            shares = max_shares

            cash -= shares * entry_price * (1 + comm)
            positions[ticker] = shares
            entry_prices[ticker] = entry_price
            entry_dates[ticker] = date

# Final liquidation
for ticker in tickers:
    if positions[ticker] > 0:
        close = indicators[ticker].loc[common_index[-1], "Close"]
        exit_price = close * (1 - slip)
        cash += positions[ticker] * exit_price * (1 - comm)

        if entry_prices[ticker] > 0:
            pnl = (exit_price - entry_prices[ticker]) / entry_prices[ticker]
            all_trades.append({
                "ticker": ticker, "entry_date": entry_dates[ticker],
                "exit_date": common_index[-1], "entry_price": entry_prices[ticker],
                "exit_price": exit_price, "pnl_pct": pnl, "reason": "End"
            })
        positions[ticker] = 0.0

equity_curve.iloc[-1] = cash

# 5. ANALYSIS
from src.backtest_engine import Trade
trade_objects = []
for t in all_trades:
    tr = Trade(
        entry_date=t["entry_date"], entry_price=t["entry_price"],
        exit_date=t["exit_date"], exit_price=t["exit_price"],
        direction="Long", pnl_pct=t["pnl_pct"], exit_reason=t["reason"], is_closed=True
    )
    trade_objects.append(tr)

rm = RiskManager(trade_objects, equity_curve)
metrics = rm.calculate_metrics()

years = (common_index[-1] - common_index[0]).days / 365.25
bh_cagr = (bench_equity.iloc[-1] / bench_equity.iloc[0]) ** (1.0 / years) - 1.0
strat_cagr = metrics['CAGR']

print(f"\n{'='*60}")
print("MULTI-ETF PORTFOLIO RESULTS (25% each, SuperTrend + HMA200 + ADX20 + RSI50)")
print(f"{'='*60}")
print(f"Period: {common_index[0].date()} to {common_index[-1].date()} ({years:.1f} years)")
print(f"\nStrategy:")
print(f"  CAGR: {strat_cagr*100:.2f}%")
print(f"  Final Value: ${equity_curve.iloc[-1]:,.2f}")
print(f"  Max Drawdown: {metrics['Max Drawdown']*100:.2f}%")
print(f"  Sharpe: {metrics['Sharpe Ratio']:.2f}")
print(f"  Sortino: {metrics['Sortino Ratio']:.2f}")
print(f"  Calmar: {metrics['Calmar Ratio']:.2f}")
print(f"  Win Rate: {metrics['Win Rate']*100:.1f}%")
print(f"  Profit Factor: {metrics['Profit Factor']:.2f}")
print(f"  Total Trades: {len(trade_objects)}")

print(f"\nBenchmark (Equal Weight Buy & Hold, Monthly Rebalance):")
print(f"  CAGR: {bh_cagr*100:.2f}%")
print(f"  Final Value: ${bench_equity.iloc[-1]:,.2f}")

# Individual ETF Buy & Hold
print(f"\nIndividual ETF Buy & Hold CAGR:")
for ticker in tickers:
    df = data[ticker].reindex(common_index).ffill()
    cagr = (df["Close"].iloc[-1] / df["Close"].iloc[0]) ** (1.0 / years) - 1.0
    print(f"  {ticker}: {cagr*100:.2f}%")

# Trade breakdown by ticker
print(f"\nTrades by Ticker:")
for ticker in tickers:
    t_trades = [t for t in trade_objects if hasattr(t, 'ticker') and ticker in str(t.__dict__)]
    # Actually, our Trade class doesn't have ticker... let's use the dict
    t_trades = [t for t in all_trades if t["ticker"] == ticker]
    if t_trades:
        wins = [t for t in t_trades if t["pnl_pct"] > 0]
        print(f"  {ticker}: {len(t_trades)} trades, {len(wins)} wins, avg PnL: {np.mean([t['pnl_pct'] for t in t_trades])*100:.2f}%")

# Monthly rebalance benchmark
print(f"\n{'='*60}")
print("COMPARISON: Strategy vs Benchmark")
print(f"{'='*60}")
print(f"Strategy outperforms by: {(strat_cagr - bh_cagr)*100:.2f}% CAGR")
print(f"Strategy Max DD: {metrics['Max Drawdown']*100:.2f}%")

# Calculate benchmark drawdown
bench_roll_max = bench_equity.cummax()
bench_dd = (bench_equity - bench_roll_max) / bench_roll_max
print(f"Benchmark Max DD: {bench_dd.min()*100:.2f}%")