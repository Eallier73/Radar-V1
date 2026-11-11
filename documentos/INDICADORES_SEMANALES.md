# Indicadores conjuntos del corpus actual

## Alcance acordado

El usuario aclaró el 10 de noviembre de 2026 que **sí se pueden reutilizar los diccionarios del proyecto anterior**, junto con código y metodología. Lo prohibido es reutilizar sus publicaciones, corpus, CSV extraídos, conteos, resultados numéricos y tablas precalculadas.

Los indicadores se calcularon con los 332 TXT de `datos/radar_semanal_procesado/` de este repo: 83 semanas de YouTube, Twitter/X, Facebook y Medios. Los hashes se verificaron antes de recuperar la tabla. Las rutas del proyecto anterior en `datos/recursos_indicadores/procedencia.json` son evidencia de los diccionarios; el programa no las abre como corpus ni como resultados.

## Tabla de uso

`datos/radar_indicadores/tabla_analisis_ponderada.csv` es la **tabla de trabajo de 70 filas y 108 columnas**, hasta la semana que termina el 1 de febrero de 2026. Las últimas 13 semanas están fuera de este archivo. Tiene tres identificadores, 21 indicadores conjuntos ponderados y suavizados MA5 y sus 84 lags de 1 a 4 semanas. Los indicadores son polaridad **Original**, diez intensidades y diez presencias temáticas. El usuario eligió Original como respuesta y retiró Etiquetado. Son 105 candidatos numéricos.

La tabla completa de 83 filas se conserva únicamente en `datos/radar_indicadores/archivo/tabla_analisis_completa_83_semanas.csv`, para reproducir la separación. Las 13 semanas finales tienen su propio archivo reservado en `datos/radar_modelado/verificacion_reservada/indicadores.csv`. `datos/radar_modelado/desarrollo/indicadores.csv` es otra copia idéntica de las 70 filas de trabajo, divididas en 56 de entrenamiento y 14 de prueba.

El soporte técnico `tabla_indicadores_83_semanas.csv` conserva 333 columnas para rastrear conteos, denominadores, resultados por fuente y tasas sin suavizar. No es la tabla principal de uso. `variables_analisis.csv` define los 105 candidatos temporales y `variables.csv` las 329 variables numéricas del soporte. Los diccionarios Etiquetado y sus resultados anteriores se retiraron a respaldo; no se leen ni se calculan en la ejecución vigente.

## Cálculo

- **Polaridad:** `100 * positivas / (positivas + negativas)`, con unigramas y expresiones de los diccionarios autorizados. Es proporción léxica, no porcentaje de personas favorables. Se aplican las stoplists y exclusiones autorizadas; no se alteran los TXT.
- **Intensidad temática:** `1000 * coincidencias_del_tema / palabras_del_TXT`. Se conservan los diez temas del diccionario V5 y sus exclusiones. Un término puede contar en varios temas.
- **Presencia conjunta:** porcentaje de segmentos consecutivos de hasta 30 palabras que mencionan el tema, para comparar las cuatro fuentes con una unidad común. Los segmentos no se presentan como publicaciones o noticias. El soporte social también conserva presencia por registro; en Medios no se inventan noticias.
- **Integración:** `suma(peso_fuente * tasa_fuente)`, con la ponderación intermedia acordada y calibrada sólo con las primeras 56 semanas. No se aplican los pesos otra vez a la tabla final.
- **MA5:** media de la semana actual y cuatro anteriores, con al menos una observación disponible. Se conserva la ventana de cinco del método anterior y se adapta a una dirección hacia atrás para no incorporar semanas futuras. No se suaviza nuevamente al usar la tabla.
- **Lags:** para cada indicador MA5, `_lag1` copia su valor en `t-1`, y análogamente hasta `_lag4`. Se comprueba que las semanas sean únicas, consecutivas y ordenadas antes de desplazar. No se generan rezagos de rezagos ni se usan semanas futuras.

Las expresiones se buscan por palabras completas, con normalización ASCII. Las coincidencias pueden superponerse; no se cruzan líneas para los indicadores por registro. La presencia en segmentos usa la envoltura común y puede cruzar límites de registros. Sin denominador observado, una tasa queda ausente; no se inventa neutralidad.

Los 21 indicadores actuales tienen valores en las 83 semanas históricas. Los rezagos dejan 210 celdas vacías por falta de historia al inicio: 21 por cada semana de desfase acumulada (1+2+3+4). No se rellenan con cero ni con valores posteriores. El archivo completo tiene 79 filas con todos los lags; la tabla de trabajo de 70 tiene 66, y el bloque de entrenamiento de 56 tiene 52.

## Procedencia y comprobaciones

El constructor sólo admite entradas dentro de `datos/` de este repo en su CLI. Los diccionarios tienen una lista exacta de recursos y hashes; se rechazan archivos adicionales como entradas léxicas. La auditoría distingue `corpus_origin_policy: current_repository_only` de `lexicon_origin_policy: historical_dictionaries_authorized`.

El separador y el cargador verifican esa procedencia del corpus y el hash de la tabla. Las pruebas confirman que cambiar semanas posteriores no altera los indicadores anteriores ni los pesos calculados con las primeras 56 semanas.

No se recortó automáticamente la matriz ni se entrenó un pronosticador. Se realizó una [inspección descriptiva y regresiones exploratorias](INSPECCION_ESTADISTICA.md), usando Original exclusivamente como respuesta. Por instrucción del usuario, sus cuatro rezagos están excluidos de la inspección de candidatas y de las regresiones: las explicativas son sólo temáticas. La estandarización usa sólo los casos completos del bloque inicial. El código histórico que ajustaba escalas globales no se ejecuta sobre toda la tabla.

## Recuperación tras la aclaración

La retirada temporal se debió a interpretar que la prohibición incluía diccionarios. Tras la aclaración del usuario se restauraron las copias autorizadas y los resultados generados aquí, comprobando los hashes del corpus y la igualdad de las particiones. No se importó ninguna tabla de resultados del proyecto anterior.

La evidencia está en [restauracion_diccionarios_y_corpus_actual_2026-11-10.json](auditorias/restauracion_diccionarios_y_corpus_actual_2026-11-10.json). La [decisión de partición](PARTICION_TEMPORAL_DATOS.md) conserva 56/14/13; la [ponderación](PONDERACION_FUENTES.md) conserva el método intermedio.
