"""
=============================================================
 BUSCADOR DE NOTICIAS — Google News RSS + trafilatura
=============================================================
Uso:
    python 07_medios_extractor_rss.py

Dependencias:
    pip install trafilatura pandas requests cloudscraper googlenewsdecoder playwright
    playwright install chromium
    
    (googlenewsdecoder es opcional pero recomendado como fallback)
=============================================================
Versión adaptada: usa Google News RSS (gratuito, sin API key)
en lugar de SerpAPI.

Incluye Playwright como estrategia de descarga para sitios
que requieren JavaScript rendering.
=============================================================
"""

# ============================================================
# CONFIGURACIÓN — solo edita esta sección
# ============================================================
UNIFORM_MEDIA_SITES = (
    "site:oem.com.mx",
    "site:milenio.com",
)
MEDIOS = list(UNIFORM_MEDIA_SITES)

UNIFORM_SEARCH_TERMS = (
    '"Monica Villarreal"',
    '"gobierno de tampico"',
    '"tampico"',
)
TERMINOS = list(UNIFORM_SEARCH_TERMS)

ANIO_INICIO = 2025
MES_INICIO = 1
FECHA_INICIO_EXACTA = "2026-03-06"   # None => usa primer_lunes_del_mes(ANIO_INICIO, MES_INICIO)
FECHA_FIN_EXACTA = "2026-03-13"      # None => hoy
MODO_QUERIES = "combinado"            # "compacto" o "combinado"

# --- RSS settings ---
RSS_MAX_REINTENTOS = 3
RSS_BACKOFF_INICIAL = 5.0
RSS_BACKOFF_MAX = 60.0
RSS_TIMEOUT = 30
RSS_USAR_CACHE_LOCAL = True
NOMBRE_CARPETA_CACHE_RSS = "_cache_rss"

# --- URL decoder settings ---
DECODER_PAUSA_ENTRE_URLS = 1.5       # segundos entre decodificaciones (evitar 429)
DECODER_MAX_REINTENTOS = 2

# --- Playwright settings ---
PLAYWRIGHT_TIMEOUT = 25000            # ms — timeout para navegación
PLAYWRIGHT_WAIT_AFTER_LOAD = 2000     # ms — espera extra tras load para JS dinámico
PLAYWRIGHT_MAX_PAGINAS_ABIERTAS = 1   # páginas simultáneas (1 = secuencial, conservador)
PLAYWRIGHT_HEADLESS = True            # False para debug visual
PLAYWRIGHT_PAUSA_ENTRE_PAGINAS = 1.5  # seg entre cada página (anti rate-limit)

# Dominios que requieren Playwright (JS rendering obligatorio).
# El script intentará primero trafilatura/cloudscraper/requests,
# y si fallan Y el dominio está en esta lista, usará Playwright.
# Si no está en la lista, Playwright se usa como último recurso universal.
DOMINIOS_PLAYWRIGHT_PRIORITARIO = [
    "noticiasdetampico.mx",
]

# --- General ---
OMITIR_SEMANAS_EXISTENTES = True
CARPETA_BASE_SEMANAL = None
NOMBRE_ARCHIVO_BASE = "medios"
PAUSA = 2.0            # segundos entre requests de trafilatura
PAUSA_ENTRE_QUERIES = 3.0   # segundos entre queries RSS (para no ser bloqueado)

# --- User-Agent rotativo para evitar bloqueos ---
USER_AGENTS = [
    "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
]
# ============================================================

import argparse
import base64
import hashlib
import json
import random
import re
import sys
import time
import unicodedata
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from urllib.parse import quote_plus, urlparse, parse_qs, unquote

try:
    import requests
except ImportError:
    requests = None

try:
    import cloudscraper
except ImportError:
    cloudscraper = None

try:
    import trafilatura
except ImportError:
    trafilatura = None

try:
    import pandas as pd
except ImportError:
    pd = None

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_DIR = REPO_ROOT / "scr" / "compartido"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from output_naming import build_source_filename, build_week_folder_name
from medios_data_contract import MEDIOS_OUTPUT_COLUMNS
from radar_paths import EXTRACTED_DATA_DIR

CARPETA_BASE_SEMANAL = str(EXTRACTED_DATA_DIR)

# Intentar importar googlenewsdecoder como fallback
TIENE_GNEWS_DECODER = False
try:
    from googlenewsdecoder import gnewsdecoder
    TIENE_GNEWS_DECODER = True
    print("✓ googlenewsdecoder disponible (se usará como fallback)")
except ImportError:
    print("⚠ googlenewsdecoder no instalado (pip install googlenewsdecoder)")
    print("  Se usará solo decodificación base64 directa")

# Intentar importar Playwright
TIENE_PLAYWRIGHT = False
_PLAYWRIGHT_CONTEXT = None   # se inicializa lazy
_PLAYWRIGHT_BROWSER = None
_PLAYWRIGHT_PW = None
try:
    from playwright.sync_api import sync_playwright
    TIENE_PLAYWRIGHT = True
    print("✓ playwright disponible (se usará para sitios con JS rendering)")
except ImportError:
    print("⚠ playwright no instalado (pip install playwright && playwright install chromium)")
    print("  Sitios con JS rendering pueden fallar en extracción de texto")

# Contadores globales
RSS_CALLS_REALES = 0
RSS_RESPUESTAS_CACHE = 0
URLS_DECODIFICADAS_OK = 0
URLS_DECODIFICADAS_FAIL = 0
PLAYWRIGHT_DESCARGAS_OK = 0
PLAYWRIGHT_DESCARGAS_FAIL = 0

# Scraper global para bypass de Cloudflare (Milenio, etc.)
SCRAPER = (
    cloudscraper.create_scraper(browser={'browser': 'firefox', 'platform': 'linux'})
    if cloudscraper is not None
    else None
)


def verificar_dependencias_ejecucion():
    faltantes = []
    if requests is None:
        faltantes.append("requests")
    if cloudscraper is None:
        faltantes.append("cloudscraper")
    if trafilatura is None:
        faltantes.append("trafilatura")
    if pd is None:
        faltantes.append("pandas")
    if faltantes:
        raise SystemExit(
            "❌ Faltan dependencias para ejecutar Medios: " + ", ".join(faltantes)
        )


# ============================================================
# PLAYWRIGHT — GESTIÓN DE BROWSER
# ============================================================
def _iniciar_playwright():
    """
    Inicializa Playwright de forma lazy (solo cuando se necesita).
    Mantiene un browser + context abierto para reusar entre páginas.
    """
    global _PLAYWRIGHT_PW, _PLAYWRIGHT_BROWSER, _PLAYWRIGHT_CONTEXT

    if _PLAYWRIGHT_CONTEXT is not None:
        return _PLAYWRIGHT_CONTEXT

    if not TIENE_PLAYWRIGHT:
        return None

    try:
        _PLAYWRIGHT_PW = sync_playwright().start()
        _PLAYWRIGHT_BROWSER = _PLAYWRIGHT_PW.chromium.launch(
            headless=PLAYWRIGHT_HEADLESS,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )
        _PLAYWRIGHT_CONTEXT = _PLAYWRIGHT_BROWSER.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1366, "height": 768},
            locale="es-MX",
            timezone_id="America/Mexico_City",
        )
        # Bloquear recursos pesados innecesarios para acelerar
        _PLAYWRIGHT_CONTEXT.route(
            "**/*.{png,jpg,jpeg,gif,webp,svg,ico,woff,woff2,ttf,eot,mp4,webm}",
            lambda route: route.abort(),
        )
        print("  ✓ Playwright browser iniciado")
        return _PLAYWRIGHT_CONTEXT
    except Exception as exc:
        print(f"  ⚠ Error iniciando Playwright: {exc}")
        return None


def _cerrar_playwright():
    """Cierra el browser de Playwright limpiamente."""
    global _PLAYWRIGHT_PW, _PLAYWRIGHT_BROWSER, _PLAYWRIGHT_CONTEXT
    try:
        if _PLAYWRIGHT_CONTEXT:
            _PLAYWRIGHT_CONTEXT.close()
        if _PLAYWRIGHT_BROWSER:
            _PLAYWRIGHT_BROWSER.close()
        if _PLAYWRIGHT_PW:
            _PLAYWRIGHT_PW.stop()
    except Exception:
        pass
    _PLAYWRIGHT_CONTEXT = None
    _PLAYWRIGHT_BROWSER = None
    _PLAYWRIGHT_PW = None


def _descargar_con_playwright(url):
    """
    Descarga una página usando Playwright (navegador real con JS).
    Retorna el texto extraído o "" si falla.
    """
    global PLAYWRIGHT_DESCARGAS_OK, PLAYWRIGHT_DESCARGAS_FAIL

    context = _iniciar_playwright()
    if context is None:
        PLAYWRIGHT_DESCARGAS_FAIL += 1
        return ""

    page = None
    try:
        page = context.new_page()

        # Navegar y esperar a que el DOM esté listo
        page.goto(url, wait_until="domcontentloaded", timeout=PLAYWRIGHT_TIMEOUT)

        # Espera extra para JS dinámico (React, Vue, etc.)
        page.wait_for_timeout(PLAYWRIGHT_WAIT_AFTER_LOAD)

        # Intentar esperar a que aparezca contenido de artículo
        # (selectores comunes en WordPress / sitios de noticias)
        selectores_articulo = [
            "article",
            ".entry-content",
            ".post-content",
            ".article-body",
            ".td-post-content",
            ".content-inner",
            "main",
        ]
        for sel in selectores_articulo:
            try:
                page.wait_for_selector(sel, timeout=3000)
                break
            except Exception:
                continue

        # Obtener HTML completo renderizado
        html = page.content()

        if not html or len(html) < 500:
            PLAYWRIGHT_DESCARGAS_FAIL += 1
            return ""

        # Verificar que no sea una página de bloqueo
        bloqueo = detectar_html_bloqueado(html)
        if bloqueo:
            PLAYWRIGHT_DESCARGAS_FAIL += 1
            return ""

        # Extraer texto con trafilatura (que ahora recibe HTML completo con JS)
        texto = trafilatura.extract(html, include_comments=False) or ""

        if not texto:
            texto = extraer_texto_basico_desde_html(html)

        # Fallback: extraer texto visible del DOM directamente
        if not texto:
            texto = _extraer_texto_dom_playwright(page, selectores_articulo)

        if texto and len(texto) >= 80:
            PLAYWRIGHT_DESCARGAS_OK += 1
            return texto

        PLAYWRIGHT_DESCARGAS_FAIL += 1
        return texto or ""

    except Exception as exc:
        PLAYWRIGHT_DESCARGAS_FAIL += 1
        return ""
    finally:
        if page:
            try:
                page.close()
            except Exception:
                pass


def _extraer_texto_dom_playwright(page, selectores):
    """
    Último recurso: extrae innerText directamente del DOM
    usando los selectores de artículo.
    """
    for sel in selectores:
        try:
            elem = page.query_selector(sel)
            if elem:
                texto = elem.inner_text()
                # Limpiar whitespace excesivo
                texto = re.sub(r"\n{3,}", "\n\n", texto)
                texto = re.sub(r"[ \t]+", " ", texto).strip()
                if len(texto) >= 120:
                    return texto
        except Exception:
            continue
    return ""


def _dominio_requiere_playwright(url):
    """Verifica si el dominio está en la lista de Playwright prioritario."""
    dominio = urlparse(url).netloc.lower()
    return any(d in dominio for d in DOMINIOS_PLAYWRIGHT_PRIORITARIO)


# ============================================================
# CACHE LOCAL
# ============================================================
def _ruta_cache_rss():
    return Path(CARPETA_BASE_SEMANAL) / NOMBRE_CARPETA_CACHE_RSS


def _hash_cache(texto):
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _leer_cache(query_url):
    if not RSS_USAR_CACHE_LOCAL:
        return None
    ruta = _ruta_cache_rss() / f"{_hash_cache(query_url)}.json"
    if not ruta.exists():
        return None
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _guardar_cache(query_url, resultados):
    if not RSS_USAR_CACHE_LOCAL:
        return
    carpeta = _ruta_cache_rss()
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{_hash_cache(query_url)}.json"
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)


# ============================================================
# DECODIFICACIÓN DE URLs DE GOOGLE NEWS
# ============================================================
def _decodificar_base64_directo(google_url):
    """
    Intenta decodificar la URL directamente desde el base64 embebido.
    
    Las URLs de Google News RSS tienen este formato:
      https://news.google.com/rss/articles/CBMi<base64_data>?oc=5
    
    El base64 contiene la URL original del artículo.
    """
    try:
        parsed = urlparse(google_url)
        path = parsed.path

        # Obtener el ID codificado
        encoded_part = None
        for prefix in ["/rss/articles/", "/articles/", "/read/"]:
            if prefix in path:
                encoded_part = path.split(prefix)[-1]
                break

        if not encoded_part:
            return None

        # Limpiar parámetros
        if "?" in encoded_part:
            encoded_part = encoded_part.split("?")[0]

        # Google usa base64url encoding
        encoded_part = encoded_part.replace("-", "+").replace("_", "/")
        # Agregar padding
        padding_needed = len(encoded_part) % 4
        if padding_needed:
            encoded_part += "=" * (4 - padding_needed)

        decoded_bytes = base64.b64decode(encoded_part)

        # Buscar URLs en los bytes decodificados
        decoded_str = decoded_bytes.decode("utf-8", errors="ignore")

        # Buscar patrón de URL http/https
        urls_encontradas = re.findall(r'https?://[^\s"\'<>\x00-\x1f]+', decoded_str)

        if urls_encontradas:
            # Preferir URL no-AMP
            for url in urls_encontradas:
                if "/amp" not in url.lower() and ".amp." not in url.lower():
                    return url.rstrip(")")
            return urls_encontradas[0].rstrip(")")

    except Exception:
        pass

    return None


def _decodificar_con_gnewsdecoder(google_url):
    """Usa la librería googlenewsdecoder como fallback."""
    if not TIENE_GNEWS_DECODER:
        return None
    try:
        result = gnewsdecoder(google_url, interval=DECODER_PAUSA_ENTRE_URLS)
        if result and result.get("status"):
            url = result.get("decoded_url", "")
            if url and "news.google.com" not in url:
                return url
    except Exception:
        pass
    return None


def _decodificar_con_requests(google_url):
    """Último recurso: seguir redirects HTTP."""
    try:
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        resp = requests.head(
            google_url, allow_redirects=True, timeout=15, headers=headers
        )
        if resp.url and "news.google.com" not in resp.url:
            return resp.url

        resp = requests.get(
            google_url, allow_redirects=True, timeout=15,
            headers=headers, stream=True
        )
        final_url = resp.url
        resp.close()
        if final_url and "news.google.com" not in final_url:
            return final_url
    except Exception:
        pass
    return None


def resolver_url_google_news(google_url):
    """
    Resuelve URL de Google News a la URL real del artículo.
    Usa 3 estrategias en orden:
      1. Decodificación base64 directa (instantánea, sin requests)
      2. googlenewsdecoder (requiere request a Google)
      3. Seguir redirects HTTP (último recurso)
    """
    global URLS_DECODIFICADAS_OK, URLS_DECODIFICADAS_FAIL

    if not google_url or "news.google.com" not in google_url:
        return google_url

    # Estrategia 1: Base64 directo (más rápido, sin requests)
    url = _decodificar_base64_directo(google_url)
    if url:
        URLS_DECODIFICADAS_OK += 1
        return url

    # Estrategia 2: googlenewsdecoder
    url = _decodificar_con_gnewsdecoder(google_url)
    if url:
        URLS_DECODIFICADAS_OK += 1
        return url

    # Estrategia 3: Seguir redirects HTTP
    url = _decodificar_con_requests(google_url)
    if url:
        URLS_DECODIFICADAS_OK += 1
        return url

    URLS_DECODIFICADAS_FAIL += 1
    return google_url


# ============================================================
# BUSQUEDA GOOGLE NEWS RSS
# ============================================================
def construir_url_rss(query, fecha_ini=None, fecha_fin=None):
    q = query
    if fecha_ini:
        q += f" after:{fecha_ini}"
    if fecha_fin:
        q += f" before:{fecha_fin}"

    url = (
        f"https://news.google.com/rss/search"
        f"?q={quote_plus(q)}"
        f"&hl=es-419"
        f"&gl=MX"
        f"&ceid=MX:es-419"
    )
    return url


def parsear_rss(xml_text):
    noticias = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        print(f"    ⚠ Error parseando XML: {e}")
        return noticias

    channel = root.find("channel")
    if channel is None:
        return noticias

    for item in channel.findall("item"):
        titulo = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        description = (item.findtext("description") or "").strip()

        source_elem = item.find("source")
        fuente = ""
        if source_elem is not None:
            fuente = (source_elem.text or "").strip()

        iso_date = ""
        fecha_legible = pub_date
        if pub_date:
            try:
                dt = parsedate_to_datetime(pub_date)
                iso_date = dt.isoformat()
                fecha_legible = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass

        noticias.append({
            "titulo": titulo,
            "url_google": link,
            "url": "",
            "fecha": fecha_legible,
            "iso_date": iso_date,
            "fuente": fuente,
            "autor": "",
            "thumbnail": "",
            "texto": "",
            "descripcion": description,
            "origen": "GOOGLE_NEWS_RSS",
        })

    return noticias


def buscar_google_news_rss(query, fecha_ini, fecha_fin):
    global RSS_CALLS_REALES, RSS_RESPUESTAS_CACHE

    url = construir_url_rss(query, fecha_ini, fecha_fin)
    print(f"\n  RSS URL: {url[:120]}...")

    cached = _leer_cache(url)
    if cached is not None:
        RSS_RESPUESTAS_CACHE += 1
        print(f"  → {len(cached)} noticias (desde cache)")
        return cached

    espera = RSS_BACKOFF_INICIAL
    ultimo_error = None

    for intento in range(1, RSS_MAX_REINTENTOS + 1):
        try:
            headers = {
                "User-Agent": random.choice(USER_AGENTS),
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
                "Accept-Language": "es-MX,es;q=0.9",
            }
            resp = requests.get(url, headers=headers, timeout=RSS_TIMEOUT)
            RSS_CALLS_REALES += 1

            if resp.status_code == 429:
                raise RuntimeError("Google News devolvió 429 (Too Many Requests)")

            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")

            noticias = parsear_rss(resp.text)
            print(f"  → {len(noticias)} noticias encontradas")

            noticias_serializables = [dict(n) for n in noticias]
            _guardar_cache(url, noticias_serializables)
            return noticias

        except Exception as exc:
            ultimo_error = exc
            if intento >= RSS_MAX_REINTENTOS:
                break
            pausa = min(espera, RSS_BACKOFF_MAX) + random.uniform(1.0, 3.0)
            print(f"  ⚠ Error RSS (intento {intento}/{RSS_MAX_REINTENTOS}): {exc}. "
                  f"Reintentando en {pausa:.1f}s...")
            time.sleep(pausa)
            espera = min(espera * 2, RSS_BACKOFF_MAX)

    print(f"  ✗ Fallo RSS tras {RSS_MAX_REINTENTOS} intentos: {ultimo_error}")
    return []


# ============================================================
# QUERIES
# ============================================================
def generar_queries(medios, terminos, modo="compacto"):
    if modo == "combinado":
        return [f"{termino} {medio}" for medio in medios for termino in terminos]
    bloque_or = " OR ".join(terminos)
    return [f"({bloque_or}) {medio}" for medio in medios]


# ============================================================
# DEDUPLICACIÓN Y FILTRADO
# ============================================================
def deduplicar(lista):
    vistos = set()
    unicos = []
    for r in lista:
        url_key = r.get("url") or r.get("url_google", "")
        if url_key and url_key not in vistos:
            vistos.add(url_key)
            unicos.append(r)
    return unicos


def filtrar_por_fecha(noticias, fecha_ini, fecha_fin):
    ini = datetime.strptime(fecha_ini, "%Y-%m-%d")
    fin = datetime.strptime(fecha_fin, "%Y-%m-%d") + timedelta(days=1)

    filtradas = []
    sin_fecha = []

    for r in noticias:
        if r.get("iso_date"):
            try:
                fecha = datetime.fromisoformat(r["iso_date"]).replace(tzinfo=None)
                if ini <= fecha < fin:
                    filtradas.append(r)
                continue
            except Exception:
                pass
        sin_fecha.append(r)

    print(f"  Dentro del rango: {len(filtradas)} | Sin fecha parseable: {len(sin_fecha)}")
    return filtradas + sin_fecha


# ============================================================
# RESOLVER URLS Y DESCARGAR TEXTOS
# ============================================================
def resolver_urls(noticias):
    print(f"\n[2/4] Decodificando URLs reales de {len(noticias)} artículos...")
    for i, r in enumerate(noticias, 1):
        if not r.get("url_google"):
            continue
        url_real = resolver_url_google_news(r["url_google"])
        r["url"] = url_real
        estado = "✓" if "news.google" not in url_real else "✗"
        print(f"  {i}/{len(noticias)} [{estado}] {r['titulo'][:50]}")
        if estado == "✓":
            print(f"       → {url_real[:80]}")
    return noticias


def descargar_textos(noticias):
    """
    Descarga el texto completo de cada URL.
    Estrategia por orden:
      1. trafilatura.fetch_url (rápido, limpio)
      2. cloudscraper + trafilatura.extract (bypass Cloudflare: Milenio, etc.)
      3. requests con headers de navegador
      4. Playwright (navegador real con JS — para sitios dinámicos)

    Para dominios en DOMINIOS_PLAYWRIGHT_PRIORITARIO, si las estrategias
    1-3 fallan se usa Playwright automáticamente. Para otros dominios,
    Playwright se usa como último recurso universal.
    """
    print(f"\n[3/4] Descargando texto completo de {len(noticias)} artículos...")
    if TIENE_PLAYWRIGHT:
        print(f"  Playwright habilitado para: {', '.join(DOMINIOS_PLAYWRIGHT_PRIORITARIO)}")

    descargados = 0
    fallidos = 0
    descargados_playwright = 0

    for i, r in enumerate(noticias, 1):
        url = r.get("url", "")
        if not url or "news.google.com" in url:
            print(f"  {i}/{len(noticias)} ✗ Sin URL real: {r['titulo'][:50]}")
            fallidos += 1
            continue

        print(f"  {i}/{len(noticias)} Descargando: {r['titulo'][:50]}")

        texto = ""
        motivo_fallo = ""
        dominio = urlparse(url).netloc.lower()
        es_dominio_playwright = _dominio_requiere_playwright(url)

        # ── Estrategia 1: trafilatura directa (más rápido) ──
        try:
            html = trafilatura.fetch_url(url)
            if html:
                bloqueo = detectar_html_bloqueado(html)
                if bloqueo:
                    motivo_fallo = f"bloqueo_detectado:{bloqueo}"
                else:
                    texto = trafilatura.extract(html, include_comments=False) or ""
                    if not texto:
                        texto = extraer_texto_basico_desde_html(html)
                        if texto:
                            print("       (fallback meta/json-ld)")
                    if not texto:
                        motivo_fallo = "trafilatura_sin_texto"
            else:
                motivo_fallo = "fetch_url_vacio"
        except Exception as exc:
            motivo_fallo = f"fetch_url_error:{type(exc).__name__}"

        # ── Estrategia 2: cloudscraper (bypass Cloudflare) ──
        if not texto:
            try:
                resp = SCRAPER.get(
                    url,
                    timeout=20,
                    headers={"User-Agent": random.choice(USER_AGENTS)},
                )
                if resp.status_code == 200 and len(resp.text) > 500:
                    bloqueo = detectar_html_bloqueado(resp.text)
                    if bloqueo:
                        motivo_fallo = f"cloudscraper_bloqueado:{bloqueo}"
                    else:
                        texto = trafilatura.extract(resp.text, include_comments=False) or ""
                        if not texto:
                            texto = extraer_texto_basico_desde_html(resp.text)
                            if texto:
                                print("       (fallback meta/json-ld via cloudscraper)")
                        if texto:
                            print(f"       (vía cloudscraper)")
                        else:
                            motivo_fallo = f"cloudscraper_sin_texto:http_{resp.status_code}"
                else:
                    motivo_fallo = f"cloudscraper_http_{resp.status_code}"
            except Exception as exc:
                motivo_fallo = f"cloudscraper_error:{type(exc).__name__}"

        # ── Estrategia 3: requests con headers de navegador ──
        if not texto:
            try:
                headers = {
                    "User-Agent": random.choice(USER_AGENTS),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "es-MX,es;q=0.9,en;q=0.6",
                    "Referer": "https://news.google.com/",
                }
                resp = requests.get(url, timeout=20, headers=headers)
                if resp.status_code == 200 and len(resp.text) > 500:
                    bloqueo = detectar_html_bloqueado(resp.text)
                    if bloqueo:
                        motivo_fallo = f"requests_bloqueado:{bloqueo}"
                    else:
                        texto = trafilatura.extract(resp.text, include_comments=False) or ""
                        if not texto:
                            texto = extraer_texto_basico_desde_html(resp.text)
                            if texto:
                                print("       (fallback meta/json-ld via requests)")
                        if texto:
                            print("       (vía requests)")
                        else:
                            motivo_fallo = "requests_sin_texto"
                else:
                    motivo_fallo = f"requests_http_{resp.status_code}"
            except Exception as exc:
                motivo_fallo = f"requests_error:{type(exc).__name__}"

        # ── Estrategia 4: Playwright (navegador real con JS) ──
        # Se activa si:
        #   a) No se obtuvo texto con las estrategias anteriores
        #   b) Playwright está disponible
        #   c) El dominio está en la lista prioritaria, O es último recurso universal
        if not texto and TIENE_PLAYWRIGHT:
            usar_playwright = es_dominio_playwright or (not texto and motivo_fallo)
            if usar_playwright:
                try:
                    texto = _descargar_con_playwright(url)
                    if texto:
                        print(f"       (vía Playwright)")
                        descargados_playwright += 1
                    else:
                        motivo_fallo = f"playwright_sin_texto|previo:{motivo_fallo}"
                except Exception as exc:
                    motivo_fallo = f"playwright_error:{type(exc).__name__}|previo:{motivo_fallo}"

                time.sleep(PLAYWRIGHT_PAUSA_ENTRE_PAGINAS)

        r["texto"] = texto
        if texto:
            descargados += 1
            print(f"       ✓ {len(texto)} caracteres")
        else:
            fallidos += 1
            print(f"       ⚠ No se pudo extraer texto | dominio:{dominio} | motivo:{motivo_fallo or 'desconocido'}")

        time.sleep(PAUSA)

    print(f"\n  Textos descargados: {descargados} (Playwright: {descargados_playwright}) | Fallidos: {fallidos}")
    return noticias


def detectar_html_bloqueado(html):
    """Detecta respuestas de challenge/bloqueo donde no hay articulo real."""
    if not html:
        return "html_vacio"

    muestra = html[:5000].lower()
    patrones = {
        "cloudflare_challenge": (
            "just a moment",
            "cf-browser-verification",
            "challenge-platform",
            "attention required",
        ),
        "access_denied": (
            "access denied",
            "forbidden",
            "request blocked",
        ),
    }

    for etiqueta, tokens in patrones.items():
        if any(token in muestra for token in tokens):
            return etiqueta
    return ""


def extraer_texto_basico_desde_html(html):
    """Fallback simple para rescatar algo de texto si trafilatura falla."""
    if not html:
        return ""

    candidatos = []
    for patron in [
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
        r'"articleBody"\s*:\s*"(.+?)"',
    ]:
        match = re.search(patron, html, flags=re.IGNORECASE | re.DOTALL)
        if match:
            texto = unescape(match.group(1))
            texto = re.sub(r"<[^>]+>", " ", texto)
            texto = re.sub(r"\s+", " ", texto).strip()
            if len(texto) >= 120:
                candidatos.append(texto)

    return max(candidatos, key=len, default="")


# ============================================================
# LIMPIEZA Y GUARDADO
# ============================================================
def limpiar_texto_para_txt(texto):
    t = (texto or "").lower()
    t = re.sub(r"https?://\S+|www\.\S+", " ", t)
    t = re.sub(r"\b[\w-]+(?:\.[\w-]+)+\b", " ", t)
    t = unicodedata.normalize("NFD", t)
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    t = t.encode("ascii", "ignore").decode("ascii")
    t = re.sub(r"\d+", " ", t)
    t = re.sub(r"[^a-z\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def formatear_en_lineas_de_palabras(texto, palabras_por_linea=30):
    palabras = texto.split()
    if not palabras:
        return ""
    return "\n".join(
        " ".join(palabras[i:i + palabras_por_linea])
        for i in range(0, len(palabras), palabras_por_linea)
    )


def guardar_txt_noticias(noticias, ruta_txt):
    material_limpio = []
    for r in noticias:
        titulo = (r.get("titulo") or "").strip()
        texto = (r.get("texto") or "").strip()
        combinado = f"{titulo} {texto}".strip()
        limpio = limpiar_texto_para_txt(combinado)
        if limpio:
            material_limpio.append(limpio)

    texto_final = formatear_en_lineas_de_palabras(
        " ".join(material_limpio), palabras_por_linea=30
    )

    with open(ruta_txt, "w", encoding="utf-8") as f:
        if texto_final:
            f.write(texto_final + "\n")


# ============================================================
# ESTRUCTURA SEMANAL
# ============================================================
def primer_lunes_del_mes(anio, mes):
    primer_dia = date(anio, mes, 1)
    dias_hasta_lunes = (0 - primer_dia.weekday()) % 7
    return primer_dia + timedelta(days=dias_hasta_lunes)


def iterar_semanas(fecha_inicio, fecha_fin):
    inicio = fecha_inicio
    while inicio <= fecha_fin:
        fin = min(inicio + timedelta(days=6), fecha_fin)
        yield inicio, fin
        inicio += timedelta(days=7)


def nombre_carpeta_semana(fecha_inicio, fecha_fin):
    return build_week_folder_name(fecha_inicio, fecha_fin)


def rutas_salida_semana(fecha_inicio_semana, fecha_fin_semana):
    report_tag = nombre_carpeta_semana(
        fecha_inicio_semana, fecha_fin_semana
    )
    carpeta_semana = Path(CARPETA_BASE_SEMANAL) / report_tag
    output_base = build_source_filename(report_tag, NOMBRE_ARCHIVO_BASE)
    archivo_salida = carpeta_semana / f"{output_base}.csv"
    archivo_txt = carpeta_semana / f"{output_base}.txt"
    return carpeta_semana, archivo_salida, archivo_txt


# ============================================================
# CLI
# ============================================================
def valid_date(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Fecha invalida '{value}'. Usa YYYY-MM-DD."
        ) from exc
    return value


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extractor de medios via Google News RSS + trafilatura."
    )
    parser.add_argument(
        "--since",
        "--fecha-inicio",
        "-s",
        dest="fecha_inicio",
        type=valid_date,
        required=True,
        help="Fecha inicial global YYYY-MM-DD (heredada del orquestador)",
    )
    parser.add_argument(
        "--before",
        "--fecha-fin",
        "-b",
        dest="fecha_fin",
        type=valid_date,
        required=True,
        help="Fecha final global YYYY-MM-DD (heredada del orquestador)",
    )
    parser.add_argument(
        "-m",
        "--medio",
        dest="medios",
        action="append",
        default=None,
        help="Medio/site a consultar. Repite --medio para varios valores.",
    )
    parser.add_argument(
        "-t",
        "--termino",
        dest="terminos",
        action="append",
        default=None,
        help="Termino de busqueda. Repite --termino para varios valores.",
    )
    parser.add_argument(
        "--modo-queries",
        choices=["compacto", "combinado"],
        default=MODO_QUERIES,
        help="Modo de construccion de queries.",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default=CARPETA_BASE_SEMANAL,
        help="Carpeta base donde se guardan las semanas. Default: %(default)s",
    )
    parser.add_argument(
        "--nombre-archivo-base",
        default=NOMBRE_ARCHIVO_BASE,
        help="Prefijo del archivo CSV/TXT de salida.",
    )
    parser.add_argument(
        "--anio-inicio",
        type=int,
        default=ANIO_INICIO,
        help="Anio para calcular el primer lunes cuando no se usa --since.",
    )
    parser.add_argument(
        "--mes-inicio",
        type=int,
        default=MES_INICIO,
        help="Mes para calcular el primer lunes cuando no se usa --since.",
    )
    parser.add_argument(
        "--omitir-semanas-existentes",
        dest="omitir_semanas_existentes",
        action="store_true",
        default=OMITIR_SEMANAS_EXISTENTES,
        help="Omite semanas cuyo CSV ya existe.",
    )
    parser.add_argument(
        "--no-omitir-semanas-existentes",
        dest="omitir_semanas_existentes",
        action="store_false",
        help="Fuerza reprocesar semanas aunque ya exista CSV.",
    )
    parser.add_argument(
        "--pausa",
        type=float,
        default=PAUSA,
        help="Segundos de pausa entre requests de descarga.",
    )
    parser.add_argument(
        "--pausa-entre-queries",
        type=float,
        default=PAUSA_ENTRE_QUERIES,
        help="Segundos de pausa entre queries RSS.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Muestra consultas y rutas sin descargar noticias.",
    )
    return parser.parse_args()


# ============================================================
# PROCESAR SEMANA
# ============================================================
def procesar_semana(fecha_inicio_semana, fecha_fin_semana):
    fecha_inicio = fecha_inicio_semana.strftime("%Y-%m-%d")
    fecha_fin = fecha_fin_semana.strftime("%Y-%m-%d")

    carpeta_semana, archivo_salida, archivo_txt = rutas_salida_semana(
        fecha_inicio_semana, fecha_fin_semana
    )
    carpeta_semana.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print(f"  MEDIOS:       {', '.join(MEDIOS)}")
    print(f"  TERMINOS:     {', '.join(TERMINOS)}")
    print(f"  FECHA INICIO: {fecha_inicio}")
    print(f"  FECHA FIN:    {fecha_fin}")
    print(f"  MÉTODO:       Google News RSS (gratuito)")
    print(f"  DECODER:      base64 + {'gnewsdecoder' if TIENE_GNEWS_DECODER else 'HTTP redirect'} (fallback)")
    print(f"  PLAYWRIGHT:   {'✓ habilitado' if TIENE_PLAYWRIGHT else '✗ no disponible'}")
    print(f"  CARPETA:      {carpeta_semana}")
    print("=" * 60)

    queries = generar_queries(MEDIOS, TERMINOS, modo=MODO_QUERIES)
    print(f"\n[1/4] Buscando con {len(queries)} queries...")

    todas_noticias = []
    for i, query in enumerate(queries, 1):
        print(f"\n{'─' * 50}")
        print(f"  Query {i}/{len(queries)}: {query}")
        print(f"{'─' * 50}")
        resultados = buscar_google_news_rss(query, fecha_inicio, fecha_fin)
        todas_noticias.extend(resultados)
        if i < len(queries):
            time.sleep(PAUSA_ENTRE_QUERIES)

    todos = deduplicar(todas_noticias)
    todos = filtrar_por_fecha(todos, fecha_inicio, fecha_fin)
    print(f"\n  TOTAL ÚNICO: {len(todos)} noticias")

    if not todos:
        print("  (sin resultados para esta semana)")
        pd.DataFrame(columns=MEDIOS_OUTPUT_COLUMNS).to_csv(
            archivo_salida,
            index=False,
            encoding="utf-8-sig",
        )
        return pd.DataFrame()

    todos = resolver_urls(todos)
    todos = deduplicar(todos)
    print(f"  TOTAL tras resolver URLs: {len(todos)} noticias")

    todos = descargar_textos(todos)

    df = pd.DataFrame(todos, columns=MEDIOS_OUTPUT_COLUMNS)

    try:
        df["_sort"] = pd.to_datetime(df["iso_date"], errors="coerce")
        df = df.sort_values("_sort", ascending=False).drop(columns="_sort")
    except Exception:
        pass

    df.to_csv(archivo_salida, index=False, encoding="utf-8-sig")
    print(f"\n✓ CSV guardado en: {archivo_salida}")

    print("\n--- NOTICIAS ---")
    for i, r in enumerate(todos, 1):
        tiene_texto = "✓" if r.get("texto") else "✗"
        resuelta = "✓" if r.get("url") and "news.google" not in r["url"] else "✗"
        print(f"  {i:2}. [{r['fecha'][:10]}] {r['titulo'][:60]}")
        print(f"       {r['fuente']} | texto:{tiene_texto} | url_real:{resuelta}")
        if resuelta == "✓":
            print(f"       {r['url'][:80]}")

    return df


# ============================================================
# MAIN
# ============================================================
def main():
    global MEDIOS, TERMINOS, ANIO_INICIO, MES_INICIO
    global FECHA_INICIO_EXACTA, FECHA_FIN_EXACTA, MODO_QUERIES
    global OMITIR_SEMANAS_EXISTENTES, CARPETA_BASE_SEMANAL
    global NOMBRE_ARCHIVO_BASE, PAUSA, PAUSA_ENTRE_QUERIES

    args = parse_args()

    requested_media = args.medios if args.medios else list(UNIFORM_MEDIA_SITES)
    requested_terms = args.terminos if args.terminos else list(UNIFORM_SEARCH_TERMS)
    if tuple(requested_media) != UNIFORM_MEDIA_SITES:
        raise SystemExit(
            "❌ El contrato uniforme de Medios requiere exactamente "
            f"{', '.join(UNIFORM_MEDIA_SITES)}."
        )
    if tuple(requested_terms) != UNIFORM_SEARCH_TERMS:
        raise SystemExit(
            "❌ El contrato uniforme de Medios requiere exactamente los tres "
            "términos históricos configurados."
        )
    if args.modo_queries != "combinado":
        raise SystemExit("❌ El contrato uniforme de Medios requiere --modo-queries combinado.")
    if args.nombre_archivo_base != "medios":
        raise SystemExit("❌ El contrato uniforme de Medios requiere --nombre-archivo-base medios.")
    MEDIOS = requested_media
    TERMINOS = requested_terms
    ANIO_INICIO = args.anio_inicio
    MES_INICIO = args.mes_inicio
    FECHA_INICIO_EXACTA = args.fecha_inicio
    FECHA_FIN_EXACTA = args.fecha_fin
    MODO_QUERIES = args.modo_queries
    OMITIR_SEMANAS_EXISTENTES = args.omitir_semanas_existentes
    CARPETA_BASE_SEMANAL = args.output_dir
    NOMBRE_ARCHIVO_BASE = args.nombre_archivo_base
    PAUSA = args.pausa
    PAUSA_ENTRE_QUERIES = args.pausa_entre_queries

    if not MEDIOS:
        raise SystemExit("❌ Debes definir al menos un medio.")
    if not TERMINOS:
        raise SystemExit("❌ Debes definir al menos un termino.")
    if not 1 <= MES_INICIO <= 12:
        raise SystemExit("❌ --mes-inicio debe estar entre 1 y 12.")

    if FECHA_INICIO_EXACTA:
        fecha_inicio_global = datetime.strptime(FECHA_INICIO_EXACTA, "%Y-%m-%d").date()
        etiqueta_inicio = f"{fecha_inicio_global} (manual)"
    else:
        fecha_inicio_global = primer_lunes_del_mes(ANIO_INICIO, MES_INICIO)
        etiqueta_inicio = f"{fecha_inicio_global} (primer lunes de {MES_INICIO}/{ANIO_INICIO})"

    if FECHA_FIN_EXACTA:
        fecha_fin_global = datetime.strptime(FECHA_FIN_EXACTA, "%Y-%m-%d").date()
        etiqueta_fin = f"{fecha_fin_global} (manual)"
    else:
        fecha_fin_global = date.today()
        etiqueta_fin = f"{fecha_fin_global} (hoy)"

    if fecha_inicio_global > fecha_fin_global:
        raise SystemExit("❌ fecha_inicio no puede ser mayor que fecha_fin.")

    print("\n" + "#" * 60)
    print("  EXTRACCIÓN SEMANAL — Google News RSS")
    print(f"  DESDE: {etiqueta_inicio}")
    print(f"  HASTA: {etiqueta_fin}")
    print(f"  BASE:  {CARPETA_BASE_SEMANAL}")
    print(f"  MODO_QUERIES: {MODO_QUERIES}")
    print(f"  DECODER: base64 → {'gnewsdecoder' if TIENE_GNEWS_DECODER else 'HTTP redirect'} (fallback)")
    print(f"  PLAYWRIGHT: {'✓ habilitado' if TIENE_PLAYWRIGHT else '✗ no disponible'}")
    print(f"  COSTO: $0 (RSS gratuito)")
    print("#" * 60)

    queries_ejemplo = generar_queries(MEDIOS, TERMINOS, modo=MODO_QUERIES)
    print(f"Queries para el rango: {len(queries_ejemplo)}")
    print(f"Total requests RSS estimados: {len(queries_ejemplo)}")

    print("\n" + "#" * 60)
    print(f"RANGO ÚNICO: {fecha_inicio_global} -> {fecha_fin_global}")
    print("#" * 60)

    _, archivo_salida, _ = rutas_salida_semana(fecha_inicio_global, fecha_fin_global)
    if args.dry_run:
        print(f"CSV canónico: {archivo_salida}")
        print("🧪 Dry-run: no se crearon carpetas ni se hicieron solicitudes HTTP.")
        return None

    verificar_dependencias_ejecucion()

    if OMITIR_SEMANAS_EXISTENTES and archivo_salida.exists():
        print(f"↷ Rango omitido (ya existe CSV): {archivo_salida}")
        df = pd.read_csv(archivo_salida, encoding="utf-8-sig")
        _cerrar_playwright()
        return df

    try:
        df = procesar_semana(fecha_inicio_global, fecha_fin_global)
    except Exception as exc:
        _cerrar_playwright()
        raise SystemExit(f"⚠ Error en rango {fecha_inicio_global} -> {fecha_fin_global}: {exc}")

    # Cerrar Playwright si se usó
    _cerrar_playwright()

    print(f"\n{'=' * 60}")
    print(f"  RSS requests reales: {RSS_CALLS_REALES}")
    print(f"  Respuestas desde cache: {RSS_RESPUESTAS_CACHE}")
    print(f"  URLs decodificadas OK: {URLS_DECODIFICADAS_OK}")
    print(f"  URLs sin resolver: {URLS_DECODIFICADAS_FAIL}")
    print(f"  Playwright descargas OK: {PLAYWRIGHT_DESCARGAS_OK}")
    print(f"  Playwright descargas FAIL: {PLAYWRIGHT_DESCARGAS_FAIL}")
    print(f"  Costo total: $0")
    print(f"{'=' * 60}")

    return df if df is not None else pd.DataFrame()


if __name__ == "__main__":
    df = main()
