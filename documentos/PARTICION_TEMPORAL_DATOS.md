# Tabla de indicadores y separación temporal

Decisión corregida del 10 de noviembre de 2026: **primero generar la tabla completa de indicadores de las 83 semanas y después partir sus filas** en 56 de entrenamiento, 14 de prueba y 13 de verificación final.

## Resultado vigente

La tabla `datos/radar_indicadores/tabla_indicadores_83_semanas.csv` tiene 83 filas y 351 columnas: cuatro identificadores y 347 variables numéricas. Cada fila integra las cuatro fuentes en una semana. No hay valores faltantes en esta generación. Las fórmulas, recursos, unidades y adaptaciones están en [INDICADORES_SEMANALES.md](INDICADORES_SEMANALES.md) y las definiciones de columnas en `datos/radar_indicadores/variables.csv`.

Después de guardar la tabla completa, el separador lee ese CSV y copia sus filas sin recalcular ni estandarizar:

| Conjunto | Filas | Inicio | Fin inclusive | Archivo relativo a `datos/radar_modelado/` |
|---|---:|---|---|---|
| Entrenamiento | 56 | 2024-09-30 | 2025-10-26 | `desarrollo/entrenamiento/indicadores.csv` |
| Prueba de desarrollo | 14 | 2025-10-27 | 2026-02-01 | `desarrollo/prueba/indicadores.csv` |
| Verificación final | 13 | 2026-02-02 | 2026-05-03 | `verificacion_reservada/indicadores.csv` |

Las 70 semanas de desarrollo son entrenamiento más prueba. Concatenar los tres conjuntos reproduce las 83 filas de la tabla completa, sin cruces ni omisiones. No se han entrenado modelos.

## Uso de los conjuntos

- **Entrenamiento:** aprender parámetros y ajustar transformaciones.
- **Prueba de desarrollo:** comparar variantes y elegir la configuración; cumple la función habitualmente llamada validación.
- **Verificación final:** evaluar únicamente la configuración congelada. Sus resultados no se usan para elegir variables, pesos, umbrales ni modelos. Si sirven para modificar el sistema, este bloque deja de ser una evaluación final independiente del desarrollo.

Los bloques son cronológicos y mantienen juntas las cuatro fuentes de cada semana. La separación no elimina la autocorrelación temporal.

Calcular determinísticamente los indicadores de las 83 semanas no autoriza aprender parámetros con todas ellas. Los diccionarios históricos permanecen fijos. La ponderación intermedia usa sólo el volumen de las primeras 56 semanas y se mantiene fija para las otras 27; conocer ese límite no implica partir físicamente el corpus antes de construir la tabla.

La media MA5 se adaptó del centrado histórico a una ventana hacia atrás (semana actual y cuatro anteriores, mínimo una observación). Así ninguna semana futura interviene en una fila anterior. Puede usar antecedentes conocidos de otro bloque; esos antecedentes no pasan al ajuste del modelo.

Las tablas están **sin estandarizar**. Selección de variables, eliminación de constantes, imputación y estandarización se ajustarán sólo con entrenamiento. La función histórica que ajusta la tabla completa no debe aplicarse a esta evaluación. Si se construyen objetivos futuros, habrá que excluir los ejemplos cuyo objetivo invada el siguiente bloque según el horizonte; 56/14/13 son filas disponibles antes de esa construcción.

El cargador `cargar_desarrollo` sólo abre `indicadores.csv` de entrenamiento o prueba y rechaza verificación. No existe aún un cargador de evaluación final ni se han conectado modelos. La separación de carpetas no es un control de acceso del sistema operativo: no se debe cargar la tabla completa para ajustar un modelo.

## Reproducción

1. Ejecutar `scr/operaciones/construir_tabla_indicadores.py` con el intérprete de Radar.
2. Después ejecutar `scr/operaciones/generar_conjuntos_temporales.py`.

Ambos se niegan a sobrescribir salidas. Admiten `--output-dir`; el constructor admite `--processed-dir` y `--resources-dir`, y el separador `--table` y `--weights`. Publican las salidas únicamente cuando terminan.

La auditoría de construcción conserva hashes de los 332 TXT y de los recursos. La de partición registra el hash de la tabla y de sus tres subconjuntos. Las tablas generadas permanecen locales; los commits conservan código, recursos de cálculo, pruebas y documentación.

## Respaldo del intento anterior

Los seis archivos de los conjuntos textuales anteriores se conservaron íntegros en `trash/respaldos/corpus_partido_antes_indicadores_2026-11-10/`, con hashes en `respaldo_integridad.json`. No son la entrada vigente. La función `generate` conserva esa operación sólo como referencia reproducible; el CLI vigente parte indicadores.

## Referencias

- [scikit-learn: prevención de filtración al preparar datos](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage).
- [scikit-learn: evaluación de datos ordenados en el tiempo](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html).
