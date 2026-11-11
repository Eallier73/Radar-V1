# Inspección semanal con Original

Esta versión sustituye los resultados que usaban MA5 y rezagos de X. La respuesta es `Sentimiento_Conjunto_Original_Original`, medida de una única semana; X contiene los veinte indicadores temáticos ponderados de la semana de origen.

## Datos y alineación

Sólo se carga el archivo inicial de 56 semanas. Hay 21 columnas numéricas inspeccionadas, incluida la respuesta; veinte son candidatas X. Las 56 filas están completas, el rango centrado es 21 y hay nueve pares con correlación absoluta de Pearson de al menos 0.90.

Para horizontes 1/2/3/4 se desplaza únicamente la respuesta, produciendo 55/54/53/52 pares. `alineacion_horizontes.csv` registra origen y objetivo. No se buscan respuestas en prueba ni verificación; se retiran los últimos h orígenes.

## Alcance de las regresiones

Se calculan asociaciones univariadas y Ridge conjunto, con alpha=1 fijado y 0.1/10 como sensibilidad. Se estandarizan sólo los pares elegibles del bloque inicial. La respuesta y sus transformaciones no forman parte de X; los encabezados MA5 o lags se rechazan.

Estos ajustes usan la calibración de fuentes del bloque inicial completo y son exploratorios. No son un backtest ni permiten afirmar calidad predictiva. Los coeficientes no son porcentajes de importancia, efectos causales ni una selección validada de columnas. No se reportan p-valores que supongan semanas independientes.

La selección temporal posterior reconstruye pesos, escalas y selección dentro de cada prefijo; está documentada en [SELECCION_INDICADORES.md](SELECCION_INDICADORES.md).

## Salidas

`datos/radar_analisis/inspeccion_indicadores/` contiene descriptivos, correlaciones, regresiones individuales y conjuntas, fechas de alineación, diagnóstico con hashes e informe. Los resultados anteriores quedaron respaldados y no son resultados del contrato semanal vigente.

Las pruebas alteran semanas futuras y comprueban que los ajustes de un prefijo anterior no cambien, que un pico semanal no se extienda a otras filas y que ningún objetivo de ajuste cruce el corte temporal.
