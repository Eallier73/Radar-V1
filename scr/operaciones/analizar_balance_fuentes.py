#!/usr/bin/env python3
"""Diagnostica el corpus y propone pesos de fuente sin modificar CSV ni TXT.

Los pesos son una decision analitica explicita, no audiencias estimadas ni
probabilidades de inclusion. Los identificadores de autor faltantes no son cero.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Mapping, Sequence
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[2]
for directory in (REPO_ROOT / "scr/compartido", REPO_ROOT / "scr/preprocesamiento"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from promover_csv_a_texto import SOURCE_COLUMNS, TEXT_COLUMNS, build_text_content, normalize_social_text, read_canonical_csv
from radar_paths import PROCESSED_DATA_DIR

SOURCES = ("youtube", "twitter", "facebook", "medios")
LABELS = {"youtube": "YouTube", "twitter": "Twitter/X", "facebook": "Facebook", "medios": "Medios"}
METHOD_REFERENCE = "https://knowledge-for-policy.ec.europa.eu/composite-indicators/toolkit_en/navigation-page/10-step-guide_en/step-6-weighting_en"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def describe(values: Sequence[int | float]) -> dict[str, float | int | None]:
    ordered = sorted(values)
    if not ordered:
        return dict(n=0, total=0, mean=None, median=None, p90=None, maximum=None)
    position = (len(ordered) - 1) * .90
    lower = math.floor(position)
    upper = math.ceil(position)
    p90 = ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
    return dict(n=len(values), total=sum(values), mean=statistics.mean(values),
                median=statistics.median(values), p90=p90, maximum=max(values))


def pearson(x: Sequence[float], y: Sequence[float]) -> float | None:
    if len(x) != len(y):
        raise ValueError("Las series deben tener la misma longitud")
    if len(x) < 3:
        return None
    xbar, ybar = statistics.mean(x), statistics.mean(y)
    xx = math.fsum((v - xbar) ** 2 for v in x)
    yy = math.fsum((v - ybar) ** 2 for v in y)
    if not xx or not yy:
        return None
    return math.fsum((a - xbar) * (b - ybar) for a, b in zip(x, y)) / math.sqrt(xx * yy)


def ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    result = [0.0] * len(values)
    first = 0
    while first < len(order):
        last = first + 1
        while last < len(order) and values[order[last]] == values[order[first]]:
            last += 1
        average = (first + 1 + last) / 2
        for index in order[first:last]:
            result[index] = average
        first = last
    return result


def relation(x: Sequence[float], y: Sequence[float]) -> dict[str, object]:
    return {"weeks": len(x), "pearson": pearson(x, y), "spearman": pearson(ranks(x), ranks(y)),
            "interpretation": "descriptive_weekly_association_not_causality"}


def power_weights(word_totals: Mapping[str, int], alpha: float) -> dict[str, float]:
    if not math.isfinite(alpha) or not 0 <= alpha <= 1:
        raise ValueError("alpha debe estar entre 0 y 1")
    if not word_totals or any(not math.isfinite(value) or value <= 0 for value in word_totals.values()):
        raise ValueError("Todas las fuentes deben tener palabras observadas positivas")
    scores = {source: value ** alpha for source, value in word_totals.items()}
    total = math.fsum(scores.values())
    return {source: value / total for source, value in scores.items()}


def author_identifier(row: Mapping[str, str]) -> tuple[str | None, str | None]:
    value = row.get("author", "").strip().lstrip("@").casefold()
    if value not in {"", "nan", "none", "null", "unknown", "desconocido", "desconocida"} and re.fullmatch(r"[a-z0-9_]+", value):
        return value, "author_field"
    try:
        parsed = urlparse(row.get("url", ""))
    except ValueError:
        return None, None
    parts = parsed.path.strip("/").split("/")
    if parsed.hostname in {"x.com", "www.x.com", "twitter.com", "www.twitter.com", "mobile.twitter.com"} and len(parts) >= 3 and parts[1] == "status" and re.fullmatch(r"[a-zA-Z0-9_]+", parts[0]):
        return parts[0].casefold(), "tweet_url"
    return None, None


def audit_source(root: Path, source: str, inputs: dict[str, str]) -> dict[str, object]:
    directory = root / f"{source}_semanal_procesado"
    texts = sorted(directory.glob(f"*/*_{source}.txt"))
    if not texts:
        raise ValueError(f"No hay TXT para {source}")
    weekly = []
    words_all, usable_lengths, raw_lengths = [], [], []
    subtypes: dict[str, list[int]] = defaultdict(list)
    all_authors, usable_authors, author_origins = Counter(), Counter(), Counter()
    institutional_accounts = set()
    for text_path in texts:
        inputs[str(text_path)] = sha256(text_path)
        text = text_path.read_text(encoding="utf-8")
        if not text.strip():
            raise ValueError(f"TXT vacio: {text_path}")
        word_total = len(text.split())
        week = {"week": text_path.parent.name, "words": word_total,
                "records": None, "usable_records": None, "mean_words_per_usable_record": None,
                "observed_authors_usable": None}
        if source != "medios":
            csv_path = text_path.with_suffix(".csv")
            inputs[str(csv_path)] = sha256(csv_path)
            rows = read_canonical_csv(csv_path, source)
            expected, written, skipped = build_text_content(source, rows)
            if expected != text:
                raise ValueError(f"TXT distinto de su CSV: {text_path}")
            lengths, local_authors = [], set()
            for row in rows:
                value = row[TEXT_COLUMNS[source]]
                length = len(normalize_social_text(value).split())
                lengths.append(length)
                words_all.append(length)
                raw_lengths.append(len(value))
                if length:
                    usable_lengths.append(length)
                subtype = (row["tipo"] if source == "facebook" else
                           "reply" if source == "twitter" and row.get("is_reply") == "true" else
                           "non_reply" if source == "twitter" else "comment")
                subtypes[subtype].append(length)
                if source == "facebook":
                    institutional_accounts.add(row["cuenta"])
                if source == "twitter":
                    author, origin = author_identifier(row)
                    if author:
                        all_authors[author] += 1
                        if length:
                            usable_authors[author] += 1
                            local_authors.add(author)
                            author_origins[origin] += 1
            if sum(lengths) != word_total or written + skipped != len(rows):
                raise ValueError(f"No concilian palabras o registros de {csv_path}")
            week.update(records=len(rows), usable_records=written,
                        mean_words_per_usable_record=word_total / written if written else None,
                        observed_authors_usable=len(local_authors) if source == "twitter" else None)
        weekly.append(week)
    result = {"weeks": len(weekly), "words": sum(week["words"] for week in weekly),
              "records": len(words_all) if source != "medios" else None,
              "usable_records": len(usable_lengths) if source != "medios" else None,
              "empty_after_normalization": len(words_all) - len(usable_lengths) if source != "medios" else None,
              "words_per_usable_record": describe(usable_lengths) if source != "medios" else None,
              "raw_characters_per_record": describe(raw_lengths) if source != "medios" else None,
              "words_per_week": describe([week["words"] for week in weekly]),
              "observed_authors_all": len(all_authors) if source == "twitter" else None,
              "observed_authors_usable": len(usable_authors) if source == "twitter" else None,
              "author_identification_origins_usable": dict(author_origins) if source == "twitter" else None,
              "institutional_account_count_not_comment_authors": len(institutional_accounts) if source == "facebook" else None,
              "subtypes": {kind: {"records": len(lengths), "usable_records": sum(length > 0 for length in lengths),
                                     "words": sum(lengths), "words_per_usable_record": describe([length for length in lengths if length])}
                           for kind, lengths in subtypes.items()}, "weekly": weekly}
    if source != "medios":
        result["weekly_records_vs_length"] = relation([week["usable_records"] for week in weekly],
                                                       [week["mean_words_per_usable_record"] for week in weekly])
    if source == "twitter":
        result["known_author_coverage_usable"] = sum(usable_authors.values()) / len(usable_lengths)
        result["records_per_observed_author_usable"] = sum(usable_authors.values()) / len(usable_authors) if usable_authors else None
        result["top_ten_authors_share_usable"] = sum(n for _, n in usable_authors.most_common(10)) / len(usable_lengths)
        result["weekly_records_vs_authors"] = relation([week["usable_records"] for week in weekly], [week["observed_authors_usable"] for week in weekly])
        result["weekly_authors_vs_length"] = relation([week["observed_authors_usable"] for week in weekly], [week["mean_words_per_usable_record"] for week in weekly])
    return result


def analyze(root: Path, alpha: float = .5) -> dict[str, object]:
    inputs: dict[str, str] = {}
    sources = {source: audit_source(root, source, inputs) for source in SOURCES}
    week_sets = [{week["week"] for week in data["weekly"]} for data in sources.values()]
    if any(weeks != week_sets[0] for weeks in week_sets[1:]):
        raise ValueError("Las fuentes no cubren las mismas semanas")
    weeks = sorted(week_sets[0])
    totals = {source: data["words"] for source, data in sources.items()}
    weights = power_weights(totals, alpha)
    raw_shares = power_weights(totals, 1)
    period_end = (date.fromisoformat(weeks[-1][:10]) + timedelta(days=6)).isoformat()
    fingerprint = hashlib.sha256(json.dumps(
        {str(Path(path).relative_to(root)): value for path, value in inputs.items()},
        sort_keys=True,
    ).encode()).hexdigest()
    for source, data in sources.items():
        data["raw_word_share"] = raw_shares[source]
        data["proposed_source_weight"] = weights[source]
    for path, before in inputs.items():
        if sha256(Path(path)) != before:
            raise ValueError(f"Cambio el corpus durante el analisis: {path}")
    return {"scope": "all_available_historical_weeks_retrospective", "weeks": len(weeks),
            "period_start": weeks[0][:10],
            "period_end": period_end,
            "total_words": sum(totals.values()), "sources": sources,
            "weighting": {"status": "proposal_not_applied_to_a_model", "alpha": alpha,
                          "formula": "w_s = T_s**alpha / sum(T_j**alpha)",
                          "basis": "observed_normalized_words_only_not_audience_or_users",
                          "calibration": {"scope": "retrospective_full_history", "weeks": len(weeks),
                                          "period_start": weeks[0][:10], "period_end": period_end,
                                          "input_sha256_fingerprint": fingerprint,
                                          "refit_on_training_only_for_prediction": True},
                          "user_factor_used": False,
                          "missing_users_are_not_zero": True,
                          "weights": weights,
                          "per_word_mass_multiplier": {source: weights[source] / totals[source] for source in SOURCES},
                          "sensitivity": {str(a): power_weights(totals, a) for a in (0, .25, .5, .75, 1)},
                          "reference": METHOD_REFERENCE},
            "input_sha256": inputs, "inputs_unchanged": True}


def render_report(result: dict[str, object]) -> str:
    sources, weighting = result["sources"], result["weighting"]
    def number(value: object, decimals: int = 2) -> str:
        return f"{value:.{decimals}f}" if value is not None else "No disponible"
    lines = ["# Balance del corpus y propuesta de ponderación", "",
             f"Periodo observado: {result['period_start']} a {result['period_end']}; {result['weeks']} semanas por fuente.", "",
             "El análisis usa el material existente. No estima audiencias de las plataformas ni convierte cuentas institucionales en usuarios ciudadanos. Los CSV y TXT permanecen intactos.", "",
             "## Volumen y longitud", "",
             "Las longitudes son palabras después de la limpieza ASCII, antes de eliminar palabras funcionales. La media y la mediana se calculan entre registros que conservan texto. Una fila de YouTube es un comentario; Facebook distingue publicaciones y comentarios. Las líneas de Medios son envolturas de 30 palabras, no noticias.", "",
             "| Fuente | Registros CSV | Registros con texto | Media palabras | Mediana palabras | Palabras totales | Porcentaje de palabras |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for source, data in sources.items():
        stats = data["words_per_usable_record"]
        values = [LABELS[source], str(data["records"]) if data["records"] is not None else "No disponible",
                  str(data["usable_records"]) if data["usable_records"] is not None else "No disponible",
                  f"{stats['mean']:.2f}" if stats else "No disponible",
                  f"{stats['median']:.2f}" if stats else "No disponible", str(data["words"]), f"{100 * data['raw_word_share']:.2f}%"]
        lines.append("| " + " | ".join(values) + " |")
    fb, tw = sources["facebook"], sources["twitter"]
    lines += ["", "### Publicaciones y comentarios", "",
              "| Fuente y tipo | Registros | Con texto | Media palabras | Mediana palabras |",
              "|---|---:|---:|---:|---:|"]
    for source in ("facebook", "twitter"):
        for kind, subtype in sources[source]["subtypes"].items():
            stats = subtype["words_per_usable_record"]
            lines.append(f"| {LABELS[source]} {kind} | {subtype['records']} | {subtype['usable_records']} | {number(stats['mean'])} | {number(stats['median'])} |")
    lines += ["", "La mezcla de publicaciones institucionales y comentarios se registra explícitamente; más texto no equivale por sí mismo a más personas ni a mayor aceptación ciudadana. En Twitter, reply y non_reply describen la marca is_reply del CSV, no una clasificación independiente de todas las interacciones originales.", "",
              "## Usuarios y metadatos disponibles", "",
              f"Twitter permite distinguir {tw['observed_authors_all']} identificadores de autor en todas sus filas y {tw['observed_authors_usable']} entre los registros con texto. La cobertura de identificación sobre texto utilizable es {100 * tw['known_author_coverage_usable']:.2f}%. Son identificadores de cuentas observadas, no personas verificadas ni audiencia total.", "",
              "YouTube no conserva autores en el contrato histórico. En Facebook `cuenta` identifica las dos instituciones objetivo, no a los autores de los comentarios. Medios no permite reconstruir autores, lectores, número de noticias ni longitud por noticia a partir del TXT continuo. Estos faltantes son desconocidos, no ceros; no se usan para penalizar esas fuentes.", "",
              "## Relaciones semanales exploratorias", "",
              "| Fuente | Registros con texto frente a longitud media Pearson | Spearman |",
              "|---|---:|---:|"]
    for source in TEXT_COLUMNS:
        data = sources[source]["weekly_records_vs_length"]
        lines.append(f"| {LABELS[source]} | {number(data['pearson'], 4)} | {number(data['spearman'], 4)} |")
    relations = tw["weekly_records_vs_authors"]
    lines += ["", f"En Twitter, registros con texto frente a autores identificables: Pearson {number(relations['pearson'], 4)}, Spearman {number(relations['spearman'], 4)}. Son asociaciones descriptivas de semanas sucesivas, no efectos causales. Más registros también dan más oportunidades de observar autores; los cambios de cobertura de extracción pueden influir.", "",
              "## Propuesta de contribución por fuente", "",
              "Se propone transformar el volumen textual con una potencia entre cero y uno; alpha 0.5 corresponde a una raíz cuadrada. Es una decisión analítica explícita, no un peso óptimo descubierto ni una estimación representativa de población. Cuando conocemos las unidades, T = registros con texto × longitud media; para Medios T se observa directamente sin inventar un número de noticias.", "",
              f"Fórmula: `w_s = T_s^{weighting['alpha']} / suma(T_j^{weighting['alpha']})`.", "",
              f"| Fuente | Sin ajuste por fuente alpha 1 | Propuesta alpha {weighting['alpha']} | Control de sensibilidad alpha 0 |",
              "|---|---:|---:|---:|"]
    for source, data in sources.items():
        lines.append(f"| {LABELS[source]} | {100 * data['raw_word_share']:.2f}% | {100 * data['proposed_source_weight']:.2f}% | 25.00% |")
    lines += ["", "## Uso y límites", "",
              "La propuesta aún no se ha aplicado a un modelo. En un resultado normalizado por fuente, combinar con `resultado = suma(w_s × resultado_normalizado_s)`. En conteos de palabras, usar `multiplicador_s = w_s / T_s`; multiplicar los conteos brutos sólo por w_s contaría el volumen otra vez. El modelo conjunto debe conservar la etiqueta de fuente y admitir la contribución deseada; el mecanismo concreto de entrenamiento depende del modelo que se elija.", "",
              "No se aplica un factor de usuarios, porque su cobertura no es comparable entre las cuatro fuentes. Para un modelo predictivo, los pesos se calibrarían sólo con el periodo de entrenamiento y se congelarían para validación; este diagnóstico es retrospectivo y usa el histórico completo.", "",
              "La elección debe contrastarse con los escenarios alpha 0 y 1 para comprobar si las conclusiones dependen de los pesos. No hay aún resultados temáticos o de sentimiento sobre los que afirmar robustez.", "",
              f"Referencia metodológica sobre la necesidad de justificar y transparentar pesos: [Comisión Europea JRC]({METHOD_REFERENCE}). La transformación por potencia es la propuesta de trabajo del proyecto, no una regla prescrita por esa referencia.", "",
              "Los detalles semanales, subtipos, percentiles y hashes de entrada están en `diagnostico_ponderacion_fuentes.json`. `pesos_fuentes_propuestos.json` contiene los coeficientes propuestos, no una configuración activa del modelo."]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", type=Path, default=PROCESSED_DATA_DIR)
    parser.add_argument("--alpha", type=float, default=.5)
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Si se omite, sólo muestra el diagnóstico resumido sin escribir archivos")
    args = parser.parse_args(argv)
    result = analyze(args.processed_dir.resolve(), args.alpha)
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "diagnostico_ponderacion_fuentes.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (args.output_dir / "pesos_fuentes_propuestos.json").write_text(json.dumps(result["weighting"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (args.output_dir / "analisis_ponderacion_fuentes.md").write_text(render_report(result), encoding="utf-8")
    print(json.dumps({"weeks": result["weeks"], "total_words": result["total_words"],
                      "weights": result["weighting"]["weights"], "inputs_unchanged": result["inputs_unchanged"],
                      "output_dir": str(args.output_dir) if args.output_dir else None}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
