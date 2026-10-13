from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scr" / "preprocesamiento" / "validar_homogeneidad_semanal.py"
SPEC = importlib.util.spec_from_file_location("radar_test_homogeneity", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"No se pudo cargar {SCRIPT}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class HomogeneityValidatorTests(unittest.TestCase):
    def _write_csv(self, path: Path, columns: tuple[str, ...]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            csv.DictWriter(handle, fieldnames=columns).writeheader()

    def test_one_empty_canonical_week_is_valid_for_all_sources(self) -> None:
        week = "2026-04-06_semana_06abril_12abril_26"
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_csv(
                root / "youtube_semanal_procesado" / week / f"{week}_youtube.csv",
                MODULE.YOUTUBE_OUTPUT_COLUMNS,
            )
            (root / "youtube_semanal_procesado" / week / f"{week}_youtube.txt").write_text(
                "", encoding="utf-8"
            )
            self._write_csv(
                root / "twitter_semanal_procesado" / week / f"{week}_twitter.csv",
                MODULE.TWITTER_OUTPUT_COLUMNS,
            )
            (root / "twitter_semanal_procesado" / week / f"{week}_twitter.txt").write_text(
                "", encoding="utf-8"
            )
            media_txt = root / "medios_semanal_procesado" / week / f"{week}_medios.txt"
            media_txt.parent.mkdir(parents=True)
            media_txt.write_text("", encoding="utf-8")
            self._write_csv(
                root / "facebook_semanal_procesado" / week / f"{week}_facebook.csv",
                MODULE.FACEBOOK_PROCESSED_COLUMNS,
            )
            facebook_txt = root / "facebook_semanal_procesado" / week / f"{week}_facebook.txt"
            facebook_txt.write_text("", encoding="utf-8")

            result = MODULE.validate(
                root,
                MODULE.SOURCES,
                set(),
                require_same_weeks=True,
            )
        self.assertEqual(result["status"], "ok", result["errors"])

    def test_folder_label_must_match_exact_monday_to_sunday_week(self) -> None:
        malformed = "2026-04-06_semana_06abril_13abril_26"
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_csv(
                root / "youtube_semanal_procesado" / malformed / f"{malformed}_youtube.csv",
                MODULE.YOUTUBE_OUTPUT_COLUMNS,
            )
            result = MODULE.validate(
                root,
                ("youtube",),
                set(),
                require_same_weeks=False,
            )
        self.assertEqual(result["status"], "error")
        self.assertTrue(
            any("Nombre semanal fuera de contrato" in error for error in result["errors"]),
            result["errors"],
        )

    def test_twitter_accepts_account_scope_without_literal_tampico(self) -> None:
        week = "2026-04-06_semana_06abril_12abril_26"
        row = {column: "" for column in MODULE.TWITTER_OUTPUT_COLUMNS}
        row.update(
            {
                "tweet_id": "1",
                "author": "@cuenta",
                "published_at": "2026-04-10T12:00:00+00:00",
                "url": "https://x.com/cuenta/status/1",
                "text": "Informe del gobierno municipal",
                "query_raw": "@TampicoGob",
                "is_reply": "false",
            }
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            csv_path = (
                root
                / "twitter_semanal_procesado"
                / week
                / f"{week}_twitter.csv"
            )
            csv_path.parent.mkdir(parents=True)
            with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=MODULE.TWITTER_OUTPUT_COLUMNS,
                )
                writer.writeheader()
                writer.writerow(row)
            text, _, _ = MODULE.build_text_content("twitter", [row])
            csv_path.with_suffix(".txt").write_text(text, encoding="utf-8")

            result = MODULE.validate(
                root,
                ("twitter",),
                set(),
                require_same_weeks=False,
            )

        self.assertEqual(result["status"], "ok", result["errors"])


if __name__ == "__main__":
    unittest.main()
