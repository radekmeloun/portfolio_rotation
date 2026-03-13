# tests/test_calc.py
import numpy as np
import pandas as pd
import pytest
from datetime import date
from types import SimpleNamespace

from src.calc import (
    calculate_sma200,
    get_latest_price,
    calculate_return,
    calculate_returns,
    calculate_momentum_score,
    determine_traffic_light,
    rank_assets,
    calculate_allocation,
    process_asset,
    resolve_shared_as_of_date,
    DAYS_1M,
    DAYS_6M,
    SLOT_AMOUNT,
    NUM_SLOTS,
)


def test_sma200_constant_series():
    idx = pd.bdate_range(end="2024-01-01", periods=210)
    df = pd.DataFrame({"Close": [100.0] * len(idx)}, index=idx)
    assert calculate_sma200(df) == 100.0


@pytest.mark.parametrize(
    "period,expected",
    [(DAYS_1M, 0.0), (63, 0.0), (126, 0.0)],
)
def test_returns_constant(period, expected):
    idx = pd.bdate_range(end="2024-01-01", periods=260)
    df = pd.DataFrame({"Close": [100.0] * len(idx)}, index=idx)
    assert calculate_return(df, period) == expected


def test_return_insufficient_data():
    idx = pd.bdate_range(end="2024-01-01", periods=10)
    df = pd.DataFrame({"Close": [100.0] * len(idx)}, index=idx)
    assert calculate_return(df, DAYS_6M) is None


def test_return_uses_current_price_override_for_live_preview():
    idx = pd.bdate_range(end="2024-01-10", periods=30)
    df = pd.DataFrame({"Close": [100.0 + i for i in range(30)]}, index=idx)

    result = calculate_return(df, DAYS_1M, current_price_override=200.0)

    expected = ((200.0 - 108.0) / 108.0) * 100.0
    assert result == pytest.approx(round(expected, 2))


@pytest.mark.parametrize(
    "r1,r3,r6,expected",
    [
        (10.0, 20.0, 30.0, 22.0),
        (-10.0, -20.0, -30.0, -22.0),
        (10.0, -5.0, 15.0, 6.0),
        (0.0, 0.0, 0.0, 0.0),
    ],
)
def test_momentum_score_parametrized(r1, r3, r6, expected):
    assert calculate_momentum_score(r1, r3, r6) == expected


@pytest.mark.parametrize(
    "price,sma,expected",
    [
        (110.0, 100.0, "GREEN"),
        (90.0, 100.0, "RED"),
        (100.0, 100.0, "RED"),
        (None, 100.0, "N/A"),
        (100.0, None, "N/A"),
    ],
)
def test_traffic_light_parametrized(price, sma, expected):
    assert determine_traffic_light(price, sma) == expected


def test_ranking_and_allocation_invariants():
    df = pd.DataFrame({
        "XTB_Ticker": ["A", "B", "C", "XEON"],
        "Traffic_Light": ["GREEN", "RED", "GREEN", "GREEN"],
        "Momentum_Score": [50.0, 40.0, 30.0, None],
        "Rank": [1, None, 2, None],
        "is_cash": [False, False, False, True],
    })
    out = calculate_allocation(rank_assets(df))
    assert out["Allocation_EUR"].sum() == NUM_SLOTS * SLOT_AMOUNT
    assert out.loc[out["XTB_Ticker"] == "XEON", "Allocation_EUR"].iloc[0] >= 0


def test_allocation_uses_configured_total_allocation():
    df = pd.DataFrame({
        "XTB_Ticker": ["A", "B", "XEON"],
        "Traffic_Light": ["GREEN", "GREEN", "GREEN"],
        "Momentum_Score": [50.0, 40.0, None],
        "Rank": [1, 2, None],
        "is_cash": [False, False, True],
    })

    out = calculate_allocation(rank_assets(df), total_allocation_eur=20000.0)

    assert out["Allocation_EUR"].sum() == pytest.approx(20000.0)
    assert out.loc[out["XTB_Ticker"] == "A", "Allocation_EUR"].iloc[0] == pytest.approx(5000.0)
    assert out.loc[out["XTB_Ticker"] == "XEON", "Allocation_EUR"].iloc[0] == pytest.approx(10000.0)

def test_process_asset_slices_by_as_of_date():
    idx = pd.date_range(end="2024-01-10", periods=20, freq="B")
    df = pd.DataFrame({"Close": [100.0 + i for i in range(20)]}, index=idx)
    
    asset_info = {"group": "Test", "name": "Asset A", "isin": "XC123", "is_cash": False}
    
    # Process without as_of_date (uses full data)
    res_full = process_asset("A", df, "mock", "A", asset_info)
    
    # Process with as_of_date slicing
    res_sliced = process_asset("A", df, "mock", "A", asset_info, as_of_date="2024-01-05")
    
    assert res_full["Price"] == 119.0  # 100 + 19
    assert res_full["Value_Date"] == "2024-01-10"
    assert res_full["Fresh"] == False
    assert res_sliced["Price"] == 116.0  # 100 + 16 (on 5th, which is index 16 over business days)
    assert res_sliced["Value_Date"] == "2024-01-05"
    assert res_sliced["Fresh"] == True


def test_process_asset_uses_live_preview_snapshot():
    idx = pd.bdate_range(end="2024-01-10", periods=30)
    df = pd.DataFrame({"Close": [100.0 + i for i in range(30)]}, index=idx)
    asset_info = {"group": "Test", "name": "Asset A", "isin": "XC123", "is_cash": False}
    snapshot = SimpleNamespace(
        price=200.0,
        timestamp=pd.Timestamp("2024-01-10 10:45"),
        price_mode="Live 15m",
        fresh=True,
    )

    res = process_asset(
        "A",
        df,
        "mock",
        "A",
        asset_info,
        as_of_date="2024-01-10",
        live_price_snapshot=snapshot,
    )

    assert res["Price"] == 200.0
    assert res["Value_Date"] == "2024-01-10"
    assert res["Price_Timestamp"] == "2024-01-10 10:45"
    assert res["Price_Mode"] == "Live 15m"
    assert res["Fresh"] == True


def test_process_asset_live_preview_daily_fallback_is_not_fresh():
    idx = pd.bdate_range(end="2024-01-10", periods=30)
    df = pd.DataFrame({"Close": [100.0 + i for i in range(30)]}, index=idx)
    asset_info = {"group": "Test", "name": "Asset A", "isin": "XC123", "is_cash": False}
    snapshot = SimpleNamespace(
        price=129.0,
        timestamp=pd.Timestamp("2024-01-10"),
        price_mode="Daily Close",
        fresh=False,
    )

    res = process_asset(
        "A",
        df,
        "mock",
        "A",
        asset_info,
        as_of_date="2024-01-10",
        live_price_snapshot=snapshot,
    )

    assert res["Value_Date"] == "2024-01-10"
    assert res["Price_Mode"] == "Daily Close"
    assert res["Fresh"] == False


def test_resolve_shared_as_of_date_actual_day_uses_latest_intersection():
    frame_a = pd.DataFrame({"Close": [1.0, 2.0, 3.0]}, index=pd.to_datetime(["2026-03-04", "2026-03-05", "2026-03-06"]))
    frame_b = pd.DataFrame({"Close": [10.0, 11.0, 12.0, 13.0]}, index=pd.to_datetime(["2026-03-04", "2026-03-05", "2026-03-06", "2026-03-09"]))

    resolved, error = resolve_shared_as_of_date(
        {"A": frame_a, "B": frame_b},
        "actual_day",
        today_override=date(2026, 3, 9),
    )

    assert error is None
    assert resolved == pd.Timestamp("2026-03-09")


def test_resolve_shared_as_of_date_weekly_close_uses_last_closed_weekday():
    frame_a = pd.DataFrame({"Close": [1.0, 2.0, 3.0]}, index=pd.to_datetime(["2026-03-04", "2026-03-05", "2026-03-06"]))
    frame_b = pd.DataFrame({"Close": [10.0, 11.0, 12.0, 13.0]}, index=pd.to_datetime(["2026-03-04", "2026-03-05", "2026-03-06", "2026-03-09"]))

    resolved, error = resolve_shared_as_of_date(
        {"A": frame_a, "B": frame_b},
        "weekly_close",
        today_override=date(2026, 3, 9),
    )

    assert error is None
    assert resolved == pd.Timestamp("2026-03-06")


def test_resolve_shared_as_of_date_live_preview_matches_actual_day_boundary():
    frame_a = pd.DataFrame({"Close": [1.0, 2.0]}, index=pd.to_datetime(["2026-03-06", "2026-03-09"]))
    frame_b = pd.DataFrame({"Close": [10.0]}, index=pd.to_datetime(["2026-03-06"]))

    resolved, error = resolve_shared_as_of_date(
        {"A": frame_a, "B": frame_b},
        "live_preview_15m",
        today_override=date(2026, 3, 9),
    )

    assert error is None
    assert resolved == pd.Timestamp("2026-03-09")


def test_resolve_shared_as_of_date_returns_error_when_asset_has_no_data_before_boundary():
    frame_a = pd.DataFrame({"Close": [1.0]}, index=pd.to_datetime(["2026-03-04"]))
    frame_b = pd.DataFrame({"Close": [2.0]}, index=pd.to_datetime(["2026-03-05"]))

    resolved, error = resolve_shared_as_of_date(
        {"A": frame_a, "B": frame_b},
        "weekly_close",
        today_override=date(2026, 3, 2),
    )

    assert resolved is None
    assert error == "Asset A has no data on or before the evaluation date (2026-02-27)."
