# Operaciones sobre el corpus

**Alcance:** se reutilizan los diccionarios y la metodología autorizados. El corpus y todos los valores semanales se calculan con los datos de Radar V1; no se importan publicaciones, CSV extraídos ni resultados del proyecto anterior.

| Programa | Propósito |
|---|---|
| `analizar_balance_fuentes.py` | Diagnóstico retrospectivo de volumen, longitud y autores observables; calcula escenarios de ponderación sin modificar entradas. |
| `construir_tabla_indicadores.py` | Calcula las 83 semanas, guarda el completo en `archivo/` y exporta una tabla de trabajo de 70 filas y 108 columnas, excluyendo las 13 reservadas. |
| `generar_conjuntos_temporales.py` | Lee la copia histórica completa de `archivo/`, separa 56/14/13 y guarda las 70 de desarrollo juntas, sin recalcular valores. |
| `inspeccionar_indicadores.py` | Calcula descriptivos, correlaciones, regresiones individuales y Ridge conjunto sólo con entrenamiento. Usa Original como respuesta por decisión del usuario. |

Las reglas están en [INDICADORES_SEMANALES.md](../../documentos/INDICADORES_SEMANALES.md). Las decisiones están en [PONDERACION_FUENTES.md](../../documentos/PONDERACION_FUENTES.md) y [PARTICION_TEMPORAL_DATOS.md](../../documentos/PARTICION_TEMPORAL_DATOS.md). Ninguno entrena un pronosticador para uso operativo; la inspección sí ajusta regresiones exploratorias. Primero se calcula la tabla y después se divide. El separador y el cargador verifican la procedencia del corpus actual y los hashes de las tablas.

```python
from pathlib import Path
from scr.operaciones.generar_conjuntos_temporales import cargar_desarrollo

entrenamiento = cargar_desarrollo(Path("datos/radar_modelado/desarrollo"), "entrenamiento")
prueba = cargar_desarrollo(Path("datos/radar_modelado/desarrollo"), "prueba")
```

Cada elemento es una fila de indicadores semanales leída de CSV; los valores numéricos se reciben como texto hasta su conversión por el consumidor. El cargador rechaza verificación. Los ajustes posteriores se calculan sólo con entrenamiento. Las tablas generadas se conservan localmente y no se incluyen en los commits de código.

`generate` y `cargar_corpus_desarrollo` conservan la operación textual anterior como referencia reproducible del respaldo. El CLI y el cargador vigente `cargar_desarrollo` trabajan con indicadores.

Después de generar y partir la tabla, ejecutar `inspeccionar_indicadores.py`. Relaciona las explicativas disponibles en t con Original MA5 en t+1, t+2, t+3 y t+4. Desplaza la respuesta sólo dentro de las 56 semanas iniciales y retira los últimos h orígenes: quedan 51, 50, 49 y 48 pares completos, respectivamente. No imputa huecos, no abre prueba ni verificación y no recorta la tabla base. La polaridad y todos sus rezagos se excluyen de los predictores: quedan 100 candidatas temáticas. Ridge usa alpha=1 fijado de antemano y compara 0.1/10 sólo como sensibilidad. Los coeficientes son asociaciones exploratorias, sin validación externa ni interpretación causal. El resultado se guarda en `datos/radar_analisis/inspeccion_indicadores/`; los CSV de coeficientes identifican el horizonte y `alineacion_horizontes.csv` registra cada origen y respuesta.
