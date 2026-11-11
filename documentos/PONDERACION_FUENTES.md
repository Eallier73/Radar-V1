# Ponderación acordada para el análisis conjunto

Decisión del usuario registrada el 10 de noviembre de 2026: usar la ponderación intermedia como escenario principal del análisis conjunto de YouTube, Twitter/X, Facebook y Medios.

## Método y pesos

Se adopta `alpha = 0.5`: `w_s = sqrt(T_s) / suma(sqrt(T_j))`, donde `T_s` es el número de palabras normalizadas observado en cada fuente. Esta transformación reduce la concentración debida al volumen de texto y conserva diferencias entre fuentes. Es una elección metodológica acordada, no una estimación de representatividad ni un óptimo demostrado.

| Fuente | Peso para cálculo | Porcentaje mostrado |
|---|---:|---:|
| YouTube | 0.2809388280054405 | 28.09% |
| Twitter/X | 0.14279471950803888 | 14.28% |
| Facebook | 0.10579986239811043 | 10.58% |
| Medios | 0.47046659008841024 | 47.05% |

Los pesos se calcularon sobre las 83 semanas del histórico, del 30 de septiembre de 2024 al 3 de mayo de 2026, con 5,801,785 palabras en total. Se conservará la precisión completa al calcular resultados. No se incorpora un factor de usuarios: el corpus no permite medir autores de manera comparable en las cuatro fuentes; los datos ausentes no equivalen a cero.

## Aplicación y comprobación

El análisis será conjunto y conservará las etiquetas de fuente y semana. Para agregar resultados comparables normalizados por fuente, usar `resultado = suma(w_s * resultado_normalizado_s)`. Para ponderar conteos de palabras, el multiplicador es `w_s / T_s`; multiplicar los conteos brutos solamente por `w_s` contaría el volumen otra vez. El mecanismo concreto de entrenamiento se definirá con el modelo elegido.

Los escenarios de igual peso (`alpha = 0`) y peso proporcional a palabras (`alpha = 1`) quedan como controles de sensibilidad. No sustituyen el escenario principal acordado. Todavía no se ha comprobado si las conclusiones temáticas o de sentimiento se mantienen entre escenarios.

Estos coeficientes corresponden a la calibración retrospectiva del histórico completo. Para desarrollar un modelo predictivo se recalibran únicamente con el periodo de entrenamiento y se congelan para prueba y verificación final.

## Calibración para la partición 56/14/13

Al generar la [partición temporal acordada](PARTICION_TEMPORAL_DATOS.md) se mantuvo `alpha = 0.5` y se recalcularon los pesos usando sólo las 56 semanas de entrenamiento, del 30 de septiembre de 2024 al 26 de octubre de 2025:

| Fuente | Peso para cálculo | Porcentaje mostrado |
|---|---:|---:|
| YouTube | 0.26708063350258315 | 26.71% |
| Twitter/X | 0.1751946357998461 | 17.52% |
| Facebook | 0.10030692333217596 | 10.03% |
| Medios | 0.4574178073653949 | 45.74% |

Se guardaron en `datos/radar_indicadores/pesos_fuentes_entrenamiento.json` y se copiaron a `datos/radar_modelado/desarrollo/entrenamiento/pesos_fuentes.json`, junto con los volúmenes y hashes de las entradas de entrenamiento. Se aplicaron a los indicadores conjuntos de la tabla completa antes de partirla; no se han aplicado a un modelo. Los de 83 semanas conservan su propósito retrospectivo. La prueba y la verificación no intervienen en esta recalibración.

## Estado y evidencia

La elección de ponderación queda aprobada y aplicada a los indicadores conjuntos de la tabla actual. El usuario aclaró que los diccionarios del proyecto anterior sí están autorizados; los datos y resultados semanales deben proceder exclusivamente de este repo. La tabla y sus particiones se recuperaron tras verificar esa procedencia. No se entrenó un modelo. Véase [INDICADORES_SEMANALES.md](INDICADORES_SEMANALES.md).

El [diagnóstico del corpus](../datos/radar_analisis/ponderacion_fuentes/analisis_ponderacion_fuentes.md), el [detalle de cálculo](../datos/radar_analisis/ponderacion_fuentes/diagnostico_ponderacion_fuentes.json) y los [coeficientes calculados](../datos/radar_analisis/ponderacion_fuentes/pesos_fuentes_propuestos.json) documentan el análisis previo a esta decisión. El estado de propuesta en esos JSON corresponde a ese diagnóstico anterior; este documento registra la adopción posterior por el usuario.
