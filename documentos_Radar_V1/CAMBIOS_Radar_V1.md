# Cambios recientes de Radar V1

## 12 de noviembre de 2026 · panel maestro y contratos

- Un único constructor NLP en `nlp_Radar_V1`, conectado directamente a la GUI.
- Procesadores CSV por fuente con nombres uniformes. Medios tiene procesador CSV y promoción TXT explícitos.
- Datos, archivos de salida y carpetas migrados a `_Radar_V1`; se conservaron textos y valores numéricos. Las referencias y hashes de procedencia se actualizaron y los originales quedaron respaldados.
- El panel controla nueve etapas implementadas, pruebas y documentación; conserva estados, terminal en vivo y auditorías. Permite simular, detener y reiniciar desde una etapa elegida.
- Modelado, tabla para tablero, tablero y reporte figuran como futuros y bloqueados; no se fabricaron implementaciones ni resultados.
- La reparación histórica de Facebook no se repite: el registro sólo reconoce filas ya incorporadas. Las corridas nuevas usan fechas estrictas.
- README por nombre de carpeta; documentación concisa actualizada y comprobación antes de commit.

## Registro de esta entrega

Se versionan código, pruebas, documentación, configuración del hook y la migración de los datos que ya estaban en Git. Las 121 pruebas aprobadas y la comprobación del panel Tk están documentadas en las auditorías. Los productos derivados, credenciales, sesiones y respaldos completos permanecen locales.

## Decisiones metodológicas conservadas

Corpus conjunto de cuatro fuentes; ponderación intermedia alpha=0.5; Original; sin MA5 ni lags adicionales; 56 iniciales, 14 de prueba y 13 reservadas. No se entrenó un modelo productivo. No se importaron datos ni resultados numéricos del proyecto anterior.

<!-- source-fingerprint: 318cf86657dccc649eeb7d9b48818089478a6799d7d9b626efef2f72328e5e79 -->
