#!/usr/bin/env python3
"""Lanzador visible de la GUI del pipeline Radar V1."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def main() -> None:
    gui_path = (
        Path(__file__).resolve().parent
        / "scr"
        / "compartido"
        / "00_gui_orquestador.py"
    )
    module_name = "radar_gui_orquestador"
    spec = importlib.util.spec_from_file_location(module_name, gui_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"No se pudo cargar la GUI desde {gui_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    module.main()


if __name__ == "__main__":
    main()
