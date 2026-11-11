# Indicadores semanales sin suavizado

Decisión del 11 de noviembre de 2026: retirar MA5 de explicativas y respuesta y retirar los rezagos adicionales de las explicativas. Se conserva la ponderación intermedia y el nombre `Visibilidad_MV`. Se reutilizaron diccionarios, código y reglas de procesamiento del proyecto anterior, adaptados al flujo actual. Los datos y valores se calculan exclusivamente con el corpus de Radar V1; no se importan corpus ni resultados numéricos anteriores.

## Tabla vigente

`datos/radar_indicadores/tabla_analisis_ponderada.csv` tiene **70 filas completas y 24 columnas**:

- Tres identificadores: `semana_iso`, `Fecha_Semana`, `Fecha_Fin`.
- Una respuesta observada: `Sentimiento_Conjunto_Original_Original`, polaridad de esa semana.
- Veinte candidatas X: diez intensidades y diez presencias temáticas, de esa misma semana.

No hay columnas MA5, lags ni valores estandarizados en esta tabla. Las 13 semanas finales se guardan fuera de ella. El archivo completo de 83 filas queda únicamente en `archivo/` para reproducir la separación 56/14/13. El soporte por fuente conserva **198 columnas**, sin versiones suavizadas, para recalcular pesos dentro de cortes temporales. `variables_analisis.csv` define 21 indicadores numéricos; `variables.csv` define el soporte.

## Fórmulas que se conservan

- Polaridad Original: `100 * positivas / (positivas + negativas)`. Sin coincidencias queda ausente; no se inventa neutralidad.
- Intensidad: `1000 * coincidencias_del_tema / palabras_totales`. El factor mil expresa la tasa por mil palabras.
- Presencia comparable: porcentaje de segmentos de hasta 30 palabras que mencionan el tema. Los segmentos no equivalen a publicaciones ni personas.
- Integración conjunta: `suma(peso_fuente * tasa_fuente)`, con `peso_fuente = sqrt(palabras_fuente) / suma(sqrt(palabras))`.

Los diccionarios, exclusiones y coincidencias superpuestas se conservan. `Visibilidad_MV` incluye nombres personales y referencias institucionales; es visibilidad léxica, no aprobación.

## Tiempo y prevención de fugas

Cada tasa de una semana se calcula sólo con su propio material. Cambiar una tasa semanal no se propaga a semanas vecinas. Los pesos de la tabla publicada son una calibración fija con las primeras 56 semanas, congelada para prueba y verificación. Esa tabla es un ajuste de desarrollo completo: **no debe usarse directamente para un backtest de cortes anteriores**.

La selección temporal parte de las tasas por fuente y recalcula pesos dentro de cada prefijo. También ajusta escalas, constantes, orden de candidatas y controles de redundancia exclusivamente con la información disponible en el corte. La respuesta semanal se desplaza a t+1, t+2, t+3 o t+4; no promedia semanas pasadas. Ningún par cuyo objetivo quede fuera del bloque de ajuste se usa para ajustar.

Se supone que X(t) está disponible al cerrar la semana t. Prueba y las 13 semanas reservadas no se abren para elegir columnas. Los cargadores rechazan encabezados MA5 o rezagos para impedir reutilizar la matriz anterior por error.

## Procedencia y reproducción

1. `scr/operaciones/construir_tabla_indicadores.py`: calcula las semanas desde el corpus actual, con hashes de textos y diccionarios.
2. `scr/operaciones/generar_conjuntos_temporales.py`: separa la tabla ya calculada, sin recalcular valores.
3. `scr/operaciones/inspeccionar_indicadores.py`: describe las 56 iniciales; sus ajustes son exploratorios, no una evaluación cronológica.
4. `scr/operaciones/seleccionar_indicadores.py`: reconstruye pesos por corte y revisa redundancia, tamaño y estabilidad.

Las versiones con MA5, los resultados anteriores y el código retirado se conservan en el respaldo indicado en `documentos/auditorias/correccion_temporal_sin_suavizado_2026-11-11.json`. Las fórmulas base, los textos y los diccionarios permanecen intactos. No se reextrajo material ni se entrenó un pronosticador operativo.
