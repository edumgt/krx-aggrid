from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import HTTPException

from .config import KRX_ENDPOINT, MAX_WORKERS, get_krx_key
from .schemas import DateResult


def format_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def dates_between(from_date: date, to_date: date) -> list[str]:
    current = from_date
    dates: list[str] = []
    while current <= to_date:
        if current.weekday() < 5:
            dates.append(format_date(current))
        current += timedelta(days=1)
    return dates


def fetch_one_day(bas_dd: str, api_key: str) -> DateResult:
    request = Request(
        f"{KRX_ENDPOINT}?{urlencode({'basDd': bas_dd})}",
        headers={"AUTH_KEY": api_key, "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"KRX API HTTP 오류 ({bas_dd}): {exc.code}") from exc
    except (URLError, TimeoutError) as exc:
        raise HTTPException(status_code=502, detail=f"KRX API 연결 오류 ({bas_dd})") from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail=f"KRX API 응답 형식 오류 ({bas_dd})") from exc

    records = payload.get("OutBlock_1", [])
    if not isinstance(records, list):
        raise HTTPException(status_code=502, detail=f"KRX API 응답 구조 오류 ({bas_dd})")
    return DateResult(bas_dd=bas_dd, records=records)


def collect_daily_trading(start: date, end: date) -> list[DateResult]:
    api_key = get_krx_key()
    results: dict[str, DateResult] = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(fetch_one_day, day, api_key): day for day in dates_between(start, end)}
        for future in as_completed(futures):
            result = future.result()
            if result.records:
                results[result.bas_dd] = result
    return [results[day] for day in sorted(results)]
