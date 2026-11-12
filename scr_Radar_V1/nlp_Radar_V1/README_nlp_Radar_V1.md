# NLP vigente de Radar V1

La única implementación vigente que aplica diccionarios y calcula polaridad, intensidad y presencia está en `scr_Radar_V1/nlp_Radar_V1/construir_tabla_indicadores_Radar_V1.py`. La etapa NLP de la GUI ejecuta directamente ese mismo archivo. La inspección y selección estadística siguen en `scr_Radar_V1/operaciones_Radar_V1/`; no son un segundo procesamiento léxico. Se reutilizan y adaptan código y reglas autorizados, y sólo se procesa el corpus actual.

Este directorio contiene el único constructor NLP y el notebook de referencia. La GUI ejecuta directamente `construir_tabla_indicadores_Radar_V1.py`; no se necesita otro runner.

`Anaisis_Polaridad_ML_MV_Radar_V1.ipynb` se conserva por instrucción del usuario como referencia para emular el modelo y la salida tabular destinada al tablero. Su implementación se adaptará al corpus y contrato actuales; los datos y resultados históricos del notebook no son entradas del análisis.

La referencia de modelado aportada por el usuario, `Modelo_ML_MV.ipynb`, sigue disponible en `/home/emilio/Datos/Ipsel/IPSEL_Tampico/Ml_Monica_Villarreal/Datos/Jupyter/Modelo_ML_MV.ipynb`. No se movió ni modificó. Se conservarán el diseño del modelo y la estructura de salida que se acuerde emular, aplicando la preparación temporal vigente y calculando los valores con los datos de Radar V1.

Los diez scripts experimentales anteriores quedaron archivados íntegros en `trash_Radar_V1/respaldos_historico_Radar_V1/`. Conservaban rutas, contratos o dependencias que no corresponden al flujo actual. Sus ubicaciones y hashes están en [el manifiesto de limpieza](../../trash_Radar_V1/manifest_limpieza_2026-11-11_historico_Radar_V1.json).
