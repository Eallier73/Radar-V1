# Preprocesamiento vigente

Esta carpeta reúne los cuatro procesadores por fuente, la promoción CSV→TXT y la validación. El procesamiento léxico de indicadores está en NLP:

| Programa | Propósito |
| --- | --- |
| `procesar_youtube_semanal_Radar_V1.py` | Derivar el CSV procesado de YouTube. |
| `procesar_twitter_semanal_Radar_V1.py` | Derivar el CSV procesado de Twitter y aplicar su alcance por cuentas. |
| `procesar_facebook_semanal_Radar_V1.py` | Derivar el CSV procesado de Facebook, conservando las excepciones históricas de fecha registradas por procedencia. |
| `procesar_medios_semanal_Radar_V1.py` | Derivar el CSV procesado de Medios cuando existe un CSV de entrada; no transforma los TXT históricos. |
| `promover_csv_a_texto_Radar_V1.py` | Derivar TXT limpios desde los CSV procesados, sin modificar los CSV. |
| `validar_homogeneidad_semanal_Radar_V1.py` | Validar contratos semanales y correspondencia CSV/TXT. |

`scr_Radar_V1/extraccion_Radar_V1/run_extraccion_Radar_V1.py` coordina los procesadores, la promoción y
la validación. `scr_Radar_V1/compartido_Radar_V1/00_orquestador_general_Radar_V1.py` también ofrece la
promoción como etapa independiente. La limpieza textual se describe en
[preprocesamiento_promocion_csv_a_texto_Radar_V1.md](preprocesamiento_promocion_csv_a_texto_Radar_V1.md).

El código histórico retirado y los TXT antiguos se conservan en `trash_Radar_V1/`;
no deben usarse como alternativa al flujo vigente.

## Preparación de indicadores para el análisis

Los indicadores se construyen en `scr_Radar_V1/nlp_Radar_V1/construir_tabla_indicadores_Radar_V1.py`
como tasas semanales ponderadas, sin suavizado ni rezagos adicionales.
La etapa **NLP · indicadores** del orquestador/GUI ejecuta directamente este
archivo; no hay un segundo `run_nlp_Radar_V1.py`. Su alcance es el histórico completo
de 83 semanas y las cuatro fuentes, independiente del periodo de extracción.
Si no existe la salida, la genera. Con `--reuse-existing`, usado por la GUI,
comprueba hashes de corpus, diccionarios y productos antes de reutilizar una
tabla existente, sin reescribirla. Si hay diferencias, falla conservando los
archivos para evitar reemplazar tablas y particiones de forma silenciosa.

`preparar_indicadores_semanales.py` se archivó íntegro en `trash_Radar_V1/respaldos_historico_Radar_V1/`
porque ajustaba escalas sobre toda la tabla. La selección vigente ajusta pesos
y escalas dentro de cada corte temporal. Su alcance y el respaldo se documentan
en [PREPARACION_DATOS_NOTEBOOK_Radar_V1.md](../../documentos_Radar_V1/PREPARACION_DATOS_NOTEBOOK_Radar_V1.md).

## Material antiguo archivado

Los filtros `boots_facebook.py`, `boots_youtube.py`, `limpieza_boots_twitter.py`
y el notebook `Scraping_Limpieza_Preprocesing_Data.ipynb` se archivaron con
autorización del usuario en `trash_Radar_V1/2026-10-26_historico_Radar_V1/scr_historico_Radar_V1/preprocesamiento_historico_Radar_V1/`.
Sus heurísticas de bots y experimentos se conservan íntegros, pero no forman
parte del pipeline ni se ejecutan automáticamente.
