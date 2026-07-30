from __future__ import annotations

import csv
import importlib.util
import json
from datetime import date
from pathlib import Path
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT
    / "scr"
    / "extraccion"
    / "6_extractors_facebook_chucho_nader_comentarios.py"
)
SPEC = importlib.util.spec_from_file_location("chucho_comments", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
extractor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = extractor
SPEC.loader.exec_module(extractor)


class FakeDataset:
    def __init__(self, items):
        self.items = items

    def iterate_items(self):
        return iter(self.items)


class FakeActor:
    def __init__(self, client, actor_id):
        self.client = client
        self.actor_id = actor_id

    def call(self, run_input):
        self.client.calls.append((self.actor_id, run_input))
        response = self.client.responses[self.actor_id].pop(0)
        if isinstance(response, Exception):
            raise response
        run, items = response
        self.client.datasets[run["defaultDatasetId"]] = items
        return run


class FakeClient:
    def __init__(self, responses):
        self.responses = {key: list(value) for key, value in responses.items()}
        self.datasets = {}
        self.calls = []

    def actor(self, actor_id):
        return FakeActor(self, actor_id)

    def dataset(self, dataset_id):
        return FakeDataset(self.datasets[dataset_id])


def successful_run(run_id, dataset_id):
    return {
        "id": run_id,
        "status": "SUCCEEDED",
        "defaultDatasetId": dataset_id,
        "usageTotalUsd": 0.01,
    }


class WeekUtilitiesTest(unittest.TestCase):
    def test_default_range_uses_only_complete_weeks(self):
        self.assertEqual(
            extractor.last_completed_sunday(date(2026, 7, 30)),
            date(2026, 7, 26),
        )
        weeks = list(
            extractor.iter_complete_weeks(
                date(2024, 9, 30),
                date(2024, 10, 13),
            )
        )
        self.assertEqual(
            [(week.start, week.end) for week in weeks],
            [
                (date(2024, 9, 30), date(2024, 10, 6)),
                (date(2024, 10, 7), date(2024, 10, 13)),
            ],
        )

    def test_current_apify_input_names_are_used(self):
        week = extractor.WeekWindow(date(2024, 9, 30), date(2024, 10, 6))
        client = FakeClient(
            {
                extractor.ACTOR_COMMENTS: [
                    (
                        successful_run("comment-run", "comment-dataset"),
                        [],
                    )
                ]
            }
        )
        rows, _ = extractor.download_comment_batch(
            client,
            ["https://www.facebook.com/ChuchoNader/posts/123"],
            week,
            None,
        )
        self.assertEqual(rows, [])
        _, run_input = client.calls[0]
        self.assertTrue(run_input["includeNestedComments"])
        self.assertEqual(run_input["viewOption"], "RECENT_ACTIVITY")
        self.assertNotIn("resultsLimit", run_input)
        self.assertNotIn("onlyCommentsNewerThan", run_input)
        self.assertNotIn("includeReplies", run_input)
        self.assertNotIn("resultsPerPost", run_input)

    def test_post_discovery_uses_exact_week_and_target(self):
        week = extractor.WeekWindow(date(2024, 9, 30), date(2024, 10, 6))
        post_url = "https://www.facebook.com/ChuchoNader/posts/123"
        client = FakeClient(
            {
                extractor.ACTOR_POSTS: [
                    (
                        successful_run("post-run", "post-dataset"),
                        [
                            {
                                "facebookUrl": extractor.TARGET_PAGE_URL,
                                "url": post_url,
                                "time": "2024-10-06T23:00:00Z",
                            }
                        ],
                    )
                ]
            }
        )
        urls, _ = extractor.discover_posts(client, week, 500)
        self.assertEqual(urls, [post_url])
        _, run_input = client.calls[0]
        self.assertEqual(
            run_input["startUrls"],
            [{"url": "https://www.facebook.com/ChuchoNader/"}],
        )
        self.assertEqual(run_input["onlyPostsNewerThan"], "2024-09-30")
        self.assertEqual(run_input["onlyPostsOlderThan"], "2024-10-07")

    def test_post_limit_stops_instead_of_confirming_truncated_week(self):
        week = extractor.WeekWindow(date(2024, 9, 30), date(2024, 10, 6))
        client = FakeClient(
            {
                extractor.ACTOR_POSTS: [
                    (
                        successful_run("post-run", "post-dataset"),
                        [
                            {
                                "facebookUrl": extractor.TARGET_PAGE_URL,
                                "url": "https://www.facebook.com/ChuchoNader/posts/123",
                                "time": "2024-10-01T10:00:00Z",
                            }
                        ],
                    )
                ]
            }
        )
        with self.assertRaisesRegex(extractor.ExtractionStopped, "aumenta el límite"):
            extractor.discover_posts(client, week, 1)


class ResumeTest(unittest.TestCase):
    def test_resume_starts_at_first_unconfirmed_batch(self):
        week = extractor.WeekWindow(date(2024, 9, 30), date(2024, 10, 6))
        post_one = "https://www.facebook.com/ChuchoNader/posts/111"
        post_two = "https://www.facebook.com/ChuchoNader/posts/222"
        post_items = [
            {
                "facebookUrl": extractor.TARGET_PAGE_URL,
                "url": post_one,
                "time": "2024-10-01T10:00:00Z",
            },
            {
                "facebookUrl": extractor.TARGET_PAGE_URL,
                "url": post_two,
                "time": "2024-10-02T10:00:00Z",
            },
        ]
        comment_one = {
            "facebookUrl": post_one,
            "commentId": "c1",
            "date": "2024-10-01T11:00:00Z",
            "text": "Primer comentario",
            "profileName": "Persona Uno",
        }
        comment_two = {
            "facebookUrl": post_two,
            "commentId": "c2",
            "date": "2024-10-02T11:00:00Z",
            "text": "Segundo comentario",
            "profileName": "Persona Dos",
        }

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_base = root / "datos"
            state_dir = root / "state"
            checkpoint_path = state_dir / "checkpoint.json"
            event_log_path = state_dir / "eventos.jsonl"
            checkpoint = extractor.load_checkpoint(checkpoint_path)

            first_client = FakeClient(
                {
                    extractor.ACTOR_POSTS: [
                        (successful_run("posts-run", "posts-dataset"), post_items)
                    ],
                    extractor.ACTOR_COMMENTS: [
                        (
                            successful_run("comments-run-1", "comments-dataset-1"),
                            [comment_one],
                        ),
                        RuntimeError("sin crédito"),
                    ],
                }
            )

            with self.assertRaises(extractor.ExtractionStopped):
                extractor.process_week(
                    first_client,
                    week,
                    output_base=output_base,
                    state_dir=state_dir,
                    checkpoint_path=checkpoint_path,
                    event_log_path=event_log_path,
                    checkpoint=checkpoint,
                    max_posts=500,
                    max_comments=None,
                    batch_size=1,
                )

            saved = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["current_week"]["next_comment_batch"], 1)
            self.assertTrue(
                (
                    state_dir
                    / "work"
                    / "2024-09-30"
                    / "comments_batch_00000.json"
                ).is_file()
            )
            self.assertFalse(extractor.weekly_csv_path(output_base, week).exists())

            second_client = FakeClient(
                {
                    extractor.ACTOR_COMMENTS: [
                        (
                            successful_run("comments-run-2", "comments-dataset-2"),
                            [comment_two],
                        )
                    ]
                }
            )
            comments, posts = extractor.process_week(
                second_client,
                week,
                output_base=output_base,
                state_dir=state_dir,
                checkpoint_path=checkpoint_path,
                event_log_path=event_log_path,
                checkpoint=saved,
                max_posts=500,
                max_comments=None,
                batch_size=1,
            )

            self.assertEqual((comments, posts), (2, 2))
            self.assertEqual(
                [actor for actor, _ in second_client.calls],
                [extractor.ACTOR_COMMENTS],
            )

            output_path = extractor.weekly_csv_path(output_base, week)
            self.assertTrue(extractor.output_is_complete(output_path))
            with output_path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([row["comment_id"] for row in rows], ["c1", "c2"])
            self.assertTrue(all(row["pagina"] == "Chucho Nader" for row in rows))
            self.assertTrue(all(row["comentario_texto"] for row in rows))
            self.assertNotIn("post_texto", rows[0])

            completed = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            self.assertEqual(completed["last_successful_week"], "2024-10-06")
            self.assertIsNone(completed["current_week"])


if __name__ == "__main__":
    unittest.main()
