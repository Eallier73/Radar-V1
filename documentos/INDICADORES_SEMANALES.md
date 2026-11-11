# Indicadores semanales del corpus actual

Se construye una tabla final de las 83 semanas (2024-09-30 a 2026-05-03) con los **valores conjuntos ya ponderados** y después se dividen sus filas en 56/14/13. El programa `scr/operaciones/construir_tabla_indicadores.py` no entrena ni evalúa modelos.

La tabla de uso es `tabla_analisis_ponderada.csv`: 47 columnas, tres identificadores temporales y 44 valores ponderados (22 indicadores semanales y sus 22 MA5). Los indicadores son dos proporciones de polaridad calculadas con los diccionarios Original/Etiquetado, diez intensidades temáticas y diez presencias temáticas. Las columnas por fuente y los conteos permanecen en el soporte técnico de 351 columnas. No hace falta combinar fuentes ni aplicar otra vez los pesos al usar la tabla final.

## Reglas históricas recuperadas

Las reglas faltantes se localizaron en notebooks relacionados de la misma carpeta que `Modelo_ML_MV.ipynb`:

- `Anaisis_Polaridad_ML_MV.ipynb`, celdas 1, 3 y 5: stoplist, diccionarios Original/Etiquetado y proporción de coincidencias positivas entre positivas y negativas.
- `Anaisis_Polaridad_ML_MV.ipynb`, celda 7: diccionario temático V5, stoplists temáticas, intensidad por 1000 palabras y presencia por unidad de texto.
- `Modelo_ML.ipynb`, celda 3: segmentación en bloques de 30 palabras.
- `Modelo_ML.ipynb`, celdas 5 y 7: media móvil de cinco semanas, originalmente centrada y con `min_periods=1`.

Los índices de celda usan base cero. Los notebooks se leyeron como JSON, sin ejecutarlos. Se encuentran en `/home/emilio/Datos/Ipsel/IPSEL_Tampico/Ml_Monica_Villarreal/Datos/Jupyter/`.

Los siete diccionarios/stoplists necesarios y la exclusión literal de polaridad se copiaron a `datos/recursos_indicadores/`, conservando los originales. `procedencia.json` registra origen y SHA-256. Son recursos históricos fijos: no se reestiman con el corpus reservado.

## Polaridad léxica

Se conservan las dos versiones históricas: Original y Etiquetado. Sus términos se normalizan al contrato ASCII, se aplica la exclusión interna y se eliminan stopwords generales del texto sólo para el cálculo de polaridad. Los TXT canónicos no cambian.

Se cuentan unigramas y n-gramas, admitiendo coincidencias superpuestas y coincidencias en ambos diccionarios. La búsqueda usa palabras completas y no cruza líneas. La normalización ASCII y evitar coincidencias dentro de otras palabras son adaptaciones explícitas al contrato actual.

`Sentimiento_<fuente>_Original_<diccionario> = 100 * positivas / (positivas + negativas)`.

Es una proporción de coincidencias léxicas positivas, no un porcentaje de personas favorables ni una clasificación contextual de opinión. Sin coincidencias, la tasa queda ausente; no se inventa un cero neutral. Todas las tasas de la ejecución actual tienen denominador observado.

La exclusión se recuperó evaluando el literal del notebook. Se conserva incluso `chiledeberian`, concatenado por una coma ausente en el original; no se hizo pasar una corrección por una regla histórica.

## Temas, intensidad y presencia

Se utiliza `Diccionario_Temas_V5.csv` y `Stoplists_Por_Tema_1.csv`: Corrupcion, Inseguridad, Basura, Alumbrado, Agua, Vialidades, Presencia_MV, Bienestar, Morena y Economia. Un término puede contribuir a varios temas; una expresión y su unigrama pueden contarse ambos.

`intensidad_por_1000 = 1000 * coincidencias_temáticas / palabras_totales_del_TXT`.

Las coincidencias temáticas se cuentan sin cruzar líneas. El denominador son palabras canónicas antes de quitar stopwords. Se conserva la precisión completa, sin el redondeo prematuro a tres decimales de la exportación histórica.

Para las redes, `presencia_tema_pct` es el porcentaje de registros con texto que mencionan el tema al menos una vez. Una línea social corresponde a una fila promovida, que puede ser publicación o comentario según la fuente. No se incluyen filas cuyo texto quedó vacío en la promoción.

En Medios sólo existe texto continuo envuelto: sus líneas no son noticias. No se fabrica un conteo de noticias ni una presencia por publicaciones.

Para comparar las cuatro fuentes se calcula `presencia_segmentos30_pct`: se reenvuelve en memoria el texto de cada fuente y semana en segmentos consecutivos de hasta 30 palabras, incluido el fragmento final, siguiendo la segmentación histórica. Se mide qué porcentaje de segmentos menciona cada tema. La segmentación puede atravesar límites de registros sociales y no representa unidades documentales. No modifica los TXT ni las tasas por registro.

La presencia **conjunta** utiliza únicamente estos segmentos comunes; no mezcla porcentajes de comentarios con supuestos porcentajes de noticias.

## Integración y MA5

Los nombres de fuente son `Youtube`, `XTwitter`, `Facebook`, `Medios` y `Conjunto`. No se equipara el antiguo nombre ambiguo «Fuentes» con una fuente concreta.

Los indicadores conjuntos son `suma(peso_fuente * tasa_fuente)`. Se aplica la ponderación intermedia acordada a tasas normalizadas, sin multiplicar otra vez conteos brutos por esos pesos. La calibración usa sólo el volumen de las primeras 56 semanas, un límite conocido antes de construir la tabla, sin partir físicamente los textos. Los coeficientes están en `pesos_fuentes_entrenamiento.json` y [PONDERACION_FUENTES.md](PONDERACION_FUENTES.md). Si falta una tasa, su indicador conjunto queda ausente; no se renormalizan los pesos silenciosamente.

Se conserva la ventana de cinco semanas y el mínimo de una observación, pero se adapta `center=True` a una media **hacia atrás**, de `t-4` a `t`. El centrado histórico incorporaría hasta dos semanas futuras y contaminaría la verificación. Esta diferencia responde a la independencia solicitada por el usuario.

Se guardan las tasas e intensidades originales y sus columnas `_MA5`, junto con los conteos de soporte. No se suavizan identificadores ni se añaden rezagos. Las primeras cuatro semanas usan los antecedentes disponibles. Los ausentes se omiten del promedio; una ventana sin observaciones queda ausente.

No se estandariza la tabla completa ni se seleccionan predictores con prueba o verificación. Los ajustes que aprenden de los datos se realizarán sólo con entrenamiento.

## Alcance y archivos

No se importaron encuestas, agenda, engagement o autores desconocidos como si procedieran del corpus actual. Tampoco se fabricó un objetivo IAD: el índice histórico de votos por comentario no equivale a esta proporción léxica. La tabla contiene las mediciones que el corpus y los recursos recuperados permiten calcular.

- `datos/radar_indicadores/tabla_analisis_ponderada.csv`: tabla principal de 83 filas y 47 columnas, sin valores faltantes en esta ejecución.
- `variables_analisis.csv`: definición de las 44 columnas numéricas de la tabla final.
- `tabla_indicadores_83_semanas.csv`: soporte técnico de 83 filas y 351 columnas, con los valores de cada fuente y los conjuntos.
- `variables.csv`, en el mismo directorio: nombre, unidad y fórmula de las 347 variables numéricas.
- `detalle_fuentes.json`: soporte de las 332 combinaciones de fuente y semana.
- `pesos_fuentes_entrenamiento.json`: coeficientes y hashes de las 224 entradas de calibración.
- `auditoria.json`: hashes de entradas, recursos y salidas, cobertura y suavizado.

Las tres particiones de esta tabla se describen en [PARTICION_TEMPORAL_DATOS.md](PARTICION_TEMPORAL_DATOS.md). Las particiones textuales anteriores están respaldadas y ya no sustituyen a los indicadores.
