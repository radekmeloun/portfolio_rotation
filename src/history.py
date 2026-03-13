"""
Historical data module for Global Regime Rotator backtest.

Provides:
- fetch_history(): Fetch historical price data with caching
- get_price_matrix(): Build aligned price matrix for all assets
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import yaml

from src.fetch import (
    fetch_from_stooq, 
    fetch_from_yahoo, 
    normalize_symbol_candidates,
    normalize_daily_index,
    remove_today_bar
)

# Configure logging
logger = logging.getLogger(__name__)


def normalize_index_tz(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize daily index to local market dates.

    Yahoo daily bars can come as timezone-aware timestamps around 23:00 UTC.
    We must map those to the local market calendar day before removing today's bar
    and before computing coverage windows.
    """
    if df is None or df.empty:
        return df

    normalized = normalize_daily_index(df)
    return normalized if normalized is not None else df

# Cache directory for historical data
HISTORY_CACHE_DIR = Path(__file__).parent.parent / "data" / "history_cache"
HISTORY_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Cache TTL in seconds (1 day)
CACHE_TTL_SECONDS = 86400

# Default buffer days for SMA200 + 126-day lookback
# 200 trading days ≈ 280 calendar days, plus holidays/weekends headroom → use 500
DEFAULT_BUFFER_DAYS = 500


def load_universe(profile_name: Optional[str] = None) -> list[dict]:
    """Load ETF universe from YAML file.
    Supports both legacy schema (list of assets) and profile-based schema.
    """
    universe_path = Path(__file__).parent.parent / "data" / "universe.yaml"
    with open(universe_path, "r") as f:
        data = yaml.safe_load(f)
        
    if data is None:
        return []
        
    # Legacy format fallback
    if "assets" in data and "profiles" not in data:
        return data.get("assets", [])
        
    profiles = data.get("profiles", {})
    if not profiles:
        return []
        
    if profile_name is None:
        profile_name = data.get("default_profile")
        if profile_name is None and profiles:
            profile_name = next(iter(profiles.keys()))
            
    profile = profiles.get(profile_name, {})
    return profile.get("assets", [])


def get_profiles() -> tuple[dict, str]:
    """
    Get available profiles and the default profile name.
    
    Returns:
        Tuple of (profiles_dict, default_profile_name)
    """
    universe_path = Path(__file__).parent.parent / "data" / "universe.yaml"
    with open(universe_path, "r") as f:
        data = yaml.safe_load(f)
        
    if data is None:
        return {}, ""
        
    # Legacy format fallback
    if "assets" in data and "profiles" not in data:
        return {"legacy": {"label": "Default Universe", "assets": data["assets"]}}, "legacy"
        
    profiles = data.get("profiles", {})
    default_profile = data.get("default_profile", "")
    
    # If no default is set but there are profiles, use the first one
    if not default_profile and profiles:
        default_profile = next(iter(profiles.keys()))
        
    return profiles, default_profile


def load_symbol_mappings() -> dict:
    """Load symbol mappings from YAML file."""
    symbols_path = Path(__file__).parent.parent / "data" / "symbols.yaml"
    with open(symbols_path, "r") as f:
        data = yaml.safe_load(f)
    return data.get("symbols", {})


def get_cache_path(xtb_ticker: str) -> Path:
    """Get cache file path for historical data."""
    return HISTORY_CACHE_DIR / f"{xtb_ticker}_history.parquet"


def is_cache_fresh(cache_path: Path) -> bool:
    """Check if cache file exists and is fresh (within TTL)."""
    if not cache_path.exists():
        return False
    
    mtime = cache_path.stat().st_mtime
    age_seconds = datetime.now().timestamp() - mtime
    return age_seconds < CACHE_TTL_SECONDS


def save_to_cache(xtb_ticker: str, df: pd.DataFrame) -> None:
    """Save historical data to parquet cache."""
    cache_path = get_cache_path(xtb_ticker)
    df.to_parquet(cache_path)
    logger.info(f"Cached history for {xtb_ticker}")


def load_from_cache(xtb_ticker: str) -> Optional[pd.DataFrame]:
    """Load historical data from cache if fresh."""
    cache_path = get_cache_path(xtb_ticker)
    
    if not is_cache_fresh(cache_path):
        return None
    
    try:
        df = pd.read_parquet(cache_path)
        logger.info(f"Loaded cached history for {xtb_ticker}")
        return df
    except Exception as e:
        logger.warning(f"Failed to load cache for {xtb_ticker}: {e}")
        return None


def fetch_history(
    xtb_ticker: str,
    start_date: datetime,
    end_date: datetime,
    force_refresh: bool = False
) -> tuple[Optional[pd.DataFrame], str, str]:
    """
    Fetch historical daily prices for a ticker.
    
    Args:
        xtb_ticker: XTB ticker symbol
        start_date: Start date for history
        end_date: End date for history
        force_refresh: Bypass cache if True
    
    Returns:
        Tuple of (DataFrame, source, symbol_used)
        DataFrame has DatetimeIndex and at least 'Close' column
    """
    # Check cache first
    if not force_refresh:
        cached_df = load_from_cache(xtb_ticker)
        if cached_df is not None:
            # Normalize timezone and filter to requested date range
            cached_df = normalize_index_tz(cached_df)
            mask = (cached_df.index >= pd.Timestamp(start_date)) & \
                   (cached_df.index <= pd.Timestamp(end_date))
            return cached_df[mask], "cache", xtb_ticker
    
    # Get symbol mappings
    mappings = load_symbol_mappings()
    ticker_map = mappings.get(xtb_ticker, {})
    
    if not ticker_map:
        logger.warning(f"No mapping for {xtb_ticker}")
        return None, "FAILED", f"{xtb_ticker} (no mapping)"
    
    # Calculate days to fetch
    days = (end_date - start_date).days + 50  # Extra buffer for weekends/holidays
    
    # Try Stooq first
    stooq_symbols = normalize_symbol_candidates(ticker_map.get("stooq"))
    for symbol in stooq_symbols:
        df = fetch_from_stooq(symbol, days=days)
        if df is not None and len(df) > 0:
            # Normalize timezone before filtering
            df = normalize_index_tz(df)
            df = remove_today_bar(df)
            
            if df is not None and len(df) > 0:
                # Filter to date range
                mask = (df.index >= pd.Timestamp(start_date)) & \
                       (df.index <= pd.Timestamp(end_date))
                filtered_df = df[mask]
                if len(filtered_df) > 0:
                    save_to_cache(xtb_ticker, df)  # Cache full data
                    return filtered_df, "stooq", symbol
    
    # Try Yahoo as fallback
    yahoo_symbols = normalize_symbol_candidates(ticker_map.get("yahoo"))
    for symbol in yahoo_symbols:
        df = fetch_from_yahoo(symbol, days=days)
        if df is not None and len(df) > 0:
            # Normalize timezone before filtering
            df = normalize_index_tz(df)
            df = remove_today_bar(df)
            
            if df is not None and len(df) > 0:
                mask = (df.index >= pd.Timestamp(start_date)) & \
                       (df.index <= pd.Timestamp(end_date))
                filtered_df = df[mask]
                if len(filtered_df) > 0:
                    save_to_cache(xtb_ticker, df)
                    return filtered_df, "yahoo", symbol
    
    logger.error(f"Failed to fetch history for {xtb_ticker}")
    return None, "FAILED", f"{xtb_ticker} (fetch failed)"


def get_price_series(df: pd.DataFrame) -> pd.Series:
    """
    Extract price series from DataFrame, preferring Adj Close.
    
    Args:
        df: DataFrame with price columns
    
    Returns:
        Series of prices (Adj Close preferred, Close fallback)
    """
    # Check for adjusted close first
    for col in ["Adj Close", "adj close", "Adj_Close", "adjusted_close"]:
        if col in df.columns:
            series = pd.to_numeric(df[col], errors="coerce")
            if series.notna().any():
                return series
    
    # Fallback to close
    for col in ["Close", "close"]:
        if col in df.columns:
            series = pd.to_numeric(df[col], errors="coerce")
            if series.notna().any():
                return series
    
    # Last resort: first numeric column
    for col in df.columns:
        series = pd.to_numeric(df[col], errors="coerce")
        if series.notna().any():
            return series
    
    return pd.Series(dtype=float)


def get_price_matrix(
    universe: list[dict],
    start_date: datetime,
    end_date: datetime,
    buffer_days: int = DEFAULT_BUFFER_DAYS,
    force_refresh: bool = False
) -> tuple[pd.DataFrame, dict]:
    """
    Build aligned price matrix for all assets in universe.
    
    Args:
        universe: List of asset dicts from load_universe()
        start_date: Backtest start date
        end_date: Backtest end date
        buffer_days: Extra calendar days before start for SMA/return calculation
        force_refresh: Bypass cache if True
    
    Returns:
        Tuple of (prices_df, fetch_status)
        - prices_df: DataFrame with DatetimeIndex, columns = xtb_tickers, values = prices
        - fetch_status: Dict mapping xtb_ticker to (source, symbol, success)
    """
    # Calculate fetch range with buffer
    fetch_start = start_date - timedelta(days=buffer_days)
    fetch_end = end_date
    
    price_series = {}
    fetch_status = {}
    
    for asset in universe:
        ticker = asset["xtb_ticker"]
        
        df, source, symbol = fetch_history(ticker, fetch_start, fetch_end, force_refresh)
        
        if df is not None and len(df) > 0:
            series = get_price_series(df)
            if len(series) > 0:
                price_series[ticker] = series
                fetch_status[ticker] = (source, symbol, True)
            else:
                fetch_status[ticker] = (source, symbol, False)
        else:
            fetch_status[ticker] = (source, symbol, False)
    
    if not price_series:
        # Return empty DataFrame if no data
        return pd.DataFrame(), fetch_status
    
    # Build aligned price matrix
    prices_df = pd.DataFrame(price_series)
    prices_df.index = pd.to_datetime(prices_df.index)
    prices_df = prices_df.sort_index()
    
    # Keep only dates where at least one asset has a price
    prices_df = prices_df.dropna(how="all")
    
    # Forward fill to handle holidays and exchange differences
    prices_df = prices_df.ffill()
    
    return prices_df, fetch_status


def clear_history_cache() -> int:
    """Clear all history cache files. Returns count of files removed."""
    removed = 0
    for cache_file in HISTORY_CACHE_DIR.glob("*.parquet"):
        try:
            cache_file.unlink()
            removed += 1
        except Exception as e:
            logger.warning(f"Failed to remove {cache_file}: {e}")
    
    logger.info(f"Cleared {removed} history cache files")
    return removed


def get_portfolio_coverage_window(universe: list[dict], force_refresh: bool = False) -> dict:
    """
    Get the available data coverage window for each asset in the portfolio.
    
    Args:
        universe: List of asset dicts
        force_refresh: Whether to force refresh cache
        
    Returns:
        Dict with per_ticker_oldest, per_ticker_latest, common_start, latest_common_end
    """
    per_ticker_oldest = {}
    per_ticker_latest = {}
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365*20)  # 20 years lookback for max history
    
    for asset in universe:
        ticker = asset["xtb_ticker"]
        
        # Try fetching full history to max lookback. 
        # Caching logic inside fetch_history will use cache if fresh.
        df, _, _ = fetch_history(ticker, start_date, end_date, force_refresh=force_refresh)
        
        if df is not None and not df.empty:
            series = get_price_series(df)
            if len(series) > 0:
                valid_series = series.dropna()
                if len(valid_series) > 0:
                    per_ticker_oldest[ticker] = valid_series.index[0]
                    per_ticker_latest[ticker] = valid_series.index[-1]
                else:
                    per_ticker_oldest[ticker] = None
                    per_ticker_latest[ticker] = None
            else:
                per_ticker_oldest[ticker] = None
                per_ticker_latest[ticker] = None
        else:
            per_ticker_oldest[ticker] = None
            per_ticker_latest[ticker] = None
            
    valid_oldest = [d for d in per_ticker_oldest.values() if d is not None]
    valid_latest = [d for d in per_ticker_latest.values() if d is not None]
    
    return {
        "per_ticker_oldest": per_ticker_oldest,
        "per_ticker_latest": per_ticker_latest,
        "common_start": max(valid_oldest) if valid_oldest else None,
        "latest_common_end": min(valid_latest) if valid_latest else None,
    }
