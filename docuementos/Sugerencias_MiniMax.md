# Rediseño de Radar — Propuesta consolidada

## 0. Resumen ejecutivo

Radar dejó de ser un modelo predictivo y pasó a ser un **sistema explicable de señales operativas**: predice, clasifica y explica el movimiento del índice en puntos, con factores verificables y un veredicto listo para tablero.

Tres decisiones que se piden al equipo:

1. **El delta correcto sustituye al delta pequeño.** El criterio operativo deja de premiar la conservaduría del modelo; premia que el signo y la magnitud del cambio predicho coincidan con lo que realmente ocurrió.
3. **Las explicaciones se calculan por movimiento, no por nivel.** La descomposición de contribuciones usa la desviación de cada variable respecto a su media de entrenamiento, no su valor absoluto, para que un «baja» nunca se explique con factores positivos.

La corrida de Tampico ya exhibió los tres defectos que estas decisiones corrigen: clasificación con la misma etiqueta en riesgo y crecimiento, factores duplicados por tema, y explicaciones que contradicen la dirección predicha.

---

## 1. Punto de partida

El script presentado debe tomarse como punto de arranque conceptual para reorientar el pipeline de Radar. Lo importante de ese código no es el algoritmo específico —Ridge, Lasso u otro— ni las métricas internas como MAE, RMSE o R². Lo importante es que ya tenía una orientación correcta hacia el cliente: no se quedaba en métricas técnicas, sino que producía una salida interpretable para tablero y reporte.

La lógica útil del script era:

- Produce una predicción futura.
- Calcula el cambio entre el valor base y el valor predicho.
- Clasifica el movimiento como *sube*, *baja* o *se mantiene*.
- Genera factores de riesgo y factores de crecimiento.
- Construye una tabla final para tablero o reporte.

Ese es el nuevo punto de partida de Radar.

---

## 2. Cambio central de objetivo

El objetivo principal de Radar deja de ser minimizar MAE como métrica dominante. El objetivo es producir una **tabla operativa útil para cliente**, con cuatro componentes obligatorios:

1. Predicción futura del índice.
2. Delta en puntos entre el valor actual y el valor predicho.
3. Clasificación del movimiento.
4. Explicación de las variables que empujan hacia arriba o hacia abajo.

La pregunta principal ya no es «¿qué MAE tiene el modelo?», sino «¿la salida del modelo le sirve al cliente para interpretar y decidir?». El MAE se conserva como métrica interna de control, pero no gobierna el producto final.

---

## 3. Producto esperado

El producto final de Radar es una tabla operativa para cliente. Por cada semana y horizonte debe permitir leer:

- cuál es el valor actual del índice;
- cuál es el valor predicho;
- si sube, baja o se mantiene;
- qué variables empujan hacia arriba;
- qué variables empujan hacia abajo;
- cuál es el veredicto operativo.

### 3.1 Estructura de la tabla objetivo

| columna               | sentido                                        |
| --------------------- | ---------------------------------------------- |
| `fecha_base`          | semana desde la que se predice                 |
| `horizonte`           | H1, H2, H3, H4                                 |
| `valor_base`          | valor actual del índice                        |
| `valor_predicho`      | predicción futura                              |
| `tendencia_predicha`  | sube / baja / se mantiene                      |
| `factor_arriba`       | variables que aumentan el índice (con signo ▲) |
| `factor_abajo`        | variables que reducen el índice (con signo ▼)  |
| `veredicto_operativo` | lectura final para cliente                     |

### 3.2 Ejemplo de salida esperada

| fecha_base | horizonte | valor_actual | valor_predicho | tendencia      | factores_arriba              | factores_abajo              | veredicto                          |
| ---------- | --------- | ------------ | -------------- | -------------- | ---------------------------- | --------------------------- | ---------------------------------- |
| 2026-W10   | H1        | 21.0         | 23.2           | se mantiene    | obras, sentimiento medios    | agua, inseguridad           | estabilidad con leve presión positiva |
| 2026-W10   | H2        | 21.0         | 17.8           | baja           | obras                        | agua, basura, delitos        | alerta moderada de deterioro       |
| 2026-W10   | H3       | 21.0         | 28.5           | sube           | sentimiento, obras           | vialidad                    | mejora clara, oportunidad de capitalización |

---

## 4. Criterio central: acierto direccional, no delta pequeño

El delta no debe ser pequeño. Debe ser **correcto en signo y magnitud**. 

### 4.1 Nueva tabla de prioridades del pipeline

| prioridad | criterio                                           |
| --------: | -------------------------------------------------- |
|         1 | acierto direccional: sube / baja / se mantiene     |
|         2 | magnitud del delta predicho cercana al delta real  |
|         3 | explicación por contribuciones reales de variables |
|         4 | utilidad para tablero y veredicto                  |
|         5 | MAE del delta como métrica interna de control      |
|         6 | MAE del nivel, RMSE, R² como métricas secundarias  |

---

## 5. Calibración del umbral de clasificación

El umbral de ±2 puntos no debe fijarse por intuición. Antes de congelarlo:

1. Calcular la distribución histórica de los cambios semanales reales del índice: desviación estándar y percentiles.
2. Fijar la banda de «se mantiene» de modo que capture el ruido natural del índice (por ejemplo, el rango donde cae el 60–70 % de los movimientos semanales).
3. Una vez calibrado, congelar el umbral y documentarlo.

Si la volatilidad natural del índice es de ±4 puntos, una banda de ±2.5 genera alertas constantes que el cliente aprenderá a ignorar. Si la volatilidad es de ±1.5, la banda de ±2.5 nunca alertará. **El umbral correcto sale de los datos, no del documento.**

Lógica de clasificación, una vez calibrado el umbral `U`:

```text
delta_puntos >=  +U  →  sube
delta_puntos <=  -U  →  baja
-U < delta_puntos < +U  →  se mantiene
```

Se prefiere el umbral en puntos al porcentaje relativo al valor base, porque el cliente necesita saber si el índice sube «3 puntos» o baja «4 puntos», no un porcentaje cuya lectura cambia según el valor base.

---

## 6. Descomposición de contribuciones: explicar el movimiento, no el nivel

La fórmula original (`contribución = valor_variable × coeficiente`) explica el **nivel** predicho respecto al intercepto, no el **movimiento** respecto al valor actual, que es lo que el cliente lee en el tablero.

Para que los factores expliquen por qué la predicción se aleja del comportamiento típico, la descomposición defendible es:

```text
contribución_i = β_i × (x_i,t − x̄_i,train)
```

donde `x̄_i,train` es la media de la variable en el conjunto de entrenamiento del fold correspondiente. Así cada contribución mide cuánto se desvía la variable de su nivel típico y cuánto empuja eso la predicción lejos de la predicción media.

Sin este ajuste puede ocurrir que una predicción clasifique «baja» pero sus top factores sean todos positivos, lo cual es incomprensible para el cliente.

Esta descomposición es exactamente lo que SHAP se reduce a calcular en modelos lineales, así que mientras Radar se mantenga en Ridge/Lasso se obtiene explicabilidad rigurosa sin dependencias adicionales. Si el pipeline migra a árboles o ensambles, se necesitará SHAP explícito.

---

## 7. Diccionario semántico condicionado al signo

**Bug observado en la corrida de Tampico:** `Agenda_notas_corrupcion_MA5` produce la misma etiqueta («↑ Trabajo anticorrupción») tanto en riesgo como en crecimiento. Eso delata un diccionario estático por variable.

Reglas de corrección:

1. La etiqueta base de cada variable debe describir el fenómeno de forma **neutra** (por ejemplo, «cobertura de corrupción en agenda»), sin asumir dirección.
2. La dirección (▲ / ▼) y el grupo (empuja arriba / empuja abajo) salen **exclusivamente del signo de la contribución calculada** en esa predicción, nunca del nombre de la variable.

---

## 8. Coherencia de factores dentro de un mismo horizonte

**Bug observado en el tablero (horizonte 2 semanas):** «Discusión Morena» aparece simultáneamente como riesgo y como oportunidad. En un modelo lineal, una misma variable no puede empujar en ambas direcciones dentro de la misma predicción. Las causas posibles son dos, y ambas requieren corrección. Esta es la primera inconsistencia que un cliente atento va a señalar, porque parece contradicción del sistema. **Caso distinto y legítimo:** que una variable tenga signo positivo en un horizonte y negativo en otro (por ejemplo, vialidades como oportunidad a 2 semanas y riesgo a 1 mes), porque son modelos distintos. Hay que anticiparlo en el veredicto, porque al cliente le parecerá raro si no se explica.

---

## 9. Tablero: escala compartida en los gauges

La lectura comparativa entre la semana seleccionada y los tres horizontes solo es honesta si los cuatro gauges comparten **exactamente la misma escala**, fijada en código. Si cada gauge se autoajusta a su propio rango, la posición de la aguja miente y la comparación visual se rompe. En la captura actual parecen consistentes; debe garantizarse que es por diseño y no por casualidad del rango de datos.

---

## 10. Selector de semanas: auditabilidad retrospectiva y modelos congelados

El selector de semanas convierte el tablero en una herramienta auditable: el cliente puede seleccionar una semana pasada, ver lo que el modelo predijo en ese momento y verificar contra la serie histórica si le atinaron. Eso genera una confianza que ningún reporte estático produce.

**Condición técnica obligatoria:** las predicciones que muestra el selector para semanas pasadas deben ser las **congeladas** — las del modelo serializado disponible en esa semana — y no una reconstrucción con el pipeline actual. Sin registro de artefactos `.pkl` por experimento, el tablero mostraría «lo que el modelo de hoy habría predicho».

---

## 11. Validación temporal (ratificación)

Se ratifican como no negociables las correcciones del documento base:

- Escalamiento dentro de cada fold temporal (fit del scaler solo con train).
- `TimeSeriesSplit` para la validación interna; nunca `cv=5` aleatorio en series de tiempo.
- Factores calculados con el modelo disponible en el momento de la predicción, sin información futura.

---

## 15. Catálogo cerrado de variables reportables

**Problema que resuelve:** con 254 variables y 248 válidas, la probabilidad de fuga o de regresión silenciosa del modelo es alta. Cualquier cambio en el pipeline puede hacer que el top-3 de esta semana sea distinto al de la próxima, sin que haya razón sustantiva.

**Recomendación:** definir un **catálogo cerrado y versionado** de variables elegibles para explicación, separado del conjunto de entrenamiento. Variables fuera del catálogo no se reportan, aunque tengan coeficiente alto. El catálogo se congela por experimento y se documenta su hash en el `.pkl`.

**Beneficio:** el cliente ve un universo estable de factores; el equipo puede mover features internas sin romper el contrato con el tablero.

---

## 16. Plan de implementación por fases

### Fase 0 — Calibración de datos (1 iteración, bloqueante)

- Calcular distribución histórica de cambios semanales del índice.
- Fijar umbral de «se mantiene» documentado.
- Definir catálogo cerrado inicial de variables reportables.

### Fase 1 — Rediseño del pipeline (1–2 iteraciones)

- Reemplazar fórmula de contribuciones por `β × (x − media_train)`.
- Implementar diccionario semántico neutro + dirección por signo.
- Implementar deduplicación por tema.
- Implementar veredicto graduado (5 niveles) además de etiqueta única.

### Fase 2 — Métricas de control (1 iteración)

- Implementar matriz de confusión direccional por horizonte.
- Implementar acierto de signo por horizonte.
- Implementar MAE del delta.
- Congelar el script de evaluación y versionar junto al modelo.

**Criterio de salida:** archivo `metricas_horizonte.json` con las tres métricas por horizonte, reproducible desde un experimento congelado.

### Fase 3 — Tablero (1–2 iteraciones)

- Fijar escala compartida de gauges en código.
- Implementar selector de semanas con predicciones congeladas por `.pkl`.
- Publicar bitácora de cambios visible para el cliente.
- Tarjeta «Tendencia predominante» con espacio completo o palabra clave.

**Criterio de salida:** tablero funcional con selector retrospectivo verificable.

### Fase 4 — Operación continua

- Revisión editorial por muestra cada N corridas.
- Procedimiento de actualización del catálogo documentado.

**Criterio de salida:** política de mantenimiento firmada por el equipo.
