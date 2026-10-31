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


# OHLCV 기반 10차원 벡터 (비율, 모멘텀, 변동성, 거래 에너지)
FEATURE_NAMES = [
    "return_rate",
    "gap_rate",
    "momentum_5d",
    "body_ratio",
    "clv",
    "upper_shadow_ratio",
    "range_rate",
    "volatility_5d",
    "volume_change",
    "volume_ratio_20d",
]

NUMERIC_FIELDS = {
    "open", "high", "low", "close", "volume",
    "TDD_OPNPRC", "TDD_HGPRC", "TDD_LWPRC", "TDD_CLSPRC", "ACC_TRDVOL",
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
            date_val = str(row.get("date") or row.get("BAS_DD") or day.date or day.bas_dd).strip()
            row["date"] = date_val
            row["BAS_DD"] = date_val.replace("-", "")

            code = str(row.get("symbol") or row.get("ISU_CD") or "").strip()
            if not code:
                rejected += 1
                continue
            if symbols and code not in symbols and code.upper() not in symbols:
                continue

            row["symbol"] = code
            row["ISU_CD"] = code
            name = str(row.get("name") or row.get("ISU_NM") or code)
            row["name"] = name
            row["ISU_NM"] = name

            key = (date_val, code)

            # Support both new and legacy field names
            for field in NUMERIC_FIELDS:
                if field in row:
                    row[field] = to_number(row[field])

            o = row.get("open") if row.get("open") is not None else row.get("TDD_OPNPRC")
            high = row.get("high") if row.get("high") is not None else row.get("TDD_HGPRC")
            low = row.get("low") if row.get("low") is not None else row.get("TDD_LWPRC")
            close = row.get("close") if row.get("close") is not None else row.get("TDD_CLSPRC")
            volume = row.get("volume") if row.get("volume") is not None else row.get("ACC_TRDVOL")

            valid = (
                key not in seen
                and all(value is not None and value > 0 for value in (o, high, low, close))
                and volume is not None and volume >= 0
                and high >= max(o, close) and low <= min(o, close)
            )
            if not valid:
                rejected += 1
                continue

            seen.add(key)
            row["open"] = o
            row["high"] = high
            row["low"] = low
            row["close"] = close
            row["volume"] = volume
            # Ensure legacy field names are also populated for FE compatibility
            row["TDD_OPNPRC"] = o
            row["TDD_HGPRC"] = high
            row["TDD_LWPRC"] = low
            row["TDD_CLSPRC"] = close
            row["ACC_TRDVOL"] = volume

            cleaned.append(row)

    # Sort per symbol chronologically
    cleaned.sort(key=lambda item: (str(item.get("symbol", "")), str(item.get("date", ""))))
    return cleaned, rejected


def enrich_features(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    histories: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "closes": deque(maxlen=20),
            "volumes": deque(maxlen=20),
            "returns": deque(maxlen=5),
        }
    )
    enriched: list[dict[str, Any]] = []

    for row in rows:
        symbol = str(row["symbol"])
        history = histories[symbol]

        o, high, low, close, volume = (
            float(row[field]) for field in ("open", "high", "low", "close", "volume")
        )

        prev_close = history["closes"][-1] if history["closes"] else None
        prev_volume = history["volumes"][-1] if history["volumes"] else None
        close_5d = history["closes"][-5] if len(history["closes"]) >= 5 else (history["closes"][0] if history["closes"] else close)

        daily_return = (close / prev_close - 1.0) if (prev_close and prev_close > 0) else 0.0
        gap = (o / prev_close - 1.0) if (prev_close and prev_close > 0) else 0.0
        momentum_5d = (close / close_5d - 1.0) if (close_5d and close_5d > 0) else 0.0

        price_range = high - low
        body_ratio = ((close - o) / price_range) if price_range > 0 else 0.0
        clv = ((2.0 * close - high - low) / price_range) if price_range > 0 else 0.0
        upper_shadow_ratio = ((high - max(o, close)) / price_range) if price_range > 0 else 0.0

        range_rate = (price_range / prev_close) if (prev_close and prev_close > 0) else (price_range / close if close > 0 else 0.0)

        history["returns"].append(daily_return)
        volatility_5d = float(np.std(list(history["returns"]), ddof=0))

        avg_volume_20d = (sum(history["volumes"]) / len(history["volumes"])) if history["volumes"] else volume
        volume_change = (volume / prev_volume - 1.0) if (prev_volume and prev_volume > 0) else 0.0
        volume_ratio_20d = (volume / avg_volume_20d) if (avg_volume_20d and avg_volume_20d > 0) else 1.0

        features = {
            "return_rate": daily_return,
            "gap_rate": gap,
            "momentum_5d": momentum_5d,
            "body_ratio": body_ratio,
            "clv": clv,
            "upper_shadow_ratio": upper_shadow_ratio,
            "range_rate": range_rate,
            "volatility_5d": volatility_5d,
            "volume_change": volume_change,
            "volume_ratio_20d": volume_ratio_20d,
        }

        output = dict(row)
        output.update({name: round(float(value), 8) for name, value in features.items()})
        output["change_rate"] = round(daily_return, 6)
        output["FLUC_RT"] = round(daily_return * 100.0, 4)
        enriched.append(output)

        history["closes"].append(close)
        history["volumes"].append(volume)

    return enriched


def cluster_label(centroid: np.ndarray, used: set[str]) -> str:
    labels = [
        ("상승 모멘텀", "하락 압력"),       # 0: return_rate
        ("상승 갭", "하락 갭"),             # 1: gap_rate
        ("중기 상승세", "중기 하락세"),     # 2: momentum_5d
        ("강한 양봉", "강한 음봉"),         # 3: body_ratio
        ("고가 마감", "저가 마감"),         # 4: clv
        ("매도 저항", "상방 돌파"),         # 5: upper_shadow_ratio
        ("고변동", "저변동"),               # 6: range_rate
        ("변동성 확대", "변동성 안정"),     # 7: volatility_5d
        ("거래량 급증", "거래량 감소"),     # 8: volume_change
        ("거래 과열", "거래 소외"),         # 9: volume_ratio_20d
    ]
    for index in np.argsort(np.abs(centroid))[::-1]:
        if index < len(labels):
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
            "cluster": cluster_id,
            "label": human_label,
            "count": int(mask.sum()),
            "mean_return": round(float(matrix[mask, FEATURE_NAMES.index("return_rate")].mean()), 6),
            "mean_range": round(float(matrix[mask, FEATURE_NAMES.index("range_rate")].mean()), 6),
            "mean_volume_ratio": round(float(matrix[mask, FEATURE_NAMES.index("volume_ratio_20d")].mean()), 4),
        })

    for index, row in enumerate(rows):
        cluster_id = int(labels[index])
        row.update({
            "cluster": cluster_id,
            "cluster_label": human_labels[cluster_id],
            "pca_x": round(float(projection[index, 0]), 6),
            "pca_y": round(float(projection[index, 1]) if component_count > 1 else 0.0, 6),
            "pca_z": round(float(projection[index, 2]) if component_count > 2 else 0.0, 6),
        })

    return rows, {
        "feature_names": FEATURE_NAMES,
        "cluster_count": cluster_count,
        "profiles": profiles,
        "explained_variance_ratio": [round(float(value), 6) for value in pca.explained_variance_ratio_],
        "preprocessing": "OHLC 유효성 검증 → 1~99% 윈저라이징 → 표준화 → K-Means/PCA",
    }
