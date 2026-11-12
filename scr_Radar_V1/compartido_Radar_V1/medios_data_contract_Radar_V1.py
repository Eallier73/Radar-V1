"""Contrato canónico para el material semanal de Medios de Radar V1."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Mapping, Sequence


MEDIOS_OUTPUT_COLUMNS = (
    "titulo",
    "fecha",
    "iso_date",
    "fuente",
    "autor",
    "url",
    "url_google",
    "thumbnail",
    "texto",
    "origen",
)


def parse_media_datetime(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def clean_media_text(value: object) -> str:
    """Reproduce la limpieza observable de los 83 TXT históricos."""
    text = str(value or "").lower()
    text = re.sub(r"https?://\S+|www\.\S+", " ", text)
    text = re.sub(r"\b[\w-]+(?:\.[\w-]+)+\b", " ", text)
    text = unicodedata.normalize("NFD", text)
    text = "".join(
        character
        for character in text
        if unicodedata.category(character) != "Mn"
    )
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"\d+", " ", text)
    text = re.sub(r"[^a-z\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def build_media_txt(rows: Sequence[Mapping[str, object]]) -> str:
    blocks: list[str] = []
    for row in rows:
        title = str(row.get("titulo") or "").strip()
        article_text = str(row.get("texto") or "").strip()
        cleaned = clean_media_text(f"{title} {article_text}".strip())
        if cleaned:
            blocks.append(cleaned)
    words = " ".join(blocks).split()
    lines = [
        " ".join(words[index:index + 30])
        for index in range(0, len(words), 30)
    ]
    return "\n".join(lines) + ("\n" if lines else "")


def _stable_key(row: Mapping[str, object]) -> tuple[str, ...]:
    url = str(row.get("url") or row.get("url_google") or "").strip()
    if url:
        return ("url", url)
    return (
        "fallback",
        clean_media_text(row.get("titulo")),
        str(row.get("iso_date") or row.get("fecha") or "").strip(),
        clean_media_text(row.get("texto")),
    )


def process_media_rows(
    rows: Sequence[Mapping[str, object]],
    since: str,
    before: str,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Filtra la semana inclusiva, deduplica y ordena de forma reproducible."""
    start = datetime.fromisoformat(since).replace(tzinfo=timezone.utc)
    end_exclusive = (
        datetime.fromisoformat(before) + timedelta(days=1)
    ).replace(tzinfo=timezone.utc)
    if start >= end_exclusive:
        raise ValueError("El rango semanal de Medios es inválido.")

    counters = {
        "read": len(rows),
        "invalid_date": 0,
        "outside_range": 0,
        "empty_content": 0,
        "duplicates": 0,
    }
    selected: list[tuple[datetime, dict[str, str]]] = []
    seen: set[tuple[str, ...]] = set()
    for raw_row in rows:
        row = {
            column: str(raw_row.get(column) or "").strip()
            for column in MEDIOS_OUTPUT_COLUMNS
        }
        published_at = parse_media_datetime(row["iso_date"] or row["fecha"])
        if published_at is None:
            counters["invalid_date"] += 1
            continue
        if not start <= published_at < end_exclusive:
            counters["outside_range"] += 1
            continue
        if not (row["titulo"] or row["texto"]):
            counters["empty_content"] += 1
            continue
        key = _stable_key(row)
        if key in seen:
            counters["duplicates"] += 1
            continue
        seen.add(key)
        selected.append((published_at, row))

    selected.sort(
        key=lambda item: (
            item[0],
            item[1]["url"],
            item[1]["titulo"],
        ),
        reverse=True,
    )
    return [row for _, row in selected], counters
