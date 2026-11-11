# Estado de Radar V1

Corte: 11 de noviembre de 2026. El flujo actual llega desde la extracción y normalización hasta la tabla semanal y su revisión estadística. La siguiente etapa es resolver la selección/modelado para los horizontes de una a cuatro semanas y conectar las etapas posteriores.

## Estado por tramo

| Tramo | Estado comprobado |
|---|---|
| Extractores | YouTube, Twitter/X, Facebook y Medios tienen scripts y contratos compartidos. La homologación histórica está documentada. |
| CSV a TXT | Procesamiento y promoción reproducibles con limpieza ASCII. Validación actual: OK, mismas 83 semanas en las cuatro fuentes y cero TXT vacíos. |
| Corpus | 332 TXT procesados y 249 CSV procesados sociales. Periodo del 30 de septiembre de 2024 al 3 de mayo de 2026. |
| Indicadores | Tabla conjunta ponderada de 70 filas y 24 columnas: fechas, polaridad Original semanal y veinte candidatas temáticas. Sin MA5 ni lags de X. |
| Separación | 56 semanas iniciales, 14 de prueba y 13 de verificación reservada. Las 13 finales no están en la tabla de trabajo. |
| Inspección | Descriptivos, correlaciones y regresiones exploratorias recalculados con el contrato semanal. No equivalen a un modelo validado. |
| Selección | Revisión temporal realizada; el procedimiento actual no respalda un conjunto temático común definitivo frente a sólo intercepto. |
| GUI/orquestador | Disponibles Extracción y Preprocesamiento. Los programas de indicadores y selección se ejecutan por terminal y aún no están conectados a una etapa NLP general. |
| Modelado | No existe `scr/modelado/run_modelado.py` ni un modelo operativo construido con esta tabla. |
| Tablero y reporte | No existen sus runners en el repo; el flujo completo hasta el producto final no está conectado. |

## Material y límites conservados

- YouTube: 83 CSV/TXT procesados; 76,986 registros CSV.
- Twitter/X: 83 CSV/TXT procesados; 9,391 registros CSV, con respuestas dentro del alcance acordado.
- Facebook: 83 CSV/TXT procesados; 10,027 registros CSV. Conserva las excepciones autorizadas de fecha de 6,789 filas en 20 semanas, sin inventar sus fechas reales de publicación.
- Medios: 83 TXT históricos aceptados como material disponible. Sus metadatos perdidos no se reconstruyen; las nuevas extracciones tienen contrato CSV canónico.

La validación de cobertura y contratos respeta estas excepciones. Los controles temporales del análisis no convierten las fechas históricas desconocidas de Facebook ni los metadatos ausentes de Medios en fechas certificadas.

Los datos y valores semanales del análisis proceden de este repo. Del proyecto anterior se reutilizaron únicamente metodología y diccionarios autorizados. `Visibilidad_MV` conserva los términos aprobados, incluidas referencias a cargos y al gobierno municipal.

## Decisiones ya aplicadas

- Integración conjunta de cuatro fuentes mediante tasas normalizadas y ponderación intermedia con alpha=0.5.
- Original como única respuesta de polaridad; Etiquetado retirado.
- Valores semanales sin MA5, ni rezagos adicionales de las explicativas.
- Horizontes X(t) frente a Y(t+1), Y(t+2), Y(t+3), Y(t+4), con 55/54/53/52 pares dentro del bloque inicial.
- Ajuste de pesos, escalas, selección y redundancia dentro de cada corte de la revisión temporal. Prueba y verificación no se usan para elegir columnas.
- Las tablas anteriores, sus resultados y dos scripts con preparación global o entradas externas están archivados íntegros en `trash/respaldos/`.

## Qué falta

1. Resolver el planteamiento de selección y modelado por horizonte a partir del resultado corregido. La revisión ya se hizo; no ha producido una lista común definitiva de columnas con respaldo suficiente bajo el criterio actual.
2. Construir el flujo de modelado con el contrato semanal y un protocolo de evaluación definido. Usar las 14 semanas de prueba en su fase y mantener las 13 reservadas para la comprobación final.
3. Integrar indicadores y análisis en el orquestador/GUI mediante un runner NLP. La existencia de los scripts de operaciones no implica que esa etapa general ya esté implementada.
4. Revisar los experimentos heredados de `scr/nlp/`: varios conservan rutas a `/home/emilio/Documentos/RAdAR`. El wrapper `experiment_logger.py` apunta a `scr/Modeling/experiment_logger.py`, que no existe en este checkout. Su adaptación o archivo queda pendiente; no se ejecutaron durante esta revisión.
5. Implementar los runners de tablero y reporte y conectarlos con resultados del modelo actual.

## Verificación y Git

Hay 108 pruebas aprobadas para los contratos y el flujo actual. Se comprobó además el corpus real con el validador semanal, exigiendo mismas semanas y texto no vacío: resultado OK. Esta revisión no lanzó nuevas descargas ni certifica que todas las integraciones externas funcionen hoy.

La corrección comprobó que los 581 archivos CSV/TXT del corpus procesado permanecen intactos. Los valores semanales de soporte y la ponderación acordada se conservaron al retirar las transformaciones.

Los originales históricos y diccionarios ya tienen archivos versionados. El commit de esta etapa registra código, pruebas y documentación; las carpetas de resultados y tablas derivadas siguen locales y reproducibles. `trash/` conserva los respaldos locales y está excluido de Git salvo sus manifiestos previstos. Hay commits locales pendientes de push.

Evidencias: [panorama y validación del corpus](auditorias/panorama_repo_2026-11-11.json), [corrección temporal](auditorias/correccion_temporal_sin_suavizado_2026-11-11.json), [contratos históricos](HOMOLOGACION_HISTORICA.md), [indicadores](INDICADORES_SEMANALES.md), [selección](SELECCION_INDICADORES.md).
