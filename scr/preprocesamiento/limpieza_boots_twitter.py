#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Normaliza y filtra un archivo de Twitter ya consolidado.

Entrada:
    /home/emilio/Documentos/Lab/tampico_env/Proyectos/IPSEL_Tampico/Ml_Monica_Villarreal/Datos/Twitter_Limpieza/
        X_Twitter_Todo_Ordenado_Homologados_Semanas.csv

Estructura esperada:
    columna 'comentario'
    columna 'semana_publicacion'

Salida:
    Mismo directorio, mismo nombre pero con sufijo _1:
        X_Twitter_Todo_Ordenado_Homologados_Semanas_1.csv

Lo que hace:
    - Normaliza texto:
        * pasa a minúsculas
        * quita URLs + tokens http, https, com, .com
        * cambia vocales con acento por vocales sin acento y ñ por n
        * elimina signos de puntuación y números
        * elimina caracteres no ASCII
        * colapsa espacios
    - Aplica filtro tipo anti-bots / anti-ruido
      (muchos links, muchos hashtags, muchas menciones, demasiados emojis,
       mensajes vacíos, duplicados exactos).
"""

import csv
import os
import re
import unicodedata
from pathlib import Path

# ================= CONFIGURA AQUÍ =================
CARPETA = Path(
    "/home/emilio/Documentos/Lab/tampico_env/Proyectos/IPSEL_Tampico/Ml_Monica_Villarreal/Datos/X_Twitter_Limpieza/"
)
NOMBRE_ENTRADA = "X_Twitter_Todo_Ordenado_Homologados_Semanas.csv"
# ==================================================


# ---------- Normalización básica de texto ----------

RE_URL = re.compile(r"https?://\S+|www\.\S+|t\.co/\S+", re.IGNORECASE)
RE_MULTIESP = re.compile(r"\s+")
# eliminar tokens http, https, com y .com que se escapen
RE_HTTP_COM = re.compile(r"\bhttps?\b|\bwww\b|\bcom\b|\.com\b", re.IGNORECASE)

# tabla de traducción para acentos y ñ
MAP_CHARS = str.maketrans({
    "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
    "Á": "a", "É": "e", "Í": "i", "Ó": "o", "Ú": "u",
    "à": "a", "è": "e", "ì": "i", "ò": "o", "ù": "u",
    "À": "a", "È": "e", "Ì": "i", "Ò": "o", "Ù": "u",
    "ä": "a", "ë": "e", "ï": "i", "ö": "o", "ü": "u",
    "Ä": "a", "Ë": "e", "Ï": "i", "Ö": "o", "Ü": "u",
    "ñ": "n", "Ñ": "n"
})

def normalizar_texto(texto: str) -> str:
    """
    Normalización extendida:
    - pasa a str
    - quita control chars y normaliza unicode
    - quita URLs + http/https/com/.com
    - minúsculas
    - cambia vocales acentuadas por no acentuadas y ñ por n
    - elimina caracteres no ASCII
    - elimina signos de puntuación y números
    - colapsa espacios
    """
    if texto is None:
        return ""
    t = str(texto)

    # Normalización unicode
    t = unicodedata.normalize("NFKC", t)

    # Eliminar saltos de línea y tabs
    t = t.replace("\r", " ").replace("\n", " ").replace("\t", " ")

    # Eliminar URLs completas
    t = RE_URL.sub(" ", t)

    # Eliminar tokens http, https, com, .com que queden sueltos
    t = RE_HTTP_COM.sub(" ", t)

    # Minúsculas
    t = t.lower()

    # Reemplazar acentos y ñ
    t = t.translate(MAP_CHARS)

    # Eliminar caracteres no ASCII explícitamente
    t = t.encode("ascii", "ignore").decode("ascii")

    # Eliminar signos de puntuación y números
    # (dejamos solo letras a-z y espacios)
    t = re.sub(r"[^a-z\s]", " ", t)

    # Colapsar espacios
    t = RE_MULTIESP.sub(" ", t).strip()

    return t


# ---------- Heurísticas tipo anti-bots ----------

RE_HASHTAG = re.compile(r"#\w+")
RE_MENCION = re.compile(r"@\w+")
# Emojis / símbolos pictográficos básicos
RE_EMOJI = re.compile(
    "["u"\U0001F300-\U0001F6FF"
     u"\U0001F900-\U0001F9FF"
     u"\U0001F1E0-\U0001F1FF"
     u"\u2600-\u26FF"
     u"\u2700-\u27BF""]",
    flags=re.UNICODE,
)

def marcar_ruido(mensaje_norm: str) -> list:
    """
    Devuelve una lista de 'razones' por las que el mensaje se considera ruido.
    Si la lista está vacía -> consideramos que el mensaje es válido.
    """
    razones = []

    m = mensaje_norm

    if not m or len(m) < 3:
        razones.append("muy_corto")

    # Muchos links (después de normalizar ya no debería haber, pero por si acaso)
    urls = len(RE_URL.findall(m))
    if urls >= 2:
        razones.append("muchos_links")
    elif urls == 1 and len(m.split()) <= 2:
        razones.append("solo_link")

    # Hashtags
    hashtags = len(RE_HASHTAG.findall(m))
    if hashtags >= 5:
        razones.append("muchos_hashtags")

    # Menciones
    menciones = len(RE_MENCION.findall(m))
    if menciones >= 5:
        razones.append("muchas_menciones")

    # Emojis
    emojis = len(RE_EMOJI.findall(m))
    if emojis > 0:
        emoji_ratio = emojis / max(1, len(m))
        if emoji_ratio > 0.4:
            razones.append("demasiados_emojis")

    # Mensajes solo con hashtags o menciones
    sin_hash_mention = RE_HASHTAG.sub(" ", m)
    sin_hash_mention = RE_MENCION.sub(" ", sin_hash_mention).strip()
    if not sin_hash_mention:
        razones.append("solo_hashtags_menciones")

    return razones


def main():
    entrada = CARPETA / NOMBRE_ENTRADA
    if not entrada.exists():
        raise FileNotFoundError(f"No encuentro el archivo de entrada: {entrada}")

    salida = CARPETA / NOMBRE_ENTRADA.replace(".csv", "_1.csv")

    print(f"Entrada : {entrada}")
    print(f"Salida  : {salida}")

    total = 0
    guardadas = 0
    duplicadas = 0
    ruido = 0

    vistos = set()  # para eliminar duplicados exactos del comentario normalizado

    with open(entrada, "r", encoding="utf-8", newline="") as f_in, \
         open(salida, "w", encoding="utf-8", newline="") as f_out:

        lector = csv.DictReader(f_in)
        # Ajustamos nombres de columnas según tu archivo
        if "comentario" not in lector.fieldnames or "semana_publicacion" not in lector.fieldnames:
            raise ValueError(
                f"El archivo debe tener columnas 'comentario' y 'semana_publicacion'. "
                f"Columnas encontradas: {lector.fieldnames}"
            )

        campos_out = ["comentario", "semana_publicacion"]
        escritor = csv.DictWriter(f_out, fieldnames=campos_out)
        escritor.writeheader()

        for fila in lector:
            total += 1
            comentario = fila.get("comentario", "")
            fecha = fila.get("semana_publicacion", "")

            comentario_norm = normalizar_texto(comentario)

            # descartar mensajes vacíos tras normalización
            if not comentario_norm:
                ruido += 1
                continue

            # descartar ruido (bots / spam)
            razones = marcar_ruido(comentario_norm)
            if razones:
                ruido += 1
                continue

            # eliminar duplicados exactos de comentario_normalizado
            clave = (comentario_norm, fecha)
            if clave in vistos:
                duplicadas += 1
                continue
            vistos.add(clave)

            # Guardamos el comentario normalizado
            escritor.writerow({
                "comentario": comentario_norm,
                "semana_publicacion": fecha
            })
            guardadas += 1

    print("\n=== RESUMEN TWITTER ===")
    print(f"Total filas leídas   : {total}")
    print(f"Filas ruido/bots     : {ruido}")
    print(f"Filas duplicadas     : {duplicadas}")
    print(f"Filas guardadas limp.: {guardadas}")
    print(f"Archivo limpio creado: {salida}")

if __name__ == "__main__":
    main()
