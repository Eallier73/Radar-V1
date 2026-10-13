"""
Extractor automatizado de YouTube
================================

Este script extrae comentarios de YouTube por queries y genera un dataset CSV
para un rango de fechas en la estructura semanal de Radar.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_DIR = REPO_ROOT / "scr" / "compartido"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from output_naming import build_source_filename, build_week_folder_name
from radar_paths import EXTRACTED_DATA_DIR
from youtube_data_contract import (
    YOUTUBE_OUTPUT_COLUMNS,
    YOUTUBE_SEARCH_QUERIES,
    deduplicate_youtube_rows,
    filter_youtube_rows_to_interval,
    project_youtube_rows,
)

try:
    import googleapiclient.discovery as google_discovery
    GOOGLE_API_IMPORT_ERROR = ""
except Exception as exc:
    google_discovery = None
    GOOGLE_API_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

try:
    import pandas as pd
    PANDAS_IMPORT_ERROR = ""
except Exception as exc:
    pd = None
    PANDAS_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"


DEFAULT_START_DATE_STR = "2026-03-15"
DEFAULT_END_DATE_STR = "2026-03-31"
DEFAULT_RANGE_DAYS = 15

DEFAULT_SEARCH_QUERIES = list(YOUTUBE_SEARCH_QUERIES)

DEFAULT_OUTPUT_BASE_DIR = str(EXTRACTED_DATA_DIR)
DEFAULT_API_KEY = ""


def valid_date(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Fecha invalida '{value}', usa YYYY-MM-DD") from exc
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extractor YouTube: comentarios por busqueda",
    )

    parser.add_argument(
        "--queries",
        nargs="+",
        default=DEFAULT_SEARCH_QUERIES,
        help="Consultas para buscar videos y extraer comentarios",
    )
    parser.add_argument(
        "--since",
        type=valid_date,
        required=True,
        help="Fecha inicio YYYY-MM-DD (heredado del orquestador)",
    )
    parser.add_argument(
        "--before",
        type=valid_date,
        required=True,
        help="Fecha fin YYYY-MM-DD (heredado del orquestador)",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_BASE_DIR,
        help="Directorio base de salida. Default: %(default)s",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("YOUTUBE_API_KEY", DEFAULT_API_KEY),
        help="API key de YouTube Data API",
    )
    parser.add_argument(
        "--skip-comments",
        action="store_true",
        help="No extraer comentarios por busquedas",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Muestra periodo y rutas de salida sin consultar YouTube",
    )

    return parser.parse_args()


def resolver_rango_fechas(since: str | None, before: str | None) -> tuple[datetime, datetime]:
    if (since and not before) or (before and not since):
        print("❌ Configuracion de fechas incompleta. Define ambas fechas o ninguna.")
        sys.exit(1)

    if since and before:
        start_date = datetime.strptime(since, "%Y-%m-%d")
        end_date = datetime.strptime(before, "%Y-%m-%d")
    else:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=DEFAULT_RANGE_DAYS)

    end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=0)
    if start_date > end_date:
        print("❌ since no puede ser mayor que before.")
        sys.exit(1)
    return start_date, end_date


def setup_youtube_api(api_key: str):
    if google_discovery is None:
        raise RuntimeError(f"No se pudo importar googleapiclient: {GOOGLE_API_IMPORT_ERROR}")
    return google_discovery.build("youtube", "v3", developerKey=api_key)


def search_videos_by_query(youtube, query: str, start_date: datetime, end_date: datetime) -> List[str]:
    start_date_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    week_before = end_date + timedelta(seconds=1)
    end_date_str = week_before.strftime("%Y-%m-%dT%H:%M:%SZ")

    video_ids: List[str] = []
    search_response = youtube.search().list(
        q=query,
        part="id,snippet",
        maxResults=50,
        type="video",
        publishedAfter=start_date_str,
        publishedBefore=end_date_str,
    ).execute()

    for item in search_response.get("items", []):
        if item.get("id", {}).get("kind") == "youtube#video":
            video_id = item.get("id", {}).get("videoId")
            if video_id:
                video_ids.append(video_id)

    return video_ids


def get_video_details(youtube, video_ids: Sequence[str]) -> Dict[str, Dict[str, str]]:
    details: Dict[str, Dict[str, str]] = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        if not batch:
            continue

        try:
            response = youtube.videos().list(
                part="snippet",
                id=",".join(batch),
            ).execute()
        except Exception as exc:
            print(f"   ⚠️ Error obteniendo detalles de videos: {exc}")
            continue

        for item in response.get("items", []):
            snippet = item.get("snippet", {})
            video_id = item.get("id")
            if not video_id:
                continue
            details[video_id] = {
                "title": snippet.get("title", ""),
                "channel_title": snippet.get("channelTitle", ""),
                "published_at": snippet.get("publishedAt", ""),
            }

    return details


def get_video_comments(
    youtube,
    video_id: str,
    query: str,
    video_title: str = "",
    channel_title: str = "",
    published_at: str = "",
) -> List[Dict]:
    comments = []
    next_page_token = None

    while True:
        try:
            response = youtube.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=100,
                pageToken=next_page_token,
            ).execute()
        except Exception as exc:
            print(f"      ⚠️ Error comentarios en {video_id}: {exc}")
            break

        for item in response.get("items", []):
            snippet = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
            comments.append(
                {
                    "video_id": video_id,
                    "comment_id": item.get("id", ""),
                    "author": snippet.get("authorDisplayName", ""),
                    "comment_text": snippet.get("textDisplay", ""),
                    "published_at": snippet.get("publishedAt", ""),
                    "like_count": snippet.get("likeCount", 0),
                    "query": query,
                    "video_title": video_title,
                    "channel_title": channel_title,
                    "video_published_at": published_at,
                }
            )

        next_page_token = response.get("nextPageToken")
        if not next_page_token:
            break

        time.sleep(0.1)

    return comments


def verificar_dependencias() -> None:
    if sys.version_info < (3, 10):
        print("❌ Python incompatible para este extractor.")
        print(f"   Version detectada: {sys.version.split()[0]}")
        print("   Usa Python 3.11+.")
        sys.exit(1)

    if pd is None:
        print("❌ Falta dependencia 'pandas'.")
        print(f"   Detalle: {PANDAS_IMPORT_ERROR}")
        print("   Instala en tu env activo:")
        print("   python -m pip install -U pandas")
        sys.exit(1)

    if google_discovery is None:
        print("❌ Falta dependencia 'google-api-python-client'.")
        print(f"   Detalle: {GOOGLE_API_IMPORT_ERROR}")
        print("   Instala en tu env activo:")
        print("   python -m pip install -U google-api-python-client")
        sys.exit(1)


def extraer_comentarios_busquedas(
    youtube,
    queries: Sequence[str],
    start_date: datetime,
    end_date: datetime,
) -> tuple[pd.DataFrame, int]:
    all_comments = []
    total_videos = 0

    for i, query in enumerate(queries, 1):
        print(f"🔍 Query {i}/{len(queries)}: {query}")
        try:
            video_ids = search_videos_by_query(youtube, query, start_date, end_date)
        except Exception as exc:
            print(f"   ❌ Error buscando videos para '{query}': {exc}")
            continue

        print(f"   📺 Videos encontrados: {len(video_ids)}")
        if not video_ids:
            print()
            continue

        details = get_video_details(youtube, video_ids)
        total_videos += len(video_ids)

        query_comments = 0
        for j, video_id in enumerate(video_ids, 1):
            info = details.get(video_id, {})
            print(f"   📄 Video {j}/{len(video_ids)}: {video_id}")
            comments = get_video_comments(
                youtube,
                video_id=video_id,
                query=query,
                video_title=info.get("title", ""),
                channel_title=info.get("channel_title", ""),
                published_at=info.get("published_at", ""),
            )
            all_comments.extend(comments)
            query_comments += len(comments)
            print(f"      💬 {len(comments)} comentarios")
            time.sleep(0.5)

        print(f"   ✅ Total query: {query_comments} comentarios")
        print()

    week_before = end_date + timedelta(seconds=1)
    comments_in_week, date_counters = filter_youtube_rows_to_interval(
        all_comments,
        week_start=start_date,
        week_before=week_before,
    )
    projected_comments = project_youtube_rows(comments_in_week)
    unique_comments, duplicates_removed = deduplicate_youtube_rows(projected_comments)

    print("🧹 Contrato semanal YouTube:")
    print(f"   Comentarios descargados: {len(all_comments)}")
    print(f"   Fuera antes de semana:   {date_counters['before']}")
    print(f"   Fuera después de semana: {date_counters['after']}")
    print(f"   Fecha inválida:          {date_counters['invalid']}")
    print(f"   Duplicados eliminados:   {duplicates_removed}")
    print(f"   Comentarios finales:     {len(unique_comments)}")

    df = pd.DataFrame(unique_comments, columns=list(YOUTUBE_OUTPUT_COLUMNS))

    return df, total_videos


def main() -> None:
    args = parse_args()
    if tuple(args.queries) != tuple(DEFAULT_SEARCH_QUERIES):
        print(
            "❌ El contrato uniforme de YouTube requiere exactamente las cuatro "
            "consultas históricas configuradas."
        )
        sys.exit(1)
    start_date, end_date = resolver_rango_fechas(args.since, args.before)

    week_name = build_week_folder_name(start_date, end_date)
    output_dir = Path(args.output_dir).expanduser() / week_name
    comments_base = build_source_filename(week_name, "youtube")
    comments_csv = output_dir / f"{comments_base}.csv"

    print("🚀 Iniciando extracción de YouTube...")
    print(f"📅 Periodo: {start_date.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')}")
    print(f"📂 Salida: {output_dir}")
    print("🎯 Modo: comentarios")
    print(f"📄 Comentarios CSV: {comments_csv}")

    if args.dry_run:
        print("🧪 Dry-run: no se crearon carpetas ni se consulto la API.")
        return

    if args.skip_comments:
        print("⚠️ --skip-comments activo: no hay tareas para ejecutar.")
        return

    verificar_dependencias()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not args.api_key:
        print("❌ No hay API key de YouTube. Usa --api-key o exporta YOUTUBE_API_KEY")
        sys.exit(1)

    try:
        youtube = setup_youtube_api(args.api_key)
    except Exception as exc:
        print(f"❌ Error configurando YouTube API: {exc}")
        sys.exit(1)

    comments_df, total_videos_comments = extraer_comentarios_busquedas(
        youtube,
        queries=args.queries,
        start_date=start_date,
        end_date=end_date,
    )

    comments_df.to_csv(comments_csv, index=False, encoding="utf-8-sig")

    print("✅ Dataset de busquedas guardado")
    print(f"   📄 CSV: {comments_csv}")
    print(f"   📺 Videos: {total_videos_comments}")
    print(f"   💬 Comentarios: {len(comments_df)}")
    print()
    print("🏁 Proceso YouTube finalizado")


if __name__ == "__main__":
    main()
