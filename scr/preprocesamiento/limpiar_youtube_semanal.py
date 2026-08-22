#!/usr/bin/env python3
"""Homologa temporalmente el material semanal existente de YouTube.

La primera regla metodológica de esta etapa es estricta: un comentario solo se
conserva si ``published_at`` cae dentro de la semana indicada por la carpeta,
usando el intervalo UTC ``[lunes 00:00, lunes siguiente 00:00)``.

El raw nunca se modifica. Los CSV filtrados se escriben en la capa de datos
procesados con un único contrato de tres columnas: ``comment_text``,
``published_at`` y ``query``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_DIR = REPO_ROOT / "scr" / "compartido"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from radar_paths import EXTRACTED_DATA_DIR, PROCESSED_DATA_DIR
from youtube_data_contract import (
    YOUTUBE_OUTPUT_COLUMNS,
    deduplicate_youtube_rows,
    filter_youtube_rows_to_interval,
    parse_youtube_datetime,
    project_youtube_rows,
)


DEFAULT_INPUT_DIR = EXTRACTED_DATA_DIR
DEFAULT_OUTPUT_DIR = PROCESSED_DATA_DIR / "youtube_semanal_limpio"
WEEK_DIR_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_semana_.+$")
REQUIRED_COLUMNS = {"comment_text", "published_at"}
OUTPUT_COLUMNS = list(YOUTUBE_OUTPUT_COLUMNS)


@dataclass
class WeekCleaningResult:
    week_name: str
    week_start_utc: str
    week_before_utc: str
    input_path: str
    output_path: str
    input_sha256: str
    contract_columns: list[str]
    output_columns: list[str]
    rows_read: int = 0
    rows_after_week_filter: int = 0
    rows_kept: int = 0
    rows_removed_before_week: int = 0
    rows_removed_after_week: int = 0
    rows_removed_invalid_date: int = 0
    rows_removed_duplicates: int = 0
    status: str = "pending"
    error: str = ""

    @property
    def rows_removed_total(self) -> int:
        return (
            self.rows_removed_before_week
            + self.rows_removed_after_week
            + self.rows_removed_invalid_date
            + self.rows_removed_duplicates
        )

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["rows_removed_total"] = self.rows_removed_total
        return payload


def parse_published_at(value: str) -> datetime | None:
    return parse_youtube_datetime(value)


def week_bounds_from_name(week_name: str) -> tuple[datetime, datetime]:
    match = WEEK_DIR_RE.fullmatch(week_name)
    if not match:
        raise ValueError(f"Nombre de carpeta semanal inválido: {week_name}")
    start = datetime.strptime(match.group(1), "%Y-%m-%d").replace(
        tzinfo=timezone.utc
    )
    return start, start + timedelta(days=7)


def detect_delimiter(path: Path) -> str:
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        header = handle.readline()
    return ";" if header.count(";") > header.count(",") else ","


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    delimiter = detect_delimiter(path)
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        fieldnames = [str(name or "").strip() for name in (reader.fieldnames or [])]
        reader.fieldnames = fieldnames
        rows = [
            {field: (row.get(field) or "") for field in fieldnames}
            for row in reader
        ]
    return fieldnames, rows


def filter_rows_to_week(
    rows: Sequence[dict[str, str]],
    *,
    week_start: datetime,
    week_before: datetime,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    kept, counters = filter_youtube_rows_to_interval(
        rows,
        week_start=week_start,
        week_before=week_before,
    )
    return [dict(row) for row in kept], counters


def deduplicate_rows(
    rows: Sequence[dict[str, str]],
) -> tuple[list[dict[str, str]], int]:
    unique, removed = deduplicate_youtube_rows(rows)
    return [dict(row) for row in unique], removed


def write_csv_atomic(
    output_path: Path,
    *,
    fieldnames: Sequence[str],
    rows: Sequence[dict[str, str]],
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
            writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
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
        contract_columns=[],
        output_columns=list(OUTPUT_COLUMNS),
    )

    try:
        fieldnames, rows = read_rows(input_path)
        result.contract_columns = fieldnames
        result.rows_read = len(rows)
        missing_columns = sorted(REQUIRED_COLUMNS.difference(fieldnames))
        if missing_columns:
            result.status = "error_incompatible_csv"
            result.error = f"Faltan columnas requeridas: {', '.join(missing_columns)}"
            return result

        kept, counters = filter_rows_to_week(
            rows,
            week_start=week_start,
            week_before=week_before,
        )
        result.rows_after_week_filter = len(kept)
        result.rows_removed_before_week = counters["before"]
        result.rows_removed_after_week = counters["after"]
        result.rows_removed_invalid_date = counters["invalid"]

        projected_rows = project_youtube_rows(kept)
        deduplicated_rows, duplicates_removed = deduplicate_rows(projected_rows)
        result.rows_removed_duplicates = duplicates_removed
        result.rows_kept = len(deduplicated_rows)

        if dry_run:
            result.status = "success_dry_run"
            return result
        if output_path.exists() and not overwrite:
            result.status = "skip_existing"
            return result

        write_csv_atomic(
            output_path,
            fieldnames=OUTPUT_COLUMNS,
            rows=deduplicated_rows,
        )
        result.status = "success"
        return result
    except Exception as exc:
        result.status = "error_processing"
        result.error = f"{type(exc).__name__}: {exc}"
        return result


def discover_youtube_files(input_dir: Path, weeks: set[str]) -> list[Path]:
    files: list[Path] = []
    if not input_dir.is_dir():
        return files
    for week_dir in sorted(input_dir.iterdir()):
        if not week_dir.is_dir() or not WEEK_DIR_RE.fullmatch(week_dir.name):
            continue
        if weeks and week_dir.name[:10] not in weeks and week_dir.name not in weeks:
            continue
        candidates = sorted(week_dir.glob("*_youtube.csv"))
        if len(candidates) != 1:
            continue
        files.append(candidates[0])
    return files


def build_summary(results: Sequence[WeekCleaningResult]) -> dict[str, object]:
    return {
        "weeks_discovered": len(results),
        "weeks_success": sum(result.status.startswith("success") for result in results),
        "weeks_skipped": sum(result.status.startswith("skip") for result in results),
        "weeks_error": sum(result.status.startswith("error") for result in results),
        "rows_read": sum(result.rows_read for result in results),
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
        "rows_removed_duplicates": sum(
            result.rows_removed_duplicates for result in results
        ),
        "rows_removed_total": sum(result.rows_removed_total for result in results),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Filtra el raw semanal de YouTube por published_at usando el intervalo "
            "estricto [inicio de carpeta, inicio + 7 días) y proyecta el resultado "
            "a comment_text,published_at,query; después deduplica por texto+fecha."
        )
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--weeks",
        nargs="*",
        default=[],
        help="Fechas YYYY-MM-DD o nombres completos de carpetas semanales.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Reemplaza salidas procesadas existentes; nunca modifica el raw.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    files = discover_youtube_files(args.input_dir, set(args.weeks))
    if not files:
        print(f"No se encontraron CSV semanales de YouTube en {args.input_dir}")
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
        audit_path = args.output_dir / "auditoria_youtube_semanal.json"
        audit_path.write_text(
            json.dumps(
                {
                    "rule": "published_at pertenece a [lunes UTC, lunes siguiente UTC)",
                    "deduplication_key": ["comment_text", "published_at"],
                    "deduplication_query_policy": "query no participa; se conserva la primera aparición",
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
