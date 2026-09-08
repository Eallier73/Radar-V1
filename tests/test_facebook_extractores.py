from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str, filename: str):
    path = REPO_ROOT / "scr" / "extraccion" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"No se pudo cargar {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


POSTS = load_script("radar_test_facebook_posts", "4_extractors_facebook_posts.py")
COMMENTS = load_script("radar_test_facebook_comments", "5_extractors_facebook_comentarios.py")


class FakeActor:
    def __init__(self, owner):
        self.owner = owner

    def call(self, *, run_input):
        self.owner.run_input = run_input
        return {"status": "SUCCEEDED", "usageTotalUsd": 0, "defaultDatasetId": "dataset"}


class FakeDataset:
    def iterate_items(self):
        return iter([])


class FakeClient:
    def __init__(self):
        self.run_input = None

    def actor(self, _name):
        return FakeActor(self)

    def dataset(self, _dataset_id):
        return FakeDataset()


class FacebookExtractorTests(unittest.TestCase):
    def test_only_the_two_historical_base_accounts_are_defaults(self) -> None:
        self.assertEqual(set(POSTS.DEFAULT_PAGES), {"TampicoGob", "monicavtampico"})
        self.assertEqual(set(COMMENTS.DEFAULT_PAGES), {"TampicoGob", "monicavtampico"})

    def test_comments_actor_uses_current_input_contract(self) -> None:
        client = FakeClient()
        COMMENTS.obtener_comentarios_batch(
            client,
            ["https://www.facebook.com/TampicoGob/posts/1"],
            200,
            "2026-03-09",
        )
        self.assertEqual(client.run_input["resultsLimit"], 200)
        self.assertTrue(client.run_input["includeNestedComments"])
        self.assertEqual(client.run_input["viewOption"], "RECENT_ACTIVITY")
        self.assertEqual(client.run_input["onlyCommentsNewerThan"], "2026-03-09")
        self.assertNotIn("resultsPerPost", client.run_input)
        self.assertNotIn("includeReplies", client.run_input)

    def test_equal_text_from_different_comments_is_not_collapsed(self) -> None:
        rows = COMMENTS.procesar_items_comentarios(
            [
                {
                    "id": "comment-1",
                    "facebookUrl": "https://www.facebook.com/TampicoGob/posts/1",
                    "text": "Excelente trabajo",
                    "profileName": "Persona Uno",
                    "date": "2026-03-10T10:00:00Z",
                },
                {
                    "id": "comment-2",
                    "facebookUrl": "https://www.facebook.com/TampicoGob/posts/1",
                    "text": "Excelente trabajo",
                    "profileName": "Persona Dos",
                    "date": "2026-03-10T10:01:00Z",
                },
            ]
        )
        self.assertEqual(len(rows), 2)

    def test_post_url_does_not_collapse_distinct_comment_ids(self) -> None:
        post_url = "https://www.facebook.com/TampicoGob/posts/1"
        rows = COMMENTS.procesar_items_comentarios(
            [
                {
                    "id": "comment-1",
                    "url": post_url,
                    "postUrl": post_url,
                    "text": "Primer comentario",
                    "profileName": "Persona Uno",
                    "date": "2026-03-10T10:00:00Z",
                },
                {
                    "id": "comment-2",
                    "url": post_url,
                    "postUrl": post_url,
                    "text": "Segundo comentario",
                    "profileName": "Persona Dos",
                    "date": "2026-03-10T10:01:00Z",
                },
            ],
            since="2026-03-09",
            before="2026-03-15",
        )
        self.assertEqual([row["comentario_id"] for row in rows], ["comment-1", "comment-2"])
        self.assertEqual([row["url_comentario"] for row in rows], ["", ""])

    def test_comments_are_limited_to_the_requested_week(self) -> None:
        base = {
            "facebookUrl": "https://www.facebook.com/TampicoGob/posts/1",
            "text": "Comentario válido",
            "profileName": "Persona",
        }
        rows = COMMENTS.procesar_items_comentarios(
            [
                {**base, "id": "inside", "date": "2026-03-15T23:59:59Z"},
                {**base, "id": "after", "date": "2026-03-16T00:00:00Z"},
                {**base, "id": "unknown", "date": "4h"},
            ],
            since="2026-03-09",
            before="2026-03-15",
        )
        self.assertEqual([row["comentario_id"] for row in rows], ["inside"])

    def test_reel_keeps_the_page_from_actor_input(self) -> None:
        row = POSTS.normalize_post_item(
            {
                "url": "https://www.facebook.com/reel/123/",
                "inputUrl": "https://www.facebook.com/monicavtampico",
                "text": "Mensaje",
                "date": "2026-03-10T10:00:00Z",
            }
        )
        self.assertEqual(row["page_handle"], "monicavtampico")

    def test_combined_csv_carries_account_to_comments(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            posts_path = Path(temp_dir) / "posts.csv"
            pd.DataFrame(
                [
                    {
                        "post_url": "https://www.facebook.com/TampicoGob/posts/1",
                        "page_url": "https://www.facebook.com/TampicoGob",
                        "page_handle": "tampicogob",
                        "fecha_post": "2026-03-10T10:00:00Z",
                        "post_texto": "Post",
                        "num_comentarios_post": 1,
                    }
                ]
            ).to_csv(posts_path, index=False, encoding="utf-8-sig")
            combined = COMMENTS.construir_facebook_canonico(
                str(posts_path),
                pd.DataFrame(
                    [
                        {
                            "post_url": "https://www.facebook.com/TampicoGob/posts/1",
                            "comentario_texto": "Comentario",
                            "fecha_comentario": "2026-03-10T11:00:00Z",
                            "url_comentario": "https://www.facebook.com/comment/1",
                        }
                    ]
                ),
            )
        self.assertEqual(list(combined["cuenta"]), ["tampicogob", "tampicogob"])


if __name__ == "__main__":
    unittest.main()
