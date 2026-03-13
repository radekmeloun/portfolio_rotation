"""
Performance metrics module for Global Regime Rotator backtest.

Provides:
- compute_metrics(): Calculate CAGR, volatility, max DD, Sharpe, Calmar, etc.
"""

import numpy as np
import pandas as pd


def compute_metrics(
    equity_df: pd.DataFrame,
    exec_log_df: pd.DataFrame = None,
    freq: int = 252
) -> dict:
    """
    Compute performance metrics from equity curve.
    
    Args:
        equity_df: DataFrame with 'portfolio_value', 'daily_return', 'drawdown' columns
        exec_log_df: Optional execution log for turnover calculation
        freq: Trading days per year (default 252)
    
    Returns:
        Dict of performance metrics
    """
    if equity_df.empty:
        return {
            "total_return": np.nan,
            "cagr": np.nan,
            "volatility": np.nan,
            "max_drawdown": np.nan,
            "sharpe": np.nan,
            "calmar": np.nan,
            "avg_yearly_turnover": np.nan,
            "total_costs": np.nan,
            "num_trades": 0,
        }
    
    # Total return
    start_value = equity_df["portfolio_value"].iloc[0]
    end_value = equity_df["portfolio_value"].iloc[-1]
    total_return = (end_value / start_value) - 1
    
    # CAGR
    num_days = len(equity_df)
    years = num_days / freq
    if years > 0 and end_value > 0 and start_value > 0:
        cagr = (end_value / start_value) ** (1 / years) - 1
    else:
        cagr = np.nan
    
    # Annualized volatility
    daily_returns = equity_df["daily_return"]
    volatility = daily_returns.std() * np.sqrt(freq)
    
    # Max drawdown
    max_drawdown = equity_df["drawdown"].min() if "drawdown" in equity_df.columns else np.nan
    
    # Sharpe ratio (rf = 0)
    mean_return = daily_returns.mean() * freq
    if volatility > 0:
        sharpe = mean_return / volatility
    else:
        sharpe = np.nan
    
    # Calmar ratio
    if max_drawdown < 0:
        calmar = cagr / abs(max_drawdown)
    else:
        calmar = np.nan
    
    # Turnover and costs from exec log
    avg_yearly_turnover = np.nan
    total_costs = 0.0
    num_trades = 0
    
    if exec_log_df is not None and not exec_log_df.empty:
        total_turnover = exec_log_df["turnover"].sum()
        total_costs = exec_log_df["cost_eur"].sum()
        num_trades = len(exec_log_df)
        
        if years > 0:
            avg_yearly_turnover = total_turnover / years
    
    return {
        "total_return": total_return,
        "cagr": cagr,
        "volatility": volatility,
        "max_drawdown": max_drawdown,
        "sharpe": sharpe,
        "calmar": calmar,
        "avg_yearly_turnover": avg_yearly_turnover,
        "total_costs": total_costs,
        "num_trades": num_trades,
    }


def format_metrics_for_display(metrics: dict) -> pd.DataFrame:
    """
    Format metrics dict as display-ready DataFrame.
    
    Args:
        metrics: Dict from compute_metrics()
    
    Returns:
        DataFrame with Metric and Value columns
    """
    rows = [
        ("Total Return", f"{metrics['total_return']:.2%}" if pd.notna(metrics['total_return']) else "-"),
        ("CAGR", f"{metrics['cagr']:.2%}" if pd.notna(metrics['cagr']) else "-"),
        ("Volatility (Ann.)", f"{metrics['volatility']:.2%}" if pd.notna(metrics['volatility']) else "-"),
        ("Max Drawdown", f"{metrics['max_drawdown']:.2%}" if pd.notna(metrics['max_drawdown']) else "-"),
        ("Sharpe Ratio", f"{metrics['sharpe']:.2f}" if pd.notna(metrics['sharpe']) else "-"),
        ("Calmar Ratio", f"{metrics['calmar']:.2f}" if pd.notna(metrics['calmar']) else "-"),
        ("Avg Yearly Turnover", f"{metrics['avg_yearly_turnover']:.2f}x" if pd.notna(metrics['avg_yearly_turnover']) else "-"),
        ("Total Trading Costs", f"{metrics['total_costs']:.2f} EUR"),
        ("Number of Rebalances", str(metrics['num_trades'])),
    ]
    
    return pd.DataFrame(rows, columns=["Metric", "Value"])
