# Operaciones sobre el corpus

**Alcance:** se reutilizan los diccionarios y la metodología autorizados. El corpus y todos los valores semanales se calculan con los datos de Radar V1; no se importan publicaciones, CSV extraídos ni resultados del proyecto anterior.

| Programa | Propósito |
|---|---|
| `analizar_balance_fuentes.py` | Diagnóstico retrospectivo de volumen, longitud y autores observables; calcula escenarios de ponderación sin modificar entradas. |
| `construir_tabla_indicadores.py` | Calcula las 83 semanas, guarda el completo en `archivo/` y exporta una tabla de trabajo de 70 filas y 24 columnas, sin suavizado ni lags de X y excluyendo las 13 reservadas. |
| `generar_conjuntos_temporales.py` | Lee la copia histórica completa de `archivo/`, separa 56/14/13 y guarda las 70 de desarrollo juntas, sin recalcular valores. |
| `inspeccionar_indicadores.py` | Calcula descriptivos, correlaciones, regresiones individuales y Ridge conjunto sólo con entrenamiento. Usa Original como respuesta por decisión del usuario. |
| `seleccionar_indicadores.py` | Revisa redundancia, estabilidad y tamaño de una ruta de candidatas en cortes temporales internos. Recalcula pesos y escalas por corte y contrasta escenarios con y sin las columnas del tema MV. |

Las reglas están en [INDICADORES_SEMANALES.md](../../documentos/INDICADORES_SEMANALES.md). Las decisiones están en [PONDERACION_FUENTES.md](../../documentos/PONDERACION_FUENTES.md) y [PARTICION_TEMPORAL_DATOS.md](../../documentos/PARTICION_TEMPORAL_DATOS.md). Ninguno entrena un pronosticador para uso operativo; la inspección sí ajusta regresiones exploratorias. Primero se calcula la tabla y después se divide. El separador y el cargador verifican la procedencia del corpus actual y los hashes de las tablas.

```python
from pathlib import Path
from scr.operaciones.generar_conjuntos_temporales import cargar_desarrollo

entrenamiento = cargar_desarrollo(Path("datos/radar_modelado/desarrollo"), "entrenamiento")
prueba = cargar_desarrollo(Path("datos/radar_modelado/desarrollo"), "prueba")
```

Cada elemento es una fila de indicadores semanales leída de CSV; los valores numéricos se reciben como texto hasta su conversión por el consumidor. El cargador rechaza verificación. Los ajustes posteriores se calculan sólo con entrenamiento. Las tablas generadas se conservan localmente y no se incluyen en los commits de código.

`generate` y `cargar_corpus_desarrollo` conservan la operación textual anterior como referencia reproducible del respaldo. El CLI y el cargador vigente `cargar_desarrollo` trabajan con indicadores.

Después de generar y partir la tabla, ejecutar `inspeccionar_indicadores.py`. Relaciona los veinte indicadores temáticos de t con Original semanal en t+1, t+2, t+3 y t+4, sin promediar la respuesta ni añadir lags de X. Desplaza la respuesta sólo dentro de las 56 semanas iniciales y retira los últimos h orígenes: quedan 55, 54, 53 y 52 pares, respectivamente. No imputa huecos ni abre prueba o verificación. Ridge usa alpha=1 fijado y compara 0.1/10 como sensibilidad. Los coeficientes son exploratorios, sin validación externa ni interpretación causal. La salida está en `datos/radar_analisis/inspeccion_indicadores/`; los CSV identifican el horizonte y `alineacion_horizontes.csv` registra cada origen y respuesta.

La revisión posterior se ejecuta con `seleccionar_indicadores.py`. Usa sólo el bloque inicial y las primeras 56 filas del soporte por fuente; no carga el resto del soporte ni abre prueba o verificación. Comprueba que los indicadores reconstruidos coincidan con la tabla vigente. En prefijos de 28/35/42/49 semanas recalcula pesos, escalas, orden y redundancia antes de comparar respuestas posteriores. La tabla publicada tiene pesos del ajuste completo inicial y no se usa directamente para un backtest interno. La salida `datos/radar_analisis/seleccion_indicadores/` conserva curvas, recurrencia, exclusiones y comparación sin MV. El resultado actual no justifica un conjunto común de explicativas: el manifiesto es provisional y la matriz principal conserva las veinte candidatas. Los cargadores rechazan MA5 y lags. Véase [SELECCION_INDICADORES.md](../../documentos/SELECCION_INDICADORES.md).
