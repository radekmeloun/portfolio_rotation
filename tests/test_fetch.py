# tests/test_fetch.py
from datetime import datetime, timedelta
import pandas as pd
import pytest

from src import fetch
from src.fetch import (
    LivePriceSnapshot,
    get_live_preview_snapshot,
    normalize_symbol_candidates,
    FetchStatus,
    get_cache_path,
    is_live_preview_fresh,
    normalize_daily_index,
    remove_today_bar,
)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("SXR8.DE", ["SXR8.DE"]),
        (["SXR8.DE", "SXR8.F"], ["SXR8.DE", "SXR8.F"]),
        ("", []),
        ("   ", []),
        (None, []),
        (["SXR8.DE", "", None], ["SXR8.DE"]),
        (123, []),
    ],
)
def test_normalize_symbol_candidates(value, expected):
    assert normalize_symbol_candidates(value) == expected


def test_fetch_status_notes_join():
    s = FetchStatus(xtb_ticker="T")
    s.add_note("A")
    s.add_note("B")
    assert s.notes_str() == "A; B"


def test_cache_key_isolation(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "CACHE_DIR", tmp_path)
    today = datetime.now().strftime("%Y-%m-%d")
    p1 = get_cache_path("stooq", "SXR8.DE", today)
    p2 = get_cache_path("yahoo", "SXR8.DE", today)
    assert p1 != p2


def test_provider_and_candidate_fallback(monkeypatch):
    tried = []

    def stooq_mock(symbol):
        tried.append(("stooq", symbol))
        return None if symbol == "A.BAD" else pd.DataFrame({"Close": [1.0] * 260},
                                                            index=pd.bdate_range(end=datetime.now(), periods=260))

    def yahoo_mock(symbol):
        tried.append(("yahoo", symbol))
        return pd.DataFrame({"Close": [1.0] * 260},
                            index=pd.bdate_range(end=datetime.now(), periods=260))

    monkeypatch.setattr(fetch, "PROVIDER_FETCHERS", {"stooq": stooq_mock, "yahoo": yahoo_mock})
    monkeypatch.setattr(fetch, "load_symbol_mappings", lambda: (
        {"TEST": {"stooq": ["A.BAD", "A.OK"], "yahoo": "Y.OK"}},
        ["stooq", "yahoo"]
    ))
    monkeypatch.setattr(fetch, "load_from_cache", lambda p, s: (None, None))
    monkeypatch.setattr(fetch, "save_to_cache", lambda *args, **kwargs: None)
    monkeypatch.setattr(fetch, "try_legacy_cache", lambda t: (None, None, None))

    result = fetch.get_price_data("TEST", force_refresh=True)
    assert result.df is not None
    assert result.status.provider == "stooq"
    assert result.status.symbol == "A.OK"
    assert ("stooq", "A.BAD") in tried and ("stooq", "A.OK") in tried


def test_all_fail_returns_data_missing(monkeypatch):
    monkeypatch.setattr(fetch, "PROVIDER_FETCHERS", {"stooq": lambda s: None, "yahoo": lambda s: None})
    monkeypatch.setattr(fetch, "load_symbol_mappings", lambda: (
        {"TEST": {"stooq": "X", "yahoo": "Y"}}, ["stooq", "yahoo"]
    ))
    monkeypatch.setattr(fetch, "load_from_cache", lambda p, s: (None, None))
    monkeypatch.setattr(fetch, "try_legacy_cache", lambda t: (None, None, None))

    result = fetch.get_price_data("TEST", force_refresh=True)
    assert result.df is None
    assert result.status.status == "DATA MISSING"

def test_remove_today_bar():
    today = datetime.now().date()
    # Create an index with dates leading up to today
    idx = pd.date_range(end=today, periods=5, freq="D")
    df = pd.DataFrame({"Close": [1.0, 2.0, 3.0, 4.0, 5.0]}, index=idx)
    
    # Original length is 5, ending on today
    assert len(df) == 5
    
    # After removal, length should be 4, and the last date should be strictly before today
    cleaned = remove_today_bar(df)
    assert len(cleaned) == 4
    assert cleaned.index[-1].date() < today
    
    # Should handle empty gracefully
    assert len(remove_today_bar(pd.DataFrame())) == 0
    assert remove_today_bar(None) is None


def test_normalize_daily_index_converts_utc_bar_to_local_trading_day():
    idx = pd.DatetimeIndex(
        [
            pd.Timestamp("2026-03-04 23:00:00+00:00"),
            pd.Timestamp("2026-03-08 23:00:00+00:00"),
        ]
    )
    df = pd.DataFrame({"Close": [100.0, 101.0]}, index=idx)

    normalized = normalize_daily_index(df)

    assert normalized.index.tolist() == [
        pd.Timestamp("2026-03-05 00:00:00"),
        pd.Timestamp("2026-03-09 00:00:00"),
    ]


@pytest.mark.parametrize(
    ("include_current_day", "expected_last_date"),
    [
        (False, "2026-03-06"),
        (True, "2026-03-09"),
    ],
)
def test_legacy_cache_respects_current_day_filter(monkeypatch, include_current_day, expected_last_date):
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 3, 9, 12, 0, 0, tzinfo=tz) if tz is not None else cls(2026, 3, 9, 12, 0, 0)

    legacy_df = pd.DataFrame(
        {"Close": [100.0, 101.0]},
        index=pd.DatetimeIndex(
            [
                pd.Timestamp("2026-03-05 23:00:00+00:00"),
                pd.Timestamp("2026-03-08 23:00:00+00:00"),
            ]
        ),
    )

    monkeypatch.setattr(fetch, "datetime", FrozenDateTime)
    monkeypatch.setattr(fetch, "PROVIDER_FETCHERS", {"stooq": lambda s: None})
    monkeypatch.setattr(fetch, "load_symbol_mappings", lambda: ({"TEST": {"stooq": "X"}}, ["stooq"]))
    monkeypatch.setattr(fetch, "load_from_cache", lambda p, s: (None, None))
    monkeypatch.setattr(fetch, "try_legacy_cache", lambda t: (legacy_df, "legacy", "LEGACY.TEST"))

    result = fetch.get_price_data("TEST", force_refresh=False, include_current_day=include_current_day)

    assert result.df is not None
    assert result.df.index[-1].strftime("%Y-%m-%d") == expected_last_date


def test_live_preview_snapshot_uses_fresh_intraday_quote(monkeypatch):
    daily_df = pd.DataFrame({"Close": [100.0, 101.0]}, index=pd.to_datetime(["2026-03-06", "2026-03-07"]))
    intraday_df = pd.DataFrame(
        {"Close": [102.0, 103.5]},
        index=pd.DatetimeIndex(
            [
                pd.Timestamp("2026-03-10 09:45:00", tz="Europe/Prague"),
                pd.Timestamp("2026-03-10 10:00:00", tz="Europe/Prague"),
            ]
        ),
    )

    monkeypatch.setattr(fetch, "load_symbol_mappings", lambda: ({"TEST": {"yahoo": "TEST.DE"}}, ["stooq", "yahoo"]))
    monkeypatch.setattr(fetch, "fetch_from_yahoo_intraday", lambda symbol, period="5d", interval="15m": intraday_df)
    monkeypatch.setattr(fetch, "is_live_preview_fresh", lambda ts: True)

    snapshot = get_live_preview_snapshot("TEST", daily_df, "stooq", "TEST.DE")

    assert snapshot.price == pytest.approx(103.5)
    assert snapshot.price_mode == "Live 15m"
    assert snapshot.fresh is True
    assert snapshot.source == "yahoo:TEST.DE"


def test_live_preview_snapshot_falls_back_to_daily_close_when_intraday_stale(monkeypatch):
    daily_df = pd.DataFrame({"Close": [100.0, 101.0]}, index=pd.to_datetime(["2026-03-06", "2026-03-07"]))
    intraday_df = pd.DataFrame(
        {"Close": [102.0]},
        index=pd.DatetimeIndex([pd.Timestamp("2026-03-10 08:00:00", tz="Europe/Prague")]),
    )

    monkeypatch.setattr(fetch, "load_symbol_mappings", lambda: ({"TEST": {"yahoo": "TEST.DE"}}, ["stooq", "yahoo"]))
    monkeypatch.setattr(fetch, "fetch_from_yahoo_intraday", lambda symbol, period="5d", interval="15m": intraday_df)
    monkeypatch.setattr(fetch, "is_live_preview_fresh", lambda ts: False)

    snapshot = get_live_preview_snapshot("TEST", daily_df, "stooq", "TEST.DE")

    assert snapshot.price == pytest.approx(101.0)
    assert snapshot.price_mode == "Daily Close"
    assert snapshot.fresh is False
    assert snapshot.source == "stooq:TEST.DE"
