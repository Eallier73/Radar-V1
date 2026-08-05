#!/usr/bin/env python3
"""Backfill semanal reanudable de noticias sobre Chucho Nader.

Conserva las mismas fuentes del extractor general de medios de Radar:
``site:oem.com.mx`` y ``site:milenio.com``. Las consultas y el filtro local
distinguen a Jesús Antonio Nader Nasrallah, de Tampico, del hotelero
regiomontano Jesús F. Nader Marcos.

Los resultados RSS y cada artículo procesado se confirman por separado en
``state/medios_chucho_nader``. Una interrupción reanuda desde la primera
consulta o artículo pendiente. El único artefacto semanal permanente es el CSV
``*_medios_chucho_nader.csv`` dentro de ``datos/radar_semanal_extraido``.
"""

from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import importlib.util
import json
import os
import random
import re
import shutil
import sys
import time
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_DIR = REPO_ROOT / "scr" / "compartido"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from output_naming import build_source_filename, build_week_folder_name
from radar_paths import EXTRACTED_DATA_DIR, STATE_DIR


TARGET_NAME = "Jesús Antonio Nader Nasrallah"
OTHER_PERSON = "Jesús F. Nader Marcos"

# Deben mantenerse iguales a MEDIOS en 3_extractors_medios.py.
MEDIA_SITES = (
    "site:oem.com.mx",
    "site:milenio.com",
)

STRONG_QUERY_TERMS = (
    '"Chucho Nader"',
    '"Nader Nasrallah"',
    '"Jesús Antonio Nader"',
)
AMBIGUOUS_QUERY = (
    '("Jesús Nader" OR "Jesus Nader") '
    '(Tampico OR Tamaulipas OR "Ciudad Madero" OR "Jaiba Brava") '
    '-"Nader Marcos" -"Jesús F. Nader" -hotelero -hoteles '
    '-Monterrey -"Nuevo León"'
)

DEFAULT_START_DATE = date(2024, 9, 30)
DEFAULT_STATE_DIR = STATE_DIR / "medios_chucho_nader"
DEFAULT_RSS_RETRIES = 3
DEFAULT_RSS_BACKOFF = 5.0
DEFAULT_QUERY_PAUSE = 3.0
DEFAULT_ARTICLE_PAUSE = 2.0

OUTPUT_SOURCE = "medios_chucho_nader"
CHECKPOINT_VERSION = 1
FILTER_VERSION = 1

ALLOWED_DOMAINS = (
    "oem.com.mx",
    "milenio.com",
)

CSV_COLUMNS = [
    "titulo",
    "fecha",
    "iso_date",
    "fuente",
    "autor",
    "url",
    "url_google",
    "thumbnail",
    "descripcion",
    "texto",
    "origen",
    "medio_consultado",
    "query_origen",
    "identidad_nader",
    "razon_inclusion",
    "semana_inicio",
    "semana_fin",
    "estado_url",
    "estado_texto",
]

TARGET_STRONG_PATTERNS = (
    "chucho nader",
    "jesus nader nasrallah",
    "jesus nader nasrrallah",
    "jesus antonio nader",
    "nader nasrallah",
    "nader nasrrallah",
)
OTHER_PERSON_PATTERNS = (
    "jesus nader marcos",
    "jesus f nader marcos",
    "jesus francisco nader marcos",
    "nader marcos",
)
TARGET_LOCAL_CONTEXT = (
    "tampico",
    "tamaulipas",
    "ciudad madero",
    "zona conurbada",
    "sur de tamaulipas",
    "distrito 8",
    "distrito viii",
    "jaiba brava",
    "puerto jaibo",
    "alcalde de tampico",
    "presidente municipal de tampico",
    "diputado por tamaulipas",
    "diputado federal por tamaulipas",
)
OTHER_PERSON_CONTEXT = (
    "monterrey",
    "nuevo leon",
    "hotelero",
    "hoteleros",
    "hoteles",
    "sector hotelero",
    "asociacion mexicana de hoteles",
    "asociacion de hoteles de nuevo leon",
    "industria hotelera",
    "hotel jolet",
    "turismo de nuevo leon",
    "fipetur",
)


class ExtractionStopped(RuntimeError):
    """Falla operativa que no debe adelantar el checkpoint."""


@dataclass(frozen=True)
class WeekWindow:
    start: date
    end: date

    @property
    def next_start(self) -> date:
        return self.end + timedelta(days=1)

    @property
    def name(self) -> str:
        return build_week_folder_name(self.start, self.end)


@dataclass(frozen=True)
class QuerySpec:
    site: str
    term: str
    query: str


@dataclass(frozen=True)
class IdentityDecision:
    accepted: bool
    identity: str
    reason: str


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Fecha inválida '{value}'. Usa YYYY-MM-DD."
        ) from exc


def last_completed_sunday(today: Optional[date] = None) -> date:
    current = today or date.today()
    current_monday = current - timedelta(days=current.weekday())
    return current_monday - timedelta(days=1)


def align_to_monday(value: date) -> date:
    return value - timedelta(days=value.weekday())


def iter_complete_weeks(start: date, end: date) -> Iterable[WeekWindow]:
    week_start = align_to_monday(start)
    while week_start + timedelta(days=6) <= end:
        yield WeekWindow(week_start, week_start + timedelta(days=6))
        week_start += timedelta(days=7)


def build_query_specs() -> list[QuerySpec]:
    specs: list[QuerySpec] = []
    for site in MEDIA_SITES:
        for term in (*STRONG_QUERY_TERMS, AMBIGUOUS_QUERY):
            specs.append(QuerySpec(site=site, term=term, query=f"{term} {site}"))
    return specs


def normalize_for_match(value: Any) -> str:
    text = str(value or "").lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(
        char for char in text if unicodedata.category(char) != "Mn"
    )
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def article_search_text(article: dict[str, Any]) -> str:
    return normalize_for_match(
        " ".join(
            str(article.get(field) or "")
            for field in ("titulo", "descripcion", "texto", "fuente", "url")
        )
    )


def classify_nader_identity(article: dict[str, Any]) -> IdentityDecision:
    text = article_search_text(article)
    if any(pattern in text for pattern in TARGET_STRONG_PATTERNS):
        return IdentityDecision(
            True,
            TARGET_NAME,
            "identidad_objetivo_explicita",
        )

    if any(pattern in text for pattern in OTHER_PERSON_PATTERNS):
        return IdentityDecision(
            False,
            OTHER_PERSON,
            "homonimo_nader_marcos",
        )

    if not re.search(r"\bnader\b", text):
        return IdentityDecision(False, "", "sin_mencion_nader")

    local_hits = [token for token in TARGET_LOCAL_CONTEXT if token in text]
    other_hits = [token for token in OTHER_PERSON_CONTEXT if token in text]

    if local_hits:
        return IdentityDecision(
            True,
            TARGET_NAME,
            f"nader_mas_contexto_local:{','.join(local_hits[:3])}",
        )

    if len(other_hits) >= 1:
        return IdentityDecision(
            False,
            OTHER_PERSON,
            f"contexto_hotelero_nuevo_leon:{','.join(other_hits[:3])}",
        )

    return IdentityDecision(False, "", "nader_ambiguo_sin_contexto_tampico")


def allowed_article_url(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower().split(":", 1)[0]
    except Exception:
        return False
    return any(host == domain or host.endswith(f".{domain}") for domain in ALLOWED_DOMAINS)


def weekly_csv_path(output_base: Path, week: WeekWindow) -> Path:
    filename = f"{build_source_filename(week.name, OUTPUT_SOURCE)}.csv"
    return output_base / week.name / filename


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(
            payload,
            handle,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=_json_default,
        )
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def append_event(log_path: Path, event: str, **details: Any) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"timestamp": utc_now_iso(), "event": event, **details}
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, default=_json_default))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def load_checkpoint(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "version": CHECKPOINT_VERSION,
            "target": TARGET_NAME,
            "last_successful_week": None,
            "current_week": None,
            "updated_at": utc_now_iso(),
        }
    payload = read_json(path)
    if payload.get("version") != CHECKPOINT_VERSION:
        raise ExtractionStopped(
            f"Checkpoint incompatible en {path}; no se modificó."
        )
    if payload.get("target") != TARGET_NAME:
        raise ExtractionStopped(f"El checkpoint {path} pertenece a otro objetivo.")
    return payload


def save_checkpoint(path: Path, checkpoint: dict[str, Any]) -> None:
    checkpoint["updated_at"] = utc_now_iso()
    atomic_write_json(path, checkpoint)


def output_is_complete(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            header = next(csv.reader(handle))
    except (OSError, StopIteration, UnicodeError, csv.Error):
        return False
    return header == CSV_COLUMNS


def write_weekly_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def load_base_media_module() -> Any:
    module_path = REPO_ROOT / "scr" / "extraccion" / "3_extractors_medios.py"
    spec = importlib.util.spec_from_file_location("radar_base_media", module_path)
    if spec is None or spec.loader is None:
        raise ExtractionStopped(f"No se pudo cargar {module_path}.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class MediaBackend:
    """Adaptador estricto sobre la lógica probada del extractor general."""

    def __init__(
        self,
        media_module: Any,
        *,
        rss_retries: int,
        rss_backoff: float,
        article_pause: float,
    ):
        self.media = media_module
        self.rss_retries = rss_retries
        self.rss_backoff = rss_backoff
        self.media.PAUSA = article_pause
        self.media.verificar_dependencias_ejecucion()

    def search(self, query: str, week: WeekWindow) -> list[dict[str, Any]]:
        url = self.media.construir_url_rss(
            query,
            week.start.isoformat(),
            week.next_start.isoformat(),
        )
        wait_seconds = self.rss_backoff
        last_error: Optional[Exception] = None

        for attempt in range(1, self.rss_retries + 1):
            try:
                headers = {
                    "User-Agent": random.choice(self.media.USER_AGENTS),
                    "Accept": "application/rss+xml, application/xml, text/xml, */*",
                    "Accept-Language": "es-MX,es;q=0.9",
                }
                response = self.media.requests.get(
                    url,
                    headers=headers,
                    timeout=self.media.RSS_TIMEOUT,
                )
                if response.status_code == 429:
                    raise RuntimeError("Google News devolvió 429")
                if response.status_code != 200:
                    raise RuntimeError(f"Google News devolvió HTTP {response.status_code}")
                xml_preview = response.text[:1000].lower()
                if "<rss" not in xml_preview or "<channel" not in response.text.lower():
                    raise RuntimeError(
                        "Google News respondió contenido que no es un RSS válido"
                    )
                return self.media.parsear_rss(response.text)
            except Exception as exc:
                last_error = exc
                if attempt >= self.rss_retries:
                    break
                pause = min(wait_seconds, 60.0)
                time.sleep(pause)
                wait_seconds = min(max(wait_seconds * 2, 0.1), 60.0)

        raise ExtractionStopped(
            f"Falló la consulta RSS después de {self.rss_retries} intentos: "
            f"{last_error}"
        )

    def enrich(self, article: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(article)
        google_url = str(enriched.get("url_google") or "")
        real_url = self.media.resolver_url_google_news(google_url)
        enriched["url"] = real_url
        enriched["estado_url"] = (
            "resuelta"
            if real_url and "news.google.com" not in real_url
            else "sin_resolver"
        )

        if enriched["estado_url"] == "resuelta":
            processed = self.media.descargar_textos([enriched])
            if processed:
                enriched = processed[0]
        enriched["estado_texto"] = (
            "descargado" if str(enriched.get("texto") or "").strip() else "sin_texto"
        )
        return enriched

    def close(self) -> None:
        self.media._cerrar_playwright()


def article_key(article: dict[str, Any]) -> str:
    raw = "|".join(
        str(article.get(field) or "")
        for field in ("url_google", "titulo", "iso_date", "fuente")
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def deduplicate_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for article in articles:
        key = str(article.get("url") or article.get("url_google") or "")
        if not key:
            key = article_key(article)
        if key in seen:
            continue
        seen.add(key)
        unique.append(article)
    return unique


def filter_article_date(article: dict[str, Any], week: WeekWindow) -> bool:
    raw = str(article.get("iso_date") or "").strip()
    if not raw:
        return True
    normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return True
    return week.start <= parsed.date() <= week.end


def _work_week_dir(state_dir: Path, week: WeekWindow) -> Path:
    return state_dir / "work" / week.start.isoformat()


def _query_path(state_dir: Path, week: WeekWindow, index: int) -> Path:
    return _work_week_dir(state_dir, week) / f"rss_{index:03d}.json"


def _article_path(state_dir: Path, week: WeekWindow, index: int) -> Path:
    return _work_week_dir(state_dir, week) / f"article_{index:05d}.json"


def _load_confirmed_query(
    path: Path,
    spec: QuerySpec,
) -> Optional[list[dict[str, Any]]]:
    if not path.is_file():
        return None
    try:
        payload = read_json(path)
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("query") != spec.query or payload.get("site") != spec.site:
        return None
    results = payload.get("results")
    return results if isinstance(results, list) else None


def _load_confirmed_article(
    path: Path,
    expected_key: str,
) -> Optional[dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        payload = read_json(path)
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("article_key") != expected_key:
        return None
    article = payload.get("article")
    return article if isinstance(article, dict) else None


def _collect_query_results(
    state_dir: Path,
    week: WeekWindow,
    query_specs: list[QuerySpec],
) -> list[dict[str, Any]]:
    all_results: list[dict[str, Any]] = []
    for index, spec in enumerate(query_specs):
        results = _load_confirmed_query(_query_path(state_dir, week, index), spec)
        if results is None:
            raise ExtractionStopped(
                f"Falta la consulta confirmada {_query_path(state_dir, week, index)}."
            )
        all_results.extend(results)
    return deduplicate_articles(
        [item for item in all_results if filter_article_date(item, week)]
    )


def _collect_processed_articles(
    state_dir: Path,
    week: WeekWindow,
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    processed: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        key = article_key(candidate)
        article = _load_confirmed_article(
            _article_path(state_dir, week, index),
            key,
        )
        if article is None:
            raise ExtractionStopped(
                f"Falta el artículo confirmado {_article_path(state_dir, week, index)}."
            )
        processed.append(article)
    return processed


def _fresh_current_week(
    week: WeekWindow,
    query_specs: list[QuerySpec],
) -> dict[str, Any]:
    query_fingerprint = hashlib.sha256(
        (
            f"filter_version={FILTER_VERSION}\n"
            + "\n".join(spec.query for spec in query_specs)
        ).encode("utf-8")
    ).hexdigest()
    return {
        "start": week.start.isoformat(),
        "end": week.end.isoformat(),
        "phase": "rss",
        "query_fingerprint": query_fingerprint,
        "next_query": 0,
        "next_article": 0,
        "candidate_count": None,
        "last_successful_step": None,
    }


def _query_fingerprint(query_specs: list[QuerySpec]) -> str:
    return hashlib.sha256(
        (
            f"filter_version={FILTER_VERSION}\n"
            + "\n".join(spec.query for spec in query_specs)
        ).encode("utf-8")
    ).hexdigest()


def process_week(
    backend: Any,
    week: WeekWindow,
    *,
    output_base: Path,
    state_dir: Path,
    checkpoint_path: Path,
    event_log_path: Path,
    checkpoint: dict[str, Any],
    query_specs: list[QuerySpec],
    query_pause: float,
) -> tuple[int, int, int]:
    output_path = weekly_csv_path(output_base, week)
    current = checkpoint.get("current_week")
    if (
        not isinstance(current, dict)
        or current.get("start") != week.start.isoformat()
        or current.get("end") != week.end.isoformat()
    ):
        current = _fresh_current_week(week, query_specs)
        checkpoint["current_week"] = current
        save_checkpoint(checkpoint_path, checkpoint)
        append_event(
            event_log_path,
            "week_started",
            week_start=week.start,
            week_end=week.end,
        )
    elif current.get("query_fingerprint") != _query_fingerprint(query_specs):
        raise ExtractionStopped(
            "Las queries cambiaron durante una semana parcial. "
            "Reanuda con la misma versión/configuración."
        )

    if current.get("phase") == "rss":
        next_query = int(current.get("next_query") or 0)
        for index in range(next_query, len(query_specs)):
            spec = query_specs[index]
            query_path = _query_path(state_dir, week, index)
            results = _load_confirmed_query(query_path, spec)
            resumed = results is not None
            if results is None:
                results = backend.search(spec.query, week)
                tagged_results = []
                for item in results:
                    tagged = dict(item)
                    tagged["medio_consultado"] = spec.site
                    tagged["query_origen"] = spec.query
                    tagged_results.append(tagged)
                results = tagged_results
                atomic_write_json(
                    query_path,
                    {
                        "query_index": index,
                        "site": spec.site,
                        "term": spec.term,
                        "query": spec.query,
                        "results": results,
                    },
                )

            current["next_query"] = index + 1
            current["last_successful_step"] = {
                "type": "rss_query",
                "timestamp": utc_now_iso(),
                "query_index": index,
                "results": len(results),
            }
            save_checkpoint(checkpoint_path, checkpoint)
            append_event(
                event_log_path,
                "rss_query_complete",
                week_start=week.start,
                query_index=index,
                query=spec.query,
                results=len(results),
                resumed=resumed,
            )
            if not resumed and index + 1 < len(query_specs) and query_pause > 0:
                time.sleep(query_pause)

        candidates = _collect_query_results(
            state_dir,
            week,
            query_specs,
        )
        candidates_path = _work_week_dir(state_dir, week) / "candidates.json"
        atomic_write_json(candidates_path, {"candidates": candidates})
        current.update(
            {
                "phase": "articles",
                "candidate_count": len(candidates),
                "next_article": 0,
                "last_successful_step": {
                    "type": "candidates_built",
                    "timestamp": utc_now_iso(),
                    "candidates": len(candidates),
                },
            }
        )
        save_checkpoint(checkpoint_path, checkpoint)
        append_event(
            event_log_path,
            "candidates_built",
            week_start=week.start,
            candidates=len(candidates),
        )
    else:
        candidates_path = _work_week_dir(state_dir, week) / "candidates.json"
        try:
            candidates_payload = read_json(candidates_path)
            candidates = candidates_payload["candidates"]
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ExtractionStopped(
                f"No se pudieron recuperar candidatos de {candidates_path}: {exc}"
            ) from exc

    next_article = int(current.get("next_article") or 0)
    for index in range(next_article, len(candidates)):
        candidate = candidates[index]
        key = article_key(candidate)
        article_path = _article_path(state_dir, week, index)
        article = _load_confirmed_article(article_path, key)
        resumed = article is not None
        if article is None:
            article = backend.enrich(candidate)
            decision = classify_nader_identity(article)
            article["identidad_nader"] = decision.identity
            article["razon_inclusion"] = decision.reason
            article["semana_inicio"] = week.start.isoformat()
            article["semana_fin"] = week.end.isoformat()
            article["aceptado_nader"] = decision.accepted
            if decision.accepted and not allowed_article_url(
                str(article.get("url") or "")
            ):
                article["aceptado_nader"] = False
                article["razon_inclusion"] = "url_fuera_de_oem_milenio"
            atomic_write_json(
                article_path,
                {
                    "article_index": index,
                    "article_key": key,
                    "article": article,
                },
            )

        current["next_article"] = index + 1
        current["last_successful_step"] = {
            "type": "article",
            "timestamp": utc_now_iso(),
            "article_index": index,
            "accepted": bool(article.get("aceptado_nader")),
        }
        save_checkpoint(checkpoint_path, checkpoint)
        append_event(
            event_log_path,
            "article_complete",
            week_start=week.start,
            article_index=index,
            accepted=bool(article.get("aceptado_nader")),
            reason=article.get("razon_inclusion"),
            resumed=resumed,
        )

    processed = _collect_processed_articles(
        state_dir,
        week,
        candidates,
    )
    accepted_before_dedup = [
        article for article in processed if article.get("aceptado_nader")
    ]
    accepted = deduplicate_articles(accepted_before_dedup)
    accepted.sort(
        key=lambda article: (
            str(article.get("iso_date") or ""),
            str(article.get("titulo") or ""),
        ),
        reverse=True,
    )
    write_weekly_csv(output_path, accepted)
    checkpoint["last_successful_week"] = week.end.isoformat()
    checkpoint["current_week"] = None
    save_checkpoint(checkpoint_path, checkpoint)

    work_dir = _work_week_dir(state_dir, week)
    try:
        shutil.rmtree(work_dir)
    except FileNotFoundError:
        pass
    except OSError as exc:
        append_event(
            event_log_path,
            "work_cleanup_failed",
            week_start=week.start,
            work_dir=str(work_dir),
            reason=str(exc),
        )

    rejected_count = sum(
        1 for article in processed if not article.get("aceptado_nader")
    )
    duplicate_count = len(accepted_before_dedup) - len(accepted)
    append_event(
        event_log_path,
        "week_complete",
        week_start=week.start,
        week_end=week.end,
        candidates=len(candidates),
        accepted=len(accepted),
        rejected=rejected_count,
        duplicates=duplicate_count,
        output=str(output_path),
    )
    return len(accepted), rejected_count, len(candidates)


class ProcessLock:
    """Evita dos procesos sobre el mismo estado."""

    def __init__(self, path: Path):
        self.path = path
        self.handle: Any = None

    def __enter__(self) -> "ProcessLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.handle.close()
            raise ExtractionStopped(
                f"Ya existe otra ejecución usando {self.path.parent}."
            ) from exc
        self.handle.seek(0)
        self.handle.truncate()
        self.handle.write(f"pid={os.getpid()} started={utc_now_iso()}\n")
        self.handle.flush()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self.handle is not None:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Descarga semanal reanudable de noticias de OEM y Milenio sobre "
            "Jesús Antonio Nader Nasrallah."
        )
    )
    parser.add_argument(
        "--since",
        type=parse_date,
        default=DEFAULT_START_DATE,
        help="Primera fecha del backfill (default: %(default)s).",
    )
    parser.add_argument(
        "--until",
        type=parse_date,
        default=None,
        help="Último domingo a procesar (default: último domingo completo).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=EXTRACTED_DATA_DIR,
        help="Raíz de datos crudos semanales (default: %(default)s).",
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=DEFAULT_STATE_DIR,
        help="Checkpoint y trabajo reanudable (default: %(default)s).",
    )
    parser.add_argument(
        "--max-weeks",
        type=int,
        default=None,
        help="Limita semanas pendientes en esta ejecución.",
    )
    parser.add_argument(
        "--rss-retries",
        type=int,
        default=DEFAULT_RSS_RETRIES,
        help="Reintentos por query RSS (default: %(default)s).",
    )
    parser.add_argument(
        "--rss-backoff",
        type=float,
        default=DEFAULT_RSS_BACKOFF,
        help="Espera inicial entre reintentos RSS (default: %(default)s).",
    )
    parser.add_argument(
        "--query-pause",
        type=float,
        default=DEFAULT_QUERY_PAUSE,
        help="Pausa entre queries nuevas (default: %(default)s).",
    )
    parser.add_argument(
        "--article-pause",
        type=float,
        default=DEFAULT_ARTICLE_PAUSE,
        help="Pausa entre descargas de artículos (default: %(default)s).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Muestra fuentes, queries y semanas sin hacer solicitudes.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Muestra el checkpoint sin hacer solicitudes.",
    )
    return parser


def _validate_positive(
    parser: argparse.ArgumentParser,
    value: Optional[float],
    label: str,
    *,
    allow_zero: bool = False,
) -> None:
    if value is None:
        return
    invalid = value < 0 if allow_zero else value <= 0
    if invalid:
        comparison = "mayor o igual que cero" if allow_zero else "mayor que cero"
        parser.error(f"{label} debe ser {comparison}.")


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _validate_positive(parser, args.max_weeks, "--max-weeks")
    _validate_positive(parser, args.rss_retries, "--rss-retries")
    _validate_positive(parser, args.rss_backoff, "--rss-backoff", allow_zero=True)
    _validate_positive(parser, args.query_pause, "--query-pause", allow_zero=True)
    _validate_positive(parser, args.article_pause, "--article-pause", allow_zero=True)

    requested_end = args.until or last_completed_sunday()
    if requested_end.weekday() != 6:
        parser.error("--until debe ser domingo para no confirmar una semana parcial.")
    if args.since > requested_end:
        parser.error("--since no puede ser posterior a --until.")

    output_base = args.output_dir.expanduser().resolve()
    state_dir = args.state_dir.expanduser().resolve()
    checkpoint_path = state_dir / "checkpoint.json"
    event_log_path = state_dir / "eventos.jsonl"
    query_specs = build_query_specs()

    if args.status:
        checkpoint = load_checkpoint(checkpoint_path)
        print(json.dumps(checkpoint, ensure_ascii=False, indent=2))
        print(f"Checkpoint: {checkpoint_path}")
        print(f"Eventos: {event_log_path}")
        return 0

    all_weeks = list(iter_complete_weeks(args.since, requested_end))
    pending = [
        week
        for week in all_weeks
        if not output_is_complete(weekly_csv_path(output_base, week))
    ]
    execution_weeks = (
        pending[: args.max_weeks] if args.max_weeks is not None else pending
    )

    print("=" * 72)
    print("MEDIOS — CHUCHO NADER")
    print("=" * 72)
    print(f"Objetivo: {TARGET_NAME}")
    print(f"Homónimo excluido: {OTHER_PERSON} (hotelería de Nuevo León)")
    print(f"Fuentes: {', '.join(MEDIA_SITES)}")
    print(f"Queries por semana: {len(query_specs)}")
    print(f"Rango: {all_weeks[0].start if all_weeks else args.since} -> {requested_end}")
    print(f"Semanas completas: {len(all_weeks)} | pendientes: {len(pending)}")
    print(f"Salida: {output_base}/<semana>/<semana>_{OUTPUT_SOURCE}.csv")
    print(f"Estado: {checkpoint_path}")

    if args.dry_run:
        print("\nQueries:")
        for index, spec in enumerate(query_specs, 1):
            print(f"  {index:02d}. {spec.query}")
        if execution_weeks:
            print(
                f"\nPrimera pendiente: "
                f"{execution_weeks[0].start} -> {execution_weeks[0].end}"
            )
            print(
                f"Última pendiente: "
                f"{execution_weeks[-1].start} -> {execution_weeks[-1].end}"
            )
        else:
            print("\nNo hay semanas pendientes.")
        print("Dry-run: no se hicieron solicitudes ni se escribió estado.")
        return 0

    if not all_weeks:
        print("No hay semanas completas en el rango.")
        return 0
    if not execution_weeks:
        print("No hay semanas pendientes en el rango.")
        return 0

    checkpoint = load_checkpoint(checkpoint_path)
    current = checkpoint.get("current_week")
    if isinstance(current, dict):
        current_start = current.get("start")
        pending_starts = {week.start.isoformat() for week in pending}
        if current_start not in pending_starts:
            print(
                "ERROR: existe una semana parcial fuera del rango solicitado. "
                "Repite el comando original o usa otro --state-dir.",
                file=sys.stderr,
            )
            return 2
        if execution_weeks[0].start.isoformat() != current_start:
            current_week = next(
                week for week in pending if week.start.isoformat() == current_start
            )
            execution_weeks = [
                current_week,
                *[week for week in execution_weeks if week != current_week],
            ]
            if args.max_weeks is not None:
                execution_weeks = execution_weeks[: args.max_weeks]

    media_module = load_base_media_module()
    backend = MediaBackend(
        media_module,
        rss_retries=args.rss_retries,
        rss_backoff=args.rss_backoff,
        article_pause=args.article_pause,
    )
    completed = 0
    accepted_total = 0
    rejected_total = 0

    try:
        with ProcessLock(state_dir / "run.lock"):
            for index, week in enumerate(execution_weeks, 1):
                print(
                    f"\n[{index}/{len(execution_weeks)}] "
                    f"{week.start} -> {week.end}"
                )
                accepted, rejected, candidates = process_week(
                    backend,
                    week,
                    output_base=output_base,
                    state_dir=state_dir,
                    checkpoint_path=checkpoint_path,
                    event_log_path=event_log_path,
                    checkpoint=checkpoint,
                    query_specs=query_specs,
                    query_pause=args.query_pause,
                )
                completed += 1
                accepted_total += accepted
                rejected_total += rejected
                print(
                    f"Semana confirmada: {accepted} aceptadas, "
                    f"{rejected} descartadas, {candidates} candidatas."
                )
    except (ExtractionStopped, OSError, json.JSONDecodeError) as exc:
        append_event(
            event_log_path,
            "backfill_stopped",
            reason=str(exc),
            current_week=checkpoint.get("current_week"),
            last_successful_week=checkpoint.get("last_successful_week"),
        )
        print(f"\nDETENIDO: {exc}", file=sys.stderr)
        print(f"Checkpoint conservado: {checkpoint_path}", file=sys.stderr)
        print(
            "Vuelve a ejecutar el mismo comando para continuar.",
            file=sys.stderr,
        )
        return 1
    except KeyboardInterrupt:
        append_event(
            event_log_path,
            "backfill_interrupted",
            current_week=checkpoint.get("current_week"),
            last_successful_week=checkpoint.get("last_successful_week"),
        )
        print("\nInterrumpido; el checkpoint se conservó.", file=sys.stderr)
        return 130
    finally:
        backend.close()

    print("\nBackfill al día para el rango solicitado.")
    print(f"Semanas confirmadas: {completed}")
    print(f"Noticias aceptadas: {accepted_total}")
    print(f"Resultados descartados: {rejected_total}")
    print(f"Checkpoint: {checkpoint_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
