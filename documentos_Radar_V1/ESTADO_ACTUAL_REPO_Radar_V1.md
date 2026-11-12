# Estado actual de Radar V1

Revisión: 12 de noviembre de 2026.

- Corpus homologado y migrado: 83 semanas por fuente, con datos y productos bajo `datos_Radar_V1`; todos los archivos y carpetas de datos tienen el sello.
- La GUI controla descarga, procesamiento CSV, promoción TXT, validación, balance, NLP, partición, inspección y selección; ofrece simulación, pruebas, estados, terminal persistente, detención y reinicio.
- La tabla conserva 70 filas y 24 columnas; existe el completo de 83 y la separación 56/14/13. No hay MA5 ni lags adicionales de X.
- La reparación histórica de Facebook fue única. El registro de excepciones sólo verifica filas ya incorporadas; las corridas nuevas son estrictas.
- Medios nuevo tiene CSV, procesador y promoción a TXT. El histórico sólo TXT sigue aceptado sin inventar metadatos.
- Modelado, tabla para tablero, tablero y reporte aparecen en el panel, pero todavía no tienen implementación aprobada. No existe un modelo productivo.
- La selección ya se revisó; el procedimiento vigente no respalda una lista común definitiva frente a sólo intercepto. Las celdas exploratorias no equivalen a una evaluación externa.
- Los datos y valores proceden de este repo. Se autorizaron diccionarios, código y metodología previos; no sus corpus ni resultados.
- Antes de cada commit se actualiza documentación y el hook comprueba la correspondencia con el código preparado. El commit de esta ampliación registra el panel, los contratos y los renombres ya versionados. Los resultados derivados y los registros locales de ejecución se conservan fuera del commit.

Entrada principal: [arquitectura y control](ARQUITECTURA_CONTRATOS_PRODUCTOS_Radar_V1.md). Las auditorías reales y simulaciones identificadas están en `auditorias_Radar_V1/`.

<!-- source-fingerprint: 318cf86657dccc649eeb7d9b48818089478a6799d7d9b626efef2f72328e5e79 -->
