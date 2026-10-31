import unittest
from app.analysis import FEATURE_NAMES, clean_ohlcv, enrich_features, run_cluster_analysis
from app.main import app, parse_date
from app.schemas import DateResult
from app.yahoo_client import normalize_symbol
from fastapi.testclient import TestClient


def sample(day: str, code: str, open_: float | str, high: float | str, low: float | str, close: float | str, volume: float | str) -> dict[str, str]:
    return {
        "date": day,
        "symbol": code,
        "name": f"종목-{code}",
        "open": str(open_),
        "high": str(high),
        "low": str(low),
        "close": str(close),
        "volume": str(volume),
    }


class OhlcvPipelineTests(unittest.TestCase):
    def test_parse_date(self) -> None:
        self.assertEqual(parse_date("2026-10-31").isoformat(), "2026-10-31")
        self.assertEqual(parse_date("20261031").isoformat(), "2026-10-31")
        self.assertEqual(parse_date("2026/10/31").isoformat(), "2026-10-31")

    def test_normalize_symbol(self) -> None:
        self.assertEqual(normalize_symbol("005930"), "005930.KS")
        self.assertEqual(normalize_symbol("000660.ks"), "000660.KS")
        self.assertEqual(normalize_symbol("aapl"), "AAPL")
        self.assertEqual(normalize_symbol("  msft  "), "MSFT")

    def test_cleaning_types_numbers_and_rejects_invalid_candles(self) -> None:
        valid = sample("2026-01-02", "AAPL", 150.0, 155.0, 149.0, 153.0, 1000000)
        invalid = sample("2026-01-02", "MSFT", 300.0, 290.0, 280.0, 295.0, 500000)  # high < open
        rows, rejected = clean_ohlcv([DateResult(date="2026-01-02", records=[valid, invalid])])
        self.assertEqual((len(rows), rejected), (1, 1))
        self.assertEqual(rows[0]["close"], 153.0)
        self.assertEqual(rows[0]["symbol"], "AAPL")

    def test_enrichment_and_clustering_add_projection(self) -> None:
        records = []
        for index in range(12):
            base = 100.0 + index * 1.5
            close = base + (-1 if index % 3 == 0 else 1) * (1.2 + index * 0.1)
            high = max(base, close) + 1.5 + index * 0.1
            low = min(base, close) - 1.0
            volume = 100000 + index * index * 5000
            records.append(sample(
                f"2026-01-{index + 1:02d}", "AAPL", base, high, low, close, volume,
            ))

        rows, rejected = clean_ohlcv([DateResult(date="2026-01-01", records=records)])
        enriched = enrich_features(rows)
        analyzed, metadata = run_cluster_analysis(enriched, 3)

        self.assertEqual(rejected, 0)
        self.assertEqual(metadata["feature_names"], FEATURE_NAMES)
        self.assertEqual(len(FEATURE_NAMES), 10)
        self.assertEqual(metadata["cluster_count"], 3)
        self.assertTrue(all({"cluster", "cluster_label", "pca_x", "pca_y", "pca_z"} <= row.keys() for row in analyzed))
        # Verify all 10 features exist in each row
        self.assertTrue(all(name in analyzed[0] for name in FEATURE_NAMES))

    def test_health_check(self) -> None:
        client = TestClient(app)
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["data_source"], "yahoo_finance")


if __name__ == "__main__":
    unittest.main()
