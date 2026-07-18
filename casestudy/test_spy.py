import pandas as pd
import numpy as np
from src.data_loader import DataLoader
from src.indicators import compute_supertrend, compute_hma, compute_rsi, compute_adx
from src.backtest_engine import BacktestEngine
from src.risk_manager import RiskManager

# Load SPY data
loader = DataLoader()
df_raw = loader.fetch_data("SPY", start_date="2020-01-01", end_date="2026-06-01", interval="1d", refresh=False)
print(f"Loaded SPY: {len(df_raw)} bars")

years = (df_raw.index[-1] - df_raw.index[0]).days / 365.25

# Buy & Hold benchmark
initial = 100000.0
first_close = df_raw["Close"].iloc[0]
last_close = df_raw["Close"].iloc[-1]
bh_value = initial * (last_close / first_close)
bh_cagr = (bh_value / initial) ** (1.0 / years) - 1.0
print(f"SPY Buy & Hold CAGR: {bh_cagr*100:.2f}%")

# Test configurations
configs = [
    ("ST(10,3) no filter", {"period": 10, "mult": 3.0, "hma": None, "sl": 0.0, "tp": 0.0}),
    ("ST(10,3) + HMA(100)", {"period": 10, "mult": 3.0, "hma": 100, "sl": 0.0, "tp": 0.0}),
    ("ST(10,3) + HMA(200)", {"period": 10, "mult": 3.0, "hma": 200, "sl": 0.0, "tp": 0.0}),
    ("ST(10,3) + SMA(200)", {"period": 10, "mult": 3.0, "sma": 200, "sl": 0.0, "tp": 0.0}),
    ("ST(10,3) + RSI>50", {"period": 10, "mult": 3.0, "rsi": 50, "sl": 0.0, "tp": 0.0}),
    ("ST(14,3) no filter", {"period": 14, "mult": 3.0, "hma": None, "sl": 0.0, "tp": 0.0}),
    ("ST(20,3) no filter", {"period": 20, "mult": 3.0, "hma": None, "sl": 0.0, "tp": 0.0}),
    ("ST(10,3) with 8% SL / 20% TP", {"period": 10, "mult": 3.0, "hma": None, "sl": 0.08, "tp": 0.20}),
]

for name, cfg in configs:
    df_st, _ = compute_supertrend(df_raw, period=cfg["period"], multiplier=cfg["mult"])

    if cfg.get("hma"):
        df_st["HMA"] = compute_hma(df_st["Close"], period=cfg["hma"])
        df_st["MA_Filter"] = df_st["Close"] > df_st["HMA"]
    elif cfg.get("sma"):
        df_st[f"SMA{cfg['sma']}"] = df_st["Close"].rolling(cfg["sma"]).mean()
        df_st["MA_Filter"] = df_st["Close"] > df_st[f"SMA{cfg['sma']}"]
    elif cfg.get("rsi"):
        df_st["RSI"] = compute_rsi(df_st["Close"], period=14)
        df_st["RSI_Filter"] = df_st["RSI"] > cfg["rsi"]
        df_st["MA_Filter"] = True
    else:
        df_st["MA_Filter"] = True

    if "RSI_Filter" not in df_st.columns:
        df_st["RSI_Filter"] = True
    if "ADX_Filter" not in df_st.columns:
        df_st["ADX_Filter"] = True

    engine = BacktestEngine(df_st)
    trades, equity, benchmark = engine.run(
        long_only=True, slippage_bps=5.0, position_sizing_mode="fixed_fraction"
    )

    rm = RiskManager(trades, equity)
    metrics = rm.calculate_metrics()
    closed = [t for t in trades if t.is_closed]
    time_in_market = sum((t.exit_date - t.entry_date).days for t in closed if t.exit_date) / (years * 365) * 100

    print(f"{name:30s}: CAGR={metrics['CAGR']*100:6.2f}% vs BH={bh_cagr*100:5.2f}% | Trades={len(closed):2d} | TimeInMkt={time_in_market:5.1f}% | MaxDD={metrics['Max Drawdown']*100:6.2f}% | Sharpe={metrics['Sharpe Ratio']:.2f}")

# Test with stop loss
print("\n--- With 8% Stop Loss / 20% Take Profit ---")
for name, cfg in configs:
    if cfg["sl"] == 0.0:
        continue
    df_st, _ = compute_supertrend(df_raw, period=cfg["period"], multiplier=cfg["mult"])
    df_st["MA_Filter"] = True
    df_st["RSI_Filter"] = True
    df_st["ADX_Filter"] = True

    engine = BacktestEngine(df_st)
    trades, equity, benchmark = engine.run(
        long_only=True, stop_loss_pct=cfg["sl"], take_profit_pct=cfg["tp"],
        commission_bps=10.0, slippage_bps=5.0, position_sizing_mode="fixed_fraction"
    )

    rm = RiskManager(trades, equity)
    metrics = rm.calculate_metrics()
    closed = [t for t in trades if t.is_closed]
    time_in_market = sum((t.exit_date - t.entry_date).days for t in closed if t.exit_date) / (years * 365) * 100
    print(f"{name:30s}: CAGR={metrics['CAGR']*100:6.2f}% | Trades={len(closed):2d} | TimeInMkt={time_in_market:5.1f}% | MaxDD={metrics['Max Drawdown']*100:6.2f}%")