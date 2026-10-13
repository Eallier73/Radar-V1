#!/usr/bin/env python3
"""Crea la vista histórica uniforme de Twitter para las cuentas objetivo."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_DIR = REPO_ROOT / "scr" / "compartido"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from radar_paths import PROCESSED_DATA_DIR
from twitter_data_contract import (
    TWITTER_OUTPUT_COLUMNS,
    filter_twitter_rows_to_account_scope,
)


DEFAULT_INPUT_DIR = PROCESSED_DATA_DIR / "twitter_semanal_limpio"
DEFAULT_OUTPUT_DIR = PROCESSED_DATA_DIR / "twitter_semanal_procesado"
OUTPUT_COLUMNS = list(TWITTER_OUTPUT_COLUMNS)


def discover_files(input_dir: Path) -> list[Path]:
    return sorted(input_dir.glob("*/*_twitter.csv"))


def read_canonical_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != OUTPUT_COLUMNS:
            raise ValueError(
                f"Contrato Twitter inesperado en {path}: {reader.fieldnames}"
            )
        return list(reader)


def write_csv_atomic(path: Path, rows: Sequence[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=OUTPUT_COLUMNS,
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)
        temp_path.replace(path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def filter_week_file(
    input_path: Path,
    output_path: Path,
    *,
    overwrite: bool,
) -> dict[str, object]:
    rows = read_canonical_rows(input_path)
    kept, removed = filter_twitter_rows_to_account_scope(rows)
    status = "success"
    if output_path.exists() and not overwrite:
        status = "skip_existing"
    else:
        write_csv_atomic(output_path, kept)
    return {
        "week_name": input_path.parent.name,
        "input_path": str(input_path),
        "output_path": str(output_path),
        "rows_read": len(rows),
        "rows_kept": len(kept),
        "rows_removed": removed,
        "status": status,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Conserva del Twitter canónico las consultas de @TampicoGob y "
            "@MonicaVTampico, junto con sus respuestas vinculadas."
        )
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    files = discover_files(args.input_dir)
    if not files:
        print(f"No se encontraron CSV canónicos de Twitter en {args.input_dir}")
        return 1

    results = []
    for input_path in files:
        output_path = args.output_dir / input_path.parent.name / input_path.name
        result = filter_week_file(input_path, output_path, overwrite=args.overwrite)
        results.append(result)
        print(
            f"[{result['status']}] {result['week_name']}: "
            f"leídas={result['rows_read']} conservadas={result['rows_kept']}"
        )

    summary = {
        "weeks": len(results),
        "weeks_with_rows": sum(result["rows_kept"] > 0 for result in results),
        "weeks_empty": sum(result["rows_kept"] == 0 for result in results),
        "rows_read": sum(int(result["rows_read"]) for result in results),
        "rows_kept": sum(int(result["rows_kept"]) for result in results),
        "rows_removed": sum(int(result["rows_removed"]) for result in results),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    audit_path = args.output_dir / "auditoria_twitter_uniforme_tampico.json"
    audit_path.write_text(
        json.dumps(
            {
                "selection_rule": (
                    "consultas from, to o mención de @TampicoGob y "
                    "@MonicaVTampico, más respuestas vinculadas"
                ),
                "query_provenance_policy": "query_raw conserva la consulta histórica real",
                "coverage_limit": (
                    "La regla uniforma el alcance sobre lo descargado; no recupera "
                    "tweets ausentes de las extracciones históricas."
                ),
                "output_columns": OUTPUT_COLUMNS,
                "summary": summary,
                "weeks": results,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Auditoría: {audit_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
