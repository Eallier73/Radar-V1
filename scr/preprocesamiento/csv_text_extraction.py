#!/usr/bin/env python3
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from stage2_text_common import (
    CanonicalCsvSelection,
    WeekContext,
    build_word_lines,
    canonical_expected_filename,
    dedupe_keep_order,
    detect_csv_delimiter,
    load_json,
)
from text_normalizers import normalize_for_source


@dataclass
class ProcessedCorpus:
    source: str
    columns_used: list[str]
    raw_row_count: int
    useful_row_count: int
    empty_rows_discarded: int
    duplicates_removed: int
    total_words: int
    total_lines: int
    lines: list[str]
    record_types_included: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def resolve_canonical_csv(week_ctx: WeekContext) -> CanonicalCsvSelection:
    expected_filename = canonical_expected_filename(week_ctx.source, week_ctx.week_name)
    direct_path = week_ctx.week_dir / expected_filename
    if direct_path.exists():
        return CanonicalCsvSelection(
            source=week_ctx.source,
            week_name=week_ctx.week_name,
            path=direct_path,
            expected_filename=expected_filename,
            selection_criteria="exact_weekly_canonical_filename",
        )

    manifest_path = week_ctx.week_dir / "manifest.json"
    if manifest_path.exists():
        manifest_data = load_json(manifest_path)
        manifest_matches: list[Path] = []
        if isinstance(manifest_data, list):
            for item in manifest_data:
                if not isinstance(item, dict):
                    continue
                if item.get("name") != expected_filename:
                    continue
                candidate_path = Path(str(item.get("path", "")))
                if candidate_path.exists():
                    manifest_matches.append(candidate_path)
        unique_manifest_matches = list(dict.fromkeys(manifest_matches))
        if len(unique_manifest_matches) == 1:
            return CanonicalCsvSelection(
                source=week_ctx.source,
                week_name=week_ctx.week_name,
                path=unique_manifest_matches[0],
                expected_filename=expected_filename,
                selection_criteria="manifest_dataset_exact_name_match",
                warnings=[
                    "El CSV canónico publicado no estaba en la carpeta semanal; se resolvió desde manifest.json.",
                ],
            )
        if len(unique_manifest_matches) > 1:
            raise FileNotFoundError(
                f"{week_ctx.source}/{week_ctx.week_name}: manifest.json expone más de un candidato para {expected_filename}: {unique_manifest_matches}"
            )

    runs_dir = week_ctx.week_dir / "runs"
    if runs_dir.exists():
        run_matches = sorted(runs_dir.rglob(expected_filename))
        unique_run_matches = list(dict.fromkeys(run_matches))
        if len(unique_run_matches) == 1:
            return CanonicalCsvSelection(
                source=week_ctx.source,
                week_name=week_ctx.week_name,
                path=unique_run_matches[0],
                expected_filename=expected_filename,
                selection_criteria="single_runs_recursive_exact_name_match",
                warnings=[
                    "El CSV canónico publicado no estaba en la carpeta semanal; se resolvió desde runs/.",
                ],
            )
        if len(unique_run_matches) > 1:
            raise FileNotFoundError(
                f"{week_ctx.source}/{week_ctx.week_name}: runs/ contiene más de un candidato para {expected_filename}: {unique_run_matches}"
            )

    raise FileNotFoundError(
        f"{week_ctx.source}/{week_ctx.week_name}: no se encontró el CSV canónico esperado {expected_filename}"
    )


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    delimiter = detect_csv_delimiter(path)
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8-sig", errors="ignore", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        for row in reader:
            normalized_row: dict[str, str] = {}
            for key, value in (row or {}).items():
                if key is None:
                    continue
                normalized_row[key.strip().lower()] = (value or "").strip()
            rows.append(normalized_row)
    return rows


def _extract_facebook_text(row: dict[str, str], warnings: list[str]) -> str:
    record_type = (row.get("record_type") or "").strip().lower()
    if record_type and record_type not in {"comment", "post_parent"}:
        warnings.append(f"record_type no incorporado al corpus: {record_type}")
        return ""
    return row.get("text", "")


def _extract_twitter_text(row: dict[str, str], _: list[str]) -> str:
    return row.get("tweet_text", "")


def _extract_youtube_text(row: dict[str, str], _: list[str]) -> str:
    return row.get("comment_text", "")


def _extract_medios_text(row: dict[str, str], _: list[str]) -> str:
    title = row.get("article_title", "")
    article_text = row.get("article_text", "")
    return f"{title} {article_text}".strip()


SOURCE_TEXT_EXTRACTORS = {
    "facebook": (_extract_facebook_text, ["text"]),
    "twitter": (_extract_twitter_text, ["tweet_text"]),
    "youtube": (_extract_youtube_text, ["comment_text"]),
    "medios": (_extract_medios_text, ["article_title", "article_text"]),
}


def process_rows_to_corpus(
    source: str,
    rows: list[dict[str, str]],
    *,
    words_per_line: int,
) -> ProcessedCorpus:
    try:
        extractor, columns_used = SOURCE_TEXT_EXTRACTORS[source]
    except KeyError as exc:
        raise ValueError(f"Fuente sin extractor textual: {source}") from exc

    for column in columns_used:
        if not any(column in row for row in rows):
            raise ValueError(f"{source}: no se encontró la columna requerida {column!r} en el CSV.")

    warnings: list[str] = []
    record_types_included: list[str] = []
    normalized_items: list[str] = []
    useful_row_count = 0

    for row in rows:
        if source == "facebook":
            record_type = (row.get("record_type") or "").strip().lower()
            if record_type and record_type not in record_types_included:
                record_types_included.append(record_type)
        raw_text = extractor(row, warnings)
        cleaned = normalize_for_source(source, raw_text)
        if not cleaned:
            continue
        useful_row_count += 1
        normalized_items.append(cleaned)

    unique_items = dedupe_keep_order(normalized_items)
    lines = build_word_lines(unique_items, words_per_line)
    total_words = len(" ".join(unique_items).split())

    return ProcessedCorpus(
        source=source,
        columns_used=list(columns_used),
        raw_row_count=len(rows),
        useful_row_count=useful_row_count,
        empty_rows_discarded=len(rows) - useful_row_count,
        duplicates_removed=useful_row_count - len(unique_items),
        total_words=total_words,
        total_lines=len(lines),
        lines=lines,
        record_types_included=sorted(record_types_included),
        warnings=list(dict.fromkeys(warnings)),
    )
