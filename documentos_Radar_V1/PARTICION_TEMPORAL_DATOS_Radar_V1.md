# Tabla semanal y separación temporal

La tabla de trabajo tiene **70 filas y 24 columnas**: tres identificadores, polaridad Original semanal y veinte indicadores temáticos ponderados de esa semana. No contiene MA5 ni rezagos adicionales. Se construye primero el histórico de 83 semanas y después se separan sus filas.

| Conjunto | Filas | Inicio | Fin inclusive | Archivo relativo a datos_Radar_V1/radar_modelado_Radar_V1/ |
|---|---:|---|---|---|
| Bloque inicial | 56 | 2024-09-30 | 2025-10-26 | desarrollo_Radar_V1/entrenamiento_Radar_V1/indicadores_Radar_V1.csv |
| Prueba | 14 | 2025-10-27 | 2026-02-01 | desarrollo_Radar_V1/prueba_Radar_V1/indicadores_Radar_V1.csv |
| Verificación reservada | 13 | 2026-02-02 | 2026-05-03 | verificacion_reservada_Radar_V1/indicadores_Radar_V1.csv |

Las cuatro fuentes de una misma semana permanecen juntas. Las tres particiones tienen 24 columnas y concatenarlas reproduce las 83 filas completas de `datos_Radar_V1/radar_indicadores_Radar_V1/archivo_Radar_V1/tabla_analisis_completa_83_semanas_Radar_V1.csv`. Las dos primeras reproducen exactamente la tabla de trabajo de 70 y su copia en `desarrollo_Radar_V1/indicadores_Radar_V1.csv`.

## Objetivos futuros

Para el horizonte h se relaciona X(t), exclusivamente temática y semanal, con la polaridad de la semana t+h. No se usa la polaridad ni ningún rezago suyo en X.

| Horizonte | Pares completos disponibles dentro de las 56 iniciales |
|---|---:|
| 1 | 55 |
| 2 | 54 |
| 3 | 53 |
| 4 | 52 |

Se retiran los últimos h orígenes porque sus respuestas caerían fuera del bloque inicial. No se pierden las primeras cuatro semanas por falta de historia: ya no hay lags. No se imputan valores.

## Pesos y escalas

La tabla de desarrollo utiliza los pesos fijos calibrados con las 56 iniciales, sin usar prueba o verificación. En una comparación interna anterior al final de ese bloque, usar directamente esos pesos sería anticipar información de calibración: por eso `seleccionar_indicadores_Radar_V1.py` los recalcula desde las tasas por fuente de cada prefijo.

La revisión usa prefijos de 28, 35, 42 y 49 semanas y compara orígenes posteriores dentro de las mismas 56. Los pares de ajuste cumplen `fecha_objetivo < inicio_comparacion`. Escalas, orden de candidatas y redundancia se ajustan de nuevo dentro de cada corte. Los errores sirven para selección interna y no son resultados independientes de prueba.

El cargador comprueba procedencia, hashes y encabezados semanales. La revisión estadística no abre los archivos de prueba, verificación ni archivo histórico completo. La partición y los indicadores pueden prepararse para las 83 semanas porque cada medición usa sólo el material de su semana; esa preparación no ajusta parámetros con las reservas.

Las versiones anteriores están respaldadas. La evidencia actual está en [correccion_temporal_sin_suavizado_2026-11-11_Radar_V1.json](auditorias_Radar_V1/correccion_temporal_sin_suavizado_2026-11-11_Radar_V1.json).

<!-- source-fingerprint: 318cf86657dccc649eeb7d9b48818089478a6799d7d9b626efef2f72328e5e79 -->
