#!/usr/bin/env python3
"""Divide la tabla de indicadores ya generada en 56/14/13, sin reajustes.

El CLI exige la tabla completa: primero construir_tabla_indicadores.py, después
este programa. La función generate conserva la generación anterior de corpus
sólo como referencia reproducible del respaldo; no es la operación del CLI.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scr" / "compartido"))
from radar_paths import PROCESSED_DATA_DIR

SOURCES = ("youtube", "twitter", "facebook", "medios")
SIZES = {"entrenamiento": 56, "prueba": 14, "verificacion": 13}
LOCATIONS = {"entrenamiento": Path("desarrollo/entrenamiento"),
             "prueba": Path("desarrollo/prueba"),
             "verificacion": Path("verificacion_reservada")}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def discover(root: Path) -> list[dict]:
    """Inspecciona nombres de archivo; no calcula estadísticas del reservado."""
    by_source = {}
    for source in SOURCES:
        found = {}
        for path in sorted((root / f"{source}_semanal_procesado").glob(f"*/*_{source}.txt")):
            week = path.parent.name
            start = date.fromisoformat(week[:10])
            if "_semana_" not in week or path.name != f"{week}_{source}.txt":
                raise ValueError(f"Nombre semanal no canónico: {path}")
            if start in found:
                raise ValueError(f"Semana duplicada para {source}: {start}")
            found[start] = (week, path)
        if not found:
            raise ValueError(f"No hay semanas de {source}")
        by_source[source] = found
    weeks = sorted(by_source[SOURCES[0]])
    if any(set(found) != set(weeks) for found in by_source.values()):
        raise ValueError("Las cuatro fuentes deben cubrir las mismas semanas")
    if any(start.weekday() != 0 for start in weeks):
        raise ValueError("Los inicios semanales deben ser lunes")
    if any(b - a != timedelta(days=7) for a, b in zip(weeks, weeks[1:])):
        raise ValueError("Hay huecos en la secuencia semanal")
    result = []
    for start in weeks:
        names = {by_source[source][start][0] for source in SOURCES}
        if len(names) != 1:
            raise ValueError(f"Carpetas semanales distintas entre fuentes: {start}")
        result.append({"week": names.pop(), "period_start": start.isoformat(),
                       "period_end": (start + timedelta(days=6)).isoformat(),
                       "files": {source: by_source[source][start][1] for source in SOURCES}})
    return result


def assign(weeks: list[dict], sizes: dict[str, int]) -> dict[str, list[dict]]:
    if set(sizes) != set(SIZES) or any(type(n) is not int or n <= 0 for n in sizes.values()):
        raise ValueError("Se requieren tres tamaños enteros positivos")
    if sum(sizes.values()) != len(weeks):
        raise ValueError(f"Los tamaños suman {sum(sizes.values())}; hay {len(weeks)} semanas")
    if [w["period_start"] for w in weeks] != sorted({w["period_start"] for w in weeks}):
        raise ValueError("Las semanas deben ser únicas y estar ordenadas")
    result, offset = {}, 0
    for name in SIZES:
        result[name] = weeks[offset:offset + sizes[name]]
        offset += sizes[name]
    return result


def generate(processed: Path, output: Path, sizes: dict[str, int] | None = None) -> dict:
    processed, output = processed.resolve(), output.resolve()
    if output == processed or output.is_relative_to(processed) or processed.is_relative_to(output):
        raise ValueError("La salida debe estar separada del corpus de entrada")
    if output.exists():
        raise FileExistsError(f"La salida ya existe; se conserva sin sobrescribir: {output}")
    groups = assign(discover(processed), SIZES if sizes is None else sizes)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    inputs, outputs, training_words, manifest = {}, {}, dict.fromkeys(SOURCES, 0), []
    report = {"status": "generated_corpus_not_indicator_table", "schema_version": 1,
              "split_order": list(SIZES), "unit": "one_source_week_per_jsonl_record",
              "sources": list(SOURCES), "subsets": {}, "models_trained": False,
              "verification_used_for_fit": False,
              "historical_full_corpus_already_audited": True}
    try:
        for name, weeks in groups.items():
            folder = staging / LOCATIONS[name]
            folder.mkdir(parents=True)
            corpus = folder / "corpus.jsonl"
            with corpus.open("w", encoding="utf-8", newline="\n") as handle:
                for week in weeks:
                    entry = {"conjunto": name, "week": week["week"],
                             "period_start": week["period_start"], "period_end": week["period_end"]}
                    for source in SOURCES:
                        path = week["files"][source]
                        raw = path.read_bytes()
                        text = raw.decode("utf-8")
                        if not text.strip():
                            raise ValueError(f"Texto vacío: {path}")
                        relative = str(path.relative_to(processed))
                        source_hash = hashlib.sha256(raw).hexdigest()
                        inputs[relative] = source_hash
                        record = {**entry, "source": source, "source_path": relative,
                                  "source_sha256": source_hash, "text": text}
                        handle.write(json.dumps(record, ensure_ascii=True) + "\n")
                        entry[f"{source}_sha256"] = source_hash
                        # El reservado sólo se transporta y verifica; no calibra pesos.
                        if name == "entrenamiento":
                            training_words[source] += len(text.split())
                    manifest.append(entry)
            outputs[str(corpus.relative_to(staging))] = digest(corpus)
            report["subsets"][name] = {"weeks": len(weeks), "source_week_records": 4 * len(weeks),
                "period_start": weeks[0]["period_start"], "period_end": weeks[-1]["period_end"],
                "corpus": str(corpus.relative_to(staging))}
        scores = {source: words ** .5 for source, words in training_words.items()}
        total = sum(scores.values())
        weights = {"alpha": .5, "status": "calibrated_on_training_not_applied_to_a_model",
                   "calibration_subset": "entrenamiento", "calibration_weeks": len(groups["entrenamiento"]),
                   "formula": "w_s = sqrt(T_s) / sum(sqrt(T_j))", "words": training_words,
                   "weights": {source: value / total for source, value in scores.items()},
                   "user_factor_used": False,
                   "input_hashes": {str(week["files"][source].relative_to(processed)):
                                    inputs[str(week["files"][source].relative_to(processed))]
                                    for week in groups["entrenamiento"] for source in SOURCES}}
        weights_path = staging / LOCATIONS["entrenamiento"] / "pesos_fuentes.json"
        write_json(weights_path, weights)
        outputs[str(weights_path.relative_to(staging))] = digest(weights_path)
        manifest_path = staging / "particion_semanas.csv"
        with manifest_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(manifest[0]))
            writer.writeheader()
            writer.writerows(manifest)
        outputs[str(manifest_path.relative_to(staging))] = digest(manifest_path)
        for relative, expected in inputs.items():
            if digest(processed / relative) != expected:
                raise ValueError(f"Cambió el corpus durante la separación: {relative}")
        report.update(input_sha256=inputs, output_sha256=outputs, source_files_unchanged=True,
                      training_weighting={key: value for key, value in weights.items() if key != "input_hashes"})
        write_json(staging / "auditoria.json", report)
        staging.rename(output)
    except BaseException:
        shutil.rmtree(staging)
        raise
    return report


def cargar_corpus_desarrollo(development_dir: Path, conjunto: str):
    """Carga sólo entrenamiento o prueba; nunca abre el directorio reservado.

    Los parámetros del aprendizaje se ajustan con entrenamiento. Prueba sirve
    para comparar configuraciones, sin reajustar las transformaciones con ella.
    """
    if conjunto not in {"entrenamiento", "prueba"}:
        raise ValueError("El cargador de desarrollo no permite verificación")
    path = development_dir / conjunto / "corpus.jsonl"
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if record["conjunto"] != conjunto:
                raise ValueError("El corpus contiene otro conjunto")
            yield record


def partition_table(table: Path, weights_path: Path, output: Path) -> dict:
    """Parte filas de la tabla existente, sin recalcular ni estandarizar."""
    table, weights_path, output = table.resolve(), weights_path.resolve(), output.resolve()
    if output.exists():
        raise FileExistsError(f"Se conserva la salida existente: {output}")
    if any(path == output or path.is_relative_to(output) for path in (table, weights_path)):
        raise ValueError("La salida no puede contener las entradas")
    table_hash, weights_hash = digest(table), digest(weights_path)
    origin_audit_path = table.parent / "auditoria.json"
    if table.parent.name == "archivo":
        origin_audit_path = table.parent.parent / "auditoria.json"
    if not origin_audit_path.is_file():
        raise ValueError("La tabla no acredita el corpus actual de este repo")
    origin_audit = json.loads(origin_audit_path.read_text())
    if (origin_audit.get("corpus_origin_policy") != "current_repository_only" or
            origin_audit.get("output_sha256", {}).get(str(table.relative_to(origin_audit_path.parent))) != table_hash):
        raise ValueError("La tabla no acredita resultados del corpus actual; no se puede dividir")
    with table.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames
        rows = list(reader)
    if not columns or len(columns) != len(set(columns)):
        raise ValueError("Encabezado vacío o duplicado")
    if not {"semana_iso", "Fecha_Semana", "Fecha_Fin"} <= set(columns):
        raise ValueError("Se requiere la tabla de indicadores, no el inventario de textos")
    if len(rows) != sum(SIZES.values()):
        raise ValueError("Se requieren las 83 filas de indicadores")
    starts = [date.fromisoformat(row["Fecha_Semana"]) for row in rows]
    if any(start.weekday() != 0 for start in starts) or any(b - a != timedelta(days=7) for a, b in zip(starts, starts[1:])):
        raise ValueError("Las filas deben ser semanas únicas, ordenadas y consecutivas")
    for row, start in zip(rows, starts):
        if row["Fecha_Fin"] != (start + timedelta(days=6)).isoformat():
            raise ValueError("La fecha final no coincide con la semana")
        year, number, _ = start.isocalendar()
        if row["semana_iso"] != f"{year}-W{number:02d}" or ("semana_corpus" in row and row["semana_corpus"][:10] != start.isoformat()):
            raise ValueError("Los identificadores de semana no coinciden con la fecha")
    weighting = json.loads(weights_path.read_text())
    if (weighting["calibration_subset"] != "entrenamiento" or
            weighting["calibration_weeks"] != SIZES["entrenamiento"] or
            weighting["period_start"] != rows[0]["Fecha_Semana"] or
            weighting["period_end"] != rows[SIZES["entrenamiento"] - 1]["Fecha_Fin"]):
        raise ValueError("Los pesos deben calibrarse sólo con las 56 semanas de entrenamiento")
    training_dates = {row["Fecha_Semana"] for row in rows[:SIZES["entrenamiento"]]}
    training_names = {row["Fecha_Semana"]: row.get("semana_corpus") for row in rows[:SIZES["entrenamiento"]]}
    observed_inputs = set()
    for relative in weighting["input_hashes"]:
        parts = Path(relative).parts
        if len(parts) != 3:
            raise ValueError("Ruta de calibración no canónica")
        folder, week, filename = parts
        source = folder.removesuffix("_semanal_procesado")
        key = (source, week[:10])
        if (source not in SOURCES or folder != f"{source}_semanal_procesado" or
                week[:10] not in training_dates or "_semana_" not in week or
                filename != f"{week}_{source}.txt" or key in observed_inputs or
                (training_names[week[:10]] is not None and training_names[week[:10]] != week)):
            raise ValueError("Entrada de calibración fuera de entrenamiento o duplicada")
        observed_inputs.add(key)
    if observed_inputs != {(source, start) for source in SOURCES for start in training_dates}:
        raise ValueError("Los pesos contienen entradas fuera de entrenamiento o cobertura incompleta")
    if not all(v > 0 for v in weighting["weights"].values()) or abs(sum(weighting["weights"].values()) - 1) > 1e-12:
        raise ValueError("Pesos de fuentes inválidos")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    subsets, offset, manifest = {}, 0, []
    try:
        for name, size in SIZES.items():
            selected = rows[offset:offset + size]
            path = staging / LOCATIONS[name] / "indicadores.csv"
            path.parent.mkdir(parents=True)
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=columns)
                writer.writeheader()
                writer.writerows(selected)
            subsets[name] = {"rows": len(selected), "period_start": selected[0]["Fecha_Semana"],
                "period_end": selected[-1]["Fecha_Fin"], "table": str(path.relative_to(staging)), "sha256": digest(path)}
            manifest.extend({"conjunto": name, "semana_iso": row["semana_iso"], "Fecha_Semana": row["Fecha_Semana"]} for row in selected)
            offset += size
        development_table = staging / "desarrollo/indicadores.csv"
        with development_table.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows[:SIZES["entrenamiento"] + SIZES["prueba"]])
        shutil.copyfile(weights_path, staging / LOCATIONS["entrenamiento"] / "pesos_fuentes.json")
        with (staging / "particion_semanas.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(manifest[0]))
            writer.writeheader()
            writer.writerows(manifest)
        if digest(table) != table_hash or digest(weights_path) != weights_hash:
            raise ValueError("Cambió la tabla o su calibración durante la partición")
        report = {"status": "indicator_table_partitioned", "pipeline_order": ["build_83_week_indicator_table", "partition_existing_table_56_14_13"],
            "input_table": str(table), "input_table_sha256": table_hash, "input_weights_sha256": weights_hash,
            "corpus_origin_policy": "current_repository_only",
            "columns": len(columns), "rows": len(rows), "subsets": subsets,
            "development_table": "desarrollo/indicadores.csv", "development_rows": SIZES["entrenamiento"] + SIZES["prueba"],
            "development_table_sha256": digest(development_table),
            "values_recalculated_during_partition": False, "models_trained": False,
            "scaling_fitted": False, "verification_used_for_fit": False}
        write_json(staging / "auditoria.json", report)
        staging.rename(output)
    except BaseException:
        shutil.rmtree(staging)
        raise
    return report


def cargar_desarrollo(development_dir: Path, conjunto: str):
    """Carga indicadores exclusivamente de entrenamiento o prueba."""
    if conjunto not in {"entrenamiento", "prueba"}:
        raise ValueError("El cargador de desarrollo no permite verificación")
    path = development_dir / conjunto / "indicadores.csv"
    evidence = json.loads((development_dir.parent / "auditoria.json").read_text())
    if (evidence.get("corpus_origin_policy") != "current_repository_only" or
            evidence.get("subsets", {}).get(conjunto, {}).get("sha256") != digest(path)):
        raise ValueError("El conjunto no acredita resultados del corpus actual")
    with path.open(encoding="utf-8", newline="") as handle:
        yield from csv.DictReader(handle)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table", type=Path, default=ROOT / "datos/radar_indicadores/archivo/tabla_analisis_completa_83_semanas.csv")
    parser.add_argument("--weights", type=Path, default=ROOT / "datos/radar_indicadores/pesos_fuentes_entrenamiento.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "datos/radar_modelado")
    args = parser.parse_args()
    result = partition_table(args.table, args.weights, args.output_dir)
    print(json.dumps({"status": result["status"], "subsets": result["subsets"]}, indent=2))


if __name__ == "__main__":
    main()
