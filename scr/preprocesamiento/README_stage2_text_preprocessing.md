# Etapa 2 de Preprocessing de Texto

## Qué hace

Puente entre la extracción estructurada semanal en `.csv` y el corpus textual limpio semanal en `.txt`.

La etapa 2:

- localiza el CSV canónico por fuente y semana dentro de `Datos_RAdAR/<Fuente>/<semana>/`,
- extrae el material textual correcto,
- normaliza y limpia el texto,
- deduplica conservando orden,
- concatena el flujo textual completo,
- lo reconstruye en bloques consecutivos de 30 palabras,
- y archiva el resultado en `Datos_RadaR_Texto/<Fuente>_Semana_Texto/YY_WW_fuente.txt`.

## Qué no hace

- No hace NLP.
- No hace sentimiento.
- No hace temas.
- No hace embeddings.
- No hace features analíticas.
- No modifica los CSV fuente.

## Entradas canónicas por fuente

- Facebook:
  - archivo: `facebook_institutional_raw_<semana>.csv`
  - columna usada: `text`
  - criterio: incorpora `record_type=post_parent` y `record_type=comment`
  - justificación: incluye posts y comentarios juntos sin duplicar `post_text` en cada comentario

- Twitter:
  - archivo: `twitter_data_<semana>.csv`
  - columna usada: `tweet_text`

- YouTube:
  - archivo: `youtube_comentarios_<semana>.csv`
  - columna usada: `comment_text`

- Medios:
  - archivo: `media_articles_<semana>.csv`
  - columnas usadas: `article_title` + `article_text`
  - justificación: la lógica histórica de medios ya combinaba título y cuerpo antes de limpiar

## Cómo detecta semana ISO

La semana ISO se deriva del prefijo de fecha del nombre de carpeta semanal.

Ejemplo:

- carpeta: `2026-03-09_semana_09marzo_15marzo_26`
- fecha base: `2026-03-09`
- ISO: `2026-W11`
- archivo final: `26_11_<fuente>.txt`

Se aceptan filtros por:

- `YY_WW`
- `YYYY-Www`
- nombre completo de carpeta semanal

## Comportamiento histórico conservado

- conversión de acentos y caracteres especiales a ASCII
- minúsculas
- eliminación de URLs
- eliminación de puntuación
- eliminación de dígitos
- limpieza específica por fuente
- deduplicación exacta conservando orden
- concatenación completa del corpus limpio
- reconstrucción final en bloques consecutivos de 30 palabras

## Estructura vigente vs legado

La etapa 2 vigente consume únicamente:

- `Datos_RAdAR/Facebook/<semana>/`
- `Datos_RAdAR/Twitter/<semana>/`
- `Datos_RAdAR/YouTube/<semana>/`
- `Datos_RAdAR/Medios/<semana>/`

El directorio `Datos_RAdAR/Juntos/` queda como archivo legado de semanas antiguas y no forma parte del flujo actual de la etapa 2.

## Decisiones por ambigüedad real

- En Facebook existen varios CSV por semana. La etapa 2 usa `facebook_institutional_raw_<semana>.csv` como entrada canónica para corpus porque es el dataset semanal que reúne posts y comentarios en una sola tabla.
- En Medios el corpus se arma con `article_title + article_text` y no solo con `article_text`, para respetar la lógica histórica del extractor de medios.
- Si falta el CSV canónico publicado en la carpeta semanal, el runner intenta resolverlo por `manifest.json` y, en último caso, por una coincidencia exacta única dentro de `runs/`.
- En el repositorio existen `.txt` históricos con bloques de 35 palabras para Facebook y 25 para Twitter. El runner nuevo fija `30` por default porque ese es el contrato metodológico explícito pedido para la etapa 2 real.

## Artefactos de auditoría

Cada corrida deja en `Datos_RadaR_Texto/runs/<run_id>/`:

- `metadata_run.json`
- `parametros_run.json`
- `resumen_preprocessing.json`
- `auditoria_preprocessing.json`
- `auditoria_archivos.csv`
