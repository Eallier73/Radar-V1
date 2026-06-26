#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from csv_text_extraction import process_rows_to_corpus, read_csv_rows, resolve_canonical_csv
from preprocessing_audit import WeekAuditRecord, build_run_metadata, write_audit_bundle
from stage2_text_common import (
    DEFAULT_DATOS_RADAR_DIR,
    DEFAULT_DATOS_TEXTO_DIR,
    VALID_OUTPUT_MODES,
    build_default_run_id,
    discover_week_contexts,
    ensure_directory,
    now_utc_text,
    resolve_requested_sources,
    resolve_requested_weeks,
    week_matches_filters,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Etapa 2 real de Radar: toma CSVs canónicos por fuente/semana, "
            "construye corpus TXT limpio y deja auditoría trazable."
        )
    )
    parser.add_argument(
        "--datos-radar-dir",
        type=Path,
        default=DEFAULT_DATOS_RADAR_DIR,
        help="Directorio raíz de Datos_RAdAR. Default: %(default)s",
    )
    parser.add_argument(
        "--datos-texto-dir",
        type=Path,
        default=DEFAULT_DATOS_TEXTO_DIR,
        help="Directorio raíz de Datos_RadaR_Texto. Default: %(default)s",
    )
    parser.add_argument(
        "--sources",
        nargs="*",
        default=None,
        help="Fuentes a procesar. Acepta facebook twitter youtube medios.",
    )
    parser.add_argument(
        "--weeks",
        nargs="*",
        default=None,
        help="Semanas a procesar. Acepta YY_WW, YYYY-Www o nombre completo de carpeta semanal.",
    )
    parser.add_argument(
        "--words-per-line",
        type=int,
        default=30,
        help="Palabras por línea del corpus final. Default: %(default)s",
    )
    parser.add_argument(
        "--output-mode",
        choices=sorted(VALID_OUTPUT_MODES),
        default="archive",
        help="archive deja intacto el TXT si ya existe; overwrite-text lo reemplaza.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Identificador de corrida. Si se omite, se genera automáticamente.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="No escribe TXT de salida. Si --save-audit está activo, sí deja auditoría.",
    )
    parser.add_argument(
        "--skip-missing",
        action="store_true",
        help="Si falta el CSV canónico, registra skip en vez de error fatal.",
    )
    parser.add_argument(
        "--save-audit",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Guardar o no los artefactos de auditoría de la corrida.",
    )
    return parser.parse_args()


def serialize_parameters(args: argparse.Namespace, *, run_id: str, sources: list[str], weeks: set[str]) -> dict[str, Any]:
    return {
        "datos_radar_dir": str(args.datos_radar_dir),
        "datos_texto_dir": str(args.datos_texto_dir),
        "sources": list(sources),
        "weeks": sorted(weeks),
        "words_per_line": args.words_per_line,
        "output_mode": args.output_mode,
        "run_id": run_id,
        "dry_run": bool(args.dry_run),
        "skip_missing": bool(args.skip_missing),
        "save_audit": bool(args.save_audit),
    }


def write_text_output(path: Path, lines: list[str]) -> None:
    ensure_directory(path.parent)
    content = "\n".join(lines)
    if content:
        content += "\n"
    path.write_text(content, encoding="utf-8")


def build_empty_record(
    *,
    source: str,
    week_name: str,
    iso_token: str,
    input_folder: Path,
    output_folder: Path,
    source_csv_path: Path,
    generated_txt_name: str,
    generated_txt_path: Path,
    canonical_csv_criteria: str,
    status: str,
    warning_messages: list[str] | None = None,
    error_message: str = "",
) -> WeekAuditRecord:
    return WeekAuditRecord(
        source=source,
        week_name=week_name,
        iso_token=iso_token,
        input_folder=str(input_folder),
        output_folder=str(output_folder),
        source_csv_path=str(source_csv_path),
        generated_txt_name=generated_txt_name,
        generated_txt_path=str(generated_txt_path),
        text_columns_used=[],
        csv_rows_read=0,
        useful_rows=0,
        empty_rows_discarded=0,
        duplicates_removed=0,
        total_words_final=0,
        total_lines_txt=0,
        words_per_line=0,
        canonical_csv_criteria=canonical_csv_criteria,
        status=status,
        warning_messages=warning_messages or [],
        error_message=error_message,
        record_types_included=[],
    )


def main() -> int:
    args = parse_args()
    run_id = args.run_id or build_default_run_id()
    sources = resolve_requested_sources(args.sources)
    requested_weeks = resolve_requested_weeks(args.weeks)

    discovered = discover_week_contexts(args.datos_radar_dir, args.datos_texto_dir, sources)
    selected_contexts = []
    for source in sources:
        source_contexts = [
            ctx
            for ctx in discovered.get(source, [])
            if week_matches_filters(ctx, requested_weeks)
        ]
        selected_contexts.extend(source_contexts)

    if not selected_contexts:
        print("No se encontraron semanas/fuentes que coincidan con los filtros dados.", file=sys.stderr)
        return 1

    artifacts_dir = args.datos_texto_dir / "runs" / run_id
    started_at = now_utc_text()
    metadata = build_run_metadata(
        run_id=run_id,
        script_path=Path(__file__).resolve(),
        datos_radar_dir=args.datos_radar_dir,
        datos_texto_dir=args.datos_texto_dir,
        artifacts_dir=artifacts_dir,
        sources=sources,
        weeks_filter=sorted(requested_weeks),
        output_mode=args.output_mode,
        dry_run=args.dry_run,
        words_per_line=args.words_per_line,
    )
    metadata["started_at_utc"] = started_at

    records: list[WeekAuditRecord] = []
    had_errors = False

    for week_ctx in selected_contexts:
        print(f"[{week_ctx.source}] {week_ctx.week_name}")
        try:
            selection = resolve_canonical_csv(week_ctx)
        except FileNotFoundError as exc:
            status = "skip_missing_csv" if args.skip_missing else "error_missing_csv"
            print(f"  - {status}: {exc}")
            records.append(
                build_empty_record(
                    source=week_ctx.source,
                    week_name=week_ctx.week_name,
                    iso_token=week_ctx.iso_token,
                    input_folder=week_ctx.week_dir,
                    output_folder=week_ctx.output_dir,
                    source_csv_path=week_ctx.week_dir / "MISSING",
                    generated_txt_name=week_ctx.output_filename,
                    generated_txt_path=week_ctx.output_path,
                    canonical_csv_criteria="missing_expected_canonical_csv",
                    status=status,
                    warning_messages=[],
                    error_message=str(exc),
                )
            )
            if not args.skip_missing:
                had_errors = True
            continue

        warnings = list(selection.warnings)
        try:
            rows = read_csv_rows(selection.path)
            processed = process_rows_to_corpus(
                week_ctx.source,
                rows,
                words_per_line=args.words_per_line,
            )
            warnings.extend(processed.warnings)
        except Exception as exc:
            had_errors = True
            print(f"  - error_processing_csv: {exc}")
            records.append(
                build_empty_record(
                    source=week_ctx.source,
                    week_name=week_ctx.week_name,
                    iso_token=week_ctx.iso_token,
                    input_folder=week_ctx.week_dir,
                    output_folder=week_ctx.output_dir,
                    source_csv_path=selection.path,
                    generated_txt_name=week_ctx.output_filename,
                    generated_txt_path=week_ctx.output_path,
                    canonical_csv_criteria=selection.selection_criteria,
                    status="error_processing_csv",
                    warning_messages=warnings,
                    error_message=str(exc),
                )
            )
            continue

        status = "success"
        error_message = ""
        if processed.useful_row_count == 0:
            status = "skip_no_useful_text"
            warnings.append("No quedó texto útil después de la normalización.")
        elif args.dry_run:
            status = "success_dry_run"
            if week_ctx.output_path.exists() and args.output_mode == "archive":
                warnings.append("El TXT destino ya existe y en archive se mantendría intacto.")
        elif week_ctx.output_path.exists() and args.output_mode == "archive":
            status = "skip_target_exists_archive_mode"
            warnings.append("El TXT destino ya existía y output-mode=archive no permite reemplazarlo.")
        else:
            write_text_output(week_ctx.output_path, processed.lines)

        print(
            "  - "
            f"{status} | csv={selection.path.name} | "
            f"filas={processed.raw_row_count} utiles={processed.useful_row_count} "
            f"dupes={processed.duplicates_removed} palabras={processed.total_words} "
            f"lineas={processed.total_lines}"
        )

        records.append(
            WeekAuditRecord(
                source=week_ctx.source,
                week_name=week_ctx.week_name,
                iso_token=week_ctx.iso_token,
                input_folder=str(week_ctx.week_dir),
                output_folder=str(week_ctx.output_dir),
                source_csv_path=str(selection.path),
                generated_txt_name=week_ctx.output_filename,
                generated_txt_path=str(week_ctx.output_path),
                text_columns_used=processed.columns_used,
                csv_rows_read=processed.raw_row_count,
                useful_rows=processed.useful_row_count,
                empty_rows_discarded=processed.empty_rows_discarded,
                duplicates_removed=processed.duplicates_removed,
                total_words_final=processed.total_words,
                total_lines_txt=processed.total_lines,
                words_per_line=args.words_per_line,
                canonical_csv_criteria=selection.selection_criteria,
                status=status,
                warning_messages=list(dict.fromkeys(warnings)),
                error_message=error_message,
                record_types_included=processed.record_types_included,
            )
        )

    metadata["finished_at_utc"] = now_utc_text()
    metadata["selected_pairs"] = len(selected_contexts)
    metadata["result_exit_code"] = 1 if had_errors else 0
    metadata["run_status"] = "completed_with_errors" if had_errors else "completed"

    if args.save_audit:
        write_audit_bundle(
            artifacts_dir,
            metadata=metadata,
            parameters=serialize_parameters(
                args,
                run_id=run_id,
                sources=sources,
                weeks=requested_weeks,
            ),
            records=records,
        )
        print(f"Artefactos de auditoría: {artifacts_dir}")

    return 1 if had_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
