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

# Calculate indicators
df_indicators, trend = compute_supertrend(df_raw, period=10, multiplier=3.0)
df_indicators["HMA"] = compute_hma(df_indicators["Close"], period=200)
df_indicators["MA_Filter"] = df_indicators["Close"] > df_indicators["HMA"]
df_indicators["ADX"] = compute_adx(df_indicators, period=14)
df_indicators["RSI"] = compute_rsi(df_indicators["Close"], period=14)
df_indicators["ADX_Filter"] = True
df_indicators["RSI_Filter"] = True

# Backtest
engine = BacktestEngine(df_indicators)
trades, equity, benchmark = engine.run(
    long_only=True,
    stop_loss_pct=0.08,
    take_profit_pct=0.20,
    commission_bps=10.0,
    slippage_bps=5.0,
    position_sizing_mode="fixed_fraction"
)

# Strategy metrics
rm = RiskManager(trades, equity)
metrics = rm.calculate_metrics()

print("\n=== Strategy Metrics ===")
for k, v in metrics.items():
    print(f"  {k}: {v}")

# Buy & Hold metrics
years = (equity.index[-1] - equity.index[0]).days / 365.25
bh_cagr = (benchmark.iloc[-1] / benchmark.iloc[0]) ** (1.0 / years) - 1.0
print(f"\n=== Buy & Hold (Benchmark) ===")
print(f"  CAGR: {bh_cagr*100:.2f}%")
print(f"  Final Value: ${benchmark.iloc[-1]:,.2f}")
print(f"  Strategy Final Value: ${equity.iloc[-1]:,.2f}")
print(f"  CAGR Gap: {(bh_cagr - metrics['CAGR'])*100:.2f}%")

# Trade stats
closed = [t for t in trades if t.is_closed]
print(f"\n=== Trade Stats ===")
print(f"  Total trades: {len(closed)}")
print(f"  Trades per year: {len(closed)/years:.2f}")
total_days_in_market = sum((t.exit_date - t.entry_date).days for t in closed if t.exit_date)
print(f"  Time in market: {total_days_in_market / (years*365)*100:.1f}%")

# Show trades
print("\n=== All Trades ===")
for t in closed:
    print(f"  {t.entry_date.date()} -> {t.exit_date.date()} | PnL: {t.pnl_pct*100:.2f}% | Reason: {t.exit_reason} | Days: {(t.exit_date - t.entry_date).days}")
