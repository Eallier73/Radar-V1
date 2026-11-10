"""Excepciones de fecha limitadas a registros historicos con procedencia."""

from __future__ import annotations

import json
from pathlib import Path

from facebook_data_contract import (
    FACEBOOK_BASE_ACCOUNTS,
    FACEBOOK_PROCESSED_COLUMNS,
    historical_facebook_row,
    normalize_absolute_datetime,
)
from radar_paths import DATA_DIR


DEFAULT_HISTORICAL_DIR = DATA_DIR / "radar_historico_reincorporado" / "facebook"
HISTORICAL_DATE_REASONS = {"date_unknown", "date_invalid"}


def row_from_exclusion(record: dict[str, object]) -> dict[str, str]:
    """Conserva la proyeccion historica y recupera el valor original de fecha."""
    if record.get("reason") not in HISTORICAL_DATE_REASONS:
        raise ValueError("Solo se autorizan exclusiones por fecha desconocida o invalida")
    original = record["original"]
    projected = record["projected"]
    if not isinstance(original, dict) or not isinstance(projected, dict):
        raise ValueError("Registro historico sin original y proyeccion")
    if "fecha" not in original:
        raise ValueError("La recuperacion requiere el valor original de fecha")
    row = historical_facebook_row(projected)
    row["fecha"] = str(original.get("fecha") or "")
    _, status = normalize_absolute_datetime(row["fecha"])
    if f"date_{status}" != record["reason"]:
        raise ValueError("La fecha original no corresponde al motivo de exclusion")
    if row["cuenta"] not in FACEBOOK_BASE_ACCOUNTS:
        raise ValueError("Cuenta historica fuera de contrato")
    return row


def load_historical_facebook_rows(
    week: str,
    historical_dir: Path = DEFAULT_HISTORICAL_DIR,
) -> list[dict[str, str]]:
    """Carga solo las filas exactas autorizadas para la semana de procedencia."""
    if Path(week).name != week:
        raise ValueError("Semana historica invalida")
    path = historical_dir / week / "facebook_reincorporado.jsonl"
    if not path.is_file():
        return []
    rows: list[dict[str, str]] = []
    seen = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("source_week") != week:
            raise ValueError(f"Procedencia semanal distinta en {path}")
        row = row_from_exclusion(record)
        accepted = record.get("accepted_row")
        if not isinstance(accepted, dict) or set(accepted) != set(FACEBOOK_PROCESSED_COLUMNS) or accepted != row:
            raise ValueError(f"Fila historica alterada respecto de su procedencia en {path}")
        provenance = (record.get("source_sha256"), record.get("source_record"))
        if not provenance[0] or not isinstance(provenance[1], int) or provenance in seen:
            raise ValueError(f"Procedencia ausente o duplicada en {path}")
        seen.add(provenance)
        rows.append(row)
    return rows
