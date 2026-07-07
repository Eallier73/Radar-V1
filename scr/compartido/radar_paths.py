"""Rutas canónicas del repositorio Radar."""

from __future__ import annotations

import os
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
SCR_DIR = REPO_ROOT / "scr"
DATA_DIR = REPO_ROOT / "datos"
EXTRACTED_DATA_DIR = DATA_DIR / "radar_semanal_extraido"
PROCESSED_DATA_DIR = DATA_DIR / "radar_semanal_procesado"
TEXT_DATA_DIR = DATA_DIR / "radar_semanal_texto"
STATE_DIR = REPO_ROOT / "state"


def resolve_python_executable() -> Path:
    """Resuelve el intérprete oficial de Radar con alternativas locales."""
    configured = os.getenv("RADAR_PYTHON", "").strip()
    candidates = [
        Path(configured).expanduser() if configured else None,
        REPO_ROOT / ".venv" / "bin" / "python",
        REPO_ROOT / "venv" / "bin" / "python",
        Path.home() / "anaconda3" / "envs" / "radar-v1" / "bin" / "python",
        Path(sys.executable),
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate.resolve()
    return Path(sys.executable)
