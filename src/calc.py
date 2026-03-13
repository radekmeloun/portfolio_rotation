"""
Calculation module for Global Regime Rotator.

Provides functions for:
- SMA200 calculation
- 1M/3M/6M returns calculation
- Momentum score calculation
- Traffic light determination
- Ranking and allocation logic
"""

from typing import Optional
from datetime import datetime, timedelta, date
import pandas as pd
import numpy as np


def resolve_shared_as_of_date(
    fetch_frames: dict[str, pd.DataFrame], 
    evaluation_mode: str, 
    today_override: Optional[date] = None
) -> tuple[Optional[pd.Timestamp], Optional[str]]:
    """
    Compute strict shared evaluation date across all assets.
    
    Args:
        fetch_frames: Mapping of ticker -> historical price DataFrame.
        evaluation_mode: 'weekly_close' or 'actual_day'.
        today_override: Optional override for the current calendar date (for testing).
        
    Returns:
        Tuple of (resolved_timestamp, error_message).
    """
    if not fetch_frames:
        return None, "No data fetched for any assets."
        
    ref_date = today_override or datetime.now().date()

    if evaluation_mode in {"actual_day", "live_preview_15m"}:
        target_date = ref_date if ref_date.weekday() <= 4 else ref_date - timedelta(days=ref_date.weekday() - 4)
    elif evaluation_mode == "weekly_close":
        current_week_start = ref_date - timedelta(days=ref_date.weekday())
        target_date = current_week_start - timedelta(days=3) if ref_date.weekday() <= 4 else current_week_start + timedelta(days=4)
    else:
        return None, f"Unknown evaluation mode: {evaluation_mode}"

    for ticker, df in fetch_frames.items():
        if df is None or len(df) == 0:
            return None, f"Missing data for asset {ticker}"

        available_dates = sorted(set(pd.to_datetime(df.index).date))
        if not available_dates:
            return None, f"Missing data for asset {ticker}"

        if available_dates[0] > target_date:
            return None, f"Asset {ticker} has no data on or before the evaluation date ({target_date})."

    return pd.Timestamp(target_date), None


def _get_price_series(df: pd.DataFrame, prefer_adjusted: bool = True) -> Optional[pd.Series]:
    """
    Get the best price series from a DataFrame, preferring adjusted close.
    
    Args:
        df: DataFrame with price data
        prefer_adjusted: If True, prefer 'Adj Close' over 'Close'
    
    Returns:
        Numeric Series of prices, or None if no suitable column found
    """
    if df is None or len(df) == 0:
        return None
    
    # Column priority: Adj Close > Close (case-insensitive)
    col_priority = [
        "Adj Close", "adj close", "Adj_Close", "adjusted_close", "AdjClose",
        "Close", "close"
    ] if prefer_adjusted else [
        "Close", "close", "Adj Close", "adj close"
    ]
    
    # Find first matching column
    for col in col_priority:
        if col in df.columns:
            series = pd.to_numeric(df[col], errors="coerce")
            if series.notna().any():
                return series
    
    # Fallback: find any column with 'close' in name
    close_cols = [c for c in df.columns if "close" in c.lower()]
    if close_cols:
        series = pd.to_numeric(df[close_cols[0]], errors="coerce")
        if series.notna().any():
            return series
    
    return None


def _safe_round(value, decimals: int = 4) -> Optional[float]:
    """Safely round a value to specified decimals, handling non-numeric types."""
    if value is None or pd.isna(value):
        return None
    try:
        return round(float(value), decimals)
    except (TypeError, ValueError):
        return None


# Trading days approximations
DAYS_1M = 21   # ~1 month
DAYS_3M = 63   # ~3 months
DAYS_6M = 126  # ~6 months
SMA_PERIOD = 200

# Allocation settings
SLOT_AMOUNT = 3500  # EUR per slot
NUM_SLOTS = 4
TOTAL_ALLOCATION = SLOT_AMOUNT * NUM_SLOTS  # 14,000 EUR


def calculate_sma200(df: pd.DataFrame, prefer_adjusted: bool = True) -> Optional[float]:
    """
    Calculate the 200-day Simple Moving Average.
    
    Uses adjusted close when available for accuracy after dividends/splits.
    
    Args:
        df: DataFrame with price data (must have at least 200 rows)
        prefer_adjusted: If True, prefer adjusted close over regular close
    
    Returns:
        SMA200 value or None if insufficient data
    """
    if df is None or len(df) < SMA_PERIOD:
        return None
    
    closes = _get_price_series(df, prefer_adjusted=prefer_adjusted)
    if closes is None:
        return None
    
    # Calculate SMA of last 200 days
    tail = closes.tail(SMA_PERIOD)
    if tail.isna().all():
        return None
    
    sma = tail.mean()
    return _safe_round(sma, 4)


def get_latest_price(df: pd.DataFrame, prefer_adjusted: bool = True) -> Optional[float]:
    """
    Get the latest closing price from the DataFrame.
    
    Uses adjusted close when available for accuracy after dividends/splits.
    
    Args:
        df: DataFrame with price data
        prefer_adjusted: If True, prefer adjusted close over regular close
    
    Returns:
        Latest close price or None
    """
    closes = _get_price_series(df, prefer_adjusted=prefer_adjusted)
    if closes is None:
        return None
    
    # Get last non-NaN value
    valid = closes.dropna()
    if len(valid) == 0:
        return None
    
    return _safe_round(valid.iloc[-1], 4)


def calculate_return(
    df: pd.DataFrame,
    days_ago: int,
    prefer_adjusted: bool = True,
    current_price_override: Optional[float] = None,
) -> Optional[float]:
    """
    Calculate percentage return over a period.
    
    Uses adjusted close when available for accuracy after dividends/splits.
    
    Args:
        df: DataFrame with price data
        days_ago: Number of trading days ago to compare
        prefer_adjusted: If True, prefer adjusted close over regular close
    
    Returns:
        Percentage return (e.g., 5.25 for 5.25%) or None
    """
    if df is None or len(df) <= days_ago:
        return None
    
    closes = _get_price_series(df, prefer_adjusted=prefer_adjusted)
    if closes is None:
        return None
    
    # Drop NaN values and check we have enough data
    valid = closes.dropna()
    if len(valid) <= days_ago:
        return None
    
    current_price = current_price_override if current_price_override is not None else valid.iloc[-1]
    
    # Handle case where we don't have exactly days_ago rows
    actual_days = min(days_ago, len(valid) - 1)
    past_price = valid.iloc[-(actual_days + 1)]
    
    # Type-safe numeric check
    try:
        current_val = float(current_price)
        past_val = float(past_price)
    except (TypeError, ValueError):
        return None
    
    if past_val == 0 or pd.isna(past_val):
        return None
    
    return_pct = ((current_val - past_val) / past_val) * 100
    return _safe_round(return_pct, 2)


def calculate_returns(df: pd.DataFrame, current_price_override: Optional[float] = None) -> dict:
    """
    Calculate 1M, 3M, and 6M returns.
    
    Args:
        df: DataFrame with price data
    
    Returns:
        Dict with keys "1M", "3M", "6M" containing percentage returns
    """
    return {
        "1M": calculate_return(df, DAYS_1M, current_price_override=current_price_override),
        "3M": calculate_return(df, DAYS_3M, current_price_override=current_price_override),
        "6M": calculate_return(df, DAYS_6M, current_price_override=current_price_override)
    }


def calculate_momentum_score(r1m: Optional[float], r3m: Optional[float], r6m: Optional[float]) -> Optional[float]:
    """
    Calculate momentum score as weighted average of returns.
    
    Formula: 0.2 * R1M + 0.4 * R3M + 0.4 * R6M
    
    Args:
        r1m: 1-month return percentage
        r3m: 3-month return percentage
        r6m: 6-month return percentage
    
    Returns:
        Momentum score or None if any return is missing
    """
    if r1m is None or r3m is None or r6m is None:
        return None
    
    score = 0.2 * r1m + 0.4 * r3m + 0.4 * r6m
    return round(score, 2)


def determine_traffic_light(price: Optional[float], sma200: Optional[float]) -> str:
    """
    Determine traffic light color based on price vs SMA200.
    
    Args:
        price: Current price
        sma200: 200-day SMA value
    
    Returns:
        "GREEN" if price > SMA200, "RED" otherwise, "N/A" if data missing
    """
    if price is None or sma200 is None:
        return "N/A"
    
    return "GREEN" if price > sma200 else "RED"


def rank_assets(df: pd.DataFrame) -> pd.DataFrame:
    """
    Rank eligible (GREEN) assets by momentum score.
    
    Args:
        df: DataFrame with asset data including Traffic_Light and Momentum_Score
    
    Returns:
        DataFrame with Rank column added (NaN for non-eligible assets)
    """
    result = df.copy()
    
    # Only rank GREEN assets with valid momentum scores
    mask = (result["Traffic_Light"] == "GREEN") & (result["Momentum_Score"].notna())
    
    # Rank by momentum score descending (higher score = better rank = lower number)
    result.loc[mask, "Rank"] = result.loc[mask, "Momentum_Score"].rank(
        ascending=False, method="min"
    ).astype(int)
    
    # Non-eligible assets get no rank
    result.loc[~mask, "Rank"] = None
    
    return result


def calculate_allocation(
    df: pd.DataFrame,
    total_allocation_eur: float = TOTAL_ALLOCATION,
    num_slots: int = NUM_SLOTS,
) -> pd.DataFrame:
    """
    Calculate allocation for each asset based on ranking.
    
    Rules:
    - Top 4 eligible (GREEN) assets get 3,500 EUR each
    - XEON (cash) is always allowed and gets any leftover
    - Non-eligible assets get 0
    
    Args:
        df: DataFrame with asset data including Rank and is_cash flag
    
    Returns:
        DataFrame with allocation columns added
    """
    result = df.copy()
    result["In_Top_4"] = False
    result["Allocation_EUR"] = 0.0
    
    # Find top 4 eligible assets (excluding XEON which is cash)
    eligible_mask = (
        (result["Traffic_Light"] == "GREEN") & 
        (result["Rank"].notna()) &
        (~result.get("is_cash", pd.Series([False] * len(result))))
    )
    
    # Handle case where no eligible assets exist
    if eligible_mask.any():
        eligible_assets = result[eligible_mask].nsmallest(num_slots, "Rank")
        top_4_indices = eligible_assets.index.tolist()
    else:
        top_4_indices = []

    
    slot_amount = float(total_allocation_eur) / float(num_slots)

    # Mark top 4 and allocate
    allocated_slots = len(top_4_indices)
    result.loc[top_4_indices, "In_Top_4"] = True
    result.loc[top_4_indices, "Allocation_EUR"] = slot_amount
    
    # Allocate leftover to XEON (cash asset)
    leftover = (num_slots - allocated_slots) * slot_amount
    if leftover > 0:
        cash_mask = result.get("is_cash", pd.Series([False] * len(result)))
        if cash_mask.any():
            cash_idx = result[cash_mask].index[0]
            result.loc[cash_idx, "Allocation_EUR"] += leftover
            # XEON is always in allocation if it receives money
            if leftover > 0:
                result.loc[cash_idx, "In_Top_4"] = True
    
    return result


def process_asset(
    xtb_ticker: str,
    df: Optional[pd.DataFrame],
    source: str,
    data_symbol: str,
    asset_info: dict,
    as_of_date: Optional[str] = None,
    live_price_snapshot: Optional[object] = None,
) -> dict:
    """
    Process a single asset and calculate all metrics.
    
    Args:
        xtb_ticker: XTB ticker symbol
        df: Price DataFrame (or None if fetch failed)
        source: Data source used
        data_symbol: Symbol used for fetching
        asset_info: Dict with group, name, isin, is_cash
        as_of_date: Optional global evaluation date to slice historical data
    
    Returns:
        Dict with all calculated metrics
    """
    
    if df is not None and as_of_date is not None:
        try:
            target_date = pd.to_datetime(as_of_date).date()
            if not isinstance(df.index, pd.DatetimeIndex):
                df.index = pd.to_datetime(df.index)
                
            mask = df.index.date <= target_date
            df = df.loc[mask].copy()
        except Exception:
            pass  # keep df as is if parsing fails
    
    result = {
        "Group": asset_info.get("group", ""),
        "Name": asset_info.get("name", ""),
        "XTB_Ticker": xtb_ticker,
        "ISIN": asset_info.get("isin", ""),
        "Data_Symbol": data_symbol,
        "Data_Source": source,
        "Value_Date": None,
        "Price_Timestamp": None,
        "Price_Mode": "Daily Close",
        "Fresh": False,
        "is_cash": asset_info.get("is_cash", False),
    }
    
    if df is None:
        # Data missing - fill with None/N/A
        result.update({
            "Price": None,
            "Return_1M": None,
            "Return_3M": None,
            "Return_6M": None,
            "SMA200": None,
            "Traffic_Light": "N/A",
            "Momentum_Score": None,
        })
    else:
        value_date = None
        price_timestamp = None
        price_mode = "Daily Close"
        if len(df) > 0:
            value_date = pd.to_datetime(df.index[-1]).strftime("%Y-%m-%d")
            price_timestamp = value_date

        price = get_latest_price(df)
        sma200 = calculate_sma200(df)
        if live_price_snapshot is not None and getattr(live_price_snapshot, "price", None) is not None:
            price = _safe_round(getattr(live_price_snapshot, "price", None), 4)
            price_mode = getattr(live_price_snapshot, "price_mode", "Daily Close")
            timestamp = getattr(live_price_snapshot, "timestamp", None)
            if timestamp is not None:
                ts = pd.Timestamp(timestamp)
                price_timestamp = ts.strftime("%Y-%m-%d %H:%M") if (ts.hour or ts.minute) else ts.strftime("%Y-%m-%d")
                value_date = ts.strftime("%Y-%m-%d")
            returns = calculate_returns(df, current_price_override=price)
        else:
            returns = calculate_returns(df)

        if live_price_snapshot is not None:
            fresh = bool(getattr(live_price_snapshot, "fresh", False))
        else:
            fresh = bool(as_of_date and value_date == as_of_date)
        
        # Skip momentum score for XEON (cash asset)
        if asset_info.get("is_cash", False):
            momentum = None
        else:
            momentum = calculate_momentum_score(
                returns["1M"], returns["3M"], returns["6M"]
            )
        
        result.update({
            "Value_Date": value_date,
            "Price_Timestamp": price_timestamp,
            "Price_Mode": price_mode,
            "Fresh": fresh,
            "Price": price,
            "Return_1M": returns["1M"],
            "Return_3M": returns["3M"],
            "Return_6M": returns["6M"],
            "SMA200": sma200,
            "Traffic_Light": determine_traffic_light(price, sma200),
            "Momentum_Score": momentum,
        })
    
    return result
