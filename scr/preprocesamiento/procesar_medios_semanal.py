#!/usr/bin/env python3
"""Convierte el CSV semanal de Medios en CSV y TXT procesados reproducibles."""

from __future__ import annotations

import argparse
import csv
import os
import sys
import tempfile
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_DIR = REPO_ROOT / "scr" / "compartido"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from medios_data_contract import (
    MEDIOS_OUTPUT_COLUMNS,
    build_media_txt,
    process_media_rows,
)
from output_naming import build_source_filename, build_week_folder_name
from radar_paths import EXTRACTED_DATA_DIR, PROCESSED_DATA_DIR


DEFAULT_OUTPUT_DIR = PROCESSED_DATA_DIR / "medios_semanal_procesado"


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"No existe el CSV semanal de Medios: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = tuple(reader.fieldnames or ())
        if fieldnames != MEDIOS_OUTPUT_COLUMNS:
            raise ValueError(
                f"Contrato CSV de Medios inesperado en {path}: {fieldnames}"
            )
        return list(reader)


def _write_csv_atomic(path: Path, rows: Sequence[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(
            descriptor,
            "w",
            encoding="utf-8-sig",
            newline="",
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=MEDIOS_OUTPUT_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        temp_path.replace(path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        temp_path.replace(path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def process_week(
    since: str,
    before: str,
    *,
    input_dir: Path = EXTRACTED_DATA_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> tuple[Path, Path, dict[str, int]]:
    week_name = build_week_folder_name(since, before)
    base_name = build_source_filename(week_name, "medios")
    input_csv = input_dir / week_name / f"{base_name}.csv"
    output_week = output_dir / week_name
    output_csv = output_week / f"{base_name}.csv"
    output_txt = output_week / f"{base_name}.txt"

    rows = _read_rows(input_csv)
    processed_rows, counters = process_media_rows(rows, since, before)
    _write_csv_atomic(output_csv, processed_rows)
    _write_text_atomic(output_txt, build_media_txt(processed_rows))
    return output_csv, output_txt, counters


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Procesa el CSV semanal de Medios hacia su corpus canónico."
    )
    parser.add_argument("--since", required=True, help="Primer día YYYY-MM-DD")
    parser.add_argument("--before", required=True, help="Último día YYYY-MM-DD")
    parser.add_argument("--input-dir", type=Path, default=EXTRACTED_DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        output_csv, output_txt, counters = process_week(
            args.since,
            args.before,
            input_dir=args.input_dir.expanduser().resolve(),
            output_dir=args.output_dir.expanduser().resolve(),
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Medios procesados: {counters['read']} filas leídas")
    print(f"CSV: {output_csv}")
    print(f"TXT: {output_txt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
