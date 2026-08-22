#!/usr/bin/env python3
"""Homologa el material semanal existente de Twitter/X sin modificar el raw.

Cada registro se conserva solamente si tiene texto y ``published_at`` cae en el
intervalo UTC estricto indicado por su carpeta: ``[lunes, lunes siguiente)``.
Los dos esquemas históricos se proyectan al mismo contrato y se deduplican por
``tweet_id``; cuando falta el identificador se usa autor+fecha+texto.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_DIR = REPO_ROOT / "scr" / "compartido"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from radar_paths import EXTRACTED_DATA_DIR, PROCESSED_DATA_DIR
from twitter_data_contract import (
    TWITTER_OUTPUT_COLUMNS,
    deduplicate_twitter_rows,
    detect_twitter_schema,
    parse_twitter_datetime,
    project_twitter_row,
)


DEFAULT_INPUT_DIR = EXTRACTED_DATA_DIR
DEFAULT_OUTPUT_DIR = PROCESSED_DATA_DIR / "twitter_semanal_limpio"
WEEK_DIR_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_semana_.+$")
OUTPUT_COLUMNS = list(TWITTER_OUTPUT_COLUMNS)


@dataclass
class WeekCleaningResult:
    week_name: str
    week_start_utc: str
    week_before_utc: str
    input_path: str
    output_path: str
    input_sha256: str
    source_columns: list[str]
    source_schema: str = ""
    output_columns: list[str] | None = None
    rows_read: int = 0
    incompatible_nonempty_lines: int = 0
    rows_after_week_filter: int = 0
    rows_kept: int = 0
    rows_removed_before_week: int = 0
    rows_removed_after_week: int = 0
    rows_removed_invalid_date: int = 0
    rows_removed_empty_text: int = 0
    rows_removed_duplicates: int = 0
    status: str = "pending"
    error: str = ""

    @property
    def rows_removed_total(self) -> int:
        return (
            self.rows_removed_before_week
            + self.rows_removed_after_week
            + self.rows_removed_invalid_date
            + self.rows_removed_empty_text
            + self.rows_removed_duplicates
        )

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["rows_removed_total"] = self.rows_removed_total
        return payload


def week_bounds_from_name(week_name: str) -> tuple[datetime, datetime]:
    match = WEEK_DIR_RE.fullmatch(week_name)
    if not match:
        raise ValueError(f"Nombre de carpeta semanal inválido: {week_name}")
    start = datetime.strptime(match.group(1), "%Y-%m-%d").replace(
        tzinfo=timezone.utc
    )
    return start, start + timedelta(days=7)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = [str(name or "").strip() for name in (reader.fieldnames or [])]
        reader.fieldnames = fieldnames
        rows = [
            {field: str(row.get(field) or "") for field in fieldnames}
            for row in reader
        ]
    return fieldnames, rows


def count_nonempty_lines(path: Path) -> int:
    with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
        return sum(bool(line.strip()) for line in handle)


def write_csv_atomic(
    output_path: Path,
    *,
    rows: Sequence[dict[str, object]],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        dir=output_path.parent,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        temp_path.replace(output_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def clean_week_file(
    input_path: Path,
    output_path: Path,
    *,
    dry_run: bool,
    overwrite: bool,
) -> WeekCleaningResult:
    week_name = input_path.parent.name
    week_start, week_before = week_bounds_from_name(week_name)
    result = WeekCleaningResult(
        week_name=week_name,
        week_start_utc=week_start.isoformat(),
        week_before_utc=week_before.isoformat(),
        input_path=str(input_path),
        output_path=str(output_path),
        input_sha256=sha256_file(input_path),
        source_columns=[],
        output_columns=OUTPUT_COLUMNS.copy(),
    )

    try:
        fieldnames, raw_rows = read_rows(input_path)
        result.source_columns = fieldnames
        schema = detect_twitter_schema(fieldnames)
        if schema is None:
            result.incompatible_nonempty_lines = count_nonempty_lines(input_path)
            result.error = "El archivo no contiene un esquema estructurado de Twitter."
            if dry_run:
                result.status = "success_empty_incompatible_dry_run"
                return result
            if output_path.exists() and not overwrite:
                result.status = "skip_existing"
                return result
            write_csv_atomic(output_path, rows=[])
            result.status = "success_empty_incompatible"
            return result

        result.source_schema = schema
        result.rows_read = len(raw_rows)
        projected = [project_twitter_row(row, schema=schema) for row in raw_rows]

        in_week: list[dict[str, str]] = []
        for row in projected:
            published_at = parse_twitter_datetime(row["published_at"])
            if published_at is None:
                result.rows_removed_invalid_date += 1
            elif published_at < week_start:
                result.rows_removed_before_week += 1
            elif published_at >= week_before:
                result.rows_removed_after_week += 1
            else:
                in_week.append(row)
        result.rows_after_week_filter = len(in_week)

        with_text = [row for row in in_week if row["text"].strip()]
        result.rows_removed_empty_text = len(in_week) - len(with_text)
        unique_rows, removed_duplicates = deduplicate_twitter_rows(with_text)
        result.rows_removed_duplicates = removed_duplicates
        result.rows_kept = len(unique_rows)

        if dry_run:
            result.status = "success_dry_run"
            return result
        if output_path.exists() and not overwrite:
            result.status = "skip_existing"
            return result
        write_csv_atomic(output_path, rows=unique_rows)
        result.status = "success"
        return result
    except Exception as exc:
        result.status = "error_processing"
        result.error = f"{type(exc).__name__}: {exc}"
        return result


def discover_twitter_files(input_dir: Path, weeks: set[str]) -> list[Path]:
    files: list[Path] = []
    if not input_dir.is_dir():
        return files
    for week_dir in sorted(input_dir.iterdir()):
        if not week_dir.is_dir() or not WEEK_DIR_RE.fullmatch(week_dir.name):
            continue
        if weeks and week_dir.name[:10] not in weeks and week_dir.name not in weeks:
            continue
        candidates = sorted(week_dir.glob("*_twitter.csv"))
        if len(candidates) == 1:
            files.append(candidates[0])
    return files


def build_summary(results: Sequence[WeekCleaningResult]) -> dict[str, int]:
    return {
        "weeks_discovered": len(results),
        "weeks_success": sum(result.status.startswith("success") for result in results),
        "weeks_empty_incompatible": sum(
            "empty_incompatible" in result.status for result in results
        ),
        "weeks_skipped": sum(result.status.startswith("skip") for result in results),
        "weeks_error": sum(result.status.startswith("error") for result in results),
        "rows_read": sum(result.rows_read for result in results),
        "incompatible_nonempty_lines": sum(
            result.incompatible_nonempty_lines for result in results
        ),
        "rows_after_week_filter": sum(
            result.rows_after_week_filter for result in results
        ),
        "rows_kept": sum(result.rows_kept for result in results),
        "rows_removed_before_week": sum(
            result.rows_removed_before_week for result in results
        ),
        "rows_removed_after_week": sum(
            result.rows_removed_after_week for result in results
        ),
        "rows_removed_invalid_date": sum(
            result.rows_removed_invalid_date for result in results
        ),
        "rows_removed_empty_text": sum(
            result.rows_removed_empty_text for result in results
        ),
        "rows_removed_duplicates": sum(
            result.rows_removed_duplicates for result in results
        ),
        "rows_removed_total": sum(result.rows_removed_total for result in results),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Proyecta los dos esquemas históricos de Twitter a un contrato común, "
            "filtra por [lunes UTC, lunes siguiente UTC), elimina filas sin texto "
            "y deduplica por tweet_id con fallback autor+fecha+texto."
        )
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--weeks", nargs="*", default=[])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    files = discover_twitter_files(args.input_dir, set(args.weeks))
    if not files:
        print(f"No se encontraron CSV semanales de Twitter en {args.input_dir}")
        return 1

    results: list[WeekCleaningResult] = []
    for input_path in files:
        output_path = args.output_dir / input_path.parent.name / input_path.name
        result = clean_week_file(
            input_path,
            output_path,
            dry_run=args.dry_run,
            overwrite=args.overwrite,
        )
        results.append(result)
        print(
            f"[{result.status}] {result.week_name}: "
            f"leídas={result.rows_read} conservadas={result.rows_kept} "
            f"eliminadas={result.rows_removed_total}"
        )
        if result.error:
            print(f"  {result.error}")

    summary = build_summary(results)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if not args.dry_run:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        audit_path = args.output_dir / "auditoria_twitter_semanal.json"
        audit_path.write_text(
            json.dumps(
                {
                    "rule": "published_at pertenece a [lunes UTC, lunes siguiente UTC)",
                    "empty_text_policy": "se elimina el registro sin texto",
                    "deduplication_key": {
                        "primary": ["tweet_id"],
                        "fallback": ["author", "published_at", "text_normalizado"],
                    },
                    "query_policy": "query_raw se conserva sin homologar en esta fase",
                    "output_columns": OUTPUT_COLUMNS,
                    "input_dir": str(args.input_dir),
                    "output_dir": str(args.output_dir),
                    "summary": summary,
                    "weeks": [result.to_dict() for result in results],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"Auditoría: {audit_path}")

    return 1 if summary["weeks_error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
