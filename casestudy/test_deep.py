import pandas as pd
import numpy as np
from src.data_loader import DataLoader
from src.indicators import compute_supertrend, compute_hma, compute_adx, compute_rsi
from src.backtest_engine import BacktestEngine
from src.risk_manager import RiskManager

# Test SPY with different approaches
ticker = "SPY"
start_date = "2010-01-01"
end_date = "2024-12-31"
interval = "1d"

loader = DataLoader()
df_raw = loader.fetch_data(ticker, start_date=start_date, end_date=end_date, interval=interval, refresh=False)
print(f"Loaded {ticker}: {len(df_raw)} bars")

df_st, _ = compute_supertrend(df_raw, period=10, multiplier=3.0)
years = (df_st.index[-1] - df_st.index[0]).days / 365.25

# Benchmark
initial_close = df_raw["Close"].iloc[0]
benchmark_shares = 100000.0 / initial_close
benchmark = df_raw["Close"] * benchmark_shares
bh_cagr = (benchmark.iloc[-1] / benchmark.iloc[0]) ** (1.0 / years) - 1.0
print(f"Buy & Hold CAGR: {bh_cagr*100:.2f}%")

# Test: Longer period SuperTrend
print("\n--- Testing longer SuperTrend periods (no filter) ---")
for period in [10, 14, 20, 30, 50]:
    df_test, _ = compute_supertrend(df_raw, period=period, multiplier=3.0)
    df_test["MA_Filter"] = True
    df_test["RSI_Filter"] = True
    df_test["ADX_Filter"] = True

    engine = BacktestEngine(df_test)
    trades, equity, _ = engine.run(long_only=True, commission_bps=10.0, slippage_bps=5.0)
    rm = RiskManager(trades, equity)
    metrics = rm.calculate_metrics()
    closed = [t for t in trades if t.is_closed]
    time_in_market = sum((t.exit_date - t.entry_date).days for t in closed if t.exit_date) / (years * 365) * 100
    print(f"  ST({period},3): CAGR={metrics['CAGR']*100:5.2f}% | Trades={len(closed):2d} | TimeInMkt={time_in_market:5.1f}% | MaxDD={metrics['Max Drawdown']*100:6.2f}%")

# Test: Different multipliers
print("\n--- Testing different multipliers (period=20) ---")
for mult in [2.0, 2.5, 3.0, 3.5, 4.0]:
    df_test, _ = compute_supertrend(df_raw, period=20, multiplier=mult)
    df_test["MA_Filter"] = True
    df_test["RSI_Filter"] = True
    df_test["ADX_Filter"] = True

    engine = BacktestEngine(df_test)
    trades, equity, _ = engine.run(long_only=True, commission_bps=10.0, slippage_bps=5.0)
    rm = RiskManager(trades, equity)
    metrics = rm.calculate_metrics()
    closed = [t for t in trades if t.is_closed]
    time_in_market = sum((t.exit_date - t.entry_date).days for t in closed if t.exit_date) / (years * 365) * 100
    print(f"  ST(20,{mult}): CAGR={metrics['CAGR']*100:5.2f}% | Trades={len(closed):2d} | TimeInMkt={time_in_market:5.1f}% | MaxDD={metrics['Max Drawdown']*100:6.2f}%")

# Test: What if we NEVER exit once we enter? (Buy on first signal, hold forever)
print("\n--- Buy on first bullish signal, hold forever (no exit) ---")
df_test, _ = compute_supertrend(df_raw, period=10, multiplier=3.0)
first_bullish = df_test[df_test["Trend"] == 1].index[0]
print(f"First bullish signal: {first_bullish.date()}")

# Calculate return from that date
entry_price = df_raw.loc[first_bullish, "Close"]
final_price = df_raw["Close"].iloc[-1]
cagr_from_signal = (final_price / entry_price) ** (1.0 / ((df_raw.index[-1] - first_bullish).days / 365.25)) - 1.0
print(f"CAGR from first signal: {cagr_from_signal*100:.2f}% vs BH {bh_cagr*100:.2f}%")

# Test: Enter on first signal, exit on LAST signal (never re-enter)
print("\n--- Enter first signal, exit last signal (no re-entry) ---")
trend_changes = df_test["Trend"].diff().ne(0)
entries = df_test[(df_test["Trend"] == 1) & trend_changes].index
exits = df_test[(df_test["Trend"] == -1) & trend_changes].index
print(f"Entries: {len(entries)}, Exits: {len(exits)}")
if len(entries) > 0 and len(exits) > 0:
    first_entry = entries[0]
    last_exit = exits[-1] if exits[-1] > first_entry else df_test.index[-1]
    print(f"First entry: {first_entry.date()}, Last exit: {last_exit.date()}")
    entry_price = df_raw.loc[first_entry, "Close"]
    exit_price = df_raw.loc[last_exit, "Close"]
    cagr = (exit_price / entry_price) ** (1.0 / ((last_exit - first_entry).days / 365.25)) - 1.0
    print(f"CAGR: {cagr*100:.2f}%")

# The fundamental problem: SuperTrend in a bull market
print("\n" + "="*60)
print("FUNDAMENTAL ISSUE: Trend following CANNOT beat Buy & Hold")
print("in a strong bull market because:")
print("  1. Entry lag: Miss first 10-20% of every trend")
print("  2. Exit lag: Give back 10-20% at trend end")
print("  3. Whipsaws: Lose money in sideways markets")
print("  4. Cash drag: Out of market during corrections (miss bounce)")
print("  5. Time in market: Only 50-70% vs 100% for B&H")
print("="*60)

# Show typical trade pattern
print("\n--- Typical trade analysis (ST 10,3) ---")
df_test, _ = compute_supertrend(df_raw, period=10, multiplier=3.0)
df_test["MA_Filter"] = True
df_test["RSI_Filter"] = True
df_test["ADX_Filter"] = True
engine = BacktestEngine(df_test)
trades, equity, _ = engine.run(long_only=True, commission_bps=10.0, slippage_bps=5.0)
closed = [t for t in trades if t.is_closed]
for i, t in enumerate(closed[:10]):
    bh_return = (df_raw.loc[t.exit_date, "Close"] / df_raw.loc[t.entry_date, "Close"] - 1) * 100
    print(f"  Trade {i+1}: {t.entry_date.date()} -> {t.exit_date.date()} | ST: {t.pnl_pct*100:+.1f}% | B&H: {bh_return:+.1f}% | Diff: {t.pnl_pct*100 - bh_return:+.1f}% | Days: {(t.exit_date-t.entry_date).days}")