# Separación temporal de entrenamiento, prueba y verificación

Decisión del usuario registrada el 10 de noviembre de 2026: generar 56 semanas de entrenamiento, 14 de prueba y 13 de verificación final. La verificación queda fuera del entrenamiento y de los ajustes durante el desarrollo. Se generaron los tres corpus; no se han entrenado modelos.

## Función de cada conjunto

- **Entrenamiento:** ajustar los parámetros del modelo y las transformaciones que aprenden del corpus.
- **Prueba de desarrollo:** comparar variantes y elegir la configuración. Cumple la función habitualmente llamada validación; se conserva el nombre «prueba» usado por el usuario.
- **Verificación final:** evaluar la configuración congelada, sin usar sus resultados para elegir variables, pesos, umbrales ni modelos. Sus entradas se entregan al modelo únicamente al realizar la evaluación final; no se incorporan al ajuste. Si los resultados se usan para modificar el sistema, este bloque deja de ser una evaluación final independiente del desarrollo.

## División por semanas

Los bloques deben seguir el orden cronológico: entrenamiento primero, prueba después y verificación al final. No se barajan semanas. Todas las fuentes de una misma semana pertenecen al mismo bloque.

Se verificó que las cuatro fuentes tienen los mismos 83 inicios semanales consecutivos, del 30 de septiembre de 2024 al 27 de abril de 2026; la última semana termina el 3 de mayo de 2026. El reparto generado es:

| Conjunto | Semanas | Inicio | Fin inclusive | Registros de fuente-semana |
|---|---:|---|---|---:|
| Entrenamiento | 56 | 2024-09-30 | 2025-10-26 | 224 |
| Prueba de desarrollo | 14 | 2025-10-27 | 2026-02-01 | 56 |
| Verificación final | 13 | 2026-02-02 | 2026-05-03 | 52 |

Las cifras son semanas del corpus, no una garantía del número de ejemplos utilizables después de construir indicadores, ventanas temporales u objetivos futuros. Las 70 semanas de desarrollo son las 56 de entrenamiento más las 14 de prueba.

## Evitar filtración de información

La partición se fija antes de cualquier ajuste que aprenda del conjunto de datos. Selección de variables, eliminación de constantes, imputación, estandarización, vocabularios o diccionarios aprendidos y otros parámetros se calculan con entrenamiento. A prueba y verificación se aplican las reglas ya fijadas, sin reajustarlas con sus valores.

Se mantiene la [ponderación intermedia acordada](PONDERACION_FUENTES.md), `alpha = 0.5`. Los porcentajes calculados con las 83 semanas son un diagnóstico retrospectivo que ya incluyó todos los periodos. Se recalcularon los coeficientes sólo con entrenamiento y se guardaron separados; los porcentajes retrospectivos no se presentan como una calibración independiente del bloque reservado. Ningún modelo se ha ajustado todavía.

El suavizado temporal deberá ser causal: ninguna variable de una semana puede usar publicaciones u observaciones posteriores al momento en que se habría producido la predicción. Su cálculo original todavía no se ha localizado. Si posteriormente se construyen objetivos futuros, se excluirán los ejemplos cuyo objetivo invada el siguiente bloque, según el horizonte. No se fija aquí un horizonte ni se añade un suavizado supuesto.

La [función copiada del notebook](PREPARACION_DATOS_NOTEBOOK.md) conserva su ajuste global para documentar y reproducir el método histórico. No se debe aplicar a las 83 semanas antes de dividirlas para una evaluación predictiva. La adaptación para ajustar exclusivamente con entrenamiento sigue pendiente.

Separar bloques temporales evita compartir filas y entrenar con el futuro; no hace estadísticamente independientes las semanas consecutivas.

## Archivos generados y reproducción

```bash
PYTHONDONTWRITEBYTECODE=1 /home/emilio/anaconda3/envs/radar-v1/bin/python \
  scr/operaciones/generar_conjuntos_temporales.py
```

El generador lee los TXT canónicos de `datos/radar_semanal_procesado/` y escribe:

- `datos/radar_modelado/desarrollo/entrenamiento/corpus.jsonl`.
- `datos/radar_modelado/desarrollo/prueba/corpus.jsonl`.
- `datos/radar_modelado/verificacion_reservada/corpus.jsonl`.
- `datos/radar_modelado/desarrollo/entrenamiento/pesos_fuentes.json`: ponderación calculada sólo con las 56 semanas de entrenamiento y sus hashes de procedencia.
- `datos/radar_modelado/particion_semanas.csv`: asignación de las 83 semanas, fechas y hashes por fuente.
- `datos/radar_modelado/auditoria.json`: conteos, hashes de entradas y salidas y estado de la generación.

Una fila JSONL contiene el texto completo de **una fuente en una semana**, junto con `conjunto`, `week`, `period_start`, `period_end`, `source`, `source_path` y `source_sha256`. Se preservan literalmente el texto y sus saltos de línea; esas filas no se presentan como publicaciones ni noticias. Las cuatro fuentes se reúnen en el mismo archivo de cada conjunto conservando su identidad para la ponderación.

El cargador `cargar_desarrollo` del generador sólo admite `entrenamiento` y `prueba`. No abre el corpus de verificación y rechaza ese nombre. No se ha añadido un cargador de evaluación final ni se han conectado modelos. La separación de directorios no es un control de acceso del sistema operativo: otro código no debe recorrer indiscriminadamente `datos/radar_modelado/`.

El generador exige las cuatro fuentes, semanas únicas y consecutivas y una cobertura que sume 83. Rechaza textos vacíos, no modifica entradas y comprueba sus hashes al terminar. Escribe en un directorio temporal y sólo publica la salida completa; se niega a sobrescribir una salida existente. Se puede indicar otra ruta con `--output-dir` para una nueva ejecución.

Los corpus generados permanecen locales; el commit conserva código, pruebas y documentación para reproducirlos.

## Estado de la tabla de indicadores

En la revisión previa se inspeccionaron los encabezados de 501 CSV de `datos/` sin encontrar una tabla de indicadores `MA5`, sentimiento, presencia temática, intensidad o IAD/IAOPD. Ahora están generados los tres conjuntos de corpus textual. Todavía no se ha generado la tabla de indicadores del nuevo corpus; no se han inventado esas mediciones para completar columnas.

## Referencias

- [scikit-learn: prevención de filtración al preparar datos](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage).
- [scikit-learn: evaluación de datos ordenados en el tiempo](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html).
