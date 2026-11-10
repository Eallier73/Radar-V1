# Registros históricos reincorporados por fecha

Por autorización del usuario del 6 de noviembre de 2026, se reincorporan 6,789
registros de 20 semanas: 3,884 excluidos por fecha desconocida y 2,905 por fecha
inválida o relativa. No se inventan fechas: se conserva el valor original de
`fecha` y la semana de procedencia, sin certificar una semana de publicación.

Cada `facebook_reincorporado.jsonl` conserva el registro de exclusión original,
su proyección aceptada de siete columnas, archivo y SHA-256 de procedencia,
posición original, referencia y hash del registro de exclusiones. Estos archivos
identifican las filas exactas que el procesador y el validador deben conservar;
no deben moverse a `trash/` mientras esas filas formen parte del corpus.

Las exclusiones originales siguen intactas en `datos/radar_historico_excluido/`.
Su presencia allí describe la decisión anterior, no una exclusión actual de
estas filas. El 9 de noviembre se autorizaron también 210 comentarios antes
excluidos por falta de post padre: sus padres ya fueron recuperados y ahora
satisfacen el contrato normal de vínculos y fechas. Su evidencia se conserva
en `facebook_comentarios_reincorporados.jsonl`; no requieren una excepción de
fecha. Los demás motivos de exclusión permanecen fuera del corpus.
Los controles de cuentas, duplicados, contenido y vínculos siguen vigentes,
y las nuevas extracciones siguen exigiendo fechas verificables.

La auditoría de esta operación se encuentra en
`documentos/auditorias/reincorporacion_facebook_fechas_2026-11-06.json`.
La reparación posterior de los vacíos está en
`documentos/auditorias/reparacion_vacios_facebook_2026-11-09.json`.
