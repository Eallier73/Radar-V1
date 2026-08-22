#!/usr/bin/env python3
"""Orquestador de las seis etapas del pipeline Radar.

El módulo mantiene la coordinación separada de la implementación de cada etapa.
Cada etapa tiene un único punto de entrada (runner), de modo que sus scripts
internos pueden evolucionar sin convertir este archivo en otro pipeline monolítico.
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Sequence

SHARED_DIR = Path(__file__).resolve().parent
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from radar_paths import resolve_python_executable


REPO_ROOT = Path(__file__).resolve().parents[2]
SCR_DIR = REPO_ROOT / "scr"
DATA_DIR = REPO_ROOT / "datos"
PYTHON_EXECUTABLE = resolve_python_executable()


def _load_env_file(path: Path) -> None:
    """Carga variables simples sin sobrescribir las ya definidas."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            os.environ.setdefault(key, value.strip().strip("'\""))


for _env_path in (REPO_ROOT / ".env", REPO_ROOT / ".env.local"):
    _load_env_file(_env_path)


@dataclass(frozen=True)
class PipelineSpec:
    """Contrato de una etapa seleccionable."""

    code: str
    key: str
    label: str
    runner: Path
    description: str

    @property
    def filename(self) -> str:
        return self.runner.name

    @property
    def relative_runner(self) -> Path:
        try:
            return self.runner.relative_to(REPO_ROOT)
        except ValueError:
            return self.runner


# Orden operativo solicitado: este catálogo contiene únicamente etapas de Radar.
PIPELINES = [
    PipelineSpec(
        "1",
        "extraccion",
        "Extracción",
        SCR_DIR / "extraccion" / "run_extraccion.py",
        "Obtiene los datos de YouTube, Twitter/X, medios y Facebook.",
    ),
    PipelineSpec(
        "2",
        "preprocesamiento",
        "Preprocesamiento",
        SCR_DIR / "preprocesamiento" / "run_stage2_text_preprocessing.py",
        "Limpia y normaliza los insumos semanales para las etapas analíticas.",
    ),
    PipelineSpec(
        "3",
        "nlp",
        "NLP",
        SCR_DIR / "nlp" / "run_nlp.py",
        "Genera variables de lenguaje, sentimiento y clasificación temática.",
    ),
    PipelineSpec(
        "4",
        "modelado",
        "Modelado",
        SCR_DIR / "modelado" / "run_modelado.py",
        "Entrena o ejecuta los modelos de proyección de Radar.",
    ),
    PipelineSpec(
        "5",
        "tablero",
        "Tablero",
        SCR_DIR / "tablero" / "run_tablero.py",
        "Construye los artefactos consumidos por el tablero.",
    ),
    PipelineSpec(
        "6",
        "reporte",
        "Reporte",
        SCR_DIR / "reporte" / "run_reporte.py",
        "Genera el reporte final del periodo seleccionado.",
    ),
]

PIPELINES_BY_CODE = {stage.code: stage for stage in PIPELINES}
PIPELINES_BY_KEY = {stage.key: stage for stage in PIPELINES}
STAGES = PIPELINES
STAGES_BY_CODE = PIPELINES_BY_CODE
STAGES_BY_KEY = PIPELINES_BY_KEY

EXTRACTION_SOURCES = (
    ("youtube", "YouTube"),
    ("twitter", "Twitter/X"),
    ("medios", "Medios"),
    ("facebook", "Facebook (posts y comentarios)"),
)
EXTRACTION_SOURCE_KEYS = tuple(key for key, _label in EXTRACTION_SOURCES)

_today = date.today()
_last_completed_sunday = _today - timedelta(days=_today.weekday() + 1)
_default_iso = _last_completed_sunday.isocalendar()
DEFAULT_GLOBAL_ISO_WEEK = f"{_default_iso.year}-W{_default_iso.week:02d}"


class MissingStageRunner(FileNotFoundError):
    """La etapa existe en el flujo, pero su runner aún no está implementado."""


def parse_iso_week(value: str) -> tuple[int, int]:
    raw = (value or "").strip().upper().replace("_", "-")
    if "-W" not in raw:
        raise ValueError("Formato inválido. Usa YYYY-Www, por ejemplo 2026-W14.")
    year_text, week_text = raw.split("-W", 1)
    try:
        year = int(year_text)
        week = int(week_text)
        date.fromisocalendar(year, week, 1)
    except ValueError as exc:
        raise ValueError(f"Semana ISO inválida: {value}") from exc
    return year, week


def iso_week_to_range(value: str) -> tuple[str, str]:
    year, week = parse_iso_week(value)
    since = date.fromisocalendar(year, week, 1)
    before = since + timedelta(days=6)
    return since.isoformat(), before.isoformat()


def date_range_to_iso_week(since: str) -> str:
    parsed = datetime.strptime(since, "%Y-%m-%d").date()
    iso = parsed.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def validate_date_range(since: str, before: str) -> tuple[str, str]:
    try:
        since_date = datetime.strptime(since, "%Y-%m-%d").date()
        before_date = datetime.strptime(before, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("Las fechas deben usar el formato YYYY-MM-DD.") from exc
    if since_date > before_date:
        raise ValueError("La fecha inicial no puede ser posterior a la final.")
    return since_date.isoformat(), before_date.isoformat()


def parse_pipeline_selection(raw: str) -> list[PipelineSpec]:
    normalized = (raw or "").strip().lower()
    if normalized in {"all", "todos", "*"}:
        return list(PIPELINES)

    selected: list[PipelineSpec] = []
    seen: set[str] = set()
    for part in normalized.split(","):
        token = part.strip()
        if not token:
            continue
        stage = PIPELINES_BY_CODE.get(token) or PIPELINES_BY_KEY.get(token)
        if stage is None:
            valid = ", ".join(stage.key for stage in PIPELINES)
            raise ValueError(f"Etapa desconocida: {token}. Opciones: {valid}.")
        if stage.code not in seen:
            selected.append(stage)
            seen.add(stage.code)
    if not selected:
        raise ValueError("No se seleccionó ninguna etapa.")
    return selected


def stage_status(stage: PipelineSpec) -> tuple[bool, str]:
    if stage.runner.is_file():
        return True, f"disponible: {stage.relative_runner}"
    return False, f"runner pendiente: {stage.relative_runner}"


def normalize_extraction_sources(
    raw_sources: Sequence[str] | None,
) -> tuple[str, ...]:
    if not raw_sources:
        return EXTRACTION_SOURCE_KEYS
    requested: list[str] = []
    for raw in raw_sources:
        requested.extend(
            token.strip().lower()
            for token in str(raw).split(",")
            if token.strip()
        )
    if any(token in {"all", "todas", "*"} for token in requested):
        return EXTRACTION_SOURCE_KEYS
    unknown = sorted(set(requested) - set(EXTRACTION_SOURCE_KEYS))
    if unknown:
        raise ValueError(
            "Fuentes de extracción desconocidas: "
            + ", ".join(unknown)
            + ". Opciones: "
            + ", ".join(EXTRACTION_SOURCE_KEYS)
        )
    selected = tuple(key for key in EXTRACTION_SOURCE_KEYS if key in requested)
    if not selected:
        raise ValueError("Selecciona al menos una fuente de extracción.")
    return selected


def _python_command(stage: PipelineSpec) -> list[str]:
    return [str(PYTHON_EXECUTABLE), str(stage.runner)]


def build_pipeline(
    stage: PipelineSpec,
    since: str,
    before: str,
    *,
    require_runner: bool = True,
    extraction_sources: Sequence[str] | None = None,
    continue_on_error: bool = False,
) -> tuple[list[str], dict[str, str]]:
    """Construye el comando de una etapa con el contrato de Radar."""
    since, before = validate_date_range(since, before)
    if require_runner and not stage.runner.is_file():
        raise MissingStageRunner(
            f"La etapa {stage.label} está incorporada, pero falta su runner: "
            f"{stage.relative_runner}"
        )

    cmd = _python_command(stage)
    if stage.key == "extraccion":
        sources = normalize_extraction_sources(extraction_sources)
        cmd.extend(["--since", since, "--before", before, "--sources", *sources])
        if continue_on_error:
            cmd.append("--continue-on-error")
    elif stage.key == "preprocesamiento":
        cmd.extend(
            [
                "--datos-radar-dir",
                str(DATA_DIR / "radar_semanal_extraido"),
                "--datos-texto-dir",
                str(DATA_DIR / "radar_semanal_texto"),
                "--weeks",
                date_range_to_iso_week(since),
            ]
        )
    else:
        cmd.extend(["--since", since, "--before", before])
    return cmd, {}


def build_stage_commands(
    stage: PipelineSpec,
    since: str,
    before: str,
    *,
    require_runner: bool = True,
    extraction_sources: Sequence[str] | None = None,
    continue_on_error: bool = False,
) -> list[tuple[list[str], dict[str, str]]]:
    return [
        build_pipeline(
            stage,
            since,
            before,
            require_runner=require_runner,
            extraction_sources=extraction_sources,
            continue_on_error=continue_on_error,
        )
    ]


def render_command(cmd: Sequence[str]) -> str:
    return " ".join(shlex.quote(str(part)) for part in cmd)


def execute_stages(
    stages: Sequence[PipelineSpec],
    since: str,
    before: str,
    *,
    dry_run: bool = False,
    continue_on_error: bool = False,
    extraction_sources: Sequence[str] | None = None,
) -> int:
    since, before = validate_date_range(since, before)
    failures = 0
    for stage in stages:
        print(f"\n[{stage.code}/6] {stage.label}")
        try:
            plans = build_stage_commands(
                stage,
                since,
                before,
                require_runner=not dry_run,
                extraction_sources=extraction_sources,
                continue_on_error=continue_on_error,
            )
        except MissingStageRunner as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            failures += 1
            if not continue_on_error:
                return 1
            continue

        for cmd, env_updates in plans:
            print(f"$ {render_command(cmd)}")
            if dry_run:
                continue
            env = os.environ.copy()
            env.update(env_updates)
            result = subprocess.run(cmd, cwd=REPO_ROOT, env=env, check=False)
            if result.returncode != 0:
                failures += 1
                print(
                    f"ERROR: {stage.label} terminó con código {result.returncode}.",
                    file=sys.stderr,
                )
                if not continue_on_error:
                    return result.returncode or 1
                break
    return 1 if failures else 0


def print_stage_catalog() -> None:
    for stage in PIPELINES:
        available, status = stage_status(stage)
        marker = "OK" if available else "PENDIENTE"
        print(f"{stage.code}. {stage.label:<18} [{marker}] {status}")


def _prompt_selection() -> list[PipelineSpec]:
    print("\nETAPAS DISPONIBLES")
    print_stage_catalog()
    while True:
        raw = input("\nSelecciona etapas (ej. 1,2,3 o all) [all]: ").strip() or "all"
        try:
            return parse_pipeline_selection(raw)
        except ValueError as exc:
            print(f"ERROR: {exc}")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Orquestador de etapas de Radar")
    parser.add_argument("--stages", "--pipelines", default=None, help="Códigos o nombres separados por coma")
    parser.add_argument("--week", default=None, help="Semana ISO YYYY-Www")
    parser.add_argument("--since", default=None, help="Fecha inicial YYYY-MM-DD")
    parser.add_argument("--before", default=None, help="Fecha final YYYY-MM-DD")
    parser.add_argument(
        "--sources",
        nargs="+",
        default=None,
        help="Fuentes de Extracción: youtube twitter medios facebook.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Muestra comandos sin ejecutarlos")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--list", action="store_true", help="Lista las seis etapas y su disponibilidad")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.list:
        print_stage_catalog()
        return 0

    if args.week and (args.since or args.before):
        raise SystemExit("Usa --week o el par --since/--before, no ambos.")
    if bool(args.since) != bool(args.before):
        raise SystemExit("--since y --before deben indicarse juntos.")

    if args.week:
        since, before = iso_week_to_range(args.week)
    elif args.since and args.before:
        since, before = validate_date_range(args.since, args.before)
    else:
        since, before = iso_week_to_range(DEFAULT_GLOBAL_ISO_WEEK)

    stages = parse_pipeline_selection(args.stages) if args.stages else _prompt_selection()
    if args.sources and not any(stage.key == "extraccion" for stage in stages):
        raise SystemExit("--sources solo aplica cuando se selecciona Extracción.")
    extraction_sources = normalize_extraction_sources(args.sources)

    print(f"\nRepositorio: {REPO_ROOT}")
    print(f"Periodo:     {since} -> {before}")
    print("Etapas:      " + ", ".join(stage.label for stage in stages))
    return execute_stages(
        stages,
        since,
        before,
        dry_run=args.dry_run,
        continue_on_error=args.continue_on_error,
        extraction_sources=extraction_sources,
    )


if __name__ == "__main__":
    raise SystemExit(main())
