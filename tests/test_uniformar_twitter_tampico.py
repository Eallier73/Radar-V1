from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scr" / "preprocesamiento" / "uniformar_twitter_tampico.py"
MODULE_NAME = "radar_test_uniformar_twitter_tampico"
SPEC = importlib.util.spec_from_file_location(MODULE_NAME, SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"No se pudo cargar {SCRIPT_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[MODULE_NAME] = MODULE
SPEC.loader.exec_module(MODULE)


class UniformarTwitterTampicoTests(unittest.TestCase):
    def test_shared_rule_requires_complete_word(self):
        self.assertTrue(MODULE.text_contains_tampico("Noticias de TAMPICO"))
        self.assertFalse(MODULE.text_contains_tampico("cuenta @TampicoGob"))
        self.assertFalse(MODULE.text_contains_tampico("tampicolandia"))

    def test_filter_preserves_contract_and_query_provenance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            week = root / "2026-04-06_semana_prueba"
            week.mkdir()
            source = week / f"{week.name}_twitter.csv"
            output = root / "salida" / week.name / source.name
            with source.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=MODULE.OUTPUT_COLUMNS)
                writer.writeheader()
                base = {column: "" for column in MODULE.OUTPUT_COLUMNS}
                writer.writerow(
                    {**base, "tweet_id": "1", "text": "Gobierno de Tampico", "query_raw": "@TampicoGob"}
                )
                writer.writerow(
                    {**base, "tweet_id": "2", "text": "Gobierno municipal", "query_raw": "tampico"}
                )
            result = MODULE.filter_week_file(source, output, overwrite=False)
            self.assertEqual(result["rows_kept"], 1)
            with output.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                rows = list(reader)
            self.assertEqual(reader.fieldnames, MODULE.OUTPUT_COLUMNS)
            self.assertEqual(rows[0]["query_raw"], "@TampicoGob")


if __name__ == "__main__":
    unittest.main()
