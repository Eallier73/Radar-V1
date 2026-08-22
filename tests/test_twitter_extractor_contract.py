from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scr" / "extraccion" / "2_extractors_twitter.py"
MODULE_NAME = "radar_test_twitter_extractor_contract"
SPEC = importlib.util.spec_from_file_location(MODULE_NAME, SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"No se pudo cargar {SCRIPT_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[MODULE_NAME] = MODULE
SPEC.loader.exec_module(MODULE)


def raw_tweet(identifier: str, published_at: str, text: str, query: str = "tampico"):
    return {
        "author": "@cuenta",
        "datetime": published_at,
        "datetime_parsed_utc": published_at,
        "url": f"https://x.com/cuenta/status/{identifier}" if identifier else "",
        "text": text,
        "replies": 0,
        "retweets": 0,
        "likes": 0,
        "bookmarks": 0,
        "views": 0,
        "query_used": query,
        "is_reply": False,
        "in_reply_to_url": "",
    }


class TwitterExtractorContractTests(unittest.TestCase):
    def build_extractor(self, root: Path):
        return MODULE.TwitterExtractorIAD(
            "2026-04-06",
            "2026-04-12",
            output_base_dir=root,
            state_path=root / "state.json",
            create_output_dir=True,
        )

    def test_only_uniform_query_is_built(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            extractor = self.build_extractor(Path(temp_dir))
            self.assertEqual(
                extractor.search_queries,
                ["tampico since:2026-04-06 until:2026-04-13"],
            )
            with self.assertRaises(ValueError):
                MODULE.TwitterExtractorIAD(
                    "2026-04-06",
                    "2026-04-12",
                    custom_queries=["@TampicoGob"],
                    output_base_dir=Path(temp_dir),
                    create_output_dir=False,
                )

    def test_output_contract_filters_content_week_and_duplicates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            extractor = self.build_extractor(Path(temp_dir))
            rows = [
                raw_tweet("1", "2026-04-06T00:00:00Z", "Noticias de Tampico", "q1"),
                raw_tweet("1", "2026-04-06T00:00:00Z", "Noticias de Tampico", "q2"),
                raw_tweet("2", "2026-04-12T23:59:59Z", "TAMPICO al cierre"),
                raw_tweet("3", "2026-04-13T00:00:00Z", "Tampico fuera"),
                raw_tweet("4", "2026-04-10T12:00:00Z", "Gobierno municipal"),
                raw_tweet("5", "2026-04-10T12:00:00Z", "@TampicoGob informa"),
            ]
            canonical, counters = extractor.apply_output_contract(rows)
            self.assertEqual(list(canonical[0]), list(MODULE.TWITTER_OUTPUT_COLUMNS))
            self.assertEqual([row["tweet_id"] for row in canonical], ["1", "2"])
            self.assertEqual(counters["duplicates"], 1)
            self.assertEqual(counters["after"], 1)
            self.assertEqual(counters["outside_content_rule"], 2)

    def test_empty_week_still_writes_canonical_header(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            extractor = self.build_extractor(Path(temp_dir))
            extractor.save_to_csv([])
            with extractor.output_csv.open(
                "r", encoding="utf-8-sig", newline=""
            ) as handle:
                reader = csv.DictReader(handle)
                self.assertEqual(
                    reader.fieldnames,
                    list(MODULE.TWITTER_OUTPUT_COLUMNS),
                )
                self.assertEqual(list(reader), [])


if __name__ == "__main__":
    unittest.main()
