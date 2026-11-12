#!/usr/bin/env python3
"""Selecciona columnas para los cuatro horizontes usando sólo el bloque inicial.

Recalcula pesos, orden y controles de redundancia dentro de cada corte temporal.
Las regresiones son instrumentos de selección; no se publica un pronosticador.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from generar_conjuntos_temporales_Radar_V1 import cargar_desarrollo, digest
from inspeccionar_indicadores_Radar_V1 import DEFAULT_TARGET, HORIZONS, META, write_rows, validate_weekly_columns

LABELS = ("Youtube", "XTwitter", "Facebook", "Medios")
CUTS = (28, 35, 42, 49)
ALPHAS = (.1, 1., 10.)
PROTOCOL = {
    "scope": "initial_56_weeks_only", "target": DEFAULT_TARGET,
    "horizons_weeks": list(HORIZONS), "initial_prefix_sizes": list(CUTS),
    "validation_block_weeks": 7, "source_weight_exponent": .5,
    "ranking": "median_absolute_standardized_ridge_coefficient_rank_over_4_horizons_and_3_alphas",
    "ridge_alpha_for_subset_comparison": 1., "ranking_alphas": list(ALPHAS),
    "redundancy_absolute_correlation_threshold": .85,
    "redundancy_correlations": ["pearson", "spearman"], "maximum_vif": 5.,
    "size_rule": "smallest_k_with_mean_loss_at_most_minimum_mean_plus_one_block_SE_at_minimum",
    "loss": "mean_over_horizons_of_MSE_divided_by_prefix_training_target_variance",
    "include_intercept_only_k0": True, "missing_values_imputed": False,
    "external_test_or_verification_used": False,
    "predictor_lags": [], "smoothing_applied": False, "target_window_weeks": 1,
    "SE_interpretation": "parsimony_heuristic_across_4_temporal_blocks_not_a_confidence_interval",
    "monica_ablation": ["exclude_weekly_presence_measure", "exclude_both_weekly_MV_measures"],
}


@dataclass
class Inputs:
    rows: list[dict]
    bases: list[str]
    names: list[str]
    rates: np.ndarray  # semana, fuente, indicador actual sin ponderar ni suavizar
    words: np.ndarray
    evidence: dict


def load_inputs(development: Path, support: Path) -> Inputs:
    path = development / "entrenamiento_Radar_V1/indicadores_Radar_V1.csv"
    rows = list(cargar_desarrollo(development, "entrenamiento"))
    if len(rows) != 56:
        raise ValueError("La selección requiere exclusivamente las 56 semanas iniciales")
    dates = pd.to_datetime([row["Fecha_Semana"] for row in rows])
    if not (dates[1:] - dates[:-1] == pd.Timedelta(weeks=1)).all():
        raise ValueError("Las semanas deben ser consecutivas y estar ordenadas")
    if any(d.weekday() != 0 for d in dates):
        raise ValueError("Las semanas deben comenzar en lunes")
    validate_weekly_columns(rows[0])
    bases = [c for c in rows[0] if c not in META]
    if DEFAULT_TARGET not in bases:
        raise ValueError("Falta la respuesta Original semanal")
    names = [c for c in rows[0] if c not in META and c != DEFAULT_TARGET
             and not c.startswith(DEFAULT_TARGET + "_lag")]
    if (not names or any(not c.startswith(("intensidad_por_1000_Conjunto_", "presencia_segmentos30_pct_Conjunto_"))
                         for c in names) or any("Etiquetado" in c for c in rows[0])):
        raise ValueError("Las explicativas deben ser exclusivamente temáticas, sin Etiquetado")
    audit = json.loads((support.parent / "auditoria_Radar_V1.json").read_text())
    if audit.get("corpus_origin_policy") != "current_repository_only":
        raise ValueError("El soporte debe proceder del corpus actual")
    columns = [f"palabras_{label}" for label in LABELS]
    columns += [base.replace("_Conjunto_", f"_{label}_")
                for label in LABELS for base in bases]
    prefix = []
    # Se consumen exactamente 56 filas; no se carga ni analiza el resto del soporte.
    with support.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for expected in rows:
            row = next(reader, None)
            if row is None or any(row[c] != expected[c] for c in META):
                raise ValueError("El soporte y el bloque inicial no tienen las mismas semanas")
            prefix.append({c: row[c] for c in list(META) + columns})
    words = np.array([[float(row[f"palabras_{label}"]) for label in LABELS] for row in prefix])
    rates = np.array([[[float(row[base.replace("_Conjunto_", f"_{label}_")])
                        for base in bases] for label in LABELS] for row in prefix])
    if not np.isfinite(words).all() or not np.isfinite(rates).all() or (words <= 0).any():
        raise ValueError("El soporte inicial requiere tasas finitas y volúmenes positivos")
    evidence = {"input_table": str(path), "input_sha256": digest(path),
        "support_path": str(support), "support_numeric_rows_consumed": len(prefix),
        "support_prefix_sha256": hashlib.sha256(json.dumps(prefix, sort_keys=True).encode()).hexdigest(),
        "support_full_table_loaded": False, "corpus_origin_policy": "current_repository_only"}
    inputs = Inputs(rows, bases, names, rates, words, evidence)
    x, y, _ = rebuild(inputs, 56)
    expected_x = pd.DataFrame(rows)[names].apply(pd.to_numeric, errors="raise").to_numpy()
    expected_y = np.array([float(row[DEFAULT_TARGET]) for row in rows])
    if (not np.allclose(x, expected_x, rtol=1e-10, atol=1e-10, equal_nan=True)
            or not np.allclose(y, expected_y, rtol=1e-10, atol=1e-10)):
        raise ValueError("El soporte inicial no reproduce los indicadores de la tabla vigente")
    return inputs


def rebuild(inputs: Inputs, prefix_size: int):
    """Pesos ajustados sólo al prefijo y tasas de cada semana, sin MA5 ni lags."""
    scores = np.sqrt(inputs.words[:prefix_size].sum(axis=0))
    weights = scores / scores.sum()
    joint = np.einsum("nsb,s->nb", inputs.rates, weights)
    lookup = {base: joint[:, i] for i, base in enumerate(inputs.bases)}
    return np.column_stack([lookup[name] for name in inputs.names]), lookup[DEFAULT_TARGET], weights


def paired(x, y, prefix_size: int, horizon: int):
    if type(horizon) is not int or horizon not in HORIZONS:
        raise ValueError("El horizonte debe ser 1, 2, 3 o 4 semanas")
    origins = np.arange(prefix_size - horizon)
    valid = np.isfinite(x[origins]).all(axis=1) & np.isfinite(y[origins + horizon])
    origins = origins[valid]
    if len(origins) < 3:
        raise ValueError("No hay suficientes pares completos dentro del prefijo")
    return x[origins], y[origins + horizon], origins


def standardized_fit(raw_x, raw_y, alpha=1.):
    mean_x, scale_x = raw_x.mean(axis=0), raw_x.std(axis=0)
    mean_y, scale_y = float(raw_y.mean()), float(raw_y.std())
    if scale_y <= 1e-12 or (scale_x <= 1e-12).any():
        raise ValueError("La regresión requiere respuesta y explicativas no constantes")
    x, y = (raw_x - mean_x) / scale_x, (raw_y - mean_y) / scale_y
    if x.shape[1] <= len(x):
        beta = np.linalg.solve(x.T @ x + alpha * np.eye(x.shape[1]), x.T @ y)
    else:
        beta = x.T @ np.linalg.solve(x @ x.T + alpha * np.eye(len(x)), y)
    return beta, mean_x, scale_x, mean_y, scale_y


def vifs(x):
    """VIF de cada explicativa contra todas las demás, con intercepto."""
    z = (x - x.mean(axis=0)) / x.std(axis=0)
    if z.shape[1] == 1:
        return np.ones(1)
    output = []
    for j in range(z.shape[1]):
        others = np.delete(z, j, axis=1)
        residual = z[:, j] - others @ np.linalg.lstsq(others, z[:, j], rcond=None)[0]
        fraction = float(residual @ residual / (z[:, j] @ z[:, j]))
        output.append(1 / fraction if fraction > 1e-12 else math.inf)
    return np.array(output)


def rank_and_prune(inputs: Inputs, prefix_size: int, correlation_limit=.85, vif_limit=5.):
    x, y, weights = rebuild(inputs, prefix_size)
    samples = {h: paired(x, y, prefix_size, h) for h in HORIZONS}
    usable = [j for j in range(len(inputs.names))
              if all(raw_x[:, j].std() > 1e-12 for raw_x, _, _ in samples.values())]
    if not usable:
        raise ValueError("No hay explicativas no constantes")
    ranks, details = [], []
    for h, (raw_x, raw_y, origins) in samples.items():
        for alpha in ALPHAS:
            beta, *_ = standardized_fit(raw_x[:, usable], raw_y, alpha)
            order = rankdata(-np.abs(beta), method="average")
            ranks.append(order)
            details.extend({"prefijo_semanas": prefix_size, "horizonte_semanas": h,
                "alpha": alpha, "variable": inputs.names[j], "rango": float(order[k]),
                "beta_estandarizado": float(beta[k]), "n_pares": len(origins)}
                for k, j in enumerate(usable))
    ranks = np.array(ranks)
    median = dict(zip(usable, np.median(ranks, axis=0)))
    average = dict(zip(usable, ranks.mean(axis=0)))
    ordered = sorted(usable, key=lambda j: (median[j], average[j], inputs.names[j]))
    complete = x[:prefix_size]
    complete = complete[np.isfinite(complete).all(axis=1)]
    pearson = np.corrcoef(complete[:, usable], rowvar=False) if len(usable) > 1 else np.ones((1, 1))
    ranked_x = np.apply_along_axis(rankdata, 0, complete[:, usable])
    spearman = np.corrcoef(ranked_x, rowvar=False) if len(usable) > 1 else np.ones((1, 1))
    position = {j: i for i, j in enumerate(usable)}
    path, decisions = [], []
    for j in ordered:
        related = [k for k in path if max(abs(pearson[position[j], position[k]]),
                                         abs(spearman[position[j], position[k]])) >= correlation_limit]
        trial = complete[:, path + [j]]
        max_vif = float(vifs(trial).max())
        reason = "correlacion_alta" if related else "vif_alto" if max_vif > vif_limit else "retenida_en_ruta"
        decisions.append({"prefijo_semanas": prefix_size, "variable": inputs.names[j],
            "rango_mediano_12_ajustes": float(median[j]), "rango_promedio": float(average[j]),
            "decision": reason, "redundante_con": ";".join(inputs.names[k] for k in related),
            "max_vif_si_se_incluye": max_vif if np.isfinite(max_vif) else "infinito"})
        if reason == "retenida_en_ruta":
            path.append(j)
    return {"x": x, "y": y, "weights": weights, "samples": samples, "path": path,
            "details": details, "decisions": decisions, "complete_x": complete,
            "constant_excluded": [inputs.names[j] for j in range(len(inputs.names)) if j not in usable]}


def choose_size(losses: list[dict]):
    """Una observación por bloque: promedio de los cuatro horizontes."""
    grid = sorted({row["k"] for row in losses})
    summary = []
    for k in grid:
        values = np.array([row["loss"] for row in losses if row["k"] == k])
        summary.append({"k": k, "error_medio": float(values.mean()),
            "error_estandar_entre_bloques": float(values.std(ddof=1) / np.sqrt(len(values))),
            "bloques": len(values)})
    best = min(summary, key=lambda row: (row["error_medio"], row["k"]))
    threshold = best["error_medio"] + best["error_estandar_entre_bloques"]
    selected = min(row["k"] for row in summary if row["error_medio"] <= threshold + 1e-12)
    for row in summary:
        row.update({"dentro_de_un_error_estandar": row["error_medio"] <= threshold + 1e-12,
                    "seleccionado": row["k"] == selected})
    return selected, summary, threshold, best["k"]


def analyze(inputs: Inputs):
    folds = [rank_and_prune(inputs, cut) for cut in CUTS]
    final = rank_and_prune(inputs, 56)
    # Se comparan todos los tamaños identificables en todos los cortes, incluido k=0.
    max_k = min(min(len(fold["path"]),
        min(len(sample[2]) - 2 for sample in fold["samples"].values())) for fold in folds)
    losses, by_horizon, boundaries = [], [], []
    for cut, fold in zip(CUTS, folds):
        origins = np.arange(cut, min(cut + 7, 56 - max(HORIZONS)))
        for h, (_, _, fit_origins) in fold["samples"].items():
            boundaries.append({"prefijo_semanas": cut, "horizonte_semanas": h,
                "ultimo_origen_ajuste": inputs.rows[fit_origins[-1]]["Fecha_Semana"],
                "ultima_respuesta_ajuste": inputs.rows[fit_origins[-1] + h]["Fecha_Semana"],
                "inicio_comparacion": inputs.rows[origins[0]]["Fecha_Semana"],
                "ultimo_origen_comparacion": inputs.rows[origins[-1]]["Fecha_Semana"],
                "ultima_respuesta_comparacion": inputs.rows[origins[-1] + h]["Fecha_Semana"],
                "n_pares_ajuste": len(fit_origins), "n_pares_comparacion": len(origins),
                **{f"peso_{s}": float(w) for s, w in zip(LABELS, fold["weights"])}})
        for k in range(max_k + 1):
            horizon_losses = []
            indices = fold["path"][:k]
            for h, (raw_x, raw_y, _) in fold["samples"].items():
                observed = fold["y"][origins + h]
                if k:
                    beta, mx, sx, my, sy = standardized_fit(raw_x[:, indices], raw_y)
                    predicted = my + sy * ((fold["x"][origins][:, indices] - mx) / sx @ beta)
                else:
                    my, sy = float(raw_y.mean()), float(raw_y.std())
                    predicted = np.full(len(origins), my)
                loss = float(np.mean(((observed - predicted) / sy) ** 2))
                horizon_losses.append(loss)
                by_horizon.append({"prefijo_semanas": cut, "horizonte_semanas": h,
                    "k": k, "n_comparacion": len(origins), "mse_normalizado": loss})
            losses.append({"cut": cut, "k": k, "loss": float(np.mean(horizon_losses))})
    selected_k, curve, threshold, best_k = choose_size(losses)
    if len(final["path"]) < selected_k:
        raise ValueError("La ruta final no admite el tamaño elegido; no se fuerza una selección distinta")
    selected_indices = final["path"][:selected_k]
    selected_names = [inputs.names[j] for j in selected_indices]
    horizon_curves, horizon_sizes = [], {}
    for h in HORIZONS:
        h_losses = [{"cut": row["prefijo_semanas"], "k": row["k"], "loss": row["mse_normalizado"]}
                    for row in by_horizon if row["horizonte_semanas"] == h]
        h_size, h_curve, h_threshold, h_best = choose_size(h_losses)
        horizon_sizes[str(h)] = {"selected_k": h_size, "k_minimum_mean_error": h_best,
                                 "one_SE_threshold": h_threshold}
        horizon_curves.extend({"horizonte_semanas": h, **row} for row in h_curve)
    details = [row for result in folds + [final] for row in result["details"]]
    stability = []
    for name in inputs.names:
        frequencies = [name in [inputs.names[j] for j in fold["path"][:selected_k]] for fold in folds]
        primary = [row for row in final["details"] if row["variable"] == name and row["alpha"] == 1.]
        item = {"variable": name, "seleccionada": name in selected_names,
            "cortes_que_la_retienen": sum(frequencies), "cortes_comparados": len(folds),
            "frecuencia_en_cortes": sum(frequencies) / len(folds)}
        item.update({key: None for h in HORIZONS for key in (f"rango_h{h}", f"beta_h{h}")})
        for row in primary:
            h = row["horizonte_semanas"]
            item.update({f"rango_h{h}": row["rango"], f"beta_h{h}": row["beta_estandarizado"]})
        item["mismo_signo_en_4_horizontes"] = len(primary) == 4 and len({np.sign(row["beta_estandarizado"]) for row in primary}) == 1
        stable_alphas = []
        for h in HORIZONS:
            signs = [int(np.sign(row["beta_estandarizado"])) for row in final["details"]
                     if row["variable"] == name and row["horizonte_semanas"] == h]
            stable_alphas.append(len(signs) == 3 and len(set(signs)) == 1)
        item["horizontes_con_signo_estable_entre_alphas"] = sum(stable_alphas)
        stability.append(item)
    # También se distingue estabilidad de tema/medida de estabilidad de rezago.
    family = lambda name: name.rsplit("_lag", 1)[0] if "_lag" in name else name
    families = []
    for base in dict.fromkeys(family(name) for name in inputs.names):
        variants = []
        counts = 0
        for fold in folds:
            present = [inputs.names[j] for j in fold["path"][:selected_k] if family(inputs.names[j]) == base]
            counts += bool(present)
            variants.extend(present)
        families.append({"indicador_sin_rezago": base, "cortes_que_retienen_alguna_version": counts,
                         "cortes_comparados": len(folds), "versiones_observadas": ";".join(dict.fromkeys(variants)),
                         "seleccionado_al_reajustar_con_56": any(family(name) == base for name in selected_names)})
    selected_stability = [row for row in stability if row["seleccionada"]]
    min_recurrence = min((row["cortes_que_la_retienen"] for row in selected_stability), default=0)
    chosen_x = final["complete_x"][:, selected_indices]
    selected_vif = vifs(chosen_x) if selected_k else []
    subset_vifs = dict(zip(selected_names, map(float, selected_vif)))
    report = {**inputs.evidence, "protocol": PROTOCOL, "target": DEFAULT_TARGET,
        "candidate_columns": len(inputs.names), "selected_k": selected_k,
        "selected_columns": selected_names, "k_minimum_mean_error": best_k,
        "one_SE_threshold": threshold, "k_compared": list(range(max_k + 1)),
        "per_horizon_size_diagnostics": horizon_sizes,
        "minimum_selected_column_recurrence_across_4_prefixes": min_recurrence,
        "selection_status": ("intercept_only_within_parsimony_threshold" if not selected_k else
                             "unstable_provisional_subset" if min_recurrence < 3 else
                             "recurrent_provisional_subset"),
        "selected_vif": subset_vifs, "path_columns_after_redundancy": len(final["path"]),
        "redundant_columns_excluded": sum(r["decision"] != "retenida_en_ruta" for r in final["decisions"]),
        "constant_columns_excluded": final["constant_excluded"],
        "heldout_data_opened": False, "internal_selection_errors_are_external_validation": False,
        "predictor_target_or_target_lags_included": False,
        "source_weights_recalibrated_inside_each_cut": True,
        "scales_and_ranking_fitted_inside_each_cut": True,
        "original_indicator_table_modified": False,
        "production_forecast_model_created": False,
        "smoothing_applied": False, "predictor_lags": [], "target_window_weeks": 1,
        "selection_is_provisional": True}
    return report, {"curva_numero_columnas_Radar_V1.csv": curve, "comparacion_horizontes_Radar_V1.csv": by_horizon,
        "curvas_por_horizonte_Radar_V1.csv": horizon_curves, "estabilidad_indicadores_sin_rezago_Radar_V1.csv": families,
        "limites_temporales_Radar_V1.csv": boundaries, "estabilidad_columnas_Radar_V1.csv": stability,
        "coeficientes_por_corte_Radar_V1.csv": details,
        "redundancia_columnas_Radar_V1.csv": [row for result in folds + [final] for row in result["decisions"]]}


def monica_diagnostic(inputs: Inputs, baseline: dict, baseline_tables: dict):
    """Redundancia observada y comparación de rutas sin usar reservas externas.

    Se excluye primero presencia y después las dos medidas semanales del tema
    MV, para que intensidad no sustituya al mismo indicador.
    No es una estimación causal ni una prueba de aporte predictivo independiente.
    """
    presence = [name for name in inputs.names if name == "presencia_segmentos30_pct_Conjunto_Visibilidad_MV"]
    topic = [name for name in inputs.names if name.endswith("_Conjunto_Visibilidad_MV")]
    if not presence or not topic:
        return {"applicable": False}, {}
    x, _, weights = rebuild(inputs, 56)
    valid = np.isfinite(x).all(axis=1)
    complete = x[valid]
    pearson = np.corrcoef(complete, rowvar=False)
    spearman = np.corrcoef(np.apply_along_axis(rankdata, 0, complete), rowvar=False)
    pairs = []
    for j, name in enumerate(inputs.names):
        for k in range(j + 1, len(inputs.names)):
            other = inputs.names[k]
            if name not in topic and other not in topic:
                continue
            p, s = float(pearson[j, k]), float(spearman[j, k])
            if not np.isfinite([p, s]).all():
                continue
            pairs.append({"variable_1": name, "variable_2": other, "n": len(complete),
                "ambas_del_tema_MV": name in topic and other in topic,
                "pearson": p, "spearman": s, "max_correlacion_absoluta": max(abs(p), abs(s)),
                "supera_umbral_085": max(abs(p), abs(s)) >= .85})
    pairs.sort(key=lambda row: row["max_correlacion_absoluta"], reverse=True)
    scenarios = [("completo", baseline, baseline_tables)]
    for label, excluded in (("sin_presencia_visibilidad_MV", presence), ("sin_tema_visibilidad_MV", topic)):
        subset = Inputs(inputs.rows, inputs.bases, [name for name in inputs.names if name not in excluded],
                        inputs.rates, inputs.words, inputs.evidence)
        result, tables = analyze(subset)
        scenarios.append((label, result, tables))
    sizes, losses = [], []
    baseline_loss = {h: np.mean([row["mse_normalizado"] for row in baseline_tables["comparacion_horizontes_Radar_V1.csv"]
        if row["horizonte_semanas"] == h and row["k"] == baseline["selected_k"]]) for h in HORIZONS}
    for label, result, tables in scenarios:
        curve = next(row for row in tables["curva_numero_columnas_Radar_V1.csv"] if row["seleccionado"])
        best_curve = next(row for row in tables["curva_numero_columnas_Radar_V1.csv"]
                          if row["k"] == result["k_minimum_mean_error"])
        sizes.append({"escenario": label, "candidatas": result["candidate_columns"],
            "k_candidato_comun": result["selected_k"], "k_de_menor_error": result["k_minimum_mean_error"],
            "error_medio_normalizado": curve["error_medio"],
            "minimo_error_medio": best_curve["error_medio"],
            "error_estandar_en_minimo": best_curve["error_estandar_entre_bloques"],
            "columnas_candidatas_reajuste_56": ";".join(result["selected_columns"]),
            "estado": result["selection_status"]})
        for h in HORIZONS:
            values = [row["mse_normalizado"] for row in tables["comparacion_horizontes_Radar_V1.csv"]
                      if row["horizonte_semanas"] == h and row["k"] == result["selected_k"]]
            loss = float(np.mean(values))
            losses.append({"escenario": label, "horizonte_semanas": h, "k": result["selected_k"],
                "error_medio_normalizado": loss, "diferencia_frente_a_completo": loss - baseline_loss[h]})
    a = "presencia_segmentos30_pct_Conjunto_Visibilidad_MV"
    b = "intensidad_por_1000_Conjunto_Visibilidad_MV"
    raw_corr = float(pearson[inputs.names.index(a), inputs.names.index(b)])
    report = {"applicable": True, "presence_columns": presence, "all_MV_topic_columns": topic,
        "comparable_weeks": len(complete), "weekly_presence_intensity_pearson": raw_corr,
        "within_MV_pairs_above_085": sum(row["ambas_del_tema_MV"] and row["supera_umbral_085"] for row in pairs),
        "scenario_summary": sizes,
        "comparison_scope": "internal_column_selection_not_independent_performance_assessment",
        "table_modified": False, "heldout_data_opened": False}
    return report, {"correlaciones_MV_Radar_V1.csv": pairs, "comparacion_sin_MV_Radar_V1.csv": sizes,
                    "comparacion_sin_MV_por_horizonte_Radar_V1.csv": losses}


def generate(development: Path, support: Path, output: Path):
    if output.exists():
        raise FileExistsError(f"Se conserva la salida existente: {output}")
    inputs = load_inputs(development, support)
    report, tables = analyze(inputs)
    monica, extra_tables = monica_diagnostic(inputs, report, tables)
    report["monica_redundancy_diagnostic"] = monica
    tables.update(extra_tables)
    if digest(development / "entrenamiento_Radar_V1/indicadores_Radar_V1.csv") != inputs.evidence["input_sha256"]:
        raise ValueError("Cambió la entrada durante la selección")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        for filename, rows in tables.items():
            write_rows(staging / filename, rows)
        columns = list(META) + [DEFAULT_TARGET] + report["selected_columns"]
        write_rows(staging / "tabla_inspeccion_reducida_Radar_V1.csv", [{c: row[c] for c in columns} for row in inputs.rows])
        (staging / "columnas_seleccionadas_Radar_V1.json").write_text(json.dumps({
            "target": DEFAULT_TARGET, "predictors": report["selected_columns"],
            "horizons_weeks": list(HORIZONS), "status": report["selection_status"],
            "is_final_selection": False,
            "requires_refitting_within_any_new_validation_cut": True}, indent=2) + "\n")
        report["output_sha256"] = {p.name: digest(p) for p in staging.iterdir()}
        (staging / "diagnostico_Radar_V1.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        chosen = [row for row in tables["estabilidad_columnas_Radar_V1.csv"] if row["seleccionada"]]
        curve = tables["curva_numero_columnas_Radar_V1.csv"]
        selected = next(row for row in curve if row["seleccionado"])
        baseline = next(row for row in curve if row["k"] == 0)
        text = ["# Selección exploratoria de columnas para horizontes 1 a 4", "",
            f"Se compararon {len(curve)} tamaños de la ruta ordenada, desde 0 hasta {curve[-1]['k']} explicativas. El mínimo de error medio usa {report['k_minimum_mean_error']}; la regla de un error estándar conserva **{report['selected_k']}** como tamaño candidato. No se compararon todos los subconjuntos posibles.", "",
            f"Error normalizado medio con el tamaño elegido: {selected['error_medio']:.4f}; referencia de sólo intercepto: {baseline['error_medio']:.4f}.", "",
            "Los errores sirven para escoger columnas dentro del bloque inicial, no acreditan rendimiento externo. No se abrieron prueba ni las 13 semanas reservadas. Se consumieron únicamente las primeras 56 filas del soporte por fuente, y se comprobó que reconstruyen la tabla vigente.", "",
            "## Procedimiento", "",
            "1. Cuatro cortes cronológicos: prefijos de 28, 35, 42 y 49 semanas. Se comparan orígenes de las siete siguientes, limitados para que todos los objetivos hasta t+4 permanezcan dentro de las 56 semanas. No se mezclan aleatoriamente las semanas.",
            "2. En cada corte se recalculan los pesos intermedios de fuentes con su propio prefijo. X contiene sólo los temas de t; Y es la polaridad de la semana t+h, sin suavizado ni rezagos de X. Sólo se usan pares cuya respuesta ya está dentro del prefijo para ajustar escalas y regresiones.",
            "3. Se ordenan candidatas por la mediana de sus rangos de magnitud de coeficiente estandarizado: cuatro horizontes por tres alphas (0.1, 1 y 10). Es una regla de ordenación explícita, no un porcentaje de importancia.",
            "4. Se retiran candidatas redundantes: correlación absoluta de Pearson o Spearman de al menos 0.85 con una retenida, o VIF conjunto mayor que 5. Son umbrales metodológicos explícitos, no pruebas de significación. No se usa la polaridad ni sus rezagos como explicativas.",
            "5. Se comparan todos los tamaños identificables en los cuatro cortes con Ridge alpha=1, incluido el intercepto solo. El error de cada horizonte se divide por la varianza de su respuesta en el prefijo; los cuatro horizontes pesan igual.",
            "6. Se conserva el menor tamaño cuyo error medio no supera el mínimo más un error estándar entre bloques. Es una regla de parsimonia; con cuatro bloques temporales dependientes ese error estándar no es un intervalo de confianza.", "",
            "## Subconjunto candidato al reajustar con las 56 semanas", "",
            "| Columna | Cortes que la retienen | Signo igual en cuatro horizontes | VIF conjunto |",
            "|---|---:|---|---:|"]
        text += [f"| {row['variable']} | {row['cortes_que_la_retienen']}/4 | {'sí' if row['mismo_signo_en_4_horizontes'] else 'no'} | {report['selected_vif'][row['variable']]:.3f} |" for row in chosen]
        if not chosen:
            text += ["| Ninguna: el intercepto solo queda dentro del umbral de parsimonia | — | — | — |"]
        text += ["", f"Estado: **{report['selection_status']}**. Se marca inestable si alguna columna candidata aparece en menos de tres de los cuatro prefijos; esa marca describe recurrencia, no cambia la regla de tamaño ni acredita significación.", "",
            "La frecuencia entre cortes es descriptiva: los prefijos se solapan y sólo hay cuatro. No es una probabilidad de selección poblacional. Un cambio de signo entre horizontes no demuestra por sí solo que una columna sea inútil, pero impide describir su asociación como de dirección uniforme.", "",
            "## Tamaño por horizonte", "",
            "| Horizonte | Tamaño con regla de un error estándar | Tamaño de menor error |",
            "|---|---:|---:|"]
        text += [f"| {h} | {values['selected_k']} | {values['k_minimum_mean_error']} |"
                 for h, values in report["per_horizon_size_diagnostics"].items()]
        text += ["", "Estos tamaños por horizonte son diagnósticos separados; no sustituyen silenciosamente el tamaño común elegido con los cuatro horizontes ponderados por igual.", "",
            "## Recurrencia de indicadores semanales", "",
            "| Indicador | Cortes | Versiones observadas |", "|---|---:|---|"]
        text += [f"| {row['indicador_sin_rezago']} | {row['cortes_que_retienen_alguna_version']}/4 | {row['versiones_observadas']} |"
                 for row in tables["estabilidad_indicadores_sin_rezago_Radar_V1.csv"] if row["cortes_que_retienen_alguna_version"]]
        text += ["", "Si cambia la variable al reajustar con las 56 semanas, la lista candidata no se considera una selección definitiva. No se añaden rezagos ni se combinan indicadores para ocultar esa inestabilidad.", "",
            "La selección final se recalcula con las 56 semanas una vez elegido el tamaño. La tabla reducida conserva esas 56 filas y los faltantes originales; la tabla base de 70 y el archivo reservado permanecen intactos. Si hay poca estabilidad entre cortes, la lista es provisional y debe tratarse como tal.", "",
            "Para una evaluación posterior, aplicar dentro de cada corte toda esta selección, sus pesos y escalas. Los errores usados para elegir el tamaño no son una evaluación independiente del conjunto definitivo. No se exportó un modelo operativo.", "",
        ]
        if monica["applicable"]:
            text += ["## ¿Es redundante la visibilidad de Mónica Villarreal?", "",
                f"Sobre las mismas {monica['comparable_weeks']} semanas, la correlación de Pearson entre presencia e intensidad semanales del tema MV es {monica['weekly_presence_intensity_pearson']:.4f}. No se aplicó suavizado ni se generaron rezagos.", "",
                "Se recalculó la selección excluyendo primero la medida semanal de presencia y después las dos columnas del tema MV. La tabla original conserva todas sus columnas.", "",
                "| Escenario | Candidatas | Tamaño candidato | Error del tamaño candidato | Menor error de la ruta |",
                "|---|---:|---:|---:|---:|"]
            text += [f"| {row['escenario']} | {row['candidatas']} | {row['k_candidato_comun']} | {row['error_medio_normalizado']:.4f} | {row['minimo_error_medio']:.4f} |"
                     for row in monica["scenario_summary"]]
            text += ["", "Las diferencias comparan procedimientos de selección dentro del mismo bloque inicial; no son una prueba de causalidad ni una validación externa del aporte único de Mónica. Hay redundancia si sus columnas son muy correlacionadas, pero eso no demuestra que toda asociación con la respuesta sea espuria. Los resultados por horizonte están en `comparacion_sin_MV_por_horizonte_Radar_V1.csv`.", ""]
        text += [
            "## Archivos", "",
            "`curva_numero_columnas_Radar_V1.csv` documenta por qué se eligió la cantidad; `curvas_por_horizonte_Radar_V1.csv` separa los diagnósticos; `estabilidad_columnas_Radar_V1.csv` muestra recurrencia, rangos y signos; `estabilidad_indicadores_sin_rezago_Radar_V1.csv` distingue familias y rezagos; `redundancia_columnas_Radar_V1.csv` registra cada exclusión; `limites_temporales_Radar_V1.csv` deja las fechas y pesos de cada corte. `columnas_seleccionadas_Radar_V1.json` define el esquema candidato y su estado provisional; `tabla_inspeccion_reducida_Radar_V1.csv` lo aplica únicamente al bloque inicial.", "",
            "Referencias: [regla de un error estándar, Stanford](https://web.stanford.edu/class/stats202/notes/Resampling/Resampling.html?highlight=e+learning), [prevención de fugas de información](https://scikit-learn.org/stable/common_pitfalls.html), [coeficientes y variables correlacionadas](https://scikit-learn.org/stable/auto_examples/inspection/plot_linear_model_coefficient_interpretation.html).", ""]
        (staging / "seleccion_Radar_V1.md").write_text("\n".join(text), encoding="utf-8")
        staging.rename(output)
    except BaseException:
        shutil.rmtree(staging)
        raise
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development-dir", type=Path, default=ROOT / "datos_Radar_V1/radar_modelado_Radar_V1/desarrollo_Radar_V1")
    parser.add_argument("--support-table", type=Path, default=ROOT / "datos_Radar_V1/radar_indicadores_Radar_V1/tabla_indicadores_83_semanas_Radar_V1.csv")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "datos_Radar_V1/radar_analisis_Radar_V1/seleccion_indicadores_Radar_V1")
    args = parser.parse_args()
    report = generate(args.development_dir, args.support_table, args.output_dir)
    print(json.dumps({key: report[key] for key in ("candidate_columns", "selected_k", "selected_columns",
        "k_minimum_mean_error", "heldout_data_opened")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
