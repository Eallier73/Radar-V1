# Comprobación documental antes de commit

`pre-commit` verifica que cada commit incluya documentación en `documentos_Radar_V1/` y que el documento principal corresponda a los scripts preparados en el índice. Git exige que el hook se llame exactamente `pre-commit`.

Antes de preparar el commit, ejecutar desde la GUI **Actualizar documentación** o:

```bash
python -B scr_Radar_V1/operaciones_Radar_V1/actualizar_documentacion_Radar_V1.py
```

Preparar después el código y los .md correspondientes. El hook no añade archivos al índice ni modifica datos. La configuración local es `core.hooksPath=githooks_Radar_V1`; al clonar se debe configurar esa ruta.
