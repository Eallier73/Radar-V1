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

SCRIPT = REPO_ROOT / "scr" / "preprocesamiento" / "promover_csv_a_texto.py"
SPEC = importlib.util.spec_from_file_location("radar_test_promover_texto", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"No se pudo cargar {SCRIPT}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class PromoverCsvATextoTests(unittest.TestCase):
    def _write_csv(
        self,
        path: Path,
        columns: tuple[str, ...],
        rows: list[dict[str, str]],
    ) -> None:
        path.parent.mkdir(parents=True)
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)

    def test_social_ascii_preserves_order_duplicates_and_record_boundaries(self) -> None:
        week = "2026-04-06_semana_06abril_12abril_26"
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / week / f"{week}_twitter.csv"
            rows = []
            for text in ("  ¡Información 2026 para NIÑAS!\nSí.  ", "Mismo registro", "Mismo registro"):
                row = {column: "" for column in MODULE.TWITTER_OUTPUT_COLUMNS}
                row["text"] = text
                rows.append(row)
            self._write_csv(path, MODULE.TWITTER_OUTPUT_COLUMNS, rows)
            original_csv = path.read_bytes()

            result = MODULE.promote_csv("twitter", path)

            self.assertEqual(result.status, "written")
            self.assertEqual(result.records_written, 3)
            self.assertEqual(
                path.with_suffix(".txt").read_text(encoding="utf-8"),
                "informacion para ninas si\nmismo registro\nmismo registro\n",
            )
            self.assertEqual(path.read_bytes(), original_csv)
            self.assertEqual(MODULE.promote_csv("twitter", path).status, "unchanged")

    def test_normalizer_removes_urls_html_digits_and_symbols(self) -> None:
        cases = (
            ("¡ÁÉÍÓÚ Ü Ñ! １２３ 456 😀", "aeiou u n"),
            ("niñas\nniños\tmañana", "ninas ninos manana"),
            ("nin\u0303as cafe\u0301", "ninas cafe"),
            ("Visita HTTPS://ejemplo.com/niñas?q=1&amp;x=2 hoy", "visita hoy"),
            ("www.ejemplo.com/nota ejemplo.com/ruta t.co/abc fin", "fin"),
            ('<a href="https://ejemplo.com">¡Información!</a><br>más', "informacion mas"),
            ("@TampicoGob #Niñez_2026 hola🚀mundo", "tampicogob ninez hola mundo"),
            ("123 !!! https://ejemplo.com/nota 😀", ""),
        )
        for original, expected in cases:
            with self.subTest(original=original):
                actual = MODULE.normalize_social_text(original)
                self.assertEqual(actual, expected)
                self.assertRegex(actual, r"^[a-z ]*$")

    def test_all_social_sources_share_ascii_contract_and_skip_empty_records(self) -> None:
        for source, column in MODULE.TEXT_COLUMNS.items():
            with self.subTest(source=source):
                content, written, empty = MODULE.build_text_content(source, [
                    {column: "¡Niñas 2026! https://ejemplo.com/nota"},
                    {column: "123 !!! www.ejemplo.com"},
                    {column: ""},
                ])
                self.assertEqual(content, "ninas\n")
                self.assertEqual((written, empty), (1, 2))

    def test_medios_reproduces_historical_ascii_contract(self) -> None:
        week = "2026-04-06_semana_06abril_12abril_26"
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / week / f"{week}_medios.csv"
            row = {column: "" for column in MODULE.MEDIOS_OUTPUT_COLUMNS}
            row.update(
                {
                    "titulo": "Última información de Tampico",
                    "texto": "Niñas y niños: 2026. Más en https://example.com/nota",
                }
            )
            self._write_csv(path, MODULE.MEDIOS_OUTPUT_COLUMNS, [row])

            result = MODULE.promote_csv("medios", path)

            self.assertEqual(result.status, "written")
            self.assertEqual(
                path.with_suffix(".txt").read_text(encoding="utf-8"),
                "ultima informacion de tampico ninas y ninos mas en\n",
            )

    def test_existing_different_txt_requires_explicit_overwrite(self) -> None:
        week = "2026-04-06_semana_06abril_12abril_26"
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / week / f"{week}_youtube.csv"
            row = {column: "" for column in MODULE.YOUTUBE_OUTPUT_COLUMNS}
            row["comment_text"] = "Texto nuevo"
            self._write_csv(path, MODULE.YOUTUBE_OUTPUT_COLUMNS, [row])
            txt_path = path.with_suffix(".txt")
            txt_path.write_text("texto histórico\n", encoding="utf-8")

            blocked = MODULE.promote_csv("youtube", path)
            replaced = MODULE.promote_csv("youtube", path, overwrite=True)

            self.assertEqual(blocked.status, "error")
            self.assertIn("--overwrite", blocked.error)
            self.assertEqual(replaced.status, "written")
            self.assertEqual(txt_path.read_text(encoding="utf-8"), "texto nuevo\n")

    def test_rejects_week_folder_with_incorrect_end_label(self) -> None:
        week = "2026-04-06_semana_06abril_13abril_26"
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / week / f"{week}_twitter.csv"
            self._write_csv(path, MODULE.TWITTER_OUTPUT_COLUMNS, [])

            result = MODULE.promote_csv("twitter", path)

            self.assertEqual(result.status, "error")
            self.assertIn("fuera de contrato", result.error)

    def test_all_weeks_ignores_historical_medios_txt_without_csv(self) -> None:
        week = "2024-09-30_semana_30septiembre_06octubre_24"
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "medios_semanal_procesado"
            txt_path = source / week / f"{week}_medios.txt"
            txt_path.parent.mkdir(parents=True)
            txt_path.write_text("material historico\n", encoding="utf-8")

            selected, missing = MODULE.discover_csv_files(
                Path(temp_dir),
                ("medios",),
                source_dir=None,
                since=None,
                before=None,
                weeks=(),
                all_weeks=True,
            )

            self.assertEqual(selected, [])
            self.assertEqual(missing, [])
            self.assertEqual(txt_path.read_text(encoding="utf-8"), "material historico\n")


if __name__ == "__main__":
    unittest.main()
