from __future__ import annotations

import importlib.util
import sys
import unittest
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scr" / "extraccion" / "1_extractors_youtube.py"
MODULE_NAME = "radar_test_youtube_extractor_contract"
SPEC = importlib.util.spec_from_file_location(MODULE_NAME, SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise ImportError(f"No se pudo cargar {SCRIPT_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[MODULE_NAME] = MODULE
SPEC.loader.exec_module(MODULE)


class YoutubeExtractorContractTests(unittest.TestCase):
    def test_extraction_filters_projects_and_deduplicates(self):
        original_search = MODULE.search_videos_by_query
        original_details = MODULE.get_video_details
        original_comments = MODULE.get_video_comments
        original_sleep = MODULE.time.sleep
        try:
            MODULE.search_videos_by_query = lambda *_args, **_kwargs: ["video-1"]
            MODULE.get_video_details = lambda *_args, **_kwargs: {
                "video-1": {
                    "title": "Video",
                    "channel_title": "Canal",
                    "published_at": "2026-04-08T10:00:00Z",
                }
            }

            def fake_comments(_youtube, video_id, query, **_kwargs):
                return [
                    {
                        "video_id": video_id,
                        "comment_id": "comment-1",
                        "comment_text": "Comentario repetido",
                        "published_at": "2026-04-10T12:00:00Z",
                        "query": query,
                    },
                    {
                        "video_id": video_id,
                        "comment_id": "comment-after",
                        "comment_text": "Comentario posterior",
                        "published_at": "2026-04-13T00:00:00Z",
                        "query": query,
                    },
                ]

            MODULE.get_video_comments = fake_comments
            MODULE.time.sleep = lambda *_args, **_kwargs: None

            dataframe, total_videos = MODULE.extraer_comentarios_busquedas(
                object(),
                queries=["Gobierno de Tampico", "gobierno de Tampico"],
                start_date=datetime(2026, 4, 6),
                end_date=datetime(2026, 4, 12, 23, 59, 59),
            )
        finally:
            MODULE.search_videos_by_query = original_search
            MODULE.get_video_details = original_details
            MODULE.get_video_comments = original_comments
            MODULE.time.sleep = original_sleep

        self.assertEqual(total_videos, 2)
        self.assertEqual(list(dataframe.columns), ["comment_text", "published_at", "query"])
        self.assertEqual(len(dataframe), 1)
        self.assertEqual(dataframe.iloc[0]["comment_text"], "Comentario repetido")
        self.assertEqual(dataframe.iloc[0]["query"], "Gobierno de Tampico")


if __name__ == "__main__":
    unittest.main()
