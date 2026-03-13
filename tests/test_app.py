import pandas as pd

import app


def test_build_freshness_message_actual_day_uses_value_dates():
    df = pd.DataFrame(
        {
            "XTB_Ticker": ["A", "B"],
            "Value_Date": ["2026-03-09", "2026-03-06"],
            "Price_Mode": ["Daily Close", "Daily Close"],
            "Fresh": [False, False],
        }
    )

    message = app.build_freshness_message(df, pd.Timestamp("2026-03-09"), "actual_day")

    assert message == (
        "1/2 assets use `2026-03-09`. "
        "Earlier last available closes are used for: B (2026-03-06, Daily Close)"
    )


def test_build_freshness_message_live_preview_counts_only_fresh_live_rows():
    df = pd.DataFrame(
        {
            "XTB_Ticker": ["A", "B"],
            "Value_Date": ["2026-03-09", "2026-03-09"],
            "Price_Mode": ["Live 15m", "Daily Close"],
            "Fresh": [True, False],
        }
    )

    message = app.build_freshness_message(df, pd.Timestamp("2026-03-09"), "live_preview_15m")

    assert message == (
        "1/2 assets use fresh `Live 15m` prices for `2026-03-09`. "
        "Daily-close fallback is used for: B (2026-03-09, Daily Close)"
    )
