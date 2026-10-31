"""Test script: Collect 2 years of Samsung Electronics data and verify the entire pipeline."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

# Add backend directory to sys.path
backend_path = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.analysis import FEATURE_NAMES, clean_ohlcv, enrich_features, run_cluster_analysis
from app.main import app
from app.yahoo_client import collect_daily_trading, normalize_symbol
from fastapi.testclient import TestClient


def main():
    print("=" * 60)
    print(" 삼성전자 (005930.KS) 2년치 데이터 수집 및 파이프라인 검증")
    print("=" * 60)

    start_date = date(2024, 10, 30)
    end_date = date(2026, 10, 30)
    symbol = "005930"

    # 1. 티커 정규화 확인
    normalized = normalize_symbol(symbol)
    print(f"\n[1] 티커 정규화: '{symbol}' -> '{normalized}'")
    assert normalized == "005930.KS", f"정규화 실패: {normalized}"

    # 2. 데이터 수집
    print(f"\n[2] 데이터 수집 기간: {start_date} ~ {end_date}")
    trading_days = collect_daily_trading(start_date, end_date, symbols=[symbol])
    total_collected_records = sum(len(d.records) for d in trading_days)
    print(f" -> 수집된 거래일 수: {len(trading_days)}일")
    print(f" -> 수집된 전체 레코드: {total_collected_records}건")
    assert len(trading_days) >= 400, f"예상보다 적은 거래일 수: {len(trading_days)}"

    # 3. 데이터 정제 (OHLCV 유효성 검사)
    print("\n[3] OHLCV 유효성 검사 및 정제")
    cleaned, rejected = clean_ohlcv(trading_days)
    print(f" -> 정제 통과 레코드: {len(cleaned)}건")
    print(f" -> 유효성 결격 제외: {rejected}건")
    assert len(cleaned) > 0, "정제된 레코드가 없습니다."
    assert rejected == 0, f"비정상 캔들 결격 레코드 발생: {rejected}건"

    # 첫 번째 및 마지막 레코드 출력
    first = cleaned[0]
    last = cleaned[-1]
    print(f" -> 시작 레코드: {first['date']} | 시가: {first['open']:,} | 고가: {first['high']:,} | 저가: {first['low']:,} | 종가: {first['close']:,} | 거래량: {first['volume']:,}")
    print(f" -> 최신 레코드: {last['date']} | 시가: {last['open']:,} | 고가: {last['high']:,} | 저가: {last['low']:,} | 종가: {last['close']:,} | 거래량: {last['volume']:,}")

    # 4. 10차원 특성 생성
    print("\n[4] 10차원 무차원/비율 특성 추출")
    enriched = enrich_features(cleaned)
    sample_row = enriched[-1]
    print(" -> 계산된 10차원 특성 (최신 레코드 기준):")
    for fname in FEATURE_NAMES:
        val = sample_row.get(fname)
        print(f"    - {fname:20s}: {val:12.6f}")

    assert all(fname in sample_row for fname in FEATURE_NAMES), "누락된 10차원 특성이 있습니다."

    # 5. K-Means 군집화 및 PCA 2D/3D 투영
    cluster_k = 5
    print(f"\n[5] K-Means (K={cluster_k}) 군집화 및 PCA 주성분 투영")
    analyzed, analysis_meta = run_cluster_analysis(enriched, cluster_k)
    print(f" -> 분석 완료 레코드: {len(analyzed)}건")
    print(f" -> PCA 설명력 비율 (PC1, PC2, PC3): {[round(v * 100, 2) for v in analysis_meta['explained_variance_ratio']]}")
    print(f" -> PCA 3개 주성분 누적 설명력: {sum(analysis_meta['explained_variance_ratio']) * 100:.2f}%")

    print("\n -> 발견된 군집 프로필:")
    for prof in analysis_meta["profiles"]:
        print(f"    [군집 C{prof['cluster']} - {prof['label']:8s}] 레코드 {prof['count']:3d}건 "
              f"| 평균수익률 {prof['mean_return'] * 100:+6.2f}% "
              f"| 평균고저폭 {prof['mean_range'] * 100:5.2f}% "
              f"| 거래량배수 {prof['mean_volume_ratio']:5.2f}x")

    # 6. FastAPI 엔드포인트 종합 호출 테스트
    print("\n[6] FastAPI 엔드포인트 (/api/v1/stocks/analysis) 종합 테스트")
    client = TestClient(app)
    response = client.get(
        "/api/v1/stocks/analysis",
        params={
            "from": start_date.strftime("%Y-%m-%d"),
            "to": end_date.strftime("%Y-%m-%d"),
            "symbols": symbol,
            "clusters": cluster_k,
        },
    )
    assert response.status_code == 200, f"API 오류: {response.status_code} - {response.text}"
    api_result = response.json()
    print(f" -> HTTP 상태: {response.status_code} OK")
    print(f" -> 반환된 record_count: {api_result['record_count']}")
    print(f" -> 반환된 trading_days: {api_result['trading_days']}")
    print(f" -> 반환된 symbols: {api_result['symbols']}")
    print(f" -> API 군집 수: {api_result['analysis']['cluster_count']}")

    print("\n" + "=" * 60)
    print(" 삼성전자 2년치 데이터 수집 및 전체 파이프라인 검증 성공!")
    print("=" * 60)


if __name__ == "__main__":
    main()
