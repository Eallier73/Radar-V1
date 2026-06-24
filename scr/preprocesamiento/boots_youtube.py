#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Filtro anti-bots v3.2 (Facebook / YouTube)
- Lee archivos con columnas: comment_text, published_at
- Duplicado/ráfaga evaluados POR ARCHIVO
- Umbrales adaptativos por tamaño
- Regla de 1 link afinada (≤2 tokens y no host “seguro”)
- Two-pass + tercer pass antipico
- Elimina siempre filas que contengan la palabra "dios"
- Log global único
"""

import csv
import re
import unicodedata
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter, defaultdict

# ===== RUTAS =====
SRC = Path("/home/emilio/Documentos/Lab/tampico_env/Proyectos/IPSEL_Tampico/Ml_Monica_Villarreal/Datos/Youtube_Columnas/")
DST = Path("/home/emilio/Documentos/Lab/tampico_env/Proyectos/IPSEL_Tampico/Ml_Monica_Villarreal/Datos/Youtube_Limpieza_Bots/")

# ===== PARÁMETROS (base) =====
UMBRAL_BOT_BASE = 4
VENTANA_MINUTOS_RAFAGA = 2
MAX_LEN_PALABRA = 40
MAX_LEN_MSG = 2000
TOP_DUP_SHOW = 50
SAMPLES_FLAGGED = 200

THIRD_PASS_MIN_IMPROV_PP = 3.0
THIRD_PASS_ENABLE = True

# Whitelist de hosts “seguros”
SAFE_HOSTS_EXPANDED = True
SAFE_LINK_HOSTS_BASE = ("facebook.com","fb.watch","instagram.com","youtu.be","youtube.com")
SAFE_LINK_HOSTS_EXTRA = (
    "l.facebook.com","m.facebook.com","fb.com","instagram.",
    "x.com","twitter.com"
)
SAFE_LINK_HOSTS = SAFE_LINK_HOSTS_BASE + (SAFE_LINK_HOSTS_EXTRA if SAFE_HOSTS_EXPANDED else ())

SPAM_KEYWORDS = {
    "gana","promo","promoción","oferta","descuento","regístrate","suscríbete",
    "bit.ly","t.me","wa.me","whatsapp","telegram","inversión","invierte",
    "cripto","crypto","bono","click","haz clic","http","https",
    "trabaja desde casa","ingresos","contacta","enlace"
}

# ===== REGEX =====
RE_URL = re.compile(r"https?://\S+", re.IGNORECASE)
RE_HASHTAG = re.compile(r"(?:^|\s)#\w+", re.UNICODE)
RE_MENCION = re.compile(r"(?:^|\s)@\w+", re.UNICODE)
RE_DIGITS = re.compile(r"\d")
RE_PHONE = re.compile(r"(?:\+?\d[\s\-\.]?){8,}")
RE_MULTI_CHAR = re.compile(r"(.)\1{2,}", re.UNICODE)
RE_EMOJI = re.compile(
    "["                     
    "\U0001F300-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\U00002700-\U000027BF"
    "\U00002600-\U000026FF"
    "]", flags=re.UNICODE
)

FORMATOS_FECHA = [
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%d %H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
]

# ===== UTILIDADES =====
def fix_tz(s: str) -> str:
    if not s: return s
    s = s.strip()
    if s.endswith("Z"):
        return s[:-1] + "+0000"
    if len(s) >= 6 and (s[-6] in "+-" and s[-3] == ":"):
        return s[:-3] + s[-2:]
    if "T" in s and ("+" not in s and "Z" not in s[-1:]):
        return s + "+0000"
    return s

def parse_dt(s: str):
    if not s: return None
    s2 = fix_tz(s)
    for fmt in FORMATOS_FECHA:
        try:
            dt = datetime.strptime(s2, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            continue
    return None

def strip_accents(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))

def norm_text(s: str) -> str:
    if s is None: return ""
    s = s.strip()
    if len(s) > MAX_LEN_MSG:
        s = s[:MAX_LEN_MSG]
    s = strip_accents(s).lower()
    s = re.sub(r"\s+", " ", s)
    return s

def features(msg: str):
    razones = []
    m = msg or ""
    m_norm = norm_text(m)

    urls = len(RE_URL.findall(m))
    if urls >= 2:
        razones.append("muchos_links")
    elif urls == 1:
        razones.append("link")

    hashtags = len(RE_HASHTAG.findall(m))
    if hashtags >= 3:
        razones.append("muchos_hashtags")

    menciones = len(RE_MENCION.findall(m))
    if menciones >= 3:
        razones.append("muchas_menciones")

    emojis = len(RE_EMOJI.findall(m))
    emoji_ratio = emojis / max(1, len(m))
    if emoji_ratio > 0.2 and len(m) > 10:
        razones.append("emoji_excesivo")

    letras = [c for c in m if c.isalpha()]
    mayus_ratio = sum(1 for c in letras if c.isupper()) / max(1, len(letras))
    if mayus_ratio > 0.7 and len(letras) >= 8:
        razones.append("mayus_excesivas")

    rep_runs = len(RE_MULTI_CHAR.findall(m))
    if rep_runs >= 2:
        razones.append("caracteres_repetidos")

    digits_ratio = len(RE_DIGITS.findall(m)) / max(1, len(m))
    if digits_ratio > 0.25:
        razones.append("muchos_digitos")

    if RE_PHONE.search(m) or "whatsapp" in m_norm or "wa.me" in m_norm:
        razones.append("telefono_whatsapp")

    toks = [t for t in re.split(r"[^\wáéíóúñü]+", m_norm) if t]
    toks = [t for t in toks if len(t) <= MAX_LEN_PALABRA]
    tok_count = len(toks)

    return {
        "urls": urls,
        "hashtags": hashtags,
        "menciones": menciones,
        "emoji_ratio": emoji_ratio,
        "mayus_ratio": mayus_ratio,
        "rep_runs": rep_runs,
        "digits_ratio": digits_ratio,
        "tok_count": tok_count,
        "norm": m_norm,
    }, razones

def puntuar(senales, razones_base, dup_count_local, rafaga_local, min_dup_local):
    score = 0
    razones = list(razones_base)

    # URLs
    if senales["urls"] >= 2:
        score += 2
    elif senales["urls"] == 1:
        norm = senales["norm"]
        has_safe = any(h in norm for h in SAFE_LINK_HOSTS)
        if senales["tok_count"] <= 2 and not has_safe:
            score += 2

    # Señales blandas
    if "muchos_hashtags" in razones: score += 1
    if "muchas_menciones" in razones: score += 1
    if "emoji_excesivo" in razones: score += 1
    if "mayus_excesivas" in razones: score += 1
    if "caracteres_repetidos" in razones: score += 1
    if "telefono_whatsapp" in razones: score += 2

    # Palabras de spam
    if any(k in senales["norm"] for k in SPAM_KEYWORDS):
        score += 1
        razones.append("palabra_spam")

    # Duplicado LOCAL
    if dup_count_local >= min_dup_local:
        score += 2
        razones.append(f"duplicado_local_x{dup_count_local}")

    # Ráfaga LOCAL
    if rafaga_local and (senales["urls"] >= 1 or "telefono_whatsapp" in razones or dup_count_local >= min_dup_local):
        score += 2
        razones.append("rafaga_temporal_local")

    return score, razones

# === Lectura robusta ===
ENCODINGS = ["utf-8", "utf-8-sig", "cp1252", "latin-1", "iso-8859-1"]

def _open_csv_any(path: Path):
    for enc in ENCODINGS:
        try:
            f = open(path, "r", encoding=enc, errors="strict", newline="")
            sample = f.read(65536); f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=[",",";","\t","|"])
            except csv.Error:
                dialect = csv.excel; dialect.delimiter = ","
            reader = csv.reader(f, dialect)
            headers = next(reader)
            return f, reader, headers, enc
        except UnicodeDecodeError:
            try:
                f = open(path, "r", encoding=enc, errors="replace", newline="")
                sample = f.read(65536); f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=[",",";","\t","|"])
                except csv.Error:
                    dialect = csv.excel; dialect.delimiter = ","
                reader = csv.reader(f, dialect)
                headers = next(reader)
                return f, reader, headers, enc + "+replace"
            except Exception:
                continue
        except Exception:
            continue
    f = open(path, "r", encoding="latin-1", errors="replace", newline="")
    reader = csv.reader(f)
    headers = next(reader, [])
    return f, reader, headers, "latin-1+replace"

def leer_csv(path: Path):
    """
    Lee filas [(comment_text, published_at)] y devuelve también el encoding usado.
    Acepta headers: comment_text/published_at o message/created_time.
    """
    f, reader, headers, enc = _open_csv_any(path)
    try:
        low = [(h or "").strip().lower() for h in headers]

        # índice del texto
        try:
            mi = low.index("comment_text")
        except ValueError:
            try:
                mi = low.index("message")
            except ValueError:
                mi = 0

        # índice del tiempo
        try:
            ti = low.index("published_at")
        except ValueError:
            try:
                ti = low.index("created_time")
            except ValueError:
                ti = 1

        filas = []
        for row in reader:
            if len(row) <= max(mi, ti):
                continue
            m = row[mi]
            t = row[ti]
            filas.append((m, t))
        return filas, enc
    finally:
        try:
            f.close()
        except Exception:
            pass

def escribir_limpio(dest_path: Path, filas):
    # Escribimos siempre con los nombres de la primera imagen:
    # comment_text, published_at
    with open(dest_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(["comment_text","published_at"])
        for m, t in filas:
            w.writerow([m, t])

def thresholds_for_file(nrows: int):
    if nrows < 300:
        min_dup = 6
        umbral = max(UMBRAL_BOT_BASE, 5)
    elif nrows < 10_000:
        min_dup = 8
        umbral = UMBRAL_BOT_BASE
    elif nrows < 30_000:
        min_dup = 10
        umbral = UMBRAL_BOT_BASE
    else:
        min_dup = 12
        umbral = UMBRAL_BOT_BASE
    return min_dup, umbral

def main_reason(reason: str) -> str:
    if reason.startswith("duplicado_local"):
        return "duplicado"
    if reason.startswith("rafaga_temporal"):
        return "rafaga"
    if reason in ("muchos_links","link"):
        return "links"
    if reason == "telefono_whatsapp":
        return "telefono_whatsapp"
    if reason == "palabra_spam":
        return "palabra_spam"
    if reason == "muchos_hashtags":
        return "muchos_hashtags"
    if reason == "muchas_menciones":
        return "muchas_menciones"
    if reason == "emoji_excesivo":
        return "emoji_excesivo"
    if reason == "mayus_excesivas":
        return "mayus_excesivas"
    if reason == "caracteres_repetidos":
        return "caracteres_repetidos"
    if reason == "contiene_dios":
        return "contiene_dios"
    return "otros"

def main():
    if not SRC.exists():
        print(f"ERROR: no existe la carpeta origen: {SRC}")
        return
    DST.mkdir(parents=True, exist_ok=True)

    archivos = sorted([p for p in SRC.glob("*.csv") if p.is_file()])
    if not archivos:
        print("No hay CSV en el origen.")
        return

    global_reason = Counter()
    global_score_hist = Counter()
    global_norm_counts = Counter()
    global_samples = []
    resumen_rows = []
    total_total = total_bots = total_clean = 0
    encodings_por_archivo = {}
    cache_filas = {}

    # Cache
    for path in archivos:
        filas, enc = leer_csv(path)
        cache_filas[path] = filas
        encodings_por_archivo[path.name] = enc
        for m, _ in filas:
            global_norm_counts[norm_text(m)] += 1

    for i, path in enumerate(archivos, 1):
        filas = cache_filas[path]

        local_norm_counts = Counter(norm_text(m) for m, _ in filas)
        local_times_by_norm = defaultdict(list)
        for m, t in filas:
            n = norm_text(m)
            dt = parse_dt(t)
            if dt:
                local_times_by_norm[n].append(dt)
        for n in local_times_by_norm:
            local_times_by_norm[n].sort()

        def en_rafaga_local(norma):
            ts = local_times_by_norm.get(norma, [])
            if len(ts) < 2: return False
            win = VENTANA_MINUTOS_RAFAGA * 60
            i2 = 0
            for j in range(1, len(ts)):
                if (ts[j] - ts[i2]).total_seconds() <= win:
                    return True
                i2 += 1
                if i2 == j:
                    i2 -= 1
            return False

        MIN_DUP_LOCAL, umbral_local = thresholds_for_file(len(filas))

        # PASS 1
        decisions_pass1 = []
        bots1 = 0
        dup_reason_count1 = 0
        for m, t in filas:
            sen, razones_base = features(m)
            dup_count_local = local_norm_counts.get(sen["norm"], 0)
            rafaga_hit = en_rafaga_local(sen["norm"])
            score, razones = puntuar(sen, razones_base, dup_count_local, rafaga_hit, MIN_DUP_LOCAL)

            # eliminar todo lo que contenga "dios"
            if re.search(r"\bdios\b", sen["norm"]):
                razones.append("contiene_dios")
                flag = True
            else:
                flag = (score >= umbral_local)

            if flag:
                bots1 += 1
                if any(r.startswith("duplicado_local_") for r in razones):
                    dup_reason_count1 += 1
            decisions_pass1.append((m, t, score, razones, flag))

        total = len(filas)
        pct1 = (bots1/total*100 if total else 0.0)
        dup_weight1 = (dup_reason_count1 / max(1, bots1)) if bots1 else 0.0
        need_relax = (pct1 > 45.0) and (dup_weight1 >= 0.60) and (len(filas) >= 10_000)

        final_decisions = decisions_pass1
        bots_final = bots1
        pct_final = pct1
        dup_weight_final = dup_weight1

        # PASS 2 (si hace falta)
        if need_relax:
            MIN_DUP_LOCAL_2 = MIN_DUP_LOCAL + 2
            decisions_pass2, bots2, dup_reason_count2 = [], 0, 0
            for m, t in filas:
                sen, razones_base = features(m)
                dup_count_local = local_norm_counts.get(sen["norm"], 0)
                rafaga_hit = en_rafaga_local(sen["norm"])
                score, razones = puntuar(sen, razones_base, dup_count_local, rafaga_hit, MIN_DUP_LOCAL_2)

                if re.search(r"\bdios\b", sen["norm"]):
                    razones.append("contiene_dios")
                    flag = True
                else:
                    flag = (score >= umbral_local)

                if flag:
                    bots2 += 1
                    if any(r.startswith("duplicado_local_") for r in razones):
                        dup_reason_count2 += 1
                decisions_pass2.append((m, t, score, razones, flag))

            pct2 = (bots2/total*100 if total else 0.0)
            if (pct1 - pct2) >= 5.0:
                final_decisions = decisions_pass2
                bots_final = bots2
                pct_final = pct2
                dup_weight_final = (dup_reason_count2 / max(1, bots2)) if bots2 else 0.0

            # PASS 3 (antipico)
            if THIRD_PASS_ENABLE and (pct_final > 40.0) and (dup_weight_final >= 0.60) and (len(filas) >= 10_000):
                MIN_DUP_LOCAL_3 = (MIN_DUP_LOCAL_2 if final_decisions is decisions_pass2 else MIN_DUP_LOCAL) + 2
                decisions_pass3, bots3, dup_reason_count3 = [], 0, 0
                for m, t in filas:
                    sen, razones_base = features(m)
                    dup_count_local = local_norm_counts.get(sen["norm"], 0)
                    rafaga_hit = en_rafaga_local(sen["norm"])
                    score, razones = puntuar(sen, razones_base, dup_count_local, rafaga_hit, MIN_DUP_LOCAL_3)

                    if re.search(r"\bdios\b", sen["norm"]):
                        razones.append("contiene_dios")
                        flag = True
                    else:
                        flag = (score >= umbral_local)

                    if flag:
                        bots3 += 1
                        if any(r.startswith("duplicado_local_") for r in razones):
                            dup_reason_count3 += 1
                    decisions_pass3.append((m, t, score, razones, flag))

                pct3 = (bots3/total*100 if total else 0.0)
                if (pct_final - pct3) >= THIRD_PASS_MIN_IMPROV_PP:
                    final_decisions = decisions_pass3
                    bots_final = bots3
                    pct_final = pct3
                    dup_weight_final = (dup_reason_count3 / max(1, bots3)) if bots3 else 0.0

        # Construir limpio
        out_clean = []
        for m, t, score, razones, flag in final_decisions:
            if flag:
                global_score_hist[score] += 1
                cats = set(main_reason(r) for r in razones)
                for cat in cats:
                    global_reason[cat] += 1
                if len(global_samples) < SAMPLES_FLAGGED:
                    global_samples.append((path.name, m[:2000], t, score, ";".join(razones)))
            else:
                out_clean.append((m, t))

        resumen_rows.append((path.name, total, bots_final, total-bots_final, f"{pct_final:.1f}%", encodings_por_archivo[path.name]))
        total_total += total
        total_bots += bots_final
        total_clean += (total - bots_final)

        # Nombre salida: *_Final.csv
        orig_stem = path.stem
        if orig_stem.endswith("_Limpios"):
            dest_stem = orig_stem[:-8] + "_Final"
        else:
            dest_stem = orig_stem + "_Final"
        dest_name = dest_stem + ".csv"

        escribir_limpio(DST / dest_name, out_clean)
        print(f"[{i:02d}/{len(archivos)}] {path.name} ({encodings_por_archivo[path.name]}) -> clean={len(out_clean):,}, bots={bots_final:,} ({pct_final:.1f}%)")

    # LOG GLOBAL
    log_path = DST / "SBots_LOG_global.csv"
    with open(log_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(["section","file","metric","value","aux","aux2","message","created_time","score","reasons"])

        for fname, total, bots, clean, pct, enc in resumen_rows:
            w.writerow(["summary", fname, "encoding", enc, "", "", "", "", "", ""])
            w.writerow(["summary", fname, "total", total, "", "", "", "", "", ""])
            w.writerow(["summary", fname, "bots", bots, "", "", "", "", "", ""])
            w.writerow(["summary", fname, "clean", clean, "", "", "", "", "", ""])
            w.writerow(["summary", fname, "pct_bots", pct, "", "", "", "", "", ""])

        w.writerow(["summary", "ALL", "total", total_total, "", "", "", "", "", ""])
        w.writerow(["summary", "ALL", "bots", total_bots, "", "", "", "", "", ""])
        w.writerow(["summary", "ALL", "clean", total_clean, "", "", "", "", "", ""])
        pct_global = f"{(total_bots/total_total*100 if total_total else 0):.1f}%"
        w.writerow(["summary", "ALL", "pct_bots", pct_global, "", "", "", "", "", ""])

        for reason, cnt in global_reason.most_common():
            w.writerow(["reason", "ALL", reason, cnt, "", "", "", "", "", ""])

        for score, cnt in sorted(global_score_hist.items()):
            w.writerow(["score_hist", "ALL", str(score), cnt, "", "", "", "", "", ""])

        for text, cnt in global_norm_counts.most_common(TOP_DUP_SHOW):
            if cnt < 6:
                break
            w.writerow(["dup_top", "ALL", "dup_count", cnt, "", "", text[:240], "", "", ""])

        for fname, m, t, s, rs in global_samples:
            w.writerow(["sample", fname, "", "", "", "", m[:240], t, s, rs])

    print("\nResumen global:")
    print(f"  total={total_total:,} | bots={total_bots:,} ({pct_global}) | clean={total_clean:,}")
    print(f"Log global: {log_path}")

if __name__ == "__main__":
    main()
