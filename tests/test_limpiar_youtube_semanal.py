from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scr" / "preprocesamiento" / "limpiar_youtube_semanal.py"
MODULE_NAME = "radar_test_limpiar_youtube_semanal"
SPEC = importlib.util.spec_from_file_location(MODULE_NAME, SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"No se pudo cargar {SCRIPT_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[MODULE_NAME] = MODULE
SPEC.loader.exec_module(MODULE)


class LimpiarYoutubeSemanalTests(unittest.TestCase):
    def test_week_bounds_are_monday_to_next_monday(self):
        start, before = MODULE.week_bounds_from_name(
            "2026-04-06_semana_06abril_12abril_26"
        )
        self.assertEqual(start, datetime(2026, 4, 6, tzinfo=timezone.utc))
        self.assertEqual(before, datetime(2026, 4, 13, tzinfo=timezone.utc))

    def test_filter_is_strict_and_removes_invalid_dates(self):
        start = datetime(2026, 4, 6, tzinfo=timezone.utc)
        before = datetime(2026, 4, 13, tzinfo=timezone.utc)
        rows = [
            {"comment_text": "lunes", "published_at": "2026-04-06T00:00:00Z", "query": "q"},
            {"comment_text": "domingo", "published_at": "2026-04-12T23:59:59Z", "query": "q"},
            {"comment_text": "antes", "published_at": "2026-04-05T23:59:59Z", "query": "q"},
            {"comment_text": "lunes siguiente", "published_at": "2026-04-13T00:00:00Z", "query": "q"},
            {"comment_text": "sin fecha", "published_at": "no-es-fecha", "query": "q"},
        ]
        kept, counters = MODULE.filter_rows_to_week(
            rows,
            week_start=start,
            week_before=before,
        )
        self.assertEqual([row["comment_text"] for row in kept], ["lunes", "domingo"])
        self.assertEqual(counters, {"before": 1, "after": 1, "invalid": 1})

    def test_deduplication_ignores_query_and_keeps_first_row(self):
        rows = [
            {
                "comment_text": "El mismo comentario",
                "published_at": "2026-04-10T12:00:00Z",
                "query": "Gobierno de Tampico",
            },
            {
                "comment_text": "El mismo comentario",
                "published_at": "2026-04-10T12:00:00+00:00",
                "query": "Presidenta municipal de Tampico",
            },
            {
                "comment_text": "Otro comentario",
                "published_at": "2026-04-10T12:00:00Z",
                "query": "Gobierno de Tampico",
            },
        ]
        unique, removed = MODULE.deduplicate_rows(rows)
        self.assertEqual(removed, 1)
        self.assertEqual(len(unique), 2)
        self.assertEqual(unique[0]["query"], "Gobierno de Tampico")

    def test_clean_week_preserves_three_column_contract(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            week = root / "2026-04-06_semana_06abril_12abril_26"
            week.mkdir()
            source = week / f"{week.name}_youtube.csv"
            output = root / "salida" / week.name / source.name
            with source.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["comment_text", "published_at", "query"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "comment_text": "conservar",
                        "published_at": "2026-04-10T12:00:00Z",
                        "query": "Gobierno de Tampico",
                    }
                )
                writer.writerow(
                    {
                        "comment_text": "eliminar",
                        "published_at": "2026-04-13T01:00:00Z",
                        "query": "Gobierno de Tampico",
                    }
                )

            result = MODULE.clean_week_file(
                source,
                output,
                dry_run=False,
                overwrite=False,
            )
            self.assertEqual(result.status, "success")
            self.assertEqual(result.rows_kept, 1)
            with output.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                self.assertEqual(
                    reader.fieldnames,
                    ["comment_text", "published_at", "query"],
                )
                self.assertEqual([row["comment_text"] for row in reader], ["conservar"])

    def test_full_contract_is_projected_to_three_columns(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            week = root / "2026-04-06_semana_06abril_12abril_26"
            week.mkdir()
            source = week / f"{week.name}_youtube.csv"
            output = root / "salida" / week.name / source.name
            full_columns = [
                "video_id",
                "comment_id",
                "author",
                "comment_text",
                "published_at",
                "like_count",
                "query",
                "video_title",
                "channel_title",
                "video_published_at",
                "fecha_extraccion",
            ]
            with source.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=full_columns)
                writer.writeheader()
                writer.writerow(
                    {
                        "video_id": "video-1",
                        "comment_id": "comment-1",
                        "author": "autor",
                        "comment_text": "texto útil",
                        "published_at": "2026-04-10T12:00:00Z",
                        "like_count": "5",
                        "query": "Gobierno de Tampico",
                        "video_title": "título",
                        "channel_title": "canal",
                        "video_published_at": "2026-04-09T12:00:00Z",
                        "fecha_extraccion": "2026-04-13 10:00:00",
                    }
                )

            result = MODULE.clean_week_file(
                source,
                output,
                dry_run=False,
                overwrite=False,
            )
            self.assertEqual(result.status, "success")
            self.assertEqual(result.contract_columns, full_columns)
            with output.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                self.assertEqual(reader.fieldnames, MODULE.OUTPUT_COLUMNS)
                self.assertEqual(
                    list(reader),
                    [
                        {
                            "comment_text": "texto útil",
                            "published_at": "2026-04-10T12:00:00Z",
                            "query": "Gobierno de Tampico",
                        }
                    ],
                )

    def test_incompatible_text_disguised_as_csv_is_reported(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            week = root / "2026-04-06_semana_06abril_12abril_26"
            week.mkdir()
            source = week / f"{week.name}_youtube.csv"
            source.write_text("esto no es un csv estructurado\n", encoding="utf-8")
            result = MODULE.clean_week_file(
                source,
                root / "salida.csv",
                dry_run=True,
                overwrite=False,
            )
            self.assertEqual(result.status, "error_incompatible_csv")
            self.assertIn("published_at", result.error)


if __name__ == "__main__":
    unittest.main()
