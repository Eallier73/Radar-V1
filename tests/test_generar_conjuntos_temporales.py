from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scr/operaciones/generar_conjuntos_temporales.py"
SPEC = importlib.util.spec_from_file_location("radar_temporal_sets", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TemporalSetTests(unittest.TestCase):
    sizes = {"entrenamiento": 3, "prueba": 2, "verificacion": 1}

    def corpus(self, root):
        for index in range(6):
            start = date(2025, 1, 6) + timedelta(weeks=index)
            week = f"{start}_semana_fixture"
            for number, source in enumerate(MODULE.SOURCES, 1):
                path = root / f"{source}_semanal_procesado" / week / f"{week}_{source}.txt"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(("palabra " * (number + index)).strip() + "\n", encoding="utf-8")

    def test_complete_chronological_groups_preserve_exact_text_and_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "processed"
            self.corpus(root)
            before = {p: p.read_bytes() for p in root.rglob("*.txt")}
            output = Path(directory) / "sets"
            report = MODULE.generate(root, output, self.sizes)
            seen = set()
            last_end = ""
            for name, size in self.sizes.items():
                meta = report["subsets"][name]
                self.assertGreater(meta["period_start"], last_end)
                last_end = meta["period_end"]
                records = [json.loads(line) for line in (output / meta["corpus"]).read_text().splitlines()]
                self.assertEqual(len(records), 4 * size)
                weeks = {r["week"] for r in records}
                self.assertEqual(len(weeks), size)
                self.assertFalse(seen & weeks)
                seen |= weeks
                for record in records:
                    self.assertEqual(record["text"].encode(), before[root / record["source_path"]])
                    self.assertEqual(record["conjunto"], name)
            self.assertEqual(len(seen), 6)
            self.assertEqual(before, {p: p.read_bytes() for p in before})
            self.assertEqual(len(report["input_sha256"]), 24)
            for relative, expected in report["output_sha256"].items():
                self.assertEqual(MODULE.digest(output / relative), expected)
            with self.assertRaises(FileExistsError):
                MODULE.generate(root, output, self.sizes)

    def test_training_weights_do_not_depend_on_test_or_verification_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "processed"
            self.corpus(root)
            first = MODULE.generate(root, Path(directory) / "first", self.sizes)
            for path in root.rglob("*.txt"):
                if path.parent.name[:10] >= "2025-01-27":
                    path.write_text("material cambiado " * 1000, encoding="utf-8")
            second = MODULE.generate(root, Path(directory) / "second", self.sizes)
            self.assertEqual(first["training_weighting"], second["training_weighting"])
            weights = first["training_weighting"]
            self.assertEqual(weights["calibration_weeks"], 3)
            self.assertEqual(weights["words"]["youtube"], 6)
            self.assertAlmostEqual(sum(weights["weights"].values()), 1)
            self.assertNotEqual(first["output_sha256"], second["output_sha256"])

    def test_development_loader_never_opens_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "processed"
            self.corpus(root)
            output = Path(directory) / "sets"
            MODULE.generate(root, output, self.sizes)
            original_open = Path.open

            def guarded_open(path, *args, **kwargs):
                if "verificacion_reservada" in path.parts:
                    self.fail("Desarrollo intentó abrir verificación")
                return original_open(path, *args, **kwargs)

            with patch.object(Path, "open", guarded_open):
                self.assertEqual(len(list(MODULE.cargar_corpus_desarrollo(output / "desarrollo", "entrenamiento"))), 12)
                self.assertEqual(len(list(MODULE.cargar_corpus_desarrollo(output / "desarrollo", "prueba"))), 8)
                for forbidden in ("verificacion", "verificacion_reservada", "../verificacion_reservada"):
                    with self.assertRaises(ValueError):
                        list(MODULE.cargar_corpus_desarrollo(output / "desarrollo", forbidden))

    def test_invalid_coverage_or_sizes_cannot_create_partial_sets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "processed"
            self.corpus(root)
            output = Path(directory) / "sets"
            with self.assertRaises(ValueError):
                MODULE.generate(root, output)
            self.assertFalse(output.exists())
            next(root.rglob("*.txt")).unlink()
            with self.assertRaises(ValueError):
                MODULE.generate(root, output, self.sizes)
            self.assertFalse(output.exists())

    def test_empty_week_aborts_and_cleans_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "processed"
            self.corpus(root)
            next(root.rglob("*.txt")).write_text(" \n")
            output = Path(directory) / "sets"
            with self.assertRaises(ValueError):
                MODULE.generate(root, output, self.sizes)
            self.assertFalse(output.exists())
            self.assertEqual(list(Path(directory).glob(".sets-*")), [])


if __name__ == "__main__":
    unittest.main()
