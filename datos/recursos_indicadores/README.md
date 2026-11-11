# Recursos fijos de indicadores

Copias de los recursos históricos de Tampico que alimentaban los notebooks de polaridad y temas. `procedencia.json` conserva las rutas originales y hashes SHA-256; los archivos originales no se modificaron.

| Recurso | Uso |
|---|---|
| `diccionario_palabras_positivas.txt`, `diccionario_palabras_negativas.txt` | Polaridad Original. |
| `diccionario_positivo_etiquetado.txt`, `diccionario_negativo_etiquetado.txt` | Polaridad Etiquetado. |
| `stop_list_español.txt` | Filtrado de tokens para polaridad, sin alterar los TXT canónicos. |
| `exclusiones_polaridad.json` | Literal `stoplist` recuperado de la celda 5 de `Anaisis_Polaridad_ML_MV.ipynb`. |
| `Diccionario_Temas_V5.csv` | Unigramas y expresiones de los diez temas históricos. |
| `Stoplists_Por_Tema_1.csv` | Exclusiones temáticas históricas. |

El constructor comprueba los hashes, normaliza términos al contrato ASCII y usa los recursos como entradas fijas; no aprende nuevas palabras del corpus de prueba o verificación. No son textos históricos promovidos ni resultados de entrenamiento. Las definiciones y adaptaciones están en [INDICADORES_SEMANALES.md](../../documentos/INDICADORES_SEMANALES.md).
