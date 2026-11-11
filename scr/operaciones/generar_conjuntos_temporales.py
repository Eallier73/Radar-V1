#!/usr/bin/env python3
"""Separa el corpus semanal en 56/14/13 sin ajustar con el bloque reservado.

Una fila JSONL es el texto completo de una fuente en una semana, no un post
ni una noticia. La verificación se escribe fuera del directorio de desarrollo.
No construye indicadores de sentimiento, MA5 ni objetivos predictivos.
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


def cargar_desarrollo(development_dir: Path, conjunto: str):
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", type=Path, default=PROCESSED_DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "datos/radar_modelado")
    args = parser.parse_args()
    result = generate(args.processed_dir, args.output_dir)
    print(json.dumps({"status": result["status"], "subsets": result["subsets"],
                      "training_weights": result["training_weighting"]["weights"]}, indent=2))


if __name__ == "__main__":
    main()
