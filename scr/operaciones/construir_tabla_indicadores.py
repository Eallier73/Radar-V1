#!/usr/bin/env python3
"""Construye primero los indicadores de las 83 semanas, sin entrenar modelos.

Usa el corpus actual de Radar V1 y los diccionarios históricos autorizados. La media MA5
es retrospectiva hacia atrás para no incorporar información de semanas futuras.
Los pesos intermedios se calibran sólo con las primeras 56 semanas.
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
import unicodedata
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from generar_conjuntos_temporales import SOURCES, SIZES, digest, discover, write_json

LABELS = {"youtube": "Youtube", "twitter": "XTwitter", "facebook": "Facebook", "medios": "Medios"}
POLARITY_FILES = {"Original": ("diccionario_palabras_positivas.txt", "diccionario_palabras_negativas.txt")}
CORPUS_ORIGIN_POLICY = "current_repository_only"


def normalize(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value.lower())
    ascii_text = "".join(c for c in folded if not unicodedata.combining(c))
    return " ".join("".join(c if "a" <= c <= "z" else " " for c in ascii_text).split())


def load_terms(path: Path) -> set[str]:
    return {normalize(line) for line in path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip() and not line.lstrip().startswith("#") and normalize(line)}


class Matcher:
    """Cuenta unigramas y n-gramas, incluidas coincidencias superpuestas."""
    def __init__(self, terms: dict[str, set[str]]):
        self.trie = {}
        for label, entries in terms.items():
            for term in entries:
                node = self.trie
                for token in term.split():
                    node = node.setdefault(token, {})
                node.setdefault(None, []).append(label)

    def counts(self, tokens: list[str]) -> Counter:
        counts = Counter()
        for index in range(len(tokens)):
            node = self.trie
            for end in range(index, len(tokens)):
                node = node.get(tokens[end])
                if node is None:
                    break
                counts.update(node.get(None, ()))
        return counts


def load_resources(directory: Path):
    required = [name for pair in POLARITY_FILES.values() for name in pair]
    required += ["Diccionario_Temas_V5.csv", "Stoplists_Por_Tema_1.csv", "stop_list_español.txt",
                 "exclusiones_polaridad.json", "procedencia.json"]
    manifest = directory / "procedencia.json"
    if not manifest.is_file():
        raise ValueError("Faltan los diccionarios autorizados o su procedencia")
    provenance = json.loads(manifest.read_text())
    if set(provenance) != set(required) - {"procedencia.json"}:
        raise ValueError("La procedencia debe cubrir exactamente los diccionarios y stoplists autorizados")
    hashes = {name: digest(directory / name) for name in required}
    # original_path/original_notebook son evidencia; nunca se abren como entradas.
    for name, evidence in provenance.items():
        if hashes[name] != evidence.get("sha256"):
            raise ValueError(f"El diccionario no coincide con su procedencia: {name}")
    exclude = {normalize(term) for term in json.loads((directory / "exclusiones_polaridad.json").read_text())}
    polarities = {}
    for version, files in POLARITY_FILES.items():
        for polarity, name in zip(("pos", "neg"), files):
            polarities[f"{version}_{polarity}"] = {term for term in load_terms(directory / name)
                if term not in exclude and not any(word in exclude for word in term.split())}
    with (directory / "Stoplists_Por_Tema_1.csv").open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        topic_stops = {topic: set() for topic in reader.fieldnames}
        for row in reader:
            for topic, term in row.items():
                if term and normalize(term):
                    topic_stops[topic].add(normalize(term))
    with (directory / "Diccionario_Temas_V5.csv").open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        topics = {topic: set() for topic in reader.fieldnames}
        for row in reader:
            for topic, term in row.items():
                term = normalize(term or "")
                excluded = topic_stops.get(topic, set())
                if term and term not in excluded and not any(word in excluded for word in term.split()):
                    topics[topic].add(term)
    return Matcher(polarities), Matcher(topics), list(topics), load_terms(directory / "stop_list_español.txt"), hashes


def analyze_text(text: str, source: str, polar: Matcher, thematic: Matcher, topics: list[str], stopwords: set[str]):
    lines = [line.split() for line in text.splitlines() if line.strip()]
    tokens = [token for line in lines for token in line]
    if not tokens:
        raise ValueError("Corpus semanal vacío")
    if normalize(text).split() != tokens:
        raise ValueError("El corpus debe cumplir el contrato de letras ASCII minúsculas")
    polar_counts, mentions, presence = Counter(), Counter(), Counter()
    for line in lines:
        polar_counts.update(polar.counts([token for token in line if token not in stopwords]))
        hits = thematic.counts(line)
        mentions.update(hits)
        presence.update(hits.keys())
    segments = [tokens[start:start + 30] for start in range(0, len(tokens), 30)]
    segment_presence = Counter()
    for segment in segments:
        segment_presence.update(thematic.counts(segment).keys())
    result = {"words": len(tokens), "text_records": len(lines) if source != "medios" else None,
              "segments30": len(segments), "polarities": {}, "topics": {}}
    for version in POLARITY_FILES:
        positive, negative = polar_counts[f"{version}_pos"], polar_counts[f"{version}_neg"]
        result["polarities"][version] = {"positive": positive, "negative": negative,
            "sentiment_pct": 100 * positive / (positive + negative) if positive + negative else None}
    for topic in topics:
        result["topics"][topic] = {"mentions": mentions[topic],
            "intensity_per_1000": 1000 * mentions[topic] / len(tokens),
            "record_presence_pct": 100 * presence[topic] / len(lines) if source != "medios" else None,
            "segment30_presence_pct": 100 * segment_presence[topic] / len(segments)}
    return result


def trailing_ma5(rows: list[dict], columns: list[str]) -> list[dict]:
    result = [dict(row) for row in rows]
    for index, target in enumerate(result):
        for column in columns:
            values = [row[column] for row in rows[max(0, index - 4):index + 1] if row[column] is not None]
            target[f"{column}_MA5"] = math.fsum(values) / len(values) if values else None
    return result


def write_table(path: Path, rows: list[dict], columns: list[str] | None = None) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def weighted_analysis_rows(rows: list[dict]) -> list[dict]:
    """Sólo fechas e indicadores conjuntos ya ponderados y suavizados MA5."""
    identifiers = ["semana_iso", "Fecha_Semana", "Fecha_Fin"]
    weighted = [column for column in rows[0] if "_Conjunto_" in column and column.endswith("_MA5")]
    if not weighted or any(name[:-4] not in rows[0] for name in weighted):
        raise ValueError("Se requieren indicadores conjuntos MA5 con su cálculo de soporte")
    return [{column: row[column] for column in identifiers + weighted} for row in rows]


def add_weekly_lags(rows: list[dict], lags=(1, 2, 3, 4)) -> list[dict]:
    """Agrega x(t-k) sin perder semanas ni rellenar historia inexistente."""
    if not rows or not lags or any(type(k) is not int or k not in (1, 2, 3, 4) for k in lags):
        raise ValueError("Se requieren filas y lags enteros entre 1 y 4")
    if len(set(lags)) != len(lags):
        raise ValueError("No se permiten lags duplicados")
    identifiers = {"semana_iso", "Fecha_Semana", "Fecha_Fin"}
    metrics = [c for c in rows[0] if c not in identifiers]
    if not metrics or any("_Conjunto_" not in c or not c.endswith("_MA5") for c in metrics):
        raise ValueError("Los lags se construyen sólo desde indicadores conjuntos MA5, sin rezagos previos")
    dates = [date.fromisoformat(row["Fecha_Semana"]) for row in rows]
    if any(d.weekday() != 0 for d in dates) or any(b - a != timedelta(days=7) for a, b in zip(dates, dates[1:])):
        raise ValueError("Las semanas deben ser consecutivas, únicas y ordenadas")
    result = []
    for index, row in enumerate(rows):
        output = dict(row)
        for column in metrics:
            for lag in sorted(lags):
                output[f"{column}_lag{lag}"] = rows[index - lag][column] if index >= lag else None
        result.append(output)
    return result


def build(processed: Path, resources: Path, output: Path) -> dict:
    processed, resources, output = processed.resolve(), resources.resolve(), output.resolve()
    if output.exists():
        raise FileExistsError(f"Se conserva la tabla existente: {output}")
    if any(output == source or output.is_relative_to(source) or source.is_relative_to(output)
           for source in (processed, resources)):
        raise ValueError("La salida debe estar separada de las entradas")
    weeks = discover(processed)
    if len(weeks) != sum(SIZES.values()):
        raise ValueError("Se requieren las 83 semanas completas antes de construir la tabla")
    polar, thematic, topics, stopwords, resource_hashes = load_resources(resources)
    rows, detail, hashes, totals, definitions, smooth_columns = [], [], {}, dict.fromkeys(SOURCES, 0), {}, []
    # Primero indicadores individuales: ni particiones físicas ni aprendizaje.
    per_week = []
    for index, week in enumerate(weeks):
        measurements = {}
        for source, path in week["files"].items():
            raw = path.read_bytes()
            hashes[str(path.relative_to(processed))] = hashlib.sha256(raw).hexdigest()
            values = analyze_text(raw.decode("utf-8"), source, polar, thematic, topics, stopwords)
            measurements[source] = values
            if index < SIZES["entrenamiento"]:
                totals[source] += values["words"]
            detail.append({"week": week["week"], "source": source, **values})
        per_week.append(measurements)
    scores = {source: words ** .5 for source, words in totals.items()}
    weights = {source: score / math.fsum(scores.values()) for source, score in scores.items()}
    for week, measurements in zip(weeks, per_week):
        year, number, _ = date.fromisoformat(week["period_start"]).isocalendar()
        row = {"semana_iso": f"{year}-W{number:02d}", "Fecha_Semana": week["period_start"],
               "Fecha_Fin": week["period_end"], "semana_corpus": week["week"]}

        def add(name, value, unit, formula, smooth=False):
            row[name] = value
            definitions.setdefault(name, {"column": name, "unit": unit, "formula": formula})
            if smooth and name not in smooth_columns:
                smooth_columns.append(name)

        for source, values in measurements.items():
            label = LABELS[source]
            add(f"palabras_{label}", values["words"], "palabras ASCII", "conteo de palabras del TXT")
            if source != "medios":
                add(f"registros_texto_{label}", values["text_records"], "registros con texto", "líneas no vacías del TXT social")
            add(f"segmentos30_{label}", values["segments30"], "segmentos de hasta 30 palabras", "ceil(palabras / 30); no publicaciones")
            for version, values_p in values["polarities"].items():
                add(f"positivas_{label}_{version}", values_p["positive"], "coincidencias léxicas", "unigramas y n-gramas positivos tras stoplists")
                add(f"negativas_{label}_{version}", values_p["negative"], "coincidencias léxicas", "unigramas y n-gramas negativos tras stoplists")
                add(f"Sentimiento_{label}_Original_{version}", values_p["sentiment_pct"], "% de coincidencias con polaridad",
                    "100 * positivas / (positivas + negativas); vacío si no hay coincidencias", True)
            for topic, values_t in values["topics"].items():
                add(f"menciones_{label}_{topic}", values_t["mentions"], "coincidencias léxicas", "unigramas y n-gramas temáticos, sin cruzar líneas")
                add(f"intensidad_por_1000_{label}_{topic}", values_t["intensity_per_1000"], "coincidencias / 1000 palabras",
                    "1000 * menciones / palabras", True)
                if source != "medios":
                    add(f"presencia_tema_pct_{label}_{topic}", values_t["record_presence_pct"], "% de registros con texto",
                        "100 * registros que mencionan el tema / registros con texto", True)
                add(f"presencia_segmentos30_pct_{label}_{topic}", values_t["segment30_presence_pct"], "% de segmentos de 30 palabras",
                    "100 * segmentos con tema / segmentos; envoltura común de todo el texto semanal", True)
        for version in POLARITY_FILES:
            vals = {s: measurements[s]["polarities"][version]["sentiment_pct"] for s in SOURCES}
            # No se convierte ausencia de polaridad en neutralidad ni se renormalizan pesos silenciosamente.
            joint = math.fsum(weights[s] * vals[s] for s in SOURCES) if all(v is not None for v in vals.values()) else None
            add(f"Sentimiento_Conjunto_Original_{version}", joint, "% de coincidencias con polaridad ponderado",
                "suma(peso_fuente * sentimiento_fuente); vacío si falta una fuente", True)
        for topic in topics:
            add(f"intensidad_por_1000_Conjunto_{topic}", math.fsum(weights[s] * measurements[s]["topics"][topic]["intensity_per_1000"] for s in SOURCES),
                "coincidencias / 1000 palabras ponderadas", "suma(peso_fuente * intensidad_fuente)", True)
            add(f"presencia_segmentos30_pct_Conjunto_{topic}", math.fsum(weights[s] * measurements[s]["topics"][topic]["segment30_presence_pct"] for s in SOURCES),
                "% de segmentos de 30 palabras ponderado", "suma(peso_fuente * presencia_segmentos_fuente)", True)
        rows.append(row)
    raw_rows = rows
    rows = trailing_ma5(raw_rows, smooth_columns)
    for column in smooth_columns:
        definitions[f"{column}_MA5"] = {"column": f"{column}_MA5", "unit": definitions[column]["unit"],
            "formula": f"media de {column} entre t-4 y t; mínimo 1 observación no ausente"}
    weighting = {"alpha": .5, "calibration_subset": "entrenamiento", "calibration_weeks": SIZES["entrenamiento"],
        "period_start": weeks[0]["period_start"], "period_end": weeks[SIZES["entrenamiento"] - 1]["period_end"],
        "words": totals, "weights": weights, "status": "applied_to_indicators_not_a_trained_model",
        "input_hashes": {str(week["files"][s].relative_to(processed)): hashes[str(week["files"][s].relative_to(processed))]
                         for week in weeks[:SIZES["entrenamiento"]] for s in SOURCES}}
    for relative, expected in hashes.items():
        if digest(processed / relative) != expected:
            raise ValueError(f"Cambió una entrada: {relative}")
    if {name: digest(resources / name) for name in resource_hashes} != resource_hashes:
        raise ValueError("Cambiaron los diccionarios durante el cálculo")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        write_table(staging / "tabla_indicadores_83_semanas.csv", rows)
        analysis_rows = weighted_analysis_rows(rows)
        base_columns = [c for c in analysis_rows[0] if c not in {"semana_iso", "Fecha_Semana", "Fecha_Fin"}]
        for column in base_columns:
            for lag in (1, 2, 3, 4):
                definitions[f"{column}_lag{lag}"] = {"column": f"{column}_lag{lag}",
                    "unit": definitions[column]["unit"], "formula": f"{column} de la semana t-{lag}; ausente sin historia"}
        analysis_rows = add_weekly_lags(analysis_rows)
        development_rows = analysis_rows[:SIZES["entrenamiento"] + SIZES["prueba"]]
        archive = staging / "archivo"
        archive.mkdir()
        write_table(archive / "tabla_analisis_completa_83_semanas.csv", analysis_rows)
        write_table(staging / "tabla_analisis_ponderada.csv", development_rows)
        write_table(staging / "variables_analisis.csv", [definition for column, definition in definitions.items()
                    if column in analysis_rows[0]])
        write_table(staging / "variables.csv", [definition for column, definition in definitions.items() if column in rows[0]])
        write_json(staging / "detalle_fuentes.json", detail)
        write_json(staging / "pesos_fuentes_entrenamiento.json", weighting)
        report = {"status": "indicator_table_generated_before_partition", "rows": len(rows), "columns": len(rows[0]),
            "corpus_origin_policy": CORPUS_ORIGIN_POLICY,
            "corpus_root": str(processed), "lexicon_origin_policy": "historical_dictionaries_authorized",
            "primary_table": "tabla_analisis_ponderada.csv", "analysis_rows": len(development_rows),
            "full_analysis_table": "archivo/tabla_analisis_completa_83_semanas.csv",
            "full_analysis_rows": len(analysis_rows), "reserved_rows": SIZES["verificacion"],
            "analysis_columns": len(analysis_rows[0]),
            "analysis_complete_rows": sum(all(v is not None for v in row.values()) for row in development_rows),
            "analysis_missing_cell_count": sum(v is None for row in development_rows for v in row.values()),
            "lags": {"weeks": [1, 2, 3, 4], "base_numeric_columns": len(base_columns),
                "lag_columns": 4 * len(base_columns), "missing_history_fill": None,
                "complete_rows": sum(all(row[c] is not None for c in row) for row in analysis_rows)},
            "analysis_missing_values_by_column": {c: sum(row[c] is None for row in analysis_rows)
                for c in analysis_rows[0] if any(row[c] is None for row in analysis_rows)},
            "period_start": weeks[0]["period_start"], "period_end": weeks[-1]["period_end"], "topics": topics,
            "smoothing": {"window": 5, "center": False, "min_periods": 1, "historical_center_was_true": True},
            "input_sha256": hashes, "resource_sha256": resource_hashes, "training_weighting": weighting,
            "models_trained": False, "scaling_fitted": False,
            "missing_values_by_column": {c: sum(r[c] is None for r in rows) for c in rows[0] if any(r[c] is None for r in rows)},
            "output_sha256": {str(p.relative_to(staging)): digest(p) for p in staging.rglob("*") if p.is_file()}}
        write_json(staging / "auditoria.json", report)
        staging.rename(output)
    except BaseException:
        shutil.rmtree(staging)
        raise
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", type=Path, default=ROOT / "datos/radar_semanal_procesado")
    parser.add_argument("--resources-dir", type=Path, default=ROOT / "datos/recursos_indicadores")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "datos/radar_indicadores")
    args = parser.parse_args()
    for directory in (args.processed_dir, args.resources_dir):
        resolved = directory.resolve()
        if not resolved.is_relative_to(ROOT / "datos") or resolved.is_relative_to(ROOT / "trash"):
            parser.error("Las entradas deben estar dentro de datos/ de este repo; no se permiten otros proyectos")
    try:
        report = build(args.processed_dir, args.resources_dir, args.output_dir)
    except (ValueError, FileNotFoundError, FileExistsError) as exc:
        parser.error(str(exc))
    print(json.dumps({key: report[key] for key in ("status", "primary_table", "analysis_rows", "analysis_columns", "analysis_complete_rows", "analysis_missing_cell_count", "period_start", "period_end")}, indent=2))


if __name__ == "__main__":
    main()
