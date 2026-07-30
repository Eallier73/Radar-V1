#!/usr/bin/env python3
"""Backfill semanal reanudable de comentarios públicos de @ChuchoNader.

El actor oficial de comentarios de Apify necesita URLs de publicaciones. Este
extractor descubre esas URLs por semana con el actor oficial de posts, pero el
único artefacto semanal que conserva en ``datos/radar_semanal_extraido`` es un
CSV de comentarios.

La unidad de confirmación es:

1. descubrimiento de posts de una semana;
2. cada lote de URLs enviado al actor de comentarios;
3. CSV semanal terminado.

Si Apify, la red o el crédito detienen el proceso, los lotes confirmados quedan
en ``state/facebook_chucho_nader``. La siguiente ejecución continúa en el
primer lote pendiente y nunca marca una semana como terminada antes de escribir
su CSV de manera atómica.
"""

from __future__ import annotations

import argparse
import csv
import fcntl
import json
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_DIR = REPO_ROOT / "scr" / "compartido"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from output_naming import build_source_filename, build_week_folder_name
from radar_paths import EXTRACTED_DATA_DIR, STATE_DIR


TARGET_HANDLE = "ChuchoNader"
TARGET_NAME = "Chucho Nader"
TARGET_PAGE_URL = "https://www.facebook.com/ChuchoNader/"

ACTOR_POSTS = "apify/facebook-posts-scraper"
ACTOR_COMMENTS = "apify/facebook-comments-scraper"

# Coincide con la primera semana disponible en el histórico de Radar y cubre
# bastante más de un año. Solo se procesan semanas completas por defecto.
DEFAULT_START_DATE = date(2024, 9, 30)
DEFAULT_POSTS_LIMIT = 500
DEFAULT_COMMENT_BATCH_SIZE = 5
DEFAULT_STATE_DIR = STATE_DIR / "facebook_chucho_nader"

CHECKPOINT_VERSION = 1
SUCCESS_STATUS = "SUCCEEDED"
OUTPUT_SOURCE = "facebook_chucho_nader_comentarios"

CSV_COLUMNS = [
    "fuente",
    "pagina",
    "page_handle",
    "page_url",
    "semana_post_inicio",
    "semana_post_fin",
    "post_url",
    "comment_id",
    "parent_comment_id",
    "threading_depth",
    "comentario_texto",
    "autor",
    "autor_id",
    "perfil_url",
    "fecha_comentario",
    "fecha_comentario_date",
    "likes_comentario",
    "respuestas_comentario",
    "es_respuesta",
    "url_comentario",
    "apify_run_id",
    "apify_dataset_id",
]


class ExtractionStopped(RuntimeError):
    """Error operativo que debe detener el backfill sin adelantar el estado."""


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
            "target_handle": TARGET_HANDLE,
            "target_page_url": TARGET_PAGE_URL,
            "last_successful_week": None,
            "current_week": None,
            "updated_at": utc_now_iso(),
        }
    payload = read_json(path)
    if payload.get("version") != CHECKPOINT_VERSION:
        raise ExtractionStopped(
            f"Checkpoint con versión incompatible en {path}. "
            "No se modificó para evitar perder el avance."
        )
    if payload.get("target_handle") != TARGET_HANDLE:
        raise ExtractionStopped(
            f"El checkpoint {path} pertenece a otro target."
        )
    return payload


def save_checkpoint(path: Path, checkpoint: dict[str, Any]) -> None:
    checkpoint["updated_at"] = utc_now_iso()
    atomic_write_json(path, checkpoint)


def output_is_complete(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader)
    except (OSError, StopIteration, UnicodeError, csv.Error):
        return False
    return header == CSV_COLUMNS


def _string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value).strip()


def parse_datetime(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        raw = float(value)
        if raw > 10_000_000_000:
            raw /= 1000
        try:
            return datetime.fromtimestamp(raw, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None

    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return parse_datetime(int(text))
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _item_error(item: dict[str, Any]) -> str:
    raw = item.get("error")
    if isinstance(raw, dict):
        return _string(raw.get("message") or raw)
    return _string(raw or item.get("errorMessage"))


def extract_post_urls(items: list[dict[str, Any]], week: WeekWindow) -> list[str]:
    errors = [_item_error(item) for item in items if _item_error(item)]
    if errors:
        raise ExtractionStopped(
            "El actor de posts devolvió errores de item: " + "; ".join(errors[:3])
        )

    urls: list[str] = []
    seen: set[str] = set()
    for item in items:
        source_page = _string(item.get("facebookUrl") or item.get("inputUrl"))
        if source_page and TARGET_HANDLE.lower() not in source_page.lower():
            continue
        raw_url = _string(item.get("url") or item.get("postUrl"))
        if not raw_url or "facebook.com" not in raw_url.lower():
            continue
        published = parse_datetime(
            item.get("time")
            or item.get("timestamp")
            or item.get("timeCreated")
            or item.get("timestampCreated")
        )
        # El filtro del actor es la primera barrera. Si entrega fecha, también
        # validamos localmente para impedir que una semana absorba otra.
        if published is not None and not (week.start <= published.date() <= week.end):
            continue
        if raw_url not in seen:
            seen.add(raw_url)
            urls.append(raw_url)
    return urls


def normalize_comment(
    item: dict[str, Any],
    week: WeekWindow,
    run_id: str,
    dataset_id: str,
) -> dict[str, Any]:
    author = item.get("author") if isinstance(item.get("author"), dict) else {}
    parent = (
        item.get("parentReply")
        if isinstance(item.get("parentReply"), dict)
        else item.get("parentComment")
        if isinstance(item.get("parentComment"), dict)
        else {}
    )
    comment_dt = parse_datetime(
        item.get("date") or item.get("timestamp") or item.get("commentDate")
    )
    depth_raw = item.get("threadingDepth")
    try:
        depth = int(depth_raw) if depth_raw not in (None, "") else 0
    except (TypeError, ValueError):
        depth = 0

    profile_url = item.get("profileUrl") or author.get("url")
    if isinstance(profile_url, dict):
        profile_url = profile_url.get("url") or profile_url.get("facebookUrl")

    return {
        "fuente": "facebook",
        "pagina": TARGET_NAME,
        "page_handle": TARGET_HANDLE,
        "page_url": TARGET_PAGE_URL,
        "semana_post_inicio": week.start.isoformat(),
        "semana_post_fin": week.end.isoformat(),
        "post_url": _string(
            item.get("facebookUrl")
            or item.get("inputUrl")
            or item.get("postUrl")
        ),
        "comment_id": _string(item.get("commentId") or item.get("id")),
        "parent_comment_id": _string(
            item.get("replyToCommentId")
            or parent.get("commentId")
            or parent.get("id")
        ),
        "threading_depth": depth,
        "comentario_texto": _string(
            item.get("text") or item.get("commentText") or item.get("body")
        ),
        "autor": _string(
            item.get("profileName")
            or item.get("name")
            or author.get("name")
        ),
        "autor_id": _string(item.get("profileId") or author.get("id")),
        "perfil_url": _string(profile_url),
        "fecha_comentario": comment_dt.isoformat() if comment_dt else _string(item.get("date")),
        "fecha_comentario_date": comment_dt.date().isoformat() if comment_dt else "",
        "likes_comentario": item.get("likesCount") or item.get("likes") or 0,
        "respuestas_comentario": item.get("commentsCount") or 0,
        "es_respuesta": bool(depth > 0 or item.get("replyToCommentId")),
        "url_comentario": _string(item.get("commentUrl") or item.get("url")),
        "apify_run_id": run_id,
        "apify_dataset_id": dataset_id,
    }


def comment_identity(row: dict[str, Any]) -> tuple[str, ...]:
    comment_id = _string(row.get("comment_id"))
    if comment_id:
        return ("id", comment_id)
    comment_url = _string(row.get("url_comentario"))
    if comment_url:
        return ("url", comment_url)
    return (
        "fallback",
        _string(row.get("post_url")),
        _string(row.get("fecha_comentario")),
        _string(row.get("autor")),
        _string(row.get("comentario_texto")),
    )


def call_actor(client: Any, actor_id: str, run_input: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        run = client.actor(actor_id).call(run_input=run_input)
    except Exception as exc:
        raise ExtractionStopped(f"Falló {actor_id}: {exc}") from exc
    if not run:
        raise ExtractionStopped(f"{actor_id} no devolvió información de ejecución.")

    status = _string(run.get("status")).upper()
    run_id = _string(run.get("id"))
    dataset_id = _string(run.get("defaultDatasetId"))
    if status != SUCCESS_STATUS:
        message = _string(run.get("statusMessage"))
        raise ExtractionStopped(
            f"{actor_id} terminó con status={status or 'UNKNOWN'}"
            + (f": {message}" if message else "")
        )
    if not dataset_id:
        raise ExtractionStopped(
            f"{actor_id} terminó correctamente, pero no informó dataset."
        )
    try:
        items = list(client.dataset(dataset_id).iterate_items())
    except Exception as exc:
        raise ExtractionStopped(
            f"No se pudo leer el dataset {dataset_id} de {actor_id}: {exc}"
        ) from exc

    return items, {
        "actor_id": actor_id,
        "run_id": run_id,
        "dataset_id": dataset_id,
        "status": status,
        "usage_total_usd": run.get("usageTotalUsd"),
        "item_count": len(items),
    }


def discover_posts(
    client: Any,
    week: WeekWindow,
    max_posts: int,
) -> tuple[list[str], dict[str, Any]]:
    # El límite superior es exclusivo a nivel local: se envía el lunes
    # siguiente para no perder publicaciones del domingo.
    run_input = {
        "startUrls": [{"url": TARGET_PAGE_URL}],
        "resultsLimit": max_posts,
        "captionText": False,
        "onlyPostsNewerThan": week.start.isoformat(),
        "onlyPostsOlderThan": week.next_start.isoformat(),
    }
    items, metadata = call_actor(client, ACTOR_POSTS, run_input)
    post_urls = extract_post_urls(items, week)
    if len(items) >= max_posts:
        raise ExtractionStopped(
            f"El actor alcanzó --max-posts={max_posts} en la semana "
            f"{week.start} -> {week.end}; aumenta el límite para no truncarla."
        )
    return post_urls, metadata


def download_comment_batch(
    client: Any,
    post_urls: list[str],
    week: WeekWindow,
    max_comments: Optional[int],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    run_input: dict[str, Any] = {
        "startUrls": [{"url": url} for url in post_urls],
        "includeNestedComments": True,
        "viewOption": "RECENT_ACTIVITY",
    }
    if max_comments is not None:
        run_input["resultsLimit"] = max_comments

    items, metadata = call_actor(client, ACTOR_COMMENTS, run_input)
    errors = [_item_error(item) for item in items if _item_error(item)]
    if errors:
        raise ExtractionStopped(
            "El actor de comentarios devolvió errores de item: "
            + "; ".join(errors[:3])
        )
    rows = []
    for item in items:
        is_comment = bool(
            item.get("commentId")
            or item.get("commentUrl")
            or (
                item.get("id")
                and (item.get("date") or item.get("text"))
            )
        )
        if not is_comment:
            continue
        rows.append(
            normalize_comment(
                item,
                week,
                metadata["run_id"],
                metadata["dataset_id"],
            )
        )
    return rows, metadata


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


def _work_week_dir(state_dir: Path, week: WeekWindow) -> Path:
    return state_dir / "work" / week.start.isoformat()


def _batch_path(state_dir: Path, week: WeekWindow, batch_index: int) -> Path:
    return _work_week_dir(state_dir, week) / f"comments_batch_{batch_index:05d}.json"


def _load_existing_batch(path: Path, expected_urls: list[str]) -> Optional[list[dict[str, Any]]]:
    if not path.is_file():
        return None
    try:
        payload = read_json(path)
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("post_urls") != expected_urls:
        return None
    rows = payload.get("rows")
    return rows if isinstance(rows, list) else None


def _collect_week_rows(
    state_dir: Path,
    week: WeekWindow,
    post_urls: list[str],
    batch_size: int,
) -> list[dict[str, Any]]:
    deduplicated: dict[tuple[str, ...], dict[str, Any]] = {}
    for batch_index, offset in enumerate(range(0, len(post_urls), batch_size)):
        batch_urls = post_urls[offset : offset + batch_size]
        batch_path = _batch_path(state_dir, week, batch_index)
        rows = _load_existing_batch(batch_path, batch_urls)
        if rows is None:
            raise ExtractionStopped(
                f"Falta o está incompleto el lote confirmado {batch_path}."
            )
        for row in rows:
            if isinstance(row, dict):
                deduplicated[comment_identity(row)] = row
    return sorted(
        deduplicated.values(),
        key=lambda row: (
            _string(row.get("fecha_comentario")),
            _string(row.get("post_url")),
            _string(row.get("comment_id")),
        ),
    )


def _fresh_current_week(
    week: WeekWindow,
    *,
    batch_size: int,
    max_comments: Optional[int],
) -> dict[str, Any]:
    return {
        "start": week.start.isoformat(),
        "end": week.end.isoformat(),
        "phase": "discover_posts",
        "post_urls": [],
        "next_comment_batch": 0,
        "batch_size": batch_size,
        "max_comments": max_comments,
        "last_successful_step": None,
    }


def process_week(
    client: Any,
    week: WeekWindow,
    *,
    output_base: Path,
    state_dir: Path,
    checkpoint_path: Path,
    event_log_path: Path,
    checkpoint: dict[str, Any],
    max_posts: int,
    max_comments: Optional[int],
    batch_size: int,
) -> tuple[int, int]:
    output_path = weekly_csv_path(output_base, week)
    if output_is_complete(output_path):
        checkpoint["last_successful_week"] = week.end.isoformat()
        checkpoint["current_week"] = None
        save_checkpoint(checkpoint_path, checkpoint)
        append_event(
            event_log_path,
            "week_already_complete",
            week_start=week.start,
            week_end=week.end,
            output=str(output_path),
        )
        with output_path.open("r", encoding="utf-8-sig", newline="") as handle:
            row_count = max(sum(1 for _ in csv.reader(handle)) - 1, 0)
        return row_count, 0

    current = checkpoint.get("current_week")
    if (
        not isinstance(current, dict)
        or current.get("start") != week.start.isoformat()
        or current.get("end") != week.end.isoformat()
    ):
        current = _fresh_current_week(
            week,
            batch_size=batch_size,
            max_comments=max_comments,
        )
        checkpoint["current_week"] = current
        save_checkpoint(checkpoint_path, checkpoint)
        append_event(
            event_log_path,
            "week_started",
            week_start=week.start,
            week_end=week.end,
        )
    else:
        saved_batch_size = int(current.get("batch_size") or batch_size)
        saved_max_comments = current.get("max_comments")
        if saved_batch_size != batch_size or saved_max_comments != max_comments:
            raise ExtractionStopped(
                "La semana actual tiene lotes parciales con otra configuración "
                f"(batch_size={saved_batch_size}, max_comments={saved_max_comments}). "
                "Repite el comando con esos valores para conservar la reanudación."
            )

    post_urls = current.get("post_urls") or []
    if current.get("phase") == "discover_posts":
        post_urls, metadata = discover_posts(client, week, max_posts)
        current.update(
            {
                "phase": "download_comments",
                "post_urls": post_urls,
                "next_comment_batch": 0,
                "last_successful_step": {
                    "type": "posts_discovered",
                    "timestamp": utc_now_iso(),
                    **metadata,
                },
            }
        )
        save_checkpoint(checkpoint_path, checkpoint)
        append_event(
            event_log_path,
            "posts_discovered",
            week_start=week.start,
            week_end=week.end,
            posts=len(post_urls),
            **metadata,
        )

    total_batches = (len(post_urls) + batch_size - 1) // batch_size
    next_batch = int(current.get("next_comment_batch") or 0)
    for batch_index in range(next_batch, total_batches):
        offset = batch_index * batch_size
        batch_urls = post_urls[offset : offset + batch_size]
        batch_path = _batch_path(state_dir, week, batch_index)
        existing_rows = _load_existing_batch(batch_path, batch_urls)

        if existing_rows is None:
            rows, metadata = download_comment_batch(
                client,
                batch_urls,
                week,
                max_comments,
            )
            atomic_write_json(
                batch_path,
                {
                    "week_start": week.start,
                    "week_end": week.end,
                    "batch_index": batch_index,
                    "post_urls": batch_urls,
                    "metadata": metadata,
                    "rows": rows,
                },
            )
        else:
            rows = existing_rows
            metadata = {"resumed_from_batch_file": True}

        current["next_comment_batch"] = batch_index + 1
        current["last_successful_step"] = {
            "type": "comments_batch",
            "timestamp": utc_now_iso(),
            "batch_index": batch_index,
            "comments": len(rows),
            **metadata,
        }
        save_checkpoint(checkpoint_path, checkpoint)
        append_event(
            event_log_path,
            "comments_batch_complete",
            week_start=week.start,
            week_end=week.end,
            batch_index=batch_index,
            total_batches=total_batches,
            posts=len(batch_urls),
            comments=len(rows),
            **metadata,
        )

    rows = _collect_week_rows(state_dir, week, post_urls, batch_size)
    write_weekly_csv(output_path, rows)
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
    append_event(
        event_log_path,
        "week_complete",
        week_start=week.start,
        week_end=week.end,
        posts=len(post_urls),
        comments=len(rows),
        output=str(output_path),
    )
    return len(rows), len(post_urls)


class ProcessLock:
    """Evita dos backfills simultáneos sobre el mismo checkpoint."""

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


def load_env_files() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(REPO_ROOT / ".env")
    load_dotenv(REPO_ROOT / ".env.local")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Descarga por semanas únicamente comentarios públicos de "
            "facebook.com/ChuchoNader y reanuda después de errores."
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
        help="Último domingo a procesar (default: último domingo terminado).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=EXTRACTED_DATA_DIR,
        help="Base de datos crudos semanales (default: %(default)s).",
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=DEFAULT_STATE_DIR,
        help="Checkpoint y lotes reanudables (default: %(default)s).",
    )
    parser.add_argument(
        "--max-posts",
        type=int,
        default=DEFAULT_POSTS_LIMIT,
        help="Tope de posts descubiertos por semana (default: %(default)s).",
    )
    parser.add_argument(
        "--max-comments",
        type=int,
        default=None,
        help="Tope de comentarios por post; sin valor pide todos los disponibles.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_COMMENT_BATCH_SIZE,
        help="Posts por ejecución del actor de comentarios (default: %(default)s).",
    )
    parser.add_argument(
        "--max-weeks",
        type=int,
        default=None,
        help="Limita semanas en esta ejecución; útil para pruebas controladas.",
    )
    parser.add_argument("--token", default=None, help="Token Apify; preferir APIFY_TOKEN.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Muestra el plan pendiente sin llamar Apify ni escribir estado.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Muestra el checkpoint y termina sin llamar Apify.",
    )
    return parser


def _positive(parser: argparse.ArgumentParser, value: Optional[int], label: str) -> None:
    if value is not None and value <= 0:
        parser.error(f"{label} debe ser mayor que cero.")


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _positive(parser, args.max_posts, "--max-posts")
    _positive(parser, args.max_comments, "--max-comments")
    _positive(parser, args.batch_size, "--batch-size")
    _positive(parser, args.max_weeks, "--max-weeks")

    output_base = args.output_dir.expanduser().resolve()
    state_dir = args.state_dir.expanduser().resolve()
    checkpoint_path = state_dir / "checkpoint.json"
    event_log_path = state_dir / "eventos.jsonl"

    if args.status:
        checkpoint = load_checkpoint(checkpoint_path)
        print(json.dumps(checkpoint, ensure_ascii=False, indent=2))
        print(f"Checkpoint: {checkpoint_path}")
        print(f"Eventos: {event_log_path}")
        return 0

    requested_end = args.until or last_completed_sunday()
    if requested_end.weekday() != 6:
        parser.error("--until debe ser domingo para no confirmar una semana parcial.")
    if args.since > requested_end:
        parser.error("--since no puede ser posterior al último domingo a procesar.")

    all_weeks = list(iter_complete_weeks(args.since, requested_end))
    pending = [
        week for week in all_weeks
        if not output_is_complete(weekly_csv_path(output_base, week))
    ]
    execution_weeks = pending[: args.max_weeks] if args.max_weeks is not None else pending
    print("=" * 72)
    print("COMENTARIOS FACEBOOK — CHUCHO NADER")
    print("=" * 72)
    print(f"Página: {TARGET_PAGE_URL}")
    print(f"Rango: {all_weeks[0].start if all_weeks else args.since} -> {requested_end}")
    print(f"Semanas completas: {len(all_weeks)} | pendientes: {len(pending)}")
    print(f"Salida: {output_base}/<semana>/<semana>_{OUTPUT_SOURCE}.csv")
    print(f"Estado: {checkpoint_path}")

    if args.dry_run:
        if execution_weeks:
            print(
                f"Primera pendiente de esta ejecución: "
                f"{execution_weeks[0].start} -> {execution_weeks[0].end}"
            )
            print(
                f"Última pendiente de esta ejecución: "
                f"{execution_weeks[-1].start} -> {execution_weeks[-1].end}"
            )
        else:
            print("No hay semanas pendientes.")
        print("Dry-run: no se llamó Apify ni se escribieron archivos.")
        return 0

    if not all_weeks:
        print("No hay semanas completas en el rango.")
        return 0
    if not execution_weeks:
        print("No hay semanas pendientes en el rango.")
        return 0

    load_env_files()
    token = args.token or os.environ.get("APIFY_TOKEN")
    if not token:
        print("ERROR: falta APIFY_TOKEN en .env/.env.local o --token.", file=sys.stderr)
        return 2
    try:
        from apify_client import ApifyClient
    except ImportError:
        print(
            "ERROR: falta apify-client. Usa el entorno radar-v1 definido por el repo.",
            file=sys.stderr,
        )
        return 2

    checkpoint = load_checkpoint(checkpoint_path)
    current = checkpoint.get("current_week")
    if isinstance(current, dict):
        current_start = current.get("start")
        pending_starts = {week.start.isoformat() for week in pending}
        if current_start not in pending_starts:
            print(
                "ERROR: el checkpoint contiene una semana parcial fuera del "
                "rango solicitado. Repite el comando original o usa otro "
                "--state-dir.",
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
    client = ApifyClient(token)
    completed_this_run = 0
    total_comments = 0

    try:
        with ProcessLock(state_dir / "run.lock"):
            for index, week in enumerate(execution_weeks, 1):
                print(
                    f"\n[{index}/{len(execution_weeks)}] "
                    f"{week.start} -> {week.end} | pendiente"
                )
                comments, posts = process_week(
                    client,
                    week,
                    output_base=output_base,
                    state_dir=state_dir,
                    checkpoint_path=checkpoint_path,
                    event_log_path=event_log_path,
                    checkpoint=checkpoint,
                    max_posts=args.max_posts,
                    max_comments=args.max_comments,
                    batch_size=args.batch_size,
                )
                completed_this_run += 1
                total_comments += comments
                print(f"Semana confirmada: {posts} posts, {comments} comentarios.")
    except (ExtractionStopped, OSError, json.JSONDecodeError) as exc:
        current = checkpoint.get("current_week") or {}
        append_event(
            event_log_path,
            "backfill_stopped",
            reason=str(exc),
            current_week=current,
            last_successful_week=checkpoint.get("last_successful_week"),
        )
        print(f"\nDETENIDO: {exc}", file=sys.stderr)
        print(f"Checkpoint conservado: {checkpoint_path}", file=sys.stderr)
        print(
            "Vuelve a ejecutar el mismo comando; continuará desde el primer "
            "lote no confirmado.",
            file=sys.stderr,
        )
        return 1
    except KeyboardInterrupt:
        current = checkpoint.get("current_week") or {}
        append_event(
            event_log_path,
            "backfill_interrupted",
            current_week=current,
            last_successful_week=checkpoint.get("last_successful_week"),
        )
        print("\nInterrumpido; el checkpoint confirmado se conservó.", file=sys.stderr)
        return 130

    print("\nBackfill al día para el rango solicitado.")
    print(f"Semanas confirmadas/reconocidas: {completed_this_run}")
    print(f"Comentarios contabilizados: {total_comments}")
    print(f"Checkpoint: {checkpoint_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
