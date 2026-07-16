#!/usr/bin/env python3
"""
03_twitter_extractor.py - Extractor de Twitter/X
================================================

Este script extrae tweets de Twitter/X y los guarda en la carpeta indicada.

Uso:
    - Sin argumentos: usa las fechas configuradas en CONFIG_START_DATE_STR/CONFIG_END_DATE_STR
    - Con fechas: python 03_twitter_extractor.py YYYY-MM-DD YYYY-MM-DD
    - Con queries: python 03_twitter_extractor.py --query "naucalpan" --query "from:GobNau"

Autor: Emilio
"""

import re
import csv
import asyncio
import sys
import json
import os
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_DIR = REPO_ROOT / "scr" / "compartido"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from output_naming import build_source_filename, build_week_folder_name
from radar_paths import EXTRACTED_DATA_DIR, STATE_DIR

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_IMPORT_ERROR = ""
except Exception as exc:
    async_playwright = None
    PLAYWRIGHT_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

# =========================
# CONFIGURACION TAMPICO
# =========================
DEFAULT_OUTPUT_BASE_DIR = EXTRACTED_DATA_DIR
DEFAULT_STATE_PATH = STATE_DIR / "x_state.json"
CONFIG_START_DATE_STR = ""
CONFIG_END_DATE_STR = ""
DEFAULT_MAX_TWEETS = 3000

# Usuarios objetivo y terminos principales
TARGET_HANDLES = ["@MonicaVTampico", "@TampicoGob"]

INSTITUTIONAL_POST_QUERIES = {
    "from:MonicaVTampico",
    "from:TampicoGob",
}

# Consultas base (sin rango de fechas)
SEARCH_QUERIES = [
    "to:MonicaVTampico",
    "from:MonicaVTampico",
    "to:TampicoGob",
    "from:TampicoGob",
    "@TampicoGob",
    "@MonicaVTampico",
    "monica villarreal",
    "gobierno de tampico",
    "tampico",
]

# Respuestas
INCLUDE_REPLIES = True
MAX_REPLIES_PER_TWEET = 200
MAX_REPLY_SCROLLS = 8
NAV_TIMEOUT_MS = 90000
NAV_MAX_RETRIES = 3

class TwitterExtractorIAD:
    def __init__(
        self,
        fecha_inicio_str,
        fecha_fin_str,
        custom_queries=None,
        output_base_dir: Path | None = None,
        state_path: Path | None = None,
        max_tweets: int = DEFAULT_MAX_TWEETS,
        max_replies_per_tweet: int = MAX_REPLIES_PER_TWEET,
        max_reply_scrolls: int = MAX_REPLY_SCROLLS,
        headless: bool = True,
        create_output_dir: bool = True,
    ):
        """
        fecha_inicio_str: string en formato YYYY-MM-DD (fecha de inicio)
        fecha_fin_str: string en formato YYYY-MM-DD (fecha de fin)
        """
        self.fecha_inicio = datetime.strptime(fecha_inicio_str, "%Y-%m-%d")
        self.fecha_fin = datetime.strptime(fecha_fin_str, "%Y-%m-%d")
        
        # Calcular nombre de carpeta de semana
        self.nombre_semana = self.calcular_nombre_semana()
        
        # Paths del sistema
        self.state_path = state_path or DEFAULT_STATE_PATH
        
        # Directorio de salida semanal dentro del repo
        base_dir = output_base_dir or DEFAULT_OUTPUT_BASE_DIR
        self.output_dir = base_dir / self.nombre_semana
        
        # Crear directorio si no existe (normalmente ya debe existir por el main)
        if create_output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Único CSV canónico semanal.
        canonical_base = build_source_filename(self.nombre_semana, "twitter")
        self.output_csv = self.output_dir / f"{canonical_base}.csv"
        
        # Configuraciones
        self.max_tweets = max_tweets
        self.max_replies_per_tweet = max_replies_per_tweet
        self.max_reply_scrolls = max_reply_scrolls
        self.headless = headless
        
        # Queries optimizadas con fechas
        fecha_inicio_str = self.fecha_inicio.strftime("%Y-%m-%d")
        # El operador `until` de X es exclusivo; se suma un día para incluir
        # por completo la fecha final solicitada.
        fecha_fin_str = (self.fecha_fin + timedelta(days=1)).strftime("%Y-%m-%d")
        
        base_queries = custom_queries if custom_queries else SEARCH_QUERIES
        self.search_queries = []
        for query in base_queries:
            query_token = f'"{query}"'
            self.search_queries.append(
                f"{query_token} since:{fecha_inicio_str} until:{fecha_fin_str}"
            )
        
        print(f"📅 Período: {self.fecha_inicio.date()} a {self.fecha_fin.date()}")
        print(f"📁 Carpeta: {self.nombre_semana}")
        print(f"📂 Salida canónica: {self.output_csv}")
        print(f"🔎 Queries base: {len(base_queries)}")
    
    def calcular_nombre_semana(self):
        """Calcula el nombre de la carpeta de salida."""
        return build_week_folder_name(self.fecha_inicio, self.fecha_fin)
    
    def clean_text(self, text: str) -> str:
        """Limpiar texto eliminando espacios extras"""
        return re.sub(r"\s+", " ", (text or "")).strip()

    def should_include_tweet(self, tweet: dict, query: str) -> bool:
        """Sin filtro de términos: incluir todo lo que caiga en el rango de fechas."""
        return True
    
    def parse_datetime(self, dt_str: str):
        """Parsear datetime de Twitter"""
        if not dt_str:
            return None
        if dt_str.endswith("Z"):
            dt_str = dt_str.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(dt_str)
        except Exception:
            return None

    async def expand_tweet_text(self, article) -> None:
        """Intenta expandir tweets truncados en el timeline."""
        candidatos = [
            'text=/^(Show more|Mostrar más)$/i',
            'text=/^(Read more|Leer más)$/i',
        ]

        for selector in candidatos:
            try:
                locator = article.locator(selector)
                if await locator.count():
                    await locator.first.click(timeout=1500)
                    await article.page.wait_for_timeout(250)
                    return
            except Exception:
                continue

    async def extract_tweet_text(self, article) -> str:
        """Extrae el texto del tweet priorizando el contenido completo."""
        await self.expand_tweet_text(article)

        text_locator = article.locator('[data-testid="tweetText"]')
        if not await text_locator.count():
            return ""

        try:
            text_parts = await text_locator.evaluate_all(
                """nodes => nodes
                .map(node => (node.textContent || '').replace(/\\s+/g, ' ').trim())
                .filter(Boolean)"""
            )
        except Exception:
            text_parts = [self.clean_text(t) for t in await text_locator.all_inner_texts()]

        seen = set()
        unique_parts = []
        for part in text_parts:
            if part and part not in seen:
                seen.add(part)
                unique_parts.append(part)

        return " ".join(unique_parts).strip()
    
    async def goto_search(self, page, query: str):
        """Navegar a búsqueda específica"""
        query_encoded = quote(query.strip(), safe=":")
        url = f"https://x.com/search?q={query_encoded}&src=typed_query&f=live"
        last_error = None

        for attempt in range(1, NAV_MAX_RETRIES + 1):
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
                await page.wait_for_timeout(2500)
                print(f"🔍 Búsqueda: {query[:50]}...")
                return
            except Exception as e:
                last_error = e
                print(f"⚠️ Intento {attempt}/{NAV_MAX_RETRIES} falló en búsqueda")
                await page.wait_for_timeout(2500)

        raise RuntimeError(
            f"No se pudo abrir la búsqueda tras {NAV_MAX_RETRIES} intentos. URL: {url}. "
            f"Último error: {last_error}"
        )
    
    async def extract_visible_tweets(self, page):
        """Extraer tweets visibles en la página actual"""
        items = []
        articles = page.locator('article[data-testid="tweet"]')
        tweet_count = await articles.count()

        for i in range(tweet_count):
            article = articles.nth(i)

            # ===== TEXTO ROBUSTO =====
            text = await self.extract_tweet_text(article)

            # ===== FECHA Y URL =====
            time_locator = article.locator("time")
            datetime_iso = ""
            url = ""
            
            if await time_locator.count():
                datetime_iso = await time_locator.first.get_attribute("datetime") or ""
                
                # Extraer URL del tweet
                parent_link = time_locator.first.locator("xpath=ancestor::a[1]")
                if await parent_link.count():
                    href = await parent_link.get_attribute("href")
                    if href:
                        url = "https://x.com" + href

            # ===== AUTOR =====
            author = ""
            user_locator = article.locator('[data-testid="User-Name"]')
            if await user_locator.count():
                user_text = self.clean_text(await user_locator.first.inner_text())
                handle_match = re.search(r"@\w+", user_text)
                author = handle_match.group(0) if handle_match else user_text

            # ===== MÉTRICAS DE ENGAGEMENT =====
            metrics = await self.extract_engagement_metrics(article)

            items.append({
                "author": author,
                "datetime": datetime_iso,
                "url": url,
                "text": text,
                **metrics
            })

        return items
    
    async def extract_engagement_metrics(self, article):
        """Extraer métricas de engagement de un tweet"""
        metrics = {
            "replies": 0,
            "retweets": 0,
            "likes": 0,
            "bookmarks": 0,
            "views": 0
        }
        
        try:
            # Replies
            reply_locator = article.locator('[data-testid="reply"]')
            if await reply_locator.count():
                reply_text = await reply_locator.first.get_attribute("aria-label") or ""
                reply_match = re.search(r"(\d+)", reply_text)
                if reply_match:
                    metrics["replies"] = int(reply_match.group(1))
            
            # Retweets
            retweet_locator = article.locator('[data-testid="retweet"]')
            if await retweet_locator.count():
                retweet_text = await retweet_locator.first.get_attribute("aria-label") or ""
                retweet_match = re.search(r"(\d+)", retweet_text)
                if retweet_match:
                    metrics["retweets"] = int(retweet_match.group(1))
            
            # Likes
            like_locator = article.locator('[data-testid="like"]')
            if await like_locator.count():
                like_text = await like_locator.first.get_attribute("aria-label") or ""
                like_match = re.search(r"(\d+)", like_text)
                if like_match:
                    metrics["likes"] = int(like_match.group(1))
        
        except Exception as e:
            print(f"⚠️  Error extrayendo métricas: {str(e)}")
        
        return metrics
    
    async def extract_query_data(self, page, query):
        """Extraer datos para una query específica"""
        await self.goto_search(page, query)
        
        seen_tweets = set()
        collected = []
        stagnation_count = 0
        last_count = 0
        
        # Configuración de extracción
        max_iterations = 10
        iteration = 0
        
        while len(collected) < self.max_tweets and stagnation_count < 8 and iteration < max_iterations:
            visible_tweets = await self.extract_visible_tweets(page)
            
            for tweet in visible_tweets:
                # Crear clave única para evitar duplicados
                tweet_key = (
                    tweet["url"] or "", 
                    tweet["datetime"] or "", 
                    tweet["text"][:80]
                )
                
                if tweet_key in seen_tweets:
                    continue
                    
                seen_tweets.add(tweet_key)
                
                # Parsear fecha
                tweet_datetime = self.parse_datetime(tweet["datetime"])
                if not tweet_datetime:
                    continue
                
                # Convertir a fecha sin timezone para comparación
                tweet_date = tweet_datetime.date()
                inicio_date = self.fecha_inicio.date()
                fin_date = self.fecha_fin.date()
                
                # Verificar que esté en el rango de fechas y cumpla filtros del query
                if inicio_date <= tweet_date <= fin_date and self.should_include_tweet(tweet, query):
                    
                    tweet_data = {
                        **tweet,
                        "datetime_parsed_utc": tweet_datetime.isoformat(),
                        "query_used": query,
                        "fecha_inicio": self.fecha_inicio.strftime("%Y-%m-%d"),
                        "fecha_fin": self.fecha_fin.strftime("%Y-%m-%d"),
                        "nombre_semana": self.nombre_semana,
                        "is_reply": False,
                        "in_reply_to_url": ""
                    }
                    collected.append(tweet_data)
            
            # Verificar si hemos llegado a tweets más antiguos que nuestro rango
            tweet_dates = [self.parse_datetime(t["datetime"]) for t in visible_tweets 
                          if self.parse_datetime(t["datetime"])]
            if tweet_dates and min(tweet_dates).date() < inicio_date:
                print(f"📍 Llegamos a tweets anteriores al período")
                break
            
            # Scroll para cargar más tweets
            await page.mouse.wheel(0, 2600)
            await page.wait_for_timeout(1000)
            
            # Control de stagnación
            if len(collected) == last_count:
                stagnation_count += 1
            else:
                stagnation_count = 0
                last_count = len(collected)
            
            iteration += 1
        
        print(f"📊 Query '{query[:30]}...': {len(collected)} tweets")
        return collected

    async def extract_replies_for_tweet(self, page, tweet_url: str):
        """Extrae respuestas para un tweet específico"""
        if not tweet_url:
            return []

        print(f"   ↳ Buscando respuestas: {tweet_url}")
        await page.goto(tweet_url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
        await page.wait_for_timeout(2000)

        collected = []
        seen = set()
        stagnation_count = 0
        last_count = 0
        iteration = 0

        while (len(collected) < self.max_replies_per_tweet and
               stagnation_count < 6 and
               iteration < self.max_reply_scrolls):
            visible_tweets = await self.extract_visible_tweets(page)

            for tweet in visible_tweets:
                if tweet.get("url") == tweet_url:
                    continue

                tweet_key = (
                    tweet["url"] or "",
                    tweet["datetime"] or "",
                    tweet["text"][:80]
                )
                if tweet_key in seen:
                    continue
                seen.add(tweet_key)

                tweet_datetime = self.parse_datetime(tweet["datetime"])
                if not tweet_datetime:
                    continue

                tweet_date = tweet_datetime.date()
                inicio_date = self.fecha_inicio.date()
                fin_date = self.fecha_fin.date()

                if inicio_date <= tweet_date <= fin_date:
                    tweet_data = {
                        **tweet,
                        "datetime_parsed_utc": tweet_datetime.isoformat(),
                        "query_used": f"reply_to:{tweet_url}",
                        "fecha_inicio": self.fecha_inicio.strftime("%Y-%m-%d"),
                        "fecha_fin": self.fecha_fin.strftime("%Y-%m-%d"),
                        "nombre_semana": self.nombre_semana,
                        "is_reply": True,
                        "in_reply_to_url": tweet_url
                    }
                    collected.append(tweet_data)

            # Scroll para cargar más respuestas
            await page.mouse.wheel(0, 2600)
            await page.wait_for_timeout(1000)

            if len(collected) == last_count:
                stagnation_count += 1
            else:
                stagnation_count = 0
                last_count = len(collected)

            iteration += 1

        print(f"   ↳ Respuestas encontradas: {len(collected)}")
        return collected
    
    def save_to_csv(self, all_tweets):
        """Guarda el único CSV canónico semanal."""
        if not all_tweets:
            print("⚠️  No hay tweets para guardar")
            return
        
        # Definir columnas del CSV
        fieldnames = [
            "fecha_semana", "nombre_semana", "author", "datetime", "datetime_parsed_utc", 
            "url", "text", "replies", "retweets", "likes", "bookmarks", 
            "views", "query_used", "is_reply", "in_reply_to_url"
        ]
        
        with open(self.output_csv, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for tweet in all_tweets:
                writer.writerow({field: tweet.get(field, "") for field in fieldnames})

        print(f"✅ Twitter: {len(all_tweets)} tweets guardados")
        print(f"   📄 CSV canónico: {self.output_csv}")
    
    async def run_extraction(self):
        """Ejecutar extracción completa"""
        if async_playwright is None:
            print("❌ Falta dependencia 'playwright'.")
            print(f"   Detalle: {PLAYWRIGHT_IMPORT_ERROR}")
            print("   Instala con: pip install playwright && playwright install chromium")
            return False

        if not self.state_path.exists():
            print(f"❌ No existe el archivo de state: {self.state_path}")
            print(f"💡 Ejecuta primero el login para generar x_state.json")
            return False
        
        print(f"🚀 Iniciando extracción Twitter...")
        
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=self.headless)
                context = await browser.new_context(
                    storage_state=str(self.state_path),
                    viewport={"width": 1280, "height": 900}
                )
                context.set_default_timeout(NAV_TIMEOUT_MS)
                context.set_default_navigation_timeout(NAV_TIMEOUT_MS)
                page = await context.new_page()
                
                all_tweets = []
                processed_reply_urls = set()
                
                # Extraer datos para cada query
                for i, query in enumerate(self.search_queries, 1):
                    print(f"\n🔍 Query {i}/{len(self.search_queries)}")
                    query_tweets = await self.extract_query_data(page, query)
                    all_tweets.extend(query_tweets)

                    if INCLUDE_REPLIES and query_tweets:
                        for tweet in query_tweets:
                            url = tweet.get("url")
                            if not url or url in processed_reply_urls:
                                continue
                            processed_reply_urls.add(url)
                            replies = await self.extract_replies_for_tweet(page, url)
                            all_tweets.extend(replies)
                
                # Remover duplicados finales por URL
                seen_urls = set()
                unique_tweets = []
                for tweet in all_tweets:
                    if tweet["url"] and tweet["url"] not in seen_urls:
                        seen_urls.add(tweet["url"])
                        unique_tweets.append(tweet)
                    elif not tweet["url"]:  # Tweets sin URL
                        unique_tweets.append(tweet)
                
                # Guardar resultados
                self.save_to_csv(unique_tweets)
                
                await context.close()
                await browser.close()
                
                print(f"\n✅ EXTRACCIÓN COMPLETADA")
                print(f"📁 Carpeta: {self.nombre_semana}")
                print(f"📊 Total de tweets únicos: {len(unique_tweets)}")
                
                return True
                
        except Exception as e:
            print(f"❌ Error en extracción Twitter: {str(e)}")
            return False

def main():
    """Función principal compatible con coordinador main"""
    parser = argparse.ArgumentParser(
        description="Extractor de Twitter/X"
    )
    parser.add_argument("fecha_inicio", nargs="?", help="Fecha inicio YYYY-MM-DD")
    parser.add_argument("fecha_fin", nargs="?", help="Fecha fin YYYY-MM-DD")
    parser.add_argument("--since", dest="since", help="Fecha inicio YYYY-MM-DD")
    parser.add_argument("--before", dest="before", help="Fecha fin YYYY-MM-DD")
    parser.add_argument(
        "--query",
        dest="queries",
        action="append",
        default=[],
        help="Query de búsqueda base (repite --query para varias)"
    )
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_BASE_DIR),
                        help="Directorio base de salida. Default: %(default)s")
    parser.add_argument("--state-path", default=str(DEFAULT_STATE_PATH),
                        help="Ruta al storage_state de X/Twitter")
    parser.add_argument("--max-tweets", type=int, default=DEFAULT_MAX_TWEETS,
                        help="Maximo de tweets por query")
    parser.add_argument("--max-replies-per-tweet", type=int, default=MAX_REPLIES_PER_TWEET,
                        help="Maximo de respuestas por tweet")
    parser.add_argument("--max-reply-scrolls", type=int, default=MAX_REPLY_SCROLLS,
                        help="Maximo de scrolls para respuestas")
    parser.add_argument("--headless", dest="headless", action="store_true", default=True,
                        help="Ejecuta el navegador en modo headless")
    parser.add_argument("--no-headless", dest="headless", action="store_false",
                        help="Ejecuta el navegador con interfaz")
    parser.add_argument("--dry-run", action="store_true",
                        help="Muestra consultas y rutas sin abrir Playwright")
    args = parser.parse_args()

    if (args.since or args.before) and (args.fecha_inicio or args.fecha_fin):
        print("❌ Usa fechas posicionales o --since/--before, pero no ambas formas.")
        sys.exit(1)

    if args.since or args.before:
        if bool(args.since) != bool(args.before):
            print("❌ Debes enviar --since y --before juntos.")
            sys.exit(1)
        fecha_inicio = args.since
        fecha_fin = args.before
    elif bool(args.fecha_inicio) != bool(args.fecha_fin):
        print("❌ Debes enviar ambas fechas o ninguna.")
        sys.exit(1)
    elif args.fecha_inicio and args.fecha_fin:
        fecha_inicio = args.fecha_inicio
        fecha_fin = args.fecha_fin
    else:
        if (CONFIG_START_DATE_STR and not CONFIG_END_DATE_STR) or (CONFIG_END_DATE_STR and not CONFIG_START_DATE_STR):
            print("❌ Configuración de fechas incompleta. Define ambas fechas o ninguna.")
            sys.exit(1)
        if CONFIG_START_DATE_STR and CONFIG_END_DATE_STR:
            fecha_inicio = CONFIG_START_DATE_STR
            fecha_fin = CONFIG_END_DATE_STR
        else:
            print("❌ No hay fechas definidas. Pasa fechas por argumento o define CONFIG_START_DATE_STR y CONFIG_END_DATE_STR.")
            sys.exit(1)

    # Validar formato y orden de fechas
    try:
        fecha_inicio_dt = datetime.strptime(fecha_inicio, "%Y-%m-%d")
        fecha_fin_dt = datetime.strptime(fecha_fin, "%Y-%m-%d")
    except ValueError:
        print("❌ Formato de fecha inválido. Usar YYYY-MM-DD")
        sys.exit(1)

    if fecha_inicio_dt > fecha_fin_dt:
        print("❌ fecha_inicio no puede ser mayor que fecha_fin.")
        sys.exit(1)

    custom_queries = [q.strip() for q in args.queries if q and q.strip()]
    if custom_queries:
        print(f"🧩 Usando queries personalizadas: {custom_queries}")
    else:
        print("🧩 Usando queries por defecto del script.")
    
    # Crear y ejecutar extractor
    extractor = TwitterExtractorIAD(
        fecha_inicio,
        fecha_fin,
        custom_queries=custom_queries,
        output_base_dir=Path(args.output_dir),
        state_path=Path(args.state_path),
        max_tweets=args.max_tweets,
        max_replies_per_tweet=args.max_replies_per_tweet,
        max_reply_scrolls=args.max_reply_scrolls,
        headless=args.headless,
        create_output_dir=not args.dry_run,
    )
    if args.dry_run:
        print(f"🔐 Estado del navegador: {extractor.state_path}")
        print("🧪 Dry-run: no se crearon carpetas ni se abrió Playwright.")
        return
    success = asyncio.run(extractor.run_extraction())
    
    if success:
        print(f"🎉 Extracción Twitter completada para {fecha_inicio} - {fecha_fin}")
    else:
        print(f"❌ Falló extracción Twitter para {fecha_inicio} - {fecha_fin}")
        sys.exit(1)

if __name__ == "__main__":
    main()
