from __future__ import annotations

import math
from collections import defaultdict, deque
from typing import Any

import numpy as np
from fastapi import HTTPException
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from .schemas import DateResult


FEATURE_NAMES = [
    "return_rate", "gap_rate", "body_ratio", "clv", "range_rate",
    "volatility_5d", "volume_change", "volume_ratio_20d",
    "log_trading_value", "turnover_rate",
]
NUMERIC_FIELDS = {
    "TDD_OPNPRC", "TDD_HGPRC", "TDD_LWPRC", "TDD_CLSPRC", "ACC_TRDVOL",
    "ACC_TRDVAL", "MKTCAP", "LIST_SHRS", "CMPPREVDD_PRC", "FLUC_RT",
}


def to_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).replace(",", "").strip()
        if not text or text in {"-", "N/A", "null"}:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
    return number if math.isfinite(number) else None


def clean_ohlcv(days: list[DateResult], symbols: set[str] | None = None) -> tuple[list[dict[str, Any]], int]:
    cleaned: list[dict[str, Any]] = []
    rejected = 0
    seen: set[tuple[str, str]] = set()
    for day in days:
        for source in day.records:
            row = dict(source)
            row.setdefault("BAS_DD", day.bas_dd)
            code = str(row.get("ISU_CD", "")).strip()
            if symbols and code not in symbols:
                continue
            key = (str(row["BAS_DD"]), code)
            for field in NUMERIC_FIELDS:
                if field in row:
                    row[field] = to_number(row[field])
            o, high, low, close, volume = (
                row.get(field) for field in
                ("TDD_OPNPRC", "TDD_HGPRC", "TDD_LWPRC", "TDD_CLSPRC", "ACC_TRDVOL")
            )
            valid = (
                code and key not in seen
                and all(value is not None and value > 0 for value in (o, high, low, close))
                and volume is not None and volume >= 0
                and high >= max(o, close) and low <= min(o, close)
            )
            if not valid:
                rejected += 1
                continue
            seen.add(key)
            cleaned.append(row)
    cleaned.sort(key=lambda row: (str(row.get("ISU_CD", "")), str(row.get("BAS_DD", ""))))
    return cleaned, rejected


def enrich_features(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    histories: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"close": None, "volume": None, "volumes": deque(maxlen=20), "returns": deque(maxlen=5)}
    )
    enriched: list[dict[str, Any]] = []
    for row in rows:
        history = histories[str(row["ISU_CD"])]
        o, high, low, close, volume = (
            float(row[field]) for field in
            ("TDD_OPNPRC", "TDD_HGPRC", "TDD_LWPRC", "TDD_CLSPRC", "ACC_TRDVOL")
        )
        previous_close, previous_volume = history["close"], history["volume"]
        daily_return = close / previous_close - 1 if previous_close else 0.0
        gap = o / previous_close - 1 if previous_close else 0.0
        price_range = high - low
        average_volume = sum(history["volumes"]) / len(history["volumes"]) if history["volumes"] else volume
        volume_ratio = volume / average_volume if average_volume > 0 else 1.0
        volume_change = volume / previous_volume - 1 if previous_volume and previous_volume > 0 else 0.0
        history["returns"].append(daily_return)
        trading_value = row.get("ACC_TRDVAL") or close * volume
        listed_shares = row.get("LIST_SHRS") or 0
        features = {
            "return_rate": daily_return,
            "gap_rate": gap,
            "body_ratio": (close - o) / price_range if price_range else 0.0,
            "clv": (2 * close - high - low) / price_range if price_range else 0.0,
            "range_rate": price_range / previous_close if previous_close else price_range / close,
            "volatility_5d": float(np.std(list(history["returns"]), ddof=0)),
            "volume_change": volume_change,
            "volume_ratio_20d": volume_ratio,
            "log_trading_value": math.log1p(max(float(trading_value), 0.0)),
            "turnover_rate": volume / listed_shares if listed_shares and listed_shares > 0 else 0.0,
        }
        output = dict(row)
        output.update({name: round(float(value), 8) for name, value in features.items()})
        enriched.append(output)
        history["close"], history["volume"] = close, volume
        history["volumes"].append(volume)
    return enriched


def cluster_label(centroid: np.ndarray, used: set[str]) -> str:
    labels = [
        ("상승 모멘텀", "하락 압력"), ("상승 갭", "하락 갭"),
        ("매수 우위", "매도 우위"), ("고가 마감", "저가 마감"),
        ("고변동", "저변동"), ("변동성 확대", "변동성 안정"),
        ("거래량 급증", "거래량 감소"), ("거래 과열", "거래 소외"),
        ("대형 유동성", "소형 유동성"), ("회전율 활발", "회전율 둔화"),
    ]
    for index in np.argsort(np.abs(centroid))[::-1]:
        name = labels[int(index)][0 if centroid[index] >= 0 else 1]
        if name not in used:
            used.add(name)
            return name
    return "중립 패턴"


def run_cluster_analysis(rows: list[dict[str, Any]], requested_clusters: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if len(rows) < 2:
        raise HTTPException(status_code=422, detail="군집 분석에는 유효한 OHLCV 레코드가 2건 이상 필요합니다.")
    matrix = np.asarray([[row[name] for name in FEATURE_NAMES] for row in rows], dtype=float)
    clipped = np.clip(matrix, np.percentile(matrix, 1, axis=0), np.percentile(matrix, 99, axis=0))
    scaled = StandardScaler().fit_transform(clipped)
    cluster_count = min(requested_clusters, len(rows))
    model = KMeans(n_clusters=cluster_count, n_init=10, random_state=42)
    labels = model.fit_predict(scaled)
    component_count = min(3, scaled.shape[0], scaled.shape[1])
    pca = PCA(n_components=component_count, random_state=42)
    projection = pca.fit_transform(scaled)
    used_labels: set[str] = set()
    profiles: list[dict[str, Any]] = []
    human_labels: dict[int, str] = {}
    for cluster_id in range(cluster_count):
        mask = labels == cluster_id
        human_label = cluster_label(model.cluster_centers_[cluster_id], used_labels)
        human_labels[cluster_id] = human_label
        profiles.append({
            "cluster": cluster_id, "label": human_label, "count": int(mask.sum()),
            "mean_return": round(float(matrix[mask, FEATURE_NAMES.index("return_rate")].mean()), 6),
            "mean_range": round(float(matrix[mask, FEATURE_NAMES.index("range_rate")].mean()), 6),
            "mean_volume_ratio": round(float(matrix[mask, FEATURE_NAMES.index("volume_ratio_20d")].mean()), 4),
        })
    for index, row in enumerate(rows):
        cluster_id = int(labels[index])
        row.update({
            "cluster": cluster_id, "cluster_label": human_labels[cluster_id],
            "pca_x": round(float(projection[index, 0]), 6),
            "pca_y": round(float(projection[index, 1]) if component_count > 1 else 0.0, 6),
            "pca_z": round(float(projection[index, 2]) if component_count > 2 else 0.0, 6),
        })
    return rows, {
        "feature_names": FEATURE_NAMES, "cluster_count": cluster_count, "profiles": profiles,
        "explained_variance_ratio": [round(float(value), 6) for value in pca.explained_variance_ratio_],
        "preprocessing": "OHLC 유효성 검증 → 1~99% 윈저라이징 → 표준화 → K-Means/PCA",
    }
