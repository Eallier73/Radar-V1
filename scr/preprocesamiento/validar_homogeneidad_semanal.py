#!/usr/bin/env python3
"""Valida el contrato canónico semanal de las cuatro fuentes de Radar V1."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_DIR = REPO_ROOT / "scr" / "compartido"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from facebook_data_contract import (
    FACEBOOK_BASE_ACCOUNTS,
    FACEBOOK_PROCESSED_COLUMNS,
    facebook_dedup_key,
    normalize_facebook_url,
)
from medios_data_contract import (
    MEDIOS_OUTPUT_COLUMNS,
    clean_media_text,
    process_media_rows,
)
from output_naming import build_week_folder_name
from radar_paths import PROCESSED_DATA_DIR
from twitter_data_contract import (
    TWITTER_OUTPUT_COLUMNS,
    deduplicate_twitter_rows,
    filter_twitter_rows_to_account_scope,
    parse_twitter_datetime,
)
from youtube_data_contract import (
    YOUTUBE_OUTPUT_COLUMNS,
    YOUTUBE_SEARCH_QUERIES,
    deduplicate_youtube_rows,
    parse_youtube_datetime,
)
from promover_csv_a_texto import build_text_content


SOURCES = ("youtube", "twitter", "medios", "facebook")
WEEK_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_semana_.+$")


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def week_bounds(week_name: str) -> tuple[datetime, datetime]:
    match = WEEK_RE.fullmatch(week_name)
    if not match:
        raise ValueError(f"Nombre semanal inválido: {week_name}")
    start = datetime.fromisoformat(match.group(1)).replace(tzinfo=timezone.utc)
    expected = build_week_folder_name(start, start + timedelta(days=6))
    if week_name != expected:
        raise ValueError(
            f"Nombre semanal fuera de contrato: {week_name}; esperado {expected}"
        )
    return start, start + timedelta(days=7)


def selected_weeks(base: Path, requested: set[str]) -> list[Path]:
    return sorted(
        path
        for path in base.iterdir()
        if path.is_dir()
        and WEEK_RE.fullmatch(path.name)
        and (
            not requested
            or path.name in requested
            or path.name[:10] in requested
        )
    )


def validate_youtube(week: Path, errors: list[str], *, require_txt: bool = True) -> int:
    path = week / f"{week.name}_youtube.csv"
    txt_path = week / f"{week.name}_youtube.txt"
    if not path.is_file():
        errors.append(f"youtube/{week.name}: falta CSV")
        return 0
    if require_txt and not txt_path.is_file():
        errors.append(f"youtube/{week.name}: falta TXT")
    header, rows = read_csv(path)
    if tuple(header) != YOUTUBE_OUTPUT_COLUMNS:
        errors.append(f"youtube/{week.name}: encabezado incompatible")
        return len(rows)
    start, before = week_bounds(week.name)
    for index, row in enumerate(rows, start=2):
        parsed = parse_youtube_datetime(row.get("published_at", ""))
        if parsed is None or not start <= parsed < before:
            errors.append(f"youtube/{week.name}:{index}: fecha fuera de contrato")
        if not str(row.get("comment_text", "")).strip():
            errors.append(f"youtube/{week.name}:{index}: texto vacío")
        if row.get("query", "") not in YOUTUBE_SEARCH_QUERIES:
            errors.append(f"youtube/{week.name}:{index}: query fuera de contrato")
    _, removed = deduplicate_youtube_rows(rows)
    if removed:
        errors.append(f"youtube/{week.name}: {removed} duplicados")
    expected_txt, _, _ = build_text_content("youtube", rows)
    if require_txt and txt_path.is_file() and txt_path.read_text(encoding="utf-8") != expected_txt:
        errors.append(f"youtube/{week.name}: TXT no corresponde al CSV")
    return len(rows)


def validate_twitter(week: Path, errors: list[str], *, require_txt: bool = True) -> int:
    path = week / f"{week.name}_twitter.csv"
    txt_path = week / f"{week.name}_twitter.txt"
    if not path.is_file():
        errors.append(f"twitter/{week.name}: falta CSV")
        return 0
    if require_txt and not txt_path.is_file():
        errors.append(f"twitter/{week.name}: falta TXT")
    header, rows = read_csv(path)
    if tuple(header) != TWITTER_OUTPUT_COLUMNS:
        errors.append(f"twitter/{week.name}: encabezado incompatible")
        return len(rows)
    start, before = week_bounds(week.name)
    for index, row in enumerate(rows, start=2):
        parsed = parse_twitter_datetime(row.get("published_at", ""))
        if parsed is None or not start <= parsed < before:
            errors.append(f"twitter/{week.name}:{index}: fecha fuera de contrato")
        text = str(row.get("text", "")).strip()
        if not text:
            errors.append(f"twitter/{week.name}:{index}: texto vacío")
    _, removed_outside_scope = filter_twitter_rows_to_account_scope(rows)
    if removed_outside_scope:
        errors.append(
            f"twitter/{week.name}: {removed_outside_scope} filas fuera del "
            "alcance de cuentas"
        )
    _, removed = deduplicate_twitter_rows(rows)
    if removed:
        errors.append(f"twitter/{week.name}: {removed} duplicados")
    expected_txt, _, _ = build_text_content("twitter", rows)
    if require_txt and txt_path.is_file() and txt_path.read_text(encoding="utf-8") != expected_txt:
        errors.append(f"twitter/{week.name}: TXT no corresponde al CSV")
    return len(rows)


def validate_medios(week: Path, errors: list[str], *, historical_text: bool = False) -> int:
    txt_path = week / f"{week.name}_medios.txt"
    if not txt_path.is_file():
        errors.append(f"medios/{week.name}: falta TXT")
        return 0
    content = txt_path.read_text(encoding="utf-8")
    compact = " ".join(content.split())
    if clean_media_text(content) != compact:
        errors.append(f"medios/{week.name}: TXT fuera de normalización")
    lines = content.splitlines()
    if any(len(line.split()) != 30 for line in lines[:-1]):
        errors.append(f"medios/{week.name}: envoltura distinta de 30 palabras")
    if lines and not 1 <= len(lines[-1].split()) <= 30:
        errors.append(f"medios/{week.name}: última línea inválida")

    csv_path = week / f"{week.name}_medios.csv"
    if not csv_path.exists():
        return len(compact.split())
    header, rows = read_csv(csv_path)
    if tuple(header) != MEDIOS_OUTPUT_COLUMNS:
        errors.append(f"medios/{week.name}: encabezado CSV incompatible")
        return len(rows)
    if historical_text:
        # Historical TXT is the accepted original corpus, not a derivation of
        # the optional CSVs. Do not pretend its dates/queries can be recovered.
        return len(compact.split())
    since = week.name[:10]
    before = (datetime.fromisoformat(since) + timedelta(days=6)).date().isoformat()
    cleaned, counters = process_media_rows(rows, since, before)
    if cleaned != rows or any(counters[key] for key in counters if key != "read"):
        errors.append(f"medios/{week.name}: CSV no satisface limpieza canónica")
    expected_txt, _, _ = build_text_content("medios", rows)
    if expected_txt != content:
        errors.append(f"medios/{week.name}: TXT no corresponde al CSV")
    return len(compact.split())


def validate_facebook(week: Path, errors: list[str], *, require_txt: bool = True) -> int:
    csv_path = week / f"{week.name}_facebook.csv"
    txt_path = week / f"{week.name}_facebook.txt"
    if not csv_path.is_file() or (require_txt and not txt_path.is_file()):
        errors.append(f"facebook/{week.name}: falta CSV o TXT")
        return 0
    header, rows = read_csv(csv_path)
    if tuple(header) != FACEBOOK_PROCESSED_COLUMNS:
        errors.append(f"facebook/{week.name}: encabezado incompatible")
        return len(rows)
    start, before = week_bounds(week.name)
    post_urls = {
        normalize_facebook_url(row.get("url", ""))
        for row in rows
        if row.get("tipo") == "POST" and row.get("url")
    }
    seen: set[tuple[str, ...]] = set()
    for index, row in enumerate(rows, start=2):
        if row.get("cuenta") not in FACEBOOK_BASE_ACCOUNTS:
            errors.append(f"facebook/{week.name}:{index}: cuenta fuera de contrato")
        if row.get("tipo") not in {"POST", "COMENTARIO"}:
            errors.append(f"facebook/{week.name}:{index}: tipo inválido")
        if not str(row.get("texto", "")).strip() and row.get("tipo") != "POST":
            errors.append(f"facebook/{week.name}:{index}: comentario vacío")
        raw_date = str(row.get("fecha", "")).strip()
        if not raw_date:
            errors.append(f"facebook/{week.name}:{index}: falta fecha verificable")
        if raw_date:
            try:
                parsed = datetime.fromisoformat(raw_date)
                parsed = (
                    parsed.replace(tzinfo=timezone.utc)
                    if parsed.tzinfo is None
                    else parsed.astimezone(timezone.utc)
                )
            except ValueError:
                parsed = None
            if parsed is None or not start <= parsed < before:
                errors.append(f"facebook/{week.name}:{index}: fecha fuera de contrato")
        if row.get("tipo") == "POST" and not row.get("url"):
            errors.append(f"facebook/{week.name}:{index}: post sin URL")
        if row.get("tipo") == "COMENTARIO":
            parent = normalize_facebook_url(row.get("post_url_padre", ""))
            if not parent or parent not in post_urls:
                errors.append(f"facebook/{week.name}:{index}: comentario huérfano")
        key = facebook_dedup_key(row)
        if key in seen:
            errors.append(f"facebook/{week.name}:{index}: duplicado")
        seen.add(key)
    expected_txt, _, _ = build_text_content("facebook", rows)
    if require_txt and expected_txt != txt_path.read_text(encoding="utf-8"):
        errors.append(f"facebook/{week.name}: TXT no corresponde al CSV")
    return len(rows)


VALIDATORS = {
    "youtube": validate_youtube,
    "twitter": validate_twitter,
    "medios": validate_medios,
    "facebook": validate_facebook,
}


def validate(
    root: Path,
    sources: Sequence[str],
    requested: set[str],
    *,
    require_same_weeks: bool,
    source_dirs: dict[str, Path] | None = None,
    csv_only: bool = False,
    historical_media_txt: bool = False,
) -> dict[str, object]:
    errors: list[str] = []
    summary: dict[str, dict[str, int]] = {}
    week_sets: dict[str, set[str]] = {}
    for source in sources:
        base = (source_dirs or {}).get(
            source,
            root / f"{source}_semanal_procesado",
        )
        if not base.is_dir():
            errors.append(f"{source}: falta directorio procesado")
            summary[source] = {"weeks": 0, "nonempty_weeks": 0, "empty_weeks": 0}
            week_sets[source] = set()
            continue
        weeks = selected_weeks(base, requested)
        if requested and not weeks:
            errors.append(f"{source}: no se encontró la semana solicitada")
        week_sets[source] = {week.name for week in weeks}
        week_counts: list[int] = []
        for week in weeks:
            try:
                if source == "medios" and historical_media_txt:
                    week_counts.append(validate_medios(week, errors, historical_text=True))
                elif csv_only and source != "medios":
                    week_counts.append(VALIDATORS[source](week, errors, require_txt=False))
                else:
                    week_counts.append(VALIDATORS[source](week, errors))
            except (OSError, ValueError) as exc:
                errors.append(f"{source}/{week.name}: {exc}")
                week_counts.append(0)
        source_summary = {
            "weeks": len(weeks),
            "nonempty_weeks": sum(count > 0 for count in week_counts),
            "empty_weeks": sum(count == 0 for count in week_counts),
        }
        if source == "medios":
            source_summary.update(
                {
                    "words": sum(week_counts),
                    "structured_weeks": sum(
                        (week / f"{week.name}_medios.csv").is_file()
                        for week in weeks
                    ),
                    "text_only_weeks": sum(
                        not (week / f"{week.name}_medios.csv").is_file()
                        for week in weeks
                    ),
                    "historical_txt_accepted": historical_media_txt,
                    "csv_content_checked": not historical_media_txt,
                }
            )
        else:
            source_summary["rows"] = sum(week_counts)
        summary[source] = source_summary
    if require_same_weeks and week_sets:
        reference = week_sets[sources[0]]
        for source in sources[1:]:
            if week_sets[source] != reference:
                errors.append(f"{source}: conjunto de semanas distinto")
    return {
        "status": "ok" if not errors else "error",
        "scope": "extractor_to_csv_with_historical_media_txt" if csv_only else "csv_to_txt",
        "root": str(root),
        "summary": summary,
        "errors": errors,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", type=Path, default=PROCESSED_DATA_DIR)
    parser.add_argument("--sources", nargs="+", choices=SOURCES, default=list(SOURCES))
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=None,
        help="Directorio de una sola fuente; requiere exactamente un --sources.",
    )
    parser.add_argument("--weeks", nargs="*", default=[])
    parser.add_argument("--extracted-dir", type=Path, default=None,
                        help="Raíz semanal común de las fuentes históricas y extraídas.")
    parser.add_argument("--csv-only", action="store_true",
                        help="Valida extractor a CSV; para Medios admite los TXT históricos existentes.")
    parser.add_argument("--accept-historical-media-txt", action="store_true",
                        help="Acepta Medios TXT como original histórico independiente del CSV; valida solo el esquema de los CSV opcionales.")
    parser.add_argument("--require-same-weeks", action="store_true")
    parser.add_argument("--audit-path", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.source_dir is not None and args.extracted_dir is not None:
        print("ERROR: no se combinan --source-dir y --extracted-dir.", file=sys.stderr)
        return 2
    if args.source_dir is not None and len(args.sources) != 1:
        print("ERROR: --source-dir requiere exactamente una fuente.", file=sys.stderr)
        return 2
    source_dirs = (
        {args.sources[0]: args.source_dir.expanduser().resolve()}
        if args.source_dir is not None
        else None
    )
    if args.extracted_dir is not None:
        source_dirs = {source: args.extracted_dir.expanduser().resolve() for source in args.sources}
    result = validate(
        (args.extracted_dir or args.processed_dir).expanduser().resolve(),
        args.sources,
        set(args.weeks),
        require_same_weeks=args.require_same_weeks,
        source_dirs=source_dirs,
        csv_only=args.csv_only,
        historical_media_txt=args.accept_historical_media_txt,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    print(rendered)
    if args.audit_path:
        args.audit_path.parent.mkdir(parents=True, exist_ok=True)
        args.audit_path.write_text(rendered + "\n", encoding="utf-8")
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
