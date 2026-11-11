# Tabla ponderada y suavizada y separación temporal

## Resultado vigente

Primero se generó la tabla de las 83 semanas con el corpus de este repo y los diccionarios históricos autorizados; después se dividieron sus filas. No se utilizaron publicaciones, CSV extraídos ni resultados precalculados del proyecto anterior.

La **tabla de trabajo** `datos/radar_indicadores/tabla_analisis_ponderada.csv` tiene **70 filas y 108 columnas**: tres identificadores, 21 indicadores Original y temáticos ponderados y suavizados, y sus 84 lags. Las últimas 13 semanas no están en este archivo. La copia completa se guarda en `datos/radar_indicadores/archivo/tabla_analisis_completa_83_semanas.csv` exclusivamente para reproducir la separación. Se usa únicamente Original; Etiquetado fue retirado.

| Conjunto | Filas | Inicio | Fin inclusive | Archivo relativo a `datos/radar_modelado/` |
|---|---:|---|---|---|
| Entrenamiento | 56 | 2024-09-30 | 2025-10-26 | `desarrollo/entrenamiento/indicadores.csv` |
| Prueba | 14 | 2025-10-27 | 2026-02-01 | `desarrollo/prueba/indicadores.csv` |
| Verificación reservada | 13 | 2026-02-02 | 2026-05-03 | `verificacion_reservada/indicadores.csv` |

Las tres particiones tienen 108 columnas. Concatenarlas reproduce las 83 filas del archivo histórico completo. Concatenar sólo entrenamiento y prueba reproduce exactamente las 70 filas de trabajo, también disponibles en `datos/radar_modelado/desarrollo/indicadores.csv`. No hay cruces ni omisiones. Las cuatro fuentes de una misma semana permanecen juntas.

Los lags se calculan sobre la secuencia completa antes de partir, siempre mirando hacia atrás. Sólo las primeras cuatro filas globales tienen historia incompleta y se conservan sin rellenar. Hay 79 filas completas en el archivo histórico, 66 en las 70 de trabajo y 52 en las 56 de entrenamiento. Prueba y verificación conservan sus antecedentes observados sin reajustar parámetros con ellos.

## Cálculo y controles

Los pesos se calibran exclusivamente con las primeras 56 semanas; el MA5 usa la semana actual y las cuatro anteriores. Las tasas e intensidades de las cuatro fuentes se integran antes del suavizado y la partición. No se recalculan valores al dividir.

La auditoría registra `corpus_origin_policy: current_repository_only`; los diccionarios reutilizados quedan identificados por separado. El separador comprueba el hash de la tabla y su procedencia del corpus actual. El cargador de desarrollo verifica la auditoría y sólo abre entrenamiento o prueba, nunca verificación.

Se generaron la tabla y sus particiones y se realizó una inspección y regresiones exploratorias sólo con el bloque inicial. El usuario eligió la polaridad Original como variable dependiente. Para horizontes 1, 2, 3 y 4 se desplaza la respuesta únicamente dentro de las 56 semanas iniciales: se retiran los últimos h orígenes y las primeras cuatro filas sin historia completa, dejando 51, 50, 49 y 48 pares. Ninguna etiqueta procede de prueba ni de verificación. La polaridad actual y todos sus rezagos quedan fuera de las explicativas. No se seleccionaron predictores automáticamente ni se entrenó un pronosticador operativo.

## Reproducción

1. Ejecutar `scr/operaciones/construir_tabla_indicadores.py` con el intérprete de Radar.
2. Ejecutar `scr/operaciones/generar_conjuntos_temporales.py`.

Ambos rechazan sobrescribir salidas. El constructor calcula las 83 semanas y exporta la tabla de trabajo de 70 junto con la copia completa en `archivo/`. El separador lee por defecto esa copia completa y genera la separación 56/14/13 y la copia de desarrollo de 70. Las tablas generadas permanecen locales.

La inspección y las regresiones ya usaban sólo el archivo de entrenamiento de 56 filas antes de corregir la tabla de trabajo. Se comprobó que su hash no cambió; las 13 reservadas no participaron en esos cálculos.

Las [fórmulas y unidades](INDICADORES_SEMANALES.md) y la [evidencia de procedencia](auditorias/restauracion_diccionarios_y_corpus_actual_2026-11-10.json) documentan la distinción entre diccionarios autorizados y datos del proyecto anterior prohibidos.
