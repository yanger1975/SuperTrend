import pandas as pd
import numpy as np
from src.data_loader import DataLoader
from src.indicators import compute_supertrend, compute_hma, compute_adx, compute_rsi
from src.backtest_engine import BacktestEngine
from src.risk_manager import RiskManager

ticker = "QQQM"
start_date = "2020-01-01"
end_date = "2026-06-01"
interval = "1d"

loader = DataLoader()
df_raw = loader.fetch_data(ticker, start_date=start_date, end_date=end_date, interval=interval, refresh=False)
print(f"Loaded {ticker}: {len(df_raw)} bars")

# Test 1: NO FILTERS (pure SuperTrend)
print("\n" + "="*60)
print("TEST 1: Pure SuperTrend (no filters)")
print("="*60)
df_st, _ = compute_supertrend(df_raw, period=10, multiplier=3.0)
df_st["MA_Filter"] = True
df_st["ADX_Filter"] = True
df_st["RSI_Filter"] = True

engine = BacktestEngine(df_st)
trades, equity, benchmark = engine.run(
    long_only=True, stop_loss_pct=0.08, take_profit_pct=0.20,
    commission_bps=10.0, slippage_bps=5.0, position_sizing_mode="fixed_fraction"
)
rm = RiskManager(trades, equity)
metrics = rm.calculate_metrics()
years = (equity.index[-1] - equity.index[0]).days / 365.25
bh_cagr = (benchmark.iloc[-1] / benchmark.iloc[0]) ** (1.0 / years) - 1.0
closed = [t for t in trades if t.is_closed]
print(f"  CAGR: {metrics['CAGR']*100:.2f}% vs BH: {bh_cagr*100:.2f}%")
print(f"  Trades: {len(closed)} | Time in market: {sum((t.exit_date - t.entry_date).days for t in closed if t.exit_date) / (years*365)*100:.1f}%")

# Test 2: SuperTrend with RSI > 50 filter only
print("\n" + "="*60)
print("TEST 2: SuperTrend + RSI > 50")
print("="*60)
df_st, _ = compute_supertrend(df_raw, period=10, multiplier=3.0)
df_st["RSI"] = compute_rsi(df_st["Close"], period=14)
df_st["RSI_Filter"] = df_st["RSI"] > 50
df_st["MA_Filter"] = True
df_st["ADX_Filter"] = True

engine = BacktestEngine(df_st)
trades, equity, benchmark = engine.run(
    long_only=True, stop_loss_pct=0.08, take_profit_pct=0.20,
    commission_bps=10.0, slippage_bps=5.0, position_sizing_mode="fixed_fraction"
)
rm = RiskManager(trades, equity)
metrics = rm.calculate_metrics()
closed = [t for t in trades if t.is_closed]
print(f"  CAGR: {metrics['CAGR']*100:.2f}% vs BH: {bh_cagr*100:.2f}%")
print(f"  Trades: {len(closed)} | Time in market: {sum((t.exit_date - t.entry_date).days for t in closed if t.exit_date) / (years*365)*100:.1f}%")

# Test 3: SuperTrend with ADX > 20 filter only
print("\n" + "="*60)
print("TEST 3: SuperTrend + ADX > 20")
print("="*60)
df_st, _ = compute_supertrend(df_raw, period=10, multiplier=3.0)
df_st["ADX"] = compute_adx(df_st, period=14)
df_st["ADX_Filter"] = df_st["ADX"] > 20
df_st["MA_Filter"] = True
df_st["RSI_Filter"] = True

engine = BacktestEngine(df_st)
trades, equity, benchmark = engine.run(
    long_only=True, stop_loss_pct=0.08, take_profit_pct=0.20,
    commission_bps=10.0, slippage_bps=5.0, position_sizing_mode="fixed_fraction"
)
rm = RiskManager(trades, equity)
metrics = rm.calculate_metrics()
closed = [t for t in trades if t.is_closed]
print(f"  CAGR: {metrics['CAGR']*100:.2f}% vs BH: {bh_cagr*100:.2f}%")
print(f"  Trades: {len(closed)} | Time in market: {sum((t.exit_date - t.entry_date).days for t in closed if t.exit_date) / (years*365)*100:.1f}%")

# Test 4: Faster SuperTrend (period=7, mult=2.5) + no HMA filter
print("\n" + "="*60)
print("TEST 4: Faster SuperTrend (7, 2.5) - no HMA filter")
print("="*60)
df_st, _ = compute_supertrend(df_raw, period=7, multiplier=2.5)
df_st["MA_Filter"] = True
df_st["ADX_Filter"] = True
df_st["RSI_Filter"] = True

engine = BacktestEngine(df_st)
trades, equity, benchmark = engine.run(
    long_only=True, stop_loss_pct=0.08, take_profit_pct=0.20,
    commission_bps=10.0, slippage_bps=5.0, position_sizing_mode="fixed_fraction"
)
rm = RiskManager(trades, equity)
metrics = rm.calculate_metrics()
closed = [t for t in trades if t.is_closed]
print(f"  CAGR: {metrics['CAGR']*100:.2f}% vs BH: {bh_cagr*100:.2f}%")
print(f"  Trades: {len(closed)} | Time in market: {sum((t.exit_date - t.entry_date).days for t in closed if t.exit_date) / (years*365)*100:.1f}%")

# Test 5: Faster SuperTrend + RSI > 50
print("\n" + "="*60)
print("TEST 5: Faster SuperTrend (7, 2.5) + RSI > 50")
print("="*60)
df_st, _ = compute_supertrend(df_raw, period=7, multiplier=2.5)
df_st["RSI"] = compute_rsi(df_st["Close"], period=14)
df_st["RSI_Filter"] = df_st["RSI"] > 50
df_st["MA_Filter"] = True
df_st["ADX_Filter"] = True

engine = BacktestEngine(df_st)
trades, equity, benchmark = engine.run(
    long_only=True, stop_loss_pct=0.08, take_profit_pct=0.20,
    commission_bps=10.0, slippage_bps=5.0, position_sizing_mode="fixed_fraction"
)
rm = RiskManager(trades, equity)
metrics = rm.calculate_metrics()
closed = [t for t in trades if t.is_closed]
print(f"  CAGR: {metrics['CAGR']*100:.2f}% vs BH: {bh_cagr*100:.2f}%")
print(f"  Trades: {len(closed)} | Time in market: {sum((t.exit_date - t.entry_date).days for t in closed if t.exit_date) / (years*365)*100:.1f}%")

# Test 6: Buy & Hold with costs (fair comparison)
print("\n" + "="*60)
print("TEST 6: Buy & Hold WITH same costs (10 bps commission + 5 bps slippage)")
print("="*60)
# Simulate: buy at start, sell at end, with costs
initial_cash = 100000.0
first_close = df_raw["Close"].iloc[0]
last_close = df_raw["Close"].iloc[-1]
comm = 10.0 / 10000.0
slip = 5.0 / 10000.0

# Entry cost
shares = initial_cash / (first_close * (1 + slip) * (1 + comm))
# Exit value
bh_value_with_costs = shares * last_close * (1 - slip) * (1 - comm)
bh_cagr_with_costs = (bh_value_with_costs / initial_cash) ** (1.0 / years) - 1.0
print(f"  CAGR with costs: {bh_cagr_with_costs*100:.2f}%")
print(f"  Final value with costs: ${bh_value_with_costs:,.2f}")

# Test 7: HMA filter with shorter period (100 instead of 200)
print("\n" + "="*60)
print("TEST 7: SuperTrend (10,3) + HMA(100) filter")
print("="*60)
df_st, _ = compute_supertrend(df_raw, period=10, multiplier=3.0)
df_st["HMA"] = compute_hma(df_st["Close"], period=100)
df_st["MA_Filter"] = df_st["Close"] > df_st["HMA"]
df_st["ADX_Filter"] = True
df_st["RSI_Filter"] = True

engine = BacktestEngine(df_st)
trades, equity, benchmark = engine.run(
    long_only=True, stop_loss_pct=0.08, take_profit_pct=0.20,
    commission_bps=10.0, slippage_bps=5.0, position_sizing_mode="fixed_fraction"
)
rm = RiskManager(trades, equity)
metrics = rm.calculate_metrics()
closed = [t for t in trades if t.is_closed]
print(f"  CAGR: {metrics['CAGR']*100:.2f}% vs BH: {bh_cagr*100:.2f}%")
print(f"  Trades: {len(closed)} | Time in market: {sum((t.exit_date - t.entry_date).days for t in closed if t.exit_date) / (years*365)*100:.1f}%")

# Test 8: Always invested - flip between long and cash based on SuperTrend (no filter)
print("\n" + "="*60)
print("TEST 8: SuperTrend (10,3) - Always long when Trend=1, Cash when Trend=-1 (no filters)")
print("="*60)
df_st, _ = compute_supertrend(df_raw, period=10, multiplier=3.0)
df_st["MA_Filter"] = True
df_st["ADX_Filter"] = True
df_st["RSI_Filter"] = True

engine = BacktestEngine(df_st)
trades, equity, benchmark = engine.run(
    long_only=True, stop_loss_pct=0.0, take_profit_pct=0.0,
    commission_bps=10.0, slippage_bps=5.0, position_sizing_mode="fixed_fraction"
)
rm = RiskManager(trades, equity)
metrics = rm.calculate_metrics()
closed = [t for t in trades if t.is_closed]
print(f"  CAGR: {metrics['CAGR']*100:.2f}% vs BH: {bh_cagr*100:.2f}%")
print(f"  Trades: {len(closed)} | Time in market: {sum((t.exit_date - t.entry_date).days for t in closed if t.exit_date) / (years*365)*100:.1f}%")
print(f"  Max DD: {metrics['Max Drawdown']*100:.2f}%")

# Test 9: Same as Test 8 but with 200 SMA filter (not HMA)
print("\n" + "="*60)
print("TEST 9: SuperTrend (10,3) + SMA(200) filter")
print("="*60)
df_st, _ = compute_supertrend(df_raw, period=10, multiplier=3.0)
df_st["SMA200"] = df_st["Close"].rolling(200).mean()
df_st["MA_Filter"] = df_st["Close"] > df_st["SMA200"]
df_st["ADX_Filter"] = True
df_st["RSI_Filter"] = True

engine = BacktestEngine(df_st)
trades, equity, benchmark = engine.run(
    long_only=True, stop_loss_pct=0.0, take_profit_pct=0.0,
    commission_bps=10.0, slippage_bps=5.0, position_sizing_mode="fixed_fraction"
)
rm = RiskManager(trades, equity)
metrics = rm.calculate_metrics()
closed = [t for t in trades if t.is_closed]
print(f"  CAGR: {metrics['CAGR']*100:.2f}% vs BH: {bh_cagr*100:.2f}%")
print(f"  Trades: {len(closed)} | Time in market: {sum((t.exit_date - t.entry_date).days for t in closed if t.exit_date) / (years*365)*100:.1f}%")

print("\n" + "="*60)
print("SUMMARY: Buy & Hold CAGR = 18.52%")
print("="*60)