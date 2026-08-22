#!/usr/bin/env python3
"""Runner de la etapa de extracción de Radar V1.

Coordina los extractores municipales existentes sin duplicar su configuración.
Facebook se ejecuta como una sola fuente: primero obtiene posts y después usa
su CSV temporal para descargar comentarios y producir el CSV canónico.
"""

from __future__ import annotations

import argparse
import csv
import os
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence


EXTRACTION_DIR = Path(__file__).resolve().parent
REPO_ROOT = EXTRACTION_DIR.parents[1]
SHARED_DIR = REPO_ROOT / "scr" / "compartido"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from output_naming import build_source_filename, build_week_folder_name
from radar_paths import EXTRACTED_DATA_DIR


SOURCE_ORDER = ("youtube", "twitter", "medios", "facebook")
SOURCE_LABELS = {
    "youtube": "YouTube",
    "twitter": "Twitter/X",
    "medios": "Medios",
    "facebook": "Facebook (posts y comentarios)",
}
EXTRACTOR_FILES = {
    "youtube": "1_extractors_youtube.py",
    "twitter": "2_extractors_twitter.py",
    "medios": "3_extractors_medios.py",
    "facebook_posts": "4_extractors_facebook_posts.py",
    "facebook_comments": "5_extractors_facebook_comentarios.py",
}
FACEBOOK_COLUMNS = (
    "tipo",
    "url",
    "post_url_padre",
    "fecha",
    "texto",
    "num_comentarios",
)


@dataclass(frozen=True)
class CommandPlan:
    """Comando individual dentro de una fuente de extracción."""

    label: str
    command: tuple[str, ...]
    skip_when_posts_empty: bool = False


@dataclass(frozen=True)
class SourcePlan:
    """Plan ejecutable de una fuente seleccionada."""

    key: str
    label: str
    commands: tuple[CommandPlan, ...]


def _load_env_file(path: Path) -> None:
    """Carga asignaciones simples sin reemplazar variables ya definidas."""

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


def validate_date_range(since: str, before: str) -> tuple[str, str]:
    try:
        start = datetime.strptime(since, "%Y-%m-%d").date()
        end = datetime.strptime(before, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("Las fechas deben usar el formato YYYY-MM-DD.") from exc
    if start > end:
        raise ValueError("--since no puede ser posterior a --before.")
    return start.isoformat(), end.isoformat()


def normalize_sources(raw_values: Sequence[str] | None) -> tuple[str, ...]:
    if not raw_values:
        return SOURCE_ORDER

    requested: list[str] = []
    for raw in raw_values:
        requested.extend(
            token.strip().lower()
            for token in str(raw).split(",")
            if token.strip()
        )
    if any(token in {"all", "todas", "*"} for token in requested):
        return SOURCE_ORDER

    unknown = sorted(set(requested) - set(SOURCE_ORDER))
    if unknown:
        raise ValueError(
            "Fuentes desconocidas: "
            + ", ".join(unknown)
            + ". Opciones: "
            + ", ".join(SOURCE_ORDER)
        )

    selected = tuple(source for source in SOURCE_ORDER if source in requested)
    if not selected:
        raise ValueError("Selecciona al menos una fuente de extracción.")
    return selected


def facebook_paths(output_dir: Path, since: str, before: str) -> tuple[Path, Path]:
    week_name = build_week_folder_name(since, before)
    week_dir = output_dir / week_name
    posts_name = build_source_filename(week_name, "facebook", "posts") + ".csv"
    canonical_name = build_source_filename(week_name, "facebook") + ".csv"
    return week_dir / posts_name, week_dir / canonical_name


def build_source_plans(
    sources: Sequence[str],
    since: str,
    before: str,
    output_dir: Path,
    *,
    python_executable: str | Path | None = None,
) -> list[SourcePlan]:
    since, before = validate_date_range(since, before)
    selected = normalize_sources(sources)
    python = str(python_executable or sys.executable)
    output = str(output_dir)

    plans: list[SourcePlan] = []
    for source in selected:
        common = ("--since", since, "--before", before, "--output-dir", output)
        if source in {"youtube", "twitter", "medios"}:
            command = (
                python,
                str(EXTRACTION_DIR / EXTRACTOR_FILES[source]),
                *common,
            )
            plans.append(
                SourcePlan(
                    source,
                    SOURCE_LABELS[source],
                    (CommandPlan(SOURCE_LABELS[source], command),),
                )
            )
            continue

        posts_csv, _canonical_csv = facebook_paths(output_dir, since, before)
        posts_command = (
            python,
            str(EXTRACTION_DIR / EXTRACTOR_FILES["facebook_posts"]),
            *common,
            "--no-prompt",
        )
        comments_command = (
            python,
            str(EXTRACTION_DIR / EXTRACTOR_FILES["facebook_comments"]),
            "--input-csv",
            str(posts_csv),
            *common,
            "--no-prompt",
        )
        plans.append(
            SourcePlan(
                "facebook",
                SOURCE_LABELS["facebook"],
                (
                    CommandPlan("Facebook posts", posts_command),
                    CommandPlan(
                        "Facebook comentarios",
                        comments_command,
                        skip_when_posts_empty=True,
                    ),
                ),
            )
        )
    return plans


def render_command(command: Sequence[str]) -> str:
    return " ".join(shlex.quote(str(part)) for part in command)


def count_post_urls(path: Path) -> int:
    if not path.is_file():
        raise FileNotFoundError(f"No se generó el CSV de posts esperado: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "post_url" not in reader.fieldnames:
            raise ValueError(f"El CSV de posts no contiene la columna post_url: {path}")
        return sum(bool(str(row.get("post_url") or "").strip()) for row in reader)


def write_empty_facebook_csv(posts_csv: Path, canonical_csv: Path) -> None:
    """Confirma una semana sin posts con el esquema canónico de Facebook."""

    canonical_csv.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8-sig",
            newline="",
            dir=canonical_csv.parent,
            prefix=f".{canonical_csv.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            csv.DictWriter(handle, fieldnames=FACEBOOK_COLUMNS).writeheader()
        temp_path.replace(canonical_csv)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
    if posts_csv != canonical_csv and posts_csv.is_file():
        posts_csv.unlink()


def execute_plans(
    plans: Sequence[SourcePlan],
    *,
    since: str,
    before: str,
    output_dir: Path,
    dry_run: bool,
    continue_on_error: bool,
) -> int:
    failures = 0
    for index, plan in enumerate(plans, start=1):
        print(f"\n[{index}/{len(plans)}] {plan.label}", flush=True)
        for command_plan in plan.commands:
            print(f"$ {render_command(command_plan.command)}", flush=True)
            if dry_run:
                continue

            if command_plan.skip_when_posts_empty:
                posts_csv, canonical_csv = facebook_paths(output_dir, since, before)
                post_count = count_post_urls(posts_csv)
                if post_count == 0:
                    write_empty_facebook_csv(posts_csv, canonical_csv)
                    print(
                        "Facebook: 0 posts; se confirmó un CSV canónico vacío "
                        "y no se llamó al actor de comentarios.",
                        flush=True,
                    )
                    continue

            result = subprocess.run(
                list(command_plan.command),
                cwd=REPO_ROOT,
                env=os.environ.copy(),
                check=False,
            )
            if result.returncode == 0:
                continue
            failures += 1
            print(
                f"ERROR: {command_plan.label} terminó con código "
                f"{result.returncode}.",
                file=sys.stderr,
                flush=True,
            )
            if not continue_on_error:
                return result.returncode or 1
            break
    return 1 if failures else 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Runner de extracción de Radar V1")
    parser.add_argument("--since", default=None, help="Fecha inicial YYYY-MM-DD")
    parser.add_argument("--before", default=None, help="Fecha final YYYY-MM-DD")
    parser.add_argument(
        "--sources",
        nargs="+",
        default=list(SOURCE_ORDER),
        help="Fuentes: youtube twitter medios facebook (acepta comas o 'all').",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=EXTRACTED_DATA_DIR,
        help="Raíz de salida semanal.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--list", action="store_true", help="Lista fuentes disponibles")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.list:
        for key in SOURCE_ORDER:
            print(f"{key:<10} {SOURCE_LABELS[key]}")
        return 0

    if not args.since or not args.before:
        print("ERROR: --since y --before son obligatorios.", file=sys.stderr)
        return 2

    try:
        since, before = validate_date_range(args.since, args.before)
        sources = normalize_sources(args.sources)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    for env_path in (REPO_ROOT / ".env", REPO_ROOT / ".env.local"):
        _load_env_file(env_path)
    os.environ.setdefault("PYTHONUNBUFFERED", "1")

    output_dir = args.output_dir.expanduser().resolve()
    plans = build_source_plans(sources, since, before, output_dir)
    print("=" * 72)
    print("EXTRACCIÓN RADAR V1")
    print("=" * 72)
    print(f"Periodo: {since} -> {before}")
    print("Fuentes: " + ", ".join(SOURCE_LABELS[source] for source in sources))
    print(f"Salida:  {output_dir}")
    if args.dry_run:
        print("Dry-run: se mostrarán comandos sin hacer solicitudes ni escribir datos.")

    return execute_plans(
        plans,
        since=since,
        before=before,
        output_dir=output_dir,
        dry_run=args.dry_run,
        continue_on_error=args.continue_on_error,
    )


if __name__ == "__main__":
    raise SystemExit(main())
