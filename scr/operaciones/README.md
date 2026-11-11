# Operaciones sobre el corpus

| Programa | Propósito |
|---|---|
| `analizar_balance_fuentes.py` | Diagnóstico retrospectivo de volumen, longitud y autores observables; calcula escenarios de ponderación sin modificar entradas. |
| `construir_tabla_indicadores.py` | Genera `tabla_analisis_ponderada.csv`: 83 semanas y 47 columnas, con indicadores conjuntos ya ponderados y MA5. Conserva el soporte de 351 columnas. |
| `generar_conjuntos_temporales.py` | Lee por defecto la tabla final ponderada y parte sus filas en 56/14/13, sin recalcular ni estandarizar valores. |

Las fórmulas están en [INDICADORES_SEMANALES.md](../../documentos/INDICADORES_SEMANALES.md). Las decisiones están en [PONDERACION_FUENTES.md](../../documentos/PONDERACION_FUENTES.md) y [PARTICION_TEMPORAL_DATOS.md](../../documentos/PARTICION_TEMPORAL_DATOS.md). Ninguno entrena modelos. Ejecutar primero el constructor y después el separador; ambos rechazan sobrescribir salidas.

```python
from pathlib import Path
from scr.operaciones.generar_conjuntos_temporales import cargar_desarrollo

entrenamiento = cargar_desarrollo(Path("datos/radar_modelado/desarrollo"), "entrenamiento")
prueba = cargar_desarrollo(Path("datos/radar_modelado/desarrollo"), "prueba")
```

Cada elemento es una fila de indicadores semanales leída de CSV; los valores numéricos se reciben como texto hasta su conversión por el consumidor. El cargador rechaza verificación. Los ajustes posteriores se calculan sólo con entrenamiento. Las tablas generadas se conservan localmente y no se incluyen en los commits de código.

`generate` y `cargar_corpus_desarrollo` conservan la operación textual anterior como referencia reproducible del respaldo. El CLI y el cargador vigente `cargar_desarrollo` trabajan con indicadores.
