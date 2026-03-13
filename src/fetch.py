"""
Data fetching module for Global Regime Rotator.

Fetches historical price data from multiple sources with fallback:
1. Stooq (CSV API)
2. Yahoo Finance (yfinance)

Features:
- Multi-symbol fallback per provider
- Configurable provider order
- Provider+symbol keyed caching
- Structured status reporting
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from typing import Optional
import logging
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import yaml

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cache directory
CACHE_DIR = Path(__file__).parent.parent / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Minimum trading days needed for SMA200 + buffer
MIN_TRADING_DAYS = 260

# Default provider order
DEFAULT_SOURCES = ["stooq", "yahoo"]
DAILY_MARKET_TIMEZONE = "Europe/Prague"
LOCAL_MARKET_TZ = ZoneInfo(DAILY_MARKET_TIMEZONE)
LIVE_PREVIEW_INTERVAL = "15m"
LIVE_PREVIEW_PERIOD = "5d"
LIVE_PREVIEW_MAX_AGE_MINUTES = 45


@dataclass
class FetchStatus:
    """Structured status for a fetch attempt."""
    xtb_ticker: str
    provider: str = ""
    symbol: str = ""
    status: str = "PENDING"  # OK, OK (cache), DATA MISSING, NEEDS MAPPING
    used_cache: bool = False
    notes: list = field(default_factory=list)
    last_data_date: Optional[str] = None
    
    def add_note(self, note: str) -> None:
        """Add a note to the status."""
        self.notes.append(note)
    
    def notes_str(self) -> str:
        """Get notes as a single string."""
        return "; ".join(self.notes) if self.notes else ""

def filter_daily_rows(df: Optional[pd.DataFrame], include_current_day: bool) -> Optional[pd.DataFrame]:
    """
    Filter daily rows based on the evaluation policy.
    If include_current_day is False, removes today's row to ensure only fully closed daily bars are evaluated.
    """
    if df is None or len(df) == 0:
        return df

    df = normalize_daily_index(df)
    if df is None or len(df) == 0:
        return df

    if include_current_day:
        return df.copy()

    today = datetime.now().date()

    # Filter for dates before today
    mask = df.index.date < today
    return df.loc[mask].copy()


def normalize_daily_index(df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    """
    Normalize daily-bar indices to local market dates.

    Yahoo may return timezone-aware daily timestamps such as 23:00 UTC for
    Xetra instruments, which belongs to the next local trading day.
    """
    if df is None or len(df) == 0:
        return df

    normalized = df.copy()
    index = pd.to_datetime(normalized.index, errors="coerce")
    valid_mask = ~index.isna()
    if not valid_mask.all():
        normalized = normalized.loc[valid_mask].copy()
        index = index[valid_mask]

    if len(index) == 0:
        return normalized.iloc[0:0]

    if getattr(index, "tz", None) is not None:
        index = index.tz_convert(DAILY_MARKET_TIMEZONE).tz_localize(None)

    normalized.index = index.normalize()
    normalized = normalized[~normalized.index.duplicated(keep="last")]
    return normalized.sort_index()


def normalize_intraday_index(df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    """Normalize intraday timestamps to Europe/Prague while preserving time-of-day."""
    if df is None or len(df) == 0:
        return df

    normalized = df.copy()
    index = pd.to_datetime(normalized.index, errors="coerce")
    valid_mask = ~index.isna()
    if not valid_mask.all():
        normalized = normalized.loc[valid_mask].copy()
        index = index[valid_mask]

    if len(index) == 0:
        return normalized.iloc[0:0]

    if getattr(index, "tz", None) is None:
        index = index.tz_localize(LOCAL_MARKET_TZ)
    else:
        index = index.tz_convert(LOCAL_MARKET_TZ)

    normalized.index = index
    normalized = normalized[~normalized.index.duplicated(keep="last")]
    return normalized.sort_index()


def extract_price_series(df: Optional[pd.DataFrame]) -> pd.Series:
    """Extract a numeric price series, preferring adjusted close when available."""
    if df is None or len(df) == 0:
        return pd.Series(dtype=float)

    for col in ["Adj Close", "adj close", "Adj_Close", "adjusted_close", "Close", "close"]:
        if col in df.columns:
            series = pd.to_numeric(df[col], errors="coerce")
            if series.notna().any():
                return series

    for col in df.columns:
        series = pd.to_numeric(df[col], errors="coerce")
        if series.notna().any():
            return series

    return pd.Series(dtype=float)


def is_live_preview_fresh(
    timestamp: Optional[pd.Timestamp],
    now_local: Optional[pd.Timestamp] = None,
    max_age_minutes: int = LIVE_PREVIEW_MAX_AGE_MINUTES,
) -> bool:
    """Return True when an intraday timestamp is recent enough for live preview."""
    if timestamp is None:
        return False

    now_local = now_local or pd.Timestamp.now(tz=LOCAL_MARKET_TZ)
    ts = pd.Timestamp(timestamp)
    if ts.tzinfo is None:
        ts = ts.tz_localize(LOCAL_MARKET_TZ)
    else:
        ts = ts.tz_convert(LOCAL_MARKET_TZ)

    if ts > now_local:
        return False

    age_minutes = (now_local - ts).total_seconds() / 60.0
    return ts.date() == now_local.date() and age_minutes <= max_age_minutes


def remove_today_bar(df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    """
    Remove any rows from today to ensure we only evaluate fully closed daily bars.
    Wrapper for filter_daily_rows for backwards compatibility.
    """
    return filter_daily_rows(df, include_current_day=False)


@dataclass 
class FetchResult:
    """Result of a fetch operation."""
    df: Optional[pd.DataFrame]
    status: FetchStatus


@dataclass
class LivePriceSnapshot:
    """Fresh intraday quote or daily-close fallback used in live preview."""
    price: Optional[float]
    timestamp: Optional[pd.Timestamp]
    price_mode: str
    source: str
    fresh: bool
    note: str = ""


def normalize_symbol_candidates(value) -> list[str]:
    """
    Normalize symbol value to a list of candidate symbols.
    
    Accepts:
    - str: returns [str] (single candidate)
    - list[str]: returns list as-is
    - None/empty/invalid: returns []
    
    Args:
        value: Symbol value from YAML (string, list, or None)
    
    Returns:
        List of candidate symbols to try
    """
    if value is None:
        return []
    if isinstance(value, str):
        value = value.strip()
        return [value] if value else []
    if isinstance(value, list):
        # Filter to valid non-empty strings
        return [s.strip() for s in value if isinstance(s, str) and s.strip()]
    return []


def load_symbol_mappings() -> tuple[dict, list[str]]:
    """
    Load symbol mappings and default sources from YAML file.
    
    Returns:
        Tuple of (symbols_dict, default_sources_list)
    """
    symbols_path = Path(__file__).parent.parent / "data" / "symbols.yaml"
    with open(symbols_path, "r") as f:
        data = yaml.safe_load(f)
    
    symbols = data.get("symbols", {})
    sources = data.get("default_sources", DEFAULT_SOURCES)
    
    # Validate sources
    if not isinstance(sources, list) or not sources:
        sources = DEFAULT_SOURCES
    
    return symbols, sources


def get_cache_key(provider: str, symbol: str, date: str) -> str:
    """Generate cache key from provider, symbol, and date."""
    # Sanitize symbol for filename (replace dots, slashes)
    safe_symbol = symbol.replace(".", "_").replace("/", "_").replace("\\", "_")
    return f"{provider}__{safe_symbol}__{date}.json"


def get_cache_path(provider: str, symbol: str, date: str) -> Path:
    """Get cache file path for a provider/symbol/date combination."""
    return CACHE_DIR / get_cache_key(provider, symbol, date)


def get_legacy_cache_path(ticker: str, date: str) -> Path:
    """Get legacy cache path (for backward compatibility)."""
    return CACHE_DIR / f"{ticker}_{date}.json"


def save_to_cache(
    provider: str, 
    symbol: str, 
    xtb_ticker: str,
    df: pd.DataFrame
) -> None:
    """Save DataFrame to cache as JSON with metadata."""
    today = datetime.now().strftime("%Y-%m-%d")
    cache_path = get_cache_path(provider, symbol, today)
    
    cache_data = {
        "version": 3,  # New cache format version (raw data)
        "provider": provider,
        "symbol": symbol,
        "xtb_ticker": xtb_ticker,
        "fetched_at": datetime.now().isoformat(),
        "data": df.reset_index().to_json(date_format="iso", orient="records")
    }
    
    with open(cache_path, "w") as f:
        json.dump(cache_data, f)
    
    logger.info(f"Cached {xtb_ticker} ({provider}:{symbol})")


def load_from_cache(
    provider: str, 
    symbol: str
) -> tuple[Optional[pd.DataFrame], Optional[dict]]:
    """
    Load DataFrame from cache if valid today.
    
    Returns:
        Tuple of (DataFrame, metadata_dict) or (None, None)
    """
    today = datetime.now().strftime("%Y-%m-%d")
    cache_path = get_cache_path(provider, symbol, today)
    
    if not cache_path.exists():
        return None, None
    
    try:
        with open(cache_path, "r") as f:
            cache_data = json.load(f)
        
        # Version check
        if cache_data.get("version", 1) < 3:
            raise ValueError(f"Cache version {cache_data.get('version', 1)} is too old. Needs 3.")
        
        # Parse data
        df = pd.read_json(StringIO(cache_data["data"]), orient="records")
        
        # Convert date column back to datetime and set as index
        # Check common date column names (including 'index' which pandas uses for unnamed index)
        date_col = None
        for col in ["Date", "date", "Datetime", "datetime", "index", "timestamp", "Timestamp"]:
            if col in df.columns:
                date_col = col
                break
        
        if date_col is None:
            raise ValueError(f"No date column found in cached data. Columns: {list(df.columns)}")
        
        df[date_col] = pd.to_datetime(df[date_col])
        df = df.set_index(date_col)
        df = normalize_daily_index(df)
        
        metadata = {
            "provider": cache_data.get("provider", provider),
            "symbol": cache_data.get("symbol", symbol),
            "fetched_at": cache_data.get("fetched_at"),
        }
        
        return df, metadata
        
    except Exception as e:
        logger.warning(f"Failed to load cache {cache_path.name}: {e}. Removing corrupt file.")
        # Delete corrupt cache file for self-healing
        try:
            cache_path.unlink()
            logger.info(f"Removed corrupt cache file: {cache_path.name}")
        except Exception as del_err:
            logger.warning(f"Could not delete corrupt cache: {del_err}")
        return None, None


def try_legacy_cache(xtb_ticker: str) -> tuple[Optional[pd.DataFrame], Optional[str], Optional[str]]:
    """
    Try to load from legacy cache format (for backward compatibility).
    
    Returns:
        Tuple of (DataFrame, provider, symbol) or (None, None, None)
    """
    today = datetime.now().strftime("%Y-%m-%d")
    legacy_path = get_legacy_cache_path(xtb_ticker, today)
    
    if not legacy_path.exists():
        return None, None, None
    
    try:
        with open(legacy_path, "r") as f:
            cache_data = json.load(f)
        
        df = pd.read_json(StringIO(cache_data["data"]), orient="records")
        
        # Convert date column
        for col in ["Date", "date"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col])
                df = df.set_index(col)
                break
        
        df = df.sort_index()
        
        provider = cache_data.get("source", "unknown")
        symbol = cache_data.get("data_symbol", "")
        
        logger.info(f"Loaded legacy cache for {xtb_ticker}")
        return df, provider, symbol
        
    except Exception as e:
        logger.warning(f"Failed to load legacy cache for {xtb_ticker}: {e}")
        # Delete corrupt legacy cache
        try:
            legacy_path.unlink()
        except:
            pass
        return None, None, None


def fetch_from_stooq(symbol: str, days: int = 400) -> Optional[pd.DataFrame]:
    """
    Fetch historical data from Stooq.
    
    Returns DataFrame with columns: Date, Open, High, Low, Close, Volume
    """
    if not symbol:
        return None
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    d1 = start_date.strftime("%Y%m%d")
    d2 = end_date.strftime("%Y%m%d")
    
    url = f"https://stooq.com/q/d/l/?s={symbol}&d1={d1}&d2={d2}"
    
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        
        content = response.text
        if "No data" in content or len(content) < 50:
            return None
        
        df = pd.read_csv(StringIO(content))
        df.columns = [col.strip().title() for col in df.columns]
        
        if "Date" not in df.columns:
            return None
        
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date")
        df = df.sort_index()
        
        if len(df) < MIN_TRADING_DAYS:
            return None
        
        logger.info(f"Stooq: Fetched {len(df)} days for {symbol}")
        return df
        
    except Exception as e:
        logger.debug(f"Stooq fetch failed for {symbol}: {e}")
        return None


def fetch_from_yahoo(symbol: str, days: int = 400) -> Optional[pd.DataFrame]:
    """
    Fetch historical data from Yahoo Finance using yfinance.
    
    Returns DataFrame with columns: Open, High, Low, Close, Adj Close, Volume
    """
    if not symbol:
        return None
    
    try:
        import yfinance as yf
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start_date, end=end_date)
        
        if df is None or len(df) == 0:
            return None
        
        if len(df) < MIN_TRADING_DAYS:
            return None
        
        df = df.sort_index()
        
        logger.info(f"Yahoo: Fetched {len(df)} days for {symbol}")
        return df
        
    except Exception as e:
        logger.debug(f"Yahoo fetch failed for {symbol}: {e}")
        return None


def fetch_from_yahoo_intraday(
    symbol: str,
    period: str = LIVE_PREVIEW_PERIOD,
    interval: str = LIVE_PREVIEW_INTERVAL,
) -> Optional[pd.DataFrame]:
    """Fetch recent intraday data from Yahoo Finance for live preview."""
    if not symbol:
        return None

    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)
        if df is None or len(df) == 0:
            return None

        df = normalize_intraday_index(df)
        logger.info(f"Yahoo intraday: Fetched {len(df)} bars for {symbol}")
        return df
    except Exception as e:
        logger.debug(f"Yahoo intraday fetch failed for {symbol}: {e}")
        return None


def get_live_preview_snapshot(
    xtb_ticker: str,
    daily_df: Optional[pd.DataFrame],
    daily_provider: str,
    daily_symbol: str,
) -> LivePriceSnapshot:
    """
    Fetch a fresh 15-minute intraday price, or fall back to the last daily close.
    """
    fallback_series = extract_price_series(daily_df)
    fallback_price = None
    fallback_timestamp = None
    if len(fallback_series) > 0:
        fallback_price = float(fallback_series.dropna().iloc[-1])
        fallback_timestamp = pd.Timestamp(fallback_series.dropna().index[-1])

    fallback_source = f"{daily_provider}:{daily_symbol}" if daily_provider else daily_symbol or "daily-close"

    mappings, _ = load_symbol_mappings()
    ticker_map = mappings.get(xtb_ticker, {})
    yahoo_candidates = normalize_symbol_candidates(ticker_map.get("yahoo"))
    if daily_provider == "yahoo" and daily_symbol:
        yahoo_candidates = [daily_symbol] + [s for s in yahoo_candidates if s != daily_symbol]

    notes: list[str] = []
    for symbol in yahoo_candidates:
        intraday_df = fetch_from_yahoo_intraday(symbol)
        if intraday_df is None or len(intraday_df) == 0:
            notes.append(f"yahoo:{symbol} intraday unavailable")
            continue

        price_series = extract_price_series(intraday_df).dropna()
        if len(price_series) == 0:
            notes.append(f"yahoo:{symbol} intraday empty")
            continue

        timestamp = pd.Timestamp(price_series.index[-1])
        price = float(price_series.iloc[-1])
        fresh = is_live_preview_fresh(timestamp)
        if fresh:
            return LivePriceSnapshot(
                price=price,
                timestamp=timestamp.tz_localize(None) if timestamp.tzinfo is not None else timestamp,
                price_mode="Live 15m",
                source=f"yahoo:{symbol}",
                fresh=True,
                note="Fresh intraday quote",
            )

        notes.append(f"yahoo:{symbol} intraday stale at {timestamp}")

    fallback_note = "; ".join(notes) if notes else "No fresh intraday quote"
    return LivePriceSnapshot(
        price=fallback_price,
        timestamp=fallback_timestamp,
        price_mode="Daily Close",
        source=fallback_source,
        fresh=False,
        note=fallback_note,
    )


# Provider fetch functions map
PROVIDER_FETCHERS = {
    "stooq": fetch_from_stooq,
    "yahoo": fetch_from_yahoo,
}


def get_price_data(
    xtb_ticker: str,
    force_refresh: bool = False,
    include_current_day: bool = False
) -> FetchResult:
    """
    Get price data for a ticker with caching and multi-symbol fallback.
    
    Args:
        xtb_ticker: The XTB ticker symbol (e.g., "SXR8")
        force_refresh: If True, bypass cache and fetch fresh data
        include_current_day: If True, allow the latest daily bar from today
    
    Returns:
        FetchResult with DataFrame and structured status
    """
    status = FetchStatus(xtb_ticker=xtb_ticker)
    
    # Load mappings and provider order
    mappings, sources = load_symbol_mappings()
    ticker_map = mappings.get(xtb_ticker, {})
    
    if not ticker_map:
        status.status = "NEEDS MAPPING"
        status.add_note(f"No mapping found for {xtb_ticker}")
        return FetchResult(df=None, status=status)
    
    # Try each provider in order
    for provider in sources:
        if provider not in PROVIDER_FETCHERS:
            status.add_note(f"Unknown provider: {provider}")
            continue
        
        fetcher = PROVIDER_FETCHERS[provider]
        candidates = normalize_symbol_candidates(ticker_map.get(provider))
        
        if not candidates:
            status.add_note(f"{provider}: no symbols configured")
            continue
        
        # Try each candidate symbol for this provider
        for symbol in candidates:
            # Check cache first (unless force refresh)
            if not force_refresh:
                cached_df, metadata = load_from_cache(provider, symbol)
                if cached_df is not None:
                    raw_last_date = cached_df.index[-1].strftime("%Y-%m-%d") if len(cached_df) > 0 else None
                    filtered_df = filter_daily_rows(cached_df, include_current_day)
                    if filtered_df is not None and len(filtered_df) > 0:
                        status.provider = provider
                        status.symbol = symbol
                        status.status = "OK (cache)"
                        status.used_cache = True
                        status.last_data_date = raw_last_date  # Report raw data boundary
                        status.add_note(f"Loaded from cache ({provider}:{symbol})")
                        return FetchResult(df=filtered_df, status=status)
            
            # Try fresh fetch
            df = fetcher(symbol)
            if df is not None and len(df) > 0:
                df = normalize_daily_index(df)
                raw_last_date = df.index[-1].strftime("%Y-%m-%d")
                save_to_cache(provider, symbol, xtb_ticker, df)  # Save raw data
                
                filtered_df = filter_daily_rows(df, include_current_day)
                if filtered_df is not None and len(filtered_df) > 0:
                    status.provider = provider
                    status.symbol = symbol
                    status.status = "OK"
                    status.last_data_date = raw_last_date
                    status.add_note(f"Fetched from {provider}:{symbol}")
                    return FetchResult(df=filtered_df, status=status)
                else:
                    status.add_note(f"{provider}:{symbol} no valid days after filter")
            else:
                status.add_note(f"{provider}:{symbol} failed or empty")
    
    # Try legacy cache as last resort (backward compatibility)
    if not force_refresh:
        legacy_df, legacy_provider, legacy_symbol = try_legacy_cache(xtb_ticker)
        if legacy_df is not None:
            legacy_df = normalize_daily_index(legacy_df)
            raw_last_date = legacy_df.index[-1].strftime("%Y-%m-%d") if len(legacy_df) > 0 else None
            filtered_legacy_df = filter_daily_rows(legacy_df, include_current_day)
            if filtered_legacy_df is not None and len(filtered_legacy_df) > 0:
                status.provider = legacy_provider or "legacy"
                status.symbol = legacy_symbol or xtb_ticker
                status.status = "OK (cache)"
                status.used_cache = True
                status.last_data_date = raw_last_date
                status.add_note("Loaded from legacy cache")
                return FetchResult(df=filtered_legacy_df, status=status)
    
    # All sources failed
    status.status = "DATA MISSING"
    status.add_note("All providers and symbols exhausted")
    logger.error(f"All data sources failed for {xtb_ticker}")
    return FetchResult(df=None, status=status)


def clear_old_cache(days_to_keep: int = 7) -> int:
    """
    Remove cache files older than specified days.
    Returns number of files removed.
    """
    removed = 0
    cutoff = datetime.now() - timedelta(days=days_to_keep)
    
    for cache_file in CACHE_DIR.glob("*.json"):
        try:
            # Try new format: provider__symbol__YYYY-MM-DD.json
            parts = cache_file.stem.split("__")
            if len(parts) >= 3:
                date_str = parts[-1]
            else:
                # Legacy format: ticker_YYYY-MM-DD.json
                date_str = cache_file.stem.split("_")[-1]
            
            file_date = datetime.strptime(date_str, "%Y-%m-%d")
            
            if file_date < cutoff:
                cache_file.unlink()
                removed += 1
        except (ValueError, IndexError):
            continue
    
    if removed > 0:
        logger.info(f"Cleared {removed} old cache files")
    
    return removed
