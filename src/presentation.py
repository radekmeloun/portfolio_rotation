"""
Presentation module for Global Regime Rotator.

Provides helpers for:
- Sorting strategy table (rank asc, momentum desc, ticker asc)
- Building allocation summary DataFrame
- Formatting display with proper decimals, %, EUR
"""

from typing import Optional
import pandas as pd
import numpy as np


# ============= Sorting Helpers =============

def sort_strategy_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    Sort strategy table for display.
    
    Sort order:
    1. Primary: Rank ascending (NaN/missing last)
    2. Secondary (for unranked): Momentum_Score descending
    3. Tertiary: XTB_Ticker ascending (deterministic tie-breaker)
    
    Args:
        df: Strategy results DataFrame with Rank, Momentum_Score, XTB_Ticker columns
    
    Returns:
        Sorted DataFrame (copy)
    """
    sorted_df = df.copy()
    
    # Create sort key for rank (NaN becomes infinity for sorting last)
    sorted_df["_rank_sort"] = sorted_df["Rank"].fillna(float("inf"))
    
    # Create sort key for momentum (NaN becomes -infinity for sorting last within unranked)
    sorted_df["_momentum_sort"] = sorted_df["Momentum_Score"].fillna(float("-inf"))
    
    # Sort: rank asc, momentum desc (negate for descending), ticker asc
    sorted_df = sorted_df.sort_values(
        by=["_rank_sort", "_momentum_sort", "XTB_Ticker"],
        ascending=[True, False, True]
    )
    
    # Drop helper columns
    sorted_df = sorted_df.drop(columns=["_rank_sort", "_momentum_sort"])
    
    return sorted_df.reset_index(drop=True)


def build_allocation_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build allocation summary DataFrame for display.
    
    Includes rows where Allocation_EUR > 0.
    Sort order:
    1. Ranked assets first by rank ascending
    2. Cash fallback (XEON with no rank) displayed last
    
    Args:
        df: Strategy results DataFrame with allocation columns
    
    Returns:
        Summary DataFrame with columns: Rank, XTB Ticker, Name, Top 4?, Allocation (EUR)
    """
    # Filter to allocated rows
    allocated = df[df["Allocation_EUR"] > 0].copy()
    
    if allocated.empty:
        return pd.DataFrame(columns=["Rank", "XTB Ticker", "Name", "Top 4?", "Allocation (EUR)"])
    
    # Sort: rank asc (NaN last for cash fallback)
    allocated["_rank_sort"] = allocated["Rank"].fillna(float("inf"))
    allocated = allocated.sort_values(by=["_rank_sort", "XTB_Ticker"], ascending=[True, True])
    allocated = allocated.drop(columns=["_rank_sort"])
    
    # Build summary DataFrame
    summary = pd.DataFrame({
        "Rank": allocated["Rank"],
        "XTB Ticker": allocated["XTB_Ticker"],
        "Name": allocated["Name"],
        "Top 4?": allocated["In_Top_4"],
        "Allocation (EUR)": allocated["Allocation_EUR"]
    })
    
    return summary.reset_index(drop=True)


# ============= Formatting Helpers =============

def format_rank(val) -> str:
    """Format rank as integer, blank for NaN."""
    if pd.isna(val):
        return "-"
    return f"{int(val)}"


def format_percent(val) -> str:
    """Format as percentage with sign and 2 decimals."""
    if pd.isna(val):
        return "-"
    return f"{val:+.2f}%"


def format_currency(val) -> str:
    """Format as EUR currency with 2 decimals and thousands separator."""
    if pd.isna(val):
        return "-"
    return f"{val:,.2f} EUR"


def format_number(val) -> str:
    """Format number with 2 decimals."""
    if pd.isna(val):
        return "-"
    return f"{val:,.2f}"


def format_boolean(val) -> str:
    """Format boolean as Yes/No."""
    if pd.isna(val):
        return "-"
    return "Yes" if val else "No"


def format_strategy_display(df: pd.DataFrame) -> pd.DataFrame:
    """
    Format strategy DataFrame for display with renamed columns.
    
    Applies column renaming and prepares for Styler formatting.
    Returns a display-ready DataFrame (copy).
    """
    display_df = df.copy()
    
    # Column mapping (raw -> display)
    column_map = {
        "Group": "Group",
        "Name": "Name",
        "XTB_Ticker": "XTB Ticker",
        "ISIN": "ISIN",
        "Data_Symbol": "Data Symbol",
        "Data_Source": "Source",
        "Value_Date": "Value Date",
        "Price_Timestamp": "Price Timestamp",
        "Price_Mode": "Price Mode",
        "Fresh": "Fresh?",
        "Price": "Price (EUR)",
        "Return_1M": "Return 1M (%)",
        "Return_3M": "Return 3M (%)",
        "Return_6M": "Return 6M (%)",
        "SMA200": "SMA200",
        "Traffic_Light": "🚦 Signal",
        "Momentum_Score": "Mom. Score",
        "Rank": "Rank",
        "In_Top_4": "Top 4?",
        "Allocation_EUR": "Allocation (EUR)"
    }
    
    # Select and rename columns
    display_cols = [c for c in column_map.keys() if c in display_df.columns]
    display_df = display_df[display_cols].rename(columns=column_map)
    
    return display_df


def get_strategy_table_formatters() -> dict:
    """
    Get formatters dict for strategy table Styler.
    
    Returns:
        Dict mapping column names to formatter functions
    """
    return {
        "Price (EUR)": format_number,
        "Return 1M (%)": format_percent,
        "Return 3M (%)": format_percent,
        "Return 6M (%)": format_percent,
        "SMA200": format_number,
        "Mom. Score": format_number,
        "Rank": format_rank,
        "Fresh?": format_boolean,
        "Top 4?": format_boolean,
        "Allocation (EUR)": format_currency,
    }


def get_summary_table_formatters() -> dict:
    """
    Get formatters dict for allocation summary table Styler.
    
    Returns:
        Dict mapping column names to formatter functions
    """
    return {
        "Rank": format_rank,
        "Top 4?": format_boolean,
        "Allocation (EUR)": format_currency,
    }


def style_strategy_table(df: pd.DataFrame) -> "pd.io.formats.style.Styler":
    """
    Apply full styling to strategy display DataFrame.
    
    Args:
        df: Display-ready DataFrame (after format_strategy_display)
    
    Returns:
        Styled DataFrame
    """
    formatters = get_strategy_table_formatters()
    
    # Filter to columns that exist
    formatters = {k: v for k, v in formatters.items() if k in df.columns}
    
    styled = df.style.format(formatters, na_rep="-")
    
    # Apply traffic light styling
    if "🚦 Signal" in df.columns:
        def highlight_signal(val):
            if val == "GREEN":
                return "background-color: #90EE90; color: black; font-weight: bold"
            elif val == "RED":
                return "background-color: #FFB6C1; color: black; font-weight: bold"
            return ""
        styled = styled.applymap(highlight_signal, subset=["🚦 Signal"])
    
    return styled


def style_summary_table(df: pd.DataFrame) -> "pd.io.formats.style.Styler":
    """
    Apply styling to allocation summary DataFrame.
    
    Args:
        df: Summary DataFrame from build_allocation_summary
    
    Returns:
        Styled DataFrame
    """
    formatters = get_summary_table_formatters()
    formatters = {k: v for k, v in formatters.items() if k in df.columns}
    
    return df.style.format(formatters, na_rep="-")
