# tests/test_presentation.py
import numpy as np
import pandas as pd
import pytest

from src.presentation import (
    sort_strategy_table,
    build_allocation_summary,
    format_strategy_display,
    format_rank,
    format_percent,
    format_currency,
    format_number,
    format_boolean,
)


def test_sort_strategy_table_rank_then_momentum_then_ticker():
    df = pd.DataFrame({
        "XTB_Ticker": ["BTCE", "SXR8", "XEON", "EXSA", "LCUJ"],
        "Rank": [np.nan, 1.0, np.nan, 3.0, 2.0],
        "Momentum_Score": [25.0, 15.5, np.nan, 10.2, 12.3],
    })
    out = sort_strategy_table(df)
    assert out["XTB_Ticker"].tolist() == ["SXR8", "LCUJ", "EXSA", "BTCE", "XEON"]


def test_build_allocation_summary_ranked_first_cash_last():
    df = pd.DataFrame({
        "XTB_Ticker": ["SXR8", "LCUJ", "XEON"],
        "Name": ["S&P", "Japan", "Cash"],
        "Rank": [1.0, 2.0, np.nan],
        "In_Top_4": [True, True, False],
        "Allocation_EUR": [3500.0, 3500.0, 7000.0],
    })
    out = build_allocation_summary(df)
    assert out.iloc[-1]["XTB Ticker"] == "XEON"


def test_format_strategy_display_includes_value_date_column():
    df = pd.DataFrame(
        {
            "Group": ["Core"],
            "Name": ["S&P 500"],
            "XTB_Ticker": ["SXR8"],
            "ISIN": ["IE00B5BMR087"],
            "Data_Symbol": ["SXR8.DE"],
            "Data_Source": ["stooq:SXR8.DE"],
            "Value_Date": ["2026-03-09"],
            "Price_Timestamp": ["2026-03-09 10:45"],
            "Price_Mode": ["Live 15m"],
            "Fresh": [True],
            "Price": [100.0],
            "Return_1M": [1.0],
            "Return_3M": [2.0],
            "Return_6M": [3.0],
            "SMA200": [95.0],
            "Traffic_Light": ["GREEN"],
            "Momentum_Score": [2.2],
            "Rank": [1.0],
            "In_Top_4": [True],
            "Allocation_EUR": [3500.0],
        }
    )

    out = format_strategy_display(df)

    assert "Value Date" in out.columns
    assert out.iloc[0]["Value Date"] == "2026-03-09"
    assert out.iloc[0]["Price Timestamp"] == "2026-03-09 10:45"
    assert out.iloc[0]["Price Mode"] == "Live 15m"
    assert out.iloc[0]["Fresh?"] == True


@pytest.mark.parametrize(
    "fn,val,expected",
    [
        (format_rank, 1.0, "1"),
        (format_rank, np.nan, "-"),
        (format_percent, 10.5, "+10.50%"),
        (format_percent, -5.25, "-5.25%"),
        (format_currency, 3500.0, "3,500.00 EUR"),
        (format_number, 1234.567, "1,234.57"),
        (format_boolean, True, "Yes"),
        (format_boolean, False, "No"),
    ],
)
def test_formatters_parametrized(fn, val, expected):
    assert fn(val) == expected
