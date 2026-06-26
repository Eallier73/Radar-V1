#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import re
import json
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import ElasticNet
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


# =========================
# CONFIG
# =========================
ROOT_DIR = Path("/home/emilio/Documentos/RAdAR/Datos_Modelo_ML")
INPUT_FILE = ROOT_DIR / "datos_ML_master.xlsx"

# Si quieres cambiar de target después, solo cambia esta línea
TARGET_COL = "target_serie_4e"

# Horizontes en semanas
HORIZONS = [1, 2, 3, 4]

# Tamaño del holdout final para evaluación cronológica
TEST_SIZE = 8

# Carpeta de salida
OUT_DIR = ROOT_DIR / "salidas_forecast_horizontes"

# Columnas de referencia temporal / ID
ID_COLS_CANDIDATES = [
    "fecha_inicio_semana",
    "semana_iso",
    "iso_year",
    "iso_week",
]

# Columnas/series contemporáneas que NO deben entrar al forecast
# OJO: sus versiones laggeadas sí pueden entrar.
LEAKY_BASE_SERIES = [
    "consenso_mensual_3e",
    "consenso_mensual_4e",
    "demoscopia",
    "scr",
    "mitofsky",
    "rubrum_x10",
    "target_serie_3e",
    "target_serie_4e",
]

# Columnas que nunca deben usarse como feature
DROP_EXACT_ALWAYS = {
    "target_serie_3e_delta1",
    "target_serie_4e_delta1",
    "has_full_pmi_features",
    "flag_missing_sentimiento_digital",
}

# Búsqueda automática si el archivo exacto no existe
FALLBACK_PATTERNS = [
    "datos_ML_master*.xlsx",
    "*master*.xlsx",
    "*.xlsx",
]


# =========================
# UTILIDADES
# =========================
def find_input_file() -> Path:
    if INPUT_FILE.exists():
        return INPUT_FILE

    for pattern in FALLBACK_PATTERNS:
        matches = sorted(ROOT_DIR.glob(pattern))
        if matches:
            return matches[0]

    raise FileNotFoundError(
        f"No encontré el archivo master en {ROOT_DIR}. "
        f"Esperaba algo como: {INPUT_FILE.name}"
    )


def normalize_week_start_date(series: pd.Series) -> pd.Series:
    """
    Convierte fecha_inicio_semana a datetime.
    Soporta:
    - datetime ya correcto
    - string
    - serial de Excel
    """
    s = series.copy()

    if pd.api.types.is_datetime64_any_dtype(s):
        return pd.to_datetime(s)

    if pd.api.types.is_numeric_dtype(s):
        # Excel serial date: día 1 = 1899-12-31 con ajuste clásico 1899-12-30
        return pd.to_datetime("1899-12-30") + pd.to_timedelta(s, unit="D")

    # intento general para strings
    return pd.to_datetime(s, errors="coerce")


def add_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    if "iso_week" in out.columns:
        week = pd.to_numeric(out["iso_week"], errors="coerce")
        out["iso_week_sin"] = np.sin(2 * np.pi * week / 52.0)
        out["iso_week_cos"] = np.cos(2 * np.pi * week / 52.0)

    if "fecha_inicio_semana" in out.columns:
        base_date = out["fecha_inicio_semana"].min()
        out["t_index"] = (out["fecha_inicio_semana"] - base_date).dt.days // 7
        out["month"] = out["fecha_inicio_semana"].dt.month
        out["quarter"] = out["fecha_inicio_semana"].dt.quarter

    return out


def is_lagged_version(col: str, base_name: str) -> bool:
    """
    True si col es base_name_lag1, base_name_lag2, etc.
    """
    pattern = rf"^{re.escape(base_name)}_lag\d+$"
    return re.match(pattern, col) is not None


def is_lead_col(col: str) -> bool:
    return re.match(r"^target_serie_[34]e_lead\d+$", col) is not None


def should_drop_feature(col: str) -> bool:
    """
    Decide si una columna debe salir del set de features.
    Conserva lags válidos.
    """
    if col in DROP_EXACT_ALWAYS:
        return True

    if is_lead_col(col):
        return True

    # targets contemporáneos: no usar
    if col in {"target_serie_3e", "target_serie_4e"}:
        return True

    # excluir series contemporáneas de encuesta/consenso
    for base in LEAKY_BASE_SERIES:
        if col == base:
            return True

        # locf, imputadas o variantes contemporáneas también fuera
        if col.startswith(base + "_") and not is_lagged_version(col, base):
            return True

    return False


def get_numeric_feature_columns(df: pd.DataFrame, target_col: str) -> List[str]:
    """
    Selecciona features numéricas forecast-safe.
    """
    feature_cols: List[str] = []

    for col in df.columns:
        if col in ID_COLS_CANDIDATES:
            continue
        if col == target_col:
            continue
        if should_drop_feature(col):
            continue

        # convertir bool a int más adelante; aquí aceptamos numéricas/bool
        if pd.api.types.is_bool_dtype(df[col]) or pd.api.types.is_numeric_dtype(df[col]):
            feature_cols.append(col)

    return feature_cols


def remove_useless_columns(df: pd.DataFrame, feature_cols: List[str]) -> List[str]:
    """
    Quita columnas vacías o constantes.
    """
    cleaned = []
    for col in feature_cols:
        s = df[col]

        # bool -> int para contar bien
        if pd.api.types.is_bool_dtype(s):
            s = s.astype(int)

        non_na = s.dropna()
        if non_na.empty:
            continue
        if non_na.nunique() <= 1:
            continue

        cleaned.append(col)

    return cleaned


def build_forecast_dataset(df: pd.DataFrame, target_col: str, horizon: int) -> Tuple[pd.DataFrame, str]:
    """
    Crea el dataset para horizonte h:
    X_t -> y_(t+h)
    """
    out = df.copy()
    lead_col = f"{target_col}_lead{horizon}"
    out[lead_col] = out[target_col].shift(-horizon)

    feature_cols = get_numeric_feature_columns(out, target_col=lead_col)
    feature_cols = remove_useless_columns(out, feature_cols)

    keep_cols = [c for c in ID_COLS_CANDIDATES if c in out.columns] + feature_cols + [lead_col]
    dataset = out[keep_cols].copy()

    # bool -> int
    for col in feature_cols:
        if pd.api.types.is_bool_dtype(dataset[col]):
            dataset[col] = dataset[col].astype(int)

    # eliminar filas sin target futuro
    dataset = dataset[dataset[lead_col].notna()].copy()

    return dataset, lead_col


def chronological_train_test_split(df: pd.DataFrame, target_col: str, test_size: int) -> Tuple[pd.DataFrame, pd.DataFrame]:
    if len(df) <= test_size + 8:
        raise ValueError(
            f"Muy pocas filas ({len(df)}) para usar test_size={test_size}. "
            "Baja el holdout o agrega más datos."
        )

    train = df.iloc[:-test_size].copy()
    test = df.iloc[-test_size:].copy()

    if train[target_col].isna().any() or test[target_col].isna().any():
        raise ValueError("Hay targets vacíos después del split.")

    return train, test


def fit_elasticnet_forecast(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    target_col: str,
    feature_cols: List[str],
) -> Tuple[Pipeline, Dict[str, float], pd.DataFrame]:
    X_train = train_df[feature_cols].copy()
    y_train = train_df[target_col].copy()

    X_test = test_df[feature_cols].copy()
    y_test = test_df[target_col].copy()

    preprocessor = ColumnTransformer(
        transformers=[
            (
                "num",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="median")),
                        ("scaler", StandardScaler()),
                    ]
                ),
                feature_cols,
            )
        ],
        remainder="drop",
    )

    model = ElasticNet(max_iter=50000, random_state=42)

    pipe = Pipeline(
        steps=[
            ("prep", preprocessor),
            ("model", model),
        ]
    )

    n_train = len(train_df)
    n_splits = min(5, max(3, n_train // 10))

    tscv = TimeSeriesSplit(n_splits=n_splits)

    param_grid = {
        "model__alpha": [0.001, 0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
        "model__l1_ratio": [0.05, 0.2, 0.5, 0.8, 0.95, 1.0],
    }

    grid = GridSearchCV(
        estimator=pipe,
        param_grid=param_grid,
        scoring="neg_mean_absolute_error",
        cv=tscv,
        n_jobs=-1,
        refit=True,
    )

    grid.fit(X_train, y_train)

    best_model = grid.best_estimator_
    preds = best_model.predict(X_test)

    metrics = {
        "mae": float(mean_absolute_error(y_test, preds)),
        "rmse": float(np.sqrt(mean_squared_error(y_test, preds))),
        "r2": float(r2_score(y_test, preds)),
        "best_alpha": float(grid.best_params_["model__alpha"]),
        "best_l1_ratio": float(grid.best_params_["model__l1_ratio"]),
        "n_train": int(len(train_df)),
        "n_test": int(len(test_df)),
        "n_features": int(len(feature_cols)),
    }

    pred_cols = [c for c in ID_COLS_CANDIDATES if c in test_df.columns]
    pred_df = test_df[pred_cols].copy()
    pred_df["y_real"] = y_test.values
    pred_df["y_pred"] = preds
    pred_df["error"] = pred_df["y_real"] - pred_df["y_pred"]

    return best_model, metrics, pred_df


def write_excel_outputs(
    datasets: Dict[str, pd.DataFrame],
    predictions: Dict[str, pd.DataFrame],
    metrics_df: pd.DataFrame,
    out_file: Path,
) -> None:
    with pd.ExcelWriter(out_file, engine="openpyxl") as writer:
        metrics_df.to_excel(writer, sheet_name="metricas", index=False)

        for name, df in datasets.items():
            sheet = f"data_{name}"[:31]
            df.to_excel(writer, sheet_name=sheet, index=False)

        for name, df in predictions.items():
            sheet = f"pred_{name}"[:31]
            df.to_excel(writer, sheet_name=sheet, index=False)


# =========================
# MAIN
# =========================
def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    input_file = find_input_file()
    print(f"[INFO] Leyendo: {input_file}")

    df = pd.read_excel(input_file)

    # limpiar columnas vacías que a veces vienen al final
    df = df.dropna(axis=1, how="all").copy()

    # validar target
    if TARGET_COL not in df.columns:
        raise KeyError(
            f"No encontré el target '{TARGET_COL}' en el archivo. "
            f"Columnas disponibles: {list(df.columns)}"
        )

    # normalizar fecha
    if "fecha_inicio_semana" not in df.columns:
        raise KeyError("Falta la columna 'fecha_inicio_semana'.")

    df["fecha_inicio_semana"] = normalize_week_start_date(df["fecha_inicio_semana"])
    if df["fecha_inicio_semana"].isna().any():
        bad_rows = df[df["fecha_inicio_semana"].isna()].index.tolist()[:10]
        raise ValueError(f"No pude convertir algunas fechas. Filas problemáticas: {bad_rows}")

    # ordenar cronológicamente
    df = df.sort_values("fecha_inicio_semana").reset_index(drop=True)

    # asegurar iso_year / iso_week si no existen o vienen mal
    iso = df["fecha_inicio_semana"].dt.isocalendar()
    df["iso_year"] = iso.year.astype(int)
    df["iso_week"] = iso.week.astype(int)
    df["semana_iso"] = df["iso_year"].astype(str) + "-W" + df["iso_week"].astype(str).str.zfill(2)

    # features de calendario
    df = add_calendar_features(df)

    # guardar master limpio
    master_clean_path = OUT_DIR / "master_limpio_ordenado.csv"
    df.to_csv(master_clean_path, index=False, encoding="utf-8-sig")
    print(f"[OK] Master limpio guardado en: {master_clean_path}")

    datasets: Dict[str, pd.DataFrame] = {}
    predictions: Dict[str, pd.DataFrame] = {}
    metrics_rows: List[Dict[str, float]] = []

    for h in HORIZONS:
        name = f"forecast_{h}w"
        print(f"[INFO] Procesando {name}...")

        ds, lead_col = build_forecast_dataset(df, TARGET_COL, h)

        id_cols = [c for c in ID_COLS_CANDIDATES if c in ds.columns]
        feature_cols = [c for c in ds.columns if c not in id_cols + [lead_col]]

        # split cronológico
        train_df, test_df = chronological_train_test_split(ds, lead_col, TEST_SIZE)

        # entrenar
        best_model, metrics, pred_df = fit_elasticnet_forecast(
            train_df=train_df,
            test_df=test_df,
            target_col=lead_col,
            feature_cols=feature_cols,
        )

        metrics["horizon"] = h
        metrics["dataset"] = name
        metrics["target_col"] = lead_col

        datasets[name] = ds
        predictions[name] = pred_df
        metrics_rows.append(metrics)

        # guardar CSV del dataset
        ds_path = OUT_DIR / f"{name}_dataset.csv"
        ds.to_csv(ds_path, index=False, encoding="utf-8-sig")

        # guardar predicciones
        pred_path = OUT_DIR / f"{name}_predicciones_holdout.csv"
        pred_df.to_csv(pred_path, index=False, encoding="utf-8-sig")

        # guardar features utilizadas
        features_path = OUT_DIR / f"{name}_features.txt"
        with open(features_path, "w", encoding="utf-8") as f:
            for col in feature_cols:
                f.write(col + "\n")

        # guardar parámetros del modelo
        params_path = OUT_DIR / f"{name}_metricas.json"
        with open(params_path, "w", encoding="utf-8") as f:
            json.dump(metrics, f, ensure_ascii=False, indent=2)

        print(
            f"[OK] {name}: MAE={metrics['mae']:.4f} | "
            f"RMSE={metrics['rmse']:.4f} | R2={metrics['r2']:.4f} | "
            f"features={metrics['n_features']}"
        )

    metrics_df = pd.DataFrame(metrics_rows).sort_values("horizon").reset_index(drop=True)

    # guardar resumen general
    metrics_csv = OUT_DIR / "resumen_metricas.csv"
    metrics_df.to_csv(metrics_csv, index=False, encoding="utf-8-sig")

    excel_out = OUT_DIR / "forecast_horizontes_resultados.xlsx"
    write_excel_outputs(
        datasets=datasets,
        predictions=predictions,
        metrics_df=metrics_df,
        out_file=excel_out,
    )

    print("\n[FIN] Archivos generados:")
    print(f" - {OUT_DIR}")
    print(f" - {metrics_csv}")
    print(f" - {excel_out}")


if __name__ == "__main__":
    main()