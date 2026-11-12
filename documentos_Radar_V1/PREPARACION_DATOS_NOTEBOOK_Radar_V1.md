# Referencia histórica del notebook y flujo vigente

Del proyecto anterior se reutilizaron diccionarios, código y reglas de procesamiento autorizados. La lógica para aplicar los diccionarios, contar coincidencias y calcular polaridad, intensidad y presencia se adaptó a los scripts actuales de `scr_Radar_V1/operaciones_Radar_V1/`. No se reutilizaron publicaciones, CSV extraídos ni resultados numéricos de ese proyecto: los indicadores se calcularon de nuevo con el corpus de Radar V1.

La corrección del 11 de noviembre de 2026 sustituye la preparación histórica: **sin MA5, sin rezagos adicionales de X y sin estandarización global antes de separar temporalmente**. La tabla vigente contiene 70 filas y 24 columnas: fechas, Original semanal y veinte candidatas temáticas. Véase [INDICADORES_SEMANALES_Radar_V1.md](INDICADORES_SEMANALES_Radar_V1.md).

Las funciones copiadas en `preparar_indicadores_semanales.py` ajustaban `StandardScaler` sobre la tabla completa, incluido el objetivo. El script `Modelo_Radar_1.py` también incluía preparación global y rutas a tablas del proyecto anterior. Ambos carecían de consumidores en el flujo vigente y se archivaron íntegros en `trash_Radar_V1/respaldos_historico_Radar_V1/correccion_sin_suavizado_2026-11-11_vzi2rys5_historico_Radar_V1/codigo_retirado_historico_Radar_V1/`, con hashes en su manifiesto. No se ejecutaron sobre el corpus actual.

La copia del código y las notas anteriores se conservan en el mismo respaldo. Se retira su ejemplo de uso para impedir que se aplique por error a prueba o verificación.

La limpieza posterior archivó los scripts experimentales de `scr_Radar_V1/nlp_Radar_V1/`. El usuario conserva expresamente `scr_Radar_V1/nlp_Radar_V1/Anaisis_Polaridad_ML_MV_Radar_V1.ipynb` como referencia para emular el modelo y la salida de tabla para el tablero. Su contenido se conserva íntegro, sin ejecutar ni importar sus datos o resultados anteriores. La adaptación usará el corpus y el contrato temporal actuales. Las rutinas adaptadas de aplicación de diccionarios que utiliza `construir_tabla_indicadores_Radar_V1.py` permanecen activas. El inventario recuperable se encuentra en `trash_Radar_V1/manifest_limpieza_2026-11-11_historico_Radar_V1.json`.

El notebook de modelado aportado originalmente, `Modelo_ML_MV.ipynb`, permanece sin cambios en `/home/emilio/Datos/Ipsel/IPSEL_Tampico/Ml_Monica_Villarreal/Datos/Jupyter/Modelo_ML_MV.ipynb`. La emulación del modelo y de su salida tabular deberá respetar la preparación temporal vigente; conservar la referencia no autoriza a reutilizar sus datos ni resultados numéricos.

El flujo activo es construcción de indicadores semanales, partición 56/14/13 e inspección/selección con ajuste de pesos y escalas dentro de cada corte temporal. Las escalas no se guardan aplicadas a toda la tabla ni se ajustan con prueba o verificación. Los horizontes desplazan sólo la respuesta hacia una semana futura concreta.

<!-- source-fingerprint: 318cf86657dccc649eeb7d9b48818089478a6799d7d9b626efef2f72328e5e79 -->
