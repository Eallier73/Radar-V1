from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scr" / "preprocesamiento" / "limpiar_twitter_semanal.py"
MODULE_NAME = "radar_test_limpiar_twitter_semanal"
SPEC = importlib.util.spec_from_file_location(MODULE_NAME, SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"No se pudo cargar {SCRIPT_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[MODULE_NAME] = MODULE
SPEC.loader.exec_module(MODULE)


class LimpiarTwitterSemanalTests(unittest.TestCase):
    def test_week_bounds_are_strict_monday_to_monday(self):
        start, before = MODULE.week_bounds_from_name(
            "2026-04-06_semana_06abril_12abril_26"
        )
        self.assertEqual(start, datetime(2026, 4, 6, tzinfo=timezone.utc))
        self.assertEqual(before, datetime(2026, 4, 13, tzinfo=timezone.utc))

    def test_both_historical_schemas_project_to_same_contract(self):
        current = {
            "author": "@cuenta",
            "datetime": "2026-04-10T12:00:00.000Z",
            "datetime_parsed_utc": "2026-04-10T12:00:00+00:00",
            "url": "https://x.com/cuenta/status/123",
            "text": "texto",
            "replies": "1",
            "retweets": "2",
            "likes": "3",
            "bookmarks": "",
            "views": "4",
            "query_used": "@TampicoGob since:2026-04-06 until:2026-04-13",
            "is_reply": "False",
        }
        provider = {
            "Author_Handle": "cuenta",
            "UTC_Time": "4/10/26 12:00",
            "Tweet_Content": "texto",
            "Post_ID": "123",
            "Tweet_URL": "https://x.com/cuenta/status/123",
            "Reply_Count": "1",
            "Repost_Count": "2",
            "Like_Count": "3",
            "Bookmark_Count": "",
            "View_Count": "4",
            "Query_Str": "(@@TampicoGob OR @@MonicaVTampico) min_replies:0 min_faves:0 min_retweets:0",
            "Replying_to": "False",
        }
        row_a = MODULE.project_twitter_row(current, schema="radar_15_columns")
        row_b = MODULE.project_twitter_row(provider, schema="provider_24_columns")
        self.assertEqual(list(row_a), MODULE.OUTPUT_COLUMNS)
        self.assertEqual(list(row_b), MODULE.OUTPUT_COLUMNS)
        self.assertEqual(row_a["tweet_id"], row_b["tweet_id"])
        self.assertEqual(row_a["author"], row_b["author"])
        self.assertEqual(row_a["published_at"], row_b["published_at"])
        self.assertEqual(
            MODULE.detect_twitter_schema(MODULE.OUTPUT_COLUMNS),
            "canonical_12_columns",
        )

    def test_clean_week_filters_dates_text_and_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            week = root / "2026-04-06_semana_06abril_12abril_26"
            week.mkdir()
            source = week / f"{week.name}_twitter.csv"
            output = root / "salida" / week.name / source.name
            fields = [
                "fecha_semana", "nombre_semana", "author", "datetime",
                "datetime_parsed_utc", "url", "text", "replies", "retweets",
                "likes", "bookmarks", "views", "query_used", "is_reply",
                "in_reply_to_url",
            ]
            with source.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                base = {
                    "author": "@cuenta", "replies": "0", "retweets": "0",
                    "likes": "0", "bookmarks": "", "views": "0",
                    "is_reply": "False",
                }
                writer.writerow({**base, "datetime": "2026-04-06T00:00:00Z", "url": "https://x.com/cuenta/status/1", "text": "conservar", "query_used": "@TampicoGob"})
                writer.writerow({**base, "datetime": "2026-04-06T00:00:00Z", "url": "https://x.com/cuenta/status/1", "text": "conservar", "query_used": "@MonicaVTampico"})
                writer.writerow({**base, "datetime": "2026-04-13T00:00:00Z", "url": "https://x.com/cuenta/status/2", "text": "fuera", "query_used": "@TampicoGob"})
                writer.writerow({**base, "datetime": "2026-04-10T12:00:00Z", "url": "https://x.com/cuenta/status/3", "text": "", "query_used": "@TampicoGob"})
                writer.writerow({**base, "datetime": "2026-04-10T12:00:00Z", "url": "https://x.com/cuenta/status/4", "text": "búsqueda general", "query_used": "tampico"})

            result = MODULE.clean_week_file(
                source, output, dry_run=False, overwrite=False
            )
            self.assertEqual(result.status, "success")
            self.assertEqual(result.rows_removed_after_week, 1)
            self.assertEqual(result.rows_removed_empty_text, 1)
            self.assertEqual(result.rows_removed_outside_account_scope, 1)
            self.assertEqual(result.rows_removed_duplicates, 1)
            self.assertEqual(result.rows_kept, 1)
            with output.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                self.assertEqual(reader.fieldnames, MODULE.OUTPUT_COLUMNS)
                rows = list(reader)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["query_raw"], "@TampicoGob")

    def test_linked_reply_is_kept_with_account_parent(self):
        rows = [
            {
                "tweet_id": "1",
                "url": "https://x.com/cuenta/status/1",
                "text": "Publicación",
                "query_raw": "from:TampicoGob",
            },
            {
                "tweet_id": "2",
                "url": "https://x.com/otra/status/2",
                "text": "Respuesta",
                "query_raw": "reply_to:https://x.com/cuenta/status/1",
            },
            {
                "tweet_id": "3",
                "url": "https://x.com/otra/status/3",
                "text": "Respuesta sin padre aceptado",
                "query_raw": "reply_to:https://x.com/cuenta/status/99",
            },
        ]
        kept, removed = MODULE.filter_twitter_rows_to_account_scope(rows)
        self.assertEqual([row["tweet_id"] for row in kept], ["1", "2"])
        self.assertEqual(removed, 1)

    def test_missing_id_fallback_ignores_query(self):
        rows = [
            {
                "tweet_id": "", "author": "@a",
                "published_at": "2026-04-10T12:00:00+00:00",
                "text": "Mismo texto", "query_raw": "q1",
            },
            {
                "tweet_id": "", "author": "@a",
                "published_at": "2026-04-10T12:00:00+00:00",
                "text": "  mismo   texto ", "query_raw": "q2",
            },
        ]
        unique, removed = MODULE.deduplicate_twitter_rows(rows)
        self.assertEqual(removed, 1)
        self.assertEqual(len(unique), 1)

    def test_new_incompatible_file_is_rejected_even_with_historical_week_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            week = root / "2025-11-10_semana_10noviembre_16noviembre_25"
            week.mkdir()
            source = week / f"{week.name}_twitter.csv"
            source.write_text("primera línea\nsegunda línea\n", encoding="utf-8")
            output = root / "salida" / week.name / source.name
            result = MODULE.clean_week_file(
                source, output, dry_run=False, overwrite=False
            )
            self.assertEqual(result.status, "error_incompatible_schema")
            self.assertEqual(result.incompatible_nonempty_lines, 2)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
