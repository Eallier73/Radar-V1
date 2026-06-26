#!/usr/bin/env python3
"""
Ejemplo ejecutable para registrar un run en el grid de experimentos.

Por default NO toca el workbook real. Si no se pasa `--workbook`, crea una
copia temporal en `/tmp/grid_experimentos_radar_demo.xlsx` y escribe ahi.

Ejemplos:
    python3 Scripts/NLP_Data_Procesing/ejemplo_registro_grid.py
    python3 Scripts/NLP_Data_Procesing/ejemplo_registro_grid.py \
        --workbook /tmp/mi_grid.xlsx
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import pandas as pd

from experiment_logger import DEFAULT_WORKBOOK, RadarExperimentTracker


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ejemplo de registro automatico de un experimento en el grid del radar.",
    )
    parser.add_argument(
        "--workbook",
        type=Path,
        help="Workbook de destino. Si no se pasa, se crea una copia demo en /tmp.",
    )
    parser.add_argument(
        "--run-id",
        default="DEMO_GRID_v1",
        help="Run_ID de ejemplo.",
    )
    return parser.parse_args()


def resolve_workbook(target: Path | None) -> Path:
    if target is None:
        demo_path = Path("/tmp/grid_experimentos_radar_demo.xlsx")
        shutil.copy2(DEFAULT_WORKBOOK, demo_path)
        return demo_path

    target = target.expanduser().resolve()
    if not target.exists():
        shutil.copy2(DEFAULT_WORKBOOK, target)
    return target


def main() -> None:
    args = parse_args()
    workbook_path = resolve_workbook(args.workbook)
    tracker = RadarExperimentTracker(workbook_path=workbook_path)
    tracker.prepare_workbook()

    run = tracker.start_run(
        run_id=args.run_id,
        experiment_id="E4",
        family="boosting",
        model="LightGBM_demo",
        script_path=__file__,
        parametros={
            "lag_weeks": [1, 2, 3, 4],
            "learning_rate": 0.03,
            "num_leaves": 31,
            "max_depth": -1,
        },
    )

    for horizon in (1, 2, 3, 4):
        pred_df = pd.DataFrame(
            {
                "fecha": ["2026-02-24", "2026-03-03", "2026-03-10"],
                "y_real": [63.2, 62.8, 62.1],
                "y_pred": [63.0 - (horizon * 0.1), 62.7 - (horizon * 0.1), 62.0 - (horizon * 0.1)],
                "horizonte_sem": [horizon, horizon, horizon],
            }
        )
        run.save_dataframe(
            pred_df,
            f"predicciones_h{horizon}.csv",
            artifact_type="predicciones",
            notes=f"Predicciones demo para horizonte {horizon}.",
        )

    horizon_results = [
        {
            "horizonte_sem": 1,
            "target": "nivel",
            "variables_temporales": "lags IAD, MA, momentum",
            "variables_tematicas": "sentimiento, intensidad, temas",
            "transformacion": "original",
            "seleccion_variables": "importancia_arboles",
            "validacion": "walk-forward",
            "dataset_periodo": "2024-10-22 a 2026-03-09",
            "notas_config": "Demo de tracking automatico para horizonte 1.",
            "l_num": 0.10,
            "l_trend": 0.09,
            "l_risk": 0.08,
            "l_tol": 0.07,
            "mae": 1.25,
            "rmse": 1.64,
            "direccion_accuracy": 0.82,
            "deteccion_caidas": 0.77,
        },
        {
            "horizonte_sem": 2,
            "target": "nivel",
            "variables_temporales": "lags IAD, MA, momentum",
            "variables_tematicas": "sentimiento, intensidad, temas",
            "transformacion": "original",
            "seleccion_variables": "importancia_arboles",
            "validacion": "walk-forward",
            "dataset_periodo": "2024-10-22 a 2026-03-09",
            "notas_config": "Demo de tracking automatico para horizonte 2.",
            "l_num": 0.12,
            "l_trend": 0.10,
            "l_risk": 0.09,
            "l_tol": 0.08,
            "mae": 1.38,
            "rmse": 1.79,
            "direccion_accuracy": 0.79,
            "deteccion_caidas": 0.74,
        },
        {
            "horizonte_sem": 3,
            "target": "nivel",
            "variables_temporales": "lags IAD, MA, momentum",
            "variables_tematicas": "sentimiento, intensidad, temas",
            "transformacion": "original",
            "seleccion_variables": "importancia_arboles",
            "validacion": "walk-forward",
            "dataset_periodo": "2024-10-22 a 2026-03-09",
            "notas_config": "Demo de tracking automatico para horizonte 3.",
            "l_num": 0.14,
            "l_trend": 0.11,
            "l_risk": 0.10,
            "l_tol": 0.09,
            "mae": 1.51,
            "rmse": 1.92,
            "direccion_accuracy": 0.76,
            "deteccion_caidas": 0.71,
        },
        {
            "horizonte_sem": 4,
            "target": "nivel",
            "variables_temporales": "lags IAD, MA, momentum",
            "variables_tematicas": "sentimiento, intensidad, temas",
            "transformacion": "original",
            "seleccion_variables": "importancia_arboles",
            "validacion": "walk-forward",
            "dataset_periodo": "2024-10-22 a 2026-03-09",
            "notas_config": "Demo de tracking automatico para horizonte 4.",
            "l_num": 0.16,
            "l_trend": 0.12,
            "l_risk": 0.11,
            "l_tol": 0.10,
            "mae": 1.68,
            "rmse": 2.08,
            "direccion_accuracy": 0.73,
            "deteccion_caidas": 0.69,
        },
    ]

    run.finalize(
        horizon_results=horizon_results,
        target="nivel",
        variables_temporales="lags IAD, MA, momentum",
        variables_tematicas="sentimiento, intensidad, temas",
        transformacion="original",
        seleccion_variables="importancia_arboles",
        validacion="walk-forward",
        dataset_periodo="2024-10-22 a 2026-03-09",
        notas_config="Demostracion del flujo de tracking.",
        estado="corrido",
        comentarios="Este run es solo de ejemplo para validar la integracion.",
        l_coh=0.02,
    )

    print(f"Workbook actualizado: {workbook_path}")
    print(f"Run demo registrado: {args.run_id}")
    print(f"Artefactos guardados en: {run.run_dir}")


if __name__ == "__main__":
    main()
