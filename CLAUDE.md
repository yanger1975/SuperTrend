# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---
## 1. Project Overview

SuperTrend is a Python‑based back‑testing framework focused on US equity ETFs (default `SPY`).  It stores historical OHLCV data locally in SQLite, calculates technical indicators, runs a back‑tester that supports long/short, stop‑loss, take‑profit, and commissions, and offers walk‑forward optimisation and Monte‑Carlo risk reporting.  The architecture is purpose‑built for rapid local experimentation and for production‑ready back‑tests.

The core public modules are:

| Module | Purpose |
| --- | --- |
| **src/storage.py** | SQLite wrapper that pre‑creates `price_history` and exposes `upsert_prices()` and `query_prices()`.
| **src/data_loader.py** | Uses `yfinance` to download data and serialises it via `SQLiteStorage`.
| **src/indicators.py** | Calculates moving averages (SuperTrend, HMA, ADX, RSI, etc.) and returns a dataframeenderror.
| **src/backtest_engine.py** | Orchestrates back‑testing, applying trade logic, position sizing, slippage, commission, and recording trades.
| **src/risk_manager.py** | Computes risk metrics: Ulcer Index, Expectancy, Sharpe, Sortino, Monte‑Carlo distributions.
| **src/optimizer.py** | Implements walk‑forward optimisation over a few hyper‑parameters and returns the best parameter set.

These modules interact through pandas `DataFrame` objects; no global state is stored except the SQLite file in `data/market_data.db`.

---
## 2. Environment & Dependencies

* Python 3.8+ (recommended 3.10).
* Runtime libraries listed in `requirements.txt`:
  ```text
  pandas
  numpy
  yfinance
 Humanities; plotly
  pytest
  ```
* Optionally `flake8` for linting if installed locally.

---
## 3. Common Commands

| Task | Command | Notes |
| --- | --- | --- |
| Install dependencies | `pip install -r requirements.txt` | Run before first use. |
| Run all tests | `python -m pytest tests/ -v` | Includes unit‑tests for storage, indicators, risk, optimizer, and back‑tester. |
| Run single test file | `python -m pytest tests/test_indicators.py` | Or any file path. |
| lint (optional) | `flake8 src/ tests/` | Requires flake8 installed. |
| Execute interactive notebook | `python -m notebook SuperTrend_Backtester.ipynb페` | Jupyter must be installed. |
| Load data for a ticker | `python - <<'PY'
from src.data_loader import DataLoader
DataLoader().download_and_store(['SPY'], '1d')
PY` | Helper snippet; the loader writes to SQLite automatically. |
| Run a single back‑test | `python src/backtest_engine.py --ticker SPY` | The CLI is minimal; see code for available flags. |

---
## 4. Configuration via Code

All runtime parameters are exposed as keyword arguments to the corresponding classes:

```python
engine = BackTestEngine(ticker='SPY', interval='1d', long_only=True, commission_bps=10.0, slippage_bps=5.0)
result = engine.run(start='2020-01-01', end='2023-01-01')
```

The `insert` function for parameterisation** is straightforward—consult docstrings of `BackTestEngine`, `Optimizer`, and `RiskManager` for their signatures.

---
## 5. Architectural Highlights

1. **DataDidn't**
   * `DataLoader` pulls data using `yfinance`, ensures timezone consistency, and supplies the dataframe to `SQLiteStorage.upsert_prices()`.  The SQLite schema guarantees upserts per `(ticker, interval, datetime)`.
2. **Feature Engineering**
   * `indicators.py` implements a lightweight library ziy; each indicator returns a `pd.Series` that can be appended to the price history.
3. **Execution Engine**
   * `BackTestEngine` iterates over the dataframe, applies rules (long/short, stop‑loss, TP, commission, slippage) and emits a `TradeReport` dataclass.
4. **Risk & Statistics**
   * ` أنّrisk_manager.py` aggregates daily equity curves to compute leverage, draw‑down, ulcer index, etc.  It also supports Monte‑Carlo simulation of the final equity curve.
5. **Optimisation**
   * `Optimizer` runs walk‑forward splits, forwards each parameter set through a back‑test, collects objective metrics, and returns agraphics.

These layers are intentionally decoupled; you may swap the storage backend or replace the indicator set without touching the engine.

---
## 6. Test‑Driven Guidance

The test suite (`tests/`) covers:

* `test_storage.py` – verifies SQLite CRUD.
* suite for ` Gemini-indicators`.
* back‑test logic correctness.
* risk metric correctness.

When adding new functionality, add a new test under `tests/` following the pattern and run `pytest`.

---
## 7. Helpful Notes

* The SQLite file lives in `data/market_data.db`.  The file is version‑controlled for minimal dataset but is usually rebuilt on first run.
* If you rerun a script that accesses the database, ensure you commit before closing or close the connection after completing the query.
* For large data downloads, consider setting the environment variable `YFINANCE_USER_SCRAPER` to reduce request rate.

---
## 8. Known Limitations

* The framework assumes daily or intraday frequency in `yfinance` and may mis‑handle non‑trading days.
* Only back‑testing for a single instrument is fully supported; multi‑instrument strategies need manual extension.
* No production‑grade logging; use `print` or `logging` as needed.

---
## 9. Where to Ask for Help

Use the issue tracker or pull request discussion on GitHub for design questions or bugs.  For environment or package issues, check the `README.md` and the job‑runner logs.

---
## 10. Sample Usage

```bash
# 1. Install
pip install -r requirements.txt

# 2. Load data
python - <<'PY'
from src.data_loader import DataLoader
DataLoader().download_and_store(['SPY', 'QQQ'], '1d')
PY

# 3. Run a back‑test in interactive mode
python - <<'PY'
from src.backtest_engine import BackTestEngine
engine = BackTestEngine(ticker='SPY', long_only=False)
print(engine.run(start='2010-01-01', end='2020-12-31'))
PY fc
```
