# NLP de Radar V1

La aplicación vigente de diccionarios y el cálculo de polaridad, intensidad y presencia están en `scr/operaciones/construir_tabla_indicadores.py`; su inspección y selección están en la misma carpeta. Esas rutinas reutilizan y adaptan código y reglas autorizados, y sólo procesan el corpus actual.

Este directorio queda reservado para integrar el runner NLP del orquestador. `run_nlp.py` todavía no existe; la interfaz mantiene la etapa como pendiente.

`Anaisis_Polaridad_ML_MV.ipynb` se conserva por instrucción del usuario como referencia para emular el modelo y la salida tabular destinada al tablero. Su implementación se adaptará al corpus y contrato actuales; los datos y resultados históricos del notebook no son entradas del análisis.

La referencia de modelado aportada por el usuario, `Modelo_ML_MV.ipynb`, sigue disponible en `/home/emilio/Datos/Ipsel/IPSEL_Tampico/Ml_Monica_Villarreal/Datos/Jupyter/Modelo_ML_MV.ipynb`. No se movió ni modificó. Se conservarán el diseño del modelo y la estructura de salida que se acuerde emular, aplicando la preparación temporal vigente y calculando los valores con los datos de Radar V1.

Los diez scripts experimentales anteriores quedaron archivados íntegros en `trash/respaldos/`. Conservaban rutas, contratos o dependencias que no corresponden al flujo actual. Sus ubicaciones y hashes están en [el manifiesto de limpieza](../../trash/manifest_limpieza_2026-11-11.json).
