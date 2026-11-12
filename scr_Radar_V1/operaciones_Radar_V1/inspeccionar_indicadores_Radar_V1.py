#!/usr/bin/env python3
"""Inspección y regresiones exploratorias sólo con entrenamiento.

El usuario eligió la polaridad Original como variable dependiente. No abre
prueba, verificación ni la tabla completa para calcular estadísticas.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from generar_conjuntos_temporales_Radar_V1 import cargar_desarrollo, digest, validate_weekly_columns

META = ("semana_iso", "Fecha_Semana", "Fecha_Fin")
DEFAULT_TARGET = "Sentimiento_Conjunto_Original_Original"
HORIZONS = (1, 2, 3, 4)


def inspect_training(development_dir: Path, target: str | None = None) -> tuple[dict, list[dict], list[dict]]:
    path = development_dir / "entrenamiento_Radar_V1/indicadores_Radar_V1.csv"
    before = digest(path)
    rows = list(cargar_desarrollo(development_dir, "entrenamiento"))
    if not rows:
        raise ValueError("Entrenamiento está vacío")
    validate_weekly_columns(rows[0])
    excluded_history = [c for c in rows[0] if target is not None and c.startswith(target + "_lag")]
    columns = [c for c in rows[0] if c not in META and c not in excluded_history]
    if not columns:
        raise ValueError("No hay columnas numéricas para inspeccionar")
    frame = pd.DataFrame(rows)
    values = frame[columns].apply(pd.to_numeric, errors="raise")
    if np.isinf(values.to_numpy()).any():
        raise ValueError("Se encontraron valores infinitos")
    complete_mask = values.notna().all(axis=1)
    complete = values.loc[complete_mask]
    if len(complete) < 3:
        raise ValueError("No hay suficientes filas semanales completas")
    summaries = []
    for column in columns:
        series = complete[column]
        quartiles = series.quantile([.25, .5, .75])
        summaries.append({"variable": column, "n_comparable": len(complete),
            "n_observado_en_bloque": int(values[column].notna().sum()),
            "faltantes_en_bloque": int(values[column].isna().sum()),
            "media": float(series.mean()), "desviacion_estandar": float(series.std(ddof=1)),
            "minimo": float(series.min()), "q25": float(quartiles.loc[.25]),
            "mediana": float(quartiles.loc[.5]), "q75": float(quartiles.loc[.75]),
            "maximo": float(series.max()), "valores_distintos": int(series.nunique()),
            "constante": bool(series.nunique() <= 1)})
    nonconstant = [item["variable"] for item in summaries if not item["constante"]]
    pearson = complete[nonconstant].corr()
    spearman = complete[nonconstant].rank().corr()
    pairs = []
    for i, first in enumerate(nonconstant):
        for second in nonconstant[i + 1:]:
            p, s = float(pearson.loc[first, second]), float(spearman.loc[first, second])
            if np.isfinite(p) and np.isfinite(s):
                pairs.append({"variable_1": first, "variable_2": second,
                              "pearson": p, "spearman": s, "abs_pearson": abs(p)})
    pairs.sort(key=lambda row: row["abs_pearson"], reverse=True)
    if nonconstant:
        centered = complete[nonconstant].to_numpy(dtype=float)
        centered = (centered - centered.mean(axis=0)) / centered.std(axis=0, ddof=0)
        rank = int(np.linalg.matrix_rank(centered))
    else:
        rank = 0
    report = {"scope": "training_only", "training_rows": len(rows),
        "complete_rows": len(complete), "rows_without_full_history": len(rows) - len(complete),
        "numeric_candidates": len(columns), "nonconstant_candidates": len(nonconstant),
        "constant_columns": [item["variable"] for item in summaries if item["constante"]],
        "centered_matrix_rank": rank, "max_centered_rank": len(complete) - 1,
        "full_column_rank": rank == len(nonconstant),
        "pairs_abs_pearson_ge_090": sum(item["abs_pearson"] >= .9 for item in pairs),
        "period_start": rows[0]["Fecha_Semana"], "period_end": rows[-1]["Fecha_Fin"],
        "complete_period_start": frame.loc[complete_mask, "Fecha_Semana"].iloc[0],
        "input_table": str(path), "input_sha256": before,
        "missing_values_imputed": False, "heldout_data_opened": False,
        "excluded_target_history": excluded_history,
        "target": None, "regressions_run": False,
        "regression_status": "awaiting_user_choice_of_dependent_variable",
        "interpretation": "descriptive_associations_not_causal_effects_or_variable_importances"}
    if digest(path) != before:
        raise ValueError("Cambió la tabla durante la inspección")
    return report, summaries, pairs


def write_rows(path: Path, rows: list[dict], columns=None):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def regress_training(development_dir: Path, target: str, horizon: int = 1):
    """Asocia X(t) con Y(t+h) semanal sin promedios, dentro del bloque inicial.

    Ridge usa alpha=1 fijado de antemano; 0.1 y 10 sólo muestran sensibilidad.
    No se reportan p-valores iid para estas observaciones temporales.
    """
    if type(horizon) is not int or horizon not in HORIZONS:
        raise ValueError("El horizonte debe ser 1, 2, 3 o 4 semanas")
    path = development_dir / "entrenamiento_Radar_V1/indicadores_Radar_V1.csv"
    before = digest(path)
    rows = list(cargar_desarrollo(development_dir, "entrenamiento"))
    if not rows:
        raise ValueError("El bloque inicial está vacío")
    validate_weekly_columns(rows[0])
    columns = [c for c in rows[0] if c not in META]
    if target not in columns:
        raise ValueError(f"La variable dependiente no existe: {target}")
    excluded_history = [c for c in columns if c.startswith(target + "_lag")]
    candidates = [c for c in columns if c != target and c not in excluded_history]
    source = pd.DataFrame(rows)
    dates = pd.to_datetime(source["Fecha_Semana"], errors="raise")
    if not dates.diff().iloc[1:].eq(pd.Timedelta(weeks=1)).all():
        raise ValueError("Las semanas deben ser consecutivas y estar ordenadas")
    values = source[[target] + candidates].apply(pd.to_numeric, errors="raise")
    if np.isinf(values.to_numpy()).any():
        raise ValueError("Se encontraron valores infinitos")
    # El desplazamiento se hace DESPUÉS de cargar únicamente el bloque inicial.
    # Las últimas h filas no tienen respuesta elegible; jamás se busca en prueba.
    values[target] = values[target].shift(-horizon)
    eligible = values.iloc[:-horizon]
    frame = eligible.dropna()
    if len(frame) < 3 or not np.isfinite(frame.to_numpy()).all():
        raise ValueError("Se requieren al menos tres filas completas y finitas")
    constants = [c for c in candidates if frame[c].nunique() <= 1]
    predictors = [c for c in candidates if c not in constants]
    if not predictors:
        raise ValueError("No hay predictores no constantes")
    raw_x, raw_y = frame[predictors].to_numpy(dtype=float), frame[target].to_numpy(dtype=float)
    xmean, xscale = raw_x.mean(axis=0), raw_x.std(axis=0, ddof=0)
    ymean, yscale = raw_y.mean(), raw_y.std(ddof=0)
    if not yscale:
        raise ValueError("La variable dependiente es constante")
    x, y = (raw_x - xmean) / xscale, (raw_y - ymean) / yscale
    univariate = []
    for index, name in enumerate(predictors):
        beta = float(x[:, index] @ y / (x[:, index] @ x[:, index]))
        slope = beta * yscale / xscale[index]
        univariate.append({"horizonte_semanas": horizon, "variable": name, "n": len(frame), "beta_estandarizado": beta,
            "pendiente_original": float(slope), "intercepto_original": float(ymean - slope * xmean[index]),
            "r2_exploratorio": beta * beta, "abs_beta": abs(beta)})
    univariate.sort(key=lambda row: row["abs_beta"], reverse=True)
    coefficients, fits = {}, {}
    gram = x @ x.T
    for alpha in (.1, 1., 10.):
        coef = x.T @ np.linalg.solve(gram + alpha * np.eye(len(frame)), y)
        coefficients[alpha] = coef
        fits[str(alpha)] = float(1 - np.sum((y - x @ coef) ** 2) / np.sum(y ** 2))
    ridge = []
    for index, name in enumerate(predictors):
        values = [float(coefficients[alpha][index]) for alpha in (.1, 1., 10.)]
        signs = [int(np.sign(v)) if abs(v) > 1e-12 else 0 for v in values]
        ridge.append({"horizonte_semanas": horizon, "variable": name,
            "tipo": "tematico",
            "beta_ridge_alpha_01": values[0], "beta_ridge_alpha_1": values[1],
            "beta_ridge_alpha_10": values[2], "abs_beta_ridge_alpha_1": abs(values[1]),
            "signo_estable_en_tres_alphas": len(set(signs)) == 1})
    ridge.sort(key=lambda row: row["abs_beta_ridge_alpha_1"], reverse=True)
    ridge = [{"rango": rank, **row} for rank, row in enumerate(ridge, 1)]
    if digest(path) != before:
        raise ValueError("Cambió entrenamiento durante las regresiones")
    alignment = [{"horizonte_semanas": horizon,
        "semana_origen": rows[i]["semana_iso"], "fecha_origen": rows[i]["Fecha_Semana"],
        "semana_objetivo": rows[i + horizon]["semana_iso"],
        "fecha_objetivo": rows[i + horizon]["Fecha_Semana"]} for i in frame.index]
    report = {"target": target, "horizon_weeks": horizon,
        "regressions_run": True, "regression_status": "exploratory_training_only",
        "regression_rows": len(frame), "regression_predictors": len(predictors),
        "origins_purged_at_block_end": min(horizon, len(rows)),
        "eligible_origins_without_complete_history": len(eligible) - len(frame),
        "origin_period_start": alignment[0]["fecha_origen"],
        "origin_period_end": alignment[-1]["fecha_origen"],
        "target_period_start": alignment[0]["fecha_objetivo"],
        "target_period_end": alignment[-1]["fecha_objetivo"],
        "alignment": alignment, "targets_confined_to_initial_block": True,
        "target_excluded_from_predictors": target not in predictors,
        "excluded_target_history": excluded_history,
        "constant_predictors_excluded": constants, "scaling_scope": "complete_training_rows_only",
        "ridge_alpha_primary": 1., "ridge_alpha_sensitivity": [.1, 10.],
        "ridge_r2_in_sample_not_validation": fits, "p_values_reported": False,
        "interpretation": "standardized_associations_not_causal_effects_or_validated_forecast_importances",
        "heldout_data_opened": False, "forecast_model_trained": False}
    report["regression_alignment"] = f"weekly y(t+{horizon}) versus weekly thematic x(t)"
    report.update({"smoothing_applied": False, "predictor_lags": [], "target_window_weeks": 1})
    return report, univariate, ridge


def generate(development_dir: Path, output: Path, target: str | None = None):
    if output.exists():
        raise FileExistsError(f"Se conserva la inspección existente: {output}")
    report, summaries, pairs = inspect_training(development_dir, target=target)
    univariate, ridge = [], []
    if target is not None:
        horizons = []
        for horizon in HORIZONS:
            result, individual, joint = regress_training(development_dir, target, horizon)
            horizons.append(result)
            univariate.extend(individual)
            ridge.extend(joint)
        report.update({"target": target, "regressions_run": True,
            "regression_status": "exploratory_training_only_by_future_horizon",
            "horizons_weeks": list(HORIZONS), "regressions_by_horizon": horizons,
            "target_excluded_from_predictors": True,
            "targets_confined_to_initial_block": True, "forecast_model_trained": False})
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        write_rows(staging / "descriptivos_Radar_V1.csv", summaries)
        write_rows(staging / "correlaciones_Radar_V1.csv", pairs,
                   ["variable_1", "variable_2", "pearson", "spearman", "abs_pearson"])
        if target is not None:
            write_rows(staging / "regresiones_univariadas_Radar_V1.csv", univariate)
            write_rows(staging / "regresion_ridge_Radar_V1.csv", ridge)
            write_rows(staging / "alineacion_horizontes_Radar_V1.csv",
                       [row for result in horizons for row in result["alignment"]])
        report["output_sha256"] = {p.name: digest(p) for p in staging.iterdir()}
        (staging / "diagnostico_Radar_V1.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        lines = ["# Inspección descriptiva de indicadores", "",
            f"Sólo bloque inicial: {report['training_rows']} semanas; {report['complete_rows']} con indicadores semanales completos. No se añade historia ni se suaviza X o Y.", "",
            f"Hay {report['numeric_candidates']} candidatos numéricos y {report['nonconstant_candidates']} no constantes. El rango de la matriz centrada es {report['centered_matrix_rank']}.", "",
            f"Pares con correlación absoluta de Pearson de al menos 0.90: {report['pairs_abs_pearson_ge_090']}.", "",
            "Las correlaciones describen asociación entre columnas; no constituyen pesos de una regresión ni efectos causales. Presencia e intensidad de un mismo tema pueden ser redundantes incluso sin suavizado.", "",
            (f"Variable dependiente elegida: `{target}` en t+1, t+2, t+3 y t+4, con explicativas disponibles hasta t. Se ejecutaron regresiones lineales por candidato y una regresión conjunta Ridge estandarizada para cada horizonte con alpha=1, fijado de antemano. Los coeficientes con alpha=0.1 y 10 muestran sensibilidad; no se eligió alpha usando datos reservados."
             if target is not None else "No se ejecutaron regresiones: falta que el usuario fije la variable dependiente.") + " No se abrieron prueba ni verificación. No se rellenaron faltantes.", "",
            "Los detalles por columna están en `descriptivos_Radar_V1.csv` y los pares en `correlaciones_Radar_V1.csv`. Las columnas constantes y el rango se registran en `diagnostico_Radar_V1.json`.", "",
            "Referencias: [coeficientes y variables correlacionadas](https://scikit-learn.org/stable/auto_examples/inspection/plot_linear_model_coefficient_interpretation.html), [Ridge](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html).", ""]
        if target is not None:
            lines += ["## Coeficientes conjuntos de mayor magnitud", "",
                "Estos coeficientes describen asociación condicionada y penalizada dentro del bloque inicial. No son efectos causales, porcentajes de importancia ni resultados validados fuera de muestra. No se reportan p-valores que supongan semanas independientes.", "",
                "La respuesta semanal se desplaza sólo dentro del bloque inicial. Para cada horizonte se retiran sus últimas h filas de origen. La estandarización se ajusta por separado a los pares elegibles de cada horizonte. Esta inspección usa los pesos del ajuste completo inicial y no acredita un backtest cronológico; la selección temporal reconstruye los pesos por prefijo.", ""]
            for result in horizons:
                h = result["horizon_weeks"]
                lines += [f"### Horizonte {h}: {result['regression_rows']} pares completos", "",
                    f"Origen: {result['origin_period_start']} a {result['origin_period_end']}; objetivo: {result['target_period_start']} a {result['target_period_end']}.", "",
                    "| Variable | Beta Ridge estandarizado, alpha=1 | Signo estable (0.1, 1, 10) |", "|---|---:|---|"]
                lines += [f"| {row['variable']} | {row['beta_ridge_alpha_1']:.4f} | {'sí' if row['signo_estable_en_tres_alphas'] else 'no'} |" for row in ridge if row["horizonte_semanas"] == h and row["rango"] <= 10]
                lines += [""]
            lines += ["Los coeficientes completos están en `regresion_ridge_Radar_V1.csv`; las asociaciones por separado están en `regresiones_univariadas_Radar_V1.csv`. Cada fila identifica su horizonte. `alineacion_horizontes_Radar_V1.csv` registra las fechas de origen y respuesta para auditar el desplazamiento. La polaridad está fuera de X. Las explicativas son temáticas y de la semana t. La tabla de indicadores de trabajo sigue siendo una sola y no fue modificada por la inspección.", ""]
        (staging / "inspeccion_Radar_V1.md").write_text("\n".join(lines), encoding="utf-8")
        staging.rename(output)
    except BaseException:
        shutil.rmtree(staging)
        raise
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development-dir", type=Path, default=ROOT / "datos_Radar_V1/radar_modelado_Radar_V1/desarrollo_Radar_V1")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "datos_Radar_V1/radar_analisis_Radar_V1/inspeccion_indicadores_Radar_V1")
    parser.add_argument("--target", default=DEFAULT_TARGET, help="Variable dependiente; por defecto Original, elegida por el usuario")
    args = parser.parse_args()
    report = generate(args.development_dir, args.output_dir, target=args.target)
    print(json.dumps({key: report[key] for key in ("training_rows", "complete_rows", "numeric_candidates", "centered_matrix_rank", "regression_status")}, indent=2))


if __name__ == "__main__":
    main()
