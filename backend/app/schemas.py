from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DateResult(BaseModel):
    bas_dd: str = Field(description="기준일자 (YYYYMMDD)")
    records: list[dict[str, Any]] = Field(description="해당 일자의 종목별 매매정보")


class DailyTradingResponse(BaseModel):
    from_date: str = Field(description="조회 시작일 (YYYYMMDD)")
    to_date: str = Field(description="조회 종료일 (YYYYMMDD)")
    trading_days: int = Field(description="데이터가 반환된 거래일 수")
    record_count: int = Field(description="반환된 전체 종목 레코드 수")
    data: list[DateResult]
