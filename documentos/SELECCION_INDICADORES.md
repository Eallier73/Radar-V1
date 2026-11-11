# Redundancia y estabilidad de columnas

Revisión del 11 de noviembre de 2026, solicitada para decidir cuántas explicativas conservar para horizontes de una a cuatro semanas. El usuario conserva el indicador de Mónica Villarreal y lo renombra a `Visibilidad_MV`. El cambio posterior de encabezados conserva todos los términos y valores del análisis; no se modifican corpus, filas ni particiones.

## Alcance y criterio

`scr/operaciones/seleccionar_indicadores.py` parte de las 100 candidatas temáticas; excluye de X la polaridad Original y todos sus rezagos. Carga únicamente el bloque inicial de 56 semanas y consume exactamente las primeras 56 filas del soporte por fuente. Comprueba que esas tasas reconstruyan los valores de la tabla vigente; no carga el resto de las 83 filas ni abre prueba, archivo completo o verificación reservada.

Se usan cuatro prefijos cronológicos de 28, 35, 42 y 49 semanas. En cada uno se ajustan nuevamente los pesos intermedios, se reconstruyen MA5 y lags causales, y se usan sólo respuestas disponibles dentro del prefijo para ajustar regresiones y escalas. Se comparan las siete semanas de origen siguientes, acortando el último bloque para que ningún objetivo t+4 salga de las 56 semanas iniciales.

La ordenación usa la mediana de rangos de magnitud de coeficiente estandarizado en los cuatro horizontes y alphas 0.1/1/10. Se construye una ruta de candidatas sin correlaciones absolutas de Pearson o Spearman de al menos 0.85 entre retenidas ni VIF conjunto mayor que 5. Son umbrales metodológicos explícitos, no pruebas de significación ni evidencia de que una variable descartada carezca de información.

Se comparan los tamaños de esa ruta identificables en todos los cortes, incluido k=0 (sólo intercepto). El criterio es el promedio de errores cuadráticos normalizados por la varianza de la respuesta del prefijo, dando el mismo peso a los cuatro horizontes. Se elige el menor tamaño dentro de un error estándar del mínimo. Esta regla favorece parsimonia; con cuatro bloques dependientes no constituye un intervalo de confianza. No se examinan todos los subconjuntos posibles ni se estima rendimiento externo.

## Resultado de tamaño y estabilidad

La ruta completa permitió comparar de cero a nueve explicativas. El menor error medio y la regla de parsimonia corresponden a **una**, con error normalizado 1.0031 frente a 1.5286 para sólo intercepto. Por horizonte, la regla elige cero para una semana y una para dos, tres y cuatro semanas. Es un resultado condicionado a esta ruta y estos cortes, no la demostración de un número universal de columnas.

La identidad es inestable. La primera candidata de los prefijos 28/35/42 es visibilidad de MV medida como presencia, lag 3; la del prefijo 49 es la misma medida, lag 2. Al reajustar el orden con las 56 semanas aparece intensidad de Alumbrado actual, que no fue la primera en ninguno de los cuatro prefijos. Por eso el esquema se marca `unstable_provisional_subset` e `is_final_selection: false`. La recurrencia por familia no justifica fijar automáticamente un rezago.

La tabla reducida candidata tiene 56 filas, tres identificadores, Original como respuesta y una explicativa. Se conserva como evidencia de la revisión y no sustituye la tabla de trabajo de 70 filas. No hay todavía un conjunto definitivo que haya superado la revisión de estabilidad.

## Visibilidad de Mónica: definición y redundancia

El indicador vigente utiliza el diccionario histórico y sus exclusiones sin alterarlos. Sus términos efectivos incluyen «alcaldesa», «autoridad municipal», «gobierno municipal» y «presidenta municipal», además de variantes del nombre. Por tanto, mide menciones a la figura y al gobierno municipal; no es un conteo exclusivo del nombre ni una medida de aprobación. Esta amplitud debe tenerse en cuenta al interpretar su recurrencia.

Sobre las mismas 52 semanas completas:

- Presencia e intensidad de MV: Pearson **0.9362** antes del MA5 y **0.9381** después. La redundancia ya existe sin suavizado.
- Presencia MV MA5, lag 2 contra lag 3: Pearson **0.9253**.
- Hay 18 pares de columnas del tema MV que superan 0.85 en Pearson o Spearman.
- La mayor correlación absoluta con una columna de otro tema es aproximadamente 0.8031, por debajo del umbral empleado. Esto no descarta combinaciones multivariadas redundantes.

La visibilidad de MV no encabeza los cuatro horizontes en la inspección con las 56 semanas: los primeros lugares de Ridge alpha=1 corresponden a Agua (h=1), visibilidad MV medida como presencia, lag 2 (h=2), Economía lag 1 (h=3) y Economía actual (h=4). La recurrencia entre prefijos y el primer lugar por horizonte son diagnósticos diferentes.

Se repite todo el procedimiento excluyendo primero las cinco versiones de presencia y luego las diez columnas del tema MV, incluidas intensidad y rezagos. Es una comparación de selección interna; no una eliminación de datos ni una prueba causal. El escenario sin el tema MV elige sólo intercepto, que también obtiene el menor error de su ruta. Esto impide concluir que su asociación se deba únicamente a duplicación entre columnas, pero tampoco acredita su aporte predictivo independiente.

El objetivo sigue siendo Original MA5 en t+h: para h de uno a cuatro comparte algunas semanas de calendario con el MA5 de las explicativas en t. No se utilizaron valores posteriores a t como explicativas ni etiquetas de los conjuntos externos; tampoco debe interpretarse el objetivo como polaridad calculada exclusivamente sobre publicaciones futuras.

## Reproducción y evidencias

```bash
PYTHONDONTWRITEBYTECODE=1 /home/emilio/anaconda3/envs/radar-v1/bin/python scr/operaciones/seleccionar_indicadores.py
```

Rechaza sobrescribir resultados; `--output-dir` admite una nueva salida. En `datos/radar_analisis/seleccion_indicadores/` quedan el informe `seleccion.md`, las curvas por tamaño y horizonte, la recurrencia de columnas y familias, todas las exclusiones, las correlaciones de MV, las comparaciones sin MV, los límites temporales y los hashes de resultados. Los candidatos del JSON no constituyen una selección final. No se creó un pronosticador operativo.

Referencias metodológicas: [regla de un error estándar, Stanford](https://web.stanford.edu/class/stats202/notes/Resampling/Resampling.html?highlight=e+learning), [coeficientes correlacionados](https://scikit-learn.org/stable/auto_examples/inspection/plot_linear_model_coefficient_interpretation.html), [prevención de fugas de información](https://scikit-learn.org/stable/common_pitfalls.html). Los umbrales y la combinación de estos procedimientos son decisiones explícitas de esta revisión, no recomendaciones atribuidas a esas fuentes.
