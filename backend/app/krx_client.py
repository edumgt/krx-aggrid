"""Compatibility shim: KRX client replaced with Yahoo Finance client."""
from .yahoo_client import collect_daily_trading, fetch_symbol_ohlcv, format_date

__all__ = ["format_date", "fetch_symbol_ohlcv", "collect_daily_trading"]
