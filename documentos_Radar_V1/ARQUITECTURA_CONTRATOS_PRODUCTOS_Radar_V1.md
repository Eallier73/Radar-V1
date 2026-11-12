# Radar V1: estructura, contratos, productos y control

Revisión: 2026-11-12. Documento de consulta del estado vigente; los registros de auditoría se conservan por separado.

## Panel de control

Abrir `abrir_gui_orquestador_Radar_V1.py`. Cada etapa tiene selección independiente, estado en pantalla y salida en la terminal en tiempo real. Se pueden preparar secuencias, simular sin descargas, ejecutar, detener y reiniciar desde una etapa elegida. El panel conserva el último estado y los registros de cada intento.

El perfil histórico utiliza el corpus existente. La semana seleccionada controla extracción y procesamiento semanal; NLP mantiene el contrato actual de 83 semanas/cuatro fuentes. Abrir la GUI no inicia descargas: el flujo comienza al pulsar Ejecutar. Los botones Pruebas y Actualizar documentación también usan el motor de control.

| Etapa | Entrada / operación | Programa | Estado |
|---|---|---|---|
| 1. Extracción | Descarga semanal de las fuentes seleccionadas. | `scr_Radar_V1/extraccion_Radar_V1/run_extraccion_Radar_V1.py` | Disponible |
| 2. Procesar CSV por fuente | Normaliza CSV; Facebook nuevo aplica fechas estrictas. | `scr_Radar_V1/preprocesamiento_Radar_V1/procesar_youtube_semanal_Radar_V1.py` | Disponible |
| 3. CSV → TXT | Limpieza ASCII; Medios: título y contenido desde CSV. | `scr_Radar_V1/preprocesamiento_Radar_V1/promover_csv_a_texto_Radar_V1.py` | Disponible |
| 4. Validar corpus | Contratos, fechas, cobertura y correspondencia CSV/TXT. | `scr_Radar_V1/preprocesamiento_Radar_V1/validar_homogeneidad_semanal_Radar_V1.py` | Disponible |
| 5. Balance y ponderaciones | Diagnóstico de fuentes; alpha=0.5 en indicadores con ajuste inicial de 56 semanas. | `scr_Radar_V1/operaciones_Radar_V1/analizar_balance_fuentes_Radar_V1.py` | Disponible |
| 6. NLP · tabla de indicadores | Diccionarios, Original y temas; 83 semanas/cuatro fuentes. | `scr_Radar_V1/nlp_Radar_V1/construir_tabla_indicadores_Radar_V1.py` | Disponible |
| 7. Separar 56 / 14 / 13 | Divide la tabla existente sin reajustar valores. | `scr_Radar_V1/operaciones_Radar_V1/generar_conjuntos_temporales_Radar_V1.py` | Disponible |
| 8. Inspección estadística | Descriptivos y regresiones exploratorias sólo con las 56 iniciales. | `scr_Radar_V1/operaciones_Radar_V1/inspeccionar_indicadores_Radar_V1.py` | Disponible |
| 9. Redundancia y selección | Horizontes 1–4; no abre prueba ni verificación. | `scr_Radar_V1/operaciones_Radar_V1/seleccionar_indicadores_Radar_V1.py` | Disponible |
| 10. Modelado | Pendiente: no hay modelo productivo aprobado. | `scr_Radar_V1/modelado_Radar_V1/run_modelado_Radar_V1.py` | Pendiente de implementar |
| 11. Tabla para tablero | Pendiente: salida del modelo para tablero. | `scr_Radar_V1/modelado_Radar_V1/run_insumo_tablero_Radar_V1.py` | Pendiente de implementar |
| 12. Tablero | Pendiente de implementación. | `scr_Radar_V1/tablero_Radar_V1/run_tablero_Radar_V1.py` | Pendiente de implementar |
| 13. Reporte | Pendiente de implementación. | `scr_Radar_V1/reporte_Radar_V1/run_reporte_Radar_V1.py` | Pendiente de implementar |

Simular comprueba programas y entradas disponibles y registra el plan. Si una entrada la produciría una etapa previa, se señala como prevista. La simulación no certifica descargas, sesiones remotas ni resultados estadísticos. Una etapa futura no implementada se bloquea; no se informa como terminada.

## Estructura y funciones

| Carpeta | Responsabilidad |
|---|---|
| `scr_Radar_V1/compartido_Radar_V1/` | Contratos, rutas, nombres, catálogo y motor del panel. |
| `scr_Radar_V1/extraccion_Radar_V1/` | Descarga por fuente. Facebook depende de posts antes de comentarios. |
| `scr_Radar_V1/preprocesamiento_Radar_V1/` | Cuatro procesadores CSV, promoción común y validación. |
| `scr_Radar_V1/nlp_Radar_V1/` | Constructor único de indicadores y notebook de referencia preservado. |
| `scr_Radar_V1/operaciones_Radar_V1/` | Balance, partición, inspección, selección y mantenimiento documental. |
| `tests_Radar_V1/` | Pruebas locales, incluido el motor y los controles de la GUI. |
| `datos_Radar_V1/` | Corpus, diccionarios, indicadores, particiones y resultados; archivos/carpetas sellados. |
| `documentos_Radar_V1/auditorias_Radar_V1/` | Sólo operaciones realmente realizadas o simulaciones identificadas como tales. |
| `state/ejecuciones_Radar_V1/` | Estados y terminal persistente de cada ejecución. |
| `trash_Radar_V1/` | Respaldos recuperables con `_historico_Radar_V1`; fuera de la ejecución. |

Cada README se llama `README_NOMBRE_DE_CARPETA.md`. Los scripts, datasets y carpetas de trabajo llevan `_Radar_V1`; Git, `.env` y el estado autenticado de X conservan sus nombres técnicos. Los proyectos externos no se modifican.

## Scripts vigentes y sus vínculos

| Script | Función | Importa módulos locales |
|---|---|---|
| `abrir_gui_orquestador_Radar_V1.py` | Lanzador visible de la GUI del pipeline Radar V1. |  |
| `scr_Radar_V1/compartido_Radar_V1/00_gui_orquestador_Radar_V1.py` | Panel maestro Radar V1: ejecutar, simular, vigilar y reanudar. | `control_flujo_Radar_V1` |
| `scr_Radar_V1/compartido_Radar_V1/00_orquestador_general_Radar_V1.py` | Catálogo del panel maestro y sus trece etapas de trabajo. | `control_flujo_Radar_V1`, `radar_paths_Radar_V1` |
| `scr_Radar_V1/compartido_Radar_V1/control_flujo_Radar_V1.py` | Motor único: planes, salida en vivo, estados, cancelación y auditorías. |  |
| `scr_Radar_V1/compartido_Radar_V1/facebook_data_contract_Radar_V1.py` | Contrato canónico y proyección histórica para Facebook en Radar V1. |  |
| `scr_Radar_V1/compartido_Radar_V1/facebook_historical_contract_Radar_V1.py` | Excepciones de fecha limitadas a registros historicos con procedencia. | `facebook_data_contract_Radar_V1`, `radar_paths_Radar_V1` |
| `scr_Radar_V1/compartido_Radar_V1/medios_data_contract_Radar_V1.py` | Contrato canónico para el material semanal de Medios de Radar V1. |  |
| `scr_Radar_V1/compartido_Radar_V1/output_naming_Radar_V1.py` | Convenciones de nombres para los artefactos semanales de Radar. |  |
| `scr_Radar_V1/compartido_Radar_V1/radar_paths_Radar_V1.py` | Rutas canónicas del repositorio Radar. |  |
| `scr_Radar_V1/compartido_Radar_V1/twitter_data_contract_Radar_V1.py` | Contrato común para material semanal de Twitter/X. |  |
| `scr_Radar_V1/compartido_Radar_V1/youtube_data_contract_Radar_V1.py` | Contrato común para material semanal de comentarios de YouTube. |  |
| `scr_Radar_V1/extraccion_Radar_V1/1_extractors_youtube_Radar_V1.py` | Extractor automatizado de YouTube | `output_naming_Radar_V1`, `radar_paths_Radar_V1`, `youtube_data_contract_Radar_V1` |
| `scr_Radar_V1/extraccion_Radar_V1/2_extractors_twitter_Radar_V1.py` | 2_extractors_twitter_Radar_V1.py - Extractor de Twitter/X | `output_naming_Radar_V1`, `radar_paths_Radar_V1`, `twitter_data_contract_Radar_V1` |
| `scr_Radar_V1/extraccion_Radar_V1/3_extractors_medios_Radar_V1.py` | ============================================================= | `medios_data_contract_Radar_V1`, `output_naming_Radar_V1`, `radar_paths_Radar_V1` |
| `scr_Radar_V1/extraccion_Radar_V1/4_extractors_facebook_posts_Radar_V1.py` | ╔═══════════════════════════════════════════════════════════════════════════╗ | `output_naming_Radar_V1`, `radar_paths_Radar_V1` |
| `scr_Radar_V1/extraccion_Radar_V1/5_extractors_facebook_comentarios_Radar_V1.py` | ╔═══════════════════════════════════════════════════════════════════════════╗ | `facebook_data_contract_Radar_V1`, `output_naming_Radar_V1`, `radar_paths_Radar_V1` |
| `scr_Radar_V1/extraccion_Radar_V1/run_extraccion_Radar_V1.py` | Runner de la etapa de extracción de Radar V1. | `facebook_data_contract_Radar_V1`, `output_naming_Radar_V1`, `radar_paths_Radar_V1` |
| `scr_Radar_V1/nlp_Radar_V1/construir_tabla_indicadores_Radar_V1.py` | Construye primero los indicadores de las 83 semanas, sin entrenar modelos. | `generar_conjuntos_temporales_Radar_V1` |
| `scr_Radar_V1/operaciones_Radar_V1/actualizar_documentacion_Radar_V1.py` | Actualiza documentación concisa y comprueba su correspondencia con cada commit. |  |
| `scr_Radar_V1/operaciones_Radar_V1/analizar_balance_fuentes_Radar_V1.py` | Diagnostica el corpus y propone pesos de fuente sin modificar CSV ni TXT. | `promover_csv_a_texto_Radar_V1`, `radar_paths_Radar_V1` |
| `scr_Radar_V1/operaciones_Radar_V1/generar_conjuntos_temporales_Radar_V1.py` | Divide la tabla de indicadores ya generada en 56/14/13, sin reajustes. |  |
| `scr_Radar_V1/operaciones_Radar_V1/inspeccionar_indicadores_Radar_V1.py` | Inspección y regresiones exploratorias sólo con entrenamiento. | `generar_conjuntos_temporales_Radar_V1` |
| `scr_Radar_V1/operaciones_Radar_V1/seleccionar_indicadores_Radar_V1.py` | Selecciona columnas para los cuatro horizontes usando sólo el bloque inicial. | `generar_conjuntos_temporales_Radar_V1`, `inspeccionar_indicadores_Radar_V1` |
| `scr_Radar_V1/preprocesamiento_Radar_V1/procesar_facebook_semanal_Radar_V1.py` | Homologa Facebook con fechas estrictas y excepciones historicas trazables. | `facebook_data_contract_Radar_V1`, `facebook_historical_contract_Radar_V1`, `output_naming_Radar_V1`, `radar_paths_Radar_V1` |
| `scr_Radar_V1/preprocesamiento_Radar_V1/procesar_medios_semanal_Radar_V1.py` | Convierte la extracción semanal de Medios en su CSV canónico procesado. | `medios_data_contract_Radar_V1`, `output_naming_Radar_V1`, `radar_paths_Radar_V1` |
| `scr_Radar_V1/preprocesamiento_Radar_V1/procesar_twitter_semanal_Radar_V1.py` | Homologa el material semanal existente de Twitter/X sin modificar el raw. | `radar_paths_Radar_V1`, `twitter_data_contract_Radar_V1` |
| `scr_Radar_V1/preprocesamiento_Radar_V1/procesar_youtube_semanal_Radar_V1.py` | Homologa temporalmente el material semanal existente de YouTube. | `radar_paths_Radar_V1`, `youtube_data_contract_Radar_V1` |
| `scr_Radar_V1/preprocesamiento_Radar_V1/promover_csv_a_texto_Radar_V1.py` | Promueve los CSV semanales canónicos de Radar V1 a corpus TXT. | `facebook_data_contract_Radar_V1`, `medios_data_contract_Radar_V1`, `output_naming_Radar_V1`, `radar_paths_Radar_V1`, `twitter_data_contract_Radar_V1`, `youtube_data_contract_Radar_V1` |
| `scr_Radar_V1/preprocesamiento_Radar_V1/validar_homogeneidad_semanal_Radar_V1.py` | Valida el contrato canónico semanal de las cuatro fuentes de Radar V1. | `facebook_data_contract_Radar_V1`, `facebook_historical_contract_Radar_V1`, `medios_data_contract_Radar_V1`, `output_naming_Radar_V1`, `promover_csv_a_texto_Radar_V1`, `radar_paths_Radar_V1`, `twitter_data_contract_Radar_V1`, `youtube_data_contract_Radar_V1` |

Cargar/importar utiliza funciones; invocar ejecuta un proceso; una dependencia de archivos significa que una etapa consume productos de otra. El panel encadena las operaciones existentes y puede ejecutarlas por separado. No hay un segundo constructor NLP.

## Contratos de extracción y texto

| Fuente | Columnas canónicas |
|---|---|
| youtube | `comment_text, published_at, query` |
| twitter | `tweet_id, author, published_at, url, text, replies, retweets, likes, bookmarks, views, query_raw, is_reply` |
| facebook | `tipo, cuenta, url, post_url_padre, fecha, texto, num_comentarios` |
| medios | `titulo, fecha, iso_date, fuente, autor, url, url_google, thumbnail, texto, origen` |

Semana nueva: lunes–domingo, con publicación dentro del intervalo. Los cuatro procesadores tienen nombres `procesar_FUENTE_semanal_Radar_V1.py`. YouTube usa sus cuatro consultas aprobadas; Twitter usa las dos cuentas y sus consultas from/to/menciones, incluidas respuestas.

**Facebook histórico (C5):** la incorporación fue una reparación realizada una vez. El registro sólo permite reconocer filas históricas exactas que ya están en el CSV. El proceso semanal nuevo no lo carga ni agrega filas. La reproducción explícita del histórico requiere `--historical-corpus`. El validador consulta la evidencia para comprobar el material ya incorporado; no lo reinserta ni inventa fechas.

**Medios:** el extractor nuevo escribe CSV; `procesar_medios_semanal_Radar_V1.py` normaliza ese CSV con su contrato; `promover_csv_a_texto_Radar_V1.py` convierte título+contenido a TXT. El histórico disponible sólo en TXT se conserva como excepción documentada, sin reconstruir metadatos perdidos.

**TXT (C7):** letras ASCII minúsculas, acentos eliminados, ñ→n, sin URLs, números ni signos. Redes: una fila textual útil por línea. Medios: título+contenido en segmentos de hasta 30 palabras. El CSV se conserva.

## Productos y consumidores

| Producto | Lo produce | Lo consume |
|---|---|---|
| `datos_Radar_V1/radar_semanal_extraido_Radar_V1/` | Extractores | Procesadores de cada fuente |
| `datos_Radar_V1/radar_semanal_procesado_Radar_V1/` | Procesadores y promotor | Validación, balance y NLP |
| `datos_Radar_V1/radar_indicadores_Radar_V1/` | Constructor NLP | Partición y soporte de selección |
| `datos_Radar_V1/radar_modelado_Radar_V1/` | Particionador | Inspector y selector: sólo 56 iniciales |
| `datos_Radar_V1/radar_analisis_Radar_V1/` | Balance, inspector y selector | Revisión metodológica; modelado aún pendiente |
| Tabla para tablero, tablero y reporte | Productores todavía no implementados | Etapas presentes y bloqueadas en GUI |

La tabla principal tiene 70 filas y 24 columnas: tres metadatos, polaridad Original y veinte candidatos temáticos. No contiene las 13 semanas reservadas. El completo de 83 semanas está en `archivo_Radar_V1/`. Todas las hojas de datos terminan en `_Radar_V1` antes de su extensión; cada carpeta de datos también lleva el sello.

## NLP y control temporal

NLP incorpora diccionarios/stoplists/exclusiones autorizados, unigramas y n-gramas, polaridad Original, temas, intensidad por mil palabras y presencia en segmentos de 30 palabras. Integra tasas por fuente con ponderación intermedia alpha=0.5: raíz del volumen de palabras, calibrada sólo con 56 iniciales. Se reutilizan diccionarios, código y metodología anteriores, nunca su corpus ni valores calculados.

No hay Etiquetado, MA5 ni lags adicionales de X. Las regresiones relacionan X(t) con Y(t+1..4) dentro de las 56 iniciales, con 55/54/53/52 pares. Las 14 de prueba y 13 de verificación no se utilizan para seleccionar columnas. Pesos, escalas y ranking se reajustan por prefijo en la selección. El resultado exploratorio no constituye un modelo productivo.

## Repetición, fallos y auditorías

El motor verifica hashes antes de reutilizar tablas, particiones y análisis existentes. Si no corresponden a las entradas, detiene la operación. Renovar TXT/análisis con respaldo guarda los TXT anteriores sin mover sus CSV y archiva las salidas exclusivas del análisis; si falla la operación, restaura los productos anteriores. Un fallo bloquea las etapas dependientes. Se puede reiniciar desde la sección elegida sin repetir las anteriores.

Cada intento conserva estados y log en `state/ejecuciones_Radar_V1/`. Las auditorías nuevas se guardan en `auditorias_Radar_V1/ejecuciones_Radar_V1/` y actualizan su referencia `control_ETAPA_actual_Radar_V1.json`. La validación del corpus guarda además su resumen propio. Los registros antiguos no se reescriben como si se acabaran de ejecutar.

## Accesos y nombres técnicos

- `.env`: nombres `APIFY_TOKEN` y `YOUTUBE_API_KEY`; los valores no se publican en documentos.
- `state/x_state.json`: estado autenticado de X/Playwright. No hay estado local de sesión de Facebook ni YouTube en los extractores vigentes: usan Apify y la clave de YouTube, respectivamente.
- `.git/`: control de versiones; `.agents/`, `.codex/`, `.aws/`, `.conda_envs/`: directorios internos locales. `.aws/` no almacena las claves de estas extracciones.
- `environment-radar-v1_Radar_V1.yml` declara el entorno; la resolución del intérprete está en `radar_paths_Radar_V1.py`.

## Documentación y cambios

Antes de cada commit, ejecutar `actualizar_documentacion_Radar_V1.py` y preparar los .md afectados. El hook comprueba que la documentación preparada corresponde al código preparado. El historial breve está en `CAMBIOS_Radar_V1.md`; este documento describe el estado actual y evita inventarios extensos duplicados.

Inventario actual: 29 scripts, 17 archivos de pruebas. Las pruebas y auditorías se ejecutan desde el panel; su resultado se registra sólo después de realizarlas.

<!-- source-fingerprint: 318cf86657dccc649eeb7d9b48818089478a6799d7d9b626efef2f72328e5e79 -->
