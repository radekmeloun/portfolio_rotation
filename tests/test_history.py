import pytest
from datetime import datetime
import pandas as pd
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.history import get_portfolio_coverage_window, normalize_index_tz

def test_get_portfolio_coverage_window(monkeypatch):
    universe = [
        {"xtb_ticker": "T1"},
        {"xtb_ticker": "T2"}
    ]
    
    # Create fake price series
    now = datetime.now()
    dates1 = pd.bdate_range(end=now, periods=100)
    dates2 = pd.bdate_range(end=now, periods=50)
    
    df1 = pd.DataFrame({"Close": [1.0]*100}, index=dates1)
    df2 = pd.DataFrame({"Close": [1.0]*50}, index=dates2)
    
    def mock_fetch_history(ticker, start_date, end_date, force_refresh):
        if ticker == "T1":
            return df1, "mock", "T1"
        return df2, "mock", "T2"
        
    import src.history
    monkeypatch.setattr(src.history, "fetch_history", mock_fetch_history)
    
    coverage = get_portfolio_coverage_window(universe)
    
    assert coverage["per_ticker_oldest"]["T1"] == dates1[0]
    assert coverage["per_ticker_oldest"]["T2"] == dates2[0]
    
    # common start should be max of the oldest dates
    assert coverage["common_start"] == max(dates1[0], dates2[0])


def test_normalize_index_tz_maps_utc_daily_bar_to_local_day():
    df = pd.DataFrame(
        {"Close": [100.0, 101.0]},
        index=pd.DatetimeIndex(
            [
                pd.Timestamp("2026-03-05 23:00:00+00:00"),
                pd.Timestamp("2026-03-08 23:00:00+00:00"),
            ]
        ),
    )

    normalized = normalize_index_tz(df)

    assert normalized.index.tolist() == [
        pd.Timestamp("2026-03-06 00:00:00"),
        pd.Timestamp("2026-03-09 00:00:00"),
    ]
