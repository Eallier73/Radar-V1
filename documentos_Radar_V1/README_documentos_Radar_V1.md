# Documentación de Radar V1

- `ARQUITECTURA_CONTRATOS_PRODUCTOS_Radar_V1.md`: estado actual, scripts, contratos, productos y controles. Es la entrada principal.
- `GUI_ORQUESTADOR_RADAR_Radar_V1.md`: uso del panel maestro.
- `CAMBIOS_Radar_V1.md`: decisiones y cambios recientes, sin repetir el inventario completo.
- Los documentos por tema conservan las reglas metodológicas vigentes; se actualizan cuando cambia su alcance.
- `auditorias_Radar_V1/`: evidencia de operaciones realmente realizadas. Las simulaciones están identificadas y no prueban descargas ni resultados.

Cada commit debe revisar y actualizar los .md afectados. El actualizador renueva el panorama y la huella del código en los documentos; el hook contrasta la documentación y el código preparados. No se crea un documento nuevo por cada ajuste menor.

Cada ejecución del panel guarda un registro con fecha y actualiza la referencia de su última ejecución. Las auditorías anteriores se conservan como historia. Nunca se añaden resultados de una prueba que no se haya realizado.

<!-- source-fingerprint: 318cf86657dccc649eeb7d9b48818089478a6799d7d9b626efef2f72328e5e79 -->
