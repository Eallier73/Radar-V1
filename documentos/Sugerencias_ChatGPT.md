# Sugerencias para el rediseño de Radar y el tablero de proyección

---

## 1. Corrección al criterio central: delta correcto, no delta pequeño

El documento original dice que «mientras más pequeño, estable y legible sea el delta_puntos, mejor». Tal como está redactado, ese criterio premia al modelo conservador: uno que siempre prediga «se mantiene» produce los deltas más pequeños posibles y es operativamente inútil. El criterio debe reformularse: el delta no debe ser pequeño, debe ser **correcto en signo y magnitud**. Si el índice realmente va a caer 4 puntos, el modelo debe predecir aproximadamente −4 (con 2 puntos de tolerancia de error hacia arriba o hacia abajo, es decir; desde -2 a -6 son criterios válidos).

Reformulación propuesta para la tabla de prioridades:

| prioridad | criterio |
| --------: | -------- |
| 1 | acierto direccional: sube / baja / se mantiene |
| 2 | magnitud del delta predicho cercana al delta real |
| 3 | explicación por contribuciones reales de variables |
| 4 | utilidad para tablero y veredicto |
| 5 | MAE del delta como métrica interna de control |
| 6 | MAE del nivel, RMSE, R² como métricas secundarias |

---

## 2. Calibración del umbral de clasificación

El umbral de ±2 puntos no debe fijarse por intuición. Antes de congelarlo se deben de hacer las siguientes operaciones:

1. Calcular la distribución histórica de los cambios semanales reales del índice (su desviación estándar y percentiles).
2. Fijar la banda de «se mantiene» de modo que capture el ruido natural del índice (por ejemplo, el rango donde cae el 60–70 % de los movimientos semanales).
3. Una vez calibrado, congelar el umbral y documentarlo.

Si la volatilidad natural del índice es de ±4 puntos, una banda de ±2 genera alertas constantes que el cliente aprenderá a ignorar. Si la volatilidad es de ±1.5, la banda de ±2 nunca alertará. El umbral correcto sale de los datos, no del documento

---

## 3. Reglas para la explicación de los cambios al cliente

Propuesta de gradación (con cortes calibrados igual que el umbral de §2):

| rango de delta | veredicto tipo |
| -------------- | -------------- |
| dentro de la banda de mantenimiento | estabilidad |
| baja moderada (p. ej. −2.5 a −5) | alerta moderada de deterioro |
| baja fuerte (p. ej. < −5) | deterioro pronunciado, requiere intervención |
| subida moderada | mejora gradual esperada |
| subida fuerte | mejora clara, oportunidad de capitalización |

---

## 4. Diccionario semántico condicionado al signo

Bug observado en la salida de Tampico: `Agenda_notas_corrupcion_MA5` produce la misma etiqueta («↑ Trabajo anticorrupción») tanto en riesgo como en crecimiento. Eso delata un diccionario estático por variable.

Reglas de corrección:

1. La etiqueta base de cada variable debe describir el fenómeno de forma **neutra** (p. ej. «cobertura de corrupción en agenda»), sin asumir dirección.
2. La dirección (▲ / ▼) y el grupo (empuja arriba / empuja abajo) salen **exclusivamente del signo de la contribución calculada** en esa predicción, nunca del nombre de la variable.
3. Variables semánticamente ambiguas (más notas de corrupción puede ser escándalo o agenda anticorrupción del gobierno) deben tener etiqueta doblemente neutra o, idealmente, separarse aguas arriba en el corpus.

---

## 5. Coherencia de factores dentro de un mismo horizonte

Bug observado en el tablero (horizonte 2 semanas): «Discusión Morena» aparece simultáneamente como riesgo y como oportunidad. En un modelo lineal, una misma variable no puede empujar en ambas direcciones dentro de la misma predicción. Las causas posibles son dos, y ambas requieren corrección:

- Dos features distintas comparten la misma etiqueta semántica (problema de diccionario, §6).
- La selección de factores sigue siendo decorativa (problema que el documento original ya condena en su §10.4).

Esta es la primera inconsistencia que un cliente atento va a señalar, porque parece contradicción del sistema.

Caso distinto y **legítimo**: que una variable tenga signo positivo en un horizonte y negativo en otro (p. ej. vialidades como oportunidad a 2 semanas y riesgo a 1 mes), porque son modelos distintos. Pero hay que anticiparlo en el veredicto, porque al cliente le parecerá raro si no se explica.

---

## 6. Tablero: escala compartida en los gauges

La lectura comparativa entre la semana seleccionada y los tres horizontes solo es honesta si los cuatro gauges comparten **exactamente la misma escala**, fijada en código. Si cada gauge se autoajusta a su propio rango, la posición de la aguja miente y la comparación visual se rompe. 

---

## 7. Selector de semanas: auditabilidad retrospectiva y modelos congelados

El selector de semanas convierte el tablero en una herramienta auditable: el cliente puede seleccionar una semana pasada, ver lo que el modelo predijo en ese momento y verificar contra la serie histórica si le atinaron. Eso genera una confianza que ningún reporte estático produce.

Condición técnica obligatoria: las predicciones que muestra el selector para semanas pasadas deben ser las **congeladas** — las del modelo serializado disponible en esa semana — y no una reconstrucción con el pipeline actual. Sin registro de artefactos `.pkl` por experimento, el tablero mostraría «lo que el modelo de hoy habría predicho».

---

## 8. Validación temporal (ratificación)

Se ratifican como no negociables las correcciones del documento original:

- Escalamiento dentro de cada fold temporal (fit del scaler solo con train).
- `TimeSeriesSplit` para la validación interna; nunca `cv=5` aleatorio en series de tiempo.
- Factores calculados con el modelo disponible en el momento de la predicción, sin información futura.

---

## 9. Detalles de presentación

- Corregir «Desiciones tácticas» → «Decisiones tácticas».
- La tarjeta «Tendencia predominante…» aparece truncada; es de las más valiosas del tablero. Darle espacio completo o resumirla a una palabra clave (estable / deterioro / mejora).
- Conservar tal cual el framing termómetro / barómetro / brújula por horizonte: le da al cliente una instrucción implícita de uso para cada número en lugar de tres cifras igual de abstractas.

## 
