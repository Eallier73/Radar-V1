# Selección de indicadores semanales sin suavizado

Revisión corregida del 11 de noviembre de 2026. Se conserva `Visibilidad_MV` y se retiran MA5 y todos los rezagos de X. El corpus, los diccionarios y las tasas semanales originales se preservan. Los resultados que dependían de las transformaciones retiradas quedan archivados.

## Procedimiento temporal

La entrada tiene veinte candidatas temáticas y polaridad Original como respuesta, todas semanales. Se cargan únicamente las primeras 56 filas del soporte por fuente y el archivo inicial, comprobando su procedencia y correspondencia. No se abren prueba, verificación ni el archivo completo para elegir columnas.

Se usan cuatro cortes con prefijos de 28/35/42/49 semanas. Dentro de cada corte:

1. Calibrar los pesos intermedios sólo con las palabras del prefijo y reconstruir tasas ponderadas semanales, sin suavizado.
2. Formar pares X(t), Y(t+h), con h=1/2/3/4. Toda respuesta usada para ajustar debe estar dentro del prefijo; se purgan los últimos h orígenes.
3. Ajustar escalas y regresiones únicamente con esos pares.
4. Ordenar por la mediana de los rangos de magnitud de coeficiente estandarizado en cuatro horizontes y alphas 0.1/1/10.
5. Construir una ruta sin correlaciones absolutas de Pearson o Spearman de al menos 0.85 entre retenidas ni VIF conjunto mayor que 5.
6. Comparar tamaños de esa ruta, incluido sólo intercepto, sobre orígenes posteriores cuyo objetivo permanezca dentro de las 56 semanas iniciales.

El error de cada horizonte se normaliza con la varianza de la respuesta de su prefijo. Los cuatro horizontes pesan igual. Se elige el menor tamaño dentro de un error estándar entre bloques del mínimo. Es un criterio explícito de parsimonia; cuatro bloques dependientes no permiten interpretarlo como intervalo de confianza. No se comparan todos los subconjuntos posibles.

## Resultado corregido

Se compararon de cero a diez explicativas. El menor error medio corresponde a una (0.9914), pero la referencia sin explicativas obtiene 1.0112 y queda dentro del umbral de parsimonia (1.3162). El procedimiento común elige **sólo intercepto**: no respalda todavía una selección temática común para los cuatro horizontes.

Por separado, la regla elige cero explicativas para horizontes 1/2/3 y una para horizonte 4. Estos son diagnósticos internos y no se convierten automáticamente en cuatro listas definitivas. No demuestran que las variables carezcan de asociación ni que otro procedimiento no pueda resultar útil.

La matriz base conserva las veinte candidatas. `tabla_inspeccion_reducida_Radar_V1.csv`, al tener cero explicativas elegidas, conserva sólo fechas y respuesta como evidencia del resultado; **no es una matriz de entrada lista para un modelo**. El manifiesto mantiene `is_final_selection: false`. La propuesta anterior de Alumbrado con MA5 queda retirada.

## Visibilidad y redundancia

La correlación semanal entre presencia e intensidad de `Visibilidad_MV` es 0.9479 sobre las 56 semanas. Se repite la selección excluyendo primero presencia (quedan 19 candidatas) y luego todo el tema (quedan 18). Los tres escenarios comunes conservan sólo intercepto con esta regla. Son comparaciones internas de procedimientos, no estimaciones causales del aporte de Mónica.

El diccionario sigue incluyendo nombres y referencias a cargos o gobierno municipal; cambiar el esquema temporal no altera su significado. No se borra ninguna columna temática de la tabla principal.

## Evidencia y límites

El informe y CSV se encuentran en `datos_Radar_V1/radar_analisis_Radar_V1/seleccion_indicadores_Radar_V1/`. `limites_temporales_Radar_V1.csv` registra fechas y pesos de cada corte; las curvas muestran todas las cantidades comparadas; los coeficientes por corte, correlaciones y exclusiones permiten inspeccionar cada decisión.

Los errores usados para elegir tamaño no son una evaluación independiente del conjunto definitivo. Prueba y las 13 semanas reservadas siguen disponibles para una evaluación futura. Las semanas se consideran observables al cierre; no se adelantan explicativas de semanas posteriores.

Referencias: [prevención de fugas de información](https://scikit-learn.org/stable/common_pitfalls.html), [separación temporal](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html), [regla de un error estándar](https://web.stanford.edu/class/stats202/notes/Resampling/Resampling.html?highlight=e+learning). Los umbrales y la combinación del procedimiento son decisiones explícitas de esta revisión.

<!-- source-fingerprint: 318cf86657dccc649eeb7d9b48818089478a6799d7d9b626efef2f72328e5e79 -->
