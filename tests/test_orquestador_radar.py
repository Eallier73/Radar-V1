from __future__ import annotations

import importlib.util
import sys
import unittest
from datetime import date, datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scr" / "compartido" / "00_orquestador_general.py"
MODULE_NAME = "radar_test_orquestador"
SPEC = importlib.util.spec_from_file_location(MODULE_NAME, SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"No se pudo cargar {SCRIPT_PATH}")
ORCH = importlib.util.module_from_spec(SPEC)
sys.modules[MODULE_NAME] = ORCH
SPEC.loader.exec_module(ORCH)


class OrquestadorRadarTests(unittest.TestCase):
    def test_catalog_keeps_six_stages(self):
        self.assertEqual(
            [stage.key for stage in ORCH.PIPELINES],
            [
                "extraccion",
                "preprocesamiento",
                "nlp",
                "modelado",
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

    def test_pending_stages_remain_in_catalog(self):
        for key in ("nlp", "modelado", "tablero", "reporte"):
            available, _message = ORCH.stage_status(ORCH.PIPELINES_BY_KEY[key])
            self.assertFalse(available)


if __name__ == "__main__":
    unittest.main()
