# Contrato del corpus histórico y de las nuevas extracciones

Estado de la revisión: 20 de octubre de 2026. El alcance de esta etapa es
extractor → CSV, con la excepción histórica de Medios descrita abajo. La promoción
de CSV a TXT se verifica por separado.

## YouTube y Twitter

Los 83 CSV de cada fuente cumplen sus contratos compartidos: columnas, consultas
o cuentas objetivo, periodo semanal UTC y deduplicación. YouTube contiene 76,986
comentarios; Twitter, 9,391 registros. La validación no supone que una plataforma
devuelva para siempre el mismo número de resultados.

YouTube conserva solo `comment_text, published_at, query` y las cuatro consultas
de `youtube_data_contract.py`. Twitter conserva las doce columnas y las seis
consultas de las dos cuentas objetivo de `twitter_data_contract.py`, con respuestas
publicadas dentro de la semana. Se reextrajeron las tres semanas anómalas de
Twitter y la semana de YouTube del 10 al 16 de noviembre de 2025.

## Facebook

Histórico normalizado y extractor comparten una única implementación del contrato
en `facebook_data_contract.py`. Las siete columnas son:

```text
tipo, cuenta, url, post_url_padre, fecha, texto, num_comentarios
```

- Cuentas: `tampicogob` y `monicavtampico`.
- Fechas absolutas normalizadas a UTC y dentro de `[lunes, lunes siguiente)`.
- Las fechas relativas, ausentes o inválidas no se infieren desde la carpeta.
- Los registros con fecha fuera de semana se excluyen, sin borrar su fecha.
- Solo se conservan comentarios vinculados a un post válido de esa misma semana.
- Los comentarios cortos no vacíos se admiten también en las nuevas extracciones.
- Se mantiene la identidad de comentarios mediante sus URLs/identificadores;
  se deduplica por la misma regla en histórico y extractor.
- Los posts fechados y con URL pueden conservarse sin texto como vínculo de sus
  comentarios; no se inventa su contenido.

La normalización de 11,246 filas conserva 2,559 registros: 1,183 posts y 1,376
comentarios. Las otras 8,687 filas se preservan íntegramente en
`datos/radar_historico_excluido/facebook/`, fuera del corpus canónico. Cada fila
excluida conserva el nombre de semana y archivo, SHA-256 de entrada, posición
lógica en el CSV, valores originales, proyección y motivo de exclusión.

| Motivo | Filas |
|---|---:|
| Fecha desconocida | 3,884 |
| Fecha inválida o relativa sin referencia fiable | 2,905 |
| Fecha fuera de la semana de origen | 706 |
| Duplicado | 384 |
| Comentario sin texto | 345 |
| Comentario sin post válido en la semana | 210 |
| Cuenta desconocida | 184 |
| Cuenta fuera de las dos cuentas objetivo | 69 |

Los 83 CSV tienen el contrato correcto, pero **21 semanas quedan sin registros
verificables**. No significa ausencia de actividad: el material disponible no
permite certificar su fecha. La lista completa consta en
`auditorias/homologacion_facebook_2026-10-20.json`. Las exclusiones permanecen
disponibles para una futura recuperación con evidencia; no se presentan como
registros validados. La correspondencia del contrato no equivale a cobertura
histórica completa.

Los archivos originales están además en el historial Git anterior a este cambio;
se creó un respaldo completo previo a la normalización. La reextracción real de
Facebook del 21 al 27 de octubre de 2024 recuperó 60 posts y 324 comentarios.
Al corregir el límite exclusivo de Apify se recuperaron 13 posts del domingo que
el límite anterior omitía. El actor no pudo acceder públicamente a los comentarios
de algunos posts; esos casos no se interpretan como ausencia de comentarios.

## Medios: histórico TXT aceptado y CSV canónico desde ahora

Por decisión del usuario, los **83 TXT históricos son el material disponible y
se conservan como fuente histórica válida**. No se exige reconstruir CSV ni
recuperar fechas o consultas que esos TXT ya no contienen.

El esquema CSV actual de `medios_data_contract.py` es el canónico para las nuevas
extracciones:

```text
titulo, fecha, iso_date, fuente, autor, url, url_google, thumbnail, texto, origen
```

Existen tres CSV junto al histórico. No se supone que los TXT previos se hayan
generado a partir de ellos. La aceptación histórica verifica el formato de los
TXT y, cuando hay CSV, su encabezado; no certifica sus metadatos perdidos ni exige
igualdad CSV ↔ TXT. Las nuevas ejecuciones siguen el procesamiento y validación
completos del contrato CSV vigente.

## Verificación reproducible

Desde la raíz del repositorio:

```bash
PYTHONDONTWRITEBYTECODE=1 /home/emilio/anaconda3/envs/radar-v1/bin/python \
  scr/preprocesamiento/validar_homogeneidad_semanal.py \
  --extracted-dir datos/radar_semanal_extraido \
  --csv-only --accept-historical-media-txt --require-same-weeks
```

La aceptación del histórico TXT de Medios requiere la opción explícita. La
validación ordinaria CSV ↔ TXT no se relaja para las nuevas extracciones.
Los CSV vacíos se cuentan explícitamente en el resultado; no se ocultan como
semanas con actividad. El registro de esta comprobación está en
`auditorias/validacion_contratos_2026-10-20.json`.
