from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scr" / "extraccion" / "run_extraccion.py"
MODULE_NAME = "radar_test_run_extraccion"
SPEC = importlib.util.spec_from_file_location(MODULE_NAME, SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"No se pudo cargar {SCRIPT_PATH}")
RUNNER = importlib.util.module_from_spec(SPEC)
sys.modules[MODULE_NAME] = RUNNER
SPEC.loader.exec_module(RUNNER)


class RunExtraccionTests(unittest.TestCase):
    def test_normalize_sources_preserves_operational_order(self):
        self.assertEqual(
            RUNNER.normalize_sources(["facebook,youtube", "medios"]),
            ("youtube", "medios", "facebook"),
        )

    def test_unknown_source_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Fuentes desconocidas"):
            RUNNER.normalize_sources(["instagram"])

    def test_list_does_not_require_dates(self):
        self.assertEqual(RUNNER.main(["--list"]), 0)

    def test_build_facebook_plan_links_posts_to_comments(self):
        output_dir = Path("/tmp/radar-test-output")
        plans = RUNNER.build_source_plans(
            ["facebook"],
            "2026-08-10",
            "2026-08-16",
            output_dir,
            python_executable="python-test",
        )
        self.assertEqual(len(plans), 1)
        self.assertEqual(len(plans[0].commands), 2)
        posts_csv, _canonical_csv = RUNNER.facebook_paths(
            output_dir,
            "2026-08-10",
            "2026-08-16",
        )
        self.assertIn(str(posts_csv), plans[0].commands[1].command)
        self.assertTrue(plans[0].commands[1].skip_when_posts_empty)

    def test_medios_plan_extracts_then_processes_csv_and_txt(self):
        output_dir = Path("/tmp/radar-test-output")
        processed_dir = Path("/tmp/radar-test-processed-medios")
        plans = RUNNER.build_source_plans(
            ["medios"],
            "2026-08-10",
            "2026-08-16",
            output_dir,
            python_executable="python-test",
            processed_medios_dir=processed_dir,
        )
        self.assertEqual(len(plans), 1)
        self.assertEqual(len(plans[0].commands), 2)
        self.assertIn("3_extractors_medios.py", plans[0].commands[0].command[1])
        self.assertIn("procesar_medios_semanal.py", plans[0].commands[1].command[1])
        self.assertIn(str(output_dir), plans[0].commands[1].command)
        self.assertIn(str(processed_dir), plans[0].commands[1].command)

    def test_empty_facebook_week_keeps_only_canonical_csv(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            posts_csv, canonical_csv = RUNNER.facebook_paths(
                output_dir,
                "2026-08-10",
                "2026-08-16",
            )
            posts_csv.parent.mkdir(parents=True)
            with posts_csv.open("w", encoding="utf-8-sig", newline="") as handle:
                csv.DictWriter(handle, fieldnames=["post_url"]).writeheader()

            self.assertEqual(RUNNER.count_post_urls(posts_csv), 0)
            RUNNER.write_empty_facebook_csv(posts_csv, canonical_csv)

            self.assertFalse(posts_csv.exists())
            self.assertTrue(canonical_csv.is_file())
            with canonical_csv.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                self.assertEqual(tuple(reader.fieldnames or ()), RUNNER.FACEBOOK_COLUMNS)
                self.assertEqual(list(reader), [])

    def test_dry_run_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "datos"
            result = RUNNER.main(
                [
                    "--since",
                    "2026-08-10",
                    "--before",
                    "2026-08-16",
                    "--sources",
                    "youtube",
                    "facebook",
                    "--output-dir",
                    str(output_dir),
                    "--dry-run",
                ]
            )
            self.assertEqual(result, 0)
            self.assertFalse(output_dir.exists())


if __name__ == "__main__":
    unittest.main()
