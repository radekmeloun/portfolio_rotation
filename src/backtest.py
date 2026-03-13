"""
Backtest engine for Global Regime Rotator.

Provides:
- generate_signal_dates(): Weekly last trading day
- generate_exec_dates(): Biweekly Monday-aligned execution dates
- compute_weekly_signals(): SMA200, returns, momentum scores, top 4 selection
- run_backtest(): Daily portfolio simulation with exec gate
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Default parameters
DEFAULT_SLOTS = 4
DEFAULT_COMMISSION_BPS = 5
DEFAULT_SLIPPAGE_BPS = 2
DEFAULT_MIN_FEE_EUR = 0.0
DEFAULT_INITIAL_CAPITAL = 14000.0

# Lookback periods in trading days
LOOKBACK_1M = 21
LOOKBACK_3M = 63
LOOKBACK_6M = 126
LOOKBACK_SMA = 200


@dataclass
class BacktestParams:
    """Parameters for backtest run."""
    initial_capital: float = DEFAULT_INITIAL_CAPITAL
    slots: int = DEFAULT_SLOTS
    commission_bps: float = DEFAULT_COMMISSION_BPS
    slippage_bps: float = DEFAULT_SLIPPAGE_BPS
    min_fee_eur: float = DEFAULT_MIN_FEE_EUR
    exec_frequency_days: int = 14
    emergency_risk_off: bool = False
    cash_ticker: str = "XEON"


@dataclass
class SignalResult:
    """Result of signal computation for one date."""
    signal_date: pd.Timestamp
    selected: list[str]  # List of selected tickers (including any XEON fills)
    scores: dict[str, float]  # Ticker -> momentum score
    traffic_lights: dict[str, str]  # Ticker -> "GREEN" or "RED"
    eligible_count: int
    notes: str = ""


# ============= Calendar Helpers =============

def generate_signal_dates(
    trading_index: pd.DatetimeIndex,
    start_date: datetime,
    end_date: datetime
) -> list[pd.Timestamp]:
    """
    Generate weekly signal dates (last trading day of each week).
    
    Args:
        trading_index: Index of trading dates from price matrix
        start_date: Backtest start date
        end_date: Backtest end date
    
    Returns:
        List of signal dates (Timestamps)
    """
    # Filter to range
    mask = (trading_index >= pd.Timestamp(start_date)) & \
           (trading_index <= pd.Timestamp(end_date))
    dates_in_range = trading_index[mask]
    
    if len(dates_in_range) == 0:
        return []
    
    # Create a DataFrame with year-week grouping
    df = pd.DataFrame({"date": dates_in_range})
    df["year"] = df["date"].dt.isocalendar().year
    df["week"] = df["date"].dt.isocalendar().week
    
    # Get last trading day per week
    signal_dates = df.groupby(["year", "week"])["date"].max().tolist()
    
    return sorted(signal_dates)


def generate_exec_dates(
    trading_index: pd.DatetimeIndex,
    start_date: datetime,
    end_date: datetime,
    every_days: int = 14
) -> list[pd.Timestamp]:
    """
    Generate biweekly execution dates (Monday-aligned, shifted to next trading day).
    
    Args:
        trading_index: Index of trading dates from price matrix
        start_date: Backtest start date
        end_date: Backtest end date
        every_days: Days between executions (default 14)
    
    Returns:
        List of execution dates (Timestamps)
    """
    # Find first Monday >= start_date
    current = pd.Timestamp(start_date)
    days_until_monday = (7 - current.weekday()) % 7
    if days_until_monday == 0 and current.weekday() != 0:
        days_until_monday = 7
    if current.weekday() == 0:
        days_until_monday = 0
    
    first_monday = current + timedelta(days=days_until_monday)
    
    # Generate scheduled Mondays
    exec_dates = []
    planned = first_monday
    
    while planned <= pd.Timestamp(end_date):
        # Align to next trading day if planned is not a trading day
        aligned = next_trading_date_on_or_after(trading_index, planned)
        if aligned is not None and aligned <= pd.Timestamp(end_date):
            exec_dates.append(aligned)
        
        planned += timedelta(days=every_days)
    
    return exec_dates


def last_trading_date_on_or_before(
    trading_index: pd.DatetimeIndex,
    date: pd.Timestamp
) -> Optional[pd.Timestamp]:
    """Find last trading date on or before given date."""
    valid = trading_index[trading_index <= date]
    if len(valid) == 0:
        return None
    return valid.max()


def next_trading_date_on_or_after(
    trading_index: pd.DatetimeIndex,
    date: pd.Timestamp
) -> Optional[pd.Timestamp]:
    """Find next trading date on or after given date."""
    valid = trading_index[trading_index >= date]
    if len(valid) == 0:
        return None
    return valid.min()


def trading_day_shift(
    trading_index: pd.DatetimeIndex,
    date: pd.Timestamp,
    shift: int
) -> Optional[pd.Timestamp]:
    """
    Shift by n trading days.
    
    Args:
        trading_index: Index of trading dates
        date: Starting date
        shift: Number of days to shift (positive = forward, negative = backward)
    
    Returns:
        Shifted date or None if out of range
    """
    try:
        idx = trading_index.get_loc(date)
        new_idx = idx + shift
        if 0 <= new_idx < len(trading_index):
            return trading_index[new_idx]
    except KeyError:
        # Date not in index, find nearest
        if shift >= 0:
            aligned = next_trading_date_on_or_after(trading_index, date)
        else:
            aligned = last_trading_date_on_or_before(trading_index, date)
        if aligned is not None:
            return trading_day_shift(trading_index, aligned, shift)
    
    return None


# ============= Signal Computation =============

def compute_metrics_for_asset(
    prices: pd.Series,
    signal_date: pd.Timestamp,
    trading_index: pd.DatetimeIndex
) -> Optional[dict]:
    """
    Compute SMA200, returns, and momentum score for one asset on signal_date.
    
    Args:
        prices: Price series for the asset
        signal_date: Date to compute metrics for
        trading_index: Full trading index for position lookup
    
    Returns:
        Dict with price, sma200, returns, score, traffic_light
        or None if insufficient data
    """
    # Get position of signal_date in trading index
    try:
        idx = trading_index.get_loc(signal_date)
    except KeyError:
        return None
    
    # Check sufficient history
    min_required = max(LOOKBACK_SMA, LOOKBACK_6M)
    if idx < min_required:
        return None
    
    # Get prices at required positions
    try:
        price_t = prices.iloc[idx]
        if pd.isna(price_t):
            return None
        
        # Returns (use positional indexing for trading day lookback)
        price_21 = prices.iloc[idx - LOOKBACK_1M]
        price_63 = prices.iloc[idx - LOOKBACK_3M]
        price_126 = prices.iloc[idx - LOOKBACK_6M]
        
        if pd.isna(price_21) or pd.isna(price_63) or pd.isna(price_126):
            return None
        
        r1m = (price_t / price_21) - 1
        r3m = (price_t / price_63) - 1
        r6m = (price_t / price_126) - 1
        
        # Momentum score
        score = 0.2 * r1m + 0.4 * r3m + 0.4 * r6m
        
        # SMA200
        sma_prices = prices.iloc[idx - LOOKBACK_SMA + 1:idx + 1]
        if len(sma_prices) < LOOKBACK_SMA or sma_prices.isna().sum() > 10:
            return None
        sma200 = sma_prices.mean()
        
        # Traffic light
        traffic_light = "GREEN" if price_t > sma200 else "RED"
        
        return {
            "price": price_t,
            "sma200": sma200,
            "r1m": r1m,
            "r3m": r3m,
            "r6m": r6m,
            "score": score,
            "traffic_light": traffic_light,
        }
        
    except (IndexError, KeyError):
        return None


def compute_weekly_signals(
    prices_df: pd.DataFrame,
    signal_dates: list[pd.Timestamp],
    params: BacktestParams
) -> list[SignalResult]:
    """
    Compute signals for all weekly signal dates.
    
    Args:
        prices_df: Price matrix (DatetimeIndex, columns = tickers)
        signal_dates: List of signal dates
        params: Backtest parameters
    
    Returns:
        List of SignalResult for each signal date
    """
    trading_index = prices_df.index
    tickers = [c for c in prices_df.columns if c != params.cash_ticker]
    
    signals = []
    
    for signal_date in signal_dates:
        if signal_date not in trading_index:
            continue
        
        # Compute metrics for each ticker
        metrics = {}
        for ticker in tickers:
            if ticker not in prices_df.columns:
                continue
            
            prices = prices_df[ticker].reindex(trading_index)
            result = compute_metrics_for_asset(prices, signal_date, trading_index)
            if result is not None:
                metrics[ticker] = result
        
        # Filter to GREEN and sort by score
        green_candidates = [
            (ticker, m["score"])
            for ticker, m in metrics.items()
            if m["traffic_light"] == "GREEN"
        ]
        green_candidates.sort(key=lambda x: x[1], reverse=True)
        
        # Select top slots
        selected = [ticker for ticker, _ in green_candidates[:params.slots]]
        
        # Fill remaining slots with cash
        while len(selected) < params.slots:
            selected.append(params.cash_ticker)
        
        # Build scores and traffic lights dicts
        scores = {ticker: m["score"] for ticker, m in metrics.items()}
        traffic_lights = {ticker: m["traffic_light"] for ticker, m in metrics.items()}
        
        # Notes about missing data
        missing = [t for t in tickers if t not in metrics]
        notes = f"Missing: {', '.join(missing)}" if missing else ""
        
        signals.append(SignalResult(
            signal_date=signal_date,
            selected=selected,
            scores=scores,
            traffic_lights=traffic_lights,
            eligible_count=len(green_candidates),
            notes=notes,
        ))
    
    return signals


# ============= Backtest Simulation =============

def run_backtest(
    prices_df: pd.DataFrame,
    signals: list[SignalResult],
    exec_dates: list[pd.Timestamp],
    start_date: datetime,
    end_date: datetime,
    params: BacktestParams
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Run backtest simulation.
    
    Args:
        prices_df: Price matrix
        signals: List of SignalResult from compute_weekly_signals
        exec_dates: List of execution dates
        start_date: Backtest start date
        end_date: Backtest end date
        params: Backtest parameters
    
    Returns:
        Tuple of (equity_df, exec_log_df, holdings_df)
    """
    trading_index = prices_df.index
    tickers = list(prices_df.columns)
    
    # Filter to backtest range
    mask = (trading_index >= pd.Timestamp(start_date)) & \
           (trading_index <= pd.Timestamp(end_date))
    sim_dates = trading_index[mask]
    
    if len(sim_dates) == 0:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    
    # Compute daily returns
    daily_returns = prices_df.pct_change().fillna(0)
    
    # Initialize
    portfolio_value = params.initial_capital
    weights = {t: 0.0 for t in tickers}
    weights[params.cash_ticker] = 1.0  # Start in cash
    
    # Results storage
    equity_records = []
    holdings_records = []
    exec_log_records = []
    
    # Build signal lookup (signal_date -> SignalResult)
    signal_map = {s.signal_date: s for s in signals}
    
    exec_dates_set = set(exec_dates)
    
    for day in sim_dates:
        value_before = portfolio_value
        
        # Check if execution day
        if day in exec_dates_set:
            # Find active signal (latest signal_date <= exec_date)
            valid_signals = [s for s in signals if s.signal_date <= day]
            if valid_signals:
                active_signal = max(valid_signals, key=lambda s: s.signal_date)
                
                # Compute target weights
                target_weights = {t: 0.0 for t in tickers}
                slot_weight = 1.0 / params.slots
                for ticker in active_signal.selected:
                    if ticker in target_weights:
                        target_weights[ticker] += slot_weight
                
                # Calculate turnover
                turnover = sum(abs(target_weights.get(t, 0) - weights.get(t, 0)) 
                              for t in tickers) / 2
                
                # Calculate cost
                cost_rate = (params.commission_bps + params.slippage_bps) / 10000
                cost_eur = portfolio_value * turnover * cost_rate
                if turnover > 0 and params.min_fee_eur > 0:
                    cost_eur = max(cost_eur, params.min_fee_eur)
                
                # Apply cost
                portfolio_value -= cost_eur
                
                # Record execution
                holdings_before = {t: w for t, w in weights.items() if w > 0}
                weights = target_weights
                holdings_after = {t: w for t, w in weights.items() if w > 0}
                
                exec_log_records.append({
                    "exec_date": day,
                    "signal_date_used": active_signal.signal_date,
                    "holdings_before": str(holdings_before),
                    "holdings_after": str(holdings_after),
                    "turnover": turnover,
                    "cost_eur": cost_eur,
                    "value_before": value_before,
                    "value_after": portfolio_value,
                    "trades": str(active_signal.selected),
                })
        
        # Emergency risk-off (optional)
        if params.emergency_risk_off:
            # Check if any held risky asset turned RED
            for signal in signals:
                if signal.signal_date < day:
                    next_day = next_trading_date_on_or_after(trading_index, 
                                                            signal.signal_date + timedelta(days=1))
                    if next_day == day:
                        # Check held assets
                        for ticker, w in list(weights.items()):
                            if w > 0 and ticker != params.cash_ticker:
                                if signal.traffic_lights.get(ticker) == "RED":
                                    # Move to cash
                                    weights[params.cash_ticker] = weights.get(params.cash_ticker, 0) + w
                                    weights[ticker] = 0
                                    logger.info(f"Emergency risk-off: {ticker} on {day}")
        
        # Compute daily portfolio return
        port_return = 0.0
        for ticker, w in weights.items():
            if w > 0 and ticker in daily_returns.columns:
                asset_ret = daily_returns.loc[day, ticker] if day in daily_returns.index else 0
                if pd.notna(asset_ret):
                    port_return += w * asset_ret
        
        # Update portfolio value
        portfolio_value *= (1 + port_return)
        
        # Record equity
        equity_records.append({
            "date": day,
            "portfolio_value": portfolio_value,
            "daily_return": port_return,
        })
        
        # Record holdings
        holdings_record = {"date": day}
        holdings_record.update(weights)
        holdings_records.append(holdings_record)
    
    # Build DataFrames
    equity_df = pd.DataFrame(equity_records)
    if not equity_df.empty:
        equity_df = equity_df.set_index("date")
        # Compute drawdown
        equity_df["cummax"] = equity_df["portfolio_value"].cummax()
        equity_df["drawdown"] = (equity_df["portfolio_value"] / equity_df["cummax"]) - 1
    
    exec_log_df = pd.DataFrame(exec_log_records)
    
    holdings_df = pd.DataFrame(holdings_records)
    if not holdings_df.empty:
        holdings_df = holdings_df.set_index("date")
    
    return equity_df, exec_log_df, holdings_df


def signals_to_dataframe(signals: list[SignalResult]) -> pd.DataFrame:
    """Convert signal results to DataFrame for display."""
    records = []
    for s in signals:
        record = {
            "signal_date": s.signal_date,
            "slot1": s.selected[0] if len(s.selected) > 0 else "",
            "slot2": s.selected[1] if len(s.selected) > 1 else "",
            "slot3": s.selected[2] if len(s.selected) > 2 else "",
            "slot4": s.selected[3] if len(s.selected) > 3 else "",
            "eligible_count": s.eligible_count,
            "notes": s.notes,
        }
        # Add scores for selected
        for i, ticker in enumerate(s.selected[:4]):
            record[f"slot{i+1}_score"] = s.scores.get(ticker, np.nan)
        
        records.append(record)
    
    return pd.DataFrame(records)
