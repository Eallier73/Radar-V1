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

Histórico normalizado y extractor comparten las siete columnas y los controles
de `facebook_data_contract.py`. Por decisión del usuario, el histórico admite
además las excepciones de fecha registradas en `facebook_historical_contract.py`;
estas excepciones no se aplican a los extractores. Las siete columnas son:

```text
tipo, cuenta, url, post_url_padre, fecha, texto, num_comentarios
```

- Cuentas: `tampicogob` y `monicavtampico`.
- Las fechas absolutas verificables se normalizan a UTC y deben estar dentro de
  `[lunes, lunes siguiente)`.
- Las fechas relativas, ausentes o inválidas no se infieren desde la carpeta.
- En el histórico se reincorporan exclusivamente los registros autorizados por
  procedencia: se conserva literalmente su fecha original y se mantiene su
  semana de origen, sin certificar que sea su semana real de publicación.
- Los registros con fecha fuera de semana se excluyen, sin borrar su fecha.
- Solo se conservan comentarios vinculados a un post válido de esa misma semana.
- Los comentarios cortos no vacíos se admiten también en las nuevas extracciones.
- Se mantiene la identidad de comentarios mediante sus URLs/identificadores;
  se deduplica por la misma regla en histórico y extractor.
- Los posts fechados y con URL pueden conservarse sin texto como vínculo de sus
  comentarios; no se inventa su contenido.

La auditoría inicial del 20 de octubre normalizó 11,246 filas y conservó 2,559
registros: 1,183 posts y 1,376 comentarios. Sus 8,687 exclusiones originales
siguen preservadas íntegramente en `datos/radar_historico_excluido/facebook/`.
Ese registro es una auditoría de la decisión inicial, no la lista actual de
material fuera del corpus. Cada fila conserva semana y archivo de origen,
SHA-256 de entrada, posición lógica, valores originales, proyección y motivo.

| Motivo inicial | Filas | Estado actual |
|---|---:|---|
| Fecha desconocida | 3,884 | Reincorporadas al histórico |
| Fecha inválida o relativa sin referencia fiable | 2,905 | Reincorporadas al histórico |
| Fecha fuera de la semana de origen | 706 | Excluidas |
| Duplicado | 384 | Excluidas |
| Comentario sin texto | 345 | Excluidas |
| Comentario sin post válido en la semana | 210 | Reincorporados tras recuperar su post padre |
| Cuenta desconocida | 184 | Excluidas |
| Cuenta fuera de las dos cuentas objetivo | 69 | Excluidas |

El 6 de noviembre se autorizó reincorporar las 6,789 filas excluidas por fecha
desconocida o inválida. Esa intervención llevó el corpus a 9,348 registros en
83 CSV, pero dejó cinco TXT sin texto: cuatro semanas tenían únicamente posts
sin contenido textual y la del 24 de marzo de 2025 seguía sin registros.

El 9 de noviembre, por autorización del usuario para resolver los cinco vacíos,
se reincorporaron los 210 comentarios cuyos posts padre ya se habían recuperado.
Sus fechas son verificables y sus vínculos ahora satisfacen el contrato; no se
añadió ninguna excepción de fecha para esos comentarios. Su procedencia está
en `facebook_comentarios_reincorporados.jsonl` junto a los registros históricos
de cada una de las cuatro semanas afectadas.

Para el 24 al 30 de marzo de 2025 se ejecutaron realmente los dos extractores
vigentes: se recuperaron 38 posts y 431 comentarios del periodo, sin reutilizar
las cuatro filas históricas fechadas en abril. El corpus de Facebook queda en
**10,027 registros: 1,626 posts y 8,401 comentarios**, con texto en las 83 semanas.
La auditoría actual de cobertura está en
`auditorias/reparacion_vacios_facebook_2026-11-09.json`.

`datos/radar_historico_reincorporado/facebook/<semana>/facebook_reincorporado.jsonl`
identifica las filas exactas autorizadas, sus fechas originales y su procedencia.
El procesador y el validador reconocen únicamente esas filas en su semana de
origen. No se relajan los filtros de cuentas, contenido, duplicados o vínculos;
las nuevas extracciones siguen exigiendo fechas verificables. No se inventan
fechas ni se presentan las semanas de procedencia como fechas certificadas.
La auditoría de esa reincorporación por fecha está en
`auditorias/reincorporacion_facebook_fechas_2026-11-06.json`.

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
validación ordinaria CSV ↔ TXT no se relaja para las nuevas extracciones;
el informe distingue las excepciones históricas de fecha de Facebook.
Los CSV vacíos se cuentan explícitamente en el resultado; no se ocultan como
semanas con actividad. El registro de esta comprobación está en
`auditorias/validacion_contratos_2026-10-20.json`.

Para exigir además contenido textual en todas las semanas procesadas:

```bash
PYTHONDONTWRITEBYTECODE=1 /home/emilio/anaconda3/envs/radar-v1/bin/python \
  scr/preprocesamiento/validar_homogeneidad_semanal.py \
  --require-same-weeks --accept-historical-media-txt --require-nonempty-text
```

El runner de extracción activa este control automáticamente: un TXT vacío se
reporta como cobertura incompleta, no como una ejecución semanal terminada.
