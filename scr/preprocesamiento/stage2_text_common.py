#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import csv
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


DEFAULT_DATOS_RADAR_DIR = Path("/home/emilio/Documentos/RAdAR/Datos_RAdAR")
DEFAULT_DATOS_TEXTO_DIR = Path("/home/emilio/Documentos/RAdAR/Datos_RadaR_Texto")

SOURCE_DIR_NAMES = {
    "facebook": "Facebook",
    "twitter": "Twitter",
    "youtube": "YouTube",
    "medios": "Medios",
}

TEXT_DIR_NAMES = {
    "facebook": "Facebook_Semana_Texto",
    "twitter": "Twitter_Semana_Texto",
    "youtube": "Youtube_Semana_Texto",
    "medios": "Medios_Semana_Texto",
}

EXPECTED_CANONICAL_FILENAMES = {
    "facebook": lambda week_name: f"facebook_institutional_raw_{week_name}.csv",
    "twitter": lambda week_name: f"twitter_data_{week_name}.csv",
    "youtube": lambda week_name: f"youtube_comentarios_{week_name}.csv",
    "medios": lambda week_name: f"media_articles_{week_name}.csv",
}

VALID_OUTPUT_MODES = {"archive", "overwrite-text"}
VALID_SOURCES = tuple(SOURCE_DIR_NAMES.keys())
ROOT_WEEK_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_semana_.+$")


@dataclass(frozen=True)
class WeekContext:
    source: str
    week_name: str
    source_root: Path
    week_dir: Path
    iso_year: int
    iso_week: int
    iso_token: str
    output_dir: Path
    output_filename: str
    output_path: Path


@dataclass
class CanonicalCsvSelection:
    source: str
    week_name: str
    path: Path
    expected_filename: str
    selection_criteria: str
    warnings: list[str] = field(default_factory=list)


def now_utc_text() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_default_run_id(prefix: str = "stage2_text_preprocessing") -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{stamp}"


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, payload: Any) -> None:
    ensure_directory(path.parent)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False),
        encoding="utf-8",
    )


def write_csv(path: Path, rows: Sequence[dict[str, Any]], fieldnames: Sequence[str]) -> None:
    ensure_directory(path.parent)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def split_cli_values(values: Sequence[str] | None) -> list[str]:
    items: list[str] = []
    for value in values or []:
        for part in value.split(","):
            token = part.strip()
            if token:
                items.append(token)
    return items


def normalize_source_token(raw_value: str) -> str:
    token = raw_value.strip().lower()
    aliases = {
        "facebook": "facebook",
        "fb": "facebook",
        "twitter": "twitter",
        "x": "twitter",
        "youtube": "youtube",
        "yt": "youtube",
        "medios": "medios",
        "medio": "medios",
    }
    normalized = aliases.get(token)
    if not normalized:
        raise ValueError(f"Fuente no soportada: {raw_value}")
    return normalized


def resolve_requested_sources(raw_values: Sequence[str] | None) -> list[str]:
    if not raw_values:
        return list(VALID_SOURCES)
    normalized: list[str] = []
    seen = set()
    for raw_value in split_cli_values(raw_values):
        source = normalize_source_token(raw_value)
        if source not in seen:
            seen.add(source)
            normalized.append(source)
    return normalized


def parse_week_name_to_iso(week_name: str) -> tuple[int, int]:
    prefix = week_name.split("_semana_", 1)[0]
    start_date = date.fromisoformat(prefix)
    iso_year, iso_week, _ = start_date.isocalendar()
    return iso_year, iso_week


def iso_token_from_parts(iso_year: int, iso_week: int) -> str:
    return f"{iso_year % 100:02d}_{iso_week:02d}"


def build_week_context(source: str, week_dir: Path, datos_texto_dir: Path) -> WeekContext:
    iso_year, iso_week = parse_week_name_to_iso(week_dir.name)
    iso_token = iso_token_from_parts(iso_year, iso_week)
    output_dir = datos_texto_dir / TEXT_DIR_NAMES[source]
    output_filename = f"{iso_token}_{source}.txt"
    return WeekContext(
        source=source,
        week_name=week_dir.name,
        source_root=week_dir.parent,
        week_dir=week_dir,
        iso_year=iso_year,
        iso_week=iso_week,
        iso_token=iso_token,
        output_dir=output_dir,
        output_filename=output_filename,
        output_path=output_dir / output_filename,
    )


def discover_week_contexts(
    datos_radar_dir: Path,
    datos_texto_dir: Path,
    sources: Sequence[str],
) -> dict[str, list[WeekContext]]:
    discovered: dict[str, list[WeekContext]] = {}
    for source in sources:
        source_dir = datos_radar_dir / SOURCE_DIR_NAMES[source]
        contexts: list[WeekContext] = []
        if source_dir.exists():
            for child in sorted(source_dir.iterdir()):
                if not child.is_dir():
                    continue
                if child.name.startswith("_"):
                    continue
                contexts.append(build_week_context(source, child, datos_texto_dir))
        discovered[source] = contexts
    return discovered


def normalize_week_filter_token(raw_value: str) -> str:
    token = raw_value.strip().lower()
    if re.fullmatch(r"\d{2}_\d{2}", token):
        return token
    if re.fullmatch(r"\d{4}-w\d{2}", token):
        return token
    return token


def week_matches_filters(week_ctx: WeekContext, requested_weeks: set[str]) -> bool:
    if not requested_weeks:
        return True
    candidates = {
        week_ctx.week_name.lower(),
        week_ctx.iso_token.lower(),
        f"{week_ctx.iso_year}-w{week_ctx.iso_week:02d}".lower(),
    }
    return any(candidate in requested_weeks for candidate in candidates)


def resolve_requested_weeks(raw_values: Sequence[str] | None) -> set[str]:
    return {normalize_week_filter_token(value) for value in split_cli_values(raw_values)}


def dedupe_keep_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def build_word_lines(items: Sequence[str], words_per_line: int) -> list[str]:
    words = " ".join(items).split()
    return [
        " ".join(words[index:index + words_per_line])
        for index in range(0, len(words), words_per_line)
        if words[index:index + words_per_line]
    ]


def detect_csv_delimiter(path: Path) -> str:
    with path.open("r", encoding="utf-8-sig", errors="ignore", newline="") as handle:
        header_line = handle.readline()
    semicolons = header_line.count(";")
    commas = header_line.count(",")
    return ";" if semicolons > commas else ","


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_expected_filename(source: str, week_name: str) -> str:
    return EXPECTED_CANONICAL_FILENAMES[source](week_name)


def is_legacy_root_week_dir(path: Path) -> bool:
    return path.is_dir() and bool(ROOT_WEEK_DIR_RE.match(path.name))
