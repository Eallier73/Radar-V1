# Preprocesamiento vigente

Estos seis programas forman la etapa operativa de CSV→TXT:

| Programa | Propósito |
| --- | --- |
| `limpiar_youtube_semanal.py` | Derivar el CSV procesado de YouTube. |
| `limpiar_twitter_semanal.py` | Derivar el CSV procesado de Twitter y aplicar su alcance por cuentas. |
| `procesar_facebook_semanal.py` | Derivar el CSV procesado de Facebook, conservando las excepciones históricas de fecha registradas por procedencia. |
| `procesar_medios_semanal.py` | Derivar el CSV procesado de Medios cuando existe un CSV de entrada; no transforma los TXT históricos. |
| `promover_csv_a_texto.py` | Derivar TXT limpios desde los CSV procesados, sin modificar los CSV. |
| `validar_homogeneidad_semanal.py` | Validar contratos semanales y correspondencia CSV/TXT. |

`scr/extraccion/run_extraccion.py` coordina los procesadores, la promoción y
la validación. `scr/compartido/00_orquestador_general.py` también ofrece la
promoción como etapa independiente. La limpieza textual se describe en
[README_promocion_csv_a_texto.md](README_promocion_csv_a_texto.md).

El código histórico retirado y los TXT antiguos se conservan en `trash/`;
no deben usarse como alternativa al flujo vigente.

## Preparación de indicadores para el análisis

`preparar_indicadores_semanales.py` recupera las tres funciones de preparación
de tablas del notebook `Modelo_ML_MV.ipynb`: detección de columnas, ordenación,
selección de variables y estandarización. Recibe indicadores ya calculados;
no transforma TXT en indicadores ni calcula `MA5`. Es un módulo de uso explícito,
sin ejecución automática en el flujo CSV→TXT. Su procedencia, reglas y límites
se documentan en [PREPARACION_DATOS_NOTEBOOK.md](../../documentos/PREPARACION_DATOS_NOTEBOOK.md).

## Material antiguo archivado

Los filtros `boots_facebook.py`, `boots_youtube.py`, `limpieza_boots_twitter.py`
y el notebook `Scraping_Limpieza_Preprocesing_Data.ipynb` se archivaron con
autorización del usuario en `trash/2026-10-26/scr/preprocesamiento/`.
Sus heurísticas de bots y experimentos se conservan íntegros, pero no forman
parte del pipeline ni se ejecutan automáticamente.
