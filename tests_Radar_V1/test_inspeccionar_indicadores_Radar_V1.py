from __future__ import annotations

import csv
import importlib.util
import json
import tempfile
import unittest
import numpy as np
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scr_Radar_V1/operaciones_Radar_V1/inspeccionar_indicadores_Radar_V1.py"
SPEC = importlib.util.spec_from_file_location("radar_inspection", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class IndicatorInspectionTests(unittest.TestCase):
    def fixture(self, root):
        development = root / "desarrollo_Radar_V1"
        path = development / "entrenamiento_Radar_V1/indicadores_Radar_V1.csv"
        path.parent.mkdir(parents=True)
        rows = []
        for i in range(10):
            start = date(2025, 1, 6) + timedelta(weeks=i)
            rows.append({"semana_iso": str(i), "Fecha_Semana": str(start),
                "Fecha_Fin": str(start + timedelta(days=6)),
                "x": i, "doble": 2 * i, "constante": 7})
        with path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        (root / "auditoria_Radar_V1.json").write_text(json.dumps({"corpus_origin_policy": "current_repository_only",
            "subsets": {"entrenamiento": {"sha256": MODULE.digest(path)}}}))
        return development, path

    def test_training_only_complete_cases_and_redundancy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            development, path = self.fixture(root)
            before = path.read_bytes()
            original = Path.open

            def guarded(path, *args, **kwargs):
                if "verificacion_reservada_Radar_V1" in path.parts or "prueba" in path.parts:
                    self.fail("La inspección intentó abrir datos reservados")
                return original(path, *args, **kwargs)

            with patch.object(Path, "open", guarded):
                report, summaries, pairs = MODULE.inspect_training(development)
            self.assertEqual(report["training_rows"], 10)
            self.assertEqual(report["complete_rows"], 10)
            self.assertEqual(report["numeric_candidates"], 3)
            self.assertEqual(report["centered_matrix_rank"], 1)
            self.assertEqual(report["constant_columns"], ["constante"])
            self.assertFalse(report["regressions_run"])
            self.assertFalse(report["heldout_data_opened"])
            self.assertEqual(next(r for r in summaries if r["variable"] == "x")["media"], 4.5)
            self.assertAlmostEqual(pairs[0]["abs_pearson"], 1)
            self.assertEqual(path.read_bytes(), before)

    def test_export_is_reproducible_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            development, _ = self.fixture(root)
            output = root / "inspection"
            report = MODULE.generate(development, output)
            self.assertEqual(report["scope"], "training_only")
            for relative, expected in report["output_sha256"].items():
                self.assertEqual(MODULE.digest(output / relative), expected)
            self.assertIn("falta que el usuario", (output / "inspeccion_Radar_V1.md").read_text())
            with self.assertRaises(FileExistsError):
                MODULE.generate(development, output)

    def test_regressions_exclude_target_and_match_ridge_reference(self):
        from sklearn.linear_model import Ridge
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            development, path = self.fixture(root)
            before = path.read_bytes()
            original = Path.open

            def guarded(path, *args, **kwargs):
                if "verificacion_reservada_Radar_V1" in path.parts or "prueba" in path.parts:
                    self.fail("Regresiones intentaron leer datos reservados")
                return original(path, *args, **kwargs)

            with patch.object(Path, "open", guarded):
                report, univariate, ridge = MODULE.regress_training(development, "x", horizon=1)
            self.assertEqual(report["regression_rows"], 9)
            self.assertEqual(report["origins_purged_at_block_end"], 1)
            self.assertTrue(report["targets_confined_to_initial_block"])
            self.assertEqual(report["regression_predictors"], 1)
            self.assertEqual(report["constant_predictors_excluded"], ["constante"])
            self.assertTrue(report["target_excluded_from_predictors"])
            self.assertFalse(report["heldout_data_opened"])
            self.assertFalse(report["p_values_reported"])
            self.assertNotIn("x", [row["variable"] for row in ridge])
            self.assertNotIn("x_lag4", [row["variable"] for row in ridge])
            self.assertEqual(report["excluded_target_history"], [])
            raw_x = (2 * np.arange(9)).reshape(-1, 1)
            x = (raw_x - raw_x.mean(axis=0)) / raw_x.std(axis=0)
            y = np.arange(1, 10, dtype=float)
            y = (y - y.mean()) / y.std()
            expected = Ridge(alpha=1., fit_intercept=False, solver="cholesky").fit(x, y).coef_
            observed = {row["variable"]: row["beta_ridge_alpha_1"] for row in ridge}
            np.testing.assert_allclose([observed["doble"]], expected, atol=1e-12)
            self.assertAlmostEqual(univariate[0]["r2_exploratorio"], 1)
            self.assertAlmostEqual(univariate[0]["intercepto_original"], 1)
            self.assertEqual(path.read_bytes(), before)
            with self.assertRaises(ValueError):
                MODULE.regress_training(development, "no_existe")

    def test_each_future_horizon_matches_dates_and_nonlinear_reference(self):
        from sklearn.linear_model import Ridge
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            development, path = self.fixture(root)
            with path.open() as handle:
                rows = list(csv.DictReader(handle))
            for i, row in enumerate(rows):
                row["x"] = i * i
            with path.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            (root / "auditoria_Radar_V1.json").write_text(json.dumps({"corpus_origin_policy": "current_repository_only",
                "subsets": {"entrenamiento": {"sha256": MODULE.digest(path)}}}))
            for h in (1, 2, 3, 4):
                with self.subTest(horizon=h):
                    report, _, ridge = MODULE.regress_training(development, "x", horizon=h)
                    self.assertEqual(report["regression_rows"], 10 - h)
                    self.assertEqual(report["origins_purged_at_block_end"], h)
                    self.assertEqual(report["alignment"][-1]["fecha_objetivo"], rows[-1]["Fecha_Semana"])
                    for pair in report["alignment"]:
                        self.assertEqual(date.fromisoformat(pair["fecha_objetivo"]) -
                                         date.fromisoformat(pair["fecha_origen"]), timedelta(weeks=h))
                    raw_x = (2 * np.arange(10 - h)).reshape(-1, 1)
                    x = (raw_x - raw_x.mean(axis=0)) / raw_x.std(axis=0)
                    raw_y = np.arange(h, 10, dtype=float) ** 2
                    y = (raw_y - raw_y.mean()) / raw_y.std()
                    expected = Ridge(alpha=1., fit_intercept=False, solver="cholesky").fit(x, y).coef_
                    np.testing.assert_allclose([ridge[0]["beta_ridge_alpha_1"]], expected, atol=1e-12)
                    self.assertEqual(ridge[0]["horizonte_semanas"], h)
            for h in (0, -1, 5, True, 1.5):
                with self.assertRaises(ValueError):
                    MODULE.regress_training(development, "x", horizon=h)

    def test_unused_early_targets_and_purged_predictors_do_not_affect_results(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            development, path = self.fixture(root)
            with path.open() as handle:
                rows = list(csv.DictReader(handle))
            def save():
                with path.open("w", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                    writer.writeheader()
                    writer.writerows(rows)
                (root / "auditoria_Radar_V1.json").write_text(json.dumps({"corpus_origin_policy": "current_repository_only",
                    "subsets": {"entrenamiento": {"sha256": MODULE.digest(path)}}}))
            save()
            for h in (1, 2, 3):
                report, _, _ = MODULE.regress_training(development, "x", horizon=h)
                self.assertEqual(report["regression_rows"], 10 - h)
                self.assertEqual(report["eligible_origins_without_complete_history"], 0)
            # Para h=3, X de los últimos tres orígenes e Y de las primeras tres
            # semanas no se usan. Cambiarlos no debe mover el ajuste.
            before, uni_before, ridge_before = MODULE.regress_training(development, "x", horizon=3)
            for i, row in enumerate(rows):
                if i < 3:
                    row["x"] = 10000 + i
                if i >= 7:
                    row["doble"] = 100000 + i
            save()
            after, uni_after, ridge_after = MODULE.regress_training(development, "x", horizon=3)
            self.assertEqual(before, after)
            self.assertEqual(uni_before, uni_after)
            self.assertEqual(ridge_before, ridge_after)

    def test_legacy_smoothed_or_lagged_schema_is_rejected(self):
        for column in ("x_MA5", "doble_lag1", "x_lag4"):
            with self.subTest(column=column), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                development, path = self.fixture(root)
                with path.open() as handle:
                    rows = list(csv.DictReader(handle))
                for row in rows:
                    row[column] = row["doble"]
                with path.open("w", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                    writer.writeheader()
                    writer.writerows(rows)
                (root / "auditoria_Radar_V1.json").write_text(json.dumps({"corpus_origin_policy": "current_repository_only",
                    "subsets": {"entrenamiento": {"sha256": MODULE.digest(path)}}}))
                with self.assertRaisesRegex(ValueError, "no se permiten MA5"):
                    MODULE.regress_training(development, "x")

    def test_regression_export_records_chosen_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            development, _ = self.fixture(root)
            output = root / "regressions"
            report = MODULE.generate(development, output, target="x")
            self.assertTrue(report["regressions_run"])
            self.assertEqual(report["target"], "x")
            self.assertTrue((output / "regresiones_univariadas_Radar_V1.csv").is_file())
            self.assertTrue((output / "regresion_ridge_Radar_V1.csv").is_file())
            self.assertTrue((output / "alineacion_horizontes_Radar_V1.csv").is_file())
            self.assertEqual(report["horizons_weeks"], [1, 2, 3, 4])
            self.assertEqual([item["regression_rows"] for item in report["regressions_by_horizon"]], [9, 8, 7, 6])


if __name__ == "__main__":
    unittest.main()
