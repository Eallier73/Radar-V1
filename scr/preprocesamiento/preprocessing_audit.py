#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence

from stage2_text_common import ensure_directory, now_utc_text, write_csv, write_json


@dataclass
class WeekAuditRecord:
    source: str
    week_name: str
    iso_token: str
    input_folder: str
    output_folder: str
    source_csv_path: str
    generated_txt_name: str
    generated_txt_path: str
    text_columns_used: list[str]
    csv_rows_read: int
    useful_rows: int
    empty_rows_discarded: int
    duplicates_removed: int
    total_words_final: int
    total_lines_txt: int
    words_per_line: int
    canonical_csv_criteria: str
    status: str
    warning_messages: list[str] = field(default_factory=list)
    error_message: str = ""
    record_types_included: list[str] = field(default_factory=list)

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_csv_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["text_columns_used"] = "|".join(self.text_columns_used)
        payload["warning_messages"] = " | ".join(self.warning_messages)
        payload["record_types_included"] = "|".join(self.record_types_included)
        return payload


def build_run_metadata(
    *,
    run_id: str,
    script_path: Path,
    datos_radar_dir: Path,
    datos_texto_dir: Path,
    artifacts_dir: Path,
    sources: Sequence[str],
    weeks_filter: Sequence[str],
    output_mode: str,
    dry_run: bool,
    words_per_line: int,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "started_at_utc": now_utc_text(),
        "script_path": str(script_path),
        "datos_radar_dir": str(datos_radar_dir),
        "datos_texto_dir": str(datos_texto_dir),
        "legacy_weekly_archive_dir": str(datos_radar_dir / "Juntos"),
        "artifacts_dir": str(artifacts_dir),
        "sources": list(sources),
        "weeks_filter": list(weeks_filter),
        "output_mode": output_mode,
        "dry_run": dry_run,
        "words_per_line": words_per_line,
        "stage_scope": "csv_canonico_por_fuente_y_semana_a_txt_limpio_por_fuente_y_semana",
        "non_scope": "no_nlp_no_sentimiento_no_temas_no_embeddings_no_features",
        "decisiones_metodologicas": [
            "La etapa 2 vigente solo consume Datos_RAdAR/<Fuente>/<semana>; Datos_RAdAR/Juntos queda como legado archivado.",
            "Facebook se construye desde facebook_institutional_raw_<semana>.csv usando la columna text para incorporar posts y comentarios sin duplicar post_text.",
            "Medios combina article_title + article_text antes de limpiar.",
            "La reconstrucción final se hace sobre el flujo concatenado completo con 30 palabras por línea por default.",
        ],
    }


def build_run_summary(records: Sequence[WeekAuditRecord]) -> dict[str, Any]:
    summary = {
        "total_pairs": len(records),
        "success": 0,
        "skipped": 0,
        "errors": 0,
        "sources": {},
    }
    for record in records:
        if record.status.startswith("success"):
            summary["success"] += 1
        elif record.status.startswith("skip"):
            summary["skipped"] += 1
        else:
            summary["errors"] += 1

        source_bucket = summary["sources"].setdefault(
            record.source,
            {
                "total_pairs": 0,
                "success": 0,
                "skipped": 0,
                "errors": 0,
                "total_words": 0,
                "total_lines": 0,
            },
        )
        source_bucket["total_pairs"] += 1
        if record.status.startswith("success"):
            source_bucket["success"] += 1
        elif record.status.startswith("skip"):
            source_bucket["skipped"] += 1
        else:
            source_bucket["errors"] += 1
        source_bucket["total_words"] += record.total_words_final
        source_bucket["total_lines"] += record.total_lines_txt
    return summary


def write_audit_bundle(
    artifacts_dir: Path,
    *,
    metadata: dict[str, Any],
    parameters: dict[str, Any],
    records: Sequence[WeekAuditRecord],
) -> None:
    ensure_directory(artifacts_dir)
    write_json(artifacts_dir / "metadata_run.json", metadata)
    write_json(artifacts_dir / "parametros_run.json", parameters)
    write_json(
        artifacts_dir / "auditoria_preprocessing.json",
        [record.to_json_dict() for record in records],
    )
    write_json(
        artifacts_dir / "resumen_preprocessing.json",
        build_run_summary(records),
    )
    write_csv(
        artifacts_dir / "auditoria_archivos.csv",
        [record.to_csv_dict() for record in records],
        fieldnames=[
            "source",
            "week_name",
            "iso_token",
            "input_folder",
            "output_folder",
            "source_csv_path",
            "generated_txt_name",
            "generated_txt_path",
            "text_columns_used",
            "csv_rows_read",
            "useful_rows",
            "empty_rows_discarded",
            "duplicates_removed",
            "total_words_final",
            "total_lines_txt",
            "words_per_line",
            "canonical_csv_criteria",
            "status",
            "warning_messages",
            "error_message",
            "record_types_included",
        ],
    )
