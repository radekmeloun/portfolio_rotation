"""
Global Regime Rotator - Streamlit App

A tool for evaluating the Global Regime Rotator ETF momentum strategy.
Includes current evaluation and historical backtesting.
"""

import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from src.fetch import get_price_data, get_live_preview_snapshot, clear_old_cache
from src.calc import (
    process_asset,
    rank_assets,
    calculate_allocation,
    resolve_shared_as_of_date,
    TOTAL_ALLOCATION,
    NUM_SLOTS
)
from src.presentation import (
    sort_strategy_table,
    build_allocation_summary,
    format_strategy_display,
    style_strategy_table,
    style_summary_table,
)
from src.history import load_universe, get_price_matrix, clear_history_cache, get_profiles, get_portfolio_coverage_window
from src.backtest import (
    BacktestParams,
    generate_signal_dates,
    generate_exec_dates,
    compute_weekly_signals,
    run_backtest,
    signals_to_dataframe,
)
from src.perf import compute_metrics, format_metrics_for_display

# Page configuration
st.set_page_config(
    page_title="Global Regime Rotator",
    page_icon="🔄",
    layout="wide"
)


# Load universe from YAML
def load_universe_cached(profile_name=None):
    """Load ETF universe from YAML file."""
    return load_universe(profile_name)


def get_profiles_cached():
    """Get profiles from YAML file."""
    return get_profiles()


def fetch_and_process_all(
    assets: list,
    evaluation_mode: str,
    total_allocation_eur: float,
    force_refresh: bool = False,
) -> tuple[Optional[pd.DataFrame], pd.DataFrame, Optional[pd.Timestamp], Optional[str]]:
    """Fetch data and process all assets for current evaluation."""
    fetches = []
    status_rows = []
    
    progress_bar = st.progress(0, text="Fetching data...")
    include_current = (evaluation_mode == "actual_day")
    
    for i, asset in enumerate(assets):
        ticker = asset["xtb_ticker"]
        fetch_result = get_price_data(ticker, force_refresh=force_refresh, include_current_day=include_current)
        fetches.append((asset, fetch_result))
        
        status = fetch_result.status
        status_rows.append({
            "XTB Ticker": ticker,
            "Provider": status.provider or "-",
            "Symbol": status.symbol or "-",
            "Status": status.status,
            "Last Data": status.last_data_date or "-",
            "Used Cache": "✓" if status.used_cache else "",
            "Notes": status.notes_str()
        })
        progress_bar.progress((i + 1) / (len(assets) * 2), text=f"Fetching {ticker}...")
        
    df_status = pd.DataFrame(status_rows)
    
    # Resolve exact shared date
    fetch_frames = {asset["xtb_ticker"]: fetch_result.df for asset, fetch_result in fetches if fetch_result.df is not None}
    common_as_of_date, error_msg = resolve_shared_as_of_date(fetch_frames, evaluation_mode)
    
    if common_as_of_date is None:
        progress_bar.empty()
        return None, df_status, None, error_msg
        
    common_as_of_str = common_as_of_date.strftime("%Y-%m-%d")
    
    results = []
    for i, (asset, fetch_result) in enumerate(fetches):
        ticker = asset["xtb_ticker"]
        status = fetch_result.status
        df = fetch_result.df
        
        live_snapshot = None
        if evaluation_mode == "live_preview_15m" and df is not None:
            live_snapshot = get_live_preview_snapshot(
                xtb_ticker=ticker,
                daily_df=df,
                daily_provider=status.provider,
                daily_symbol=status.symbol,
            )

        result = process_asset(
            xtb_ticker=ticker,
            df=df,
            source=f"{status.provider}:{status.symbol}" if status.provider else status.status,
            data_symbol=status.symbol or "-",
            asset_info=asset,
            as_of_date=common_as_of_str,
            live_price_snapshot=live_snapshot,
        )
        results.append(result)
        
        progress_bar.progress(0.5 + (i + 1) / (len(assets) * 2), text=f"Processing {ticker}...")
    
    progress_bar.empty()
    
    df_results = pd.DataFrame(results)
    df_results = rank_assets(df_results)
    df_results = calculate_allocation(df_results, total_allocation_eur=total_allocation_eur)
    
    return df_results, df_status, common_as_of_date, None


def style_status(val):
    """Style the status column in fetch status table."""
    if val == "OK":
        return "background-color: #90EE90; color: black"
    elif val == "OK (cache)":
        return "background-color: #87CEEB; color: black"
    elif val == "DATA MISSING":
        return "background-color: #FFB6C1; color: black"
    elif val == "NEEDS MAPPING":
        return "background-color: #FFD700; color: black"
    return ""


def build_freshness_message(
    df_results: pd.DataFrame,
    as_of_date: pd.Timestamp,
    evaluation_mode: str,
) -> Optional[str]:
    """Build a short message describing which rows use the boundary date."""
    if (
        df_results is None
        or df_results.empty
        or as_of_date is None
        or "Value_Date" not in df_results.columns
    ):
        return None

    value_dates = pd.to_datetime(df_results["Value_Date"], errors="coerce")
    valid_mask = value_dates.notna()
    if not valid_mask.any():
        return None

    as_of_day = pd.Timestamp(as_of_date).strftime("%Y-%m-%d")
    total_count = int(valid_mask.sum())

    if evaluation_mode == "live_preview_15m":
        live_modes = df_results.get("Price_Mode", pd.Series([""] * len(df_results), index=df_results.index))
        live_mask = live_modes.eq("Live 15m")
        fresh_flags = df_results.get("Fresh", pd.Series([False] * len(df_results), index=df_results.index))
        fresh_mask = valid_mask & live_mask & fresh_flags.fillna(False).astype(bool)
    else:
        fresh_mask = valid_mask & value_dates.dt.strftime("%Y-%m-%d").eq(as_of_day)

    fresh_count = int(fresh_mask.sum())
    stale_rows = df_results.loc[valid_mask & ~fresh_mask, ["XTB_Ticker", "Value_Date", "Price_Mode"]]

    if stale_rows.empty:
        if evaluation_mode == "live_preview_15m":
            return f"All {total_count} assets use fresh `Live 15m` prices for `{as_of_day}`."
        return f"All {total_count} assets use the selected evaluation date `{as_of_day}`."

    stale_bits = [
        f"{row.XTB_Ticker} ({row.Value_Date}, {row.Price_Mode})"
        for row in stale_rows.itertuples(index=False)
    ]
    stale_preview = ", ".join(stale_bits[:6])
    if len(stale_bits) > 6:
        stale_preview += ", ..."

    if evaluation_mode == "live_preview_15m":
        return (
            f"{fresh_count}/{total_count} assets use fresh `Live 15m` prices for `{as_of_day}`. "
            f"Daily-close fallback is used for: {stale_preview}"
        )

    return (
        f"{fresh_count}/{total_count} assets use `{as_of_day}`. "
        f"Earlier last available closes are used for: {stale_preview}"
    )


def current_evaluation_tab():
    """Render current evaluation tab."""
    st.markdown("""
    **Momentum-based ETF allocation strategy** using SMA200 as trend filter.
    
    - **GREEN** = Price > SMA200 (eligible)
    - **RED** = Price < SMA200 (forbidden)
    - Top 4 eligible assets by momentum score receive equal allocation
    """)
    
    st.divider()
    
    # Controls
    col1, col2, col3, col4, col5 = st.columns([1.4, 1.4, 1.3, 1.0, 1.0])
    
    with col1:
        update_button = st.button(
            "🔄 Update & Generate Table", 
            type="primary",
            use_container_width=True,
            key="update_current"
        )
        
    with col2:
        eval_mode_display = st.selectbox(
            "Evaluation Mode",
            options=["Weekly Close", "Actual Day", "Live Preview (15m)"],
            index=0,
            key="eval_mode_ui",
            label_visibility="collapsed"
        )
        evaluation_mode_map = {
            "Weekly Close": "weekly_close",
            "Actual Day": "actual_day",
            "Live Preview (15m)": "live_preview_15m",
        }
        evaluation_mode = evaluation_mode_map[eval_mode_display]
    
    with col3:
        total_allocation_eur = st.number_input(
            "Total Allocation (EUR)",
            min_value=1000.0,
            max_value=100000.0,
            value=float(st.session_state.get("current_total_allocation_target", TOTAL_ALLOCATION)),
            step=500.0,
            key="current_total_allocation_input",
        )

    with col4:
        force_refresh = st.checkbox("Force refresh (bypass cache)", key="force_current")
    
    with col5:
        if st.button("🗑️ Clear old cache", key="clear_current"):
            removed = clear_old_cache(days_to_keep=3)
            st.success(f"Removed {removed} old cache files")
    
    # Main content
    if update_button:
        profile_name = st.session_state.get("selected_profile")
        assets = load_universe_cached(profile_name)
        
        with st.spinner("Fetching and processing data..."):
            df_results, df_status, common_as_of, error_msg = fetch_and_process_all(
                assets,
                evaluation_mode,
                total_allocation_eur,
                force_refresh,
            )
        
        st.session_state["current_as_of"] = common_as_of
        st.session_state["current_eval_mode"] = evaluation_mode
        st.session_state["current_status"] = df_status
        st.session_state["current_total_allocation_target"] = float(total_allocation_eur)
        
        if error_msg:
            st.session_state.pop("current_results", None)
            st.session_state["current_as_of"] = None
            st.error(f"**Evaluation Failed:** {error_msg}")
            
        with st.expander("📊 Fetch Status Details", expanded=(error_msg is not None)):
            ok_count = len(df_status[df_status["Status"].isin(["OK", "OK (cache)"])])
            fail_count = len(df_status[df_status["Status"] == "DATA MISSING"])
            mapping_count = len(df_status[df_status["Status"] == "NEEDS MAPPING"])
            
            st.markdown(f"**Summary:** ✅ {ok_count} OK | ❌ {fail_count} Failed | ⚠️ {mapping_count} Need Mapping")
            styled_status = df_status.style.applymap(style_status, subset=["Status"])
            st.dataframe(styled_status, use_container_width=True, height=300)
            
        if error_msg:
            return
            
        st.divider()
        
        if "current_as_of" in st.session_state and st.session_state["current_as_of"]:
            mode_prefix = {
                "weekly_close": "weekly close",
                "actual_day": "actual day",
                "live_preview_15m": "live preview",
            }[evaluation_mode]
            st.info(f"📅 **As of {mode_prefix}:** {st.session_state['current_as_of'].strftime('%Y-%m-%d')}")
            
            if evaluation_mode == "actual_day":
                st.caption("*Note: values use the latest available daily close on or before this date. On Monday or before providers publish a new close, some tickers may still reflect Friday.*")
            elif evaluation_mode == "live_preview_15m":
                st.caption("*Note: `Live Preview (15m)` recalculates returns and score with the latest fresh 15-minute price when available. If live data is missing or stale, the row falls back to the last daily close.*")

        freshness_message = build_freshness_message(df_results, common_as_of, evaluation_mode)
        if freshness_message:
            st.caption(freshness_message)
        
        st.subheader("📈 Allocation Summary")
        summary_df = build_allocation_summary(df_results)
        
        if not summary_df.empty:
            styled_summary = style_summary_table(summary_df)
            st.dataframe(styled_summary, use_container_width=True, hide_index=True)
            
            total_allocated = df_results["Allocation_EUR"].sum()
            st.info(f"**Total Allocation:** {total_allocated:,.2f} EUR / {float(total_allocation_eur):,.2f} EUR")
        else:
            st.warning("No eligible assets found! All allocation goes to XEON (cash).")
        
        st.divider()
        
        st.subheader("📋 Full Results Table")
        sorted_results = sort_strategy_table(df_results)
        display_df = format_strategy_display(sorted_results)
        styled_df = style_strategy_table(display_df)
        
        st.dataframe(styled_df, use_container_width=True, height=600)
        
        csv = sorted_results.to_csv(index=False)
        st.download_button(
            label="📥 Download CSV (raw)",
            data=csv,
            file_name="regime_rotator_results.csv",
            mime="text/csv",
            key="download_current"
        )
        
        st.session_state["current_results"] = df_results
        
    elif "current_results" in st.session_state:
        st.info("Showing previous results. Click 'Update & Generate Table' to refresh.")
        
        df_results = st.session_state["current_results"]
        saved_mode = st.session_state.get("current_eval_mode", "weekly_close")
        saved_total_allocation = float(st.session_state.get("current_total_allocation_target", TOTAL_ALLOCATION))
        if evaluation_mode != saved_mode:
            st.warning(
                "Displayed results belong to the last successful update in "
                f"`{dict(weekly_close='Weekly Close', actual_day='Actual Day', live_preview_15m='Live Preview (15m)')[saved_mode]}` mode. "
                "Click `Update & Generate Table` to refresh for the currently selected mode."
            )
        elif float(total_allocation_eur) != saved_total_allocation:
            st.warning(
                f"Displayed results belong to the last successful update with total allocation `{saved_total_allocation:,.2f} EUR`. "
                "Click `Update & Generate Table` to refresh for the currently selected amount."
            )
        
        if "current_as_of" in st.session_state and st.session_state["current_as_of"]:
            mode_prefix = {
                "weekly_close": "weekly close",
                "actual_day": "actual day",
                "live_preview_15m": "live preview",
            }[saved_mode]
            st.info(f"📅 **As of {mode_prefix}:** {st.session_state['current_as_of'].strftime('%Y-%m-%d')}")
            
            if saved_mode == "actual_day":
                st.caption("*Note: values use the latest available daily close on or before this date. On Monday or before providers publish a new close, some tickers may still reflect Friday.*")
            elif saved_mode == "live_preview_15m":
                st.caption("*Note: `Live Preview (15m)` recalculates returns and score with the latest fresh 15-minute price when available. If live data is missing or stale, the row falls back to the last daily close.*")

        freshness_message = build_freshness_message(df_results, st.session_state["current_as_of"], saved_mode)
        if freshness_message:
            st.caption(freshness_message)
            
        sorted_results = sort_strategy_table(df_results)
        display_df = format_strategy_display(sorted_results)
        styled_df = style_strategy_table(display_df)
        
        st.dataframe(styled_df, use_container_width=True, height=600)
    
    else:
        st.info("👆 Click **'Update & Generate Table'** to fetch data and generate the allocation table.")


def backtest_tab():
    """Render backtest tab."""
    st.markdown("""
    **Historical backtest** of the Global Regime Rotator strategy.
    
    - Weekly signals (last trading day of week)
    - Biweekly execution (every 14 days, Monday-aligned)
    - Transaction costs applied on rebalance
    """)
    
    st.divider()
    
    # Load universe for availability checking
    profile_name = st.session_state.get("selected_profile")
    universe = load_universe(profile_name)
    
    with st.spinner("Checking data availability..."):
        coverage = get_portfolio_coverage_window(universe)
        
    common_start = coverage["common_start"]
    latest_common_end = coverage.get("latest_common_end")
    min_start_date = common_start.date() if common_start else None
    today = datetime.now().date()
    
    max_end_date = latest_common_end.date() if latest_common_end else today
    if max_end_date > today:
        max_end_date = today
    
    # Parameters
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.subheader("📅 Date Range")
        default_end = max_end_date
        default_start = default_end - timedelta(days=365 * 3)  # 3 years
        if min_start_date and default_start < min_start_date:
            default_start = min_start_date
            
        start_date = st.date_input("Start Date", value=default_start, min_value=min_start_date, max_value=max_end_date, key="bt_start")
        end_date = st.date_input("End Date", value=default_end, min_value=min_start_date, max_value=max_end_date, key="bt_end")
    
    with col2:
        st.subheader("💰 Capital & Slots")
        initial_capital = st.number_input("Initial Capital (EUR)", value=14000, min_value=1000, step=1000, key="bt_capital")
        slots = st.number_input("Number of Slots", value=4, min_value=1, max_value=10, key="bt_slots")
        exec_freq = st.number_input("Exec Frequency (days)", value=14, min_value=7, max_value=30, key="bt_freq")
    
    with col3:
        st.subheader("💸 Transaction Costs")
        commission_bps = st.number_input("Commission (bps)", value=5, min_value=0, max_value=50, key="bt_comm")
        slippage_bps = st.number_input("Slippage (bps)", value=2, min_value=0, max_value=20, key="bt_slip")
        min_fee = st.number_input("Min Fee (EUR)", value=0.0, min_value=0.0, step=1.0, key="bt_minfee")
        
    st.divider()
    
    # Availability Overview
    with st.expander("📊 Ticker Data Availability", expanded=False):
        status_rows = []
        for asset in universe:
            ticker = asset["xtb_ticker"]
            name = asset.get("name", "")
            oldest = coverage["per_ticker_oldest"].get(ticker)
            latest = coverage["per_ticker_latest"].get(ticker)
            
            if oldest and latest:
                cov_days = (latest - oldest).days
                status = "OK"
            else:
                cov_days = 0
                status = "Missing"
                
            status_rows.append({
                "Ticker": ticker,
                "Name": name,
                "Oldest Date": oldest.date() if oldest else None,
                "Latest Date": latest.date() if latest else None,
                "Coverage Days": cov_days,
                "Status": status
            })
            
        if status_rows:
            df_status = pd.DataFrame(status_rows)
            df_status = df_status.sort_values(by="Oldest Date", na_position="first")
            st.dataframe(df_status, use_container_width=True, hide_index=True)
            
        if common_start:
            st.info(f"**Common start date across all tickers:** {common_start.date()}")
        else:
            st.warning("**Cannot determine common start date due to missing data.**")
            
    # Options
    # Options
    col1, col2 = st.columns(2)
    with col1:
        force_refresh = st.checkbox("Force refresh history", key="bt_force")
    with col2:
        emergency_off = st.checkbox("Emergency risk-off (experimental)", value=False, key="bt_emergency")
    
    # Clear cache button
    if st.button("🗑️ Clear history cache", key="bt_clear"):
        removed = clear_history_cache()
        st.success(f"Removed {removed} history cache files")
    
    st.divider()
    
    # Run button
    if st.button("🚀 Run Backtest", type="primary", use_container_width=True, key="bt_run"):
        run_backtest_ui(
            start_date=datetime.combine(start_date, datetime.min.time()),
            end_date=datetime.combine(end_date, datetime.min.time()),
            initial_capital=initial_capital,
            slots=slots,
            exec_freq=exec_freq,
            commission_bps=commission_bps,
            slippage_bps=slippage_bps,
            min_fee=min_fee,
            force_refresh=force_refresh,
            emergency_off=emergency_off,
        )
    
    # Show previous results
    elif "bt_equity" in st.session_state:
        display_backtest_results()


def run_backtest_ui(
    start_date: datetime,
    end_date: datetime,
    initial_capital: float,
    slots: int,
    exec_freq: int,
    commission_bps: float,
    slippage_bps: float,
    min_fee: float,
    force_refresh: bool,
    emergency_off: bool,
):
    """Run backtest and display results."""
    today = datetime.now().date()
    if end_date.date() > today:
        st.error(f"End date cannot be in the future (after {today}).")
        return
    
    # Load universe
    profile_name = st.session_state.get("selected_profile")
    universe = load_universe(profile_name)
    
    # Check start date against availability overlap
    coverage = get_portfolio_coverage_window(universe)
    common_start = coverage["common_start"]
    if common_start and start_date.date() < common_start.date():
        st.error(f"Start date cannot be earlier than common start date ({common_start.date()}).")
        return
    
    # Fetch price matrix
    with st.spinner("Fetching historical data (this may take a minute)..."):
        prices_df, fetch_status = get_price_matrix(
            universe=universe,
            start_date=start_date,
            end_date=end_date,
            force_refresh=force_refresh,
        )
    
    if prices_df.empty:
        st.error("Failed to fetch historical data. Check symbol mappings.")
        return
    
    # Display fetch status
    with st.expander("📊 Data Fetch Status", expanded=False):
        status_rows = []
        for ticker, (source, symbol, success) in fetch_status.items():
            status_rows.append({
                "Ticker": ticker,
                "Source": source,
                "Symbol": symbol,
                "Status": "✅ OK" if success else "❌ Failed",
            })
        st.dataframe(pd.DataFrame(status_rows), use_container_width=True)
    
    # Generate dates
    signal_dates = generate_signal_dates(prices_df.index, start_date, end_date)
    exec_dates = generate_exec_dates(prices_df.index, start_date, end_date, exec_freq)
    
    if not signal_dates:
        st.error("No signal dates generated. Check date range and data availability.")
        return
    
    # Build params
    params = BacktestParams(
        initial_capital=initial_capital,
        slots=slots,
        commission_bps=commission_bps,
        slippage_bps=slippage_bps,
        min_fee_eur=min_fee,
        exec_frequency_days=exec_freq,
        emergency_risk_off=emergency_off,
    )
    
    # Compute signals
    with st.spinner("Computing weekly signals..."):
        signals = compute_weekly_signals(prices_df, signal_dates, params)
    
    # Run backtest
    with st.spinner("Running backtest simulation..."):
        equity_df, exec_log_df, holdings_df = run_backtest(
            prices_df, signals, exec_dates, start_date, end_date, params
        )
    
    # Store results
    st.session_state["bt_equity"] = equity_df
    st.session_state["bt_exec_log"] = exec_log_df
    st.session_state["bt_holdings"] = holdings_df
    st.session_state["bt_signals"] = signals
    st.session_state["bt_params"] = params
    
    display_backtest_results()


def display_backtest_results():
    """Display backtest results from session state."""
    equity_df = st.session_state.get("bt_equity")
    exec_log_df = st.session_state.get("bt_exec_log")
    signals = st.session_state.get("bt_signals")
    params = st.session_state.get("bt_params")
    
    if equity_df is None or equity_df.empty:
        st.warning("No backtest results available.")
        return
    
    # Compute metrics
    metrics = compute_metrics(equity_df, exec_log_df)
    
    # Display metrics
    st.subheader("📊 Performance Metrics")
    
    TOOLTIPS = {
        "Total Return": "Total percentage return over the entire period.",
        "CAGR": "Compound Annual Growth Rate = (End/Start)^(1/years) - 1. Average annualized return.",
        "Volatility": "Annualized standard deviation of daily returns.",
        "Max Drawdown": "Maximum observed loss from a peak to a trough.",
        "Sharpe Ratio": "Annualized mean excess return / annualized volatility (risk-free rate = 0).",
        "Calmar Ratio": "CAGR / |Max Drawdown|. Return relative to downside risk.",
        "Total Costs": "Total transaction costs (commissions & slippage) incurred during rebalancing.",
        "Rebalances": "Total number of execution dates where trades occurred.",
    }
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Return", f"{metrics['total_return']:.2%}" if pd.notna(metrics['total_return']) else "-", help=TOOLTIPS["Total Return"])
    with col2:
        st.metric("CAGR", f"{metrics['cagr']:.2%}" if pd.notna(metrics['cagr']) else "-", help=TOOLTIPS["CAGR"])
    with col3:
        st.metric("Max Drawdown", f"{metrics['max_drawdown']:.2%}" if pd.notna(metrics['max_drawdown']) else "-", help=TOOLTIPS["Max Drawdown"])
    with col4:
        st.metric("Sharpe Ratio", f"{metrics['sharpe']:.2f}" if pd.notna(metrics['sharpe']) else "-", help=TOOLTIPS["Sharpe Ratio"])
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Volatility", f"{metrics['volatility']:.2%}" if pd.notna(metrics['volatility']) else "-", help=TOOLTIPS["Volatility"])
    with col2:
        st.metric("Calmar Ratio", f"{metrics['calmar']:.2f}" if pd.notna(metrics['calmar']) else "-", help=TOOLTIPS["Calmar Ratio"])
    with col3:
        st.metric("Total Costs", f"{metrics['total_costs']:.2f} EUR", help=TOOLTIPS["Total Costs"])
    with col4:
        st.metric("Rebalances", str(metrics['num_trades']), help=TOOLTIPS["Rebalances"])
    
    st.divider()
    
    # Equity curve
    st.subheader("📈 Equity Curve")
    chart_df = equity_df.reset_index()
    chart_df = chart_df.rename(columns={"date": "Date", "portfolio_value": "Portfolio Value", "daily_return": "Daily Return"})
    
    chart = alt.Chart(chart_df).mark_line().encode(
        x=alt.X("Date:T", title=""),
        y=alt.Y("Portfolio Value:Q", title="Portfolio Value (EUR)", scale=alt.Scale(zero=False)),
        tooltip=[
            alt.Tooltip("Date:T", format="%Y-%m-%d"),
            alt.Tooltip("Portfolio Value:Q", format=",.2f"),
            alt.Tooltip("Daily Return:Q", format=".2%"),
        ]
    ).interactive()
    
    st.altair_chart(chart, use_container_width=True)
    
    # Drawdown
    with st.expander("📉 Drawdown Chart", expanded=False):
        st.area_chart(equity_df["drawdown"], use_container_width=True)
    
    st.divider()
    
    # Execution log
    st.subheader("📝 Execution Log")
    if exec_log_df is not None and not exec_log_df.empty:
        st.data_editor(exec_log_df, use_container_width=True, height=300, disabled=True, hide_index=True)
        
        csv = exec_log_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Execution Log",
            data=csv,
            file_name="backtest_exec_log.csv",
            mime="text/csv",
            key="download_exec"
        )
    else:
        st.info("No executions recorded.")
    
    st.divider()
    
    # Signal log
    st.subheader("📋 Weekly Signal Log")
    if signals:
        signals_df = signals_to_dataframe(signals)
        st.data_editor(signals_df, use_container_width=True, height=300, disabled=True, hide_index=True)
        
        csv = signals_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Signal Log",
            data=csv,
            file_name="backtest_signals.csv",
            mime="text/csv",
            key="download_signals"
        )
    else:
        st.info("No signals recorded.")
    
    # Equity CSV download
    st.divider()
    csv = equity_df.to_csv()
    st.download_button(
        label="📥 Download Equity Curve",
        data=csv,
        file_name="backtest_equity.csv",
        mime="text/csv",
        key="download_equity"
    )


def render_theme():
    """Apply lightweight modern dark theme overriding Streamlit defaults."""
    st.markdown("""
        <style>
        :root {
            --bg: #121212;
            --panel: #1E1E1E;
            --panel-2: #282828;
            --text: #E0E0E0;
            --muted: #A0A0A0;
            --accent: #4DA8DA;
            --success: #66BB6A;
            --warning: #FFA726;
            --danger: #EF5350;
        }
        /* Base Streamlit overrides for lighter dark theme */
        .stApp {
            background-color: var(--bg);
            color: var(--text);
        }
        /* Style headers to reduce emoji noise slightly via standard font weights */
        h1, h2, h3 {
            font-weight: 500 !important;
            color: #FFFFFF !important;
        }
        /* Panels */
        .stExpander, .css-1d391kg {
            background-color: var(--panel) !important;
            border-color: var(--panel-2) !important;
        }
        </style>
    """, unsafe_allow_html=True)


def main():
    """Main Streamlit app with tabs."""
    render_theme()
    
    # Header
    st.title("🔄 Global Regime Rotator")
    
    # Profile selector
    profiles, default_profile = get_profiles_cached()
    
    if profiles:
        profile_options = list(profiles.keys())
        
        # Initialize session state if not set
        if "selected_profile" not in st.session_state:
            st.session_state["selected_profile"] = default_profile
            
        def on_profile_change():
            for key in [
                "current_results",
                "current_status",
                "current_as_of",
                "current_eval_mode",
                "current_total_allocation_target",
            ]:
                if key in st.session_state:
                    del st.session_state[key]
                
        try:
            current_idx = profile_options.index(st.session_state["selected_profile"])
        except ValueError:
            current_idx = 0
            
        col1, _ = st.columns([1, 2])
        with col1:
            selected_id = st.selectbox(
                "💼 Portfolio Profile",
                options=profile_options,
                index=current_idx,
                format_func=lambda x: profiles[x].get("label", x) if x in profiles else x,
                key="profile_selector"
            )
            
            if selected_id != st.session_state["selected_profile"]:
                st.session_state["selected_profile"] = selected_id
                on_profile_change()
                st.rerun()
                
    st.divider()
    
    # Tab navigation
    tab1, tab2 = st.tabs(["📊 Current Evaluation", "📈 Backtest"])
    
    with tab1:
        current_evaluation_tab()
    
    with tab2:
        backtest_tab()
    
    # Footer
    st.divider()
    footer_total_allocation = float(
        st.session_state.get(
            "current_total_allocation_target",
            st.session_state.get("current_total_allocation_input", TOTAL_ALLOCATION),
        )
    )
    footer_slot_amount = footer_total_allocation / NUM_SLOTS
    st.caption(f"""
    **Strategy Rules**: Momentum Score = 0.2×R1M + 0.4×R3M + 0.4×R6M | 
    Top 4 GREEN assets get {NUM_SLOTS} × {footer_slot_amount:,.2f} EUR = {footer_total_allocation:,.2f} EUR |
    Leftover → XEON (cash)
    """)


if __name__ == "__main__":
    main()
