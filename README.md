# Global Regime Rotator

A Streamlit app for evaluating and backtesting the "Global Regime Rotator" ETF momentum strategy.

## Features

### Current Evaluation
- Fetches fresh ETF prices from Stooq/Yahoo Finance with multi-symbol fallback
- Supports three current-evaluation modes: Weekly Close, Actual Day, and Live Preview (15m)
- Recalculates momentum score intraday with a fresh 15-minute price when available, falling back to last close otherwise
- Shows row-level value date, price timestamp, price mode, and freshness
- Allows configurable total allocation in EUR for the current evaluation table
- Configurable portfolio profiles with profile switcher logic dynamically adapting the UI
- Traffic light system: GREEN (Price > SMA200) = eligible, RED = forbidden
- Allocates to top 4 eligible assets by momentum score
- Daily disk caching with provider+symbol isolation

### Backtest (NEW)
- Historical simulation with weekly signals and biweekly execution
- Built-in data availability overlap overview checking
- Date constraint bounding validation so out of bounds fetches do not crash execution
- Weekly monitoring signals (computed every Friday close)
- Biweekly execution gate (trades allowed every 14 days, Monday-aligned)
- Transaction cost model with commission and slippage
- Modern lightweight dark theme UI with Altair charting tooltips
- Hoverable performance metrics tooltips: CAGR, Sharpe, Max Drawdown, Calmar
- Equity curve and drawdown visualization
- Execution and signal log exports

## Quick Start

```bash
# Option 1: Use bootstrap script (recommended)
./scripts/bootstrap.sh

# Option 2: Manual setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Running Tests

```bash
source venv/bin/activate
python -m pytest tests/ -v
```

### Generate Test Report Files

Create a timestamped test report and refresh `latest` report files:

```bash
./scripts/test_report.sh
```

Report files are written to:
- `reports/tests/latest.log`
- `reports/tests/latest.junit.xml`
- `reports/tests/pytest_<timestamp>.log`
- `reports/tests/pytest_<timestamp>.junit.xml`

## Project Structure

```
├── app.py                 # Streamlit UI (tabs: Current Evaluation, Backtest)
├── data/
│   ├── universe.yaml      # ETF universe (group, name, ISIN)
│   ├── symbols.yaml       # Symbol mappings for Stooq/Yahoo
│   ├── cache/             # Cached current price data
│   └── history_cache/     # Cached historical price data (parquet)
├── src/
│   ├── fetch.py           # Data fetching with fallback & caching
│   ├── calc.py            # SMA200, returns, scoring, allocation
│   ├── presentation.py    # UI formatting helpers
│   ├── history.py         # Historical data fetching & caching
│   ├── backtest.py        # Backtest engine (signals, execution, simulation)
│   └── perf.py            # Performance metrics computation
├── tests/
│   ├── test_calc.py       # Calculation tests
│   ├── test_fetch.py      # Fetch and cache tests
│   ├── test_presentation.py # Display formatting tests
│   └── test_backtest.py   # Backtest engine tests
├── scripts/
│   └── bootstrap.sh       # Setup and run script
└── requirements.txt
```

## Strategy Rules

1. **SMA200 Filter**: Only assets with Price > SMA200 are eligible (GREEN)
2. **Momentum Score**: `0.2 × R1M + 0.4 × R3M + 0.4 × R6M`
3. **Top 4 Selection**: Rank eligible assets by momentum, pick top 4
4. **Allocation**: 4 slots with configurable total allocation (default €14,000)
5. **Cash Parking**: Empty slots or leftover → XEON

## Backtest Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| Start/End Date | 3 years | Backtest period |
| Initial Capital | €14,000 | Starting portfolio value |
| Slots | 4 | Number of asset slots |
| Exec Frequency | 14 days | Days between rebalances |
| Commission | 5 bps | Per-trade commission |
| Slippage | 2 bps | Estimated slippage |
| Emergency Risk-Off | Off | Sell RED assets immediately (experimental) |

## Symbol Mappings

Edit `data/symbols.yaml` to configure data sources:

```yaml
# Simple string (single symbol)
SXR8:
  stooq: "SXR8.DE"
  yahoo: "SXR8.DE"

# List of symbols (tried in order until one succeeds)
BTCE:
  stooq: ["BTCE.DE", "BTCE.F"]
  yahoo: ["BTCE.DE", "BTCE-EUR.DE"]
```

## Adding New Assets & Profiles

1. Add to `data/universe.yaml`. The app ships with `Wide Portfolio` and `Narrow Portfolio`, and you can construct more profiles using the same schema:
   ```yaml
   default_profile: "core_global_rotator"
   profiles:
     core_global_rotator:
       label: "Core Global Rotator"
       assets:
         - group: "New Category"
           name: "Asset Name"
           xtb_ticker: "TICK"
           isin: "XX0000000000"
   ```

2. Add symbol mapping to `data/symbols.yaml`:
   ```yaml
   TICK:
     stooq: "TICK.DE"
     yahoo: "TICK.DE"
   ```

## License

MIT
