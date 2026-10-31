from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from typing import Any
import yfinance as yf

from .config import DEFAULT_SYMBOLS, MAX_WORKERS, TICKER_NAMES
from .schemas import DateResult


def format_date(value: date) -> str:
    return value.strftime("%Y-%m-%d")


def normalize_symbol(symbol: str) -> str:
    cleaned = symbol.strip().upper()
    if len(cleaned) == 6 and cleaned.isdigit():
        return f"{cleaned}.KS"
    return cleaned


def fetch_symbol_ohlcv(symbol: str, start: date, end: date) -> list[dict[str, Any]]:
    # yfinance end date is exclusive, so query until end + 1 day
    query_end = end + timedelta(days=1)
    normalized = normalize_symbol(symbol)
    company_name = TICKER_NAMES.get(normalized, normalized)

    try:
        ticker = yf.Ticker(normalized)
        df = ticker.history(
            start=start.isoformat(),
            end=query_end.isoformat(),
            auto_adjust=False,
        )
    except Exception:
        return []

    if df is None or df.empty:
        return []

    records: list[dict[str, Any]] = []
    for dt_index, row in df.iterrows():
        if hasattr(dt_index, "date"):
            record_date = dt_index.date()
        else:
            record_date = dt_index
        date_str = record_date.strftime("%Y-%m-%d") if hasattr(record_date, "strftime") else str(record_date)[:10]
        bas_dd = date_str.replace("-", "")

        o = float(row.get("Open", 0.0))
        h = float(row.get("High", 0.0))
        l = float(row.get("Low", 0.0))
        c = float(row.get("Close", 0.0))
        v = float(row.get("Volume", 0.0))

        records.append({
            "date": date_str,
            "bas_dd": bas_dd,
            "BAS_DD": bas_dd,
            "symbol": normalized,
            "ISU_CD": normalized,
            "name": company_name,
            "ISU_NM": company_name,
            "MKT_NM": "US" if "." not in normalized else normalized.partition(".")[2],
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": v,
            "TDD_OPNPRC": o,
            "TDD_HGPRC": h,
            "TDD_LWPRC": l,
            "TDD_CLSPRC": c,
            "ACC_TRDVOL": v,
        })

    return records


def collect_daily_trading(start: date, end: date, symbols: list[str] | None = None) -> list[DateResult]:
    target_symbols = [normalize_symbol(s) for s in (symbols or DEFAULT_SYMBOLS) if s.strip()]
    if not target_symbols:
        target_symbols = [normalize_symbol(s) for s in DEFAULT_SYMBOLS]

    date_records: dict[str, list[dict[str, Any]]] = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(fetch_symbol_ohlcv, sym, start, end): sym for sym in target_symbols}
        for future in as_completed(futures):
            try:
                records = future.result()
                for rec in records:
                    d = rec["date"]
                    date_records.setdefault(d, []).append(rec)
            except Exception:
                continue

    results: list[DateResult] = []
    for d in sorted(date_records.keys()):
        results.append(DateResult(
            date=d,
            bas_dd=d.replace("-", ""),
            records=date_records[d],
        ))
    return results
