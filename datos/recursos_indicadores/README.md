# Diccionarios y stoplists autorizados

El usuario autorizó reutilizar los diccionarios del proyecto anterior. Sus publicaciones, corpus, CSV extraídos, conteos, resultados y tablas precalculadas no son entradas autorizadas.

Este directorio contiene el par de diccionarios de polaridad **Original**, el diccionario temático V5, las stoplists generales y temáticas y las exclusiones de polaridad. El usuario pidió retirar Etiquetado, que ya no es una entrada activa. `procedencia.json` registra el origen y SHA-256 de cada recurso vigente.

Las rutas originales son sólo evidencia. El programa lee estas copias locales y el corpus de `datos/radar_semanal_procesado/`; no abre datos del proyecto anterior. El constructor comprueba los hashes y exige exactamente la lista de recursos léxicos conocida.

Las [fórmulas y unidades](../../documentos/INDICADORES_SEMANALES.md) explican cómo se calculan de nuevo los valores con el corpus actual. Los diccionarios no contienen resultados semanales importados.
