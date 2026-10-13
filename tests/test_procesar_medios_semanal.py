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

from medios_data_contract import MEDIOS_OUTPUT_COLUMNS
from output_naming import build_source_filename, build_week_folder_name


SCRIPT_PATH = REPO_ROOT / "scr" / "preprocesamiento" / "procesar_medios_semanal.py"
SPEC = importlib.util.spec_from_file_location("radar_test_procesar_medios", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"No se pudo cargar {SCRIPT_PATH}")
PROCESSOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROCESSOR)


def media_row(**overrides: str) -> dict[str, str]:
    row = {column: "" for column in MEDIOS_OUTPUT_COLUMNS}
    row.update(
        {
            "titulo": "Noticia de Tampico",
            "fecha": "2026-04-06",
            "iso_date": "2026-04-06T12:00:00+00:00",
            "fuente": "Medio",
            "url": "https://example.com/uno",
            "texto": "Información número 2026 para la ciudad.",
            "origen": "tampico site:example.com",
        }
    )
    row.update(overrides)
    return row


class ProcesarMediosSemanalTests(unittest.TestCase):
    def _write_input(
        self,
        input_dir: Path,
        since: str,
        before: str,
        rows: list[dict[str, str]],
    ) -> None:
        week_name = build_week_folder_name(since, before)
        base_name = build_source_filename(week_name, "medios")
        path = input_dir / week_name / f"{base_name}.csv"
        path.parent.mkdir(parents=True)
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=MEDIOS_OUTPUT_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

    def test_week_writes_only_canonical_csv(self) -> None:
        since, before = "2026-04-06", "2026-04-12"
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_dir = root / "extraido"
            output_dir = root / "procesado"
            self._write_input(
                input_dir,
                since,
                before,
                [
                    media_row(),
                    media_row(),
                    media_row(
                        titulo="Última noticia",
                        iso_date="2026-04-12T23:59:59Z",
                        url="https://example.com/dos",
                        texto="Más información en www.example.com y 100 datos.",
                    ),
                    media_row(
                        iso_date="2026-04-13T00:00:00Z",
                        url="https://example.com/fuera",
                    ),
                    media_row(
                        iso_date="fecha-invalida",
                        url="https://example.com/invalida",
                    ),
                ],
            )

            output_csv, counters = PROCESSOR.process_week(
                since,
                before,
                input_dir=input_dir,
                output_dir=output_dir,
            )

            self.assertEqual(
                sorted(path.name for path in output_csv.parent.iterdir()),
                [output_csv.name],
            )
            with output_csv.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                rows = list(reader)
                self.assertEqual(tuple(reader.fieldnames or ()), MEDIOS_OUTPUT_COLUMNS)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["url"], "https://example.com/dos")
            self.assertEqual(counters["duplicates"], 1)
            self.assertEqual(counters["outside_range"], 1)
            self.assertEqual(counters["invalid_date"], 1)

    def test_empty_week_keeps_headers(self) -> None:
        since, before = "2026-04-06", "2026-04-12"
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_dir = root / "extraido"
            output_dir = root / "procesado"
            self._write_input(input_dir, since, before, [])
            output_csv, _ = PROCESSOR.process_week(
                since,
                before,
                input_dir=input_dir,
                output_dir=output_dir,
            )
            with output_csv.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                self.assertEqual(tuple(reader.fieldnames or ()), MEDIOS_OUTPUT_COLUMNS)
                self.assertEqual(list(reader), [])
            self.assertEqual(list(output_csv.parent.iterdir()), [output_csv])


if __name__ == "__main__":
    unittest.main()
