# Extractor semanal de medios sobre Chucho Nader

El script `scr/extraccion/7_extractors_medios_chucho_nader.py` consulta las
mismas fuentes configuradas en el extractor general de medios:

- `site:oem.com.mx`
- `site:milenio.com`

El objetivo es Jesús Antonio Nader Nasrallah, también conocido como Chucho
Nader. El proceso excluye al homónimo Jesús F. Nader Marcos, empresario
hotelero de Monterrey y dirigente de la Asociación de Hoteles de Nuevo León.

## Salida

El único artefacto semanal permanente se guarda junto con los demás datos
crudos:

```text
datos/radar_semanal_extraido/
└── 2024-09-30_semana_30septiembre_06octubre_24/
    └── 2024-09-30_semana_30septiembre_06octubre_24_medios_chucho_nader.csv
```

Cada CSV contiene únicamente artículos aceptados como referentes al Nader de
Tampico. Incluye la query que encontró cada noticia y la razón por la que el
filtro confirmó su identidad.

## Desambiguación

La selección se realiza en dos capas:

1. Las queries inequívocas buscan `Chucho Nader`, `Nader Nasrallah` y
   `Jesús Antonio Nader`.
2. La query ambigua de `Jesús Nader` exige contexto de Tampico, Tamaulipas,
   Ciudad Madero o Jaiba Brava y excluye `Nader Marcos`, hotelería, Monterrey
   y Nuevo León.
3. Después de descargar cada artículo, se revisan título, descripción, texto,
   fuente y URL. Las menciones explícitas a Nader Nasrallah se aceptan; las de
   Nader Marcos se rechazan; una mención ambigua solo se acepta con contexto
   local de Tampico/Tamaulipas.

El filtro posterior es el control definitivo porque un buscador puede ignorar
o reinterpretar operadores de una query.

## Ejecución

El rango predeterminado comienza el 30 de septiembre de 2024 y termina en el
último domingo completo:

```bash
/home/emilio/anaconda3/envs/radar-v1/bin/python \
  scr/extraccion/7_extractors_medios_chucho_nader.py
```

Para revisar las ocho queries y las semanas pendientes sin hacer solicitudes:

```bash
/home/emilio/anaconda3/envs/radar-v1/bin/python \
  scr/extraccion/7_extractors_medios_chucho_nader.py \
  --dry-run
```

Para una prueba de una semana:

```bash
/home/emilio/anaconda3/envs/radar-v1/bin/python \
  scr/extraccion/7_extractors_medios_chucho_nader.py \
  --max-weeks 1
```

## Reanudación

El estado se conserva en:

```text
state/medios_chucho_nader/
├── checkpoint.json
├── eventos.jsonl
└── work/
```

Cada respuesta RSS y cada artículo procesado se escriben antes de adelantar el
checkpoint. Si Google News bloquea, se agotan los reintentos, falla la red o se
interrumpe el proceso, la ejecución termina sin confirmar la semana. Al volver
a ejecutar el mismo comando continúa desde la primera query o artículo
pendiente.

Los artículos que no entregan texto completo conservan su título y descripción,
pero solo llegan al CSV si la identidad puede confirmarse y la URL resuelta
pertenece a OEM o Milenio.

Para consultar el avance:

```bash
/home/emilio/anaconda3/envs/radar-v1/bin/python \
  scr/extraccion/7_extractors_medios_chucho_nader.py \
  --status
```

Cuando un CSV semanal se escribe correctamente, el trabajo temporal de esa
semana se elimina. Si el checkpoint se pierde, los CSV con el encabezado
esperado se reconocen como semanas completas.
