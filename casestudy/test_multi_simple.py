import pandas as pd
import numpy as np
from src.data_loader import DataLoader
from src.indicators import compute_supertrend, compute_hma, compute_adx, compute_rsi
from src.backtest_engine import BacktestEngine, Trade
from src.risk_manager import RiskManager

tickers = ["QQQ", "TLT", "VNQ", "GLD"]
start_date = "2010-01-01"
end_date = "2024-12-31"
interval = "1d"

loader = DataLoader()
data = {}
for ticker in tickers:
    df = loader.fetch_data(ticker, start_date, end_date, interval, refresh=False)
    data[ticker] = df

# Common index
common_index = None
for ticker, df in data.items():
    if common_index is None:
        common_index = df.index
    else:
        common_index = common_index.intersection(df.index)
common_index = common_index.sort_values()

for ticker in tickers:
    data[ticker] = data[ticker].reindex(common_index).ffill()

years = (common_index[-1] - common_index[0]).days / 365.25

# Benchmark: Equal weight monthly rebalance
bench_equity = pd.Series(0.0, index=common_index)
bench_equity.iloc[0] = 100000.0
bench_shares = {t: 0.0 for t in tickers}
for t in tickers:
    bench_shares[t] = 25000.0 / data[t].loc[common_index[0], "Close"]

for i in range(1, len(common_index)):
    date = common_index[i]
    prev_date = common_index[i-1]
    val = sum(bench_shares[t] * data[t].loc[date, "Close"] for t in tickers)
    bench_equity.iloc[i] = val
    # Monthly rebalance
    if date.month != prev_date.month:
        for t in tickers:
            bench_shares[t] = (val * 0.25) / data[t].loc[date, "Close"]

bh_cagr = (bench_equity.iloc[-1] / bench_equity.iloc[0]) ** (1.0 / years) - 1.0

print(f"Benchmark (Monthly Rebal): CAGR = {bh_cagr*100:.2f}%")

# ============================================================
# STRATEGY 1: Pure SuperTrend (no filters)
# ============================================================
print("\n" + "="*60)
print("STRATEGY 1: Pure SuperTrend (10, 3) - No Filters")
print("="*60)

indicators = {}
for ticker in tickers:
    df_st, _ = compute_supertrend(data[ticker], period=10, multiplier=3.0)
    indicators[ticker] = df_st

cash = 100000.0
positions = {t: 0.0 for t in tickers}
entry_prices = {t: 0.0 for t in tickers}
entry_dates = {t: None for t in tickers}
all_trades = []
equity_curve = pd.Series(0.0, index=common_index)
equity_curve.iloc[0] = 100000.0

comm = 10.0 / 10000.0
slip = 5.0 / 10000.0

for i in range(1, len(common_index)):
    date = common_index[i]

    # Mark to market
    portfolio_value = cash
    for t in tickers:
        portfolio_value += positions[t] * indicators[t].loc[date, "Close"]
    equity_curve.iloc[i] = portfolio_value

    target_per_ticker = portfolio_value * 0.25

    for ticker in tickers:
        df = indicators[ticker]
        close = df.loc[date, "Close"]
        trend = df.loc[date, "Trend"]
        prev_trend = df.loc[common_index[i-1], "Trend"]

        pos = positions[ticker]

        # EXIT
        if pos > 0 and trend == -1:
            exit_price = close * (1 - slip)
            cash += pos * exit_price * (1 - comm)
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

        # ENTRY
        elif pos == 0 and trend == 1 and prev_trend == -1:
            entry_price = close * (1 + slip)
            max_shares = target_per_ticker / (entry_price * (1 + comm))
            cash -= max_shares * entry_price * (1 + comm)
            positions[ticker] = max_shares
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

# Analyze
trade_objects = []
for t in all_trades:
    tr = Trade(entry_date=t["entry_date"], entry_price=t["entry_price"],
               exit_date=t["exit_date"], exit_price=t["exit_price"],
               direction="Long", pnl_pct=t["pnl_pct"], exit_reason=t["reason"], is_closed=True)
    trade_objects.append(tr)

rm = RiskManager(trade_objects, equity_curve)
metrics = rm.calculate_metrics()
strat_cagr = metrics['CAGR']

print(f"Strategy CAGR: {strat_cagr*100:.2f}% (vs BH {bh_cagr*100:.2f}%)")
print(f"Final Value: ${equity_curve.iloc[-1]:,.2f} (vs BH ${bench_equity.iloc[-1]:,.2f})")
print(f"Max DD: {metrics['Max Drawdown']*100:.2f}%")
print(f"Sharpe: {metrics['Sharpe Ratio']:.2f}")
print(f"Total Trades: {len(trade_objects)}")
print(f"Win Rate: {metrics['Win Rate']*100:.1f}%")

# By ticker
for t in tickers:
    tt = [tr for tr in all_trades if tr["ticker"] == t]
    if tt:
        wins = [x for x in tt if x["pnl_pct"] > 0]
        print(f"  {t}: {len(tt)} trades, {len(wins)} wins, avg={np.mean([x['pnl_pct'] for x in tt])*100:.2f}%")

# Benchmark DD
bench_dd = (bench_equity - bench_equity.cummax()) / bench_equity.cummax()
print(f"Benchmark Max DD: {bench_dd.min()*100:.2f}%")

# ============================================================
# STRATEGY 2: SuperTrend + ONLY HMA200 filter
# ============================================================
print("\n" + "="*60)
print("STRATEGY 2: SuperTrend + HMA200 Filter Only")
print("="*60)

indicators = {}
for ticker in tickers:
    df_st, _ = compute_supertrend(data[ticker], period=10, multiplier=3.0)
    df_st["HMA"] = compute_hma(df_st["Close"], period=200)
    df_st["MA_Filter"] = df_st["Close"] > df_st["HMA"]
    indicators[ticker] = df_st

cash = 100000.0
positions = {t: 0.0 for t in tickers}
entry_prices = {t: 0.0 for t in tickers}
entry_dates = {t: None for t in tickers}
all_trades = []
equity_curve = pd.Series(0.0, index=common_index)
equity_curve.iloc[0] = 100000.0

for i in range(1, len(common_index)):
    date = common_index[i]
    portfolio_value = cash
    for t in tickers:
        portfolio_value += positions[t] * indicators[t].loc[date, "Close"]
    equity_curve.iloc[i] = portfolio_value
    target_per_ticker = portfolio_value * 0.25

    for ticker in tickers:
        df = indicators[ticker]
        close = df.loc[date, "Close"]
        trend = df.loc[date, "Trend"]
        prev_trend = df.loc[common_index[i-1], "Trend"]
        ma_ok = df.loc[date, "MA_Filter"]

        pos = positions[ticker]

        if pos > 0 and trend == -1:
            exit_price = close * (1 - slip)
            cash += pos * exit_price * (1 - comm)
            if entry_prices[ticker] > 0:
                pnl = (exit_price - entry_prices[ticker]) / entry_prices[ticker]
                all_trades.append({"ticker": ticker, "entry_date": entry_dates[ticker], "exit_date": date,
                                 "entry_price": entry_prices[ticker], "exit_price": exit_price, "pnl_pct": pnl, "reason": "Signal"})
            positions[ticker] = 0.0; entry_prices[ticker] = 0.0; entry_dates[ticker] = None
        elif pos == 0 and trend == 1 and prev_trend == -1 and ma_ok:
            entry_price = close * (1 + slip)
            max_shares = target_per_ticker / (entry_price * (1 + comm))
            cash -= max_shares * entry_price * (1 + comm)
            positions[ticker] = max_shares
            entry_prices[ticker] = entry_price; entry_dates[ticker] = date

for ticker in tickers:
    if positions[ticker] > 0:
        close = indicators[ticker].loc[common_index[-1], "Close"]
        exit_price = close * (1 - slip)
        cash += positions[ticker] * exit_price * (1 - comm)
        if entry_prices[ticker] > 0:
            pnl = (exit_price - entry_prices[ticker]) / entry_prices[ticker]
            all_trades.append({"ticker": ticker, "entry_date": entry_dates[ticker], "exit_date": common_index[-1],
                             "entry_price": entry_prices[ticker], "exit_price": exit_price, "pnl_pct": pnl, "reason": "End"})
        positions[ticker] = 0.0
equity_curve.iloc[-1] = cash

trade_objects = [Trade(entry_date=t["entry_date"], entry_price=t["entry_price"],
              exit_date=t["exit_date"], exit_price=t["exit_price"],
              direction="Long", pnl_pct=t["pnl_pct"], exit_reason=t["reason"], is_closed=True) for t in all_trades]
rm = RiskManager(trade_objects, equity_curve)
metrics = rm.calculate_metrics()
strat_cagr = metrics['CAGR']

print(f"Strategy CAGR: {strat_cagr*100:.2f}% (vs BH {bh_cagr*100:.2f}%)")
print(f"Final Value: ${equity_curve.iloc[-1]:,.2f}")
print(f"Max DD: {metrics['Max Drawdown']*100:.2f}%")
print(f"Sharpe: {metrics['Sharpe Ratio']:.2f}")
print(f"Total Trades: {len(trade_objects)}")
print(f"Win Rate: {metrics['Win Rate']*100:.1f}%")
for t in tickers:
    tt = [tr for tr in all_trades if tr["ticker"] == t]
    if tt:
        wins = [x for x in tt if x["pnl_pct"] > 0]
        print(f"  {t}: {len(tt)} trades, {len(wins)} wins, avg={np.mean([x['pnl_pct'] for x in tt])*100:.2f}%")

# ============================================================
# STRATEGY 3: QQQ-only SuperTrend, others Buy & Hold
# ============================================================
print("\n" + "="*60)
print("STRATEGY 3: QQQ Trend Following, TLT/VNQ/GLD Buy & Hold")
print("="*60)

# QQQ with SuperTrend
df_qqq, _ = compute_supertrend(data["QQQ"], period=10, multiplier=3.0)
df_qqq["HMA"] = compute_hma(df_qqq["Close"], period=200)
df_qqq["MA_Filter"] = df_qqq["Close"] > df_qqq["HMA"]

cash = 100000.0
qqq_pos = 0.0
qqq_entry = 0.0
qqq_entry_date = None
all_trades = []
equity_curve = pd.Series(0.0, index=common_index)
equity_curve.iloc[0] = 100000.0

# Fixed positions for TLT, VNQ, GLD
tlt_shares = 25000.0 / data["TLT"].loc[common_index[0], "Close"]
vnq_shares = 25000.0 / data["VNQ"].loc[common_index[0], "Close"]
gld_shares = 25000.0 / data["GLD"].loc[common_index[0], "Close"]

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
    ma_ok = df_qqq.loc[date, "MA_Filter"]

    # EXIT QQQ
    if qqq_pos > 0 and trend == -1:
        exit_price = close * (1 - slip)
        cash += qqq_pos * exit_price * (1 - comm)
        if qqq_entry > 0:
            pnl = (exit_price - qqq_entry) / qqq_entry
            all_trades.append({"ticker": "QQQ", "entry_date": qqq_entry_date, "exit_date": date,
                             "entry_price": qqq_entry, "exit_price": exit_price, "pnl_pct": pnl, "reason": "Signal"})
        qqq_pos = 0.0; qqq_entry = 0.0; qqq_entry_date = None

    # ENTRY QQQ
    elif qqq_pos == 0 and trend == 1 and prev_trend == -1 and ma_ok:
        entry_price = close * (1 + slip)
        max_shares = target_qqq / (entry_price * (1 + comm))
        cash -= max_shares * entry_price * (1 + comm)
        qqq_pos = max_shares
        qqq_entry = entry_price; qqq_entry_date = date

# Final
if qqq_pos > 0:
    close = df_qqq.loc[common_index[-1], "Close"]
    exit_price = close * (1 - slip)
    cash += qqq_pos * exit_price * (1 - comm)
    if qqq_entry > 0:
        pnl = (exit_price - qqq_entry) / qqq_entry
        all_trades.append({"ticker": "QQQ", "entry_date": qqq_entry_date, "exit_date": common_index[-1],
                         "entry_price": qqq_entry, "exit_price": exit_price, "pnl_pct": pnl, "reason": "End"})
    qqq_pos = 0.0

# Add final value of buy & hold positions
final_val = cash
final_val += tlt_shares * data["TLT"].loc[common_index[-1], "Close"]
final_val += vnq_shares * data["VNQ"].loc[common_index[-1], "Close"]
final_val += gld_shares * data["GLD"].loc[common_index[-1], "Close"]
equity_curve.iloc[-1] = final_val

trade_objects = [Trade(entry_date=t["entry_date"], entry_price=t["entry_price"],
              exit_date=t["exit_date"], exit_price=t["exit_price"],
              direction="Long", pnl_pct=t["pnl_pct"], exit_reason=t["reason"], is_closed=True) for t in all_trades]
rm = RiskManager(trade_objects, equity_curve)
metrics = rm.calculate_metrics()
strat_cagr = metrics['CAGR']

print(f"Strategy CAGR: {strat_cagr*100:.2f}% (vs BH {bh_cagr*100:.2f}%)")
print(f"Final Value: ${final_val:,.2f}")
print(f"Max DD: {metrics['Max Drawdown']*100:.2f}%")
print(f"Sharpe: {metrics['Sharpe Ratio']:.2f}")
print(f"QQQ Trades: {len(trade_objects)}")
print(f"QQQ Win Rate: {metrics['Win Rate']*100:.1f}%")
for t in all_trades:
    print(f"  {t['entry_date'].date()} -> {t['exit_date'].date()}: {t['pnl_pct']*100:.2f}% ({t['reason']})")
