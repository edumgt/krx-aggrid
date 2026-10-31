from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Query

from .analysis import clean_ohlcv, enrich_features, run_cluster_analysis
from .config import DEFAULT_SYMBOLS, MAX_DAYS
from .schemas import DailyTradingResponse
from .yahoo_client import collect_daily_trading, format_date


app = FastAPI(
    title="Yahoo Finance OHLCV 군집 분석 API",
    description="Yahoo Finance 다중 티커 OHLCV를 수집·정제하고 10차원 파생 특성을 2D/3D로 투영합니다.",
    version="3.0.0",
)


def parse_date(value: str) -> date:
    clean = value.replace("-", "").replace("/", "").strip()
    try:
        return datetime.strptime(clean, "%Y%m%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="날짜는 YYYY-MM-DD 또는 YYYYMMDD 형식이어야 합니다.") from exc


def validated_period(from_: str, to: str) -> tuple[date, date]:
    start, end = parse_date(from_), parse_date(to)
    if start > end:
        raise HTTPException(status_code=422, detail="from은 to보다 늦을 수 없습니다.")
    if (end - start).days + 1 > MAX_DAYS:
        raise HTTPException(status_code=422, detail=f"조회 기간은 최대 {MAX_DAYS}일입니다.")
    return start, end


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "backend", "data_source": "yahoo_finance"}


@app.get("/api/v1/stocks/daily", response_model=DailyTradingResponse, tags=["stocks"])
def get_daily_trading(
    from_: str = Query(..., alias="from", description="조회 시작일 (YYYY-MM-DD)"),
    to: str = Query(..., description="조회 종료일 (YYYY-MM-DD)"),
    symbols: str | None = Query(None, description="쉼표로 구분한 티커 목록"),
) -> DailyTradingResponse:
    start, end = validated_period(from_, to)
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()] if symbols else DEFAULT_SYMBOLS
    data = collect_daily_trading(start, end, symbol_list)
    return DailyTradingResponse(
        from_date=format_date(start),
        to_date=format_date(end),
        trading_days=len(data),
        record_count=sum(len(item.records) for item in data),
        symbols=symbol_list,
        data=data,
    )


@app.get("/api/v1/stocks/analysis", tags=["stocks"])
def get_stock_analysis(
    from_: str = Query(..., alias="from", description="조회 시작일 (YYYY-MM-DD)"),
    to: str = Query(..., description="조회 종료일 (YYYY-MM-DD)"),
    clusters: int = Query(5, ge=2, le=8, description="K-Means 군집 수"),
    symbols: str | None = Query(None, description="쉼표로 구분한 티커 목록"),
) -> dict[str, Any]:
    start, end = validated_period(from_, to)
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()] if symbols else DEFAULT_SYMBOLS
    days = collect_daily_trading(start, end, symbol_list)
    cleaned, rejected = clean_ohlcv(days)
    analyzed, analysis = run_cluster_analysis(enrich_features(cleaned), clusters)
    analyzed.sort(key=lambda row: (str(row.get("date", "")), str(row.get("symbol", ""))))
    return {
        "from_date": format_date(start),
        "to_date": format_date(end),
        "trading_days": len(days),
        "record_count": len(analyzed),
        "rejected_count": rejected,
        "symbols": symbol_list,
        "data": analyzed,
        "analysis": analysis,
    }
