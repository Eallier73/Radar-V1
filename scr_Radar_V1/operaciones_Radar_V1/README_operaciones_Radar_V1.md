# Operaciones sobre el corpus

**Alcance:** se reutilizan diccionarios, código y reglas de procesamiento autorizados, adaptados al flujo actual. Incluyen la aplicación de diccionarios, el conteo y las fórmulas de los indicadores. El corpus y todos los valores semanales se calculan con los datos de Radar V1; no se importan publicaciones, CSV extraídos ni resultados numéricos del proyecto anterior.

| Programa | Propósito |
|---|---|
| `analizar_balance_fuentes_Radar_V1.py` | Diagnóstico retrospectivo de volumen, longitud y autores observables; calcula escenarios de ponderación sin modificar entradas. |
| `generar_conjuntos_temporales_Radar_V1.py` | Lee la copia histórica completa de `archivo_Radar_V1/`, separa 56/14/13 y guarda las 70 de desarrollo juntas, sin recalcular valores. |
| `inspeccionar_indicadores_Radar_V1.py` | Calcula descriptivos, correlaciones, regresiones individuales y Ridge conjunto sólo con entrenamiento. Usa Original como respuesta por decisión del usuario. |
| `seleccionar_indicadores_Radar_V1.py` | Revisa redundancia, estabilidad y tamaño de una ruta de candidatas en cortes temporales internos. Recalcula pesos y escalas por corte y contrasta escenarios con y sin las columnas del tema MV. |

El único constructor NLP es `scr_Radar_V1/nlp_Radar_V1/construir_tabla_indicadores_Radar_V1.py`, conectado directamente a la etapa NLP de la GUI. Calcula las 83 semanas y exporta la tabla de trabajo de 70 filas y 24 columnas, sin suavizado ni lags y excluyendo las 13 reservadas. Esta carpeta conserva el diagnóstico, la partición y el análisis estadístico posterior.

Las reglas están en [INDICADORES_SEMANALES_Radar_V1.md](../../documentos_Radar_V1/INDICADORES_SEMANALES_Radar_V1.md). Las decisiones están en [PONDERACION_FUENTES_Radar_V1.md](../../documentos_Radar_V1/PONDERACION_FUENTES_Radar_V1.md) y [PARTICION_TEMPORAL_DATOS_Radar_V1.md](../../documentos_Radar_V1/PARTICION_TEMPORAL_DATOS_Radar_V1.md). Ninguno entrena un pronosticador para uso operativo; la inspección sí ajusta regresiones exploratorias. Primero se calcula la tabla y después se divide. El separador y el cargador verifican la procedencia del corpus actual y los hashes de las tablas.

```python
from pathlib import Path
from scr_Radar_V1.operaciones_Radar_V1.generar_conjuntos_temporales_Radar_V1 import cargar_desarrollo

entrenamiento = cargar_desarrollo(Path("datos_Radar_V1/radar_modelado_Radar_V1/desarrollo"), "entrenamiento")
prueba = cargar_desarrollo(Path("datos_Radar_V1/radar_modelado_Radar_V1/desarrollo"), "prueba")
```

Cada elemento es una fila de indicadores semanales leída de CSV; los valores numéricos se reciben como texto hasta su conversión por el consumidor. El cargador rechaza verificación. Los ajustes posteriores se calculan sólo con entrenamiento. Las tablas generadas se conservan localmente y no se incluyen en los commits de código.

El CLI y el cargador `cargar_desarrollo` trabajan exclusivamente con indicadores. Las funciones anteriores de partición de corpus TXT y sus pruebas quedaron archivadas con su versión de origen; no se conserva un flujo alternativo dentro del separador vigente.

Después de generar y partir la tabla, ejecutar `inspeccionar_indicadores_Radar_V1.py`. Relaciona los veinte indicadores temáticos de t con Original semanal en t+1, t+2, t+3 y t+4, sin promediar la respuesta ni añadir lags de X. Desplaza la respuesta sólo dentro de las 56 semanas iniciales y retira los últimos h orígenes: quedan 55, 54, 53 y 52 pares, respectivamente. No imputa huecos ni abre prueba o verificación. Ridge usa alpha=1 fijado y compara 0.1/10 como sensibilidad. Los coeficientes son exploratorios, sin validación externa ni interpretación causal. La salida está en `datos_Radar_V1/radar_analisis_Radar_V1/inspeccion_indicadores_Radar_V1/`; los CSV identifican el horizonte y `alineacion_horizontes_Radar_V1.csv` registra cada origen y respuesta.

La revisión posterior se ejecuta con `seleccionar_indicadores_Radar_V1.py`. Usa sólo el bloque inicial y las primeras 56 filas del soporte por fuente; no carga el resto del soporte ni abre prueba o verificación. Comprueba que los indicadores reconstruidos coincidan con la tabla vigente. En prefijos de 28/35/42/49 semanas recalcula pesos, escalas, orden y redundancia antes de comparar respuestas posteriores. La tabla publicada tiene pesos del ajuste completo inicial y no se usa directamente para un backtest interno. La salida `datos_Radar_V1/radar_analisis_Radar_V1/seleccion_indicadores_Radar_V1/` conserva curvas, recurrencia, exclusiones y comparación sin MV. El resultado actual no justifica un conjunto común de explicativas: el manifiesto es provisional y la matriz principal conserva las veinte candidatas. Los cargadores rechazan MA5 y lags. Véase [SELECCION_INDICADORES_Radar_V1.md](../../documentos_Radar_V1/SELECCION_INDICADORES_Radar_V1.md).
