from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scr" / "preprocesamiento" / "analizar_queries_twitter.py"
MODULE_NAME = "radar_test_analizar_queries_twitter"
SPEC = importlib.util.spec_from_file_location(MODULE_NAME, SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"No se pudo cargar {SCRIPT_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[MODULE_NAME] = MODULE
SPEC.loader.exec_module(MODULE)


class AnalizarQueriesTwitterTests(unittest.TestCase):
    def test_query_normalization_removes_dates_but_preserves_provenance(self):
        self.assertEqual(
            MODULE.normalize_query(
                '"to:MonicaVTampico" since:2026-04-06 until:2026-04-13'
            ),
            "to:MonicaVTampico",
        )
        self.assertEqual(
            MODULE.normalize_query("reply_to:https://x.com/a/status/1"),
            "<reply_to>",
        )

    def test_analysis_does_not_invent_a_common_query(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            columns = [
                "tweet_id", "author", "published_at", "url", "text",
                "replies", "retweets", "likes", "bookmarks", "views",
                "query_raw", "is_reply",
            ]
            for index, (query, text) in enumerate(
                (("@TampicoGob", "Tampico uno"), ("monica villarreal", "Tampico dos")),
                start=1,
            ):
                week = root / f"2026-04-{index:02d}_semana_prueba"
                week.mkdir()
                path = week / f"{week.name}_twitter.csv"
                with path.open("w", encoding="utf-8-sig", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=columns)
                    writer.writeheader()
                    writer.writerow(
                        {
                            "tweet_id": str(index), "author": "@a",
                            "published_at": "2026-04-01T00:00:00+00:00",
                            "url": "", "text": text, "replies": "0",
                            "retweets": "0", "likes": "0", "bookmarks": "0",
                            "views": "0", "query_raw": query, "is_reply": "false",
                        }
                    )
            analysis = MODULE.analyze_queries(root)
            self.assertEqual(analysis["exact_query_intersection_all_weeks"], [])
            candidate = analysis["uniform_content_candidates"]["text_contains_tampico"]
            self.assertEqual(candidate["weeks_with_rows"], 2)
            self.assertEqual(candidate["rows"], 2)
            account_scope = analysis["uniform_content_candidates"]["account_scope"]
            self.assertEqual(account_scope["weeks_with_rows"], 1)
            self.assertEqual(account_scope["rows"], 1)
            self.assertEqual(
                analysis["conclusion"]["best_observable_uniform_rule"],
                "account_scope",
            )


if __name__ == "__main__":
    unittest.main()
