#!/usr/bin/env python3
"""
╔═══════════════════════════════════════════════════════════════════════════╗
║                                                                           ║
║   📝 EXTRACTOR DE POSTS FACEBOOK VÍA APIFY                               ║
║                                                                           ║
║   Modo A (sin CSV): Descargo posts directamente desde páginas             ║
║   Modo B (con CSV): Descargo posts de URLs específicas (CSV con post_url)  ║
║                                                                           ║
║   IMPORTANTE: Solo descarga posts, NUNCA comentarios                      ║
║                                                                           ║
║   Uso Modo A (directo):                                                  ║
║   python 4_extractors_facebook_posts.py \\                               ║
║     --pages GobiernoCDMX ClaraBrugadaM \\                                ║
║     --since 2026-03-01 --before 2026-03-12 \\                            ║
║     --output-dir ./Facebook                                              ║
║                                                                           ║
║   Uso Modo B (desde URLs):                                               ║
║   python 4_extractors_facebook_posts.py \\                               ║
║     --input-csv ./Facebook/2026-03-01_Facebook/2026-03-01_posts.csv \\  ║
║     --since 2026-03-01 --before 2026-03-12 \\                            ║
║     --output-dir ./Facebook                                              ║
║                                                                           ║
╚═══════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import argparse
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import pandas as pd

from output_naming import build_report_tag


ACTOR_POSTS = "apify/facebook-posts-scraper"
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_BASE_DIR = str(REPO_ROOT / "Facebook")
DEFAULT_PAGES = ["GobiernoCDMX", "ClaraBrugadaM"]
DEFAULT_RESULTS_LIMIT_PER_PAGE = 100
DEFAULT_BATCH_SIZE = 10


def valid_date(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Fecha invalida '{value}', usa YYYY-MM-DD") from exc
    return value


def valid_sampling_percent(value: str) -> float:
    try:
        pct = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Sampling invalido '{value}', usa un numero entre 0 y 100."
        ) from exc

    if pct <= 0 or pct > 100:
        raise argparse.ArgumentTypeError(
            f"Sampling invalido '{value}', debe ser > 0 y <= 100."
        )
    return pct


def parse_pages_text(raw: str) -> list[str]:
    normalizado = raw.replace(",", " ").strip()
    return [p for p in normalizado.split() if p]


def normalize_target(target: str) -> str:
    value = (target or "").strip()
    if not value:
        return ""

    if "facebook.com" in value.lower():
        parsed = urlparse(value)
        path = (parsed.path or "").strip("/")
        if path:
            return path.split("/")[0].lower()
        return ""

    value = value.removeprefix("@").strip("/")
    return value.lower()


def target_to_page_url(target: str) -> str:
    value = (target or "").strip()
    if not value:
        return ""
    if value.lower().startswith("http://") or value.lower().startswith("https://"):
        return value
    value = value.removeprefix("@")
    return f"https://www.facebook.com/{value}"


def extract_handle_from_url(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        path = (parsed.path or "").strip("/")
        if not path:
            return ""
        return path.split("/")[0].lower()
    except Exception:
        return ""


def parse_item_datetime(item: dict) -> Optional[datetime]:
    # Prioridad: timestamp numerico (s/ms), luego campos string ISO.
    timestamp_candidates = [
        item.get("timestamp"),
        item.get("postTimestamp"),
        item.get("createdTime"),
        item.get("createdAt"),
    ]
    for raw in timestamp_candidates:
        if raw is None:
            continue
        try:
            if isinstance(raw, str) and raw.strip().isdigit():
                raw = int(raw.strip())
            if isinstance(raw, (int, float)):
                ts = float(raw)
                if ts > 10_000_000_000:  # milisegundos
                    ts = ts / 1000.0
                return datetime.fromtimestamp(ts)
        except Exception:
            continue

    date_candidates = [
        item.get("time"),
        item.get("date"),
        item.get("postDate"),
        item.get("publishedAt"),
        item.get("createdAt"),
    ]
    for raw in date_candidates:
        text = str(raw or "").strip()
        if not text:
            continue
        try:
            if text.endswith("Z"):
                text = text.replace("Z", "+00:00")
            return datetime.fromisoformat(text).replace(tzinfo=None)
        except Exception:
            pass
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(text, fmt)
            except Exception:
                continue
    return None


def in_date_range(value: Optional[datetime], since: Optional[str], before: Optional[str]) -> bool:
    if value is None:
        return False
    since_dt = datetime.strptime(since, "%Y-%m-%d") if since else None
    before_dt = datetime.strptime(before, "%Y-%m-%d") if before else None

    date_only = value.date()
    if since_dt and date_only < since_dt.date():
        return False
    if before_dt and date_only > before_dt.date():
        return False
    return True


def belongs_to_targets(item: dict, target_handles: set[str]) -> bool:
    if not target_handles:
        return True

    page_url = str(item.get("page_url") or "")
    post_url = str(item.get("post_url") or "")
    explicit = str(item.get("page_handle") or "").lower().strip()
    if explicit and explicit in target_handles:
        return True

    candidates = {
        extract_handle_from_url(page_url),
        extract_handle_from_url(post_url),
    }
    if any(c and c in target_handles for c in candidates):
        return True

    page_url_l = page_url.lower()
    post_url_l = post_url.lower()
    for h in target_handles:
        token = f"/{h}/"
        if token in page_url_l or token in post_url_l:
            return True
    return False


def normalize_post_item(item: dict) -> dict:
    user = item.get("user") if isinstance(item.get("user"), dict) else {}

    # apify/facebook-posts-scraper usa "url" para post y "facebookUrl" para página
    post_url = str(item.get("url") or item.get("facebookUrl") or "").strip()
    page_url = str(item.get("facebookUrl") or item.get("inputUrl") or "").strip()

    dt = parse_item_datetime(item)
    dt_iso = dt.isoformat(sep=" ") if dt else ""

    return {
        "post_url": post_url,
        "page_url": page_url,
        "page_handle": str(item.get("pageName") or extract_handle_from_url(page_url) or "").strip().lower(),
        "post_texto": str(item.get("text") or "").strip(),
        "fecha_post": dt_iso,
        "fecha_post_date": dt.date().isoformat() if dt else "",
        "num_comentarios_post": item.get("comments") or 0,
        "reacciones_post": item.get("likes") or 0,
        "autor": str(user.get("name") or item.get("pageName") or "").strip(),
    }


def leer_urls_csv(input_csv: str) -> list[str]:
    """Lee URLs desde CSV con columna post_url/url/URL."""
    if not os.path.exists(input_csv):
        raise FileNotFoundError(f"No existe: {input_csv}")
    
    urls = []
    vistas = set()
    
    try:
        df = pd.read_csv(input_csv, encoding="utf-8")
    except Exception as e:
        raise ValueError(f"Error leyendo CSV: {e}")
    
    # Buscar columna de URL
    col_url = None
    for candidato in ["post_url", "url", "URL"]:
        if candidato in df.columns:
            col_url = candidato
            break
    
    if col_url is None:
        raise ValueError(f"CSS sin columna 'post_url'. Columnas: {df.columns.tolist()}")
    
    for _, row in df.iterrows():
        raw = str(row.get(col_url) or "").strip()
        if raw and raw not in vistas:
            urls.append(raw)
            vistas.add(raw)
    
    return urls


def run_posts_batch(client, page_urls: list[str], results_limit: int, since: Optional[str] = None, before: Optional[str] = None) -> list[dict]:
    run_input = {
        "startUrls": [{"url": url} for url in page_urls],
        "resultsLimit": results_limit,
        "captionText": True,
    }
    if since:
        run_input["onlyPostsNewerThan"] = since
    if before:
        run_input["onlyPostsOlderThan"] = before

    try:
        run = client.actor(ACTOR_POSTS).call(run_input=run_input)
    except Exception as exc:
        print(f"     Error al correr actor: {exc}")
        return []

    if not run:
        print("     El actor no retorno resultado.")
        return []

    status = run.get("status", "UNKNOWN")
    cost = run.get("usageTotalUsd", 0)
    print(f"     Status: {status} | Costo: ${cost:.4f} USD")

    dataset_id = run.get("defaultDatasetId")
    if not dataset_id:
        print("     Sin dataset en respuesta del actor.")
        return []

    items = list(client.dataset(dataset_id).iterate_items())
    print(f"     Items recibidos: {len(items)}")
    return items


def _input_con_default(label: str, default: str) -> str:
    val = input(f"{label} [{default}]: ").strip()
    return val or default


def _input_int(label: str, default: Optional[int], minimo: int = 1) -> Optional[int]:
    suffix = f" [{default}]" if default is not None else " [vacio]"
    while True:
        raw = input(f"{label}{suffix}: ").strip()
        if not raw:
            return default
        try:
            n = int(raw)
            if n < minimo:
                print(f"   Debe ser >= {minimo}")
                continue
            return n
        except ValueError:
            print("   Ingresa un entero valido.")


def _input_float(
    label: str,
    default: Optional[float],
    minimo: float = 0.01,
    maximo: float = 100.0,
) -> Optional[float]:
    suffix = f" [{default}]" if default is not None else " [vacio]"
    while True:
        raw = input(f"{label}{suffix}: ").strip()
        if not raw:
            return default
        try:
            n = float(raw)
            if n < minimo or n > maximo:
                print(f"   Debe estar entre {minimo} y {maximo}.")
                continue
            return n
        except ValueError:
            print("   Ingresa un numero valido.")


def _input_date(label: str, default: str) -> str:
    while True:
        value = _input_con_default(label, default)
        try:
            valid_date(value)
            return value
        except argparse.ArgumentTypeError:
            print("   Formato invalido. Usa YYYY-MM-DD.")


def ejecutar_prompt_interactivo(args: argparse.Namespace) -> argparse.Namespace:
    print("\n" + "=" * 70)
    print("MODO INTERACTIVO - EXTRACTOR FACEBOOK POSTS APIFY")
    print("=" * 70)

    default_pages = " ".join(args.pages or DEFAULT_PAGES)
    pages_raw = _input_con_default("Paginas target (espacio o coma)", default_pages)
    args.pages = parse_pages_text(pages_raw)

    today = datetime.now().date()
    since_default = args.since or (today - timedelta(days=7)).strftime("%Y-%m-%d")
    before_default = args.before or today.strftime("%Y-%m-%d")
    args.since = _input_date("Fecha desde (YYYY-MM-DD)", since_default)
    args.before = _input_date("Fecha hasta (YYYY-MM-DD)", before_default)

    args.max_posts = _input_int("Max posts por pagina", args.max_posts, minimo=1) or DEFAULT_RESULTS_LIMIT_PER_PAGE
    args.max_pages = _input_int("Max paginas target (vacio = todas)", args.max_pages, minimo=1)
    args.sample_percent = _input_float(
        "Sampling paginas target (%) (vacio = sin sampling)",
        args.sample_percent,
        minimo=0.01,
        maximo=100.0,
    )
    if args.sample_percent is not None:
        args.sample_seed = _input_int("Semilla sampling", args.sample_seed, minimo=0) or 42
    args.batch_size = _input_int("Batch size paginas", args.batch_size, minimo=1) or DEFAULT_BATCH_SIZE

    output_raw = input(f"Directorio base salida [{args.output_dir}]: ").strip()
    if output_raw:
        args.output_dir = output_raw

    if not (args.token or os.environ.get("APIFY_TOKEN")):
        token_raw = input("APIFY token (ENTER si ya esta en APIFY_TOKEN): ").strip()
        if token_raw:
            args.token = token_raw
    return args


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Descarga posts de Facebook usando scraper_one/facebook-posts-scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modo A - Descarga directa desde páginas:
  python 4_extractors_facebook_posts.py \\
    --pages GobiernoCDMX ClaraBrugadaM \\
    --since 2026-03-01 --before 2026-03-12 \\
    --output-dir ./Facebook

Modo B - Desde URLs preexistentes (recomendado, más eficiente):
  python 4_extractors_facebook_posts.py \\
        --input-csv ./Facebook/2026-03-01_Facebook/2026-03-01_posts.csv \
    --since 2026-03-01 --before 2026-03-12 \\
    --output-dir ./Facebook
        """,
    )
    parser.add_argument("--pages", nargs="+", default=None,
                        help="Paginas target (handles o URLs). Requerido si NO se usa --input-csv")
    parser.add_argument("--input-csv", default=None,
                        help="CSV con columna post_url/url/URL (Modo B)")
    parser.add_argument("--since", required=True, type=valid_date,
                        help="Fecha inicio YYYY-MM-DD (heredada del orquestador)")
    parser.add_argument("--before", required=True, type=valid_date,
                        help="Fecha fin YYYY-MM-DD (heredada del orquestador)")
    parser.add_argument("--max-posts", type=int, default=DEFAULT_RESULTS_LIMIT_PER_PAGE,
                        help="Maximo de posts por pagina target en el actor")
    parser.add_argument("--max-pages", type=int, default=None,
                        help="Limitar numero de paginas target")
    parser.add_argument("--max-urls", type=int, default=None,
                        help="Alias legacy de --max-pages")
    parser.add_argument("--sample-percent", type=valid_sampling_percent, default=None,
                        help="Sampling aleatorio de paginas target en porcentaje (0-100)")
    parser.add_argument("--sample-seed", type=int, default=42,
                        help="Semilla para sampling de paginas target (default: 42)")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
                        help="Paginas/URLs por batch de ejecucion (default: 10)")
    parser.add_argument("--token", default=None,
                        help="Apify API token (o variable APIFY_TOKEN)")
    parser.add_argument("--output-dir", required=True,
                        help="Directorio base de salida (heredado del orquestador)")
    parser.add_argument("--prompt", action="store_true",
                        help="Forzar modo interactivo")
    parser.add_argument("--no-prompt", action="store_true",
                        help="Desactivar modo interactivo")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.prompt and args.no_prompt:
        print("No puedes usar --prompt y --no-prompt al mismo tiempo.")
        sys.exit(1)

    # Validar que si se usa --input-csv, no se requieren --pages
    use_csv_mode = args.input_csv is not None
    if not use_csv_mode and not args.pages:
        args.pages = DEFAULT_PAGES

    if not args.since or not args.before:
        print("Debes indicar --since y --before (o capturarlas en prompt).")
        sys.exit(1)

    since_dt = datetime.strptime(args.since, "%Y-%m-%d")
    before_dt = datetime.strptime(args.before, "%Y-%m-%d")
    if since_dt > before_dt:
        print("Fecha invalida: --since no puede ser mayor a --before.")
        sys.exit(1)

    token = args.token or os.environ.get("APIFY_TOKEN")
    if not token:
        print("Necesitas APIFY_TOKEN o --token para ejecutar el actor.")
        print("Token: https://console.apify.com/settings/integrations")
        sys.exit(1)

    try:
        from apify_client import ApifyClient
    except ImportError:
        print("Falta dependencia: apify-client")
        print("Instala con: pip install apify-client pandas")
        sys.exit(1)

    client = ApifyClient(token)

    # ========================================================================
    # MODO A: Leer URLs desde file CSV (recomendado)
    # ========================================================================
    if use_csv_mode:
        print("\n" + "=" * 70)
        print("MODO B: POSTS DESDE URLs (CSV)")
        print("=" * 70)
        
        try:
            page_urls = leer_urls_csv(args.input_csv)
        except (FileNotFoundError, ValueError) as e:
            print(f"❌ Error leyendo CSV: {e}")
            sys.exit(1)
        
        if not page_urls:
            print("❌ No hay URLs en el CSV.")
            sys.exit(1)
        
        print(f"✅ {len(page_urls)} URLs leídas desde CSV")
        target_handles = ["from_csv"]
        
    # ========================================================================
    # MODO B: Descargar URLs directamente desde páginas
    # ========================================================================
    else:
        print("\n" + "=" * 70)
        print("MODO A: POSTS DESDE PÁGINAS")
        print("=" * 70)
        
        target_handles = [normalize_target(p) for p in args.pages]
        target_handles = [h for h in target_handles if h]
        if not target_handles:
            print("❌ No se pudieron normalizar páginas target.")
            sys.exit(1)

        page_urls = [target_to_page_url(p) for p in args.pages if str(p).strip()]
        page_urls = [u for u in page_urls if u]

        if args.sample_percent is not None and args.sample_percent < 100:
            original_count = len(page_urls)
            sample_size = max(1, round(original_count * (args.sample_percent / 100.0)))
            if sample_size < original_count:
                random.seed(args.sample_seed)
                page_urls = random.sample(page_urls, sample_size)
                print(f"🎲 Sampling páginas: {args.sample_percent:.2f}% ({sample_size}/{original_count})")

        max_pages = args.max_pages if args.max_pages is not None else args.max_urls
        if max_pages and len(page_urls) > max_pages:
            page_urls = page_urls[:max_pages]
            print(f"Limitado a {max_pages} páginas target")

    if not page_urls:
        print("❌ No hay URLs para procesar.")
        sys.exit(1)

    print(f"Actor: {ACTOR_POSTS}")
    print(f"Targets: {', '.join(target_handles)}")
    print(f"Rango: {args.since} -> {args.before}")
    print(f"URLs a procesar: {len(page_urls)}")

    all_items: list[dict] = []
    total_batches = (len(page_urls) + args.batch_size - 1) // args.batch_size
    for i in range(0, len(page_urls), args.batch_size):
        batch = page_urls[i:i + args.batch_size]
        batch_num = (i // args.batch_size) + 1
        print(f"\n📦 Batch {batch_num}/{total_batches} ({len(batch)} URL(s))")
        items = run_posts_batch(client, batch, args.max_posts, since=args.since, before=args.before)
        all_items.extend(items)
        print(f"   Acumulado: {len(all_items)} items")
        if i + args.batch_size < len(page_urls):
            time.sleep(3)

    rows = []
    seen_urls = set()

    for item in all_items:
        row = normalize_post_item(item)
        if not row.get("post_url"):
            continue
        if row["post_url"] in seen_urls:
            continue
        dt = parse_item_datetime(item)
        if not in_date_range(dt, args.since, args.before):
            continue
        seen_urls.add(row["post_url"])
        rows.append(row)

    rows.sort(key=lambda x: (x.get("fecha_post") or ""), reverse=True)
    df_posts = pd.DataFrame(rows, columns=[
        "post_url",
        "page_url",
        "page_handle",
        "autor",
        "fecha_post",
        "fecha_post_date",
        "post_texto",
        "num_comentarios_post",
        "reacciones_post",
    ])

    # Preparar salida
    since_label = args.since or "sin_inicio"
    before_label = args.before or "sin_fin"
    report_tag = build_report_tag(since_label, "Facebook")
    output_dir = os.path.join(args.output_dir, report_tag)
    os.makedirs(output_dir, exist_ok=True)

    # Nombre simplificado: [tag]_posts.csv
    csv_path = os.path.join(output_dir, f"{report_tag}_posts.csv")
    txt_path = os.path.join(output_dir, f"{report_tag}_posts.txt")

    df_posts.to_csv(csv_path, index=False, encoding="utf-8-sig")
    with open(txt_path, "w", encoding="utf-8") as f:
        for text in df_posts["post_texto"].fillna("").astype(str).tolist():
            clean = re.sub(r"\s+", " ", text).strip()
            if clean:
                f.write(clean + "\n")

    print("\n" + "=" * 70)
    print("✅ EXTRACCIÓN COMPLETADA")
    print("=" * 70)
    print(f"Posts raw del actor: {len(all_items)}")
    print(f"Posts finales: {len(df_posts)}")
    print(f"CSV: {csv_path}")
    print(f"TXT: {txt_path}")
    print("\n⚠️ IMPORTANTE: Este extractor SOLO descarga posts (sin comentarios).")
    print("Para comentarios, usa: 5_extractors_facebook_comentarios.py")


if __name__ == "__main__":
    main()
