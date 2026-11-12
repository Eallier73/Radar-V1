from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from datetime import date, datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scr_Radar_V1" / "compartido_Radar_V1" / "00_orquestador_general_Radar_V1.py"
MODULE_NAME = "radar_test_orquestador"
SPEC = importlib.util.spec_from_file_location(MODULE_NAME, SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"No se pudo cargar {SCRIPT_PATH}")
ORCH = importlib.util.module_from_spec(SPEC)
sys.modules[MODULE_NAME] = ORCH
SPEC.loader.exec_module(ORCH)


class OrquestadorRadarTests(unittest.TestCase):
    def test_catalog_covers_all_operations_and_future_stages(self):
        self.assertEqual(
            [stage.key for stage in ORCH.PIPELINES],
            [
                "extraccion",
                "procesar_csv",
                "preprocesamiento",
                "validacion",
                "ponderacion",
                "nlp",
                "particion",
                "inspeccion",
                "seleccion",
                "modelado",
                "insumo_tablero",
                "tablero",
                "reporte",
            ],
        )

    def test_default_week_is_complete(self):
        _since, before = ORCH.iso_week_to_range(ORCH.DEFAULT_GLOBAL_ISO_WEEK)
        end = datetime.strptime(before, "%Y-%m-%d").date()
        self.assertEqual(end.weekday(), 6)
        self.assertLess(end, date.today())

    def test_extraction_runner_is_available(self):
        stage = ORCH.PIPELINES_BY_KEY["extraccion"]
        available, message = ORCH.stage_status(stage)
        self.assertTrue(available, message)

    def test_extraction_command_contains_selected_sources(self):
        stage = ORCH.PIPELINES_BY_KEY["extraccion"]
        command, _env = ORCH.build_pipeline(
            stage,
            "2026-08-10",
            "2026-08-16",
            extraction_sources=["medios", "youtube"],
        )
        source_index = command.index("--sources")
        self.assertEqual(command[source_index + 1 :], ["youtube", "medios"])

    def test_continue_on_error_reaches_extraction_runner(self):
        stage = ORCH.PIPELINES_BY_KEY["extraccion"]
        command, _env = ORCH.build_pipeline(
            stage,
            "2026-08-10",
            "2026-08-16",
            continue_on_error=True,
        )
        self.assertIn("--continue-on-error", command)

    def test_preprocessing_uses_current_processed_tree_and_selected_sources(self):
        stage = ORCH.PIPELINES_BY_KEY["preprocesamiento"]
        command, _env = ORCH.build_pipeline(
            stage,
            "2026-08-10",
            "2026-08-16",
            extraction_sources=["facebook", "twitter"],
        )
        self.assertIn("promover_csv_a_texto_Radar_V1.py", command[1])
        self.assertIn("radar_semanal_procesado_Radar_V1", command[command.index("--processed-dir") + 1])
        source_index = command.index("--sources")
        self.assertEqual(command[source_index + 1 :], ["twitter", "facebook"])

    def test_pending_stages_remain_in_catalog(self):
        for key in ("modelado", "tablero", "reporte"):
            available, _message = ORCH.stage_status(ORCH.PIPELINES_BY_KEY[key])
            self.assertFalse(available)

    def test_nlp_uses_the_actual_builder_with_its_own_cli_contract(self):
        stage = ORCH.PIPELINES_BY_KEY["nlp"]
        self.assertTrue(ORCH.stage_status(stage)[0])
        self.assertEqual(stage.runner, REPO_ROOT / "scr_Radar_V1/nlp_Radar_V1/construir_tabla_indicadores_Radar_V1.py")
        command, _env = ORCH.build_pipeline(stage, "2026-08-10", "2026-08-16",
                                          extraction_sources=["youtube"])
        self.assertNotIn("--since", command)
        self.assertNotIn("--before", command)
        self.assertNotIn("--sources", command)
        self.assertIn("--reuse-existing", command)
        self.assertEqual(command[command.index("--processed-dir") + 1],
                         str(REPO_ROOT / "datos_Radar_V1/radar_semanal_procesado_Radar_V1"))
        completed = subprocess.run([*command, "--help"], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_gui_uses_the_same_available_nlp_stage_and_command(self):
        spec = importlib.util.spec_from_file_location("radar_gui_nlp_test", REPO_ROOT / "scr_Radar_V1/compartido_Radar_V1/00_gui_orquestador_Radar_V1.py")
        gui = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gui)
        stage = next(stage for stage in gui.PIPELINES if stage.key == "nlp")
        self.assertTrue(gui.ORQUESTADOR.stage_status(stage)[0])
        plans = gui.ORQUESTADOR.build_stage_commands(stage, "2026-08-10", "2026-08-16")
        self.assertEqual(plans[0][0][1], str(REPO_ROOT / "scr_Radar_V1/nlp_Radar_V1/construir_tabla_indicadores_Radar_V1.py"))


if __name__ == "__main__":
    unittest.main()
