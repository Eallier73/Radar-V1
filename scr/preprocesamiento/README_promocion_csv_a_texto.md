# Promoción semanal de CSV a TXT

`promover_csv_a_texto.py` es la única etapa que deriva corpus TXT desde los CSV
canónicos de `datos/radar_semanal_procesado`.

## Ubicación

Cada TXT se guarda junto al CSV que lo origina:

```text
datos/radar_semanal_procesado/<fuente>_semanal_procesado/<semana>/
  <semana>_<fuente>.csv
  <semana>_<fuente>.txt
```

## Contratos

- Facebook: columna `texto`; incluye `POST` y `COMENTARIO`; una fila textual
  del CSV por línea.
- Twitter/X: columna `text`; una fila del CSV por línea.
- YouTube: columna `comment_text`; una fila del CSV por línea.
- Medios: combina `titulo + texto`, aplica la limpieza histórica y envuelve el
  corpus semanal en líneas de 30 palabras.
- Las redes se guardan en minúsculas y Unicode NFC. Se conservan acentos, `ñ`,
  números, puntuación, menciones y URLs.
- La promoción no vuelve a deduplicar ni reordenar: respeta el CSV procesado.
- Un TXT existente idéntico se acepta como idempotente. Uno diferente requiere
  `--overwrite` explícito.

Los 83 TXT históricos de Medios que carecen de CSV no se descubren en
`--all-weeks` y permanecen intactos.

## Ejecución semanal

```bash
python scr/preprocesamiento/promover_csv_a_texto.py \
  --since 2026-08-10 \
  --before 2026-08-16 \
  --sources youtube twitter medios facebook
```

## Simulación histórica

```bash
python scr/preprocesamiento/promover_csv_a_texto.py \
  --all-weeks \
  --sources youtube twitter facebook \
  --dry-run \
  --overwrite
```

El runner de extracción llama automáticamente al promotor después de crear el
CSV procesado y antes de validar el contrato semanal. La etapa 2 del
orquestador permite ejecutarlo de forma independiente.
