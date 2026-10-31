from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Query

from .analysis import clean_ohlcv, enrich_features, run_cluster_analysis
from .config import KRX_API_MODE, MAX_DAYS
from .krx_client import collect_daily_trading, format_date
from .schemas import DailyTradingResponse


app = FastAPI(
    title="KRX OHLCV 군집 분석 API",
    description="KRX OHLCV를 수집·정제하고 고차원 파생 특성을 2D/3D로 투영합니다.",
    version="2.1.0",
)


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value.replace("-", ""), "%Y%m%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="날짜는 YYYYMMDD 또는 YYYY-MM-DD 형식이어야 합니다.") from exc


def validated_period(from_: str, to: str) -> tuple[date, date]:
    start, end = parse_date(from_), parse_date(to)
    if start > end:
        raise HTTPException(status_code=422, detail="from은 to보다 늦을 수 없습니다.")
    if (end - start).days + 1 > MAX_DAYS:
        raise HTTPException(status_code=422, detail=f"조회 기간은 최대 {MAX_DAYS}일입니다.")
    return start, end


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "backend", "krx_api_mode": KRX_API_MODE}


@app.get("/api/v1/stocks/daily", response_model=DailyTradingResponse, tags=["stocks"])
def get_daily_trading(
    from_: str = Query(..., alias="from", description="조회 시작일"),
    to: str = Query(..., description="조회 종료일"),
) -> DailyTradingResponse:
    start, end = validated_period(from_, to)
    data = collect_daily_trading(start, end)
    return DailyTradingResponse(
        from_date=format_date(start), to_date=format_date(end), trading_days=len(data),
        record_count=sum(len(item.records) for item in data), data=data,
    )


@app.get("/api/v1/stocks/analysis", tags=["stocks"])
def get_stock_analysis(
    from_: str = Query(..., alias="from", description="조회 시작일"),
    to: str = Query(..., description="조회 종료일"),
    clusters: int = Query(5, ge=2, le=8, description="K-Means 군집 수"),
    symbols: str | None = Query(None, description="쉼표로 구분한 종목코드"),
) -> dict[str, Any]:
    start, end = validated_period(from_, to)
    symbol_set = {value.strip() for value in symbols.split(",") if value.strip()} if symbols else None
    days = collect_daily_trading(start, end)
    cleaned, rejected = clean_ohlcv(days, symbol_set)
    analyzed, analysis = run_cluster_analysis(enrich_features(cleaned), clusters)
    analyzed.sort(key=lambda row: (str(row.get("BAS_DD", "")), str(row.get("ISU_CD", ""))))
    return {
        "from_date": format_date(start), "to_date": format_date(end), "trading_days": len(days),
        "record_count": len(analyzed), "rejected_count": rejected, "data": analyzed, "analysis": analysis,
    }
