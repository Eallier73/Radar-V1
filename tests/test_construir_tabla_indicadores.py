from __future__ import annotations

import csv
import importlib.util
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scr/operaciones/construir_tabla_indicadores.py"
SPEC = importlib.util.spec_from_file_location("radar_indicator_table", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
from generar_conjuntos_temporales import cargar_desarrollo, partition_table


def read_table(path):
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


class IndicatorTests(unittest.TestCase):
    def resources(self, folder):
        folder.mkdir()
        for positive, negative in MODULE.POLARITY_FILES.values():
            (folder / positive).write_text("bueno\n")
            (folder / negative).write_text("malo\n")
        (folder / "Diccionario_Temas_V5.csv").write_text("Agua\nagua\nagua potable\n")
        (folder / "Stoplists_Por_Tema_1.csv").write_text("Agua\nuno\n")
        (folder / "stop_list_español.txt").write_text("de\n")
        (folder / "exclusiones_polaridad.json").write_text("[]")
        (folder / "procedencia.json").write_text("{}")

    def corpus(self, folder):
        for index in range(83):
            start = date(2024, 9, 30) + timedelta(weeks=index)
            week = f"{start}_semana_fixture"
            for source in MODULE.SOURCES:
                path = folder / f"{source}_semanal_procesado" / week / f"{week}_{source}.txt"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("bueno malo agua agua potable\nbueno\n")

    def test_indicator_numerators_denominators_and_missing_polarity(self):
        polar = MODULE.Matcher({"Original_pos": {"bueno"}, "Original_neg": {"malo"},
                                "Etiquetado_pos": {"bueno"}, "Etiquetado_neg": {"malo"}})
        thematic = MODULE.Matcher({"Agua": {"agua", "agua potable"}})
        args = (polar, thematic, ["Agua"], set())
        social = MODULE.analyze_text("bueno malo agua agua potable\nbueno\n", "youtube", *args)
        self.assertEqual(social["words"], 6)
        self.assertEqual(social["text_records"], 2)
        self.assertAlmostEqual(social["polarities"]["Original"]["sentiment_pct"], 200 / 3)
        self.assertEqual(social["topics"]["Agua"]["mentions"], 3)
        self.assertEqual(social["topics"]["Agua"]["intensity_per_1000"], 500)
        self.assertEqual(social["topics"]["Agua"]["record_presence_pct"], 50)
        media = MODULE.analyze_text("agua potable\n", "medios", *args)
        self.assertIsNone(media["text_records"])
        self.assertIsNone(media["topics"]["Agua"]["record_presence_pct"])
        self.assertEqual(media["topics"]["Agua"]["segment30_presence_pct"], 100)
        self.assertIsNone(media["polarities"]["Original"]["sentiment_pct"])

    def test_ngrams_do_not_cross_posts_and_overlapping_hits_are_counted(self):
        polar = MODULE.Matcher({})
        topics = MODULE.Matcher({"Agua": {"agua", "agua potable", "potable agua"}})
        values = MODULE.analyze_text("agua potable agua\n", "youtube", polar, topics, ["Agua"], set())
        self.assertEqual(values["topics"]["Agua"]["mentions"], 4)
        values = MODULE.analyze_text("agua\npotable\n", "youtube", polar, topics, ["Agua"], set())
        self.assertEqual(values["topics"]["Agua"]["mentions"], 1)

    def test_ma5_is_causal_with_partial_windows_and_does_not_fill_missing_as_zero(self):
        raw = [{"x": x} for x in (1, 2, None, 4, 5, 100)]
        result = MODULE.trailing_ma5(raw, ["x"])
        self.assertEqual(result[0]["x_MA5"], 1)
        self.assertEqual(result[4]["x_MA5"], 3)
        self.assertEqual(result[5]["x_MA5"], 27.75)
        self.assertEqual(raw[0], {"x": 1})
        self.assertIsNone(MODULE.trailing_ma5([{"x": None}], ["x"])[0]["x_MA5"])

    def test_build_then_partition_and_future_mutations_do_not_affect_development(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            resources, processed = base / "resources", base / "processed"
            self.resources(resources)
            self.corpus(processed)
            first = base / "first_table"
            report = MODULE.build(processed, resources, first)
            table = first / "tabla_indicadores_83_semanas.csv"
            before = table.read_bytes()
            rows = read_table(table)
            self.assertEqual(report["rows"], 83)
            self.assertEqual(len(rows), 83)
            self.assertFalse(report["smoothing"]["center"])
            output = base / "sets"
            divided = partition_table(table, first / "pesos_fuentes_entrenamiento.json", output)
            self.assertEqual([m["rows"] for m in divided["subsets"].values()], [56, 14, 13])
            recombined = []
            for name, meta in divided["subsets"].items():
                recombined.extend(read_table(output / meta["table"]))
            self.assertEqual(rows, recombined)
            self.assertEqual(table.read_bytes(), before)
            original_open = Path.open

            def guarded_open(path, *args, **kwargs):
                if "verificacion_reservada" in path.parts:
                    self.fail("Se abrió verificación desde desarrollo")
                return original_open(path, *args, **kwargs)

            with patch.object(Path, "open", guarded_open):
                self.assertEqual(len(list(cargar_desarrollo(output / "desarrollo", "entrenamiento"))), 56)
                self.assertEqual(len(list(cargar_desarrollo(output / "desarrollo", "prueba"))), 14)
                with self.assertRaises(ValueError):
                    list(cargar_desarrollo(output / "desarrollo", "verificacion"))
            for path in processed.rglob("*.txt"):
                if path.parent.name[:10] >= "2026-02-02":
                    path.write_text("malo malo agua\n")
            second = base / "second_table"
            changed = MODULE.build(processed, resources, second)
            self.assertEqual(rows[:70], read_table(second / table.name)[:70])
            self.assertNotEqual(rows[70:], read_table(second / table.name)[70:])
            self.assertEqual(report["training_weighting"], changed["training_weighting"])
            for path in processed.rglob("*.txt"):
                if path.parent.name[:10] >= "2025-10-27":
                    path.write_text("malo agua potable malo\n")
            third = base / "third_table"
            test_changed = MODULE.build(processed, resources, third)
            self.assertEqual(rows[:56], read_table(third / table.name)[:56])
            self.assertEqual(report["training_weighting"], test_changed["training_weighting"])
            with self.assertRaises(FileExistsError):
                MODULE.build(processed, resources, first)
            weights_path = second / "pesos_fuentes_entrenamiento.json"
            weights = json.loads(weights_path.read_text())
            weights["calibration_weeks"] = 83
            weights_path.write_text(json.dumps(weights))
            with self.assertRaises(ValueError):
                partition_table(second / table.name, weights_path, base / "invalid")
            self.assertFalse((base / "invalid").exists())


if __name__ == "__main__":
    unittest.main()
