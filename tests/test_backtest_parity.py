# tests/test_backtest_parity.py
import pytest
import numpy as np
import pandas as pd
from datetime import datetime
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.backtest import (
    BacktestParams,
    generate_signal_dates,
    generate_exec_dates,
    compute_weekly_signals,
    run_backtest
)

def test_backtest_regression_parity():
    # Fixed seed for stable tests
    rng = np.random.default_rng(42)
    
    # Dates
    hist_start = datetime(2022, 1, 1)
    start_date = datetime(2023, 1, 1)
    end_date = datetime(2023, 12, 31)
    dates = pd.bdate_range(start=hist_start, end=end_date, freq="B")
    
    n_days = len(dates)
    
    # Synthetic price series with stable seed
    prices = {
        "A": 100 * (1 + np.cumsum(rng.normal(0.001, 0.015, n_days))),
        "B": 100 * (1 + np.cumsum(rng.normal(0.000, 0.020, n_days))),
        "C": 100 * (1 + np.cumsum(rng.normal(-0.001, 0.010, n_days))),
        "D": 100 * (1 + np.cumsum(rng.normal(0.002, 0.030, n_days))),
        "XEON": np.ones(n_days)
    }
    
    prices_df = pd.DataFrame(prices, index=dates)
    
    # Run full pipeline
    params = BacktestParams(
        initial_capital=14000.0,
        slots=4,
        commission_bps=5,
        slippage_bps=2,
        exec_frequency_days=14,
        cash_ticker="XEON"
    )
    
    signal_dates = generate_signal_dates(prices_df.index, start_date, end_date)
    exec_dates = generate_exec_dates(prices_df.index, start_date, end_date, every_days=14)
    signals = compute_weekly_signals(prices_df, signal_dates, params)
    
    equity_df, exec_log_df, holdings_df = run_backtest(
        prices_df, signals, exec_dates, start_date, end_date, params
    )
    
    # Assert stable final state outputs
    final_equity = equity_df["portfolio_value"].iloc[-1]
    
    # Total costs
    total_costs = exec_log_df["cost_eur"].sum() if not exec_log_df.empty else 0.0
    num_trades = len(exec_log_df)
    
    assert final_equity == pytest.approx(54844.128171709046, abs=1e-3)
    assert total_costs == pytest.approx(23.622423594258724, abs=1e-3)
    assert num_trades == 25
    
    equity_head = equity_df["portfolio_value"].head(5).tolist()
    assert equity_head == pytest.approx([14000.0, 14000.0, 14000.0, 14000.0, 14000.0], abs=1e-3)
    
    if not exec_log_df.empty:
        exec_head = exec_log_df.head(3)
        assert exec_head["turnover"].tolist() == pytest.approx([0.5, 0.0, 0.0], abs=1e-3)
        assert exec_head["cost_eur"].tolist() == pytest.approx([4.9, 0.0, 0.0], abs=1e-3)
        assert exec_head["value_after"].tolist() == pytest.approx([13995.100, 14201.291, 14138.345], abs=1e-3)
