from __future__ import annotations

import csv
import ast
import importlib.util
import json
from datetime import date
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT
    / "scr"
    / "extraccion"
    / "7_extractors_medios_chucho_nader.py"
)
SPEC = importlib.util.spec_from_file_location("medios_chucho_nader", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
extractor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = extractor
SPEC.loader.exec_module(extractor)


class FakeBackend:
    def __init__(self, search_responses, enriched_by_url=None):
        self.search_responses = list(search_responses)
        self.enriched_by_url = enriched_by_url or {}
        self.search_calls = []
        self.enrich_calls = []

    def search(self, query, week):
        self.search_calls.append((query, week))
        response = self.search_responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def enrich(self, article):
        self.enrich_calls.append(article["url_google"])
        enriched = dict(article)
        enriched.update(self.enriched_by_url[article["url_google"]])
        return enriched


def raw_article(title, google_url, iso_date="2024-10-01T12:00:00+00:00"):
    return {
        "titulo": title,
        "url_google": google_url,
        "url": "",
        "fecha": iso_date[:10],
        "iso_date": iso_date,
        "fuente": "Fuente de prueba",
        "autor": "",
        "thumbnail": "",
        "texto": "",
        "descripcion": "",
        "origen": "GOOGLE_NEWS_RSS",
    }


class IdentityFilterTest(unittest.TestCase):
    def test_accepts_explicit_target_identity(self):
        decision = extractor.classify_nader_identity(
            {"titulo": "Chucho Nader presenta iniciativa", "texto": ""}
        )
        self.assertTrue(decision.accepted)
        self.assertEqual(decision.identity, extractor.TARGET_NAME)
        self.assertEqual(decision.reason, "identidad_objetivo_explicita")

    def test_accepts_ambiguous_name_only_with_tampico_context(self):
        decision = extractor.classify_nader_identity(
            {
                "titulo": "Jesús Nader anuncia nuevas acciones",
                "texto": "El diputado por Tamaulipas habló en Tampico.",
            }
        )
        self.assertTrue(decision.accepted)
        self.assertIn("contexto_local", decision.reason)

    def test_rejects_hotelier_from_nuevo_leon(self):
        decision = extractor.classify_nader_identity(
            {
                "titulo": "Reconocen a Jesús Nader Marcos",
                "texto": (
                    "El presidente de la Asociación de Hoteles de Nuevo León "
                    "recibió el premio en Monterrey."
                ),
            }
        )
        self.assertFalse(decision.accepted)
        self.assertEqual(decision.identity, extractor.OTHER_PERSON)
        self.assertEqual(decision.reason, "homonimo_nader_marcos")

    def test_rejects_ambiguous_nader_without_local_context(self):
        decision = extractor.classify_nader_identity(
            {"titulo": "Nader participa en una reunión", "texto": ""}
        )
        self.assertFalse(decision.accepted)
        self.assertEqual(decision.reason, "nader_ambiguo_sin_contexto_tampico")


class QueryAndWeekTest(unittest.TestCase):
    def test_queries_use_exact_same_media_sites(self):
        specs = extractor.build_query_specs()
        self.assertEqual(
            {spec.site for spec in specs},
            {"site:oem.com.mx", "site:milenio.com"},
        )
        self.assertEqual(len(specs), 8)
        ambiguous = [spec.query for spec in specs if spec.term == extractor.AMBIGUOUS_QUERY]
        self.assertEqual(len(ambiguous), 2)
        self.assertTrue(all('-"Nader Marcos"' in query for query in ambiguous))
        self.assertTrue(all("-hotelero" in query for query in ambiguous))
        self.assertTrue(all('-"Nuevo León"' in query for query in ambiguous))

    def test_media_sites_stay_in_sync_with_general_extractor(self):
        general_path = (
            REPO_ROOT / "scr" / "extraccion" / "3_extractors_medios.py"
        )
        tree = ast.parse(general_path.read_text(encoding="utf-8"))
        general_media = None
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            if any(
                isinstance(target, ast.Name) and target.id == "MEDIOS"
                for target in node.targets
            ):
                general_media = ast.literal_eval(node.value)
                break
        self.assertIsNotNone(general_media)
        self.assertEqual(tuple(general_media), extractor.MEDIA_SITES)

    def test_default_range_uses_complete_weeks(self):
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
        self.assertEqual(len(weeks), 2)
        self.assertEqual(weeks[0].start, date(2024, 9, 30))
        self.assertEqual(weeks[-1].end, date(2024, 10, 13))

    def test_invalid_rss_response_stops_instead_of_confirming_empty_query(self):
        class FakeRequests:
            @staticmethod
            def get(*args, **kwargs):
                return SimpleNamespace(
                    status_code=200,
                    text="<html><title>Access denied</title></html>",
                )

        fake_media = SimpleNamespace(
            PAUSA=0,
            USER_AGENTS=["test-agent"],
            RSS_TIMEOUT=1,
            requests=FakeRequests(),
            verificar_dependencias_ejecucion=lambda: None,
            construir_url_rss=lambda query, start, end: "https://example.test/rss",
            parsear_rss=lambda text: [],
        )
        backend = extractor.MediaBackend(
            fake_media,
            rss_retries=1,
            rss_backoff=0,
            article_pause=0,
        )
        week = extractor.WeekWindow(date(2024, 9, 30), date(2024, 10, 6))
        with self.assertRaisesRegex(extractor.ExtractionStopped, "no es un RSS válido"):
            backend.search('"Chucho Nader" site:oem.com.mx', week)


class ResumeTest(unittest.TestCase):
    def test_resume_skips_confirmed_query_and_outputs_only_target(self):
        week = extractor.WeekWindow(date(2024, 9, 30), date(2024, 10, 6))
        query_specs = [
            extractor.QuerySpec(
                "site:oem.com.mx",
                '"Chucho Nader"',
                '"Chucho Nader" site:oem.com.mx',
            ),
            extractor.QuerySpec(
                "site:milenio.com",
                '"Jesús Nader"',
                '"Jesús Nader" site:milenio.com',
            ),
        ]
        target_google = "https://news.google.com/rss/articles/target"
        other_google = "https://news.google.com/rss/articles/other"
        target = raw_article("Chucho Nader presenta iniciativa", target_google)
        other = raw_article("Premian a Jesús Nader Marcos", other_google)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_base = root / "datos"
            state_dir = root / "state"
            checkpoint_path = state_dir / "checkpoint.json"
            event_log_path = state_dir / "eventos.jsonl"
            checkpoint = extractor.load_checkpoint(checkpoint_path)

            first_backend = FakeBackend(
                [
                    [target],
                    extractor.ExtractionStopped("Google News bloqueado"),
                ]
            )
            with self.assertRaises(extractor.ExtractionStopped):
                extractor.process_week(
                    first_backend,
                    week,
                    output_base=output_base,
                    state_dir=state_dir,
                    checkpoint_path=checkpoint_path,
                    event_log_path=event_log_path,
                    checkpoint=checkpoint,
                    query_specs=query_specs,
                    query_pause=0,
                )

            saved = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["current_week"]["next_query"], 1)
            self.assertFalse(extractor.weekly_csv_path(output_base, week).exists())

            second_backend = FakeBackend(
                [[other]],
                {
                    target_google: {
                        "url": "https://oem.com.mx/elsoldetampico/local/target",
                        "texto": "Jesús Antonio Nader Nasrallah, diputado por Tamaulipas.",
                        "estado_url": "resuelta",
                        "estado_texto": "descargado",
                    },
                    other_google: {
                        "url": "https://www.milenio.com/negocios/hoteles-nuevo-leon",
                        "texto": (
                            "Jesús Nader Marcos, dirigente de los hoteleros "
                            "de Nuevo León."
                        ),
                        "estado_url": "resuelta",
                        "estado_texto": "descargado",
                    },
                },
            )
            accepted, rejected, candidates = extractor.process_week(
                second_backend,
                week,
                output_base=output_base,
                state_dir=state_dir,
                checkpoint_path=checkpoint_path,
                event_log_path=event_log_path,
                checkpoint=saved,
                query_specs=query_specs,
                query_pause=0,
            )

            self.assertEqual((accepted, rejected, candidates), (1, 1, 2))
            self.assertEqual(
                [query for query, _ in second_backend.search_calls],
                ['"Jesús Nader" site:milenio.com'],
            )
            self.assertEqual(
                second_backend.enrich_calls,
                [target_google, other_google],
            )

            output_path = extractor.weekly_csv_path(output_base, week)
            self.assertTrue(extractor.output_is_complete(output_path))
            with output_path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["identidad_nader"], extractor.TARGET_NAME)
            self.assertEqual(
                rows[0]["titulo"],
                "Chucho Nader presenta iniciativa",
            )
            self.assertFalse((state_dir / "work" / "2024-09-30").exists())

            completed = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            self.assertEqual(completed["last_successful_week"], "2024-10-06")
            self.assertIsNone(completed["current_week"])


if __name__ == "__main__":
    unittest.main()
