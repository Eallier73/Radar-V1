# Redefinición operativa del objetivo de Radar

## 1. Punto de partida

El script presentado debe tomarse como punto de arranque conceptual para reorientar el pipeline de Radar.

Lo importante de ese código no es el algoritmo específico que usa —Ridge, Lasso u otro— ni tampoco las métricas internas como MAE, RMSE o R². Lo importante es que ya tenía una orientación correcta hacia el cliente: no se quedaba en métricas técnicas, sino que producía una salida interpretable para tablero y reporte.

La lógica útil del script era la siguiente:

1. Produce una predicción futura.
2. Calcula el cambio entre el valor base y el valor predicho.
3. Clasifica el movimiento como sube, baja o se mantiene.
4. Genera factores de riesgo y factores de crecimiento.
5. Construye una tabla final para tablero o reporte.

Ese debe ser el nuevo punto de partida de Radar.

## 2. Cambio central de objetivo

A partir de ahora, el objetivo principal de Radar no debe ser minimizar MAE como métrica dominante. Ojo, esto no debe interpretarse como si el MEA fuese inútil. Si los resultados esperados dependen de que el MAE se reduzca entonces eso es importante. El objetivo debe ser producir una tabla operativa útil para cliente, con cuatro componentes obligatorios:

1. Predicción futura del índice.
2. Delta en puntos entre valor actual y valor predicho.
3. Clasificación del movimiento.
4. Explicación de las variables que empujan hacia arriba o hacia abajo.

La pregunta principal ya no debe ser:

¿Qué MAE tiene el modelo?

La pregunta principal debe ser:

¿La salida del modelo le sirve al cliente para interpretar y decidir?

El MAE puede conservarse como métrica interna de control, pero no debe gobernar el producto final.

## 3. Producto esperado

El producto final de Radar debe ser una tabla operativa para cliente. La tabla debe permitir leer, por cada semana y horizonte:

- cuál es el valor actual del índice;
- cuál es el valor predicho;
- cuánto cambia en puntos;
- si sube, baja o se mantiene;
- qué variables empujan hacia arriba;
- qué variables empujan hacia abajo;
- cuál es el veredicto operativo.

La tabla objetivo debe tener una estructura como esta:

| columna              | sentido                                         |
| -------------------- | ----------------------------------------------- |
| fecha_base           | semana desde la que se predice                  |
| horizonte            | H1, H2, H3, H4                                  |
| valor_base           | valor actual del índice                         |
| valor_predicho       | predicción futura para H1, H2, H3, H4           |
| delta_puntos         | diferencia entre valor predicho y el valor real |
| tendencia_predicha   | sube / baja / se mantiene                       |
| factor_empuja_arriba | variables que aumentan el índice positivamente  |
| factor_empuja_abajo  | variables que reducen el índice negativamente   |
| veredicto_operativo  | lectura final para cliente                      |

Ejemplo de salida esperada solo de los primeros tres horizontes, el cuarto se da por sentado en el ejemplo.

| fecha_base | horizonte | valor_actual | valor_predicho | delta_puntos | tendencia               | factores_arriba                       | factores_abajo                    | veredicto                                         |
| :--------- | --------- | ------------ | -------------- | ------------ | ----------------------- | ------------------------------------- | --------------------------------- | ------------------------------------------------- |
| 2026-W10   | H1        | 21.0         | 23.2           | +2.2         | se 			mantiene | obras, 			sentimiento medios | agua, 			inseguridad     | estabilidad 			con leve presión positiva |
| 2026-W10   | H2        | 21.0         | 17.8           | -3.2         | baja                    | obras                                 | agua, 			basura, delitos | alerta 			moderada de deterioro          |
| 2026-W10   | H3        | 21.0         | 28.5           | +7.5         | sube                    | sentimiento, 			obras        | vialidad                          | mejora 			esperada                       |

## 4. Criterio central: delta_puntos

El criterio operativo principal debe ser delta_puntos que se interpreta como la medida de diferencia entre lo que el radar produce y el valor real esperado del data set. Mientras más pequeño, estable y legible sea el delta_puntos, mejor será la salida para cliente. El modelo no debe producir únicamente un valor futuro abstracto. Debe producir una lectura de movimiento:

sube
 baja
 se mantiene
 cuánto cambia
 por qué cambia

La detección de subidas, bajadas y caídas debe hacerse a partir de delta_puntos pero el delta_puntos se debe de optimizar con acuerdo a un criterio muy específico: si el valor esperado sube el delta_puntos solo es útil si se trata de una diferencia entre el valor esperado y el valor de predicción, sí el valor de predicción también subió. Si el delta_puntos se optimiza en 2% de error, ese error no puede ser algo así: valor base 66%, valor esperado 67%, valor predicho 65%. Siguiendo la lógica del ejemplo, el valor delta_puntos solo es aceptable en el rango que va de 67% a 69%,

## 5. Clasificación operativa del movimiento

La clasificación debe salir directamente del delta en puntos del índice. La lógica recomendada es:

delta_puntos >= +2 → sube
 delta_puntos <= -2 → baja
 -2 < delta_puntos < +2 → se mantiene

Esto es preferible a usar porcentaje relativo al valor base. No conviene clasificar así: delta porcentual respecto al valor actual, porque el cliente no necesita saber si el índice sube 2.% respecto a un valor base. Necesita saber si sube o baja una cantidad clara de puntos. Para cliente es más comprensible decir:

sube 3 puntos
baja 4 puntos
se mantiene dentro de ±2 puntos

que decir: sube 2% respecto al valor base

## 6. Explicación obligatoria por variables

El modelo no solo debe predecir. Debe explicar. Cada predicción debe responder:

¿Qué variables empujan hacia arriba?
¿Qué variables empujan hacia abajo?

No basta con entregar una predicción numérica. Tampoco basta con decir que el modelo detectó una subida o una baja. Para que el resultado sea útil al cliente, debe haber explicación operativa. Ejemplos de factores interpretables:

▼ presión negativa por agua
▲ impulso positivo por obras
▼ conversación crítica sobre inseguridad
▲ sentimiento favorable en medios

## 7. Diferencia entre coeficientes globales y contribuciones reales

El script viejo separaba factores usando el signo del coeficiente:

coeficiente < 0 → factor de riesgo
 coeficiente > 0 → factor de crecimiento

Esa lógica es útil como punto de partida, pero no es suficiente. No basta con listar coeficientes globales del modelo, porque eso solo dice qué variables tienden a pesar más en general. Lo que se necesita es explicar cada predicción específica. La lógica correcta debe ser:

contribución_variable = valor_variable_en_esa_semana × coeficiente_modelo

Con esto se puede saber qué empujó hacia arriba o hacia abajo en una semana concreta y para un horizonte concreto. La explicación debe salir de contribuciones reales por caso, no de una lista decorativa de variables importantes.

## 8. Factores hacia arriba y hacia abajo

Para cada predicción, el modelo debe generar dos grupos de factores: 

Factores que empujan hacia arriba: son las variables cuya contribución aumenta el valor predicho del índice. Deben reportarse como:

▲ factor positivo 1
▲ factor positivo 2
▲ factor positivo 3

Factores que empujan hacia abajo: son las variables cuya contribución reduce el valor predicho del índice. Deben reportarse como:

▼ factor negativo 1
▼ factor negativo 2
▼ factor negativo 3

La selección de factores debe hacerse por magnitud real de contribución en esa predicción. No debe hacerse por rotación, decoración, aleatoriedad o selección artificial.

top factores hacia arriba = mayores contribuciones positivas
top factores hacia abajo = mayores contribuciones negativas

## 9. Qué conservar del script viejo

Del script viejo deben conservarse cuatro elementos conceptuales.

### 9.1. La lógica de tabla final

El script construía una tabla unificada para tablero/reporte. Esa orientación debe mantenerse. Radar debe terminar en una tabla de cliente, no solo en archivos internos de métricas.

### 9.2. La clasificación por umbral

El script clasificaba los movimientos como sube, baja o igual. Esa lógica debe conservarse, pero ajustando el criterio a puntos del índice en lugar de porcentaje relativo.

### 9.3. La explicación por factores

El script ya intentaba traducir variables técnicas a factores interpretables. Esa lógica debe conservarse, pero mejorarse para que la explicación salga de contribuciones reales por predicción.

### 9.4. La orientación al tablero

El script estaba pensado para producir una salida final utilizable. Eso es exactamente lo que necesita Radar: una tabla que pueda alimentar tablero, reporte e interpretación ejecutiva.



## 10. Qué no debe copiarse del script viejo

El script viejo no debe copiarse tal cual. Debe tomarse como punto de arranque conceptual, pero rehacerse metodológicamente. Tiene cuatro problemas principales.

### 10.1. Escalamiento global del dataset

El script escala todo el dataset antes de la evaluación. Eso puede introducir información futura. En Radar, cualquier escalamiento debe hacerse dentro de cada fold temporal:

fit scaler solo con train
transform train
transform test
predecir test

### 10.2. Validación cruzada no necesariamente temporal

El script usa validación tipo cv=5 en modelos como RidgeCV o LassoCV. En series de tiempo, eso puede mezclar pasado y futuro. Radar debe usar validación temporal: TimeSeriesSplit dentro del train de cada fold externo

### 10.3. Factores calculados con modelo entrenado en toda la muestra

El script entrena un modelo final con todos los datos para obtener coeficientes. Eso puede servir para análisis exploratorio, pero no para explicación operativa limpia. En Radar, los factores deben salir del modelo disponible en el momento de la predicción. Es decir, de cada fold temporal, sin usar información futura.

### 10.4. Selección decorativa de factores

El script usa una lógica de selección de factores que puede variar artificialmente los factores mostrados. Eso no debe conservarse. La explicación debe salir de las contribuciones reales de las variables en cada predicción.

## 11. Nueva prioridad del pipeline Radar

La prioridad del pipeline debe quedar así:


| prioridad | criterio                                |
| --------- | --------------------------------------- |
| 1         | delta_puntos pequeño y legible          |
| 2         | clasificación sube / baja / se mantiene |
| 3         | detección de bajadas y caídas           |
| 4         | explicación por variables accionantes   |
| 5         | utilidad para tablero/reporte           |
| 6         | MAE como métrica secundaria             |
| 7         | loss_h como métrica secundaria          |
| 8         | R² casi irrelevante para cliente        |

Esto implica que el pipeline debe evaluarse principalmente por utilidad operativa, no por elegancia estadística.

## 12. Salidas obligatorias del nuevo Radar

El nuevo Radar debe producir, como mínimo, dos archivos orientados a cliente:

tabla_cliente_predicciones_factores_prediccion.csv
tabla_cliente_predicciones_factores_prediccion.xlsx

La tabla principal debe contener predicción, delta, tendencia y veredicto junto con la descomposición de variables que empujan hacia arriba y hacia abajo por semana y horizonte. Los archivos internos pueden seguir existiendo:

metricas_horizonte.json
 predicciones_h1.csv
 predicciones_h2.csv
 predicciones_h3.csv
 predicciones_h4.csv
 loss_h
 MAE
 RMSE

pero esos archivos son para control técnico, no para el cliente.

## 13. Nuevo estándar de evaluación

El modelo debe evaluarse con una pregunta operativa: ¿La predicción cambia o mejora una decisión del cliente? No basta con que el modelo tenga una métrica razonable. Debe permitir responder:

¿Sube?
 ¿Baja?
 ¿Se mantiene?
 ¿Cuánto se mueve?
 ¿Qué factores empujan el movimiento?
 ¿Hay alerta de deterioro?
 ¿La señal es suficientemente clara para reportarse?

Si no responde eso, el modelo no está listo para cliente.

## 14. Reformulación del pipeline

La dirección correcta ya no es: buscar el menor MAE posible

La dirección correcta es:construir un modelo explicable que produzca cambios pequeños, clasificables y accionables para cliente. Esto significa que Radar debe pasar de ser un sistema centrado en métricas internas a ser un sistema explicable de señales operativas.

