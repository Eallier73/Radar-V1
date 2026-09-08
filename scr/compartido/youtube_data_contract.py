"""Contrato común para material semanal de comentarios de YouTube."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Mapping, Sequence


YOUTUBE_OUTPUT_COLUMNS = ("comment_text", "published_at", "query")
YOUTUBE_SEARCH_QUERIES = (
    "presidenta municipal de Tampico",
    "Presidenta municipal de Tampico",
    "Gobierno de Tampico",
    "gobierno de Tampico",
    "presidenta municipal Tampico",
    "municipio Tampico",
)


def parse_youtube_datetime(value: str) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    if re.search(r"[+-]\d{4}$", text):
        text = f"{text[:-5]}{text[-5:-2]}:{text[-2:]}"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def filter_youtube_rows_to_interval(
    rows: Sequence[Mapping[str, object]],
    *,
    week_start: datetime,
    week_before: datetime,
) -> tuple[list[dict[str, object]], dict[str, int]]:
    start_utc = as_utc(week_start)
    before_utc = as_utc(week_before)
    kept: list[dict[str, object]] = []
    counters = {"before": 0, "after": 0, "invalid": 0}
    for row in rows:
        published_at = parse_youtube_datetime(str(row.get("published_at", "") or ""))
        if published_at is None:
            counters["invalid"] += 1
        elif published_at < start_utc:
            counters["before"] += 1
        elif published_at >= before_utc:
            counters["after"] += 1
        else:
            kept.append(dict(row))
    return kept, counters


def project_youtube_rows(
    rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    return [
        {column: row.get(column, "") for column in YOUTUBE_OUTPUT_COLUMNS}
        for row in rows
    ]


def deduplicate_youtube_rows(
    rows: Sequence[Mapping[str, object]],
) -> tuple[list[dict[str, object]], int]:
    """Deduplica por texto+fecha, ignora query y conserva la primera fila."""
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, object]] = []
    for row in rows:
        normalized_text = re.sub(
            r"\s+",
            " ",
            str(row.get("comment_text", "") or "").strip(),
        )
        parsed_date = parse_youtube_datetime(
            str(row.get("published_at", "") or "")
        )
        normalized_date = (
            parsed_date.isoformat()
            if parsed_date is not None
            else str(row.get("published_at", "") or "").strip()
        )
        key = (normalized_text, normalized_date)
        if key in seen:
            continue
        seen.add(key)
        unique.append(dict(row))
    return unique, len(rows) - len(unique)
