import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.analysis import FEATURE_NAMES, clean_ohlcv, enrich_features, run_cluster_analysis
from app.config import get_krx_key
from app.main import parse_date
from app.schemas import DateResult


class GetKrxKeyTests(unittest.TestCase):
    def test_reads_trimmed_primary_environment_value(self) -> None:
        with patch.dict(os.environ, {"KRX_KEY": "  secret  "}):
            self.assertEqual(get_krx_key(), "secret")

    def test_supports_krx_auth_key_name(self) -> None:
        with patch.dict(os.environ, {"KRX_KEY": "", "KRX_AUTH_KEY": "auth-secret"}):
            self.assertEqual(get_krx_key(), "auth-secret")

    def test_supports_legacy_hyphenated_environment_name(self) -> None:
        with patch.dict(os.environ, {"KRX_KEY": "", "KRX_AUTH_KEY": "", "KRX-KEY": "legacy-secret"}):
            self.assertEqual(get_krx_key(), "legacy-secret")

    def test_falls_back_to_key_file(self) -> None:
        with TemporaryDirectory() as directory:
            key_file = Path(directory) / ".key"
            key_file.write_text("KRX-KEY=local-secret\n", encoding="utf-8")
            with patch.dict(os.environ, {"KRX_KEY": "", "KRX_AUTH_KEY": ""}):
                with patch("app.config.KEY_FILE", key_file):
                    self.assertEqual(get_krx_key(), "local-secret")


def sample(day: str, code: str, open_: str, high: str, low: str, close: str, volume: str) -> dict[str, str]:
    return {
        "BAS_DD": day, "ISU_CD": code, "ISU_NM": f"종목-{code}", "MKT_NM": "KOSPI",
        "TDD_OPNPRC": open_, "TDD_HGPRC": high, "TDD_LWPRC": low, "TDD_CLSPRC": close,
        "ACC_TRDVOL": volume, "ACC_TRDVAL": str(int(close.replace(",", "")) * int(volume.replace(",", ""))),
        "LIST_SHRS": "10000000",
    }


class OhlcvPipelineTests(unittest.TestCase):
    def test_parse_date(self) -> None:
        self.assertEqual(parse_date("2026-10-31").isoformat(), "2026-10-31")

    def test_cleaning_types_numbers_and_rejects_invalid_candles(self) -> None:
        valid = sample("20260102", "005930", "10,000", "10,500", "9,900", "10,300", "1,000")
        invalid = sample("20260102", "000660", "10,000", "9,500", "9,000", "9,800", "100")
        rows, rejected = clean_ohlcv([DateResult(bas_dd="20260102", records=[valid, invalid])])
        self.assertEqual((len(rows), rejected), (1, 1))
        self.assertEqual(rows[0]["TDD_CLSPRC"], 10300.0)

    def test_enrichment_and_clustering_add_projection(self) -> None:
        records = []
        for index in range(12):
            base = 10000 + index * 70
            close = base + (-1 if index % 3 == 0 else 1) * (80 + index * 5)
            records.append(sample(
                f"202601{index + 1:02d}", "005930", str(base), str(max(base, close) + 120 + index),
                str(min(base, close) - 90), str(close), str(1000 + index * index * 30),
            ))
        rows, rejected = clean_ohlcv([DateResult(bas_dd="20260101", records=records)])
        analyzed, metadata = run_cluster_analysis(enrich_features(rows), 3)
        self.assertEqual(rejected, 0)
        self.assertEqual(metadata["feature_names"], FEATURE_NAMES)
        self.assertEqual(metadata["cluster_count"], 3)
        self.assertTrue(all({"cluster", "cluster_label", "pca_x", "pca_y", "pca_z"} <= row.keys() for row in analyzed))


if __name__ == "__main__":
    unittest.main()
