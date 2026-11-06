# Archivo local de material retirado

Esta carpeta no es una entrada del pipeline. Su contenido se conserva como
respaldo recuperable, sin borrarlo ni ejecutarlo. Git ignora los respaldos,
salvo este índice y los manifiestos de movimientos; así no se vuelven a
publicar corpus obsoletos por accidente.

## Limpieza del 26 de octubre de 2026

- `2026-10-26/scr/preprocesamiento/`: limpiadores antiguos de Facebook y
  YouTube que apuntaban al proyecto `Lab/.../Ml_Monica_Villarreal`, y las
  utilidades de auditoría/uniformado usadas para la homologación histórica
  de Twitter. El pipeline vigente no las invoca. El filtrado por cuentas ya
  está integrado en `limpiar_twitter_semanal.py`.
  También contiene los filtros antiguos `boots_facebook.py`,
  `boots_youtube.py`, `limpieza_boots_twitter.py` y el notebook
  `Scraping_Limpieza_Preprocesing_Data.ipynb`, archivados con autorización
  expresa del usuario y sin modificar su contenido.
- `2026-10-26/tests/`: pruebas de las dos utilidades históricas retiradas,
  conservadas junto con su implementación. Para volver a ejecutarlas hay que
  restaurar primero sus rutas originales.
- `2026-10-26/cache/`: cachés regenerables de extracción y preprocesamiento.
- `respaldos/txt_anteriores_2026-10-20_b50h7c6i/`: 249 TXT sociales antiguos
  (83 por red), retirados previamente de `datos/radar_semanal_texto/`.
  Su `MANIFIESTO.json` original conserva la procedencia y los hashes.

`manifest_2026-10-26.json` registra cada ruta original, destino, motivo,
tamaño y SHA-256. Para recuperar un archivo, cópialo a su ruta original
después de comprobar que no vas a sobrescribir una versión vigente.

Los CSV canónicos, los TXT históricos de Medios y los registros de exclusión
con valor de auditoría **no** se archivan aquí.
