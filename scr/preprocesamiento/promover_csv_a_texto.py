#!/usr/bin/env python3
"""Promueve los CSV semanales canónicos de Radar V1 a corpus TXT.

El CSV procesado es la referencia canónica. Este módulo sólo deriva el TXT que
vive junto a él y nunca modifica el CSV de entrada.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import sys
import tempfile
import unicodedata
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_DIR = REPO_ROOT / "scr" / "compartido"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from facebook_data_contract import FACEBOOK_PROCESSED_COLUMNS
from medios_data_contract import MEDIOS_OUTPUT_COLUMNS, build_media_txt, clean_media_text
from output_naming import build_source_filename, build_week_folder_name
from radar_paths import PROCESSED_DATA_DIR
from twitter_data_contract import TWITTER_OUTPUT_COLUMNS
from youtube_data_contract import YOUTUBE_OUTPUT_COLUMNS


SOURCE_ORDER = ("youtube", "twitter", "medios", "facebook")
SOURCE_DIRECTORIES = {
    "youtube": "youtube_semanal_procesado",
    "twitter": "twitter_semanal_procesado",
    "medios": "medios_semanal_procesado",
    "facebook": "facebook_semanal_procesado",
}
SOURCE_COLUMNS = {
    "youtube": YOUTUBE_OUTPUT_COLUMNS,
    "twitter": TWITTER_OUTPUT_COLUMNS,
    "medios": MEDIOS_OUTPUT_COLUMNS,
    "facebook": FACEBOOK_PROCESSED_COLUMNS,
}
TEXT_COLUMNS = {
    "youtube": "comment_text",
    "twitter": "text",
    "facebook": "texto",
}
WEEK_DIRECTORY_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_semana_.+$")


@dataclass
class PromotionResult:
    source: str
    week: str
    csv_path: str
    txt_path: str
    rows_read: int = 0
    records_written: int = 0
    empty_records_skipped: int = 0
    lines_written: int = 0
    csv_sha256: str = ""
    txt_sha256: str = ""
    status: str = "pending"
    error: str = ""


def normalize_social_text(value: object) -> str:
    """Normaliza sin perder acentos, ñ, números, signos, menciones o URLs."""

    text = html.unescape(str(value or ""))
    text = unicodedata.normalize("NFC", text).lower()
    return unicodedata.normalize("NFC", " ".join(text.split()))


def validate_week_directory_name(week: str) -> None:
    match = WEEK_DIRECTORY_RE.fullmatch(week)
    if not match:
        raise ValueError(f"Nombre de carpeta semanal inválido: {week}")
    start = date.fromisoformat(match.group(1))
    expected = build_week_folder_name(start, start + timedelta(days=6))
    if week != expected:
        raise ValueError(
            f"Nombre de carpeta semanal fuera de contrato: {week}; esperado {expected}"
        )


def read_canonical_csv(path: Path, source: str) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        actual = tuple(reader.fieldnames or ())
        expected = SOURCE_COLUMNS[source]
        if actual != expected:
            raise ValueError(
                f"Contrato CSV incompatible para {source}: esperado {expected}; "
                f"recibido {actual}"
            )
        return [
            {column: str(row.get(column) or "") for column in expected}
            for row in reader
        ]


def build_text_content(
    source: str,
    rows: Sequence[Mapping[str, object]],
) -> tuple[str, int, int]:
    """Devuelve contenido, registros emitidos y registros textualmente vacíos."""

    if source == "medios":
        content = build_media_txt(rows)
        useful = sum(
            bool(
                clean_media_text(
                    f"{row.get('titulo') or ''} {row.get('texto') or ''}"
                )
            )
            for row in rows
        )
        return content, useful, len(rows) - useful

    try:
        text_column = TEXT_COLUMNS[source]
    except KeyError as exc:
        raise ValueError(f"Fuente no soportada: {source}") from exc

    lines: list[str] = []
    empty = 0
    for row in rows:
        normalized = normalize_social_text(row.get(text_column, ""))
        if normalized:
            lines.append(normalized)
        else:
            empty += 1
    content = "\n".join(lines) + ("\n" if lines else "")
    return content, len(lines), empty


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
        temp_path.replace(path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def promote_csv(
    source: str,
    csv_path: Path,
    *,
    overwrite: bool = False,
    dry_run: bool = False,
) -> PromotionResult:
    week = csv_path.parent.name
    expected_name = f"{build_source_filename(week, source)}.csv"
    txt_path = csv_path.with_suffix(".txt")
    result = PromotionResult(
        source=source,
        week=week,
        csv_path=str(csv_path),
        txt_path=str(txt_path),
    )
    try:
        validate_week_directory_name(week)
        if csv_path.name != expected_name:
            raise ValueError(
                f"Nombre CSV fuera de contrato: {csv_path.name}; esperado {expected_name}"
            )
        csv_bytes = csv_path.read_bytes()
        rows = read_canonical_csv(csv_path, source)
        content, written, empty = build_text_content(source, rows)
        txt_bytes = content.encode("utf-8")
        result.rows_read = len(rows)
        result.records_written = written
        result.empty_records_skipped = empty
        result.lines_written = len(content.splitlines())
        result.csv_sha256 = _sha256_bytes(csv_bytes)
        result.txt_sha256 = _sha256_bytes(txt_bytes)

        if txt_path.exists():
            if txt_path.read_bytes() == txt_bytes:
                result.status = "unchanged"
                return result
            if not overwrite:
                raise FileExistsError(
                    f"El TXT existe con contenido distinto: {txt_path}. "
                    "Usa --overwrite para reemplazarlo de forma explícita."
                )
        if not dry_run:
            _write_atomic(txt_path, content)
        result.status = "success_dry_run" if dry_run else "written"
    except Exception as exc:
        result.status = "error"
        result.error = f"{type(exc).__name__}: {exc}"
    return result


def normalize_sources(values: Sequence[str] | None) -> tuple[str, ...]:
    if not values:
        return SOURCE_ORDER
    requested: list[str] = []
    for value in values:
        requested.extend(part.strip().lower() for part in value.split(",") if part.strip())
    unknown = sorted(set(requested) - set(SOURCE_ORDER))
    if unknown:
        raise ValueError(f"Fuentes desconocidas: {', '.join(unknown)}")
    return tuple(source for source in SOURCE_ORDER if source in requested)


def _source_root(processed_dir: Path, source: str, source_dir: Path | None) -> Path:
    if source_dir is not None:
        return source_dir
    return processed_dir / SOURCE_DIRECTORIES[source]


def discover_csv_files(
    processed_dir: Path,
    sources: Sequence[str],
    *,
    source_dir: Path | None,
    since: str | None,
    before: str | None,
    weeks: Sequence[str],
    all_weeks: bool,
) -> tuple[list[tuple[str, Path]], list[str]]:
    if source_dir is not None and len(sources) != 1:
        raise ValueError("--source-dir requiere exactamente una fuente.")
    if all_weeks and (since or before or weeks):
        raise ValueError("--all-weeks no se combina con filtros de semana.")
    if bool(since) != bool(before):
        raise ValueError("--since y --before deben indicarse juntos.")
    if not all_weeks and not weeks and not since:
        raise ValueError("Indica --all-weeks, --weeks o --since/--before.")

    exact_week = build_week_folder_name(since, before) if since and before else None
    filters = {value.strip() for value in weeks if value.strip()}
    selected: list[tuple[str, Path]] = []
    missing: list[str] = []
    for source in sources:
        root = _source_root(processed_dir, source, source_dir)
        if exact_week:
            week_names = [exact_week]
        else:
            week_names = [
                path.name
                for path in sorted(root.iterdir())
                if path.is_dir()
                and WEEK_DIRECTORY_RE.fullmatch(path.name)
                and (
                    all_weeks
                    or path.name in filters
                    or path.name[:10] in filters
                )
            ] if root.is_dir() else []
        if not week_names:
            missing.append(f"{source}: no se encontraron semanas seleccionadas en {root}")
            continue
        for week in week_names:
            path = root / week / f"{build_source_filename(week, source)}.csv"
            if path.is_file():
                selected.append((source, path))
            elif not all_weeks:
                missing.append(f"{source}/{week}: falta {path.name}")
    return selected, missing


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", type=Path, default=PROCESSED_DATA_DIR)
    parser.add_argument("--source-dir", type=Path, default=None)
    parser.add_argument("--sources", nargs="+", default=list(SOURCE_ORDER))
    parser.add_argument("--since", default=None)
    parser.add_argument("--before", default=None)
    parser.add_argument("--weeks", nargs="*", default=[])
    parser.add_argument("--all-weeks", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--audit-path", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        sources = normalize_sources(args.sources)
        selected, missing = discover_csv_files(
            args.processed_dir.expanduser().resolve(),
            sources,
            source_dir=args.source_dir.expanduser().resolve() if args.source_dir else None,
            since=args.since,
            before=args.before,
            weeks=args.weeks,
            all_weeks=args.all_weeks,
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    results = [
        promote_csv(source, path, overwrite=args.overwrite, dry_run=args.dry_run)
        for source, path in selected
    ]
    for result in results:
        print(
            f"[{result.source}] {result.week}: {result.status} | "
            f"filas={result.rows_read} líneas={result.lines_written}"
        )
        if result.error:
            print(f"  ERROR: {result.error}", file=sys.stderr)
    for message in missing:
        print(f"ERROR: {message}", file=sys.stderr)

    audit = {
        "contract": {
            "csv_is_canonical": True,
            "txt_next_to_csv": True,
            "social_record_boundary": "one_csv_row_per_txt_line",
            "social_unicode": "NFC_lowercase_preserve_accents_enye_numbers_punctuation",
            "medios": "titulo_mas_texto_ascii_historical_wrap_30_words",
        },
        "results": [asdict(result) for result in results],
        "missing": missing,
    }
    if args.audit_path:
        audit_path = args.audit_path.expanduser().resolve()
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 1 if missing or any(result.status == "error" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
