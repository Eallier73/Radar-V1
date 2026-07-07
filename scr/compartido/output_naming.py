"""Convenciones de nombres para los artefactos semanales de Radar."""

from __future__ import annotations

from datetime import date, datetime
import os
import re


MONTH_NAMES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def _normalize_date_label(
    run_date: str | date | datetime | None,
    fallback: str,
) -> str:
    if isinstance(run_date, datetime):
        iso = run_date.isocalendar()
        return f"{iso.year}_W{iso.week:02d}"
    if isinstance(run_date, date):
        iso = run_date.isocalendar()
        return f"{iso.year}_W{iso.week:02d}"
    if run_date:
        raw = str(run_date).strip()
        try:
            parsed = datetime.strptime(raw, "%Y-%m-%d")
            iso = parsed.date().isocalendar()
            return f"{iso.year}_W{iso.week:02d}"
        except ValueError:
            return raw
    return fallback


def _normalize_source_label(source: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z]+", "_", (source or "").strip())
    return normalized.strip("_") or "Reporte"


def build_report_tag(
    run_date: str | date | datetime | None,
    source: str,
    fallback: str = "sin_inicio",
) -> str:
    """Compatibilidad con los extractores importados originalmente."""
    override = os.getenv("REPORT_TAG_OVERRIDE", "").strip()
    source_label = _normalize_source_label(source)
    if override:
        return f"{override}_{source_label}"
    return f"{_normalize_date_label(run_date, fallback)}_{source_label}"


def build_prefixed_name(base_name: str, report_tag: str) -> str:
    """Antepone el identificador del reporte si todavía no está presente."""
    if base_name.startswith(f"{report_tag}_") or base_name == report_tag:
        return base_name
    return f"{report_tag}_{base_name}"


def _as_date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


def build_week_folder_name(
    since: str | date | datetime,
    before: str | date | datetime,
) -> str:
    """Construye el nombre semanal usado en ``datos/radar_semanal_extraido``."""
    start = _as_date(since)
    end = _as_date(before)
    if start > end:
        raise ValueError("La fecha inicial no puede ser posterior a la fecha final.")
    start_label = f"{start.day:02d}{MONTH_NAMES[start.month - 1]}"
    end_label = f"{end.day:02d}{MONTH_NAMES[end.month - 1]}_{end.year % 100:02d}"
    return f"{start.isoformat()}_semana_{start_label}_{end_label}"


def build_source_filename(week_name: str, source: str, suffix: str = "") -> str:
    source_token = source.strip().lower()
    suffix_token = suffix.strip().lower()
    parts = [week_name, source_token]
    if suffix_token:
        parts.append(suffix_token)
    return "_".join(parts)
