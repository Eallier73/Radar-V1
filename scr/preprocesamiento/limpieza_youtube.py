#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import csv
import string

# ================== CONFIGURA AQUÍ ==================
CARPETA_ORIGEN = "/home/emilio/Documentos/Lab/tampico_env/Proyectos/IPSEL_Tampico/Ml_Monica_Villarreal/Datos/Youtube/"
CARPETA_DESTINO = CARPETA_ORIGEN  # mismo directorio
NOMBRE_MASTER = "Youtube_MV_Todo_Limpio.csv"
# ====================================================

def normalizar_texto(texto):
    """
    Normaliza el texto:
    - Cambia vocales con acento por vocales sin acento y ñ por n
    - Convierte a minúsculas
    - Elimina URLs, http, https, com y .com
    - Elimina signos de puntuación y números
    - Elimina caracteres no ASCII
    """
    if texto is None:
        return ""

    # Cambiar vocales con acento por vocales sin acento y ñ por n
    reemplazos = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'Á': 'a', 'É': 'e', 'Í': 'i', 'Ó': 'o', 'Ú': 'u',
        'ñ': 'n', 'Ñ': 'n'
    }
    for original, reemplazo in reemplazos.items():
        texto = texto.replace(original, reemplazo)

    # Convertir a minúsculas
    texto = texto.lower()

    # Eliminar http, https y com
    texto = re.sub(r'https?:\/\/\S*', ' ', texto)   # Elimina URLs que comienzan con http:// o https://
    texto = re.sub(r'\bhttp\b', ' ', texto)         # Elimina la palabra http
    texto = re.sub(r'\bhttps\b', ' ', texto)        # Elimina la palabra https
    texto = re.sub(r'\bcom\b', ' ', texto)          # Elimina la palabra com
    texto = re.sub(r'\.\s*com\b', ' ', texto)       # Elimina .com

    # Eliminar signos de puntuación y números
    texto = re.sub(r'[' + string.punctuation + string.digits + ']', ' ', texto)

    # Eliminar caracteres no ASCII
    texto = ''.join(c for c in texto if ord(c) < 128)

    # Quitar espacios extra al principio y final
    texto = texto.strip()

    return texto

def procesar_archivo_csv_youtube(ruta_csv, carpeta_destino):
    """
    Procesa un archivo Youtube_MV_MES_AÑO.csv:
    - Elimina la columna 'query'
    - Limpia 'comment_text'
    - Mantiene 'published_at' intacta
    - Elimina filas duplicadas y vacías
    - Guarda Youtube_MV_MES_AÑO_Limpio.csv
    Devuelve la lista de filas [comment_text_limpio, published_at] para el master.
    """
    nombre_archivo = os.path.basename(ruta_csv)
    nombre_base, ext = os.path.splitext(nombre_archivo)

    # No reprocesar archivos ya limpios
    if nombre_base.lower().endswith("_limpio"):
        print(f"Saltando (ya limpio): {nombre_archivo}")
        return []

    ruta_salida = os.path.join(
        carpeta_destino,
        f"{nombre_base}_Limpio.csv"
    )

    print(f"Procesando: {nombre_archivo}")
    filas_limpias = []

    try:
        with open(ruta_csv, 'r', encoding='utf-8', errors='ignore', newline='') as f_in:
            lector = csv.reader(f_in)
            encabezados = next(lector, None)

            if not encabezados:
                print(f"  [AVISO] Archivo vacío o sin encabezados: {ruta_csv}")
                return []

            # Normalizar encabezados (quitar BOM, espacios, etc.)
            encabezados_norm = []
            for h in encabezados:
                h_clean = h.replace("\ufeff", "")  # quitar BOM si viene
                h_clean = h_clean.strip()
                encabezados_norm.append(h_clean)

            # Buscar índices de columnas usando encabezados normalizados
            idx_query = None
            idx_comment = None
            idx_published = None

            for i, h in enumerate(encabezados_norm):
                h_low = h.lower()
                if h_low == "query":
                    idx_query = i
                elif h_low in ("comment_text", "comment", "texto", "text"):
                    idx_comment = i
                elif h_low in ("published_at", "fecha", "date", "created_at"):
                    idx_published = i

            # Si no encontramos por nombre, asumimos estructura [query, comment, published_at]
            if idx_comment is None or idx_published is None:
                if len(encabezados_norm) >= 3:
                    # Suponiendo: 0 = comment_text, 1 = published_at, 2 = query
                    print("  [AVISO] Usando índices fijos (0=comment, 1=published_at, 2=query)")
                    idx_comment = 0
                    idx_published = 1
                    if len(encabezados_norm) > 2:
                        idx_query = 2
                else:
                    print(f"  [ERROR] No se pudieron determinar columnas de comentario y fecha en {nombre_archivo}")
                    return []

            # Preparamos escritura: solo dos columnas: comment_text, published_at
            with open(ruta_salida, 'w', encoding='utf-8', newline='') as f_out:
                escritor = csv.writer(f_out)
                escritor.writerow(["comment_text", "published_at"])

                vistos = set()
                filas_entrada = 0
                filas_salida = 0

                for fila in lector:
                    filas_entrada += 1
                    # Proteger filas cortas
                    if len(fila) <= max(idx_comment, idx_published):
                        continue

                    comentario_original = fila[idx_comment]
                    fecha = fila[idx_published]

                    comentario_limpio = normalizar_texto(comentario_original)

                    # Eliminar filas cuyo comentario quede vacío
                    if not comentario_limpio:
                        continue

                    clave = (comentario_limpio, fecha)
                    if clave in vistos:
                        # Duplicado: misma combinación comentario+fecha
                        continue
                    vistos.add(clave)

                    escritor.writerow([comentario_limpio, fecha])
                    filas_limpias.append([comentario_limpio, fecha])
                    filas_salida += 1

        print(f"  -> Filas leídas: {filas_entrada}, filas escritas (no vacías y no duplicadas): {filas_salida}")
        print(f"  -> Archivo limpio: {ruta_salida}")
        return filas_limpias

    except Exception as e:
        print(f"  [ERROR] Al procesar {ruta_csv}: {e}")
        return []

def procesar_todos_los_archivos():
    """
    Procesa todos los Youtube_MV_MES_AÑO.csv en CARPETA_ORIGEN
    y crea un master Youtube_MV_Todo_Limpio.csv en CARPETA_DESTINO.
    """
    if not os.path.exists(CARPETA_ORIGEN):
        print(f"La carpeta de origen no existe: {CARPETA_ORIGEN}")
        return

    if not os.path.exists(CARPETA_DESTINO):
        os.makedirs(CARPETA_DESTINO, exist_ok=True)

    # Tomamos todos los CSV que parezcan de YouTube MV (y evitamos ya limpios)
    archivos_csv = sorted(
        f for f in os.listdir(CARPETA_ORIGEN)
        if f.lower().endswith(".csv") and "youtube_mv_" in f.lower() and "_limpio" not in f.lower()
    )

    if not archivos_csv:
        print(f"No se encontraron archivos Youtube_MV_*.csv en {CARPETA_ORIGEN}")
        return

    master_rows = []
    for nombre in archivos_csv:
        ruta = os.path.join(CARPETA_ORIGEN, nombre)
        filas = procesar_archivo_csv_youtube(ruta, CARPETA_DESTINO)
        master_rows.extend(filas)

    # Crear master: Youtube_MV_Todo_Limpio.csv
    if not master_rows:
        print("No se generaron filas limpias; no se crea archivo master.")
        return

    # Eliminar duplicados también a nivel global (entre meses)
    vistos_global = set()
    filas_master_final = []
    for comentario, fecha in master_rows:
        clave = (comentario, fecha)
        if clave in vistos_global:
            continue
        vistos_global.add(clave)
        filas_master_final.append([comentario, fecha])

    ruta_master = os.path.join(CARPETA_DESTINO, NOMBRE_MASTER)
    with open(ruta_master, 'w', encoding='utf-8', newline='') as f_master:
        escritor = csv.writer(f_master)
        escritor.writerow(["comment_text", "published_at"])
        escritor.writerows(filas_master_final)

    print("\n=== RESUMEN ===")
    print(f"Archivos procesados: {len(archivos_csv)}")
    print(f"Filas totales en master (sin duplicados, sin vacías): {len(filas_master_final)}")
    print(f"Archivo master creado: {ruta_master}")

def main():
    procesar_todos_los_archivos()

if __name__ == "__main__":
    main()
