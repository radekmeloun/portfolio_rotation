import pytest
from datetime import datetime, date, timedelta
import pandas as pd

from src.fetch import filter_daily_rows
from src.calc import resolve_shared_as_of_date

def test_filter_daily_rows():
    today = datetime.now()
    yesterday = today - timedelta(days=1)
    
    df = pd.DataFrame(
        {"Close": [100, 105]},
        index=pd.DatetimeIndex([yesterday, today])
    )
    
    # Exclude today
    filtered_no_today = filter_daily_rows(df, include_current_day=False)
    assert len(filtered_no_today) == 1
    assert filtered_no_today.index[0].date() == yesterday.date()
    
    # Include today
    filtered_with_today = filter_daily_rows(df, include_current_day=True)
    assert len(filtered_with_today) == 2
    assert filtered_with_today.index[-1].date() == today.date()


def test_resolve_shared_as_of_date_intersection():
    df1 = pd.DataFrame(index=pd.DatetimeIndex(['2026-03-05', '2026-03-06', '2026-03-09']))
    df2 = pd.DataFrame(index=pd.DatetimeIndex(['2026-03-04', '2026-03-05', '2026-03-06']))
    frames = {"A": df1, "B": df2}
    
    resolved, err = resolve_shared_as_of_date(frames, "actual_day", today_override=date(2026, 3, 9))
    assert err is None
    assert resolved == pd.Timestamp('2026-03-09')


def test_resolve_shared_as_of_date_weekly_close():
    # 2026-03-06 is Friday
    df = pd.DataFrame(index=pd.DatetimeIndex(['2026-03-05', '2026-03-06', '2026-03-09']))
    frames = {"A": df}
    
    # If today is Monday 2026-03-09, weekly close should be prior week (Friday 2026-03-06)
    resolved, err = resolve_shared_as_of_date(frames, "weekly_close", today_override=date(2026, 3, 9))
    assert err is None
    assert resolved == pd.Timestamp('2026-03-06')
    
    # If today is Saturday 2026-03-07, weekly close should be just-finished week (Friday 2026-03-06)
    resolved, err = resolve_shared_as_of_date(frames, "weekly_close", today_override=date(2026, 3, 7))
    assert err is None
    assert resolved == pd.Timestamp('2026-03-06')


def test_resolve_shared_as_of_date_missing_data_before_boundary():
    df1 = pd.DataFrame(index=pd.DatetimeIndex(['2026-03-01']))
    df2 = pd.DataFrame(index=pd.DatetimeIndex(['2026-03-10']))
    frames = {"A": df1, "B": df2}
    
    resolved, err = resolve_shared_as_of_date(frames, "actual_day", today_override=date(2026, 3, 9))
    assert resolved is None
    assert err == "Asset B has no data on or before the evaluation date (2026-03-09)."
