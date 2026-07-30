# Extractor semanal de comentarios de Chucho Nader

El script `scr/extraccion/6_extractors_facebook_chucho_nader_comentarios.py`
descarga únicamente comentarios públicos asociados con las publicaciones de:

`https://www.facebook.com/ChuchoNader/`

Apify exige URLs de publicaciones para su actor de comentarios. Por eso el
script usa internamente el actor de posts para descubrir las publicaciones de
cada semana, pero no guarda posts en los datos crudos. El único artefacto
semanal permanente es:

```text
datos/radar_semanal_extraido/
└── 2024-09-30_semana_30septiembre_06octubre_24/
    └── 2024-09-30_semana_30septiembre_06octubre_24_facebook_chucho_nader_comentarios.csv
```

## Ejecución

El rango predeterminado comienza el 30 de septiembre de 2024 y termina en el
último domingo completo. Así no se confirma una semana que todavía puede
recibir publicaciones.

```bash
/home/emilio/anaconda3/envs/radar-v1/bin/python \
  scr/extraccion/6_extractors_facebook_chucho_nader_comentarios.py
```

El token se lee automáticamente de `APIFY_TOKEN` en `.env` o `.env.local`.
Para revisar el plan sin gastar crédito:

```bash
/home/emilio/anaconda3/envs/radar-v1/bin/python \
  scr/extraccion/6_extractors_facebook_chucho_nader_comentarios.py \
  --dry-run
```

Para una prueba real de una sola semana y con topes conservadores:

```bash
/home/emilio/anaconda3/envs/radar-v1/bin/python \
  scr/extraccion/6_extractors_facebook_chucho_nader_comentarios.py \
  --max-weeks 1 \
  --max-comments 50
```

Sin `--max-comments`, el actor solicita todos los comentarios públicos que
pueda entregar. Se incluyen respuestas anidadas.

## Reanudación

El avance operativo se guarda en:

```text
state/facebook_chucho_nader/
├── checkpoint.json
├── eventos.jsonl
└── work/
```

Cada lote exitoso se escribe antes de adelantar el checkpoint. Al completar el
CSV semanal, sus lotes temporales se eliminan para no duplicar el volumen de
datos. Si hay bloqueo, falta de crédito, error del actor, fallo de red o
interrupción del proceso, el script se detiene con código distinto de cero. Al
ejecutar otra vez el mismo comando reutiliza los lotes confirmados y empieza en
el primero pendiente.

El estado puede consultarse sin llamar a Apify:

```bash
/home/emilio/anaconda3/envs/radar-v1/bin/python \
  scr/extraccion/6_extractors_facebook_chucho_nader_comentarios.py \
  --status
```

Si el checkpoint se pierde pero los CSV semanales permanecen, los archivos con
el encabezado esperado se reconocen como semanas completas y no se vuelven a
descargar.

## Opciones principales

- `--since YYYY-MM-DD`: fecha inicial; se alinea al lunes de esa semana.
- `--until YYYY-MM-DD`: último domingo completo que se debe procesar.
- `--max-weeks N`: limita cuántas semanas atiende una ejecución.
- `--batch-size N`: número de publicaciones por llamada al actor de comentarios.
- `--max-posts N`: tope de publicaciones descubiertas por semana.
- `--max-comments N`: tope por publicación; si se omite, no se fija un límite.
- `--output-dir RUTA`: cambia la raíz de datos crudos.
- `--state-dir RUTA`: cambia la ubicación del checkpoint reanudable.

Los datos reflejan únicamente contenido que Facebook expone públicamente y que
los actores de Apify consiguen recuperar.
