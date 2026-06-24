#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Limpia la columna 'message' de todos los CSV en un directorio:

- Cambia vocales con acento por vocales sin acento
- Cambia ñ / Ñ por n
- Elimina todos los signos de puntuación
- Elimina todos los números EXCEPTO el 4
- Elimina URLs (http, https, www, etc.)
- Convierte todo a minúsculas
- Quita emojis y cualquier caracter no ASCII (distinto de letras, espacio y 4)
- Elimina filas donde 'message' quede vacío tras la limpieza
- Elimina filas duplicadas dentro de cada archivo
  (mismo 'message' limpio + mismo 'created_time')

Solo se modifica la columna 'message'. 'created_time' y el resto de columnas
se conservan idénticas.

Para cada archivo de entrada X.csv genera:
  X_Limpios.csv  en OUT_DIR

Además crea un archivo maestro en OUT_DIR:
  Facebook_Todo_Limpios.csv
que concatena todas las filas limpias de todos los archivos.
"""

from pathlib import Path
import csv
import re

# ==== CONFIGURA AQUÍ TUS CARPETAS ====
INPUT_DIR = Path("/home/emilio/Documentos/Lab/tampico_env/Proyectos/IPSEL_Tampico/Ml_Monica_Villarreal/Datos/Facebook_Columnas/")
OUT_DIR   = Path("/home/emilio/Documentos/Lab/tampico_env/Proyectos/IPSEL_Tampico/Ml_Monica_Villarreal/Datos/Facebook_Limpios/")
MASTER_NAME = "Facebook_Todo_Limpios.csv"
# =====================================

# Traducción de acentos y ñ
TRANSLATION_TABLE = str.maketrans({
    "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
    "Á": "a", "É": "e", "Í": "i", "Ó": "o", "Ú": "u",
    "ñ": "n", "Ñ": "n"
})

# Regex para URLs
URL_RE = re.compile(r"(https?://\S+|www\.\S+)", re.IGNORECASE)

def limpiar_texto(texto: str) -> str:
    if texto is None:
        return ""
    
    # 1) Quitar acentos y ñ
    texto = texto.translate(TRANSLATION_TABLE)
    
    # 2) Eliminar URLs
    texto = URL_RE.sub(" ", texto)
    
    # 3) Pasar a minúsculas
    texto = texto.lower()
    
    # 4) Eliminar TODO lo que no sea letras minúsculas, espacio o el dígito 4
    #    (se van emojis, signos, otros dígitos, etc.)
    texto = re.sub(r"[^a-z4\s]", " ", texto)
    
    # 5) Colapsar espacios múltiples y recortar
    texto = re.sub(r"\s+", " ", texto).strip()
    
    return texto

def procesar_archivo(csv_path: Path):
    """
    Procesa un archivo individual.
    Devuelve (header, filas_limpias) para luego crear el master.
    Si el archivo se omite (vacío o sin 'message'), devuelve (None, []).
    """
    print(f"Procesando: {csv_path.name}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    out_path = OUT_DIR / f"{csv_path.stem}_Limpios.csv"

    cleaned_rows = []

    with csv_path.open("r", newline="", encoding="utf-8") as f_in, \
         out_path.open("w", newline="", encoding="utf-8") as f_out:
        
        reader = csv.reader(f_in)
        writer = csv.writer(f_out)

        try:
            header = next(reader)
        except StopIteration:
            print(f"  [AVISO] Archivo vacío, se omite: {csv_path.name}")
            return None, []

        writer.writerow(header)

        # Buscar índices de columnas
        try:
            idx_message = header.index("message")
        except ValueError:
            print(f"  [AVISO] No se encontró la columna 'message' en {csv_path.name}, se omite.")
            return None, []

        try:
            idx_time = header.index("created_time")
        except ValueError:
            idx_time = None  # Por si en algún archivo no está

        filas_entrada = 0
        filas_salida = 0
        vistos = set()  # para eliminar duplicados dentro del archivo

        for row in reader:
            filas_entrada += 1

            if not row:
                continue

            # Proteger filas cortas
            if len(row) <= idx_message:
                continue

            # Limpiar solo 'message'
            mensaje_limpio = limpiar_texto(row[idx_message])

            # Si el message queda vacío, no escribimos la fila
            if mensaje_limpio == "":
                continue

            # Construir clave para detectar duplicados dentro del archivo
            if idx_time is not None and len(row) > idx_time:
                clave = (mensaje_limpio, row[idx_time])
            else:
                clave = (mensaje_limpio,)

            if clave in vistos:
                # Fila duplicada, se omite
                continue
            vistos.add(clave)

            # Actualizar el message limpio
            row[idx_message] = mensaje_limpio

            writer.writerow(row)
            cleaned_rows.append(row)
            filas_salida += 1

    print(f"  -> Filas leídas: {filas_entrada}, filas escritas: {filas_salida}")
    print(f"  -> Salida: {out_path}")
    return header, cleaned_rows

def main():
    if not INPUT_DIR.exists():
        print(f"La carpeta de entrada no existe: {INPUT_DIR}")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    archivos = sorted(INPUT_DIR.glob("*.csv"))
    if not archivos:
        print(f"No se encontraron CSV en {INPUT_DIR}")
        return

    master_header = None
    master_rows = []

    for path in archivos:
        header, rows = procesar_archivo(path)
        if header is None:
            continue

        if master_header is None:
            master_header = header
        elif header != master_header:
            print(f"  [AVISO] Encabezado distinto en {path.name}; se agregan al master tal cual.")

        master_rows.extend(rows)

    # Crear archivo master combinado
    if master_header is not None and master_rows:
        master_path = OUT_DIR / MASTER_NAME
        with master_path.open("w", newline="", encoding="utf-8") as f_master:
            writer = csv.writer(f_master)
            writer.writerow(master_header)
            writer.writerows(master_rows)
        print(f"\nMaster combinado creado: {master_path} ({len(master_rows)} filas)")
    else:
        print("No se generó master combinado (no hubo filas limpias).")

if __name__ == "__main__":
    main()
