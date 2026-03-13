"""
Unit tests for backtest module.

Tests:
- Signal selection (top 4 GREEN, XEON fill)
- Execution gate (holdings change only on exec dates)
- Turnover and cost calculation
- Active signal selection (latest signal <= exec_date)
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.backtest import (
    BacktestParams,
    generate_signal_dates,
    generate_exec_dates,
    compute_weekly_signals,
    run_backtest,
    last_trading_date_on_or_before,
    next_trading_date_on_or_after,
    trading_day_shift,
    compute_metrics_for_asset,
)


# ============= Fixtures =============

@pytest.fixture
def sample_trading_index():
    """Create sample trading day index (weekdays only)."""
    # Generate business days for 2024
    return pd.bdate_range(start="2023-01-01", end="2024-12-31", freq="B")


@pytest.fixture
def sample_prices_df(sample_trading_index, rng):
    """Create sample price matrix for testing."""
    n = len(sample_trading_index)
    
    # Generate price series with some trending
    prices = {
        "SXR8": 100 * (1 + np.cumsum(rng.normal(0, 1, n) * 0.01)),  # Trending up
        "EXSA": 80 * (1 + np.cumsum(rng.normal(0, 1, n) * 0.012)),  # Volatile up
        "LCUJ": 60 * (1 + np.cumsum(rng.normal(0, 1, n) * 0.008)),  # Slow trend
        "BTCE": 50 * (1 + np.cumsum(rng.normal(0, 1, n) * 0.02)),   # Very volatile
        "XEON": np.full(n, 1.0),  # Cash - flat
    }
    
    return pd.DataFrame(prices, index=sample_trading_index)


# ============= Signal Date Generation Tests =============

class TestGenerateSignalDates:
    """Tests for weekly signal date generation."""
    
    def test_generates_weekly_dates(self, sample_trading_index):
        """Test that one signal per week is generated."""
        start = datetime(2024, 1, 1)
        end = datetime(2024, 3, 31)
        
        signal_dates = generate_signal_dates(sample_trading_index, start, end)
        
        # Should have roughly 13 weeks (Jan-Mar)
        assert len(signal_dates) >= 12
        assert len(signal_dates) <= 14
    
    def test_signal_dates_are_last_trading_day_of_week(self, sample_trading_index):
        """Test that signal dates are end-of-week trading days within the range."""
        start = datetime(2024, 2, 1)  # Avoid January week overlap issues
        end = datetime(2024, 2, 29)
        
        signal_dates = generate_signal_dates(sample_trading_index, start, end)
        
        for sd in signal_dates:
            # Should be a trading day
            assert sd in sample_trading_index
            
            # Should be Thursday or Friday typically (end of week)
            assert sd.weekday() >= 3  # Thursday=3, Friday=4
            
            # Verify it's within the requested range
            assert sd >= pd.Timestamp(start)
            assert sd <= pd.Timestamp(end)
    
    def test_respects_date_range(self, sample_trading_index):
        """Test that signal dates are within specified range."""
        start = datetime(2024, 6, 1)
        end = datetime(2024, 6, 30)
        
        signal_dates = generate_signal_dates(sample_trading_index, start, end)
        
        for sd in signal_dates:
            assert sd >= pd.Timestamp(start)
            assert sd <= pd.Timestamp(end)


# ============= Execution Date Generation Tests =============

class TestGenerateExecDates:
    """Tests for biweekly execution date generation."""
    
    def test_generates_biweekly_dates(self, sample_trading_index):
        """Test that execution dates are ~14 days apart."""
        start = datetime(2024, 1, 1)
        end = datetime(2024, 6, 30)
        
        exec_dates = generate_exec_dates(sample_trading_index, start, end, every_days=14)
        
        # Check spacing is approximately 14 days
        for i in range(1, len(exec_dates)):
            delta = (exec_dates[i] - exec_dates[i-1]).days
            # Should be 14 days +/- a few for holiday adjustments
            assert 10 <= delta <= 18
    
    def test_exec_dates_are_monday_aligned(self, sample_trading_index):
        """Test that execution dates target Mondays."""
        start = datetime(2024, 1, 1)
        end = datetime(2024, 3, 31)
        
        exec_dates = generate_exec_dates(sample_trading_index, start, end)
        
        # Most dates should be Monday (0) or Tuesday (1) if Monday is holiday
        monday_or_tuesday_count = sum(1 for d in exec_dates if d.weekday() <= 1)
        assert monday_or_tuesday_count >= len(exec_dates) * 0.8
    
    def test_exec_dates_are_trading_days(self, sample_trading_index):
        """Test that all execution dates are valid trading days."""
        start = datetime(2024, 1, 1)
        end = datetime(2024, 6, 30)
        
        exec_dates = generate_exec_dates(sample_trading_index, start, end)
        
        for ed in exec_dates:
            assert ed in sample_trading_index


# ============= Signal Computation Tests =============

class TestComputeWeeklySignals:
    """Tests for weekly signal computation."""
    
    def test_selects_top_4_green_assets(self, sample_prices_df):
        """Test that top 4 GREEN assets are selected."""
        start = datetime(2024, 6, 1)
        end = datetime(2024, 6, 30)
        
        signal_dates = generate_signal_dates(sample_prices_df.index, start, end)
        params = BacktestParams(slots=4, cash_ticker="XEON")
        
        signals = compute_weekly_signals(sample_prices_df, signal_dates, params)
        
        assert len(signals) > 0
        
        for signal in signals:
            assert len(signal.selected) == 4
    
    def test_fills_with_xeon_when_not_enough_candidates(self):
        """Test that XEON fills empty slots when fewer than 4 GREEN assets."""
        # Create prices where only 2 assets are GREEN (price > SMA200)
        dates = pd.bdate_range(start="2023-01-01", end="2024-06-30", freq="B")
        n = len(dates)
        
        # Asset A: strongly trending up (GREEN)
        a_prices = 100 * (1 + np.arange(n) * 0.001)
        # Asset B: trending up (GREEN)
        b_prices = 80 * (1 + np.arange(n) * 0.0008)
        # Asset C: trending down (RED)
        c_prices = 100 * (1 - np.arange(n) * 0.001)
        # Asset D: flat below SMA (RED) 
        d_prices = np.full(n, 50.0)
        
        prices_df = pd.DataFrame({
            "A": a_prices,
            "B": b_prices,
            "C": c_prices,
            "D": d_prices,
            "XEON": np.ones(n),
        }, index=dates)
        
        signal_dates = generate_signal_dates(prices_df.index, datetime(2024, 6, 1), datetime(2024, 6, 30))
        params = BacktestParams(slots=4, cash_ticker="XEON")
        
        signals = compute_weekly_signals(prices_df, signal_dates, params)
        
        for signal in signals:
            assert len(signal.selected) == 4
            # Should have XEON fills since only 2 GREEN assets
            xeon_count = signal.selected.count("XEON")
            assert xeon_count >= 2
    
    def test_ineligible_assets_excluded(self):
        """Test that assets with insufficient data are marked ineligible."""
        # Create prices with not enough history for one asset
        dates = pd.bdate_range(start="2024-01-01", end="2024-06-30", freq="B")
        n = len(dates)
        
        prices_df = pd.DataFrame({
            "A": 100 * (1 + np.cumsum(np.random.randn(n) * 0.01)),
            "B": np.concatenate([np.full(100, np.nan), np.random.randn(n-100) + 100]),  # Missing early data
            "XEON": np.ones(n),
        }, index=dates)
        
        signal_dates = generate_signal_dates(prices_df.index, datetime(2024, 6, 1), datetime(2024, 6, 30))
        params = BacktestParams(slots=4, cash_ticker="XEON")
        
        signals = compute_weekly_signals(prices_df, signal_dates, params)
        
        for signal in signals:
            if signal.signal_date < datetime(2024, 5, 20):  # B needs ~100 trading days
                assert "B" not in signal.selected
            elif "B" in signal.selected:
                assert signal.signal_date >= datetime(2024, 5, 20)


# ============= Backtest Simulation Tests =============

class TestRunBacktest:
    """Tests for backtest simulation."""
    
    def test_holdings_change_only_on_exec_dates(self, sample_prices_df):
        """Test that portfolio holdings only change on execution dates."""
        start = datetime(2024, 3, 1)
        end = datetime(2024, 6, 30)
        
        signal_dates = generate_signal_dates(sample_prices_df.index, start, end)
        exec_dates = generate_exec_dates(sample_prices_df.index, start, end, every_days=14)
        params = BacktestParams(slots=4)
        
        signals = compute_weekly_signals(sample_prices_df, signal_dates, params)
        equity_df, exec_log_df, holdings_df = run_backtest(
            sample_prices_df, signals, exec_dates, start, end, params
        )
        
        # Check that holdings don't change between exec dates
        exec_dates_set = set(exec_dates)
        prev_holdings = None
        
        for date, row in holdings_df.iterrows():
            current_holdings = tuple(row.values)
            
            if prev_holdings is not None and date not in exec_dates_set:
                # Holdings should be same as previous day if not exec date
                assert current_holdings == prev_holdings, f"Holdings changed on non-exec date {date}"
            
            prev_holdings = current_holdings
    
    def test_uses_latest_signal_before_exec_date(self, sample_prices_df):
        """Test that execution uses the most recent signal <= exec_date."""
        start = datetime(2024, 3, 1)
        end = datetime(2024, 6, 30)
        
        signal_dates = generate_signal_dates(sample_prices_df.index, start, end)
        exec_dates = generate_exec_dates(sample_prices_df.index, start, end, every_days=14)
        params = BacktestParams(slots=4)
        
        signals = compute_weekly_signals(sample_prices_df, signal_dates, params)
        equity_df, exec_log_df, holdings_df = run_backtest(
            sample_prices_df, signals, exec_dates, start, end, params
        )
        
        if not exec_log_df.empty:
            for _, row in exec_log_df.iterrows():
                exec_date = row["exec_date"]
                signal_used = row["signal_date_used"]
                
                # Signal date should be <= exec date
                assert signal_used <= exec_date
                
                # Should be the latest signal before exec
                later_signals = [s for s in signals if s.signal_date <= exec_date]
                if later_signals:
                    expected_signal = max(later_signals, key=lambda s: s.signal_date)
                    assert signal_used == expected_signal.signal_date
    

    
    def test_transaction_cost_applied(self, sample_prices_df):
        """Test that transaction costs are applied on rebalances."""
        start = datetime(2024, 3, 1)
        end = datetime(2024, 6, 30)
        
        signal_dates = generate_signal_dates(sample_prices_df.index, start, end)
        exec_dates = generate_exec_dates(sample_prices_df.index, start, end, every_days=14)
        params = BacktestParams(
            slots=4,
            commission_bps=10,
            slippage_bps=5,
            min_fee_eur=0,
        )
        
        signals = compute_weekly_signals(sample_prices_df, signal_dates, params)
        equity_df, exec_log_df, holdings_df = run_backtest(
            sample_prices_df, signals, exec_dates, start, end, params
        )
        
        if not exec_log_df.empty:
            # Check that costs are recorded
            total_costs = exec_log_df["cost_eur"].sum()
            assert total_costs >= 0
            
            # Check that costs reduce portfolio value
            for _, row in exec_log_df.iterrows():
                if row["turnover"] > 0:
                    assert row["cost_eur"] > 0
                    assert row["value_after"] < row["value_before"]


# ============= Calendar Helper Tests =============

class TestCalendarHelpers:
    """Tests for calendar helper functions."""
    
    def test_last_trading_date_on_or_before(self, sample_trading_index):
        """Test finding last trading date on or before a date."""
        # Test with a Saturday
        saturday = pd.Timestamp("2024-06-15")  # Should be a Saturday
        result = last_trading_date_on_or_before(sample_trading_index, saturday)
        
        assert result is not None
        assert result <= saturday
        assert result in sample_trading_index
    
    def test_next_trading_date_on_or_after(self, sample_trading_index):
        """Test finding next trading date on or after a date."""
        # Test with a Sunday
        sunday = pd.Timestamp("2024-06-16")  # Should be a Sunday
        result = next_trading_date_on_or_after(sample_trading_index, sunday)
        
        assert result is not None
        assert result >= sunday
        assert result in sample_trading_index
    
    def test_trading_day_shift(self, sample_trading_index):
        """Test shifting by trading days."""
        date = pd.Timestamp("2024-06-14")  # A Friday
        
        # Shift forward 1 trading day
        result = trading_day_shift(sample_trading_index, date, 1)
        assert result is not None
        assert result > date
        
        # Shift backward 1 trading day
        result = trading_day_shift(sample_trading_index, date, -1)
        assert result is not None
        assert result < date


# ============= Signal Logging Tests =============

class TestSignalLogging:
    """Tests for signal logging."""
    
    def test_weekly_signals_logged_even_when_not_executed(self, sample_prices_df):
        """Test that weekly signals are logged regardless of execution."""
        start = datetime(2024, 3, 1)
        end = datetime(2024, 6, 30)
        
        signal_dates = generate_signal_dates(sample_prices_df.index, start, end)
        exec_dates = generate_exec_dates(sample_prices_df.index, start, end, every_days=14)
        params = BacktestParams(slots=4)
        
        signals = compute_weekly_signals(sample_prices_df, signal_dates, params)
        
        # Should have more signals than executions
        assert len(signals) > len(exec_dates)
        
        # Each signal should have the required fields
        for signal in signals:
            assert signal.signal_date is not None
            assert len(signal.selected) == params.slots
            assert isinstance(signal.scores, dict)
            assert isinstance(signal.traffic_lights, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
