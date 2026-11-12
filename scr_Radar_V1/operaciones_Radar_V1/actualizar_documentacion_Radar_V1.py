#!/usr/bin/env python3
"""Actualiza documentación concisa y comprueba su correspondencia con cada commit."""
from __future__ import annotations
import argparse,ast,csv,hashlib,importlib.util,json,re,subprocess,sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[2]
DOCS='documentos_Radar_V1'
ARCH='ARQUITECTURA_CONTRATOS_PRODUCTOS_Radar_V1.md'

def git(root,*args):
    r=subprocess.run(['git',*args],cwd=root,capture_output=True)
    if r.returncode:raise ValueError(r.stderr.decode().strip())
    return r.stdout
def source_paths(root,staged=False):
    paths=git(root,'ls-files','--cached','-z').decode().split('\0') if staged else [str(p.relative_to(root)) for p in root.rglob('*.py') if 'trash_Radar_V1' not in p.parts and '.git' not in p.parts]
    return sorted(p for p in paths if p.endswith('.py') and (p.startswith(('scr_Radar_V1/','tests_Radar_V1/')) or p=='abrir_gui_orquestador_Radar_V1.py'))
def fingerprint(root,staged=False):
    h=hashlib.sha256()
    for name in source_paths(root,staged):
        raw=git(root,'show',':'+name) if staged else (root/name).read_bytes()
        h.update(name.encode()+b'\0'+raw+b'\0')
    return h.hexdigest()
def check_staged(root):
    changed=[p for p in git(root,'diff','--cached','--name-only','--diff-filter=ACMRD').decode().splitlines() if p]
    if not changed:return 0
    docs=[p for p in changed if p.startswith(DOCS+'/') and p.endswith('.md')]
    if not docs:raise ValueError('Este commit requiere documentación: ejecuta actualizar_documentacion_Radar_V1.py y prepara los .md afectados.')
    text=git(root,'show',':'+DOCS+'/'+ARCH).decode()
    if '<!-- source-fingerprint: '+fingerprint(root,True)+' -->' not in text:
        raise ValueError('La documentación preparada no corresponde al código preparado. Actualízala después de preparar el código y vuelve a preparar los .md.')
    return 0

def update(root,date_label):
    folder=root/DOCS;folder.mkdir(exist_ok=True)
    path=root/'scr_Radar_V1/compartido_Radar_V1/00_orquestador_general_Radar_V1.py'
    spec=importlib.util.spec_from_file_location('radar_documentation_catalog',path)
    cat=importlib.util.module_from_spec(spec);sys.modules[spec.name]=cat;spec.loader.exec_module(cat)
    scripts=[p for p in source_paths(root) if not p.startswith('tests_Radar_V1/')]
    tests=[p for p in source_paths(root) if p.startswith('tests_Radar_V1/')]
    table=root/'datos_Radar_V1/radar_indicadores_Radar_V1/tabla_analisis_ponderada_Radar_V1.csv'
    if table.exists():
        with table.open(encoding='utf-8-sig',newline='') as h:reader=csv.reader(h);header=next(reader);rows=sum(1 for _ in reader)
        table_status=f'{rows} filas y {len(header)} columnas'
    else:table_status='todavía no generada'
    lines=['# Radar V1: estructura, contratos, productos y control', '', 'Revisión: '+date_label+'. Documento de consulta del estado vigente; los registros de auditoría se conservan por separado.', '',
      '## Panel de control', '',
      'Abrir `abrir_gui_orquestador_Radar_V1.py`. Cada etapa tiene selección independiente, estado en pantalla y salida en la terminal en tiempo real. Se pueden preparar secuencias, simular sin descargas, ejecutar, detener y reiniciar desde una etapa elegida. El panel conserva el último estado y los registros de cada intento.', '',
      'El perfil histórico utiliza el corpus existente. La semana seleccionada controla extracción y procesamiento semanal; NLP mantiene el contrato actual de 83 semanas/cuatro fuentes. Abrir la GUI no inicia descargas: el flujo comienza al pulsar Ejecutar. Los botones Pruebas y Actualizar documentación también usan el motor de control.', '',
      '| Etapa | Entrada / operación | Programa | Estado |','|---|---|---|---|']
    for stage in cat.PIPELINES:
        lines.append('| '+stage.code+'. '+stage.label+' | '+stage.description+' | `'+str(stage.relative_runner)+'` | '+('Disponible' if cat.stage_status(stage)[0] else 'Pendiente de implementar')+' |')
    lines+=['', 'Simular comprueba programas y entradas disponibles y registra el plan. Si una entrada la produciría una etapa previa, se señala como prevista. La simulación no certifica descargas, sesiones remotas ni resultados estadísticos. Una etapa futura no implementada se bloquea; no se informa como terminada.', '',
      '## Estructura y funciones', '', '| Carpeta | Responsabilidad |','|---|---|',
      '| `scr_Radar_V1/compartido_Radar_V1/` | Contratos, rutas, nombres, catálogo y motor del panel. |',
      '| `scr_Radar_V1/extraccion_Radar_V1/` | Descarga por fuente. Facebook depende de posts antes de comentarios. |',
      '| `scr_Radar_V1/preprocesamiento_Radar_V1/` | Cuatro procesadores CSV, promoción común y validación. |',
      '| `scr_Radar_V1/nlp_Radar_V1/` | Constructor único de indicadores y notebook de referencia preservado. |',
      '| `scr_Radar_V1/operaciones_Radar_V1/` | Balance, partición, inspección, selección y mantenimiento documental. |',
      '| `tests_Radar_V1/` | Pruebas locales, incluido el motor y los controles de la GUI. |',
      '| `datos_Radar_V1/` | Corpus, diccionarios, indicadores, particiones y resultados; archivos/carpetas sellados. |',
      '| `documentos_Radar_V1/auditorias_Radar_V1/` | Sólo operaciones realmente realizadas o simulaciones identificadas como tales. |',
      '| `state/ejecuciones_Radar_V1/` | Estados y terminal persistente de cada ejecución. |',
      '| `trash_Radar_V1/` | Respaldos recuperables con `_historico_Radar_V1`; fuera de la ejecución. |','',
      'Cada README se llama `README_NOMBRE_DE_CARPETA.md`. Los scripts, datasets y carpetas de trabajo llevan `_Radar_V1`; Git, `.env` y el estado autenticado de X conservan sus nombres técnicos. Los proyectos externos no se modifican.', '',
      '## Scripts vigentes y sus vínculos', '', '| Script | Función | Importa módulos locales |', '|---|---|---|']
    modules={Path(p).stem for p in scripts}
    for name in scripts:
        tree=ast.parse((root/name).read_text());purpose=(ast.get_docstring(tree) or '').split('\n')[0].replace('|','/')
        imports=sorted({n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom) and n.module in modules})
        lines.append('| `'+name+'` | '+purpose+' | '+', '.join('`'+p+'`' for p in imports)+' |')
    lines+=['', 'Cargar/importar utiliza funciones; invocar ejecuta un proceso; una dependencia de archivos significa que una etapa consume productos de otra. El panel encadena las operaciones existentes y puede ejecutarlas por separado. No hay un segundo constructor NLP.', '',
      '## Contratos de extracción y texto', '', '| Fuente | Columnas canónicas |', '|---|---|']
    for name in ['youtube','twitter','facebook','medios']:
        file=root/f'scr_Radar_V1/compartido_Radar_V1/{name}_data_contract_Radar_V1.py'
        constants={}
        for n in ast.parse(file.read_text()).body:
            if isinstance(n,ast.Assign):
                try:constants[n.targets[0].id]=ast.literal_eval(n.value)
                except (ValueError,AttributeError,TypeError):pass
        key={'youtube':'YOUTUBE_OUTPUT_COLUMNS','twitter':'TWITTER_OUTPUT_COLUMNS','facebook':'FACEBOOK_RAW_COLUMNS','medios':'MEDIOS_OUTPUT_COLUMNS'}[name]
        lines.append('| '+name+' | `'+', '.join(constants[key])+'` |')
    lines+=['', 'Semana nueva: lunes–domingo, con publicación dentro del intervalo. Los cuatro procesadores tienen nombres `procesar_FUENTE_semanal_Radar_V1.py`. YouTube usa sus cuatro consultas aprobadas; Twitter usa las dos cuentas y sus consultas from/to/menciones, incluidas respuestas.', '',
      '**Facebook histórico (C5):** la incorporación fue una reparación realizada una vez. El registro sólo permite reconocer filas históricas exactas que ya están en el CSV. El proceso semanal nuevo no lo carga ni agrega filas. La reproducción explícita del histórico requiere `--historical-corpus`. El validador consulta la evidencia para comprobar el material ya incorporado; no lo reinserta ni inventa fechas.', '',
      '**Medios:** el extractor nuevo escribe CSV; `procesar_medios_semanal_Radar_V1.py` normaliza ese CSV con su contrato; `promover_csv_a_texto_Radar_V1.py` convierte título+contenido a TXT. El histórico disponible sólo en TXT se conserva como excepción documentada, sin reconstruir metadatos perdidos.', '',
      '**TXT (C7):** letras ASCII minúsculas, acentos eliminados, ñ→n, sin URLs, números ni signos. Redes: una fila textual útil por línea. Medios: título+contenido en segmentos de hasta 30 palabras. El CSV se conserva.', '',
      '## Productos y consumidores', '', '| Producto | Lo produce | Lo consume |','|---|---|---|',
      '| `datos_Radar_V1/radar_semanal_extraido_Radar_V1/` | Extractores | Procesadores de cada fuente |',
      '| `datos_Radar_V1/radar_semanal_procesado_Radar_V1/` | Procesadores y promotor | Validación, balance y NLP |',
      '| `datos_Radar_V1/radar_indicadores_Radar_V1/` | Constructor NLP | Partición y soporte de selección |',
      '| `datos_Radar_V1/radar_modelado_Radar_V1/` | Particionador | Inspector y selector: sólo 56 iniciales |',
      '| `datos_Radar_V1/radar_analisis_Radar_V1/` | Balance, inspector y selector | Revisión metodológica; modelado aún pendiente |',
      '| Tabla para tablero, tablero y reporte | Productores todavía no implementados | Etapas presentes y bloqueadas en GUI |', '',
      'La tabla principal tiene '+table_status+': tres metadatos, polaridad Original y veinte candidatos temáticos. No contiene las 13 semanas reservadas. El completo de 83 semanas está en `archivo_Radar_V1/`. Todas las hojas de datos terminan en `_Radar_V1` antes de su extensión; cada carpeta de datos también lleva el sello.', '',
      '## NLP y control temporal', '',
      'NLP incorpora diccionarios/stoplists/exclusiones autorizados, unigramas y n-gramas, polaridad Original, temas, intensidad por mil palabras y presencia en segmentos de 30 palabras. Integra tasas por fuente con ponderación intermedia alpha=0.5: raíz del volumen de palabras, calibrada sólo con 56 iniciales. Se reutilizan diccionarios, código y metodología anteriores, nunca su corpus ni valores calculados.', '',
      'No hay Etiquetado, MA5 ni lags adicionales de X. Las regresiones relacionan X(t) con Y(t+1..4) dentro de las 56 iniciales, con 55/54/53/52 pares. Las 14 de prueba y 13 de verificación no se utilizan para seleccionar columnas. Pesos, escalas y ranking se reajustan por prefijo en la selección. El resultado exploratorio no constituye un modelo productivo.', '',
      '## Repetición, fallos y auditorías', '',
      'El motor verifica hashes antes de reutilizar tablas, particiones y análisis existentes. Si no corresponden a las entradas, detiene la operación. Renovar TXT/análisis con respaldo guarda los TXT anteriores sin mover sus CSV y archiva las salidas exclusivas del análisis; si falla la operación, restaura los productos anteriores. Un fallo bloquea las etapas dependientes. Se puede reiniciar desde la sección elegida sin repetir las anteriores.', '',
      'Cada intento conserva estados y log en `state/ejecuciones_Radar_V1/`. Las auditorías nuevas se guardan en `auditorias_Radar_V1/ejecuciones_Radar_V1/` y actualizan su referencia `control_ETAPA_actual_Radar_V1.json`. La validación del corpus guarda además su resumen propio. Los registros antiguos no se reescriben como si se acabaran de ejecutar.', '',
      '## Accesos y nombres técnicos', '',
      '- `.env`: nombres `APIFY_TOKEN` y `YOUTUBE_API_KEY`; los valores no se publican en documentos.',
      '- `state/x_state.json`: estado autenticado de X/Playwright. No hay estado local de sesión de Facebook ni YouTube en los extractores vigentes: usan Apify y la clave de YouTube, respectivamente.',
      '- `.git/`: control de versiones; `.agents/`, `.codex/`, `.aws/`, `.conda_envs/`: directorios internos locales. `.aws/` no almacena las claves de estas extracciones.',
      '- `environment-radar-v1_Radar_V1.yml` declara el entorno; la resolución del intérprete está en `radar_paths_Radar_V1.py`.', '',
      '## Documentación y cambios', '',
      'Antes de cada commit, ejecutar `actualizar_documentacion_Radar_V1.py` y preparar los .md afectados. El hook comprueba que la documentación preparada corresponde al código preparado. El historial breve está en `CAMBIOS_Radar_V1.md`; este documento describe el estado actual y evita inventarios extensos duplicados.', '',
      f'Inventario actual: {len(scripts)} scripts, {len(tests)} archivos de pruebas. Las pruebas y auditorías se ejecutan desde el panel; su resultado se registra sólo después de realizarlas.', '']
    (folder/ARCH).write_text('\n'.join(lines))
    gui=['# Uso del panel maestro Radar V1','', '1. Abrir `abrir_gui_orquestador_Radar_V1.py`.','2. Elegir perfil histórico o semanal y fuentes.','3. Elegir etapas: Corpus existente, Todas disponibles o selección individual.','4. Pulsar Simular y comprobar para revisar el plan sin descargas.','5. Pulsar Ejecutar seleccionadas; seguir cada estado y la terminal en vivo.','6. Detener cuando sea necesario; Preparar reinicio desde la etapa elegida permite continuar sin repetir lo anterior.','7. Pruebas del panel y pipeline ejecuta la suite local. Actualizar documentación renueva el estado documental.','', 'Las etapas futuras aparecen como pendientes y no ejecutables. Abrir el panel no inicia una extracción automáticamente. El perfil histórico no implica reincorporar registros de Facebook; la reproducción de CSV histórico es una operación explícita.','', 'La opción de renovar TXT/análisis guarda un respaldo antes de reemplazar salidas y las restaura si falla la operación. No modifican la división 56/14/13 ni autorizan abrir verificación para seleccionar columnas.','']
    (folder/'GUI_ORQUESTADOR_RADAR_Radar_V1.md').write_text('\n'.join(gui))
    for p in folder.glob('*.md'):
        text=p.read_text();text=re.sub(r'\n?<!-- source-fingerprint: [0-9a-f]+ -->\n?','\n',text)
        p.write_text(text.rstrip()+'\n\n<!-- source-fingerprint: '+fingerprint(root)+' -->\n')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check-staged',action='store_true');p.add_argument('--check',action='store_true');p.add_argument('--date',default=datetime.now(ZoneInfo('America/Mexico_City')).date().isoformat())
    args=p.parse_args()
    try:
        if args.check_staged:return check_staged(ROOT)
        if args.check:
            if '<!-- source-fingerprint: '+fingerprint(ROOT)+' -->' not in (ROOT/DOCS/ARCH).read_text():raise ValueError('Documentación desactualizada')
        else:update(ROOT,args.date);print('Documentación actualizada con rutas, catálogo y contratos vigentes.')
    except (ValueError,FileNotFoundError) as e:print(str(e),file=sys.stderr);return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
