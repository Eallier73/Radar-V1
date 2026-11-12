from __future__ import annotations

import csv
import importlib.util
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scr_Radar_V1/nlp_Radar_V1/construir_tabla_indicadores_Radar_V1.py"
SPEC = importlib.util.spec_from_file_location("radar_indicator_table", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
from generar_conjuntos_temporales_Radar_V1 import cargar_desarrollo, partition_table


def read_table(path):
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


class IndicatorTests(unittest.TestCase):
    def resources(self, folder):
        folder.mkdir()
        for positive, negative in MODULE.POLARITY_FILES.values():
            (folder / positive).write_text("bueno\n")
            (folder / negative).write_text("malo\n")
        (folder / "Diccionario_Temas_V5_Radar_V1.csv").write_text("Agua\nagua\nagua potable\n")
        (folder / "Stoplists_Por_Tema_1_Radar_V1.csv").write_text("Agua\nuno\n")
        (folder / "stop_list_español_Radar_V1.txt").write_text("de\n")
        (folder / "exclusiones_polaridad_Radar_V1.json").write_text("[]")
        entries = {p.name: {"original_path": "/proyecto_anterior/solo_diccionarios/" + p.name, "sha256": MODULE.digest(p)}
                   for p in folder.iterdir() if p.is_file()}
        (folder / "procedencia_Radar_V1.json").write_text(json.dumps(entries))

    def corpus(self, folder):
        for index in range(83):
            start = date(2024, 9, 30) + timedelta(weeks=index)
            week = f"{start}_semana_fixture"
            for source in MODULE.SOURCES:
                path = folder / f"{source}_semanal_procesado_Radar_V1" / week / f"{week.removesuffix('_Radar_V1')}_{source}_Radar_V1.txt"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("bueno malo agua agua potable\nbueno\n")

    def test_indicator_numerators_denominators_and_missing_polarity(self):
        polar = MODULE.Matcher({"Original_pos": {"bueno"}, "Original_neg": {"malo"}})
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

    def test_analysis_keeps_exact_weekly_values_and_rejects_smoothed_support(self):
        names = ("semana_iso", "Fecha_Semana", "Fecha_Fin")
        rows = [{**dict.fromkeys(names, str(i)), "intensidad_por_1000_Conjunto_Agua": value,
                 "palabras_Youtube": 100} for i, value in enumerate([1, 500, 2])]
        selected = MODULE.weighted_analysis_rows(rows)
        self.assertEqual([r["intensidad_por_1000_Conjunto_Agua"] for r in selected], [1, 500, 2])
        self.assertTrue(all(len(r) == 4 for r in selected))
        rows[0]["intensidad_por_1000_Conjunto_Agua_MA5"] = 123
        with self.assertRaisesRegex(ValueError, "sin suavizado"):
            MODULE.weighted_analysis_rows(rows)

    def test_dictionary_reuse_is_allowed_but_hashes_and_file_roles_are_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "resources"
            folder.mkdir()
            with self.assertRaisesRegex(ValueError, "Faltan los diccionarios"):
                MODULE.load_resources(folder)
            folder.rmdir()
            self.resources(folder)
            manifest = folder / "procedencia_Radar_V1.json"
            approved = json.loads(manifest.read_text())
            MODULE.load_resources(folder)
            manifest.write_text(json.dumps({"corpus.csv": {"original_path": "/otro_proyecto/corpus.csv"}}))
            with self.assertRaisesRegex(ValueError, "exactamente los diccionarios"):
                MODULE.load_resources(folder)
            name = "diccionario_palabras_positivas_Radar_V1.txt"
            manifest.write_text(json.dumps(approved))
            (folder / name).write_text("cambiado\n")
            with self.assertRaisesRegex(ValueError, "no coincide"):
                MODULE.load_resources(folder)

    def test_reuse_checks_inputs_and_outputs_without_rebuilding_or_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            resources, processed, output = base / "resources", base / "processed", base / "indicators"
            self.resources(resources)
            self.corpus(processed)
            MODULE.build(processed, resources, output)
            before = {p: p.read_bytes() for p in output.rglob("*") if p.is_file()}
            with patch.object(MODULE, "build", side_effect=AssertionError("No debe recalcular")):
                result = MODULE.build_or_reuse(processed, resources, output, reuse_existing=True)
            self.assertEqual(result["status"], "existing_indicator_table_verified")
            self.assertEqual(before, {p: p.read_bytes() for p in output.rglob("*") if p.is_file()})
            changed = output / "tabla_analisis_ponderada_Radar_V1.csv"
            changed.write_text("alterada\n")
            with self.assertRaisesRegex(ValueError, "productos fueron alterados"):
                MODULE.build_or_reuse(processed, resources, output, reuse_existing=True)
            changed.write_bytes(before[changed])
            corpus_file = next(processed.rglob("*.txt"))
            corpus_file.write_text("malo agua\n")
            with self.assertRaisesRegex(ValueError, "Cambió el corpus"):
                MODULE.build_or_reuse(processed, resources, output, reuse_existing=True)
            self.assertEqual(before, {p: p.read_bytes() for p in output.rglob("*") if p.is_file()})

    def test_build_then_partition_and_future_mutations_do_not_affect_development(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            resources, processed = base / "resources", base / "processed"
            self.resources(resources)
            self.corpus(processed)
            first = base / "first_table"
            report = MODULE.build(processed, resources, first)
            table = first / "tabla_indicadores_83_semanas_Radar_V1.csv"
            before = table.read_bytes()
            rows = read_table(table)
            analysis = read_table(first / "archivo_Radar_V1/tabla_analisis_completa_83_semanas_Radar_V1.csv")
            working = read_table(first / "tabla_analisis_ponderada_Radar_V1.csv")
            self.assertEqual(len(working), 70)
            self.assertEqual(working, analysis[:70])
            self.assertFalse({row["Fecha_Semana"] for row in working} & {row["Fecha_Semana"] for row in analysis[70:]})
            self.assertFalse(any("Etiquetado" in column for column in rows[0]))
            self.assertFalse(any("Etiquetado" in column for column in analysis[0]))
            base_rows = [{key: value for key, value in row.items()
                         if key in {"semana_iso", "Fecha_Semana", "Fecha_Fin"} or "_Conjunto_" in key} for row in rows]
            self.assertEqual(analysis, base_rows)
            self.assertFalse(any("_MA5" in c or "_lag" in c for c in analysis[0]))
            self.assertTrue(all("_Conjunto_" in key for key in analysis[0] if key not in {"semana_iso", "Fecha_Semana", "Fecha_Fin"}))
            self.assertIn("Sentimiento_Conjunto_Original_Original", analysis[0])
            self.assertNotIn("palabras_Youtube", analysis[0])
            self.assertEqual(report["rows"], 83)
            self.assertEqual(len(rows), 83)
            self.assertFalse(report["smoothing"]["applied"])
            self.assertEqual(report["predictor_lags"], [])
            output = base / "sets"
            divided = partition_table(first / "archivo_Radar_V1/tabla_analisis_completa_83_semanas_Radar_V1.csv", first / "pesos_fuentes_entrenamiento_Radar_V1.json", output)
            self.assertEqual([m["rows"] for m in divided["subsets"].values()], [56, 14, 13])
            recombined = []
            for name, meta in divided["subsets"].items():
                recombined.extend(read_table(output / meta["table"]))
            self.assertEqual(analysis, recombined)
            self.assertEqual(working, read_table(output / "desarrollo_Radar_V1/indicadores_Radar_V1.csv"))
            self.assertEqual(table.read_bytes(), before)
            original_open = Path.open

            def guarded_open(path, *args, **kwargs):
                if "verificacion_reservada_Radar_V1" in path.parts:
                    self.fail("Se abrió verificación desde desarrollo_Radar_V1")
                return original_open(path, *args, **kwargs)

            with patch.object(Path, "open", guarded_open):
                self.assertEqual(len(list(cargar_desarrollo(output / "desarrollo_Radar_V1", "entrenamiento"))), 56)
                self.assertEqual(len(list(cargar_desarrollo(output / "desarrollo_Radar_V1", "prueba"))), 14)
                with self.assertRaises(ValueError):
                    list(cargar_desarrollo(output / "desarrollo_Radar_V1", "verificacion"))
            for path in processed.rglob("*.txt"):
                if path.parent.name[:10] >= "2026-02-02":
                    path.write_text("malo malo agua\n")
            second = base / "second_table"
            changed = MODULE.build(processed, resources, second)
            self.assertEqual(rows[:70], read_table(second / table.name)[:70])
            self.assertEqual(working, read_table(second / "tabla_analisis_ponderada_Radar_V1.csv"))
            self.assertNotEqual(rows[70:], read_table(second / table.name)[70:])
            self.assertEqual(report["training_weighting"], changed["training_weighting"])
            for path in processed.rglob("*.txt"):
                if path.parent.name[:10] >= "2025-10-27":
                    path.write_text("malo agua potable malo\n")
            third = base / "third_table"
            test_changed = MODULE.build(processed, resources, third)
            self.assertEqual(rows[:56], read_table(third / table.name)[:56])
            self.assertEqual(analysis[:56], read_table(third / "tabla_analisis_ponderada_Radar_V1.csv")[:56])
            self.assertEqual(report["training_weighting"], test_changed["training_weighting"])
            with self.assertRaises(FileExistsError):
                MODULE.build(processed, resources, first)
            weights_path = second / "pesos_fuentes_entrenamiento_Radar_V1.json"
            weights = json.loads(weights_path.read_text())
            weights["calibration_weeks"] = 83
            weights_path.write_text(json.dumps(weights))
            with self.assertRaises(ValueError):
                partition_table(second / table.name, weights_path, base / "invalid")
            self.assertFalse((base / "invalid").exists())


if __name__ == "__main__":
    unittest.main()
