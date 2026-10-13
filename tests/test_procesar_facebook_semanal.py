from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SHARED_DIR = REPO_ROOT / "scr" / "compartido"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from facebook_data_contract import FACEBOOK_PROCESSED_COLUMNS
from output_naming import build_source_filename, build_week_folder_name


SCRIPT_PATH = REPO_ROOT / "scr" / "preprocesamiento" / "procesar_facebook_semanal.py"
MODULE_NAME = "radar_test_procesar_facebook"
SPEC = importlib.util.spec_from_file_location(MODULE_NAME, SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"No se pudo cargar {SCRIPT_PATH}")
PROCESSOR = importlib.util.module_from_spec(SPEC)
sys.modules[MODULE_NAME] = PROCESSOR
SPEC.loader.exec_module(PROCESSOR)


class ProcesarFacebookSemanalTests(unittest.TestCase):
    def test_canonical_filters_accounts_dates_empty_and_duplicates(self) -> None:
        week = "2026-03-09_semana_09marzo_15marzo_26"
        rows = [
            {
                "tipo": "POST",
                "url": "https://www.facebook.com/monicavtampico/posts/1",
                "post_url_padre": "",
                "fecha": "2026-03-10T12:00:00Z",
                "texto": "Mensaje institucional",
                "num_comentarios": "2",
            },
            {
                "tipo": "COMENTARIO",
                "url": "https://www.facebook.com/comment/1",
                "post_url_padre": "https://www.facebook.com/monicavtampico/posts/1",
                "fecha": "Desconocida",
                "texto": "Comentario conservado",
                "num_comentarios": "",
            },
            {
                "tipo": "POST",
                "url": "https://www.facebook.com/servpublicostampico/posts/2",
                "post_url_padre": "",
                "fecha": "2026-03-10T12:00:00Z",
                "texto": "Cuenta fuera del contrato",
                "num_comentarios": "0",
            },
            {
                "tipo": "POST",
                "url": "https://www.facebook.com/TampicoGob/posts/3",
                "post_url_padre": "",
                "fecha": "2026-03-20T12:00:00Z",
                "texto": "Fuera de semana",
                "num_comentarios": "0",
            },
            {
                "tipo": "COMENTARIO",
                "url": "https://www.facebook.com/comment/4",
                "post_url_padre": "https://www.facebook.com/monicavtampico/posts/1",
                "fecha": "2026-03-11T12:00:00Z",
                "texto": "",
                "num_comentarios": "",
            },
            {
                "tipo": "POST",
                "url": "https://www.facebook.com/reel/5",
                "post_url_padre": "",
                "fecha": "2026-03-11T12:00:00Z",
                "texto": "Reel sin cuenta recuperable",
                "num_comentarios": "0",
            },
        ]
        rows.append(dict(rows[0]))

        cleaned, counters = PROCESSOR.project_and_clean_rows(
            rows,
            schema="canonical",
            week_name=week,
        )
        self.assertEqual(len(cleaned), 3)
        self.assertEqual(cleaned[0]["cuenta"], "monicavtampico")
        self.assertEqual(cleaned[1]["fecha"], "")
        self.assertEqual(cleaned[2]["fecha"], "")
        self.assertEqual(counters["non_base_account"], 1)
        self.assertEqual(counters["date_outside_week"], 1)
        self.assertEqual(counters["empty_text"], 1)
        self.assertEqual(counters["duplicates"], 1)
        self.assertEqual(counters["unknown_account"], 1)

    def test_legacy_ids_are_projected_to_base_accounts(self) -> None:
        rows = [
            {
                "query_type": "Facebook:/<page-id>/posts",
                "message": "Publicación de Mónica",
                "created_time": "1/4/25 16:27",
                "object_id": "964877296876825_100",
                "path": "964877296876825_100",
                "object_key": "data.*",
                "comment_count": "4",
            },
            {
                "query_type": "Facebook:/<page-id>/posts",
                "message": "Publicación de Tampico",
                "created_time": "2025-01-05T09:00:00+0000",
                "object_id": "474462132406835_200",
                "path": "TampicoGob/474462132406835_200",
                "object_key": "data.*",
                "comment_count": "1",
            },
            {
                "query_type": "Facebook:/<post-id>/comments",
                "message": "Respuesta ciudadana",
                "created_time": "2025-01-05T10:00:00+0000",
                "object_id": "474462132406835_200",
                "path": "TampicoGob/474462132406835_200",
                "object_key": "data.*",
                "comment_count": "",
            },
        ]
        cleaned, counters = PROCESSOR.project_and_clean_rows(
            rows,
            schema="legacy",
            week_name="2024-12-30_semana_30diciembre_05enero_25",
        )
        self.assertEqual(
            [row["cuenta"] for row in cleaned],
            ["monicavtampico", "tampicogob", "tampicogob"],
        )
        self.assertEqual(cleaned[0]["fecha"], "2025-01-04T16:27:00")
        self.assertEqual(cleaned[2]["tipo"], "COMENTARIO")
        self.assertEqual(counters["kept"], 3)

    def test_empty_post_keeps_distinct_historical_comments_linked(self) -> None:
        post_url = "https://facebook.com/TampicoGob/posts/1"
        rows = [
            {
                "tipo": "POST",
                "url": post_url,
                "post_url_padre": "",
                "fecha": "",
                "texto": "",
                "num_comentarios": "2",
            },
            {
                "tipo": "COMENTARIO",
                "url": f"{post_url}?comment_id=100",
                "post_url_padre": post_url,
                "fecha": "2026-03-10T10:00:00Z",
                "texto": "Primer comentario",
                "num_comentarios": "",
            },
            {
                "tipo": "COMENTARIO",
                "url": f"{post_url}?comment_id=200",
                "post_url_padre": post_url,
                "fecha": "2026-03-10T10:01:00Z",
                "texto": "Segundo comentario",
                "num_comentarios": "",
            },
        ]
        cleaned, counters = PROCESSOR.project_and_clean_rows(
            rows,
            schema="canonical",
            week_name="2026-03-09_semana_09marzo_15marzo_26",
        )
        self.assertEqual(len(cleaned), 3)
        self.assertEqual(counters["posts_without_text"], 1)
        self.assertEqual(counters["duplicates"], 0)
        self.assertEqual(
            [row["url"] for row in cleaned[1:]],
            [
                f"https://facebook.com/TampicoGob/posts/1?comment_id=100",
                f"https://facebook.com/TampicoGob/posts/1?comment_id=200",
            ],
        )

    def test_process_file_writes_only_canonical_csv(self) -> None:
        since, before = "2026-03-09", "2026-03-15"
        week = build_week_folder_name(since, before)
        base = build_source_filename(week, "facebook")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "extraido" / week / f"{base}.csv"
            input_path.parent.mkdir(parents=True)
            with input_path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=("tipo", "url", "post_url_padre", "fecha", "texto", "num_comentarios"),
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "tipo": "POST",
                        "url": "https://www.facebook.com/TampicoGob/posts/1",
                        "post_url_padre": "",
                        "fecha": "2026-03-10T10:00:00Z",
                        "texto": "Información número 2026 para Tampico",
                        "num_comentarios": "1",
                    }
                )

            result = PROCESSOR.process_file(input_path, root / "procesado")
            self.assertEqual(result.status, "success")
            output_csv = Path(result.output_csv)
            with output_csv.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                self.assertEqual(tuple(reader.fieldnames or ()), FACEBOOK_PROCESSED_COLUMNS)
                self.assertEqual(len(list(reader)), 1)
            self.assertEqual(
                sorted(path.name for path in output_csv.parent.iterdir()),
                [output_csv.name],
            )


if __name__ == "__main__":
    unittest.main()
