# Inspección y regresiones exploratorias con Original

El usuario decidió conservar una sola tabla con indicadores actuales y lags 1, 2, 3 y 4, eligió la polaridad **Original** como variable dependiente y pidió retirar Etiquetado. La tabla actual tiene 105 columnas numéricas y tres identificadores; los diccionarios y las columnas Etiquetado están fuera del flujo activo.

## Datos utilizados

La inspección y las regresiones usan exclusivamente las 56 semanas del bloque inicial, leídas por el cargador con procedencia y hash verificados. Hay 52 filas con todos los lags observados, del 28 de octubre de 2024 al 26 de octubre de 2025. Las primeras cuatro filas permanecen en la tabla, sin imputación. Las regresiones usan menos pares porque sus respuestas están una, dos, tres o cuatro semanas después del origen.

La tabla de trabajo ahora contiene sólo 70 semanas (56 de entrenamiento más 14 de prueba); las últimas 13 están reservadas físicamente aparte. La copia completa de 83 se conserva en `archivo/`. Este cambio de presentación no alteró el hash del archivo de entrenamiento usado en la inspección y las regresiones, que ya excluían las semanas reservadas.

No se abrieron los valores de prueba ni verificación. No se incorporaron datos ni resultados del proyecto anterior; sólo los diccionarios Original autorizados.

## Inspección descriptiva

- 101 columnas numéricas inspeccionadas: la respuesta y 100 candidatas temáticas. Los cuatro rezagos de polaridad quedan excluidos por instrucción del usuario.
- Rango 51 de la matriz centrada.
- 66 pares con correlación absoluta de Pearson de al menos 0.90.
- La polaridad actual se usa únicamente como respuesta. Ni esa columna ni ninguno de sus cuatro rezagos forman parte de X: quedan 100 candidatas temáticas.

## Regresiones realizadas

La respuesta es `Sentimiento_Conjunto_Original_Original_MA5` en **t+h**, para h=1, 2, 3 y 4. Las explicativas son los indicadores temáticos disponibles en t y sus lags 1 a 4. Horizonte significa cuánto se adelanta la respuesta; lag significa cuánto se retrocede una explicativa. La polaridad actual y sus cuatro rezagos están excluidos de X.

Se desplaza la respuesta después de cargar exclusivamente el bloque inicial. Los últimos h orígenes se descartan, porque sus respuestas caerían fuera del bloque: nunca se buscan etiquetas en prueba ni en verificación. Los pares quedan así; las fechas identifican el lunes de cada semana:

| Horizonte | Pares completos | Último origen | Último objetivo |
|---|---:|---|---|
| 1 semana | 51 | 2025-10-13 | 2025-10-20 |
| 2 semanas | 50 | 2025-10-06 | 2025-10-20 |
| 3 semanas | 49 | 2025-09-29 | 2025-10-20 |
| 4 semanas | 48 | 2025-09-22 | 2025-10-20 |

La respuesta sigue siendo la polaridad MA5: en t+h resume esa semana y sus cuatro anteriores, no exclusivamente las publicaciones posteriores a t. No se cambió la definición del indicador. El MA5 es causal, sin semanas posteriores a la fecha que representa.

Se calcularon regresiones lineales de una variable a la vez, con pendiente en unidades originales, coeficiente estandarizado y R² del ajuste. Estas asociaciones marginales no controlan las otras variables.

Para examinar asociaciones conjuntas se calculó Ridge por separado para cada horizonte con alpha=1, fijado de antemano. Se estandarizaron X e Y únicamente con los pares completos elegibles de ese horizonte. Los coeficientes con alpha=0.1 y 10 se registran como sensibilidad; no se eligió alpha usando prueba o verificación.

Se usa penalización porque 100 predictores y entre 48 y 51 pares no permiten identificar por mínimos cuadrados ordinarios un coeficiente único para cada predictor. Los coeficientes Ridge describen asociaciones condicionadas y penalizadas; dependen de la redundancia y de alpha. No son efectos causales, porcentajes de importancia ni resultados validados fuera de muestra. Los horizontes tienen tamaños de muestra diferentes; comparar sus coeficientes no constituye una comparación de desempeño predictivo.

No se reportan p-valores que supongan semanas independientes. Los R² guardados son exclusivamente del ajuste de entrenamiento y no acreditan calidad predictiva. No se seleccionaron columnas automáticamente.

## Dos mayores coeficientes por horizonte, alpha=1

| Horizonte | Candidato | Beta estandarizado |
|---|---|---:|
| 1 | Presencia de Agua, t | -0.2084 |
| 1 | Intensidad de Agua, t | -0.2072 |
| 2 | Presencia de MV, lag 2 | 0.1923 |
| 2 | Intensidad de Alumbrado, lag 1 | 0.1742 |
| 3 | Presencia de Economía, lag 1 | -0.1918 |
| 3 | Intensidad de Alumbrado, t | 0.1841 |
| 4 | Presencia de Economía, t | -0.1751 |
| 4 | Intensidad de Alumbrado, lag 4 | -0.1744 |

El signo de estos ocho coeficientes se conserva en los tres valores de alpha estudiados. Eso es una comprobación limitada de sensibilidad, no una validación externa de importancia.

Las regresiones anteriores, primero con rezagos de polaridad y después con respuesta contemporánea, se retiraron a respaldo y fueron sustituidas. La lista de cinco variables propuesta con Y(t) queda reemplazada por esta inspección con Y(t+h); todavía no se fija una selección final. La tabla histórica sigue siendo una sola y no se recortó ni se modificó durante esta inspección.

Los pesos de fuentes siguen calibrados en las primeras 56 semanas. Si después se evalúan pronósticos con cortes temporales internos, deberán recalibrarse los pesos y cualquier transformación aprendida dentro de cada corte; estos ajustes exploratorios no implementan ni acreditan esa validación.

## Archivos y reproducción

Ejecutar `scr/operaciones/inspeccionar_indicadores.py` con el intérprete de Radar después de construir y partir la tabla. La respuesta predeterminada es Original, según la elección del usuario. Rechaza sobrescribir resultados; `--output-dir` permite una nueva salida.

En `datos/radar_analisis/inspeccion_indicadores/` se guardan `descriptivos.csv`, `correlaciones.csv`, `regresiones_univariadas.csv`, `regresion_ridge.csv`, `alineacion_horizontes.csv`, `diagnostico.json` e `inspeccion.md`. Las dos tablas de coeficientes reúnen los cuatro horizontes e incluyen `horizonte_semanas`; el rango de Ridge comienza en 1 para cada horizonte. Los descriptivos y correlaciones son contemporáneos y sólo describen la tabla de origen; las regresiones sí usan respuestas futuras.

Las entradas permanecen intactas. El diagnóstico registra el hash del bloque inicial, la respuesta, los pares y predictores por horizonte, los orígenes retirados y que no se abrieron datos reservados. `alineacion_horizontes.csv` permite comprobar la separación exacta de 7h días entre origen y respuesta.

Referencias: [Ridge](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html), [interpretación de coeficientes y variables correlacionadas](https://scikit-learn.org/stable/auto_examples/inspection/plot_linear_model_coefficient_interpretation.html), [orden temporal y separación entre bloques](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html).
