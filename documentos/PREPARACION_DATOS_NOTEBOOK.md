# Preparación de datos recuperada del notebook

Registro del 10 de noviembre de 2026. Se copiaron al módulo [preparar_indicadores_semanales.py](../scr/preprocesamiento/preparar_indicadores_semanales.py) las funciones `detectar_columna_target`, `detectar_columnas_tiempo` y `preparar_dataset_completo` de la última implementación ejecutada del notebook. Sus cuerpos se conservan, salvo espacios de formato. No se copiaron entrenamiento, predicción, clasificación, rezagos ni dashboards.

## Procedencia

- Archivo: `/home/emilio/Datos/Ipsel/IPSEL_Tampico/Ml_Monica_Villarreal/Datos/Jupyter/Modelo_ML_MV.ipynb`.
- SHA-256 del notebook: `f372ad39f899df62273580fe2aa0ddfe56d65d1aac47f90096963b6b6439ffb7`.
- Celda de código con índice 37 (base cero), funciones en las líneas 226–306 del texto de la celda. Tiene salida de ejecución guardada y escribe en `RResultados_Modelo_Funcional_4`.
- Se copió código mediante lectura del JSON y análisis de su sintaxis; no se ejecutó el notebook.

## 1. Datos de entrada

El módulo recibe un CSV de indicadores semanales ya construidos. El notebook utiliza columnas de sentimiento por fuente y columnas temáticas de presencia e intensidad, incluidas variables integradas. Ejemplos literales: `Sentimiento_Fuentes_Original_Etiquetado_MA5`, `X_Presencia_Youtube_Agua_MA5`, `intensidad_por_1000_Facebook_Alumbrado_MA5` y `presencia_tema_pct_Fuentes_Integradas_Vialidades_MA5`.

No se establece aquí un esquema completo obligatorio: la función selecciona las columnas numéricas disponibles según las exclusiones que se detallan abajo. No calcula esos indicadores a partir de TXT; tampoco define sus diccionarios, denominadores ni reglas de sentimiento.

El objetivo se detecta, en este orden, como `IAOPD_MA5`, `IAD_global_MA5`, `Indice_Aceptacion_MA5` o `IAOPD_global_MA5`. Si ninguno existe, toma la primera columna cuyo nombre contiene `IAD` o `IAOPD` y también `MA5`. Si no existe, genera un error; no inventa un objetivo.

## 2. Suavizado

Se conserva el uso de los indicadores de entrada con sufijo `MA5`. El notebook no contiene el cálculo de esa media: no especifica mediante una implementación la alineación, el mínimo de observaciones ni el tratamiento de los extremos. El módulo copiado consume esas columnas y no les aplica un segundo suavizado.

Por ello no se ha añadido una implementación supuesta de `MA5` ni se presentan como calculados los indicadores que todavía no existen en el flujo actual.

## 3. Preparación de la tabla

Las reglas copiadas de la versión final son:

1. Leer el CSV con `pandas.read_csv`.
2. Buscar la columna semanal en orden: `semana_iso`, `semana`, `week_label`. Buscar la fecha en orden: `Fecha_Semana`, `fecha_semana`, `fecha`, `date`.
3. Ordenar por la columna semanal si existe; en su ausencia, por fecha. Si no hay ninguna, conservar el orden original. El código no convierte ni valida el calendario.
4. Seleccionar variables numéricas y excluir la columna semanal detectada, la fecha detectada, el objetivo, las columnas cuyo nombre contiene `encuesta` y las columnas con un máximo de un valor distinto observado.
5. Excluir además `IAD_global`, `IAD_global_MA5`, `IAD_global_suavizado` e `IAOPD_MA5` de las variables explicativas.
6. Estandarizar con `StandardScaler` las variables seleccionadas **y el objetivo**, ajustando sobre la tabla completa. Esta es la versión final; una versión anterior del notebook escalaba sólo las variables explicativas.
7. Devolver la tabla escalada, una copia sin escalar ordenada, el nombre del objetivo, la lista de variables explicativas, la media y escala del objetivo y el objeto de estandarización.

La función no imputa faltantes, no rellena semanas, no elimina filas y no integra fuentes. Los valores ausentes no se convierten en cero. Tampoco impone que todas las columnas de entrada tengan el sufijo `MA5`.

## Uso y estado

```python
from pathlib import Path
from scr.preprocesamiento.preparar_indicadores_semanales import preparar_dataset_completo

tabla_z, tabla_original, objetivo, variables, media_y, escala_y, scaler = (
    preparar_dataset_completo(Path("ruta/a/indicadores_semanales.csv"), "Histórico")
)
```

La función queda disponible para reutilizar con una tabla de indicadores. No se conecta automáticamente a extracción ni a promoción CSV→TXT, y no se ha ejecutado sobre el corpus histórico: esos archivos contienen textos, no esta tabla de indicadores.

El ajuste global de la estandarización reproduce el procesamiento retrospectivo del notebook. Para evaluar predicciones futuras, ese ajuste deberá hacerse únicamente con los datos de entrenamiento.

La decisión posterior de reservar un bloque de verificación final se documenta en [PARTICION_TEMPORAL_DATOS.md](PARTICION_TEMPORAL_DATOS.md). La función histórica no implementa esa separación ni debe ajustarse con el conjunto completo para esa evaluación.

La [ponderación intermedia acordada](PONDERACION_FUENTES.md) sigue siendo la decisión vigente para las cuatro fuentes. Estas tres funciones no contienen pesos por fuente; su copia no aplica, sustituye ni recalcula los pesos acordados.
