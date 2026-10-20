#!/usr/bin/env python3
"""Homologa Facebook con fechas semanales verificables y exclusiones trazables."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass
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
    canonicalize_facebook_rows,
    detect_facebook_schema,
)
from output_naming import build_source_filename, build_week_folder_name
from radar_paths import DATA_DIR, EXTRACTED_DATA_DIR, PROCESSED_DATA_DIR


DEFAULT_INPUT_DIR = EXTRACTED_DATA_DIR
DEFAULT_OUTPUT_DIR = PROCESSED_DATA_DIR / "facebook_semanal_procesado"
DEFAULT_EXCLUDED_DIR = DATA_DIR / "radar_historico_excluido" / "facebook"
WEEK_DIR_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_semana_.+$")


@dataclass
class WeekResult:
    week_name: str
    input_path: str
    output_csv: str
    input_sha256: str
    excluded_path: str = ""
    excluded_rows: int = 0
    source_schema: str = ""
    rows_read: int = 0
    rows_kept: int = 0
    posts_kept: int = 0
    comments_kept: int = 0
    rows_removed_non_base_account: int = 0
    rows_removed_empty_text: int = 0
    posts_kept_without_text: int = 0
    rows_removed_duplicates: int = 0
    rows_removed_orphan_comments: int = 0
    rows_date_outside_week: int = 0
    rows_removed_unknown_date: int = 0
    rows_removed_invalid_date: int = 0
    rows_removed_invalid_type: int = 0
    rows_removed_missing_post_url: int = 0
    rows_removed_unknown_account: int = 0
    dates_valid: int = 0
    dates_unknown: int = 0
    dates_invalid: int = 0
    status: str = "pending"
    error: str = ""

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["rows_removed_total"] = self.rows_read - self.rows_kept
        return payload


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_facebook_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        first_line = handle.readline()
        handle.seek(0)
        delimiter = ";" if first_line.count(";") > first_line.count(",") else ","
        reader = csv.DictReader(handle, delimiter=delimiter)
        fieldnames = [str(field or "").strip() for field in (reader.fieldnames or [])]
        reader.fieldnames = fieldnames
        rows = [
            {field: str(row.get(field) or "") for field in fieldnames}
            for row in reader
        ]
    return fieldnames, rows


def project_and_clean_rows(
    raw_rows: Sequence[dict[str, str]],
    *,
    schema: str,
    week_name: str,
    exclusions: list[dict[str, object]] | None = None,
) -> tuple[list[dict[str, str]], Counter[str]]:
    week_match = WEEK_DIR_RE.fullmatch(week_name)
    if not week_match:
        raise ValueError(f"Nombre de semana inválido: {week_name}")
    week_start = datetime.strptime(week_match.group(1), "%Y-%m-%d").replace(
        tzinfo=timezone.utc
    )
    week_before = week_start + timedelta(days=7)

    return canonicalize_facebook_rows(
        raw_rows, schema=schema, week_start=week_start,
        week_before=week_before, exclusions=exclusions,
    )


def _write_csv_atomic(path: Path, rows: Sequence[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FACEBOOK_PROCESSED_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        temp_path.replace(path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def process_file(
    input_path: Path, output_dir: Path, *, dry_run: bool = False,
    excluded_dir: Path = DEFAULT_EXCLUDED_DIR,
) -> WeekResult:
    week_name = input_path.parent.name
    base_name = build_source_filename(week_name, "facebook")
    output_week = output_dir / week_name
    output_csv = output_week / f"{base_name}.csv"
    result = WeekResult(
        week_name=week_name,
        input_path=str(input_path),
        output_csv=str(output_csv),
        input_sha256=sha256_file(input_path),
    )
    try:
        fieldnames, raw_rows = read_facebook_rows(input_path)
        schema = detect_facebook_schema(fieldnames)
        if schema is None:
            raise ValueError(f"Esquema Facebook no reconocido: {fieldnames}")
        result.source_schema = schema
        exclusions: list[dict[str, object]] = []
        cleaned, counters = project_and_clean_rows(
            raw_rows,
            schema=schema,
            week_name=week_name,
            exclusions=exclusions,
        )
        result.rows_read = counters["read"]
        result.rows_kept = counters["kept"]
        result.posts_kept = counters["posts"]
        result.comments_kept = counters["comments"]
        result.rows_removed_non_base_account = counters["non_base_account"]
        result.rows_removed_empty_text = counters["empty_text"]
        result.posts_kept_without_text = counters["posts_without_text"]
        result.rows_removed_duplicates = counters["duplicates"]
        result.rows_removed_orphan_comments = counters["orphan_comments"]
        result.rows_date_outside_week = counters["date_outside_week"]
        result.rows_removed_unknown_date = counters["date_unknown"]
        result.rows_removed_invalid_date = counters["date_invalid"]
        result.rows_removed_invalid_type = counters["invalid_type"]
        result.rows_removed_missing_post_url = counters["missing_post_url"]
        result.rows_removed_unknown_account = counters["unknown_account"]
        result.dates_valid = counters["dates_valid"]
        result.dates_unknown = counters["dates_unknown"]
        result.dates_invalid = counters["dates_invalid"]
        result.excluded_rows = len(exclusions)
        if result.rows_read != result.rows_kept + result.excluded_rows:
            raise ValueError("Las filas conservadas y excluidas no reconcilian con la entrada")
        if exclusions:
            excluded_path = excluded_dir / week_name / f"facebook_excluido_{result.input_sha256[:16]}.jsonl"
            result.excluded_path = str(excluded_path)
            if not dry_run:
                excluded_path.parent.mkdir(parents=True, exist_ok=True)
                payload = "".join(
                    json.dumps({
                        "source_week": week_name,
                        "source_file": input_path.name,
                        "source_sha256": result.input_sha256,
                        **record,
                    }, ensure_ascii=False) + "\n"
                    for record in exclusions
                )
                # Never overwrite a different record of the original input.
                if excluded_path.exists() and excluded_path.read_text(encoding="utf-8") != payload:
                    raise ValueError(f"Archivo de exclusiones distinto: {excluded_path}")
                excluded_path.write_text(payload, encoding="utf-8")
        if not dry_run:
            _write_csv_atomic(output_csv, cleaned)
        result.status = "success_dry_run" if dry_run else "success"
    except Exception as exc:
        result.status = "error"
        result.error = f"{type(exc).__name__}: {exc}"
    return result


def discover_files(input_dir: Path, weeks: set[str]) -> list[Path]:
    files: list[Path] = []
    if not input_dir.is_dir():
        return files
    for week_dir in sorted(input_dir.iterdir()):
        if not week_dir.is_dir() or not WEEK_DIR_RE.fullmatch(week_dir.name):
            continue
        if weeks and week_dir.name not in weeks and week_dir.name[:10] not in weeks:
            continue
        canonical = week_dir / f"{build_source_filename(week_dir.name, 'facebook')}.csv"
        if canonical.is_file():
            files.append(canonical)
    return files


def build_audit(results: Sequence[WeekResult]) -> dict[str, object]:
    return {
        "contract": {
            "accounts": list(FACEBOOK_BASE_ACCOUNTS),
            "columns": list(FACEBOOK_PROCESSED_COLUMNS),
            "excluded_original_rows_preserved": True,
            "unknown_dates_preserved_as_blank": False,
            "unknown_dates_excluded": True,
            "invalid_dates_excluded": True,
            "unknown_accounts_removed": True,
            "historical_dates_outside_folder_removed": True,
            "future_extractors_filter_requested_week": True,
            "orphan_comments_removed": True,
        },
        "summary": {
            "weeks": len(results),
            "weeks_success": sum(result.status.startswith("success") for result in results),
            "weeks_error": sum(result.status == "error" for result in results),
            "empty_weeks": [r.week_name for r in results if r.status.startswith("success") and not r.rows_kept],
            "excluded_rows": sum(r.excluded_rows for r in results),
            "rows_read": sum(result.rows_read for result in results),
            "rows_kept": sum(result.rows_kept for result in results),
            "posts_kept": sum(result.posts_kept for result in results),
            "comments_kept": sum(result.comments_kept for result in results),
            "rows_removed_non_base_account": sum(result.rows_removed_non_base_account for result in results),
            "rows_removed_empty_text": sum(result.rows_removed_empty_text for result in results),
            "posts_kept_without_text": sum(
                result.posts_kept_without_text for result in results
            ),
            "rows_removed_duplicates": sum(result.rows_removed_duplicates for result in results),
            "rows_removed_orphan_comments": sum(
                result.rows_removed_orphan_comments for result in results
            ),
            "rows_date_outside_week": sum(result.rows_date_outside_week for result in results),
            "rows_removed_unknown_date": sum(r.rows_removed_unknown_date for r in results),
            "rows_removed_invalid_date": sum(r.rows_removed_invalid_date for r in results),
            "rows_removed_invalid_type": sum(r.rows_removed_invalid_type for r in results),
            "rows_removed_missing_post_url": sum(r.rows_removed_missing_post_url for r in results),
            "rows_removed_unknown_account": sum(
                result.rows_removed_unknown_account for result in results
            ),
            "dates_valid": sum(result.dates_valid for result in results),
            "dates_unknown": sum(result.dates_unknown for result in results),
            "dates_invalid": sum(result.dates_invalid for result in results),
        },
        "weeks": [result.to_dict() for result in results],
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Unifica y limpia el corpus semanal de Facebook.")
    parser.add_argument("--since", default=None, help="Primer día YYYY-MM-DD")
    parser.add_argument("--before", default=None, help="Último día YYYY-MM-DD")
    parser.add_argument("--weeks", nargs="*", default=[])
    parser.add_argument("--all-weeks", action="store_true")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--excluded-dir", type=Path, default=DEFAULT_EXCLUDED_DIR)
    parser.add_argument("--audit-path", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.all_weeks and (args.since or args.before or args.weeks):
        print("ERROR: --all-weeks no se combina con filtros de semana.", file=sys.stderr)
        return 2
    if bool(args.since) != bool(args.before):
        print("ERROR: --since y --before deben indicarse juntos.", file=sys.stderr)
        return 2

    weeks = set(args.weeks)
    if args.since and args.before:
        week_name = build_week_folder_name(args.since, args.before)
        weeks.add(week_name)
    if not args.all_weeks and not weeks:
        print("ERROR: indica --all-weeks, --weeks o --since/--before.", file=sys.stderr)
        return 2

    input_dir = args.input_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    files = discover_files(input_dir, weeks)
    if not files:
        print("ERROR: no se encontraron CSV semanales de Facebook.", file=sys.stderr)
        return 1

    results = [process_file(
        path, output_dir, dry_run=args.dry_run,
        excluded_dir=args.excluded_dir.expanduser().resolve(),
    ) for path in files]
    audit = build_audit(results)
    if not args.dry_run or args.audit_path:
        audit_path = args.audit_path or (output_dir / "auditoria_facebook_semanal_procesado.json")
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    summary = audit["summary"]
    print(f"Semanas procesadas: {summary['weeks_success']}/{summary['weeks']}")
    print(f"Filas: {summary['rows_read']} leídas, {summary['rows_kept']} conservadas")
    print(f"Posts: {summary['posts_kept']} | Comentarios: {summary['comments_kept']}")
    print(f"Exclusiones conservadas: {summary['excluded_rows']} | Semanas sin material verificable: {len(summary['empty_weeks'])}")
    print(f"Salida: {output_dir}")
    return 1 if summary["weeks_error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
