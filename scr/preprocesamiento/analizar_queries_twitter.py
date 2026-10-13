#!/usr/bin/env python3
"""Analiza qué uniformidad de alcance es demostrable en Twitter histórico.

Este análisis no altera ni filtra los CSV canónicos. Distingue la procedencia
registrada en ``query_raw`` de criterios posteriores aplicables al contenido.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Callable, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_DIR = REPO_ROOT / "scr" / "compartido"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from twitter_data_contract import (
    filter_twitter_rows_to_account_scope,
    fold_text,
    text_contains_tampico,
)


DEFAULT_INPUT_DIR = (
    REPO_ROOT / "datos" / "radar_semanal_procesado" / "twitter_semanal_limpio"
)
DEFAULT_OUTPUT_PATH = DEFAULT_INPUT_DIR / "analisis_queries_twitter.json"


def normalize_query(value: str) -> str:
    query = (value or "").strip()
    if query.startswith("reply_to:"):
        return "<reply_to>"
    query = re.sub(
        r"\s+since:\d{4}-\d{2}-\d{2}\s+until:\d{4}-\d{2}-\d{2}\s*$",
        "",
        query,
        flags=re.IGNORECASE,
    ).strip()
    if len(query) >= 2 and query[0] == query[-1] == '"':
        query = query[1:-1]
    return query


def discover_files(input_dir: Path) -> list[Path]:
    return sorted(input_dir.glob("*/*_twitter.csv"))


def _coverage_payload(
    files: Sequence[Path],
    rows_by_week: dict[str, list[dict[str, str]]],
    predicate: Callable[[dict[str, str]], bool],
) -> dict[str, object]:
    counts = {
        path.parent.name: sum(predicate(row) for row in rows_by_week[path.parent.name])
        for path in files
    }
    weeks_with_rows = [week for week, count in counts.items() if count]
    return {
        "rows": sum(counts.values()),
        "weeks_with_rows": len(weeks_with_rows),
        "weeks_without_rows": [week for week, count in counts.items() if not count],
        "rows_by_week": counts,
    }


def analyze_queries(input_dir: Path) -> dict[str, object]:
    files = discover_files(input_dir)
    rows_by_week: dict[str, list[dict[str, str]]] = {}
    query_sets: dict[str, set[str]] = {}
    query_rows: Counter[str] = Counter()
    query_weeks: defaultdict[str, set[str]] = defaultdict(set)

    for path in files:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
        week = path.parent.name
        rows_by_week[week] = rows
        normalized = {
            normalize_query(row.get("query_raw", ""))
            for row in rows
            if normalize_query(row.get("query_raw", ""))
        }
        query_sets[week] = normalized
        for row in rows:
            query = normalize_query(row.get("query_raw", ""))
            if query:
                query_rows[query] += 1
                query_weeks[query].add(week)

    nonempty_sets = [values for values in query_sets.values() if values]
    exact_all = (
        sorted(set.intersection(*query_sets.values())) if query_sets else []
    )
    exact_nonempty = (
        sorted(set.intersection(*nonempty_sets)) if nonempty_sets else []
    )

    def query_family_coverage(predicate: Callable[[str], bool]) -> dict[str, object]:
        weeks = [
            week
            for week, queries in query_sets.items()
            if any(predicate(query) for query in queries)
        ]
        return {
            "weeks_with_family": len(weeks),
            "weeks_without_family": [week for week in query_sets if week not in weeks],
        }

    content_candidates = {
        "account_scope": {
            "rows": sum(
                len(filter_twitter_rows_to_account_scope(rows)[0])
                for rows in rows_by_week.values()
            ),
            "weeks_with_rows": sum(
                bool(filter_twitter_rows_to_account_scope(rows)[0])
                for rows in rows_by_week.values()
            ),
            "weeks_without_rows": [
                week
                for week, rows in rows_by_week.items()
                if not filter_twitter_rows_to_account_scope(rows)[0]
            ],
        },
        "text_contains_tampico": _coverage_payload(
            files,
            rows_by_week,
            lambda row: text_contains_tampico(row.get("text", "")),
        ),
        "text_or_author_mentions_target": _coverage_payload(
            files,
            rows_by_week,
            lambda row: bool(
                re.search(
                    r"tampico|monicavtampico|tampicogob|monica\s+villarreal",
                    fold_text(
                        f"{row.get('text', '')} {row.get('author', '')}"
                    ),
                )
            ),
        ),
    }

    return {
        "input_dir": str(input_dir),
        "weeks": len(files),
        "weeks_with_rows": sum(bool(rows_by_week[path.parent.name]) for path in files),
        "weeks_without_rows": [
            path.parent.name for path in files if not rows_by_week[path.parent.name]
        ],
        "rows": sum(len(rows) for rows in rows_by_week.values()),
        "exact_query_intersection_all_weeks": exact_all,
        "exact_query_intersection_nonempty_weeks": exact_nonempty,
        "normalized_queries": [
            {
                "query": query,
                "rows": count,
                "weeks": len(query_weeks[query]),
            }
            for query, count in query_rows.most_common()
        ],
        "semantic_query_families": {
            "monica_entity": query_family_coverage(
                lambda query: "monica" in fold_text(query)
            ),
            "tampicogob_entity": query_family_coverage(
                lambda query: "tampicogob" in fold_text(query)
            ),
            "any_account_entity": query_family_coverage(
                lambda query: any(
                    token in fold_text(query)
                    for token in ("monicavtampico", "tampicogob")
                )
            ),
            "any_tampico_query": query_family_coverage(
                lambda query: "tampico" in fold_text(query)
            ),
        },
        "uniform_content_candidates": content_candidates,
        "conclusion": {
            "common_query": "ninguna",
            "provenance_limit": (
                "No es válido renombrar queries distintas como una query histórica común."
            ),
            "best_observable_uniform_rule": "account_scope",
            "rule_limit": (
                "Uniforma el alcance de las dos cuentas sobre lo descargado, pero no "
                "recupera tweets que las queries históricas nunca capturaron."
            ),
        },
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analiza intersección y alternativas de queries en Twitter limpio."
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    analysis = analyze_queries(args.input_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(analysis, ensure_ascii=False, indent=2))
    print(f"Análisis: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
