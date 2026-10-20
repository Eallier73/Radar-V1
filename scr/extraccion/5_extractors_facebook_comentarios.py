#!/usr/bin/env python3
r"""
╔═══════════════════════════════════════════════════════════════════════════╗
║                                                                           ║
║   💬 EXTRACTOR DE COMENTARIOS FACEBOOK VÍA APIFY                         ║
║                                                                           ║
║   Descarga comentarios de posts usando CSV con columna post_url/url:    ║
║   (normalmente generado por 4_extractors_facebook_posts.py)             ║
║                                                                           ║
║   ⚠️  REQUERIDO: --input-csv (no descarga posts)                         ║
║                                                                           ║
║   Uso:                                                                   ║
║   python 5_extractors_facebook_comentarios.py \\                         ║
║     --input-csv ./Facebook/2026-03-01_Facebook/2026-03-01_posts.csv \\  ║
║     --since 2026-03-01 --before 2026-03-12 \\                            ║
║     --output-dir ./Facebook \\                                            ║
║     --max-comments 200                                                   ║
║                                                                           ║
║   Output: YYYY-MM-DD_Facebook/YYYY-MM-DD_comentarios.csv                ║
║                                                                           ║
║   Requisitos: pip install apify-client pandas                            ║
║                                                                           ║
╚═══════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import argparse
import csv
import html
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_DIR = REPO_ROOT / "scr" / "compartido"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from output_naming import (
    build_prefixed_name,
    build_report_tag,
    build_source_filename,
    build_week_folder_name,
)
from facebook_data_contract import (
    FACEBOOK_RAW_COLUMNS,
    account_from_url,
    canonicalize_facebook_rows,
    normalize_account,
    normalize_facebook_comment_url,
    normalize_facebook_url,
)
from radar_paths import EXTRACTED_DATA_DIR


ACTOR_COMMENTS = "apify/facebook-comments-scraper"
DEFAULT_OUTPUT_BASE_DIR = str(EXTRACTED_DATA_DIR)
DEFAULT_URLS_BASE_DIR = str(EXTRACTED_DATA_DIR)
DEFAULT_PAGES = ["TampicoGob", "monicavtampico"]


# ============================================================================
# LECTURA DE URLs
# ============================================================================

def leer_urls_csv(input_csv: str, pages: Optional[List[str]] = None) -> List[str]:
    """Lee URLs del CSV generado por facebook_scraper_unified.py (Fase 1)."""
    if not os.path.exists(input_csv):
        raise FileNotFoundError(f"No existe: {input_csv}")

    urls = []
    vistas = set()
    pages_l = {p.strip().lower() for p in (pages or []) if p.strip()}

    with open(input_csv, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        campos = [str(field or "").strip().lstrip("\ufeff") for field in (reader.fieldnames or [])]
        reader.fieldnames = campos

        # Soportar tanto "url" como "post_url"
        col_url = None
        for candidato in ["url", "post_url", "URL", "link"]:
            if candidato in campos:
                col_url = candidato
                break

        if col_url is None:
            raise ValueError(
                f"CSV sin columna de URL reconocida. Columnas: {campos}"
            )

        for row in reader:
            raw = (row.get(col_url) or "").strip()
            if not raw or raw in vistas:
                continue
            if "facebook.com" not in raw.lower():
                continue

            if pages_l:
                page_handle = (row.get("page_handle") or "").strip().lower()
                if page_handle:
                    if page_handle not in pages_l:
                        continue
                else:
                    raw_l = raw.lower()
                    if not any(f"/{p}/" in raw_l for p in pages_l):
                        continue

            vistas.add(raw)
            urls.append(raw)

    return urls


def inferir_rango_desde_input_csv(input_csv: str) -> tuple[Optional[str], Optional[str]]:
    base = os.path.basename(input_csv)
    match = re.search(r"(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})", base)
    if not match:
        return None, None
    return match.group(1), match.group(2)


def encontrar_csv_urls_mas_reciente(base_dir: str) -> Optional[str]:
    candidatos: list[tuple[float, str]] = []
    for root, _, files in os.walk(base_dir):
        for name in files:
            if not name.startswith("urls_") or not name.endswith(".csv"):
                continue
            path = os.path.join(root, name)
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            candidatos.append((mtime, path))
    if not candidatos:
        return None
    candidatos.sort(reverse=True)
    return candidatos[0][1]


def encontrar_csv_urls_en_semana(base_dir: str, since_label: str, before_label: str) -> Optional[str]:
    semana_dir = os.path.join(base_dir, build_report_tag(since_label, "Facebook"))
    if not os.path.isdir(semana_dir):
        return None
    return encontrar_csv_urls_mas_reciente(semana_dir)


def encontrar_csv_urls_por_filtros(
    base_dir: str,
    pages: Optional[List[str]],
    since_label: Optional[str],
    before_label: Optional[str],
) -> Optional[str]:
    """
    Busca CSV de URLs priorizando semana y páginas, luego cae a opciones más amplias.
    """
    safe_pages = "_".join(p.strip() for p in (pages or []) if p.strip()).replace("/", "_")
    candidatos: list[tuple[float, str]] = []

    roots = []
    if since_label and before_label:
        roots.append(os.path.join(base_dir, build_report_tag(since_label, "Facebook")))
    roots.append(base_dir)

    for root in roots:
        if not os.path.isdir(root):
            continue
        for current_root, _, files in os.walk(root):
            for name in files:
                if not name.startswith("urls_") or not name.endswith(".csv"):
                    continue
                if safe_pages and safe_pages not in name:
                    continue
                path = os.path.join(current_root, name)
                try:
                    mtime = os.path.getmtime(path)
                except OSError:
                    continue
                candidatos.append((mtime, path))

    if not candidatos:
        return None

    candidatos.sort(reverse=True)
    return candidatos[0][1]


def build_output_variant_name(input_csv: str, report_tag: str, kind: str) -> str:
    stem = Path(input_csv).stem.strip()
    if not stem:
        return build_prefixed_name(kind, report_tag)

    variant = stem
    for removable_prefix in ("urls_", "posts_", "comentarios_", "posts_comentarios_"):
        if variant.startswith(removable_prefix):
            variant = variant[len(removable_prefix):]
            break

    if variant.startswith(f"{report_tag}_"):
        variant = variant[len(report_tag) + 1 :]
    elif variant == report_tag:
        variant = ""

    for repeated_prefix in ("posts_comentarios_", "posts_", "comentarios_"):
        if variant.startswith(repeated_prefix):
            variant = variant[len(repeated_prefix):]
            break

    for removable_suffix in ("_posts", "_comentarios", "_posts_comentarios"):
        if variant.endswith(removable_suffix):
            variant = variant[: -len(removable_suffix)]
            break

    if variant in {"posts", "comentarios", "posts_comentarios"}:
        variant = ""

    variant = variant.strip("_")
    base_name = kind if not variant else f"{kind}_{variant}"
    return build_prefixed_name(base_name, report_tag)


def build_pipeline_dataset_name(input_csv: str, report_tag: str, kind: str) -> str:
    stem = Path(input_csv).stem.strip()
    if not stem:
        return f"{kind}_{report_tag}"

    base_name = stem
    for removable_prefix in ("urls_", "posts_", "comentarios_", "posts_comentarios_"):
        if base_name.startswith(removable_prefix):
            base_name = base_name[len(removable_prefix):]
            break

    if not base_name:
        base_name = report_tag
    elif not base_name.startswith(report_tag):
        base_name = f"{report_tag}_{base_name}"

    return f"{kind}_{base_name}"


# ============================================================================
# OBTENER COMENTARIOS
# ============================================================================

def obtener_comentarios_batch(
    client: ApifyClient,
    post_urls: List[str],
    max_comments: int,
    since: Optional[str] = None,
) -> list:
    """Corre facebook-comments-scraper para un batch de URLs y retorna items crudos."""

    start_urls = [{"url": url} for url in post_urls]

    run_input = {
        "startUrls": start_urls,
        "resultsLimit": max_comments,
        "includeNestedComments": True,
        "viewOption": "RECENT_ACTIVITY",
    }
    if since:
        run_input["onlyCommentsNewerThan"] = since

    try:
        run = client.actor(ACTOR_COMMENTS).call(run_input=run_input)
    except Exception as e:
        print(f"     ❌ Error al correr actor: {e}")
        return []

    if run is None:
        print("     ❌ El actor no retornó resultado.")
        return []

    status = run.get("status", "UNKNOWN")
    costo = run.get("usageTotalUsd", 0)
    print(f"     Status: {status} | Costo: ${costo:.4f} USD")

    dataset_id = run.get("defaultDatasetId")
    if not dataset_id:
        print("     ❌ Sin dataset.")
        return []

    items = list(client.dataset(dataset_id).iterate_items())
    print(f"     ✅ {len(items)} items")
    return items


def _parse_comment_datetime(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000.0
        try:
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    raw = str(value).strip()
    if not raw:
        return None
    if raw.isdigit():
        return _parse_comment_datetime(int(raw))
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def procesar_items_comentarios(
    items: list,
    since: Optional[str] = None,
    before: Optional[str] = None,
) -> List[dict]:
    """Extrae campos relevantes de los items del actor."""
    filas = []
    vistos = set()

    for item in items:
        texto = (
            item.get("text")
            or item.get("commentText")
            or item.get("body")
            or ""
        ).strip()

        if not texto:
            continue

        # Priorizar la identidad del comentario; el texto solo es fallback.
        post_url = item.get("postUrl") or item.get("facebookUrl") or ""
        comment_url = item.get("commentUrl") or item.get("url") or ""
        comment_id = item.get("id") or item.get("commentId") or ""
        author = (
            item.get("profileName")
            or item.get("authorName")
            or item.get("userName")
            or ""
        )
        raw_comment_date = (
            item.get("date")
            or item.get("timestamp")
            or item.get("commentDate")
            or ""
        )
        parsed_date = _parse_comment_datetime(raw_comment_date)
        if since or before:
            if parsed_date is None:
                continue
            start = datetime.strptime(since, "%Y-%m-%d").replace(tzinfo=timezone.utc) if since else None
            end = (
                datetime.strptime(before, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                + timedelta(days=1)
                if before
                else None
            )
            if start and parsed_date < start:
                continue
            if end and parsed_date >= end:
                continue
        comment_date = parsed_date.isoformat() if parsed_date else str(raw_comment_date).strip()
        if normalize_facebook_comment_url(comment_url) == normalize_facebook_url(post_url):
            comment_url = ""
        clave = (
            ("id", str(comment_id).strip())
            if str(comment_id).strip()
            else ("url", str(comment_url).strip())
            if str(comment_url).strip()
            else ("fallback",) + tuple(
                str(value or "").strip()
                for value in (post_url, author, comment_date, texto)
            )
        )
        if clave in vistos:
            continue
        vistos.add(clave)

        fila = {
            "post_url": post_url,
            "comentario_texto": texto,
            "autor": author,
            "fecha_comentario": comment_date,
            "likes_comentario": (
                item.get("likesCount")
                or item.get("likes")
                or item.get("reactionsCount")
                or 0
            ),
            "es_respuesta": item.get("isReply", False),
            "url_comentario": comment_url,
            "comentario_id": comment_id,
        }
        filas.append(fila)

    return filas


def extraer_texto_post_desde_item(item: dict) -> str:
    """
    Intenta recuperar el texto del post desde diferentes campos posibles del actor.
    """
    candidatos = [
        item.get("postText"),
        item.get("postMessage"),
        item.get("postDescription"),
        item.get("postContent"),
        item.get("postCaption"),
        item.get("message"),
        item.get("description"),
    ]

    post_obj = item.get("post")
    if isinstance(post_obj, dict):
        candidatos.extend([
            post_obj.get("text"),
            post_obj.get("message"),
            post_obj.get("description"),
        ])

    for c in candidatos:
        if isinstance(c, str):
            txt = c.strip()
            if len(txt) >= 5:
                return txt
    return ""


def _limpiar_texto_post(texto: str) -> str:
    texto = html.unescape(texto or "")
    texto = re.sub(r"\s+", " ", texto).strip()
    texto = texto.strip(" -|")
    return texto


def _es_texto_generico_facebook(texto: str) -> bool:
    t = (texto or "").lower()
    if len(t) < 5:
        return True
    patrones = [
        "log into facebook",
        "inicia sesión en facebook",
        "facebook te ayuda",
        "create new account",
        "forgot account",
        "join facebook",
        "meta",
    ]
    return any(p in t for p in patrones)


def _extraer_meta_content(html_text: str, key: str) -> str:
    patrones = [
        rf'<meta[^>]+property=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']+)["\']',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']{re.escape(key)}["\']',
        rf'<meta[^>]+name=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']+)["\']',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']{re.escape(key)}["\']',
    ]
    for patron in patrones:
        m = re.search(patron, html_text, flags=re.IGNORECASE)
        if m:
            return _limpiar_texto_post(m.group(1))
    return ""


def _variantes_url_post(url: str) -> List[str]:
    variantes = [url]
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if host.startswith("www.facebook.com"):
            variantes.append(urlunparse((parsed.scheme, "m.facebook.com", parsed.path, parsed.params, parsed.query, parsed.fragment)))
            variantes.append(urlunparse((parsed.scheme, "mbasic.facebook.com", parsed.path, parsed.params, parsed.query, parsed.fragment)))
        elif host.startswith("facebook.com"):
            variantes.append(urlunparse((parsed.scheme, "m.facebook.com", parsed.path, parsed.params, parsed.query, parsed.fragment)))
            variantes.append(urlunparse((parsed.scheme, "mbasic.facebook.com", parsed.path, parsed.params, parsed.query, parsed.fragment)))
    except Exception:
        pass

    vistas = set()
    out = []
    for v in variantes:
        if v not in vistas:
            vistas.add(v)
            out.append(v)
    return out


def extraer_texto_post_desde_url(url: str, timeout: int = 20) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
    }

    for target in _variantes_url_post(url):
        try:
            req = Request(target, headers=headers)
            with urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            html_text = raw.decode("utf-8", errors="ignore")
        except Exception:
            continue

        for key in ("og:description", "twitter:description", "description", "og:title"):
            cand = _extraer_meta_content(html_text, key)
            if cand and not _es_texto_generico_facebook(cand):
                return cand

    return ""


def procesar_items_posts(items: list, urls_batch: List[str]) -> List[dict]:
    """
    Arma filas de POST a partir de items del actor y completa faltantes con las URLs del batch.
    """
    por_post: dict[str, dict] = {}

    for item in items:
        post_url = (
            item.get("postUrl")
            or item.get("facebookUrl")
            or item.get("postURL")
            or ""
        ).strip()
        if not post_url:
            continue

        texto = extraer_texto_post_desde_item(item)
        fecha_post = (
            item.get("postDate")
            or item.get("postTimestamp")
            or item.get("date")
            or item.get("timestamp")
            or ""
        )
        num_comentarios = (
            item.get("commentsCount")
            or item.get("numComments")
            or item.get("comments")
            or ""
        )

        actual = por_post.get(post_url)
        if not actual:
            por_post[post_url] = {
                "post_url": post_url,
                "post_texto": texto,
                "fecha_post": fecha_post,
                "num_comentarios_post": num_comentarios,
            }
            continue

        # Priorizar el texto más informativo si llegan múltiples items del mismo post.
        if len(texto) > len(actual.get("post_texto") or ""):
            actual["post_texto"] = texto
        if not actual.get("fecha_post") and fecha_post:
            actual["fecha_post"] = fecha_post
        if not actual.get("num_comentarios_post") and num_comentarios:
            actual["num_comentarios_post"] = num_comentarios

    for url in urls_batch:
        if url not in por_post:
            por_post[url] = {
                "post_url": url,
                "post_texto": "",
                "fecha_post": "",
                "num_comentarios_post": "",
            }

    return list(por_post.values())


# ============================================================================
# PIPELINE PRINCIPAL
# ============================================================================

def run_pipeline(
    client,
    urls: List[str],
    max_comments: int,
    since: Optional[str],
    output_dir: str,
    input_csv: str,
    batch_size: int,
    modo: str,
):
    if modo != "ambos":
        raise ValueError("Radar requiere modo 'ambos' para generar un único CSV combinado.")
    want_posts = modo in {"posts", "ambos"}
    want_comments = modo in {"comentarios", "ambos"}
    max_comments_eff = max_comments if want_comments else 0
    if want_comments and client is None:
        raise ValueError("Modo con comentarios requiere cliente Apify inicializado.")

    print(f"\n  📥 URLs cargadas: {len(urls)}")
    print(f"  🧩 Modo: {modo}")
    print(f"  💬 Máx comentarios por post: {max_comments_eff}")
    print(f"  📦 Batch size: {batch_size}")
    print(f"  📅 Desde: {since or 'sin filtro'}")

    todas_las_filas_comentarios = []
    posts_por_url: dict[str, dict] = {}
    if want_comments:
        total_batches = (len(urls) + batch_size - 1) // batch_size

        for i in range(0, len(urls), batch_size):
            batch = urls[i:i + batch_size]
            batch_num = (i // batch_size) + 1

            print(f"\n  ─── Batch {batch_num}/{total_batches} "
                  f"({len(batch)} posts) ───")

            items = obtener_comentarios_batch(client, batch, max_comments_eff, since)

            filas = procesar_items_comentarios(items)
            todas_las_filas_comentarios.extend(filas)
            print(f"     📊 Acumulado comentarios: {len(todas_las_filas_comentarios)}")

            if want_posts:
                posts_batch = procesar_items_posts(items, batch)
                for post in posts_batch:
                    post_url = post.get("post_url", "")
                    if not post_url:
                        continue
                    actual = posts_por_url.get(post_url)
                    if not actual:
                        posts_por_url[post_url] = post
                        continue
                    if len(post.get("post_texto") or "") > len(actual.get("post_texto") or ""):
                        actual["post_texto"] = post.get("post_texto", "")
                    if not actual.get("fecha_post") and post.get("fecha_post"):
                        actual["fecha_post"] = post["fecha_post"]
                    if not actual.get("num_comentarios_post") and post.get("num_comentarios_post"):
                        actual["num_comentarios_post"] = post["num_comentarios_post"]

            # Pausa entre batches
            if i + batch_size < len(urls):
                pausa = 5
                print(f"     ⏸️  Pausa {pausa}s...")
                time.sleep(pausa)
    elif want_posts:
        print("  💸 Modo posts: no se ejecuta actor de comentarios (sin costo Apify para esta parte).")

    if want_posts:
        # Asegurar que todos los posts tengan registro.
        for url in urls:
            if url not in posts_por_url:
                posts_por_url[url] = {
                    "post_url": url,
                    "post_texto": "",
                    "fecha_post": "",
                    "num_comentarios_post": "",
                }

        faltantes = [u for u in urls if len((posts_por_url.get(u, {}).get("post_texto") or "").strip()) < 5]
        if faltantes:
            print(f"\n  🧾 Extrayendo texto de post directo desde URL para {len(faltantes)} posts...")
            for idx, url in enumerate(faltantes, 1):
                texto = extraer_texto_post_desde_url(url)
                if texto:
                    posts_por_url[url]["post_texto"] = texto
                if idx % 10 == 0 or idx == len(faltantes):
                    print(f"     Progreso texto post: {idx}/{len(faltantes)}")

    # ── Guardar CSVs ──
    os.makedirs(output_dir, exist_ok=True)

    # Conservar un posible calificador del CSV de entrada para distinguir subsets.
    report_tag = os.path.basename(os.path.normpath(output_dir))

    csv_mixto = None

    columnas_posts = ["post_url", "post_texto", "fecha_post", "num_comentarios_post"]
    columnas_comentarios = [
        "post_url",
        "comentario_texto",
        "autor",
        "fecha_comentario",
        "likes_comentario",
        "es_respuesta",
        "url_comentario",
    ]

    if want_posts:
        filas_posts = []
        for url in urls:
            filas_posts.append(posts_por_url.get(url, {
                "post_url": url,
                "post_texto": "",
                "fecha_post": "",
                "num_comentarios_post": "",
            }))
        df_posts = pd.DataFrame(filas_posts, columns=columnas_posts)
    else:
        df_posts = pd.DataFrame(columns=columnas_posts)

    if want_comments:
        df_comments = pd.DataFrame(todas_las_filas_comentarios, columns=columnas_comentarios)
    else:
        df_comments = pd.DataFrame(columns=columnas_comentarios)

    if want_posts and want_comments:
        filas_mixtas = []
        for _, row in df_posts.iterrows():
            post_url = row.get("post_url", "")
            filas_mixtas.append({
                "tipo": "POST",
                "cuenta": account_from_url(post_url),
                "url": post_url,
                "post_url_padre": "",
                "fecha": row.get("fecha_post", ""),
                "texto": row.get("post_texto", ""),
                "num_comentarios": row.get("num_comentarios_post", ""),
            })
        for _, row in df_comments.iterrows():
            post_url = row.get("post_url", "")
            filas_mixtas.append({
                "tipo": "COMENTARIO",
                "cuenta": account_from_url(post_url),
                "url": row.get("url_comentario", ""),
                "post_url_padre": row.get("post_url", ""),
                "fecha": row.get("fecha_comentario", ""),
                "texto": row.get("comentario_texto", ""),
                "num_comentarios": "",
            })

        csv_mixto = os.path.join(
            output_dir,
            f"{build_source_filename(report_tag, 'facebook')}.csv",
        )
        pd.DataFrame(filas_mixtas, columns=FACEBOOK_RAW_COLUMNS).to_csv(
            csv_mixto,
            index=False,
            encoding="utf-8-sig",
        )

    # ── Resumen ──
    print("\n" + "=" * 70)
    print("✅ DESCARGA COMPLETADA")
    print("=" * 70)
    print(f"  📊 Posts procesados:  {len(urls)}")
    if want_posts:
        print(f"  📝 Posts:             {len(df_posts)}")
        sin_texto = (df_posts["post_texto"].fillna("").str.len() < 5).sum()
        if sin_texto > 0:
            print(f"  ⚠️ Posts sin texto:    {sin_texto} (puede depender del actor/fuente)")
    if want_comments:
        print(f"  💬 Comentarios:       {len(df_comments)}")
    if csv_mixto:
        print(f"  📁 Facebook combinado: {csv_mixto}")

    if want_comments and not df_comments.empty:
        por_post = df_comments.groupby("post_url").size()
        print(f"  📈 Promedio por post: {por_post.mean():.1f}")
        print(f"  📈 Máximo en un post: {por_post.max()}")


# ============================================================================
# CLI
# ============================================================================

def valid_date(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as e:
        raise argparse.ArgumentTypeError(
            f"Fecha inválida '{value}', usa YYYY-MM-DD"
        ) from e
    return value


def valid_sampling_percent(value: str) -> float:
    try:
        pct = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Sampling inválido '{value}', usa un número entre 0 y 100."
        ) from exc

    if pct <= 0 or pct > 100:
        raise argparse.ArgumentTypeError(
            f"Sampling inválido '{value}', debe ser > 0 y <= 100."
        )
    return pct


def parse_pages_text(raw: str) -> List[str]:
    normalizado = raw.replace(",", " ").strip()
    return [p for p in normalizado.split() if p]


def _input_con_default(label: str, default: str) -> str:
    val = input(f"{label} [{default}]: ").strip()
    return val or default


def _input_int(label: str, default: Optional[int], minimo: int = 1) -> Optional[int]:
    suffix = f" [{default}]" if default is not None else " [vacío]"
    while True:
        raw = input(f"{label}{suffix}: ").strip()
        if not raw:
            return default
        try:
            n = int(raw)
            if n < minimo:
                print(f"   ⚠️ Debe ser >= {minimo}")
                continue
            return n
        except ValueError:
            print("   ⚠️ Ingresa un entero válido.")


def _input_float(
    label: str,
    default: Optional[float],
    minimo: float = 0.01,
    maximo: float = 100.0,
) -> Optional[float]:
    suffix = f" [{default}]" if default is not None else " [vacío]"
    while True:
        raw = input(f"{label}{suffix}: ").strip()
        if not raw:
            return default
        try:
            n = float(raw)
            if n < minimo or n > maximo:
                print(f"   ⚠️ Debe estar entre {minimo} y {maximo}.")
                continue
            return n
        except ValueError:
            print("   ⚠️ Ingresa un número válido.")


def _input_date(label: str, default: str) -> str:
    while True:
        value = _input_con_default(label, default)
        try:
            valid_date(value)
            return value
        except argparse.ArgumentTypeError:
            print("   ⚠️ Formato inválido. Usa YYYY-MM-DD.")


def ejecutar_prompt_interactivo(args: argparse.Namespace) -> argparse.Namespace:
    print("\n" + "=" * 70)
    print("🧭 MODO INTERACTIVO - EXTRACTOR APIFY")
    print("=" * 70)
    print("Elige qué bajar y con qué filtros.\n")

    modo_in = _input_con_default(
        "Modo (posts/comentarios/ambos)",
        args.modo,
    ).lower()
    if modo_in in {"post", "p"}:
        modo_in = "posts"
    if modo_in in {"comentario", "c"}:
        modo_in = "comentarios"
    if modo_in not in {"posts", "comentarios", "ambos"}:
        print("   ⚠️ Modo inválido; se usa 'ambos'.")
        modo_in = "ambos"
    args.modo = modo_in

    default_pages = " ".join(args.pages or DEFAULT_PAGES)
    pages_raw = _input_con_default("Páginas (separadas por espacio o coma)", default_pages)
    args.pages = parse_pages_text(pages_raw)

    today = datetime.now().date()
    since_default = args.since or (today - timedelta(days=7)).strftime("%Y-%m-%d")
    before_default = args.before or today.strftime("%Y-%m-%d")

    args.since = _input_date("Fecha desde (YYYY-MM-DD)", since_default)
    args.before = _input_date("Fecha hasta (YYYY-MM-DD)", before_default)

    csv_raw = input(
        f"Ruta CSV URLs (ENTER = auto en {DEFAULT_URLS_BASE_DIR}): "
    ).strip()
    args.input_csv = csv_raw or None

    args.max_comments = _input_int("Máx comentarios por post", args.max_comments, minimo=1) or 200
    args.max_urls = _input_int("Máx URLs (vacío = todas)", args.max_urls, minimo=1)
    args.sample_percent = _input_float(
        "Sampling URLs Facebook (%) (vacío = sin sampling)",
        args.sample_percent,
        minimo=0.01,
        maximo=100.0,
    )
    if args.sample_percent is not None:
        args.sample_seed = _input_int("Semilla sampling", args.sample_seed, minimo=0) or 42
    args.batch_size = _input_int("Batch size", args.batch_size, minimo=1) or 25

    output_raw = input(
        f"Directorio base salida [{args.output_dir}]: "
    ).strip()
    if output_raw:
        args.output_dir = output_raw

    if args.modo in {"comentarios", "ambos"} and not (args.token or os.environ.get("APIFY_TOKEN")):
        token_raw = input("APIFY token (ENTER si ya está en APIFY_TOKEN): ").strip()
        if token_raw:
            args.token = token_raw

    return args


def parse_args():
    parser = argparse.ArgumentParser(
        description="Baja SOLO comentarios de Facebook vía Apify desde CSV con post_url/url",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Uso:

  1) Generar posts (usar extractor 5):
      python 4_extractors_facebook_posts.py \
    --pages GobiernoCDMX ClaraBrugadaM \\
       --since 2026-03-01 --before 2026-03-12 \\
       --output-dir ./Facebook

  2) Bajar comentarios:
     python 5_extractors_facebook_comentarios.py \\
       --input-csv ./Facebook/2026-03-01_Facebook/2026-03-01_posts.csv \
       --since 2026-03-01 --before 2026-03-12 \\
       --output-dir ./Facebook \\
       --max-comments 200
        """,
    )

    parser.add_argument("--input-csv", required=True,
                        help="CSV con URLs de posts (por ejemplo, generado por 4_extractors_facebook_posts.py)")
    parser.add_argument("--max-comments", type=int, default=200,
                        help="Máximo de comentarios por post (default: 200)")
    parser.add_argument("--max-urls", type=int, default=None,
                        help="Limitar número de URLs a procesar")
    parser.add_argument("--sample-percent", type=valid_sampling_percent, default=None,
                        help="Sampling aleatorio de URLs en porcentaje (0-100)")
    parser.add_argument("--sample-seed", type=int, default=42,
                        help="Semilla para muestreo aleatorio de URLs (default: 42)")
    parser.add_argument("--since", required=True, type=valid_date,
                        help="Fecha inicio YYYY-MM-DD (heredada del orquestador)")
    parser.add_argument("--before", required=True, type=valid_date,
                        help="Fecha fin YYYY-MM-DD (heredada del orquestador)")
    parser.add_argument("--batch-size", type=int, default=25,
                        help="URLs por batch (default: 25)")
    parser.add_argument("--token", default=None,
                        help="Apify API token (o variable APIFY_TOKEN)")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_BASE_DIR,
                        help="Directorio base de salida. Default: %(default)s")
    parser.add_argument("--prompt", action="store_true",
                        help="Fuerza modo interactivo (preguntas en consola)")
    parser.add_argument("--no-prompt", action="store_true",
                        help="Desactiva preguntas interactivas y usa solo CLI")

    return parser.parse_args()


def construir_facebook_canonico(input_csv: str, df_comentarios: pd.DataFrame) -> pd.DataFrame:
    """Combina el CSV intermedio de posts y los comentarios en un solo dataset."""
    df_posts = pd.read_csv(input_csv, encoding="utf-8-sig").fillna("")
    filas = []
    cuentas_por_post: dict[str, str] = {}
    for _, row in df_posts.iterrows():
        post_url = row.get("post_url", row.get("url", ""))
        cuenta = (
            account_from_url(row.get("page_url", ""))
            or account_from_url(post_url)
            or normalize_account(row.get("page_handle", row.get("cuenta", "")))
        )
        if post_url and cuenta:
            cuentas_por_post[str(post_url)] = cuenta
        filas.append({
            "tipo": "POST",
            "cuenta": cuenta,
            "url": post_url,
            "post_url_padre": "",
            "fecha": row.get("fecha_post", row.get("fecha", "")),
            "texto": row.get("post_texto", row.get("texto", "")),
            "num_comentarios": row.get(
                "num_comentarios_post",
                row.get("num_comentarios", ""),
            ),
        })

    for _, row in df_comentarios.fillna("").iterrows():
        post_url = row.get("post_url", "")
        filas.append({
            "tipo": "COMENTARIO",
            "cuenta": cuentas_por_post.get(str(post_url), "") or account_from_url(post_url),
            "url": row.get("url_comentario", ""),
            "post_url_padre": post_url,
            "fecha": row.get("fecha_comentario", ""),
            "texto": row.get("comentario_texto", ""),
            "num_comentarios": "",
        })

    return pd.DataFrame(filas, columns=FACEBOOK_RAW_COLUMNS)


def main():
    """Ejecuta descarga de SOLO comentarios desde CSV de URLs."""
    args = parse_args()

    since_dt = datetime.strptime(args.since, "%Y-%m-%d")
    before_dt = datetime.strptime(args.before, "%Y-%m-%d")
    if since_dt > before_dt:
        print("❌ --since no puede ser posterior a --before.")
        sys.exit(1)

    # Validar token
    token = args.token or os.environ.get("APIFY_TOKEN")
    if not token:
        print("❌ Necesitas APIFY_TOKEN o --token para ejecutar el actor.")
        print("   export APIFY_TOKEN='tu_token'")
        print("   o --token tu_token")
        print("   → https://console.apify.com/settings/integrations")
        sys.exit(1)

    try:
        from apify_client import ApifyClient
    except ImportError:
        print("❌ Falta dependencia: apify-client")
        print("   Instala con: pip install apify-client pandas")
        sys.exit(1)

    client = ApifyClient(token)

    # Input CSV (REQUERIDO)
    input_csv = args.input_csv
    if not input_csv:
        print("❌ --input-csv es REQUERIDO.")
        print("   Debe contener columna post_url/url (ej. generado por 4_extractors_facebook_posts.py)")
        sys.exit(1)

    # Leer URLs desde CSV
    try:
        urls = leer_urls_csv(input_csv)
    except (FileNotFoundError, ValueError) as e:
        print(f"❌ Error leyendo CSV: {e}")
        sys.exit(1)

    if not urls:
        print("❌ No se encontraron URLs válidas en el CSV.")
        sys.exit(1)

    # Aplicar sampling si se especifica
    if args.sample_percent is not None and args.sample_percent < 100:
        original_count = len(urls)
        sample_size = max(1, round(original_count * (args.sample_percent / 100.0)))
        if sample_size < len(urls):
            random.seed(args.sample_seed)
            urls = random.sample(urls, sample_size)
            print(f"🎲 Sampling URLs: {args.sample_percent:.2f}% ({sample_size}/{original_count})")

    # Limitar URLs si se especifica
    if args.max_urls and len(urls) > args.max_urls:
        urls = urls[:args.max_urls]
        print(f"✂️  Limitado a {args.max_urls} URLs")

    # Preparar directorio de salida
    week_name = build_week_folder_name(since_dt, before_dt)
    output_dir = os.path.join(args.output_dir, week_name)
    os.makedirs(output_dir, exist_ok=True)

    print("\n" + "=" * 70)
    print("💬 EXTRACTOR DE COMENTARIOS FACEBOOK VÍA APIFY")
    print("=" * 70)
    print(f"URLs a procesar: {len(urls)}")
    print(f"Máx comentarios por post: {args.max_comments}")
    print(f"Batch size: {args.batch_size}")

    # Procesar URLs en batches
    all_comments = []
    total_batches = (len(urls) + args.batch_size - 1) // args.batch_size
    
    for i in range(0, len(urls), args.batch_size):
        batch = urls[i:i + args.batch_size]
        batch_num = (i // args.batch_size) + 1
        print(f"\n📦 Batch {batch_num}/{total_batches} ({len(batch)} URL(s))")
        
        items = obtener_comentarios_batch(
            client=client,
            post_urls=batch,
            max_comments=args.max_comments,
            since=args.since,
        )
        
        comentarios = procesar_items_comentarios(
            items,
            since=args.since,
            before=args.before,
        )
        all_comments.extend(comentarios)
        print(f"   Acumulado comentarios: {len(all_comments)}")
        
        if i + args.batch_size < len(urls):
            time.sleep(3)

    # Crear DataFrame y guardar
    df_comentarios = pd.DataFrame(all_comments)

    canonical_name = build_source_filename(week_name, "facebook")
    csv_path = os.path.join(output_dir, f"{canonical_name}.csv")
    df_canonico = construir_facebook_canonico(input_csv, df_comentarios)
    canonical_rows, counters = canonicalize_facebook_rows(
        df_canonico.fillna("").to_dict(orient="records"),
        schema="canonical",
        week_start=since_dt.replace(tzinfo=timezone.utc),
        week_before=(before_dt + timedelta(days=1)).replace(tzinfo=timezone.utc),
    )
    df_canonico = pd.DataFrame(canonical_rows, columns=FACEBOOK_RAW_COLUMNS)
    df_canonico.to_csv(csv_path, index=False, encoding="utf-8-sig")

    input_path = Path(input_csv).resolve()
    if (
        input_path.parent == Path(output_dir).resolve()
        and input_path.name.endswith("_facebook_posts.csv")
        and input_path != Path(csv_path).resolve()
    ):
        input_path.unlink()

    print("\n" + "=" * 70)
    print("✅ EXTRACCIÓN COMPLETADA")
    print("=" * 70)
    print(f"Comentarios descargados: {len(all_comments)}")
    print(f"Registros canónicos: {len(df_canonico)} | Excluidos por contrato: {counters['read'] - counters['kept']}")
    print(f"CSV combinado: {csv_path}")


if __name__ == "__main__":
    main()
