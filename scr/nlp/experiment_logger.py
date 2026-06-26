#!/usr/bin/env python3
"""
Compatibilidad canónica para el logger experimental.

La implementación viva y mantenida del tracker de experimentos está en:
`Scripts/Modeling/experiment_logger.py`.

Este wrapper evita la deriva entre dos copias del mismo logger y mantiene
compatibilidad con scripts de NLP que importan `experiment_logger` desde este
directorio.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


CANONICAL_LOGGER_PATH = (
    Path(__file__).resolve().parents[1] / "Modeling" / "experiment_logger.py"
)

spec = importlib.util.spec_from_file_location(
    "radar_modeling_experiment_logger",
    CANONICAL_LOGGER_PATH,
)
if spec is None or spec.loader is None:
    raise ImportError(f"No se pudo cargar el logger canonico: {CANONICAL_LOGGER_PATH}")

module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

__all__ = [name for name in dir(module) if not name.startswith("_")]
globals().update({name: getattr(module, name) for name in __all__})


if __name__ == "__main__":
    module.main()
