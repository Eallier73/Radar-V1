"""
Extractor automatizado de YouTube
================================

Este script genera dos datasets principales para un rango de fechas:
1) Comentarios encontrados por búsquedas (queries) -> CSV + TXT limpio
2) Transcripciones de videos por canales (handles) -> CSV + TXT limpio

Ejemplo:
python3 Youtube_Extractor_CDMX.py \
  --channels GobCDMX ClaraBrugadaM \
  --since 2026-02-27 --before 2026-03-06
"""

from __future__ import annotations

import argparse
import os
import re
import string
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Sequence

from output_naming import build_report_tag

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

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    TRANSCRIPT_IMPORT_ERROR = ""
except Exception as exc:
    YouTubeTranscriptApi = None
    TRANSCRIPT_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

try:
    from youtube_transcript_api.proxies import GenericProxyConfig
except Exception:
    GenericProxyConfig = None


# =========================
# CONFIGURACION
# =========================
DEFAULT_START_DATE_STR = "2026-03-15"
DEFAULT_END_DATE_STR = "2026-03-31"
DEFAULT_RANGE_DAYS = 15

DEFAULT_SEARCH_QUERIES = [
    '"jefa de gobierno"',
    '"clara brugada"',
    '"brugada"',
    '"cdmx"',
    '"ciudad de mexico"',
    '"gobierno de CDMX"',
    '"gobierno de la ciudad de mexico"',
]

DEFAULT_CHANNEL_HANDLES = ["GobCDMX", "ClaraBrugadaM"]

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_BASE_DIR = str(REPO_ROOT / "Youtube")
DEFAULT_API_KEY = ""


def valid_date(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Fecha invalida '{value}', usa YYYY-MM-DD") from exc
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extractor YouTube: comentarios por busqueda + transcripciones por canal",
    )

    parser.add_argument("--channels", nargs="+", default=DEFAULT_CHANNEL_HANDLES,
                        help="Handles de canales YouTube (con o sin @)")
    parser.add_argument("--queries", nargs="+", default=DEFAULT_SEARCH_QUERIES,
                        help="Consultas para buscar videos y extraer comentarios")

    parser.add_argument("--since", type=valid_date, required=True,
                        help="Fecha inicio YYYY-MM-DD (heredado del orquestador)")
    parser.add_argument("--before", type=valid_date, required=True,
                        help="Fecha fin YYYY-MM-DD (heredado del orquestador)")

    parser.add_argument("--output-dir", required=True,
                        help="Directorio base de salida (heredado del orquestador)")
    parser.add_argument("--api-key", default=os.getenv("YOUTUBE_API_KEY", DEFAULT_API_KEY),
                        help="API key de YouTube Data API")

    parser.add_argument("--max-videos-query", type=int, default=200,
                        help="Maximo de videos por query")
    parser.add_argument("--max-videos-channel", type=int, default=300,
                        help="Maximo de videos por canal")

    parser.add_argument("--skip-comments", action="store_true",
                        help="No extraer comentarios por busquedas")
    parser.add_argument("--skip-transcripts", action="store_true",
                        help="No extraer transcripciones por canal")
    parser.add_argument(
        "--modo",
        "--mode",
        choices=["comentarios", "transcripciones", "ambos"],
        help="Que descargar: comentarios, transcripciones o ambos (si no se indica, se pregunta en consola)",
    )
    parser.add_argument("--prompt", action="store_true",
                        help="Fuerza modo interactivo para seleccionar que descargar")
    parser.add_argument("--no-prompt", action="store_true",
                        help="Desactiva preguntas interactivas y usa solo CLI/defaults")
    parser.add_argument("--proxy-http", default=os.getenv("YT_PROXY_HTTP", ""),
                        help="Proxy HTTP para transcripciones (http://user:pass@host:port)")
    parser.add_argument("--proxy-https", default=os.getenv("YT_PROXY_HTTPS", ""),
                        help="Proxy HTTPS para transcripciones (http://user:pass@host:port)")

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
    return start_date, end_date


def setup_youtube_api(api_key: str):
    if google_discovery is None:
        raise RuntimeError(f"No se pudo importar googleapiclient: {GOOGLE_API_IMPORT_ERROR}")
    return google_discovery.build("youtube", "v3", developerKey=api_key)


def search_videos_by_query(youtube, query: str, start_date: datetime, end_date: datetime,
                           max_videos: int) -> List[str]:
    start_date_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_date_str = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")

    video_ids: List[str] = []
    seen = set()
    next_page_token = None

    while len(video_ids) < max_videos:
        request = youtube.search().list(
            q=query,
            part="id",
            type="video",
            maxResults=min(50, max_videos - len(video_ids)),
            publishedAfter=start_date_str,
            publishedBefore=end_date_str,
            pageToken=next_page_token,
        )
        response = request.execute()

        for item in response.get("items", []):
            video_id = item.get("id", {}).get("videoId")
            if not video_id or video_id in seen:
                continue
            seen.add(video_id)
            video_ids.append(video_id)

        next_page_token = response.get("nextPageToken")
        if not next_page_token:
            break

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
                "channel_id": snippet.get("channelId", ""),
                "published_at": snippet.get("publishedAt", ""),
            }

    return details


def get_video_comments(youtube, video_id: str, query: str,
                       video_title: str = "", channel_title: str = "", published_at: str = "") -> List[Dict]:
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
            comments.append({
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
            })

        next_page_token = response.get("nextPageToken")
        if not next_page_token:
            break

        time.sleep(0.1)

    return comments


def normalizar_handle(handle: str) -> str:
    return (handle or "").strip().lstrip("@")


def resolve_channel_id(youtube, handle: str) -> tuple[str, str]:
    clean_handle = normalizar_handle(handle)
    if not clean_handle:
        return "", ""

    try:
        response = youtube.channels().list(
            part="id,snippet",
            forHandle=clean_handle,
            maxResults=1,
        ).execute()
        items = response.get("items", [])
        if items:
            item = items[0]
            return item.get("id", ""), item.get("snippet", {}).get("title", clean_handle)
    except Exception:
        pass

    try:
        response = youtube.search().list(
            q=f"@{clean_handle}",
            part="snippet",
            type="channel",
            maxResults=5,
        ).execute()
        items = response.get("items", [])
        if not items:
            return "", ""

        first = items[0]
        channel_id = first.get("snippet", {}).get("channelId") or first.get("id", {}).get("channelId", "")
        channel_title = first.get("snippet", {}).get("channelTitle", clean_handle)
        return channel_id, channel_title
    except Exception:
        return "", ""


def search_channel_videos(youtube, channel_id: str, start_date: datetime,
                          end_date: datetime, max_videos: int) -> List[str]:
    start_date_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_date_str = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")

    video_ids: List[str] = []
    seen = set()
    next_page_token = None

    while len(video_ids) < max_videos:
        request = youtube.search().list(
            part="id",
            channelId=channel_id,
            type="video",
            order="date",
            maxResults=min(50, max_videos - len(video_ids)),
            publishedAfter=start_date_str,
            publishedBefore=end_date_str,
            pageToken=next_page_token,
        )
        response = request.execute()

        for item in response.get("items", []):
            video_id = item.get("id", {}).get("videoId")
            if not video_id or video_id in seen:
                continue
            seen.add(video_id)
            video_ids.append(video_id)

        next_page_token = response.get("nextPageToken")
        if not next_page_token:
            break

    return video_ids


def resolver_modo_descarga(args: argparse.Namespace) -> tuple[bool, bool]:
    if args.skip_comments and args.skip_transcripts:
        print("❌ No puedes usar --skip-comments y --skip-transcripts al mismo tiempo.")
        sys.exit(1)

    if args.skip_comments or args.skip_transcripts:
        return (not args.skip_comments), (not args.skip_transcripts)

    if args.modo:
        return args.modo in {"comentarios", "ambos"}, args.modo in {"transcripciones", "ambos"}

    if args.no_prompt or not sys.stdin.isatty():
        return True, True

    print("\n📥 ¿Que quieres bajar de YouTube?")
    print("1) Solo comentarios")
    print("2) Solo transcripciones")
    print("3) Ambos (comentarios + transcripciones)")

    while True:
        try:
            respuesta = input("Selecciona opcion [1/2/3] (ENTER=3): ").strip().lower()
        except EOFError:
            return True, True

        if respuesta in {"", "3", "ambos", "a"}:
            return True, True
        if respuesta in {"1", "comentarios", "c"}:
            return True, False
        if respuesta in {"2", "transcripciones", "t"}:
            return False, True
        print("⚠️ Opcion invalida. Usa 1, 2 o 3.")


def verificar_dependencias(run_comments: bool, run_transcripts: bool) -> None:
    if sys.version_info < (3, 10):
        print("❌ Python incompatible para este extractor.")
        print(f"   Versión detectada: {sys.version.split()[0]}")
        print("   Usa Python 3.11+ para evitar errores de importlib.metadata.")
        print("   Ejemplo:")
        print("   python3.11 -m venv .venv && source .venv/bin/activate")
        print("   pip install -U google-api-python-client pandas youtube-transcript-api")
        sys.exit(1)

    if pd is None:
        print("❌ Falta dependencia 'pandas'.")
        print(f"   Detalle: {PANDAS_IMPORT_ERROR}")
        print("   Instala en tu env activo:")
        print("   python -m pip install -U pandas")
        sys.exit(1)

    if google_discovery is None and (run_comments or run_transcripts):
        print("❌ Falta dependencia 'google-api-python-client'.")
        print(f"   Detalle: {GOOGLE_API_IMPORT_ERROR}")
        print("   Instala en tu env activo:")
        print("   python -m pip install -U google-api-python-client")
        sys.exit(1)

    if run_transcripts and YouTubeTranscriptApi is None:
        print("⚠️ No se pudo importar youtube-transcript-api.")
        if TRANSCRIPT_IMPORT_ERROR:
            print(f"   Detalle: {TRANSCRIPT_IMPORT_ERROR}")
        print("   Se continuará, pero las transcripciones saldrán con status dependency_missing.")
        print("   Para corregirlo en tu env activo:")
        print("   python -m pip install -U youtube-transcript-api")
        print()


def construir_transcript_client(proxy_http: str, proxy_https: str):
    if YouTubeTranscriptApi is None:
        return None

    http_proxy = (proxy_http or "").strip() or None
    https_proxy = (proxy_https or "").strip() or None

    if http_proxy or https_proxy:
        if GenericProxyConfig is None:
            print("⚠️ GenericProxyConfig no disponible; se ignoran proxies de transcripciones.")
            return YouTubeTranscriptApi()
        proxy_cfg = GenericProxyConfig(http_url=http_proxy, https_url=https_proxy)
        return YouTubeTranscriptApi(proxy_config=proxy_cfg)

    return YouTubeTranscriptApi()


def _segmentos_a_texto(segmentos: Sequence) -> tuple[str, int]:
    if segmentos is None:
        return "", 0

    try:
        segmentos = list(segmentos)
    except Exception:
        segmentos = [segmentos]

    partes = []
    for segmento in segmentos:
        if isinstance(segmento, dict):
            texto = str(segmento.get("text", "")).strip()
        else:
            texto = str(getattr(segmento, "text", "")).strip()
        if texto:
            partes.append(texto)
    return " ".join(partes).strip(), len(segmentos)


def _obtener_lista_transcripciones(video_id: str):
    list_method = getattr(YouTubeTranscriptApi, "list_transcripts", None)
    if callable(list_method):
        return list_method(video_id)

    # Compatibilidad con versiones nuevas del cliente.
    try:
        api = YouTubeTranscriptApi()
    except Exception:
        return None

    list_method = getattr(api, "list_transcripts", None)
    if callable(list_method):
        return list_method(video_id)

    list_method = getattr(api, "list", None)
    if callable(list_method):
        return list_method(video_id)

    return None


def _fetch_por_finder(transcript_list, finder_name: str, langs: Sequence[str]):
    finder = getattr(transcript_list, finder_name, None)
    if not callable(finder):
        return None

    for lang in langs:
        try:
            transcript = finder([lang])
            fetch = getattr(transcript, "fetch", None)
            if callable(fetch):
                return fetch(), lang
        except Exception:
            continue
    return None


def get_video_transcript(video_id: str, transcript_api=None,
                         idiomas: Sequence[str] | None = None) -> tuple[str, str, str, int]:
    if YouTubeTranscriptApi is None:
        return "", "", "dependency_missing", 0

    langs = list(idiomas or ["es", "es-MX", "es-419", "en"])
    errores = []

    # Estrategia 1: API moderna por instancia.
    if transcript_api is not None:
        fetch_method = getattr(transcript_api, "fetch", None)
        if callable(fetch_method):
            try:
                segmentos = fetch_method(video_id, languages=langs)
                transcript_text, n_segments = _segmentos_a_texto(segmentos)
                status = "ok" if transcript_text else "empty"
                return transcript_text, ",".join(langs), status, n_segments
            except Exception as exc:
                errores.append(type(exc).__name__)

    # Estrategia 2: API clasica (versiones anteriores).
    get_transcript_method = getattr(YouTubeTranscriptApi, "get_transcript", None)
    if callable(get_transcript_method):
        try:
            segmentos = get_transcript_method(video_id, languages=langs)
            transcript_text, n_segments = _segmentos_a_texto(segmentos)
            status = "ok" if transcript_text else "empty"
            return transcript_text, ",".join(langs), status, n_segments
        except Exception as exc:
            errores.append(type(exc).__name__)

    # Estrategia 2: listar y fetch de transcripcion manual/generada.
    try:
        transcript_list = _obtener_lista_transcripciones(video_id)
    except Exception as exc:
        transcript_list = None
        errores.append(type(exc).__name__)

    if transcript_list is not None:
        for finder_name in ("find_manually_created_transcript", "find_generated_transcript"):
            resultado = _fetch_por_finder(transcript_list, finder_name, langs)
            if resultado:
                segmentos, _ = resultado
                transcript_text, n_segments = _segmentos_a_texto(segmentos)
                status = "ok" if transcript_text else "empty"
                return transcript_text, ",".join(langs), status, n_segments

        try:
            transcript_items = list(transcript_list)
        except Exception:
            transcript_items = []

        for transcript in transcript_items:
            try:
                fetch = getattr(transcript, "fetch", None)
                if not callable(fetch):
                    continue
                segmentos = fetch()
                transcript_text, n_segments = _segmentos_a_texto(segmentos)
                status = "ok" if transcript_text else "empty"
                return transcript_text, ",".join(langs), status, n_segments
            except Exception as exc:
                errores.append(type(exc).__name__)

    if errores:
        return "", ",".join(langs), f"error:{errores[-1]}", 0
    return "", ",".join(langs), "error:Unknown", 0


def normalizar_texto(texto: str) -> str:
    reemplazos = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
        "Á": "a", "É": "e", "Í": "i", "Ó": "o", "Ú": "u",
        "ñ": "n", "Ñ": "n",
    }
    for original, reemplazo in reemplazos.items():
        texto = texto.replace(original, reemplazo)

    texto = texto.lower()
    texto = re.sub(r"https?:\/\/\S*", " ", texto)
    texto = re.sub(r"\bhttp\b", " ", texto)
    texto = re.sub(r"\bhttps\b", " ", texto)
    texto = re.sub(r"\bcom\b", " ", texto)
    texto = re.sub(r"\.\s*com\b", " ", texto)
    texto = re.sub(r"[" + string.punctuation + string.digits + r"]", " ", texto)
    texto = "".join(c for c in texto if ord(c) < 128)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def construir_txt_limpio(textos: Sequence[str], palabras_por_linea: int = 30) -> List[str]:
    normalizados = []
    for texto in textos:
        limpio = normalizar_texto(str(texto or "").strip())
        if limpio:
            normalizados.append(limpio)

    vistos = set()
    unicos = []
    for item in normalizados:
        if item in vistos:
            continue
        vistos.add(item)
        unicos.append(item)

    palabras = " ".join(unicos).split()
    lineas = []
    for i in range(0, len(palabras), palabras_por_linea):
        linea = " ".join(palabras[i:i + palabras_por_linea]).strip()
        if linea:
            lineas.append(linea)
    return lineas


def guardar_txt_limpio(df: pd.DataFrame, columna_texto: str, ruta_salida: str) -> int:
    os.makedirs(os.path.dirname(ruta_salida) or ".", exist_ok=True)

    if columna_texto not in df.columns:
        with open(ruta_salida, "w", encoding="utf-8") as f:
            f.write("")
        return 0

    textos = df[columna_texto].fillna("").astype(str).tolist()
    lineas = construir_txt_limpio(textos, palabras_por_linea=30)

    with open(ruta_salida, "w", encoding="utf-8") as f:
        for linea in lineas:
            f.write(linea + "\n")

    return len(lineas)


def extraer_comentarios_busquedas(youtube, queries: Sequence[str], start_date: datetime,
                                  end_date: datetime, max_videos_query: int) -> tuple[pd.DataFrame, int]:
    columnas = [
        "video_id", "comment_id", "author", "comment_text", "published_at", "like_count",
        "query", "video_title", "channel_title", "video_published_at", "fecha_extraccion",
    ]

    all_comments = []
    total_videos = 0

    for i, query in enumerate(queries, 1):
        print(f"🔍 Query {i}/{len(queries)}: {query}")
        try:
            video_ids = search_videos_by_query(youtube, query, start_date, end_date, max_videos_query)
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
            time.sleep(0.3)

        print(f"   ✅ Total query: {query_comments} comentarios")
        print()

    if all_comments:
        df = pd.DataFrame(all_comments)
        df["fecha_extraccion"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    else:
        df = pd.DataFrame(columns=columnas)

    return df, total_videos


def extraer_transcripciones_canales(youtube, handles: Sequence[str], start_date: datetime,
                                    end_date: datetime, max_videos_channel: int,
                                    transcript_api=None) -> tuple[pd.DataFrame, int]:
    columnas = [
        "video_id", "channel_handle", "channel_id", "channel_title", "video_title",
        "video_published_at", "transcript_text", "idiomas_intentados", "transcript_status",
        "segmentos_transcripcion", "fecha_extraccion",
    ]

    filas = []
    total_videos = 0
    videos_procesados = set()

    for idx, handle in enumerate(handles, 1):
        clean_handle = normalizar_handle(handle)
        print(f"🎬 Canal {idx}/{len(handles)}: @{clean_handle}")

        channel_id, channel_title = resolve_channel_id(youtube, clean_handle)
        if not channel_id:
            print(f"   ❌ No se pudo resolver canal para @{clean_handle}")
            print()
            continue

        print(f"   ✅ Canal: {channel_title} ({channel_id})")

        try:
            video_ids = search_channel_videos(youtube, channel_id, start_date, end_date, max_videos_channel)
        except Exception as exc:
            print(f"   ❌ Error buscando videos de @{clean_handle}: {exc}")
            print()
            continue

        print(f"   📺 Videos encontrados: {len(video_ids)}")
        if not video_ids:
            print()
            continue

        details = get_video_details(youtube, video_ids)

        for j, video_id in enumerate(video_ids, 1):
            if video_id in videos_procesados:
                continue
            videos_procesados.add(video_id)
            total_videos += 1

            info = details.get(video_id, {})
            print(f"   📄 Video {j}/{len(video_ids)}: {video_id}")
            transcript_text, langs, status, n_segments = get_video_transcript(
                video_id,
                transcript_api=transcript_api,
            )

            filas.append({
                "video_id": video_id,
                "channel_handle": f"@{clean_handle}",
                "channel_id": channel_id,
                "channel_title": info.get("channel_title", channel_title),
                "video_title": info.get("title", ""),
                "video_published_at": info.get("published_at", ""),
                "transcript_text": transcript_text,
                "idiomas_intentados": langs,
                "transcript_status": status,
                "segmentos_transcripcion": n_segments,
                "fecha_extraccion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })

            if status == "ok":
                print(f"      📝 Transcripcion OK ({n_segments} segmentos)")
            else:
                print(f"      ⚠️ Sin transcripcion ({status})")

            time.sleep(0.15)

        print()

    if filas:
        df = pd.DataFrame(filas)
    else:
        df = pd.DataFrame(columns=columnas)

    return df, total_videos


def main() -> None:
    args = parse_args()
    if args.prompt and args.no_prompt:
        print("❌ No puedes usar --prompt y --no-prompt al mismo tiempo.")
        sys.exit(1)
    run_comments, run_transcripts = resolver_modo_descarga(args)
    verificar_dependencias(run_comments, run_transcripts)
    start_date, end_date = resolver_rango_fechas(args.since, args.before)

    report_tag = build_report_tag(start_date, "Youtube")
    output_dir = os.path.join(args.output_dir, report_tag)
    os.makedirs(output_dir, exist_ok=True)

    print("🚀 Iniciando extracción de YouTube...")
    print(f"📅 Periodo: {start_date.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')}")
    print(f"📂 Salida: {output_dir}")
    modo_etiqueta = []
    if run_comments:
        modo_etiqueta.append("comentarios")
    if run_transcripts:
        modo_etiqueta.append("transcripciones")
    print(f"🎯 Modo: {', '.join(modo_etiqueta)}")
    if run_transcripts and (args.proxy_http or args.proxy_https):
        print("🌐 Proxy de transcripciones: activado")

    if not args.api_key:
        print("❌ No hay API key de YouTube. Usa --api-key o exporta YOUTUBE_API_KEY")
        sys.exit(1)

    try:
        youtube = setup_youtube_api(args.api_key)
    except Exception as exc:
        print(f"❌ Error configurando YouTube API: {exc}")
        sys.exit(1)

    comentarios_base = f"{report_tag}_comentarios"
    scripts_base = f"{report_tag}_scripts"

    comments_csv = os.path.join(output_dir, f"{comentarios_base}.csv")
    comments_txt = os.path.join(output_dir, f"{comentarios_base}.txt")

    transcripts_csv = os.path.join(output_dir, f"{scripts_base}.csv")
    transcripts_txt = os.path.join(output_dir, f"{scripts_base}.txt")

    total_videos_comments = 0
    total_videos_transcripts = 0

    if run_comments:
        comments_df, total_videos_comments = extraer_comentarios_busquedas(
            youtube,
            queries=args.queries,
            start_date=start_date,
            end_date=end_date,
            max_videos_query=args.max_videos_query,
        )

        comments_df.to_csv(comments_csv, index=False, encoding="utf-8-sig")
        n_lineas_busquedas = guardar_txt_limpio(comments_df, "comment_text", comments_txt)

        print("✅ Dataset de busquedas guardado")
        print(f"   📄 CSV: {comments_csv}")
        print(f"   📄 TXT: {comments_txt}")
        print(f"   📺 Videos: {total_videos_comments}")
        print(f"   💬 Comentarios: {len(comments_df)}")
        print(f"   🧹 Lineas TXT: {n_lineas_busquedas}")
        print()

    if run_transcripts:
        if YouTubeTranscriptApi is None:
            print("⚠️ youtube-transcript-api no esta instalada. Se generara CSV con status dependency_missing.")

        transcript_api = construir_transcript_client(args.proxy_http, args.proxy_https)
        transcripts_df, total_videos_transcripts = extraer_transcripciones_canales(
            youtube,
            handles=args.channels,
            start_date=start_date,
            end_date=end_date,
            max_videos_channel=args.max_videos_channel,
            transcript_api=transcript_api,
        )

        transcripts_df.to_csv(transcripts_csv, index=False, encoding="utf-8-sig")
        n_lineas_transcripciones = guardar_txt_limpio(transcripts_df, "transcript_text", transcripts_txt)

        print("✅ Dataset de transcripciones guardado")
        print(f"   📄 CSV: {transcripts_csv}")
        print(f"   📄 TXT: {transcripts_txt}")
        print(f"   📺 Videos: {total_videos_transcripts}")
        print(f"   📝 Filas: {len(transcripts_df)}")
        print(f"   🧹 Lineas TXT: {n_lineas_transcripciones}")
        if not transcripts_df.empty and "transcript_status" in transcripts_df.columns:
            n_ip_blocked = int((transcripts_df["transcript_status"] == "error:IpBlocked").sum())
            if n_ip_blocked > 0:
                print(f"   ⚠️ IpBlocked en {n_ip_blocked} videos. Usa --proxy-http/--proxy-https.")
        print()

    print("🏁 Proceso YouTube finalizado")


if __name__ == "__main__":
    main()
