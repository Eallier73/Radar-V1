"""Preparación histórica de tablas de indicadores, copiada de Modelo_ML_MV.ipynb.

Origen: /home/emilio/Datos/Ipsel/IPSEL_Tampico/Ml_Monica_Villarreal/Datos/Jupyter/Modelo_ML_MV.ipynb
Celda de código: índice 37 (base cero), última implementación ejecutada.
Funciones originales, sin entrenamiento ni predicción. No calcula indicadores
textuales, MA5 ni ponderaciones. Escala el conjunto completo, incluido el objetivo:
uso retrospectivo; no usar este ajuste global para evaluar predicciones futuras.
Véase documentos/PREPARACION_DATOS_NOTEBOOK.md para el alcance y la procedencia.
"""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

def detectar_columna_target(df: pd.DataFrame) -> str:
    """Detecta la columna del índice objetivo."""
    candidatos_preferidos = [
        "IAOPD_MA5", "IAD_global_MA5", "Indice_Aceptacion_MA5", "IAOPD_global_MA5"
    ]
    for c in candidatos_preferidos:
        if c in df.columns:
            return c

    poss = [c for c in df.columns
            if ("IAD" in c.upper() or "IAOPD" in c.upper()) and ("MA5" in c.upper())]
    if len(poss) == 0:
        raise ValueError("No encontré columna objetivo tipo IAOPD/IAD_MA5.")
    return poss[0]


def detectar_columnas_tiempo(df: pd.DataFrame):
    """Detecta columnas de semana / fecha para ordenar cronológicamente."""
    week_candidates = ["semana_iso", "semana", "week_label"]
    date_candidates = ["Fecha_Semana", "fecha_semana", "fecha", "date"]

    week_col, date_col = None, None
    for c in week_candidates:
        if c in df.columns:
            week_col = c
            break
    for c in date_candidates:
        if c in df.columns:
            date_col = c
            break

    return week_col, date_col


def preparar_dataset_completo(file_path: Path, dataset_nombre: str):
    """Prepara un dataset completo: carga, ordena, escala."""
    print(f"\n📁 PREPARANDO {dataset_nombre}")
    print(f"   Archivo: {file_path}")

    df_raw = pd.read_csv(file_path)
    print(f"   Shape original: {df_raw.shape}")

    week_col, date_col = detectar_columnas_tiempo(df_raw)
    if week_col:
        df = df_raw.sort_values(week_col).reset_index(drop=True)
    elif date_col:
        df = df_raw.sort_values(date_col).reset_index(drop=True)
    else:
        df = df_raw.copy()

    target_col = detectar_columna_target(df)

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    exclude_cols = {week_col, date_col, target_col}
    exclude_cols.update([c for c in df.columns if isinstance(c, str) and "encuesta" in c.lower()])
    constant_cols = [c for c in numeric_cols if df[c].nunique() <= 1]

    feature_cols = [c for c in numeric_cols
                    if c not in exclude_cols and c not in constant_cols]

    # NUEVO: Filtrar variables dependientes adicionales que no deben aparecer como features
    variables_dependientes = ['IAD_global', 'IAD_global_MA5', 'IAD_global_suavizado', 'IAOPD_MA5']
    feature_cols = [c for c in feature_cols if c not in variables_dependientes]

    print(f"   Variables dependientes filtradas: {[c for c in variables_dependientes if c in numeric_cols]}")
    print(f"   Features finales: {len(feature_cols)}")

    scaler = StandardScaler()
    cols_to_scale = feature_cols + [target_col]
    scaled_array = scaler.fit_transform(df[cols_to_scale])

    df_scaled = df.copy()
    df_scaled[cols_to_scale] = scaled_array

    target_mean = scaler.mean_[-1]
    target_std = scaler.scale_[-1]

    print(f"   Target: {target_col}")
    print(f"   Features disponibles: {len(feature_cols)}")

    return df_scaled, df, target_col, feature_cols, target_mean, target_std, scaler
