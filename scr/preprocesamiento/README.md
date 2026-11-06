# Preprocesamiento vigente

Sólo estos seis programas forman la etapa operativa:

| Programa | Propósito |
| --- | --- |
| `limpiar_youtube_semanal.py` | Derivar el CSV procesado de YouTube. |
| `limpiar_twitter_semanal.py` | Derivar el CSV procesado de Twitter y aplicar su alcance por cuentas. |
| `procesar_facebook_semanal.py` | Derivar el CSV procesado de publicaciones y comentarios de Facebook. |
| `procesar_medios_semanal.py` | Derivar el CSV procesado de Medios cuando existe un CSV de entrada; no transforma los TXT históricos. |
| `promover_csv_a_texto.py` | Derivar TXT limpios desde los CSV procesados, sin modificar los CSV. |
| `validar_homogeneidad_semanal.py` | Validar contratos semanales y correspondencia CSV/TXT. |

`scr/extraccion/run_extraccion.py` coordina los procesadores, la promoción y
la validación. `scr/compartido/00_orquestador_general.py` también ofrece la
promoción como etapa independiente. La limpieza textual se describe en
[README_promocion_csv_a_texto.md](README_promocion_csv_a_texto.md).

El código histórico retirado y los TXT antiguos se conservan en `trash/`;
no deben usarse como alternativa al flujo vigente.

## Material antiguo archivado

Los filtros `boots_facebook.py`, `boots_youtube.py`, `limpieza_boots_twitter.py`
y el notebook `Scraping_Limpieza_Preprocesing_Data.ipynb` se archivaron con
autorización del usuario en `trash/2026-10-26/scr/preprocesamiento/`.
Sus heurísticas de bots y experimentos se conservan íntegros, pero no forman
parte del pipeline ni se ejecutan automáticamente.
