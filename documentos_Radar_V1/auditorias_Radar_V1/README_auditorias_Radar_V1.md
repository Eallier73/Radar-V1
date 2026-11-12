# Auditorías de Radar V1

Aquí sólo se guardan comprobaciones realmente realizadas. Una simulación lleva `mode: dry_run` y no prueba que haya habido descargas o cálculos.

- Los archivos históricos describen el estado de la fecha en que se ejecutaron; no se reescribe su historia.
- El panel guarda cada intento en `ejecuciones_Radar_V1/` y actualiza `control_ETAPA_actual_Radar_V1.json`.
- La validación del corpus conserva su resumen propio en `validacion_corpus_actual_Radar_V1.json`.
- La migración de datos registra nombres, hashes, respaldo y preservación de valores; no es una nueva extracción.

Los logs detallados y el estado para reiniciar se guardan bajo `state/ejecuciones_Radar_V1/`.
