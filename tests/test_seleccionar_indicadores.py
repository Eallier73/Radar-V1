from __future__ import annotations

import copy
import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import numpy as np

SCRIPT = Path(__file__).resolve().parents[1] / "scr/operaciones/seleccionar_indicadores.py"
SPEC = importlib.util.spec_from_file_location("radar_selection", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class IndicatorSelectionTests(unittest.TestCase):
    def inputs(self, monica=False):
        rng = np.random.default_rng(724)
        target = MODULE.DEFAULT_TARGET
        bases = [target, "intensidad_por_1000_Conjunto_Agua",
                 "presencia_segmentos30_pct_Conjunto_Agua",
                 "intensidad_por_1000_Conjunto_Economia",
                 "presencia_segmentos30_pct_Conjunto_Economia"]
        if monica:
            bases = [base.replace("_Agua", "_Visibilidad_MV") for base in bases]
        names = bases[1:]
        rates = rng.uniform(20, 80, (56, 4, len(bases)))
        # Duplicado exacto: debe identificarse como redundante para cualquier corte.
        rates[:, :, 2] = rates[:, :, 1] * 1.5
        words = rng.integers(100, 2000, (56, 4)).astype(float)
        result = MODULE.Inputs([], bases, names, rates, words, {})
        x, y, _ = MODULE.rebuild(result, 56)
        for i in range(56):
            start = date(2024, 9, 30) + timedelta(weeks=i)
            year, week, _ = start.isocalendar()
            row = {"semana_iso": f"{year}-W{week:02d}", "Fecha_Semana": str(start),
                   "Fecha_Fin": str(start + timedelta(days=6)), target: y[i]}
            row.update({name: x[i, j] if np.isfinite(x[i, j]) else "" for j, name in enumerate(names)})
            result.rows.append(row)
        return result

    def fixture(self, root, monica=False):
        data = self.inputs(monica=monica)
        development = root / "modelado/desarrollo"
        path = development / "entrenamiento/indicadores.csv"
        path.parent.mkdir(parents=True)
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(data.rows[0]))
            writer.writeheader()
            writer.writerows(data.rows)
        (development.parent / "auditoria.json").write_text(json.dumps({
            "corpus_origin_policy": "current_repository_only",
            "subsets": {"entrenamiento": {"sha256": MODULE.digest(path)}}}))
        support = root / "indicadores/soporte.csv"
        support.parent.mkdir()
        (support.parent / "auditoria.json").write_text(json.dumps({"corpus_origin_policy": "current_repository_only"}))
        rows = []
        for i, meta in enumerate(data.rows):
            row = {c: meta[c] for c in MODULE.META}
            row.update({f"palabras_{label}": data.words[i, s] for s, label in enumerate(MODULE.LABELS)})
            row.update({base.replace("_Conjunto_", f"_{label}_"): data.rates[i, s, j]
                        for s, label in enumerate(MODULE.LABELS) for j, base in enumerate(data.bases)})
            rows.append(row)
        with support.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
            # El lector debe cerrar después de 56 filas sin consumir siquiera ésta.
            handle.write('"FILA POSTERIOR QUE NO ES UNA TASA NUMERICA",ERROR\n')
        return development, support

    def test_loading_consumes_initial_prefix_only_and_excludes_polarity_history(self):
        with tempfile.TemporaryDirectory() as directory:
            development, support = self.fixture(Path(directory))
            original = Path.open

            def guarded(path, *args, **kwargs):
                if any(part in {"prueba", "verificacion_reservada", "archivo"} for part in path.parts):
                    self.fail("Se intentaron leer datos fuera del bloque inicial")
                return original(path, *args, **kwargs)

            with patch.object(Path, "open", guarded):
                inputs = MODULE.load_inputs(development, support)
            self.assertEqual(inputs.rates.shape, (56, 4, 5))
            self.assertEqual(inputs.evidence["support_numeric_rows_consumed"], 56)
            self.assertFalse(any("Sentimiento" in name for name in inputs.names))
            self.assertEqual(len(inputs.names), 4)

    def test_rebuild_recalibrates_prefix_weights_and_never_borrows_future(self):
        inputs = self.inputs()
        before_x, before_y, before_weights = MODULE.rebuild(inputs, 28)
        ranking = MODULE.rank_and_prune(inputs, 28)
        changed = copy.deepcopy(inputs)
        changed.rates[28:] *= 100
        changed.words[28:, 0] *= 10000
        after_x, after_y, after_weights = MODULE.rebuild(changed, 28)
        np.testing.assert_allclose(before_weights, after_weights)
        np.testing.assert_allclose(before_x[:28], after_x[:28], equal_nan=True)
        np.testing.assert_allclose(before_y[:28], after_y[:28])
        reranked = MODULE.rank_and_prune(changed, 28)
        self.assertEqual(ranking["details"], reranked["details"])
        self.assertEqual(ranking["decisions"], reranked["decisions"])
        self.assertFalse(np.allclose(before_weights, MODULE.rebuild(inputs, 56)[2]))
        expected = np.sqrt(inputs.words[:28].sum(axis=0))
        np.testing.assert_allclose(before_weights, expected / expected.sum())

    def test_pairs_purge_labels_crossing_each_temporal_boundary(self):
        inputs = self.inputs()
        x, y, _ = MODULE.rebuild(inputs, 28)
        for h in MODULE.HORIZONS:
            paired_x, paired_y, origins = MODULE.paired(x, y, 28, h)
            self.assertEqual(len(origins), 28 - h)
            self.assertTrue((origins + h < 28).all())
            np.testing.assert_allclose(paired_x, x[origins])
            np.testing.assert_allclose(paired_y, y[origins + h])

    def test_a_weekly_spike_does_not_spread_to_other_rows_or_the_response(self):
        inputs = self.inputs()
        before_x, before_y, _ = MODULE.rebuild(inputs, 28)
        changed = copy.deepcopy(inputs)
        changed.rates[35, :, 1] += 1000
        after_x, after_y, _ = MODULE.rebuild(changed, 28)
        others = np.arange(56) != 35
        np.testing.assert_allclose(before_x[others], after_x[others])
        np.testing.assert_allclose(before_y, after_y)
        self.assertFalse(np.allclose(before_x[35], after_x[35]))
        changed = copy.deepcopy(inputs)
        changed.rates[35, :, 0] += 1000
        after_x, after_y, _ = MODULE.rebuild(changed, 28)
        np.testing.assert_allclose(before_x, after_x)
        np.testing.assert_allclose(before_y[others], after_y[others])
        self.assertNotEqual(before_y[35], after_y[35])

    def test_redundancy_removes_duplicate_and_controls_joint_vif(self):
        inputs = self.inputs()
        result = MODULE.rank_and_prune(inputs, 56)
        names = {inputs.names[j] for j in result["path"]}
        a = "intensidad_por_1000_Conjunto_Agua"
        b = "presencia_segmentos30_pct_Conjunto_Agua"
        self.assertFalse({a, b} <= names)
        kept = result["complete_x"][:, result["path"]]
        self.assertLessEqual(MODULE.vifs(kept).max(), 5.)
        if len(names) > 1:
            corr = np.corrcoef(kept, rowvar=False)
            self.assertLess(np.abs(corr[np.triu_indices(len(names), 1)]).max(), .85)
        z = np.arange(10., dtype=float)
        self.assertTrue(np.isinf(MODULE.vifs(np.column_stack([z, z]))).all())
        np.testing.assert_equal(MODULE.vifs(z[:, None]), [1])

    def test_one_SE_rule_can_choose_zero_and_does_not_force_a_count(self):
        losses = [{"cut": cut, "k": k, "loss": value}
                  for cut, values in zip(MODULE.CUTS, [(1.0, .8, .7), (1.0, 1.2, 1.3),
                                                     (1.0, .8, .7), (1.0, 1.2, 1.3)])
                  for k, value in enumerate(values)]
        selected, summary, threshold, _ = MODULE.choose_size(losses)
        self.assertEqual(selected, 0)
        self.assertEqual(sum(row["seleccionado"] for row in summary), 1)
        losses = [{"cut": cut, "k": k, "loss": value}
                  for cut in MODULE.CUTS for k, value in enumerate([3., 2., 1., 1.])]
        self.assertEqual(MODULE.choose_size(losses)[0], 2)

    def test_export_is_auditable_keeps_sources_and_only_uses_initial_block(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            development, support = self.fixture(root)
            source_bytes = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
            output = root / "selection"
            original = Path.open

            def guarded(path, *args, **kwargs):
                if any(part in {"prueba", "verificacion_reservada", "archivo"} for part in path.parts):
                    self.fail("La selección abrió datos reservados")
                return original(path, *args, **kwargs)

            with patch.object(Path, "open", guarded):
                report = MODULE.generate(development, support, output)
            self.assertFalse(report["heldout_data_opened"])
            self.assertEqual(report["selected_k"], len(report["selected_columns"]))
            for filename, expected in report["output_sha256"].items():
                self.assertEqual(MODULE.digest(output / filename), expected)
            with (output / "tabla_inspeccion_reducida.csv").open() as handle:
                reader = csv.DictReader(handle)
                rows = list(reader)
                self.assertEqual(len(reader.fieldnames), report["selected_k"] + 4)
                self.assertFalse(any(name.startswith(MODULE.DEFAULT_TARGET + "_lag") for name in reader.fieldnames))
            self.assertEqual(len(rows), 56)
            self.assertEqual({p: p.read_bytes() for p in source_bytes}, source_bytes)
            with self.assertRaises(FileExistsError):
                MODULE.generate(development, support, output)
            with (output / "limites_temporales.csv").open() as handle:
                for row in csv.DictReader(handle):
                    self.assertLess(row["ultima_respuesta_ajuste"], row["inicio_comparacion"])
                    self.assertLessEqual(row["ultima_respuesta_comparacion"], "2025-10-20")

    def test_monica_redundancy_and_ablation_keep_original_columns(self):
        inputs = self.inputs(monica=True)
        before = copy.deepcopy(inputs)
        baseline, tables = MODULE.analyze(inputs)
        report, results = MODULE.monica_diagnostic(inputs, baseline, tables)
        self.assertTrue(report["applicable"])
        self.assertAlmostEqual(report["weekly_presence_intensity_pearson"], 1.)
        self.assertEqual(len(report["presence_columns"]), 1)
        self.assertEqual(len(report["all_MV_topic_columns"]), 2)
        self.assertEqual([row["candidatas"] for row in report["scenario_summary"]], [4, 3, 2])
        self.assertNotIn("Visibilidad_MV", report["scenario_summary"][-1]["columnas_candidatas_reajuste_56"])
        self.assertFalse(report["table_modified"])
        self.assertFalse(report["heldout_data_opened"])
        self.assertEqual(inputs.names, before.names)
        self.assertEqual(inputs.rows, before.rows)
        np.testing.assert_array_equal(inputs.rates, before.rates)
        self.assertEqual(len(results["comparacion_sin_MV_por_horizonte.csv"]), 12)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            development, support = self.fixture(root, monica=True)
            output = root / "selection"
            exported = MODULE.generate(development, support, output)
            self.assertTrue(exported["monica_redundancy_diagnostic"]["applicable"])
            self.assertIn("¿Es redundante", (output / "seleccion.md").read_text())
            self.assertTrue((output / "correlaciones_MV.csv").is_file())


if __name__ == "__main__":
    unittest.main()
