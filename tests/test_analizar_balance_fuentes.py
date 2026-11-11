from __future__ import annotations

import csv
import importlib.util
import math
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scr/operaciones/analizar_balance_fuentes.py"
SPEC = importlib.util.spec_from_file_location("radar_balance_sources_test", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class CorpusBalanceTests(unittest.TestCase):
    def test_weighting_scenarios_and_scale_invariance(self):
        totals = {"a": 4, "b": 16}
        self.assertEqual(MODULE.power_weights(totals, 0), {"a": .5, "b": .5})
        self.assertEqual(MODULE.power_weights(totals, 1), {"a": .2, "b": .8})
        weights = MODULE.power_weights(totals, .5)
        self.assertAlmostEqual(weights["a"], 1 / 3)
        self.assertAlmostEqual(weights["b"], 2 / 3)
        scaled = MODULE.power_weights({key: value * 100 for key, value in totals.items()}, .5)
        self.assertEqual(weights, scaled)
        self.assertAlmostEqual(sum(weights.values()), 1)
        multipliers = {key: weights[key] / value for key, value in totals.items()}
        self.assertAlmostEqual(sum(totals[key] * value for key, value in multipliers.items()), 1)

    def test_missing_or_invalid_inputs_do_not_produce_silent_weights(self):
        for data in ({}, {"a": 0}, {"a": -1}, {"a": math.nan}):
            with self.assertRaises(ValueError):
                MODULE.power_weights(data, .5)
        for alpha in (-.1, 1.1, math.nan):
            with self.assertRaises(ValueError):
                MODULE.power_weights({"a": 1}, alpha)

    def test_statistics_distinguish_empty_data_and_handle_tied_ranks(self):
        self.assertIsNone(MODULE.describe([])["mean"])
        self.assertEqual(MODULE.describe([0, 2, 4])["median"], 2)
        self.assertEqual(MODULE.ranks([10, 10, 20]), [1.5, 1.5, 3])
        self.assertAlmostEqual(MODULE.pearson([1, 2, 3], [3, 6, 9]), 1)
        self.assertIsNone(MODULE.pearson([1, 1, 1], [1, 2, 3]))
        self.assertIsNone(MODULE.pearson([1, 2], [1, 2]))

    def test_author_identifiers_are_not_manufactured(self):
        self.assertEqual(MODULE.author_identifier({"author": " @Cuenta "}), ("cuenta", "author_field"))
        self.assertEqual(MODULE.author_identifier({"author": "", "url": "https://x.com/Cuenta/status/1"}), ("cuenta", "tweet_url"))
        self.assertEqual(MODULE.author_identifier({"author": "", "url": "https://not-x.com/Cuenta/status/1"}), (None, None))
        self.assertEqual(MODULE.author_identifier({"author": "unknown"}), (None, None))
        self.assertEqual(MODULE.author_identifier({"url": "https://[invalid"}), (None, None))

    def corpus(self, root):
        week = "2026-04-06_semana_06abril_12abril_26"
        for source, column in MODULE.TEXT_COLUMNS.items():
            path = root / f"{source}_semanal_procesado" / week / f"{week}_{source}.csv"
            path.parent.mkdir(parents=True)
            columns = MODULE.SOURCE_COLUMNS[source]
            row = dict.fromkeys(columns, "")
            row[column] = "Niñas y niños 2026"
            if source == "twitter":
                row["author"] = "@Cuenta"
            if source == "facebook":
                row.update(tipo="POST", cuenta="tampicogob")
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=columns)
                writer.writeheader()
                writer.writerow(row)
            path.with_suffix(".txt").write_text(MODULE.build_text_content(source, [row])[0], encoding="utf-8")
        media = root / "medios_semanal_procesado" / week / f"{week}_medios.txt"
        media.parent.mkdir(parents=True)
        media.write_text("noticia de prueba\n", encoding="utf-8")

    def test_audit_preserves_inputs_and_does_not_invent_media_articles_or_users(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.corpus(root)
            before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
            result = MODULE.analyze(root)
            self.assertEqual(result["weeks"], 1)
            self.assertEqual(result["total_words"], 12)
            self.assertIsNone(result["sources"]["medios"]["records"])
            self.assertIsNone(result["sources"]["medios"]["words_per_usable_record"])
            self.assertIsNone(result["sources"]["facebook"]["observed_authors_all"])
            self.assertIsNone(result["sources"]["youtube"]["observed_authors_all"])
            self.assertEqual(result["sources"]["twitter"]["observed_authors_usable"], 1)
            self.assertFalse(result["weighting"]["user_factor_used"])
            self.assertIn("propuesta", MODULE.render_report(result).lower())
            self.assertEqual(before, {path: path.read_bytes() for path in before})

    def test_inconsistent_txt_is_an_error_not_a_new_source_weight(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.corpus(root)
            path = next((root / "youtube_semanal_procesado").rglob("*.txt"))
            path.write_text("texto ajeno\n")
            with self.assertRaises(ValueError):
                MODULE.analyze(root)


if __name__ == "__main__":
    unittest.main()
